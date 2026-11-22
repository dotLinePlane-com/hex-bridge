#include "core/spi_bus_manager.h"
#include "core/device_profile.h"

static unsigned references[2];
static bool configured[2];

esp_err_t hex_spi_buses_init(void)
{
    bool added[2] = {false, false};
    for (int i = 0; i < 2; ++i) {
        if (configured[i] || (!profile_spi_enabled(i + 2) || profile_spi_slave(i + 2))) continue;
        esp_err_t err = hex_spi_bus_retain(i == 0 ? SPI2_HOST : SPI3_HOST);
        if (err != ESP_OK) {
            for (int j = 0; j < i; ++j) if (added[j]) {
                hex_spi_bus_release(j == 0 ? SPI2_HOST : SPI3_HOST);
                configured[j] = false;
            }
            return err;
        }
        configured[i] = added[i] = true;
    }
    return ESP_OK;
}

esp_err_t hex_spi_bus_retain(int host)
{
    if ((host != SPI2_HOST && host != SPI3_HOST) ||
        (!profile_spi_enabled(host == SPI2_HOST ? 2 : 3) ||
         profile_spi_slave(host == SPI2_HOST ? 2 : 3))) return ESP_ERR_INVALID_ARG;
    unsigned *refs = &references[host == SPI2_HOST ? 0 : 1];
    if (*refs) { ++*refs; return ESP_OK; }
    int instance = host == SPI2_HOST ? 2 : 3;
    bool quad = profile_spi_width(instance) == 4;
    spi_bus_config_t bus = {
        .sclk_io_num = profile_spi_pin(instance, 0),
        .mosi_io_num = profile_spi_pin(instance, 1),
        .miso_io_num = profile_spi_pin(instance, 2),
        .quadwp_io_num = quad ? profile_spi_pin(instance, 3) : -1,
        .quadhd_io_num = quad ? profile_spi_pin(instance, 4) : -1,
        .max_transfer_sz = 4096,
        .flags = SPICOMMON_BUSFLAG_MASTER | (quad ? SPICOMMON_BUSFLAG_QUAD : 0),
    };
    /* ESP32 host/DMA pairing must not depend on which configured host starts
     * first. SPI3 alone with AUTO selects DMA1; on the HXB1 test board that
     * produced corrupt MCP reads (0xFE). Keep the verified SPI2=1/SPI3=2 pair. */
    esp_err_t err = spi_bus_initialize(host, &bus, host == SPI2_HOST ? SPI_DMA_CH1 : SPI_DMA_CH2);
    /* INVALID_STATE means somebody else owns this bus, never adopt it. */
    if (err == ESP_OK) *refs = 1;
    return err;
}

esp_err_t hex_spi_bus_release(int host)
{
    if (host != SPI2_HOST && host != SPI3_HOST) return ESP_ERR_INVALID_ARG;
    unsigned *refs = &references[host == SPI2_HOST ? 0 : 1];
    if (!*refs) return ESP_ERR_INVALID_STATE;
    if (*refs > 1) { --*refs; return ESP_OK; }
    esp_err_t err = spi_bus_free(host);
    if (err == ESP_OK) *refs = 0;
    return err;
}
