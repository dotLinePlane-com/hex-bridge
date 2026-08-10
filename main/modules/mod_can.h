/**
 * @file mod_can.h
 * @brief CAN FD 模块接口 (0x10-0x1F)
 *
 * 管理 MCP2518FD CAN FD 控制器的完整生命周期：
 * OPEN/CLOSE/CONFIG/SEND/RECV/FILTER/STATUS/BUS_EVENT/ERROR_EVENT/
 * SLEEP/WAKEUP/FILTER_BATCH
 */

#pragma once

#include "core/module_base.h"

/**
 * @brief 获取 CAN 扩展模块定义
 * @return 模块定义指针（静态生命周期）
 */
const hex_module_t *mod_can_get(void);
