#pragma once
#include <stddef.h>
#include <stdint.h>

#define DAP_PACKET_SIZE 1024U
#define DAP_PACKET_COUNT 1U

/* Single DAP task owns all calls, including release. Buffers must not overlap.
 * Returns 0 for an empty/oversized request or insufficient response capacity.
 * Malformed and unsupported commands return the CMSIS-DAP invalid command byte.
 */
size_t dap_execute(const uint8_t *request, size_t length,
                   uint8_t *response, size_t capacity);
/* Release GPIO and restore command configuration on EVERY transport disconnect. */
void dap_release(void);
