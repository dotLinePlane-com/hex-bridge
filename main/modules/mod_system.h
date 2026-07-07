/**
 * @file mod_system.h
 * @brief 系统管理模块接口 (0x00-0x0F)
 *
 * 处理 PING、GET_INFO 等系统级命令。
 */

#pragma once

#include "core/module_base.h"

/**
 * @brief 获取系统模块定义
 * @return 模块定义指针（静态生命周期）
 */
const hex_module_t *mod_system_get(void);
