#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "driver/gpio.h"
#include "esp_mac.h"
#include "esp_eth.h"
#include "esp_eth_mac_esp.h"
#include "esp_eth_netif_glue.h"
#include "esp_eth_phy_lan87xx.h"
#include "esp_netif.h"
#include "esp_event.h"
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
    ESP_LOGI(TAG, "LAN8720 以太网硬件初始化...");
    ESP_LOGI(TAG, "  MDC=GPIO%d, MDIO=GPIO%d, RST=GPIO%d",
             HEX_ETH_MDC_PIN, HEX_ETH_MDIO_PIN, HEX_ETH_PHY_RST_PIN);

    /* 1. Initialize netif and event loop (once globally) */
    esp_netif_init();
    esp_event_loop_create_default();

    /* 2. Create ESP32 EMAC instance */
    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_esp32_emac_config_t esp32_emac_config = ETH_ESP32_EMAC_DEFAULT_CONFIG();
    esp32_emac_config.smi_gpio.mdc_num  = HEX_ETH_MDC_PIN;
    esp32_emac_config.smi_gpio.mdio_num = HEX_ETH_MDIO_PIN;
    esp32_emac_config.mdc_freq_hz       = 250000;  /* 250kHz for weak pull-up reliability */

    esp_eth_mac_t *mac = esp_eth_mac_new_esp32(&esp32_emac_config, &mac_config);
    if (!mac) {
        ESP_LOGE(TAG, "esp_eth_mac_new_esp32 失败");
        return ESP_FAIL;
    }

    /* Enable weak internal pull-up on MDIO (GPIO18) — MDIO is open-drain, needs pull-up */
    gpio_set_pull_mode(HEX_ETH_MDIO_PIN, GPIO_PULLUP_ONLY);
    ESP_LOGI(TAG, "MDIO 内部上拉已启用 (GPIO%d)", HEX_ETH_MDIO_PIN);

    /* 4. Create LAN8720 PHY instance */
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.phy_addr          = 0x01;  /* PHYAD0 strapped high → addr=1 */
    phy_config.reset_gpio_num    = -1;

    esp_eth_phy_t *phy = esp_eth_phy_new_lan87xx(&phy_config);
    if (!phy) {
        ESP_LOGE(TAG, "esp_eth_phy_new_lan87xx 失败");
        mac->del(mac);
        return ESP_FAIL;
    }

    /* 5. Install Ethernet driver */
    esp_eth_config_t eth_config = ETH_DEFAULT_CONFIG(mac, phy);
    esp_err_t ret = esp_eth_driver_install(&eth_config, &s_eth_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "esp_eth_driver_install 失败: %d", ret);
        mac->del(mac);
        phy->del(phy);
        return ret;
    }

    /* 6. Set custom MAC address */
    esp_eth_ioctl(s_eth_handle, ETH_CMD_S_MAC_ADDR, s_mac_addr);

    /* 7. Create netif and attach to IP stack */
    esp_netif_config_t cfg = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&cfg);
    if (!s_netif) {
        ESP_LOGE(TAG, "esp_netif_new 失败");
        return ESP_FAIL;
    }

    esp_eth_netif_glue_handle_t glue = esp_eth_new_netif_glue(s_eth_handle);
    if (!glue) {
        ESP_LOGE(TAG, "esp_eth_new_netif_glue 失败");
        return ESP_FAIL;
    }
    ESP_ERROR_CHECK(esp_netif_attach(s_netif, glue));

    ESP_LOGI(TAG, "以太网硬件初始化完成 (未启动, 等待事件处理器注册)");

    if (out_eth_handle) {
        *out_eth_handle = s_eth_handle;
    }

    return ESP_OK;
}

esp_err_t eth_hw_start(void)
{
    if (!s_eth_handle) {
        ESP_LOGE(TAG, "eth 未初始化, 无法启动");
        return ESP_ERR_INVALID_STATE;
    }

    esp_err_t ret = esp_eth_start(s_eth_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "esp_eth_start 失败: %d", ret);
        return ret;
    }

    ESP_LOGI(TAG, "以太网已启动 (DHCP 获取中...)");
    return ESP_OK;
}
