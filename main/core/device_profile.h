#pragma once
#include "protocol/ubcp_frame.h"

enum profile_feature {
    PF_SERIAL = 1,
    PF_CONTROL_TCP = 2,
    PF_CAN = 4,
    PF_UART = 8,
    PF_WIFI = 16,
    PF_TCP = 32,
    PF_UDP = 64,
    PF_WS = 128,
    PF_DAP = 256,
    PF_ALL = 511
};
enum profile_signal {
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
bool profile_enabled(enum profile_feature feature);
int profile_pin(enum profile_signal signal);
void profile_command(const ubcp_frame_t *request);
