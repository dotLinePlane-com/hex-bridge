#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/sockets.h"
#include "esp_timer.h"
#include "modules/mod_udp.h"
#include "modules/mod_network.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_udp";

#define UDP_MAX_SERVERS  4
#define UDP_MAX_CLIENTS  8

typedef struct {
    uint16_t handle;
    int      socket_fd;
    uint16_t port;
    bool     broadcast_en;
    uint32_t multicast_addr;
    bool     active;
} udp_server_t;

typedef struct {
    uint16_t handle;
    int      socket_fd;
    uint32_t default_dest_ip;
    uint16_t default_dest_port;
    uint16_t local_port;
    bool     active;
} udp_client_t;

static udp_server_t s_servers[UDP_MAX_SERVERS];
static udp_client_t s_clients[UDP_MAX_CLIENTS];
static SemaphoreHandle_t s_mutex = NULL;
static TaskHandle_t s_select_task = NULL;
static volatile bool s_task_running = false;

static uint16_t s_next_handle = 0x3000;

static uint16_t alloc_handle(void)
{
    uint16_t h = s_next_handle++;
    if (s_next_handle > 0x3FFF) s_next_handle = 0x3000;
    return h;
}

static void send_event(uint8_t cmd, uint8_t *payload, uint16_t len)
{
    ubcp_frame_t evt;
    memset(&evt, 0, sizeof(evt));
    evt.version       = UBCP_VERSION;
    evt.flags         = UBCP_FLAG_DIR | UBCP_FLAG_EVT | UBCP_FLAG_TS;
    evt.seq_num       = seq_num_next();
    evt.cmd_code      = cmd;
    evt.channel_id    = 0;
    evt.has_timestamp = true;
    evt.timestamp     = (uint32_t)(esp_timer_get_time() & 0xFFFFFFFF);
    evt.payload       = payload;
    evt.payload_len   = len;
    msg_bus_send_frame(&evt);
}

/* ── NET_LIST_CONNS provider ── */
static void udp_iterate_conns(net_conn_iter_cb cb, void *ctx)
{
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    for (int i = 0; i < UDP_MAX_SERVERS; i++) {
        if (s_servers[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_UDP_SERVER;
            entry.handle        = s_servers[i].handle;
            entry.parent_handle = 0;
            entry.local_port    = s_servers[i].port;
            entry.remote_ip     = 0;
            cb(&entry, ctx);
        }
    }
    for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
        if (s_clients[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_UDP_CLIENT;
            entry.handle        = s_clients[i].handle;
            entry.parent_handle = 0;
            entry.local_port    = s_clients[i].local_port;
            entry.remote_ip     = s_clients[i].default_dest_ip;
            cb(&entry, ctx);
        }
    }
    xSemaphoreGive(s_mutex);
}

/* ── Select event loop for UDP receive ── */
static void udp_event_task(void *arg)
{
    struct timeval tv;
    fd_set read_fds;
    uint8_t recv_buf[UBCP_MAX_PAYLOAD_LEN];

    while (s_task_running) {
        FD_ZERO(&read_fds);
        int max_fd = -1;

        xSemaphoreTake(s_mutex, portMAX_DELAY);
        for (int i = 0; i < UDP_MAX_SERVERS; i++) {
            if (s_servers[i].active && s_servers[i].socket_fd >= 0) {
                FD_SET(s_servers[i].socket_fd, &read_fds);
                if (s_servers[i].socket_fd > max_fd) max_fd = s_servers[i].socket_fd;
            }
        }
        for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
            if (s_clients[i].active && s_clients[i].socket_fd >= 0) {
                FD_SET(s_clients[i].socket_fd, &read_fds);
                if (s_clients[i].socket_fd > max_fd) max_fd = s_clients[i].socket_fd;
            }
        }
        xSemaphoreGive(s_mutex);

        if (max_fd < 0) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        tv.tv_sec  = 0;
        tv.tv_usec = 100000;

        int ret = select(max_fd + 1, &read_fds, NULL, NULL, &tv);
        if (ret <= 0) continue;

        xSemaphoreTake(s_mutex, portMAX_DELAY);

        /* Check servers */
        for (int i = 0; i < UDP_MAX_SERVERS; i++) {
            if (!s_servers[i].active || s_servers[i].socket_fd < 0) continue;
            if (!FD_ISSET(s_servers[i].socket_fd, &read_fds)) continue;

            struct sockaddr_in src_addr;
            socklen_t addr_len = sizeof(src_addr);
            int recv_len = recvfrom(s_servers[i].socket_fd, recv_buf, sizeof(recv_buf),
                                     MSG_DONTWAIT, (struct sockaddr *)&src_addr, &addr_len);

            if (recv_len > 0) {
                uint16_t evt_len = 10 + recv_len;
                uint8_t *evt_payload = malloc(evt_len);
                if (evt_payload) {
                    evt_payload[0] = (uint8_t)(s_servers[i].handle >> 8);
                    evt_payload[1] = (uint8_t)(s_servers[i].handle & 0xFF);
                    evt_payload[2] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 24);
                    evt_payload[3] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 16);
                    evt_payload[4] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 8);
                    evt_payload[5] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) & 0xFF);
                    evt_payload[6] = (uint8_t)(ntohs(src_addr.sin_port) >> 8);
                    evt_payload[7] = (uint8_t)(ntohs(src_addr.sin_port) & 0xFF);
                    evt_payload[8] = (uint8_t)(recv_len >> 8);
                    evt_payload[9] = (uint8_t)(recv_len & 0xFF);
                    memcpy(&evt_payload[10], recv_buf, recv_len);

                    xSemaphoreGive(s_mutex);
                    send_event(UBCP_CMD_UDP_RECV, evt_payload, evt_len);
                    free(evt_payload);
                    xSemaphoreTake(s_mutex, portMAX_DELAY);
                }
            }
        }

        /* Check clients */
        for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
            if (!s_clients[i].active || s_clients[i].socket_fd < 0) continue;
            if (!FD_ISSET(s_clients[i].socket_fd, &read_fds)) continue;

            struct sockaddr_in src_addr;
            socklen_t addr_len = sizeof(src_addr);
            int recv_len = recvfrom(s_clients[i].socket_fd, recv_buf, sizeof(recv_buf),
                                     MSG_DONTWAIT, (struct sockaddr *)&src_addr, &addr_len);

            if (recv_len > 0) {
                uint16_t evt_len = 10 + recv_len;
                uint8_t *evt_payload = malloc(evt_len);
                if (evt_payload) {
                    evt_payload[0] = (uint8_t)(s_clients[i].handle >> 8);
                    evt_payload[1] = (uint8_t)(s_clients[i].handle & 0xFF);
                    evt_payload[2] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 24);
                    evt_payload[3] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 16);
                    evt_payload[4] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) >> 8);
                    evt_payload[5] = (uint8_t)(htonl(src_addr.sin_addr.s_addr) & 0xFF);
                    evt_payload[6] = (uint8_t)(ntohs(src_addr.sin_port) >> 8);
                    evt_payload[7] = (uint8_t)(ntohs(src_addr.sin_port) & 0xFF);
                    evt_payload[8] = (uint8_t)(recv_len >> 8);
                    evt_payload[9] = (uint8_t)(recv_len & 0xFF);
                    memcpy(&evt_payload[10], recv_buf, recv_len);

                    xSemaphoreGive(s_mutex);
                    send_event(UBCP_CMD_UDP_RECV, evt_payload, evt_len);
                    free(evt_payload);
                    xSemaphoreTake(s_mutex, portMAX_DELAY);
                }
            }
        }

        xSemaphoreGive(s_mutex);
    }

    vTaskDelete(NULL);
}

/* ========================================================================
 *  UDP_SERVER_OPEN (0x60)
 * ======================================================================== */
static void handle_server_open(const ubcp_frame_t *req)
{
    if (req->payload_len < 7) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t port       = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  broadcast  = req->payload[2];
    uint32_t multicast  = ntohl(((uint32_t)req->payload[3] << 24) | ((uint32_t)req->payload[4] << 16) |
                          ((uint32_t)req->payload[5] << 8)  |  (uint32_t)req->payload[6]);

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    udp_server_t *svr = NULL;
    for (int i = 0; i < UDP_MAX_SERVERS; i++) {
        if (!s_servers[i].active) { svr = &s_servers[i]; break; }
    }
    if (!svr) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_MAX_CONN);
        return;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    if (broadcast) {
        int opt = 1;
        setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &opt, sizeof(opt));
    }

    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = multicast ? multicast : INADDR_ANY;
    addr.sin_port        = htons(port);

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_PORT_IN_USE);
        return;
    }

    if (multicast) {
        struct ip_mreq mreq;
        mreq.imr_multiaddr.s_addr = multicast;
        mreq.imr_interface.s_addr = INADDR_ANY;
        setsockopt(sock, IPPROTO_IP, IP_ADD_MEMBERSHIP, &mreq, sizeof(mreq));
    }

    struct sockaddr_in actual_addr;
    socklen_t alen = sizeof(actual_addr);
    uint16_t actual_port = port;
    if (getsockname(sock, (struct sockaddr *)&actual_addr, &alen) == 0) {
        actual_port = ntohs(actual_addr.sin_port);
    }

    svr->handle         = alloc_handle();
    svr->socket_fd      = sock;
    svr->port           = actual_port;
    svr->broadcast_en   = broadcast;
    svr->multicast_addr = multicast;
    svr->active         = true;

    ESP_LOGI(TAG, "UDP Server opened: handle=0x%04X, port=%u", svr->handle, actual_port);
    xSemaphoreGive(s_mutex);

    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(svr->handle >> 8);
    payload[2] = (uint8_t)(svr->handle & 0xFF);
    payload[3] = (uint8_t)(actual_port >> 8);
    payload[4] = (uint8_t)(actual_port & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  UDP_SERVER_CLOSE (0x61)
 * ======================================================================== */
static void handle_server_close(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    for (int i = 0; i < UDP_MAX_SERVERS; i++) {
        if (s_servers[i].active && s_servers[i].handle == handle) {
            close(s_servers[i].socket_fd);
            s_servers[i].active = false;
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
            return;
        }
    }
    xSemaphoreGive(s_mutex);
    msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
}

/* ========================================================================
 *  UDP_CLIENT_CREATE (0x62)
 * ======================================================================== */
static void handle_client_create(const ubcp_frame_t *req)
{
    if (req->payload_len < 8) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint32_t dest_ip   = ntohl(((uint32_t)req->payload[0] << 24) | ((uint32_t)req->payload[1] << 16) |
                         ((uint32_t)req->payload[2] << 8)  |  (uint32_t)req->payload[3]);
    uint16_t dest_port = ((uint16_t)req->payload[4] << 8) | req->payload[5];
    uint16_t local_port = ((uint16_t)req->payload[6] << 8) | req->payload[7];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    udp_client_t *cli = NULL;
    for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
        if (!s_clients[i].active) { cli = &s_clients[i]; break; }
    }
    if (!cli) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_MAX_CONN);
        return;
    }

    int sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (sock < 0) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    if (local_port != 0) {
        struct sockaddr_in laddr;
        memset(&laddr, 0, sizeof(laddr));
        laddr.sin_family      = AF_INET;
        laddr.sin_addr.s_addr = INADDR_ANY;
        laddr.sin_port        = htons(local_port);
        if (bind(sock, (struct sockaddr *)&laddr, sizeof(laddr)) < 0) {
            close(sock);
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_PORT_IN_USE);
            return;
        }
    }

    struct sockaddr_in actual_addr;
    socklen_t alen = sizeof(actual_addr);
    uint16_t actual_port = local_port;
    if (getsockname(sock, (struct sockaddr *)&actual_addr, &alen) == 0) {
        actual_port = ntohs(actual_addr.sin_port);
    }

    cli->handle           = alloc_handle() | 0x8000; /* Mark as client handle (high bit) */
    cli->socket_fd        = sock;
    cli->default_dest_ip  = dest_ip;
    cli->default_dest_port = dest_port;
    cli->local_port       = actual_port;
    cli->active           = true;

    ESP_LOGI(TAG, "UDP Client created: handle=0x%04X, port=%u", cli->handle, actual_port);
    xSemaphoreGive(s_mutex);

    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(cli->handle >> 8);
    payload[2] = (uint8_t)(cli->handle & 0xFF);
    payload[3] = (uint8_t)(actual_port >> 8);
    payload[4] = (uint8_t)(actual_port & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  UDP_CLIENT_DELETE (0x63)
 * ======================================================================== */
static void handle_client_delete(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
        if (s_clients[i].active && s_clients[i].handle == handle) {
            close(s_clients[i].socket_fd);
            s_clients[i].active = false;
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
            return;
        }
    }
    xSemaphoreGive(s_mutex);
    msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
}

/* ========================================================================
 *  UDP_SERVER_SEND (0x64)
 * ======================================================================== */
static void handle_server_send(const ubcp_frame_t *req)
{
    if (req->payload_len < 10) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle   = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint32_t dest_ip  = ntohl(((uint32_t)req->payload[2] << 24) | ((uint32_t)req->payload[3] << 16) |
                        ((uint32_t)req->payload[4] << 8)  |  (uint32_t)req->payload[5]);
    uint16_t dest_port = ((uint16_t)req->payload[6] << 8) | req->payload[7];
    uint16_t data_len  = ((uint16_t)req->payload[8] << 8) | req->payload[9];

    if (req->payload_len < (uint16_t)(10 + data_len)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    int sock_fd = -1;
    for (int i = 0; i < UDP_MAX_SERVERS; i++) {
        if (s_servers[i].active && s_servers[i].handle == handle) {
            sock_fd = s_servers[i].socket_fd;
            break;
        }
    }
    xSemaphoreGive(s_mutex);

    if (sock_fd < 0) {
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = dest_ip;
    addr.sin_port        = htons(dest_port);

    int sent = sendto(sock_fd, &req->payload[10], data_len, MSG_DONTWAIT,
                      (struct sockaddr *)&addr, sizeof(addr));

    uint8_t payload[3];
    payload[0] = (sent >= 0) ? UBCP_ERR_SUCCESS : UBCP_ERR_NET_DISCONNECTED;
    payload[1] = (uint8_t)((sent > 0 ? sent : 0) >> 8);
    payload[2] = (uint8_t)((sent > 0 ? sent : 0) & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  UDP_CLIENT_SEND (0x66)
 * ======================================================================== */
static void handle_client_send(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle    = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  addr_mode = req->payload[2];

    uint32_t dest_ip;
    uint16_t dest_port;
    uint16_t data_offset;
    uint16_t data_len;

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    udp_client_t *cli = NULL;
    for (int i = 0; i < UDP_MAX_CLIENTS; i++) {
        if (s_clients[i].active && s_clients[i].handle == handle) {
            cli = &s_clients[i];
            break;
        }
    }
    if (!cli) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    if (addr_mode == 0x00) {
        dest_ip   = cli->default_dest_ip;
        dest_port = cli->default_dest_port;

        if (req->payload_len < 5) {
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        data_len   = ((uint16_t)req->payload[3] << 8) | req->payload[4];
        data_offset = 5;
    } else if (addr_mode == 0x01) {
        if (req->payload_len < 11) {
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }
        dest_ip   = ntohl(((uint32_t)req->payload[3] << 24) | ((uint32_t)req->payload[4] << 16) |
                    ((uint32_t)req->payload[5] << 8)  |  (uint32_t)req->payload[6]);
        dest_port = ((uint16_t)req->payload[7] << 8) | req->payload[8];
        data_len  = ((uint16_t)req->payload[9] << 8) | req->payload[10];
        data_offset = 11;
    } else {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    if (req->payload_len < (uint16_t)(data_offset + data_len)) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    int sock_fd = cli->socket_fd;
    xSemaphoreGive(s_mutex);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = dest_ip;
    addr.sin_port        = htons(dest_port);

    int sent = sendto(sock_fd, &req->payload[data_offset], data_len, MSG_DONTWAIT,
                      (struct sockaddr *)&addr, sizeof(addr));

    uint8_t payload[3];
    payload[0] = (sent >= 0) ? UBCP_ERR_SUCCESS : UBCP_ERR_NET_DISCONNECTED;
    payload[1] = (uint8_t)((sent > 0 ? sent : 0) >> 8);
    payload[2] = (uint8_t)((sent > 0 ? sent : 0) & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  Module init and dispatch
 * ======================================================================== */
static esp_err_t udp_init(void)
{
    memset(s_servers, 0, sizeof(s_servers));
    memset(s_clients, 0, sizeof(s_clients));

    s_mutex = xSemaphoreCreateMutex();
    if (!s_mutex) return ESP_ERR_NO_MEM;

    s_task_running = true;
    BaseType_t ret = xTaskCreate(udp_event_task, "udp_select", 4096, NULL, 7, &s_select_task);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create UDP select task");
        return ESP_ERR_NO_MEM;
    }

    mod_network_register_conn_provider("UDP", udp_iterate_conns);

    ESP_LOGI(TAG, "UDP 模块初始化完成");
    return ESP_OK;
}

static void udp_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_UDP_SERVER_OPEN:  handle_server_open(frame);  break;
    case UBCP_CMD_UDP_SERVER_CLOSE: handle_server_close(frame); break;
    case UBCP_CMD_UDP_CLIENT_CREATE: handle_client_create(frame); break;
    case UBCP_CMD_UDP_CLIENT_DELETE: handle_client_delete(frame); break;
    case UBCP_CMD_UDP_SERVER_SEND:  handle_server_send(frame); break;
    case UBCP_CMD_UDP_CLIENT_SEND:  handle_client_send(frame); break;
    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static const hex_module_t s_udp_module = {
    .name            = "UDP",
    .cmd_range_start = UBCP_CMD_RANGE_UDP_START,
    .cmd_range_end   = UBCP_CMD_RANGE_UDP_END,
    .init            = udp_init,
    .handle_cmd      = udp_handle_cmd,
    .stop            = NULL,
};

const hex_module_t *mod_udp_get(void)
{
    return &s_udp_module;
}
