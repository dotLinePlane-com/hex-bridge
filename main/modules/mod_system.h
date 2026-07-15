/**
 * @file mod_system.h
 * @brief 系统管理模块接口 (0x00-0x0F)
 *
 * 处理 PING、GET_INFO 等系统级命令。
 */

#pragma once

#include "core/module_base.h"

const hex_module_t *mod_system_get(void);

void mod_system_send_boot_event(void);
