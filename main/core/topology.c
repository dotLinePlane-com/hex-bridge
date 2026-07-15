#include <stddef.h>
#include "core/topology.h"

#define TOPOLOGY_MAX_ENTRIES 16

static ubcp_route_entry_t s_routes[TOPOLOGY_MAX_ENTRIES];
static uint8_t s_count = 0;

void topology_init(void)
{
    s_count = 0;
}

void topology_register(uint8_t channel_id, uint8_t device_type, void *driver)
{
    if (s_count >= TOPOLOGY_MAX_ENTRIES) {
        return;
    }
    s_routes[s_count].channel_id   = channel_id;
    s_routes[s_count].device_type  = device_type;
    s_routes[s_count].device_driver = driver;
    s_count++;
}

int topology_for_each(void (*cb)(uint8_t ch, uint8_t type, void *drv, void *ctx), void *ctx)
{
    if (!cb) {
        return (int)s_count;
    }
    for (uint8_t i = 0; i < s_count; i++) {
        cb(s_routes[i].channel_id, s_routes[i].device_type, s_routes[i].device_driver, ctx);
    }
    return (int)s_count;
}

const ubcp_route_entry_t *topology_find(uint8_t channel_id)
{
    for (uint8_t i = 0; i < s_count; i++) {
        if (s_routes[i].channel_id == channel_id) {
            return &s_routes[i];
        }
    }
    return NULL;
}
