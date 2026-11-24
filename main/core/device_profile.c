#include "core/device_profile.h"
#include "core/msg_bus.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "hex_config.h"
#include "modules/mod_network.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "transport/mcp_transport.h"
#include <stddef.h>
#include <string.h>

enum
{
    DESCRIBE,
    READ,
    CHECK,
    SAVE,
    CANCEL,
    APPLY,
    CONFIRM
};
enum
{
    IDLE,
    STAGED,
    ARMED,
    TRIAL
};
enum
{
    UNAVAILABLE,
    FLEX,
    INPUT_ONLY,
    CAN_CS_ONLY,
    CONSOLE_TX,
    CONSOLE_RX,
    CONTROL_TX,
    CONTROL_RX,
    FLASH,
    PSRAM,
    SPI2,
    EEPROM,
    STRAP
};
/* HXB1 control wiring is a board invariant, even when serial control is off.
 * Do not let changes to configurable peripheral defaults move these reservations. */
_Static_assert(HEX_MCP_UART_TX_PIN == GPIO_NUM_4 && HEX_MCP_UART_RX_PIN == GPIO_NUM_34,
               "HXB1 UART1 control must remain on GPIO4/34");
/* Indexed by physical GPIO. Zero includes unbonded pins and numbering gaps. */
static const uint8_t board[40] = {[0] = STRAP,
                                  [1] = CONSOLE_TX,
                                  [2] = STRAP,
                                  [3] = CONSOLE_RX,
                                  [HEX_MCP_UART_TX_PIN] = CONTROL_TX,
                                  [5] = STRAP,
                                  [6] = FLASH,
                                  [7] = FLASH,
                                  [8] = FLASH,
                                  [9] = FLASH,
                                  [10] = FLASH,
                                  [11] = FLASH,
                                  [12] = EEPROM,
                                  [13] = FLEX,
                                  [14] = FLEX,
                                  [15] = CAN_CS_ONLY,
                                  [16] = PSRAM,
                                  [17] = PSRAM,
                                  [18] = FLEX,
                                  [19] = FLEX,
                                  [21] = FLEX,
                                  [22] = FLEX,
                                  [23] = FLEX,
                                  [25] = FLEX,
                                  [26] = FLEX,
                                  [27] = FLEX,
                                  [32] = FLEX,
                                  [33] = EEPROM,
                                  [HEX_MCP_UART_RX_PIN] = CONTROL_RX,
                                  [35] = INPUT_ONLY,
                                  [36] = INPUT_ONLY,
                                  [39] = INPUT_ONLY};
typedef struct
{
    uint8_t mask_hi, mask_lo, pin[SIG_COUNT];
} mapping_t;
_Static_assert(sizeof(mapping_t) == 11, "Device profile v1 mapping must remain 11 bytes");
static const mapping_t defaults = {PF_ALL >> 8,
                                   PF_ALL & 255,
                                   {HEX_EXT_UART_TX_PIN, HEX_EXT_UART_RX_PIN, HEX_CAN_SPI_SCK_PIN,
                                    HEX_CAN_SPI_MOSI_PIN, HEX_CAN_SPI_MISO_PIN, HEX_CAN_SPI_CS_PIN,
                                    HEX_CAN_INT_PIN, HEX_SWD_CLK_GPIO, HEX_SWD_IO_GPIO}};
typedef struct
{
    uint8_t enabled, width, pin[5];
} spi_mapping_t;
typedef struct
{
    mapping_t legacy;
    spi_mapping_t bus[2];
    uint8_t external_enabled, external_host, external_cs, mcp_host;
} extended_v2_t;
typedef struct
{
    mapping_t legacy;
    spi_mapping_t bus[2];
    uint8_t external_enabled, external_host, external_cs, mcp_host;
    uint8_t external2_enabled, external2_host, external2_cs;
} extended_v3_t;
typedef struct
{
    mapping_t legacy;
    spi_mapping_t bus[2];
    uint8_t external_enabled, external_host, external_cs, mcp_host;
    uint8_t external2_enabled, external2_host, external2_cs;
    uint8_t uart1_business;
} extended_v4_t;
typedef struct
{
    mapping_t legacy;
    spi_mapping_t bus[2];
    uint8_t external_enabled, external_host, external_cs, mcp_host;
    uint8_t external2_enabled, external2_host, external2_cs;
    uint8_t uart1_business;
    uint8_t role[2], slave_cs[2];
} extended_v5_t;
typedef struct
{
    mapping_t legacy;
    spi_mapping_t bus[2];
    uint8_t external_enabled, external_host, external_cs, mcp_host;
    uint8_t external2_enabled, external2_host, external2_cs;
    uint8_t uart1_business;
    uint8_t role[2], slave_cs[2];
    profile_i2c_t i2c[2];
    profile_gpio_t gpio[14];
} extended_t;
/* v1 disk layout is frozen, including ABI padding. */
typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    mapping_t confirmed, candidate;
} legacy_record_t;
_Static_assert(sizeof(legacy_record_t) == 40, "Frozen v1 NVS ABI");
_Static_assert(sizeof(spi_mapping_t) == 7, "SPI wire layout");

typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    extended_v2_t confirmed, candidate;
    uint32_t confirmed_checksum, candidate_checksum, checksum;
} record_v2_t;
_Static_assert(sizeof(extended_v2_t) == 29, "Frozen v2 mapping ABI");
_Static_assert(sizeof(record_v2_t) == 88, "Frozen v2 NVS ABI");

typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    extended_v3_t confirmed, candidate;
    uint32_t confirmed_checksum, candidate_checksum, checksum;
} record_v3_t;
_Static_assert(sizeof(extended_v3_t) == 32, "Frozen v3 mapping ABI");
_Static_assert(sizeof(record_v3_t) == 96, "Frozen v3 NVS ABI");
typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    extended_v4_t confirmed, candidate;
    uint32_t confirmed_checksum, candidate_checksum, checksum;
} record_v4_t;
_Static_assert(sizeof(extended_v4_t) == 33, "Frozen v4 mapping ABI");
_Static_assert(sizeof(record_v4_t) == 96, "Frozen v4 NVS ABI");
typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    extended_v5_t confirmed, candidate;
    uint32_t confirmed_checksum, candidate_checksum, checksum;
} record_v5_t;
typedef struct
{
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    extended_t confirmed, candidate;
    uint32_t confirmed_checksum, candidate_checksum, checksum;
} record_t;
_Static_assert(sizeof(extended_v5_t) == 37, "Frozen v5 mapping ABI");
_Static_assert(sizeof(record_v5_t) == 104, "Frozen v5 NVS ABI");
static record_t state;
static extended_t active;
static SemaphoreHandle_t lock;
static nvs_handle_t storage;
static bool writable;
static bool boot_ready, network_ready, driver_failed;
static int64_t deadline;
bool profile_is_trial(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    bool trial = state.phase == TRIAL;
    xSemaphoreGive(lock);
    return trial;
}
#define TRIAL_US (120LL * 1000000)
static uint16_t mask(const mapping_t *m)
{
    return ((uint16_t)m->mask_hi << 8) | m->mask_lo;
}
static void stage2_defaults(extended_t *e)
{
    for (int i = 0; i < 2; i++)
        e->i2c[i] = (profile_i2c_t){0, 255, 255, 0, 3, 232};
    for (int i = 0; i < 14; i++)
        e->gpio[i] = (profile_gpio_t){255, 0, 0, 0, 0};
}
const profile_i2c_t *profile_i2c(int i)
{
    return i >= 0 && i < 2 ? &active.i2c[i] : NULL;
}
const profile_gpio_t *profile_gpio(int i)
{
    return i >= 0 && i < 14 ? &active.gpio[i] : NULL;
}
bool profile_gpio_capable(int pin, int mode, int pull, int trigger)
{
    if (pin < 0 || pin >= 40 || mode < 0 || mode > 2 || pull < 0 || pull > 3)
        return false;
    if (board[pin] != FLEX && board[pin] != INPUT_ONLY)
        return false;
    if (board[pin] == INPUT_ONLY && (mode || pull))
        return false;
    if (trigger && (mode || pin == 36 || pin == 39))
        return false;
    return trigger == 0 || trigger == 1 || trigger == 2 || trigger == 3 || trigger == 4 ||
           trigger == 8;
}
static extended_t extend(const mapping_t *old)
{
    extended_t e = {0};
    stage2_defaults(&e);
    e.legacy = *old;
    e.bus[0] = (spi_mapping_t){1,
                               4,
                               {HEX_EXT_SPI_SCLK_PIN, HEX_EXT_SPI_DATA0_PIN, HEX_EXT_SPI_DATA1_PIN,
                                HEX_EXT_SPI_DATA2_PIN, HEX_EXT_SPI_DATA3_PIN}};
    e.bus[1] = (spi_mapping_t){
        (mask(old) & PF_CAN) != 0,
        1,
        {old->pin[SIG_CAN_SCK], old->pin[SIG_CAN_MOSI], old->pin[SIG_CAN_MISO], 22, 23}};
    e.external_enabled = 1;
    e.external_host = 2;
    e.external_cs = HEX_EXT_SPI_CS_PIN;
    e.mcp_host = 3;
    e.external2_host = 2;
    e.external2_cs = 255;
    e.slave_cs[0] = e.slave_cs[1] = 255;
    return e;
}
static void sync_legacy(extended_t *e)
{
    if (e->mcp_host == 2 || e->mcp_host == 3)
        memcpy(e->legacy.pin + SIG_CAN_SCK, e->bus[e->mcp_host - 2].pin, 3);
}
bool profile_enabled(enum profile_feature feature)
{
    if (feature == PF_I2C)
        return active.i2c[0].enabled || active.i2c[1].enabled;
    if (feature == PF_GPIO)
    {
        for (int i = 0; i < 14; i++)
            if (active.gpio[i].flags & 1)
                return true;
        return false;
    }
    return feature == PF_SPI ? active.external_enabled || active.external2_enabled ||
                                   profile_spi_slave(2) || profile_spi_slave(3)
                             : (mask(&active.legacy) & feature) != 0;
}
bool profile_uart1_business_enabled(void)
{
    return active.uart1_business != 0;
}
int profile_pin(enum profile_signal signal)
{
    return signal < SIG_COUNT ? active.legacy.pin[signal] : -1;
}
int profile_spi_host(bool can)
{
    return can ? active.mcp_host : active.external_host;
}
int profile_spi_pin(int host, int index)
{
    return host >= 2 && host <= 3 && index >= 0 && index < 5 ? active.bus[host - 2].pin[index] : -1;
}
int profile_spi_width(int host)
{
    return host >= 2 && host <= 3 ? active.bus[host - 2].width : 0;
}
bool profile_spi_enabled(int host)
{
    return host >= 2 && host <= 3 && active.bus[host - 2].enabled;
}
bool profile_spi_slave(int host)
{
    return profile_spi_enabled(host) && active.role[host - 2] == 1;
}
int profile_spi_slave_cs(int host)
{
    return host >= 2 && host <= 3 ? active.slave_cs[host - 2] : 255;
}
int profile_spi_cs(bool can)
{
    return can ? profile_pin(SIG_CAN_CS) : active.external_cs;
}
bool profile_spi_device_enabled(int instance)
{
    return instance == 0 ? active.external_enabled : instance == 1 && active.external2_enabled;
}
int profile_spi_device_host(int instance)
{
    return instance == 0 ? active.external_host : instance == 1 ? active.external2_host : -1;
}
int profile_spi_device_cs(int instance)
{
    return instance == 0 ? active.external_cs : instance == 1 ? active.external2_cs : 255;
}
uint32_t profile_spi_clock(bool can)
{
    return can ? 10000000 : 1000000;
}
void profile_boot_ready(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    boot_ready = true;
    xSemaphoreGive(lock);
}
void profile_network_ready(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    network_ready = true;
    xSemaphoreGive(lock);
}
bool profile_wifi_forget_allowed(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    /* A temporary serial trial must preserve the confirmed Wi-Fi rollback path. */
    bool allowed =
        (mask(&active.legacy) & PF_SERIAL) && (mask(&state.confirmed.legacy) & PF_SERIAL);
    xSemaphoreGive(lock);
    return allowed;
}
static void encode(uint8_t *p, const extended_t *e)
{
    p[0] = e->legacy.mask_hi;
    p[1] = e->legacy.mask_lo;
    p[2] = e->legacy.pin[0];
    p[3] = e->legacy.pin[1];
    p[4] = e->legacy.pin[7];
    p[5] = e->legacy.pin[8];
    memcpy(p + 6, e->bus, 14);
    p[20] = e->external_enabled;
    p[21] = e->external_host;
    p[22] = e->external_cs;
    p[23] = e->mcp_host;
    p[24] = e->legacy.pin[5];
    p[25] = e->legacy.pin[6];
}
static extended_t decode(const uint8_t *p)
{
    extended_t e = {0};
    stage2_defaults(&e);
    e.legacy.mask_hi = p[0];
    e.legacy.mask_lo = p[1];
    e.legacy.pin[0] = p[2];
    e.legacy.pin[1] = p[3];
    e.legacy.pin[7] = p[4];
    e.legacy.pin[8] = p[5];
    memcpy(e.bus, p + 6, 14);
    e.external_enabled = p[20];
    e.external_host = p[21];
    e.external_cs = p[22];
    e.mcp_host = p[23];
    e.legacy.pin[5] = p[24];
    e.legacy.pin[6] = p[25];
    e.external2_host = 2;
    e.external2_cs = 255;
    e.slave_cs[0] = e.slave_cs[1] = 255;
    sync_legacy(&e);
    return e;
}
static void encode3(uint8_t *p, const extended_t *e)
{
    encode(p, e);
    p[26] = e->external2_enabled;
    p[27] = e->external2_host;
    p[28] = e->external2_cs;
}
static extended_t decode3(const uint8_t *p)
{
    extended_t e = decode(p);
    e.external2_enabled = p[26];
    e.external2_host = p[27];
    e.external2_cs = p[28];
    return e;
}
static void encode4(uint8_t *p, const extended_t *e)
{
    encode3(p, e);
    p[29] = e->uart1_business;
}
static extended_t decode4(const uint8_t *p)
{
    extended_t e = decode3(p);
    e.uart1_business = p[29];
    return e;
}
static void encode5(uint8_t *p, const extended_t *e)
{
    encode4(p, e);
    for (int h = 0; h < 2; h++)
    {
        p[30 + h * 2] = e->role[h];
        p[31 + h * 2] = e->slave_cs[h];
    }
}
static extended_t decode5(const uint8_t *p)
{
    extended_t e = decode4(p);
    for (int h = 0; h < 2; h++)
    {
        e.role[h] = p[30 + h * 2];
        e.slave_cs[h] = p[31 + h * 2];
    }
    return e;
}
static void encode6(uint8_t *p, const extended_t *e)
{
    encode5(p, e);
    memcpy(p + 34, e->i2c, 12);
    memcpy(p + 46, e->gpio, 70);
}
static extended_t decode6(const uint8_t *p)
{
    extended_t e = decode5(p);
    memcpy(e.i2c, p + 34, 12);
    memcpy(e.gpio, p + 46, 70);
    return e;
}
static bool v5_compatible(const extended_t *e)
{
    extended_t d = {0};
    stage2_defaults(&d);
    return !memcmp(e->i2c, d.i2c, sizeof(e->i2c)) && !memcmp(e->gpio, d.gpio, sizeof(e->gpio));
}
_Static_assert(14 + 2 * 116 <= 256, "Profile dual snapshot capacity");
_Static_assert(52 + 116 <= 256, "Profile describe capacity");
static uint32_t crc(const void *data, size_t n)
{
    const uint8_t *p = data;
    uint32_t c = 0xffffffffu;
    for (size_t i = 0; i < n; i++)
    {
        c ^= p[i];
        for (int b = 0; b < 8; b++)
            c = (c >> 1) ^ ((0u - (c & 1u)) & 0xedb88320u);
    }
    return ~c;
}
static uint32_t mapping_checksum(const extended_t *e)
{
    uint8_t p[116];
    encode6(p, e);
    return crc(p, sizeof(p));
}
static extended_t upgrade_v2(const extended_v2_t *old)
{
    extended_t e = {0};
    stage2_defaults(&e);
    memcpy(&e, old, sizeof(*old));
    e.external2_host = 2;
    e.external2_cs = 255;
    e.slave_cs[0] = e.slave_cs[1] = 255;
    return e;
}
static uint32_t v2_mapping_checksum(const extended_v2_t *old)
{
    extended_t e = upgrade_v2(old);
    uint8_t p[26];
    encode(p, &e);
    return crc(p, sizeof(p));
}
static uint32_t v2_checksum(const record_v2_t *old)
{
    return crc(old, offsetof(record_v2_t, checksum));
}
static extended_t upgrade_v3(const extended_v3_t *old)
{
    extended_t e = {0};
    stage2_defaults(&e);
    memcpy(&e, old, sizeof(*old));
    e.slave_cs[0] = e.slave_cs[1] = 255;
    return e;
}
static uint32_t v3_mapping_checksum(const extended_v3_t *old)
{
    extended_t e = upgrade_v3(old);
    uint8_t p[29];
    encode3(p, &e);
    return crc(p, sizeof(p));
}
static uint32_t v3_checksum(const record_v3_t *old)
{
    return crc(old, offsetof(record_v3_t, checksum));
}
static extended_t upgrade_v4(const extended_v4_t *old)
{
    extended_t e = {0};
    stage2_defaults(&e);
    memcpy(&e, old, sizeof(*old));
    e.slave_cs[0] = e.slave_cs[1] = 255;
    return e;
}
static uint32_t v4_mapping_checksum(const extended_v4_t *old)
{
    extended_t e = upgrade_v4(old);
    uint8_t p[30];
    encode4(p, &e);
    return crc(p, sizeof(p));
}
static uint32_t v4_checksum(const record_v4_t *old)
{
    return crc(old, offsetof(record_v4_t, checksum));
}
static uint32_t checksum(const record_t *r)
{
    const uint8_t *p = (const uint8_t *)r;
    uint32_t c = 0xffffffffu;
    for (size_t i = 0; i < offsetof(record_t, checksum); i++)
    {
        c ^= p[i];
        for (int b = 0; b < 8; b++)
            c = (c >> 1) ^ ((0u - (c & 1u)) & 0xedb88320u);
    }
    return ~c;
}
/* Diagnostics: [reason, signal or feature bit index, gpio, conflicting signal]. */
static void issue(uint8_t *out, uint8_t reason, uint8_t id, uint8_t pin, uint8_t other)
{
    if (out[1] >= (256 - 2) / 4)
        return;
    uint8_t *dst = out + 2 + 4 * out[1]++;
    dst[0] = reason;
    dst[1] = id;
    dst[2] = pin;
    dst[3] = other;
}
static void check_pin(uint8_t *out, uint8_t used[40], uint8_t id, uint8_t p, bool input, bool cs,
                      bool enabled)
{
    uint8_t kind = p < sizeof(board) ? board[p] : UNAVAILABLE;
    if (!(kind == FLEX || (input && kind == INPUT_ONLY) || (cs && kind == CAN_CS_ONLY)))
        issue(out, 5, id, p, 255);
    else if (enabled)
    {
        if (used[p] != 255)
            issue(out, 6, id, p, used[p]);
        else
            used[p] = id;
    }
}
static bool valid(const extended_t *e, bool check_credentials, uint8_t *out)
{
    uint16_t flags = mask(&e->legacy);
    uint8_t used[40];
    memset(used, 255, sizeof(used));
    out[1] = 0;
    if (e->uart1_business > 1)
        issue(out, 7, 18, 255, 255);
    if (e->uart1_business && (flags & PF_SERIAL))
        issue(out, 10, 18, 255, 0);
    if (flags & ~PF_ALL)
        issue(out, 1, 255, 255, 255);
    if (!(flags & PF_SERIAL) && !((flags & PF_CONTROL_TCP) && (flags & PF_WIFI)))
        issue(out, 2, 255, 255, 255);
    if (!(flags & PF_WIFI))
        for (int i = 0; i < 9; i++)
            if ((flags & (PF_CONTROL_TCP | PF_TCP | PF_UDP | PF_WS | PF_DAP)) & (1u << i))
                issue(out, 3, i, 255, 255);
    if (check_credentials && !(flags & PF_SERIAL) && (flags & PF_WIFI) &&
        (flags & PF_CONTROL_TCP) && !mod_network_has_saved_credentials())
        issue(out, 4, 1, 255, 255);
    check_pin(out, used, 0, e->legacy.pin[0], false, false, flags & PF_UART);
    check_pin(out, used, 1, e->legacy.pin[1], true, false, flags & PF_UART);
    check_pin(out, used, 2, e->legacy.pin[7], false, false, flags & PF_DAP);
    check_pin(out, used, 3, e->legacy.pin[8], false, false, flags & PF_DAP);
    for (int h = 0; h < 2; h++)
    {
        const spi_mapping_t *b = &e->bus[h];
        if (b->enabled > 1 || (b->width != 1 && b->width != 4))
            issue(out, 7, 4 + 5 * h, 255, 255);
        if (e->role[h] > 1 || (e->role[h] == 1 && b->enabled && b->width != 1))
            issue(out, 7, 21 + h, 255, 255);
        for (int i = 0; i < 5; i++)
            if (i < 3 || b->width == 4)
                check_pin(out, used, 4 + 5 * h + i, b->pin[i],
                          b->width == 1 && (e->role[h] == 1 ? i < 2 : i == 2), false, b->enabled);
        if (e->slave_cs[h] != 255 || (b->enabled && e->role[h] == 1))
            check_pin(out, used, 19 + h, e->slave_cs[h], true, false,
                      b->enabled && e->role[h] == 1);
    }
    if (e->external_enabled > 1 || e->external_host < 2 || e->external_host > 3)
        issue(out, 7, 14, 255, 255);
    if (e->mcp_host < 2 || e->mcp_host > 3)
        issue(out, 7, 15, 255, 255);
    if (e->external_enabled && e->external_host >= 2 && e->external_host <= 3 &&
        !e->bus[e->external_host - 2].enabled)
        issue(out, 8, 14, 255, 255);
    if ((flags & PF_CAN) && e->mcp_host >= 2 && e->mcp_host <= 3 &&
        !e->bus[e->mcp_host - 2].enabled)
        issue(out, 8, 15, 255, 255);
    const uint8_t hosts[3] = {e->external_host, e->external2_host, e->mcp_host};
    const uint8_t enabled[3] = {e->external_enabled, e->external2_enabled, (flags & PF_CAN) != 0};
    const uint8_t subjects[3] = {14, 17, 15};
    for (int i = 0; i < 3; i++)
        if (enabled[i] && hosts[i] >= 2 && hosts[i] <= 3 && e->role[hosts[i] - 2] == 1)
            issue(out, 11, subjects[i], hosts[i], 21 + hosts[i] - 2);
    if (e->external_cs != 255)
        check_pin(out, used, 14, e->external_cs, false, false, e->external_enabled);
    check_pin(out, used, 15, e->legacy.pin[5], false, true, flags & PF_CAN);
    check_pin(out, used, 16, e->legacy.pin[6], true, false, flags & PF_CAN);
    if (e->external2_enabled > 1 || e->external2_host < 2 || e->external2_host > 3)
        issue(out, 7, 17, 255, 255);
    if (e->external2_enabled && e->external2_host >= 2 && e->external2_host <= 3 &&
        !e->bus[e->external2_host - 2].enabled)
        issue(out, 8, 17, 255, 255);
    if (e->external2_cs != 255)
        check_pin(out, used, 17, e->external2_cs, false, false, e->external2_enabled);
    /* A CS-less device observes every transfer, including the CAN controller's.
     * Disabled instances preserve settings but do not own the bus or their CS. */
    if (e->external_enabled && e->external_cs == 255)
    {
        if ((flags & PF_CAN) && e->external_host == e->mcp_host)
            issue(out, 9, 14, e->external_host, 15);
        if (e->external2_enabled && e->external_host == e->external2_host)
            issue(out, 9, 14, e->external_host, 17);
    }
    if (e->external2_enabled && e->external2_cs == 255)
    {
        if ((flags & PF_CAN) && e->external2_host == e->mcp_host)
            issue(out, 9, 17, e->external2_host, 15);
        if (e->external_enabled && e->external2_host == e->external_host)
            issue(out, 9, 17, e->external2_host, 14);
    }
    for (int i = 0; i < 2; i++)
    {
        const profile_i2c_t *b = &e->i2c[i];
        int timeout = (b->timeout_hi << 8) | b->timeout_lo;
        if (b->enabled > 1 || b->speed > 1 || timeout < 1 || timeout > 1000)
            issue(out, 7, 41 + i, 255, 255);
        if (b->enabled || b->scl != 255)
            check_pin(out, used, 23 + 2 * i, b->scl, false, false, b->enabled);
        if (b->enabled || b->sda != 255)
            check_pin(out, used, 24 + 2 * i, b->sda, false, false, b->enabled);
    }
    for (int i = 0; i < 14; i++)
    {
        const profile_gpio_t *g = &e->gpio[i];
        int mode = (g->flags >> 1) & 3;
        bool on = g->flags & 1;
        bool enums = !(g->flags & 0xf0) && mode <= 2 && g->pull <= 3 &&
                     ((g->trigger == 0 && g->debounce == 0) ||
                      ((g->trigger == 1 || g->trigger == 2 || g->trigger == 3 || g->trigger == 4 ||
                        g->trigger == 8) &&
                       g->debounce));
        if (!enums)
            issue(out, 7, 27 + i, g->pin, 255);
        else if (g->pin != 255 || on)
        {
            if (!profile_gpio_capable(g->pin, mode, g->pull, g->trigger))
                issue(out, 5, 27 + i, g->pin, 255);
            else if (on)
            {
                if (used[g->pin] != 255)
                    issue(out, 6, 27 + i, g->pin, used[g->pin]);
                else
                    used[g->pin] = 27 + i;
            }
        }
    }
    return !out[1];
}
static bool valid_v1(const mapping_t *m, uint8_t *out)
{
    out[1] = 0;
    for (int i = 0; i < SIG_COUNT; i++)
    {
        uint8_t p = m->pin[i];
        bool input = i == SIG_UART_RX || i == SIG_CAN_MISO || i == SIG_CAN_INT;
        uint8_t kind = p < 40 ? board[p] : UNAVAILABLE;
        if (p == 18 || p == 19 || p == 21 || p == 22 || p == 23 || p == 27)
            kind = SPI2;
        if (!(kind == FLEX || (input && kind == INPUT_ONLY) ||
              (i == SIG_CAN_CS && kind == CAN_CS_ONLY)))
            issue(out, 5, i, p, 255);
    }
    return !out[1];
}
static bool v4_compatible(const extended_t *e)
{
    return !e->role[0] && !e->role[1] && e->slave_cs[0] == 255 && e->slave_cs[1] == 255;
}
static bool v1_compatible(const extended_t *e)
{
    extended_t old = extend(&e->legacy);
    uint8_t a[29], b[29];
    encode3(a, e);
    encode3(b, &old);
    return !e->uart1_business && !memcmp(a, b, sizeof(a));
}
static bool v2_compatible(const extended_t *e)
{
    return !e->uart1_business && e->external_cs != 255 && !e->external2_enabled &&
           e->external2_host == 2 && e->external2_cs == 255;
}
static bool persist(record_t *next)
{
    next->confirmed_checksum = mapping_checksum(&next->confirmed);
    next->candidate_checksum = mapping_checksum(&next->candidate);
    next->checksum = checksum(next);
    if (!writable || nvs_set_blob(storage, "record", next, sizeof(*next)) != ESP_OK ||
        nvs_commit(storage) != ESP_OK)
        return false;
    state = *next;
    return true;
}
void profile_driver_failed(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
    driver_failed = true;
    if (state.phase == TRIAL)
        esp_restart();
    xSemaphoreGive(lock);
}
static void trial_timeout(void *arg)
{
    (void)arg;
    vTaskDelay(pdMS_TO_TICKS(120000));
    xSemaphoreTake(lock, portMAX_DELAY);
    if (state.phase == TRIAL)
        esp_restart();
    xSemaphoreGive(lock);
    vTaskDelete(NULL);
}
void profile_init(void)
{
    active = extend(&defaults);
    boot_ready = network_ready = driver_failed = writable = false;
    deadline = 0;
    state = (record_t){.version = 6, .revision = 1, .confirmed = active};
    lock = xSemaphoreCreateMutex();
    ESP_ERROR_CHECK(lock ? ESP_OK : ESP_ERR_NO_MEM);
    if (nvs_flash_init_partition("profile") != ESP_OK ||
        nvs_open_from_partition("profile", "device", NVS_READWRITE, &storage) != ESP_OK)
    {
        ESP_LOGW("profile", "Profile storage unavailable; using board defaults");
        return;
    }
    writable = true;
    record_t saved = {0};
    bool migrated = false;
    size_t len = 0;
    uint8_t errors[256];
    esp_err_t err = nvs_get_blob(storage, "record", NULL, &len);
    if (err == ESP_OK && len <= sizeof(saved))
        err = nvs_get_blob(storage, "record", &saved, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND)
        return;
    if (err == ESP_OK && len == sizeof(legacy_record_t))
    {
        legacy_record_t old;
        memcpy(&old, &saved, sizeof(old));
        if (old.version != 1 || !valid_v1(&old.confirmed, errors))
            return;
        if (old.candidate_id && !valid_v1(&old.candidate, errors))
        {
            old.phase = TRIAL;
        }
        memset(&saved, 0, sizeof(saved));
        saved.revision = old.revision;
        saved.candidate_id = old.candidate_id;
        saved.confirmed_id = old.confirmed_id;
        saved.saved_from = old.saved_from;
        saved.version = 6;
        saved.phase = old.phase;
        saved.confirmed = extend(&old.confirmed);
        saved.candidate = extend(&old.candidate);
        saved.confirmed_checksum = mapping_checksum(&saved.confirmed);
        saved.candidate_checksum = mapping_checksum(&saved.candidate);
        saved.checksum = checksum(&saved);
        len = sizeof(saved);
        migrated = true;
    }
    else if (err == ESP_OK && len == sizeof(record_v2_t))
    {
        record_v2_t old;
        memcpy(&old, &saved, sizeof(old));
        if (old.version != 2 || !old.revision ||
            old.confirmed_checksum != v2_mapping_checksum(&old.confirmed))
            return;
        memset(&saved, 0, sizeof(saved));
        saved.revision = old.revision;
        saved.candidate_id = old.candidate_id;
        saved.confirmed_id = old.confirmed_id;
        saved.saved_from = old.saved_from;
        saved.version = 6;
        saved.phase = old.phase;
        saved.confirmed = upgrade_v2(&old.confirmed);
        saved.candidate = upgrade_v2(&old.candidate);
        /* Never accept the new sentinel from old firmware, which did not define it. */
        if (!v2_compatible(&saved.confirmed))
            return;
        if (old.checksum != v2_checksum(&old) ||
            (old.candidate_id && (old.candidate_checksum != v2_mapping_checksum(&old.candidate) ||
                                  !v2_compatible(&saved.candidate))))
        {
            saved.phase = IDLE;
            saved.candidate_id = 0;
            if (++saved.revision == 0)
                saved.revision = 1;
        }
        saved.confirmed_checksum = mapping_checksum(&saved.confirmed);
        saved.candidate_checksum = mapping_checksum(&saved.candidate);
        saved.checksum = checksum(&saved);
        len = sizeof(saved);
        migrated = true;
    }
    else if (err == ESP_OK && len == sizeof(record_v3_t) && saved.version == 3)
    {
        record_v3_t old;
        memcpy(&old, &saved, sizeof(old));
        if (!old.revision || old.confirmed_checksum != v3_mapping_checksum(&old.confirmed))
            return;
        memset(&saved, 0, sizeof(saved));
        saved.revision = old.revision;
        saved.candidate_id = old.candidate_id;
        saved.confirmed_id = old.confirmed_id;
        saved.saved_from = old.saved_from;
        saved.version = 6;
        saved.phase = old.phase;
        saved.confirmed = upgrade_v3(&old.confirmed);
        saved.candidate = upgrade_v3(&old.candidate);
        if (old.checksum != v3_checksum(&old) ||
            (old.candidate_id && old.candidate_checksum != v3_mapping_checksum(&old.candidate)))
        {
            saved.phase = IDLE;
            saved.candidate_id = 0;
            if (++saved.revision == 0)
                saved.revision = 1;
        }
        saved.confirmed_checksum = mapping_checksum(&saved.confirmed);
        saved.candidate_checksum = mapping_checksum(&saved.candidate);
        saved.checksum = checksum(&saved);
        len = sizeof(saved);
        migrated = true;
    }
    else if (err == ESP_OK && len == sizeof(record_v4_t) && saved.version == 4)
    {
        record_v4_t old;
        memcpy(&old, &saved, sizeof(old));
        if (!old.revision || old.confirmed_checksum != v4_mapping_checksum(&old.confirmed))
            return;
        memset(&saved, 0, sizeof(saved));
        saved.revision = old.revision;
        saved.candidate_id = old.candidate_id;
        saved.confirmed_id = old.confirmed_id;
        saved.saved_from = old.saved_from;
        saved.version = 6;
        saved.phase = old.phase;
        saved.confirmed = upgrade_v4(&old.confirmed);
        saved.candidate = upgrade_v4(&old.candidate);
        if (old.checksum != v4_checksum(&old) ||
            (old.candidate_id && old.candidate_checksum != v4_mapping_checksum(&old.candidate)))
        {
            saved.phase = IDLE;
            saved.candidate_id = 0;
            if (++saved.revision == 0)
                saved.revision = 1;
        }
        saved.confirmed_checksum = mapping_checksum(&saved.confirmed);
        saved.candidate_checksum = mapping_checksum(&saved.candidate);
        saved.checksum = checksum(&saved);
        len = sizeof(saved);
        migrated = true;
    }
    else if (err == ESP_OK && len == sizeof(record_v5_t) && saved.version == 5)
    {
        record_v5_t old;
        memcpy(&old, &saved, sizeof(old));
        extended_t confirmed = {0}, candidate = {0};
        stage2_defaults(&confirmed);
        stage2_defaults(&candidate);
        memcpy(&confirmed, &old.confirmed, sizeof(old.confirmed));
        memcpy(&candidate, &old.candidate, sizeof(old.candidate));
        uint8_t wire[34];
        encode5(wire, &confirmed);
        if (!old.revision || old.confirmed_checksum != crc(wire, 34))
            return;
        encode5(wire, &candidate);
        bool bad = old.checksum != crc(&old, offsetof(record_v5_t, checksum)) ||
                   (old.candidate_id && old.candidate_checksum != crc(wire, 34));
        memset(&saved, 0, sizeof(saved));
        saved.revision = old.revision;
        saved.candidate_id = old.candidate_id;
        saved.confirmed_id = old.confirmed_id;
        saved.saved_from = old.saved_from;
        saved.version = 6;
        saved.phase = old.phase;
        saved.confirmed = confirmed;
        saved.candidate = candidate;
        if (bad)
        {
            saved.phase = IDLE;
            saved.candidate_id = 0;
            if (!++saved.revision)
                saved.revision = 1;
        }
        saved.confirmed_checksum = mapping_checksum(&saved.confirmed);
        saved.candidate_checksum = mapping_checksum(&saved.candidate);
        saved.checksum = checksum(&saved);
        len = sizeof(saved);
        migrated = true;
    }
    if (err != ESP_OK || len != sizeof(saved) || saved.version != 6 || !saved.revision ||
        saved.confirmed_checksum != mapping_checksum(&saved.confirmed) ||
        !valid(&saved.confirmed, true, errors))
    {
        ESP_LOGW("profile", "Invalid record; using board defaults");
        return;
    }
    if (saved.checksum != checksum(&saved))
    {
        /* A damaged candidate never replaces the independently checked confirmed snapshot. */
        saved.phase = IDLE;
        saved.candidate_id = 0;
        if (++saved.revision == 0)
            saved.revision = 1;
        if (!persist(&saved))
            writable = false;
    }
    if (migrated && saved.phase != ARMED && !persist(&saved))
        writable = false;
    state = saved;
    active = saved.confirmed;
    if (saved.phase == IDLE && !saved.candidate_id)
        return;
    if (saved.phase != TRIAL && saved.candidate_id &&
        saved.candidate_checksum == mapping_checksum(&saved.candidate) &&
        valid(&saved.candidate, true, errors))
    {
        if (saved.phase == STAGED)
            return;
        if (saved.phase == ARMED)
        {
            saved.phase = TRIAL;
            if (persist(&saved))
            {
                deadline = esp_timer_get_time() + TRIAL_US;
                active = saved.candidate;
                ESP_ERROR_CHECK(xTaskCreate(trial_timeout, "profile_trial", 3072, NULL, 5, NULL) ==
                                        pdPASS
                                    ? ESP_OK
                                    : ESP_ERR_NO_MEM);
                return;
            }
        }
    }
    saved.phase = IDLE;
    saved.candidate_id = 0;
    if (++saved.revision == 0)
        saved.revision = 1;
    if (!persist(&saved))
    {
        writable = false;
        state = saved;
    }
}
static uint32_t get32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static void put32(uint8_t *p, uint32_t v)
{
    p[0] = v >> 24;
    p[1] = v >> 16;
    p[2] = v >> 8;
    p[3] = v;
}
static size_t execute(const ubcp_frame_t *req, uint8_t *out, bool *restart)
{
    const uint8_t *p = req->payload;
    size_t n = req->payload_len;
    if (req->channel_id || n < 2 || p[0] < 1 || p[0] > 6 || n > 2048)
    {
        out[0] = n && (p[0] < 1 || p[0] > 6) ? UBCP_ERR_VERSION : UBCP_ERR_PARAM;
        return 1;
    }
    uint8_t op = p[1];
    bool v2 = p[0] >= 2;
    bool v3 = p[0] >= 3;
    bool v4 = p[0] >= 4;
    bool v5 = p[0] >= 5;
    bool v6 = p[0] == 6;
    size_t mapping_len = v6 ? 116 : v5 ? 34 : v4 ? 30 : v3 ? 29 : v2 ? 26 : sizeof(mapping_t);
    if (op == DESCRIBE && n == 2)
    {
        if (v2)
        {
            out[1] = p[0];
            memcpy(out + 2, HEX_MODEL_ID, 4);
            memset(out + 6, 0, 4);
            out[8] = v6 ? 7 : v5 ? 1 : 0;
            out[9] = v5 ? 255 : v4 ? 127 : v3 ? 63 : 15;
            out[10] = 0;
            out[11] = mapping_len;
            extended_t d = extend(&defaults);
            if (v6)
                encode6(out + 12, &d);
            else if (v5)
                encode5(out + 12, &d);
            else if (v4)
                encode4(out + 12, &d);
            else if (v3)
                encode3(out + 12, &d);
            else
                encode(out + 12, &d);
            memcpy(out + 12 + mapping_len, board, 40);
            return 52 + mapping_len;
        }
        out[1] = 1;
        memcpy(out + 2, HEX_MODEL_ID, 4);
        memcpy(out + 6, &defaults, sizeof(defaults));
        memcpy(out + 6 + sizeof(defaults), board, sizeof(board));
        const int fixed[] = {18, 19, 21, 22, 23, 27};
        for (unsigned i = 0; i < 6; i++)
            out[17 + fixed[i]] = SPI2;
        return 6 + sizeof(defaults) + sizeof(board);
    }
    if (op == READ && n == 2)
    {
        out[1] = state.phase;
        put32(out + 2, state.revision);
        put32(out + 6, state.candidate_id);
        put32(out + 10, state.confirmed_id);
        if (v6)
            encode6(out + 14, &active);
        else if (v5)
            encode5(out + 14, &active);
        else if (v4)
            encode4(out + 14, &active);
        else if (v3)
            encode3(out + 14, &active);
        else if (v2)
            encode(out + 14, &active);
        else
            memcpy(out + 14, &active.legacy, sizeof(mapping_t));
        if (!state.candidate_id)
            return 14 + mapping_len;
        if (v6)
            encode6(out + 14 + mapping_len, &state.candidate);
        else if (v5)
            encode5(out + 14 + mapping_len, &state.candidate);
        else if (v4)
            encode4(out + 14 + mapping_len, &state.candidate);
        else if (v3)
            encode3(out + 14 + mapping_len, &state.candidate);
        else if (v2)
            encode(out + 14 + mapping_len, &state.candidate);
        else
            memcpy(out + 14 + mapping_len, &state.candidate.legacy, sizeof(mapping_t));
        return 14 + 2 * mapping_len;
    }
    if (n < 6)
    {
        out[0] = UBCP_ERR_PARAM;
        return 1;
    }
    uint32_t id = get32(p + 2);
    record_t next = state;
    /* Older schemas may inspect a projection, but must never overwrite or apply
     * state they cannot represent, including the confirmed rollback snapshot. */
    if (!v6 && (op == CHECK || op == SAVE || op == CANCEL || op == APPLY || op == CONFIRM) &&
        (!v5_compatible(&active) || !v5_compatible(&state.confirmed) ||
         (state.candidate_id && !v5_compatible(&state.candidate))))
    {
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    if (!v5 && (op == CHECK || op == SAVE || op == CANCEL || op == APPLY || op == CONFIRM) &&
        (!v4_compatible(&active) || !v4_compatible(&state.confirmed) ||
         (state.candidate_id && !v4_compatible(&state.candidate))))
    {
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    if (!v4 && (op == CHECK || op == SAVE || op == CANCEL || op == APPLY || op == CONFIRM) &&
        (active.uart1_business || state.confirmed.uart1_business ||
         (state.candidate_id && state.candidate.uart1_business) ||
         (!v3 && (v2 ? (!v2_compatible(&active) || !v2_compatible(&state.confirmed) ||
                        (state.candidate_id && !v2_compatible(&state.candidate)))
                     : (!v1_compatible(&active) || !v1_compatible(&state.confirmed) ||
                        (state.candidate_id && !v1_compatible(&state.candidate)))))))
    {
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    if ((op == SAVE || op == CHECK) && n == 6 + mapping_len)
    {
        extended_t m;
        if (v6)
            m = decode6(p + 6);
        else if (v5)
            m = decode5(p + 6);
        else if (v4)
            m = decode4(p + 6);
        else if (v3)
            m = decode3(p + 6);
        else if (v2)
        {
            m = decode(p + 6);
            if (m.external_cs == 255)
            {
                out[0] = UBCP_ERR_PARAM;
                return 1;
            }
        }
        else
        {
            mapping_t old;
            memcpy(&old, p + 6, sizeof(old));
            m = extend(&old);
            if (!valid_v1(&old, out))
            {
                out[0] = UBCP_ERR_PARAM;
                return 2 + 4 * out[1];
            }
            if (!v1_compatible(&state.confirmed) ||
                (state.candidate_id && !v1_compatible(&state.candidate)))
            {
                out[0] = UBCP_ERR_NOT_SUPPORT;
                return 1;
            }
        }
        if (!valid(&m, true, out))
        {
            if (!v2)
            {
                const uint8_t ids[17] = {0, 1, 7, 8,   255, 255, 255, 255, 255,
                                         2, 3, 4, 255, 255, 255, 5,   6};
                for (int i = 0; i < out[1]; i++)
                {
                    uint8_t *d = out + 2 + 4 * i;
                    if (d[0] == 5 || d[0] == 6)
                    {
                        if (d[1] < 17)
                            d[1] = ids[d[1]];
                        if (d[3] < 17)
                            d[3] = ids[d[3]];
                    }
                }
            }
            out[0] = UBCP_ERR_PARAM;
            return 2 + 4 * out[1];
        }
        if (op == SAVE && state.phase == STAGED && id == state.saved_from &&
            memcmp(&m, &state.candidate, sizeof(m)) == 0)
        {
            put32(out + 1, state.candidate_id);
            return 5;
        }
        if (id != state.revision)
        {
            out[0] = UBCP_ERR_SEQ_MISMATCH;
            return 1;
        }
        if (op == CHECK)
            return 1;
        if (state.phase >= ARMED)
        {
            out[0] = UBCP_ERR_BUSY;
            return 1;
        }
        next.phase = STAGED;
        next.candidate = m;
        next.saved_from = id;
        next.candidate_id = state.revision + 1;
    }
    else if (n == 6 && (op == CANCEL || op == APPLY || op == CONFIRM))
    {
        if (!v2 && (!v1_compatible(&state.confirmed) ||
                    (state.candidate_id && !v1_compatible(&state.candidate))))
        {
            out[0] = UBCP_ERR_NOT_SUPPORT;
            return 1;
        }
        if (op == CONFIRM && id && id == state.confirmed_id && state.phase == IDLE)
            return 1;
        if (!id || id != state.candidate_id)
        {
            out[0] = UBCP_ERR_SEQ_MISMATCH;
            return 1;
        }
        if (op == APPLY && state.phase == TRIAL)
            return 1;
        if (state.phase != (op == CONFIRM ? TRIAL : STAGED))
        {
            out[0] = UBCP_ERR_BUSY;
            return 1;
        }
        if (op == APPLY)
        {
            if (!valid(&next.candidate, true, out))
            {
                out[0] = UBCP_ERR_PARAM;
                return 2 + 4 * out[1];
            }
            next.phase = ARMED;
        }
        else
        {
            if (op == CONFIRM)
            {
                if (esp_timer_get_time() >= deadline)
                {
                    out[0] = UBCP_ERR_TIMEOUT;
                    return 1;
                }
                if (!boot_ready || driver_failed ||
                    ((mask(&active.legacy) & PF_WIFI) && !network_ready))
                {
                    out[0] = UBCP_ERR_BUSY;
                    return 1;
                }
                if (!mcp_transport_session_is_current(req->session_id))
                {
                    out[0] = UBCP_ERR_PERMISSION;
                    return 1;
                }
                uint16_t added = mask(&active.legacy) & ~mask(&state.confirmed.legacy);
                bool tcp = mcp_transport_using_tcp();
                /* A takeover between session verification and transport inspection
                 * must not turn an old UART request into TCP confirmation proof. */
                if (!mcp_transport_session_is_current(req->session_id))
                {
                    out[0] = UBCP_ERR_PERMISSION;
                    return 1;
                }
                if (((added & PF_CONTROL_TCP) && !tcp) || ((added & PF_SERIAL) && tcp) ||
                    (active.uart1_business && !tcp))
                {
                    out[0] = UBCP_ERR_PERMISSION;
                    return 1;
                }
                next.confirmed = active;
                next.confirmed_id = id;
            }
            next.phase = IDLE;
            next.candidate_id = 0;
        }
    }
    else
    {
        out[0] = UBCP_ERR_PARAM;
        return 1;
    }
    next.revision++;
    if (!next.revision || !persist(&next))
    {
        out[0] = UBCP_ERR_UNKNOWN;
        return 1;
    }
    *restart = op == APPLY;
    if (op == SAVE)
    {
        put32(out + 1, next.candidate_id);
        return 5;
    }
    return 1;
}
void profile_command(const ubcp_frame_t *req)
{
    uint8_t out[256] = {0};
    bool restart = false;
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t len = execute(req, out, &restart);
    xSemaphoreGive(lock);
    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload = out;
    resp.payload_len = len;
    msg_bus_send_frame(&resp);
    if (restart)
    {
        mcp_transport_prepare_restart(req->session_id);
        esp_restart();
    }
}
