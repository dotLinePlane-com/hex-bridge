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

#include "core/device_profile.h"
#include "hex_config.h"
#include "utils/hex_log.h"
#include "core/msg_bus.h"
#include "core/topology.h"
#include "transport/mcp_transport.h"
#include "dap/dap_server.h"
#include "dap/dap_engine.h"
#include "modules/mod_system.h"
#include "modules/mod_uart.h"
#include "modules/mod_network.h"
#include "modules/mod_tcp.h"
#include "modules/mod_udp.h"
#include "modules/mod_ws.h"
#include "modules/mod_can.h"
#include "modules/mod_spi.h"

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
    if (ret != ESP_OK) {
        /* Keep UART/CAN alive; do not erase previously saved credentials. */
        HEX_LOGE(TAG, "NVS unavailable: 0x%x; persistent settings disabled", ret);
    }

    /* ── 2. 初始化消息总线 ── */
    ESP_ERROR_CHECK(msg_bus_init());

    /* ── 2.5 初始化硬件拓扑路由表 ── */
    topology_init();

    /* ── 3. 注册功能模块 ── */
    profile_init();
    const struct {
        const hex_module_t *module;
        unsigned feature;
    } modules[] = {
        {mod_system_get(), 0}, {mod_uart_get(), PF_UART}, {mod_can_get(), PF_CAN},
        {mod_tcp_get(), PF_TCP}, {mod_udp_get(), PF_UDP}, {mod_ws_get(), PF_WS},
        {mod_network_get(), PF_WIFI}, {mod_spi_get(), 0},
    };
    for (size_t i = 0; i < sizeof(modules) / sizeof(modules[0]); i++) {
        if (modules[i].feature && !profile_enabled(modules[i].feature)) continue;
        const hex_module_t *module = modules[i].module;
        ESP_ERROR_CHECK(msg_bus_register_module(module));
        if (module->init) ESP_ERROR_CHECK(module->init());
    }
    uint32_t mcp_baud = mod_system_get_mcp_baud_rate();
    ESP_ERROR_CHECK(mcp_transport_init(mcp_baud));
    if (profile_enabled(PF_DAP)) {
        dap_release();
        ret = dap_server_start();
        if (ret != ESP_OK) {
            HEX_LOGE(TAG, "DAP service unavailable: %s", esp_err_to_name(ret));
            profile_driver_failed();
        }
    }
    if (profile_enabled(PF_WIFI)) mod_network_start();

    /* ── 6. 广播 SYS_BOOT_EVENT 通知主机系统复位/启动原因 ── */
    mod_system_send_boot_event();

    HEX_LOGI(TAG, "========================================");
    HEX_LOGI(TAG, "  HEX-Bridge 启动完成，等待 MCP 连接...");
    HEX_LOGI(TAG, "  MCP UART: %lu bps (UART%d)",
             mcp_baud, HEX_MCP_UART_NUM);
    HEX_LOGI(TAG, "========================================");

    /* app_main 可以返回，FreeRTOS 调度器会继续运行各任务 */
}
