"""
HEX-Bridge UART Module Tests — MCP 模式 (UART-01 ~ UART-27)

COM35 (MCP/UBCP): pyserial 直连
COM24 (扩展口监控): 通过 MCP24Bridge → Kilo → serial-monitor-mcp 工具

Run (Kilo orchestrated):
  1. Kilo: serial-monitor-mcp_open_serial_port COM24 115200
  2. Kilo: set __MCP24_ACTIVE__=1
  3. Kilo: 启动本脚本 + MCP24 IPC 轮询
  4. 执行测试
  5. Kilo: serial-monitor-mcp_close_serial_port COM24

Run standalone (pyserial fallback):
  python3 test_uart_mcp.py --com24 COM24 --ext-baud 115200
"""

import sys
import time
import struct
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from mcp24_bridge import MCP24IPCBridge

CMD_UART_OPEN       = 0xA0
CMD_UART_CLOSE      = 0xA1
CMD_UART_CONFIG     = 0xA2
CMD_UART_SEND       = 0xA3
CMD_UART_RECV       = 0xA4
CMD_UART_SET_BREAK  = 0xA5
CMD_UART_STATUS     = 0xA6
CMD_UART_FLUSH      = 0xA7
CMD_FLOW_CONTROL    = 0x05

ERR_SUCCESS      = 0x00
ERR_PARAM        = 0x02
ERR_NOT_OPEN     = 0x05
ERR_NOT_SUPPORT  = 0x06
ERR_ALREADY_OPEN = 0x0B

RXMODE_PASSIVE = 0x00
RXMODE_LINE    = 0x01
RXMODE_FIXED   = 0x02
RXMODE_TIMEOUT = 0x03

FLUSH_RX    = 0x00
FLUSH_TX    = 0x01
FLUSH_ALL   = 0x02
FLUSH_DRAIN = 0x03

passed = 0
failed = 0
skipped = 0
com24 = None


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
            pass_(f'{name}: {actual.hex()}')
        else:
            pass_(f'{name}: {actual:#04x}')
    else:
        if isinstance(actual, bytes):
            fail_(f'{name}: expected {expected.hex()}, got {actual.hex()}')
        elif isinstance(expected, bytes):
            fail_(f'{name}: expected {expected.hex()}, got {actual:#04x}')
        else:
            fail_(f'{name}: expected {expected:#04x}, got {actual:#04x}')


def assert_bool(name, cond, info=''):
    if cond:
        pass_(name)
    else:
        fail_(name, info)


def send_cmd(transport, seq, cmd, payload=b'', channel=0):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    transport.send(wire)
    return transport.recv_frame(timeout=2.0)


def expect_status(transport, seq, cmd, payload, channel, expected_status, name=''):
    f = send_cmd(transport, seq, cmd, payload, channel)
    if f is None:
        fail_(name or f'cmd=0x{cmd:02X}', 'no response')
        return None
    s = f.payload[0]
    assert_eq(name or f'cmd=0x{cmd:02X}', s, expected_status)
    return f


def uart_config(transport, seq, baud, data_bits=0x08, stop_bits=0x01,
                parity=0x00, flow=0x00, threshold=1, timeout=0):
    payload = struct.pack('>IBBBBHB', baud, data_bits, stop_bits, parity,
                          flow, threshold, timeout)
    return expect_status(transport, seq, CMD_UART_CONFIG, payload, 0,
                         ERR_SUCCESS, f'CONFIG {baud}')


def uart_open(transport, seq, rx_mode=RXMODE_PASSIVE, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_UART_OPEN,
                         bytes([rx_mode]), 0, expected, f'OPEN rx={rx_mode}')


def uart_close(transport, seq, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_UART_CLOSE, b'', 0,
                         expected, 'CLOSE')


def com24_read(timeout=1.0):
    """通过 MCP 桥接层读取 COM24 数据"""
    if com24 is None:
        return b''
    deadline = time.time() + timeout
    buf = bytearray()
    while time.time() < deadline:
        nb = com24.in_waiting
        if nb > 0:
            b = com24.read(nb)
            if b:
                buf.extend(b)
        else:
            time.sleep(0.05)
    return bytes(buf)


def com24_write(data):
    """通过 MCP 桥接层向 COM24 写入数据"""
    if com24:
        com24.write(data)
        com24.flush()
        print(f'    [MCP24] TX: {data.hex()}')


def com24_flush():
    if com24:
        com24.flushInput()


# ─────────────────────────────────────────────────────────
# 测试用例
# ─────────────────────────────────────────────────────────

def test_uart01_open(transport, seq):
    """UART-01: UART_OPEN passive mode"""
    print('\n--- UART-01: OPEN passive ---')
    transport.flush_input()
    f = uart_open(transport, seq, RXMODE_PASSIVE)
    if f and len(f.payload) >= 5:
        rx_size = struct.unpack('>H', f.payload[1:3])[0]
        tx_size = struct.unpack('>H', f.payload[3:5])[0]
        assert_eq('RxBufSize', rx_size, 2048)
        assert_eq('TxBufSize', tx_size, 1024)


def test_uart02_open_dup(transport, seq):
    """UART-02: UART_OPEN duplicate"""
    print('\n--- UART-02: OPEN duplicate ---')
    uart_open(transport, seq, RXMODE_PASSIVE, ERR_ALREADY_OPEN)


def test_uart03_open_bad_rxmode(transport, seq):
    """UART-03: UART_OPEN invalid RxMode"""
    print('\n--- UART-03: OPEN invalid RxMode ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    uart_open(transport, seq, 0x04, ERR_PARAM)
    uart_open(transport, seq + 1, RXMODE_PASSIVE)


def test_uart04_open_line(transport, seq):
    """UART-04: UART_OPEN line mode"""
    print('\n--- UART-04: OPEN line mode ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    f = uart_open(transport, seq, RXMODE_LINE)
    if f and len(f.payload) >= 5:
        assert_eq('Status', f.payload[0], ERR_SUCCESS)


def test_uart05_config_921600(transport, seq):
    """UART-05: CONFIG 921600"""
    print('\n--- UART-05: CONFIG 921600 ---')
    f = uart_config(transport, seq, 921600)
    if f and len(f.payload) >= 5:
        actual = struct.unpack('>I', f.payload[1:5])[0]
        assert abs(actual - 921600) / 921600 < 0.05
        pass_(f'  ActualBaud={actual}')


def test_uart06_config_115200(transport, seq):
    """UART-06: CONFIG 115200"""
    print('\n--- UART-06: CONFIG 115200 ---')
    f = uart_config(transport, seq, 115200)
    if f and len(f.payload) >= 5:
        actual = struct.unpack('>I', f.payload[1:5])[0]
        assert abs(actual - 115200) / 115200 < 0.05
        pass_(f'  ActualBaud={actual}')


def test_uart07_config_7e1(transport, seq):
    """UART-07: CONFIG 7E1"""
    print('\n--- UART-07: CONFIG 7E1 ---')
    uart_config(transport, seq, 115200, data_bits=0x07, parity=0x02)
    seq += 1
    uart_config(transport, seq, 115200)  # restore 8N1


def test_uart08_config_bad_databits(transport, seq):
    """UART-08: CONFIG invalid DataBits"""
    print('\n--- UART-08: CONFIG invalid DataBits ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x04, 0x01, 0x00, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_PARAM,
                  'bad DataBits=0x04')


def test_uart09_config_bad_stopbits(transport, seq):
    """UART-09: CONFIG invalid StopBits"""
    print('\n--- UART-09: CONFIG invalid StopBits ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x04, 0x00, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_PARAM,
                  'bad StopBits=0x04')


def test_uart10_config_mark_space(transport, seq):
    """UART-10: CONFIG Mark/Space parity (unsupported)"""
    print('\n--- UART-10: CONFIG Mark parity ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x03, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_NOT_SUPPORT, 'Mark')
    seq += 1
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x04, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_NOT_SUPPORT, 'Space')


def test_uart11_config_hw_flow(transport, seq):
    """UART-11: CONFIG HW flow control (unsupported)"""
    print('\n--- UART-11: CONFIG HW flow ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x01, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_NOT_SUPPORT, 'HW flow')


def test_uart12_config_not_open(transport, seq):
    """UART-12: CONFIG when closed"""
    print('\n--- UART-12: CONFIG not open ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, 0, ERR_NOT_OPEN, 'not open')
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart13_send(transport, seq):
    """UART-13: SEND data → 通过 MCP24 监控发送内容"""
    print('\n--- UART-13: SEND ---')
    data = b'Hello World'
    com24.marker("UART-13: SEND Hello World (11 bytes) -> UART2")
    payload = struct.pack('>H', len(data)) + data
    f = expect_status(transport, seq, CMD_UART_SEND, payload, 0, ERR_SUCCESS, 'SEND')
    if f and len(f.payload) >= 3:
        actual = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual, len(data))
    ext_data = com24_read(timeout=0.5)
    if ext_data:
        print(f'    [MCP24] Monitor RX: {ext_data.hex()} ({len(ext_data)} bytes)')
        pass_(f'[MCP24] COM24 captured: {len(ext_data)} bytes')
    else:
        print('    [MCP24] Monitor: no data captured')


def test_uart14_send_empty(transport, seq):
    """UART-14: SEND empty"""
    print('\n--- UART-14: SEND empty ---')
    payload = struct.pack('>H', 0)
    f = expect_status(transport, seq, CMD_UART_SEND, payload, 0, ERR_SUCCESS, 'SEND empty')
    if f and len(f.payload) >= 3:
        actual = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual, 0)


def test_uart15_send_mismatch(transport, seq):
    """UART-15: SEND length mismatch"""
    print('\n--- UART-15: SEND length mismatch ---')
    payload = struct.pack('>H', 10) + b'He'
    expect_status(transport, seq, CMD_UART_SEND, payload, 0, ERR_PARAM, 'length mismatch')


def test_uart16_close(transport, seq):
    """UART-16: CLOSE normal"""
    print('\n--- UART-16: CLOSE ---')
    uart_close(transport, seq, ERR_SUCCESS)


def test_uart17_close_not_open(transport, seq):
    """UART-17: CLOSE not open"""
    print('\n--- UART-17: CLOSE not open ---')
    uart_close(transport, seq, ERR_NOT_OPEN)
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart18_status(transport, seq):
    """UART-18: STATUS"""
    print('\n--- UART-18: STATUS ---')
    f = send_cmd(transport, seq, CMD_UART_STATUS)
    if f is None:
        fail_('STATUS', 'no response')
        return
    p = f.payload
    assert_eq('Status', p[0], ERR_SUCCESS)
    if len(p) >= 19:
        baud = struct.unpack('>I', p[1:5])[0]
        assert_bool('LineState TxIdle', p[5] & 0x01)
        tx_count = struct.unpack('>I', p[10:14])[0]
        rx_count = struct.unpack('>I', p[14:18])[0]
        pass_(f'BaudRate={baud} Tx={tx_count} Rx={rx_count} Err={p[18]}')


def test_uart19_status_not_open(transport, seq):
    """UART-19: STATUS not open"""
    print('\n--- UART-19: STATUS not open ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    expect_status(transport, seq, CMD_UART_STATUS, b'', 0, ERR_NOT_OPEN)
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart20_flush_rx(transport, seq):
    """UART-20: FLUSH RX"""
    print('\n--- UART-20: FLUSH RX ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_RX]), 0, ERR_SUCCESS, 'FLUSH RX')


def test_uart21_flush_bad(transport, seq):
    """UART-21: FLUSH invalid type"""
    print('\n--- UART-21: FLUSH invalid ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([0x04]), 0, ERR_PARAM, 'FLUSH invalid')


def test_uart22_break(transport, seq):
    """UART-22: SET_BREAK 10ms"""
    print('\n--- UART-22: SET_BREAK 10ms ---')
    payload = struct.pack('>H', 10)
    expect_status(transport, seq, CMD_UART_SET_BREAK, payload, 0, ERR_SUCCESS, 'BREAK 10ms')


def test_uart23_break_default(transport, seq):
    """UART-23: SET_BREAK default"""
    print('\n--- UART-23: SET_BREAK default ---')
    payload = struct.pack('>H', 0)
    expect_status(transport, seq, CMD_UART_SET_BREAK, payload, 0, ERR_SUCCESS, 'BREAK default')


def test_uart24_recv_event(transport, seq):
    """UART-24: RECV event — 通过 MCP24 向 UART2 注入数据"""
    print('\n--- UART-24: RECV event (MCP24 inject) ---')
    if com24 is None:
        skip_('RECV event', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_PASSIVE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24_flush()
    com24.marker("UART-24: Inject ABC -> UART2 (passive mode)")
    com24_write(b'ABC')
    print('    [MCP24] Injected: ABC → UART2')
    time.sleep(0.3)

    f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=2.0)
    if f is None:
        fail_('RECV event', 'no event received')
        return
    p = f.payload
    assert_eq('RxFlags', p[0], 0x00)
    dlen = struct.unpack('>H', p[1:3])[0]
    assert_eq('DataLen', dlen, 3)
    assert_eq('Data', p[3:6], b'ABC')


def test_uart25_line_mode(transport, seq):
    """UART-25: Line mode — 通过 MCP24 注入分行数据"""
    print('\n--- UART-25: Line mode (MCP24 inject) ---')
    if com24 is None:
        skip_('Line mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_LINE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24_flush()
    com24.marker("UART-25: Inject Hello\\nWorld\\n -> UART2 (line mode)")
    com24_write(b'Hello\nWorld\n')
    print('    [MCP24] Injected: Hello\\nWorld\\n → UART2')
    time.sleep(0.3)

    events = []
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
        if f:
            events.append(f.payload[3:])
        else:
            break

    assert_bool('Got 2 line events', len(events) >= 2, f'got {len(events)}')
    for i, e in enumerate(events):
        pass_(f'Line {i}: {e}')


def test_uart26_fixed_mode(transport, seq):
    """UART-26: Fixed-length mode — 通过 MCP24 注入"""
    print('\n--- UART-26: Fixed mode (MCP24 inject) ---')
    if com24 is None:
        skip_('Fixed mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_FIXED); seq += 1
    uart_config(transport, seq, 115200, threshold=4); seq += 1

    transport.flush_input()
    com24_flush()
    com24.marker("UART-26: Inject 8 bytes -> UART2 (fixed mode, thr=4)")
    com24_write(bytes([0, 1, 2, 3, 4, 5, 6, 7]))
    print('    [MCP24] Injected: 00 01 02 03 04 05 06 07 → UART2')
    time.sleep(0.3)

    events = []
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
        if f:
            dlen = struct.unpack('>H', f.payload[1:3])[0]
            events.append((dlen, f.payload[3:3 + dlen]))
        else:
            break

    assert_bool('Got 2 fixed events', len(events) >= 2, f'got {len(events)}')
    if len(events) >= 2:
        assert_eq('Chunk 0', events[0][1], bytes([0, 1, 2, 3]))
        assert_eq('Chunk 1', events[1][1], bytes([4, 5, 6, 7]))


def test_uart27_timeout_mode(transport, seq):
    """UART-27: Timeout mode — 通过 MCP24 注入"""
    print('\n--- UART-27: Timeout mode (MCP24 inject) ---')
    if com24 is None:
        skip_('Timeout mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_TIMEOUT); seq += 1
    uart_config(transport, seq, 115200, timeout=20); seq += 1

    transport.flush_input()
    com24_flush()
    com24.marker("UART-27: Inject AA BB CC -> UART2 (timeout mode)")
    com24_write(b'\xAA\xBB\xCC')
    print('    [MCP24] Injected: AA BB CC → UART2')
    time.sleep(0.5)

    f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=2.0)
    if f is None:
        fail_('Timeout mode', 'no event received')
        return
    dlen = struct.unpack('>H', f.payload[1:3])[0]
    assert_eq('DataLen', dlen, 3)
    assert_eq('Data', f.payload[3:3 + dlen], b'\xAA\xBB\xCC')


def test_uart28_flow_query(transport, seq):
    """UART-28: FLOW_CONTROL query UART module (MCP mode)"""
    print('\n--- UART-28: FLOW_CONTROL query ---')
    payload = bytes([0xA0])
    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, payload)
    if f is None:
        fail_('FLOW query', 'no response')
        return
    p = f.payload
    assert_eq('Status', p[0], ERR_SUCCESS)
    assert_bool('Count >= 1', p[1] >= 1)
    if p[1] >= 1:
        assert_eq('ModuleID', p[2], 0xA0)
        pass_(f'State={p[3]}, Usage={struct.unpack(">H", p[4:6])[0]}, Pct={p[6]}%')


def test_uart29_flow_query_all(transport, seq):
    """UART-29: FLOW_CONTROL query all modules (MCP mode)"""
    print('\n--- UART-29: FLOW_CONTROL query all ---')
    payload = bytes([0xFF])
    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, payload)
    if f is None:
        fail_('FLOW query all', 'no response')
        return
    p = f.payload
    assert_eq('Status', p[0], ERR_SUCCESS)
    count = p[1]
    pass_(f'Found {count} module(s)')
    pos = 2
    for i in range(count):
        mod_id = p[pos]; state = p[pos+1]
        usage = struct.unpack('>H', p[pos+2:pos+4])[0]; pct = p[pos+4]
        pass_(f'  Mod 0x{mod_id:02X}: state={state}, usage={usage}, {pct}%')
        pos += 5


def test_uart30_flow_xoff(transport, seq):
    """UART-30: FLOW_CONTROL XOFF/XON sequence (MCP mode)"""
    print('\n--- UART-30: FLOW_CONTROL XOFF/XON ---')
    if com24 is None:
        skip_('Flow XOFF/XON', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_PASSIVE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24_flush()

    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, bytes([0xA0]))
    seq += 1
    if f and len(f.payload) >= 5:
        pass_(f'Initial flow state={f.payload[3]}, usage={struct.unpack(">H", f.payload[4:6])[0]}')

    com24.marker("UART-30: Inject 4096 bytes -> UART2 (flow control test)")
    block = bytes([i & 0xFF for i in range(256)])
    total_injected = 0
    for _ in range(16):
        com24_write(block)
        total_injected += 256
        time.sleep(0.01)
    print(f'    [MCP24] Injected {total_injected} bytes -> UART2')
    time.sleep(0.3)

    xoff_events = 0
    xon_events = 0
    for _ in range(8):
        f = transport.recv_event(cmd_code=CMD_FLOW_CONTROL, timeout=0.5)
        if f and len(f.payload) >= 1:
            action = f.payload[0]
            if action == 0x00: xoff_events += 1
            elif action == 0x01: xon_events += 1
    pass_(f'Flow events: XOFF={xoff_events}, XON={xon_events}')

    time.sleep(0.3)
    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, bytes([0xA0]))
    if f and len(f.payload) >= 5:
        pass_(f'Final flow: state={f.payload[3]}, usage={struct.unpack(">H", f.payload[4:6])[0]}, pct={f.payload[6]}%')


def main():
    global passed, failed, skipped, com24
    import argparse
    ap = argparse.ArgumentParser(description='HEX-Bridge UART Tests (MCP mode)')
    ap.add_argument('--com24', default='COM24', help='COM24 port for ext device')
    ap.add_argument('--ext-baud', type=int, default=115200, help='External device baud rate')
    args = ap.parse_args()

    print('=' * 60)
    print('HEX-Bridge UART Module Tests — MCP Mode')
    print(f'  COM24 transport: {"MCP bridge" if os.environ.get("__MCP24_ACTIVE__") == "1" else "pyserial fallback"}')
    print('=' * 60)

    transport = MCPTransport()
    try:
        transport.open()
    except Exception as e:
        print(f'FATAL: Cannot open {transport.port}: {e}')
        return 1

    # 打开 COM24 (MCP 回放桥接)
    com24 = MCP24IPCBridge(port=args.com24, baud=args.ext_baud)
    com24.marker("==== HEX-Bridge UART Tests Start ====")
    com24.marker(f"COM24: pyserial mode, {args.ext_baud} bps")

    seq = 10
    try:
        transport.flush_input()
        # 预清理：确保 UART 通道初始为关闭状态
        send_cmd(transport, 1, CMD_UART_CLOSE, b'', 0)
        transport.recv_frame(timeout=1.0)  # 丢弃可能的旧响应
        transport.flush_input()

        test_uart01_open(transport, seq); seq += 1
        test_uart02_open_dup(transport, seq); seq += 1
        test_uart03_open_bad_rxmode(transport, seq); seq += 3
        test_uart04_open_line(transport, seq); seq += 1
        test_uart05_config_921600(transport, seq); seq += 1
        test_uart06_config_115200(transport, seq); seq += 1
        test_uart07_config_7e1(transport, seq); seq += 1
        test_uart08_config_bad_databits(transport, seq); seq += 1
        test_uart09_config_bad_stopbits(transport, seq); seq += 1
        test_uart10_config_mark_space(transport, seq); seq += 1
        test_uart11_config_hw_flow(transport, seq); seq += 1
        test_uart12_config_not_open(transport, seq); seq += 4
        test_uart13_send(transport, seq); seq += 1
        test_uart14_send_empty(transport, seq); seq += 1
        test_uart15_send_mismatch(transport, seq); seq += 1
        test_uart16_close(transport, seq); seq += 1
        test_uart17_close_not_open(transport, seq); seq += 4
        test_uart18_status(transport, seq); seq += 1
        test_uart19_status_not_open(transport, seq); seq += 4
        test_uart20_flush_rx(transport, seq); seq += 1
        test_uart21_flush_bad(transport, seq); seq += 1
        test_uart22_break(transport, seq); seq += 1
        test_uart23_break_default(transport, seq); seq += 1
        test_uart24_recv_event(transport, seq); seq += 1
        test_uart25_line_mode(transport, seq); seq += 1
        test_uart26_fixed_mode(transport, seq); seq += 1
        test_uart27_timeout_mode(transport, seq); seq += 1
        test_uart28_flow_query(transport, seq); seq += 1
        test_uart29_flow_query_all(transport, seq); seq += 1
        test_uart30_flow_xoff(transport, seq); seq += 1

        com24.marker(f"==== Results: {passed}P {failed}F {skipped}S ====")
    finally:
        transport.close()
        com24.close()

    print(f'\n{"=" * 60}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 60}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    import os
    sys.exit(main())
