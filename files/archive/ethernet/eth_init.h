#pragma once

#include "esp_err.h"
#include "esp_eth.h"
#include "esp_netif.h"

esp_err_t eth_hw_init(esp_eth_handle_t *out_eth_handle);
esp_err_t eth_hw_start(void);
esp_eth_handle_t eth_get_handle(void);
esp_netif_t *eth_get_netif(void);
void eth_get_mac_addr(uint8_t mac[6]);
