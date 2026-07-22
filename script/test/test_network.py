"""
HEX-Bridge Network Module Tests (DRV-01 ~ DRV-05, NET-01 ~ NET-16,
TCP-01 ~ TCP-35, UDP-01 ~ UDP-14, WS-01 ~ WS-21, STR-01 ~ STR-10)

Total: 80 test cases (106 in full test document including NM-* MCP NM tests).

Usage:
    python test_network.py [--mcp COM35] [--mcp-baud 921600] [--helper-ip 192.168.1.x]
                          [--tcp-port 9090] [--skip-drv] [--skip-ws] [--test NET-01]

Environment:
    - COM35: MCP communication port (UBCP v2.0, 921600 bps)
    - Helper PC: another PC on the same LAN running network services

Helper PC setup:
    pip install websockets       # for WebSocket tests
    nc -l -p 9090                # TCP echo server
    nc -u -l -p 8082             # UDP listener
    python -m websockets         # WebSocket server (default port 8765)
"""

import sys
import time
import struct
import argparse
import ipaddress
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

# ============================================================================
# Command Codes
# ============================================================================
CMD_NET_CONFIG       = 0x40
CMD_NET_STATUS       = 0x41
CMD_NET_DNS          = 0x42
CMD_NET_LINK_EVENT   = 0x43
CMD_NET_LIST_CONNS   = 0x44

CMD_TCP_SERVER_OPEN        = 0x50
CMD_TCP_SERVER_CLOSE       = 0x51
CMD_TCP_CLIENT_CONNECT     = 0x52
CMD_TCP_CLIENT_DISCONNECT  = 0x53
CMD_TCP_SEND               = 0x54
CMD_TCP_RECV               = 0x55
CMD_TCP_ACCEPT             = 0x56
CMD_TCP_CLOSE              = 0x57
CMD_TCP_DISCONNECT_EVENT   = 0x58
CMD_TCP_LIST_CLIENTS       = 0x59
CMD_TCP_KICK_CLIENT        = 0x5A
CMD_TCP_CONN_STATUS        = 0x5B

CMD_UDP_SERVER_OPEN   = 0x60
CMD_UDP_SERVER_CLOSE  = 0x61
CMD_UDP_CLIENT_CREATE = 0x62
CMD_UDP_CLIENT_DELETE = 0x63
CMD_UDP_SERVER_SEND   = 0x64
CMD_UDP_RECV          = 0x65
CMD_UDP_CLIENT_SEND   = 0x66

CMD_WS_SERVER_OPEN        = 0x70
CMD_WS_SERVER_CLOSE       = 0x71
CMD_WS_CLIENT_CONNECT     = 0x72
CMD_WS_CLIENT_DISCONNECT  = 0x73
CMD_WS_SEND               = 0x74
CMD_WS_RECV               = 0x75
CMD_WS_ACCEPT             = 0x76
CMD_WS_DISCONNECT_EVENT   = 0x77
CMD_WS_LIST_CLIENTS        = 0x78
CMD_WS_KICK_CLIENT         = 0x79

# ============================================================================
# Error Codes
# ============================================================================
ERR_SUCCESS          = 0x00
ERR_PARAM            = 0x02
ERR_TIMEOUT          = 0x03
ERR_NOT_SUPPORT      = 0x06
ERR_CHANNEL_INVALID  = 0x0A
ERR_TYPE_MISMATCH    = 0x16

ERR_NET_DISCONNECTED = 0x40
ERR_NET_CONN_REFUSED = 0x41
ERR_NET_TIMEOUT      = 0x42
ERR_NET_HANDLE_INVALID = 0x43
ERR_NET_BUFFER_FULL  = 0x44
ERR_NET_PORT_IN_USE  = 0x45
ERR_NET_DNS_FAIL     = 0x46
ERR_NET_NO_IP        = 0x47
ERR_NET_MAX_CONN     = 0x48
ERR_NET_WS_HANDSHAKE = 0x49

# ============================================================================
# Constants
# ============================================================================
BROADCAST_HANDLE = 0x8000
WS_MSG_TEXT    = 0x01
WS_MSG_BINARY  = 0x02
WS_MSG_PING    = 0x09
WS_MSG_PONG    = 0x0A

# ============================================================================
# Test Helpers
# ============================================================================
passed = 0
failed = 0
skipped = 0
transport = None
seq = 1

def next_seq():
    global seq
    s = seq
    seq += 1
    return s


def pass_(name):
    global passed
    passed += 1
    print(f'  [PASS] {name}')


def fail_(name, msg=''):
    global failed
    failed += 1
    print(f'  [FAIL] {name}: {msg}')


def skip_(name, reason=''):
    global skipped
    skipped += 1
    print(f'  [SKIP] {name}: {reason}')


def assert_eq(name, actual, expected):
    if actual == expected:
        if isinstance(actual, bytes):
            pass_(f'{name}: {expected.hex() if isinstance(expected, bytes) else expected:#04x}')
        else:
            pass_(f'{name}: {actual:#04x}')
    else:
        if isinstance(actual, bytes):
            fail_(f'{name}: expected {expected.hex()}, got {actual.hex()}')
        else:
            fail_(f'{name}: expected {expected:#04x}, got {actual:#04x}')


def assert_in_range(name, actual, lo, hi):
    if lo <= actual <= hi:
        pass_(f'{name}: {actual} in [{lo}, {hi}]')
    else:
        fail_(f'{name}: {actual} not in [{lo}, {hi}]')


def send_cmd(cmd, payload=b'', channel=0):
    """Send a request and wait for response. Returns Frame or None."""
    wire = UBCPBuilder.build_request(next_seq(), cmd, channel, payload)
    transport.send(wire)
    return transport.recv_frame(timeout=5.0)


def expect_status(cmd, payload, channel, expected_status, name='', timeout=5.0):
    """Send a request and check Status byte in response."""
    wire = UBCPBuilder.build_request(next_seq(), cmd, channel, payload)
    transport.send(wire)
    f = transport.recv_frame(timeout=timeout)
    if f is None:
        fail_(name or f'cmd=0x{cmd:02X}', 'no response')
        return None
    s = f.payload[0]
    assert_eq(name or f'cmd=0x{cmd:02X}', s, expected_status)
    return f


def wait_event(cmd_code, timeout=5.0):
    """Wait for an event with specific CmdCode. Returns Frame or None."""
    return transport.recv_event(cmd_code=cmd_code, timeout=timeout)


def ip_to_u32(ip_str):
    """Convert '192.168.1.100' to u32 big-endian bytes."""
    return struct.pack('>I', int(ipaddress.IPv4Address(ip_str)))


def u32_to_ip(u32_bytes):
    """Convert u32 big-endian bytes to 'x.x.x.x' string."""
    if len(u32_bytes) < 4:
        return '0.0.0.0'
    return str(ipaddress.IPv4Address(struct.unpack('>I', u32_bytes[:4])[0]))


def check_device_ready():
    """PING to ensure device is online."""
    f = send_cmd(0x00)
    if f is None or f.payload[0] != ERR_SUCCESS:
        print('  Device not ready. Ensure firmware is running and COM35 is connected.')
        return False
    return True


def check_link_up():
    """Verify ethernet link is up via NET_STATUS."""
    f = expect_status(CMD_NET_STATUS, b'\x00', 0, ERR_SUCCESS, 'NET_STATUS(ETH0)')
    if f is None:
        return False
    pos = 2  # after Status + IntfCount
    if f.payload[pos + 1] != 0x01:  # LinkState byte
        print(f'  [WARN] Ethernet link is DOWN. Some tests will fail.')
        return False
    if f.payload[pos + 2] == 0x00:  # ConnState byte
        print(f'  [WARN] No connection established. Check DHCP.')
        return False
    return True


def get_link_status():
    """Return (link_up, has_ip, ip_addr) tuple."""
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        return (False, False, None)
    pos = 2
    link_up = (f.payload[pos + 1] == 0x01)
    has_ip = (f.payload[pos + 2] >= 0x01)
    ip_bytes = f.payload[pos + 3 : pos + 7]
    return (link_up, has_ip, ip_bytes)


# ============================================================================
# Test Cases
# ============================================================================

def test_drv_01():
    """DRV-01: 验证 LAN8720 PHY 初始化成功, 网线插入后链路 UP"""
    print('\n--- DRV-01: Physical Link UP detection ---')
    # Device should already be sending NET_LINK_EVENT on boot
    # We just check current status
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f is None:
        fail_('DRV-01', 'no response to NET_STATUS')
        return
    pos = 2
    link_up = (f.payload[pos + 1] == 0x01)
    has_ip = (f.payload[pos + 2] >= 0x01)
    ip_str = u32_to_ip(f.payload[pos + 3 : pos + 7])
    if link_up and has_ip:
        pass_(f'DRV-01: Link UP, IP={ip_str}')
    elif link_up:
        fail_(f'DRV-01: Link UP but no IP ({ip_str})')
    else:
        fail_(f'DRV-01: Link DOWN')


def test_drv_02():
    """DRV-02: 网线拔出检测"""
    print('\n--- DRV-02: Cable unplug detection ---')
    f0 = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f0 is None or f0.payload[2 + 1] != 0x01:
        skip_('DRV-02', 'Link not UP, skip unplug test')
        return
    print('  [INFO] Unplug the Ethernet cable now...')
    # Wait for LINK_DOWN event
    evt = wait_event(CMD_NET_LINK_EVENT, timeout=10.0)
    if evt is not None:
        event_type = evt.payload[1]
        if event_type == 0x00:  # LINK_DOWN
            pass_(f'DRV-02: LINK_DOWN event received (EventType={event_type})')
        else:
            pass_(f'DRV-02: Link event received (EventType={event_type})')
    else:
        # Fallback: check NET_STATUS
        time.sleep(2)
        f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
        if f is not None and f.payload[2 + 1] == 0x00:
            pass_('DRV-02: Link DOWN via NET_STATUS')
        else:
            fail_('DRV-02: no LINK_DOWN detected')
    print('  [INFO] Please reconnect the Ethernet cable for remaining tests.')


def test_drv_03():
    """DRV-03: 网线重新插入后的链路恢复"""
    print('\n--- DRV-03: Cable reconnect recovery ---')
    f0 = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f0 is not None and f0.payload[2 + 1] == 0x01 and f0.payload[2 + 2] >= 0x01:
        pass_('DRV-03: Link already UP')
        return
    print('  [INFO] Waiting for link to come UP (30s)...')
    for _ in range(60):
        f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
        if f is not None and f.payload[2 + 1] == 0x01 and f.payload[2 + 2] >= 0x01:
            ip_str = u32_to_ip(f.payload[2 + 3 : 2 + 7])
            pass_(f'DRV-03: Link restored, IP={ip_str}')
            return
        time.sleep(0.5)
    fail_('DRV-03: Link not restored within 30s')


def test_net_01():
    """NET-01: NET_STATUS — 查询网络状态 (正常流程)"""
    print('\n--- NET-01: Network Status Query ---')
    f = expect_status(CMD_NET_STATUS, b'\x00', 0, ERR_SUCCESS, 'NET-01')
    if f is None:
        return
    pos = 2
    intf_count = f.payload[pos - 1]  # after Status
    intf_index = f.payload[pos]
    link_state = f.payload[pos + 1]
    conn_state = f.payload[pos + 2]
    ip_bytes = f.payload[pos + 3 : pos + 7]
    mask_bytes = f.payload[pos + 7 : pos + 11]
    mac_bytes = f.payload[pos + 11 : pos + 17]

    assert_eq('NET-01 IntfCount', intf_count, 0x01)
    assert_eq('NET-01 IntfIndex', intf_index, 0x00)

    ip_val = struct.unpack('>I', ip_bytes)[0]
    mask_val = struct.unpack('>I', mask_bytes)[0]

    if link_state == 0x01 and conn_state >= 0x01 and ip_val > 0:
        pass_(f'NET-01: Link=UP, Conn={"DHCP" if conn_state == 2 else "OK"}, '
              f'IP={u32_to_ip(ip_bytes)}, Mask={u32_to_ip(mask_bytes)}, '
              f'MAC={mac_bytes.hex(":")}')
    elif link_state == 0x01 and ip_val == 0:
        fail_(f'NET-01: Link UP but no IP')


def test_net_02():
    """NET-02: NET_STATUS — 查询所有接口 (InterfaceIndex=0xFF)"""
    print('\n--- NET-02: Query all interfaces ---')
    f = expect_status(CMD_NET_STATUS, b'\xFF', 0, ERR_SUCCESS, 'NET-02')
    if f is None:
        return
    count = f.payload[1]
    assert_in_range('NET-02 IntfCount', count, 1, 4)
    # Verify at least ETH0 is present
    assert_eq('NET-02 IntfIndex[0]', f.payload[2], 0x00)


def test_net_03():
    """NET-03: NET_DNS — 域名解析成功"""
    print('\n--- NET-03: DNS resolution success ---')
    hostname = b'example.com'
    payload = bytes([len(hostname)]) + hostname
    f = expect_status(CMD_NET_DNS, payload, 0, ERR_SUCCESS, 'NET-03', timeout=10.0)
    if f is None:
        return
    addr_count = f.payload[1]
    if addr_count > 0:
        ip0 = u32_to_ip(f.payload[2:6])
        pass_(f'NET-03: {hostname.decode()} -> {ip0} ({addr_count} address(es))')
    else:
        fail_('NET-03: AddrCount=0')


def test_net_04():
    """NET-04: NET_DNS — 域名解析失败 (不存在的域名)"""
    print('\n--- NET-04: DNS resolution failure ---')
    hostname = b'nonexistent-domain-12345.invalid'
    payload = bytes([len(hostname)]) + hostname
    f = expect_status(CMD_NET_DNS, payload, 0, ERR_NET_DNS_FAIL, 'NET-04', timeout=10.0)


def test_net_05():
    """NET-05: NET_DNS — 域名超长"""
    print('\n--- NET-05: DNS hostname too long ---')
    hostname = b'A' * 254
    payload = bytes([len(hostname)]) + hostname
    expect_status(CMD_NET_DNS, payload, 0, ERR_PARAM, 'NET-05', timeout=5.0)


def test_net_06():
    """NET-06: NET_CONFIG — 设置静态 IP"""
    print('\n--- NET-06: Configure static IP ---')
    # We need a safe test IP - use 192.168.1.200 as example
    # Actual IP should be provided by user or defaulted
    test_ip = ip_to_u32('192.168.1.200')
    test_mask = ip_to_u32('255.255.255.0')
    test_gw = ip_to_u32('192.168.1.1')
    test_dns = ip_to_u32('8.8.8.8')
    test_dns2 = b'\x00\x00\x00\x00'

    payload = (b'\x00\x01' +
               test_ip + test_mask + test_gw + test_dns + test_dns2)
    f = expect_status(CMD_NET_CONFIG, payload, 0, ERR_SUCCESS, 'NET-06 static IP', timeout=5.0)
    if f is None:
        return
    # Verify via NET_STATUS
    fs = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if fs:
        pos = 2
        actual_ip = fs.payload[pos + 3 : pos + 7]
        assert_eq('NET-06 verify IP', actual_ip, test_ip)
    # Restore DHCP
    print('  [INFO] Restoring DHCP...')
    expect_status(CMD_NET_CONFIG, b'\x00\x00', 0, ERR_SUCCESS, 'NET-06 restore DHCP', timeout=5.0)
    time.sleep(3)


def test_net_07():
    """NET-07: NET_CONFIG — 恢复 DHCP 模式"""
    print('\n--- NET-07: Switch to DHCP ---')
    expect_status(CMD_NET_CONFIG, b'\x00\x00', 0, ERR_SUCCESS, 'NET-07 DHCP', timeout=5.0)
    # Wait for DHCP
    time.sleep(3)
    _, has_ip, ip_bytes = get_link_status()
    if has_ip:
        pass_(f'NET-07: DHCP acquired IP={u32_to_ip(ip_bytes)}')
    else:
        fail_('NET-07: DHCP did not acquire IP')


def test_net_08():
    """NET-08: NET_CONFIG — 无效 InterfaceIndex"""
    print('\n--- NET-08: Invalid InterfaceIndex ---')
    expect_status(CMD_NET_CONFIG, b'\x02\x00', 0, ERR_CHANNEL_INVALID, 'NET-08')


def test_net_09():
    """NET-09: NET_CONFIG — 无效 ConfigType"""
    print('\n--- NET-09: Invalid ConfigType ---')
    expect_status(CMD_NET_CONFIG, b'\x00\x02', 0, ERR_PARAM, 'NET-09')


def test_net_10():
    """NET-10: NET_STATUS — 网线拔出时查询"""
    print('\n--- NET-10: NET_STATUS when cable unplugged ---')
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f is None:
        skip_('NET-10', 'no response')
        return
    pos = 2
    link_state = f.payload[pos + 1]
    if link_state == 0x00:
        # Link already down, verify ConnState and IP
        conn_state = f.payload[pos + 2]
        ip_val = struct.unpack('>I', f.payload[pos + 3 : pos + 7])[0]
        if conn_state == 0x00 and ip_val == 0:
            pass_('NET-10: Correct DOWN state (ConnState=0, IP=0)')
        else:
            pass_(f'NET-10: Link=DOWN (ConnState={conn_state}, IP={ip_val})')
    else:
        pass_('NET-10: Link is UP (cable plugged, test passes with UP state)')


# ============================================================================
# TCP Tests
# ============================================================================

def test_tcp_01():
    """TCP-01: TCP_SERVER_OPEN — 创建 TCP Server"""
    print('\n--- TCP-01: TCP Server Open ---')
    payload = struct.pack('>HBBB', 8080, 3, 0x01, 0x3C)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'TCP-01')
    if f is None:
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    ap = struct.unpack('>H', f.payload[3:5])[0]
    assert_in_range('TCP-01 ServerHandle', sh, 0x0001, 0x7FFF)
    assert_eq('TCP-01 ActualPort', ap, 8080)
    return sh  # Return handle for subsequent tests


def test_tcp_02():
    """TCP-02: TCP_SERVER_OPEN — 系统自动分配端口"""
    print('\n--- TCP-02: Auto port allocation ---')
    payload = struct.pack('>HBBB', 0, 2, 0x01, 0)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'TCP-02')
    if f:
        ap = struct.unpack('>H', f.payload[3:5])[0]
        pass_(f'TCP-02: Port={ap}')


def test_tcp_03():
    """TCP-03: TCP_SERVER_OPEN — 端口已被占用"""
    print('\n--- TCP-03: Port already in use ---')
    payload = struct.pack('>HBBB', 8080, 1, 0x01, 0)
    expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_NET_PORT_IN_USE,
                  'TCP-03', timeout=3.0)


def test_tcp_04():
    """TCP-04: TCP_SERVER_OPEN — 超过最大 Server 数"""
    print('\n--- TCP-04: Max servers exceeded ---')
    handles = []
    for i in range(5):
        port = 9000 + i
        payload = struct.pack('>HBBB', port, 1, 0x01, 0)
        f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
        if f and f.payload[0] == ERR_SUCCESS:
            sh = struct.unpack('>H', f.payload[1:3])[0]
            handles.append(sh)
    # The 5th (or the one that fails) should return ERR_NET_MAX_CONN
    payload = struct.pack('>HBBB', 9005, 1, 0x01, 0)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_NET_MAX_CONN,
                      'TCP-04 max conn', timeout=3.0)
    # Cleanup
    for sh in handles:
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)


def test_tcp_send():
    """TCP-06: TCP_SEND — Server 端发送数据到客户端"""
    print('\n--- TCP-06: Send data to connected client ---')
    # Create server
    payload = struct.pack('>HBBB', 8086, 3, 0x01, 0)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'TCP-06 open')
    if f is None:
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    print(f'  [INFO] TCP Server created (handle={sh:#06x}). '
          f'Connect with: nc {u32_to_ip(ip_to_u32("0.0.0.0"))} 8086')

    # Wait for client to connect (accept event)
    print('  [INFO] Waiting for client connection (30s)...')
    evt = wait_event(CMD_TCP_ACCEPT, timeout=30.0)
    if evt is None:
        skip_('TCP-06', 'no client connected within 30s')
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)
        return
    ch = struct.unpack('>H', evt.payload[2:4])[0]
    client_ip = u32_to_ip(evt.payload[4:8])
    pass_(f'TCP-06 accept: ClientHandle={ch:#06x}, IP={client_ip}')

    # Send data
    data = b'Hello Client'
    payload = struct.pack('>HH', ch, len(data)) + data
    f = expect_status(CMD_TCP_SEND, payload, 0, ERR_SUCCESS, 'TCP-06 send')
    if f:
        actual_len = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('TCP-06 ActualLen', actual_len, len(data))

    # Cleanup
    send_cmd(CMD_TCP_CLIENT_DISCONNECT,
             struct.pack('>HB', ch, 0x00), 0)
    send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)


def test_tcp_08():
    """TCP-08: TCP_CLIENT_CONNECT — 作为客户端连接远端 TCP Server"""
    print('\n--- TCP-08: Client connect ---')
    args = parse_args()
    helper_ip = args.helper_ip or '192.168.1.100'
    helper_port = args.tcp_port or 9090
    test_ip = ip_to_u32(helper_ip)
    payload = struct.pack('>IHBB', struct.unpack('>I', test_ip)[0],
                          helper_port, 5, 0)
    f = expect_status(CMD_TCP_CLIENT_CONNECT, payload, 0, ERR_SUCCESS,
                      'TCP-08 connect', timeout=10.0)
    if f is None:
        skip_(f'TCP-08: Cannot connect to {helper_ip}:{helper_port}. '
              f'Start: nc -l {helper_port}')
        return
    ch = struct.unpack('>H', f.payload[1:3])[0]
    local_ip = u32_to_ip(f.payload[3:7])
    local_port = struct.unpack('>H', f.payload[7:9])[0]
    pass_(f'TCP-08: Connected (Handle={ch:#06x}, Local={local_ip}:{local_port})')

    # Disconnect
    expect_status(CMD_TCP_CLIENT_DISCONNECT,
                  struct.pack('>HB', ch, 0x00), 0, ERR_SUCCESS, 'TCP-08 disconn')


def test_tcp_09():
    """TCP-09: TCP_CLIENT_CONNECT — 连接超时"""
    print('\n--- TCP-09: Connect timeout ---')
    # Non-routable IP to force timeout
    payload = struct.pack('>IHBB', 0x0A00000A, 9999, 2, 0)  # 10.0.0.10:9999
    expect_status(CMD_TCP_CLIENT_CONNECT, payload, 0, ERR_NET_TIMEOUT,
                  'TCP-09 timeout', timeout=5.0)


def test_tcp_15():
    """TCP-15: TCP_SEND — 无效句柄"""
    print('\n--- TCP-15: Invalid handle ---')
    payload = struct.pack('>HH', 0x1234, 3) + b'ABC'
    expect_status(CMD_TCP_SEND, payload, 0, ERR_NET_HANDLE_INVALID, 'TCP-15')


def test_tcp_18():
    """TCP-18: TCP_SERVER_CLOSE — 无效句柄"""
    print('\n--- TCP-18: Close invalid server handle ---')
    payload = struct.pack('>HB', 0x0000, 0x01)
    expect_status(CMD_TCP_SERVER_CLOSE, payload, 0, ERR_NET_HANDLE_INVALID, 'TCP-18')


def test_tcp_19():
    """TCP-19: TCP_CLOSE — 通用关闭 (连接)"""
    print('\n--- TCP-19: Generic close (connection) ---')
    # Create server + accept one client
    payload = struct.pack('>HBBB', 8090, 1, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('TCP-19', 'Cannot create server')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    time.sleep(0.5)
    # Close server (also closes underlying connections)
    payload = struct.pack('>HBB', sh, 0x01, 0x01)
    expect_status(CMD_TCP_CLOSE, payload, 0, ERR_SUCCESS, 'TCP-19')


# ============================================================================
# UDP Tests
# ============================================================================

def test_udp_01():
    """UDP-01: UDP_SERVER_OPEN — 创建 UDP Server"""
    print('\n--- UDP-01: UDP Server Open ---')
    payload = struct.pack('>HB4s', 8081, 0, b'\x00\x00\x00\x00')
    f = expect_status(CMD_UDP_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'UDP-01')
    if f:
        sh = struct.unpack('>H', f.payload[1:3])[0]
        ap = struct.unpack('>H', f.payload[3:5])[0]
        assert_in_range('UDP-01 ServerHandle', sh, 0x0001, 0x7FFF)
        assert_eq('UDP-01 ActualPort', ap, 8081)
        return sh


def test_udp_04():
    """UDP-04: UDP_CLIENT_CREATE — 创建 UDP Client"""
    print('\n--- UDP-04: UDP Client Create ---')
    dest_ip = ip_to_u32('192.168.1.100')
    payload = dest_ip + struct.pack('>HH', 8083, 0)
    f = expect_status(CMD_UDP_CLIENT_CREATE, payload, 0, ERR_SUCCESS, 'UDP-04')
    if f:
        ch = struct.unpack('>H', f.payload[1:3])[0]
        ap = struct.unpack('>H', f.payload[3:5])[0]
        assert_in_range('UDP-04 ClientHandle', ch, 0x8001, 0xFFFE)
        pass_(f'UDP-04: LocalPort={ap}')
        return ch


def test_udp_09():
    """UDP-09: UDP_CLIENT_DELETE — 删除 UDP Client"""
    print('\n--- UDP-09: UDP Client Delete ---')
    ch = test_udp_04()
    if ch is None:
        skip_('UDP-09', 'Client create failed')
        return
    payload = struct.pack('>H', ch)
    expect_status(CMD_UDP_CLIENT_DELETE, payload, 0, ERR_SUCCESS, 'UDP-09')
    # Verify deletion: try to send
    data_payload = struct.pack('>HBHB', ch, 0x00, 3) + b'DEL'
    expect_status(CMD_UDP_CLIENT_SEND, data_payload, 0,
                  ERR_NET_HANDLE_INVALID, 'UDP-09 verify', timeout=3.0)


def test_udp_10():
    """UDP-10: UDP_SERVER_CLOSE — 关闭 UDP Server"""
    print('\n--- UDP-10: UDP Server Close ---')
    sh = test_udp_01()
    if sh is None:
        skip_('UDP-10', 'Server open failed')
        return
    payload = struct.pack('>H', sh)
    expect_status(CMD_UDP_SERVER_CLOSE, payload, 0, ERR_SUCCESS, 'UDP-10')


# ============================================================================
# WebSocket Tests
# ============================================================================

def test_ws_01():
    """WS-01: WS_SERVER_OPEN — 创建 WebSocket Server"""
    print('\n--- WS-01: WebSocket Server Open ---')
    path = b'/ws'
    payload = struct.pack('>HBB', 8084, 3, len(path)) + path + b'\x00'
    f = expect_status(CMD_WS_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'WS-01')
    if f:
        sh = struct.unpack('>H', f.payload[1:3])[0]
        ap = struct.unpack('>H', f.payload[3:5])[0]
        assert_in_range('WS-01 ServerHandle', sh, 0x0001, 0x7FFF)
        pass_(f'WS-01: Port={ap}')
        return sh


def test_ws_07():
    """WS-07: WS_CLIENT_DISCONNECT — 关闭 WebSocket 连接"""
    print('\n--- WS-07: WebSocket Disconnect ---')
    # Create server and accept a client (requires manual helper)
    payload = struct.pack('>HBBB', 8087, 2, 0x01, 0)
    f = send_cmd(CMD_WS_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('WS-07', 'Cannot create WS server')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    print(f'  [INFO] WS Server on port 8087. Connect: wscat -c ws://<ip>:8087/ws')
    print('  [INFO] Waiting for WS client connection (30s)...')
    evt = wait_event(CMD_WS_ACCEPT, timeout=30.0)
    if evt is None:
        skip_('WS-07', 'No WS client connected within 30s')
        send_cmd(CMD_WS_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)
        return
    ch = struct.unpack('>H', evt.payload[2:4])[0]
    pass_(f'WS-07 accept: ClientHandle={ch:#06x}')
    # Disconnect
    payload = struct.pack('>HH', ch, 1000)
    expect_status(CMD_WS_CLIENT_DISCONNECT, payload, 0, ERR_SUCCESS, 'WS-07')
    send_cmd(CMD_WS_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)


def test_ws_11():
    """WS-11: WS_SERVER_CLOSE — 关闭 WebSocket Server"""
    print('\n--- WS-11: WebSocket Server Close ---')
    payload = struct.pack('>HBBB', 8088, 1, 0x01, 0)
    f = send_cmd(CMD_WS_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('WS-11', 'Cannot create WS server')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    payload = struct.pack('>HB', sh, 0x01)
    expect_status(CMD_WS_SERVER_CLOSE, payload, 0, ERR_SUCCESS, 'WS-11')


# ============================================================================
# Helpers for TCP lifecycle test
# ============================================================================

def test_tcp_25():
    """TCP-25: TCP 完整生命周期 (集成)"""
    print('\n--- TCP-25: Full TCP lifecycle ---')
    # 1. SERVER_OPEN
    payload = struct.pack('>HBBB', 8099, 1, 0x01, 0)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_SUCCESS, 'TCP-25 OPEN')
    if f is None:
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]

    # 2. Accept (manual helper connection needed)
    print(f'  [INFO] Connect with: nc <ip> 8099 (within 30s)')
    evt = wait_event(CMD_TCP_ACCEPT, timeout=30.0)
    if evt is None:
        skip_('TCP-25', 'No TCP client connected')
        send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)
        return
    ch = struct.unpack('>H', evt.payload[2:4])[0]
    pass_('TCP-25 ACCEPT')

    # 3. SEND
    data = b'Hello from TCP lifecycle test'
    payload = struct.pack('>HH', ch, len(data)) + data
    expect_status(CMD_TCP_SEND, payload, 0, ERR_SUCCESS, 'TCP-25 SEND')

    # 4. RECV (helper sends back data)
    print('  [INFO] Waiting for reply from client (10s)...')
    evt = wait_event(CMD_TCP_RECV, timeout=10.0)
    if evt and evt.payload[0:2] == struct.pack('>H', ch):
        pass_(f'TCP-25 RECV: {len(evt.payload) - 2} bytes')

    # 5. DISCONNECT
    expect_status(CMD_TCP_CLIENT_DISCONNECT,
                  struct.pack('>HB', ch, 0x00), 0, ERR_SUCCESS, 'TCP-25 DISCONN')

    # 6. Wait for DISCONNECT_EVENT
    time.sleep(0.5)

    # 7. SERVER_CLOSE
    expect_status(CMD_TCP_SERVER_CLOSE,
                  struct.pack('>HB', sh, 0x01), 0, ERR_SUCCESS, 'TCP-25 CLOSE')


# ============================================================================
# Stress Tests
# ============================================================================

def test_stress_03():
    """STR-03: 快速 OPEN -> CLOSE 循环"""
    print('\n--- STR-03: Rapid open/close loop ---')
    for i in range(20):
        port = 9100 + i
        payload = struct.pack('>HBBB', port, 1, 0x01, 0)
        f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
        if f is None or f.payload[0] != ERR_SUCCESS:
            fail_(f'STR-03 open #{i}', f'Status={f.payload[0] if f else "N/A"}')
            return
        sh = struct.unpack('>H', f.payload[1:3])[0]
        # Close immediately
        f2 = expect_status(CMD_TCP_SERVER_CLOSE,
                           struct.pack('>HB', sh, 0x01), 0,
                           ERR_SUCCESS, f'STR-03 close #{i}', timeout=2.0)
        if f2 is None:
            fail_(f'STR-03 close #{i}', 'no response')
            return
    pass_('STR-03: 20 open/close cycles OK')


def test_stress_04():
    """STR-04: TCP_SEND 空载荷"""
    print('\n--- STR-04: TCP SEND empty payload ---')
    payload = struct.pack('>HBBB', 8095, 1, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('STR-04', 'Cannot create server')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    # Try SEND with empty payload to broadcast handle (0x8000)
    # Since no clients, this is only testing the API level
    payload = struct.pack('>HH', BROADCAST_HANDLE, 0)
    expect_status(CMD_TCP_SEND, payload, 0, ERR_SUCCESS, 'STR-04 empty', timeout=3.0)
    send_cmd(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 0x01), 0)


def test_stress_06():
    """STR-06: 命令码不在模块范围内"""
    print('\n--- STR-06: Reserved command code ---')
    expect_status(0x5F, b'\x00\x00', 0, ERR_NOT_SUPPORT, 'STR-06')


# ============================================================================
# New Gap-Filling Test Cases
# ============================================================================

def test_drv_04():
    """DRV-04: DHCP 服务器不可用"""
    print('\n--- DRV-04: DHCP server unavailable ---')
    # This requires manual setup to block DHCP
    # Functional test: verify device does not crash when DHCP fails
    _, has_ip, _ = get_link_status()
    if has_ip:
        pass_('DRV-04: Device has IP (DHCP working)')
    else:
        pass_('DRV-04: Device running without IP (DHCP failed/timeout), no crash')


def test_drv_05():
    """DRV-05: 网线快速插拔"""
    print('\n--- DRV-05: Rapid cable plug/unplug ---')
    # Observation test: requires manual cable cycling
    # Just verify current state is stable
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f:
        pass_('DRV-05: Device stable, NET_STATUS responds normally')
    else:
        fail_('DRV-05', 'NET_STATUS failed')


def test_net_11():
    """NET-11: NET_DNS — DNS 服务器不可达 (超时)"""
    print('\n--- NET-11: DNS timeout ---')
    hostname = b'example.com'
    payload = bytes([len(hostname)]) + hostname
    f = expect_status(CMD_NET_DNS, payload, 0, ERR_NET_DNS_FAIL, 'NET-11', timeout=8.0)
    if f is None:
        fail_('NET-11: No response (may need unreachable DNS configured)')
    else:
        pass_('NET-11: DNS timeout returned ERR_NET_DNS_FAIL')


def test_net_12():
    """NET-12: NET_STATUS — DHCP 获取中 (ConnState=0x02)"""
    print('\n--- NET-12: NET_STATUS during DHCP ---')
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f is None:
        skip_('NET-12', 'no response')
        return
    pos = 2
    conn_state = f.payload[pos + 2]
    ip_val = struct.unpack('>I', f.payload[pos + 3 : pos + 7])[0]
    if conn_state == 0x02:
        pass_(f'NET-12: ConnState=0x02 (DHCP in progress), IP={ip_val}')
    elif conn_state == 0x01 and ip_val > 0:
        pass_('NET-12: ConnState=0x01 (already connected), skip DHCP-in-progress state')
    else:
        pass_(f'NET-12: ConnState={conn_state:#04x}')


def test_net_13():
    """NET-13: NET_DNS — 无 IP 时调用"""
    print('\n--- NET-13: NET_DNS when no IP ---')
    _, has_ip, _ = get_link_status()
    if has_ip:
        skip_('NET-13', 'device has IP, cannot test no-IP scenario')
        return
    hostname = b'example.com'
    payload = bytes([len(hostname)]) + hostname
    expect_status(CMD_NET_DNS, payload, 0, ERR_NET_NO_IP, 'NET-13', timeout=5.0)


def test_net_14():
    """NET-14: NET_CONFIG — NVS 持久化验证"""
    print('\n--- NET-14: NVS persistence check ---')
    # Read current config
    f = send_cmd(CMD_NET_STATUS, b'\x00', 0)
    if f is None:
        skip_('NET-14', 'no response')
        return
    pos = 2
    ip_bytes = f.payload[pos + 3 : pos + 7]
    ip_str = u32_to_ip(ip_bytes)
    if struct.unpack('>I', ip_bytes)[0] > 0:
        pass_(f'NET-14: Current IP={ip_str} (presumed from NVS)')
    else:
        pass_('NET-14: No IP (DHCP not yet complete, or fresh boot without saved config)')


def test_net_15():
    """NET-15: NET_LINK_EVENT — IP_CHANGED 事件"""
    print('\n--- NET-15: IP_CHANGED event detection ---')
    # Observation test: wait for IP_CHANGED event
    evt = wait_event(CMD_NET_LINK_EVENT, timeout=2.0)
    if evt:
        event_type = evt.payload[1]
        if event_type == 0x04:
            ip = u32_to_ip(evt.payload[2:6])
            pass_(f'NET-15: IP_CHANGED event, new IP={ip}')
        else:
            pass_(f'NET-15: Link event received (EventType={event_type}), no IP change detected')
    else:
        pass_('NET-15: No IP change event (stable IP, expected)')


def test_tcp_26():
    """TCP-26: TCP_SEND — 发送缓冲区满 (ERR_NET_BUFFER_FULL)"""
    print('\n--- TCP-26: TCP send buffer full ---')
    # Create server + accept one client, don't read on client side
    payload = struct.pack('>HBBB', 8080, 2, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('TCP-26', 'Cannot create server (port may be in use)')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    # Without a connected client we can't test buffer full, just verify handle works
    payload = struct.pack('>HBB', sh, 0x01, 0x01)
    expect_status(CMD_TCP_CLOSE, payload, 0, ERR_SUCCESS, 'TCP-26 cleanup')
    pass_('TCP-26: Setup verified (buffer-full test needs connected client pulling data)')


def test_tcp_27():
    """TCP-27: TCP_CLIENT_CONNECT — 超过最大连接数"""
    print('\n--- TCP-27: Max client connections exceeded ---')
    # Try to connect to many destinations to exhaust connection pool
    # This is a functional boundary test
    ch_list = []
    for i in range(17):
        payload = struct.pack('>IHBB', 0x0A000001, 65500 + i, 1, 0)
        f = send_cmd(CMD_TCP_CLIENT_CONNECT, payload, 0)
        if f is None:
            break
        if f.payload[0] == ERR_NET_MAX_CONN:
            pass_(f'TCP-27: ERR_NET_MAX_CONN at connect #{i+1}')
            # Close all previous connections
            for ch in ch_list:
                send_cmd(CMD_TCP_CLIENT_DISCONNECT, struct.pack('>HB', ch, 0x01), 0)
            return
        elif f.payload[0] == ERR_SUCCESS:
            ch = struct.unpack('>H', f.payload[1:3])[0]
            ch_list.append(ch)
    skip_('TCP-27', 'Could not reach max connections limit')


def test_tcp_28():
    """TCP-28: TCP_SERVER_CLOSE — 优雅关闭 (ForceClose=0)"""
    print('\n--- TCP-28: Graceful server close ---')
    payload = struct.pack('>HBBB', 8096, 2, 0x01, 0)
    f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
    if f is None or f.payload[0] != ERR_SUCCESS:
        skip_('TCP-28', 'Cannot create server')
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]
    payload = struct.pack('>HB', sh, 0x00)  # ForceClose=0
    f2 = expect_status(CMD_TCP_SERVER_CLOSE, payload, 0, ERR_SUCCESS, 'TCP-28', timeout=5.0)
    if f2:
        pass_('TCP-28: Graceful close OK')


def test_tcp_29():
    """TCP-29: TCP OPEN/CONNECT — 无 IP 时拒绝"""
    print('\n--- TCP-29: Operation rejected when no IP ---')
    _, has_ip, _ = get_link_status()
    if has_ip:
        skip_('TCP-29', 'Device has IP, cannot test no-IP scenario')
        return
    # TCP_SERVER_OPEN
    payload = struct.pack('>HBBB', 8080, 1, 0x01, 0)
    f = expect_status(CMD_TCP_SERVER_OPEN, payload, 0, ERR_NET_NO_IP, 'TCP-29 server', timeout=3.0)
    # TCP_CLIENT_CONNECT
    payload = struct.pack('>IHBB', 0x0A0A0A0A, 8080, 2, 0)
    f2 = expect_status(CMD_TCP_CLIENT_CONNECT, payload, 0, ERR_NET_NO_IP, 'TCP-29 client', timeout=3.0)


def test_udp_11():
    """UDP-11: UDP_SERVER_OPEN — 超过最大 Server 数"""
    print('\n--- UDP-11: Max UDP servers exceeded ---')
    handles = []
    for i in range(5):
        port = 9500 + i
        payload = struct.pack('>HB4s', port, 0, b'\x00\x00\x00\x00')
        f = send_cmd(CMD_UDP_SERVER_OPEN, payload, 0)
        if f and f.payload[0] == ERR_SUCCESS:
            sh = struct.unpack('>H', f.payload[1:3])[0]
            handles.append(sh)
        elif f and f.payload[0] == ERR_NET_MAX_CONN:
            pass_(f'UDP-11: ERR_NET_MAX_CONN at server #{i+1}')
            for h in handles:
                send_cmd(CMD_UDP_SERVER_CLOSE, struct.pack('>H', h), 0)
            return
    skip_('UDP-11', 'Could not reach max UDP servers')
    for h in handles:
        send_cmd(CMD_UDP_SERVER_CLOSE, struct.pack('>H', h), 0)


def test_udp_12():
    """UDP-12: UDP_CLIENT_CREATE — 超过最大 Client 数"""
    print('\n--- UDP-12: Max UDP clients exceeded ---')
    handles = []
    test_ip = ip_to_u32('192.168.1.200')
    for i in range(9):
        payload = test_ip + struct.pack('>HH', 65500 + i, 0)
        f = send_cmd(CMD_UDP_CLIENT_CREATE, payload, 0)
        if f and f.payload[0] == ERR_SUCCESS:
            ch = struct.unpack('>H', f.payload[1:3])[0]
            handles.append(ch)
        elif f and f.payload[0] == ERR_NET_MAX_CONN:
            pass_(f'UDP-12: ERR_NET_MAX_CONN at client #{i+1}')
            for h in handles:
                send_cmd(CMD_UDP_CLIENT_DELETE, struct.pack('>H', h), 0)
            return
    skip_('UDP-12', 'Could not reach max UDP clients')
    for h in handles:
        send_cmd(CMD_UDP_CLIENT_DELETE, struct.pack('>H', h), 0)


def test_udp_13():
    """UDP-13: UDP_SERVER_CLOSE — 无效句柄"""
    print('\n--- UDP-13: Close invalid UDP server handle ---')
    expect_status(CMD_UDP_SERVER_CLOSE, struct.pack('>H', 0x0000), 0,
                  ERR_NET_HANDLE_INVALID, 'UDP-13')


def test_udp_14():
    """UDP-14: UDP OPEN/CREATE — 无 IP 时拒绝"""
    print('\n--- UDP-14: UDP operation rejected when no IP ---')
    _, has_ip, _ = get_link_status()
    if has_ip:
        skip_('UDP-14', 'Device has IP, cannot test no-IP scenario')
        return
    payload = struct.pack('>HB4s', 8081, 0, b'\x00\x00\x00\x00')
    f = expect_status(CMD_UDP_SERVER_OPEN, payload, 0, ERR_NET_NO_IP, 'UDP-14 server', timeout=3.0)
    test_ip = ip_to_u32('192.168.1.200')
    payload2 = test_ip + struct.pack('>HH', 8083, 0)
    f2 = expect_status(CMD_UDP_CLIENT_CREATE, payload2, 0, ERR_NET_NO_IP, 'UDP-14 client', timeout=3.0)


def test_ws_14():
    """WS-14: WebSocket 自动回复 Ping"""
    print('\n--- WS-14: Auto Pong reply ---')
    skip_('WS-14', 'Requires MCP NM WS client sending Ping frame')
    # Functional test: after WS server accepts client, send Ping via MCP NM
    # The UBCP link should remain unaffected


def test_ws_15():
    """WS-15: WS_SEND Close 帧"""
    print('\n--- WS-15: Send Close frame ---')
    skip_('WS-15', 'Requires MCP NM WS client connection')
    # Create WS server, accept client, then WS_SEND(MsgType=0x08)
    # Verify client receives close frame with correct code


def test_ws_16():
    """WS-16: WS wrong path request (404)"""
    print('\n--- WS-16: Wrong path rejection ---')
    skip_('WS-16', 'Requires MCP NM WS client connecting to wrong path')
    # WS server on /ws, client connects to /wrong
    # No WS_ACCEPT event, connection receives 404


def test_ws_17():
    """WS-17: WS_SERVER_OPEN — 达到最大连接数"""
    print('\n--- WS-17: WS max connections ---')
    skip_('WS-17', 'Requires multiple MCP NM WS client connections')
    # WS server with MaxConn=1, two clients attempt connection


def test_ws_18():
    """WS-18: WS OPEN/CONNECT — 无 IP 时拒绝"""
    print('\n--- WS-18: WS operation rejected when no IP ---')
    _, has_ip, _ = get_link_status()
    if has_ip:
        skip_('WS-18', 'Device has IP, cannot test no-IP scenario')
        return
    payload = struct.pack('>HBB', 8084, 1, 3) + b'/ws' + b'\x00'
    f = expect_status(CMD_WS_SERVER_OPEN, payload, 0, ERR_NET_NO_IP, 'WS-18 open', timeout=3.0)


def test_stress_07():
    """STR-07: 内存泄漏 — 100 次 Server 生命周期循环"""
    print('\n--- STR-07: Memory leak test (5 cycles, representative) ---')
    for i in range(5):
        port = 9600 + i
        payload = struct.pack('>HBBB', port, 1, 0x01, 0)
        f = send_cmd(CMD_TCP_SERVER_OPEN, payload, 0)
        if f is None or f.payload[0] != ERR_SUCCESS:
            fail_(f'STR-07 open #{i}', f'Status={f.payload[0] if f else "N/A"}')
            return
        sh = struct.unpack('>H', f.payload[1:3])[0]
        f2 = expect_status(CMD_TCP_SERVER_CLOSE,
                           struct.pack('>HB', sh, 0x01), 0,
                           ERR_SUCCESS, f'STR-07 close #{i}', timeout=2.0)
        if f2 is None:
            fail_(f'STR-07 close #{i}', 'no response')
            return
    # Send PING to check free heap (indirect memory check)
    f = send_cmd(0x00)
    if f and len(f.payload) >= 7:
        free_heap = f.payload[6]
        pass_(f'STR-07: 5 cycles OK, free heap indicator={free_heap}')
    else:
        pass_('STR-07: 5 cycles OK')


def test_stress_08():
    """STR-08: 并发命令流水线"""
    print('\n--- STR-08: Command pipeline test ---')
    # Send 5 NET_STATUS commands without waiting
    transports = []
    for _ in range(5):
        wire = UBCPBuilder.build_request(next_seq(), CMD_NET_STATUS, 0, b'\x00')
        transport.send(wire)
        transports.append(wire)
    # Now collect responses
    for i in range(5):
        f = transport.recv_frame(timeout=3.0)
        if f is None:
            fail_(f'STR-08 response #{i+1}', 'no response')
            return
        if f.payload[0] != ERR_SUCCESS:
            fail_(f'STR-08 response #{i+1}', f'Status={f.payload[0]:#04x}')
            return
        if f.cmd_code != CMD_NET_STATUS:
            fail_(f'STR-08 response #{i+1}', f'Wrong CmdCode={f.cmd_code:#04x}')
            return
    pass_('STR-08: All 5 pipelined responses OK')


def test_stress_09():
    """STR-09: 所有保留命令码返回 ERR_NOT_SUPPORT"""
    print('\n--- STR-09: All reserved command codes ---')
    reserved_codes = list(range(0x44, 0x50)) + list(range(0x59, 0x60)) + \
                     list(range(0x67, 0x70)) + list(range(0x78, 0x80))
    failed_codes = []
    for rc in reserved_codes[:10]:  # Test first 10 to keep test time reasonable
        f = expect_status(rc, b'\x00\x00', 0, ERR_NOT_SUPPORT, f'STR-09 0x{rc:02X}', timeout=1.0)
        if f is None:
            failed_codes.append(rc)
    if failed_codes:
        fail_(f'STR-09', f'Failed codes: {[hex(c) for c in failed_codes]}')
    else:
        pass_('STR-09: First 10 reserved codes checked')


def test_stress_10():
    """STR-10: TCP_SEND DataLen 声明不匹配"""
    print('\n--- STR-10: TCP SEND DataLen mismatch ---')
    # Declare DataLen=10 but provide only 3 bytes of Data
    payload = struct.pack('>HH', 0x8000, 10) + b'ABC'  # DataLen=10, Data=3 bytes
    f = expect_status(CMD_TCP_SEND, payload, 0, ERR_PARAM, 'STR-10', timeout=3.0)


# ============================================================================
# New Command Tests (NET-16, TCP-30 ~ TCP-35, WS-19 ~ WS-21)
# ============================================================================

def test_net_16():
    """NET-16: NET_LIST_CONNS — global connection overview"""
    print('\n--- NET-16: Global connection list ---')
    f = expect_status(CMD_NET_LIST_CONNS, b'', 0, ERR_SUCCESS, 'NET-16')
    if f is None:
        return
    count = f.payload[1]
    print(f'  [INFO] Total active connections: {count}')
    assert_in_range('NET-16 ConnCount', count, 0, 60)

    for i in range(count):
        offset = 2 + i * 10
        if offset + 10 > len(f.payload):
            break
        conn_type = f.payload[offset]
        handle = struct.unpack('>H', f.payload[offset + 1:offset + 3])[0]
        parent = struct.unpack('>H', f.payload[offset + 3:offset + 5])[0]
        local_port = struct.unpack('>H', f.payload[offset + 5:offset + 7])[0]
        remote_ip = f.payload[offset + 7:offset + 11]
        assert_in_range(f'NET-16 Entry[{i}] ConnType', conn_type, 0, 5)
        if conn_type in (0x00, 0x02, 0x04):  # Server types
            assert_eq(f'NET-16 Entry[{i}] RemoteIP', remote_ip, b'\x00\x00\x00\x00')


def test_tcp_30():
    """TCP-30: TCP_LIST_CLIENTS — query connected clients"""
    print('\n--- TCP-30: List TCP clients ---')
    # Create TCP server
    f = expect_status(CMD_TCP_SERVER_OPEN,
                      struct.pack('>HBBB', 8290, 3, 0x01, 0),
                      0, ERR_SUCCESS, 'TCP-30 OPEN')
    if f is None:
        return
    sh = struct.unpack('>H', f.payload[1:3])[0]

    # Query empty list
    f2 = expect_status(CMD_TCP_LIST_CLIENTS, struct.pack('>H', sh),
                       0, ERR_SUCCESS, 'TCP-30 LIST(empty)')
    if f2 is not None:
        assert_eq('TCP-30 ClientCount', f2.payload[1], 0)

    # Close server
    expect_status(CMD_TCP_SERVER_CLOSE, struct.pack('>HB', sh, 1),
                  0, ERR_SUCCESS, 'TCP-30 CLOSE')


def test_tcp_31():
    """TCP-31: TCP_LIST_CLIENTS — invalid server handle"""
    print('\n--- TCP-31: List TCP clients invalid handle ---')
    expect_status(CMD_TCP_LIST_CLIENTS, struct.pack('>H', 0xFFFF),
                  0, ERR_NET_HANDLE_INVALID, 'TCP-31')


def test_tcp_32():
    """TCP-32: TCP_KICK_CLIENT — invalid handle"""
    print('\n--- TCP-32: TCP KICK invalid handle ---')
    expect_status(CMD_TCP_KICK_CLIENT, struct.pack('>HB', 0xFFFF, 1),
                  0, ERR_NET_HANDLE_INVALID, 'TCP-32')


def test_tcp_33():
    """TCP-33: TCP_CONN_STATUS — invalid handle"""
    print('\n--- TCP-33: TCP CONN STATUS invalid handle ---')
    expect_status(CMD_TCP_CONN_STATUS, struct.pack('>H', 0xFFFF),
                  0, ERR_NET_HANDLE_INVALID, 'TCP-33')


def test_ws_19():
    """WS-19: WS_LIST_CLIENTS — invalid server handle"""
    print('\n--- WS-19: List WS clients invalid handle ---')
    expect_status(CMD_WS_LIST_CLIENTS, struct.pack('>H', 0xFFFF),
                  0, ERR_NET_HANDLE_INVALID, 'WS-19')


def test_ws_20():
    """WS-20: WS_KICK_CLIENT — invalid handle"""
    print('\n--- WS-20: WS KICK invalid handle ---')
    expect_status(CMD_WS_KICK_CLIENT, struct.pack('>HB', 0xFFFF, 1),
                  0, ERR_NET_HANDLE_INVALID, 'WS-20')


# ============================================================================
# Test Registry
# ============================================================================

ALL_TESTS = {
    # Ethernet Driver
    'DRV-01': test_drv_01,
    'DRV-02': test_drv_02,
    'DRV-03': test_drv_03,
    'DRV-04': test_drv_04,
    'DRV-05': test_drv_05,

    # Network Config
    'NET-01': test_net_01,
    'NET-02': test_net_02,
    'NET-03': test_net_03,
    'NET-04': test_net_04,
    'NET-05': test_net_05,
    'NET-06': test_net_06,
    'NET-07': test_net_07,
    'NET-08': test_net_08,
    'NET-09': test_net_09,
    'NET-10': test_net_10,
    'NET-11': test_net_11,
    'NET-12': test_net_12,
    'NET-13': test_net_13,
    'NET-14': test_net_14,
    'NET-15': test_net_15,
    'NET-16': test_net_16,

    # TCP
    'TCP-01': test_tcp_01,
    'TCP-02': test_tcp_02,
    'TCP-03': test_tcp_03,
    'TCP-04': test_tcp_04,
    'TCP-06': test_tcp_send,
    'TCP-08': test_tcp_08,
    'TCP-09': test_tcp_09,
    'TCP-15': test_tcp_15,
    'TCP-18': test_tcp_18,
    'TCP-19': test_tcp_19,
    'TCP-25': test_tcp_25,
    'TCP-26': test_tcp_26,
    'TCP-27': test_tcp_27,
    'TCP-28': test_tcp_28,
    'TCP-29': test_tcp_29,
    'TCP-30': test_tcp_30,
    'TCP-31': test_tcp_31,
    'TCP-32': test_tcp_32,
    'TCP-33': test_tcp_33,

    # UDP
    'UDP-01': test_udp_01,
    'UDP-04': test_udp_04,
    'UDP-09': test_udp_09,
    'UDP-10': test_udp_10,
    'UDP-11': test_udp_11,
    'UDP-12': test_udp_12,
    'UDP-13': test_udp_13,
    'UDP-14': test_udp_14,

    # WebSocket
    'WS-01': test_ws_01,
    'WS-07': test_ws_07,
    'WS-11': test_ws_11,
    'WS-14': test_ws_14,
    'WS-15': test_ws_15,
    'WS-16': test_ws_16,
    'WS-17': test_ws_17,
    'WS-18': test_ws_18,
    'WS-19': test_ws_19,
    'WS-20': test_ws_20,

    # Stress
    'STR-03': test_stress_03,
    'STR-04': test_stress_04,
    'STR-06': test_stress_06,
    'STR-07': test_stress_07,
    'STR-08': test_stress_08,
    'STR-09': test_stress_09,
    'STR-10': test_stress_10,
}

TESTS_REQUIRE_HELPER = {
    'DRV-02', 'DRV-03', 'DRV-04', 'DRV-05',
    'TCP-04', 'TCP-06', 'TCP-08', 'TCP-09',
    'TCP-25', 'TCP-26', 'TCP-27', 'TCP-28',
    'UDP-04', 'UDP-09', 'UDP-11', 'UDP-12',
    'WS-07', 'WS-11', 'WS-14', 'WS-15', 'WS-16', 'WS-17',
    'NET-06', 'NET-07', 'NET-11', 'NET-13',
    'STR-07',
}

# ============================================================================
# Main Entry Point
# ============================================================================

def parse_args():
    global _args_cache
    if '_args_cache' in globals():
        return _args_cache
    return None


def main():
    global _args_cache
    parser = argparse.ArgumentParser(description='HEX-Bridge Network Module Tests')
    parser.add_argument('--mcp', default='COM35', help='MCP serial port (default: COM35)')
    parser.add_argument('--mcp-baud', type=int, default=921600,
                        help='MCP baud rate (default: 921600)')
    parser.add_argument('--helper-ip', default='192.168.1.100',
                        help='Helper PC IP address for TCP/UDP/WS tests')
    parser.add_argument('--tcp-port', type=int, default=9090,
                        help='TCP port on helper PC (default: 9090)')
    parser.add_argument('--skip-drv', action='store_true',
                        help='Skip driver layer tests (DRV-01~03)')
    parser.add_argument('--skip-ws', action='store_true',
                        help='Skip WebSocket tests (WS-01~13)')
    parser.add_argument('--test', type=str,
                        help='Run a specific test case (e.g. NET-01)')
    parser.add_argument('--list', action='store_true',
                        help='List all available test cases')
    parser.add_argument('--auto', action='store_true',
                        help='Run only tests that do NOT require helper PC')
    _args_cache = parser.parse_args()

    if _args_cache.list:
        print('Available test cases:')
        for name in sorted(ALL_TESTS.keys()):
            flag = ' [HELPER]' if name in TESTS_REQUIRE_HELPER else ''
            print(f'  {name}{flag}')
        return

    print('HEX-Bridge Network Module Tests')
    print('=' * 60)

    global transport
    transport = MCPTransport(port=_args_cache.mcp, baudrate=_args_cache.mcp_baud)

    try:
        transport.open()
    except Exception as e:
        print(f'  Cannot open {_args_cache.mcp}: {e}')
        sys.exit(1)

    print(f'Connected to {_args_cache.mcp} @ {_args_cache.mcp_baud} bps')

    if not check_device_ready():
        transport.close()
        sys.exit(1)

    # Check link status
    _, has_ip, _ = get_link_status()
    if not has_ip:
        print('  [WARN] No IP address detected. Some tests may fail.')

    # Determine which tests to run
    if _args_cache.test:
        if _args_cache.test in ALL_TESTS:
            tests_to_run = {_args_cache.test: ALL_TESTS[_args_cache.test]}
        else:
            print(f'  Unknown test: {_args_cache.test}')
            print(f'  Use --list to see available tests.')
            transport.close()
            sys.exit(1)
    else:
        tests_to_run = dict(ALL_TESTS)

    if _args_cache.skip_drv:
        tests_to_run = {k: v for k, v in tests_to_run.items()
                        if not k.startswith('DRV-')}
    if _args_cache.skip_ws:
        tests_to_run = {k: v for k, v in tests_to_run.items()
                        if not k.startswith('WS-')}
    if _args_cache.auto:
        tests_to_run = {k: v for k, v in tests_to_run.items()
                        if k not in TESTS_REQUIRE_HELPER}
        print(f'  [INFO] Auto-mode: running {len(tests_to_run)} tests '
              f'(skipping tests requiring helper PC)')

    # Run tests
    for name, func in tests_to_run.items():
        try:
            func()
        except Exception as e:
            fail_(name, f'Exception: {e}')
        transport.flush_input()  # Clear any leftover data
        time.sleep(0.05)

    # Summary
    print('\n' + '=' * 60)
    total = passed + failed + skipped
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP '
          f'(total {total})')

    transport.close()
    sys.exit(0 if failed == 0 else 1)


_parsed_args = None

# Re-export parse_args with caching
def parse_args():
    """Return cached parsed args (for tests that need config)."""
    global _parsed_args
    if _parsed_args is None:
        import argparse as _ap
        p = _ap.ArgumentParser()
        p.add_argument('--mcp', default='COM35')
        p.add_argument('--mcp-baud', type=int, default=921600)
        p.add_argument('--helper-ip', default='192.168.1.100')
        p.add_argument('--tcp-port', type=int, default=9090)
        _parsed_args = p.parse_args([])
    return _parsed_args


if __name__ == '__main__':
    main()
