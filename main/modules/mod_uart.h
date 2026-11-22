/**
 * @file mod_uart.h
 * @brief UART 扩展模块接口 (0xA0-0xAF)
 *
 * 管理 UART2 (通道1，可改配) 与 UART1 业务模式 (通道2，固定GPIO4/34)：
 * OPEN/CLOSE/CONFIG/SEND/RECV/STATUS/FLUSH/SET_BREAK
 */

#pragma once

#include "core/module_base.h"

/**
 * @brief 获取 UART 扩展模块定义
 * @return 模块定义指针（静态生命周期）
 */
const hex_module_t *mod_uart_get(void);
