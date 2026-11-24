#include "modules/mod_gpio.h"
#include "core/device_profile.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "core/topology.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "transport/mcp_transport.h"
#include <string.h>

#define EVENT_DEPTH 64
typedef struct
{
    uint8_t route, level;
    uint32_t session, generation;
    int64_t time;
} sample_t;
typedef struct
{
    uint8_t pin, mode, pull, latch, trigger, debounce;
    bool enabled, attached, pending, rate_masked;
    volatile bool level_masked;
    volatile uint32_t generation, session;
    uint32_t count;
    int64_t window;
    sample_t sample;
} pin_t;
typedef struct
{
    int base;
    bool ready;
} group_t;
static pin_t pins[14];
static group_t groups[2] = {{.base = 0}, {.base = 32}};
static QueueHandle_t events;
static SemaphoreHandle_t lock;
static TaskHandle_t task;
static uint32_t current_session;
static volatile bool stopping;
static volatile uint32_t dropped;
static uint32_t reported_drops;
static gpio_int_type_t interrupt_type(uint8_t trigger)
{
    switch (trigger)
    {
    case 1:
        return GPIO_INTR_POSEDGE;
    case 2:
        return GPIO_INTR_NEGEDGE;
    case 3:
        return GPIO_INTR_ANYEDGE;
    case 4:
        return GPIO_INTR_HIGH_LEVEL;
    case 8:
        return GPIO_INTR_LOW_LEVEL;
    default:
        return GPIO_INTR_DISABLE;
    }
}
static gpio_mode_t direction(int mode)
{
    return mode == 1   ? GPIO_MODE_INPUT_OUTPUT
           : mode == 2 ? GPIO_MODE_INPUT_OUTPUT_OD
                       : GPIO_MODE_INPUT;
}
static void interrupt_handler(void *arg)
{
    pin_t *p = arg;
    sample_t sample = {.route = p - pins,
                       .level = gpio_get_level(p->pin),
                       .time = esp_timer_get_time(),
                       .session = p->session,
                       .generation = p->generation};
    /* Level interrupts must be masked before returning to avoid a tight ISR loop. */
    if (p->trigger == 4 || p->trigger == 8)
    {
        gpio_intr_disable(p->pin);
        p->level_masked = true;
    }
    BaseType_t wake = pdFALSE;
    if (xQueueSendFromISR(events, &sample, &wake) != pdTRUE)
        dropped++;
    if (wake)
        portYIELD_FROM_ISR();
}
static void detach(pin_t *p)
{
    gpio_intr_disable(p->pin);
    if (p->attached)
    {
        gpio_isr_handler_remove(p->pin);
        p->attached = false;
    }
    p->generation++;
    p->pending = false;
    p->level_masked = false;
    p->rate_masked = false;
}
static esp_err_t subscribe(pin_t *p, int trigger, int debounce)
{
    detach(p);
    p->trigger = trigger;
    p->debounce = debounce;
    p->count = 0;
    p->window = esp_timer_get_time();
    esp_err_t err = gpio_set_intr_type(p->pin, interrupt_type(trigger));
    if (err != ESP_OK || !trigger)
        return err;
    err = gpio_isr_handler_add(p->pin, interrupt_handler, p);
    if (err != ESP_OK)
        return err;
    p->attached = true;
    return gpio_intr_enable(p->pin);
}
static esp_err_t restore(void)
{
    current_session = mcp_transport_session_id();
    if (events)
        xQueueReset(events);
    for (int i = 0; i < 14; i++)
    {
        pin_t *p = &pins[i];
        const profile_gpio_t *cfg = profile_gpio(i);
        if (p->enabled)
            detach(p);
        p->enabled = (cfg->flags & 1) != 0;
        p->pin = cfg->pin;
        p->session = current_session;
        p->mode = (cfg->flags >> 1) & 3;
        p->latch = (cfg->flags >> 3) & 1;
        p->pull = cfg->pull;
        if (!p->enabled)
            continue;
        gpio_intr_disable(p->pin);
        gpio_set_level(p->pin, p->latch);
        gpio_config_t config = {.pin_bit_mask = 1ULL << p->pin,
                                .mode = direction(p->mode),
                                .pull_up_en = (p->pull & 1) != 0,
                                .pull_down_en = (p->pull & 2) != 0,
                                .intr_type = GPIO_INTR_DISABLE};
        esp_err_t err = gpio_config(&config);
        if (err != ESP_OK)
            return err;
        err = subscribe(p, cfg->trigger, cfg->debounce);
        if (err != ESP_OK)
            return err;
    }
    return ESP_OK;
}
/* Transport ownership resets subscriptions, while output and direction changes
 * remain effective until reboot. A connection must not toggle application IO. */
static esp_err_t reset_subscriptions(void)
{
    current_session = mcp_transport_session_id();
    for (int i = 0; i < 14; i++)
        if (pins[i].enabled)
        {
            detach(&pins[i]);
            pins[i].session = current_session;
        }
    xQueueReset(events);
    for (int i = 0; i < 14; i++)
        if (pins[i].enabled)
        {
            pin_t *p = &pins[i];
            const profile_gpio_t *cfg = profile_gpio(i);
            int trigger = p->mode == 0 ? cfg->trigger : 0;
            esp_err_t err = subscribe(p, trigger, trigger ? cfg->debounce : 0);
            if (err != ESP_OK)
                return err;
        }
    return ESP_OK;
}
static pin_t *find_pin(int physical)
{
    for (int i = 0; i < 14; i++)
        if (pins[i].enabled && pins[i].pin == physical)
            return &pins[i];
    return NULL;
}
static uint8_t pin_error(int physical)
{
    return profile_gpio_capable(physical, 0, 0, 0) ? UBCP_ERR_GPIO_IN_USE
                                                   : UBCP_ERR_GPIO_PIN_INVALID;
}
static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static void put32(uint8_t *p, uint32_t value)
{
    p[0] = value >> 24;
    p[1] = value >> 16;
    p[2] = value >> 8;
    p[3] = value;
}
static size_t execute(const ubcp_frame_t *r, group_t *group, uint8_t out[9])
{
    const uint8_t *data = r->payload;
    size_t len = r->payload_len;
    uint8_t cmd = r->cmd_code;
    out[0] = UBCP_ERR_PARAM;
    if (cmd == UBCP_CMD_GPIO_WRITE_MASK || cmd == UBCP_CMD_GPIO_READ_ALL)
    {
        if (len != (cmd == UBCP_CMD_GPIO_READ_ALL ? 4 : 8))
            return 1;
        uint32_t selected = be32(data), available = 0;
        for (int i = 0; i < 14; i++)
            if (pins[i].enabled && pins[i].pin / 32 == group->base / 32)
                available |= 1UL << (pins[i].pin - group->base);
        if (cmd == UBCP_CMD_GPIO_READ_ALL && selected == UINT32_MAX)
            selected = available;
        if (selected & ~available)
        {
            for (int bit = 0; bit < 32; bit++)
                if ((selected & ~available) & (1UL << bit))
                {
                    out[0] = pin_error(group->base + bit);
                    break;
                }
            return 1;
        }
        if (cmd == UBCP_CMD_GPIO_WRITE_MASK)
        {
            uint32_t values = be32(data + 4);
            for (int bit = 0; bit < 32; bit++)
                if (selected & (1UL << bit))
                {
                    pin_t *p = find_pin(group->base + bit);
                    if (!p->mode)
                    {
                        out[0] = UBCP_ERR_GPIO_DIR_MISMATCH;
                        return 1;
                    }
                }
            for (int bit = 0; bit < 32; bit++)
                if (selected & (1UL << bit))
                {
                    pin_t *p = find_pin(group->base + bit);
                    p->latch = (values >> bit) & 1;
                    gpio_set_level(p->pin, p->latch);
                }
            out[0] = 0;
            return 1;
        }
        uint32_t levels = 0, dirs = 0;
        for (int bit = 0; bit < 32; bit++)
            if (selected & (1UL << bit))
            {
                pin_t *p = find_pin(group->base + bit);
                if (gpio_get_level(p->pin))
                    levels |= 1UL << bit;
                if (p->mode)
                    dirs |= 1UL << bit;
            }
        out[0] = 0;
        put32(out + 1, levels);
        put32(out + 5, dirs);
        return 9;
    }
    size_t expected = cmd == UBCP_CMD_GPIO_READ ? 1 : cmd == UBCP_CMD_GPIO_INT_EN ? 3 : 2;
    if (cmd == UBCP_CMD_GPIO_INT_EVENT || cmd > UBCP_CMD_GPIO_READ_ALL)
    {
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    if (len != expected)
        return 1;
    if (data[0] > 31)
    {
        out[0] = UBCP_ERR_GPIO_PIN_INVALID;
        return 1;
    }
    int physical = group->base + data[0];
    pin_t *p = find_pin(physical);
    if (!p)
    {
        out[0] = pin_error(physical);
        return 1;
    }
    esp_err_t err = ESP_OK;
    switch (cmd)
    {
    case UBCP_CMD_GPIO_SET_DIR:
        if (data[1] > 2)
            return 1;
        if (!profile_gpio_capable(physical, data[1], p->pull, 0))
        {
            out[0] = UBCP_ERR_GPIO_DIR_MISMATCH;
            return 1;
        }
        if (data[1])
        {
            err = subscribe(p, 0, 0);
            gpio_set_level(physical, p->latch);
        }
        if (err == ESP_OK)
            err = gpio_set_direction(physical, direction(data[1]));
        if (err == ESP_OK)
            p->mode = data[1];
        break;
    case UBCP_CMD_GPIO_WRITE:
        if (data[1] > 1)
            return 1;
        if (!p->mode)
        {
            out[0] = UBCP_ERR_GPIO_DIR_MISMATCH;
            return 1;
        }
        err = gpio_set_level(physical, data[1]);
        if (err == ESP_OK)
            p->latch = data[1];
        break;
    case UBCP_CMD_GPIO_READ:
        out[0] = 0;
        out[1] = gpio_get_level(physical);
        return 2;
    case UBCP_CMD_GPIO_SET_PULL:
        if (data[1] > 3)
            return 1;
        if (!profile_gpio_capable(physical, p->mode, data[1], p->trigger))
        {
            out[0] = UBCP_ERR_GPIO_PIN_INVALID;
            return 1;
        }
        err = gpio_set_pull_mode(physical, data[1] == 0   ? GPIO_FLOATING
                                           : data[1] == 1 ? GPIO_PULLUP_ONLY
                                           : data[1] == 2 ? GPIO_PULLDOWN_ONLY
                                                          : GPIO_PULLUP_PULLDOWN);
        if (err == ESP_OK)
            p->pull = data[1];
        break;
    case UBCP_CMD_GPIO_INT_EN:
        if ((data[1] == 0) != (data[2] == 0) || !(data[1] == 0 || data[1] == 1 || data[1] == 2 ||
                                                  data[1] == 3 || data[1] == 4 || data[1] == 8))
            return 1;
        if (p->mode)
        {
            out[0] = UBCP_ERR_GPIO_DIR_MISMATCH;
            return 1;
        }
        if (!profile_gpio_capable(physical, p->mode, p->pull, data[1]))
        {
            out[0] = UBCP_ERR_GPIO_PIN_INVALID;
            return 1;
        }
        err = subscribe(p, data[1], data[2]);
        break;
    default:
        out[0] = UBCP_ERR_NOT_SUPPORT;
        return 1;
    }
    out[0] = err == ESP_OK ? 0 : UBCP_ERR_HAL_FAIL;
    return 1;
}
static void handle(const ubcp_frame_t *r)
{
    const ubcp_route_entry_t *route = topology_find(r->channel_id);
    if (!route)
    {
        msg_bus_send_status_response(r, UBCP_ERR_CHANNEL_INVALID);
        return;
    }
    if (route->device_type != UBCP_DEV_TYPE_GPIO)
    {
        msg_bus_send_status_response(r, UBCP_ERR_TYPE_MISMATCH);
        return;
    }
    if (r->payload_len && !r->payload)
    {
        msg_bus_send_status_response(r, UBCP_ERR_PARAM);
        return;
    }
    uint8_t out[9];
    xSemaphoreTake(lock, portMAX_DELAY);
    if (current_session != mcp_transport_session_id())
        reset_subscriptions();
    size_t len = execute(r, route->device_driver, out);
    xSemaphoreGive(lock);
    ubcp_frame_t response;
    ubcp_frame_make_response(r, &response);
    response.payload = out;
    response.payload_len = len;
    msg_bus_send_frame(&response);
}
static void event_task(void *arg)
{
    (void)arg;
    while (!stopping)
    {
        sample_t sample;
        bool got = xQueueReceive(events, &sample, pdMS_TO_TICKS(10)) == pdTRUE;
        xSemaphoreTake(lock, portMAX_DELAY);
        if (current_session != mcp_transport_session_id())
        {
            reset_subscriptions();
            got = false;
        }
        if (got && sample.route < 14)
        {
            pin_t *p = &pins[sample.route];
            if (p->enabled && p->trigger && sample.session == current_session &&
                sample.generation == p->generation)
            {
                p->sample = sample;
                p->pending = true;
            }
        }
        int64_t now = esp_timer_get_time();
        for (int i = 0; i < 14; i++)
        {
            pin_t *p = &pins[i];
            if (!p->enabled || !p->trigger)
                continue;
            int level = gpio_get_level(p->pin);
            if (now - p->window >= 1000000)
            {
                p->window = now;
                p->count = 0;
                if (p->rate_masked)
                {
                    p->rate_masked = false;
                    if (!p->level_masked)
                        gpio_intr_enable(p->pin);
                }
            }
            if (p->level_masked && ((p->trigger == 4 && !level) || (p->trigger == 8 && level)))
            {
                p->level_masked = false;
                p->pending = false;
                if (!p->rate_masked)
                    gpio_intr_enable(p->pin);
            }
            if (!p->pending || now - p->sample.time < (int64_t)p->debounce * 1000)
                continue;
            p->pending = false;
            if (level != p->sample.level || p->sample.session != current_session ||
                p->sample.generation != p->generation)
                continue;
            if (p->count >= 50)
            {
                gpio_intr_disable(p->pin);
                p->rate_masked = true;
                dropped++;
                continue;
            }
            p->count++;
            uint8_t payload[3] = {p->pin % 32, p->trigger == 3 ? (level ? 1 : 2) : p->trigger,
                                  level};
            ubcp_frame_t event = {.version = UBCP_VERSION,
                                  .flags = UBCP_FLAG_DIR | UBCP_FLAG_EVT | UBCP_FLAG_TS,
                                  .seq_num = seq_num_next(),
                                  .cmd_code = UBCP_CMD_GPIO_INT_EVENT,
                                  .channel_id = p->pin < 32 ? UBCP_CH_GPIO_LOW : UBCP_CH_GPIO_HIGH,
                                  .has_timestamp = true,
                                  .timestamp = (uint32_t)p->sample.time,
                                  .session_id = p->sample.session,
                                  .payload = payload,
                                  .payload_len = 3};
            /* Transport checks the captured session again while sending. */
            msg_bus_send_frame(&event);
        }
        bool paused = dropped != reported_drops;
        for (int i = 0; i < 14; i++)
            if (pins[i].enabled && pins[i].rate_masked)
                paused = true;
        reported_drops = dropped;
        msg_bus_update_flow_state(0x80, paused, uxQueueMessagesWaiting(events), EVENT_DEPTH);
        xSemaphoreGive(lock);
    }
    task = NULL;
    vTaskDelete(NULL);
}
static void stop(void)
{
    stopping = true;
    while (task)
        vTaskDelay(pdMS_TO_TICKS(10));
    for (int i = 0; i < 14; i++)
        if (pins[i].enabled)
        {
            detach(&pins[i]);
            gpio_reset_pin(pins[i].pin);
            pins[i].enabled = false;
        }
    if (events)
    {
        vQueueDelete(events);
        events = NULL;
    }
    if (lock)
    {
        vSemaphoreDelete(lock);
        lock = NULL;
    }
    groups[0].ready = groups[1].ready = false;
}
static esp_err_t init(void)
{
    stopping = false;
    lock = xSemaphoreCreateMutex();
    events = xQueueCreate(EVENT_DEPTH, sizeof(sample_t));
    if (!lock || !events)
    {
        stop();
        return ESP_ERR_NO_MEM;
    }
    esp_err_t err = gpio_install_isr_service(0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE)
    {
        stop();
        return err;
    }
    err = restore();
    if (err != ESP_OK)
    {
        stop();
        return err;
    }
    if (xTaskCreate(event_task, "gpio_events", 4096, NULL, 5, &task) != pdPASS)
    {
        stop();
        return ESP_ERR_NO_MEM;
    }
    for (int i = 0; i < 14; i++)
        if (pins[i].enabled)
            groups[pins[i].pin / 32].ready = true;
    for (int i = 0; i < 2; i++)
        if (groups[i].ready)
            topology_register(UBCP_CH_GPIO_LOW + i, UBCP_DEV_TYPE_GPIO, &groups[i]);
    return ESP_OK;
}
bool mod_gpio_available(void)
{
    return groups[0].ready || groups[1].ready;
}
static const hex_module_t module = {.name = "GPIO",
                                    .cmd_range_start = 0x80,
                                    .cmd_range_end = 0x8f,
                                    .init = init,
                                    .handle_cmd = handle,
                                    .stop = stop};
const hex_module_t *mod_gpio_get(void)
{
    return &module;
}
