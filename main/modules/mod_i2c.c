#include "modules/mod_i2c.h"
#include "core/device_profile.h"
#include "core/msg_bus.h"
#include "core/topology.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "transport/mcp_transport.h"
#include <stdlib.h>
#include <string.h>

#define QUEUE_DEPTH 4
typedef struct
{
    ubcp_frame_t frame;
    uint8_t data[];
} request_t;
typedef struct
{
    i2c_master_bus_handle_t bus;
    i2c_master_dev_handle_t device;
    QueueHandle_t queue;
    TaskHandle_t task;
    bool open, ready, needs_reset;
    volatile bool stopping;
    uint8_t instance, mode;
    uint16_t address, timeout;
    uint32_t speed, session;
    uint8_t *out;
    request_t *active_job;
} context_t;
static context_t contexts[2];
static uint16_t be16(const uint8_t *p)
{
    return ((uint16_t)p[0] << 8) | p[1];
}
static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)be16(p) << 16) | be16(p + 2);
}
static void close_device(context_t *c)
{
    if (c->device)
    {
        i2c_master_bus_rm_device(c->device);
        c->device = NULL;
    }
}
static void defaults(context_t *c)
{
    const profile_i2c_t *p = profile_i2c(c->instance);
    close_device(c);
    c->open = false;
    c->mode = 0;
    c->speed = p->speed ? 400000 : 100000;
    c->timeout = ((uint16_t)p->timeout_hi << 8) | p->timeout_lo;
}
static bool bus_lines_released(const context_t *c)
{
    const profile_i2c_t *p = profile_i2c(c->instance);
    return gpio_get_level(p->scl) && gpio_get_level(p->sda);
}
static int remaining_ms(int64_t deadline)
{
    int64_t us = deadline - esp_timer_get_time();
    return us > 0 ? (int)((us + 999) / 1000) : 0;
}
/* Clearing while SDA is externally held can report ESP_OK without producing a
 * STOP. Keep recovery pending until a new request sees released lines. */
static uint8_t prepare_bus(context_t *c, int64_t deadline)
{
    if (!bus_lines_released(c))
    {
        c->needs_reset = true;
        close_device(c);
    }
    while (!bus_lines_released(c) && remaining_ms(deadline) &&
           mcp_transport_session_is_current(c->session) && !c->stopping)
        vTaskDelay(1);
    if (!mcp_transport_session_is_current(c->session) || c->stopping)
        return UBCP_ERR_PERMISSION;
    if (!bus_lines_released(c) || !remaining_ms(deadline))
        return UBCP_ERR_TIMEOUT;
    if (c->needs_reset)
    {
        close_device(c);
        esp_err_t err = i2c_master_bus_reset(c->bus);
        if (err != ESP_OK || !bus_lines_released(c))
            return err == ESP_ERR_TIMEOUT || !bus_lines_released(c) ? UBCP_ERR_TIMEOUT
                                                                    : UBCP_ERR_I2C_BUS_ERROR;
        c->needs_reset = false;
    }
    return remaining_ms(deadline) ? UBCP_ERR_SUCCESS : UBCP_ERR_TIMEOUT;
}
static uint8_t status(context_t *c, esp_err_t err, int64_t deadline)
{
    if (err == ESP_OK)
        return UBCP_ERR_SUCCESS;
    if ((err == ESP_ERR_INVALID_RESPONSE || err == ESP_ERR_NOT_FOUND) && bus_lines_released(c) &&
        remaining_ms(deadline))
        return UBCP_ERR_I2C_NACK;
    bool held = !bus_lines_released(c);
    while (held && remaining_ms(deadline) && mcp_transport_session_is_current(c->session) &&
           !c->stopping)
    {
        vTaskDelay(1);
        held = !bus_lines_released(c);
    }
    close_device(c);
    c->needs_reset = true;
    /* Never replay the failed operation, including a register prefix write. */
    return err == ESP_ERR_TIMEOUT || held || !remaining_ms(deadline) ? UBCP_ERR_TIMEOUT
                                                                     : UBCP_ERR_I2C_BUS_ERROR;
}
static esp_err_t device(context_t *c, uint16_t address)
{
    if (c->device && c->address == address)
        return ESP_OK;
    close_device(c);
    i2c_device_config_t config = {.dev_addr_length =
                                      c->mode ? I2C_ADDR_BIT_LEN_10 : I2C_ADDR_BIT_LEN_7,
                                  .device_address = address,
                                  .scl_speed_hz = c->speed};
    esp_err_t err = i2c_master_bus_add_device(c->bus, &config, &c->device);
    if (err != ESP_OK)
        c->device = NULL;
    else
        c->address = address;
    return err;
}
static size_t execute(context_t *c, const ubcp_frame_t *r, uint8_t *out)
{
    const uint8_t *p = r->payload;
    size_t n = r->payload_len;
    uint8_t cmd = r->cmd_code;
    out[0] = UBCP_ERR_PARAM;
    if (cmd == UBCP_CMD_I2C_OPEN)
    {
        if (n != 1 || p[0] > 1)
            return 1;
        if (c->open)
        {
            out[0] = UBCP_ERR_ALREADY_OPEN;
            return 1;
        }
        defaults(c);
        c->mode = p[0];
        c->open = true;
        out[0] = 0;
        return 1;
    }
    if (cmd == UBCP_CMD_I2C_CLOSE)
    {
        if (n)
            return 1;
        if (!c->open)
        {
            out[0] = UBCP_ERR_NOT_OPEN;
            return 1;
        }
        defaults(c);
        out[0] = 0;
        return 1;
    }
    if (!c->open)
    {
        out[0] = UBCP_ERR_NOT_OPEN;
        return 1;
    }
    if (cmd == UBCP_CMD_I2C_CONFIG)
    {
        if (n != 6 || be16(p + 4) < 1 || be16(p + 4) > 1000)
            return 1;
        uint32_t speed = be32(p);
        if (speed != 100000 && speed != 400000)
        {
            out[0] = UBCP_ERR_NOT_SUPPORT;
            return 1;
        }
        close_device(c);
        c->speed = speed;
        c->timeout = be16(p + 4);
        out[0] = 0;
        return 1;
    }
    if (cmd == UBCP_CMD_I2C_SCAN)
    {
        if (n != 2 || p[0] < 8 || p[1] > 0x77 || p[0] > p[1])
            return 1;
        if (c->mode)
        {
            out[0] = UBCP_ERR_NOT_SUPPORT;
            return 1;
        }
        close_device(c);
        size_t found = 0;
        int64_t end = esp_timer_get_time() + (int64_t)c->timeout * 1000;
        out[0] = prepare_bus(c, end);
        if (out[0])
            return 1;
        for (int address = p[0]; address <= p[1]; address++)
        {
            if (!mcp_transport_session_is_current(r->session_id))
                return 0;
            int64_t remaining = (end - esp_timer_get_time()) / 1000;
            if (remaining <= 0)
            {
                out[0] = UBCP_ERR_TIMEOUT;
                return 1;
            }
            esp_err_t err = i2c_master_probe(c->bus, address, remaining > 10 ? 10 : remaining);
            if (err == ESP_OK)
                out[2 + found++] = address;
            else if ((err != ESP_ERR_NOT_FOUND && err != ESP_ERR_INVALID_RESPONSE) ||
                     !bus_lines_released(c))
            {
                out[0] = status(c, err, end);
                return 1;
            }
        }
        out[0] = 0;
        out[1] = found;
        return 2 + found;
    }
    uint16_t address = 0, read_len = 0, write_len = 0;
    const uint8_t *write_data = NULL;
    uint8_t *joined = NULL;
    if (cmd == UBCP_CMD_I2C_WRITE || cmd == UBCP_CMD_I2C_READ)
    {
        if (n < 5 || p[2] > 4 || n < (size_t)5 + p[2])
            return 1;
        address = be16(p);
        uint8_t prefix = p[2];
        uint16_t len = be16(p + 3 + prefix);
        if (cmd == UBCP_CMD_I2C_READ)
        {
            if (n != (size_t)5 + prefix || !len || len > UBCP_MAX_PAYLOAD_LEN - 3)
                return 1;
            write_data = p + 3;
            write_len = prefix;
            read_len = len;
        }
        else
        {
            if (n != (size_t)5 + prefix + len || (!len && !prefix))
                return 1;
            write_len = prefix + len;
            joined = malloc(write_len);
            if (!joined)
            {
                out[0] = UBCP_ERR_UNKNOWN;
                return 1;
            }
            memcpy(joined, p + 3, prefix);
            memcpy(joined + prefix, p + 5 + prefix, len);
            write_data = joined;
        }
    }
    else if (cmd == UBCP_CMD_I2C_WRITE_READ)
    {
        if (n < 6)
            return 1;
        address = be16(p);
        write_len = be16(p + 2);
        read_len = be16(p + 4);
        if (n != (size_t)6 + write_len || !read_len || read_len > UBCP_MAX_PAYLOAD_LEN - 3)
            return 1;
        write_data = p + 6;
    }
    else
    {
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    if (address > (c->mode ? 1023 : 127))
    {
        free(joined);
        out[0] = UBCP_ERR_I2C_ADDR_INVALID;
        return 1;
    }
    int64_t deadline = esp_timer_get_time() + (int64_t)c->timeout * 1000;
    out[0] = prepare_bus(c, deadline);
    if (out[0])
    {
        free(joined);
        return 1;
    }
    esp_err_t err = device(c, address);
    if (!mcp_transport_session_is_current(c->session) || c->stopping)
    {
        free(joined);
        return 0;
    }
    int timeout = remaining_ms(deadline);
    if (!timeout)
        err = ESP_ERR_TIMEOUT;
    if (err == ESP_OK)
    {
        if (read_len && write_len)
            err = i2c_master_transmit_receive(c->device, write_data, write_len, out + 3, read_len,
                                              timeout);
        else if (read_len)
            err = i2c_master_receive(c->device, out + 3, read_len, timeout);
        else
            err = i2c_master_transmit(c->device, write_data, write_len, timeout);
    }
    free(joined);
    out[0] = status(c, err, deadline);
    if (out[0])
        return 1;
    uint16_t actual = read_len ? read_len : be16(p + 3 + p[2]);
    out[1] = actual >> 8;
    out[2] = actual;
    return 3 + read_len;
}
static void worker(void *arg)
{
    context_t *c = arg;
    uint8_t *out = c->out;
    while (!c->stopping)
    {
        request_t *job = NULL;
        uint32_t session = mcp_transport_session_id();
        if (c->session != session)
        {
            defaults(c);
            c->session = session;
        }
        if (xQueueReceive(c->queue, &job, pdMS_TO_TICKS(20)) != pdTRUE)
            continue;
        c->active_job = job;
        if (mcp_transport_session_is_current(job->frame.session_id))
        {
            if (c->session != job->frame.session_id)
            {
                defaults(c);
                c->session = job->frame.session_id;
            }
            size_t len = execute(c, &job->frame, out);
            if (len && mcp_transport_session_is_current(job->frame.session_id))
            {
                ubcp_frame_t response;
                ubcp_frame_make_response(&job->frame, &response);
                response.payload = out;
                response.payload_len = len;
                msg_bus_send_frame(&response);
            }
        }
        free(job);
        c->active_job = NULL;
    }
    c->task = NULL;
    vTaskDelete(NULL);
}
static void handle(const ubcp_frame_t *r)
{
    const ubcp_route_entry_t *route = topology_find(r->channel_id);
    if (!route)
    {
        msg_bus_send_status_response(r, UBCP_ERR_CHANNEL_INVALID);
        return;
    }
    if (route->device_type != UBCP_DEV_TYPE_I2C)
    {
        msg_bus_send_status_response(r, UBCP_ERR_TYPE_MISMATCH);
        return;
    }
    if (r->cmd_code > UBCP_CMD_I2C_SCAN)
    {
        msg_bus_send_status_response(r, UBCP_ERR_NOT_SUPPORT);
        return;
    }
    if (r->payload_len > UBCP_MAX_PAYLOAD_LEN || (r->payload_len && !r->payload))
    {
        msg_bus_send_status_response(r, UBCP_ERR_PARAM);
        return;
    }
    context_t *c = route->device_driver;
    request_t *job = malloc(sizeof(*job) + r->payload_len);
    if (!job)
    {
        msg_bus_send_status_response(r, UBCP_ERR_BUSY);
        return;
    }
    job->frame = *r;
    if (r->payload_len)
        memcpy(job->data, r->payload, r->payload_len);
    job->frame.payload = job->data;
    if (xQueueSend(c->queue, &job, 0) != pdTRUE)
    {
        free(job);
        msg_bus_send_status_response(r, UBCP_ERR_BUSY);
    }
}
static void stop(void)
{
    for (int i = 0; i < 2; i++)
    {
        context_t *c = &contexts[i];
        c->stopping = true;
        /* Each transaction is bounded by 1000 ms; allow its driver lock to unwind. */
        while (c->task)
            vTaskDelay(pdMS_TO_TICKS(10));
        if (c->queue)
        {
            request_t *job;
            while (xQueueReceive(c->queue, &job, 0) == pdTRUE)
                free(job);
            vQueueDelete(c->queue);
            c->queue = NULL;
        }
        free(c->active_job);
        c->active_job = NULL;
        free(c->out);
        c->out = NULL;
        close_device(c);
        if (c->bus)
        {
            i2c_del_master_bus(c->bus);
            c->bus = NULL;
        }
        c->ready = false;
    }
}
static esp_err_t init(void)
{
    for (int i = 0; i < 2; i++)
    {
        const profile_i2c_t *p = profile_i2c(i);
        if (!p->enabled)
            continue;
        context_t *c = &contexts[i];
        c->instance = i;
        c->stopping = false;
        defaults(c);
        i2c_master_bus_config_t config = {.i2c_port = i,
                                          .scl_io_num = p->scl,
                                          .sda_io_num = p->sda,
                                          .clk_source = I2C_CLK_SRC_DEFAULT,
                                          .glitch_ignore_cnt = 7,
                                          /* Supplemental idle bias; external pull-ups remain
                                           * necessary for the specified bus rise times. */
                                          .flags.enable_internal_pullup = true};
        esp_err_t err = i2c_new_master_bus(&config, &c->bus);
        if (err != ESP_OK)
        {
            stop();
            return err;
        }
        c->needs_reset = false;
        c->out = malloc(UBCP_MAX_PAYLOAD_LEN);
        c->queue = xQueueCreate(QUEUE_DEPTH, sizeof(request_t *));
        if (!c->out || !c->queue ||
            xTaskCreate(worker, i ? "i2c1" : "i2c0", 6144, c, 6, &c->task) != pdPASS)
        {
            stop();
            return ESP_ERR_NO_MEM;
        }
        c->ready = true;
        topology_register(UBCP_CH_I2C0 + i, UBCP_DEV_TYPE_I2C, c);
    }
    return ESP_OK;
}
bool mod_i2c_available(void)
{
    return contexts[0].ready || contexts[1].ready;
}
static const hex_module_t module = {.name = "I2C",
                                    .cmd_range_start = 0x30,
                                    .cmd_range_end = 0x3f,
                                    .init = init,
                                    .handle_cmd = handle,
                                    .stop = stop};
const hex_module_t *mod_i2c_get(void)
{
    return &module;
}
