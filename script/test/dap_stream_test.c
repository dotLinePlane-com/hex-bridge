/* Host-only framing regression: cc -std=c11 -Wall -Wextra -Werror
 * -Imain/dap main/dap/dap_stream.c script/test/dap_stream_test.c -o dap_test */
#include "dap_stream.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned calls;
static size_t output_size, chunk = 3;
static ptrdiff_t forced_write = 1;
static uint8_t output[4096];
static size_t execute(const uint8_t *request, size_t size, uint8_t *response, size_t cap)
{
    assert(size <= cap);
    ++calls;
    memcpy(response, request, size);
    return size;
}
static ptrdiff_t write_response(void *ctx, const uint8_t *data, size_t length)
{
    (void)ctx;
    if (forced_write <= 0) return forced_write;
    if (length > chunk) length = chunk;
    assert(output_size + length <= sizeof(output));
    memcpy(output + output_size, data, length);
    output_size += length;
    return (ptrdiff_t)length;
}
static void reset(dap_stream_t *s)
{
    dap_stream_reset(s); calls = 0; output_size = 0; forced_write = 1; chunk = 3;
}
static bool feed(dap_stream_t *s, const uint8_t *data, size_t length)
{
    return dap_stream_feed(s, data, length, execute, write_response, NULL);
}
int main(void)
{
    dap_stream_t s;
    const uint8_t frame[] = {'D','A','P',0,2,0,1,0,0,0xfe};
    /* Every split position, including header and payload boundaries. */
    for (size_t split = 0; split <= sizeof(frame); ++split) {
        reset(&s);
        assert(feed(&s, frame, split));
        assert(feed(&s, frame + split, sizeof(frame) - split));
        assert(calls == 1 && output_size == sizeof(frame));
        assert(output[6] == 2 && output[7] == 0);
        assert(memcmp(output + 8, frame + 8, 2) == 0);
    }
    reset(&s);
    uint8_t combined[sizeof(frame) * 3];
    for (unsigned i = 0; i < 3; ++i) memcpy(combined + i * sizeof(frame), frame, sizeof(frame));
    assert(feed(&s, combined, sizeof(combined)) && calls == 3);
    reset(&s);
    for (size_t i = 0; i < sizeof(combined); ++i) assert(feed(&s, combined + i, 1));
    assert(calls == 3);
    /* Strict signature, empty/oversize lengths, request type and reserved byte. */
    const unsigned offsets[] = {0,1,2,3,4,5,6,7};
    for (unsigned i = 0; i < sizeof(offsets)/sizeof(offsets[0]); ++i) {
        uint8_t bad[sizeof(frame)]; memcpy(bad, frame, sizeof(frame));
        bad[offsets[i]] = offsets[i] == 4 ? 0 : (offsets[i] == 5 ? 5 : 0xff);
        reset(&s);
        assert(!feed(&s, bad, sizeof(bad)) && calls == 0);
        assert(!feed(&s, frame, sizeof(frame))); /* Sticky fatal state. */
        dap_stream_reset(&s);
        assert(feed(&s, frame, sizeof(frame)) && calls == 1);
    }
    uint8_t maximum[8 + DAP_PACKET_SIZE] = {'D','A','P',0,0,4,1,0};
    memset(maximum + 8, 0xa5, DAP_PACKET_SIZE);
    reset(&s); chunk = 1;
    assert(feed(&s, maximum, sizeof(maximum)) && calls == 1);
    assert(output_size == sizeof(maximum) && output[4] == 0 && output[5] == 4);
    for (ptrdiff_t fail = -1; fail <= 0; ++fail) {
        reset(&s); forced_write = fail;
        assert(!feed(&s, frame, sizeof(frame)) && calls == 1);
    }
    reset(&s);
    assert(feed(&s, frame, 9) && calls == 0);
    dap_stream_reset(&s); /* Disconnect discards partial commands. */
    assert(feed(&s, frame, sizeof(frame)) && calls == 1);
    puts("DAP stream: fragmentation, coalescing, strict headers, 1024-byte bounds, short/failed writes, reset PASS");
    return 0;
}
