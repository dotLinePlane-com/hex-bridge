#pragma once

#define HEX_MCP_TCP_PORT 9500
#define HEX_DAP_TCP_PORT 4441

static inline int hex_tcp_port_reserved(unsigned port)
{
    return port == HEX_MCP_TCP_PORT || port == HEX_DAP_TCP_PORT;
}
