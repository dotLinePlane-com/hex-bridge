#include "dap_server.h"
#include "transport/service_ports.h"
#include "dap_stream.h"
#include "dap_engine.h"
#include "modules/mod_network.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lwip/sockets.h"
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>

static const char *TAG = "dap_server";
static TaskHandle_t s_task;
/* Only dap_task owns these buffers and descriptors. */
static dap_stream_t s_stream;
typedef struct { int fd; uint32_t generation; int64_t deadline; } writer_t;
static writer_t *s_writer;

static bool network_current(uint32_t generation)
{
    return mod_network_is_ready() && generation == mod_network_generation();
}

static size_t execute_current(const uint8_t *request, size_t length,
                              uint8_t *response, size_t capacity)
{
    if (!network_current(s_writer->generation)) return 0;
    size_t result = dap_execute(request, length, response, capacity);
    /* Give the other protocol workers time even for a coalesced command burst.
     * Write deadlines start after SWD execution, once per response. */
    vTaskDelay(1);
    s_writer->deadline = esp_timer_get_time() + 2000000;
    return network_current(s_writer->generation) ? result : 0;
}

static ptrdiff_t socket_write(void *context, const uint8_t *data, size_t length)
{
    writer_t *w = context;
    while (network_current(w->generation) && esp_timer_get_time() < w->deadline) {
        int n = send(w->fd, data, length, 0);
        if (n >= 0) return n;
        if (errno == EINTR) continue;
        if (errno != EAGAIN && errno != EWOULDBLOCK) return -1;
        fd_set writable;
        FD_ZERO(&writable);
        FD_SET(w->fd, &writable);
        struct timeval wait = {.tv_sec = 0, .tv_usec = 100000};
        int ready = select(w->fd + 1, NULL, &writable, NULL, &wait);
        if (ready < 0 && errno != EINTR) return -1;
    }
    return -1;
}

static bool nonblocking(int fd)
{
    int flags = fcntl(fd, F_GETFL, 0);
    return flags >= 0 && fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0;
}

static int open_listener(void)
{
    int fd = socket(AF_INET, SOCK_STREAM, IPPROTO_IP);
    if (fd < 0) return -1;
    int reuse = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));
    struct sockaddr_in addr = {
        .sin_family = AF_INET, .sin_port = htons(HEX_DAP_TCP_PORT),
        .sin_addr.s_addr = htonl(INADDR_ANY),
    };
    if (!nonblocking(fd) || bind(fd, (struct sockaddr *)&addr, sizeof(addr)) < 0 ||
        listen(fd, 2) < 0) {
        close(fd);
        return -1;
    }
    ESP_LOGI(TAG, "CMSIS-DAP listening on %d", HEX_DAP_TCP_PORT);
    return fd;
}

static void drop_client(int *client)
{
    if (*client >= 0) {
        shutdown(*client, SHUT_RDWR);
        close(*client);
        *client = -1;
        dap_release();
        ESP_LOGI(TAG, "debugger disconnected; SWD released");
    }
    dap_stream_reset(&s_stream);
}

static void dap_task(void *arg)
{
    (void)arg;
    int listener = -1, client = -1;
    uint32_t generation = mod_network_generation();
    uint8_t incoming[512];
    dap_stream_reset(&s_stream);
    for (;;) {
        if (!network_current(generation)) {
            drop_client(&client);
            if (listener >= 0) close(listener);
            listener = -1;
            generation = mod_network_generation();
        }
        if (!mod_network_is_ready()) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (listener < 0) {
            listener = open_listener();
            if (listener < 0) {
                vTaskDelay(pdMS_TO_TICKS(500));
                continue;
            }
        }
        fd_set readable;
        FD_ZERO(&readable);
        FD_SET(listener, &readable);
        int maxfd = listener;
        if (client >= 0) { FD_SET(client, &readable); if (client > maxfd) maxfd = client; }
        struct timeval wait = {.tv_sec = 0, .tv_usec = 100000};
        int ready = select(maxfd + 1, &readable, NULL, NULL, &wait);
        if (!network_current(generation)) continue;
        if (ready < 0) {
            if (errno == EINTR) continue;
            drop_client(&client);
            close(listener);
            listener = -1;
            continue;
        }
        if (ready == 0) continue;
        /* Snapshot before accept: a newly accepted fd was not in this select. */
        int readable_client = client >= 0 && FD_ISSET(client, &readable) ? client : -1;
        if (FD_ISSET(listener, &readable)) {
            int accepted = accept(listener, NULL, NULL);
            if (accepted >= 0) {
                if (client >= 0 || !network_current(generation) || !nonblocking(accepted)) {
                    close(accepted); /* Busy clients never modify the active engine. */
                } else {
                    int one = 1;
                    setsockopt(accepted, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
                    setsockopt(accepted, SOL_SOCKET, SO_KEEPALIVE, &one, sizeof(one));
                    int idle = 10, interval = 2, count = 3;
                    setsockopt(accepted, IPPROTO_TCP, TCP_KEEPIDLE, &idle, sizeof(idle));
                    setsockopt(accepted, IPPROTO_TCP, TCP_KEEPINTVL, &interval, sizeof(interval));
                    setsockopt(accepted, IPPROTO_TCP, TCP_KEEPCNT, &count, sizeof(count));
                    client = accepted;
                    dap_stream_reset(&s_stream);
                }
            }
        }
        if (readable_client < 0) continue;
        int n = recv(client, incoming, sizeof(incoming), 0);
        if (n < 0 && (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK)) continue;
        writer_t writer = {.fd = client, .generation = generation};
        s_writer = &writer;
        if (n <= 0 || !dap_stream_feed(&s_stream, incoming, (size_t)n,
                                      execute_current, socket_write, &writer)) drop_client(&client);
        s_writer = NULL;
        /* Yield even when the peer continuously floods complete requests. */
        vTaskDelay(1);
    }
}

esp_err_t dap_server_start(void)
{
    if (s_task) return ESP_OK;
    return xTaskCreate(dap_task, "dap_tcp", 6144, NULL, 4, &s_task) == pdPASS
        ? ESP_OK : ESP_ERR_NO_MEM;
}
