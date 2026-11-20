#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "hex_config.h"
#include "core/msg_bus.h"
#include "core/topology.h"
#include "modules/mod_spi.h"
#include "protocol/ubcp_def.h"

#define TAG "mod_spi"
#define SPI_RESPONSE_MAX HEX_UBCP_MAX_PAYLOAD

static SemaphoreHandle_t s_lock;
static spi_device_handle_t s_dev;
static bool s_open;
static uint8_t s_cs_polarity;
static uint8_t s_mode;
static uint8_t s_bit_order;
static uint8_t s_word_size;
static uint8_t s_cs_mode;
static uint8_t s_width;
static uint32_t s_clock_hz;
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

static void set_cs(bool active)
{
    int level = active ? (s_cs_polarity ? 1 : 0) : (s_cs_polarity ? 0 : 1);
    gpio_set_level(HEX_EXT_SPI_CS_PIN, level);
}

static esp_err_t add_device(void)
{
    spi_device_interface_config_t cfg = {
        .clock_speed_hz = (int)s_clock_hz,
        .mode = s_mode,
        .spics_io_num = -1, /* CS is GPIO-controlled to support polarity and hold. */
        .queue_size = 1,
        .flags = (s_width == UBCP_SPI_WIDTH_QUAD ? SPI_DEVICE_HALFDUPLEX : 0) |
                 (s_bit_order ? SPI_DEVICE_BIT_LSBFIRST : 0),
    };
    return spi_bus_add_device(HEX_EXT_SPI_HOST, &cfg, &s_dev);
}

static esp_err_t configure_bus(void)
{
    if (s_dev) {
        spi_bus_remove_device(s_dev);
        s_dev = NULL;
    }
    return add_device();
}

static bool channel_ok(const ubcp_frame_t *f)
{
    return f->channel_id == UBCP_CH_SPI_EXT1;
}

static void handle_open(const ubcp_frame_t *f)
{
    if (f->payload_len != 2 || !f->payload || f->payload[1] > 1) {
        send_status(f, UBCP_ERR_PARAM);
        return;
    }
    if (f->payload[0] != HEX_EXT_SPI_CS_PIN) { send_status(f, UBCP_ERR_SPI_CS_INVALID); return; }
    if (s_open) {
        send_status(f, UBCP_ERR_ALREADY_OPEN);
        return;
    }
    s_cs_polarity = f->payload[1];
    s_mode = 0;
    s_bit_order = 0;
    s_word_size = UBCP_SPI_WORD_8;
    s_cs_mode = UBCP_SPI_CS_AUTO;
    s_width = UBCP_SPI_WIDTH_SINGLE;
    s_clock_hz = 1000000;
    gpio_config_t gpio = {
        .pin_bit_mask = 1ULL << HEX_EXT_SPI_CS_PIN,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&gpio);
    if (err == ESP_OK) {
        set_cs(false);
        err = add_device();
    }
    if (err == ESP_OK) s_open = true;
    send_status(f, status_for(err));
}

static void handle_config(const ubcp_frame_t *f)
{
    if (f->payload_len != 9 || !f->payload) { send_status(f, UBCP_ERR_PARAM); return; }
    const uint8_t *p = f->payload;
    uint32_t hz = ((uint32_t)p[1] << 24) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 8) | p[4];
    if (hz < 10000 || hz > 40000000) { send_status(f, UBCP_ERR_SPI_CLOCK); return; }
    if (p[0] > 3 || p[5] > 1 || p[6] > 1 || p[7] > 1 || (p[8] != 1 && p[8] != 4)) {
        send_status(f, UBCP_ERR_PARAM); return;
    }
    if (p[8] == 4 && p[6] != UBCP_SPI_WORD_8) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (!s_open || !s_dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
    uint8_t old_mode=s_mode, old_order=s_bit_order, old_word=s_word_size, old_cs=s_cs_mode, old_width=s_width;
    uint32_t old_hz=s_clock_hz;
    set_cs(false);
    s_mode=p[0]; s_clock_hz=hz; s_bit_order=p[5]; s_word_size=p[6]; s_cs_mode=p[7]; s_width=p[8];
    esp_err_t err = configure_bus();
    if (err != ESP_OK) {
        s_mode=old_mode; s_bit_order=old_order; s_word_size=old_word; s_cs_mode=old_cs; s_width=old_width; s_clock_hz=old_hz;
        esp_err_t restore_err = configure_bus();
        if (restore_err != ESP_OK) {
            s_open = false;
            err = restore_err;
        }
    }
    xSemaphoreGive(s_lock);
    send_status(f, status_for(err));
}

static void handle_cs(const ubcp_frame_t *f)
{
    if (f->payload_len != 1 || !f->payload || f->payload[0] > 1) { send_status(f, UBCP_ERR_PARAM); return; }
    if (!s_open || !s_dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    if (s_cs_mode != UBCP_SPI_CS_MANUAL) { send_status(f, UBCP_ERR_SPI_CS_MODE); return; }
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
    set_cs(f->payload[0] == 0);
    xSemaphoreGive(s_lock);
    send_status(f, UBCP_ERR_SUCCESS);
}

static void handle_transfer(const ubcp_frame_t *f, uint8_t cmd)
{
    if (!s_open || !s_dev) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
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
    if (n == 0 || n > HEX_EXT_SPI_MAX_TRANSFER || (s_word_size == UBCP_SPI_WORD_16 && (n & 1))) { send_status(f, UBCP_ERR_PARAM); return; }
    if (s_width == UBCP_SPI_WIDTH_QUAD && cmd == UBCP_CMD_SPI_TRANSFER) { send_status(f, UBCP_ERR_NOT_SUPPORT); return; }
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
    bool auto_cs = s_cs_mode == UBCP_SPI_CS_AUTO;
    if (auto_cs) set_cs(true);
    spi_transaction_t t = {0};
    t.length = (size_t)n * 8;
    t.tx_buffer = tx;
    if (cmd == UBCP_CMD_SPI_READ || cmd == UBCP_CMD_SPI_TRANSFER) {
        t.rxlength = (size_t)n * 8;
        t.rx_buffer = s_rx;
    }
    if (s_width == UBCP_SPI_WIDTH_QUAD) {
        t.flags = SPI_TRANS_MODE_QIO;
        if (cmd == UBCP_CMD_SPI_READ) {
            /* DMA does not support a half-duplex transaction with both phases. */
            t.length = 0;
            t.tx_buffer = NULL;
        }
    }
    esp_err_t err = spi_device_transmit(s_dev, &t);
    if (auto_cs) set_cs(false);
    if (err != ESP_OK) {
        xSemaphoreGive(s_lock);
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
    xSemaphoreGive(s_lock);
}

static void handle_close(const ubcp_frame_t *f)
{
    if (f->payload_len != 0) { send_status(f, UBCP_ERR_PARAM); return; }
    if (!s_open) { send_status(f, UBCP_ERR_NOT_OPEN); return; }
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) { send_status(f, UBCP_ERR_BUSY); return; }
    set_cs(false);
    esp_err_t err = spi_bus_remove_device(s_dev);
    s_dev = NULL;
    s_open = false;
    gpio_reset_pin(HEX_EXT_SPI_CS_PIN);
    xSemaphoreGive(s_lock);
    send_status(f, status_for(err));
}

static void spi_handle(const ubcp_frame_t *f)
{
    if (!channel_ok(f)) { send_status(f, UBCP_ERR_CHANNEL_INVALID); return; }
    switch (f->cmd_code) {
    case UBCP_CMD_SPI_OPEN: handle_open(f); break;
    case UBCP_CMD_SPI_CLOSE: handle_close(f); break;
    case UBCP_CMD_SPI_CONFIG: handle_config(f); break;
    case UBCP_CMD_SPI_TRANSFER: case UBCP_CMD_SPI_WRITE: case UBCP_CMD_SPI_READ: handle_transfer(f, f->cmd_code); break;
    case UBCP_CMD_SPI_CS_CONTROL: handle_cs(f); break;
    default: send_status(f, UBCP_ERR_NOT_SUPPORT); break;
    }
}

static esp_err_t spi_init(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return ESP_ERR_NO_MEM;
    spi_bus_config_t bus = {
        .sclk_io_num = HEX_EXT_SPI_SCLK_PIN,
        .data0_io_num = HEX_EXT_SPI_DATA0_PIN,
        .data1_io_num = HEX_EXT_SPI_DATA1_PIN,
        .data2_io_num = HEX_EXT_SPI_DATA2_PIN,
        .data3_io_num = HEX_EXT_SPI_DATA3_PIN,
        .max_transfer_sz = HEX_EXT_SPI_MAX_TRANSFER,
        .flags = SPICOMMON_BUSFLAG_MASTER | SPICOMMON_BUSFLAG_QUAD,
    };
    esp_err_t err = spi_bus_initialize(HEX_EXT_SPI_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) return err;
    topology_register(UBCP_CH_SPI_EXT1, UBCP_DEV_TYPE_SPI, NULL);
    ESP_LOGI(TAG, "SPI2 外部总线就绪 (SCLK=%d, IO0=%d, IO1=%d, IO2=%d, IO3=%d, CS=%d)",
             HEX_EXT_SPI_SCLK_PIN, HEX_EXT_SPI_DATA0_PIN, HEX_EXT_SPI_DATA1_PIN,
             HEX_EXT_SPI_DATA2_PIN, HEX_EXT_SPI_DATA3_PIN, HEX_EXT_SPI_CS_PIN);
    return ESP_OK;
}

static void spi_stop(void)
{
    if (s_open) {
        set_cs(false);
        spi_bus_remove_device(s_dev);
        s_dev = NULL;
        s_open = false;
        gpio_reset_pin(HEX_EXT_SPI_CS_PIN);
    }
    spi_bus_free(HEX_EXT_SPI_HOST);
}

static const hex_module_t s_module = {
    .name = "SPI2",
    .cmd_range_start = UBCP_CMD_RANGE_SPI_START,
    .cmd_range_end = UBCP_CMD_RANGE_SPI_END,
    .init = spi_init,
    .handle_cmd = spi_handle,
    .stop = spi_stop,
};

const hex_module_t *mod_spi_get(void) { return &s_module; }
