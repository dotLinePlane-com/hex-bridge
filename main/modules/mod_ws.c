#include <string.h>
#include <stdlib.h>
#include <errno.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/sockets.h"
#include "esp_timer.h"
#include "modules/mod_ws.h"
#include "modules/mod_network.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_ws";

#define WS_MAX_SERVERS  4
#define WS_MAX_CONNS   16
#define WS_RECV_BUF_SIZE 4096

static const char WS_GUID[] = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

typedef struct {
    uint16_t server_handle;
    int      listen_fd;
    uint16_t port;
    uint8_t  max_conn;
    char     path[64];
    uint8_t  path_len;
    bool     active;
} ws_server_t;

typedef struct {
    uint16_t conn_handle;
    uint16_t server_handle;
    int      socket_fd;
    uint32_t client_ip;
    uint16_t client_port;
    uint8_t  subproto_index;
    uint8_t  path_len;
    char     path[64];
    uint32_t connect_time_sec;
    bool     is_client_side;
    bool     active;
} ws_conn_t;

static ws_server_t s_servers[WS_MAX_SERVERS];
static ws_conn_t   s_conns[WS_MAX_CONNS];
static SemaphoreHandle_t s_mutex = NULL;
static TaskHandle_t s_ws_task = NULL;
static volatile bool s_task_running = false;

static uint16_t s_next_server_handle = 0x0001;
static uint16_t s_next_conn_handle   = 0x8001;

static uint16_t alloc_server_handle(void)
{
    uint16_t h = s_next_server_handle++;
    if (s_next_server_handle >= 0x8000) s_next_server_handle = 0x0001;
    return h;
}

static uint16_t alloc_conn_handle(void)
{
    uint16_t h = s_next_conn_handle++;
    if (s_next_conn_handle >= 0xFFFE) s_next_conn_handle = 0x8001;
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

static void cleanup_conn(ws_conn_t *conn)
{
    if (conn->socket_fd >= 0) {
        close(conn->socket_fd);
        conn->socket_fd = -1;
    }
    conn->active = false;
}

/* ── Base64 encode ── */
static int base64_encode(const uint8_t *src, size_t src_len, char *dst, size_t dst_len)
{
    static const char table[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    size_t out_len = ((src_len + 2) / 3) * 4;
    if (out_len + 1 > dst_len) return -1;

    size_t i, j;
    for (i = 0, j = 0; i < src_len; i += 3) {
        uint32_t val = (uint32_t)src[i] << 16;
        if (i + 1 < src_len) val |= (uint32_t)src[i + 1] << 8;
        if (i + 2 < src_len) val |= (uint32_t)src[i + 2];

        dst[j++] = table[(val >> 18) & 0x3F];
        dst[j++] = table[(val >> 12) & 0x3F];
        dst[j++] = (i + 1 < src_len) ? table[(val >> 6) & 0x3F] : '=';
        dst[j++] = (i + 2 < src_len) ? table[val & 0x3F] : '=';
    }
    dst[j] = '\0';
    return j;
}

/* ── HTTP header parser ── */
static char *http_header_find(char *data, int len, const char *key)
{
    int key_len = strlen(key);
    char *p = data;
    char *end = data + len;

    while (p < end) {
        if (p + key_len < end && strncasecmp(p, key, key_len) == 0 && p[key_len] == ':') {
            p += key_len + 1;
            while (p < end && (*p == ' ' || *p == '\t')) p++;
            return p;
        }
        /* Skip to next line */
        while (p < end && *p != '\r' && *p != '\n') p++;
        if (p < end && *p == '\r') p++;
        if (p < end && *p == '\n') p++;
    }
    return NULL;
}

/* ── SHA-1 implementation (inline, avoids mbedtls 4.x API changes) ── */
typedef struct {
    uint32_t state[5];
    uint64_t count;
    uint8_t  buffer[64];
} sha1_ctx_t;

#define SHA1_ROL(val, bits) (((val) << (bits)) | ((val) >> (32 - (bits))))

static void sha1_transform(uint32_t state[5], const uint8_t buffer[64])
{
    uint32_t w[80];
    for (int i = 0; i < 16; i++)
        w[i] = ((uint32_t)buffer[i*4]<<24)|((uint32_t)buffer[i*4+1]<<16)|((uint32_t)buffer[i*4+2]<<8)|buffer[i*4+3];
    for (int i = 16; i < 80; i++)
        w[i] = SHA1_ROL(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1);

    uint32_t a = state[0], b = state[1], c = state[2], d = state[3], e = state[4];
    for (int i = 0; i < 80; i++) {
        uint32_t f, k;
        if (i < 20)      { f = (b & c) | ((~b) & d); k = 0x5A827999; }
        else if (i < 40) { f = b ^ c ^ d;              k = 0x6ED9EBA1; }
        else if (i < 60) { f = (b & c) | (b & d) | (c & d); k = 0x8F1BBCDC; }
        else             { f = b ^ c ^ d;              k = 0xCA62C1D6; }
        uint32_t temp = SHA1_ROL(a, 5) + f + e + k + w[i];
        e = d; d = c; c = SHA1_ROL(b, 30); b = a; a = temp;
    }
    state[0] += a; state[1] += b; state[2] += c; state[3] += d; state[4] += e;
}

static void sha1_init(sha1_ctx_t *ctx)
{
    ctx->state[0] = 0x67452301;
    ctx->state[1] = 0xEFCDAB89;
    ctx->state[2] = 0x98BADCFE;
    ctx->state[3] = 0x10325476;
    ctx->state[4] = 0xC3D2E1F0;
    ctx->count = 0;
}

static void sha1_update(sha1_ctx_t *ctx, const uint8_t *data, size_t len)
{
    size_t i;
    for (i = 0; i < len; i++) {
        ctx->buffer[ctx->count % 64] = data[i];
        ctx->count++;
        if ((ctx->count % 64) == 0) sha1_transform(ctx->state, ctx->buffer);
    }
}

static void sha1_final(sha1_ctx_t *ctx, uint8_t digest[20])
{
    uint64_t bits = ctx->count * 8;
    uint8_t pad = 0x80;
    sha1_update(ctx, &pad, 1);
    while ((ctx->count % 64) != 56) { pad = 0; sha1_update(ctx, &pad, 1); }
    uint8_t len_buf[8];
    for (int i = 0; i < 8; i++) len_buf[i] = (uint8_t)(bits >> (56 - i * 8));
    sha1_update(ctx, len_buf, 8);
    for (int i = 0; i < 5; i++) {
        digest[i*4]   = (uint8_t)(ctx->state[i] >> 24);
        digest[i*4+1] = (uint8_t)(ctx->state[i] >> 16);
        digest[i*4+2] = (uint8_t)(ctx->state[i] >> 8);
        digest[i*4+3] = (uint8_t)(ctx->state[i]);
    }
}

/* ── WS handshake ── */
static int ws_perform_handshake(int sock_fd, char *path_out, size_t path_out_len, uint8_t *subproto_out)
{
    char buf[WS_RECV_BUF_SIZE];
    int ret;

    /* Read HTTP upgrade request with timeout */
    struct timeval tv;
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(sock_fd, &read_fds);
    tv.tv_sec  = 5;
    tv.tv_usec = 0;

    ret = select(sock_fd + 1, &read_fds, NULL, NULL, &tv);
    if (ret <= 0) return -1;

    ret = recv(sock_fd, buf, sizeof(buf) - 1, 0);
    if (ret <= 0) return -1;

    buf[ret] = '\0';
    char *key_start = http_header_find(buf, ret, "Sec-WebSocket-Key");
    if (!key_start) {
        ESP_LOGW(TAG, "WS handshake: no Sec-WebSocket-Key");
        return -1;
    }

    char ws_key[256];
    int ki = 0;
    while (key_start < buf + ret && *key_start != '\r' && *key_start != '\n' && ki < 255) {
        ws_key[ki++] = *key_start++;
    }
    ws_key[ki] = '\0';

    /* Extract path from request line */
    char *path_start = strchr(buf, ' ');
    if (path_start) {
        path_start++;
        char *path_end = strchr(path_start, ' ');
        if (path_end) {
            size_t plen = path_end - path_start;
            if (plen < path_out_len) {
                memcpy(path_out, path_start, plen);
                path_out[plen] = '\0';
            }
        }
    }

    /* Compute accept key: base64(sha1(key + GUID)) */
    char concat[512];
    int clen = snprintf(concat, sizeof(concat), "%s%s", ws_key, WS_GUID);

    uint8_t sha1_hash[20];
    sha1_ctx_t sha1_ctx;
    sha1_init(&sha1_ctx);
    sha1_update(&sha1_ctx, (const uint8_t *)concat, clen);
    sha1_final(&sha1_ctx, sha1_hash);

    char accept_key[64];
    base64_encode(sha1_hash, 20, accept_key, sizeof(accept_key));

    /* Send HTTP 101 response */
    char response[512];
    int resp_len = snprintf(response, sizeof(response),
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %s\r\n"
        "\r\n", accept_key);

    ret = send(sock_fd, response, resp_len, 0);
    if (ret < 0) return -1;

    *subproto_out = 0;  /* No subprotocol negotiation for now */
    return 0;
}

/* ── WS Client handshake ── */
static int ws_client_handshake(int sock_fd, const char *path, uint8_t *extra_headers, uint8_t header_len)
{
    /* Generate random key (simplified) */
    char key_buf[17];
    for (int i = 0; i < 16; i++) {
        key_buf[i] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"[(esp_random() % 64)];
    }
    key_buf[16] = '\0';

    /* Build HTTP upgrade request */
    char request[1024];
    int req_len = snprintf(request, sizeof(request),
        "GET %s HTTP/1.1\r\n"
        "Host: localhost\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Key: %s\r\n"
        "Sec-WebSocket-Version: 13\r\n",
        path, key_buf);

    if (extra_headers && header_len > 0 && req_len + header_len + 2 < (int)sizeof(request)) {
        memcpy(request + req_len, extra_headers, header_len);
        req_len += header_len;
    }

    request[req_len++] = '\r';
    request[req_len++] = '\n';

    if (send(sock_fd, request, req_len, 0) != req_len) return -1;

    /* Read response with timeout */
    struct timeval tv;
    fd_set read_fds;
    FD_ZERO(&read_fds);
    FD_SET(sock_fd, &read_fds);
    tv.tv_sec  = 5;
    tv.tv_usec = 0;

    if (select(sock_fd + 1, &read_fds, NULL, NULL, &tv) <= 0) return -1;

    char response[WS_RECV_BUF_SIZE];
    int ret = recv(sock_fd, response, sizeof(response) - 1, 0);
    if (ret <= 0) return -1;
    response[ret] = '\0';

    /* Check for 101 */
    if (strstr(response, "101") == NULL) return -1;

    return 0;
}

/* ── WS frame encode ── */
static int ws_encode_frame(uint8_t opcode, const uint8_t *data, uint16_t data_len,
                            uint8_t *out, size_t out_size)
{
    /* Server→Client: MASK=0 */
    size_t pos = 0;
    out[pos++] = 0x80 | opcode;  /* FIN=1 */

    if (data_len < 126) {
        out[pos++] = (uint8_t)data_len;
    } else {
        out[pos++] = 126;
        out[pos++] = (uint8_t)(data_len >> 8);
        out[pos++] = (uint8_t)(data_len & 0xFF);
    }

    if (pos + data_len > out_size) return -1;
    if (data_len > 0) memcpy(out + pos, data, data_len);
    return pos + data_len;
}

/* ── WS frame decode ── */
typedef struct {
    uint8_t  fin;
    uint8_t  opcode;
    uint8_t  mask;
    uint8_t  mask_key[4];
    uint64_t payload_len;
    uint16_t payload_offset;
    bool     complete;
} ws_frame_header_t;

static int ws_decode_frame_header(const uint8_t *data, size_t data_len, ws_frame_header_t *hdr)
{
    if (data_len < 2) return -1;

    hdr->fin    = (data[0] >> 7) & 0x01;
    hdr->opcode = data[0] & 0x0F;
    hdr->mask   = (data[1] >> 7) & 0x01;
    hdr->payload_len = data[1] & 0x7F;

    size_t pos = 2;

    if (hdr->payload_len == 126) {
        if (data_len < 4) return -1;
        hdr->payload_len = ((uint16_t)data[2] << 8) | data[3];
        pos = 4;
    } else if (hdr->payload_len == 127) {
        if (data_len < 10) return -1;
        hdr->payload_len = 0;
        for (int i = 0; i < 8; i++) {
            hdr->payload_len = (hdr->payload_len << 8) | data[2 + i];
        }
        pos = 10;
    }

    if (hdr->mask) {
        if (data_len < pos + 4) return -1;
        memcpy(hdr->mask_key, data + pos, 4);
        pos += 4;
    }

    hdr->payload_offset = pos;
    hdr->complete = true;
    return 0;
}

/* ── NET_LIST_CONNS provider ── */
static void ws_iterate_conns(net_conn_iter_cb cb, void *ctx)
{
    xSemaphoreTake(s_mutex, portMAX_DELAY);
    for (int i = 0; i < WS_MAX_SERVERS; i++) {
        if (s_servers[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_WS_SERVER;
            entry.handle        = s_servers[i].server_handle;
            entry.parent_handle = 0;
            entry.local_port    = s_servers[i].port;
            entry.remote_ip     = 0;
            cb(&entry, ctx);
        }
    }
    for (int i = 0; i < WS_MAX_CONNS; i++) {
        if (s_conns[i].active) {
            net_conn_entry_t entry;
            entry.conn_type     = NET_CONN_TYPE_WS_CONN;
            entry.handle        = s_conns[i].conn_handle;
            entry.parent_handle = s_conns[i].is_client_side ? 0 : s_conns[i].server_handle;
            entry.local_port    = 0;
            entry.remote_ip     = s_conns[i].client_ip;
            cb(&entry, ctx);
        }
    }
    xSemaphoreGive(s_mutex);
}

/* ── Find helpers ── */
static ws_server_t *find_server_slot(void)
{
    for (int i = 0; i < WS_MAX_SERVERS; i++) {
        if (!s_servers[i].active) return &s_servers[i];
    }
    return NULL;
}

static ws_server_t *find_server_by_handle(uint16_t handle)
{
    for (int i = 0; i < WS_MAX_SERVERS; i++) {
        if (s_servers[i].active && s_servers[i].server_handle == handle) return &s_servers[i];
    }
    return NULL;
}

static ws_conn_t *find_conn_slot(void)
{
    for (int i = 0; i < WS_MAX_CONNS; i++) {
        if (!s_conns[i].active) return &s_conns[i];
    }
    return NULL;
}

static ws_conn_t *find_conn_by_handle(uint16_t handle)
{
    for (int i = 0; i < WS_MAX_CONNS; i++) {
        if (s_conns[i].active && s_conns[i].conn_handle == handle) return &s_conns[i];
    }
    return NULL;
}

/* ── Send WS_DISCONNECT_EVENT ── */
static void send_ws_disconnect(ws_conn_t *conn, uint16_t close_code, uint8_t reason)
{
    uint8_t payload[7];
    payload[0] = (uint8_t)(conn->conn_handle >> 8);
    payload[1] = (uint8_t)(conn->conn_handle & 0xFF);
    payload[2] = (uint8_t)(close_code >> 8);
    payload[3] = (uint8_t)(close_code & 0xFF);
    payload[4] = reason;
    send_event(UBCP_CMD_WS_DISC_EVENT, payload, 5);
}

/* ========================================================================
 *  WS event task (select loop for server accepts + connection reads)
 * ======================================================================== */
static void ws_event_task(void *arg)
{
    struct timeval tv;
    fd_set read_fds;
    uint8_t raw_buf[WS_RECV_BUF_SIZE];

    while (s_task_running) {
        FD_ZERO(&read_fds);
        int max_fd = -1;

        xSemaphoreTake(s_mutex, portMAX_DELAY);
        for (int i = 0; i < WS_MAX_SERVERS; i++) {
            if (s_servers[i].active && s_servers[i].listen_fd >= 0) {
                FD_SET(s_servers[i].listen_fd, &read_fds);
                if (s_servers[i].listen_fd > max_fd) max_fd = s_servers[i].listen_fd;
            }
        }
        for (int i = 0; i < WS_MAX_CONNS; i++) {
            if (s_conns[i].active && s_conns[i].socket_fd >= 0) {
                FD_SET(s_conns[i].socket_fd, &read_fds);
                if (s_conns[i].socket_fd > max_fd) max_fd = s_conns[i].socket_fd;
            }
        }
        xSemaphoreGive(s_mutex);

        if (max_fd < 0) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        tv.tv_sec  = 0;
        tv.tv_usec = 100000;
        if (select(max_fd + 1, &read_fds, NULL, NULL, &tv) <= 0) continue;

        xSemaphoreTake(s_mutex, portMAX_DELAY);

        /* Accept new connections on servers */
        for (int i = 0; i < WS_MAX_SERVERS; i++) {
            if (!s_servers[i].active || s_servers[i].listen_fd < 0) continue;
            if (!FD_ISSET(s_servers[i].listen_fd, &read_fds)) continue;

            struct sockaddr_in client_addr;
            socklen_t addr_len = sizeof(client_addr);
            int client_fd = accept(s_servers[i].listen_fd, (struct sockaddr *)&client_addr, &addr_len);
            if (client_fd < 0) continue;

            /* Set non-blocking */
            int flags = fcntl(client_fd, F_GETFL, 0);
            if (flags >= 0) fcntl(client_fd, F_SETFL, flags | O_NONBLOCK);

            char path_buf[64] = "/";
            uint8_t subproto = 0;

            if (ws_perform_handshake(client_fd, path_buf, sizeof(path_buf), &subproto) != 0) {
                ESP_LOGW(TAG, "WS handshake failed, closing fd=%d", client_fd);
                close(client_fd);
                continue;
            }

            ws_conn_t *conn = find_conn_slot();
            if (!conn) {
                close(client_fd);
                continue;
            }

            conn->conn_handle      = alloc_conn_handle();
            conn->server_handle    = s_servers[i].server_handle;
            conn->socket_fd        = client_fd;
            conn->client_ip        = client_addr.sin_addr.s_addr;
            conn->client_port      = ntohs(client_addr.sin_port);
            conn->subproto_index   = subproto;
            conn->path_len         = strlen(path_buf);
            memcpy(conn->path, path_buf, conn->path_len + 1);
            conn->connect_time_sec = esp_timer_get_time() / 1000000;
            conn->is_client_side   = false;
            conn->active           = true;

            ESP_LOGI(TAG, "WS accepted: handle=0x%04X, ip=0x%08" PRIX32, conn->conn_handle, client_addr.sin_addr.s_addr);

            /* Send WS_ACCEPT event */
            uint16_t evt_len = 12 + conn->path_len;
            uint8_t *evt_payload = malloc(evt_len);
            if (evt_payload) {
                evt_payload[0]  = (uint8_t)(s_servers[i].server_handle >> 8);
                evt_payload[1]  = (uint8_t)(s_servers[i].server_handle & 0xFF);
                evt_payload[2]  = (uint8_t)(conn->conn_handle >> 8);
                evt_payload[3]  = (uint8_t)(conn->conn_handle & 0xFF);
                evt_payload[4]  = (uint8_t)(conn->client_ip >> 24);
                evt_payload[5]  = (uint8_t)(conn->client_ip >> 16);
                evt_payload[6]  = (uint8_t)(conn->client_ip >> 8);
                evt_payload[7]  = (uint8_t)(conn->client_ip & 0xFF);
                evt_payload[8]  = (uint8_t)(conn->client_port >> 8);
                evt_payload[9]  = (uint8_t)(conn->client_port & 0xFF);
                evt_payload[10] = subproto;
                evt_payload[11] = conn->path_len;
                if (conn->path_len > 0) memcpy(&evt_payload[12], conn->path, conn->path_len);

                xSemaphoreGive(s_mutex);
                send_event(UBCP_CMD_WS_ACCEPT, evt_payload, evt_len);
                free(evt_payload);
                xSemaphoreTake(s_mutex, portMAX_DELAY);
            }
        }

        /* Read data from connections */
        for (int i = 0; i < WS_MAX_CONNS; i++) {
            if (!s_conns[i].active || s_conns[i].socket_fd < 0) continue;
            if (!FD_ISSET(s_conns[i].socket_fd, &read_fds)) continue;

            int recv_len = recv(s_conns[i].socket_fd, raw_buf, sizeof(raw_buf), MSG_DONTWAIT);
            if (recv_len == 0) {
                send_ws_disconnect(&s_conns[i], 1006, 0x04);
                cleanup_conn(&s_conns[i]);
                continue;
            }
            if (recv_len < 0) {
                if (errno != EAGAIN && errno != EWOULDBLOCK) {
                    send_ws_disconnect(&s_conns[i], 1006, 0x04);
                    cleanup_conn(&s_conns[i]);
                }
                continue;
            }

            /* Decode WS frame */
            ws_frame_header_t hdr;
            if (ws_decode_frame_header(raw_buf, recv_len, &hdr) != 0 || !hdr.complete) continue;

            size_t frame_offset = hdr.payload_offset;
            size_t payload_len = (size_t)hdr.payload_len;

            if (frame_offset + payload_len > (size_t)recv_len) continue;

            /* Apply mask (client→server: MASK=1) */
            if (hdr.mask) {
                for (size_t j = 0; j < payload_len; j++) {
                    raw_buf[frame_offset + j] ^= hdr.mask_key[j % 4];
                }
            }

            if (hdr.opcode == 0x08) {
                /* Close frame */
                uint16_t close_code = 1000;
                if (payload_len >= 2) {
                    close_code = ((uint16_t)raw_buf[frame_offset] << 8) | raw_buf[frame_offset + 1];
                }
                send_ws_disconnect(&s_conns[i], close_code, 0x00);
                cleanup_conn(&s_conns[i]);
            } else if (hdr.opcode == 0x09) {
                /* Ping → send Pong */
                uint8_t pong_frame[128];
                int pong_len = ws_encode_frame(0x0A, raw_buf + frame_offset, payload_len,
                                                pong_frame, sizeof(pong_frame));
                if (pong_len > 0) send(s_conns[i].socket_fd, pong_frame, pong_len, MSG_DONTWAIT);
            } else if (hdr.opcode == 0x01 || hdr.opcode == 0x02) {
                /* Text or Binary → send WS_RECV event */
                uint16_t evt_len = 5 + payload_len;
                uint8_t *evt_payload = malloc(evt_len);
                if (evt_payload) {
                    evt_payload[0] = (uint8_t)(s_conns[i].conn_handle >> 8);
                    evt_payload[1] = (uint8_t)(s_conns[i].conn_handle & 0xFF);
                    evt_payload[2] = hdr.opcode;
                    evt_payload[3] = (uint8_t)(payload_len >> 8);
                    evt_payload[4] = (uint8_t)(payload_len & 0xFF);
                    if (payload_len > 0) memcpy(&evt_payload[5], raw_buf + frame_offset, payload_len);

                    xSemaphoreGive(s_mutex);
                    send_event(UBCP_CMD_WS_RECV, evt_payload, evt_len);
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
 *  WS_SERVER_OPEN (0x70)
 * ======================================================================== */
static void handle_server_open(const ubcp_frame_t *req)
{
    /* Port(2) + MaxConn(1) + PathLen(1) + Path(L) + SubProtoLen(1) + SubProto(S) */
    if (req->payload_len < 5) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t port    = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  maxconn = req->payload[2];
    uint8_t  path_len = req->payload[3];
    const char *path = (const char *)&req->payload[4];

    if (req->payload_len < (uint16_t)(4 + path_len + 1)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    ws_server_t *svr = find_server_slot();
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

    int opt = 1;
    setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    int flags = fcntl(sock, F_GETFL, 0);
    if (flags >= 0) fcntl(sock, F_SETFL, flags | O_NONBLOCK);

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
    if (path_len > 0 && path_len < 64) {
        memcpy(svr->path, path, path_len);
        svr->path[path_len] = '\0';
        svr->path_len = path_len;
    }
    svr->active = true;

    ESP_LOGI(TAG, "WS Server opened: handle=0x%04X, port=%u, path=%s", svr->server_handle, actual_port, svr->path);
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
 *  WS_SERVER_CLOSE (0x71)
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
    ws_server_t *svr = find_server_by_handle(handle);
    if (!svr) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    for (int i = 0; i < WS_MAX_CONNS; i++) {
        if (s_conns[i].active && !s_conns[i].is_client_side &&
            s_conns[i].server_handle == handle) {
            send_ws_disconnect(&s_conns[i], 1001, force ? 0x01 : 0x00);
            cleanup_conn(&s_conns[i]);
        }
    }

    close(svr->listen_fd);
    svr->active = false;
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  WS_CLIENT_CONNECT (0x72)
 * ======================================================================== */
static void handle_client_connect(const ubcp_frame_t *req)
{
    if (req->payload_len < 7) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint32_t ip   = ((uint32_t)req->payload[0] << 24) | ((uint32_t)req->payload[1] << 16) |
                    ((uint32_t)req->payload[2] << 8)  |  (uint32_t)req->payload[3];
    uint16_t port = ((uint16_t)req->payload[4] << 8) | req->payload[5];
    uint8_t  path_len = req->payload[6];

    if (path_len > 63 || req->payload_len < (uint16_t)(7 + path_len + 1)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    char path[64];
    memcpy(path, &req->payload[7], path_len);
    path[path_len] = '\0';

    uint8_t header_len = req->payload[7 + path_len];
    uint8_t *extra_headers = NULL;
    if (header_len > 0 && (req->payload_len >= (uint16_t)(8 + path_len + header_len))) {
        extra_headers = (uint8_t *)&req->payload[8 + path_len];
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    ws_conn_t *conn = find_conn_slot();
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
    addr.sin_addr.s_addr = ip;
    addr.sin_port        = htons(port);

    int cr = connect(sock, (struct sockaddr *)&addr, sizeof(addr));
    if (cr < 0 && errno != EINPROGRESS) {
        close(sock);
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_CONN_REFUSED);
        return;
    }

    /* Wait for connect */
    if (cr < 0) {
        fd_set wfds;
        struct timeval tv = { .tv_sec = 5, .tv_usec = 0 };
        FD_ZERO(&wfds);
        FD_SET(sock, &wfds);
        int sel = select(sock + 1, NULL, &wfds, NULL, &tv);
        if (sel <= 0) {
            close(sock);
            xSemaphoreGive(s_mutex);
            msg_bus_send_status_response(req, UBCP_ERR_NET_TIMEOUT);
            return;
        }
    }

    /* Perform WS handshake */
    if (ws_client_handshake(sock, path, extra_headers, header_len) != 0) {
        close(sock);
        xSemaphoreGive(s_mutex);
        uint8_t err_payload[1] = { UBCP_ERR_NET_WS_HANDSHAKE };
        ubcp_frame_t resp;
        ubcp_frame_make_response(req, &resp);
        resp.payload     = err_payload;
        resp.payload_len = 1;
        msg_bus_send_frame(&resp);
        return;
    }

    conn->conn_handle      = alloc_conn_handle();
    conn->server_handle    = 0;
    conn->socket_fd        = sock;
    conn->client_ip        = ip;
    conn->client_port      = port;
    conn->subproto_index   = 0;
    conn->path_len         = path_len;
    memcpy(conn->path, path, path_len + 1);
    conn->connect_time_sec = esp_timer_get_time() / 1000000;
    conn->is_client_side   = true;
    conn->active           = true;

    ESP_LOGI(TAG, "WS Client connected: handle=0x%04X, fd=%d", conn->conn_handle, sock);
    xSemaphoreGive(s_mutex);

    uint8_t payload[4];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = (uint8_t)(conn->conn_handle >> 8);
    payload[2] = (uint8_t)(conn->conn_handle & 0xFF);
    payload[3] = 1;  /* ConnResult: success */

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  WS_CLIENT_DISCONNECT (0x73)
 * ======================================================================== */
static void handle_client_disconnect(const ubcp_frame_t *req)
{
    if (req->payload_len < 4) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle     = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint16_t close_code = ((uint16_t)req->payload[2] << 8) | req->payload[3];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    ws_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    /* Send close frame */
    uint8_t close_payload[2] = {
        (uint8_t)(close_code >> 8), (uint8_t)(close_code & 0xFF)
    };
    uint8_t frame_buf[128];
    int frame_len = ws_encode_frame(0x08, close_payload, 2, frame_buf, sizeof(frame_buf));
    if (frame_len > 0) send(conn->socket_fd, frame_buf, frame_len, MSG_DONTWAIT);

    cleanup_conn(conn);
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  WS_SEND (0x74)
 * ======================================================================== */
static void handle_send(const ubcp_frame_t *req)
{
    if (req->payload_len < 5) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle    = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  msg_type  = req->payload[2];
    uint16_t data_len  = ((uint16_t)req->payload[3] << 8) | req->payload[4];

    if (req->payload_len < (uint16_t)(5 + data_len)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    ws_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    /* Encode WS frame */
    uint8_t frame_buf[UBCP_MAX_PAYLOAD_LEN];
    int frame_len = ws_encode_frame(msg_type, &req->payload[5], data_len,
                                     frame_buf, sizeof(frame_buf));

    int sent = 0;
    if (frame_len > 0) {
        sent = send(conn->socket_fd, frame_buf, frame_len, MSG_DONTWAIT);
    }
    xSemaphoreGive(s_mutex);

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
 *  WS_LIST_CLIENTS (0x78)
 * ======================================================================== */
static void handle_list_clients(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t server_handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    int count = 0;
    uint8_t entries[WS_MAX_CONNS * 12];
    uint16_t entry_offset = 0;

    for (int i = 0; i < WS_MAX_CONNS; i++) {
        if (s_conns[i].active && !s_conns[i].is_client_side &&
            s_conns[i].server_handle == server_handle) {
            ws_conn_t *c = &s_conns[i];
            uint32_t now = esp_timer_get_time() / 1000000;
            uint16_t up_time = (uint16_t)(now - c->connect_time_sec);

            entries[entry_offset + 0]  = (uint8_t)(c->conn_handle >> 8);
            entries[entry_offset + 1]  = (uint8_t)(c->conn_handle & 0xFF);
            entries[entry_offset + 2]  = (uint8_t)(c->client_ip >> 24);
            entries[entry_offset + 3]  = (uint8_t)(c->client_ip >> 16);
            entries[entry_offset + 4]  = (uint8_t)(c->client_ip >> 8);
            entries[entry_offset + 5]  = (uint8_t)(c->client_ip & 0xFF);
            entries[entry_offset + 6]  = (uint8_t)(c->client_port >> 8);
            entries[entry_offset + 7]  = (uint8_t)(c->client_port & 0xFF);
            entries[entry_offset + 8]  = c->subproto_index;
            entries[entry_offset + 9]  = c->path_len;
            entries[entry_offset + 10] = (uint8_t)(up_time >> 8);
            entries[entry_offset + 11] = (uint8_t)(up_time & 0xFF);
            entry_offset += 12;
            count++;
        }
    }
    xSemaphoreGive(s_mutex);

    uint16_t plen = 2 + count * 12;
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
 *  WS_KICK_CLIENT (0x79)
 * ======================================================================== */
static void handle_kick_client(const ubcp_frame_t *req)
{
    if (req->payload_len < 3) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint16_t handle = ((uint16_t)req->payload[0] << 8) | req->payload[1];
    uint8_t  force  = req->payload[2];

    xSemaphoreTake(s_mutex, portMAX_DELAY);
    ws_conn_t *conn = find_conn_by_handle(handle);
    if (!conn) {
        xSemaphoreGive(s_mutex);
        msg_bus_send_status_response(req, UBCP_ERR_NET_HANDLE_INVALID);
        return;
    }

    if (!force) {
        /* Send close frame */
        uint8_t close_payload[2] = { 0x03, 0xE8 }; /* 1000 = normal */
        uint8_t frame_buf[128];
        int frame_len = ws_encode_frame(0x08, close_payload, 2, frame_buf, sizeof(frame_buf));
        if (frame_len > 0) send(conn->socket_fd, frame_buf, frame_len, MSG_DONTWAIT);
    }

    send_ws_disconnect(conn, 1000, force ? 0x01 : 0x00);
    cleanup_conn(conn);
    xSemaphoreGive(s_mutex);

    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

/* ========================================================================
 *  Module init and dispatch
 * ======================================================================== */
static esp_err_t ws_init(void)
{
    memset(s_servers, 0, sizeof(s_servers));
    memset(s_conns, 0, sizeof(s_conns));

    s_mutex = xSemaphoreCreateMutex();
    if (!s_mutex) return ESP_ERR_NO_MEM;

    s_task_running = true;
    BaseType_t ret = xTaskCreate(ws_event_task, "ws_event", 5120, NULL, 7, &s_ws_task);
    if (ret != pdPASS) {
        ESP_LOGE(TAG, "Failed to create WS event task");
        return ESP_ERR_NO_MEM;
    }

    mod_network_register_conn_provider("WebSocket", ws_iterate_conns);

    ESP_LOGI(TAG, "WebSocket 模块初始化完成");
    return ESP_OK;
}

static void ws_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_WS_SERVER_OPEN:   handle_server_open(frame);     break;
    case UBCP_CMD_WS_SERVER_CLOSE:  handle_server_close(frame);    break;
    case UBCP_CMD_WS_CLIENT_CONN:   handle_client_connect(frame);  break;
    case UBCP_CMD_WS_CLIENT_DISC:   handle_client_disconnect(frame); break;
    case UBCP_CMD_WS_SEND:          handle_send(frame);            break;
    case UBCP_CMD_WS_LIST_CLIENTS:  handle_list_clients(frame);    break;
    case UBCP_CMD_WS_KICK_CLIENT:   handle_kick_client(frame);     break;
    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static const hex_module_t s_ws_module = {
    .name            = "WebSocket",
    .cmd_range_start = UBCP_CMD_RANGE_WS_START,
    .cmd_range_end   = UBCP_CMD_RANGE_WS_END,
    .init            = ws_init,
    .handle_cmd      = ws_handle_cmd,
    .stop            = NULL,
};

const hex_module_t *mod_ws_get(void)
{
    return &s_ws_module;
}
