/* Archived legacy LAN8720 initialization path. Not part of the active build. */
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

static const char *TAG = "eth_init_archived";
static esp_eth_handle_t s_eth_handle = NULL;
static esp_netif_t *s_netif = NULL;
static uint8_t s_mac_addr[6] = {0x28, 0x56, 0x2f, 0x8f, 0x82, 0x88};

esp_eth_handle_t eth_get_handle(void) { return s_eth_handle; }
esp_netif_t *eth_get_netif(void) { return s_netif; }
void eth_get_mac_addr(uint8_t mac[6]) { memcpy(mac, s_mac_addr, 6); }

esp_err_t eth_hw_init(esp_eth_handle_t *out_eth_handle)
{
    ESP_LOGI(TAG, "LAN8720 Ethernet initialization (archived)");
    ESP_LOGI(TAG, "  MDC=GPIO%d, MDIO=GPIO%d, RST=GPIO%d",
             HEX_ETH_MDC_PIN, HEX_ETH_MDIO_PIN, HEX_ETH_PHY_RST_PIN);

    esp_netif_init();
    esp_event_loop_create_default();

    eth_mac_config_t mac_config = ETH_MAC_DEFAULT_CONFIG();
    eth_esp32_emac_config_t emac_config = ETH_ESP32_EMAC_DEFAULT_CONFIG();
    emac_config.smi_gpio.mdc_num = HEX_ETH_MDC_PIN;
    emac_config.smi_gpio.mdio_num = HEX_ETH_MDIO_PIN;
    emac_config.mdc_freq_hz = 250000;
    esp_eth_mac_t *mac = esp_eth_mac_new_esp32(&emac_config, &mac_config);
    if (!mac) return ESP_FAIL;

    gpio_set_pull_mode(HEX_ETH_MDIO_PIN, GPIO_PULLUP_ONLY);
    eth_phy_config_t phy_config = ETH_PHY_DEFAULT_CONFIG();
    phy_config.phy_addr = 0x01;
    phy_config.reset_gpio_num = -1;
    esp_eth_phy_t *phy = esp_eth_phy_new_lan87xx(&phy_config);
    if (!phy) {
        mac->del(mac);
        return ESP_FAIL;
    }

    esp_eth_config_t config = ETH_DEFAULT_CONFIG(mac, phy);
    esp_err_t ret = esp_eth_driver_install(&config, &s_eth_handle);
    if (ret != ESP_OK) {
        mac->del(mac);
        phy->del(phy);
        return ret;
    }
    esp_eth_ioctl(s_eth_handle, ETH_CMD_S_MAC_ADDR, s_mac_addr);

    esp_netif_config_t netif_config = ESP_NETIF_DEFAULT_ETH();
    s_netif = esp_netif_new(&netif_config);
    if (!s_netif) return ESP_FAIL;
    esp_eth_netif_glue_handle_t glue = esp_eth_new_netif_glue(s_eth_handle);
    if (!glue) return ESP_FAIL;
    ESP_ERROR_CHECK(esp_netif_attach(s_netif, glue));
    if (out_eth_handle) *out_eth_handle = s_eth_handle;
    return ESP_OK;
}

esp_err_t eth_hw_start(void)
{
    if (!s_eth_handle) return ESP_ERR_INVALID_STATE;
    return esp_eth_start(s_eth_handle);
}
