#!/usr/bin/env python3
"""
hex-bridge-network-cli.py — HEX-Bridge Network CLI Tool

Sends UBCP v2.0 network commands to the HEX-Bridge device over MCP COM35.
Supports NET_STATUS, NET_LIST_CONNS, TCP server/client, UDP, WebSocket ops,
and MCP baud rate configuration with auto-probe.

Usage:
    python hex-bridge-network-cli.py --port COM35 net-status
    python hex-bridge-network-cli.py --port COM35 tcp-server-open --port 8080
    python hex-bridge-network-cli.py --port COM35 tcp-client-connect --ip 192.168.1.100 --port 8080
    python hex-bridge-network-cli.py --port COM35 net-list-conns
    python hex-bridge-network-cli.py --port COM35 mcp-baud --probe
    python hex-bridge-network-cli.py --port COM35 mcp-baud --set 921600
"""

import sys
import os
import argparse
import serial
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'test'))
from ubcp_client import UBCPBuilder, UBCPParser, SOF_0, SOF_1, EOF, ESC, ESC_EOF, ESC_ESC
from ubcp_client import VERSION, FLAG_DIR, FLAG_ACK
from mcp_transport import MCPTransport

# ── Build/parse helpers ──

_seq_counter = 1

def mk_frame(cmd, payload=b'', channel=0):
    global _seq_counter
    seq = _seq_counter
    _seq_counter += 1
    return UBCPBuilder.build_request(seq, cmd, channel, payload)

# Create a parser for each connection, but MCPTransport has its own parser.
# We'll just use MCPTransport's recv_frame and build our own frames.


def send_cmd(transport, cmd, payload=b'', channel=0, timeout=5.0):
    """Send a command and return the response frame."""
    transport.flush_input()
    frame = mk_frame(cmd, payload, channel)
    transport.send(frame)
    return transport.recv_frame(timeout=timeout)


def ip_to_int(ip_str):
    parts = ip_str.split('.')
    if len(parts) != 4:
        raise ValueError("Invalid IP: " + ip_str)
    return (int(parts[0]) << 24) | (int(parts[1]) << 16) | (int(parts[2]) << 8) | int(parts[3])


def int_to_ip(val):
    return f"{(val >> 24) & 0xFF}.{(val >> 16) & 0xFF}.{(val >> 8) & 0xFF}.{val & 0xFF}"


# ════════════════════════════════════════════════════════════
#  Commands
# ════════════════════════════════════════════════════════════

def cmd_net_config(transport, args):
    if args.dhcp:
        payload = bytes([0x00, 0x00])
    else:
        ip = ip_to_int(args.ip)
        mask = ip_to_int(args.mask)
        gw = ip_to_int(args.gateway)
        dns1 = ip_to_int(args.dns1) if args.dns1 else 0
        dns2 = ip_to_int(args.dns2) if args.dns2 else 0
        payload = bytes([0x00, 0x01])
        payload += bytes([(ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF])
        payload += bytes([(mask >> 24) & 0xFF, (mask >> 16) & 0xFF, (mask >> 8) & 0xFF, mask & 0xFF])
        payload += bytes([(gw >> 24) & 0xFF, (gw >> 16) & 0xFF, (gw >> 8) & 0xFF, gw & 0xFF])
        payload += bytes([(dns1 >> 24) & 0xFF, (dns1 >> 16) & 0xFF, (dns1 >> 8) & 0xFF, dns1 & 0xFF])
        payload += bytes([(dns2 >> 24) & 0xFF, (dns2 >> 16) & 0xFF, (dns2 >> 8) & 0xFF, dns2 & 0xFF])
    resp = send_cmd(transport, 0x40, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 1:
            print(f"  Status={'OK' if resp.payload[0] == 0 else f'ERR 0x{resp.payload[0]:02X}'}")
    else:
        print("No response")


def cmd_net_dns(transport, args):
    hostname = args.hostname.encode('utf-8')[:253]
    payload = bytes([len(hostname)]) + hostname
    resp = send_cmd(transport, 0x42, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 2:
            status = resp.payload[0]
            count = resp.payload[1]
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, AddrCount={count}")
            for i in range(count):
                off = 2 + i * 4
                ip = int_to_ip(int.from_bytes(resp.payload[off:off+4], 'big'))
                print(f"    [{i}] {ip}")
    else:
        print("No response")


def cmd_net_status(transport, args):
    idx = args.index if args.index is not None else 0
    payload = bytes([idx])
    resp = send_cmd(transport, 0x41, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 19:
            link = 'UP' if resp.payload[3] else 'DOWN'
            conn_state = ['未连接', '已连接', '获取IP中'][resp.payload[4] % 3]
            ip = int_to_ip(int.from_bytes(resp.payload[5:9], 'big'))
            mask = int_to_ip(int.from_bytes(resp.payload[9:13], 'big'))
            mac = ':'.join(f'{b:02X}' for b in resp.payload[13:19])
            print(f"  Link={link}, Conn={conn_state}, IP={ip}, Mask={mask}, MAC={mac}")
    else:
        print("No response")


def cmd_net_list_conns(transport, args):
    resp = send_cmd(transport, 0x44, b'')
    if resp:
        print_resp(resp)
        if resp.payload_len >= 2:
            count = resp.payload[1]
            print(f"  Connections: {count}")
            for i in range(count):
                off = 2 + i * 10
                ct = resp.payload[off]
                ct_names = {0: 'TCP_SERVER', 1: 'TCP_CONN', 2: 'UDP_SERVER',
                            3: 'UDP_CLIENT', 4: 'WS_SERVER', 5: 'WS_CONN'}
                handle = int.from_bytes(resp.payload[off+1:off+3], 'big')
                parent = int.from_bytes(resp.payload[off+3:off+5], 'big')
                lport  = int.from_bytes(resp.payload[off+5:off+7], 'big')
                rmt_ip  = int.from_bytes(resp.payload[off+7:off+11], 'big')
                print(f"    [{ct_names.get(ct, hex(ct))}] handle=0x{handle:04X} "
                      f"parent=0x{parent:04X} lport={lport} rmt_ip={int_to_ip(rmt_ip)}")
    else:
        print("No response")


def cmd_tcp_server_open(transport, args):
    port = args.port_num
    maxconn = args.maxconn
    accept = args.accept_mode
    keepalive = args.keepalive
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, maxconn, accept, keepalive])
    resp = send_cmd(transport, 0x50, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 5:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            actual = int.from_bytes(resp.payload[3:5], 'big')
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, port={actual}")
    else:
        print("No response")


def cmd_tcp_server_close(transport, args):
    handle = args.handle
    force = args.force
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, force])
    resp = send_cmd(transport, 0x51, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_tcp_client_connect(transport, args):
    ip = ip_to_int(args.ip)
    port = args.port_num
    timeout = args.connect_timeout
    keepalive = args.keepalive
    payload = bytes([
        (ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF,
        (port >> 8) & 0xFF, port & 0xFF,
        timeout, keepalive,
    ])

    # Wait for response and also ACCEPT event
    resp = send_cmd(transport, 0x52, payload, timeout=10.0)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 9:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            local_ip = int_to_ip(int.from_bytes(resp.payload[3:7], 'big'))
            local_port = int.from_bytes(resp.payload[7:9], 'big')
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, local={local_ip}:{local_port}")
    else:
        print("No response")


def cmd_tcp_disconnect(transport, args):
    handle = args.handle
    method = args.method
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, method])
    resp = send_cmd(transport, 0x53, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_tcp_accept(transport, args):
    handle = args.handle
    decision = args.decision
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, decision])
    resp = send_cmd(transport, 0x56, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_tcp_close(transport, args):
    handle = args.handle
    htype = args.handle_type
    force = args.force
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, htype, force])
    resp = send_cmd(transport, 0x57, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_tcp_kick_client(transport, args):
    handle = args.handle
    force = args.force
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, force])
    resp = send_cmd(transport, 0x5A, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_tcp_send(transport, args):
    handle = args.handle
    data = args.data.encode('utf-8') if args.data else b''
    if args.hex_data:
        data = bytes.fromhex(args.hex_data.replace(' ', ''))
    plen = len(data)
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, (plen >> 8) & 0xFF, plen & 0xFF]) + data
    resp = send_cmd(transport, 0x54, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 3:
            sent = int.from_bytes(resp.payload[1:3], 'big')
            status = 'OK' if resp.payload[0] == 0 else f'ERR 0x{resp.payload[0]:02X}'
            print(f"  Status={status}, sent={sent} bytes")
    else:
        print("No response")


def cmd_tcp_list_clients(transport, args):
    handle = args.handle
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF])
    resp = send_cmd(transport, 0x59, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 2:
            count = resp.payload[1]
            print(f"  Clients: {count}")
            for i in range(count):
                off = 2 + i * 10
                ch = int.from_bytes(resp.payload[off:off+2], 'big')
                cip = int_to_ip(int.from_bytes(resp.payload[off+2:off+6], 'big'))
                cp = int.from_bytes(resp.payload[off+6:off+8], 'big')
                ct = int.from_bytes(resp.payload[off+8:off+10], 'big')
                print(f"    handle=0x{ch:04X}, ip={cip}:{cp}, uptime={ct}s")
    else:
        print("No response")


def cmd_tcp_conn_status(transport, args):
    handle = args.handle
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF])
    resp = send_cmd(transport, 0x5B, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 22:
            states = {0: 'ESTABLISHED', 1: 'CLOSING', 2: 'CLOSED'}
            cs = resp.payload[1]
            tx = int.from_bytes(resp.payload[2:6], 'big')
            rx = int.from_bytes(resp.payload[6:10], 'big')
            rip = int_to_ip(int.from_bytes(resp.payload[10:14], 'big'))
            rp = int.from_bytes(resp.payload[14:16], 'big')
            lp = int.from_bytes(resp.payload[16:18], 'big')
            ut = int.from_bytes(resp.payload[18:22], 'big')
            print(f"  State={states.get(cs, hex(cs))}, Tx={tx}, Rx={rx}")
            print(f"  Remote={rip}:{rp}, LocalPort={lp}, Uptime={ut}s")
    else:
        print("No response")


def cmd_udp_server_open(transport, args):
    port = args.port_num
    broadcast = 1 if args.broadcast else 0
    mc = ip_to_int(args.multicast) if args.multicast else 0
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, broadcast,
                     (mc >> 24) & 0xFF, (mc >> 16) & 0xFF, (mc >> 8) & 0xFF, mc & 0xFF])
    resp = send_cmd(transport, 0x60, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 5:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            actual = int.from_bytes(resp.payload[3:5], 'big')
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, port={actual}")
    else:
        print("No response")


def cmd_udp_server_close(transport, args):
    handle = args.handle
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF])
    resp = send_cmd(transport, 0x61, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_udp_client_create(transport, args):
    ip = ip_to_int(args.ip)
    port = args.port_num
    local_port = args.local_port if args.local_port else 0
    payload = bytes([
        (ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF,
        (port >> 8) & 0xFF, port & 0xFF,
        (local_port >> 8) & 0xFF, local_port & 0xFF,
    ])
    resp = send_cmd(transport, 0x62, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 5:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            actual = int.from_bytes(resp.payload[3:5], 'big')
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, local_port={actual}")
    else:
        print("No response")


def cmd_udp_client_delete(transport, args):
    handle = args.handle
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF])
    resp = send_cmd(transport, 0x63, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_udp_server_send(transport, args):
    handle = args.handle
    ip = ip_to_int(args.ip)
    port = args.port_num
    data = args.data.encode('utf-8') if args.data else b''
    if args.hex_data:
        data = bytes.fromhex(args.hex_data.replace(' ', ''))
    plen = len(data)
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF,
                     (ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF,
                     (port >> 8) & 0xFF, port & 0xFF,
                     (plen >> 8) & 0xFF, plen & 0xFF]) + data
    resp = send_cmd(transport, 0x64, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 3:
            sent = int.from_bytes(resp.payload[1:3], 'big')
            status = 'OK' if resp.payload[0] == 0 else f'ERR 0x{resp.payload[0]:02X}'
            print(f"  Status={status}, sent={sent} bytes")
    else:
        print("No response")


def cmd_udp_client_send(transport, args):
    handle = args.handle
    addr_mode = args.addr_mode
    data = args.data.encode('utf-8') if args.data else b''
    if args.hex_data:
        data = bytes.fromhex(args.hex_data.replace(' ', ''))
    plen = len(data)
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, addr_mode])
    if addr_mode == 1:
        ip = ip_to_int(args.ip)
        port = args.port_num
        payload += bytes([(ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF,
                          (port >> 8) & 0xFF, port & 0xFF])
    payload += bytes([(plen >> 8) & 0xFF, plen & 0xFF]) + data
    resp = send_cmd(transport, 0x66, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 3:
            sent = int.from_bytes(resp.payload[1:3], 'big')
            status = 'OK' if resp.payload[0] == 0 else f'ERR 0x{resp.payload[0]:02X}'
            print(f"  Status={status}, sent={sent} bytes")
    else:
        print("No response")


def cmd_ws_server_open(transport, args):
    port = args.port_num
    maxconn = args.maxconn
    path_str = args.path or '/'
    path = path_str.encode('utf-8')[:63]
    subproto = (args.subproto or '').encode('utf-8')[:63]
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, maxconn, len(path)]) + path + bytes([len(subproto)]) + subproto
    resp = send_cmd(transport, 0x70, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 5:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            actual = int.from_bytes(resp.payload[3:5], 'big')
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, port={actual}")
    else:
        print("No response")


def cmd_ws_client_connect(transport, args):
    ip = ip_to_int(args.ip)
    port = args.port_num
    path_str = args.path or '/'
    path = path_str.encode('utf-8')[:63]
    plen = 7 + len(path)
    payload = bytes([
        (ip >> 24) & 0xFF, (ip >> 16) & 0xFF, (ip >> 8) & 0xFF, ip & 0xFF,
        (port >> 8) & 0xFF, port & 0xFF,
        len(path),
    ]) + path + b'\x00'  # HeaderLen=0
    resp = send_cmd(transport, 0x72, payload, timeout=10.0)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 4:
            status = resp.payload[0]
            handle = int.from_bytes(resp.payload[1:3], 'big')
            result = resp.payload[3]
            print(f"  Status={'OK' if status == 0 else f'ERR 0x{status:02X}'}, "
                  f"handle=0x{handle:04X}, result={result}")
    else:
        print("No response")


def cmd_ws_server_close(transport, args):
    handle = args.handle
    force = args.force
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, force])
    resp = send_cmd(transport, 0x71, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_ws_client_disconnect(transport, args):
    handle = args.handle
    close_code = args.close_code
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF,
                     (close_code >> 8) & 0xFF, close_code & 0xFF])
    resp = send_cmd(transport, 0x73, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_ws_send(transport, args):
    handle = args.handle
    msg_type = args.msg_type
    data = args.data.encode('utf-8') if args.data else b''
    if args.hex_data:
        data = bytes.fromhex(args.hex_data.replace(' ', ''))
    plen = len(data)
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, msg_type,
                     (plen >> 8) & 0xFF, plen & 0xFF]) + data
    resp = send_cmd(transport, 0x74, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 3:
            sent = int.from_bytes(resp.payload[1:3], 'big')
            status = 'OK' if resp.payload[0] == 0 else f'ERR 0x{resp.payload[0]:02X}'
            print(f"  Status={status}, sent={sent} bytes")
    else:
        print("No response")


def cmd_ws_list_clients(transport, args):
    handle = args.handle
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF])
    resp = send_cmd(transport, 0x78, payload)
    if resp:
        print_resp(resp)
        if resp.payload_len >= 2:
            count = resp.payload[1]
            print(f"  Clients: {count}")
            for i in range(count):
                off = 2 + i * 12
                ch = int.from_bytes(resp.payload[off:off+2], 'big')
                cip = int_to_ip(int.from_bytes(resp.payload[off+2:off+6], 'big'))
                cp = int.from_bytes(resp.payload[off+6:off+8], 'big')
                sub = resp.payload[off+8]
                plen = resp.payload[off+9]
                ct = int.from_bytes(resp.payload[off+10:off+12], 'big')
                print(f"    handle=0x{ch:04X}, ip={cip}:{cp}, sub_proto={sub}, "
                      f"path_len={plen}, uptime={ct}s")
    else:
        print("No response")


def cmd_ws_kick_client(transport, args):
    handle = args.handle
    force = args.force
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, force])
    resp = send_cmd(transport, 0x79, payload)
    if resp:
        print_resp(resp)
    else:
        print("No response")


def cmd_mcp_baud(transport, args):
    """Get or set the MCP UART baud rate via UBCP config (key=0x12)."""
    group = 0x00  # system group
    key = 0x12    # UBCP_CFGKEY_MCP_BAUD_RATE

    if args.set_baud is not None:
        new_baud = args.set_baud
        if new_baud < 9600 or new_baud > 5000000:
            print(f"Error: baud rate {new_baud} out of range (9600-5000000)")
            return
        val_bytes = bytes([(new_baud >> 24) & 0xFF, (new_baud >> 16) & 0xFF,
                           (new_baud >> 8) & 0xFF, new_baud & 0xFF])
        payload = bytes([group, key, 0x00, 0x04]) + val_bytes
        resp = send_cmd(transport, 0x03, payload)
        if resp and resp.payload_len >= 1:
            if resp.payload[0] == 0:
                print(f"MCP baud rate set to {new_baud} (reboot required)")
            else:
                print(f"SET_CONFIG failed: ERR 0x{resp.payload[0]:02X}")
        else:
            print("No response")
    else:
        # GET_CONFIG
        resp = send_cmd(transport, 0x02, bytes([group, key]))
        if resp and resp.payload_len >= 8:
            status = resp.payload[0]
            rsp_group = resp.payload[1]
            rsp_key = resp.payload[2]
            rsp_valuelen = (resp.payload[3] << 8) | resp.payload[4]
            if status == 0 and rsp_valuelen == 4:
                baud = (resp.payload[5] << 24) | (resp.payload[6] << 16) | \
                       (resp.payload[7] << 8) | resp.payload[8]
                print(f"MCP baud rate: {baud}")
            else:
                print(f"MCP baud rate: unknown (status=0x{status:02X}, valuelen={rsp_valuelen})")
        else:
            print("No response")


def probe_baud_rate(port, rates=None, ping_timeout=2.0):
    """Try common baud rates, send a UBCP PING, return the rate that works."""
    if rates is None:
        rates = [921600, 460800, 230400, 115200, 57600, 38400, 19200, 9600]

    print(f"Probing baud rates on {port}...")
    pkt = UBCPBuilder.build_request(1, 0x00, 0, b'')

    for rate in rates:
        try:
            ser = serial.Serial(port=port, baudrate=rate, bytesize=serial.EIGHTBITS,
                                parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                                timeout=0.5)
            ser.reset_input_buffer()
            ser.write(pkt)
            ser.flush()

            parser = UBCPParser()
            deadline = time.time() + ping_timeout
            matched = False
            while time.time() < deadline:
                b = ser.read(1)
                if not b:
                    continue
                frame = parser.feed(b[0])
                if frame is not None and frame.cmd_code == 0x00 and frame.is_response:
                    print(f"  Found: {rate} bps")
                    matched = True
                    break
            ser.close()
            if matched:
                return rate
        except Exception as e:
            print(f"  {rate}: {e}")

    print("No response at any baud rate")
    return None


def print_resp(frame):
    """Print frame details."""
    if frame is None:
        print("  (null frame)")
        return
    print(f"  [Frame] cmd=0x{frame.cmd_code:02X} flags=0x{frame.flags:02X} "
          f"seq=0x{frame.seq_num:04X} plen={frame.payload_len} "
          f"payload={frame.payload[:32].hex()}")


# ════════════════════════════════════════════════════════════
#  Main
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='HEX-Bridge Network CLI')
    parser.add_argument('--port', default='COM35', help='MCP COM port (default: COM35)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')

    sub = parser.add_subparsers(dest='command')

    # Network Config
    p_nc = sub.add_parser('net-config', help='Configure network (DHCP or static IP) (NET_CONFIG 0x40)')
    p_nc.add_argument('--dhcp', action='store_true', help='Switch to DHCP mode')
    p_nc.add_argument('--ip', help='Static IP address')
    p_nc.add_argument('--mask', default='255.255.255.0', help='Subnet mask')
    p_nc.add_argument('--gateway', default='192.168.1.1', help='Gateway')
    p_nc.add_argument('--dns1', help='Primary DNS')
    p_nc.add_argument('--dns2', help='Secondary DNS')

    p_nd = sub.add_parser('net-dns', help='DNS resolve hostname (NET_DNS 0x42)')
    p_nd.add_argument('hostname', help='Hostname to resolve')

    p_ns = sub.add_parser('net-status', help='Query network status (NET_STATUS 0x41)')
    p_ns.add_argument('--index', type=int, default=None, help='Interface index (default 0=ETH0, 0xFF=all)')

    p_nlc = sub.add_parser('net-list-conns', help='List all active connections (0x44)')

    # TCP
    p_tso = sub.add_parser('tcp-server-open', help='Open TCP server (0x50)')
    p_tso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_tso.add_argument('--maxconn', type=int, default=5)
    p_tso.add_argument('--accept-mode', type=int, default=1, help='0=manual, 1=auto')
    p_tso.add_argument('--keepalive', type=int, default=0, help='KeepAlive interval in seconds')

    p_tsc = sub.add_parser('tcp-server-close', help='Close TCP server (0x51)')
    p_tsc.add_argument('--handle', type=lambda x: int(x, 0), required=True, help='Server handle (hex or dec)')
    p_tsc.add_argument('--force', type=int, default=0, help='1=force close')

    p_tcc = sub.add_parser('tcp-client-connect', help='TCP client connect (0x52)')
    p_tcc.add_argument('--ip', required=True, help='Destination IP')
    p_tcc.add_argument('--port', dest='port_num', type=int, required=True)
    p_tcc.add_argument('--connect-timeout', type=int, default=5)
    p_tcc.add_argument('--keepalive', type=int, default=0)

    p_td = sub.add_parser('tcp-disconnect', help='TCP disconnect (0x53)')
    p_td.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_td.add_argument('--method', type=int, default=0, help='0=graceful FIN, 1=force RST')

    p_ts = sub.add_parser('tcp-send', help='TCP send (0x54)')
    p_ts.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_ts.add_argument('--data', default=None, help='Text data to send')
    p_ts.add_argument('--hex-data', default=None, help='Hex data to send')

    p_tlc = sub.add_parser('tcp-list-clients', help='TCP list clients (0x59)')
    p_tlc.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_tcs = sub.add_parser('tcp-conn-status', help='TCP connection status (0x5B)')
    p_tcs.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_ta = sub.add_parser('tcp-accept', help='TCP manual accept/reject (0x56)')
    p_ta.add_argument('--handle', type=lambda x: int(x, 0), required=True, help='Client handle')
    p_ta.add_argument('--decision', type=int, default=0, help='0=accept, 1=reject')

    p_tcp_close = sub.add_parser('tcp-close', help='TCP generic close (0x57)')
    p_tcp_close.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_tcp_close.add_argument('--handle-type', type=int, default=0, help='0=connection, 1=server')
    p_tcp_close.add_argument('--force', type=int, default=0, help='0=graceful, 1=force')

    p_tk = sub.add_parser('tcp-kick-client', help='TCP kick client (0x5A)')
    p_tk.add_argument('--handle', type=lambda x: int(x, 0), required=True, help='Client handle')
    p_tk.add_argument('--force', type=int, default=1, help='0=graceful, 1=force')

    # UDP
    p_uso = sub.add_parser('udp-server-open', help='Open UDP server (0x60)')
    p_uso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_uso.add_argument('--broadcast', action='store_true')
    p_uso.add_argument('--multicast', default=None, help='Multicast group IP (e.g. 224.0.0.1)')

    p_usc = sub.add_parser('udp-server-close', help='Close UDP server (0x61)')
    p_usc.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_ucc = sub.add_parser('udp-client-create', help='Create UDP client (0x62)')
    p_ucc.add_argument('--ip', required=True, help='Default destination IP')
    p_ucc.add_argument('--port', dest='port_num', type=int, required=True, help='Default destination port')
    p_ucc.add_argument('--local-port', type=int, default=None, help='Local port (0=auto)')

    p_ucd = sub.add_parser('udp-client-delete', help='Delete UDP client (0x63)')
    p_ucd.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_uss = sub.add_parser('udp-server-send', help='UDP server send (0x64)')
    p_uss.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_uss.add_argument('--ip', required=True, help='Destination IP')
    p_uss.add_argument('--port', dest='port_num', type=int, required=True, help='Destination port')
    p_uss.add_argument('--data', default=None, help='Text data to send')
    p_uss.add_argument('--hex-data', default=None, help='Hex data to send')

    p_ucs = sub.add_parser('udp-client-send', help='UDP client send (0x66)')
    p_ucs.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_ucs.add_argument('--addr-mode', type=int, default=0, help='0=use default addr, 1=override')
    p_ucs.add_argument('--ip', help='Override destination IP (addr-mode=1)')
    p_ucs.add_argument('--port', dest='port_num', type=int, help='Override destination port (addr-mode=1)')
    p_ucs.add_argument('--data', default=None, help='Text data to send')
    p_ucs.add_argument('--hex-data', default=None, help='Hex data to send')

    # WebSocket
    p_wso = sub.add_parser('ws-server-open', help='Open WebSocket server (0x70)')
    p_wso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_wso.add_argument('--maxconn', type=int, default=5)
    p_wso.add_argument('--path', default='/')
    p_wso.add_argument('--subproto', default=None, help='Sub-protocol name')

    p_wsc = sub.add_parser('ws-server-close', help='Close WebSocket server (0x71)')
    p_wsc.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_wsc.add_argument('--force', type=int, default=0, help='1=force close')

    p_wscc = sub.add_parser('ws-client-connect', help='WebSocket client connect (0x72)')
    p_wscc.add_argument('--ip', required=True)
    p_wscc.add_argument('--port', dest='port_num', type=int, required=True)
    p_wscc.add_argument('--path', default='/')

    p_wscd = sub.add_parser('ws-client-disconnect', help='WebSocket client disconnect (0x73)')
    p_wscd.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_wscd.add_argument('--close-code', type=int, default=1000, help='WebSocket close code (default 1000)')

    p_wss = sub.add_parser('ws-send', help='WebSocket send (0x74)')
    p_wss.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_wss.add_argument('--msg-type', type=int, default=1, help='1=Text, 2=Binary, 9=Ping, 10=Pong, 8=Close')
    p_wss.add_argument('--data', default=None, help='Text data to send')
    p_wss.add_argument('--hex-data', default=None, help='Hex data to send')

    p_wslc = sub.add_parser('ws-list-clients', help='WebSocket list clients (0x78)')
    p_wslc.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_wsk = sub.add_parser('ws-kick-client', help='WebSocket kick client (0x79)')
    p_wsk.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_wsk.add_argument('--force', type=int, default=1, help='0=graceful, 1=force')

    # MCP Baud Rate
    p_mb = sub.add_parser('mcp-baud', help='Get/set MCP UART baud rate (GET_CONFIG/SET_CONFIG 0x02/0x03)')
    p_mb.add_argument('--set', dest='set_baud', type=int, default=None,
                      help='Set baud rate (9600-5000000, reboot required)')
    p_mb.add_argument('--probe', action='store_true',
                      help='Probe and auto-detect baud rate before get/set')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Handle baud probe before opening transport
    baud_rate = args.baud
    if hasattr(args, 'probe') and args.probe:
        detected = probe_baud_rate(args.port)
        if detected:
            baud_rate = detected
        else:
            print(f"Baud rate probe failed on {args.port}")
            return

    transport = MCPTransport(port=args.port, baudrate=baud_rate)
    transport.open()

    try:
        if args.command == 'net-config':
            cmd_net_config(transport, args)
        elif args.command == 'net-dns':
            cmd_net_dns(transport, args)
        elif args.command == 'net-status':
            cmd_net_status(transport, args)
        elif args.command == 'net-list-conns':
            cmd_net_list_conns(transport, args)
        elif args.command == 'tcp-server-open':
            cmd_tcp_server_open(transport, args)
        elif args.command == 'tcp-server-close':
            cmd_tcp_server_close(transport, args)
        elif args.command == 'tcp-client-connect':
            cmd_tcp_client_connect(transport, args)
        elif args.command == 'tcp-disconnect':
            cmd_tcp_disconnect(transport, args)
        elif args.command == 'tcp-accept':
            cmd_tcp_accept(transport, args)
        elif args.command == 'tcp-close':
            cmd_tcp_close(transport, args)
        elif args.command == 'tcp-kick-client':
            cmd_tcp_kick_client(transport, args)
        elif args.command == 'tcp-send':
            cmd_tcp_send(transport, args)
        elif args.command == 'tcp-list-clients':
            cmd_tcp_list_clients(transport, args)
        elif args.command == 'tcp-conn-status':
            cmd_tcp_conn_status(transport, args)
        elif args.command == 'udp-server-open':
            cmd_udp_server_open(transport, args)
        elif args.command == 'udp-server-close':
            cmd_udp_server_close(transport, args)
        elif args.command == 'udp-client-create':
            cmd_udp_client_create(transport, args)
        elif args.command == 'udp-client-delete':
            cmd_udp_client_delete(transport, args)
        elif args.command == 'udp-server-send':
            cmd_udp_server_send(transport, args)
        elif args.command == 'udp-client-send':
            cmd_udp_client_send(transport, args)
        elif args.command == 'ws-server-open':
            cmd_ws_server_open(transport, args)
        elif args.command == 'ws-server-close':
            cmd_ws_server_close(transport, args)
        elif args.command == 'ws-client-connect':
            cmd_ws_client_connect(transport, args)
        elif args.command == 'ws-client-disconnect':
            cmd_ws_client_disconnect(transport, args)
        elif args.command == 'ws-send':
            cmd_ws_send(transport, args)
        elif args.command == 'ws-list-clients':
            cmd_ws_list_clients(transport, args)
        elif args.command == 'ws-kick-client':
            cmd_ws_kick_client(transport, args)
        elif args.command == 'mcp-baud':
            cmd_mcp_baud(transport, args)
        else:
            print(f"Unknown command: {args.command}")
    finally:
        transport.close()


if __name__ == '__main__':
    main()
