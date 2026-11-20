#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "lwip/sockets.h"
#include "transport/mcp_transport.h"
#include "protocol/ubcp_frame.h"
#include "core/msg_bus.h"
#include "hex_config.h"
#include "utils/hex_log.h"

#include "transport/service_ports.h"
static const char *TAG = "mcp_transport";
static ubcp_parser_t s_parser;
static uint8_t s_parse_buf[HEX_UBCP_FRAME_BUF_SIZE + UBCP_CRC_SIZE];
/* State lock also covers a complete write. No bus/module calls under this lock. */
static SemaphoreHandle_t s_lock;
static TaskHandle_t s_task;
static bool s_running, s_online;
static int s_listener = -1, s_client = -1;
static uint32_t s_session = 1;

static void next_session(void)
{
    if (++s_session == 0) ++s_session;
    /* Finish already accepted UART output before another owner is admitted.
     * The TX ring is then empty; incoming bytes from the old owner are dropped. */
    uart_wait_tx_done(HEX_MCP_UART_NUM, portMAX_DELAY);
    uart_flush_input(HEX_MCP_UART_NUM);
}
static void fallback(void)
{
    if (s_client >= 0) {
        shutdown(s_client, SHUT_RDWR);
        close(s_client);
        s_client = -1;
        next_session();
    }
}
uint32_t mcp_transport_session_id(void)
{
    if (!s_lock) return 0;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    uint32_t session = s_running ? s_session : 0;
    xSemaphoreGive(s_lock);
    return session;
}
bool mcp_transport_session_is_current(uint32_t session)
{
    return session != 0 && session == mcp_transport_session_id();
}
void mcp_transport_set_network_ready(bool ready)
{
    if (!s_lock) return;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_online = ready;
    if (!ready) {
        fallback();
        if (s_listener >= 0) { close(s_listener); s_listener = -1; }
    }
    xSemaphoreGive(s_lock);
}
static int listener_open(void)
{
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (fd < 0) return -1;
    int yes = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));
    struct sockaddr_in addr = {.sin_family = AF_INET,
        .sin_port = htons(HEX_MCP_TCP_PORT), .sin_addr.s_addr = htonl(INADDR_ANY)};
    if (bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 || listen(fd, 2) < 0 ||
        fcntl(fd, F_SETFL, O_NONBLOCK) < 0) { close(fd); return -1; }
    return fd;
}
static void feed(const uint8_t *data, int len, uint32_t session)
{
    static uint32_t parser_session;
    if (parser_session != session) {
        ubcp_parser_reset(&s_parser);
        parser_session = session;
    }
    for (int i = 0; i < len; ++i) {
        if (!mcp_transport_session_is_current(session)) {
            ubcp_parser_reset(&s_parser); return;
        }
        ubcp_parse_result_t result = ubcp_parser_feed(&s_parser, data[i]);
        if (result == UBCP_PARSE_FRAME_OK) {
            ubcp_frame_t frame;
            if (ubcp_parser_get_frame(&s_parser, &frame) == ESP_OK) {
                frame.session_id = session;
                if (frame.version != UBCP_VERSION)
                    msg_bus_send_status_response(&frame, UBCP_ERR_VERSION);
                else msg_bus_dispatch(&frame);
            }
            ubcp_parser_reset(&s_parser);
        } else if (result != UBCP_PARSE_NEED_MORE) ubcp_parser_reset(&s_parser);
    }
}
static void io_task(void *arg)
{
    (void)arg;
    uint8_t data[256];
    for (;;) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (!s_running) { xSemaphoreGive(s_lock); break; }
        if (s_online && s_listener < 0) s_listener = listener_open();
        if (s_listener >= 0) {
            int fd = accept(s_listener, NULL, NULL);
            if (fd >= 0) {
                if (s_client >= 0 || !s_online || fcntl(fd, F_SETFL, O_NONBLOCK) < 0) {
                    close(fd); /* Busy: never disturb the existing session. */
                } else {
                    int yes = 1, idle = 10, interval = 3, count = 3;
                    setsockopt(fd, SOL_SOCKET, SO_KEEPALIVE, &yes, sizeof(yes));
                    setsockopt(fd, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof(idle));
                    setsockopt(fd, IPPROTO_TCP, TCP_KEEPINTVL, &interval, sizeof(interval));
                    setsockopt(fd, IPPROTO_TCP, TCP_KEEPCNT, &count, sizeof(count));
                    next_session();
                    s_client = fd;
                    HEX_LOGI(TAG, "TCP 9500 took UBCP control");
                }
            }
        }
        int len;
        if (s_client >= 0) {
            /* Drain UART while inactive, so stale provisioning commands cannot
             * execute when the TCP client disconnects. */
            uart_flush_input(HEX_MCP_UART_NUM);
            len = recv(s_client, data, sizeof(data), MSG_DONTWAIT);
            if (len == 0 || (len < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
                fallback(); len = 0;
            }
        } else len = uart_read_bytes(HEX_MCP_UART_NUM, data, sizeof(data), 0);
        uint32_t session = s_session;
        xSemaphoreGive(s_lock);
        if (len > 0) feed(data, len, session);
        else vTaskDelay(pdMS_TO_TICKS(10));
    }
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_task = NULL;
    xSemaphoreGive(s_lock);
    vTaskDelete(NULL);
}
esp_err_t mcp_transport_send_session(const uint8_t *data, size_t len, uint32_t session)
{
    if (!data || !len || !s_lock) return ESP_ERR_INVALID_ARG;
    if (xSemaphoreTake(s_lock, pdMS_TO_TICKS(1000)) != pdTRUE) return ESP_ERR_TIMEOUT;
    esp_err_t result = ESP_ERR_INVALID_STATE;
    if (s_running && session && session == s_session) {
        if (s_client < 0) {
            result = uart_write_bytes(HEX_MCP_UART_NUM, data, len) == (int)len ? ESP_OK : ESP_FAIL;
        } else {
            /* A bounded send includes partial writes. On timeout close this
             * stream: continuing after a half frame would corrupt framing. */
            TickType_t start = xTaskGetTickCount();
            size_t pos = 0;
            while (pos < len) {
                int n = send(s_client, data + pos, len - pos, MSG_DONTWAIT);
                if (n > 0) { pos += n; continue; }
                if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) &&
                    xTaskGetTickCount() - start < pdMS_TO_TICKS(250)) {
                    vTaskDelay(1); continue;
                }
                break;
            }
            result = pos == len ? ESP_OK : ESP_FAIL;
            if (result != ESP_OK) fallback();
        }
    }
    xSemaphoreGive(s_lock);
    return result;
}
esp_err_t mcp_transport_send(const uint8_t *data, size_t len)
{
    uint32_t session = mcp_transport_session_id();
    return mcp_transport_send_session(data, len, session);
}
esp_err_t mcp_transport_init(uint32_t baud_rate)
{
    if (s_running) return ESP_ERR_INVALID_STATE;
    if (!s_lock) s_lock = xSemaphoreCreateMutex();
    if (!s_lock) return ESP_ERR_NO_MEM;
    uart_config_t config = {.baud_rate = baud_rate ? baud_rate : HEX_MCP_UART_BAUD,
        .data_bits = UART_DATA_8_BITS, .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1, .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_APB};
    esp_err_t err = uart_driver_install(HEX_MCP_UART_NUM, HEX_MCP_UART_RX_BUF_SIZE,
                                       HEX_MCP_UART_TX_BUF_SIZE, 0, NULL, 0);
    if (err != ESP_OK) return err;
    err = uart_param_config(HEX_MCP_UART_NUM, &config);
    if (err == ESP_OK) err = uart_set_pin(HEX_MCP_UART_NUM, HEX_MCP_UART_TX_PIN,
        HEX_MCP_UART_RX_PIN, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) { uart_driver_delete(HEX_MCP_UART_NUM); return err; }
    ubcp_parser_init(&s_parser, s_parse_buf, sizeof(s_parse_buf));
    s_running = true;
    if (xTaskCreate(io_task, "mcp_io", HEX_MCP_RECV_TASK_STACK, NULL,
                    HEX_MCP_RECV_TASK_PRIO, &s_task) != pdPASS) {
        s_running = false; uart_driver_delete(HEX_MCP_UART_NUM); return ESP_ERR_NO_MEM;
    }
    return ESP_OK;
}
void mcp_transport_stop(void)
{
    if (!s_lock) return;
    xSemaphoreTake(s_lock, portMAX_DELAY);
    s_running = false; s_online = false;
    fallback();
    if (s_listener >= 0) { close(s_listener); s_listener = -1; }
    next_session();
    xSemaphoreGive(s_lock);
    for (;;) {
        xSemaphoreTake(s_lock, portMAX_DELAY);
        bool done = s_task == NULL;
        xSemaphoreGive(s_lock);
        if (done) break;
        vTaskDelay(1);
    }
    uart_driver_delete(HEX_MCP_UART_NUM);
    /* Keep the lock alive: a delayed module completion may still arrive. */
}
