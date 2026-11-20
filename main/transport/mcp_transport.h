#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"

/* UART1 is always provisioned. One TCP 9500 client exclusively takes over all
 * UBCP traffic while STA has a valid IP. Wi-Fi failure restores UART1. */
esp_err_t mcp_transport_init(uint32_t baud_rate);
esp_err_t mcp_transport_send(const uint8_t *data, size_t len);
void mcp_transport_stop(void);
/* Called after GOT_IP, and BEFORE cleanup on loss/reconfiguration. */
void mcp_transport_set_network_ready(bool ready);
/* Generation zero is reserved for unbound local events. Requests and delayed
 * completions retain a nonzero generation through ubcp_frame_make_response. */
uint32_t mcp_transport_session_id(void);
bool mcp_transport_session_is_current(uint32_t session);
esp_err_t mcp_transport_send_session(const uint8_t *data, size_t len, uint32_t session);
