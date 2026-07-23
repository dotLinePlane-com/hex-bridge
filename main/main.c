/**
 * @file main.c
 * @brief HEX-Bridge 固件入口
 *
 * 启动流程：
 * 1. 初始化 NVS Flash
 * 2. 初始化消息总线
 * 3. 注册功能模块
 * 4. 初始化 MCP 传输层（启动接收/发送任务）
 * 5. 初始化各功能模块
 *
 * 之后各模块在独立的 FreeRTOS 任务中并发运行。
 */

#include <stdio.h>
#include "sdkconfig.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "nvs_flash.h"

#include "hex_config.h"
#include "utils/hex_log.h"
#include "core/msg_bus.h"
#include "core/topology.h"
#include "transport/mcp_transport.h"
#include "modules/mod_system.h"
#include "modules/mod_uart.h"
#include "modules/mod_network.h"
#include "modules/mod_tcp.h"
#include "modules/mod_udp.h"
#include "modules/mod_ws.h"

static const char *TAG = "main";

void app_main(void)
{
    HEX_LOGI(TAG, "========================================");
    HEX_LOGI(TAG, "  HEX-Bridge v%d.%d.%d 启动中...",
             HEX_FW_VERSION_MAJOR, HEX_FW_VERSION_MINOR, HEX_FW_VERSION_PATCH);
    HEX_LOGI(TAG, "  协议版本: UBCP v2.0");
    HEX_LOGI(TAG, "========================================");

    /* ── 1. 初始化 NVS Flash ── */
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    HEX_LOGI(TAG, "NVS Flash 初始化完成");

    /* ── 2. 初始化消息总线 ── */
    ESP_ERROR_CHECK(msg_bus_init());

    /* ── 2.5 初始化硬件拓扑路由表 ── */
    topology_init();

    /* ── 3. 注册功能模块 ── */
    ESP_ERROR_CHECK(msg_bus_register_module(mod_system_get()));
    ESP_ERROR_CHECK(msg_bus_register_module(mod_uart_get()));
    ESP_ERROR_CHECK(msg_bus_register_module(mod_network_get()));
    ESP_ERROR_CHECK(msg_bus_register_module(mod_tcp_get()));
    ESP_ERROR_CHECK(msg_bus_register_module(mod_udp_get()));
    ESP_ERROR_CHECK(msg_bus_register_module(mod_ws_get()));

    /* ── 4. 初始化各功能模块 ── */
    const hex_module_t *modules[] = {
        mod_system_get(),
        mod_uart_get(),
        mod_network_get(),
        mod_tcp_get(),
        mod_udp_get(),
        mod_ws_get(),
    };
    for (int i = 0; i < sizeof(modules) / sizeof(modules[0]); i++) {
        if (modules[i]->init) {
            ESP_ERROR_CHECK(modules[i]->init());
        }
    }

    /* ── 5. 初始化 MCP 传输层（启动 UART1 收发任务） ── */
    uint32_t mcp_baud = mod_system_get_mcp_baud_rate();
    ESP_ERROR_CHECK(mcp_transport_init(mcp_baud));

    /* ── 6. 广播 SYS_BOOT_EVENT 通知主机系统复位/启动原因 ── */
    mod_system_send_boot_event();

    HEX_LOGI(TAG, "========================================");
    HEX_LOGI(TAG, "  HEX-Bridge 启动完成，等待 MCP 连接...");
    HEX_LOGI(TAG, "  MCP UART: %lu bps (UART%d)",
             mcp_baud, HEX_MCP_UART_NUM);
    HEX_LOGI(TAG, "========================================");

    /* app_main 可以返回，FreeRTOS 调度器会继续运行各任务 */
}
