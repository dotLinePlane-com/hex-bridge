/**
 * @file mod_system.c
 * @brief 系统管理模块实现 (0x00-0x0F)
 *
 * 当前实现：
 * - PING (0x00): 心跳检测，返回 uptime/CPU负载/剩余堆内存
 * - GET_INFO (0x01): 返回固件版本/序列号/型号/能力位图
 * - GET_CONFIG (0x02): 读取系统全局配置参数
 * - SET_CONFIG (0x03): 写入系统全局配置参数
 * - RESET (0x04): 软复位、看门狗复位
 * - FLOW_CONTROL (0x05): 流控状态查询
 * - SYS_BOOT_EVENT (0x06): 启动/复位事件主动上报
 * - GET_TOPOLOGY (0x07): 获取硬件拓扑通道列表
 */

#include <string.h>
#include <stdlib.h>
#include "modules/mod_system.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "core/topology.h"
#include "hex_config.h"
#include "utils/hex_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_chip_info.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "nvs.h"

static const char *TAG = "mod_system";

static uint8_t get_reset_reason(void)
{
    switch (esp_reset_reason()) {
    case ESP_RST_POWERON:   return UBCP_RESET_POWERON;
    case ESP_RST_SW:        return UBCP_RESET_SW;
    case ESP_RST_DEEPSLEEP: return UBCP_RESET_DEEPSLEEP;
    case ESP_RST_INT_WDT:   return UBCP_RESET_INT_WDT;
    case ESP_RST_TASK_WDT:  return UBCP_RESET_TASK_WDT;
    case ESP_RST_WDT:       return UBCP_RESET_WDT;
    case ESP_RST_BROWNOUT:  return UBCP_RESET_BROWNOUT;
    case ESP_RST_PANIC:     return UBCP_RESET_PANIC;
    default:                return UBCP_RESET_UNKNOWN;
    }
}

void mod_system_send_boot_event(void)
{
    uint8_t payload[2] = {
        get_reset_reason(),
        UBCP_BOOT_STATUS_NORMAL,
    };

    ubcp_frame_t evt;
    memset(&evt, 0, sizeof(evt));
    evt.version       = UBCP_VERSION;
    evt.flags         = UBCP_FLAG_DIR | UBCP_FLAG_EVT | UBCP_FLAG_TS;
    evt.seq_num       = seq_num_next();
    evt.cmd_code      = UBCP_CMD_SYS_BOOT_EVENT;
    evt.channel_id    = 0;
    evt.has_timestamp = true;
    evt.timestamp     = (uint32_t)(esp_timer_get_time() & 0xFFFFFFFF);
    evt.payload       = payload;
    evt.payload_len   = sizeof(payload);

    HEX_LOGI(TAG, "系统启动事件上报: ResetReason=0x%02X, BootStatus=0x%02X",
             payload[0], payload[1]);
    msg_bus_send_frame(&evt);
}

/* ========================================================================
 * PING 处理 (0x00)
 * ======================================================================== */

static void handle_ping(const ubcp_frame_t *req)
{
    /*
     * 响应载荷（7 字节）：
     * [0]    Status      u8   0x00 = SUCCESS
     * [1-4]  Uptime      u32  设备运行时间（微秒）
     * [5]    Load        u8   CPU 负载百分比 (暂返回 0)
     * [6]    FreeHeap    u8   剩余堆内存百分比
     */
    uint8_t payload[7];

    payload[0] = UBCP_ERR_SUCCESS;

    /* 运行时间（微秒） */
    uint32_t uptime = (uint32_t)(esp_timer_get_time() & 0xFFFFFFFF);
    payload[1] = (uint8_t)(uptime >> 24);
    payload[2] = (uint8_t)(uptime >> 16);
    payload[3] = (uint8_t)(uptime >> 8);
    payload[4] = (uint8_t)(uptime & 0xFF);

    /* CPU 负载（暂不实现，返回 0） */
    payload[5] = 0;

    /* 剩余堆内存百分比 */
    size_t free_heap  = esp_get_free_heap_size();
    size_t total_heap = esp_get_minimum_free_heap_size(); /* 历史最小值仅作参考 */
    /* 简单估算：假设初始堆约 300KB */
    uint32_t total_est = 300 * 1024;
    uint8_t heap_pct = (uint8_t)((free_heap * 100) / total_est);
    if (heap_pct > 100) heap_pct = 100;
    payload[6] = heap_pct;

    (void)total_heap; /* 避免未使用警告 */

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);

    msg_bus_send_frame(&resp);
}

/* ========================================================================
 * GET_INFO 处理 (0x01)
 * ======================================================================== */

static void handle_get_info(const ubcp_frame_t *req)
{
    /*
     * 响应载荷（17 字节）：
     * [0]     Status         u8
     * [1-3]   FwVersion      u8[3]   主.次.补丁
     * [4-7]   SerialNum      u32     设备序列号
     * [8-11]  ModelID        u8[4]   "HXB1"
     * [12-13] Capabilities   u16     功能位图
     * [14-15] MaxPayload     u16     最大载荷长度
     * [16]    ProtoVersion   u8      协议版本
     */
    uint8_t payload[17];

    payload[0] = UBCP_ERR_SUCCESS;

    /* 固件版本 */
    payload[1] = HEX_FW_VERSION_MAJOR;
    payload[2] = HEX_FW_VERSION_MINOR;
    payload[3] = HEX_FW_VERSION_PATCH;

    /* 设备序列号（使用 ESP32 MAC 地址后 4 字节） */
    uint8_t mac[6];
    esp_efuse_mac_get_default(mac);
    payload[4] = mac[2];
    payload[5] = mac[3];
    payload[6] = mac[4];
    payload[7] = mac[5];

    /* 型号 */
    memcpy(&payload[8], HEX_MODEL_ID, 4);

    /* 能力位图 */
    uint16_t caps = UBCP_CAP_CAN | UBCP_CAP_CAN_FD | UBCP_CAP_SPI |
                    UBCP_CAP_I2C | UBCP_CAP_UART | UBCP_CAP_ETH |
                    UBCP_CAP_TCP | UBCP_CAP_UDP | UBCP_CAP_WEBSOCKET |
                    UBCP_CAP_GPIO | UBCP_CAP_BULK | UBCP_CAP_OTA;
    payload[12] = (uint8_t)(caps >> 8);
    payload[13] = (uint8_t)(caps & 0xFF);

    /* 最大载荷 */
    payload[14] = (uint8_t)(UBCP_MAX_PAYLOAD_LEN >> 8);
    payload[15] = (uint8_t)(UBCP_MAX_PAYLOAD_LEN & 0xFF);

    /* 协议版本 */
    payload[16] = HEX_PROTO_VERSION;

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);

    msg_bus_send_frame(&resp);
}

/* ========================================================================
 * GET_TOPOLOGY 处理 (0x07)
 * ======================================================================== */

typedef struct {
    uint8_t *buf;
    uint16_t offset;
    uint16_t cap;
} topo_iter_ctx_t;

static void topo_collect_cb(uint8_t ch, uint8_t type, void *drv, void *ctx)
{
    (void)drv;
    topo_iter_ctx_t *tc = (topo_iter_ctx_t *)ctx;
    if (tc->offset + 2 <= tc->cap) {
        tc->buf[tc->offset + 0] = ch;
        tc->buf[tc->offset + 1] = type;
        tc->offset += 2;
    }
}

static void handle_get_topology(const ubcp_frame_t *req)
{
    int count = topology_for_each(NULL, NULL);

    /*
     * 响应载荷：
     * [0]       Status       u8
     * [1]       ChannelCount u8
     * [2 + i*2] ChannelID    u8
     * [3 + i*2] DeviceType   u8
     */
    uint16_t plen = 2 + (uint16_t)count * 2;
    uint8_t *payload = malloc(plen);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)count;

    topo_iter_ctx_t tc = {
        .buf    = payload,
        .offset = 2,
        .cap    = plen,
    };
    topology_for_each(topo_collect_cb, &tc);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = plen;
    msg_bus_send_frame(&resp);

    free(payload);
}

/* ========================================================================
 * FLOW_CONTROL 处理 (0x05)
 * ======================================================================== */

static void handle_flow_control(const ubcp_frame_t *req)
{
    /*
     * 主机 → 设备（流控查询）:
     * [0]    ModuleID    u8    0xFF = 全部
     *
     * 响应:
     * [0]    Status      u8
     * [1]    Count       u8    模块数量 N
     * [2...] Reports     N×5  (ModuleID u8 + State u8 + BufUsage u16 + BufPercent u8)
     */
    if (!req->payload || req->payload_len < 1) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t query_module = req->payload[0];

    flow_module_state_t states[MSG_BUS_MAX_MODULES];
    uint8_t total = msg_bus_collect_flow_states(states, MSG_BUS_MAX_MODULES);

    /* 过滤：仅返回匹配的模块或全部 */
    uint8_t matched = 0;
    for (uint8_t i = 0; i < total; i++) {
        if (query_module == 0xFF || states[i].module_id == query_module) {
            matched++;
        }
    }

    /*
     * 响应载荷:
     * [0] Status
     * [1] Count
     * [2+] N × 5 bytes per module
     */
    uint16_t plen = 2 + (uint16_t)matched * 5;
    uint8_t *payload = malloc(plen);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = matched;

    uint8_t pos = 2;
    for (uint8_t i = 0; i < total; i++) {
        if (query_module == 0xFF || states[i].module_id == query_module) {
            uint8_t pct = states[i].buf_capacity > 0 ?
                (uint8_t)((states[i].buf_usage * 100) / states[i].buf_capacity) : 0;
            payload[pos + 0] = states[i].module_id;
            payload[pos + 1] = states[i].state;
            payload[pos + 2] = (uint8_t)(states[i].buf_usage >> 8);
            payload[pos + 3] = (uint8_t)(states[i].buf_usage & 0xFF);
            payload[pos + 4] = pct;
            pos += 5;
        }
    }

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = plen;
    msg_bus_send_frame(&resp);

    free(payload);
}

/* ========================================================================
 * RESET 处理 (0x04)
 * ======================================================================== */

static void handle_reset(const ubcp_frame_t *req)
{
    if (!req->payload || req->payload_len < 1) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t reset_type = req->payload[0];

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);

    vTaskDelay(pdMS_TO_TICKS(50));

    switch (reset_type) {
    case 0x00: /* 软复位 */
        HEX_LOGI(TAG, "执行软复位...");
        esp_restart();
        break;
    case 0x03: /* 硬件看门狗复位 */
        HEX_LOGI(TAG, "触发看门狗复位...");
        while (1) { vTaskDelay(pdMS_TO_TICKS(1000)); }
        break;
    default:
        HEX_LOGW(TAG, "不支持的复位类型: 0x%02X", reset_type);
        break;
    }
}

/* ========================================================================
 * 配置存储（系统全局配置组 0x00）
 * ======================================================================== */

#define MAX_DEVICE_NAME_LEN     32
#define MCP_CONFIG_NVS_NS       "mcp_config"
#define MCP_CONFIG_NVS_KEY      "baud_rate"

static char     s_device_name[MAX_DEVICE_NAME_LEN] = "HXB-Device";
static uint16_t s_heartbeat_interval              = 5000;   /* ms */
static uint8_t  s_flow_control_enable             = 0x01;   /* 启用 */
static uint32_t s_mcp_baud_rate                   = HEX_MCP_UART_BAUD;

/** 只读硬件能力参数 */
#define UART_CHANNEL_COUNT      1
#define CAN_CHANNEL_COUNT       2

/* ========================================================================
 * GET_CONFIG 处理 (0x02)
 * ======================================================================== */

/**
 * 在动态分配的缓冲区中构建 GET_CONFIG 响应载荷。
 * 调用者负责释放返回的指针，或通过 payload 字段传递。
 *
 * 响应载荷格式：
 * [0]    Status       u8
 * [1]    ConfigGroup  u8
 * [2]    ConfigKey    u8
 * [3-4]  ValueLen     u16  大端
 * [5+]   Value
 */
static void handle_get_config(const ubcp_frame_t *req)
{
    if (!req->payload || req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t group = req->payload[0];
    uint8_t key   = req->payload[1];

    if (group != 0x00) {
        /* 目前仅支持系统全局配置组 */
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    /* 先确定 value 指针和长度 */
    const uint8_t *value     = NULL;
    uint16_t       value_len = 0;
    uint8_t        tmp_buf[4];

    switch (key) {
    case UBCP_CFGKEY_DEVICE_NAME:
        value     = (const uint8_t *)s_device_name;
        value_len = (uint16_t)strlen(s_device_name);
        break;

    case UBCP_CFGKEY_HEARTBEAT_INTERVAL:
        tmp_buf[0] = (uint8_t)(s_heartbeat_interval >> 8);
        tmp_buf[1] = (uint8_t)(s_heartbeat_interval & 0xFF);
        value     = tmp_buf;
        value_len = 2;
        break;

    case UBCP_CFGKEY_FLOW_CONTROL_ENABLE:
        value     = &s_flow_control_enable;
        value_len = 1;
        break;

    case UBCP_CFGKEY_UART_CHANNEL_COUNT: {
        static const uint8_t uart_cnt = UART_CHANNEL_COUNT;
        value     = &uart_cnt;
        value_len = 1;
        break;
    }

    case UBCP_CFGKEY_CAN_CHANNEL_COUNT: {
        static const uint8_t can_cnt = CAN_CHANNEL_COUNT;
        value     = &can_cnt;
        value_len = 1;
        break;
    }

    case UBCP_CFGKEY_MCP_BAUD_RATE:
        tmp_buf[0] = (uint8_t)(s_mcp_baud_rate >> 24);
        tmp_buf[1] = (uint8_t)(s_mcp_baud_rate >> 16);
        tmp_buf[2] = (uint8_t)(s_mcp_baud_rate >> 8);
        tmp_buf[3] = (uint8_t)(s_mcp_baud_rate & 0xFF);
        value     = tmp_buf;
        value_len = 4;
        break;

    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    /* 构建响应：Status(1) + Group(1) + Key(1) + ValueLen(2) + Value(V) */
    uint16_t plen = 5 + value_len;
    uint8_t *payload = malloc(plen);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = group;
    payload[2] = key;
    payload[3] = (uint8_t)(value_len >> 8);
    payload[4] = (uint8_t)(value_len & 0xFF);
    if (value_len > 0) {
        memcpy(&payload[5], value, value_len);
    }

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = plen;
    msg_bus_send_frame(&resp);

    free(payload);
}

/* ========================================================================
 * SET_CONFIG 处理 (0x03)
 * ======================================================================== */

static void handle_set_config(const ubcp_frame_t *req)
{
    if (!req->payload || req->payload_len < 4) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t  group     = req->payload[0];
    uint8_t  key       = req->payload[1];
    uint16_t value_len = ((uint16_t)req->payload[2] << 8) | req->payload[3];

    if (group != 0x00) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    /* 只读检查：仅真正的只读配置项不可写入 */
    if (key == UBCP_CFGKEY_UART_CHANNEL_COUNT || key == UBCP_CFGKEY_CAN_CHANNEL_COUNT) {
        HEX_LOGW(TAG, "SET_CONFIG 拒绝写入只读 Key 0x%02X", key);
        msg_bus_send_status_response(req, UBCP_ERR_PERMISSION);
        return;
    }

    /* 检查载荷长度是否足够 */
    uint16_t expected_total = 4 + value_len;  /* group(1)+key(1)+vallen(2)+value(V) */
    if (req->payload_len < expected_total) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    const uint8_t *value = &req->payload[4];

    switch (key) {
    case UBCP_CFGKEY_DEVICE_NAME: {
        if (value_len == 0 || value_len >= MAX_DEVICE_NAME_LEN) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        memcpy(s_device_name, value, value_len);
        s_device_name[value_len] = '\0';
        HEX_LOGI(TAG, "DeviceName 已更新为: %s", s_device_name);
        break;
    }

    case UBCP_CFGKEY_HEARTBEAT_INTERVAL: {
        if (value_len != 2) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        s_heartbeat_interval = ((uint16_t)value[0] << 8) | value[1];
        HEX_LOGI(TAG, "HeartbeatInterval 已更新为: %u ms", s_heartbeat_interval);
        break;
    }

    case UBCP_CFGKEY_FLOW_CONTROL_ENABLE: {
        if (value_len != 1 || value[0] > 0x01) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        s_flow_control_enable = value[0];
        HEX_LOGI(TAG, "FlowControlEnable 已更新为: 0x%02X", s_flow_control_enable);
        break;
    }

    case UBCP_CFGKEY_MCP_BAUD_RATE: {
        if (value_len != 4) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        uint32_t new_baud = ((uint32_t)value[0] << 24) |
                            ((uint32_t)value[1] << 16) |
                            ((uint32_t)value[2] << 8)  |
                             (uint32_t)value[3];
        if (new_baud < 9600 || new_baud > 5000000) {
            HEX_LOGW(TAG, "MCP 波特率 %lu 超出有效范围 (9600-5000000)", new_baud);
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }

        nvs_handle_t nvs_handle;
        esp_err_t err = nvs_open(MCP_CONFIG_NVS_NS, NVS_READWRITE, &nvs_handle);
        if (err != ESP_OK) {
            HEX_LOGE(TAG, "打开 NVS 失败: 0x%x", err);
            msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
            return;
        }
        err = nvs_set_u32(nvs_handle, MCP_CONFIG_NVS_KEY, new_baud);
        if (err != ESP_OK) {
            HEX_LOGE(TAG, "NVS 写入失败: 0x%x", err);
            nvs_close(nvs_handle);
            msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
            return;
        }
        nvs_commit(nvs_handle);
        nvs_close(nvs_handle);

        s_mcp_baud_rate = new_baud;
        HEX_LOGI(TAG, "McpBaudRate 已更新为: %lu bps (需软复位生效)", new_baud);
        break;
    }

    default:
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

uint32_t mod_system_get_mcp_baud_rate(void)
{
    return s_mcp_baud_rate;
}

static esp_err_t system_init(void)
{
    nvs_handle_t nvs_handle;
    if (nvs_open(MCP_CONFIG_NVS_NS, NVS_READONLY, &nvs_handle) == ESP_OK) {
        uint32_t stored_baud = 0;
        if (nvs_get_u32(nvs_handle, MCP_CONFIG_NVS_KEY, &stored_baud) == ESP_OK) {
            if (stored_baud >= 9600 && stored_baud <= 5000000) {
                s_mcp_baud_rate = stored_baud;
                HEX_LOGI(TAG, "从 NVS 加载 MCP 波特率: %lu", s_mcp_baud_rate);
            } else {
                HEX_LOGW(TAG, "NVS 中 MCP 波特率 %lu 无效，使用默认值 %lu",
                         stored_baud, (unsigned long)HEX_MCP_UART_BAUD);
            }
        }
        nvs_close(nvs_handle);
    }
    HEX_LOGI(TAG, "系统管理模块初始化 (MCP 波特率: %lu)", s_mcp_baud_rate);
    return ESP_OK;
}

static void system_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_PING:
        handle_ping(frame);
        break;

    case UBCP_CMD_GET_INFO:
        handle_get_info(frame);
        break;

    case UBCP_CMD_FLOW_CONTROL:
        handle_flow_control(frame);
        break;

    case UBCP_CMD_GET_CONFIG:
        handle_get_config(frame);
        break;

    case UBCP_CMD_SET_CONFIG:
        handle_set_config(frame);
        break;

    case UBCP_CMD_RESET:
        handle_reset(frame);
        break;

    case UBCP_CMD_GET_TOPOLOGY:
        handle_get_topology(frame);
        break;

    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

/* 模块定义（静态生命周期） */
static const hex_module_t s_system_module = {
    .name            = "System",
    .cmd_range_start = UBCP_CMD_RANGE_SYSTEM_START,
    .cmd_range_end   = UBCP_CMD_RANGE_SYSTEM_END,
    .init            = system_init,
    .handle_cmd      = system_handle_cmd,
    .stop            = NULL,
};

const hex_module_t *mod_system_get(void)
{
    return &s_system_module;
}
