#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "driver/spi_slave.h"
#include "esp_log.h"
#include "esp_attr.h"
#include "hex_config.h"
#include "core/msg_bus.h"
#include "core/device_profile.h"
#include "core/spi_bus_manager.h"
#include "core/topology.h"
#include "modules/mod_spi.h"
#include "protocol/ubcp_def.h"

#define TAG "mod_spi"
#define SPI_RESPONSE_MAX HEX_UBCP_MAX_PAYLOAD

static SemaphoreHandle_t s_lock;
typedef struct {
    spi_device_handle_t dev;
    bool open, bus_held, bus_retained;
    int instance;
    uint8_t cs_polarity, mode, bit_order, word_size, cs_mode, width;
    uint32_t clock_hz;
} spi_context_t;
static spi_context_t s_devices[2] = {{.instance = 0}, {.instance = 1}};

static int spi_host(const spi_context_t *ctx)
{
    return profile_spi_device_host(ctx->instance) == 2 ? SPI2_HOST : SPI3_HOST;
}
static int cs_pin(const spi_context_t *ctx) { return profile_spi_device_cs(ctx->instance); }
static bool has_cs(const spi_context_t *ctx) { return cs_pin(ctx) != UBCP_SPI_NO_CS; }
static void reset_cs(const spi_context_t *ctx) { if (has_cs(ctx)) gpio_reset_pin(cs_pin(ctx)); }
static bool shared_host(const spi_context_t *ctx)
{
    int host = profile_spi_device_host(ctx->instance);
    int peer = 1 - ctx->instance;
    return (profile_enabled(PF_CAN) && host == profile_spi_host(true)) ||
           (profile_spi_device_enabled(peer) && host == profile_spi_device_host(peer));
}
/* One mutex protects both contexts and the shared transfer buffers. A held
 * manual CS is rejected on a host with peers, so it cannot starve CAN or SPI2. */
static uint8_t s_tx[HEX_EXT_SPI_MAX_TRANSFER];
static uint8_t s_rx[HEX_EXT_SPI_MAX_TRANSFER];
static uint8_t s_response[SPI_RESPONSE_MAX];

static uint8_t status_for(esp_err_t err)
{
    return err == ESP_OK ? UBCP_ERR_SUCCESS : UBCP_ERR_HAL_FAIL;
}

static void send_status(const ubcp_frame_t *req, uint8_t status)
{
    msg_bus_send_status_response(req, status);
}

static void send_response(const ubcp_frame_t *req, uint16_t len)
{
    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload = s_response;
    resp.payload_len = len;
    msg_bus_send_frame(&resp);
}


/* Driver owns a slot from queue_trans until get_trans_result returns it.
 * In particular neither a transport handover nor stop may free/reuse it. */
typedef struct {
    bool initialized, pending, acknowledged;
    uint32_t session;
    SemaphoreHandle_t armed;
    spi_slave_transaction_t transaction;
    uint8_t tx[64], rx[64];
} slave_context_t;
static slave_context_t s_slaves[2];

static void IRAM_ATTR slave_armed(spi_slave_transaction_t *transaction)
{
    slave_context_t *ctx = transaction->user;
    BaseType_t wake = pdFALSE;
    xSemaphoreGiveFromISR(ctx->armed, &wake);
    if (wake) portYIELD_FROM_ISR();
}

static int slave_host(int index) { return index == 0 ? SPI2_HOST : SPI3_HOST; }
static esp_err_t slave_init(int index)
{
    slave_context_t *ctx = &s_slaves[index];
    int host = index + 2;
    ctx->armed = xSemaphoreCreateBinary();
    if (!ctx->armed) return ESP_ERR_NO_MEM;
    spi_bus_config_t bus = {
        .sclk_io_num = profile_spi_pin(host, 0),
        .mosi_io_num = profile_spi_pin(host, 1),
        .miso_io_num = profile_spi_pin(host, 2),
        .quadwp_io_num = -1, .quadhd_io_num = -1,
        .max_transfer_sz = 64,
    };
    spi_slave_interface_config_t cfg = {
        .spics_io_num = profile_spi_slave_cs(host),
        .mode = 0, .queue_size = 1, .post_setup_cb = slave_armed,
    };
    esp_err_t err = spi_slave_initialize(slave_host(index), &bus, &cfg, SPI_DMA_DISABLED);
    if (err == ESP_OK) ctx->initialized = true;
    else { vSemaphoreDelete(ctx->armed); ctx->armed = NULL; }
    return err;
}

static bool slave_stop(int index)
{
    slave_context_t *ctx = &s_slaves[index];
    if (!ctx->initialized) return true;
    if (ctx->pending) {
        spi_slave_transaction_t *done;
        if (spi_slave_get_trans_result(slave_host(index), &done, 0) != ESP_OK) return false;
        ctx->pending = false;
    }
    if (spi_slave_free(slave_host(index)) != ESP_OK) return false;
    vSemaphoreDelete(ctx->armed);
    memset(ctx, 0, sizeof(*ctx));
    return true;
}

static void slave_handle(int index, const ubcp_frame_t *f)
{
    slave_context_t *ctx = &s_slaves[index];
    if (!ctx->initialized) { send_status(f, UBCP_ERR_PERMISSION); return; }
    if (f->cmd_code != UBCP_CMD_SPI_SLAVE_PREPARE && f->cmd_code != UBCP_CMD_SPI_SLAVE_FETCH) {
        send_status(f, UBCP_ERR_NOT_SUPPORT); return;
    }
    bool prepare = f->cmd_code == UBCP_CMD_SPI_SLAVE_PREPARE;
    if ((prepare && (!f->payload || f->payload_len < 2 || f->payload[0] < 1 ||
                     f->payload[0] > 64 || f->payload_len != 1 + f->payload[0])) ||
        (!prepare && f->payload_len)) { send_status(f, UBCP_ERR_PARAM); return; }
    /* Drain stale sessions without ever handing their RX data to a new owner. */
    if (ctx->pending && ctx->session != f->session_id) {
        spi_slave_transaction_t *done;
        if (spi_slave_get_trans_result(slave_host(index), &done, 0) != ESP_OK) {
            send_status(f, UBCP_ERR_BUSY); return;
        }
        ctx->pending = false;
        memset(ctx->rx, 0, sizeof(ctx->rx));
    }
    if (prepare) {
        if (ctx->pending) {
            /* A timed-out arm wait retains the only slot. An exact retry may
             * acknowledge its late setup callback without queuing a duplicate. */
            if (!ctx->acknowledged && ctx->transaction.length == f->payload[0] * 8 &&
                !memcmp(ctx->tx, f->payload + 1, f->payload[0]) &&
                xSemaphoreTake(ctx->armed, pdMS_TO_TICKS(100)) == pdTRUE) {
                ctx->acknowledged = true;
                send_status(f, UBCP_ERR_SUCCESS);
            } else send_status(f, UBCP_ERR_BUSY);
            return;
        }
        while (xSemaphoreTake(ctx->armed, 0) == pdTRUE) {}
        memcpy(ctx->tx, f->payload + 1, f->payload[0]);
        memset(ctx->rx, 0, sizeof(ctx->rx));
        ctx->transaction = (spi_slave_transaction_t){
            .length = f->payload[0] * 8, .tx_buffer = ctx->tx,
            .rx_buffer = ctx->rx, .user = ctx,
        };
        esp_err_t err = spi_slave_queue_trans(slave_host(index), &ctx->transaction, 0);
        if (err != ESP_OK) { send_status(f, UBCP_ERR_HAL_FAIL); return; }
        ctx->pending = true;
        ctx->acknowledged = false;
        ctx->session = f->session_id;
        /* queue_trans alone does not mean the ISR loaded the hardware yet. */
        if (xSemaphoreTake(ctx->armed, pdMS_TO_TICKS(100)) != pdTRUE) {
            send_status(f, UBCP_ERR_BUSY); return;
        }
        ctx->acknowledged = true;
        send_status(f, UBCP_ERR_SUCCESS);
    } else {
        if (!ctx->pending) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
        spi_slave_transaction_t *done;
        esp_err_t err = spi_slave_get_trans_result(slave_host(index), &done, 0);
        if (err == ESP_ERR_TIMEOUT) { send_status(f, UBCP_ERR_BUSY); return; }
        if (err != ESP_OK) { send_status(f, UBCP_ERR_HAL_FAIL); return; }
        ctx->pending = false;
        size_t bits = done->trans_len;
        if (bits > ctx->transaction.length) bits = ctx->transaction.length;
        size_t bytes = (bits + 7) / 8;
        s_response[0] = UBCP_ERR_SUCCESS;
        s_response[1] = bits >> 8; s_response[2] = bits;
        memcpy(s_response + 3, ctx->rx, bytes);
        send_response(f, 3 + bytes);
    }
}

static void set_cs(spi_context_t *ctx, bool active)
{
    if (!has_cs(ctx)) return;
    int level = active ? (ctx->cs_polarity ? 1 : 0) : (ctx->cs_polarity ? 0 : 1);
    gpio_set_level(cs_pin(ctx), level);
}

static void release_bus(spi_context_t *ctx)
{
    set_cs(ctx, false);
    if (ctx->bus_held) { spi_device_release_bus(ctx->dev); ctx->bus_held = false; }
}

static esp_err_t add_device(spi_context_t *ctx)
{
    spi_device_interface_config_t cfg = {
        .clock_speed_hz = (int)ctx->clock_hz,
        .mode = ctx->mode,
        .spics_io_num = -1, /* CS is GPIO-controlled to support polarity and hold. */
        .queue_size = 1,
        .flags = (ctx->width == UBCP_SPI_WIDTH_QUAD ? SPI_DEVICE_HALFDUPLEX : 0) |
                 (ctx->bit_order ? SPI_DEVICE_BIT_LSBFIRST : 0),
    };
    return spi_bus_add_device(spi_host(ctx), &cfg, &ctx->dev);
}

static esp_err_t configure_bus(spi_context_t *ctx)
{
    if (ctx->dev) {
        esp_err_t err = spi_bus_remove_device(ctx->dev);
        if (err != ESP_OK) return err;
        ctx->dev = NULL;
    }
    return add_device(ctx);
}

static void handle_open(spi_context_t *ctx, const ubcp_frame_t *f)
{
    if (f->payload_len != 2 || !f->payload || f->payload[1] > 1) {
        send_status(f, UBCP_ERR_PARAM);
        return;
    }
    if (f->payload[0] != cs_pin(ctx)) { send_status(f, UBCP_ERR_SPI_CS_INVALID); return; }
    if (!has_cs(ctx) && shared_host(ctx)) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (ctx->open) {
        send_status(f, UBCP_ERR_ALREADY_OPEN);
        return;
    }
    ctx->cs_polarity = f->payload[1];
    ctx->mode = 0;
    ctx->bit_order = 0;
    ctx->word_size = UBCP_SPI_WORD_8;
    ctx->cs_mode = UBCP_SPI_CS_AUTO;
    ctx->width = UBCP_SPI_WIDTH_SINGLE;
    ctx->clock_hz = profile_spi_clock(false);
    esp_err_t err = ESP_OK;
    if (has_cs(ctx)) {
        gpio_config_t gpio = {
            .pin_bit_mask = 1ULL << cs_pin(ctx),
            .mode = GPIO_MODE_OUTPUT,
            .pull_up_en = GPIO_PULLUP_DISABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        /* Preload the inactive latch before enabling output to avoid a CS pulse. */
        set_cs(ctx, false);
        err = gpio_config(&gpio);
        set_cs(ctx, false);
    }
    if (err == ESP_OK) err = add_device(ctx);
    if (err == ESP_OK) ctx->open = true;
    else { set_cs(ctx, false); reset_cs(ctx); }
    send_status(f, status_for(err));
}

static void handle_config(spi_context_t *ctx, const ubcp_frame_t *f)
{
    if (f->payload_len != 9 || !f->payload) { send_status(f, UBCP_ERR_PARAM); return; }
    const uint8_t *p = f->payload;
    uint32_t hz = ((uint32_t)p[1] << 24) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 8) | p[4];
    if (hz < 10000 || hz > 40000000) { send_status(f, UBCP_ERR_SPI_CLOCK); return; }
    if (p[0] > 3 || p[5] > 1 || p[6] > 1 || p[7] > 1 || (p[8] != 1 && p[8] != 4)) {
        send_status(f, UBCP_ERR_PARAM); return;
    }
    if (p[8] == 4 && profile_spi_width(profile_spi_device_host(ctx->instance)) != 4) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (p[8] == 4 && p[6] != UBCP_SPI_WORD_8) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (p[7] == UBCP_SPI_CS_MANUAL && (!has_cs(ctx) || shared_host(ctx))) {
        send_status(f, UBCP_ERR_NOT_SUPPORT); return;
    }
    if (!ctx->open || !ctx->dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    uint8_t old_mode=ctx->mode, old_order=ctx->bit_order, old_word=ctx->word_size, old_cs=ctx->cs_mode, old_width=ctx->width;
    uint32_t old_hz=ctx->clock_hz;
    release_bus(ctx);
    ctx->mode=p[0]; ctx->clock_hz=hz; ctx->bit_order=p[5]; ctx->word_size=p[6]; ctx->cs_mode=p[7]; ctx->width=p[8];
    esp_err_t err = configure_bus(ctx);
    if (err != ESP_OK) {
        ctx->mode=old_mode; ctx->bit_order=old_order; ctx->word_size=old_word; ctx->cs_mode=old_cs; ctx->width=old_width; ctx->clock_hz=old_hz;
        esp_err_t restore_err = configure_bus(ctx);
        if (restore_err != ESP_OK) {
            /* A failed remove leaves the old handle alive. Preserve CLOSE's
             * ability to clean it up rather than allowing OPEN to leak it. */
            ctx->open = ctx->dev != NULL;
            if (!ctx->open) reset_cs(ctx);
            err = restore_err;
        }
    }
    send_status(f, status_for(err));
}

static void handle_cs(spi_context_t *ctx, const ubcp_frame_t *f)
{
    if (f->payload_len != 1 || !f->payload || f->payload[0] > 1) { send_status(f, UBCP_ERR_PARAM); return; }
    if (!ctx->open || !ctx->dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    if (!has_cs(ctx)) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (ctx->cs_mode != UBCP_SPI_CS_MANUAL) { send_status(f, UBCP_ERR_SPI_CS_MODE); return; }
    if (f->payload[0] == 0 && !ctx->bus_held) {
        esp_err_t err = spi_device_acquire_bus(ctx->dev, portMAX_DELAY);
        if (err != ESP_OK) { send_status(f, status_for(err)); return; }
        ctx->bus_held = true;
    }
    if (f->payload[0] == 0) set_cs(ctx, true);
    else release_bus(ctx);
    send_status(f, UBCP_ERR_SUCCESS);
}

static void handle_transfer(spi_context_t *ctx, const ubcp_frame_t *f, uint8_t cmd)
{
    if (!ctx->open || !ctx->dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    if (!f->payload) { send_status(f, UBCP_ERR_PARAM); return; }
    uint16_t n;
    const uint8_t *tx = NULL;
    uint8_t fill = 0xFF;
    if (cmd == UBCP_CMD_SPI_READ) {
        if (f->payload_len != 3) { send_status(f, UBCP_ERR_PARAM); return; }
        n = ((uint16_t)f->payload[0] << 8) | f->payload[1];
        fill = f->payload[2];
        memset(s_tx, fill, n <= HEX_EXT_SPI_MAX_TRANSFER ? n : 0);
        tx = s_tx;
    } else {
        if (f->payload_len < 2) { send_status(f, UBCP_ERR_PARAM); return; }
        n = ((uint16_t)f->payload[0] << 8) | f->payload[1];
        if (f->payload_len != (uint16_t)(2 + n)) { send_status(f, UBCP_ERR_PARAM); return; }
        if (cmd != UBCP_CMD_SPI_READ) tx = f->payload + 2;
        if (cmd == UBCP_CMD_SPI_WRITE) tx = f->payload + 2;
    }
    if (n == 0 || n > HEX_EXT_SPI_MAX_TRANSFER || (ctx->word_size == UBCP_SPI_WORD_16 && (n & 1))) { send_status(f, UBCP_ERR_PARAM); return; }
    if (ctx->width == UBCP_SPI_WIDTH_QUAD && cmd == UBCP_CMD_SPI_TRANSFER) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    bool auto_cs = ctx->cs_mode == UBCP_SPI_CS_AUTO;
    bool transaction_owns_bus = !ctx->bus_held;
    if (transaction_owns_bus) {
        esp_err_t err = spi_device_acquire_bus(ctx->dev, portMAX_DELAY);
        if (err != ESP_OK) { send_status(f, status_for(err)); return; }
    }
    if (auto_cs) set_cs(ctx, true);
    spi_transaction_t t = {0};
    t.length = (size_t)n * 8;
    t.tx_buffer = tx;
    if (cmd == UBCP_CMD_SPI_READ || cmd == UBCP_CMD_SPI_TRANSFER) {
        t.rxlength = (size_t)n * 8;
        t.rx_buffer = s_rx;
    }
    if (ctx->width == UBCP_SPI_WIDTH_QUAD) {
        t.flags = SPI_TRANS_MODE_QIO;
        if (cmd == UBCP_CMD_SPI_READ) {
            /* DMA does not support a half-duplex transaction with both phases. */
            t.length = 0;
            t.tx_buffer = NULL;
        }
    }
    esp_err_t err = spi_device_transmit(ctx->dev, &t);
    if (auto_cs) set_cs(ctx, false);
    if (transaction_owns_bus) spi_device_release_bus(ctx->dev);
    if (err != ESP_OK) {
        send_status(f, UBCP_ERR_SPI_TRANSFER);
        return;
    }
    s_response[0] = UBCP_ERR_SUCCESS;
    s_response[1] = (uint8_t)(n >> 8);
    s_response[2] = (uint8_t)(n & 0xFF);
    uint16_t out_len = 3;
    if (cmd == UBCP_CMD_SPI_READ || cmd == UBCP_CMD_SPI_TRANSFER) {
        memcpy(s_response + 3, s_rx, n);
        out_len += n;
    }
    send_response(f, out_len);
}

static void handle_close(spi_context_t *ctx, const ubcp_frame_t *f)
{
    if (f->payload_len != 0) { send_status(f, UBCP_ERR_PARAM); return; }
    if (!ctx->open) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    release_bus(ctx);
    esp_err_t err = spi_bus_remove_device(ctx->dev);
    if (err == ESP_OK) {
        ctx->dev = NULL;
        ctx->open = false;
        reset_cs(ctx);
    }
    send_status(f, status_for(err));
}

static void spi_handle(const ubcp_frame_t *f)
{
    if (f->channel_id == UBCP_CH_SPI_SLAVE2 || f->channel_id == UBCP_CH_SPI_SLAVE3) {
        if (!s_lock) { send_status(f, UBCP_ERR_PERMISSION); return; }
        if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
        slave_handle(f->channel_id - UBCP_CH_SPI_SLAVE2, f);
        xSemaphoreGive(s_lock);
        return;
    }
    int instance = f->channel_id == UBCP_CH_SPI_EXT1 ? 0 :
                   f->channel_id == UBCP_CH_SPI_EXT2 ? 1 : -1;
    if (instance < 0) { send_status(f, UBCP_ERR_CHANNEL_INVALID); return; }
    if (!profile_spi_device_enabled(instance) || !s_lock) { send_status(f, UBCP_ERR_PERMISSION); return; }
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
    spi_context_t *ctx = &s_devices[instance];
    switch (f->cmd_code) {
    case UBCP_CMD_SPI_OPEN: handle_open(ctx, f); break;
    case UBCP_CMD_SPI_CLOSE: handle_close(ctx, f); break;
    case UBCP_CMD_SPI_CONFIG: handle_config(ctx, f); break;
    case UBCP_CMD_SPI_TRANSFER: case UBCP_CMD_SPI_WRITE: case UBCP_CMD_SPI_READ: handle_transfer(ctx, f, f->cmd_code); break;
    case UBCP_CMD_SPI_CS_CONTROL: handle_cs(ctx, f); break;
    default: send_status(f, UBCP_ERR_NOT_SUPPORT); break;
    }
    xSemaphoreGive(s_lock);
}

static esp_err_t spi_init(void)
{
    if (s_lock) return ESP_OK;
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return ESP_ERR_NO_MEM;
    for (int i = 0; i < 2; ++i) {
        spi_context_t *ctx = &s_devices[i];
        if (!profile_spi_device_enabled(i)) continue;
        esp_err_t err = hex_spi_bus_retain(spi_host(ctx));
        if (err != ESP_OK) {
            for (int j = 0; j < i; ++j) {
                spi_context_t *old = &s_devices[j];
                if (old->bus_retained && hex_spi_bus_release(spi_host(old)) == ESP_OK) old->bus_retained = false;
            }
            vSemaphoreDelete(s_lock); s_lock = NULL;
            return err;
        }
        ctx->bus_retained = true;
    }
    for (int i = 0; i < 2; ++i) {
        if (!profile_spi_enabled(i + 2) || !profile_spi_slave(i + 2)) continue;
        esp_err_t err = slave_init(i);
        if (err != ESP_OK) {
            for (int j = 0; j < i; ++j) slave_stop(j);
            for (int j = 0; j < 2; ++j) {
                spi_context_t *old = &s_devices[j];
                if (old->bus_retained && hex_spi_bus_release(spi_host(old)) == ESP_OK) old->bus_retained = false;
            }
            vSemaphoreDelete(s_lock); s_lock = NULL;
            return err;
        }
    }
    for (int i = 0; i < 2; ++i) if (s_slaves[i].initialized)
        topology_register(UBCP_CH_SPI_SLAVE2 + i, UBCP_DEV_TYPE_SPI, NULL);
    /* Publish topology only after all enabled devices retained their buses. */
    for (int i = 0; i < 2; ++i) {
        if (!profile_spi_device_enabled(i)) continue;
        topology_register(i == 0 ? UBCP_CH_SPI_EXT1 : UBCP_CH_SPI_EXT2, UBCP_DEV_TYPE_SPI, NULL);
        ESP_LOGI(TAG, "SPI device %d ready (host=%d CS=%d)", i + 1, profile_spi_device_host(i), profile_spi_device_cs(i));
    }
    return ESP_OK;
}

static void spi_stop(void)
{
    if (!s_lock) return;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    bool stopped = true;
    for (int i = 0; i < 2; ++i) if (!slave_stop(i)) stopped = false;
    for (int i = 0; i < 2; ++i) {
        spi_context_t *ctx = &s_devices[i];
        if (ctx->dev) {
            release_bus(ctx);
            if (spi_bus_remove_device(ctx->dev) != ESP_OK) { stopped = false; continue; }
            ctx->dev = NULL;
            ctx->open = false;
            reset_cs(ctx);
        }
        if (ctx->bus_retained) {
            if (hex_spi_bus_release(spi_host(ctx)) == ESP_OK) ctx->bus_retained = false;
            else stopped = false;
        }
    }
    xSemaphoreGive(s_lock);
    if (stopped) { vSemaphoreDelete(s_lock); s_lock = NULL; }
}

static const hex_module_t s_module = {
    .name = "SPI",
    .cmd_range_start = UBCP_CMD_RANGE_SPI_START,
    .cmd_range_end = UBCP_CMD_RANGE_SPI_END,
    .init = spi_init,
    .handle_cmd = spi_handle,
    .stop = spi_stop,
};

const hex_module_t *mod_spi_get(void) { return &s_module; }
