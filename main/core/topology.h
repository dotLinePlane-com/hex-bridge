#pragma once

#include <stdint.h>

typedef struct {
    uint8_t channel_id;
    uint8_t device_type;
    void   *device_driver;
} ubcp_route_entry_t;

void topology_init(void);
void topology_register(uint8_t channel_id, uint8_t device_type, void *driver);
int topology_for_each(void (*cb)(uint8_t ch, uint8_t type, void *drv, void *ctx), void *ctx);
const ubcp_route_entry_t *topology_find(uint8_t channel_id);
