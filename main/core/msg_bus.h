/**
 * @file msg_bus.h
 * @brief HEX-Bridge 消息总线接口
 *
 * 消息总线负责：
 * 1. 注册功能模块（按命令码范围）
 * 2. 将解析后的请求帧分发到对应模块
 * 3. 将响应帧/事件帧发送到 MCP 传输层
 */

#pragma once

#include "esp_err.h"
#include "protocol/ubcp_frame.h"
#include "core/module_base.h"

/** 支持的最大模块数量 */
#define MSG_BUS_MAX_MODULES     16

/**
 * @brief 初始化消息总线
 * @return ESP_OK 或错误码
 */
esp_err_t msg_bus_init(void);

/**
 * @brief 注册一个功能模块
 *
 * 模块的命令码范围不可与已注册模块重叠。
 *
 * @param module    模块定义指针（内容由调用者管理，生命周期需持续到程序结束）
 * @return ESP_OK 或 ESP_ERR_NO_MEM（模块数超限）
 */
esp_err_t msg_bus_register_module(const hex_module_t *module);

/**
 * @brief 分发一个请求帧到对应模块
 *
 * 由 MCP 接收任务调用。根据帧的 CmdCode 查找注册模块并调用其 handle_cmd。
 *
 * @param frame 解析后的请求帧
 */
void msg_bus_dispatch(const ubcp_frame_t *frame);

/**
 * @brief 发送一个响应帧或事件帧到 MCP 传输层
 *
 * 将帧编码（构建线路帧）后放入 MCP 发送队列。
 * 可从任意任务调用（线程安全）。
 *
 * @param frame 待发送的帧
 * @return ESP_OK 或 ESP_ERR_TIMEOUT（发送队列满）
 */
esp_err_t msg_bus_send_frame(const ubcp_frame_t *frame);

/**
 * @brief 快速发送一个简单的状态响应（仅含 1 字节 Status）
 *
 * 便捷函数：基于请求帧构建响应，载荷只有一个 status 字节。
 *
 * @param req       请求帧
 * @param status    状态码
 * @return ESP_OK 或错误码
 */
esp_err_t msg_bus_send_status_response(const ubcp_frame_t *req, uint8_t status);

/* ========================================================================
 * 流控状态管理
 * ======================================================================== */

/** 流控状态记录 */
typedef struct {
    uint8_t  module_id;
    uint8_t  state;          /**< 0=normal, 1=paused(XOFF) */
    uint16_t buf_usage;      /**< 当前缓冲区使用量 */
    uint16_t buf_capacity;   /**< 缓冲区总容量 */
} flow_module_state_t;

/**
 * @brief 更新模块流控状态
 * @param module_id  模块 ID (命令码范围前缀)
 * @param state      状态: 0=normal, 1=paused(XOFF)
 * @param buf_usage  缓冲区使用量
 * @param buf_capacity 缓冲区容量
 */
void msg_bus_update_flow_state(uint8_t module_id, uint8_t state,
                               uint16_t buf_usage, uint16_t buf_capacity);

/**
 * @brief 获取所有已更新过流控状态的模块数量
 * @param out        输出数组
 * @param max_count  数组最大容量
 * @return 实际收集到的模块数量
 */
uint8_t msg_bus_collect_flow_states(flow_module_state_t *out, uint8_t max_count);
