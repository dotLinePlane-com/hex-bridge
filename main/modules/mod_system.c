/**
 * @file mod_system.c
 * @brief 系统管理模块实现 (0x00-0x0F)
 *
 * 当前实现：
 * - PING (0x00): 心跳检测，返回 uptime/CPU负载/剩余堆内存
 * - GET_INFO (0x01): 返回固件版本/序列号/型号/能力位图
 *
 * 待实现：GET_CONFIG, SET_CONFIG, RESET, FLOW_CONTROL
 */

#include <string.h>
#include <stdlib.h>
#include "modules/mod_system.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "hex_config.h"
#include "utils/hex_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_chip_info.h"
#include "esp_mac.h"

static const char *TAG = "mod_system";

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
 * 模块入口
 * ======================================================================== */

static esp_err_t system_init(void)
{
    HEX_LOGI(TAG, "系统管理模块初始化");
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
    case UBCP_CMD_SET_CONFIG:
    case UBCP_CMD_RESET:
        HEX_LOGW(TAG, "命令 0x%02X 暂未实现", frame->cmd_code);
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
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
