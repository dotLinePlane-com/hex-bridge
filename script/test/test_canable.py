"""
HEX-Bridge CAN Module Tests via CANable 2.0 (slcan, supports CAN FD)

This test suite drives the HEX-Bridge MCP2518FD CAN FD controller from a
CANable 2.0 device (normaldotcom/canable2-fw) instead of PCAN-USB.
The CANable speaks LAWICEL slcan with CAN FD extensions over a serial port.

Prerequisites:
  - Firmware with CAN module (mod_can.c) flashed
  - CANable 2.0 connected to CAN bus (both ends 120ohm terminated)
  - CANable serial port (default COM6)

Usage:
  python test_canable.py                          # all classic + FD
  python test_canable.py --mcp COM4 --canable COM6
  python test_canable.py --baud 500k
  python test_canable.py --no-fd                  # classic only
"""

import sys
import time
import struct

from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from canable_slcan import CanableChannel, CanableMessage

# ── Protocol Constants ─────────────────────────────────────────────────────

CMD_CAN_OPEN        = 0x10
CMD_CAN_CLOSE       = 0x11
CMD_CAN_CONFIG      = 0x12
CMD_CAN_SEND        = 0x13
CMD_CAN_RECV        = 0x14
CMD_CAN_FILTER      = 0x15
CMD_CAN_STATUS      = 0x16
CMD_CAN_BUS_EVENT   = 0x17
CMD_CAN_ERROR_EVENT = 0x18
CMD_CAN_SLEEP       = 0x19
CMD_CAN_WAKEUP      = 0x1A
CMD_CAN_FILTER_BATCH = 0x1B

ERR_SUCCESS           = 0x00
ERR_PARAM             = 0x02
ERR_NOT_OPEN          = 0x05
ERR_NOT_SUPPORT       = 0x06
ERR_CHANNEL_INVALID   = 0x0A
ERR_ALREADY_OPEN      = 0x0B
ERR_CAN_BAUD_UNSUPPORT = 0x18
ERR_HAL_FAIL          = 0x17

CAN_CHANNEL = 3

CAN_MODE_NORMAL      = 0x00
CAN_MODE_LISTEN_ONLY = 0x01
CAN_MODE_LOOPBACK    = 0x02

FILTER_TYPE_STD  = 0x00
FILTER_TYPE_EXT  = 0x01
FILTER_TYPE_BOTH = 0x02

CAN_FLAG_EXT = 0x80000000
CAN_FLAG_RTR = 0x40000000
CAN_FLAG_FD  = 0x20000000
CAN_FLAG_BRS = 0x10000000
CAN_ID_EXT_MAX = 0x1FFFFFFF

# ── Test State ─────────────────────────────────────────────────────────────

passed = 0
failed = 0
skipped = 0


def pass_(name):
    global passed; passed += 1
    print(f'  [PASS] {name}')


def fail_(name, msg=''):
    global failed; failed += 1
    print(f'  [FAIL] {name}: {msg}')


def skip_(name, reason=''):
    global skipped; skipped += 1
    print(f'  [SKIP] {name}: {reason}')


def assert_eq(name, actual, expected):
    if actual == expected:
        print(f'  [PASS] {name}: {actual}')
        global passed; passed += 1
    else:
        fail_(f'{name}: expected {expected}, got {actual}')


def assert_bool(name, cond, info=''):
    if cond:
        pass_(name)
    else:
        fail_(name, info)


# ── MCP Helpers ────────────────────────────────────────────────────────────

def send_cmd(transport, seq, cmd, payload=b'', channel=CAN_CHANNEL):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    transport.send(wire)
    f = transport.recv_response(cmd_code=cmd, seq_num=seq, timeout=3.0)
    if f is not None and (not f.is_response or f.is_event or
                          (f.seq_num, f.cmd_code, f.channel_id) != (seq, cmd, channel)):
        return None
    return f


def expect_status(transport, seq, cmd, payload, channel, expected, name=''):
    f = send_cmd(transport, seq, cmd, payload, channel)
    if f is None:
        fail_(name or f'cmd=0x{cmd:02X}', 'no response')
        return None
    if not f.payload:
        fail_(name or f'cmd=0x{cmd:02X}', 'empty STATUS response')
        return None
    success_size = {CMD_CAN_CONFIG: 1, CMD_CAN_SEND: 5}.get(cmd)
    if f.payload[0] == ERR_SUCCESS and success_size is not None and len(f.payload) != success_size:
        fail_(name or f'cmd=0x{cmd:02X}', 'invalid success response length')
        return None
    assert_eq(name or f'cmd=0x{cmd:02X}', f.payload[0], expected)
    return f


def can_open(transport, seq, mode=CAN_MODE_NORMAL, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_CAN_OPEN, bytes([mode]),
                         CAN_CHANNEL, expected, f'OPEN mode={mode}')


def can_close(transport, seq, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL,
                         expected, 'CLOSE')


def can_config(transport, seq, baud_idx, flags=0x03, fd_baud_idx=0,
               expected=ERR_SUCCESS):
    payload = struct.pack('>BBBB', baud_idx, flags, 32, fd_baud_idx)
    return expect_status(transport, seq, CMD_CAN_CONFIG, payload, CAN_CHANNEL,
                         expected, f'CONFIG baud={baud_idx:#04x} flags={flags:#04x}')


def can_send(transport, seq, can_id, data, is_ext=False, is_rtr=False,
             is_fd=False, is_brs=False, expected=ERR_SUCCESS):
    flags_val = 0
    if is_ext: flags_val |= CAN_FLAG_EXT
    if is_rtr: flags_val |= CAN_FLAG_RTR
    if is_fd:  flags_val |= CAN_FLAG_FD
    if is_brs: flags_val |= CAN_FLAG_BRS
    can_id_raw = (flags_val | (can_id & CAN_ID_EXT_MAX)) & 0xFFFFFFFF
    dlc = len(data)
    if is_fd:
        dlc_enc = mcp_fd_dlc(dlc)
    else:
        dlc_enc = dlc
    payload = struct.pack('>IB', can_id_raw, dlc_enc) + data
    return expect_status(transport, seq, CMD_CAN_SEND, payload, CAN_CHANNEL,
                         expected, f'SEND ID={can_id:#x}')


def mcp_fd_dlc(n):
    if n <= 8: return n
    elif n <= 12: return 9
    elif n <= 16: return 10
    elif n <= 20: return 11
    elif n <= 24: return 12
    elif n <= 32: return 13
    elif n <= 48: return 14
    else: return 15


def can_status(transport, seq, expected=ERR_SUCCESS):
    f = send_cmd(transport, seq, CMD_CAN_STATUS)
    if f is None:
        fail_('STATUS', 'no response')
        return None
    assert_eq('STATUS.Status', f.payload[0], expected)
    if f.payload[0] == ERR_SUCCESS and len(f.payload) >= 28:
        bs, tec, rec = f.payload[1], f.payload[2], f.payload[3]
        tx = struct.unpack('>H', f.payload[8:10])[0]
        rx = struct.unpack('>H', f.payload[10:12])[0]
        pass_(f'BusState={bs}, TEC={tec}, REC={rec}, Tx={tx}, Rx={rx}')
    return f


def can_filter(transport, seq, idx, mask, code, enable=1,
               ftype=FILTER_TYPE_STD, fifo_num=1, expected=ERR_SUCCESS):
    payload = struct.pack('>BIIBBB', idx, mask, code, enable, ftype, fifo_num)
    return expect_status(transport, seq, CMD_CAN_FILTER, payload, CAN_CHANNEL,
                         expected, f'FILTER idx={idx}')


# ── Canable helpers ────────────────────────────────────────────────────────

def wait_matching(receive, matches, timeout):
    """Ignore other bus traffic without extending the total observation window."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        item = receive(timeout=remaining)
        if item is None:
            return None
        if matches(item):
            return item
    return None


def recv_canable(can, can_id, timeout=1.0):
    # Assert all flags after matching the ID: a wrong type must fail, not vanish.
    return wait_matching(can.recv, lambda msg: msg.id == can_id, timeout)


def event_id(frame):
    if frame.channel_id != CAN_CHANNEL or len(frame.payload) < 10:
        raise ValueError('Malformed CAN_RECV event or wrong CAN channel')
    raw = struct.unpack_from('>I', frame.payload)[0]
    if len(frame.payload) != 10 + frame.payload[4]:
        raise ValueError('CAN_RECV length does not match DLC/data/flags/timestamp')
    return raw & (CAN_ID_EXT_MAX if raw & CAN_FLAG_EXT else 0x7FF)


def recv_can_event(transport, can_id, timeout=2.0):
    return wait_matching(lambda timeout: transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=timeout),
                         lambda frame: event_id(frame) == can_id, timeout)


def check_canable(name, msg, can_id, data, *, extended=False, rtr=False, fd=False, brs=False):
    if msg is None:
        fail_(name, f'no frame for ID {can_id:#x}')
        return
    assert_eq(name + ' ID', msg.id, can_id)
    assert_eq(name + ' EXT', msg.is_extended, extended)
    assert_eq(name + ' RTR', msg.is_rtr, rtr)
    assert_eq(name + ' FD', msg.is_fd, fd)
    assert_eq(name + ' BRS', msg.is_brs, brs)
    assert_eq(name + ' DLC', msg.dlc, len(data))
    assert_eq(name + ' data', msg.data, data)


def check_event(name, frame, can_id, data, *, extended=False, fd=False, brs=False):
    if frame is None:
        fail_(name, f'no event for ID {can_id:#x}')
        return
    event_id(frame)
    expected_raw = can_id | (CAN_FLAG_EXT if extended else 0) | (CAN_FLAG_FD if fd else 0)
    if brs and not extended:
        expected_raw |= CAN_FLAG_BRS
    assert_eq(name + ' CanID/flags', struct.unpack_from('>I', frame.payload)[0], expected_raw)
    assert_eq(name + ' DLC', frame.payload[4], len(data))
    assert_eq(name + ' data', frame.payload[5:5 + frame.payload[4]], data)
    assert_eq(name + ' RxFlags', frame.payload[5 + frame.payload[4]], 0x08 if brs else 0)


def drain_events(transport, timeout=0.2):
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        if transport.recv_event(timeout=remaining) is None:
            break


def canable_setup(can, baud=500000, data_baud=2000000, silent=False):
    # S/Y commands are only valid while closed. This helper is also used to
    # restore a channel that previous tests have left open.
    can.cmd_close()
    can.set_bitrate(baud)
    can.set_data_bitrate(data_baud)
    can.set_silent(silent)
    can.set_retransmit(True)
    can.cmd_open()
    time.sleep(0.3)


def mcp_open_classic(transport, seq, baud_idx=0x06):
    transport.flush_input()
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
    transport.recv_frame(timeout=1.0)
    transport.flush_input(); seq += 1
    can_open(transport, seq, CAN_MODE_NORMAL)
    seq += 1
    can_config(transport, seq, baud_idx, flags=0x03, fd_baud_idx=0)
    seq += 1
    time.sleep(0.2)
    return seq


def mcp_open_fd(transport, seq, baud_idx=0x06, fd_baud=0x02):
    transport.flush_input()
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
    transport.recv_frame(timeout=1.0)
    transport.flush_input(); seq += 1
    can_open(transport, seq, CAN_MODE_NORMAL)
    seq += 1
    can_config(transport, seq, baud_idx, flags=0x07, fd_baud_idx=fd_baud)
    seq += 1
    time.sleep(0.2)
    return seq


# ═══════════════════════════════════════════════════════════════════════════
# Classic CAN 2.0 tests
# ═══════════════════════════════════════════════════════════════════════════

def test_can_send_std(transport, seq, can):
    """SEND standard frame MCP -> canable"""
    print('\n--- SEND standard ---')
    can.recv_all(timeout=0.2)
    f = can_send(transport, seq, 0x123, b'\x01\x02\x03'); seq += 1
    time.sleep(0.3)
    check_canable('standard TX', recv_canable(can, 0x123), 0x123, b'\x01\x02\x03')
    return seq


def test_can_send_ext(transport, seq, can):
    """SEND extended frame MCP -> canable"""
    print('\n--- SEND extended ---')
    can.recv_all(timeout=0.2)
    data = bytes(range(8))
    can_send(transport, seq, 0x567, data, is_ext=True); seq += 1
    time.sleep(0.3)
    check_canable('extended TX', recv_canable(can, 0x567), 0x567, data, extended=True)
    return seq


def test_can_send_rtr(transport, seq, can):
    """SEND RTR frame MCP -> canable"""
    print('\n--- SEND RTR ---')
    can.recv_all(timeout=0.2)
    can_send(transport, seq, 0x100, b'', is_rtr=True); seq += 1
    time.sleep(0.3)
    check_canable('RTR TX', recv_canable(can, 0x100), 0x100, b'', rtr=True)
    return seq


def test_can_recv_std(transport, seq, can):
    """RECV standard frame canable -> MCP"""
    print('\n--- RECV standard ---')
    transport.flush_input()
    can.send(0x456, b'\xAA\xBB\xCC')
    check_event('standard RX', recv_can_event(transport, 0x456), 0x456, b'\xAA\xBB\xCC')
    return seq


def test_can_recv_ext(transport, seq, can):
    """RECV extended frame canable -> MCP"""
    print('\n--- RECV extended ---')
    transport.flush_input()
    can.send(0x1ABCDEF, b'\x01\x02\x03\x04\x05', is_extended=True)
    check_event('extended RX', recv_can_event(transport, 0x1ABCDEF), 0x1ABCDEF,
                b'\x01\x02\x03\x04\x05', extended=True)
    return seq


def test_can_multi_frame(transport, seq, can):
    """Multi-frame send/recv"""
    print('\n--- Multi-frame ---')
    transport.flush_input()
    can.recv_all(timeout=0.2)
    for i in range(20):
        can_send(transport, seq, 0x700 + i, struct.pack('>B', (i * 3) & 0xFF))
        seq += 1
        # Standard identifiers must fit in eleven bits.
        can.send(0x500 + i, struct.pack('>B', (i * 5) & 0xFF))
        time.sleep(0.002)
    time.sleep(0.3)
    expected_rx = set(range(0x500, 0x514))
    expected_tx = set(range(0x700, 0x714))
    deadline = time.monotonic() + 2.0
    while expected_rx and (remaining := deadline - time.monotonic()) > 0:
        frame = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=remaining)
        if frame is None:
            break
        cid = event_id(frame)
        if cid in expected_rx:
            check_event(f'multi RX {cid:#x}', frame, cid, bytes([(cid - 0x500) * 5]))
            expected_rx.remove(cid)
    deadline = time.monotonic() + 2.0
    while expected_tx and (remaining := deadline - time.monotonic()) > 0:
        msg = can.recv(timeout=remaining)
        if msg is None:
            break
        if msg.id in expected_tx:
            check_canable(f'multi TX {msg.id:#x}', msg, msg.id, bytes([(msg.id - 0x700) * 3]))
            expected_tx.remove(msg.id)
    assert_eq('multi missing RX IDs', sorted(expected_rx), [])
    assert_eq('multi missing TX IDs', sorted(expected_tx), [])
    return seq


def test_can_filter(transport, seq, can):
    """FILTER standard blocking/passing"""
    print('\n--- FILTER standard ---')
    can_filter(transport, seq, 0, 0x7F0, 0x120, ftype=FILTER_TYPE_STD)
    seq += 1
    transport.flush_input()
    can.send(0x123, b'\x01')
    time.sleep(0.1)
    f1 = recv_can_event(transport, 0x123, timeout=1.0)
    check_event('ID 0x123 passes filter', f1, 0x123, b'\x01')
    transport.flush_input()
    can.send(0x200, b'\x02')
    time.sleep(0.1)
    f2 = recv_can_event(transport, 0x200, timeout=0.5)
    assert_bool('ID 0x200 blocked', f2 is None)
    can_filter(transport, seq, 0, 0, 0, enable=0)
    seq += 1
    return seq


def test_can_filter_both(transport, seq, can):
    """FILTER FilterType=Both"""
    print('\n--- FILTER Both ---')
    can_filter(transport, seq, 0, 0x1FF, 0x100, ftype=FILTER_TYPE_BOTH)
    seq += 1
    transport.flush_input()
    can.send(0x100, b'\x01')
    time.sleep(0.1)
    f1 = recv_can_event(transport, 0x100, timeout=1.0)
    check_event('Std 0x100 passes Both', f1, 0x100, b'\x01')
    transport.flush_input()
    can.send(0x100, b'\x02', is_extended=True)
    time.sleep(0.1)
    f2 = recv_can_event(transport, 0x100, timeout=1.0)
    check_event('Ext 0x100 passes Both', f2, 0x100, b'\x02', extended=True)
    transport.flush_input()
    can.send(0x200, b'\x03')
    time.sleep(0.1)
    f3 = recv_can_event(transport, 0x200, timeout=0.5)
    assert_bool('Std 0x200 blocked', f3 is None)
    can_filter(transport, seq, 0, 0, 0, enable=0)
    seq += 1
    return seq


def test_can_status(transport, seq):
    """STATUS query"""
    print('\n--- STATUS ---')
    f = can_status(transport, seq)
    seq += 1
    return seq


def test_can_loopback(transport, seq):
    """LOOPBACK self-receive"""
    print('\n--- Loopback self-recv ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_LOOPBACK); seq += 1
    can_config(transport, seq, 0x06, flags=0x03); seq += 1
    time.sleep(0.2)
    transport.flush_input()
    data = b'\x01\x02\x03'
    can_send(transport, seq, 0x100, data); seq += 1
    check_event('Loopback self-recv', recv_can_event(transport, 0x100, timeout=1.0), 0x100, data)
    return seq


def test_can_baud_switch(transport, seq, can, base_baud=500000, base_index=0x06):
    """Switch both peers to 250k and back to the selected baseline."""
    if {250000: 0x05, 500000: 0x06, 1000000: 0x08}.get(base_baud) != base_index:
        raise ValueError('Baseline bitrate/index must match a supported suite rate')
    print('\n--- Baud switch ---')
    def check_transfer(name, ident, data, seq):
        can_send(transport, seq, ident, data)
        if ident != 0x600:
            time.sleep(0.3)
        msg = recv_canable(can, ident)
        check_canable(name, msg, ident, data)
        if ident == 0x601 and msg is None:
            print('  Hint: set all active bus nodes to 250k or isolate the test peers; '
                  'this is a diagnostic suggestion, not a conclusion about the cause.')

    # Discard old host-side observations before the first probe as well.
    # SEND success only acknowledges enqueueing; the exact peer frame is proof
    # of this transfer. A bad matching-ID frame must fail rather than be skipped.
    can.recv_all(timeout=0.2)
    check_transfer('Hello before switch', 0x600, b'Hello', seq); seq += 1
    # Close the adapter before changing either peer's timing.
    can.cmd_close()
    configured = can_config(transport, seq, 0x05, flags=0x03); seq += 1
    if configured is None or configured.payload != bytes([ERR_SUCCESS]):
        fail_('250k CONFIG', 'unconfirmed configuration; skipping World and restoring baseline')
    else:
        can.set_bitrate(250000)
        can.set_data_bitrate(2000000)
        can.cmd_open()
        time.sleep(0.3)
        can.recv_all(timeout=0.2)
        check_transfer('World at 250k', 0x601, b'World', seq); seq += 1
    # back to the selected baseline, while the adapter is closed
    can.cmd_close()
    configured = can_config(transport, seq, base_index, flags=0x03); seq += 1
    if configured is None or configured.payload != bytes([ERR_SUCCESS]):
        # Unknown controller timing is fatal. Leave the adapter closed and let
        # the suite finally block own cleanup rather than issuing commands here.
        raise RuntimeError('Baseline CONFIG failed; bitrate transfer checks cannot run')
    can.set_bitrate(base_baud)
    can.cmd_open()
    time.sleep(0.3)
    can.recv_all(timeout=0.2)
    check_transfer(f'Back at {base_baud}', 0x602, b'Back', seq); seq += 1
    return seq


def test_can_error_paths(transport, seq, can):
    """Protocol error paths"""
    print('\n--- Error paths ---')
    expect_status(transport, seq, CMD_CAN_OPEN, bytes([0x00]), 0xFF,
                  ERR_CHANNEL_INVALID, 'OPEN ch=0xFF')
    seq += 1
    expect_status(transport, seq, CMD_CAN_OPEN, bytes([0x00]), 1,
                  0x16, 'OPEN ch=1(UART)')
    seq += 1
    expect_status(transport, seq, CMD_CAN_RECV, b'', CAN_CHANNEL,
                  ERR_NOT_SUPPORT, 'RECV host cmd')
    seq += 1
    # config not open
    can_close(transport, seq); seq += 1
    can_config(transport, seq, 0x06, expected=ERR_NOT_OPEN); seq += 1
    return seq


# ═══════════════════════════════════════════════════════════════════════════
# CAN FD tests
# ═══════════════════════════════════════════════════════════════════════════

def test_fd_send_64(transport, seq, can):
    """FD 64-byte MCP -> canable"""
    print('\n--- FD SEND 64B ---')
    can.recv_all(timeout=0.2)
    data = bytes(range(64))
    can_send(transport, seq, 0x100, data, is_fd=True); seq += 1
    time.sleep(0.3)
    check_canable('FD TX 64B', recv_canable(can, 0x100), 0x100, data, fd=True)
    return seq


def test_fd_send_brs(transport, seq, can):
    """FD + BRS MCP -> bus. Verify MCP TX is ACKed (frame valid on bus).

    Note: CANable2 slcan firmware does NOT forward received FD+BRS frames
    via slcan (firmware limitation). The MCP's TX is verified by checking
    that the frame is transmitted without ACK errors (TEC stays 0), which
    proves the CANable CAN controller received and ACKed it.
    """
    print('\n--- FD SEND+BRS (bus ACK verification) ---')
    # Clear pending events
    drain_events(transport)
    data = bytes([0xAA] * 16)
    can_send(transport, seq, 0x100, data, is_fd=True, is_brs=True); seq += 1
    time.sleep(0.3)
    # Check MCP error state: if frame was ACKed, TEC=0 and no ack errors
    f = send_cmd(transport, seq, CMD_CAN_STATUS)
    if f and len(f.payload) >= 28 and f.payload[0] == ERR_SUCCESS:
        tec = f.payload[2]
        ack = struct.unpack('>H', f.payload[22:24])[0]
        assert_bool('FD+BRS frame ACKed (TEC=0, AckErr=0)',
                    tec == 0 and ack == 0,
                    f'TEC={tec} AckErr={ack}')
    else:
        fail_('FD+BRS ACK status', 'missing, short, or unsuccessful STATUS response')
    seq += 1
    # Try to read from canable (may fail due to canable2 slcan BRS limitation)
    msg = recv_canable(can, 0x100, timeout=0.5)
    if msg:
        check_canable('BRS forwarded frame', msg, 0x100, data, fd=True, brs=True)
    else:
        skip_('canable BRS RX', 'canable2 slcan does not forward FD+BRS frames')
    return seq


def test_fd_recv_64(transport, seq, can):
    """FD 64-byte canable -> MCP"""
    print('\n--- FD RECV 64B ---')
    transport.flush_input()
    data = bytes(range(64))
    can.send(0x200, data, is_fd=True)
    check_event('FD RX 64B', recv_can_event(transport, 0x200), 0x200, data, fd=True)
    return seq


def test_fd_recv_brs(transport, seq, can):
    """FD BRS canable -> MCP, check RxFlags.FdBRS"""
    print('\n--- FD RECV BRS ---')
    transport.flush_input()
    data = bytes([0x55] * 16)
    can.send(0x301, data, is_fd=True, is_brs=True)
    check_event('FD BRS RX', recv_can_event(transport, 0x301), 0x301, data, fd=True, brs=True)
    return seq


def test_fd_dlc_map(transport, seq, can):
    """FD DLC mapping: 9/11/12/13/14/15"""
    print('\n--- FD DLC mapping ---')
    dlc_map = {9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64}
    for dlc_code, expected_len in dlc_map.items():
        data = bytes([(i * 7) & 0xFF for i in range(expected_len)])
        can.recv_all(timeout=0.2)
        can_send(transport, seq, 0x200, data, is_fd=True); seq += 1
        time.sleep(0.2)
        check_canable(f'FD DLC={dlc_code}', recv_canable(can, 0x200, timeout=0.8),
                      0x200, data, fd=True)
    return seq


def test_fd_loopback(transport, seq):
    """FD loopback self-receive"""
    print('\n--- FD Loopback ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_LOOPBACK); seq += 1
    can_config(transport, seq, 0x06, flags=0x07, fd_baud_idx=0x02); seq += 1
    time.sleep(0.2)
    transport.flush_input()
    data = bytes(range(64))
    can_send(transport, seq, 0x100, data, is_fd=True, is_brs=True); seq += 1
    check_event('FD loopback', recv_can_event(transport, 0x100, timeout=1.0),
                0x100, data, fd=True, brs=True)
    return seq


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global passed, failed, skipped
    import argparse
    ap = argparse.ArgumentParser(description='HEX-Bridge CAN Tests via CANable 2.0')
    ap.add_argument('--mcp', default='COM4', help='MCP COM port')
    ap.add_argument('--mcp-baud', type=int, default=115200, help='MCP baud')
    ap.add_argument('--canable', default='COM6', help='CANable serial port')
    ap.add_argument('--canable-baud', type=int, default=115200,
                    help='CANable serial baud')
    ap.add_argument('--baud', default='500k', choices=('500k', '250k', '1M'), help='CAN nominal baud')
    ap.add_argument('--no-fd', action='store_true', help='Skip FD tests')
    args = ap.parse_args()

    baud_nominal = {'500k': 500000, '250k': 250000, '1M': 1000000}[args.baud]
    baud_index = {'500k': 0x06, '250k': 0x05, '1M': 0x08}[args.baud]

    print('=' * 60)
    print('HEX-Bridge CAN Tests via CANable 2.0')
    print(f'MCP: {args.mcp} @ {args.mcp_baud}')
    print(f'CANable: {args.canable} @ {args.canable_baud}')
    print(f'Baud: {args.baud} ({"FD enabled" if not args.no_fd else "classic only"})')
    print('=' * 60)

    # ── Init CANable ──
    can = CanableChannel(port=args.canable, serial_baud=args.canable_baud)
    try:
        can.open()
        ver = can.get_version()
        print(f'[OK] CANable: {ver}')
    except Exception as e:
        print(f'FATAL: CANable init: {e}')
        return 1

    # ── Init MCP Transport ──
    transport = MCPTransport(port=args.mcp, baudrate=args.mcp_baud)
    try:
        transport.open()
    except Exception as e:
        print(f'FATAL: Cannot open {args.mcp}: {e}')
        can.close()
        return 1

    seq = 10
    try:
        # Pre-clean
        send_cmd(transport, 1, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
        transport.recv_frame(timeout=1.0)
        transport.flush_input()

        # ═══ Classic CAN 2.0 ═══
        print('\n' + '=' * 60)
        print('Classic CAN 2.0 Tests')
        print('=' * 60)

        canable_setup(can, baud=baud_nominal, data_baud=2000000)
        seq = mcp_open_classic(transport, seq, baud_idx=baud_index)

        seq = test_can_send_std(transport, seq, can)
        seq = test_can_send_ext(transport, seq, can)
        seq = test_can_send_rtr(transport, seq, can)
        seq = test_can_recv_std(transport, seq, can)
        seq = test_can_recv_ext(transport, seq, can)
        seq = test_can_multi_frame(transport, seq, can)
        seq = test_can_filter(transport, seq, can)
        seq = test_can_filter_both(transport, seq, can)
        seq = test_can_status(transport, seq)
        seq = test_can_loopback(transport, seq)
        seq = test_can_error_paths(transport, seq, can)

        # restore open state
        seq = mcp_open_classic(transport, seq, baud_idx=baud_index)
        canable_setup(can, baud=baud_nominal, data_baud=2000000)

        seq = test_can_baud_switch(transport, seq, can, baud_nominal, baud_index)

        # ═══ CAN FD ═══
        if not args.no_fd:
            print('\n' + '=' * 60)
            print('CAN FD Tests')
            print('=' * 60)

            seq = mcp_open_fd(transport, seq, baud_idx=baud_index, fd_baud=0x02)
            canable_setup(can, baud=baud_nominal, data_baud=2000000)

            seq = test_fd_send_64(transport, seq, can)
            seq = test_fd_send_brs(transport, seq, can)
            seq = test_fd_recv_64(transport, seq, can)
            seq = test_fd_recv_brs(transport, seq, can)
            seq = test_fd_dlc_map(transport, seq, can)
            seq = test_fd_loopback(transport, seq)

    except KeyboardInterrupt:
        fail_('Suite interrupted', 'remaining tests did not run')
    except Exception as e:
        import traceback
        fail_('Suite exception', str(e))
        traceback.print_exc()
    finally:
        try:
            send_cmd(transport, 9999, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
        except Exception as exc:
            fail_('MCP cleanup', str(exc))
        try:
            can.cmd_close()
        except Exception as exc:
            fail_('CANable cleanup', str(exc))
        transport.close()
        can.close()
        print('[OK] Resources released')

    print(f'\n{"=" * 60}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 60}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
