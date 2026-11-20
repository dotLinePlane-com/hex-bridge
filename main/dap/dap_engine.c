#include "dap_engine.h"
#include "swd_gpio.h"
#include "esp_timer.h"
#include "esp_rom_sys.h"
#include "esp_mac.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

enum { OK = 1, WAIT = 2, FAULT = 4, ERROR = 8, MISMATCH = 16 };
static bool connected, data_phase;
static uint8_t turnaround = 1, idle;
static uint16_t wait_retry = 100, match_retry;
static uint32_t match_mask = UINT32_MAX;
static int64_t deadline;

static uint16_t u16(const uint8_t *p) { return p[0] | ((uint16_t)p[1] << 8); }
static uint32_t u32(const uint8_t *p)
{
    return (uint32_t)u16(p) | ((uint32_t)u16(p + 2) << 16);
}
static void put32(uint8_t *p, uint32_t v)
{
    for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static bool expired(void) { return esp_timer_get_time() >= deadline; }
static void cycles(unsigned n) { while (n--) swd_gpio_cycle(); }
static unsigned parity(uint32_t v)
{
    v ^= v >> 16; v ^= v >> 8; v ^= v >> 4;
    return (0x6996U >> (v & 15)) & 1;
}
static void write_bits(uint32_t value, unsigned n)
{
    while (n--) { swd_gpio_write_bit(value & 1); value >>= 1; }
}
static uint32_t read_bits(unsigned n)
{
    uint32_t v = 0;
    for (unsigned i = 0; i < n; i++) v |= swd_gpio_read_bit() << i;
    return v;
}

static uint8_t wire(uint8_t req, uint32_t *data)
{
    uint32_t value = data ? *data : 0;
    bool read = (req & 2) != 0;
    swd_gpio_drive(true);
    swd_gpio_write_bit(1);
    write_bits(req & 15, 4);
    swd_gpio_write_bit(parity(req & 15));
    swd_gpio_write_bit(0);
    swd_gpio_write_bit(1);
    swd_gpio_drive(false);
    cycles(turnaround);
    uint8_t ack = (uint8_t)read_bits(3);
    if (ack == OK) {
        if (read) {
            value = read_bits(32);
            unsigned p = swd_gpio_read_bit();
            cycles(turnaround);
            swd_gpio_drive(true);
            if (data) *data = value;
            if (p != parity(value)) ack = ERROR;
        } else {
            cycles(turnaround);
            swd_gpio_drive(true);
            write_bits(value, 32);
            swd_gpio_write_bit(parity(value));
        }
        if (idle) { swd_gpio_write_bit(0); cycles(idle - 1U); }
    } else if (ack == WAIT || ack == FAULT) {
        if (data_phase && read) cycles(33);
        cycles(turnaround);
        swd_gpio_drive(true);
        if (data_phase && !read) { swd_gpio_write_bit(0); cycles(32); }
    } else {
        cycles(turnaround + 33U);
        swd_gpio_drive(true);
        ack = ERROR;
    }
    /* Clock remains high; set idle data using pins, without an extra clock. */
    swd_gpio_pins(2, 2);
    return ack;
}

static uint8_t retry(uint8_t req, uint32_t *value)
{
    uint8_t ack = ERROR;
    int64_t retry_until = esp_timer_get_time() + 100000;
    for (unsigned attempt = 0; attempt <= wait_retry; attempt++) {
        if (expired() || esp_timer_get_time() >= retry_until) return ack;
        ack = wire(req, value);
        if (ack != WAIT) break;
        /* Yield retries so a held target cannot monopolize this CPU. */
        if ((attempt & 7U) == 7U) vTaskDelay(1);
    }
    return ack;
}

/* Resolve posted AP reads and deferred write faults before reporting success. */
static uint8_t access_register(uint8_t req, uint32_t *value)
{
    uint8_t ack = retry(req, value);
    if (ack == OK && ((req & 3) == 3 || !(req & 2)))
        ack = retry(0x0e, (req & 2) ? value : NULL);
    return ack;
}

void dap_release(void)
{
    swd_gpio_release();
    connected = data_phase = false;
    turnaround = 1; idle = 0; wait_retry = 100; match_retry = 0;
    match_mask = UINT32_MAX;
    swd_gpio_clock(100000);
}

/* Validate complete variable requests before touching target GPIO. Compute the
 * largest possible reply as well, so capacity failures never partly execute. */
static bool validate(const uint8_t *q, size_t len, size_t *reply)
{
    size_t n = 0;
    *reply = 2;
    switch (q[0]) {
    case 0x00: case 0x02: case 0x13: n = 2; break;
    case 0x01: case 0x09: n = 3; break;
    case 0x03: case 0x07: n = 1; break;
    case 0x0a: n = 1; *reply = 3; break;
    case 0x04: case 0x08: n = 6; break;
    case 0x10: n = 7; break;
    case 0x11: n = 5; break;
    case 0x12:
        if (len < 2) return false;
        n = 2 + ((q[1] ? q[1] : 256U) + 7U) / 8U;
        break;
    case 0x05:
        if (len < 3 || q[1] != 0) return false;
        n = 3; *reply = 3;
        for (unsigned i = 0; i < q[2]; i++) {
            if (n >= len) return false;
            uint8_t r = q[n++];
            /* No timestamp extension; mask updates are write requests only. */
            if ((r & 0xc0) || ((r & 0x20) && (r & 0x12)) ||
                ((r & 0x10) && !(r & 2))) return false;
            if (!(r & 2) || (r & 0x10)) n += 4;
            else *reply += 4;
            if (n > len) return false;
        }
        break;
    case 0x06: {
        if (len < 5 || q[1] != 0 || (q[4] & 0xf0)) return false;
        unsigned count = u16(q + 2);
        /* Bound write and read counts even if caller supplies excessive capacity. */
        if (count > (DAP_PACKET_SIZE - 4) / 4) return false;
        n = 5 + ((q[4] & 2) ? 0 : (size_t)count * 4);
        *reply = 4 + ((q[4] & 2) ? (size_t)count * 4 : 0);
        break;
    }
    case 0x1d:
        if (len < 2) return false;
        n = 2;
        for (unsigned i = 0; i < q[1]; i++) {
            if (n >= len) return false;
            uint8_t info = q[n++];
            if (info & 0x40) return false;
            unsigned bytes = (((info & 63) ? (info & 63) : 64U) + 7) / 8;
            if (info & 0x80) *reply += bytes; else n += bytes;
            if (n > len) return false;
        }
        break;
    default: return false;
    }
    /* Transports may include zero padding, as standard CMSIS-DAP packets do. */
    return n <= len && *reply <= DAP_PACKET_SIZE;
}

static size_t info(uint8_t id, uint8_t *out, size_t cap)
{
    uint8_t data[64]; size_t n = 0;
    const char *s = NULL;
    switch (id) {
    case 1: s = "HEX-Bridge"; break;
    case 2: s = "HEX-Bridge CMSIS-DAP"; break;
    case 3: {
        uint8_t mac[6];
        if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == 0) {
            snprintf((char *)data, sizeof data, "%02X%02X%02X%02X%02X%02X",
                     mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            n = 13;
        }
        break;
    }
    case 4: s = "2.0.0"; break;
    case 9: s = "HEX-Bridge 0.1.0"; break;
    case 0xf0: data[0] = 1; n = 1; break; /* SWD only; no SWO/JTAG/atomic/timestamps */
    case 0xfe: data[0] = DAP_PACKET_COUNT; n = 1; break;
    case 0xff: data[0] = DAP_PACKET_SIZE & 255; data[1] = DAP_PACKET_SIZE >> 8; n = 2; break;
    default: break;
    }
    if (s) { n = strlen(s) + 1; memcpy(data, s, n); }
    if (cap < n + 2) return 0;
    out[0] = 0; out[1] = (uint8_t)n; memcpy(out + 2, data, n);
    return n + 2;
}

size_t dap_execute(const uint8_t *q, size_t len, uint8_t *out, size_t cap)
{
    if (!q || !out || !len || len > DAP_PACKET_SIZE || !cap) return 0;
    size_t needed;
    if (!validate(q, len, &needed)) { out[0] = 0xff; return 1; }
    if (cap < needed) return 0;
    if (q[0] == 0) return info(q[1], out, cap);
    /* A full AP-read packet needs >250 ms even at the default clock. Bound
     * pathological requests while allowing legitimate packets at 10 kHz. */
    deadline = esp_timer_get_time() + 5000000;
    out[0] = q[0]; out[1] = 0;
    switch (q[0]) {
    case 1: if (q[1] > 1 || q[2] > 1) out[1] = 0xff; break;
    case 2:
        if (q[1] <= 1) { connected = swd_gpio_connect(); out[1] = connected ? 1 : 0; }
        else { dap_release(); out[1] = 0; }
        break;
    case 3: dap_release(); break;
    case 4: idle = q[1]; wait_retry = u16(q + 2); match_retry = u16(q + 4); break;
    case 7: break; /* synchronous single-task engine: no transfer remains in flight */
    case 8: {
        uint32_t value = u32(q + 2);
        if (q[1] || !connected || retry(0, &value) != OK) out[1] = 0xff;
        break;
    }
    case 9: esp_rom_delay_us(u16(q + 1)); break;
    case 0x0a:
        /* No device-specific reset sequence. CMSIS status OK, Execute=0 tells
         * the debugger to perform its software reset sequence. */
        out[2] = 0; return 3;
    case 0x11: if (!swd_gpio_clock(u32(q + 1))) out[1] = 0xff; break;
    case 0x13:
        if (q[1] & 0xf8) out[1] = 0xff;
        else { turnaround = (q[1] & 3) + 1; data_phase = (q[1] & 4) != 0; }
        break;
    case 0x10: {
        if (!connected) { out[1] = 0; break; }
        uint8_t select = q[2] & (swd_gpio_has_reset() ? 0x83 : 3);
        out[1] = swd_gpio_pins(q[1], select);
        uint32_t wait = u32(q + 3);
        if (wait > 100000) wait = 100000;
        int64_t until = esp_timer_get_time() + wait;
        while (((out[1] ^ q[1]) & select) && esp_timer_get_time() < until)
            out[1] = swd_gpio_pins(0, 0);
        break;
    }
    case 0x12: {
        if (!connected) { out[1] = 0xff; break; }
        unsigned bits = q[1] ? q[1] : 256U;
        swd_gpio_drive(true);
        for (unsigned i = 0; i < bits; i++) swd_gpio_write_bit((q[2 + i / 8] >> (i % 8)) & 1);
        break;
    }
    case 0x1d: {
        if (!connected) { out[1] = 0xff; break; }
        size_t pos = 2, op = 2;
        for (unsigned i = 0; i < q[1]; i++) {
            if (expired()) { out[1] = 0xff; break; }
            uint8_t seq = q[pos++];
            unsigned bits = (seq & 63) ? (seq & 63) : 64;
            unsigned bytes = (bits + 7) / 8;
            swd_gpio_drive(!(seq & 0x80));
            if (seq & 0x80) {
                memset(out + op, 0, bytes);
                for (unsigned b = 0; b < bits; b++)
                    out[op + b / 8] |= swd_gpio_read_bit() << (b % 8);
                op += bytes;
            } else {
                for (unsigned b = 0; b < bits; b++) swd_gpio_write_bit((q[pos + b / 8] >> (b % 8)) & 1);
                pos += bytes;
            }
        }
        /* Input stays released until the next output sequence. */
        return op;
    }
    case 5: {
        size_t pos = 3, op = 3;
        uint8_t ack = connected ? OK : ERROR;
        unsigned done = 0;
        for (; done < q[2] && ack == OK; done++) {
            if ((done & 7U) == 7U) vTaskDelay(1);
            uint8_t req = q[pos++];
            uint32_t value = 0;
            if (!(req & 2) || (req & 0x10)) { value = u32(q + pos); pos += 4; }
            if (req & 0x20) { match_mask = value; continue; }
            if (expired()) { ack = ERROR; break; }
            if (req & 0x10) {
                uint32_t expected = value;
                int64_t match_until = esp_timer_get_time() + 100000;
                for (unsigned attempt = 0;; attempt++) {
                    ack = access_register(req, &value);
                    if (ack != OK || (value & match_mask) == (expected & match_mask)) break;
                    if (attempt >= match_retry || expired() || esp_timer_get_time() >= match_until) {
                        ack = OK | MISMATCH; break;
                    }
                    if ((attempt & 7U) == 7U) vTaskDelay(1);
                }
            } else ack = access_register(req, &value);
            if (ack != OK) break;
            if ((req & 2) && !(req & 0x10)) { put32(out + op, value); op += 4; }
        }
        out[1] = (uint8_t)done; out[2] = ack; return op;
    }
    case 6: {
        unsigned count = u16(q + 2), done = 0;
        uint8_t req = q[4], ack = connected ? OK : ERROR;
        size_t op = 4;
        for (; done < count && ack == OK; done++) {
            if ((done & 7U) == 7U) vTaskDelay(1);
            uint32_t value = (req & 2) ? 0 : u32(q + 5 + done * 4);
            if (expired()) { ack = ERROR; break; }
            ack = access_register(req, &value);
            if (ack != OK) break;
            if (req & 2) { put32(out + op, value); op += 4; }
        }
        out[1] = done & 255; out[2] = done >> 8; out[3] = ack; return op;
    }
    default: break;
    }
    return 2;
}
