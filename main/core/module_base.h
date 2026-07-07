/**
 * @file module_base.h
 * @brief HEX-Bridge 模块基类接口定义
 *
 * 所有功能模块（System、UART、CAN、SPI 等）必须实现此接口，
 * 以便通过消息总线统一注册和路由。
 */

#pragma once

#include <stdint.h>
#include "esp_err.h"
#include "protocol/ubcp_frame.h"

/**
 * @brief 模块定义结构体
 *
 * 每个功能模块填充一个 hex_module_t 实例，通过 msg_bus_register_module() 注册。
 * 消息总线根据 cmd_range_start/end 将命令码路由到对应模块的 handle_cmd 函数。
 */
typedef struct {
    const char *name;               /**< 模块名称（日志/调试用） */
    uint8_t     cmd_range_start;    /**< 处理的命令码起始值（含） */
    uint8_t     cmd_range_end;      /**< 处理的命令码结束值（含） */

    /**
     * @brief 模块初始化函数
     *
     * 在 app_main() 启动阶段调用，用于创建任务、分配资源等。
     * @return ESP_OK 成功，其他值表示初始化失败
     */
    esp_err_t (*init)(void);

    /**
     * @brief 命令处理函数
     *
     * 当消息总线收到该模块命令范围内的帧时调用。
     * 模块内部负责解析载荷并构建响应帧。
     *
     * @param frame 解析后的请求帧（只读）
     */
    void (*handle_cmd)(const ubcp_frame_t *frame);

    /**
     * @brief 模块停止函数
     *
     * 清理资源、删除任务。可为 NULL 表示不需要清理。
     */
    void (*stop)(void);
} hex_module_t;
