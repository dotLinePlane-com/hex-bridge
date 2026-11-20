/* Portable classic ESP32 GPIO implementation; no RISC-V dedicated GPIO dependency.
 * SWD tolerates clock stretching, so interrupts remain enabled for CAN/UART/Wi-Fi.
 * Requested frequency is an upper bound; GPIO call overhead lowers actual speed.
 */
#include "swd_gpio.h"
#include "hex_config.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"

static unsigned half_us = 5; /* conservative 100 kHz at boot */

void swd_gpio_release(void)
{
    gpio_set_direction(HEX_SWD_IO_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(HEX_SWD_IO_GPIO, GPIO_FLOATING);
    gpio_set_direction(HEX_SWD_CLK_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(HEX_SWD_CLK_GPIO, GPIO_FLOATING);
#if HEX_SWD_RESET_ENABLED
    gpio_set_direction(HEX_SWD_RESET_GPIO, GPIO_MODE_INPUT);
    gpio_set_pull_mode(HEX_SWD_RESET_GPIO, GPIO_FLOATING);
#endif
}

bool swd_gpio_connect(void)
{
    swd_gpio_release();
    gpio_set_level(HEX_SWD_CLK_GPIO, 1);
    gpio_set_level(HEX_SWD_IO_GPIO, 1);
    /* gpio_config also routes IO_MUX back to GPIO after a previous peripheral. */
    gpio_config_t cfg = {
        .pin_bit_mask = (1ULL << HEX_SWD_CLK_GPIO) | (1ULL << HEX_SWD_IO_GPIO),
        .mode = GPIO_MODE_INPUT_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    if (gpio_config(&cfg) != ESP_OK) {
        swd_gpio_release();
        return false;
    }
#if HEX_SWD_RESET_ENABLED
    cfg.pin_bit_mask = 1ULL << HEX_SWD_RESET_GPIO;
    cfg.mode = GPIO_MODE_INPUT;
    if (gpio_config(&cfg) != ESP_OK) {
        swd_gpio_release();
        return false;
    }
#endif
    return true;
}

bool swd_gpio_clock(uint32_t hz)
{
    /* Reject clocks that would make a single transaction unreasonably long.
     * Above 250 kHz safely run at 250 kHz, never above the requested rate. */
    if (hz < 10000) return false;
    if (hz > 250000) hz = 250000;
    half_us = (500000U + hz - 1U) / hz;
    return true;
}

void swd_gpio_drive(bool output)
{
    gpio_set_direction(HEX_SWD_IO_GPIO,
                       output ? GPIO_MODE_INPUT_OUTPUT : GPIO_MODE_INPUT);
}

void swd_gpio_cycle(void)
{
    gpio_set_level(HEX_SWD_CLK_GPIO, 0);
    esp_rom_delay_us(half_us);
    gpio_set_level(HEX_SWD_CLK_GPIO, 1);
    esp_rom_delay_us(half_us);
}

void swd_gpio_write_bit(unsigned bit)
{
    /* Change data only while clock is low; target samples the rising edge. */
    gpio_set_level(HEX_SWD_CLK_GPIO, 0);
    gpio_set_level(HEX_SWD_IO_GPIO, bit != 0);
    esp_rom_delay_us(half_us);
    gpio_set_level(HEX_SWD_CLK_GPIO, 1);
    esp_rom_delay_us(half_us);
}

unsigned swd_gpio_read_bit(void)
{
    gpio_set_level(HEX_SWD_CLK_GPIO, 0);
    esp_rom_delay_us(half_us);
    unsigned bit = gpio_get_level(HEX_SWD_IO_GPIO) != 0;
    gpio_set_level(HEX_SWD_CLK_GPIO, 1);
    esp_rom_delay_us(half_us);
    return bit;
}

bool swd_gpio_has_reset(void) { return HEX_SWD_RESET_ENABLED != 0; }

uint8_t swd_gpio_pins(uint8_t value, uint8_t select)
{
    if (select & 1) gpio_set_level(HEX_SWD_CLK_GPIO, value & 1);
    if (select & 2) {
        gpio_set_level(HEX_SWD_IO_GPIO, (value & 2) != 0);
        swd_gpio_drive(true);
    }
#if HEX_SWD_RESET_ENABLED
    if (select & 0x80) {
        /* Open drain: high always means release, never drive target reset high. */
        gpio_set_level(HEX_SWD_RESET_GPIO, 0);
        gpio_set_direction(HEX_SWD_RESET_GPIO,
            (value & 0x80) ? GPIO_MODE_INPUT : GPIO_MODE_OUTPUT_OD);
    }
#endif
    uint8_t pins = (gpio_get_level(HEX_SWD_CLK_GPIO) ? 1 : 0) |
                   (gpio_get_level(HEX_SWD_IO_GPIO) ? 2 : 0);
#if HEX_SWD_RESET_ENABLED
    if (gpio_get_level(HEX_SWD_RESET_GPIO)) pins |= 0x80;
#else
    pins |= 0x80;
#endif
    return pins;
}
