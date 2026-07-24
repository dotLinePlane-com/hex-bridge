#!/usr/bin/env python3
"""
hex-bridge-network-cli.py — HEX-Bridge Network CLI Tool

============================================================
  MCP Network Command-Line Tool for UBCP v2.0 Protocol
============================================================

Sends UBCP v2.0 network commands to HEX-Bridge device over MCP serial port.
Covers NET, TCP, UDP, WebSocket modules, MCP baud rate configuration,
and UBCP event monitoring.

────────────────────────────────────────────────────────────
 Quick Start
────────────────────────────────────────────────────────────

    # Basic usage (default: COM35, 115200 bps)
    python hex-bridge-network-cli.py net-status
    python hex-bridge-network-cli.py tcp-server-open --port 9191
    python hex-bridge-network-cli.py ws-send --handle 0xA000 --msg-type 1 --data "Hello"

────────────────────────────────────────────────────────────
 Global Options
────────────────────────────────────────────────────────────

    --port PORT       MCP serial port (default: COM35)
    --baud BAUD       Baud rate (default: 115200)
    --timeout SEC     Response timeout in seconds (default: 5)
    --json            Machine-readable JSON output
    -i, --interactive Interactive session mode (connection stays open)

────────────────────────────────────────────────────────────
 Interactive Mode (-i)
────────────────────────────────────────────────────────────

    python hex-bridge-network-cli.py -i
    > tcp-server-open --port 9191 --save-as srv
    # handle=0x1000 saved as $srv
    > tcp-list-clients --handle $srv
    # Clients: 0
    > net-list-conns
    > ws-server-open --port 9201 --path /test --save-as ws
    > quit

    Saved handles persist across commands within the session.

────────────────────────────────────────────────────────────
 JSON Output Mode (--json)
────────────────────────────────────────────────────────────

    python hex-bridge-network-cli.py --json net-status
    {
      "cmd": "NET_STATUS",
      "status": "OK",
      "link": "UP",
      "conn_state": "已连接",
      "ip": "192.168.1.109",
      ...
    }

────────────────────────────────────────────────────────────
 Event Listening (listen)
────────────────────────────────────────────────────────────

    # Listen for specific events (comma-separated hex codes)
    python hex-bridge-network-cli.py listen --events 0x55,0x75,0x77 --timeout 30

    # Listen for all events
    python hex-bridge-network-cli.py listen --all --timeout 60

    # Filter by command code
    python hex-bridge-network-cli.py listen --cmd 0x76

────────────────────────────────────────────────────────────
 Command Reference
────────────────────────────────────────────────────────────

  Network Config (0x40-0x4F):
    net-config     DHCP/static IP configuration (0x40)
    net-status     Network interface status (0x41)
    net-dns        DNS hostname resolution (0x42)
    net-list-conns Global connection overview (0x44)

  TCP (0x50-0x5F):
    tcp-server-open       Create TCP server (0x50)
    tcp-server-close      Close TCP server (0x51)
    tcp-client-connect    TCP client connect (0x52)
    tcp-disconnect        TCP disconnect (0x53)
    tcp-send              TCP send data (0x54)
    tcp-accept            Manual accept/reject (0x56)
    tcp-close             Generic close (0x57)
    tcp-list-clients      List server clients (0x59)
    tcp-kick-client       Kick client (0x5A)
    tcp-conn-status       Connection status (0x5B)

  UDP (0x60-0x6F):
    udp-server-open       Create UDP server (0x60)
    udp-server-close      Close UDP server (0x61)
    udp-client-create     Create UDP client (0x62)
    udp-client-delete     Delete UDP client (0x63)
    udp-server-send       Send via server (0x64)
    udp-client-send       Send via client (0x66)

  WebSocket (0x70-0x7F):
    ws-server-open        Create WS server (0x70)
    ws-server-close       Close WS server (0x71)
    ws-client-connect     WS client connect (0x72)
    ws-client-disconnect  WS client disconnect (0x73)
    ws-send               WS send frame (0x74)
    ws-list-clients       List WS clients (0x78)
    ws-kick-client        Kick WS client (0x79)

  System:
    mcp-baud              Get/set/probe MCP baud rate
    listen                Monitor UBCP event frames
    ping                  Send PING to verify connectivity

────────────────────────────────────────────────────────────
 Error Codes
────────────────────────────────────────────────────────────

    0x41  ERR_NET_CONN_REFUSED    0x43  ERR_NET_HANDLE_INVALID
    0x45  ERR_NET_PORT_IN_USE     0x46  ERR_NET_DNS_FAIL
    0x49  ERR_NET_WS_HANDSHAKE

────────────────────────────────────────────────────────────
 Dependencies
────────────────────────────────────────────────────────────

    ubcp_client.py   UBCP v2.0 frame build/parse (CRC + byte-stuffing)
    mcp_transport.py Serial port wrapper with frame receive/event filter
    ubcp_utils.py    Shared IP/error-code/frame helpers
"""

import sys
import os
import argparse
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'test'))
from ubcp_client import UBCPBuilder, UBCPParser
from mcp_transport import MCPTransport
from ubcp_utils import (
    ip_to_int, int_to_ip, err_name, status_str,
    conn_type_name, ws_msg_name, cmd_name,
    parse_u16, parse_u32, encode_u16, encode_u32,
)

# ════════════════════════════════════════════════════════════
#  Global state
# ════════════════════════════════════════════════════════════

_seq_counter = 1
_json_mode = False
_saved_handles = {}  # name -> handle value


def next_seq():
    global _seq_counter
    s = _seq_counter
    _seq_counter += 1
    return s


def resolve_handle(val):
    """Resolve a handle: raw int, hex string, or $saved_name reference."""
    if isinstance(val, int):
        return val
    s = str(val)
    if s.startswith('$'):
        name = s[1:]
        if name in _saved_handles:
            return _saved_handles[name]
        raise ValueError(f"Unknown saved handle: ${name}")
    return int(s, 0)


def read_hex_data(arg_val):
    """Parse --data or --hex-data into bytes."""
    if arg_val is None:
        return b''
    if isinstance(arg_val, bytes):
        return arg_val
    return arg_val.encode('utf-8')


def read_hex_or_text(args_data, args_hex_data):
    """Resolve --data (text) or --hex-data into bytes. hex-data wins if both set."""
    if args_hex_data:
        return bytes.fromhex(args_hex_data.replace(' ', ''))
    if args_data:
        return args_data.encode('utf-8')
    return b''


# ════════════════════════════════════════════════════════════
#  Output helpers
# ════════════════════════════════════════════════════════════

def output(result):
    """Print result as JSON or human-readable key-value pairs."""
    if _json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, val in result.items():
            if key.startswith('_'):
                continue
            if isinstance(val, bool):
                continue
            print(f"  {key}={val}")


def output_table(headers, rows):
    """Print table. In JSON mode, output list of dicts."""
    if _json_mode:
        print(json.dumps([dict(zip(headers, r)) for r in rows], ensure_ascii=False, indent=2))
    else:
        for row in rows:
            parts = []
            for h, v in zip(headers, row):
                parts.append(f"{h}={v}")
            print("    " + " ".join(parts))


def frame_info(f):
    """Basic frame metadata for JSON output."""
    return {
        "cmd": cmd_name(f.cmd_code),
        "cmd_code": f"0x{f.cmd_code:02X}",
        "flags": f"0x{f.flags:02X}",
        "seq": f"0x{f.seq_num:04X}",
        "plen": f.payload_len,
    }


# ════════════════════════════════════════════════════════════
#  Transport helpers
# ════════════════════════════════════════════════════════════

def send_cmd(transport, cmd, payload=b'', channel=0, timeout=5.0):
    """Send a UBCP request and return the response frame."""
    transport.flush_input()
    frame = UBCPBuilder.build_request(next_seq(), cmd, channel, payload)
    transport.send(frame)
    return transport.recv_response(cmd_code=cmd, timeout=timeout)


def expect_response(transport, cmd, payload=b'', channel=0, timeout=5.0):
    """Send and expect a response. Raises if no response.
    Returns (frame, status_byte)."""
    resp = send_cmd(transport, cmd, payload, channel, timeout)
    if resp is None:
        raise TimeoutError(f"No response for {cmd_name(cmd)}")
    return resp, resp.payload[0]


# ════════════════════════════════════════════════════════════
#  NET commands
# ════════════════════════════════════════════════════════════

def cmd_net_config(transport, args):
    if args.dhcp:
        payload = b'\x00\x00'
    else:
        payload = b'\x00\x01'
        payload += encode_u32(ip_to_int(args.ip))
        payload += encode_u32(ip_to_int(args.mask))
        payload += encode_u32(ip_to_int(args.gateway))
        payload += encode_u32(ip_to_int(args.dns1)) if args.dns1 else b'\x00\x00\x00\x00'
        payload += encode_u32(ip_to_int(args.dns2)) if args.dns2 else b'\x00\x00\x00\x00'
    resp, st = expect_response(transport, 0x40, payload)
    output({**frame_info(resp), "status": status_str(st)})


def cmd_net_dns(transport, args):
    hostname = args.hostname.encode('utf-8')[:253]
    payload = bytes([len(hostname)]) + hostname
    resp, st = expect_response(transport, 0x42, payload, timeout=8.0)
    count = resp.payload[1]
    addrs = []
    for i in range(count):
        addrs.append(int_to_ip(parse_u32(resp.payload, 2 + i * 4)))
    output({**frame_info(resp), "status": status_str(st), "addr_count": count, "addresses": addrs})


def cmd_net_status(transport, args):
    idx = args.index if args.index is not None else 0
    resp, st = expect_response(transport, 0x41, bytes([idx]))
    if resp.payload_len < 19:
        output({**frame_info(resp), "status": status_str(st)})
        return
    link = "UP" if resp.payload[3] else "DOWN"
    conn_map = {0: "未连接", 1: "已连接", 2: "获取IP中"}
    conn_state = conn_map.get(resp.payload[4] % 3, f"0x{resp.payload[4]:02X}")
    ip = int_to_ip(parse_u32(resp.payload, 5))
    mask = int_to_ip(parse_u32(resp.payload, 9))
    mac = ':'.join(f'{b:02X}' for b in resp.payload[13:19])
    output({**frame_info(resp), "status": status_str(st),
            "link": link, "conn_state": conn_state,
            "ip": ip, "mask": mask, "mac": mac})


def cmd_net_list_conns(transport, args):
    resp, st = expect_response(transport, 0x44, b'')
    count = resp.payload[1]
    rows = []
    for i in range(count):
        off = 2 + i * 10
        ct = resp.payload[off]
        handle = parse_u16(resp.payload, off + 1)
        parent = parse_u16(resp.payload, off + 3)
        lport = parse_u16(resp.payload, off + 5)
        rmt_ip = (resp.payload[off + 7] << 16) | (resp.payload[off + 8] << 8) | resp.payload[off + 9]
        rows.append([conn_type_name(ct), f"0x{handle:04X}",
                     f"0x{parent:04X}", str(lport), int_to_ip(rmt_ip)])
    output({**frame_info(resp), "status": status_str(st), "connections": count})
    if rows:
        output_table(["type", "handle", "parent", "lport", "remote_ip"], rows)


# ════════════════════════════════════════════════════════════
#  TCP commands
# ════════════════════════════════════════════════════════════

def cmd_tcp_server_open(transport, args):
    payload = encode_u16(args.port_num)
    payload += bytes([args.maxconn, args.accept_mode, args.keepalive])
    resp, st = expect_response(transport, 0x50, payload)
    handle = parse_u16(resp.payload, 1)
    actual = parse_u16(resp.payload, 3)
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "port": actual})


def cmd_tcp_server_close(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x51, bytes([(h>>8)&0xFF, h&0xFF, args.force]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_tcp_client_connect(transport, args):
    ip = ip_to_int(args.ip)
    payload = encode_u32(ip) + encode_u16(args.port_num)
    payload += bytes([args.connect_timeout, args.keepalive])
    resp, st = expect_response(transport, 0x52, payload, timeout=10.0)
    handle = parse_u16(resp.payload, 1)
    local_ip = int_to_ip(parse_u32(resp.payload, 3))
    local_port = parse_u16(resp.payload, 7)
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "local": f"{local_ip}:{local_port}"})


def cmd_tcp_disconnect(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x53, bytes([(h>>8)&0xFF, h&0xFF, args.method]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_tcp_accept(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x56, bytes([(h>>8)&0xFF, h&0xFF, args.decision]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_tcp_close(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x57, bytes([(h>>8)&0xFF, h&0xFF, args.handle_type, args.force]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_tcp_kick_client(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x5A, bytes([(h>>8)&0xFF, h&0xFF, args.force]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_tcp_send(transport, args):
    h = resolve_handle(args.handle)
    data = read_hex_or_text(args.data, args.hex_data)
    payload = encode_u16(h) + encode_u16(len(data)) + data
    resp, st = expect_response(transport, 0x54, payload)
    sent = parse_u16(resp.payload, 1) if resp.payload_len >= 3 else 0
    output({**frame_info(resp), "status": status_str(st), "sent_bytes": sent})


def cmd_tcp_list_clients(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x59, encode_u16(h))
    count = resp.payload[1]
    rows = []
    for i in range(count):
        off = 2 + i * 10
        ch = parse_u16(resp.payload, off)
        cip = int_to_ip(parse_u32(resp.payload, off + 2))
        cp = parse_u16(resp.payload, off + 6)
        ct = parse_u16(resp.payload, off + 8)
        rows.append([f"0x{ch:04X}", f"{cip}:{cp}", f"{ct}s"])
    output({**frame_info(resp), "status": status_str(st), "clients": count})
    if rows:
        output_table(["handle", "address", "uptime"], rows)


def cmd_tcp_conn_status(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x5B, encode_u16(h))
    if resp.payload_len < 22:
        output({**frame_info(resp), "status": status_str(st)})
        return
    states = {0: "ESTABLISHED", 1: "CLOSING", 2: "CLOSED"}
    cs = resp.payload[1]
    tx = parse_u32(resp.payload, 2)
    rx = parse_u32(resp.payload, 6)
    rip = int_to_ip(parse_u32(resp.payload, 10))
    rp = parse_u16(resp.payload, 14)
    lp = parse_u16(resp.payload, 16)
    ut = parse_u32(resp.payload, 18)
    output({**frame_info(resp), "status": status_str(st),
            "state": states.get(cs, f"0x{cs:02X}"),
            "tx_bytes": tx, "rx_bytes": rx,
            "remote": f"{rip}:{rp}", "local_port": lp, "uptime_s": ut})


# ════════════════════════════════════════════════════════════
#  UDP commands
# ════════════════════════════════════════════════════════════

def cmd_udp_server_open(transport, args):
    bc = 1 if args.broadcast else 0
    mc = ip_to_int(args.multicast) if args.multicast else 0
    payload = encode_u16(args.port_num) + bytes([bc]) + encode_u32(mc)
    resp, st = expect_response(transport, 0x60, payload)
    handle = parse_u16(resp.payload, 1)
    actual = parse_u16(resp.payload, 3)
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "port": actual})


def cmd_udp_server_close(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x61, encode_u16(h))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_udp_client_create(transport, args):
    ip = ip_to_int(args.ip)
    lp = args.local_port if args.local_port else 0
    payload = encode_u32(ip) + encode_u16(args.port_num) + encode_u16(lp)
    resp, st = expect_response(transport, 0x62, payload)
    handle = parse_u16(resp.payload, 1)
    actual = parse_u16(resp.payload, 3)
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "local_port": actual})


def cmd_udp_client_delete(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x63, encode_u16(h))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_udp_server_send(transport, args):
    h = resolve_handle(args.handle)
    ip = ip_to_int(args.ip)
    data = read_hex_or_text(args.data, args.hex_data)
    payload = encode_u16(h) + encode_u32(ip) + encode_u16(args.port_num)
    payload += encode_u16(len(data)) + data
    resp, st = expect_response(transport, 0x64, payload)
    sent = parse_u16(resp.payload, 1) if resp.payload_len >= 3 else 0
    output({**frame_info(resp), "status": status_str(st), "sent_bytes": sent})


def cmd_udp_client_send(transport, args):
    h = resolve_handle(args.handle)
    data = read_hex_or_text(args.data, args.hex_data)
    payload = encode_u16(h) + bytes([args.addr_mode])
    if args.addr_mode == 1:
        payload += encode_u32(ip_to_int(args.ip)) + encode_u16(args.port_num)
    payload += encode_u16(len(data)) + data
    resp, st = expect_response(transport, 0x66, payload)
    sent = parse_u16(resp.payload, 1) if resp.payload_len >= 3 else 0
    output({**frame_info(resp), "status": status_str(st), "sent_bytes": sent})


# ════════════════════════════════════════════════════════════
#  WS commands
# ════════════════════════════════════════════════════════════

def cmd_ws_server_open(transport, args):
    path = (args.path or '/').encode('utf-8')[:63]
    subproto = (args.subproto or '').encode('utf-8')[:63]
    payload = encode_u16(args.port_num) + bytes([args.maxconn, len(path)]) + path
    payload += bytes([len(subproto)]) + subproto
    resp, st = expect_response(transport, 0x70, payload)
    handle = parse_u16(resp.payload, 1)
    actual = parse_u16(resp.payload, 3)
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "port": actual})


def cmd_ws_client_connect(transport, args):
    ip = ip_to_int(args.ip)
    path = (args.path or '/').encode('utf-8')[:63]
    payload = encode_u32(ip) + encode_u16(args.port_num) + bytes([len(path)]) + path + b'\x00'
    resp, st = expect_response(transport, 0x72, payload, timeout=10.0)
    handle = parse_u16(resp.payload, 1) if resp.payload_len >= 3 else 0
    result = resp.payload[3] if resp.payload_len >= 4 else 0
    _save_handle(args, handle)
    output({**frame_info(resp), "status": status_str(st),
            "handle": f"0x{handle:04X}", "result": result})


def cmd_ws_server_close(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x71, bytes([(h>>8)&0xFF, h&0xFF, args.force]))
    output({**frame_info(resp), "status": status_str(st)})


def cmd_ws_client_disconnect(transport, args):
    h = resolve_handle(args.handle)
    payload = encode_u16(h) + encode_u16(args.close_code)
    resp, st = expect_response(transport, 0x73, payload)
    output({**frame_info(resp), "status": status_str(st)})


def cmd_ws_send(transport, args):
    h = resolve_handle(args.handle)
    data = read_hex_or_text(args.data, args.hex_data)
    payload = encode_u16(h) + bytes([args.msg_type]) + encode_u16(len(data)) + data
    resp, st = expect_response(transport, 0x74, payload)
    sent = parse_u16(resp.payload, 1) if resp.payload_len >= 3 else 0
    output({**frame_info(resp), "status": status_str(st),
            "msg_type": ws_msg_name(args.msg_type), "sent_bytes": sent})


def cmd_ws_list_clients(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x78, encode_u16(h))
    count = resp.payload[1]
    rows = []
    for i in range(count):
        off = 2 + i * 12
        ch = parse_u16(resp.payload, off)
        cip = int_to_ip(parse_u32(resp.payload, off + 2))
        cp = parse_u16(resp.payload, off + 6)
        sub = resp.payload[off + 8]
        plen = resp.payload[off + 9]
        ut = parse_u16(resp.payload, off + 10)
        rows.append([f"0x{ch:04X}", f"{cip}:{cp}", str(sub), str(plen), f"{ut}s"])
    output({**frame_info(resp), "status": status_str(st), "clients": count})
    if rows:
        output_table(["handle", "address", "subproto", "path_len", "uptime"], rows)


def cmd_ws_kick_client(transport, args):
    h = resolve_handle(args.handle)
    resp, st = expect_response(transport, 0x79, bytes([(h>>8)&0xFF, h&0xFF, args.force]))
    output({**frame_info(resp), "status": status_str(st)})


# ════════════════════════════════════════════════════════════
#  MCP baud rate
# ════════════════════════════════════════════════════════════

def cmd_mcp_baud(transport, args):
    group, key = 0x00, 0x12
    if args.set_baud is not None:
        new_baud = args.set_baud
        if new_baud < 9600 or new_baud > 5000000:
            print(f"Error: baud rate {new_baud} out of range (9600-5000000)")
            return
        payload = bytes([group, key, 0x00, 0x04]) + encode_u32(new_baud)
        resp, st = expect_response(transport, 0x03, payload)
        output({**frame_info(resp), "status": status_str(st),
                "baud_set": new_baud, "note": "reboot required"})
    else:
        resp, st = expect_response(transport, 0x02, bytes([group, key]))
        if resp.payload_len >= 9:
            baud = parse_u32(resp.payload, 5)
            output({**frame_info(resp), "status": status_str(st),
                    "baud_rate": baud})
        else:
            output({**frame_info(resp), "status": status_str(st), "baud_rate": "unknown"})


def probe_baud_rate(port, rates=None, ping_timeout=2.0):
    if rates is None:
        rates = [921600, 460800, 230400, 115200, 57600, 38400, 19200, 9600]
    print(f"Probing baud rates on {port}...")
    pkt = UBCPBuilder.build_request(1, 0x00, 0, b'')
    for rate in rates:
        try:
            t = MCPTransport(port=port, baudrate=rate)
            t.open()
            t.send(pkt)
            parser = UBCPParser()
            deadline = time.time() + ping_timeout
            while time.time() < deadline:
                b = t.ser.read(1)
                if not b:
                    continue
                frame = parser.feed(b[0])
                if frame is not None and frame.cmd_code == 0x00 and frame.is_response:
                    print(f"  Found: {rate} bps")
                    t.close()
                    return rate
            t.close()
        except Exception as e:
            print(f"  {rate}: {e}")
    print("No response at any baud rate")
    return None


# ════════════════════════════════════════════════════════════
#  listen — event monitoring
# ════════════════════════════════════════════════════════════

def cmd_listen(transport, args):
    timeout = args.timeout_val
    filter_cmds = None
    if args.events:
        filter_cmds = [int(c.strip(), 16) for c in args.events.split(',')]
    elif args.cmd is not None:
        filter_cmds = [args.cmd]

    if _json_mode:
        print(f'{{"mode":"listen","filter":{[f"0x{c:02X}" for c in filter_cmds] if filter_cmds else "all"},"timeout":{timeout}}}')
    else:
        flt = ','.join(f'0x{c:02X}' for c in filter_cmds) if filter_cmds else 'ALL'
        print(f"Listening for events (filter={flt}, timeout={timeout}s)...")
        print("Press Ctrl+C to stop.\n")

    deadline = time.time() + timeout
    count = 0
    try:
        while time.time() < deadline:
            frame = transport.recv_frame(timeout=0.2)
            if frame is None:
                continue
            if not frame.is_event:
                continue
            if filter_cmds and frame.cmd_code not in filter_cmds:
                continue
            count += 1
            ts = time.strftime("%H:%M:%S")
            name = cmd_name(frame.cmd_code)
            payload_hex = frame.payload[:64].hex()
            if _json_mode:
                print(json.dumps({
                    "n": count, "time": ts,
                    "cmd": name, "cmd_code": f"0x{frame.cmd_code:02X}",
                    "seq": f"0x{frame.seq_num:04X}",
                    "plen": frame.payload_len,
                    "payload_hex": payload_hex,
                }, ensure_ascii=False))
            else:
                print(f"[{ts}] #{count} {name} (0x{frame.cmd_code:02X}) "
                      f"seq=0x{frame.seq_num:04X} plen={frame.payload_len}")
                if frame.payload_len > 0:
                    print(f"    payload: {payload_hex}")
                # Decode common events
                _decode_event(frame)
    except KeyboardInterrupt:
        pass
    if not _json_mode:
        print(f"\n{count} event(s) received in {timeout}s.")


def _decode_event(frame):
    """Decode and print human-readable content for known event types."""
    cmd = frame.cmd_code
    payload = frame.payload
    if cmd in (0x55,):  # TCP_RECV
        if len(payload) >= 2:
            ch = parse_u16(payload, 0)
            data = payload[2:].decode('utf-8', errors='replace')
            print(f"    TCP_RECV: handle=0x{ch:04X} data={repr(data)}")
    elif cmd in (0x56,):  # TCP_ACCEPT
        if len(payload) >= 8:
            sh = parse_u16(payload, 0)
            ch = parse_u16(payload, 2)
            ip = int_to_ip(parse_u32(payload, 4))
            port = parse_u16(payload, 8)
            print(f"    TCP_ACCEPT: server=0x{sh:04X} client=0x{ch:04X} "
                  f"from={ip}:{port}")
    elif cmd in (0x58,):  # TCP_DISCONNECT_EVENT
        if len(payload) >= 3:
            ch = parse_u16(payload, 0)
            reason = payload[2]
            print(f"    TCP_DISCONNECT: handle=0x{ch:04X} reason={reason}")
    elif cmd in (0x75,):  # WS_RECV
        if len(payload) >= 5:
            ch = parse_u16(payload, 0)
            mt = payload[2]
            plen = parse_u16(payload, 3)
            data = payload[5:5+plen].decode('utf-8', errors='replace')
            print(f"    WS_RECV: handle=0x{ch:04X} type={ws_msg_name(mt)} "
                  f"len={plen} data={repr(data)}")
    elif cmd in (0x76,):  # WS_ACCEPT
        if len(payload) >= 10:
            sh = parse_u16(payload, 0)
            ch = parse_u16(payload, 2)
            ip = int_to_ip(parse_u32(payload, 4))
            port = parse_u16(payload, 8)
            print(f"    WS_ACCEPT: server=0x{sh:04X} client=0x{ch:04X} "
                  f"from={ip}:{port}")
    elif cmd in (0x77,):  # WS_DISCONNECT_EVENT
        if len(payload) >= 5:
            ch = parse_u16(payload, 0)
            code = parse_u16(payload, 2)
            reason = payload[4]
            print(f"    WS_DISCONNECT: handle=0x{ch:04X} close_code={code} reason={reason}")
    elif cmd in (0x43,):  # NET_LINK_EVENT
        if len(payload) >= 5:
            event_type = payload[1]
            state = payload[2] if len(payload) > 2 else 0
            print(f"    LINK_EVENT: type={event_type} state={state}")


# ════════════════════════════════════════════════════════════
#  PING
# ════════════════════════════════════════════════════════════

def cmd_ping(transport, args):
    resp, st = expect_response(transport, 0x00, b'\x00', timeout=3.0)
    output({**frame_info(resp), "status": status_str(st)})


# ════════════════════════════════════════════════════════════
#  Handle tracking
# ════════════════════════════════════════════════════════════

def _save_handle(args, handle):
    """Save handle if --save-as was specified."""
    save_as = getattr(args, 'save_as', None)
    if save_as and handle:
        _saved_handles[save_as] = handle
        if not _json_mode:
            print(f"  [saved as ${save_as}]")


# ════════════════════════════════════════════════════════════
#  Interactive session
# ════════════════════════════════════════════════════════════

def _parse_interactive_line(line):
    """Parse a line from interactive mode into an args namespace.
    Reuses the global argparse setup but with individual subparser parsing."""
    return line.strip().split()


def interactive_session(transport, global_args):
    """Run an interactive command loop. Parses each line as a CLI subcommand."""
    print("HEX-Bridge Network CLI — Interactive Mode")
    print(f"  port={global_args.port}, baud={global_args.baud}")
    print("  Type 'help' for commands, 'quit' to exit.\n")

    import shlex
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ('quit', 'exit', 'q'):
            break
        if line in ('help', 'h', '?'):
            print("  Commands: net-status, net-dns <host>, net-list-conns,")
            print("    tcp-server-open/close, tcp-client-connect/disconnect/send,")
            print("    tcp-list-clients, tcp-conn-status, tcp-kick-client,")
            print("    udp-server-open/close, udp-client-create/delete/send,")
            print("    ws-server-open/close, ws-client-connect/disconnect/send,")
            print("    ws-list-clients, ws-kick-client,")
            print("    mcp-baud, ping, listen, quit")
            print("  Handles: $name (saved with --save-as name)")
            continue

        try:
            tokens = shlex.split(line)
        except ValueError:
            tokens = line.split()

        # Build a fresh parser for this one-off command
        from argparse import ArgumentParser
        subparser = ArgumentParser(prog='')
        _register_subcommands(subparser)

        try:
            cmd_args = subparser.parse_args(tokens)
        except SystemExit:
            continue

        if not cmd_args.command:
            print("  Unknown command. Type 'help'.")
            continue

        _dispatch(transport, cmd_args)
        sys.stdout.flush()


# ════════════════════════════════════════════════════════════
#  Subcommand registration
# ════════════════════════════════════════════════════════════

def _register_subcommands(parser):
    """Register all subcommands on an argparse parser."""
    sub = parser.add_subparsers(dest='command')

    # NET
    p_nc = sub.add_parser('net-config')
    p_nc.add_argument('--dhcp', action='store_true')
    p_nc.add_argument('--ip'); p_nc.add_argument('--mask', default='255.255.255.0')
    p_nc.add_argument('--gateway', default='192.168.1.1')
    p_nc.add_argument('--dns1'); p_nc.add_argument('--dns2')

    p_nd = sub.add_parser('net-dns')
    p_nd.add_argument('hostname')

    p_ns = sub.add_parser('net-status')
    p_ns.add_argument('--index', type=int, default=None)

    sub.add_parser('net-list-conns')

    # TCP
    p_tso = sub.add_parser('tcp-server-open')
    p_tso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_tso.add_argument('--maxconn', type=int, default=5)
    p_tso.add_argument('--accept-mode', type=int, default=1)
    p_tso.add_argument('--keepalive', type=int, default=0)
    _add_save_as(p_tso)

    p_tsc = sub.add_parser('tcp-server-close')
    p_tsc.add_argument('--handle', type=str, required=True)
    p_tsc.add_argument('--force', type=int, default=0)

    p_tcc = sub.add_parser('tcp-client-connect')
    p_tcc.add_argument('--ip', required=True)
    p_tcc.add_argument('--port', dest='port_num', type=int, required=True)
    p_tcc.add_argument('--connect-timeout', type=int, default=5)
    p_tcc.add_argument('--keepalive', type=int, default=0)
    _add_save_as(p_tcc)

    p_td = sub.add_parser('tcp-disconnect')
    p_td.add_argument('--handle', type=str, required=True)
    p_td.add_argument('--method', type=int, default=0)

    p_ts = sub.add_parser('tcp-send')
    p_ts.add_argument('--handle', type=str, required=True)
    p_ts.add_argument('--data', default=None)
    p_ts.add_argument('--hex-data', default=None)

    p_tlc = sub.add_parser('tcp-list-clients')
    p_tlc.add_argument('--handle', type=str, required=True)

    p_tcs = sub.add_parser('tcp-conn-status')
    p_tcs.add_argument('--handle', type=str, required=True)

    p_ta = sub.add_parser('tcp-accept')
    p_ta.add_argument('--handle', type=str, required=True)
    p_ta.add_argument('--decision', type=int, default=0)

    p_tcp_close = sub.add_parser('tcp-close')
    p_tcp_close.add_argument('--handle', type=str, required=True)
    p_tcp_close.add_argument('--handle-type', type=int, default=0)
    p_tcp_close.add_argument('--force', type=int, default=0)

    p_tk = sub.add_parser('tcp-kick-client')
    p_tk.add_argument('--handle', type=str, required=True)
    p_tk.add_argument('--force', type=int, default=1)

    # UDP
    p_uso = sub.add_parser('udp-server-open')
    p_uso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_uso.add_argument('--broadcast', action='store_true')
    p_uso.add_argument('--multicast', default=None)
    _add_save_as(p_uso)

    p_usc = sub.add_parser('udp-server-close')
    p_usc.add_argument('--handle', type=str, required=True)

    p_ucc = sub.add_parser('udp-client-create')
    p_ucc.add_argument('--ip', required=True)
    p_ucc.add_argument('--port', dest='port_num', type=int, required=True)
    p_ucc.add_argument('--local-port', type=int, default=None)
    _add_save_as(p_ucc)

    p_ucd = sub.add_parser('udp-client-delete')
    p_ucd.add_argument('--handle', type=str, required=True)

    p_uss = sub.add_parser('udp-server-send')
    p_uss.add_argument('--handle', type=str, required=True)
    p_uss.add_argument('--ip', required=True)
    p_uss.add_argument('--port', dest='port_num', type=int, required=True)
    p_uss.add_argument('--data', default=None)
    p_uss.add_argument('--hex-data', default=None)

    p_ucs = sub.add_parser('udp-client-send')
    p_ucs.add_argument('--handle', type=str, required=True)
    p_ucs.add_argument('--addr-mode', type=int, default=0)
    p_ucs.add_argument('--ip')
    p_ucs.add_argument('--port', dest='port_num', type=int)
    p_ucs.add_argument('--data', default=None)
    p_ucs.add_argument('--hex-data', default=None)

    # WS
    p_wso = sub.add_parser('ws-server-open')
    p_wso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_wso.add_argument('--maxconn', type=int, default=5)
    p_wso.add_argument('--path', default='/')
    p_wso.add_argument('--subproto', default=None)
    _add_save_as(p_wso)

    p_wsc = sub.add_parser('ws-server-close')
    p_wsc.add_argument('--handle', type=str, required=True)
    p_wsc.add_argument('--force', type=int, default=0)

    p_wscc = sub.add_parser('ws-client-connect')
    p_wscc.add_argument('--ip', required=True)
    p_wscc.add_argument('--port', dest='port_num', type=int, required=True)
    p_wscc.add_argument('--path', default='/')
    _add_save_as(p_wscc)

    p_wscd = sub.add_parser('ws-client-disconnect')
    p_wscd.add_argument('--handle', type=str, required=True)
    p_wscd.add_argument('--close-code', type=int, default=1000)

    p_wss = sub.add_parser('ws-send')
    p_wss.add_argument('--handle', type=str, required=True)
    p_wss.add_argument('--msg-type', type=int, default=1)
    p_wss.add_argument('--data', default=None)
    p_wss.add_argument('--hex-data', default=None)

    p_wslc = sub.add_parser('ws-list-clients')
    p_wslc.add_argument('--handle', type=str, required=True)

    p_wsk = sub.add_parser('ws-kick-client')
    p_wsk.add_argument('--handle', type=str, required=True)
    p_wsk.add_argument('--force', type=int, default=1)

    # System
    p_ping = sub.add_parser('ping', help='Send PING to verify connectivity')
    p_ping.add_argument('--data', default=None)

    p_ls = sub.add_parser('listen', help='Listen for UBCP event frames')
    p_ls.add_argument('--events', default=None, help='Comma-separated hex cmd codes, e.g. 0x55,0x75')
    p_ls.add_argument('--cmd', type=lambda x: int(x, 0), default=None, help='Single cmd code filter')
    p_ls.add_argument('--all', action='store_true', help='Listen for all event types')
    p_ls.add_argument('--timeout', dest='timeout_val', type=int, default=30, help='Listen duration in seconds')

    p_mb = sub.add_parser('mcp-baud')
    p_mb.add_argument('--set', dest='set_baud', type=int, default=None)
    p_mb.add_argument('--probe', action='store_true')


def _add_save_as(parser):
    """Add --save-as option to commands that return a handle."""
    parser.add_argument('--save-as', default=None, help='Save handle for later reference as $name')


# ════════════════════════════════════════════════════════════
#  Command dispatch
# ════════════════════════════════════════════════════════════

DISPATCH = {
    'net-config':           cmd_net_config,
    'net-dns':              cmd_net_dns,
    'net-status':           cmd_net_status,
    'net-list-conns':       cmd_net_list_conns,
    'tcp-server-open':      cmd_tcp_server_open,
    'tcp-server-close':     cmd_tcp_server_close,
    'tcp-client-connect':   cmd_tcp_client_connect,
    'tcp-disconnect':       cmd_tcp_disconnect,
    'tcp-accept':           cmd_tcp_accept,
    'tcp-close':            cmd_tcp_close,
    'tcp-kick-client':      cmd_tcp_kick_client,
    'tcp-send':             cmd_tcp_send,
    'tcp-list-clients':     cmd_tcp_list_clients,
    'tcp-conn-status':      cmd_tcp_conn_status,
    'udp-server-open':      cmd_udp_server_open,
    'udp-server-close':     cmd_udp_server_close,
    'udp-client-create':    cmd_udp_client_create,
    'udp-client-delete':    cmd_udp_client_delete,
    'udp-server-send':      cmd_udp_server_send,
    'udp-client-send':      cmd_udp_client_send,
    'ws-server-open':       cmd_ws_server_open,
    'ws-server-close':      cmd_ws_server_close,
    'ws-client-connect':    cmd_ws_client_connect,
    'ws-client-disconnect': cmd_ws_client_disconnect,
    'ws-send':              cmd_ws_send,
    'ws-list-clients':      cmd_ws_list_clients,
    'ws-kick-client':       cmd_ws_kick_client,
    'mcp-baud':             cmd_mcp_baud,
    'ping':                 cmd_ping,
    'listen':               cmd_listen,
}


def _dispatch(transport, args):
    """Route a command to its handler."""
    func = DISPATCH.get(args.command)
    if func:
        func(transport, args)
    else:
        print(f"Unknown command: {args.command}")


# ════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════

def main():
    global _json_mode

    parser = argparse.ArgumentParser(
        description='HEX-Bridge Network CLI — UBCP v2.0 MCP Command Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Examples:\n'
               '  %(prog)s net-status\n'
               '  %(prog)s tcp-server-open --port 9191\n'
               '  %(prog)s --json net-list-conns\n'
               '  %(prog)s -i\n'
               '  %(prog)s listen --events 0x55,0x75')
    parser.add_argument('--port', default='COM35', help='MCP COM port (default: COM35)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    parser.add_argument('--timeout', type=int, default=5, help='Response timeout in seconds (default: 5)')
    parser.add_argument('--json', action='store_true', help='Machine-readable JSON output')
    parser.add_argument('-i', '--interactive', action='store_true', help='Interactive session mode')

    _register_subcommands(parser)
    args = parser.parse_args()

    _json_mode = args.json

    if not args.command:
        parser.print_help()
        return

    # Handle baud probe before opening transport
    baud_rate = args.baud
    if 'probe' in args and args.probe:
        detected = probe_baud_rate(args.port)
        if detected:
            baud_rate = detected
        else:
            print(f"Baud rate probe failed on {args.port}")
            return

    transport = MCPTransport(port=args.port, baudrate=baud_rate)
    transport.open()

    try:
        if args.interactive:
            interactive_session(transport, args)
        else:
            _dispatch(transport, args)
    except TimeoutError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        transport.close()


if __name__ == '__main__':
    main()
