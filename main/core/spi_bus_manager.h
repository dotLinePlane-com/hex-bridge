#pragma once
#include "driver/spi_master.h"

/* Lifecycle runs on the module/command dispatcher. Devices retain a reference
 * until removal; IDF device bus acquisition serializes all wire transactions. */
esp_err_t hex_spi_bus_retain(int host);
esp_err_t hex_spi_bus_release(int host);
esp_err_t hex_spi_buses_init(void);
