#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "dap_engine.h"
#define DAP_HEADER_SIZE 8

/* Negative/zero writes fail the session; the socket adapter handles EINTR. */
typedef ptrdiff_t (*dap_stream_write_fn)(void *, const uint8_t *, size_t);
typedef size_t (*dap_stream_execute_fn)(const uint8_t *, size_t, uint8_t *, size_t);
typedef struct {
    uint8_t request[DAP_HEADER_SIZE + DAP_PACKET_SIZE];
    uint8_t response[DAP_HEADER_SIZE + DAP_PACKET_SIZE];
    size_t buffered;
    bool failed;
} dap_stream_t;

void dap_stream_reset(dap_stream_t *stream);
bool dap_stream_feed(dap_stream_t *stream, const uint8_t *data, size_t length,
                     dap_stream_execute_fn execute, dap_stream_write_fn write, void *ctx);
