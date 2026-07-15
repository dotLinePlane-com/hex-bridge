/**
 * @file mod_uart.c
 * @brief UART 扩展模块实现 (0xA0-0xAF)
 *
 * 管理 UART2 (扩展口, GPIO 2 TX / GPIO 35 RX)：
 * - UART_OPEN   (0xA0): 安装驱动，创建接收任务
 * - UART_CLOSE  (0xA1): 卸载驱动，销毁接收任务
 * - UART_CONFIG (0xA2): 配置波特率/数据位/校验/停止位/流控
 * - UART_SEND   (0xA3): 向 UART2 发送数据
 * - UART_RECV   (0xA4): 接收任务自动上报事件
 * - UART_SET_BREAK (0xA5): 发送 Break 信号
 * - UART_STATUS (0xA6): 查询状态
 * - UART_FLUSH  (0xA7): 清空缓冲区
 *
 * 接收模式：
 * - 被动上报 (0x00): 收到数据即上报
 * - 行模式  (0x01): 遇到 \n 或 \r\n 时上报
 * - 定长模式 (0x02): 累积到 RxThreshold 字节后上报
 * - 超时模式 (0x03): 首字节后 RxTimeout ms 内无新数据则上报
 */

#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "driver/uart.h"
#include "modules/mod_uart.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "core/topology.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_uart";

/* ========================================================================
 * 通道状态
 * ======================================================================== */

/** UART RxFlags 位定义（与协议 7.5 一致） */
#define UART_RXFLAG_BUFFER_OVERFLOW    (1 << 0)
#define UART_RXFLAG_PARITY_ERROR       (1 << 1)
#define UART_RXFLAG_FRAME_ERROR        (1 << 2)
#define UART_RXFLAG_BREAK_DETECT       (1 << 3)

/** UART 事件队列大小 */
#define UART_EVENT_QUEUE_SIZE          8

/* ========================================================================
 * 通道状态
 * ======================================================================== */

/** UART 通道运行状态 */
typedef struct {
    bool        is_open;            /**< 通道是否已打开 */
    uint8_t     rx_mode;            /**< 接收模式 */
    uint16_t    rx_threshold;       /**< 接收上报阈值 */
    uint8_t     rx_timeout_ms;      /**< 接收超时（毫秒） */
    uint32_t    baud_rate;          /**< 当前波特率 */
    uint32_t    tx_count;           /**< 总发送字节数 */
    uint32_t    rx_count;           /**< 总接收字节数 */
    uint8_t     error_count;        /**< 错误计数 (Parity + Frame) */
    TaskHandle_t rx_task_handle;    /**< 接收任务句柄 */
    volatile bool rx_running;       /**< 接收任务运行标志 */
    uint8_t     channel_id;         /**< 通道号（支持未来多通道） */
    QueueHandle_t event_queue;      /**< UART 事件队列句柄 */
    bool        flow_xoff_sent;     /**< 是否已发送 XOFF */
} uart_channel_t;

/** 当前只有一个 UART2 通道 */
static uart_channel_t s_channel = {
    .is_open    = false,
    .rx_mode    = UBCP_UART_RXMODE_PASSIVE,
    .baud_rate  = HEX_EXT_UART_DEFAULT_BAUD,
    .channel_id = UBCP_CH_UART_EXT1,
};

/* ========================================================================
 * 接收任务
 * ======================================================================== */

/**
 * @brief 发送 FLOW_CONTROL 事件 (XOFF/XON) 到主机
 */
static void send_flow_event(uint8_t channel, uint8_t action,
                            uint16_t buf_usage, uint16_t buf_capacity)
{
    uint8_t payload[7];
    payload[0] = action;     /* 0x00=XOFF, 0x01=XON */
    payload[1] = 0xA0;       /* ModuleID = UART */
    payload[2] = channel;
    payload[3] = (uint8_t)(buf_usage >> 8);
    payload[4] = (uint8_t)(buf_usage & 0xFF);
    payload[5] = (uint8_t)(buf_capacity >> 8);
    payload[6] = (uint8_t)(buf_capacity & 0xFF);

    ubcp_frame_t evt;
    ubcp_frame_make_event(&evt, UBCP_CMD_FLOW_CONTROL, channel, seq_num_next());
    evt.payload     = payload;
    evt.payload_len = sizeof(payload);

    msg_bus_send_frame(&evt);
}

/**
 * @brief 检查 RX 缓冲区水位并触发流控
 */
static void check_rx_flow(uart_channel_t *ch)
{
    size_t rx_buffered = 0;
    uart_get_buffered_data_len(HEX_EXT_UART_NUM, &rx_buffered);
    uint16_t buf_cap = HEX_EXT_UART_RX_BUF_SIZE;
    uint8_t pct = buf_cap > 0 ? (uint8_t)((rx_buffered * 100) / buf_cap) : 0;

    /* 更新 msg_bus 全局流控状态 */
    msg_bus_update_flow_state(0xA0, ch->flow_xoff_sent ? 1 : 0,
                              (uint16_t)rx_buffered, buf_cap);

    if (pct >= HEX_FLOW_XOFF_PCT && !ch->flow_xoff_sent) {
        ch->flow_xoff_sent = true;
        HEX_LOGW(TAG, "XOFF: RX 缓冲 %u/%u (%u%%)",
                 (unsigned)rx_buffered, (unsigned)buf_cap, pct);
        send_flow_event(ch->channel_id, 0x00,
                        (uint16_t)rx_buffered, buf_cap);
    } else if (pct <= HEX_FLOW_XON_PCT && ch->flow_xoff_sent) {
        ch->flow_xoff_sent = false;
        HEX_LOGI(TAG, "XON: RX 缓冲 %u/%u (%u%%)",
                 (unsigned)rx_buffered, (unsigned)buf_cap, pct);
        send_flow_event(ch->channel_id, 0x01,
                        (uint16_t)rx_buffered, buf_cap);
    }
}

/**
 * @brief 发送 UART_RECV 事件帧到 MCP
 */
static void send_recv_event(uint8_t channel, uint8_t rx_flags,
                            const uint8_t *data, uint16_t data_len)
{
    uint16_t event_data_len = data_len;
    if (event_data_len > UBCP_MAX_PAYLOAD_LEN - 3) {
        event_data_len = UBCP_MAX_PAYLOAD_LEN - 3;
    }

    uint16_t total_len = 3 + event_data_len;
    uint8_t *payload = malloc(total_len);
    if (!payload) {
        HEX_LOGE(TAG, "RECV 事件载荷分配失败 (%u 字节)", total_len);
        return;
    }

    payload[0] = rx_flags;
    payload[1] = (uint8_t)(event_data_len >> 8);
    payload[2] = (uint8_t)(event_data_len & 0xFF);
    memcpy(&payload[3], data, event_data_len);

    ubcp_frame_t evt;
    ubcp_frame_make_event(&evt, UBCP_CMD_UART_RECV, channel, seq_num_next());
    evt.payload     = payload;
    evt.payload_len = total_len;

    msg_bus_send_frame(&evt);

    free(payload);
}

/**
 * @brief 清空 UART 事件队列，累积错误标志和计数
 *
 * 从非阻塞的事件队列中取出所有待处理事件，
 * 累加错误计数并返回当前批次数据对应的 RxFlags。
 *
 * @param ch  通道状态
 * @return 累积的错误标志（UART_RXFLAG_* 位图）
 */
static uint8_t drain_uart_events(uart_channel_t *ch)
{
    uint8_t flags = 0;
    uart_event_t event;

    if (ch->event_queue == NULL) {
        return 0;
    }

    while (xQueueReceive(ch->event_queue, &event, 0) == pdTRUE) {
        switch (event.type) {
        case UART_DATA:
            break;
        case UART_BREAK:
            flags |= UART_RXFLAG_BREAK_DETECT;
            break;
        case UART_BUFFER_FULL:
        case UART_FIFO_OVF:
            flags |= UART_RXFLAG_BUFFER_OVERFLOW;
            break;
        case UART_FRAME_ERR:
            flags |= UART_RXFLAG_FRAME_ERROR;
            ch->error_count++;
            break;
        case UART_PARITY_ERR:
            flags |= UART_RXFLAG_PARITY_ERROR;
            ch->error_count++;
            break;
        default:
            break;
        }
    }

    return flags;
}

/**
 * @brief UART 接收任务 — 被动上报模式
 *
 * 从 UART2 读取数据，一旦有数据就上报。
 */
static void uart_rx_task_passive(void *arg)
{
    uart_channel_t *ch = (uart_channel_t *)arg;
    uint8_t rx_buf[512];

    HEX_LOGI(TAG, "UART RX 任务启动（被动上报模式）");

    while (ch->rx_running) {
        int len = uart_read_bytes(HEX_EXT_UART_NUM, rx_buf, sizeof(rx_buf),
                                  pdMS_TO_TICKS(50));
        if (len > 0) {
            ch->rx_count += len;
            uint8_t flags = drain_uart_events(ch);
            send_recv_event(ch->channel_id, flags, rx_buf, (uint16_t)len);
        } else {
            drain_uart_events(ch);
        }
        check_rx_flow(ch);
    }

    HEX_LOGI(TAG, "UART RX 任务退出");
    vTaskDelete(NULL);
}

/**
 * @brief UART 接收任务 — 行模式
 *
 * 缓存数据直到遇到 \n，然后一次性上报整行。
 */
static void uart_rx_task_line(void *arg)
{
    uart_channel_t *ch = (uart_channel_t *)arg;
    uint8_t rx_buf[16];
    uint8_t line_buf[1024];
    size_t line_pos = 0;

    HEX_LOGI(TAG, "UART RX 任务启动（行模式）");

    while (ch->rx_running) {
        int len = uart_read_bytes(HEX_EXT_UART_NUM, rx_buf, sizeof(rx_buf),
                                  pdMS_TO_TICKS(50));
        if (len <= 0) {
            drain_uart_events(ch);
            check_rx_flow(ch);
            continue;
        }

        ch->rx_count += len;
        uint8_t err_flags = drain_uart_events(ch);

        for (int i = 0; i < len; i++) {
            if (line_pos < sizeof(line_buf)) {
                line_buf[line_pos++] = rx_buf[i];
            }
            if (rx_buf[i] == '\n' || line_pos >= sizeof(line_buf)) {
                send_recv_event(ch->channel_id, err_flags, line_buf, (uint16_t)line_pos);
                line_pos = 0;
            }
        }
        check_rx_flow(ch);
    }

    drain_uart_events(ch);

    /* 上报残余数据 */
    if (line_pos > 0) {
        send_recv_event(ch->channel_id, 0x00, line_buf, (uint16_t)line_pos);
    }

    HEX_LOGI(TAG, "UART RX 任务退出（行模式）");
    vTaskDelete(NULL);
}

/**
 * @brief UART 接收任务 — 定长模式
 *
 * 累积到 rx_threshold 字节后上报。
 */
static void uart_rx_task_fixed(void *arg)
{
    uart_channel_t *ch = (uart_channel_t *)arg;
    uint16_t threshold = ch->rx_threshold > 0 ? ch->rx_threshold : 64;
    uint8_t *accum_buf = malloc(threshold);
    if (!accum_buf) {
        HEX_LOGE(TAG, "定长模式缓冲区分配失败");
        vTaskDelete(NULL);
        return;
    }
    size_t accum_pos = 0;

    HEX_LOGI(TAG, "UART RX 任务启动（定长模式，阈值=%u）", threshold);

    while (ch->rx_running) {
        size_t want = threshold - accum_pos;
        int len = uart_read_bytes(HEX_EXT_UART_NUM, accum_buf + accum_pos,
                                  want, pdMS_TO_TICKS(100));
        if (len > 0) {
            ch->rx_count += len;
            accum_pos += len;
            if (accum_pos >= threshold) {
                uint8_t flags = drain_uart_events(ch);
                send_recv_event(ch->channel_id, flags, accum_buf, threshold);
                accum_pos = 0;
            }
        } else {
            drain_uart_events(ch);
        }
        check_rx_flow(ch);
    }

    drain_uart_events(ch);

    /* 上报残余数据 */
    if (accum_pos > 0) {
        send_recv_event(ch->channel_id, 0x00, accum_buf, (uint16_t)accum_pos);
    }

    free(accum_buf);
    HEX_LOGI(TAG, "UART RX 任务退出（定长模式）");
    vTaskDelete(NULL);
}

/**
 * @brief UART 接收任务 — 超时模式
 *
 * 收到首字节后，如果 rx_timeout_ms 内无新数据则上报。
 */
static void uart_rx_task_timeout(void *arg)
{
    uart_channel_t *ch = (uart_channel_t *)arg;
    uint8_t rx_buf[512];
    uint8_t accum_buf[1024];
    size_t accum_pos = 0;
    uint8_t timeout_ms = ch->rx_timeout_ms > 0 ? ch->rx_timeout_ms : 20;

    HEX_LOGI(TAG, "UART RX 任务启动（超时模式，超时=%ums）", timeout_ms);

    while (ch->rx_running) {
        TickType_t wait_ticks = (accum_pos > 0) ?
            pdMS_TO_TICKS(timeout_ms) : pdMS_TO_TICKS(50);

        int len = uart_read_bytes(HEX_EXT_UART_NUM, rx_buf, sizeof(rx_buf),
                                  wait_ticks);
        if (len > 0) {
            ch->rx_count += len;
            drain_uart_events(ch);

            size_t copy_len = len;
            if (accum_pos + copy_len > sizeof(accum_buf)) {
                copy_len = sizeof(accum_buf) - accum_pos;
            }
            memcpy(accum_buf + accum_pos, rx_buf, copy_len);
            accum_pos += copy_len;

            if (accum_pos >= sizeof(accum_buf)) {
                uint8_t flags = drain_uart_events(ch);
                send_recv_event(ch->channel_id, flags, accum_buf, (uint16_t)accum_pos);
                accum_pos = 0;
            }
        } else if (accum_pos > 0) {
            uint8_t flags = drain_uart_events(ch);
            send_recv_event(ch->channel_id, flags, accum_buf, (uint16_t)accum_pos);
            accum_pos = 0;
        } else {
            drain_uart_events(ch);
        }
        check_rx_flow(ch);
    }

    drain_uart_events(ch);

    /* 上报残余数据 */
    if (accum_pos > 0) {
        send_recv_event(ch->channel_id, 0x00, accum_buf, (uint16_t)accum_pos);
    }

    HEX_LOGI(TAG, "UART RX 任务退出（超时模式）");
    vTaskDelete(NULL);
}

/**
 * @brief 启动接收任务（根据 rx_mode 选择对应实现）
 */
static esp_err_t start_rx_task(uart_channel_t *ch)
{
    TaskFunction_t task_fn;
    switch (ch->rx_mode) {
    case UBCP_UART_RXMODE_LINE:
        task_fn = uart_rx_task_line;
        break;
    case UBCP_UART_RXMODE_FIXED:
        task_fn = uart_rx_task_fixed;
        break;
    case UBCP_UART_RXMODE_TIMEOUT:
        task_fn = uart_rx_task_timeout;
        break;
    case UBCP_UART_RXMODE_PASSIVE:
    default:
        task_fn = uart_rx_task_passive;
        break;
    }

    ch->rx_running = true;
    BaseType_t ret = xTaskCreate(task_fn, "uart_rx",
                                 HEX_UART_RX_TASK_STACK,
                                 ch,
                                 HEX_UART_RX_TASK_PRIO,
                                 &ch->rx_task_handle);
    if (ret != pdPASS) {
        ch->rx_running = false;
        HEX_LOGE(TAG, "UART RX 任务创建失败");
        return ESP_ERR_NO_MEM;
    }

    return ESP_OK;
}

/**
 * @brief 停止接收任务
 */
static void stop_rx_task(uart_channel_t *ch)
{
    if (ch->rx_running) {
        ch->rx_running = false;
        vTaskDelay(pdMS_TO_TICKS(200)); /* 等待任务退出 */
        ch->rx_task_handle = NULL;
    }
}

/* ========================================================================
 * 命令处理函数
 * ======================================================================== */

/**
 * @brief UART_OPEN (0xA0) — 打开 UART 通道
 */
static void handle_uart_open(const ubcp_frame_t *req)
{
    if (s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_ALREADY_OPEN);
        return;
    }

    /* 解析 RxMode */
    uint8_t rx_mode = UBCP_UART_RXMODE_PASSIVE;
    if (req->payload && req->payload_len >= 1) {
        rx_mode = req->payload[0];
        if (rx_mode > UBCP_UART_RXMODE_TIMEOUT) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
    }

    /* 安装 UART2 驱动（使用默认配置） */
    uart_config_t uart_config = {
        .baud_rate  = s_channel.baud_rate,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_APB,
    };

    esp_err_t err;
    err = uart_driver_install(HEX_EXT_UART_NUM,
                              HEX_EXT_UART_RX_BUF_SIZE,
                              HEX_EXT_UART_TX_BUF_SIZE,
                              UART_EVENT_QUEUE_SIZE,
                              &s_channel.event_queue, 0);
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "UART2 驱动安装失败: 0x%x", err);
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    err = uart_param_config(HEX_EXT_UART_NUM, &uart_config);
    if (err != ESP_OK) {
        uart_driver_delete(HEX_EXT_UART_NUM);
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    err = uart_set_pin(HEX_EXT_UART_NUM,
                       HEX_EXT_UART_TX_PIN,
                       HEX_EXT_UART_RX_PIN,
                       UART_PIN_NO_CHANGE,
                       UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        uart_driver_delete(HEX_EXT_UART_NUM);
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    const ubcp_route_entry_t *route = topology_find(req->channel_id);
    if (!route) {
        uart_driver_delete(HEX_EXT_UART_NUM);
        msg_bus_send_status_response(req, UBCP_ERR_CHANNEL_INVALID);
        return;
    }
    if (route->device_type != UBCP_DEV_TYPE_UART) {
        uart_driver_delete(HEX_EXT_UART_NUM);
        msg_bus_send_status_response(req, UBCP_ERR_TYPE_MISMATCH);
        return;
    }

    s_channel.rx_mode    = rx_mode;
    s_channel.tx_count   = 0;
    s_channel.rx_count   = 0;
    s_channel.error_count = 0;
    s_channel.flow_xoff_sent = false;
    s_channel.is_open    = true;

    /* 启动接收任务 */
    err = start_rx_task(&s_channel);
    if (err != ESP_OK) {
        uart_driver_delete(HEX_EXT_UART_NUM);
        s_channel.is_open = false;
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    /*
     * 响应载荷（5 字节）：
     * [0]    Status      u8
     * [1-2]  RxBufSize   u16
     * [3-4]  TxBufSize   u16
     */
    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(HEX_EXT_UART_RX_BUF_SIZE >> 8);
    payload[2] = (uint8_t)(HEX_EXT_UART_RX_BUF_SIZE & 0xFF);
    payload[3] = (uint8_t)(HEX_EXT_UART_TX_BUF_SIZE >> 8);
    payload[4] = (uint8_t)(HEX_EXT_UART_TX_BUF_SIZE & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);

    HEX_LOGI(TAG, "UART2 已打开，RxMode=%u, 波特率=%lu",
             rx_mode, (unsigned long)s_channel.baud_rate);
}

/**
 * @brief UART_CLOSE (0xA1) — 关闭 UART 通道
 */
static void handle_uart_close(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    stop_rx_task(&s_channel);
    uart_driver_delete(HEX_EXT_UART_NUM);
    s_channel.event_queue = NULL;
    s_channel.is_open = false;

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
    HEX_LOGI(TAG, "UART2 已关闭");
}

/**
 * @brief UART_CONFIG (0xA2) — 配置 UART 参数
 */
static void handle_uart_config(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    /*
     * 请求载荷（11 字节）：
     * [0-3]  BaudRate      u32
     * [4]    DataBits      u8
     * [5]    StopBits      u8
     * [6]    Parity        u8
     * [7]    FlowControl   u8
     * [8-9]  RxThreshold   u16
     * [10]   RxTimeout     u8
     */
    if (!req->payload || req->payload_len < 11) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *p = req->payload;

    uint32_t baud = ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
                    ((uint32_t)p[2] << 8) | (uint32_t)p[3];
    uint8_t data_bits    = p[4];
    uint8_t stop_bits    = p[5];
    uint8_t parity       = p[6];
    uint8_t flow_ctrl     = p[7];
    uint16_t rx_threshold = ((uint16_t)p[8] << 8) | p[9];
    uint8_t rx_timeout    = p[10];

    /* 校验 FlowControl：UART2 无 RTS/CTS 引脚，不支持硬件和软件流控 */
    if (flow_ctrl != 0x00) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_SUPPORT);
        return;
    }

    /* 映射参数到 ESP-IDF 枚举 */
    uart_word_length_t esp_data_bits;
    switch (data_bits) {
    case 0x05: esp_data_bits = UART_DATA_5_BITS; break;
    case 0x06: esp_data_bits = UART_DATA_6_BITS; break;
    case 0x07: esp_data_bits = UART_DATA_7_BITS; break;
    case 0x08: esp_data_bits = UART_DATA_8_BITS; break;
    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uart_stop_bits_t esp_stop_bits;
    switch (stop_bits) {
    case 0x01: esp_stop_bits = UART_STOP_BITS_1; break;
    case 0x02: esp_stop_bits = UART_STOP_BITS_1_5; break;
    case 0x03: esp_stop_bits = UART_STOP_BITS_2; break;
    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uart_parity_t esp_parity;
    switch (parity) {
    case 0x00: esp_parity = UART_PARITY_DISABLE; break;
    case 0x01: esp_parity = UART_PARITY_ODD;     break;
    case 0x02: esp_parity = UART_PARITY_EVEN;    break;
    case 0x03: /* Mark */  /* fallthrough */
    case 0x04: /* Space */
        msg_bus_send_status_response(req, UBCP_ERR_NOT_SUPPORT);
        return;
    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    /* 应用配置 */
    esp_err_t err;
    err = uart_set_baudrate(HEX_EXT_UART_NUM, baud);
    if (err != ESP_OK) {
        msg_bus_send_status_response(req, UBCP_ERR_UART_BAUD);
        return;
    }

    err = uart_set_word_length(HEX_EXT_UART_NUM, esp_data_bits);
    if (err != ESP_OK) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uart_set_stop_bits(HEX_EXT_UART_NUM, esp_stop_bits);
    uart_set_parity(HEX_EXT_UART_NUM, esp_parity);

    /* 检测参数变化是否需要重启接收任务（定长/超时模式下阈值/超时变化） */
    bool need_restart = false;
    if (s_channel.rx_mode == UBCP_UART_RXMODE_FIXED &&
        s_channel.rx_threshold != rx_threshold) {
        need_restart = true;
    }
    if (s_channel.rx_mode == UBCP_UART_RXMODE_TIMEOUT &&
        s_channel.rx_timeout_ms != rx_timeout) {
        need_restart = true;
    }

    /* 保存配置 */
    s_channel.baud_rate     = baud;
    s_channel.rx_threshold  = rx_threshold;
    s_channel.rx_timeout_ms = rx_timeout;

    if (need_restart) {
        stop_rx_task(&s_channel);
        start_rx_task(&s_channel);
    }

    /* 读取实际波特率（可能因分频略有偏差） */
    uint32_t actual_baud = 0;
    uart_get_baudrate(HEX_EXT_UART_NUM, &actual_baud);

    /*
     * 响应载荷（5 字节）：
     * [0]    Status       u8
     * [1-4]  ActualBaud   u32
     */
    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(actual_baud >> 24);
    payload[2] = (uint8_t)(actual_baud >> 16);
    payload[3] = (uint8_t)(actual_baud >> 8);
    payload[4] = (uint8_t)(actual_baud & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);

    HEX_LOGI(TAG, "UART2 配置更新: 波特率=%lu (实际=%lu), %u%c%u",
             (unsigned long)baud, (unsigned long)actual_baud,
             data_bits,
             parity == 0 ? 'N' : (parity == 1 ? 'O' : 'E'),
             stop_bits == 1 ? 1 : 2);
}

/**
 * @brief UART_SEND (0xA3) — 发送数据
 */
static void handle_uart_send(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    /*
     * 请求载荷：
     * [0-1]  DataLen  u16
     * [2...] Data     u8[N]
     */
    if (!req->payload || req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t data_len = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    if (req->payload_len < 2 + data_len) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *data = &req->payload[2];

    /* 写入 UART2 */
    int written = uart_write_bytes(HEX_EXT_UART_NUM, data, data_len);
    if (written < 0) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    s_channel.tx_count += written;

    /*
     * 响应载荷（3 字节）：
     * [0]    Status     u8
     * [1-2]  ActualLen  u16
     */
    uint8_t payload[3];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)((uint16_t)written >> 8);
    payload[2] = (uint8_t)((uint16_t)written & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/**
 * @brief UART_SET_BREAK (0xA5) — 发送 Break 信号
 *
 * 通过 GPIO 直接控制 TXD 线实现 Break，避免 uart_set_line_inverse
 * 在极性恢复时产生的电平跳变被接收端误判为起始位（产生 0x00 假字节）。
 */
static void handle_uart_set_break(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    uint16_t duration_ms = 10; /* 默认 10ms */
    if (req->payload && req->payload_len >= 2) {
        duration_ms = ((uint16_t)req->payload[0] << 8) | req->payload[1];
        if (duration_ms == 0) duration_ms = 10;
    }

    int tx_pin = HEX_EXT_UART_TX_PIN;

    /* 等待正在进行的 UART 发送完成 */
    uart_wait_tx_done(HEX_EXT_UART_NUM, pdMS_TO_TICKS(100));

    /*
     * GPIO 直接控制 TXD 产生 Break：
     * 1. 将 TX pin 切换为 GPIO 输出并拉低 (Break 状态)
     * 2. 延时 duration_ms
     * 3. 恢复到高电平
     * 4. 稳定延时让接收端重同步 (>1 帧时间, 最坏 1200bps≈10ms, 取 20ms)
     * 5. 将 TX pin 交还给 UART 控制器
     */
    gpio_set_direction(tx_pin, GPIO_MODE_OUTPUT);
    gpio_set_level(tx_pin, 0);
    vTaskDelay(pdMS_TO_TICKS(duration_ms));
    gpio_set_level(tx_pin, 1);

    /*
     * 注意：Break 恢复时 CH340 接收端会将电平跳变检测为 0x00 + 帧错误，
     * 这是所有 UART 接收器的标准 Break 检测行为，无法从发送侧消除。
     * 接收端可通过帧错误标志 (RxFlags=0x04 BreakDetect) 区分真实数据与 Break 假字节。
     */
    gpio_set_level(tx_pin, 1);
    vTaskDelay(pdMS_TO_TICKS(20));

    /* 恢复 UART 控制 */
    gpio_set_direction(tx_pin, GPIO_MODE_INPUT_OUTPUT);
    uart_set_pin(HEX_EXT_UART_NUM,
                 tx_pin, HEX_EXT_UART_RX_PIN,
                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/**
 * @brief UART_STATUS (0xA6) — 获取状态
 */
static void handle_uart_status(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    /*
     * 响应载荷（19 字节）：
     * [0]     Status      u8
     * [1-4]   BaudRate    u32
     * [5]     LineState   u8
     * [6-7]   TxBufUsed   u16
     * [8-9]   RxBufUsed   u16
     * [10-13] TxCount     u32
     * [14-17] RxCount     u32
     * [18]    ErrorCount  u8
     */
    uint8_t payload[19];

    payload[0] = UBCP_ERR_SUCCESS;

    /* 波特率 */
    uint32_t baud = s_channel.baud_rate;
    payload[1] = (uint8_t)(baud >> 24);
    payload[2] = (uint8_t)(baud >> 16);
    payload[3] = (uint8_t)(baud >> 8);
    payload[4] = (uint8_t)(baud & 0xFF);

    /* 先清空事件队列，让错误计数更新到最新 */
    drain_uart_events(&s_channel);

    /* LineState：
     * Bit 0: TxIdle = 1 (常态)
     * Bit 1: RxActive (接收缓冲区有数据表示正在接收)
     */
    size_t tx_buf_free = 0;
    size_t rx_buf_used = 0;
    uart_get_tx_buffer_free_size(HEX_EXT_UART_NUM, &tx_buf_free);
    size_t tx_buf_used = HEX_EXT_UART_TX_BUF_SIZE > tx_buf_free
                       ? HEX_EXT_UART_TX_BUF_SIZE - tx_buf_free : 0;
    uart_get_buffered_data_len(HEX_EXT_UART_NUM, &rx_buf_used);

    uint8_t line_state = (tx_buf_used == 0) ? 0x01 : 0x00; /* TxIdle */
    if (rx_buf_used > 0) {
        line_state |= 0x02; /* RxActive */
    }
    payload[5] = line_state;


    payload[6] = (uint8_t)(tx_buf_used >> 8);
    payload[7] = (uint8_t)(tx_buf_used & 0xFF);
    payload[8] = (uint8_t)(rx_buf_used >> 8);
    payload[9] = (uint8_t)(rx_buf_used & 0xFF);

    /* 总发送/接收计数 */
    payload[10] = (uint8_t)(s_channel.tx_count >> 24);
    payload[11] = (uint8_t)(s_channel.tx_count >> 16);
    payload[12] = (uint8_t)(s_channel.tx_count >> 8);
    payload[13] = (uint8_t)(s_channel.tx_count & 0xFF);
    payload[14] = (uint8_t)(s_channel.rx_count >> 24);
    payload[15] = (uint8_t)(s_channel.rx_count >> 16);
    payload[16] = (uint8_t)(s_channel.rx_count >> 8);
    payload[17] = (uint8_t)(s_channel.rx_count & 0xFF);

    /* 错误计数 */
    payload[18] = s_channel.error_count;

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/**
 * @brief 带任务让出的 TX 排空等待
 *
 * 轮询 TX 缓冲区空闲大小，每轮让出 CPU 给其他任务（包括 MCP 接收任务）。
 * 最多等待 max_wait_ms，TX 完全排空后立即返回。
 */
static void flush_tx_with_yield(int uart_num, int max_wait_ms)
{
    int elapsed = 0;
    const int poll_interval = 5;

    while (elapsed < max_wait_ms) {
        size_t tx_free = 0;
        uart_get_tx_buffer_free_size(uart_num, &tx_free);
        if (tx_free >= HEX_EXT_UART_TX_BUF_SIZE) {
            return;
        }
        vTaskDelay(pdMS_TO_TICKS(poll_interval));
        elapsed += poll_interval;
    }
}

/**
 * @brief UART_FLUSH (0xA7) — 清空缓冲区
 */
static void handle_uart_flush(const ubcp_frame_t *req)
{
    if (!s_channel.is_open) {
        msg_bus_send_status_response(req, UBCP_ERR_NOT_OPEN);
        return;
    }

    uint8_t flush_type = UBCP_UART_FLUSH_ALL;
    if (req->payload && req->payload_len >= 1) {
        flush_type = req->payload[0];
    }

    switch (flush_type) {
    case UBCP_UART_FLUSH_RX:
        uart_flush_input(HEX_EXT_UART_NUM);
        break;
    case UBCP_UART_FLUSH_TX:
        flush_tx_with_yield(HEX_EXT_UART_NUM, 200);
        break;
    case UBCP_UART_FLUSH_ALL:
        uart_flush_input(HEX_EXT_UART_NUM);
        flush_tx_with_yield(HEX_EXT_UART_NUM, 200);
        break;
    case UBCP_UART_FLUSH_DRAIN:
        flush_tx_with_yield(HEX_EXT_UART_NUM, 1000);
        uart_flush_input(HEX_EXT_UART_NUM);
        break;
    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 * 模块入口
 * ======================================================================== */

static esp_err_t uart_module_init(void)
{
    HEX_LOGI(TAG, "UART 扩展模块初始化 (UART%d, TX=GPIO%d, RX=GPIO%d)",
             HEX_EXT_UART_NUM, HEX_EXT_UART_TX_PIN, HEX_EXT_UART_RX_PIN);
    topology_register(UBCP_CH_UART_EXT1, UBCP_DEV_TYPE_UART, &s_channel);
    return ESP_OK;
}

static void uart_module_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_UART_OPEN:
        handle_uart_open(frame);
        break;
    case UBCP_CMD_UART_CLOSE:
        handle_uart_close(frame);
        break;
    case UBCP_CMD_UART_CONFIG:
        handle_uart_config(frame);
        break;
    case UBCP_CMD_UART_SEND:
        handle_uart_send(frame);
        break;
    case UBCP_CMD_UART_RECV:
        /* RECV 是事件上报，设备端不会收到此命令 */
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    case UBCP_CMD_UART_SET_BREAK:
        handle_uart_set_break(frame);
        break;
    case UBCP_CMD_UART_STATUS:
        handle_uart_status(frame);
        break;
    case UBCP_CMD_UART_FLUSH:
        handle_uart_flush(frame);
        break;
    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static void uart_module_stop(void)
{
    if (s_channel.is_open) {
        stop_rx_task(&s_channel);
        uart_driver_delete(HEX_EXT_UART_NUM);
        s_channel.event_queue = NULL;
        s_channel.is_open = false;
    }
    HEX_LOGI(TAG, "UART 扩展模块已停止");
}

/* 模块定义（静态生命周期） */
static const hex_module_t s_uart_module = {
    .name            = "UART",
    .cmd_range_start = UBCP_CMD_RANGE_UART_START,
    .cmd_range_end   = UBCP_CMD_RANGE_UART_END,
    .init            = uart_module_init,
    .handle_cmd      = uart_module_handle_cmd,
    .stop            = uart_module_stop,
};

const hex_module_t *mod_uart_get(void)
{
    return &s_uart_module;
}
