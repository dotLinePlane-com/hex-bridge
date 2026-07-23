#include <string.h>
#include <stdlib.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "freertos/semphr.h"
#include "esp_netif.h"
#include "esp_eth.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "lwip/sockets.h"
#include "lwip/dns.h"
#include "modules/mod_network.h"
#include "core/msg_bus.h"
#include "core/seq_num.h"
#include "core/eth_init.h"
#include "hex_config.h"
#include "utils/hex_log.h"

static const char *TAG = "mod_network";

/* ── Internal state ── */
static bool s_eth_initialized = false;
static uint8_t s_link_state = 0;
static uint8_t s_conn_state = 0;
static uint32_t s_current_ip = 0;
static uint32_t s_subnet_mask = 0;
static uint32_t s_gateway = 0;
static uint32_t s_dns_primary = 0;
static SemaphoreHandle_t s_state_mutex = NULL;
static esp_netif_t *s_netif_ptr = NULL;

/* Cross-module connection list providers */
#define MAX_CONN_PROVIDERS 4
static struct {
    const char *name;
    void (*iterate)(net_conn_iter_cb cb, void *ctx);
} s_conn_providers[MAX_CONN_PROVIDERS];
static int s_conn_provider_count = 0;

void mod_network_register_conn_provider(const char *name, void (*iterate)(net_conn_iter_cb cb, void *ctx))
{
    if (s_conn_provider_count < MAX_CONN_PROVIDERS) {
        s_conn_providers[s_conn_provider_count].name    = name;
        s_conn_providers[s_conn_provider_count].iterate = iterate;
        s_conn_provider_count++;
    }
}

/* ── Internal helpers ── */
static void send_link_event(uint8_t event_type, uint32_t ip)
{
    uint8_t payload[6];
    payload[0] = 0x00;           /* IntfIndex (ETH0) */
    payload[1] = event_type;
    payload[2] = (uint8_t)(ip >> 24);
    payload[3] = (uint8_t)(ip >> 16);
    payload[4] = (uint8_t)(ip >> 8);
    payload[5] = (uint8_t)(ip & 0xFF);

    ubcp_frame_t evt;
    memset(&evt, 0, sizeof(evt));
    evt.version       = UBCP_VERSION;
    evt.flags         = UBCP_FLAG_DIR | UBCP_FLAG_EVT | UBCP_FLAG_TS;
    evt.seq_num       = seq_num_next();
    evt.cmd_code      = UBCP_CMD_NET_LINK_EVENT;
    evt.channel_id    = 0;
    evt.has_timestamp = true;
    evt.timestamp     = (uint32_t)(esp_timer_get_time() & 0xFFFFFFFF);
    evt.payload       = payload;
    evt.payload_len   = sizeof(payload);

    msg_bus_send_frame(&evt);
}

static void update_link_state(uint8_t new_state)
{
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    s_link_state = new_state;
    xSemaphoreGive(s_state_mutex);
}

static void update_conn_state(uint8_t new_state)
{
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    s_conn_state = new_state;
    xSemaphoreGive(s_state_mutex);
}

static void update_ip_info(const esp_netif_ip_info_t *ip_info)
{
    uint32_t old_ip;
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    old_ip         = s_current_ip;
    s_current_ip   = ip_info->ip.addr;
    s_subnet_mask  = ip_info->netmask.addr;
    s_gateway      = ip_info->gw.addr;
    s_conn_state   = 1;  /* 已连接 */
    xSemaphoreGive(s_state_mutex);

    if (old_ip != 0 && old_ip != s_current_ip) {
        send_link_event(0x04, s_current_ip); /* IP_CHANGED */
    } else {
        send_link_event(0x02, s_current_ip); /* IP_ACQUIRED */
    }
}

/* ── Event handlers registered with ESP-IDF ── */
static void net_eth_event_handler(void *arg, esp_event_base_t event_base,
                                  int32_t event_id, void *event_data)
{
    switch (event_id) {
    case ETHERNET_EVENT_CONNECTED:
        update_link_state(1);
        update_conn_state(2);  /* 获取IP中 */
        send_link_event(0x01, 0);  /* LINK_UP */
        ESP_LOGI(TAG, "链路 UP 事件上报");
        break;
    case ETHERNET_EVENT_DISCONNECTED:
        update_link_state(0);
        update_conn_state(0);
        send_link_event(0x00, 0);  /* LINK_DOWN */
        ESP_LOGI(TAG, "链路 DOWN 事件上报");
        break;
    default:
        break;
    }
}

static void net_ip_event_handler(void *arg, esp_event_base_t event_base,
                                 int32_t event_id, void *event_data)
{
    ip_event_got_ip_t *evt = (ip_event_got_ip_t *)event_data;
    if (event_id == IP_EVENT_ETH_GOT_IP) {
        update_ip_info(&evt->ip_info);
        ESP_LOGI(TAG, "IP 获取事件上报: " IPSTR, IP2STR(&evt->ip_info.ip));
    } else if (event_id == IP_EVENT_ETH_LOST_IP) {
        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
        s_current_ip = 0;
        s_conn_state = 0;
        xSemaphoreGive(s_state_mutex);
        send_link_event(0x03, 0);  /* IP_LOST */
        ESP_LOGI(TAG, "IP 丢失事件上报");
    }
}

/* ── DNS callback context ── */
typedef struct {
    SemaphoreHandle_t sem;
    ip_addr_t         resolved_ip;
    bool              done;
} dns_ctx_t;

static void dns_found_cb(const char *name, const ip_addr_t *ipaddr, void *arg)
{
    dns_ctx_t *ctx = (dns_ctx_t *)arg;
    if (ipaddr) {
        ctx->resolved_ip = *ipaddr;
    }
    ctx->done = true;
    xSemaphoreGive(ctx->sem);
}

/* ========================================================================
 *  NET_CONFIG (0x40)
 * ======================================================================== */
static void handle_net_config(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t config_type = req->payload[1];

    if (config_type == 0x00) {
        /* DHCP mode */
        if (s_netif_ptr) {
            esp_netif_dhcpc_stop(s_netif_ptr);
            esp_netif_dhcpc_start(s_netif_ptr);
        }
    } else if (config_type == 0x01) {
        /* Static IP — payload must be 22 bytes */
        if (req->payload_len < 22) {
            msg_bus_send_status_response(req, UBCP_ERR_PARAM);
            return;
        }

        uint32_t ip   = ((uint32_t)req->payload[2]  << 24) | ((uint32_t)req->payload[3]  << 16) |
                        ((uint32_t)req->payload[4]  << 8)  |  (uint32_t)req->payload[5];
        uint32_t mask = ((uint32_t)req->payload[6]  << 24) | ((uint32_t)req->payload[7]  << 16) |
                        ((uint32_t)req->payload[8]  << 8)  |  (uint32_t)req->payload[9];
        uint32_t gw   = ((uint32_t)req->payload[10] << 24) | ((uint32_t)req->payload[11] << 16) |
                        ((uint32_t)req->payload[12] << 8)  |  (uint32_t)req->payload[13];
        uint32_t dns1 = ((uint32_t)req->payload[14] << 24) | ((uint32_t)req->payload[15] << 16) |
                        ((uint32_t)req->payload[16] << 8)  |  (uint32_t)req->payload[17];

        esp_netif_ip_info_t ip_info;
        ip_info.ip.addr      = ip;
        ip_info.netmask.addr = mask;
        ip_info.gw.addr      = gw;

        if (s_netif_ptr) {
            esp_netif_dhcpc_stop(s_netif_ptr);
            esp_netif_set_ip_info(s_netif_ptr, &ip_info);

            esp_netif_dns_info_t dns;
            dns.ip.u_addr.ip4.addr = dns1;
            dns.ip.type = ESP_IPADDR_TYPE_V4;
            esp_netif_set_dns_info(s_netif_ptr, ESP_NETIF_DNS_MAIN, &dns);
        }

        xSemaphoreTake(s_state_mutex, portMAX_DELAY);
        s_current_ip  = ip;
        s_subnet_mask = mask;
        s_gateway     = gw;
        s_dns_primary = dns1;
        s_conn_state  = 1;
        xSemaphoreGive(s_state_mutex);
    } else {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    /* Build response: Status(1) + IP(4) + Mask(4) + GW(4) + DNS(4) = 17 bytes */

    /* Need access to netif to get actual IP. Using cached values */

    uint8_t payload[17];
    uint32_t cur_ip, cur_mask, cur_gw, cur_dns;
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    cur_ip  = s_current_ip;
    cur_mask = s_subnet_mask;
    cur_gw  = s_gateway;
    cur_dns = s_dns_primary;
    xSemaphoreGive(s_state_mutex);

    payload[0] = UBCP_ERR_SUCCESS;
    payload[1]  = (uint8_t)(cur_ip >> 24);
    payload[2]  = (uint8_t)(cur_ip >> 16);
    payload[3]  = (uint8_t)(cur_ip >> 8);
    payload[4]  = (uint8_t)(cur_ip & 0xFF);
    payload[5]  = (uint8_t)(cur_mask >> 24);
    payload[6]  = (uint8_t)(cur_mask >> 16);
    payload[7]  = (uint8_t)(cur_mask >> 8);
    payload[8]  = (uint8_t)(cur_mask & 0xFF);
    payload[9]  = (uint8_t)(cur_gw >> 24);
    payload[10] = (uint8_t)(cur_gw >> 16);
    payload[11] = (uint8_t)(cur_gw >> 8);
    payload[12] = (uint8_t)(cur_gw & 0xFF);
    payload[13] = (uint8_t)(cur_dns >> 24);
    payload[14] = (uint8_t)(cur_dns >> 16);
    payload[15] = (uint8_t)(cur_dns >> 8);
    payload[16] = (uint8_t)(cur_dns & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  NET_STATUS (0x41)
 * ======================================================================== */
static void handle_net_status(const ubcp_frame_t *req)
{
    uint8_t mac[6];
    eth_get_mac_addr(mac);

    uint32_t ip, mask;
    uint8_t link, conn;
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    link = s_link_state;
    conn = s_conn_state;
    ip   = s_current_ip;
    mask = s_subnet_mask;
    xSemaphoreGive(s_state_mutex);

    /* Status(1) + IntfCount(1) + 17 bytes per interface */
    uint8_t payload[2 + 17];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = 1;  /* IntfCount */

    payload[2]  = 0x00;  /* IntfIndex: ETH0 */
    payload[3]  = link;
    payload[4]  = conn;
    payload[5]  = (uint8_t)(ip >> 24);
    payload[6]  = (uint8_t)(ip >> 16);
    payload[7]  = (uint8_t)(ip >> 8);
    payload[8]  = (uint8_t)(ip & 0xFF);
    payload[9]  = (uint8_t)(mask >> 24);
    payload[10] = (uint8_t)(mask >> 16);
    payload[11] = (uint8_t)(mask >> 8);
    payload[12] = (uint8_t)(mask & 0xFF);
    memcpy(&payload[13], mac, 6);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
}

/* ========================================================================
 *  NET_DNS (0x42)
 * ======================================================================== */
static void handle_net_dns(const ubcp_frame_t *req)
{
    if (req->payload_len < 2) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint8_t name_len = req->payload[0];
    if (name_len == 0 || name_len > 253 || (req->payload_len < (uint16_t)(1 + name_len))) {
        msg_bus_send_status_response(req, UBCP_ERR_PARAM);
        return;
    }

    uint32_t cur_ip;
    xSemaphoreTake(s_state_mutex, portMAX_DELAY);
    cur_ip = s_current_ip;
    xSemaphoreGive(s_state_mutex);

    if (cur_ip == 0) {
        uint8_t err_payload[2] = { UBCP_ERR_NET_NO_IP, 0 };
        ubcp_frame_t resp;
        ubcp_frame_make_response(req, &resp);
        resp.payload     = err_payload;
        resp.payload_len = sizeof(err_payload);
        msg_bus_send_frame(&resp);
        return;
    }

    char hostname[254];
    memcpy(hostname, &req->payload[1], name_len);
    hostname[name_len] = '\0';

    dns_ctx_t ctx;
    ctx.sem  = xSemaphoreCreateBinary();
    ctx.done = false;
    memset(&ctx.resolved_ip, 0, sizeof(ctx.resolved_ip));

    ip_addr_t resolved;
    err_t dns_err = dns_gethostbyname(hostname, &resolved, dns_found_cb, &ctx);
    if (dns_err == ERR_OK) {
        ctx.resolved_ip = resolved;
        ctx.done = true;
    }

    if (!ctx.done) {
        if (xSemaphoreTake(ctx.sem, pdMS_TO_TICKS(5000)) != pdTRUE) {
            vSemaphoreDelete(ctx.sem);
            uint8_t err_payload[2] = { UBCP_ERR_NET_DNS_FAIL, 0 };
            ubcp_frame_t resp;
            ubcp_frame_make_response(req, &resp);
            resp.payload     = err_payload;
            resp.payload_len = sizeof(err_payload);
            msg_bus_send_frame(&resp);
            return;
        }
    }
    vSemaphoreDelete(ctx.sem);

    if (ctx.resolved_ip.type != IPADDR_TYPE_V4 || ctx.resolved_ip.u_addr.ip4.addr == 0) {
        uint8_t err_payload[2] = { UBCP_ERR_NET_DNS_FAIL, 0 };
        ubcp_frame_t resp;
        ubcp_frame_make_response(req, &resp);
        resp.payload     = err_payload;
        resp.payload_len = sizeof(err_payload);
        msg_bus_send_frame(&resp);
        return;
    }

    uint32_t ip_addr = ctx.resolved_ip.u_addr.ip4.addr;
    uint8_t payload[2 + 4];
    payload[0] = UBCP_ERR_SUCCESS;
    payload[1] = 1;  /* AddrCount */
    payload[2] = (uint8_t)(ip_addr >> 24);
    payload[3] = (uint8_t)(ip_addr >> 16);
    payload[4] = (uint8_t)(ip_addr >> 8);
    payload[5] = (uint8_t)(ip_addr & 0xFF);

    ubcp_frame_t resp;
    ubcp_frame_make_response(req, &resp);
    resp.payload     = payload;
    resp.payload_len = sizeof(payload);
    msg_bus_send_frame(&resp);
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
    if (lc->offset + 10 > lc->capacity) return;

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
    lc->offset += 10;
    lc->count++;
}

static void handle_net_list_conns(const ubcp_frame_t *req)
{
    /* First pass: count total entries */
    uint16_t max_entries = 60;
    uint16_t buf_size = 2 + max_entries * 10;
    uint8_t *payload = malloc(buf_size);
    if (!payload) {
        msg_bus_send_status_response(req, UBCP_ERR_UNKNOWN);
        return;
    }

    list_conns_ctx_t lc;
    lc.buf      = payload + 2;
    lc.offset   = 0;
    lc.capacity = max_entries * 10;
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
 *  Module dispatch and init
 * ======================================================================== */
static esp_err_t network_init(void)
{
    s_state_mutex = xSemaphoreCreateMutex();
    if (!s_state_mutex) return ESP_ERR_NO_MEM;

    esp_eth_handle_t eth_handle;
    esp_err_t ret = eth_hw_init(&eth_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "以太网初始化失败: %d", ret);
        return ret;
    }

    s_netif_ptr = eth_get_netif();

    /* Register second-level event handlers (on top of the ones in eth_init.c) */
    esp_event_handler_register(ETH_EVENT, ETHERNET_EVENT_CONNECTED,
                                &net_eth_event_handler, NULL);
    esp_event_handler_register(ETH_EVENT, ETHERNET_EVENT_DISCONNECTED,
                                &net_eth_event_handler, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_GOT_IP,
                                &net_ip_event_handler, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_ETH_LOST_IP,
                                &net_ip_event_handler, NULL);

    s_eth_initialized = true;
    ESP_LOGI(TAG, "网络配置模块初始化完成");
    return ESP_OK;
}

static void network_handle_cmd(const ubcp_frame_t *frame)
{
    switch (frame->cmd_code) {
    case UBCP_CMD_NET_CONFIG:
        handle_net_config(frame);
        break;
    case UBCP_CMD_NET_STATUS:
        handle_net_status(frame);
        break;
    case UBCP_CMD_NET_DNS:
        handle_net_dns(frame);
        break;
    case UBCP_CMD_NET_LIST_CONNS:
        handle_net_list_conns(frame);
        break;
    default:
        msg_bus_send_status_response(frame, UBCP_ERR_NOT_SUPPORT);
        break;
    }
}

static const hex_module_t s_network_module = {
    .name            = "Network",
    .cmd_range_start = UBCP_CMD_RANGE_NET_START,
    .cmd_range_end   = UBCP_CMD_RANGE_NET_END,
    .init            = network_init,
    .handle_cmd      = network_handle_cmd,
    .stop            = NULL,
};

const hex_module_t *mod_network_get(void)
{
    return &s_network_module;
}
