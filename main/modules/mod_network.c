#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_wifi.h"
#include "esp_wifi_default.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "esp_timer.h"
#include "nvs.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"
#include "modules/mod_network.h"
#include "core/device_profile.h"
#include "core/msg_bus.h"
#include "transport/mcp_transport.h"
#include "core/seq_num.h"
#include "utils/hex_log.h"

/* Only network_task owns the driver, credentials, timers and persistent record.
 * ESP event callbacks copy events; the message bus only copies commands. */
static const char *TAG = "mod_network";
#define MAX_CONN_PROVIDERS 4
#define WIFI_RECORD_VERSION 1
#define DHCP_TIMEOUT_US (30LL * 1000000)
typedef struct {
    uint8_t version, auth, ssid_len, key_len;
    uint8_t ssid[32], key[63];
} wifi_record_t;
typedef struct {
    ubcp_frame_t req;
    uint8_t data[254];
    uint32_t generation;
} command_t;
typedef struct {
    int32_t id;
    bool ip_event;
    uint16_t reason;
    esp_netif_ip_info_t ip;
} driver_event_t;
static QueueHandle_t s_commands, s_events, s_dns_commands;
static TaskHandle_t s_worker;
void mod_network_start(void) { if (s_worker) xTaskNotifyGive(s_worker); }
static volatile bool s_ready, s_event_overflow;
static volatile uint32_t s_generation = 1;
static esp_netif_t *s_netif;
static bool s_driver_ready, s_started, s_stopping, s_active, s_save;
static uint8_t s_state, s_reason, s_link, s_channel, s_retry;
static uint32_t s_ip, s_mask, s_gw, s_dns;
static int64_t s_deadline;
static wifi_record_t s_target;
static esp_event_handler_instance_t s_wifi_handler, s_ip_handler;
static struct {
    const char *name;
    void (*iterate)(net_conn_iter_cb cb, void *ctx);
} s_conn_providers[MAX_CONN_PROVIDERS];
static int s_conn_provider_count;
static net_conn_close_all_cb s_close_providers[MAX_CONN_PROVIDERS];
static int s_close_provider_count;
bool mod_network_is_ready(void) { return s_ready; }
uint32_t mod_network_generation(void) { return s_generation; }
void mod_network_register_conn_provider(const char *name, void (*iterate)(net_conn_iter_cb, void *))
{
    if (s_conn_provider_count < MAX_CONN_PROVIDERS) {
        s_conn_providers[s_conn_provider_count].name = name;
        s_conn_providers[s_conn_provider_count++].iterate = iterate;
    }
}
void mod_network_register_close_provider(const char *name, net_conn_close_all_cb cb)
{
    (void)name;
    if (s_close_provider_count < MAX_CONN_PROVIDERS) s_close_providers[s_close_provider_count++] = cb;
}
static void close_sockets(void)
{
    for (int i = 0; i < s_close_provider_count; ++i) if (s_close_providers[i]) s_close_providers[i]();
}
static void response(const ubcp_frame_t *req, uint8_t *data, size_t len)
{
    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload = data;
    resp.payload_len = len;
    msg_bus_send_frame(&resp);
}
static void put_ip(uint8_t *p, uint32_t ip)
{
    p[0] = ip >> 24; p[1] = ip >> 16; p[2] = ip >> 8; p[3] = ip;
}
static uint32_t get_ip(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
}
static void send_link_event(uint8_t type, uint32_t ip)
{
    uint8_t payload[6] = {0, type};
    put_ip(payload + 2, ip);
    ubcp_frame_t evt = {
        .version = UBCP_VERSION, .flags = UBCP_FLAG_DIR | UBCP_FLAG_EVT | UBCP_FLAG_TS,
        .seq_num = seq_num_next(), .cmd_code = UBCP_CMD_NET_LINK_EVENT,
        .has_timestamp = true, .timestamp = (uint32_t)esp_timer_get_time(),
        .payload = payload, .payload_len = sizeof(payload),
    };
    msg_bus_send_frame(&evt);
}
static void invalidate_ip(void)
{
    bool had_ip = s_ready;
    s_ready = false; mcp_transport_set_network_ready(false);
    ++s_generation;
    s_ip = s_mask = s_gw = s_dns = 0;
    if (had_ip) {
        close_sockets();
        send_link_event(3, 0);
    }
}
static void link_down(void)
{
    invalidate_ip();
    if (s_link) send_link_event(0, 0);
    s_link = s_channel = 0;
}
static void driver_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    (void)arg;
    driver_event_t evt = {.id = id, .ip_event = base == IP_EVENT};
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *got = data;
        if (got->esp_netif != s_netif) return;
        evt.ip = got->ip_info;
    }
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) evt.reason = ((wifi_event_sta_disconnected_t *)data)->reason;
    if (xQueueSend(s_events, &evt, 0) != pdTRUE) s_event_overflow = true;
}
static bool valid_record(const wifi_record_t *r)
{
    if (r->version != WIFI_RECORD_VERSION || r->ssid_len == 0 || r->ssid_len > 32 || r->auth > 1) return false;
    if (r->auth == 0) return r->key_len == 0;
    if (r->key_len < 8 || r->key_len > 63) return false;
    for (int i = 0; i < r->key_len; ++i) if (r->key[i] < 32 || r->key[i] > 126) return false;
    return true;
}
static esp_err_t record_write(bool erase)
{
    nvs_handle_t h;
    esp_err_t err = nvs_open("hex_wifi", NVS_READWRITE, &h);
    if (err != ESP_OK) return err;
    err = erase ? nvs_erase_key(h, "sta") : nvs_set_blob(h, "sta", &s_target, sizeof(s_target));
    if (erase && err == ESP_ERR_NVS_NOT_FOUND) err = ESP_OK;
    if (err == ESP_OK) err = nvs_commit(h);
    nvs_close(h);
    return err;
}
static bool read_saved_record(wifi_record_t *record)
{
    nvs_handle_t h;
    size_t len = sizeof(*record);
    if (nvs_open("hex_wifi", NVS_READONLY, &h) != ESP_OK) return false;
    esp_err_t err = nvs_get_blob(h, "sta", record, &len);
    nvs_close(h);
    return err == ESP_OK && len == sizeof(*record) && valid_record(record);
}

bool mod_network_has_saved_credentials(void)
{
    wifi_record_t record = {0};
    return read_saved_record(&record);
}

static void record_load(void)
{
    wifi_record_t r = {0};
    if (read_saved_record(&r)) {
        s_target = r; s_active = true; s_state = 1;
    }
    memset(&r, 0, sizeof(r));
}
static void schedule_retry(uint8_t reason)
{
    static const unsigned delays[] = {1, 2, 4, 8, 16, 30};
    s_reason = reason;
    if (!s_active || reason == 2) { s_state = 5; s_deadline = 0; return; }
    s_state = 4;
    s_deadline = esp_timer_get_time() + (int64_t)delays[s_retry] * 1000000;
    if (s_retry < 5) ++s_retry;
}
static void connect_attempt(void)
{
    if (!s_active || !s_started || s_stopping) return;
    s_state = 1;
    s_deadline = esp_timer_get_time() + DHCP_TIMEOUT_US;
    if (esp_wifi_connect() != ESP_OK) schedule_retry(5);
}
static void start_target(void)
{
    if (!s_active || !s_driver_ready || s_stopping) return;
    wifi_config_t cfg = {0};
    memcpy(cfg.sta.ssid, s_target.ssid, s_target.ssid_len);
    memcpy(cfg.sta.password, s_target.key, s_target.key_len);
    cfg.sta.threshold.authmode = s_target.auth ? WIFI_AUTH_WPA2_PSK : WIFI_AUTH_OPEN;
    esp_err_t err = esp_wifi_set_config(WIFI_IF_STA, &cfg);
    memset(&cfg, 0, sizeof(cfg));
    if (err == ESP_OK) {
        s_started = true;
        err = esp_wifi_start();
        if (err != ESP_OK) s_started = false;
    }
    if (err != ESP_OK) { s_reason = 5; s_state = 5; s_deadline = 0; }
}
/* STA_STOP is a fence: events already queued by the old driver session are
 * ignored until this event, and the next session starts only afterwards. */
static void stop_session(void)
{
    s_deadline = 0;
    link_down();
    if (s_started && !s_stopping) {
        s_stopping = true;
        if (esp_wifi_stop() != ESP_OK) {
            s_stopping = false; s_started = false; s_driver_ready = false; s_active = false; s_reason = 5; s_state = 5;
        }
    }
}
static void got_ip(const esp_netif_ip_info_t *ip)
{
    if (!s_active || !s_link || !ip->ip.addr || (s_state != 2 && s_state != 3)) return;
    uint32_t new_ip = ntohl(ip->ip.addr);
    if (s_ready && s_ip == new_ip && s_mask == ntohl(ip->netmask.addr) && s_gw == ntohl(ip->gw.addr)) return;
    bool changed = s_ip != 0;
    if (s_ready) { s_ready = false; mcp_transport_set_network_ready(false); ++s_generation; close_sockets(); }
    s_ip = new_ip; s_mask = ntohl(ip->netmask.addr); s_gw = ntohl(ip->gw.addr);
    esp_netif_dns_info_t dns = {0};
    if (esp_netif_get_dns_info(s_netif, ESP_NETIF_DNS_MAIN, &dns) == ESP_OK) s_dns = ntohl(dns.ip.u_addr.ip4.addr);
    s_ready = true; mcp_transport_set_network_ready(true); s_state = 3; s_reason = 0; s_retry = 0; s_deadline = 0;
    if (s_save) {
        s_save = false;
        if (record_write(false) != ESP_OK) s_reason = 6;
    }
    send_link_event(changed ? 4 : 2, s_ip);
}
static void process_event(const driver_event_t *evt)
{
    if (s_stopping) {
        if (!evt->ip_event && evt->id == WIFI_EVENT_STA_STOP) {
            s_started = s_stopping = false;
            if (s_active) start_target();
            else { wifi_config_t empty = {0}; esp_wifi_set_config(WIFI_IF_STA, &empty); }
        }
        return;
    }
    if (!evt->ip_event && evt->id == WIFI_EVENT_STA_START) {
        s_started = true;
        if (s_active) connect_attempt(); else stop_session();
        return;
    }
    if (!s_active || !s_started) return;
    if (evt->ip_event) {
        if (evt->id == IP_EVENT_STA_GOT_IP) {
            /* Re-read actual state to reject an obsolete GOT_IP notification. */
            esp_netif_ip_info_t actual;
            wifi_ap_record_t ap;
            if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK && esp_netif_get_ip_info(s_netif, &actual) == ESP_OK && actual.ip.addr == evt->ip.ip.addr) got_ip(&actual);
        } else if (evt->id == IP_EVENT_STA_LOST_IP && s_ready) {
            esp_netif_ip_info_t actual;
            if (esp_netif_get_ip_info(s_netif, &actual) == ESP_OK && actual.ip.addr) return;
            invalidate_ip(); schedule_retry(4); esp_wifi_disconnect();
        }
    } else if (evt->id == WIFI_EVENT_STA_CONNECTED) {
        if (s_link || s_state != 1) return;
        wifi_ap_record_t ap;
        if (esp_wifi_sta_get_ap_info(&ap) != ESP_OK) return;
        s_link = 1; s_channel = ap.primary; s_state = 2;
        s_deadline = esp_timer_get_time() + DHCP_TIMEOUT_US;
        send_link_event(1, 0);
        esp_netif_ip_info_t ip;
        esp_netif_dhcp_status_t dhcp;
        if (esp_netif_dhcpc_get_status(s_netif, &dhcp) == ESP_OK && dhcp == ESP_NETIF_DHCP_STOPPED &&
            esp_netif_get_ip_info(s_netif, &ip) == ESP_OK) got_ip(&ip);
    } else if (evt->id == WIFI_EVENT_STA_DISCONNECTED) {
        if (!s_link && (s_state == 4 || s_state == 5)) return;
        link_down();
        uint8_t reason = evt->reason == WIFI_REASON_NO_AP_FOUND ? 1 :
            (evt->reason == WIFI_REASON_AUTH_FAIL || evt->reason == WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT ||
             evt->reason == WIFI_REASON_HANDSHAKE_TIMEOUT || evt->reason == WIFI_REASON_AUTH_EXPIRE ||
             evt->reason == WIFI_REASON_NO_AP_FOUND_W_COMPATIBLE_SECURITY ||
             evt->reason == WIFI_REASON_NO_AP_FOUND_IN_AUTHMODE_THRESHOLD ||
             evt->reason == WIFI_REASON_802_1X_AUTH_FAILED || evt->reason == WIFI_REASON_CIPHER_SUITE_REJECTED ? 2 : 3);
        /* Keep DHCP timeout classification across the disconnect we requested. */
        if (s_state == 4 && s_reason == 4) return;
        schedule_retry(reason);
    }
}
static void handle_wifi(const ubcp_frame_t *req)
{
    const uint8_t *p = req->payload;
    if (req->cmd_code == UBCP_CMD_WIFI_JOIN) {
        wifi_record_t target = { .version = WIFI_RECORD_VERSION };
        if (req->payload_len < 5 || p[0] != 0 || p[1] > 1 || p[2] > 1 ||
            req->payload_len != (unsigned)(5 + p[3] + p[4]) || p[3] > 32 || p[4] > 63) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM); return;
        }
        target.auth = p[2]; target.ssid_len = p[3]; target.key_len = p[4];
        memcpy(target.ssid, p + 5, target.ssid_len);
        memcpy(target.key, p + 5 + target.ssid_len, target.key_len);
        if (!valid_record(&target)) { memset(&target, 0, sizeof(target)); msg_bus_send_status_response(req, UBCP_ERR_PARAM); return; }
        if (!s_driver_ready) { memset(&target, 0, sizeof(target)); msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN); return; }
        bool same = memcmp(&target, &s_target, sizeof(target)) == 0 && s_save == (bool)p[1];
        if (s_active && (s_state == 1 || s_state == 2 || s_state == 4)) {
            memset(&target, 0, sizeof(target));
            msg_bus_send_status_response(req, same ? UBCP_ERR_SUCCESS : UBCP_ERR_BUSY); return;
        }
        s_active = false; stop_session();
        if (!s_driver_ready) {
            memset(&target, 0, sizeof(target));
            msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN); return;
        }
        s_target = target; s_save = p[1]; s_active = true; s_state = 1; s_reason = s_retry = 0;
        memset(&target, 0, sizeof(target));
        if (!s_stopping) start_target();
        msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
        return;
    }
    if (req->payload_len != 1 || p[0] != 0) { msg_bus_send_status_response(req, UBCP_ERR_PARAM); return; }
    if (req->cmd_code == UBCP_CMD_WIFI_STATUS) {
        uint8_t data[38] = {0, s_state, s_reason, s_link ? s_channel : 0, 0x80, s_state ? s_target.ssid_len : 0};
        wifi_ap_record_t ap;
        if (s_link && esp_wifi_sta_get_ap_info(&ap) == ESP_OK) data[4] = (uint8_t)ap.rssi;
        memcpy(data + 6, s_target.ssid, data[5]);
        response(req, data, 6 + data[5]);
    } else {
        s_active = s_save = false; stop_session();
        memset(&s_target, 0, sizeof(s_target)); s_state = s_reason = s_retry = 0;
        if (s_driver_ready && !s_started && !s_stopping) {
            wifi_config_t empty = {0}; esp_wifi_set_config(WIFI_IF_STA, &empty);
        }
        esp_err_t err = ESP_OK;
        if (req->cmd_code == UBCP_CMD_WIFI_FORGET) err = record_write(true);
        if (err != ESP_OK) s_reason = 6;
        msg_bus_send_status_response(req, err == ESP_OK ? UBCP_ERR_SUCCESS : UBCP_ERR_UNKNOWN);
    }
}
static void handle_net_status(const ubcp_frame_t *req)
{
    uint8_t data[19] = {0, 1, 0, s_link, s_ready ? 1 : s_link ? 2 : 0};
    put_ip(data + 5, s_ip); put_ip(data + 9, s_mask);
    esp_read_mac(data + 13, ESP_MAC_WIFI_STA);
    response(req, data, sizeof(data));
}
static void handle_net_config(const ubcp_frame_t *req)
{
    const uint8_t *p = req->payload;
    if (req->payload_len < 2 || p[0] != 0 || p[1] > 1 || req->payload_len != (p[1] ? 22 : 2)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM); return;
    }
    if (!s_netif || !s_driver_ready) { msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN); return; }
    bool replacing = p[1] && s_ready;
    if (replacing) {
        s_ready = false; mcp_transport_set_network_ready(false); ++s_generation; close_sockets();
    } else invalidate_ip();
    esp_err_t err = esp_netif_dhcpc_stop(s_netif);
    if (err == ESP_ERR_ESP_NETIF_DHCP_ALREADY_STOPPED) err = ESP_OK;
    esp_netif_ip_info_t ip = {0};
    if (err == ESP_OK && p[1] == 0) {
        err = esp_netif_set_ip_info(s_netif, &ip);
        if (err == ESP_OK) err = esp_netif_dhcpc_start(s_netif);
        if (err == ESP_ERR_ESP_NETIF_DHCP_ALREADY_STARTED) err = ESP_OK;
    } else if (err == ESP_OK) {
        ip.ip.addr = htonl(get_ip(p + 2)); ip.netmask.addr = htonl(get_ip(p + 6)); ip.gw.addr = htonl(get_ip(p + 10));
        err = esp_netif_set_ip_info(s_netif, &ip);
        esp_netif_dns_info_t dns = {0};
        dns.ip.type = ESP_IPADDR_TYPE_V4; dns.ip.u_addr.ip4.addr = htonl(get_ip(p + 14));
        if (err == ESP_OK) err = esp_netif_set_dns_info(s_netif, ESP_NETIF_DNS_MAIN, &dns);
        if (err == ESP_OK) got_ip(&ip);
    }
    if (err != ESP_OK) {
        if (replacing) { s_ip = s_mask = s_gw = s_dns = 0; send_link_event(3, 0); }
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN); return;
    }
    if (s_link && !s_ready) { s_state = 2; s_deadline = esp_timer_get_time() + DHCP_TIMEOUT_US; }
    uint8_t data[17] = {0};
    put_ip(data + 1, s_ip); put_ip(data + 5, s_mask); put_ip(data + 9, s_gw); put_ip(data + 13, s_dns);
    response(req, data, sizeof(data));
}
/* Blocking resolver is isolated from the UART dispatcher and STA worker. No
 * callback context is freed while lwIP may still refer to it. */
static void dns_task(void *arg)
{
    (void)arg;
    command_t cmd;
    while (xQueueReceive(s_dns_commands, &cmd, portMAX_DELAY) == pdTRUE) {
        cmd.req.payload = cmd.data;
        uint8_t result[6] = {UBCP_ERR_NET_NO_IP, 0};
        if (s_ready && cmd.generation == s_generation && mcp_transport_session_is_current(cmd.req.session_id)) {
            char host[254]; memcpy(host, cmd.data + 1, cmd.data[0]); host[cmd.data[0]] = 0;
            struct addrinfo hints = {.ai_family = AF_INET, .ai_socktype = SOCK_STREAM}, *res = NULL;
            int err = getaddrinfo(host, NULL, &hints, &res);
            if (s_ready && cmd.generation == s_generation && mcp_transport_session_is_current(cmd.req.session_id)) {
                result[0] = UBCP_ERR_NET_DNS_FAIL;
                if (err == 0 && res) {
                    result[0] = 0; result[1] = 1;
                    put_ip(result + 2, ntohl(((struct sockaddr_in *)res->ai_addr)->sin_addr.s_addr));
                }
            }
            if (res) freeaddrinfo(res);
        }
        response(&cmd.req, result, result[0] ? 2 : sizeof(result));
        memset(&cmd, 0, sizeof(cmd));
    }
}
static void handle_net_dns(const ubcp_frame_t *req)
{
    if (req->payload_len < 2 || req->payload[0] == 0 || req->payload[0] > 253 ||
        req->payload_len != req->payload[0] + 1 || memchr(req->payload + 1, 0, req->payload[0])) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM); return;
    }
    if (!s_ready) { uint8_t err[2] = {UBCP_ERR_NET_NO_IP, 0}; response(req, err, sizeof(err)); return; }
    command_t cmd = {.req = *req, .generation = s_generation};
    memcpy(cmd.data, req->payload, req->payload_len);
    if (!s_dns_commands || xQueueSend(s_dns_commands, &cmd, 0) != pdTRUE) msg_bus_send_status_response(req, UBCP_ERR_BUSY);
}
/* ========================================================================
 *  NET_LIST_CONNS (0x44)
 * ======================================================================== */
typedef struct {
    uint8_t *buf;
    uint16_t offset;
    uint16_t capacity;
    uint8_t  count;
} list_conns_ctx_t;

static void list_conns_collect_cb(const net_conn_entry_t *entry, void *ctx)
{
    list_conns_ctx_t *lc = (list_conns_ctx_t *)ctx;
    if (lc->offset + 11 > lc->capacity) return;

    lc->buf[lc->offset + 0] = entry->conn_type;
    lc->buf[lc->offset + 1] = (uint8_t)(entry->handle >> 8);
    lc->buf[lc->offset + 2] = (uint8_t)(entry->handle & 0xFF);
    lc->buf[lc->offset + 3] = (uint8_t)(entry->parent_handle >> 8);
    lc->buf[lc->offset + 4] = (uint8_t)(entry->parent_handle & 0xFF);
    lc->buf[lc->offset + 5] = (uint8_t)(entry->local_port >> 8);
    lc->buf[lc->offset + 6] = (uint8_t)(entry->local_port & 0xFF);
        lc->buf[lc->offset + 7] = (uint8_t)(entry->remote_ip >> 24);
        lc->buf[lc->offset + 8] = (uint8_t)(entry->remote_ip >> 16);
        lc->buf[lc->offset + 9] = (uint8_t)(entry->remote_ip >> 8);
        lc->buf[lc->offset + 10]= (uint8_t)(entry->remote_ip & 0xFF);
    lc->offset += 11;
    lc->count++;
}

static void handle_net_list_conns(const ubcp_frame_t *req)
{
    /* First pass: count total entries */
    uint16_t max_entries = 60;
    uint16_t buf_size = 2 + max_entries * 11;
    uint8_t *payload = malloc(buf_size);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    list_conns_ctx_t lc;
    lc.buf      = payload + 2;
    lc.offset   = 0;
    lc.capacity = max_entries * 11;
    lc.count    = 0;

    for (int i = 0; i < s_conn_provider_count; i++) {
        if (s_conn_providers[i].iterate) {
            s_conn_providers[i].iterate(list_conns_collect_cb, &lc);
        }
    }

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = lc.count;

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = 2 + lc.offset;
    msg_bus_send_frame(&resp);

    free(payload);
}

/* ========================================================================
 *  NET_CLOSE_ALL (0x45)
 * ======================================================================== */
static void handle_net_close_all(const ubcp_frame_t *req)
{
    HEX_LOGI(TAG, "NET_CLOSE_ALL: 关闭 %d 个连接提供者上报的所有连接", s_close_provider_count);
    for (int i = 0; i < s_close_provider_count; i++) {
        if (s_close_providers[i]) {
            s_close_providers[i]();
        }
    }
    msg_bus_send_status_response(req, UBCP_ERR_SUCCESS);
}

static esp_err_t driver_init(void)
{
    esp_err_t err = esp_netif_init();
    if (err != ESP_OK) return err;
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;
    esp_netif_config_t netif_cfg = ESP_NETIF_DEFAULT_WIFI_STA();
    s_netif = esp_netif_new(&netif_cfg);
    if (!s_netif) return ESP_ERR_NO_MEM;
    err = esp_netif_attach_wifi_station(s_netif);
    if (err != ESP_OK) return err;
    err = esp_wifi_set_default_wifi_sta_handlers();
    if (err != ESP_OK) return err;
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    cfg.nvs_enable = 0;
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) return err;
    err = esp_wifi_set_storage(WIFI_STORAGE_RAM);
    if (err == ESP_OK) err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err == ESP_OK) err = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, driver_event, NULL, &s_wifi_handler);
    if (err == ESP_OK) err = esp_event_handler_instance_register(IP_EVENT, ESP_EVENT_ANY_ID, driver_event, NULL, &s_ip_handler);
    return err;
}
static void network_task(void *arg)
{
    (void)arg;
    ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    if (driver_init() != ESP_OK) { profile_driver_failed(); s_state = 5; s_reason = 5; }
    else {
        s_driver_ready = true;
        record_load();
        start_target();
    }
    command_t *cmd;
    driver_event_t evt;
    while (1) {
        if (s_event_overflow) {
            /* Dropped events cannot authorize a connection or persistence. */
            s_event_overflow = false; s_active = s_save = false;
            stop_session(); s_state = 5; s_reason = 5;
        }
        if (xQueueReceive(s_commands, &cmd, pdMS_TO_TICKS(20)) == pdTRUE) {
            if (cmd->req.cmd_code != 0xff && !mcp_transport_session_is_current(cmd->req.session_id)) {
                memset(cmd, 0, sizeof(*cmd)); free(cmd); continue;
            }
            cmd->req.payload = cmd->data;
            switch (cmd->req.cmd_code) {
            case UBCP_CMD_NET_CONFIG: handle_net_config(&cmd->req); break;
            case UBCP_CMD_NET_STATUS: handle_net_status(&cmd->req); break;
            case UBCP_CMD_NET_DNS: handle_net_dns(&cmd->req); break;
            case UBCP_CMD_NET_LIST_CONNS: handle_net_list_conns(&cmd->req); break;
            case UBCP_CMD_NET_CLOSE_ALL: handle_net_close_all(&cmd->req); break;
            case UBCP_CMD_WIFI_JOIN:
            case UBCP_CMD_WIFI_STATUS:
            case UBCP_CMD_WIFI_LEAVE:
            case UBCP_CMD_WIFI_FORGET: handle_wifi(&cmd->req); break;
            case 0xff: s_active = s_save = false; stop_session(); break;
            default: msg_bus_send_status_response(&cmd->req, UBCP_ERR_NOT_SUPPORT); break;
            }
            memset(cmd, 0, sizeof(*cmd)); free(cmd);
        }
        /* Bound each batch so repeated callbacks cannot starve commands. */
        for (unsigned n = 0; n < 32 && xQueueReceive(s_events, &evt, 0) == pdTRUE; ++n) process_event(&evt);
        if (s_deadline && esp_timer_get_time() >= s_deadline) {
            s_deadline = 0;
            if (s_state == 4) connect_attempt();
            else if (s_state == 1 || s_state == 2) {
                link_down(); schedule_retry(s_state == 2 ? 4 : 1);
                esp_wifi_disconnect();
            }
        }
    }
}
static esp_err_t network_init(void)
{
    s_commands = xQueueCreate(8, sizeof(command_t *));
    s_events = xQueueCreate(32, sizeof(driver_event_t));
    s_dns_commands = xQueueCreate(4, sizeof(command_t));
    if (!s_commands || !s_events || !s_dns_commands) {
        if (s_commands) vQueueDelete(s_commands);
        if (s_events) vQueueDelete(s_events);
        if (s_dns_commands) vQueueDelete(s_dns_commands);
        s_commands = s_events = s_dns_commands = NULL;
        s_state = 5; s_reason = 5;
        profile_driver_failed();
        return ESP_OK; /* network failure never prevents CAN/UART boot */
    }
    if (xTaskCreate(dns_task, "net_dns", 4096, NULL, 1, NULL) != pdPASS) {
        vQueueDelete(s_dns_commands); s_dns_commands = NULL;
    }
    if (xTaskCreate(network_task, "net_sta", 6144, NULL, 2, &s_worker) != pdPASS) {
        vQueueDelete(s_commands); s_commands = NULL;
        profile_driver_failed();
        s_state = 5; s_reason = 5;
    }
    return ESP_OK;
}
static void network_handle_cmd(const ubcp_frame_t *req)
{
    if (!s_commands) {
        /* Status remains inspectable even after task/allocation failure. */
        if (req->cmd_code == UBCP_CMD_WIFI_STATUS) handle_wifi(req);
        else if (req->cmd_code == UBCP_CMD_NET_STATUS) handle_net_status(req);
        else msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }
    if (req->payload_len > sizeof(((command_t *)0)->data)) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM); return;
    }
    command_t *cmd = calloc(1, sizeof(*cmd));
    if (!cmd) { msg_bus_send_status_response(req, UBCP_ERR_BUSY); return; }
    cmd->req = *req;
    if (req->payload_len) memcpy(cmd->data, req->payload, req->payload_len);
    if (xQueueSend(s_commands, &cmd, 0) != pdTRUE) {
        memset(cmd, 0, sizeof(*cmd)); free(cmd);
        msg_bus_send_status_response(req, UBCP_ERR_BUSY);
    }
}
static void network_stop(void)
{
    command_t *cmd = calloc(1, sizeof(*cmd));
    if (!cmd) return;
    cmd->req.cmd_code = 0xff;
    if (!s_commands || xQueueSend(s_commands, &cmd, 0) != pdTRUE) free(cmd);
}
static const hex_module_t s_network_module = {
    .name = "Network", .cmd_range_start = UBCP_CMD_RANGE_NET_START,
    .cmd_range_end = UBCP_CMD_RANGE_NET_END, .init = network_init,
    .handle_cmd = network_handle_cmd, .stop = network_stop,
};
const hex_module_t *mod_network_get(void) { return &s_network_module; }
