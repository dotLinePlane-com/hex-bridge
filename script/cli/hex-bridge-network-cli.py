#!/usr/bin/env python3
"""
hex-bridge-network-cli.py — HEX-Bridge Network CLI Tool

Sends UBCP v2.0 network commands to the HEX-Bridge device over MCP COM35.
Supports NET_STATUS, NET_LIST_CONNS, TCP server/client, UDP, WebSocket ops.

Usage:
    python hex-bridge-network-cli.py --port COM35 net-status
    python hex-bridge-network-cli.py --port COM35 tcp-server-open --port 8080
    python hex-bridge-network-cli.py --port COM35 tcp-client-connect --ip 192.168.1.100 --port 8080
    python hex-bridge-network-cli.py --port COM35 net-list-conns
"""

import sys
import os
import argparse

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

def cmd_net_status(transport, args):
    payload = b'\x00'  # InterfaceIndex = 0 (ETH0)
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
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, maxconn, accept, 0])
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
    payload = bytes([(handle >> 8) & 0xFF, handle & 0xFF, 0])  # graceful
    resp = send_cmd(transport, 0x53, payload)
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
    mc = 0  # no multicast for now
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, broadcast, 0, 0, 0, 0])
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


def cmd_ws_server_open(transport, args):
    port = args.port_num
    maxconn = args.maxconn
    path_str = args.path or '/'
    path = path_str.encode('utf-8')[:63]
    plen = 4 + len(path)
    payload = bytes([(port >> 8) & 0xFF, port & 0xFF, maxconn, len(path)]) + path + b'\x00'  # SubProtoLen=0
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
    p_ns = sub.add_parser('net-status', help='Query network status (NET_STATUS 0x41)')

    p_nlc = sub.add_parser('net-list-conns', help='List all active connections (0x44)')

    # TCP
    p_tso = sub.add_parser('tcp-server-open', help='Open TCP server (0x50)')
    p_tso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_tso.add_argument('--maxconn', type=int, default=5)
    p_tso.add_argument('--accept-mode', type=int, default=1, help='0=manual, 1=auto')

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

    p_ts = sub.add_parser('tcp-send', help='TCP send (0x54)')
    p_ts.add_argument('--handle', type=lambda x: int(x, 0), required=True)
    p_ts.add_argument('--data', default=None, help='Text data to send')
    p_ts.add_argument('--hex-data', default=None, help='Hex data to send')

    p_tlc = sub.add_parser('tcp-list-clients', help='TCP list clients (0x59)')
    p_tlc.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    p_tcs = sub.add_parser('tcp-conn-status', help='TCP connection status (0x5B)')
    p_tcs.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    # UDP
    p_uso = sub.add_parser('udp-server-open', help='Open UDP server (0x60)')
    p_uso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_uso.add_argument('--broadcast', action='store_true')

    p_usc = sub.add_parser('udp-server-close', help='Close UDP server (0x61)')
    p_usc.add_argument('--handle', type=lambda x: int(x, 0), required=True)

    # WebSocket
    p_wso = sub.add_parser('ws-server-open', help='Open WebSocket server (0x70)')
    p_wso.add_argument('--port', dest='port_num', type=int, default=8080)
    p_wso.add_argument('--maxconn', type=int, default=5)
    p_wso.add_argument('--path', default='/')

    p_wscc = sub.add_parser('ws-client-connect', help='WebSocket client connect (0x72)')
    p_wscc.add_argument('--ip', required=True)
    p_wscc.add_argument('--port', dest='port_num', type=int, required=True)
    p_wscc.add_argument('--path', default='/')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    transport = MCPTransport(port=args.port, baudrate=args.baud)
    transport.open()

    try:
        if args.command == 'net-status':
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
        elif args.command == 'tcp-send':
            cmd_tcp_send(transport, args)
        elif args.command == 'tcp-list-clients':
            cmd_tcp_list_clients(transport, args)
        elif args.command == 'tcp-conn-status':
            cmd_tcp_conn_status(transport, args)
        elif args.command == 'udp-server-open':
            cmd_udp_server_open(transport, args)
        elif args.command == 'ws-server-open':
            cmd_ws_server_open(transport, args)
        elif args.command == 'ws-client-connect':
            cmd_ws_client_connect(transport, args)
        else:
            print(f"Unknown command: {args.command}")
    finally:
        transport.close()


if __name__ == '__main__':
    main()
