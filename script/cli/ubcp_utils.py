"""
UBCP v2.0 shared utilities for CLI and test scripts.

IP conversion, error code tables, frame parsing helpers, connection type names.
Imported by hex-bridge-network-cli.py and test_network.py.
"""

import struct

# ════════════════════════════════════════════════════════════
#  IP conversion
# ════════════════════════════════════════════════════════════

def ip_to_int(ip_str):
    """Convert '192.168.1.100' to u32 big-endian int."""
    parts = ip_str.split('.')
    if len(parts) != 4:
        raise ValueError(f"Invalid IP: {ip_str}")
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | \
           (int(parts[2]) << 8) | int(parts[3])


def int_to_ip(val):
    """Convert u32 big-endian int to 'x.x.x.x' string."""
    return f"{(val >> 24) & 0xFF}.{(val >> 16) & 0xFF}.{(val >> 8) & 0xFF}.{val & 0xFF}"


def ip_to_bytes(ip_str):
    """Convert '192.168.1.100' to 4 bytes big-endian."""
    return struct.pack('>I', ip_to_int(ip_str))


# ════════════════════════════════════════════════════════════
#  Error codes
# ════════════════════════════════════════════════════════════

ERR_CODES = {
    0x00: "SUCCESS",
    0x01: "ERR_GENERAL",
    0x02: "ERR_PARAM",
    0x03: "ERR_TIMEOUT",
    0x04: "ERR_BUSY",
    0x05: "ERR_NO_MEM",
    0x06: "ERR_NOT_SUPPORT",
    0x0A: "ERR_CHANNEL_INVALID",
    0x16: "ERR_TYPE_MISMATCH",
    0x40: "ERR_NET_DISCONNECTED",
    0x41: "ERR_NET_CONN_REFUSED",
    0x42: "ERR_NET_TIMEOUT",
    0x43: "ERR_NET_HANDLE_INVALID",
    0x44: "ERR_NET_BUFFER_FULL",
    0x45: "ERR_NET_PORT_IN_USE",
    0x46: "ERR_NET_DNS_FAIL",
    0x47: "ERR_NET_NO_IP",
    0x48: "ERR_NET_MAX_CONN",
    0x49: "ERR_NET_WS_HANDSHAKE",
    0x4A: "ERR_NET_WS_PROTOCOL",
}


def err_name(code):
    """Return human-readable name for an error code, e.g. 0x43 -> 'ERR_NET_HANDLE_INVALID'."""
    return ERR_CODES.get(code, f"UNKNOWN_0x{code:02X}")


def status_str(code):
    """Return 'OK' or 'ERR 0xNN (NAME)' for a status byte."""
    if code == 0:
        return "OK"
    return f"ERR 0x{code:02X} ({err_name(code)})"


# ════════════════════════════════════════════════════════════
#  Connection type names
# ════════════════════════════════════════════════════════════

CONN_TYPE_NAMES = {
    0: "TCP_SERVER",
    1: "TCP_CONN",
    2: "UDP_SERVER",
    3: "UDP_CLIENT",
    4: "WS_SERVER",
    5: "WS_CONN",
}


def conn_type_name(ct):
    return CONN_TYPE_NAMES.get(ct, f"TYPE_0x{ct:02X}")


# ════════════════════════════════════════════════════════════
#  WS message type names
# ════════════════════════════════════════════════════════════

WS_MSG_NAMES = {
    0x01: "Text",
    0x02: "Binary",
    0x08: "Close",
    0x09: "Ping",
    0x0A: "Pong",
}


def ws_msg_name(mt):
    return WS_MSG_NAMES.get(mt, f"0x{mt:02X}")


# ════════════════════════════════════════════════════════════
#  Frame parsing helpers
# ════════════════════════════════════════════════════════════

def parse_u16(data, offset):
    """Parse big-endian u16 from bytes at offset."""
    return (data[offset] << 8) | data[offset + 1]


def parse_u32(data, offset):
    """Parse big-endian u32 from bytes at offset."""
    return (data[offset] << 24) | (data[offset + 1] << 16) | \
           (data[offset + 2] << 8) | data[offset + 3]


def encode_u16(val):
    """Encode u16 to 2 big-endian bytes."""
    return bytes([(val >> 8) & 0xFF, val & 0xFF])


def encode_u32(val):
    """Encode u32 to 4 big-endian bytes."""
    return bytes([(val >> 24) & 0xFF, (val >> 16) & 0xFF,
                  (val >> 8) & 0xFF, val & 0xFF])


# ════════════════════════════════════════════════════════════
#  UBCP command names (for display)
# ════════════════════════════════════════════════════════════

CMD_NAMES = {
    0x00: "PING",
    0x01: "GET_INFO",
    0x02: "GET_CONFIG",
    0x03: "SET_CONFIG",
    0x40: "NET_CONFIG",
    0x41: "NET_STATUS",
    0x42: "NET_DNS",
    0x43: "NET_LINK_EVENT",
    0x44: "NET_LIST_CONNS",
    0x50: "TCP_SERVER_OPEN",
    0x51: "TCP_SERVER_CLOSE",
    0x52: "TCP_CLIENT_CONNECT",
    0x53: "TCP_CLIENT_DISCONNECT",
    0x54: "TCP_SEND",
    0x55: "TCP_RECV",
    0x56: "TCP_ACCEPT",
    0x57: "TCP_CLOSE",
    0x58: "TCP_DISCONNECT_EVENT",
    0x59: "TCP_LIST_CLIENTS",
    0x5A: "TCP_KICK_CLIENT",
    0x5B: "TCP_CONN_STATUS",
    0x60: "UDP_SERVER_OPEN",
    0x61: "UDP_SERVER_CLOSE",
    0x62: "UDP_CLIENT_CREATE",
    0x63: "UDP_CLIENT_DELETE",
    0x64: "UDP_SERVER_SEND",
    0x65: "UDP_RECV",
    0x66: "UDP_CLIENT_SEND",
    0x70: "WS_SERVER_OPEN",
    0x71: "WS_SERVER_CLOSE",
    0x72: "WS_CLIENT_CONNECT",
    0x73: "WS_CLIENT_DISCONNECT",
    0x74: "WS_SEND",
    0x75: "WS_RECV",
    0x76: "WS_ACCEPT",
    0x77: "WS_DISCONNECT_EVENT",
    0x78: "WS_LIST_CLIENTS",
    0x79: "WS_KICK_CLIENT",
}


def cmd_name(code):
    return CMD_NAMES.get(code, f"0x{code:02X}")
