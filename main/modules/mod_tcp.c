#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "esp_timer.h"
#include "modules/mod_tcp.h"
#include "modules/mod_network.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "core/eth_init.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_tcp";

/* ── Constants ── */
#define TCP_MAX_SERVERS  4
#define TCP_MAX_CONNS   16

/* ── TCP Server ── */
typedef struct {
    uint16_t server_handle;
    int      listen_fd;
    uint16_t port;
    uint8_t  max_conn;
    uint8_t  accept_mode;
    uint8_t  keepalive_sec;
    bool     active;
} tcp_server_t;

/* ── TCP Connection ── */
typedef struct {
    uint16_t conn_handle;
    uint16_t server_handle;
    int      socket_fd;
    uint32_t remote_ip;
    uint16_t remote_port;
    uint32_t local_ip;
    uint16_t local_port;
    uint8_t  keepalive_sec;
    bool     is_server_child;
    bool     active;
    uint32_t connect_time_sec;
    uint32_t tx_bytes;
    uint32_t rx_bytes;
    uint8_t  conn_state;
} tcp_conn_t;

/* ── Global state ── */
static tcp_server_t s_servers[TCP_MAX_SERVERS];
static tcp_conn_t   s_conns[TCP_MAX_CONNS];
static SemaphoreHandle_t s_mutex = NULL;
static TaskHandle_t s_select_task = NULL;
static volatile bool s_task_running = false;

static uint16_t s_next_server_handle = 0x0001;
static uint16_t s_next_client_handle = 0x8001;

/* ── Handles ── */
static uint16_t alloc_server_handle(void)
{
    uint16_t h = s_next_server_handle++;
    if (s_next_server_handle >= 0x8000) s_next_server_handle = 0x0001;
    return h;
}

static uint16_t alloc_client_handle(void)
{
    uint16_t h = s_next_client_handle++;
    if (s_next_client_handle >= 0xFFFE) s_next_client_handle = 0x8001;
    return h;
}

/* ── Send event frame helper ── */
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

/* ── Find helpers ── */
static tcp_server_t *find_server_by_handle(uint16_t handle)
{
    for (int i = 0; i < TCP_MAX_SERVERS; i++) {
        if (s_servers[i].active && s_servers[i].server_handle == handle) {
            return &s_servers[i];
        }
    }
    return NULL;
}

static tcp_server_t *find_empty_server_slot(void)
{
    for (int i = 0; i < TCP_MAX_SERVERS; i++) {
        if (!s_servers[i].active) return &s_servers[i];
    }
    return NULL;
}

static tcp_conn_t *find_conn_by_handle(uint16_t handle)
{
    for (int i = 0; i < TCP_MAX_CONNS; i++) {
        if (s_conns[i].active && s_conns[i].conn_handle == handle) {
            return &s_conns[i];
        }
    }
    return NULL;
}

static tcp_conn_t *find_empty_conn_slot(void)
{
    for (int i = 0; i < TCP_MAX_CONNS; i++) {
        if (!s_conns[i].active) return &s_conns[i];
    }
    return NULL;
}

/* ── Cleanup connection ── */
static void cleanup_conn(tcp_conn_t *conn)
{
    if (conn->socket_fd >= 0) {
        close(conn->socket_fd);
        conn->socket_fd = -1;
    }
    conn->active = false;
}

/* ── Send disconnect event ── */
static void send_disconnect_event(tcp_conn_t *conn, uint8_t reason)
{
    uint8_t payload[9];
    payload[0] = (uint8_t)(conn->conn_handle >> 8);
    payload[1] = (uint8_t)(conn->conn_handle & 0xFF);
    payload[2] = reason;
    payload[3] = (uint8_t)(conn->remote_ip >> 24);
    payload[4] = (uint8_t)(conn->remote_ip >> 16);
    payload[5] = (uint8_t)(conn->remote_ip >> 8);
    payload[6] = (uint8_t)(conn->remote_ip & 0xFF);
    payload[7] = (uint8_t)(conn->remote_port >> 8);
    payload[8] = (uint8_t)(conn->remote_port & 0xFF);

    send_event(UBCP_CMD_TCP_DISC_EVENT, payload, sizeof(payload));
}

/* ── Connection list iterate for NET_LIST_CONNS ── */
static void tcp_iterate_conns(net_conn_iter_cb cb, void *ctx)
{
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    for (int i = 0; i < TCP_MAX_SERVERS; i++) {
        if (s_servers[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_TCP_SERVER;
            entry.handle        = s_servers[i].server_handle;
            entry.parent_handle = 0;
            entry.local_port    = s_servers[i].port;
            entry.remote_ip     = 0;
            cb(&entry, ctx);
        }
    }
    for (int i = 0; i < TCP_MAX_CONNS; i++) {
        if (s_conns[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_TCP_CONN;
            entry.handle        = s_conns[i].conn_handle;
            entry.parent_handle = s_conns[i].is_server_child ? s_conns[i].server_handle : 0;
            entry.local_port    = s_conns[i].local_port;
            entry.remote_ip     = s_conns[i].remote_ip;
            cb(&entry, ctx);
        }
    }
    xSemaphoreGive(s_mutex);
}

/* ========================================================================
 *  Select event loop
 * ======================================================================== */
static void tcp_event_task(void *arg)
{
    struct timeval tv;
    fd_set read_fds, write_fds, except_fds;
    uint8_t recv_buf[UBCP_MAX_PAYLOAD_LEN];

    while (s_task_running) {
        FD_ZERO(&read_fds);
        FD_ZERO(&write_fds);
        FD_ZERO(&except_fds);
        int max_fd = -1;

        xSemaphoreTake(s_mutex, portMAX_DELAY);

        for (int i = 0; i < TCP_MAX_SERVERS; i++) {
            if (s_servers[i].active && s_servers[i].listen_fd >= 0) {
                FD_SET(s_servers[i].listen_fd, &read_fds);
                if (s_servers[i].listen_fd > max_fd) max_fd = s_servers[i].listen_fd;
            }
        }

        for (int i = 0; i < TCP_MAX_CONNS; i++) {
            if (s_conns[i].active && s_conns[i].socket_fd >= 0) {
                FD_SET(s_conns[i].socket_fd, &read_fds);
                FD_SET(s_conns[i].socket_fd, &except_fds);
                if (s_conns[i].socket_fd > max_fd) max_fd = s_conns[i].socket_fd;
            }
        }

        xSemaphoreGive(s_mutex);

        if (max_fd < 0) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        tv.tv_sec  = 0;
        tv.tv_usec = 100000; /* 100ms */

        int ret = select(max_fd + 1, &read_fds, NULL, &except_fds, &tv);
        if (ret < 0) {
            ESP_LOGE(TAG, "select() error: %d", errno);
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }
        if (ret == 0) continue;

        xSemaphoreTake(s_mutex, portMAX_DELAY);

        /* Check server accept */
        for (int i = 0; i < TCP_MAX_SERVERS; i++) {
            if (!s_servers[i].active || s_servers[i].listen_fd < 0) continue;
            if (!FD_ISSET(s_servers[i].listen_fd, &read_fds)) continue;

            struct sockaddr_in client_addr;
            socklen_t addr_len = sizeof(client_addr);
            int client_fd = accept(s_servers[i].listen_fd, (struct sockaddr *)&client_addr, &addr_len);

            if (client_fd < 0) {
                ESP_LOGW(TAG, "accept() failed: %d", errno);
                continue;
            }

            tcp_conn_t *conn = find_empty_conn_slot();
            if (!conn) {
                ESP_LOGW(TAG, "Max connections reached, rejecting new client");
                close(client_fd);
                continue;
            }

            /* Set non-blocking */
            int flags = fcntl(client_fd, F_GETFL, 0);
            if (flags >= 0) fcntl(client_fd, F_SETFL, flags | O_NONBLOCK);

            conn->conn_handle      = alloc_client_handle();
            conn->server_handle    = s_servers[i].server_handle;
            conn->socket_fd        = client_fd;
            conn->remote_ip        = client_addr.sin_addr.s_addr;
            conn->remote_port      = ntohs(client_addr.sin_port);
            conn->is_server_child  = true;
            conn->active           = true;
            conn->connect_time_sec = esp_timer_get_time() / 1000000;
            conn->tx_bytes         = 0;
            conn->rx_bytes         = 0;
            conn->conn_state       = 0; /* ESTABLISHED */

            /* Get local addr */
            struct sockaddr_in local_addr;
            socklen_t local_len = sizeof(local_addr);
            if (getsockname(client_fd, (struct sockaddr *)&local_addr, &local_len) == 0) {
                conn->local_ip   = local_addr.sin_addr.s_addr;
                conn->local_port = ntohs(local_addr.sin_port);
            }

            ESP_LOGI(TAG, "TCP client accepted: fd=%d, handle=0x%04X", client_fd, conn->conn_handle);

            /* Send TCP_ACCEPT event */
            uint8_t evt_payload[10];
            memset(evt_payload, 0, sizeof(evt_payload));
            evt_payload[0] = (uint8_t)(s_servers[i].server_handle >> 8);
            evt_payload[1] = (uint8_t)(s_servers[i].server_handle & 0xFF);
            evt_payload[2] = (uint8_t)(conn->conn_handle >> 8);
            evt_payload[3] = (uint8_t)(conn->conn_handle & 0xFF);
            evt_payload[4] = (uint8_t)(conn->remote_ip >> 24);
            evt_payload[5] = (uint8_t)(conn->remote_ip >> 16);
            evt_payload[6] = (uint8_t)(conn->remote_ip >> 8);
            evt_payload[7] = (uint8_t)(conn->remote_ip & 0xFF);
            evt_payload[8] = (uint8_t)(conn->remote_port >> 8);
            evt_payload[9] = (uint8_t)(conn->remote_port & 0xFF);

            /* Need to release mutex before sending event to avoid deadlock */
            xSemaphoreGive(s_mutex);
            send_event(UBCP_CMD_TCP_ACCEPT, evt_payload, sizeof(evt_payload));
            xSemaphoreTake(s_mutex, portMAX_DELAY);
        }

        /* Check connection readability */
        for (int i = 0; i < TCP_MAX_CONNS; i++) {
            if (!s_conns[i].active || s_conns[i].socket_fd < 0) continue;

            bool has_error = FD_ISSET(s_conns[i].socket_fd, &except_fds);
            bool has_data  = FD_ISSET(s_conns[i].socket_fd, &read_fds);

            if (has_error) {
                send_disconnect_event(&s_conns[i], 0x01); /* 连接重置 */
                cleanup_conn(&s_conns[i]);
                continue;
            }

            if (has_data) {
                int recv_len = recv(s_conns[i].socket_fd, recv_buf, sizeof(recv_buf), MSG_DONTWAIT);

                if (recv_len == 0) {
                    /* Remote closed gracefully */
                    send_disconnect_event(&s_conns[i], 0x00); /* 正常关闭 */
                    cleanup_conn(&s_conns[i]);
                } else if (recv_len < 0) {
                    if (errno != EAGAIN && errno != EWOULDBLOCK) {
                        send_disconnect_event(&s_conns[i], 0x03); /* 网络错误 */
                        cleanup_conn(&s_conns[i]);
                    }
                } else {
                    s_conns[i].rx_bytes += recv_len;

                    /* Build TCP_RECV event */
                    uint16_t evt_len = 4 + recv_len;
                    uint8_t *evt_payload = malloc(evt_len);
                    if (evt_payload) {
                        evt_payload[0] = (uint8_t)(s_conns[i].conn_handle >> 8);
                        evt_payload[1] = (uint8_t)(s_conns[i].conn_handle & 0xFF);
                        evt_payload[2] = (uint8_t)(recv_len >> 8);
                        evt_payload[3] = (uint8_t)(recv_len & 0xFF);
                        memcpy(&evt_payload[4], recv_buf, recv_len);

                        xSemaphoreGive(s_mutex);
                        send_event(UBCP_CMD_TCP_RECV, evt_payload, evt_len);
                        free(evt_payload);
                        xSemaphoreTake(s_mutex, portMAX_DELAY);
                    }
                }
            }
        }

        xSemaphoreGive(s_mutex);
    }

    vTaskDelete(NULL);
}

/* ========================================================================
 *  TCP_SERVER_OPEN (0x50)
 * ======================================================================== */
static void handle_server_open(const ubcp_frame_t *req)
{
    if (req->payload_len < 4) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t port   = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  maxconn = req->payload[2];
    uint8_t  accept_mode = req->payload[3];
    uint8_t  keepalive   = (req->payload_len > 4) ? req->payload[4] : 0;

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    tcp_server_t *svr = find_empty_server_slot();
    if (!svr) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_MAX_CONN);
        return;
    }

    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port        = htons(port);

    if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        close(sock);
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_PORT_IN_USE);
        return;
    }

    if (listen(sock, maxconn > 0 ? maxconn : 5) < 0) {
        close(sock);
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    /* Set non-blocking */
    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    /* Get actual port */
    struct sockaddr_in actual_addr;
    socklen_t alen = sizeof(actual_addr);
    uint16_t actual_port = port;
    if (getsockname(sock, (struct sockaddr *)&actual_addr, &alen) == 0) {
        actual_port = ntohs(actual_addr.sin_port);
    }

    svr->server_handle = alloc_server_handle();
    svr->listen_fd     = sock;
    svr->port          = actual_port;
    svr->max_conn      = maxconn;
    svr->accept_mode   = accept_mode;
    svr->keepalive_sec = keepalive;
    svr->active        = true;

    ESP_LOGI(TAG, "TCP Server opened: handle=0x%04X, port=%u", svr->server_handle, actual_port);

    xSemaphoreGive(s_mutex);

    uint8_t payload[5];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(svr->server_handle >> 8);
    payload[2] = (uint8_t)(svr->server_handle & 0xFF);
    payload[3] = (uint8_t)(actual_port >> 8);
    payload[4] = (uint8_t)(actual_port & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  TCP_SERVER_CLOSE (0x51)
 * ======================================================================== */
static void handle_server_close(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  force  = req->payload[2];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_server_t *svr = find_server_by_handle(handle);
    if (!svr) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    /* Close all child connections */
    for (int i = 0; i < TCP_MAX_CONNS; i++) {
        if (s_conns[i].active && s_conns[i].is_server_child &&
            s_conns[i].server_handle == handle) {
            send_disconnect_event(&s_conns[i], force ? 0x01 : 0x00);
            cleanup_conn(&s_conns[i]);
        }
    }

    close(svr->listen_fd);
    svr->active = false;
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  TCP_CLIENT_CONNECT (0x52)
 * ======================================================================== */
static void handle_client_connect(const ubcp_frame_t *req)
{
    if (req->payload_len < 7) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint32_t dest_ip   = ((uint32_t)req->payload[0] << 24) | ((uint32_t)req->payload[1] << 16) |
                         ((uint32_t)req->payload[2] << 8)  |  (uint32_t)req->payload[3];
    uint16_t dest_port = ((uint16_t)req->payload[4] << 8) | req->payload[5];
    uint8_t  timeout   = req->payload[6];
    uint8_t  keepalive = (req->payload_len > 7) ? req->payload[7] : 0;

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_empty_conn_slot();
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_MAX_CONN);
        return;
    }

    int sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (sock < 0) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) fcntl(sock, F_SETFL, flags | O_NONBLOCK);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family      = AF_INET;
    addr.sin_addr.s_addr = dest_ip;
    addr.sin_port        = htons(dest_port);

    int cr = connect(sock, (struct sockaddr *)&addr, sizeof(addr));
    if (cr < 0 && errno != EINPROGRESS) {
        close(sock);
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_CONN_REFUSED);
        return;
    }

    /* Wait for connection via select */
    if (cr < 0) {
        fd_set wfds;
        struct timeval tv;
        FD_ZERO(&wfds);
        FD_SET(sock, &wfds);
        tv.tv_sec  = timeout > 0 ? timeout : 5;
        tv.tv_usec = 0;

        int sel = select(sock + 1, NULL, &wfds, NULL, &tv);
        if (sel <= 0) {
            close(sock);
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_TIMEOUT);
            return;
        }

        /* Check if connection succeeded */
        int err = 0;
        socklen_t errlen = sizeof(err);
        getsockopt(sock, SOL_SOCKET, SO_ERROR, &err, &errlen);
        if (err != 0) {
            close(sock);
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_CONN_REFUSED);
            return;
        }
    }

    /* Get local addr */
    struct sockaddr_in local_addr;
    socklen_t local_len = sizeof(local_addr);
    uint32_t local_ip = 0;
    uint16_t local_port = 0;
    if (getsockname(sock, (struct sockaddr *)&local_addr, &local_len) == 0) {
        local_ip   = local_addr.sin_addr.s_addr;
        local_port = ntohs(local_addr.sin_port);
    }

    conn->conn_handle      = alloc_client_handle();
    conn->server_handle    = 0;
    conn->socket_fd        = sock;
    conn->remote_ip        = dest_ip;
    conn->remote_port      = dest_port;
    conn->local_ip         = local_ip;
    conn->local_port       = local_port;
    conn->keepalive_sec    = keepalive;
    conn->is_server_child  = false;
    conn->active           = true;
    conn->connect_time_sec = esp_timer_get_time() / 1000000;
    conn->tx_bytes         = 0;
    conn->rx_bytes         = 0;
    conn->conn_state       = 0;

    ESP_LOGI(TAG, "TCP Client connected: handle=0x%04X, fd=%d", conn->conn_handle, sock);
    xSemaphoreGive(s_mutex);

    uint8_t payload[9];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(conn->conn_handle >> 8);
    payload[2] = (uint8_t)(conn->conn_handle & 0xFF);
    payload[3] = (uint8_t)(local_ip >> 24);
    payload[4] = (uint8_t)(local_ip >> 16);
    payload[5] = (uint8_t)(local_ip >> 8);
    payload[6] = (uint8_t)(local_ip & 0xFF);
    payload[7] = (uint8_t)(local_port >> 8);
    payload[8] = (uint8_t)(local_port & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  TCP_CLIENT_DISCONNECT (0x53)
 * ======================================================================== */
static void handle_client_disconnect(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    cleanup_conn(conn);
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  TCP_SEND (0x54)
 * ======================================================================== */
static void handle_send(const ubcp_frame_t *req)
{
    if (req->payload_len < 4) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle   = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint16_t data_len = ((uint16_t)req->payload[2] << 8) | req->payload[3];

    if (req->payload_len < (uint16_t)(4 + data_len)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    int sent = send(conn->socket_fd, &req->payload[4], data_len, MSG_DONTWAIT);
    xSemaphoreGive(s_mutex);

    uint8_t payload[3];
    if (sent < 0) {
        payload[0] = UBCP_ERR_NET_DISCONNECTED;
        payload[1] = 0;
        payload[2] = 0;
    } else {
        conn->tx_bytes += sent;
        payload[0] = UBCP_ERR_SUCCESS;
        payload[1] = (uint8_t)(sent >> 8);
        payload[2] = (uint8_t)(sent & 0xFF);
    }

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  TCP_ACCEPT (0x56) — Manual accept confirm
 * ======================================================================== */
static void handle_accept_confirm(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t client_handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  decision      = req->payload[2]; /* 0=accept, 1=reject */

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_conn_by_handle(client_handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    if (decision == 1) {
        /* Reject — close connection */
        cleanup_conn(conn);
    }
    /* Accept — keep active (already accepted by accept()) */
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  TCP_CLOSE (0x57) — Generic close
 * ======================================================================== */
static void handle_close(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle      = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  handle_type = req->payload[2];

    xSemaphoreTake(s_mutex, portMAX_DELAY);

    if (handle_type == 0) {
        /* Close connection */
        tcp_conn_t *conn = find_conn_by_handle(handle);
        if (!conn) {
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
            return;
        }
        cleanup_conn(conn);
    } else if (handle_type == 1) {
        /* Close server */
        tcp_server_t *svr = find_server_by_handle(handle);
        if (!svr) {
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
            return;
        }

        for (int i = 0; i < TCP_MAX_CONNS; i++) {
            if (s_conns[i].active && s_conns[i].is_server_child &&
                s_conns[i].server_handle == handle) {
                cleanup_conn(&s_conns[i]);
            }
        }
        close(svr->listen_fd);
        svr->active = false;
    }

    xSemaphoreGive(s_mutex);
    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  TCP_LIST_CLIENTS (0x59)
 * ======================================================================== */
static void handle_list_clients(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t server_handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_server_t *svr = find_server_by_handle(server_handle);
    if (!svr) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    /* Count and collect */
    int count = 0;
    uint8_t entries[TCP_MAX_CONNS * 10];
    uint16_t entry_offset = 0;

    for (int i = 0; i < TCP_MAX_CONNS; i++) {
        if (s_conns[i].active && s_conns[i].is_server_child &&
            s_conns[i].server_handle == server_handle) {
            tcp_conn_t *c = &s_conns[i];
            uint32_t now = esp_timer_get_time() / 1000000;
            uint16_t up_time = (uint16_t)(now - c->connect_time_sec);

            entries[entry_offset + 0] = (uint8_t)(c->conn_handle >> 8);
            entries[entry_offset + 1] = (uint8_t)(c->conn_handle & 0xFF);
            entries[entry_offset + 2] = (uint8_t)(c->remote_ip >> 24);
            entries[entry_offset + 3] = (uint8_t)(c->remote_ip >> 16);
            entries[entry_offset + 4] = (uint8_t)(c->remote_ip >> 8);
            entries[entry_offset + 5] = (uint8_t)(c->remote_ip & 0xFF);
            entries[entry_offset + 6] = (uint8_t)(c->remote_port >> 8);
            entries[entry_offset + 7] = (uint8_t)(c->remote_port & 0xFF);
            entries[entry_offset + 8] = (uint8_t)(up_time >> 8);
            entries[entry_offset + 9] = (uint8_t)(up_time & 0xFF);
            entry_offset += 10;
            count++;
        }
    }
    xSemaphoreGive(s_mutex);

    uint16_t plen = 2 + count * 10;
    uint8_t *payload = malloc(plen);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)count;
    if (entry_offset > 0) memcpy(&payload[2], entries, entry_offset);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = plen;
    msg_bus_send_frame(&resp);
    free(payload);
}

/* ========================================================================
 *  TCP_KICK_CLIENT (0x5A)
 * ======================================================================== */
static void handle_kick_client(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t client_handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  force_flag    = req->payload[2];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_conn_by_handle(client_handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    if (force_flag) {
        struct linger l = { .l_onoff = 1, .l_linger = 0 };
        setsockopt(conn->socket_fd, SOL_SOCKET, SO_LINGER, &l, sizeof(l));
    }

    send_disconnect_event(conn, force_flag ? 0x01 : 0x00);
    cleanup_conn(conn);
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  TCP_CONN_STATUS (0x5B)
 * ======================================================================== */
static void handle_conn_status(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    tcp_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    uint32_t now = esp_timer_get_time() / 1000000;
    uint32_t up_time = now - conn->connect_time_sec;

    uint8_t payload[22];
    payload[0]  = UBCP_ERR_SUCCESS;
    payload[1]  = conn->conn_state;
    payload[2]  = (uint8_t)(conn->tx_bytes >> 24);
    payload[3]  = (uint8_t)(conn->tx_bytes >> 16);
    payload[4]  = (uint8_t)(conn->tx_bytes >> 8);
    payload[5]  = (uint8_t)(conn->tx_bytes & 0xFF);
    payload[6]  = (uint8_t)(conn->rx_bytes >> 24);
    payload[7]  = (uint8_t)(conn->rx_bytes >> 16);
    payload[8]  = (uint8_t)(conn->rx_bytes >> 8);
    payload[9]  = (uint8_t)(conn->rx_bytes & 0xFF);
    payload[10] = (uint8_t)(conn->remote_ip >> 24);
    payload[11] = (uint8_t)(conn->remote_ip >> 16);
    payload[12] = (uint8_t)(conn->remote_ip >> 8);
    payload[13] = (uint8_t)(conn->remote_ip & 0xFF);
    payload[14] = (uint8_t)(conn->remote_port >> 8);
    payload[15] = (uint8_t)(conn->remote_port & 0xFF);
    payload[16] = (uint8_t)(conn->local_port >> 8);
    payload[17] = (uint8_t)(conn->local_port & 0xFF);
    payload[18] = (uint8_t)(up_time >> 24);
    payload[19] = (uint8_t)(up_time >> 16);
    payload[20] = (uint8_t)(up_time >> 8);
    payload[21] = (uint8_t)(up_time & 0xFF);

    xSemaphoreGive(s_mutex);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  Module init and dispatch
 * ======================================================================== */
static esp_err_t tcp_init(void)
{
    memset(s_servers, 0, sizeof(s_servers));
    memset(s_conns, 0, sizeof(s_conns));

    s_mutex = xSemaphoreCreateMutex();
    if (!s_mutex) return ESP_ERR_NO_MEM;

    s_task_running = true;
    BaseType_t ret = xTaskCreate(tcp_event_task, "tcp_select", 6144, NULL, 7, &s_select_task);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create TCP select task");
        return ESP_ERR_NO_MEM;
    }

    /* Register with mod_network for NET_LIST_CONNS */
    mod_network_register_conn_provider("TCP", tcp_iterate_conns);

    ESP_LOGI(TAG, "TCP 模块初始化完成");
    return ESP_OK;
}

static void tcp_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_TCP_SERVER_OPEN:   handle_server_open(frame);    break;
    case UBCP_CMD_TCP_SERVER_CLOSE:  handle_server_close(frame);   break;
    case UBCP_CMD_TCP_CLIENT_CONN:   handle_client_connect(frame); break;
    case UBCP_CMD_TCP_CLIENT_DISC:   handle_client_disconnect(frame); break;
    case UBCP_CMD_TCP_SEND:          handle_send(frame);           break;
    case UBCP_CMD_TCP_ACCEPT:        handle_accept_confirm(frame); break;
    case UBCP_CMD_TCP_CLOSE:         handle_close(frame);          break;
    case UBCP_CMD_TCP_LIST_CLIENTS:  handle_list_clients(frame);   break;
    case UBCP_CMD_TCP_KICK_CLIENT:   handle_kick_client(frame);    break;
    case UBCP_CMD_TCP_CONN_STATUS:   handle_conn_status(frame);    break;
    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static const hex_module_t s_tcp_module = {
    .name            = "TCP",
    .cmd_range_start = UBCP_CMD_RANGE_TCP_START,
    .cmd_range_end   = UBCP_CMD_RANGE_TCP_END,
    .init            = tcp_init,
    .handle_cmd      = tcp_handle_cmd,
    .stop            = NULL,
};

const hex_module_t *mod_tcp_get(void)
{
    return &s_tcp_module;
}
