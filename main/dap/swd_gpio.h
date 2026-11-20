#pragma once
#include <stdbool.h>
#include <stdint.h>

bool swd_gpio_connect(void);
void swd_gpio_release(void);
bool swd_gpio_clock(uint32_t hz);
void swd_gpio_drive(bool output);
void swd_gpio_write_bit(unsigned bit);
unsigned swd_gpio_read_bit(void);
void swd_gpio_cycle(void);
uint8_t swd_gpio_pins(uint8_t value, uint8_t select);
bool swd_gpio_has_reset(void);
