/**
 * @file hex_log.h
 * @brief HEX-Bridge 日志宏封装
 *
 * 基于 ESP-IDF 的 esp_log 封装，支持通过 HEX_DEBUG_UART_ENABLE 控制开关。
 */

#pragma once

#include "esp_log.h"
#include "hex_config.h"

#if HEX_DEBUG_UART_ENABLE
    #define HEX_LOGE(tag, fmt, ...)     ESP_LOGE(tag, fmt, ##__VA_ARGS__)
    #define HEX_LOGW(tag, fmt, ...)     ESP_LOGW(tag, fmt, ##__VA_ARGS__)
    #define HEX_LOGI(tag, fmt, ...)     ESP_LOGI(tag, fmt, ##__VA_ARGS__)
    #define HEX_LOGD(tag, fmt, ...)     ESP_LOGD(tag, fmt, ##__VA_ARGS__)
    #define HEX_LOGV(tag, fmt, ...)     ESP_LOGV(tag, fmt, ##__VA_ARGS__)
#else
    #define HEX_LOGE(tag, fmt, ...)     do {} while(0)
    #define HEX_LOGW(tag, fmt, ...)     do {} while(0)
    #define HEX_LOGI(tag, fmt, ...)     do {} while(0)
    #define HEX_LOGD(tag, fmt, ...)     do {} while(0)
    #define HEX_LOGV(tag, fmt, ...)     do {} while(0)
#endif
