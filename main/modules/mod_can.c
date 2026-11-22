/**
 * @file mod_can.c
 * @brief CAN FD 模块实现 (0x10-0x1F)
 *
 * 管理 MCP2518FD CAN FD 控制器：
 * - CAN_OPEN (0x10): 打开通道，配置 SPI + 过滤器 + 中断
 * - CAN_CLOSE (0x11): 关闭通道
 * - CAN_CONFIG (0x12): 波特率/标志/FD 配置
 * - CAN_SEND (0x13): 发送帧 (TXQ)
 * - CAN_RECV (0x14): 接收帧事件上报
 * - CAN_FILTER (0x15): 单个过滤器配置
 * - CAN_STATUS (0x16): 状态查询
 * - CAN_BUS_EVENT (0x17): 总线状态变化上报
 * - CAN_ERROR_EVENT (0x18): 错误帧详情上报 (500ms 限速)
 * - CAN_SLEEP (0x19): 进入休眠
 * - CAN_WAKEUP (0x1A): 唤醒
 * - CAN_FILTER_BATCH (0x1B): 批量过滤器配置
 *
 * 中断流程：
 *   GPIO39 下降沿 ISR → can_event_queue → can_int_task (SPI 读 FIFO)
 *   → can_rx_queue → can_rx_proc (UBCP 事件上报)
 */

#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "modules/mod_can.h"
#include "modules/mcp2518fd.h"
#include "core/msg_bus.h"
#include "transport/mcp_transport.h"
#include "core/seq_num.h"
#include "core/topology.h"
#include "core/device_profile.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_can";

/* ========================================================================
 * 协议常量
 * ======================================================================== */

#define CAN_CHANNEL_ID              UBCP_CH_CAN_EXT1   /* 0x03 */

/* CanID 位定义 */
#define CANID_EXT                   (1u << 31)
#define CANID_RTR                   (1u << 30)
#define CANID_FD                    (1u << 29)
#define CANID_BRS                   (1u << 28)
#define CANID_ONESHOT               (1u << 27)

/* Mode */
#define CAN_MODE_NORMAL             0x00
#define CAN_MODE_LISTEN_ONLY        0x01
#define CAN_MODE_LOOPBACK           0x02

/* FilterType */
#define CAN_FILTER_TYPE_STD         0x00
#define CAN_FILTER_TYPE_EXT         0x01
#define CAN_FILTER_TYPE_BOTH        0x02

/* RxFlags */
#define CAN_RXFLAG_FRAME_LOST       (1 << 0)
#define CAN_RXFLAG_FIFO_OVERFLOW    (1 << 1)
#define CAN_RXFLAG_ERROR_FRAME      (1 << 2)
#define CAN_RXFLAG_FDBRS            (1 << 3)
#define CAN_RXFLAG_FDESI            (1 << 4)

/* ConfigFlags */
#define CAN_CFG_AUTO_RETRANSMIT     (1 << 0)
#define CAN_CFG_AUTO_BUSOFF         (1 << 1)
#define CAN_CFG_FD_MODE             (1 << 2)
#define CAN_CFG_FDBRS_DEFAULT       (1 << 3)

/* 错误事件限速 */
#define CAN_ERROR_THROTTLE_MS       500

/* FIFO 深度 */
#define CAN_TXQ_SIZE                8
#define CAN_RX_FIFO1_SIZE           16
#define CAN_RX_FIFO2_SIZE           4

/* ========================================================================
 * 通道状态
 * ======================================================================== */

typedef struct {
    uint32_t session_id;
    uint32_t id;            /* UBCP CanID (含标志位) */
    uint8_t  dlc;           /* 实际数据字节数 */
    uint8_t  data[64];
    uint8_t  rx_flags;
} can_rx_item_t;

/** 软件过滤器模型 */
typedef struct {
    bool     enabled;
    uint32_t mask;
    uint32_t code;
    uint8_t  ftype;         /* 0=std, 1=ext, 2=both */
    uint8_t  fifo;          /* 1 或 2 */
} can_filter_cfg_t;

typedef struct {
    bool        is_open;
    uint8_t     mode;               /* 当前工作模式 */
    uint8_t     mode_snapshot;      /* 休眠前模式 */
    bool        sleeping;
    uint8_t     config_flags;
    uint8_t     fd_baud_index;
    uint8_t     baud_index;
    uint32_t    tx_count;
    uint32_t    rx_count;
    uint16_t    lost_count;
    uint16_t    crc_err_count;
    uint16_t    form_err_count;
    uint16_t    ack_err_count;
    uint16_t    bit_err_count;
    uint16_t    stuff_err_count;
    uint32_t    last_bd1;           /* 上次 BDIAG1 快照 */
    uint32_t    last_error_ts;      /* 上次错误事件时间 */
    uint8_t     last_error_type;    /* 上次错误类型 */
    uint8_t     bus_state;          /* 0=active,1=passive,2=busoff,3=recovering */
    uint8_t     prev_bus_state;
    uint8_t     rx_pending_overflow;/* 待上报的溢出标志 */
    can_filter_cfg_t filters[32];

    QueueHandle_t  event_queue;     /* GPIO ISR → can_int_task */
    QueueHandle_t  rx_queue;        /* can_int_task → can_rx_proc */
    TaskHandle_t   int_task;        /* can_int_task 句柄 */
    TaskHandle_t   rx_proc_task;    /* can_rx_proc 句柄 */
    bool           tasks_running;
} can_channel_t;

static can_channel_t s_can = {
    .mode          = CAN_MODE_NORMAL,
    .baud_index    = 0x06,
    .fd_baud_index = 0x00,
    .config_flags  = 0x03,
    .bus_state     = 0,
    .prev_bus_state = 0,
};

/* ========================================================================
 * 帧发送辅助
 * ======================================================================== */

static esp_err_t send_status_resp(const ubcp_frame_t *req, uint8_t status)
{
    return msg_bus_send_status_response(req, status);
}

/* ========================================================================
 * 过滤器应用
 * ======================================================================== */

/**
 * @brief 将一个软件过滤器写入硬件 (BOTH 使用两个硬件过滤器)
 */
static void apply_one_filter(const can_filter_cfg_t *cfg, uint8_t idx)
{
    if (cfg->ftype == CAN_FILTER_TYPE_EXT) {
        uint16_t sid = (uint16_t)((cfg->code >> 18) & 0x7FF);
        uint32_t eid = cfg->code & 0x3FFFF;
        uint16_t msid = (uint16_t)((cfg->mask >> 18) & 0x7FF);
        uint32_t meid = cfg->mask & 0x3FFFF;

        mcp2518fd_filter_object_config(idx, sid, eid, true);
        mcp2518fd_filter_mask_config(idx, msid, meid, true);
        mcp2518fd_filter_to_fifo_link(idx, cfg->fifo, true);
        return;
    }

    /* 标准帧过滤器 (STD 或 BOTH 的标准部分) */
    mcp2518fd_filter_object_config(idx,
                                   (uint16_t)(cfg->code & 0x7FF),
                                   0,
                                   false);
    mcp2518fd_filter_mask_config(idx,
                                 (uint16_t)(cfg->mask & 0x7FF),
                                 0,
                                 cfg->ftype != CAN_FILTER_TYPE_BOTH);
    mcp2518fd_filter_to_fifo_link(idx, cfg->fifo, true);

    /* BOTH 类型: 追加扩展帧过滤器 (idx+1) */
    if (cfg->ftype == CAN_FILTER_TYPE_BOTH && idx < 31) {
        uint8_t j = idx + 1;
        uint16_t sid = (uint16_t)((cfg->code >> 18) & 0x7FF);
        uint32_t eid = cfg->code & 0x3FFFF;
        uint16_t msid = (uint16_t)((cfg->mask >> 18) & 0x7FF);
        uint32_t meid = cfg->mask & 0x3FFFF;

        mcp2518fd_filter_object_config(j, sid, eid, true);
        mcp2518fd_filter_mask_config(j, msid, meid, true);
        mcp2518fd_filter_to_fifo_link(j, cfg->fifo, true);
    }
}

/**
 * @brief 将软件过滤器模型同步到硬件
 */
static void apply_filters(void)
{
    bool any_enabled = false;
    for (int i = 0; i < 32; i++) {
        if (s_can.filters[i].enabled) {
            any_enabled = true;
            break;
        }
    }

    /* 先禁用所有硬件过滤器 */
    for (int i = 0; i < 32; i++) {
        mcp2518fd_filter_to_fifo_link(i, MCP2518FD_CH_FIFO1, false);
    }

    if (!any_enabled) {
        /* 默认接受所有 (filter0, mask=0) */
        mcp2518fd_filter_object_config(0, 0, 0, false);
        mcp2518fd_filter_mask_config(0, 0, 0, false);
        mcp2518fd_filter_to_fifo_link(0, MCP2518FD_CH_FIFO1, true);
        return;
    }

    for (int i = 0; i < 32; i++) {
        if (s_can.filters[i].enabled) {
            apply_one_filter(&s_can.filters[i], (uint8_t)i);
        }
    }
}

/* ========================================================================
 * 中断处理任务
 * ======================================================================== */

static void can_send_bus_event(uint8_t state, uint8_t prev,
                               uint8_t tec, uint8_t rec)
{
    uint8_t payload[4];
    payload[0] = state;
    payload[1] = prev;
    payload[2] = tec;
    payload[3] = rec;

    ubcp_frame_t evt;
    ubcp_frame_make_event(&evt, UBCP_CMD_CAN_BUS_EVENT, CAN_CHANNEL_ID,
                          seq_num_next());
    evt.payload     = payload;
    evt.payload_len = sizeof(payload);
    msg_bus_send_frame(&evt);
}

static void can_send_error_event(uint8_t err_type, uint8_t tec, uint8_t rec)
{
    uint8_t payload[4];
    payload[0] = err_type;
    payload[1] = tec;
    payload[2] = rec;
    payload[3] = 0xFF;   /* ErrorLocation: 未知 */

    ubcp_frame_t evt;
    ubcp_frame_make_event(&evt, UBCP_CMD_CAN_ERROR_EVENT, CAN_CHANNEL_ID,
                          seq_num_next());
    evt.payload     = payload;
    evt.payload_len = sizeof(payload);
    msg_bus_send_frame(&evt);
}

/**
 * @brief 计算总线状态 (0=active, 1=passive, 2=busoff)
 */
static uint8_t compute_bus_state(uint8_t tec, uint8_t rec)
{
    uint8_t err_state = mcp2518fd_error_state_get();
    if (err_state & MCP2518FD_ERR_TXBO) {
        return 2;
    }
    if (tec >= 128 || (err_state & (MCP2518FD_ERR_TXPASSIVE |
                                    MCP2518FD_ERR_RXPASSIVE))) {
        return 1;
    }
    return 0;
}

/**
 * @brief 处理中断 (由 can_int_task 调用)
 */
static void process_interrupt(void)
{
    if (s_can.sleeping) {
        return;
    }

    uint16_t flags = 0;
    if (mcp2518fd_int_flags_get(&flags) != ESP_OK) {
        return;
    }
    if (flags == 0) {
        return;
    }

    /* 错误事件 (限速) */
    if (flags & MCP2518FD_INT_CERRIF) {
        uint32_t bd0 = 0, bd1 = 0;
        mcp2518fd_bus_diagnostics_get(&bd0, &bd1);

        uint32_t new_bd = bd1 & ~s_can.last_bd1;
        s_can.last_bd1 = bd1;

        /* 更新错误计数 */
        if (new_bd & (MCP2518FD_BD_NCRC | MCP2518FD_BD_DCRC)) {
            s_can.crc_err_count++;
        }
        if (new_bd & (MCP2518FD_BD_NFORM | MCP2518FD_BD_DFORM)) {
            s_can.form_err_count++;
        }
        if (new_bd & (MCP2518FD_BD_NACK | MCP2518FD_BD_DACK)) {
            s_can.ack_err_count++;
        }
        if (new_bd & (MCP2518FD_BD_NBIT0 | MCP2518FD_BD_DBIT0 |
                      MCP2518FD_BD_NBIT1 | MCP2518FD_BD_DBIT1)) {
            s_can.bit_err_count++;
        }
        if (new_bd & (MCP2518FD_BD_NSTUFF | MCP2518FD_BD_DSTUFF)) {
            s_can.stuff_err_count++;
        }

        /* 组装 ErrorType */
        uint8_t err_type = 0;
        if (new_bd & (MCP2518FD_BD_NCRC | MCP2518FD_BD_DCRC)) err_type |= 0x01;
        if (new_bd & (MCP2518FD_BD_NFORM | MCP2518FD_BD_DFORM)) err_type |= 0x02;
        if (new_bd & (MCP2518FD_BD_NACK | MCP2518FD_BD_DACK)) err_type |= 0x04;
        if (new_bd & (MCP2518FD_BD_NBIT1 | MCP2518FD_BD_DBIT1)) err_type |= 0x08;
        if (new_bd & (MCP2518FD_BD_NBIT0 | MCP2518FD_BD_DBIT0)) err_type |= 0x10;
        if (new_bd & (MCP2518FD_BD_NSTUFF | MCP2518FD_BD_DSTUFF)) err_type |= 0x20;

        uint8_t tec = 0, rec = 0;
        mcp2518fd_tec_rec_get(&tec, &rec);
        if (rec >= 96) err_type |= 0x40;
        if (new_bd & MCP2518FD_BD_TXBO) err_type |= 0x80;

        if (err_type) {
            uint32_t now = (uint32_t)(esp_timer_get_time() / 1000);
            if (now - s_can.last_error_ts >= CAN_ERROR_THROTTLE_MS ||
                s_can.last_error_type != err_type) {
                can_send_error_event(err_type, tec, rec);
                s_can.last_error_ts = now;
                s_can.last_error_type = err_type;
            }
        }
    }

    /* 总线状态变化 */
    {
        uint8_t tec = 0, rec = 0;
        mcp2518fd_tec_rec_get(&tec, &rec);
        uint8_t state = compute_bus_state(tec, rec);
        if (state != s_can.prev_bus_state) {
            can_send_bus_event(state, s_can.prev_bus_state, tec, rec);
            s_can.bus_state = state;
            s_can.prev_bus_state = state;
        }
    }

    /* 接收 FIFO 溢出标志 */
    if (flags & MCP2518FD_INT_RXOVIF) {
        s_can.rx_pending_overflow = 1;
        s_can.lost_count++;
    }

    /* 清除中断标志 (写入 0 清除) */
    mcp2518fd_int_flags_clear(flags);
}

/**
 * @brief 从 FIFO 读取并投递到接收队列
 */
static void drain_rx_fifo(uint8_t channel)
{
    if (s_can.sleeping || !s_can.is_open) {
        return;
    }

    while (mcp2518fd_rx_not_empty(channel)) {
        uint32_t session = mcp_transport_session_id();
        mcp2518fd_rx_obj_t obj;
        uint8_t data_len = 0;
        if (mcp2518fd_rx_read(channel, &obj, &data_len) != ESP_OK) {
            break;
        }

        can_rx_item_t item;
        memset(&item, 0, sizeof(item));

        /* 解码 CanID */
        uint8_t ide  = (obj.ctrl >> 4) & 1;
        uint8_t rtr  = (obj.ctrl >> 5) & 1;
        uint8_t brs  = (obj.ctrl >> 6) & 1;
        uint8_t fdf  = (obj.ctrl >> 7) & 1;
        uint8_t esi  = (obj.ctrl >> 8) & 1;
        uint16_t sid = (uint16_t)(obj.id & 0x7FF);
        uint32_t eid = (obj.id >> 11) & 0x3FFFF;

        uint32_t can_id = 0;
        if (ide) {
            can_id = CANID_EXT | ((uint32_t)((sid << 18) | eid) & 0x1FFFFFFF);
        } else {
            can_id = (uint32_t)sid;
        }
        if (rtr) can_id |= CANID_RTR;
        if (fdf) can_id |= CANID_FD;
        if (brs && !ide) can_id |= CANID_BRS;

        item.session_id = session;
        item.id   = can_id;
        item.dlc  = data_len;
        memcpy(item.data, obj.data, data_len);

        /* RxFlags */
        item.rx_flags = 0;
        if (brs) item.rx_flags |= CAN_RXFLAG_FDBRS;
        if (esi) item.rx_flags |= CAN_RXFLAG_FDESI;
        if (s_can.rx_pending_overflow) {
            item.rx_flags |= CAN_RXFLAG_FIFO_OVERFLOW | CAN_RXFLAG_FRAME_LOST;
            s_can.rx_pending_overflow = 0;
        }

        if (xQueueSend(s_can.rx_queue, &item, pdMS_TO_TICKS(20)) != pdTRUE) {
            s_can.lost_count++;
        }
        s_can.rx_count++;
    }
}

/**
 * @brief CAN 中断任务: 等待 GPIO39 事件 → 读 FIFO
 */
static void can_int_task_fn(void *arg)
{
    HEX_LOGI(TAG, "CAN 中断任务启动");

    while (s_can.tasks_running) {
        uint32_t dummy = 0;
        if (xQueueReceive(s_can.event_queue, &dummy, pdMS_TO_TICKS(100)) == pdTRUE) {
            process_interrupt();
        }
        /* 超时兜底: 主动检查 FIFO 是否有数据 (防止边沿丢失) */
        drain_rx_fifo(MCP2518FD_CH_FIFO1);
        drain_rx_fifo(MCP2518FD_CH_FIFO2);
    }

    HEX_LOGI(TAG, "CAN 中断任务退出");
    s_can.int_task = NULL;
    vTaskDelete(NULL);
}

/**
 * @brief CAN 接收上报任务: 从队列取帧 → UBCP 事件
 */
static void can_rx_proc_fn(void *arg)
{
    HEX_LOGI(TAG, "CAN 接收上报任务启动");

    while (s_can.tasks_running) {
        can_rx_item_t item;
        if (xQueueReceive(s_can.rx_queue, &item, pdMS_TO_TICKS(100)) != pdTRUE) {
            continue;
        }

        uint8_t payload[4 + 1 + 64 + 1 + 4];
        uint16_t len = 0;

        /* CanID u32 BE */
        payload[0] = (uint8_t)(item.id >> 24);
        payload[1] = (uint8_t)(item.id >> 16);
        payload[2] = (uint8_t)(item.id >> 8);
        payload[3] = (uint8_t)(item.id & 0xFF);
        len = 4;

        /* DLC = 实际字节数 */
        payload[len++] = item.dlc;

        /* Data */
        memcpy(&payload[len], item.data, item.dlc);
        len += item.dlc;

        /* RxFlags */
        payload[len++] = item.rx_flags;

        /* RxTimestamp u32 BE */
        uint32_t ts = (uint32_t)esp_timer_get_time();
        payload[len++] = (uint8_t)(ts >> 24);
        payload[len++] = (uint8_t)(ts >> 16);
        payload[len++] = (uint8_t)(ts >> 8);
        payload[len++] = (uint8_t)(ts & 0xFF);

        ubcp_frame_t evt;
        ubcp_frame_make_event(&evt, UBCP_CMD_CAN_RECV, CAN_CHANNEL_ID,
                              seq_num_next());
        evt.payload     = payload;
        evt.payload_len = len;
        evt.session_id = item.session_id;
        msg_bus_send_frame(&evt);
    }

    HEX_LOGI(TAG, "CAN 接收上报任务退出");
    s_can.rx_proc_task = NULL;
    vTaskDelete(NULL);
}

/* ========================================================================
 * GPIO 中断
 * ======================================================================== */

static void can_gpio_isr(void *arg)
{
    BaseType_t xHigher = pdFALSE;
    uint32_t dummy = 1;
    if (s_can.event_queue) {
        xQueueSendFromISR(s_can.event_queue, &dummy, &xHigher);
    }
    if (xHigher) {
        portYIELD_FROM_ISR();
    }
}

static esp_err_t setup_gpio_isr(void)
{
    gpio_config_t io = {
        .pin_bit_mask = (1ULL << profile_pin(SIG_CAN_INT)),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,   /* GPIO39 为 input-only，无内部上拉，外部已有 10kΩ 上拉 */
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_NEGEDGE,
    };
    esp_err_t err = gpio_config(&io);
    if (err != ESP_OK) {
        return err;
    }

    /* 安装 ISR 服务 (幂等) */
    static bool isr_installed = false;
    if (!isr_installed) {
        err = gpio_install_isr_service(0);
        if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        profile_driver_failed();
            return err;
        }
        isr_installed = true;
    }

    return gpio_isr_handler_add(profile_pin(SIG_CAN_INT), can_gpio_isr, NULL);
}

/* ========================================================================
 * 硬件初始化
 * ======================================================================== */

static esp_err_t hw_init(void)
{
    esp_err_t err;

    err = mcp2518fd_init();
    if (err != ESP_OK) {
        return err;
    }

    /* 复位 */
    err = mcp2518fd_reset();
    if (err != ESP_OK) {
        return err;
    }
    vTaskDelay(pdMS_TO_TICKS(20));

    /* 使能振荡器并等待就绪 (OSCDIS=0, OSCRDY=1) */
    err = mcp2518fd_osc_enable();
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "振荡器使能失败 (0x%x)", err);
        return err;
    }

    /* 读取器件 ID 验证 SPI 通信 */
    uint8_t dev_id = 0;
    mcp2518fd_get_dev_id(&dev_id);
    HEX_LOGI(TAG, "MCP2518FD DEVID=0x%02X", dev_id);

    /* 读取 OSC 寄存器，检测系统时钟配置 */
    {
        uint32_t osc = 0;
        mcp2518fd_read_word(MCP2518FD_REG_OSC, &osc);
        HEX_LOGI(TAG, "OSC=0x%08X (PLLEN=%u SCLKDIV=%u PLLRDY=%u OSCRDY=%u)",
                 (unsigned)osc,
                 (unsigned)((osc >> 0) & 1),
                 (unsigned)((osc >> 4) & 1),
                 (unsigned)((osc >> 8) & 1),
                 (unsigned)((osc >> 10) & 1));
    }

    /* 配置模式 (复位后默认) */
    mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);

    /* 配置 CiCON: ISO CRC 使能, 无 TEF, TXQ 使能 */
    uint32_t con = (1 << 5);              /* ISOCRCEN */
    /* ProtocolExceptionEventDisable=1 (bit6), TXQEN=1 (bit20) */
    con |= (1 << 6) | (1 << 20);
    /* RequestOpMode=Config */
    con |= (MCP2518FD_MODE_CONFIG << 24);
    err = mcp2518fd_write_word(MCP2518FD_REG_CiCON, con);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(5));

    /* 默认位时序: 500k + 无 FD */
    const mcp2518fd_nom_timing_t *nom =
        mcp2518fd_nom_timing_get(s_can.baud_index);
    if (nom) {
        err = mcp2518fd_bit_time_config(nom, NULL);
        if (err != ESP_OK) return err;
    }
    vTaskDelay(pdMS_TO_TICKS(5));

    /* TXQ 配置: 8 帧, 64 字节 */
    err = mcp2518fd_txq_config(CAN_TXQ_SIZE, 64, 0);
    if (err != ESP_OK) return err;

    /* RX FIFO1: 16 帧, 64 字节 */
    err = mcp2518fd_rx_fifo_config(MCP2518FD_CH_FIFO1, CAN_RX_FIFO1_SIZE, 64);
    if (err != ESP_OK) return err;

    /* RX FIFO2: 4 帧, 64 字节 */
    err = mcp2518fd_rx_fifo_config(MCP2518FD_CH_FIFO2, CAN_RX_FIFO2_SIZE, 64);
    if (err != ESP_OK) return err;
    vTaskDelay(pdMS_TO_TICKS(5));

    /* 默认过滤器: 接受所有 */
    s_can.last_bd1 = 0;
    for (int i = 0; i < 32; i++) {
        s_can.filters[i].enabled = false;
    }
    apply_filters();

    /* 使能收发器待机控制 (XSTBY → ATA6563 STBY 低电平) */
    err = mcp2518fd_xstby_enable();
    if (err != ESP_OK) {
        HEX_LOGW(TAG, "XSTBY 使能失败 (0x%x)", err);
    }

    /* 回读 IOCON 验证 XSTBY */
    {
        uint32_t iocon = 0;
        mcp2518fd_read_word(MCP2518FD_REG_IOCON, &iocon);
        HEX_LOGI(TAG, "IOCON=0x%08X (XSTBYEN=%u TRIS0=%u LAT0=%u PM0=%u)",
                 (unsigned)iocon,
                 (unsigned)((iocon >> 6) & 1),
                 (unsigned)((iocon >> 0) & 1),
                 (unsigned)((iocon >> 8) & 1),
                 (unsigned)((iocon >> 24) & 1));
    }

    return ESP_OK;
}

static esp_err_t hw_set_mode(uint8_t mode)
{
    uint8_t hw_mode;
    switch (mode) {
    case CAN_MODE_NORMAL:
        hw_mode = MCP2518FD_MODE_NORMAL;
        break;
    case CAN_MODE_LISTEN_ONLY:
        hw_mode = MCP2518FD_MODE_LISTEN_ONLY;
        break;
    case CAN_MODE_LOOPBACK:
        hw_mode = MCP2518FD_MODE_INTERNAL_LOOP;
        break;
    default:
        return ESP_ERR_INVALID_ARG;
    }

    /* 模式切换前确保 TX 排空，避免残留报文干扰 */
    mcp2518fd_txq_wait_empty(500);

    esp_err_t err = mcp2518fd_opmode_select(hw_mode);
    if (err != ESP_OK) {
        return err;
    }

    /* 等待模式切换完成 (轮询 OPMOD，超时 100ms) */
    for (int i = 0; i < 100; i++) {
        if (mcp2518fd_opmode_get() == hw_mode) {
            vTaskDelay(pdMS_TO_TICKS(10));
            return ESP_OK;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
    HEX_LOGW(TAG, "模式切换超时: req=%u OPMOD=%u",
             hw_mode, mcp2518fd_opmode_get());
    return ESP_ERR_TIMEOUT;
}

/* ========================================================================
 * 命令处理
 * ======================================================================== */

/**
 * @brief CAN_OPEN (0x10)
 */
static void stop_workers(void)
{
    s_can.tasks_running = false;
    while (s_can.int_task || s_can.rx_proc_task) vTaskDelay(pdMS_TO_TICKS(10));
    if (s_can.event_queue) { vQueueDelete(s_can.event_queue); s_can.event_queue = NULL; }
    if (s_can.rx_queue) { vQueueDelete(s_can.rx_queue); s_can.rx_queue = NULL; }
}

static void handle_can_open(const ubcp_frame_t *req)
{
    /* 校验通道 */
    const ubcp_route_entry_t *route = topology_find(req->channel_id);
    if (!route) {
        send_status_resp(req, UBCP_ERR_CHANNEL_INVALID);
        return;
    }
    if (route->device_type != UBCP_DEV_TYPE_CAN) {
        send_status_resp(req, UBCP_ERR_TYPE_MISMATCH);
        return;
    }

    if (s_can.is_open) {
        send_status_resp(req, UBCP_ERR_ALREADY_OPEN);
        return;
    }

    /* Mode 必填 */
    if (!req->payload || req->payload_len < 1) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t mode = req->payload[0];
    if (mode > CAN_MODE_LOOPBACK) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    /* 硬件初始化 */
    if (hw_init() != ESP_OK) {
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    /* 创建队列与任务 */
    s_can.event_queue = xQueueCreate(16, sizeof(uint32_t));
    s_can.rx_queue    = xQueueCreate(32, sizeof(can_rx_item_t));
    if (!s_can.event_queue || !s_can.rx_queue) {
        if (s_can.event_queue) vQueueDelete(s_can.event_queue);
        if (s_can.rx_queue) vQueueDelete(s_can.rx_queue);
        s_can.event_queue = NULL;
        s_can.rx_queue = NULL;
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    s_can.tasks_running = true;
    BaseType_t r1 = xTaskCreate(can_int_task_fn, "can_int", 4096, NULL, 9,
                                &s_can.int_task);
    BaseType_t r2 = xTaskCreate(can_rx_proc_fn, "can_rx", 4096, NULL, 8,
                                &s_can.rx_proc_task);
    if (r1 != pdPASS || r2 != pdPASS) {
        stop_workers();
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    /* 设置工作模式 */
    if (hw_set_mode(mode) != ESP_OK) {
        stop_workers();
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    /* 诊断: 回读 OPMOD 与位时序 */
    {
        uint8_t opmod = mcp2518fd_opmode_get();
        uint32_t nb = 0, db = 0, con = 0;
        mcp2518fd_read_word(MCP2518FD_REG_CiCON, &con);
        mcp2518fd_read_word(MCP2518FD_REG_CiNBTCFG, &nb);
        mcp2518fd_read_word(MCP2518FD_REG_CiDBTCFG, &db);
        HEX_LOGI(TAG, "OPMOD=%u CON=0x%08X NBTCFG=0x%08X DBTCFG=0x%08X",
                 opmod, (unsigned)con, (unsigned)nb, (unsigned)db);
    }

    /* 启用中断 */
    mcp2518fd_int_enable(MCP2518FD_INT_RXIF | MCP2518FD_INT_CERRIF |
                         MCP2518FD_INT_MODIF | MCP2518FD_INT_RXOVIF);
    mcp2518fd_int_flags_clear(0xFFFF);
    if (setup_gpio_isr() != ESP_OK) {
        HEX_LOGE(TAG, "GPIO 中断配置失败");
        stop_workers();
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    s_can.is_open       = true;
    s_can.mode          = mode;
    s_can.sleeping      = false;
    s_can.tx_count      = 0;
    s_can.rx_count      = 0;
    s_can.lost_count    = 0;
    s_can.crc_err_count = 0;
    s_can.form_err_count = 0;
    s_can.ack_err_count = 0;
    s_can.bit_err_count = 0;
    s_can.stuff_err_count = 0;
    s_can.bus_state     = 0;
    s_can.prev_bus_state = 0;
    s_can.rx_pending_overflow = 0;
    s_can.last_bd1 = 0;
    s_can.last_error_ts = 0;
    s_can.last_error_type = 0;

    /*
     * 响应载荷 (10 字节)：
     * [0]    Status        u8
     * [1]    ActualMode    u8
     * [2-3]  RxFIFODepth   u16
     * [4-7]  Capabilities  u32
     * [8-9]  TxQueueSize   u16
     */
    uint8_t payload[10];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = mode;
    payload[2] = (uint8_t)(CAN_RX_FIFO1_SIZE >> 8);
    payload[3] = (uint8_t)(CAN_RX_FIFO1_SIZE & 0xFF);
    uint32_t caps = (1 << 0) | (1 << 1);   /* CAN_FD | BRS */
    payload[4] = (uint8_t)(caps >> 24);
    payload[5] = (uint8_t)(caps >> 16);
    payload[6] = (uint8_t)(caps >> 8);
    payload[7] = (uint8_t)(caps & 0xFF);
    payload[8] = (uint8_t)(CAN_TXQ_SIZE >> 8);
    payload[9] = (uint8_t)(CAN_TXQ_SIZE & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);

    HEX_LOGI(TAG, "CAN 已打开, Mode=%u, 500k/经典", mode);
}

/**
 * @brief CAN_CLOSE (0x11)
 */
static void handle_can_close(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    /* 先停止接收任务与中断，避免配置模式误触发事件 */
    s_can.tasks_running = false;
    gpio_isr_handler_remove(profile_pin(SIG_CAN_INT));
    while (s_can.int_task || s_can.rx_proc_task) vTaskDelay(pdMS_TO_TICKS(10));

    /* 等待 TX 排空 (1s 超时) */
    mcp2518fd_txq_wait_empty(1000);
    mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
    vTaskDelay(pdMS_TO_TICKS(10));

    s_can.int_task = NULL;
    s_can.rx_proc_task = NULL;

    if (s_can.event_queue) {
        vQueueDelete(s_can.event_queue);
        s_can.event_queue = NULL;
    }
    if (s_can.rx_queue) {
        vQueueDelete(s_can.rx_queue);
        s_can.rx_queue = NULL;
    }

    s_can.is_open = false;
    s_can.sleeping = false;

    send_status_resp(req, UBCP_ERR_SUCCESS);
    HEX_LOGI(TAG, "CAN 已关闭");
}

/**
 * @brief CAN_CONFIG (0x12)
 */
static void handle_can_config(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    if (!req->payload || req->payload_len < 4) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *p = req->payload;
    uint8_t baud_idx = p[0];
    uint8_t flags    = p[1];
    uint8_t rx_buf   = p[2];   /* 保留 (硬件 FIFO 已固定) */
    uint8_t fd_baud  = p[3];

    (void)rx_buf;

    /* 解析自定义位时序参数 (模式 B) */
    mcp2518fd_nom_timing_t custom_nom = {0};
    mcp2518fd_data_timing_t custom_data = {0};
    bool has_custom_nom = false;
    bool has_custom_data = false;
    bool custom = (baud_idx >= 0x80);

    if (custom) {
        /* 仲裁段 (需要至少 5 个时序字节: p[4..8]) */
        if (req->payload_len >= 9) {
            uint8_t prop = p[5];
            uint8_t ps1  = p[6];
            uint8_t ps2  = p[7];
            uint8_t sjw  = p[8];
            custom_nom.brp   = 0;
            custom_nom.tseg1 = (uint8_t)(prop + ps1 - 1);
            custom_nom.tseg2 = (uint8_t)(ps2 - 1);
            custom_nom.sjw   = (uint8_t)(sjw - 1);
            has_custom_nom = true;
        }

        /* FD 段 (可选) */
        if (req->payload_len >= 14) {
            uint8_t fd_sync = p[9];
            uint8_t fd_prop = p[10];
            uint8_t fd_ps1  = p[11];
            uint8_t fd_ps2  = p[12];
            uint8_t fd_sjw  = p[13];
            if (fd_sync != 0) {
                custom_data.brp   = 0;
                custom_data.tseg1 = (uint8_t)(fd_prop + fd_ps1 - 1);
                custom_data.tseg2 = (uint8_t)(fd_ps2 - 1);
                custom_data.sjw   = (uint8_t)(fd_sjw - 1);
                custom_data.tdc_enable = false;
                if (req->payload_len >= 17) {
                    uint8_t tdc_en  = p[14];
                    uint8_t tdc_val = p[15];
                    uint8_t tdc_off = p[16];
                    (void)tdc_val;
                    if (tdc_en) {
                        custom_data.tdc_enable = true;
                        custom_data.tdc_offset = tdc_off;
                    }
                }
                has_custom_data = true;
            }
        }

        if (!has_custom_nom) {
            send_status_resp(req, UBCP_ERR_PARAM);
            return;
        }
    } else {
        /* 模式 A: 预定义波特率 */
        const mcp2518fd_nom_timing_t *nom = mcp2518fd_nom_timing_get(baud_idx);
        if (!nom) {
            send_status_resp(req, UBCP_ERR_CAN_BAUD_UNSUPPORT);
            return;
        }
        if ((flags & CAN_CFG_FD_MODE) && fd_baud != 0) {
            const mcp2518fd_data_timing_t *data =
                mcp2518fd_data_timing_get(fd_baud);
            if (!data) {
                send_status_resp(req, UBCP_ERR_CAN_BAUD_UNSUPPORT);
                return;
            }
        }
    }

    /* 进入配置模式前先排空 TXQ，避免残留报文干扰时序配置 */
    mcp2518fd_txq_wait_empty(500);

    /* 进入配置模式 */
    esp_err_t opm_err = mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
    if (opm_err != ESP_OK) {
        HEX_LOGW(TAG, "进入配置模式失败 (0x%x), 重试...", opm_err);
        vTaskDelay(pdMS_TO_TICKS(10));
        opm_err = mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
        if (opm_err != ESP_OK) {
            send_status_resp(req, UBCP_ERR_HAL_FAIL);
            return;
        }
    }
    vTaskDelay(pdMS_TO_TICKS(5));

    /* 验证已进入配置模式 */
    if (mcp2518fd_opmode_get() != MCP2518FD_MODE_CONFIG) {
        HEX_LOGE(TAG, "OPMOD 未切换到配置模式: %u", mcp2518fd_opmode_get());
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    /* 应用新位时序 (在配置模式下) */
    esp_err_t err = ESP_OK;
    if (custom) {
        err = mcp2518fd_bit_time_config(&custom_nom,
                                        has_custom_data ? &custom_data : NULL);
        if (err != ESP_OK) {
            hw_set_mode(s_can.mode);
            send_status_resp(req, UBCP_ERR_PARAM);
            return;
        }
        s_can.baud_index    = 0x06;
        s_can.fd_baud_index = 0x00;
    } else {
        const mcp2518fd_nom_timing_t *nom = mcp2518fd_nom_timing_get(baud_idx);
        err = mcp2518fd_bit_time_config(nom, NULL);
        if (err != ESP_OK) {
            hw_set_mode(s_can.mode);
            send_status_resp(req, UBCP_ERR_HAL_FAIL);
            return;
        }
        if (flags & CAN_CFG_FD_MODE) {
            const mcp2518fd_data_timing_t *data =
                mcp2518fd_data_timing_get(fd_baud);
            if (data && fd_baud != 0) {
                err = mcp2518fd_bit_time_config(NULL, data);
                if (err != ESP_OK) {
                    hw_set_mode(s_can.mode);
                    send_status_resp(req, UBCP_ERR_HAL_FAIL);
                    return;
                }
            }
        }
        s_can.baud_index    = baud_idx;
        s_can.fd_baud_index = fd_baud;
    }
    s_can.config_flags = flags;

    /* 模式切换后重置 TXQ, 防止硬件读指针与写指针错位 */
    mcp2518fd_txq_reset();

    /* 恢复原工作模式 */
    if (!s_can.sleeping) {
        if (hw_set_mode(s_can.mode) != ESP_OK) {
            send_status_resp(req, UBCP_ERR_HAL_FAIL);
            return;
        }
    }

    send_status_resp(req, UBCP_ERR_SUCCESS);
    HEX_LOGI(TAG, "CAN_CONFIG: baud_idx=%u flags=0x%02X fd=%u",
             baud_idx, flags, fd_baud);
}

/**
 * @brief CAN_SEND (0x13)
 */
static void handle_can_send(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    /* 只听模式禁止发送 */
    if (s_can.mode == CAN_MODE_LISTEN_ONLY) {
        send_status_resp(req, UBCP_ERR_NOT_SUPPORT);
        return;
    }

    if (!req->payload || req->payload_len < 5) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *p = req->payload;
    uint32_t can_id = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                      ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    uint8_t dlc_code = p[4];

    if (dlc_code > 15) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    /* DLC 码 → 实际字节数 */
    uint8_t data_len = mcp2518fd_dlc_to_bytes(dlc_code);
    if (req->payload_len < 5 + data_len) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    /* 校验 TXQ 未满 */
    if (!mcp2518fd_txq_not_full()) {
        send_status_resp(req, UBCP_ERR_CAN_TX_QUEUE_FULL);
        return;
    }

    /* 编码报文对象 */
    mcp2518fd_tx_obj_t obj;
    memset(&obj, 0, sizeof(obj));

    uint8_t ext = (can_id >> 31) & 1;
    uint8_t rtr = (can_id >> 30) & 1;
    uint8_t fd  = (can_id >> 29) & 1;
    uint8_t brs = (can_id >> 28) & 1;

    if (ext) {
        uint32_t id = can_id & 0x1FFFFFFF;
        obj.id = ((id >> 18) & 0x7FF) | ((id & 0x3FFFF) << 11);
    } else {
        obj.id = can_id & 0x7FF;
    }

    obj.ctrl = (uint32_t)(dlc_code & 0x0F);
    if (ext)  obj.ctrl |= (1 << 4);   /* IDE */
    if (rtr)  obj.ctrl |= (1 << 5);   /* RTR */
    if (brs)  obj.ctrl |= (1 << 6);   /* BRS */
    if (fd)   obj.ctrl |= (1 << 7);   /* FDF */

    memcpy(obj.data, &p[5], data_len);

    if (mcp2518fd_txq_load(&obj, data_len) != ESP_OK) {
        send_status_resp(req, UBCP_ERR_HAL_FAIL);
        return;
    }

    s_can.tx_count++;

    /* 响应: Status + TxTimestamp */
    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    uint32_t ts = (uint32_t)esp_timer_get_time();
    payload[1] = (uint8_t)(ts >> 24);
    payload[2] = (uint8_t)(ts >> 16);
    payload[3] = (uint8_t)(ts >> 8);
    payload[4] = (uint8_t)(ts & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/**
 * @brief CAN_FILTER (0x15)
 */
static void handle_can_filter(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    if (!req->payload || req->payload_len < 12) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *p = req->payload;
    uint8_t idx  = p[0];
    uint32_t mask = ((uint32_t)p[1] << 24) | ((uint32_t)p[2] << 16) |
                    ((uint32_t)p[3] << 8) | (uint32_t)p[4];
    uint32_t code = ((uint32_t)p[5] << 24) | ((uint32_t)p[6] << 16) |
                    ((uint32_t)p[7] << 8) | (uint32_t)p[8];
    uint8_t enable = p[9];
    uint8_t ftype  = p[10];
    uint8_t fifo   = p[11];

    if (idx >= 32) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }
    if (fifo != 1 && fifo != 2) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }
    if (ftype > CAN_FILTER_TYPE_BOTH) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    /* 更新软件模型 */
    can_filter_cfg_t *cfg = &s_can.filters[idx];
    cfg->enabled = (enable != 0);
    cfg->mask    = mask;
    cfg->code    = code;
    cfg->ftype   = ftype;
    cfg->fifo    = fifo;

    /* 同步到硬件 (进入配置模式) */
    mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
    vTaskDelay(pdMS_TO_TICKS(2));
    apply_filters();
    mcp2518fd_txq_reset();
    if (!s_can.sleeping) {
        if (hw_set_mode(s_can.mode) != ESP_OK) {
            send_status_resp(req, UBCP_ERR_HAL_FAIL);
            return;
        }
    }

    send_status_resp(req, UBCP_ERR_SUCCESS);
}

/**
 * @brief CAN_STATUS (0x16)
 */
static void handle_can_status(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    uint8_t tec = 0, rec = 0;
    mcp2518fd_tec_rec_get(&tec, &rec);

    uint8_t bus_state = compute_bus_state(tec, rec);
    if (bus_state != s_can.prev_bus_state) {
        s_can.bus_state = bus_state;
        s_can.prev_bus_state = bus_state;
    }

    uint8_t tx_usage = mcp2518fd_txq_usage();
    uint8_t rx_usage = mcp2518fd_rx_usage(MCP2518FD_CH_FIFO1);

    /*
     * 响应载荷 (28 字节)：
     * [0]     Status         u8
     * [1]     BusState       u8
     * [2]     TxErrCount     u8
     * [3]     RxErrCount     u8
     * [4-5]   TxQueueUsage   u16
     * [6-7]   RxQueueUsage   u16
     * [8-9]   TxCount        u16
     * [10-11] RxCount        u16
     * [12-13] LostCount      u16
     * [14-15] TxQueueSize    u16
     * [16-17] RxQueueSize    u16
     * [18-19] CrcErrCount    u16
     * [20-21] FormErrCount   u16
     * [22-23] AckErrCount    u16
     * [24-25] BitErrCount    u16
     * [26-27] StuffErrCount  u16
     */
    uint8_t payload[28];
    uint16_t tx_cnt = (uint16_t)(s_can.tx_count > 0xFFFF ? 0xFFFF : s_can.tx_count);
    uint16_t rx_cnt = (uint16_t)(s_can.rx_count > 0xFFFF ? 0xFFFF : s_can.rx_count);

    payload[0]  = UBCP_ERR_SUCCESS;
    payload[1]  = bus_state;
    payload[2]  = tec;
    payload[3]  = rec;
    payload[4]  = (uint8_t)(tx_usage >> 8);
    payload[5]  = (uint8_t)(tx_usage & 0xFF);
    payload[6]  = (uint8_t)(rx_usage >> 8);
    payload[7]  = (uint8_t)(rx_usage & 0xFF);
    payload[8]  = (uint8_t)(tx_cnt >> 8);
    payload[9]  = (uint8_t)(tx_cnt & 0xFF);
    payload[10] = (uint8_t)(rx_cnt >> 8);
    payload[11] = (uint8_t)(rx_cnt & 0xFF);
    payload[12] = (uint8_t)(s_can.lost_count >> 8);
    payload[13] = (uint8_t)(s_can.lost_count & 0xFF);
    payload[14] = (uint8_t)(CAN_TXQ_SIZE >> 8);
    payload[15] = (uint8_t)(CAN_TXQ_SIZE & 0xFF);
    payload[16] = (uint8_t)(CAN_RX_FIFO1_SIZE >> 8);
    payload[17] = (uint8_t)(CAN_RX_FIFO1_SIZE & 0xFF);
    payload[18] = (uint8_t)(s_can.crc_err_count >> 8);
    payload[19] = (uint8_t)(s_can.crc_err_count & 0xFF);
    payload[20] = (uint8_t)(s_can.form_err_count >> 8);
    payload[21] = (uint8_t)(s_can.form_err_count & 0xFF);
    payload[22] = (uint8_t)(s_can.ack_err_count >> 8);
    payload[23] = (uint8_t)(s_can.ack_err_count & 0xFF);
    payload[24] = (uint8_t)(s_can.bit_err_count >> 8);
    payload[25] = (uint8_t)(s_can.bit_err_count & 0xFF);
    payload[26] = (uint8_t)(s_can.stuff_err_count >> 8);
    payload[27] = (uint8_t)(s_can.stuff_err_count & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/**
 * @brief CAN_SLEEP (0x19)
 */
static void handle_can_sleep(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    if (s_can.sleeping) {
        send_status_resp(req, UBCP_ERR_BUSY);
        return;
    }

    /* 等待 TX 排空，进入休眠 */
    mcp2518fd_txq_wait_empty(500);
    mcp2518fd_opmode_select(MCP2518FD_MODE_SLEEP);
    vTaskDelay(pdMS_TO_TICKS(10));

    s_can.sleeping = true;
    s_can.mode_snapshot = s_can.mode;

    /* 禁用 GPIO39 中断避免误唤醒 */
    gpio_isr_handler_remove(profile_pin(SIG_CAN_INT));

    send_status_resp(req, UBCP_ERR_SUCCESS);
    HEX_LOGI(TAG, "CAN 进入休眠");
}

/**
 * @brief CAN_WAKEUP (0x1A)
 */
static void handle_can_wakeup(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    uint16_t wakeup_reason = 0;

    if (!s_can.sleeping) {
        /* 幂等: 返回 ERR_BUSY */
        send_status_resp(req, UBCP_ERR_BUSY);
        return;
    }

    /* 恢复工作模式 */
    hw_set_mode(s_can.mode_snapshot);
    s_can.sleeping = false;
    s_can.mode = s_can.mode_snapshot;

    /* 重新启用中断 */
    if (setup_gpio_isr() != ESP_OK) {
        HEX_LOGE(TAG, "GPIO 中断重新配置失败");
    }

    wakeup_reason = 0x0001;   /* CMD_WAKEUP */

    /*
     * 响应载荷 (4 字节)：
     * [0]    Status        u8
     * [1]    ActualMode    u8
     * [2-3]  WakeupReason  u16
     */
    uint8_t payload[4];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = s_can.mode;
    payload[2] = (uint8_t)(wakeup_reason >> 8);
    payload[3] = (uint8_t)(wakeup_reason & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);

    HEX_LOGI(TAG, "CAN 已唤醒 (reason=0x%04X)", wakeup_reason);
}

/**
 * @brief CAN_FILTER_BATCH (0x1B)
 */
static void handle_can_filter_batch(const ubcp_frame_t *req)
{
    if (!s_can.is_open) {
        send_status_resp(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    if (!req->payload || req->payload_len < 2) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *p = req->payload;
    uint8_t start = p[0];
    uint8_t count = p[1];

    if (count < 1 || start + count > 32) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }
    if (req->payload_len < 2 + (uint16_t)count * 12) {
        send_status_resp(req, UBCP_ERR_PARAM);
        return;
    }

    /* 逐条更新软件模型 */
    for (uint8_t i = 0; i < count; i++) {
        const uint8_t *e = &p[2 + (uint16_t)i * 12];
        uint8_t idx = (uint8_t)(start + i);
        uint32_t mask = ((uint32_t)e[0] << 24) | ((uint32_t)e[1] << 16) |
                        ((uint32_t)e[2] << 8) | (uint32_t)e[3];
        uint32_t code = ((uint32_t)e[4] << 24) | ((uint32_t)e[5] << 16) |
                        ((uint32_t)e[6] << 8) | (uint32_t)e[7];
        uint8_t enable = e[8];
        uint8_t ftype  = e[9];
        uint8_t fifo   = e[10];

        if (fifo != 1 && fifo != 2) {
            send_status_resp(req, UBCP_ERR_PARAM);
            return;
        }
        if (ftype > CAN_FILTER_TYPE_BOTH) {
            send_status_resp(req, UBCP_ERR_PARAM);
            return;
        }

        can_filter_cfg_t *cfg = &s_can.filters[idx];
        cfg->enabled = (enable != 0);
        cfg->mask    = mask;
        cfg->code    = code;
        cfg->ftype   = ftype;
        cfg->fifo    = fifo;
    }

    /* 同步到硬件 */
    mcp2518fd_opmode_select(MCP2518FD_MODE_CONFIG);
    vTaskDelay(pdMS_TO_TICKS(2));
    apply_filters();
    mcp2518fd_txq_reset();
    if (!s_can.sleeping) {
        if (hw_set_mode(s_can.mode) != ESP_OK) {
            send_status_resp(req, UBCP_ERR_HAL_FAIL);
            return;
        }
    }

    /*
     * 响应载荷 (2 字节)：
     * [0] Status
     * [1] WrittenCount
     */
    uint8_t payload[2];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = count;

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 * 模块入口
 * ======================================================================== */

static esp_err_t can_module_init(void)
{
    esp_err_t err = mcp2518fd_init();
    if (err != ESP_OK) { profile_driver_failed(); return err; }
    if (profile_is_trial()) {
        err = mcp2518fd_probe();
        if (err != ESP_OK) {
            mcp2518fd_deinit();
            profile_driver_failed();
            return err;
        }
    }
    topology_register(CAN_CHANNEL_ID, UBCP_DEV_TYPE_CAN, &s_can);
    return ESP_OK;
}

static void can_module_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_CAN_OPEN:
        handle_can_open(frame);
        break;
    case UBCP_CMD_CAN_CLOSE:
        handle_can_close(frame);
        break;
    case UBCP_CMD_CAN_CONFIG:
        handle_can_config(frame);
        break;
    case UBCP_CMD_CAN_SEND:
        handle_can_send(frame);
        break;
    case UBCP_CMD_CAN_RECV:
        /* RECV 是事件上报，设备端不会收到此命令 */
        send_status_resp(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    case UBCP_CMD_CAN_FILTER:
        handle_can_filter(frame);
        break;
    case UBCP_CMD_CAN_STATUS:
        handle_can_status(frame);
        break;
    case UBCP_CMD_CAN_BUS_EVENT:
        /* BUS_EVENT 是事件上报 */
        send_status_resp(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    case UBCP_CMD_CAN_ERROR_EVENT:
        /* ERROR_EVENT 是事件上报 */
        send_status_resp(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    case UBCP_CMD_CAN_SLEEP:
        handle_can_sleep(frame);
        break;
    case UBCP_CMD_CAN_WAKEUP:
        handle_can_wakeup(frame);
        break;
    case UBCP_CMD_CAN_FILTER_BATCH:
        handle_can_filter_batch(frame);
        break;
    default:
        send_status_resp(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static void can_module_stop(void)
{
    if (s_can.is_open) {
        gpio_isr_handler_remove(profile_pin(SIG_CAN_INT));
        s_can.is_open = false;
    }
    stop_workers();
    mcp2518fd_deinit();
}

static const hex_module_t s_can_module = {
    .name            = "CAN",
    .cmd_range_start = UBCP_CMD_RANGE_CAN_START,
    .cmd_range_end   = UBCP_CMD_RANGE_CAN_END,
    .init            = can_module_init,
    .handle_cmd      = can_module_handle_cmd,
    .stop            = can_module_stop,
};

const hex_module_t *mod_can_get(void)
{
    return &s_can_module;
}
