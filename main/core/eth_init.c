#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_eth.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "lwip/sockets.h"
#include "hex_config.h"
#include "eth_init.h"

static const char *TAG = "eth_init";

static esp_eth_handle_t s_eth_handle = NULL;
static esp_netif_t *s_netif = NULL;
static uint8_t s_mac_addr[6] = {0x28, 0x56, 0x2f, 0x8f, 0x82, 0x88};

esp_eth_handle_t eth_get_handle(void) { return s_eth_handle; }
esp_netif_t *eth_get_netif(void) { return s_netif; }
void eth_get_mac_addr(uint8_t mac[6]) { memcpy(mac, s_mac_addr, 6); }

esp_err_t eth_hw_init(esp_eth_handle_t *out_eth_handle)
{
    ESP_LOGI(TAG, "以太网初始化 (轻量模式, 仅初始化 netif)");
    esp_netif_init();
    esp_event_loop_create_default();

    gpio_set_direction(HEX_ETH_PHY_RST_PIN, GPIO_MODE_OUTPUT);
    gpio_set_level(HEX_ETH_PHY_RST_PIN, 0);  /* keep in reset for now */
    vTaskDelay(pdMS_TO_TICKS(10));
    ESP_LOGI(TAG, "PHY 保持复位状态, 以太网硬件未激活");

    /* Create a minimal netif for lwIP to be operational */
    esp_netif_config_t cfg = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&cfg);
    if (!s_netif) {
        ESP_LOGE(TAG, "esp_netif_new 失败");
        return ESP_FAIL;
    }

    if (out_eth_handle) {
        *out_eth_handle = s_eth_handle;
    }

    ESP_LOGI(TAG, "以太网轻量初始化完成 (无硬件, 仅 netif 可用)");
    return ESP_OK;
}
