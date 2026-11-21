#include <string.h>
#include "core/device_profile.h"
#include "core/msg_bus.h"
#include "modules/mod_network.h"
#include "transport/mcp_transport.h"
#include "hex_config.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs_flash.h"
#include "nvs.h"

enum { DESCRIBE, READ, CHECK, SAVE, CANCEL, APPLY, CONFIRM };
enum { IDLE, STAGED, ARMED, TRIAL };
enum {
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
                                  [18] = SPI2,
                                  [19] = SPI2,
                                  [21] = SPI2,
                                  [22] = SPI2,
                                  [23] = SPI2,
                                  [25] = FLEX,
                                  [26] = FLEX,
                                  [27] = SPI2,
                                  [32] = FLEX,
                                  [33] = EEPROM,
                                  [HEX_MCP_UART_RX_PIN] = CONTROL_RX,
                                  [35] = INPUT_ONLY,
                                  [36] = INPUT_ONLY,
                                  [39] = INPUT_ONLY};
static const uint16_t owners[SIG_COUNT] = {PF_UART, PF_UART, PF_CAN, PF_CAN, PF_CAN,
                                           PF_CAN,  PF_CAN,  PF_DAP, PF_DAP};
typedef struct {
    uint8_t mask_hi, mask_lo, pin[SIG_COUNT];
} mapping_t;
static const mapping_t defaults = {PF_ALL >> 8,
                                   PF_ALL & 255,
                                   {HEX_EXT_UART_TX_PIN, HEX_EXT_UART_RX_PIN, HEX_CAN_SPI_SCK_PIN,
                                    HEX_CAN_SPI_MOSI_PIN, HEX_CAN_SPI_MISO_PIN, HEX_CAN_SPI_CS_PIN,
                                    HEX_CAN_INT_PIN, HEX_SWD_CLK_GPIO, HEX_SWD_IO_GPIO}};
typedef struct {
    uint32_t revision, candidate_id, confirmed_id, saved_from;
    uint8_t version, phase;
    mapping_t confirmed, candidate;
} record_t;
static record_t state;
static mapping_t active;
static SemaphoreHandle_t lock;
static nvs_handle_t storage;
static bool writable;
static int64_t deadline;
#define TRIAL_US (120LL * 1000000)
static uint16_t mask(const mapping_t *m) { return ((uint16_t)m->mask_hi << 8) | m->mask_lo; }
bool profile_enabled(enum profile_feature feature) { return (mask(&active) & feature) != 0; }
int profile_pin(enum profile_signal signal) { return active.pin[signal]; }

/* Diagnostics: [reason, signal or feature bit index, gpio, conflicting signal]. */
static void issue(uint8_t *out, uint8_t reason, uint8_t id, uint8_t pin, uint8_t other)
{
    uint8_t *dst = out + 2 + 4 * out[1]++;
    dst[0] = reason;
    dst[1] = id;
    dst[2] = pin;
    dst[3] = other;
}
static bool valid(const mapping_t *m, bool check_credentials, uint8_t *out)
{
    uint16_t flags = mask(m);
    uint8_t used[40];
    memset(used, 255, sizeof(used));
    out[1] = 0;
    if (flags & ~PF_ALL)
        issue(out, 1, 255, 255, 255);
    if (!(flags & (PF_SERIAL | PF_CONTROL_TCP)))
        issue(out, 2, 255, 255, 255);
    if (!(flags & PF_WIFI)) {
        unsigned network = flags & (PF_CONTROL_TCP | PF_TCP | PF_UDP | PF_WS | PF_DAP);
        for (int i = 0; i < 9; i++)
            if (network & (1u << i))
                issue(out, 3, i, 255, 255);
    }
    if (check_credentials && !(flags & PF_SERIAL) && (flags & PF_CONTROL_TCP) &&
        !mod_network_has_saved_credentials())
        issue(out, 4, 1, 255, 255);
    for (int i = 0; i < SIG_COUNT; i++) {
        uint8_t p = m->pin[i];
        uint8_t kind = p < sizeof(board) ? board[p] : UNAVAILABLE;
        bool input = i == SIG_UART_RX || i == SIG_CAN_MISO || i == SIG_CAN_INT;
        if (!(kind == FLEX || (kind == INPUT_ONLY && input) ||
              (kind == CAN_CS_ONLY && i == SIG_CAN_CS))) {
            issue(out, 5, i, p, 255);
        } else if (flags & owners[i]) {
            if (used[p] != 255)
                issue(out, 6, i, p, used[p]);
            else
                used[p] = i;
        }
    }
    return out[1] == 0;
}
static bool persist(const record_t *next)
{
    if (!writable || nvs_set_blob(storage, "record", next, sizeof(*next)) != ESP_OK ||
        nvs_commit(storage) != ESP_OK)
        return false;
    state = *next;
    return true;
}
void profile_driver_failed(void)
{
    xSemaphoreTake(lock, portMAX_DELAY);
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
    active = defaults;
    state = (record_t){.version = 1, .revision = 1, .confirmed = defaults};
    lock = xSemaphoreCreateMutex();
    ESP_ERROR_CHECK(lock ? ESP_OK : ESP_ERR_NO_MEM);
    if (nvs_flash_init_partition("profile") != ESP_OK ||
        nvs_open_from_partition("profile", "device", NVS_READWRITE, &storage) != ESP_OK) {
        ESP_LOGW("profile", "Profile storage unavailable; using board defaults");
        return;
    }
    writable = true;
    record_t saved;
    size_t len = sizeof(saved);
    uint8_t errors[80];
    esp_err_t err = nvs_get_blob(storage, "record", &saved, &len);
    if (err == ESP_ERR_NVS_NOT_FOUND)
        return;
    if (err != ESP_OK || len != sizeof(saved) || saved.version != 1 || !saved.revision ||
        !valid(&saved.confirmed, false, errors)) {
        ESP_LOGW("profile", "Invalid record; using board defaults");
        return;
    }
    state = saved;
    active = saved.confirmed;
    if (saved.phase == IDLE)
        return;
    if (saved.phase != TRIAL && saved.candidate_id && valid(&saved.candidate, true, errors)) {
        if (saved.phase == STAGED)
            return;
        if (saved.phase == ARMED) {
            saved.phase = TRIAL;
            if (persist(&saved)) {
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
    saved.revision++;
    if (!persist(&saved)) {
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
    if (req->channel_id || n < 2 || p[0] != 1) {
        out[0] = n && p[0] != 1 ? UBCP_ERR_VERSION : UBCP_ERR_PARAM;
        return 1;
    }
    uint8_t op = p[1];
    if (op == DESCRIBE && n == 2) {
        out[1] = 1;
        memcpy(out + 2, HEX_MODEL_ID, 4);
        memcpy(out + 6, &defaults, sizeof(defaults));
        memcpy(out + 6 + sizeof(defaults), board, sizeof(board));
        return 6 + sizeof(defaults) + sizeof(board);
    }
    if (op == READ && n == 2) {
        out[1] = state.phase;
        put32(out + 2, state.revision);
        put32(out + 6, state.candidate_id);
        put32(out + 10, state.confirmed_id);
        memcpy(out + 14, &active, sizeof(active));
        if (!state.candidate_id)
            return 14 + sizeof(active);
        memcpy(out + 14 + sizeof(active), &state.candidate, sizeof(active));
        return 14 + 2 * sizeof(active);
    }
    if (n < 6) {
        out[0] = UBCP_ERR_PARAM;
        return 1;
    }
    uint32_t id = get32(p + 2);
    record_t next = state;
    if ((op == SAVE || op == CHECK) && n == 6 + sizeof(mapping_t)) {
        mapping_t m;
        memcpy(&m, p + 6, sizeof(m));
        if (!valid(&m, true, out)) {
            out[0] = UBCP_ERR_PARAM;
            return 2 + 4 * out[1];
        }
        if (op == SAVE && state.phase == STAGED && id == state.saved_from &&
            memcmp(&m, &state.candidate, sizeof(m)) == 0) {
            put32(out + 1, state.candidate_id);
            return 5;
        }
        if (id != state.revision) {
            out[0] = UBCP_ERR_SEQ_MISMATCH;
            return 1;
        }
        if (op == CHECK)
            return 1;
        if (state.phase >= ARMED) {
            out[0] = UBCP_ERR_BUSY;
            return 1;
        }
        next.phase = STAGED;
        next.candidate = m;
        next.saved_from = id;
        next.candidate_id = state.revision + 1;
    } else if (n == 6 && (op == CANCEL || op == APPLY || op == CONFIRM)) {
        if (op == CONFIRM && id && id == state.confirmed_id && state.phase == IDLE)
            return 1;
        if (!id || id != state.candidate_id) {
            out[0] = UBCP_ERR_SEQ_MISMATCH;
            return 1;
        }
        if (op == APPLY && state.phase == TRIAL)
            return 1;
        if (state.phase != (op == CONFIRM ? TRIAL : STAGED)) {
            out[0] = UBCP_ERR_BUSY;
            return 1;
        }
        if (op == APPLY) {
            if (!valid(&next.candidate, true, out)) {
                out[0] = UBCP_ERR_PARAM;
                return 2 + 4 * out[1];
            }
            next.phase = ARMED;
        } else {
            if (op == CONFIRM) {
                if (esp_timer_get_time() >= deadline) {
                    out[0] = UBCP_ERR_TIMEOUT;
                    return 1;
                }
                uint16_t added = mask(&active) & ~mask(&state.confirmed);
                bool tcp = mcp_transport_using_tcp();
                if (((added & PF_CONTROL_TCP) && !tcp) || ((added & PF_SERIAL) && tcp)) {
                    out[0] = UBCP_ERR_PERMISSION;
                    return 1;
                }
                next.confirmed = active;
                next.confirmed_id = id;
            }
            next.phase = IDLE;
            next.candidate_id = 0;
        }
    } else {
        out[0] = UBCP_ERR_PARAM;
        return 1;
    }
    next.revision++;
    if (!next.revision || !persist(&next)) {
        out[0] = UBCP_ERR_UNKNOWN;
        return 1;
    }
    *restart = op == APPLY;
    if (op == SAVE) {
        put32(out + 1, next.candidate_id);
        return 5;
    }
    return 1;
}
void profile_command(const ubcp_frame_t *req)
{
    uint8_t out[80] = {0};
    bool restart = false;
    xSemaphoreTake(lock, portMAX_DELAY);
    size_t len = execute(req, out, &restart);
    xSemaphoreGive(lock);
    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload = out;
    resp.payload_len = len;
    msg_bus_send_frame(&resp);
    if (restart) {
        if (profile_enabled(PF_SERIAL))
            uart_wait_tx_done(HEX_MCP_UART_NUM, pdMS_TO_TICKS(500));
        esp_restart();
    }
}
