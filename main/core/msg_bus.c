/**
 * @file msg_bus.c
 * @brief HEX-Bridge 消息总线实现
 *
 * 核心功能：
 * - 模块注册表（命令码范围 → 模块处理函数）
 * - 命令路由分发
 * - 帧构建与发送（通过 MCP 传输层）
 */

#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "core/msg_bus.h"
#include "transport/mcp_transport.h"
#include "utils/hex_log.h"

static const char *TAG = "msg_bus";

/* ========================================================================
 * 模块注册表
 * ======================================================================== */

static const hex_module_t *s_modules[MSG_BUS_MAX_MODULES];
static int s_module_count = 0;

/* ========================================================================
 * 流控状态
 * ======================================================================== */

static flow_module_state_t s_flow_states[MSG_BUS_MAX_MODULES];
static int s_flow_state_count = 0;

/* ========================================================================
 * 帧发送缓冲区（每次构建线路帧时使用）
 * ======================================================================== */

/*
 * 最大线路帧大小估算：
 * SOF(2) + (Header(8) + Timestamp(4) + Payload(2048) + CRC(2)) * 2(最坏转义) + EOF(1)
 * = 2 + 2062*2 + 1 = 4127 字节
 * 取 4200 字节足够
 */
#define WIRE_FRAME_BUF_SIZE     4200

/** 线路帧构建缓冲区（静态分配，避免栈溢出） */
static uint8_t s_wire_buf[WIRE_FRAME_BUF_SIZE];

/** 发送互斥锁（保护 s_wire_buf 和 UART 发送） */
static SemaphoreHandle_t s_bus_mutex = NULL;

esp_err_t msg_bus_init(void)
{
    s_module_count = 0;
    memset(s_modules, 0, sizeof(s_modules));

    s_bus_mutex = xSemaphoreCreateMutex();
    if (s_bus_mutex == NULL) {
        HEX_LOGE(TAG, "消息总线互斥锁创建失败");
        return ESP_ERR_NO_MEM;
    }

    HEX_LOGI(TAG, "消息总线初始化完成");
    return ESP_OK;
}

esp_err_t msg_bus_register_module(const hex_module_t *module)
{
    if (s_module_count >= MSG_BUS_MAX_MODULES) {
        HEX_LOGE(TAG, "模块注册失败：超过最大数量 %d", MSG_BUS_MAX_MODULES);
        return ESP_ERR_NO_MEM;
    }

    /* 检查命令码范围冲突 */
    for (int i = 0; i < s_module_count; i++) {
        const hex_module_t *existing = s_modules[i];
        if (!(module->cmd_range_end < existing->cmd_range_start ||
              module->cmd_range_start > existing->cmd_range_end)) {
            HEX_LOGE(TAG, "模块 '%s' 命令码范围 [0x%02X-0x%02X] 与 '%s' [0x%02X-0x%02X] 冲突",
                     module->name, module->cmd_range_start, module->cmd_range_end,
                     existing->name, existing->cmd_range_start, existing->cmd_range_end);
            return ESP_ERR_INVALID_ARG;
        }
    }

    s_modules[s_module_count++] = module;
    HEX_LOGI(TAG, "模块 '%s' 已注册，命令码范围 [0x%02X-0x%02X]",
             module->name, module->cmd_range_start, module->cmd_range_end);
    return ESP_OK;
}

void msg_bus_dispatch(const ubcp_frame_t *frame)
{
    uint8_t cmd = frame->cmd_code;

    for (int i = 0; i < s_module_count; i++) {
        const hex_module_t *mod = s_modules[i];
        if (cmd >= mod->cmd_range_start && cmd <= mod->cmd_range_end) {
            HEX_LOGD(TAG, "路由 CMD=0x%02X → 模块 '%s'", cmd, mod->name);
            mod->handle_cmd(frame);
            return;
        }
    }

    /* 未找到处理模块 */
    HEX_LOGW(TAG, "未注册的命令码 0x%02X，发送 ERR_NOT_SUPPORT", cmd);
    msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
}

esp_err_t msg_bus_send_frame(const ubcp_frame_t *frame)
{
    if (xSemaphoreTake(s_bus_mutex, pdMS_TO_TICKS(1000)) != pdTRUE) {
        HEX_LOGW(TAG, "消息总线互斥锁超时");
        return ESP_ERR_TIMEOUT;
    }

    size_t wire_len = 0;
    esp_err_t err = ubcp_frame_build(frame, s_wire_buf, sizeof(s_wire_buf), &wire_len);
    if (err != ESP_OK) {
        HEX_LOGE(TAG, "帧构建失败: 0x%x", err);
        xSemaphoreGive(s_bus_mutex);
        return err;
    }

    err = mcp_transport_send(s_wire_buf, wire_len);

    xSemaphoreGive(s_bus_mutex);
    return err;
}

esp_err_t msg_bus_send_status_response(const ubcp_frame_t *req, uint8_t status)
{
    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);

    resp.payload     = &status;
    resp.payload_len = 1;

    return msg_bus_send_frame(&resp);
}

/* ========================================================================
 * 流控状态管理
 * ======================================================================== */

void msg_bus_update_flow_state(uint8_t module_id, uint8_t state,
                               uint16_t buf_usage, uint16_t buf_capacity)
{
    for (int i = 0; i < s_flow_state_count; i++) {
        if (s_flow_states[i].module_id == module_id) {
            s_flow_states[i].state        = state;
            s_flow_states[i].buf_usage    = buf_usage;
            s_flow_states[i].buf_capacity = buf_capacity;
            return;
        }
    }

    if (s_flow_state_count < MSG_BUS_MAX_MODULES) {
        s_flow_states[s_flow_state_count].module_id   = module_id;
        s_flow_states[s_flow_state_count].state       = state;
        s_flow_states[s_flow_state_count].buf_usage   = buf_usage;
        s_flow_states[s_flow_state_count].buf_capacity = buf_capacity;
        s_flow_state_count++;
    }
}

uint8_t msg_bus_collect_flow_states(flow_module_state_t *out, uint8_t max_count)
{
    uint8_t count = 0;
    for (int i = 0; i < s_flow_state_count && count < max_count; i++) {
        out[count] = s_flow_states[i];
        count++;
    }
    return count;
}
