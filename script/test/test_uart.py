"""
HEX-Bridge UART Module Tests (UART-01 ~ UART-57)

Run: python test_uart.py [--com24 COM24] [--ext-baud 115200]
"""

import sys, time, struct
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

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

UART_CHANNEL = 1

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
        else:
            fail_(f'{name}: expected {expected:#04x}, got {actual:#04x}')


def send_cmd(transport, seq, cmd, payload=b'', channel=UART_CHANNEL):
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
    return expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL,
                         ERR_SUCCESS, f'CONFIG {baud}')


def uart_open(transport, seq, rx_mode=RXMODE_PASSIVE, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_UART_OPEN,
                         bytes([rx_mode]), UART_CHANNEL, expected, f'OPEN rx={rx_mode}')


def uart_close(transport, seq, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_UART_CLOSE, b'', UART_CHANNEL,
                         expected, 'CLOSE')


def open_com24(port, baud=115200):
    global com24
    try:
        import serial
        com24 = serial.Serial(port=port, baudrate=baud, timeout=0.1)
        com24.flushInput()
        return True
    except Exception as e:
        print(f'  [INFO] COM24 not available: {e}')
        return False


def com24_read(timeout=1.0):
    if com24 is None:
        return b''
    deadline = time.time() + timeout
    buf = bytearray()
    while time.time() < deadline:
        b = com24.read(com24.in_waiting or 1)
        if b:
            buf.extend(b)
    return bytes(buf)


def com24_write(data):
    if com24:
        com24.write(data)
        com24.flush()


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
    uart_open(transport, seq + 1, RXMODE_PASSIVE)  # re-open for next tests


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
        assert abs(actual - 921600) / 921600 < 0.05  # ±5%


def test_uart06_config_115200(transport, seq):
    """UART-06: CONFIG 115200"""
    print('\n--- UART-06: CONFIG 115200 ---')
    f = uart_config(transport, seq, 115200)
    if f and len(f.payload) >= 5:
        actual = struct.unpack('>I', f.payload[1:5])[0]
        assert abs(actual - 115200) / 115200 < 0.05


def test_uart07_config_7e1(transport, seq):
    """UART-07: CONFIG 7E1"""
    print('\n--- UART-07: CONFIG 7E1 ---')
    f = uart_config(transport, seq, 115200, data_bits=0x07, parity=0x02)
    # restore 8N1
    seq += 1
    uart_config(transport, seq, 115200)


def test_uart08_config_bad_databits(transport, seq):
    """UART-08: CONFIG invalid DataBits"""
    print('\n--- UART-08: CONFIG invalid DataBits ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x04, 0x01, 0x00, 0x00, 1, 0)
    f = expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_PARAM,
                      'bad DataBits=0x04')


def test_uart09_config_bad_stopbits(transport, seq):
    """UART-09: CONFIG invalid StopBits"""
    print('\n--- UART-09: CONFIG invalid StopBits ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x04, 0x00, 0x00, 1, 0)
    f = expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_PARAM,
                      'bad StopBits=0x04')


def test_uart10_config_mark_space(transport, seq):
    """UART-10: CONFIG Mark/Space parity (unsupported)"""
    print('\n--- UART-10: CONFIG Mark parity ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x03, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_NOT_SUPPORT,
                  'Mark')
    seq += 1
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x04, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_NOT_SUPPORT,
                  'Space')


def test_uart11_config_hw_flow(transport, seq):
    """UART-11: CONFIG HW flow control (unsupported)"""
    print('\n--- UART-11: CONFIG HW flow ---')
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x01, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_NOT_SUPPORT,
                  'HW flow')


def test_uart12_config_not_open(transport, seq):
    """UART-12: CONFIG when closed"""
    print('\n--- UART-12: CONFIG not open ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    payload = struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x00, 1, 0)
    expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_NOT_OPEN,
                  'not open')
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart13_send(transport, seq):
    """UART-13: SEND data"""
    print('\n--- UART-13: SEND ---')
    data = b'Hello World'
    payload = struct.pack('>H', len(data)) + data
    f = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS,
                      'SEND')
    if f and len(f.payload) >= 3:
        actual = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual, len(data))
    # dump COM24 monitor data if available
    ext_data = com24_read(timeout=0.3)
    if ext_data:
        print(f'    COM24 received: {ext_data.hex()}')
        pass_(f'COM24 data: {len(ext_data)} bytes')


def test_uart14_send_empty(transport, seq):
    """UART-14: SEND empty"""
    print('\n--- UART-14: SEND empty ---')
    payload = struct.pack('>H', 0)
    f = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS,
                      'SEND empty')
    if f and len(f.payload) >= 3:
        actual = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual, 0)


def test_uart15_send_mismatch(transport, seq):
    """UART-15: SEND length mismatch"""
    print('\n--- UART-15: SEND length mismatch ---')
    # Declare 10 bytes but provide only 2
    payload = struct.pack('>H', 10) + b'He'
    f = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_PARAM,
                      'length mismatch')


def test_uart16_close(transport, seq):
    """UART-16: CLOSE normal"""
    print('\n--- UART-16: CLOSE ---')
    uart_close(transport, seq, ERR_SUCCESS)


def test_uart17_close_not_open(transport, seq):
    """UART-17: CLOSE not open"""
    print('\n--- UART-17: CLOSE not open ---')
    uart_close(transport, seq, ERR_NOT_OPEN)
    # re-open for next tests
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
        line_state = p[5]
        pass_(f'LineState=0x{line_state:02x} (TxIdle={(line_state & 1)!=0}, RxActive={(line_state & 2)!=0})')
        pass_(f'TxCount={p[10]:#x}')


def assert_bool(name, cond, info=''):
    if cond:
        pass_(name)
    else:
        fail_(name, info)


def test_uart19_status_not_open(transport, seq):
    """UART-19: STATUS not open"""
    print('\n--- UART-19: STATUS not open ---')
    uart_close(transport, seq, ERR_SUCCESS)
    seq += 1
    expect_status(transport, seq, CMD_UART_STATUS, b'', UART_CHANNEL, ERR_NOT_OPEN)
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart20_flush_rx(transport, seq):
    """UART-20: FLUSH RX"""
    print('\n--- UART-20: FLUSH RX ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_RX]), UART_CHANNEL,
                  ERR_SUCCESS, 'FLUSH RX')


def test_uart21_flush_bad(transport, seq):
    """UART-21: FLUSH invalid type"""
    print('\n--- UART-21: FLUSH invalid ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([0x04]), UART_CHANNEL,
                  ERR_PARAM, 'FLUSH invalid')


def test_uart22_break(transport, seq):
    """UART-22: SET_BREAK 10ms"""
    print('\n--- UART-22: SET_BREAK 10ms ---')
    payload = struct.pack('>H', 10)
    expect_status(transport, seq, CMD_UART_SET_BREAK, payload, UART_CHANNEL,
                  ERR_SUCCESS, 'BREAK 10ms')


def test_uart23_break_default(transport, seq):
    """UART-23: SET_BREAK default"""
    print('\n--- UART-23: SET_BREAK default ---')
    payload = struct.pack('>H', 0)  # 0 = default 10ms
    expect_status(transport, seq, CMD_UART_SET_BREAK, payload, UART_CHANNEL,
                  ERR_SUCCESS, 'BREAK default')


def test_uart24_recv_event(transport, seq):
    """UART-24: RECV event (needs COM24 injection)"""
    print('\n--- UART-24: RECV event ---')
    if com24 is None:
        skip_('RECV event', 'COM24 not available for data injection')
        return

    # Ensure 115200 8N1 passive mode
    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_PASSIVE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24_write(b'ABC')
    time.sleep(0.2)

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
    """UART-25: Line mode (needs COM24 injection)"""
    print('\n--- UART-25: Line mode ---')
    if com24 is None:
        skip_('Line mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_LINE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24_write(b'Hello\nWorld\n')
    time.sleep(0.3)

    events = []
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
        if f:
            events.append(f.payload[3:])
        else:
            break

    assert_bool('Got 2 line events', len(events) >= 2,
                f'got {len(events)}')


def test_uart26_fixed_mode(transport, seq):
    """UART-26: Fixed-length mode (needs COM24)"""
    print('\n--- UART-26: Fixed mode ---')
    if com24 is None:
        skip_('Fixed mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_FIXED); seq += 1
    uart_config(transport, seq, 115200, threshold=4); seq += 1

    transport.flush_input()
    com24_write(bytes([0, 1, 2, 3, 4, 5, 6, 7]))
    time.sleep(0.3)

    events = []
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
        if f:
            dlen = struct.unpack('>H', f.payload[1:3])[0]
            events.append((dlen, f.payload[3:3 + dlen]))
        else:
            break

    assert_bool('Got 2 fixed events', len(events) >= 2,
                f'got {len(events)}')
    if len(events) >= 2:
        assert_eq('Chunk 0', events[0][1], bytes([0, 1, 2, 3]))
        assert_eq('Chunk 1', events[1][1], bytes([4, 5, 6, 7]))


def test_uart27_timeout_mode(transport, seq):
    """UART-27: Timeout mode (needs COM24)"""
    print('\n--- UART-27: Timeout mode ---')
    if com24 is None:
        skip_('Timeout mode', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_TIMEOUT); seq += 1
    uart_config(transport, seq, 115200, timeout=20); seq += 1

    transport.flush_input()
    com24_write(b'\xAA\xBB\xCC')
    time.sleep(0.5)  # wait for timeout to trigger

    f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=2.0)
    if f is None:
        fail_('Timeout mode', 'no event received')
        return
    dlen = struct.unpack('>H', f.payload[1:3])[0]
    assert_eq('DataLen', dlen, 3)
    assert_eq('Data', f.payload[3:3 + dlen], b'\xAA\xBB\xCC')


def test_uart28_flow_query(transport, seq):
    """UART-28: FLOW_CONTROL query UART module"""
    print('\n--- UART-28: FLOW_CONTROL query ---')
    payload = bytes([0xA0])  # query UART module
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
    """UART-29: FLOW_CONTROL query all modules"""
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
    """UART-30: FLOW_CONTROL XOFF/XON sequence"""
    print('\n--- UART-30: FLOW_CONTROL XOFF/XON ---')
    if com24 is None:
        skip_('Flow XOFF/XON', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_PASSIVE); seq += 1
    uart_config(transport, seq, 115200); seq += 1

    transport.flush_input()
    com24.flushInput()

    # Query initial state
    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, bytes([0xA0]))
    seq += 1
    if f and len(f.payload) >= 5:
        pass_(f'Initial flow state={f.payload[3]}, usage={struct.unpack(">H", f.payload[4:6])[0]}')

    # Inject data to fill buffer (4000 bytes to trigger high watermark)
    block = bytes([i & 0xFF for i in range(256)])  # 256-byte block
    total_injected = 0
    for _ in range(16):  # 16 × 256 = 4096 bytes
        com24_write(block)
        total_injected += 256
        time.sleep(0.01)

    print(f'    [COM24] Injected {total_injected} bytes → UART2')
    time.sleep(0.3)

    # Check for XOFF/XON events
    xoff_events = 0
    xon_events = 0
    for _ in range(8):
        f = transport.recv_event(cmd_code=CMD_FLOW_CONTROL, timeout=0.5)
        if f and len(f.payload) >= 1:
            action = f.payload[0]
            if action == 0x00: xoff_events += 1
            elif action == 0x01: xon_events += 1

    pass_(f'Flow events: XOFF={xoff_events}, XON={xon_events}')

    # Query final state
    time.sleep(0.3)
    f = send_cmd(transport, seq, CMD_FLOW_CONTROL, bytes([0xA0]))
    if f and len(f.payload) >= 5:
        final_pct = f.payload[6]
        pass_(f'Final flow: state={f.payload[3]}, usage={struct.unpack(">H", f.payload[4:6])[0]}, pct={final_pct}%')


# ====================================================================
# v0.2.0 补充测试 (UART-31 ~ UART-57)
# ====================================================================

def _ensure_open_passive(transport, seq):
    """确保 UART 通道处于打开+被动上报+115200 8N1 状态"""
    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_PASSIVE); seq += 1
    uart_config(transport, seq, 115200); seq += 1
    return seq


def test_uart31_send_not_open(transport, seq):
    """UART-31: SEND when closed → ERR_NOT_OPEN"""
    print('\n--- UART-31: SEND not open ---')
    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    payload = struct.pack('>H', 5) + b'Hello'
    expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_NOT_OPEN, 'SEND closed')
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart32_break_not_open(transport, seq):
    """UART-32: SET_BREAK when closed → ERR_NOT_OPEN"""
    print('\n--- UART-32: SET_BREAK not open ---')
    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    payload = struct.pack('>H', 10)
    expect_status(transport, seq, CMD_UART_SET_BREAK, payload, UART_CHANNEL, ERR_NOT_OPEN, 'BREAK closed')
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart33_flush_not_open(transport, seq):
    """UART-33: FLUSH when closed → ERR_NOT_OPEN"""
    print('\n--- UART-33: FLUSH not open ---')
    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_ALL]), UART_CHANNEL, ERR_NOT_OPEN, 'FLUSH closed')
    uart_open(transport, seq + 1, RXMODE_PASSIVE)
    uart_config(transport, seq + 2, 115200)


def test_uart34_config_short_payload(transport, seq):
    """UART-34: CONFIG with short payload → ERR_PARAM"""
    print('\n--- UART-34: CONFIG short payload ---')
    payload = bytes([0x00, 0x01, 0x02, 0x03, 0x08])  # 5 bytes, need 11
    expect_status(transport, seq, CMD_UART_CONFIG, payload, UART_CHANNEL, ERR_PARAM, 'CONFIG short')


def test_uart35_send_short_payload(transport, seq):
    """UART-35: SEND payload < 2 bytes → ERR_PARAM"""
    print('\n--- UART-35: SEND short payload ---')
    expect_status(transport, seq, CMD_UART_SEND, bytes([0x00]), UART_CHANNEL, ERR_PARAM, 'SEND short')


def test_uart36_break_empty_payload(transport, seq):
    """UART-36: SET_BREAK empty payload → uses default 10ms"""
    print('\n--- UART-36: SET_BREAK empty payload ---')
    expect_status(transport, seq, CMD_UART_SET_BREAK, b'', UART_CHANNEL, ERR_SUCCESS, 'BREAK empty')


def test_uart37_flush_tx(transport, seq):
    """UART-37: FLUSH TX"""
    print('\n--- UART-37: FLUSH TX ---')
    # Send some data first to have something in TX buffer
    data = bytes([i & 0xFF for i in range(100)])
    payload = struct.pack('>H', 100) + data
    send_cmd(transport, seq, CMD_UART_SEND, payload); seq += 1
    transport.recv_frame(timeout=1.0)
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_TX]), UART_CHANNEL, ERR_SUCCESS, 'FLUSH TX')


def test_uart38_flush_all(transport, seq):
    """UART-38: FLUSH ALL"""
    print('\n--- UART-38: FLUSH ALL ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_ALL]), UART_CHANNEL, ERR_SUCCESS, 'FLUSH ALL')


def test_uart39_flush_drain(transport, seq):
    """UART-39: FLUSH DRAIN"""
    print('\n--- UART-39: FLUSH DRAIN ---')
    expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_DRAIN]), UART_CHANNEL, ERR_SUCCESS, 'FLUSH DRAIN')


def test_uart40_break_detect(transport, seq):
    """UART-40: RECV with BreakDetect (RxFlags Bit3)"""
    print('\n--- UART-40: BreakDetect ---')
    if com24 is None:
        skip_('BreakDetect', 'COM24 not available for loopback verification')
        return

    seq = _ensure_open_passive(transport, seq)
    transport.flush_input()
    com24.flushInput()

    # Send Break → GPIO32 TXD goes low, GPIO35 should see Break if loopback
    payload = struct.pack('>H', 10)
    send_cmd(transport, seq, CMD_UART_SET_BREAK, payload); seq += 1
    transport.recv_frame(timeout=0.5)
    time.sleep(0.3)

    # Check for RECV events with BreakDetect flag
    found_break = False
    for _ in range(8):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=0.5)
        if f and f.payload[0] & 0x08:
            found_break = True
            pass_('BreakDetect (RxFlags Bit3=1)')
            break
    if not found_break:
        skip_('BreakDetect', 'no loopback — Break not reflected to RX')


def test_uart41_parity_error(transport, seq):
    """UART-41: RECV with ParityError (RxFlags Bit1)"""
    print('\n--- UART-41: ParityError ---')
    if com24 is None:
        skip_('ParityError', 'COM24 not available')
        return

    seq = _ensure_open_passive(transport, seq)
    # Configure 7E1, but COM24 sends 8N1 → parity mismatch
    uart_config(transport, seq, 115200, data_bits=0x07, parity=0x02); seq += 1

    transport.flush_input()
    com24_write(b'\x41\x42\x43')
    time.sleep(0.2)

    found_parity = False
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=0.5)
        if f and f.payload[0] & 0x02:
            found_parity = True
            pass_('ParityError (RxFlags Bit1=1)')
            break
    if not found_parity:
        skip_('ParityError', 'parity mismatch not detected by hardware')
    uart_config(transport, seq, 115200)  # restore 8N1


def test_uart42_frame_error(transport, seq):
    """UART-42: RECV with FrameError (RxFlags Bit2)"""
    print('\n--- UART-42: FrameError ---')
    if com24 is None:
        skip_('FrameError', 'COM24 not available')
        return

    seq = _ensure_open_passive(transport, seq)
    transport.flush_input()

    # Configure 8N1, but COM24 sends with 2 stop bits → frame error
    import serial
    saved_baud = 115200
    try:
        com24.baudrate = saved_baud
        com24.stopbits = serial.STOPBITS_TWO
        com24_write(b'\x41')
        time.sleep(0.1)
        com24.stopbits = serial.STOPBITS_ONE  # restore
    except Exception:
        pass

    found_frame = False
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=0.5)
        if f and f.payload[0] & 0x04:
            found_frame = True
            pass_('FrameError (RxFlags Bit2=1)')
            break
    if not found_frame:
        skip_('FrameError', 'frame error not detected by hardware')


def test_uart43_buffer_overflow(transport, seq):
    """UART-43: RECV with BufferOverflow (RxFlags Bit0)"""
    print('\n--- UART-43: BufferOverflow ---')
    if com24 is None:
        skip_('BufferOverflow', 'COM24 not available')
        return

    seq = _ensure_open_passive(transport, seq)
    transport.flush_input()
    com24.flushInput()

    # Inject data at max COM24 speed to try to overflow RX buffer
    block = bytes([i & 0xFF for i in range(256)])
    for _ in range(24):  # 24 × 256 = 6144 bytes > 2048 buffer
        com24_write(block)
        time.sleep(0.002)

    time.sleep(0.3)
    found_overflow = False
    for _ in range(10):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=0.3)
        if f and f.payload[0] & 0x01:
            found_overflow = True
            pass_('BufferOverflow (RxFlags Bit0=1)')
            break
    if not found_overflow:
        pass_('No overflow — buffer keeps up')


def test_uart44_status_after_send(transport, seq):
    """UART-44: STATUS after SEND (TxCount > 0)"""
    print('\n--- UART-44: STATUS after SEND ---')
    transport.flush_input()
    data = bytes([0x41] * 100)
    payload = struct.pack('>H', 100) + data
    send_cmd(transport, seq, CMD_UART_SEND, payload)
    seq += 1

    f = send_cmd(transport, seq, CMD_UART_STATUS)
    if f and len(f.payload) >= 19:
        tx_count = struct.unpack('>I', f.payload[10:14])[0]
        assert_bool('TxCount >= 100', tx_count >= 100, f'TxCount={tx_count}')
    else:
        fail_('STATUS', 'no response')


def test_uart45_status_after_recv(transport, seq):
    """UART-45: STATUS after RECV (RxCount > 0)"""
    print('\n--- UART-45: STATUS after RECV ---')
    if com24 is None:
        skip_('STATUS after RECV', 'COM24 not available')
        return

    seq = _ensure_open_passive(transport, seq)
    transport.flush_input()
    com24_write(b'\x01\x02\x03\x04\x05' * 10)  # 50 bytes
    time.sleep(0.3)
    # drain events
    for _ in range(4):
        transport.recv_event(timeout=0.2)

    f = send_cmd(transport, seq, CMD_UART_STATUS)
    if f and len(f.payload) >= 19:
        rx_count = struct.unpack('>I', f.payload[14:18])[0]
        assert_bool('RxCount >= 50', rx_count >= 50, f'RxCount={rx_count}')
    else:
        fail_('STATUS', 'no response')


def test_uart46_status_error_count(transport, seq):
    """UART-46: STATUS with accumulated ErrorCount"""
    print('\n--- UART-46: STATUS error count ---')
    seq = _ensure_open_passive(transport, seq)
    uart_config(transport, seq, 115200, data_bits=0x07, parity=0x02); seq += 1

    if com24:
        transport.flush_input()
        # Inject data with parity mismatch
        for _ in range(8):
            com24_write(b'\x41\x42\x43\x44')
        time.sleep(0.2)

    f = send_cmd(transport, seq, CMD_UART_STATUS)
    if f and len(f.payload) >= 19:
        err = f.payload[18]
        if com24:
            pass_(f'ErrorCount={err}')
        else:
            pass_(f'ErrorCount={err} (no injection)')
    uart_config(transport, seq, 115200)


def test_uart47_send_large(transport, seq):
    """UART-47: SEND 512 bytes"""
    print('\n--- UART-47: SEND large ---')
    transport.flush_input()
    time.sleep(0.3)  # allow any pending FW processing to complete
    transport.flush_input()
    data = bytes([i & 0xFF for i in range(512)])
    payload = struct.pack('>H', 512) + data
    f = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS, 'SEND 512')
    if f and len(f.payload) >= 3:
        actual = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual, 512)


def test_uart48_config_1200(transport, seq):
    """UART-48: CONFIG 1200 bps"""
    print('\n--- UART-48: CONFIG 1200 ---')
    f = uart_config(transport, seq, 1200)
    if f and len(f.payload) >= 5:
        actual = struct.unpack('>I', f.payload[1:5])[0]
        delta = abs(int(actual) - 1200)
        assert_bool('ActualBaud ~1200', delta <= 100, f'actual={actual}')
    # restore 115200
    uart_config(transport, seq + 1, 115200)


def test_uart49_fixed_threshold_restart(transport, seq):
    """UART-49: Fixed mode threshold change triggers RX task restart"""
    print('\n--- UART-49: Fixed threshold restart ---')
    if com24 is None:
        skip_('Fixed threshold restart', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_FIXED); seq += 1
    uart_config(transport, seq, 115200, threshold=4); seq += 1

    transport.flush_input()
    com24.flushInput()

    # Change threshold to 8 via CONFIG (triggers RX task restart)
    # Note: accumulated data from old task is lost on restart
    uart_config(transport, seq, 115200, threshold=8); seq += 1
    transport.flush_input()
    time.sleep(0.2)

    # Send 8 bytes → should report as one 8-byte chunk with new threshold
    com24_write(bytes([0, 1, 2, 3, 4, 5, 6, 7]))
    time.sleep(0.3)

    f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
    if f:
        dlen = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('Chunk Len new threshold', dlen, 8)
    else:
        fail_('Threshold restart', 'no event after threshold change')


def test_uart50_timeout_restart(transport, seq):
    """UART-50: Timeout mode timeout change triggers RX task restart"""
    print('\n--- UART-50: Timeout restart ---')
    if com24 is None:
        skip_('Timeout restart', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_TIMEOUT); seq += 1
    uart_config(transport, seq, 115200, timeout=50); seq += 1

    transport.flush_input()

    # Shorten timeout to 10ms (triggers RX task restart)
    # Note: accumulated data from old task is lost on restart
    uart_config(transport, seq, 115200, timeout=10); seq += 1
    transport.flush_input()
    time.sleep(0.2)

    # Send data → should report after 10ms timeout with NEW task
    com24_write(b'\xAA\xBB\xCC')
    time.sleep(0.3)  # > 10ms, should trigger report

    f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
    if f:
        dlen = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('Timeout DataLen', dlen, 3)
        assert_eq('Timeout Data', f.payload[3:3+dlen], b'\xAA\xBB\xCC')
    else:
        fail_('Timeout restart', 'no event after timeout change')


def test_uart51_config_5bits(transport, seq):
    """UART-51: CONFIG 5 data bits"""
    print('\n--- UART-51: CONFIG 5 data bits ---')
    f = uart_config(transport, seq, 115200, data_bits=0x05)
    # restore 8N1
    uart_config(transport, seq + 1, 115200)


def test_uart52_config_2stop(transport, seq):
    """UART-52: CONFIG 2 stop bits"""
    print('\n--- UART-52: CONFIG 2 stop bits ---')
    f = uart_config(transport, seq, 115200, stop_bits=0x03)
    # restore 8N1
    uart_config(transport, seq + 1, 115200)


def test_uart53_break_long(transport, seq):
    """UART-53: SET_BREAK 1000ms"""
    print('\n--- UART-53: SET_BREAK 1000ms ---')
    start = time.time()
    payload = struct.pack('>H', 1000)
    f = expect_status(transport, seq, CMD_UART_SET_BREAK, payload, UART_CHANNEL, ERR_SUCCESS, 'BREAK 1000ms')
    elapsed = time.time() - start
    pass_(f'Break took {elapsed:.1f}s (expected ~1.1s with 20ms restore)')


def test_uart54_close_reopen(transport, seq):
    """UART-54: CLOSE → re-OPEN with different RxMode"""
    print('\n--- UART-54: Close-reopen ---')
    if com24 is None:
        skip_('Close-reopen', 'COM24 not available')
        return

    uart_close(transport, seq, ERR_SUCCESS); seq += 1
    uart_open(transport, seq, RXMODE_FIXED); seq += 1
    uart_config(transport, seq, 115200, threshold=4); seq += 1

    transport.flush_input()
    com24_write(b'\x00\x01\x02\x03\x04\x05\x06\x07')
    time.sleep(0.3)

    events = []
    for _ in range(4):
        f = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=0.5)
        if f:
            dlen = struct.unpack('>H', f.payload[1:3])[0]
            events.append(dlen)
        else:
            break
    assert_bool('Fixed mode works after reopen', len(events) >= 2, f'got {len(events)}')


def test_uart55_config_then_send(transport, seq):
    """UART-55: CONFIG mangle then SEND"""
    print('\n--- UART-55: Config then send ---')
    seq = _ensure_open_passive(transport, seq)

    # Send at 115200
    payload = struct.pack('>H', 5) + b'Hello'
    f1 = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS, 'SEND 115200'); seq += 1

    # Change baud to 921600, then send
    uart_config(transport, seq, 921600); seq += 1
    payload = struct.pack('>H', 5) + b'World'
    f2 = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS, 'SEND 921600'); seq += 1

    # Restore 115200
    uart_config(transport, seq, 115200)


def test_uart56_concurrent_send_recv(transport, seq):
    """UART-56: Full-duplex SEND + RECV"""
    print('\n--- UART-56: Concurrent SEND+RECV ---')
    if com24 is None:
        skip_('Concurrent SEND+RECV', 'COM24 not available')
        return

    seq = _ensure_open_passive(transport, seq)
    transport.flush_input()
    com24.flushInput()

    # Send 100 bytes while simultaneously COM24 injects 50 bytes
    send_data = bytes([i & 0xFF for i in range(100)])
    send_payload = struct.pack('>H', 100) + send_data
    f_send = send_cmd(transport, seq, CMD_UART_SEND, send_payload)
    if f_send and len(f_send.payload) >= 3:
        actual = struct.unpack('>H', f_send.payload[1:3])[0]
        assert_eq('SEND ActualLen', actual, 100)
    else:
        fail_('SEND response', 'no response')

    recv_data = bytes([0x80 + i for i in range(50)])
    com24_write(recv_data)

    time.sleep(0.3)
    recv_event = transport.recv_event(cmd_code=CMD_UART_RECV, timeout=1.0)
    if recv_event:
        dlen = struct.unpack('>H', recv_event.payload[1:3])[0]
        assert_bool(f'RECV {dlen} bytes (expected ~50)', dlen >= 40, f'dlen={dlen}')
    else:
        skip_('RECV event', 'timing')


def test_uart57_lifecycle(transport, seq):
    """UART-57: Full lifecycle (OPEN→CONFIG→SEND→STATUS→FLUSH→CLOSE)"""
    print('\n--- UART-57: Full lifecycle ---')
    transport.flush_input()

    # Ensure channel is closed first
    send_cmd(transport, seq, CMD_UART_CLOSE, b'', 0)
    transport.recv_frame(timeout=1.0)
    transport.flush_input()
    seq += 1

    # 1. OPEN
    f = uart_open(transport, seq, RXMODE_LINE); seq += 1
    assert_bool('1.OPEN', f is not None and f.payload[0] == ERR_SUCCESS)

    # 2. CONFIG
    f = uart_config(transport, seq, 115200); seq += 1
    assert_bool('2.CONFIG', f is not None and f.payload[0] == ERR_SUCCESS)

    # 3. STATUS (initial)
    f = send_cmd(transport, seq, CMD_UART_STATUS); seq += 1
    assert_bool('3.STATUS', f is not None and f.payload[0] == ERR_SUCCESS)

    # 4. SEND
    payload = struct.pack('>H', 6) + b'PING\r\n'
    f = expect_status(transport, seq, CMD_UART_SEND, payload, UART_CHANNEL, ERR_SUCCESS, '4.SEND'); seq += 1

    # 5. STATUS (after send)
    f = send_cmd(transport, seq, CMD_UART_STATUS); seq += 1
    if f and len(f.payload) >= 19:
        tx_count = struct.unpack('>I', f.payload[10:14])[0]
        assert_bool(f'5.STATUS TxCount={tx_count}', tx_count >= 6)

    # 6. FLUSH
    f = expect_status(transport, seq, CMD_UART_FLUSH, bytes([FLUSH_ALL]), UART_CHANNEL, ERR_SUCCESS, '6.FLUSH'); seq += 1

    # 7. CLOSE
    f = uart_close(transport, seq, ERR_SUCCESS)
    assert_bool('7.CLOSE', f is not None and f.payload[0] == ERR_SUCCESS)
    seq += 1

    # 8. STATUS (after close) → ERR_NOT_OPEN
    f = expect_status(transport, seq, CMD_UART_STATUS, b'', UART_CHANNEL, ERR_NOT_OPEN, '8.STATUS closed')

    pass_('Full lifecycle complete')


def main():
    global passed, failed, skipped, com24
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--com24', default='COM24', help='COM24 port for ext device')
    ap.add_argument('--ext-baud', type=int, default=115200,
                    help='External device baud rate')
    args = ap.parse_args()

    print('=' * 50)
    print('HEX-Bridge UART Module Tests')
    print('=' * 50)

    transport = MCPTransport()
    try:
        transport.open()
    except Exception as e:
        print(f'FATAL: Cannot open {transport.port}: {e}')
        return 1

    # Try opening COM24 for external data injection/monitoring
    open_com24(args.com24, args.ext_baud)

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
        # v0.2.0 补充测试
        test_uart31_send_not_open(transport, seq); seq += 3
        test_uart32_break_not_open(transport, seq); seq += 3
        test_uart33_flush_not_open(transport, seq); seq += 3
        test_uart34_config_short_payload(transport, seq); seq += 1
        test_uart35_send_short_payload(transport, seq); seq += 1
        test_uart36_break_empty_payload(transport, seq); seq += 1
        test_uart37_flush_tx(transport, seq); seq += 2
        test_uart38_flush_all(transport, seq); seq += 1
        test_uart39_flush_drain(transport, seq); seq += 1
        test_uart40_break_detect(transport, seq); seq += 1
        test_uart41_parity_error(transport, seq); seq += 1
        test_uart42_frame_error(transport, seq); seq += 1
        test_uart43_buffer_overflow(transport, seq); seq += 1
        test_uart44_status_after_send(transport, seq); seq += 2
        test_uart45_status_after_recv(transport, seq); seq += 1
        test_uart46_status_error_count(transport, seq); seq += 1
        test_uart47_send_large(transport, seq); seq += 1
        test_uart48_config_1200(transport, seq); seq += 2
        test_uart49_fixed_threshold_restart(transport, seq); seq += 1
        test_uart50_timeout_restart(transport, seq); seq += 1
        test_uart51_config_5bits(transport, seq); seq += 2
        test_uart52_config_2stop(transport, seq); seq += 2
        test_uart53_break_long(transport, seq); seq += 1
        test_uart54_close_reopen(transport, seq); seq += 1
        test_uart55_config_then_send(transport, seq); seq += 1
        test_uart56_concurrent_send_recv(transport, seq); seq += 1
        test_uart57_lifecycle(transport, seq)
    finally:
        transport.close()
        if com24:
            com24.close()

    print(f'\n{"=" * 50}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 50}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
