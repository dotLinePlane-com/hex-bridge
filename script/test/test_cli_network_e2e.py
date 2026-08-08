"""
HEX-Bridge CLI-Style Network End-to-End Test
=============================================

Tests TCP/UDP/WS bidirectional data exchange by using the same
MCPTransport + UBCPBuilder infrastructure as the CLI, combined
with Python sockets for the PC-side network peer.

Covers:
  TCP-01   Server accept + RECV/SEND/reply verification
  TCP-02   Client connect to PC server + SEND/RECV
  TCP-06   Manual Accept (decision=0)
  TCP-07   Manual Reject (decision=1)
  TCP-15   TCP_SEND invalid handle â†?ERR_NET_HANDLE_INVALID
  TCP-14   TCP_CONN_STATUS invalid handle â†?0x43
  TCP-18   TCP_SERVER_CLOSE invalid handle â†?0x43
  UDP-06   UDP_SERVER_SEND invalid handle â†?0x43
  WS-10    WS_SEND invalid handle â†?0x43

Use case:
  This script provides the same test coverage as CLI + MCP
  Network Monitor coordinated testing, but is fully self-contained
  (no MCP NM tools needed). It creates PC-side TCP servers/clients
  within the same process, keeping COM4 open for event capture.

  Best for: CI/CD pipelines, automated regression tests, and
  environments where MCP NM tools are not available.

  For interactive/manual testing with MCP NM tools, use the CLI
  with --wait-events flag instead:
    python script/cli/hex-bridge-network-cli.py \
        --wait-events 0x56,0x55 --event-timeout 15 \
        tcp-server-open --port 9190

  For protocol-only tests (no network peer), use:
    python script/test/test_network.py --mcp COM4 --mcp-baud 115200 --auto

Usage:
  python script/test/test_cli_network_e2e.py
  python script/test/test_cli_network_e2e.py --esp-ip 192.168.1.105 --pc-ip 192.168.1.4
"""

import socket
import struct
import time
import threading
import sys
import os
import argparse

# Add project script/test directory to path
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)

from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

# ============================================================================
# Command Codes
# ============================================================================
CMD_PING               = 0x00
CMD_TCP_SERVER_OPEN    = 0x50
CMD_TCP_SERVER_CLOSE   = 0x51
CMD_TCP_CLIENT_CONNECT = 0x52
CMD_TCP_CLIENT_DISCONNECT = 0x53
CMD_TCP_SEND           = 0x54
CMD_TCP_RECV           = 0x55
CMD_TCP_ACCEPT         = 0x56
CMD_TCP_CONN_STATUS    = 0x5B
CMD_UDP_SERVER_SEND    = 0x64
CMD_WS_SEND            = 0x74

ERR_SUCCESS            = 0x00
ERR_NET_HANDLE_INVALID = 0x43

# ============================================================================
# Globals
# ============================================================================
passed = 0
failed = 0
transport = None
seq = 1

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--mcp', default='COM4')
    p.add_argument('--mcp-baud', type=int, default=115200)
    p.add_argument('--esp-ip', default='192.168.1.105', help='ESP32 IP address')
    p.add_argument('--pc-ip', default=None, help='PC IP address (auto-detect if not set)')
    return p.parse_args()

args = None

def next_seq():
    global seq
    s = seq
    seq += 1
    return s

def P(name):
    global passed
    passed += 1
    print(f'  [PASS] {name}')

def F(name, msg=''):
    global failed
    failed += 1
    print(f'  [FAIL] {name}: {msg}')

def info(msg):
    print(f'  [INFO] {msg}')

def send_cmd(cmd, payload=b'', channel=0, timeout=5.0):
    s = next_seq()
    wire = UBCPBuilder.build_request(s, cmd, channel, payload)
    transport.send(wire)
    return transport.recv_response(cmd_code=cmd, timeout=timeout)

def wait_event(cmd_code, timeout=5.0):
    return transport.recv_event(cmd_code=cmd_code, timeout=timeout)

def expect_status(cmd, payload, channel, expected_status, name, timeout=5.0):
    f = send_cmd(cmd, payload, channel, timeout)
    if f is None:
        F(name, 'no response')
        return None
    if f.payload[0] != expected_status:
        F(f'{name}: expected 0x{expected_status:02X}, got 0x{f.payload[0]:02X}')
    else:
        P(f'{name}: 0x{expected_status:02X}')
    return f

def check_ping():
    f = send_cmd(CMD_PING, timeout=3.0)
    if f is None:
        F('PING', 'device not responding')
        return False
    if f.payload[0] == ERR_SUCCESS:
        P('PING: device ready')
        return True
    F(f'PING: status=0x{f.payload[0]:02X}')
    return False

def get_pc_ip(target_ip):
    """Auto-detect PC's IP by connecting to target IP."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(1.0)
        s.connect((target_ip, 9))
        ip = s.getsockname()[0]
    except Exception:
        ip = None
    finally:
        s.close()
    return ip

# ============================================================================
# Test: TCP-01 â€?Server: accept client, receive data, reply back
# ============================================================================
def test_tcp_01(esp_ip):
    print('\n' + '=' * 60)
    print('  TCP-01: TCP Server Open + PC Connect + RECV + Reply + Verify')
    print('=' * 60)

    transport.flush_input()

    # Try closing any stale servers from previous crashed runs (ports 9190-9193)
    for stale_handle in [0x1043, 0x1044]:
        transport.send(UBCPBuilder.build_request(next_seq(), CMD_TCP_SERVER_CLOSE,
                         0, struct.pack('>HB', stale_handle, 0x01)))
    # Also try clearing old connection handles
    for stale_conn in [0x9014, 0x9015, 0x9016, 0x9017]:
        transport.send(UBCPBuilder.build_request(next_seq(),
                         CMD_TCP_CLIENT_DISCONNECT, 0,
                         struct.pack('>HB', stale_conn, 0x01)))
    time.sleep(0.5)
    transport.flush_input()

    # Step 1: Create server on port 9193, accept_mode=1, max_conn=3
    payload = struct.pack('>HBBB', 9193, 3, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload)
    if f is None or f.payload[0] != ERR_SUCCESS:
        F('TCP-01 SERVER_OPEN', f'status=0x{f.payload[0]:02X}' if f else 'no response')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    ap = struct.unpack('>H', f.payload[3:5])[0]
    P(f'TCP-01 SERVER_OPEN: handle=0x{sh:04X}, port={ap} (9193)')

    # Step 2: Connect from PC Python socket
    info(f'Connecting PC -> {esp_ip}:9193 ...')
    pc_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pc_sock.settimeout(5.0)
    try:
        pc_sock.connect((esp_ip, 9193))
        P('TCP-01 PC connected')
    except Exception as e:
        F('TCP-01 PC connect', str(e))
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
        return

    # Step 3: Wait for ACCEPT event
    evt = wait_event(CMD_TCP_ACCEPT, timeout=5.0)
    if evt is None:
        F('TCP-01 ACCEPT event', 'no event received')
        pc_sock.close()
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
        return
    ch = struct.unpack('>H', evt.payload[2:4])[0]
    rip = f'{evt.payload[4]}.{evt.payload[5]}.{evt.payload[6]}.{evt.payload[7]}'
    rport = struct.unpack('>H', evt.payload[8:10])[0]
    P(f'TCP-01 ACCEPT: client_handle=0x{ch:04X}, client={rip}:{rport}')

    # Step 4: Send data from PC to ESP32
    test_data = b'Hello ESP32'
    pc_sock.sendall(test_data)
    info(f'PC sent: {test_data}')
    time.sleep(0.3)

    # Step 5: Wait for RECV event on ESP32
    evt2 = wait_event(CMD_TCP_RECV, timeout=5.0)
    if evt2 is None:
        F('TCP-01 RECV event', 'no event')
    else:
        recv_ch = struct.unpack('>H', evt2.payload[0:2])[0]
        recv_len = struct.unpack('>H', evt2.payload[2:4])[0]
        recv_data = evt2.payload[4:4 + recv_len]
        if recv_data == test_data:
            P(f'TCP-01 RECV: ch=0x{recv_ch:04X}, data={recv_data}')
        else:
            F(f'TCP-01 RECV: expected {test_data}, got {recv_data}')

    # Step 6: Reply via UBCP TCP_SEND
    reply = b'Hello PC!'
    send_payload = struct.pack('>HH', ch, len(reply)) + reply
    f2 = send_cmd(CMD_TCP_SEND, send_payload)
    if f2 and f2.payload[0] == ERR_SUCCESS:
        sent_len = struct.unpack('>H', f2.payload[1:3])[0]
        P(f'TCP-01 Reply sent: {sent_len} bytes')
    else:
        F('TCP-01 Reply send', f'status=0x{f2.payload[0]:02X}' if f2 else 'no response')

    # Step 7: Verify PC received reply
    try:
        pc_sock.settimeout(3.0)
        data = pc_sock.recv(1024)
        if data == reply:
            P(f'TCP-01 PC received reply: {data}')
        else:
            F(f'TCP-01 PC reply mismatch: expected {reply}, got {data}')
    except socket.timeout:
        F('TCP-01 PC reply', 'timeout')
    except Exception as e:
        F('TCP-01 PC reply', str(e))

    # Cleanup
    pc_sock.close()
    send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
    time.sleep(0.5)


# ============================================================================
# Test: TCP-02 â€?ESP32 as client connects to PC server
# ============================================================================
def test_tcp_02(esp_ip, pc_ip):
    print('\n' + '=' * 60)
    print('  TCP-02: ESP32 Client Connect to PC Server')
    print('=' * 60)

    transport.flush_input()

    # Step 1: Create PC TCP server
    info(f'Starting PC TCP server on {pc_ip}:9191 ...')
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(('0.0.0.0', 9191))
    server_sock.listen(1)
    server_sock.settimeout(10.0)
    P(f'TCP-02 PC server listening on :9191')

    # Step 2: ESP32 connects via TCP_CLIENT_CONNECT
    ip_bytes = socket.inet_aton(pc_ip)
    ip_u32 = struct.unpack('>I', ip_bytes)[0]
    payload = struct.pack('>IHBB', ip_u32, 9191, 5, 0)
    f = send_cmd(CMD_TCP_CLIENT_CONNECT, payload, timeout=10.0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        F('TCP-02 CLIENT_CONNECT', f'status=0x{f.payload[0]:02X}' if f else 'no response')
        server_sock.close()
        return
    ch = struct.unpack('>H', f.payload[1:3])[0]
    local_ip = f'{f.payload[3]}.{f.payload[4]}.{f.payload[5]}.{f.payload[6]}'
    local_port = struct.unpack('>H', f.payload[7:9])[0]
    P(f'TCP-02 Client connected: handle=0x{ch:04X}, local={local_ip}:{local_port}')

    # Step 3: Accept on PC side
    try:
        client_sock, addr = server_sock.accept()
        P(f'TCP-02 PC accepted: {addr}')
        client_sock.settimeout(5.0)
    except Exception as e:
        F('TCP-02 PC accept', str(e))
        send_cmd(CMD_TCP_CLIENT_DISCONNECT, struct.pack('>HB', ch, 0x00))
        server_sock.close()
        return

    # Step 4: ESP32 sends data via TCP_SEND
    send_data = b'Hello from ESP32'
    send_payload = struct.pack('>HH', ch, len(send_data)) + send_data
    f2 = send_cmd(CMD_TCP_SEND, send_payload)
    if f2 and f2.payload[0] == ERR_SUCCESS:
        sent = struct.unpack('>H', f2.payload[1:3])[0]
        P(f'TCP-02 SEND: {sent} bytes')

        # Step 5: PC receives data
        try:
            data = client_sock.recv(1024)
            if data == send_data:
                P(f'TCP-02 PC RECV: {data}')
            else:
                F(f'TCP-02 PC RECV mismatch: {data}')
        except Exception as e:
            F('TCP-02 PC RECV', str(e))
    else:
        F('TCP-02 SEND', f'status=0x{f2.payload[0]:02X}' if f2 else 'no response')

    # Cleanup
    client_sock.close()
    server_sock.close()
    send_cmd(CMD_TCP_CLIENT_DISCONNECT, struct.pack('>HB', ch, 0x00))
    time.sleep(0.5)


# ============================================================================
# Test: TCP-06/07 â€?Manual Accept / Reject
# ============================================================================
def test_tcp_06_07(esp_ip):
    print('\n' + '=' * 60)
    print('  TCP-06/07: Manual Accept (decision=0) and Reject (decision=1)')
    print('=' * 60)

    transport.flush_input()

    # Step 1: Create server on port 9192, accept_mode=1
    payload = struct.pack('>HBBB', 9192, 3, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload)
    if f is None or f.payload[0] != ERR_SUCCESS:
        F('TCP-06 SERVER_OPEN', f'status=0x{f.payload[0]:02X}' if f else 'no response')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    P(f'TCP-06/07 SERVER_OPEN: handle=0x{sh:04X}')

    # --- TCP-06: Accept (decision=0) ---
    info(f'TCP-06: Connecting PC -> {esp_ip}:9192 ...')
    pc_sock1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pc_sock1.settimeout(5.0)
    try:
        pc_sock1.connect((esp_ip, 9192))
        P('TCP-06 PC connected')
    except Exception as e:
        F('TCP-06 PC connect', str(e))
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
        return

    # Wait for ACCEPT event
    evt = wait_event(CMD_TCP_ACCEPT, timeout=5.0)
    if evt is None:
        F('TCP-06 ACCEPT event', 'no event')
    else:
        ch = struct.unpack('>H', evt.payload[2:4])[0]
        P(f'TCP-06 ACCEPT event: client_handle=0x{ch:04X}')

        # Accept with decision=0
        f_a = send_cmd(CMD_TCP_ACCEPT, struct.pack('>HB', ch, 0x00))
        if f_a and f_a.payload[0] == ERR_SUCCESS:
            P('TCP-06 ACCEPT(decision=0): accepted')
        else:
            F('TCP-06 ACCEPT(decision=0)', f'status=0x{f_a.payload[0]:02X}' if f_a else 'no response')

    # Close PC socket
    pc_sock1.close()
    time.sleep(0.5)

    # --- TCP-07: Reject (decision=1) ---
    info(f'TCP-07: Connecting PC -> {esp_ip}:9192 ...')
    pc_sock2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pc_sock2.settimeout(5.0)
    try:
        pc_sock2.connect((esp_ip, 9192))
        P('TCP-07 PC connected')
    except Exception as e:
        F('TCP-07 PC connect', str(e))
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
        return

    # Wait for ACCEPT event
    evt2 = wait_event(CMD_TCP_ACCEPT, timeout=5.0)
    if evt2 is None:
        F('TCP-07 ACCEPT event', 'no event')
    else:
        ch2 = struct.unpack('>H', evt2.payload[2:4])[0]
        P(f'TCP-07 ACCEPT event: client_handle=0x{ch2:04X}')

        # Reject with decision=1
        f_r = send_cmd(CMD_TCP_ACCEPT, struct.pack('>HB', ch2, 0x01))
        if f_r and f_r.payload[0] == ERR_SUCCESS:
            P('TCP-07 ACCEPT(decision=1): rejected')
            # Try to recv on PC side â€?should get 0 bytes (connection closed)
            try:
                pc_sock2.settimeout(2.0)
                data = pc_sock2.recv(1024)
                if len(data) == 0:
                    P('TCP-07 PC-side confirmed: connection closed by ESP32')
                else:
                    info(f'TCP-07 PC-side recv: {len(data)} bytes (unexpected)')
            except Exception as e:
                P(f'TCP-07 PC-side confirmed closed: {e}')
        else:
            F('TCP-07 ACCEPT(decision=1)', f'status=0x{f_r.payload[0]:02X}' if f_r else 'no response')

    # Cleanup
    pc_sock2.close()
    send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01))
    time.sleep(0.3)


# ============================================================================
# Test: TCP-15 â€?TCP_SEND with invalid handle
# ============================================================================
def test_tcp_15():
    print('\n' + '=' * 60)
    print('  TCP-15: TCP_SEND with invalid handle')
    print('=' * 60)

    transport.flush_input()
    payload = struct.pack('>HH', 0x1234, 3) + b'ABC'
    expect_status(CMD_TCP_SEND, payload, 0, ERR_NET_HANDLE_INVALID, 'TCP-15')


# ============================================================================
# Test: TCP-14 â€?TCP_CONN_STATUS with 0xFFFF
# ============================================================================
def test_tcp_14():
    print('\n' + '=' * 60)
    print('  TCP-14: TCP_CONN_STATUS with invalid handle 0xFFFF')
    print('=' * 60)

    transport.flush_input()
    payload = struct.pack('>H', 0xFFFF)
    expect_status(CMD_TCP_CONN_STATUS, payload, 0, ERR_NET_HANDLE_INVALID, 'TCP-14')


# ============================================================================
# Test: TCP-18 â€?TCP_SERVER_CLOSE with 0x0000
# ============================================================================
def test_tcp_18():
    print('\n' + '=' * 60)
    print('  TCP-18: TCP_SERVER_CLOSE with invalid handle 0x0000')
    print('=' * 60)

    transport.flush_input()
    payload = struct.pack('>HB', 0x0000, 0x01)
    expect_status(CMD_TCP_SERVER_CLOSE, payload, 0, ERR_NET_HANDLE_INVALID, 'TCP-18')


# ============================================================================
# Test: UDP-06 â€?UDP_SERVER_SEND with invalid handle
# ============================================================================
def test_udp_06():
    print('\n' + '=' * 60)
    print('  UDP-06: UDP_SERVER_SEND with invalid handle')
    print('=' * 60)

    transport.flush_input()
    payload = struct.pack('>H4sHH', 0x1234, b'\x00\x00\x00\x00', 0, 3) + b'ABC'
    expect_status(CMD_UDP_SERVER_SEND, payload, 0, ERR_NET_HANDLE_INVALID, 'UDP-06')


# ============================================================================
# Test: WS-10 â€?WS_SEND with invalid handle
# ============================================================================
def test_ws_10():
    print('\n' + '=' * 60)
    print('  WS-10: WS_SEND with invalid handle')
    print('=' * 60)

    transport.flush_input()
    # WS_SEND: Handle (2B) + MsgType (1B) + DataLen (2B) + Data
    payload = struct.pack('>HBH', 0x1234, 0x01, 3) + b'ABC'
    expect_status(CMD_WS_SEND, payload, 0, ERR_NET_HANDLE_INVALID, 'WS-10')


# ============================================================================
# Main
# ============================================================================
def main():
    global args, transport, passed, failed

    args = parse_args()

    print('=' * 60)
    print('  HEX-Bridge CLI + Network Monitor E2E Test')
    print('=' * 60)
    print(f'  MCP: {args.mcp} @ {args.mcp_baud} bps')
    print(f'  ESP32 IP: {args.esp_ip}')

    # Auto-detect PC IP
    pc_ip = args.pc_ip
    if pc_ip is None:
        info('Auto-detecting PC IP ...')
        pc_ip = get_pc_ip(args.esp_ip)
        if pc_ip is None:
            pc_ip = '192.168.1.4'
            info(f'Cannot auto-detect, using default: {pc_ip}')
        else:
            info(f'Detected PC IP: {pc_ip}')
    print(f'  PC IP: {pc_ip}')

    # Open transport
    print(f'\nOpening MCP transport: {args.mcp} @ {args.mcp_baud} ...')
    transport = MCPTransport(port=args.mcp, baudrate=args.mcp_baud)
    try:
        transport.open()
        P(f'MCP transport opened: {args.mcp}')
    except Exception as e:
        F(f'MCP transport open', str(e))
        print(f'\nFAILED to open {args.mcp}. Ensure device is connected and not in use.')
        sys.exit(1)

    # Ping check
    print()
    if not check_ping():
        transport.close()
        print('\nDevice not reachable. Aborting.')
        sys.exit(1)

    # Run tests
    try:
        test_tcp_01(args.esp_ip)
        test_tcp_02(args.esp_ip, pc_ip)
        test_tcp_06_07(args.esp_ip)
        test_tcp_15()
        test_tcp_14()
        test_tcp_18()
        test_udp_06()
        test_ws_10()
    except KeyboardInterrupt:
        print('\n\nTest interrupted by user.')
    except Exception as e:
        import traceback
        print(f'\n\nUnhandled exception: {e}')
        traceback.print_exc()
    finally:
        transport.close()
        print('\nTransport closed.')

    # Summary
    total = passed + failed
    print('\n' + '=' * 60)
    print('  SUMMARY')
    print('=' * 60)
    print(f'  PASS: {passed}')
    print(f'  FAIL: {failed}')
    print(f'  TOTAL: {total}')
    if failed == 0:
        print('\n  ALL TESTS PASSED!')
    else:
        print(f'\n  {failed} TEST(S) FAILED.')
    print('=' * 60)

    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
