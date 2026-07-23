#pragma once

#include "core/module_base.h"
#include <stdint.h>

const hex_module_t *mod_network_get(void);

/* Conntype exported for NET_LIST_CONNS cross-module query */
#define NET_CONN_TYPE_TCP_SERVER  0x00
#define NET_CONN_TYPE_TCP_CONN    0x01
#define NET_CONN_TYPE_UDP_SERVER  0x02
#define NET_CONN_TYPE_UDP_CLIENT  0x03
#define NET_CONN_TYPE_WS_SERVER   0x04
#define NET_CONN_TYPE_WS_CONN     0x05

typedef struct {
    uint8_t  conn_type;
    uint16_t handle;
    uint16_t parent_handle;
    uint16_t local_port;
    uint32_t remote_ip;
} net_conn_entry_t;

typedef void (*net_conn_iter_cb)(const net_conn_entry_t *entry, void *ctx);

void mod_network_register_conn_provider(const char *name, void (*iterate)(net_conn_iter_cb cb, void *ctx));
