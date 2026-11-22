#pragma once
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"

/* Enabled control transports share one session. TCP takes over while connected.
 * UART1 uses fixed board pins and resumes on disconnect if enabled. */
esp_err_t mcp_transport_init(uint32_t baud_rate);
esp_err_t mcp_transport_send(const uint8_t *data, size_t len);
void mcp_transport_stop(void);
/* Called after GOT_IP, and BEFORE cleanup on loss/reconfiguration. */
void mcp_transport_set_network_ready(bool ready);
/* Generation zero is reserved for unbound local events. Requests and delayed
 * completions retain a nonzero generation through ubcp_frame_make_response. */
uint32_t mcp_transport_session_id(void);
bool mcp_transport_using_tcp(void);
bool mcp_transport_session_is_current(uint32_t session);
esp_err_t mcp_transport_send_session(const uint8_t *data, size_t len, uint32_t session);
/* Drain a just-sent reboot response to this session. UART waits at most 500 ms;
 * TCP sends an ordered FIN and waits at most 1500 ms for peer EOF before close.
 * This quiesces transport I/O; only use immediately before restarting. */
void mcp_transport_prepare_restart(uint32_t session);
