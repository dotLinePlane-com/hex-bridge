#pragma once
#include "protocol/ubcp_frame.h"

enum profile_feature
{
    PF_SERIAL = 1,
    PF_CONTROL_TCP = 2,
    PF_CAN = 4,
    PF_UART = 8,
    PF_WIFI = 16,
    PF_TCP = 32,
    PF_UDP = 64,
    PF_WS = 128,
    PF_DAP = 256,
    PF_ALL = 511,
    PF_SPI = 512,
    PF_I2C = 1024,
    PF_GPIO = 2048
};
enum profile_signal
{
    SIG_UART_TX,
    SIG_UART_RX,
    SIG_CAN_SCK,
    SIG_CAN_MOSI,
    SIG_CAN_MISO,
    SIG_CAN_CS,
    SIG_CAN_INT,
    SIG_SWCLK,
    SIG_SWDIO,
    SIG_COUNT
};

void profile_init(void);
void profile_driver_failed(void);
bool profile_is_trial(void);
bool profile_enabled(enum profile_feature feature);
int profile_pin(enum profile_signal signal);
void profile_command(const ubcp_frame_t *request);

void profile_boot_ready(void);
void profile_network_ready(void);
bool profile_wifi_forget_allowed(void);
int profile_spi_host(bool can);
int profile_spi_pin(int host, int index);
int profile_spi_width(int host);
bool profile_spi_enabled(int host);
int profile_spi_cs(bool can);
uint32_t profile_spi_clock(bool can);
/* Ordinary SPI device instances are zero-based; 0xff means no chip select. */
bool profile_spi_device_enabled(int instance);
int profile_spi_device_host(int instance);
int profile_spi_device_cs(int instance);
bool profile_uart1_business_enabled(void);

bool profile_spi_slave(int host);
int profile_spi_slave_cs(int host);

#define PROFILE_I2C_COUNT 2
#define PROFILE_GPIO_COUNT 14
typedef struct
{
    uint8_t enabled, scl, sda, speed, timeout_hi, timeout_lo;
} profile_i2c_t;
typedef struct
{
    uint8_t pin, flags, pull, trigger, debounce;
} profile_gpio_t;
const profile_i2c_t *profile_i2c(int instance);
const profile_gpio_t *profile_gpio(int route);
/* Board electrical policy, independent of current ownership. */
bool profile_gpio_capable(int pin, int mode, int pull, int trigger);
