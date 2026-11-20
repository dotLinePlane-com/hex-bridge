#include "dap_stream.h"
#include <string.h>

void dap_stream_reset(dap_stream_t *s)
{
    s->buffered = 0;
    s->failed = false;
}

bool dap_stream_feed(dap_stream_t *s, const uint8_t *data, size_t length,
                     dap_stream_execute_fn execute, dap_stream_write_fn write, void *ctx)
{
    if (s->failed) return false;
    while (length) {
        size_t target = DAP_HEADER_SIZE;
        if (s->buffered >= DAP_HEADER_SIZE) {
            target += (size_t)s->request[4] | ((size_t)s->request[5] << 8);
        }
        size_t copy = target - s->buffered;
        if (copy > length) copy = length;
        memcpy(s->request + s->buffered, data, copy);
        s->buffered += copy;
        data += copy;
        length -= copy;
        if (s->buffered < DAP_HEADER_SIZE) continue;
        const uint8_t *p = s->request;
        size_t payload = (size_t)p[4] | ((size_t)p[5] << 8);
        if (memcmp(p, "DAP\0", 4) || p[6] != 1 || p[7] != 0 ||
            payload == 0 || payload > DAP_PACKET_SIZE) goto fail;
        if (s->buffered < DAP_HEADER_SIZE + payload) continue;
        size_t response = execute(p + DAP_HEADER_SIZE, payload,
                                  s->response + DAP_HEADER_SIZE, DAP_PACKET_SIZE);
        if (!response || response > DAP_PACKET_SIZE) goto fail;
        memcpy(s->response, "DAP\0", 4);
        s->response[4] = (uint8_t)response;
        s->response[5] = (uint8_t)(response >> 8);
        s->response[6] = 2;
        s->response[7] = 0;
        size_t sent = 0, total = DAP_HEADER_SIZE + response;
        while (sent < total) {
            ptrdiff_t n = write(ctx, s->response + sent, total - sent);
            if (n <= 0 || (size_t)n > total - sent) goto fail;
            sent += (size_t)n;
        }
        s->buffered = 0;
    }
    return true;
fail:
    s->failed = true;
    return false;
}
