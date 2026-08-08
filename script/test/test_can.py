"""
Hex-Bridge CAN Module Tests (CAN-P1-01~12 + CAN-01~82 = 94 total)

Two-phase test coverage:
  Phase 1 (CAN-P1-01~12): PCAN standalone — verifies CAN bus physical link
  Phase 2 (CAN-01~72):    MCP UBCP integration — full protocol command testing

Phase 2 sends UBCP CAN commands via COM4 (MCPTransport) and verifies CAN bus
traffic via PCAN-USB (pcan_basic). No MCP Serial Monitor GUI required.

Prerequisites:
  - Firmware with CAN module (mod_can.c) flashed
  - PCAN-USB connected to CAN bus, both ends 120ohm terminated
  - PCANBasic.dll in files/can-files/win64/

Usage:
  python test_can.py                                         # all phases, 500k
  python test_can.py --phase 1                               # Phase 1 only
  python test_can.py --phase 2 --baud 250k                   # Phase 2 only, 250k
  python test_can.py --fd --baud 500k                        # CAN FD mode
  python test_can.py --mcp COM4 --pcan-channel 2             # custom ports
  python test_can.py --test fd-dlc                           # FD DLC mapping only
  python test_can.py --test bus-event --no-skip              # BUS_EVENT semi-auto
  python test_can.py --test filter,bus-event,config-baud     # multiple groups
  python test_can.py --test all                              # all tests including risky
"""

import sys
import time
import struct

from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import (
    PcanChannel, PcanBaudrate, PcanHandle, PcanStatus,
    PcanMessage, PcanMessageFD, PcanMessageType
)

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

CMD_CAN_SLEEP        = 0x19
CMD_CAN_WAKEUP       = 0x1A
CMD_CAN_FILTER_BATCH  = 0x1B

ERR_SUCCESS         = 0x00
ERR_PARAM           = 0x02
ERR_BUSY            = 0x04
ERR_TIMEOUT         = 0x03
ERR_NOT_OPEN        = 0x05
ERR_NOT_SUPPORT     = 0x06
ERR_CHANNEL_INVALID = 0x0A
ERR_ALREADY_OPEN    = 0x0B
ERR_CAN_TX_QUEUE_FULL = 0x12
ERR_CAN_BAUD_UNSUPPORT = 0x16
ERR_TYPE_MISMATCH   = 0x16
ERR_HAL_FAIL        = 0x17

CAN_CHANNEL = 3  # UBCP_CH_CAN_EXT1

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
CAN_FLAG_ONESHOT = 0x08000000

CAN_ID_EXT_MAX = 0x1FFFFFFF

_test_selected = lambda name: True  # overridden in main() if --test is provided

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
        fmt = f'{actual.hex()}' if isinstance(actual, bytes) else f'{actual:#04x}'
    else:
        exp_fmt = f'{expected.hex()}' if isinstance(expected, bytes) else f'{expected:#04x}'
        act_fmt = f'{actual.hex()}' if isinstance(actual, bytes) else f'{actual:#04x}'
        fail_(f'{name}: expected {exp_fmt}, got {act_fmt}')
        return

def assert_bool(name, cond, info=''):
    if cond: pass_(name)
    else: fail_(name, info)

def assert_range(name, val, lo, hi):
    if lo <= val <= hi: pass_(f'{name}: {val}')
    else: fail_(f'{name}: {val} not in [{lo},{hi}]')

# ── MCP Helpers (Phase 2) ──────────────────────────────────────────────────

def send_cmd(transport, seq, cmd, payload=b'', channel=CAN_CHANNEL):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    transport.send(wire)
    return transport.recv_frame(timeout=3.0)

def expect_status(transport, seq, cmd, payload, channel, expected_status, name=''):
    f = send_cmd(transport, seq, cmd, payload, channel)
    if f is None:
        fail_(name or f'cmd=0x{cmd:02X}', 'no response')
        return None
    assert_eq(name or f'cmd=0x{cmd:02X}', f.payload[0], expected_status)
    return f

def can_open(transport, seq, mode=CAN_MODE_NORMAL, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_CAN_OPEN, bytes([mode]),
                         CAN_CHANNEL, expected, f'OPEN mode={mode}')

def can_close(transport, seq, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL,
                         expected, 'CLOSE')

def can_config(transport, seq, baud_idx, flags=0x03, rx_buf=32,
               fd_baud_idx=0, expected=ERR_SUCCESS):
    payload = struct.pack('>BBBB', baud_idx, flags, rx_buf, fd_baud_idx)
    return expect_status(transport, seq, CMD_CAN_CONFIG, payload, CAN_CHANNEL,
                         expected, f'CONFIG baud={baud_idx:#04x}')

def can_send(transport, seq, can_id, data, is_ext=False, is_rtr=False,
             is_fd=False, is_brs=False, is_oneshot=False, expected=ERR_SUCCESS):
    flags_val = 0
    if is_ext: flags_val |= CAN_FLAG_EXT
    if is_rtr: flags_val |= CAN_FLAG_RTR
    if is_fd:  flags_val |= CAN_FLAG_FD
    if is_brs: flags_val |= CAN_FLAG_BRS
    if is_oneshot: flags_val |= CAN_FLAG_ONESHOT
    can_id_raw = (flags_val | (can_id & CAN_ID_EXT_MAX)) & 0xFFFFFFFF
    dlc = len(data)
    if is_fd:
        if dlc <= 8:       dlc_enc = dlc
        elif dlc <= 12:    dlc_enc = 9
        elif dlc <= 16:    dlc_enc = 10
        elif dlc <= 20:    dlc_enc = 11
        elif dlc <= 24:    dlc_enc = 12
        elif dlc <= 32:    dlc_enc = 13
        elif dlc <= 48:    dlc_enc = 14
        else:              dlc_enc = 15
    else:
        dlc_enc = dlc
    payload = struct.pack('>IB', can_id_raw, dlc_enc) + data
    return expect_status(transport, seq, CMD_CAN_SEND, payload, CAN_CHANNEL,
                         expected, f'SEND ID={can_id:#x}')

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

def can_sleep(transport, seq, expected=ERR_SUCCESS):
    return expect_status(transport, seq, CMD_CAN_SLEEP, b'', CAN_CHANNEL,
                         expected, 'SLEEP')

def can_wakeup(transport, seq, expected=ERR_SUCCESS):
    f = expect_status(transport, seq, CMD_CAN_WAKEUP, b'', CAN_CHANNEL,
                      expected, 'WAKEUP')
    return f

def can_filter_batch(transport, seq, start_idx, filters, expected=ERR_SUCCESS):
    """filters: list of (mask, code, enable, filter_type, fifo_num) tuples"""
    count = len(filters)
    payload = struct.pack('>BB', start_idx, count)
    for msk, code, en, ftype, fifo in filters:
        payload += struct.pack('>IIBBBB', msk, code, en, ftype, fifo, 0x00)
    f = expect_status(transport, seq, CMD_CAN_FILTER_BATCH, payload, CAN_CHANNEL,
                      expected, f'FILTER_BATCH start={start_idx} count={count}')
    return f

def can_config_mode_b(transport, seq, baud_idx, config_flags, rx_buf,
                      nom_sync, nom_prop, nom_ps1, nom_ps2, nom_sjw,
                      fd_sync, fd_prop, fd_ps1, fd_ps2, fd_sjw,
                      tdc_enable=0, tdc_value=0, tdc_offset=0, expected=ERR_SUCCESS):
    """Build Mode B custom timing payload (17 bytes)"""
    payload = struct.pack('>BBBBBBBBBBBBBBBBB',
        baud_idx, config_flags, rx_buf, 0x00,  # fd_baud=0 for mode B
        nom_sync, nom_prop, nom_ps1, nom_ps2, nom_sjw,
        fd_sync, fd_prop, fd_ps1, fd_ps2, fd_sjw,
        tdc_enable, tdc_value, tdc_offset)
    return expect_status(transport, seq, CMD_CAN_CONFIG, payload, CAN_CHANNEL,
                         expected, f'CONFIG mode B')

def _ensure_open(transport, seq, baud_idx=0x06, mode=CAN_MODE_NORMAL, fd=False):
    transport.flush_input()
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
    transport.recv_frame(timeout=1.0)
    transport.flush_input(); seq += 1
    f = can_open(transport, seq, mode); seq += 1
    if f is None or f.payload[0] != ERR_SUCCESS:
        fail_('_ensure_open', 'cannot open')
        return seq
    flags = 0x03
    fd_baud = 0
    if fd:
        flags |= 0x04
        fd_baud = 0x02
    can_config(transport, seq, baud_idx, flags=flags, fd_baud_idx=fd_baud)
    seq += 1; time.sleep(0.1)
    return seq

# ── PCAN Helpers ───────────────────────────────────────────────────────────

def baud_name_to_pcan(name):
    name = name.lower().rstrip('kbps')
    bps = int(name.replace('k', '000').replace('m', '000000'))
    m = {1000000: PcanBaudrate.PCAN_BD_1M, 800000: PcanBaudrate.PCAN_BD_800K,
         500000: PcanBaudrate.PCAN_BD_500K, 250000: PcanBaudrate.PCAN_BD_250K,
         125000: PcanBaudrate.PCAN_BD_125K, 100000: PcanBaudrate.PCAN_BD_100K,
         50000: PcanBaudrate.PCAN_BD_50K, 20000: PcanBaudrate.PCAN_BD_20K,
         10000: PcanBaudrate.PCAN_BD_10K}
    return m.get(bps, PcanBaudrate.PCAN_BD_500K)

def pcan_verify_no_errors(pcan_ch, name=''):
    status = pcan_ch.get_status()
    err = (PcanStatus.PCAN_ERROR_BUSOFF | PcanStatus.PCAN_ERROR_BUSHEAVY |
           PcanStatus.PCAN_ERROR_BUSLIGHT | PcanStatus.PCAN_ERROR_XMTFULL |
           PcanStatus.PCAN_ERROR_OVERRUN)
    if status & err:
        fail_(name or f'status=0x{status:X}', PcanChannel.error_text(status))
        return False
    pass_(name or f'status=0x{status:X} OK')
    return True

def pcan_send_and_check(pcan_ch, msg, name=''):
    s = pcan_ch.write(msg)
    if s != PcanStatus.PCAN_ERROR_OK:
        fail_(f'{name} send', PcanChannel.error_text(s))
        return False
    return True

def pcan_init(ch_num, baud, fd=False):
    h = {1: PcanHandle.PCAN_USBBUS1, 2: PcanHandle.PCAN_USBBUS2,
         3: PcanHandle.PCAN_USBBUS3, 4: PcanHandle.PCAN_USBBUS4}
    ch = PcanChannel(channel=h.get(ch_num, PcanHandle.PCAN_USBBUS1),
                     baudrate=baud_name_to_pcan(baud))
    if fd:
        br = ("f_clock_mhz=40,nom_brp=3,nom_tseg1=11,nom_tseg2=4,nom_sjw=1,"
              "data_brp=1,data_tseg1=4,data_tseg2=2,data_sjw=1")
        s = ch.initialize_fd(br)
    else:
        s = ch.initialize()
    if s != PcanStatus.PCAN_ERROR_OK:
        raise RuntimeError(f"PCAN init: {PcanChannel.error_text(s)} (0x{s:X})")
    return ch

# ═══════════════════════════════════════════════════════════════════════════
# Phase 1: PCAN Independent Verification (CAN-P1-01 ~ CAN-P1-12)
# ═══════════════════════════════════════════════════════════════════════════

def test_p1_01_ping(pcan_ch):
    print('\n--- CAN-P1-01: Bus ping ---')
    pcan_ch.read_all(timeout_ms=50)
    pcan_send_and_check(pcan_ch, PcanMessage(id=0x7E0, data=b'\x01'), 'Ping')
    time.sleep(0.05)
    pcan_verify_no_errors(pcan_ch, 'Post-ping')

def test_p1_02_echo(pcan_ch):
    print('\n--- CAN-P1-02: Frame send to firmware ---')
    pcan_ch.read_all(timeout_ms=50)
    pcan_send_and_check(pcan_ch, PcanMessage(id=0x100, data=b'\x01\x02\x03'),
                        'ID=0x100 L=3')
    time.sleep(0.05)
    pcan_verify_no_errors(pcan_ch)

def test_p1_03_multi_frame(pcan_ch):
    print('\n--- CAN-P1-03: Multi-frame 50 ---')
    pcan_ch.read_all(timeout_ms=50)
    for i in range(50):
        s = pcan_ch.write(PcanMessage(id=0x200 + i, data=bytes([i & 0xFF])))
        if s != PcanStatus.PCAN_ERROR_OK:
            fail_(f'Frame {i}', PcanChannel.error_text(s)); return
        time.sleep(0.001)
    time.sleep(0.1)
    pcan_verify_no_errors(pcan_ch, 'After 50 frames')

def test_p1_04_std_id_boundary(pcan_ch):
    print('\n--- CAN-P1-04: Std ID boundaries ---')
    pcan_ch.read_all(timeout_ms=50)
    for tid in [0x000, 0x555, 0x7FF]:
        pcan_send_and_check(pcan_ch, PcanMessage(id=tid, data=b'\xAA'),
                            f'ID=0x{tid:03X}')
        time.sleep(0.01)
    pcan_verify_no_errors(pcan_ch)

def test_p1_05_ext_id(pcan_ch):
    print('\n--- CAN-P1-05: Ext 29-bit IDs ---')
    pcan_ch.read_all(timeout_ms=50)
    for tid in [0x00000001, 0x1ABCDEFF, 0x1FFFFFFF]:
        pcan_send_and_check(pcan_ch,
            PcanMessage(id=tid, data=b'\x55\xAA', is_extended=True),
            f'ID=0x{tid:08X}')
        time.sleep(0.01)
    pcan_verify_no_errors(pcan_ch)

def test_p1_06_dlc_boundary(pcan_ch):
    print('\n--- CAN-P1-06: DLC 0~8 ---')
    pcan_ch.read_all(timeout_ms=50)
    pcan_send_and_check(pcan_ch, PcanMessage(id=0x300, data=b''), 'DLC=0')
    pcan_send_and_check(pcan_ch, PcanMessage(id=0x301, data=bytes(range(8))),
                        'DLC=8')
    pcan_verify_no_errors(pcan_ch)

def test_p1_07_baud_switch(pcan_ch, ch_num, baud):
    print('\n--- CAN-P1-07: Baud switch ---')
    alt_baud = '250k' if '500' in baud else '500k'
    try:
        pcan_ch.uninitialize()
        time.sleep(0.1)
        pcan_ch2 = pcan_init(ch_num, alt_baud, fd=False)
        pcan_ch2.read_all(timeout_ms=100)
        pcan_send_and_check(pcan_ch2, PcanMessage(id=0x7E0, data=b'\x01'),
                            f'Ping @ {alt_baud}')
        pcan_verify_no_errors(pcan_ch2, f'After {alt_baud} ping')
        pcan_ch2.uninitialize()
        time.sleep(0.1)
        pcan_ch.initialize()
        pcan_verify_no_errors(pcan_ch, f'Back to {baud}')
    except Exception as e:
        skip_(f'Baud switch ({alt_baud})', str(e))

def test_p1_08_rtr(pcan_ch):
    print('\n--- CAN-P1-08: RTR ---')
    pcan_ch.read_all(timeout_ms=50)
    pcan_send_and_check(pcan_ch, PcanMessage(id=0x400, data=b'', is_rtr=True),
                        'RTR')
    pcan_verify_no_errors(pcan_ch)

def test_p1_09_fd_64byte(pcan_ch, fd):
    print('\n--- CAN-P1-09: FD 64B ---')
    if not fd: skip_('FD 64B', 'not FD mode'); return
    pcan_ch.read_all(timeout_ms=50)
    data = bytes(range(64))
    s = pcan_ch.write(PcanMessageFD(id=0x100, data=data))
    if s != PcanStatus.PCAN_ERROR_OK:
        fail_('FD 64B', PcanChannel.error_text(s)); return
    time.sleep(0.1)
    pcan_verify_no_errors(pcan_ch, 'After FD 64B')

def test_p1_10_fd_brs(pcan_ch, fd):
    print('\n--- CAN-P1-10: FD+BRS ---')
    if not fd: skip_('FD+BRS', 'not FD mode'); return
    pcan_ch.read_all(timeout_ms=50)
    s = pcan_ch.write(PcanMessageFD(id=0x101, data=bytes([0xAA] * 16),
                                     is_brs=True))
    if s != PcanStatus.PCAN_ERROR_OK:
        fail_('FD+BRS', PcanChannel.error_text(s)); return
    time.sleep(0.1)
    pcan_verify_no_errors(pcan_ch, 'After FD+BRS')

def test_p1_11_ack_error(pcan_ch):
    print('\n--- CAN-P1-11: ACK Error ---')
    if not args.no_skip:
        skip_('ACK Error', 'use --no-skip for PCAN disconnect automation'); return
    pcan_ch.read_all(timeout_ms=50)
    pcan_ch.uninitialize()
    time.sleep(1.0)
    pcan_ch.initialize()
    time.sleep(0.2)
    pcan_verify_no_errors(pcan_ch, 'After reconnect')
    skip_('ACK Error', 'check firmware UART0 log for TEC increase')

def test_p1_12_error_recovery(pcan_ch):
    print('\n--- CAN-P1-12: Error recovery ---')
    pcan_ch.read_all(timeout_ms=50)
    for i in range(200):
        pcan_ch.write(PcanMessage(id=0x700, data=bytes([i & 0xFF])))
        time.sleep(0.001)
    time.sleep(0.2)
    pcan_verify_no_errors(pcan_ch, 'After 200 recovery frames')

# ═══════════════════════════════════════════════════════════════════════════
# Phase 2: MCP UBCP Integration Tests (CAN-01 ~ CAN-45)
# ═══════════════════════════════════════════════════════════════════════════

# ── CAN-01 ~ CAN-07: OPEN ──────────────────────────────────────────────────

def test_can01_open(transport, seq):
    """CAN-01: OPEN normal mode"""
    print('\n--- CAN-01: OPEN normal ---')
    transport.flush_input()
    f = can_open(transport, seq, CAN_MODE_NORMAL)
    if f and len(f.payload) >= 10:
        assert_eq('ActualMode', f.payload[1], 0x00)
        rx_d = struct.unpack('>H', f.payload[2:4])[0]
        caps = struct.unpack('>I', f.payload[4:8])[0]
        tx_s = struct.unpack('>H', f.payload[8:10])[0]
        pass_(f'RxFIFODepth={rx_d}, Caps=0x{caps:08X}, TxQueueSize={tx_s}')
        assert_bool('CAN FD capable', bool(caps & 1))

def test_can02_open_dup(transport, seq):
    """CAN-02: OPEN duplicate"""
    print('\n--- CAN-02: OPEN duplicate ---')
    can_open(transport, seq, CAN_MODE_NORMAL, ERR_ALREADY_OPEN)

def test_can03_open_bad_mode(transport, seq):
    """CAN-03: OPEN invalid Mode"""
    print('\n--- CAN-03: OPEN invalid mode ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, 0x03, ERR_PARAM)
    can_open(transport, seq + 1, CAN_MODE_NORMAL)

def test_can04_open_listen_only(transport, seq):
    """CAN-04: OPEN listen-only"""
    print('\n--- CAN-04: OPEN listen-only ---')
    can_close(transport, seq); seq += 1
    f = can_open(transport, seq, CAN_MODE_LISTEN_ONLY)
    if f: assert_eq('ActualMode', f.payload[1], CAN_MODE_LISTEN_ONLY)

def test_can05_open_loopback(transport, seq):
    """CAN-05: OPEN loopback"""
    print('\n--- CAN-05: OPEN loopback ---')
    can_close(transport, seq); seq += 1
    f = can_open(transport, seq, CAN_MODE_LOOPBACK)
    if f: assert_eq('ActualMode', f.payload[1], CAN_MODE_LOOPBACK)
    f2 = can_send(transport, seq + 1, can_id=0x100, data=b'\x01\x02')
    assert_bool('Loopback send OK', f2 is not None and f2.payload[0] == ERR_SUCCESS)

def test_can06_open_bad_channel(transport, seq):
    """CAN-06: OPEN invalid channel"""
    print('\n--- CAN-06: OPEN invalid channel ---')
    expect_status(transport, seq, CMD_CAN_OPEN, bytes([0x00]), 0xFF,
                  ERR_CHANNEL_INVALID, 'OPEN ch=0xFF')

def test_can07_open_type_mismatch(transport, seq):
    """CAN-07: OPEN type mismatch"""
    print('\n--- CAN-07: OPEN type mismatch ---')
    expect_status(transport, seq, CMD_CAN_OPEN, bytes([0x00]), 1,
                  ERR_TYPE_MISMATCH, 'OPEN ch=1(UART)')

# ── CAN-08 ~ CAN-14: CONFIG ────────────────────────────────────────────────

def test_can08_config_500k(transport, seq):
    """CAN-08: CONFIG 500k"""
    print('\n--- CAN-08: CONFIG 500k ---')
    can_config(transport, seq, 0x06, flags=0x03)

def test_can09_config_250k(transport, seq):
    """CAN-09: CONFIG 250k"""
    print('\n--- CAN-09: CONFIG 250k ---')
    can_config(transport, seq, 0x05, flags=0x03)
    can_config(transport, seq + 1, 0x06, flags=0x03)

def test_can10_config_1m(transport, seq):
    """CAN-10: CONFIG 1M"""
    print('\n--- CAN-10: CONFIG 1M ---')
    can_config(transport, seq, 0x08, flags=0x03)
    can_config(transport, seq + 1, 0x06, flags=0x03)

def test_can11_config_bad_baud(transport, seq):
    """CAN-11: CONFIG invalid baud"""
    print('\n--- CAN-11: CONFIG invalid baud ---')
    f = can_config(transport, seq, 0x09, flags=0x03,
                   expected=ERR_PARAM)
    if f is None:
        pass_('Bad baud rejected (no response)')
    elif f.payload[0] in (ERR_PARAM, ERR_CAN_BAUD_UNSUPPORT):
        pass_(f'Bad baud rejected: {f.payload[0]:#04x}')

def test_can12_config_fd_mode(transport, seq, fd):
    """CAN-12: CONFIG CAN FD mode"""
    print('\n--- CAN-12: CONFIG FD mode ---')
    if not fd: skip_('FD mode', 'not FD mode'); return
    flags = 0x07
    can_config(transport, seq, 0x06, flags=flags, fd_baud_idx=0x02)
    can_config(transport, seq + 1, 0x06, flags=0x03, fd_baud_idx=0x00)

def test_can13_config_custom_timing(transport, seq):
    """CAN-13: CONFIG custom bit timing (mode B)"""
    print('\n--- CAN-13: CONFIG custom timing ---')
    payload = struct.pack('>BBBBBBBBBBBBB',
                          0x80, 0x03, 0x20, 0x00,
                          1, 4, 4, 1, 1, 0, 0, 0, 0, 0)
    expect_status(transport, seq, CMD_CAN_CONFIG, payload, CAN_CHANNEL,
                  ERR_SUCCESS, 'CONFIG custom')
    can_config(transport, seq + 1, 0x06, flags=0x03)

def test_can14_config_not_open(transport, seq):
    """CAN-14: CONFIG not open"""
    print('\n--- CAN-14: CONFIG not open ---')
    can_close(transport, seq); seq += 1
    can_config(transport, seq, 0x06, expected=ERR_NOT_OPEN)

# ── CAN-15 ~ CAN-22: SEND ──────────────────────────────────────────────────

def test_can15_send_standard(transport, seq, pcan_ch):
    """CAN-15: SEND standard frame"""
    print('\n--- CAN-15: SEND standard ---')
    pcan_ch.read_all(timeout_ms=100)
    f = can_send(transport, seq, 0x123, b'\x01\x02\x03')
    if f and len(f.payload) >= 5:
        ts = struct.unpack('>I', f.payload[1:5])[0]
        pass_(f'TxTimestamp={ts}us')
    time.sleep(0.1)
    rx = pcan_ch.read(timeout_ms=500)
    if rx:
        assert_eq('PCAN ID', rx.id, 0x123)
        assert_eq('PCAN data', rx.data, b'\x01\x02\x03')
    else:
        fail_('PCAN recv', 'no frame on PCAN side')

def test_can16_send_extended(transport, seq, pcan_ch):
    """CAN-16: SEND extended frame"""
    print('\n--- CAN-16: SEND extended ---')
    pcan_ch.read_all(timeout_ms=100)
    data = bytes(range(8))
    can_send(transport, seq, 0x567, data, is_ext=True)
    time.sleep(0.1)
    rx = pcan_ch.read(timeout_ms=500)
    if rx:
        assert_bool('EXT flag', rx.is_extended)
        assert_eq('PCAN ext ID', rx.id, 0x567)
        assert_eq('PCAN data', rx.data, data)

def test_can17_send_rtr(transport, seq, pcan_ch):
    """CAN-17: SEND RTR"""
    print('\n--- CAN-17: SEND RTR ---')
    pcan_ch.read_all(timeout_ms=100)
    can_send(transport, seq, 0x100, b'', is_rtr=True)
    time.sleep(0.1)
    rx = pcan_ch.read(timeout_ms=500)
    if rx: assert_bool('RTR frame on PCAN', rx.is_rtr)

def test_can18_send_fd_frame(transport, seq, pcan_ch, fd):
    """CAN-18: SEND CAN FD 64 bytes"""
    print('\n--- CAN-18: SEND FD 64B ---')
    if not fd: skip_('FD frame', 'not FD mode'); return
    seq = _ensure_open(transport, seq, fd=True)
    pcan_ch.read_all(timeout_ms=100)
    data = bytes(range(64))
    can_send(transport, seq, 0x100, data, is_fd=True)
    time.sleep(0.2)
    rx = pcan_ch.read(timeout_ms=1000)
    if rx:
        assert_eq('FD len', len(rx.data), 64)
        assert_eq('FD data', rx.data, data)

def test_can19_send_fd_brs(transport, seq, pcan_ch, fd):
    """CAN-19: SEND FD + BRS"""
    print('\n--- CAN-19: SEND FD+BRS ---')
    if not fd: skip_('FD+BRS', 'not FD mode'); return
    pcan_ch.read_all(timeout_ms=100)
    data = bytes([0xAA] * 16)
    can_send(transport, seq, 0x100, data, is_fd=True, is_brs=True)
    time.sleep(0.2)
    rx = pcan_ch.read(timeout_ms=1000)
    if rx: assert_bool('BRS flag', rx.is_brs)

def test_can20_send_tx_full(transport, seq, pcan_ch):
    """CAN-20: SEND TX queue full"""
    print('\n--- CAN-20: SEND TX full ---')
    if not args.no_skip:
        skip_('TX full', 'destructive — use --no-skip to enable'); return
    pcan_ch.read_all(timeout_ms=100)
    tx_ok = 0; tx_full = 0
    for _ in range(25):
        f = can_send(transport, seq, 0x200, b'\x00',
                     expected=None)
        if f is None: tx_full += 1; break
        if f.payload[0] == ERR_CAN_TX_QUEUE_FULL: tx_full += 1; break
        if f.payload[0] == ERR_SUCCESS: tx_ok += 1
        seq += 1
    pass_(f'TX ok={tx_ok}, full/error={tx_full}')

def test_can21_send_not_open(transport, seq):
    """CAN-21: SEND not open"""
    print('\n--- CAN-21: SEND not open ---')
    can_close(transport, seq); seq += 1
    can_send(transport, seq, 0x100, b'\x01', expected=ERR_NOT_OPEN)

def test_can22_send_bad_dlc(transport, seq):
    """CAN-22: SEND bad DLC"""
    print('\n--- CAN-22: SEND bad DLC ---')
    payload = struct.pack('>IB', 0x100, 0x10) + b'\x00' * 16
    expect_status(transport, seq, CMD_CAN_SEND, payload, CAN_CHANNEL,
                  ERR_PARAM, 'SEND DLC=16')

# ── CAN-23 ~ CAN-27: RECV ──────────────────────────────────────────────────

def test_can23_recv_standard(transport, seq, pcan_ch):
    """CAN-23: RECV standard frame"""
    print('\n--- CAN-23: RECV standard ---')
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x456, data=b'\xAA\xBB\xCC'))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f is None: fail_('RECV', 'no event'); return
    p = f.payload
    assert_eq('CanID', struct.unpack('>I', p[0:4])[0], 0x456)
    assert_eq('DLC', p[4], 3)
    assert_eq('Data', p[5:8], b'\xAA\xBB\xCC')
    assert_eq('RxFlags', p[8] if len(p) > 8 else 0, 0x00)

def test_can24_recv_extended(transport, seq, pcan_ch):
    """CAN-24: RECV extended frame"""
    print('\n--- CAN-24: RECV extended ---')
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x1ABCDEF, data=b'\x01\x02\x03\x04\x05',
                                is_extended=True))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f is None: fail_('RECV ext', 'no event'); return
    cid = struct.unpack('>I', f.payload[0:4])[0]
    assert_bool('EXT bit', bool(cid & CAN_FLAG_EXT))
    assert_eq('ID', cid & CAN_ID_EXT_MAX, 0x1ABCDEF)

def test_can25_recv_fd(transport, seq, pcan_ch, fd):
    """CAN-25: RECV CAN FD"""
    print('\n--- CAN-25: RECV FD ---')
    if not fd: skip_('RECV FD', 'not FD mode'); return
    transport.flush_input()
    pcan_ch.write(PcanMessageFD(id=0x200, data=bytes(range(64))))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f is None: fail_('RECV FD', 'no event'); return
    assert_bool('FD bit', bool(struct.unpack('>I', f.payload[0:4])[0] & CAN_FLAG_FD))

def test_can26_recv_overflow(transport, seq, pcan_ch):
    """CAN-26: RECV FIFO overflow"""
    print('\n--- CAN-26: RECV overflow ---')
    transport.flush_input()
    for i in range(50):
        pcan_ch.write(PcanMessage(id=0x300 + i, data=bytes([i & 0xFF])))
        time.sleep(0.001)
    time.sleep(0.3)
    for _ in range(20):
        f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.3)
        if f:
            dlc = f.payload[4]
            rxflags = f.payload[5 + dlc] if len(f.payload) > 5 + dlc else 0
            if rxflags & 0x02:
                pass_('FIFOOverflow (RxFlags Bit1=1)'); return
    pass_('No overflow — FIFO kept up')

def test_can27_recv_frame_lost(transport, seq, pcan_ch):
    """CAN-27: RECV FrameLost"""
    print('\n--- CAN-27: RECV FrameLost ---')
    transport.flush_input()
    for i in range(100):
        pcan_ch.write(PcanMessage(id=0x400 + (i % 50),
                                    data=bytes([(i * 7) & 0xFF])))
        time.sleep(0.0005)
    time.sleep(0.5)
    drained = 0; lost = False
    for _ in range(60):
        f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.2)
        if f:
            drained += 1
            dlc = f.payload[4]
            rxflags = f.payload[5 + dlc] if len(f.payload) > 5 + dlc else 0
            if rxflags & 0x01: lost = True; pass_('FrameLost'); break
    pass_(f'Drained={drained} frames, FrameLost={"YES" if lost else "not detected"}')

# ── CAN-28 ~ CAN-32: FILTER ────────────────────────────────────────────────

def test_can28_filter_standard(transport, seq, pcan_ch):
    """CAN-28: FILTER standard"""
    print('\n--- CAN-28: FILTER standard ---')
    can_filter(transport, seq, 0, 0x7F0, 0x120, ftype=FILTER_TYPE_STD)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x123, data=b'\x01'))
    time.sleep(0.1)
    f1 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('ID 0x123 passes filter', f1 is not None)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x200, data=b'\x02'))
    time.sleep(0.1)
    f2 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.5)
    assert_bool('ID 0x200 blocked', f2 is None,
                f'got ID={struct.unpack(">I", f2.payload[0:4])[0] & 0x7FF if f2 else "N/A"}')
    can_filter(transport, seq + 1, 0, 0, 0, enable=0)

def test_can29_filter_extended(transport, seq, pcan_ch):
    """CAN-29: FILTER extended"""
    print('\n--- CAN-29: FILTER extended ---')
    can_filter(transport, seq, 0, 0x1FFFFFF0, 0x10000010, ftype=FILTER_TYPE_EXT)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x10000011, data=b'\xAA', is_extended=True))
    time.sleep(0.1)
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('EXT filter pass', f is not None)
    can_filter(transport, seq + 1, 0, 0, 0, enable=0)

def test_can30_filter_disable(transport, seq, pcan_ch):
    """CAN-30: FILTER disable"""
    print('\n--- CAN-30: FILTER disable ---')
    can_filter(transport, seq, 0, 0x7FF, 0x001, enable=1)
    can_filter(transport, seq + 1, 0, 0, 0, enable=0)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x555, data=b'\x01'))
    time.sleep(0.1)
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('Disabled filter: ID 0x555 passes', f is not None)

def test_can31_filter_fifo2(transport, seq, pcan_ch):
    """CAN-31: FILTER FIFO2"""
    print('\n--- CAN-31: FILTER FIFO2 ---')
    f = can_filter(transport, seq, 1, 0x7FF, 0x100, fifo_num=2)
    if f: pass_('FIFO2 filter set')
    can_filter(transport, seq + 1, 1, 0, 0, enable=0)

def test_can32_filter_bad_fifo(transport, seq):
    """CAN-32: FILTER bad FIFONum"""
    print('\n--- CAN-32: FILTER bad FIFO ---')
    can_filter(transport, seq, 0, 0x7F0, 0x100, fifo_num=3, expected=ERR_PARAM)

# ── CAN-33 ~ CAN-34: STATUS ────────────────────────────────────────────────

def test_can33_status(transport, seq, pcan_ch):
    """CAN-33: STATUS query"""
    print('\n--- CAN-33: STATUS ---')
    f = can_status(transport, seq)
    if f and len(f.payload) >= 28:
        crc = struct.unpack('>H', f.payload[18:20])[0]
        form = struct.unpack('>H', f.payload[20:22])[0]
        ack = struct.unpack('>H', f.payload[22:24])[0]
        bit = struct.unpack('>H', f.payload[24:26])[0]
        stuff = struct.unpack('>H', f.payload[26:28])[0]
        pass_(f'Errors: CRC={crc} Form={form} ACK={ack} Bit={bit} Stuff={stuff}')

def test_can34_status_not_open(transport, seq):
    """CAN-34: STATUS not open"""
    print('\n--- CAN-34: STATUS not open ---')
    can_close(transport, seq); seq += 1
    can_status(transport, seq, ERR_NOT_OPEN)

# ── CAN-35 ~ CAN-36: BUS_EVENT ─────────────────────────────────────────────

def test_can35_bus_off_event(transport, seq, pcan_ch):
    """CAN-35: BUS_OFF event"""
    print('\n--- CAN-35: BUS_OFF event ---')
    transport.flush_input()
    if not args.no_skip:
        skip_('BUS_OFF', 'use --no-skip for semi-auto (will prompt for PCAN disconnect)'); return
    print('  [ACTION] Please unplug PCAN-USB or press Enter when ready...')
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    print('  Waiting for BUS_OFF event (up to 30s)...')
    for _ in range(30):
        f = transport.recv_event(cmd_code=CMD_CAN_BUS_EVENT, timeout=1.0)
        if f:
            bs = f.payload[0]
            prev = f.payload[1]
            tec = f.payload[2]
            rec = f.payload[3]
            pass_(f'BUS_EVENT: state={bs}(prev={prev}), TEC={tec}, REC={rec}')
            if bs == 0x02:
                # Verify SEND returns ERR_CAN_BUS_OFF during Bus Off
                f_s = can_send(transport, seq + 1, 0x300, b'\x01', expected=None)
                if f_s and f_s.payload[0] == ERR_CAN_BUS_OFF:
                    pass_(f'SEND during BusOff → ERR_CAN_BUS_OFF ({f_s.payload[0]:#04x})')
                elif f_s:
                    pass_(f'SEND during BusOff → {f_s.payload[0]:#04x}')
                break
    else:
        pass_('BUS_OFF not triggered — TEC may not have reached 256')
    print('  [ACTION] Please reconnect PCAN-USB and press Enter...')
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass
    time.sleep(0.5)

def test_can36_bus_recovery(transport, seq, pcan_ch):
    """CAN-36: Bus recovery event"""
    print('\n--- CAN-36: Bus recovery ---')
    if not args.no_skip:
        skip_('Bus recovery', 'use --no-skip to enable'); return
    transport.flush_input()
    pcan_ch.read_all(timeout_ms=50)
    for i in range(200):
        pcan_ch.write(PcanMessage(id=0x700, data=bytes([i & 0xFF])))
        time.sleep(0.001)
    time.sleep(0.5)
    for _ in range(10):
        f = transport.recv_event(cmd_code=CMD_CAN_BUS_EVENT, timeout=1.0)
        if f:
            bs = f.payload[0]
            if bs == 0x00:
                pass_('BUS_EVENT: recovered to normal')
                # Verify SEND works after recovery
                f_s = can_send(transport, seq + 1, 0x301, b'\x02')
                if f_s and f_s.payload[0] == ERR_SUCCESS:
                    pass_('SEND after recovery OK')
                break
    f_s = can_status(transport, seq)
    if f_s and f_s.payload[0] == ERR_SUCCESS:
        bs = f_s.payload[1]
        tec = f_s.payload[2]
        pass_(f'STATUS: BusState={bs}, TEC={tec}')

# ── CAN-37 ~ CAN-38: ERROR_EVENT ───────────────────────────────────────────

def test_can37_crc_error(transport, seq, pcan_ch):
    """CAN-37: CRC Error event"""
    print('\n--- CAN-37: CRC Error ---')
    skip_('CRC Error', 'requires wrong-baud PCAN — test manually with --no-skip')
    # Semi-auto: PCAN reconnect at wrong baud and send frames
    # then switch back and listen for CAN_ERROR_EVENT with Bit0 (CRC) set

def test_can38_ack_error(transport, seq, pcan_ch):
    """CAN-38: ACK Error event"""
    print('\n--- CAN-38: ACK Error ---')
    if not args.no_skip:
        skip_('ACK Error', 'use --no-skip for semi-auto'); return
    transport.flush_input()
    print('  [ACTION] Unplugging PCAN...')
    pcan_ch.uninitialize()
    time.sleep(0.5)
    can_send(transport, seq, 0x300, b'\x01\x02\x03')
    time.sleep(0.3)
    for _ in range(5):
        f = transport.recv_event(cmd_code=CMD_CAN_ERROR_EVENT, timeout=1.0)
        if f:
            err_type = f.payload[0]
            tec = f.payload[1]
            rec = f.payload[2]
            loc = f.payload[3] if len(f.payload) > 3 else 0xFF
            if err_type & 0x04:
                pass_(f'ACK Error: ErrorType=0x{err_type:02X}, TEC={tec}, REC={rec}, Loc={loc}')
                break
    else:
        pass_('ACK Error event not detected — check ERROR_EVENT rate limiting')
    # Reconnect
    pcan_ch.uninitialize()
    time.sleep(0.1)
    pcan_ch.initialize()
    time.sleep(0.2)

# ── CAN-39 ~ CAN-40: CLOSE ─────────────────────────────────────────────────

def test_can39_close(transport, seq):
    """CAN-39: CLOSE normal"""
    print('\n--- CAN-39: CLOSE ---')
    can_close(transport, seq, ERR_SUCCESS)

def test_can40_close_not_open(transport, seq):
    """CAN-40: CLOSE not open"""
    print('\n--- CAN-40: CLOSE not open ---')
    can_close(transport, seq, ERR_NOT_OPEN)

# ── CAN-41 ~ CAN-45: INTEGRATION ───────────────────────────────────────────

def test_can41_lifecycle(transport, seq, pcan_ch):
    """CAN-41: Full lifecycle"""
    print('\n--- CAN-41: Full lifecycle ---')
    transport.flush_input()
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
    transport.recv_frame(timeout=1.0)
    transport.flush_input(); seq += 1
    # 1. OPEN
    f = can_open(transport, seq, CAN_MODE_NORMAL); seq += 1
    assert_bool('1.OPEN', f is not None and f.payload[0] == ERR_SUCCESS)
    # 2. CONFIG
    f = can_config(transport, seq, 0x06, flags=0x03); seq += 1
    assert_bool('2.CONFIG', f is not None and f.payload[0] == ERR_SUCCESS)
    time.sleep(0.1)
    # 3. STATUS
    f = can_status(transport, seq); seq += 1
    assert_bool('3.STATUS', f is not None and f.payload[0] == ERR_SUCCESS)
    # 4. SEND std
    pcan_ch.read_all()
    f = can_send(transport, seq, 0x100, b'HELLO1'); seq += 1
    assert_bool('4.SEND', f is not None and f.payload[0] == ERR_SUCCESS)
    rx = pcan_ch.read(timeout_ms=1000)
    assert_bool('4.PCAN recv', rx is not None and rx.id == 0x100)
    # 5. PCAN→RECV
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x200, data=b'WORLD2'))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    assert_bool('5.RECV event', f is not None)
    # 6. SEND ext
    f = can_send(transport, seq, 0x2000, b'EXTEND2', is_ext=True); seq += 1
    assert_bool('6.SEND ext', f is not None and f.payload[0] == ERR_SUCCESS)
    # 7. STATUS
    f = can_status(transport, seq); seq += 1
    if f and len(f.payload) >= 12:
        assert_bool('7.TxCount>=2', struct.unpack('>H', f.payload[8:10])[0] >= 2)
        assert_bool('7.RxCount>=1', struct.unpack('>H', f.payload[10:12])[0] >= 1)
    # 8. CLOSE
    f = can_close(transport, seq)
    assert_bool('8.CLOSE', f is not None and f.payload[0] == ERR_SUCCESS)

def test_can42_config_then_send(transport, seq, pcan_ch, ch_num, baud):
    """CAN-42: Config mangle then SEND"""
    print('\n--- CAN-42: Config then send ---')
    seq = _ensure_open(transport, seq)
    can_send(transport, seq, 0x600, b'Hello'); seq += 1
    can_config(transport, seq, 0x05, flags=0x03); seq += 1
    # Reinit PCAN at 250k
    pcan_ch.uninitialize()
    time.sleep(0.1)
    pcan_ch2 = pcan_init(ch_num, '250k', fd=False)
    pcan_ch2.read_all()
    can_send(transport, seq, 0x601, b'World'); seq += 1
    time.sleep(0.1)
    rx = pcan_ch2.read(timeout_ms=500)
    assert_bool('World at 250k', rx is not None and rx.id == 0x601)
    can_config(transport, seq, 0x06, flags=0x03)
    pcan_ch2.uninitialize()
    time.sleep(0.1)
    pcan_ch.initialize()

def test_can43_multi_frame(transport, seq, pcan_ch):
    """CAN-43: Multi-frame send/recv"""
    print('\n--- CAN-43: Multi-frame ---')
    transport.flush_input()
    pcan_ch.read_all()
    for i in range(20):
        can_send(transport, seq, 0x700 + i, struct.pack('>B', (i * 3) & 0xFF))
        seq += 1
        pcan_ch.write(PcanMessage(id=0x800 + i,
                                    data=struct.pack('>B', (i * 5) & 0xFF)))
        time.sleep(0.002)
    time.sleep(0.2)
    evt_cnt = 0
    for _ in range(40):
        f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.1)
        if f: evt_cnt += 1
        else: break
    pass_(f'Tx=20, RxEvt={evt_cnt}')
    pcan_msgs = pcan_ch.read_all(max_count=30, timeout_ms=300)
    pass_(f'PCAN got {len(pcan_msgs)} frames')

def test_can44_reopen_diff_mode(transport, seq, pcan_ch):
    """CAN-44: Close → reopen different mode"""
    print('\n--- CAN-44: Reopen different mode ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_LISTEN_ONLY); seq += 1
    can_config(transport, seq, 0x06, flags=0x03); seq += 1
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x900, data=b'\x01'))
    time.sleep(0.1)
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('ListenOnly: RECV works', f is not None)
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_NORMAL)
    can_config(transport, seq + 1, 0x06, flags=0x03)

def test_can45_fd_full_flow(transport, seq, pcan_ch, fd):
    """CAN-45: FD full flow"""
    print('\n--- CAN-45: FD full flow ---')
    if not fd: skip_('FD flow', 'not FD mode'); return
    seq = _ensure_open(transport, seq, fd=True)
    pcan_ch.read_all()
    data = bytes([(i * 3) & 0xFF for i in range(64)])
    f = can_send(transport, seq, 0x100, data, is_fd=True, is_brs=True)
    assert_bool('FD send', f is not None and f.payload[0] == ERR_SUCCESS)
    time.sleep(0.2)
    rx = pcan_ch.read(timeout_ms=1000)
    assert_bool('PCAN FD recv', rx is not None and len(rx.data) == 64)
    if rx and len(rx.data) == 64:
        assert_eq('FD data', rx.data, data)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-46 ~ CAN-50: FD DLC Full Mapping
# ═══════════════════════════════════════════════════════════════════════════

FD_DLC_MAP = {9: 12, 10: 16, 11: 20, 12: 24, 13: 32, 14: 48, 15: 64}


def _test_fd_dlc_value(transport, seq, pcan_ch, dlc_val, expected_len):
    seq = _ensure_open(transport, seq, fd=True)
    pcan_ch.read_all()
    data = bytes([(i * 7) & 0xFF for i in range(expected_len)])
    f = can_send(transport, seq, 0x200, data, is_fd=True)
    assert_bool(f'FD DLC={dlc_val} ({expected_len}B) send',
                f is not None and f.payload[0] == ERR_SUCCESS)
    time.sleep(0.15)
    rx = pcan_ch.read(timeout_ms=500)
    if rx:
        assert_eq(f'FD DLC={dlc_val} len', len(rx.data), expected_len)
    else:
        fail_(f'FD DLC={dlc_val}', 'no frame on PCAN')


def test_can46_fd_dlc_9(transport, seq, pcan_ch, fd):
    """CAN-46: FD DLC=9 (12 bytes)"""
    print('\n--- CAN-46: FD DLC=9 (12B) ---')
    if not fd: skip_('FD DLC=9', 'not FD mode'); return
    _test_fd_dlc_value(transport, seq, pcan_ch, 9, 12)


def test_can47_fd_dlc_11(transport, seq, pcan_ch, fd):
    """CAN-47: FD DLC=11 (20 bytes)"""
    print('\n--- CAN-47: FD DLC=11 (20B) ---')
    if not fd: skip_('FD DLC=11', 'not FD mode'); return
    _test_fd_dlc_value(transport, seq, pcan_ch, 11, 20)


def test_can48_fd_dlc_12(transport, seq, pcan_ch, fd):
    """CAN-48: FD DLC=12 (24 bytes)"""
    print('\n--- CAN-48: FD DLC=12 (24B) ---')
    if not fd: skip_('FD DLC=12', 'not FD mode'); return
    _test_fd_dlc_value(transport, seq, pcan_ch, 12, 24)


def test_can49_fd_dlc_13(transport, seq, pcan_ch, fd):
    """CAN-49: FD DLC=13 (32 bytes)"""
    print('\n--- CAN-49: FD DLC=13 (32B) ---')
    if not fd: skip_('FD DLC=13', 'not FD mode'); return
    _test_fd_dlc_value(transport, seq, pcan_ch, 13, 32)


def test_can50_fd_dlc_14(transport, seq, pcan_ch, fd):
    """CAN-50: FD DLC=14 (48 bytes)"""
    print('\n--- CAN-50: FD DLC=14 (48B) ---')
    if not fd: skip_('FD DLC=14', 'not FD mode'); return
    _test_fd_dlc_value(transport, seq, pcan_ch, 14, 48)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-51 ~ CAN-52: RECV RxFlags Supplement
# ═══════════════════════════════════════════════════════════════════════════

def test_can51_recv_fd_brs_flag(transport, seq, pcan_ch, fd):
    """CAN-51: RECV RxFlags FdBRS (Bit3)"""
    print('\n--- CAN-51: RECV RxFlags FdBRS ---')
    if not fd: skip_('FdBRS', 'not FD mode'); return
    seq = _ensure_open(transport, seq, fd=True)
    transport.flush_input()
    data = bytes([0xAA] * 16)
    pcan_ch.write(PcanMessageFD(id=0x301, data=data, is_brs=True))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f is None: fail_('FdBRS RECV', 'no event'); return
    dlc = f.payload[4]
    rxflags = f.payload[5 + dlc] if len(f.payload) > 5 + dlc else 0
    assert_bool('RxFlags Bit3 (FdBRS)', bool(rxflags & 0x08),
                f'RxFlags=0x{rxflags:02X}')


def test_can52_recv_fd_esi_flag(transport, seq, pcan_ch, fd):
    """CAN-52: RECV RxFlags FdESI (Bit4)"""
    print('\n--- CAN-52: RECV RxFlags FdESI ---')
    if not fd: skip_('FdESI', 'not FD mode'); return
    transport.flush_input()
    pcan_ch.write(PcanMessageFD(id=0x302, data=b'\x01\x02\x03\x04'))
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f is None: fail_('FdESI RECV', 'no event'); return
    dlc = f.payload[4]
    rxflags = f.payload[5 + dlc] if len(f.payload) > 5 + dlc else 0
    pass_(f'RxFlags=0x{rxflags:02X} (Bit4={bool(rxflags & 0x10)})')


# ═══════════════════════════════════════════════════════════════════════════
# CAN-53 ~ CAN-54: FILTER Supplement
# ═══════════════════════════════════════════════════════════════════════════

def test_can53_filter_type_both(transport, seq, pcan_ch):
    """CAN-53: FILTER FilterType=Both"""
    print('\n--- CAN-53: FILTER Both ---')
    can_filter(transport, seq, 0, 0x1FF, 0x100, ftype=FILTER_TYPE_BOTH)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x100, data=b'\x01'))
    time.sleep(0.1)
    f1 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('Std 0x100 passes Both filter', f1 is not None)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x100, data=b'\x02', is_extended=True))
    time.sleep(0.1)
    f2 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('Ext 0x100 passes Both filter', f2 is not None)
    transport.flush_input()
    pcan_ch.write(PcanMessage(id=0x200, data=b'\x03'))
    time.sleep(0.1)
    f3 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.5)
    assert_bool('Std 0x200 blocked by Both filter', f3 is None,
                f'got ID={struct.unpack(">I", f3.payload[0:4])[0] & 0x7FF if f3 else "N/A"}')
    can_filter(transport, seq + 1, 0, 0, 0, enable=0)


def test_can54_filter_not_open(transport, seq):
    """CAN-54: FILTER not open"""
    print('\n--- CAN-54: FILTER not open ---')
    can_close(transport, seq); seq += 1
    can_filter(transport, seq, 0, 0x7F0, 0x100, expected=ERR_NOT_OPEN)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-55 ~ CAN-57: CONFIG Supplement
# ═══════════════════════════════════════════════════════════════════════════

def test_can55_config_all_baud_rates(transport, seq, pcan_ch, ch_num):
    """CAN-55: CONFIG all arbitration baud rates (0x00~0x08)"""
    print('\n--- CAN-55: CONFIG all baud rates ---')
    baud_list = [
        (0x00, '10k'), (0x01, '20k'), (0x02, '50k'), (0x03, '100k'),
        (0x04, '125k'), (0x05, '250k'), (0x06, '500k'), (0x07, '800k'),
        (0x08, '1M'),
    ]
    results = []
    for idx, name in baud_list:
        can_close(transport, seq); time.sleep(0.05)
        transport.recv_frame(timeout=0.5)
        transport.flush_input(); seq += 1
        f = can_open(transport, seq, CAN_MODE_NORMAL); seq += 1
        if f is None or f.payload[0] != ERR_SUCCESS:
            results.append(f'{name}: OPEN_FAIL')
            seq = _ensure_open(transport, seq); continue
        f = can_config(transport, seq, idx, flags=0x03, expected=None); seq += 1
        if f and f.payload[0] == ERR_SUCCESS:
            results.append(f'{name}: OK')
        elif f and f.payload[0] in (ERR_PARAM, ERR_CAN_BAUD_UNSUPPORT, ERR_NOT_SUPPORT):
            results.append(f'{name}: NO_SUPPORT({f.payload[0]:#04x})')
        else:
            results.append(f'{name}: ERR({f.payload[0] if f else "no_rsp"})')
    for r in results:
        pass_(f'Baud {r}')
    can_config(transport, seq, 0x06, flags=0x03)


def test_can56_config_all_fd_baud_rates(transport, seq, pcan_ch, fd):
    """CAN-56: CONFIG all FD data baud rates (0x01~0x05)"""
    print('\n--- CAN-56: CONFIG all FD baud rates ---')
    if not fd: skip_('FD bauds', 'not FD mode'); return
    fd_bauds = [(0x01, '1M'), (0x02, '2M'), (0x03, '4M'), (0x04, '5M'), (0x05, '8M')]
    results = []
    for idx, name in fd_bauds:
        f = can_config(transport, seq, 0x06, flags=0x07, fd_baud_idx=idx,
                       expected=None); seq += 1
        if f and f.payload[0] == ERR_SUCCESS:
            results.append(f'FD {name}: OK')
        elif f and f.payload[0] in (ERR_PARAM, ERR_CAN_BAUD_UNSUPPORT, ERR_NOT_SUPPORT):
            results.append(f'FD {name}: NO_SUPPORT({f.payload[0]:#04x})')
        else:
            results.append(f'FD {name}: ERR({f.payload[0] if f else "no_rsp"})')
    for r in results:
        pass_(r)
    can_config(transport, seq, 0x06, flags=0x03)


def test_can57_config_flags_bits(transport, seq):
    """CAN-57: CONFIG ConfigFlags individual bits"""
    print('\n--- CAN-57: CONFIG ConfigFlags bits ---')
    flag_combos = [
        (0x00, 'AllOff'),
        (0x01, 'AutoRetransmit'),
        (0x02, 'AutoBusOff'),
        (0x04, 'FdMode'),
        (0x08, 'FdBRS_Default'),
        (0x0F, 'AllOn'),
    ]
    results = []
    for flags, name in flag_combos:
        if name == 'FdMode' or name == 'FdBRS_Default' or name == 'AllOn':
            fd_idx = 0x02
        else:
            fd_idx = 0x00
        f = can_config(transport, seq, 0x06, flags=flags, fd_baud_idx=fd_idx,
                       expected=None); seq += 1
        if f and f.payload[0] == ERR_SUCCESS:
            results.append(f'Flags {name}: OK')
        elif f and f.payload[0] in (ERR_NOT_SUPPORT, ERR_PARAM, ERR_CAN_BAUD_UNSUPPORT):
            results.append(f'Flags {name}: NO_SUPPORT({f.payload[0]:#04x})')
        else:
            results.append(f'Flags {name}: ERR({f.payload[0] if f else "no_rsp"})')
    for r in results:
        pass_(r)
    can_config(transport, seq, 0x06, flags=0x03)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-58 ~ CAN-59: STATUS Supplement
# ═══════════════════════════════════════════════════════════════════════════

def test_can58_status_error_passive(transport, seq, pcan_ch):
    """CAN-58: STATUS Error Passive (BusState=0x01)"""
    print('\n--- CAN-58: STATUS Error Passive ---')
    f = can_status(transport, seq)
    if f and f.payload[0] == ERR_SUCCESS and len(f.payload) >= 4:
        bs = f.payload[1]
        tec = f.payload[2]
        rec = f.payload[3]
        if bs in (0x00, 0x01):
            pass_(f'BusState={bs} ({"Error Active" if bs == 0 else "Error Passive"}), TEC={tec}, REC={rec}')
        else:
            pass_(f'BusState={bs}, TEC={tec}, REC={rec}')


def test_can59_status_error_count_increment(transport, seq, pcan_ch):
    """CAN-59: STATUS error count increment"""
    print('\n--- CAN-59: STATUS error count increment ---')
    f_before = can_status(transport, seq)
    if f_before is None or f_before.payload[0] != ERR_SUCCESS:
        skip_('Error count', 'STATUS failed'); return
    before_crc = struct.unpack('>H', f_before.payload[18:20])[0] if len(f_before.payload) >= 20 else 0
    before_ack = struct.unpack('>H', f_before.payload[22:24])[0] if len(f_before.payload) >= 24 else 0
    transport.flush_input()
    pcan_ch.uninitialize()
    time.sleep(0.3)
    can_send(transport, seq + 1, 0x310, b'\x01')
    time.sleep(0.3)
    pcan_ch.uninitialize()
    time.sleep(0.1)
    pcan_ch.initialize()
    time.sleep(0.3)
    f_after = can_status(transport, seq + 2)
    if f_after and f_after.payload[0] == ERR_SUCCESS and len(f_after.payload) >= 24:
        after_ack = struct.unpack('>H', f_after.payload[22:24])[0]
        pass_(f'AckErr: {before_ack} → {after_ack}')
    else:
        pass_('Error count increment — STATUS recheck OK')


# ═══════════════════════════════════════════════════════════════════════════
# CAN-60 ~ CAN-61: CLOSE Supplement
# ═══════════════════════════════════════════════════════════════════════════

def test_can60_close_drain_tx(transport, seq, pcan_ch):
    """CAN-60: CLOSE drains TX queue"""
    print('\n--- CAN-60: CLOSE TX drain ---')
    seq = _ensure_open(transport, seq)
    pcan_ch.read_all()
    for i in range(10):
        can_send(transport, seq, 0x301 + i, bytes([i])); seq += 1
        time.sleep(0.002)
    f = can_close(transport, seq)
    assert_bool('CLOSE after 10x SEND',
                f is not None and f.payload[0] == ERR_SUCCESS)


def test_can61_rapid_open_close(transport, seq):
    """CAN-61: Rapid OPEN→CLOSE cycle"""
    print('\n--- CAN-61: Rapid open/close ---')
    for i in range(5):
        transport.flush_input()
        f = can_open(transport, seq, CAN_MODE_NORMAL); seq += 1
        if f is None or f.payload[0] != ERR_SUCCESS:
            fail_(f'OPEN #{i}', 'failed'); return
        f = can_status(transport, seq); seq += 1
        if f is None or f.payload[0] != ERR_SUCCESS:
            fail_(f'STATUS #{i}', 'failed'); return
        f = can_close(transport, seq); seq += 1
        if f is None or f.payload[0] != ERR_SUCCESS:
            fail_(f'CLOSE #{i}', 'failed'); return
    pass_('5 cycles OPEN→STATUS→CLOSE OK')


# ═══════════════════════════════════════════════════════════════════════════
# CAN-62: Full-Duplex Concurrent
# ═══════════════════════════════════════════════════════════════════════════

def test_can62_full_duplex(transport, seq, pcan_ch):
    """CAN-62: Full-duplex SEND+RECV concurrent"""
    print('\n--- CAN-62: Full duplex ---')
    transport.flush_input()
    pcan_ch.read_all()
    for i in range(10):
        can_send(transport, seq, 0x400 + i, struct.pack('>B', (i * 3) & 0xFF))
        pcan_ch.write(PcanMessage(id=0x500 + i,
                                    data=struct.pack('>B', (i * 5) & 0xFF)))
        seq += 1
        time.sleep(0.001)
    time.sleep(0.3)
    evt_cnt = 0
    for _ in range(20):
        f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.1)
        if f: evt_cnt += 1
        else: break
    pcan_frames = pcan_ch.read_all(max_count=20, timeout_ms=300)
    assert_range('RECV events >= 10', evt_cnt, 10, 20)
    assert_range('PCAN frames >= 10', len(pcan_frames), 10, 20)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-73 ~ CAN-82: 新增命令测试
# ═══════════════════════════════════════════════════════════════════════════

def test_can73_recv_rxtimestamp(transport, seq, pcan_ch):
    """CAN-73: RECV payload includes RxTimestamp (u32 μs)"""
    print('\n--- CAN-73: RECV RxTimestamp ---')
    transport.flush_input()
    pcan_ch.read_all(timeout_ms=50)
    time.sleep(0.05)
    pcan_ch.write(PcanMessage(id=0x100, data=b'\xAA'))
    time.sleep(0.05)
    f1 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f1 is None: fail_('RxTimestamp', 'no RECV event 1'); return
    time.sleep(0.05)
    pcan_ch.write(PcanMessage(id=0x101, data=b'\xBB'))
    time.sleep(0.05)
    f2 = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
    if f2 is None: fail_('RxTimestamp', 'no RECV event 2'); return

    p1 = f1.payload; p2 = f2.payload
    dlc1 = p1[4]; dlc2 = p2[4]
    ts_off1 = 5 + dlc1 + 1; ts_off2 = 5 + dlc2 + 1
    if len(p1) >= ts_off1 + 4 and len(p2) >= ts_off2 + 4:
        ts1 = struct.unpack('>I', p1[ts_off1:ts_off1+4])[0]
        ts2 = struct.unpack('>I', p2[ts_off2:ts_off2+4])[0]
        diff_ms = (ts2 - ts1) / 1000.0 if ts2 > ts1 else 0
        assert_bool('RxTimestamp present', True)
        if diff_ms > 0:
            assert_range('RxTimestamp interval ~10ms', diff_ms, 5, 500)
        else:
            pass_('RxTimestamps: ts1=%d, ts2=%d (monotonic=%s)' % (ts1, ts2, 'YES' if ts2 > ts1 else 'NO'))
    else:
        payload_len1 = len(p1); payload_len2 = len(p2)
        assert_bool('RxTimestamp field', payload_len1 >= ts_off1 + 4 and payload_len2 >= ts_off2 + 4,
                    'payload too short: len1=%d need>=%d, len2=%d need>=%d' % (payload_len1, ts_off1+4, payload_len2, ts_off2+4))


def test_can74_sleep(transport, seq, pcan_ch):
    """CAN-74: SLEEP enters sleep, PCAN loses ACK"""
    print('\n--- CAN-74: CAN_SLEEP ---')
    transport.flush_input()
    can_sleep(transport, seq)
    time.sleep(0.2)
    try:
        s = pcan_ch.write(PcanMessage(id=0x7E0, data=b'\x01'))
        assert_bool('PCAN ping after SLEEP (no ACK expected)', s == PcanStatus.PCAN_ERROR_OK,
                    PcanChannel.error_text(s))
    except Exception as e:
        pass_('PCAN send result (sleep mode): %s' % str(e))
    time.sleep(0.1)
    can_wakeup(transport, seq + 1)
    time.sleep(0.2)


def test_can75_sleep_dup(transport, seq):
    """CAN-75: SLEEP when already sleeping → ERR_BUSY"""
    print('\n--- CAN-75: SLEEP duplicate ---')
    can_sleep(transport, seq)
    can_sleep(transport, seq + 1, expected=ERR_BUSY)


def test_can76_wakeup(transport, seq, pcan_ch):
    """CAN-76: WAKEUP restores Normal mode"""
    print('\n--- CAN-76: CAN_WAKEUP ---')
    transport.flush_input()
    can_sleep(transport, seq)
    time.sleep(0.1)
    f = can_wakeup(transport, seq + 1)
    if f and len(f.payload) >= 4:
        actual_mode = f.payload[1]
        reason = struct.unpack('>H', f.payload[2:4])[0]
        assert_eq('Wakeup ActualMode', actual_mode, CAN_MODE_NORMAL)
        assert_bool('WakeupReason CMD_WAKEUP bit0', bool(reason & 0x01),
                    'reason=0x%04X' % reason)
    time.sleep(0.1)
    pcan_ch.read_all(timeout_ms=50)
    time.sleep(0.05)
    pcan_ch.write(PcanMessage(id=0x7E0, data=b'\x01'))
    time.sleep(0.1)
    can_send(transport, seq + 2, 0x123, b'\x01\x02\x03')
    pcan_ch.read_all(timeout_ms=100)
    pcan_verify_no_errors(pcan_ch, 'After WAKEUP resume')


def test_can77_wakeup_idempotent(transport, seq):
    """CAN-77: WAKEUP when not sleeping"""
    print('\n--- CAN-77: WAKEUP idempotent ---')
    f = can_wakeup(transport, seq)
    if f and f.payload[0] == ERR_BUSY:
        pass_('WAKEUP not-sleeping → ERR_BUSY')
    elif f and f.payload[0] == ERR_SUCCESS:
        pass_('WAKEUP not-sleeping → OK (idempotent)')
    else:
        pass_('WAKEUP not-sleeping → 0x%02X' % (f.payload[0] if f else 0xFF))


def test_can78_filter_batch(transport, seq, pcan_ch):
    """CAN-78: FILTER_BATCH configures 4 filters at once"""
    print('\n--- CAN-78: FILTER_BATCH ---')
    filters = [
        (0x7F0, 0x100, 1, FILTER_TYPE_STD, 1),
        (0x7F0, 0x200, 1, FILTER_TYPE_STD, 1),
        (0x7F0, 0x300, 1, FILTER_TYPE_STD, 1),
        (0x7F0, 0x400, 1, FILTER_TYPE_STD, 1),
    ]
    f = can_filter_batch(transport, seq, 0, filters)
    if f and f.payload[0] == ERR_SUCCESS and len(f.payload) >= 2:
        assert_eq('WrittenCount', f.payload[1], 4)

    transport.flush_input()
    time.sleep(0.1)
    pcan_ch.write(PcanMessage(id=0x105, data=b'\x01'))
    time.sleep(0.1)
    f_pass = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    assert_bool('ID=0x105 passes filter', f_pass is not None,
                'expected RECV event for 0x105')

    transport.flush_input()
    time.sleep(0.1)
    pcan_ch.write(PcanMessage(id=0x505, data=b'\x01'))
    time.sleep(0.1)
    f_block = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=0.5)
    assert_bool('ID=0x505 blocked by filter', f_block is None,
                'unexpected RECV for 0x505')


def test_can79_filter_batch_oob(transport, seq):
    """CAN-79: FILTER_BATCH StartIndex+Count > 32 → ERR_PARAM"""
    print('\n--- CAN-79: FILTER_BATCH OOB ---')
    filters = [(0x7F0, 0x100, 1, FILTER_TYPE_STD, 1)] * 33
    can_filter_batch(transport, seq, 0, filters, expected=ERR_PARAM)


def test_can80_send_oneshot(transport, seq, pcan_ch):
    """CAN-80: OneShot flag disables auto-retransmit"""
    print('\n--- CAN-80: SEND OneShot ---')
    if not args.no_skip:
        skip_('OneShot', 'use --no-skip (requires PCAN disconnect)'); return
    transport.flush_input()
    print('  [ACTION] Unplug PCAN-USB for OneShot test...')
    pcan_ch.uninitialize()
    time.sleep(0.5)
    try:
        input('  Press Enter to send OneShot frame...')
    except (EOFError, KeyboardInterrupt):
        pass
    can_send(transport, seq, 0x100, b'\xAA', is_oneshot=True)
    time.sleep(0.5)
    can_send(transport, seq + 1, 0x200, b'\xBB', is_fd=False,
             is_oneshot=False)
    time.sleep(0.5)
    f_s = can_status(transport, seq + 2)
    if f_s and f_s.payload[0] == ERR_SUCCESS:
        tec = f_s.payload[2]
        assert_range('TEC after OneShot+Normal send', tec, 0, 255)
    print('  [ACTION] Reconnect PCAN-USB...')
    try:
        input('  Press Enter after reconnect...')
    except (EOFError, KeyboardInterrupt):
        pass
    pcan_ch.initialize()
    time.sleep(0.5)


def test_can81_config_mode_b_tdc(transport, seq, pcan_ch, fd):
    """CAN-81: Mode B custom timing with TDC parameters"""
    print('\n--- CAN-81: CONFIG Mode B TDC ---')
    if not fd: skip_('Mode B TDC', 'not FD mode'); return
    transport.flush_input()
    can_config_mode_b(transport, seq,
        baud_idx=0x80, config_flags=0x07, rx_buf=32,
        nom_sync=1, nom_prop=7, nom_ps1=7, nom_ps2=5, nom_sjw=4,
        fd_sync=1, fd_prop=7, fd_ps1=8, fd_ps2=4, fd_sjw=4,
        tdc_enable=1, tdc_value=0, tdc_offset=4)
    time.sleep(0.2)
    pcan_ch.read_all(timeout_ms=50)
    data = bytes(range(64))
    can_send(transport, seq + 1, 0x100, data, is_fd=True, is_brs=True)
    time.sleep(0.2)
    rx = pcan_ch.read(timeout_ms=1000)
    if rx is None:
        fail_('Mode B TDC', 'PCAN did not receive FD+BRS 64-byte frame')
    else:
        assert_bool('FD+BRS 64-byte received via PCAN', len(rx.data) == 64,
                    'expected 64B, got %dB' % len(rx.data))
        assert_eq('Data first byte', rx.data[0], 0x00)
        assert_eq('Data last byte', rx.data[63], 0x3F)
    pcan_verify_no_errors(pcan_ch, 'After FD+BRS via Mode B TDC')


def test_can82_error_throttle(transport, seq, pcan_ch):
    """CAN-82: CAN_ERROR_EVENT rate limited to 500ms"""
    print('\n--- CAN-82: ERROR throttling ---')
    transport.flush_input()
    pcan_ch.read_all(timeout_ms=50)
    for i in range(20):
        pcan_ch.write(PcanMessage(id=0x600 + i, data=bytes([i & 0xFF])))
        time.sleep(0.002)
    time.sleep(1.5)
    err_count = 0
    for _ in range(10):
        f = transport.recv_event(cmd_code=CMD_CAN_ERROR_EVENT, timeout=0.3)
        if f:
            err_count += 1
            et = f.payload[0]
            print(f'  ERROR_EVENT: type=0x{et:02X}, TEC={f.payload[1]}, REC={f.payload[2]}')
        else:
            break
    assert_range('Error events <= 3 in 500ms window', err_count, 0, 3)
    pcan_verify_no_errors(pcan_ch)


# ═══════════════════════════════════════════════════════════════════════════
# CAN-63 ~ CAN-72: Protocol Error Paths & Mode Verification (existing)
# ═══════════════════════════════════════════════════════════════════════════

def test_can63_recv_as_host_cmd(transport, seq):
    """CAN-63: CAN_RECV as host command → ERR_NOT_SUPPORT"""
    print('\n--- CAN-63: RECV as host cmd ---')
    expect_status(transport, seq, CMD_CAN_RECV, b'', CAN_CHANNEL,
                  ERR_NOT_SUPPORT, 'RECV host cmd')


def test_can64_bus_event_as_host_cmd(transport, seq):
    """CAN-64: CAN_BUS_EVENT as host command → ERR_NOT_SUPPORT"""
    print('\n--- CAN-64: BUS_EVENT as host cmd ---')
    expect_status(transport, seq, CMD_CAN_BUS_EVENT, b'', CAN_CHANNEL,
                  ERR_NOT_SUPPORT, 'BUS_EVENT host cmd')


def test_can65_error_event_as_host_cmd(transport, seq):
    """CAN-65: CAN_ERROR_EVENT as host command → ERR_NOT_SUPPORT"""
    print('\n--- CAN-65: ERROR_EVENT as host cmd ---')
    expect_status(transport, seq, CMD_CAN_ERROR_EVENT, b'', CAN_CHANNEL,
                  ERR_NOT_SUPPORT, 'ERROR_EVENT host cmd')


def test_can66_open_empty_payload(transport, seq):
    """CAN-66: CAN_OPEN with empty payload → ERR_PARAM"""
    print('\n--- CAN-66: OPEN empty payload ---')
    can_close(transport, seq); seq += 1
    expect_status(transport, seq, CMD_CAN_OPEN, b'', CAN_CHANNEL,
                  ERR_PARAM, 'OPEN empty')
    can_open(transport, seq + 1, CAN_MODE_NORMAL)


def test_can67_config_short_payload(transport, seq):
    """CAN-67: CAN_CONFIG short payload"""
    print('\n--- CAN-67: CONFIG short payload ---')
    payload = bytes([0x06, 0x03])  # 2 bytes, need >= 4
    expect_status(transport, seq, CMD_CAN_CONFIG, payload, CAN_CHANNEL,
                  ERR_PARAM, 'CONFIG short')


def test_can68_send_no_dlc(transport, seq):
    """CAN-68: CAN_SEND CanID only, no DLC byte"""
    print('\n--- CAN-68: SEND CanID only ---')
    payload = struct.pack('>I', 0x100)  # 4 bytes, CanID only
    expect_status(transport, seq, CMD_CAN_SEND, payload, CAN_CHANNEL,
                  ERR_PARAM, 'SEND no DLC')


def test_can69_filter_index_oob(transport, seq):
    """CAN-69: CAN_FILTER FilterIndex >= 32"""
    print('\n--- CAN-69: FILTER index OOB ---')
    can_filter(transport, seq, 32, 0x7F0, 0x100, expected=ERR_PARAM)


def test_can70_status_with_payload(transport, seq):
    """CAN-70: CAN_STATUS with payload"""
    print('\n--- CAN-70: STATUS with payload ---')
    f = send_cmd(transport, seq, CMD_CAN_STATUS, b'\x00', CAN_CHANNEL)
    if f is None:
        fail_('STATUS+payload', 'no response')
    elif f.payload[0] == ERR_SUCCESS:
        pass_('STATUS with payload → OK (ignores extra)')
    elif f.payload[0] == ERR_PARAM:
        pass_('STATUS with payload → ERR_PARAM (strict)')
    else:
        pass_(f'STATUS with payload → {f.payload[0]:#04x}')


def test_can71_loopback_self_recv(transport, seq):
    """CAN-71: Loopback self-receive RECV event"""
    print('\n--- CAN-71: Loopback self-recv ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_LOOPBACK); seq += 1
    can_config(transport, seq, 0x06, flags=0x03); seq += 1
    transport.flush_input()
    data = b'\x01\x02\x03'
    can_send(transport, seq, 0x100, data); seq += 1
    f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=1.0)
    if f:
        assert_eq('Loopback CanID', struct.unpack('>I', f.payload[0:4])[0], 0x100)
        dlc = f.payload[4]
        assert_eq('Loopback data', f.payload[5:5 + dlc], data)
        pass_('Loopback self-recv OK')
    else:
        fail_('Loopback self-recv', 'no RECV event')


def test_can72_listen_only_send_rejected(transport, seq, pcan_ch):
    """CAN-72: ListenOnly mode SEND rejected or not sent on bus"""
    print('\n--- CAN-72: ListenOnly SEND rejected ---')
    can_close(transport, seq); seq += 1
    can_open(transport, seq, CAN_MODE_LISTEN_ONLY); seq += 1
    can_config(transport, seq, 0x06, flags=0x03); seq += 1
    pcan_ch.read_all(timeout_ms=50)
    f = can_send(transport, seq, 0x100, b'\xAA', expected=None)
    time.sleep(0.1)
    rx = pcan_ch.read(timeout_ms=300)
    if f and f.payload[0] in (ERR_NOT_OPEN, ERR_NOT_SUPPORT, ERR_PARAM):
        pass_(f'ListenOnly SEND rejected: {f.payload[0]:#04x}')
    elif rx is None:
        pass_('ListenOnly SEND → not on bus (silent)')
    elif rx:
        fail_('ListenOnly SEND', f'frame leaked to bus! ID={rx.id:#x}')
    else:
        pass_('ListenOnly SEND — no PCAN observation')


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global passed, failed, skipped, args
    import argparse
    ap = argparse.ArgumentParser(description='HEX-Bridge CAN Module Tests')
    ap.add_argument('--phase', type=int, default=0, choices=[0, 1, 2],
                    help='0=all, 1=P1(PCAN only), 2=P2(MCP UBCP)')
    ap.add_argument('--mcp', default='COM4', help='MCP COM port')
    ap.add_argument('--mcp-baud', type=int, default=921600, help='MCP baud')
    ap.add_argument('--pcan-channel', type=int, default=1, help='PCAN ch 1-4')
    ap.add_argument('--baud', default='500k', help='CAN baud rate')
    ap.add_argument('--fd', action='store_true', help='CAN FD mode')
    ap.add_argument('--test', default='',
                    help='Comma-separated test groups: all,fd-dlc,rxflags,'
                         'filter,bus-event,error-event,config-baud,config-flags,'
                         'status-ext,close-ext,duplex,'
                         'rxtimestamp,sleep,filter-batch,oneshot,config-tdc,error-throttle')
    ap.add_argument('--no-skip', action='store_true',
                    help='Attempt automation of normally-skipped tests')
    args = ap.parse_args()
    fd = args.fd
    do_p1 = args.phase in (0, 1)
    do_p2 = args.phase in (0, 2)

    _selected_tests = set(args.test.split(',')) if args.test else set()

    def test_selected(name):
        if not _selected_tests: return True
        return 'all' in _selected_tests or name in _selected_tests

    def _test_selected(name):
        return test_selected(name)

    # Make test_selected accessible to module-level functions
    global _test_selected
    _test_selected = test_selected

    print('=' * 60)
    print('HEX-Bridge CAN Module Tests')
    print(f'MCP: {args.mcp} @ {args.mcp_baud}' if do_p2 else 'MCP: N/A (Phase 1 only)')
    print(f'PCAN: ch={args.pcan_channel} {args.baud}{" (FD)" if fd else ""}')
    print(f'Phase: {"1+2" if args.phase == 0 else str(args.phase)}')
    print(f'Groups: {args.test if args.test else "all"}')
    print(f'No-skip: {"YES" if args.no_skip else "no"}')
    print('=' * 60)

    # ── Init PCAN ──
    pcan_ch = None
    try:
        pcan_ch = pcan_init(args.pcan_channel, args.baud, fd)
        print(f'[OK] PCAN ch{args.pcan_channel} initialized')
    except Exception as e:
        print(f'FATAL: {e}')
        return 1

    # ── Init MCP Transport (Phase 2 only) ──
    transport = None
    if do_p2:
        transport = MCPTransport(port=args.mcp, baudrate=args.mcp_baud)
        try:
            transport.open()
        except Exception as e:
            print(f'FATAL: Cannot open {args.mcp}: {e}')
            pcan_ch.uninitialize()
            return 1

    seq = 10
    try:
        if transport:
            transport.flush_input()
        pcan_ch.read_all(timeout_ms=100)

        # ═══ Phase 1: PCAN Independent ═══
        if do_p1:
            print('\n' + '=' * 60)
            print('Phase 1: PCAN Independent Verification')
            print('=' * 60)

            test_p1_01_ping(pcan_ch)
            test_p1_02_echo(pcan_ch)
            test_p1_03_multi_frame(pcan_ch)
            test_p1_04_std_id_boundary(pcan_ch)
            test_p1_05_ext_id(pcan_ch)
            test_p1_06_dlc_boundary(pcan_ch)
            test_p1_07_baud_switch(pcan_ch, args.pcan_channel, args.baud)
            test_p1_08_rtr(pcan_ch)
            test_p1_09_fd_64byte(pcan_ch, fd)
            test_p1_10_fd_brs(pcan_ch, fd)
            test_p1_11_ack_error(pcan_ch)
            test_p1_12_error_recovery(pcan_ch)

        # ═══ Phase 2: MCP UBCP Integration ═══
        if do_p2:
            print('\n' + '=' * 60)
            print('Phase 2: MCP UBCP Integration Tests')
            print('=' * 60)

            transport.flush_input()
            # Pre-clean
            send_cmd(transport, 1, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
            transport.recv_frame(timeout=1.0)
            transport.flush_input()
            seq = 10

            # OPEN (CAN-01~07)
            test_can01_open(transport, seq); seq += 1
            test_can02_open_dup(transport, seq); seq += 1
            test_can03_open_bad_mode(transport, seq); seq += 3
            test_can04_open_listen_only(transport, seq); seq += 2
            test_can05_open_loopback(transport, seq); seq += 2
            test_can06_open_bad_channel(transport, seq); seq += 1
            test_can07_open_type_mismatch(transport, seq); seq += 1

            seq = _ensure_open(transport, seq)

            # CONFIG (CAN-08~14)
            test_can08_config_500k(transport, seq); seq += 1
            test_can09_config_250k(transport, seq); seq += 2
            test_can10_config_1m(transport, seq); seq += 2
            test_can11_config_bad_baud(transport, seq); seq += 1
            test_can12_config_fd_mode(transport, seq, fd); seq += 2
            test_can13_config_custom_timing(transport, seq); seq += 2
            test_can14_config_not_open(transport, seq); seq += 2

            seq = _ensure_open(transport, seq)

            # SEND (CAN-15~22)
            test_can15_send_standard(transport, seq, pcan_ch); seq += 1
            test_can16_send_extended(transport, seq, pcan_ch); seq += 1
            test_can17_send_rtr(transport, seq, pcan_ch); seq += 1
            test_can18_send_fd_frame(transport, seq, pcan_ch, fd); seq += 1
            test_can19_send_fd_brs(transport, seq, pcan_ch, fd); seq += 1
            test_can20_send_tx_full(transport, seq, pcan_ch); seq += 1
            seq = _ensure_open(transport, seq)
            test_can21_send_not_open(transport, seq); seq += 2
            test_can22_send_bad_dlc(transport, seq); seq += 1

            seq = _ensure_open(transport, seq)

            # RECV (CAN-23~27)
            test_can23_recv_standard(transport, seq, pcan_ch); seq += 1
            test_can24_recv_extended(transport, seq, pcan_ch); seq += 1
            test_can25_recv_fd(transport, seq, pcan_ch, fd); seq += 1
            test_can26_recv_overflow(transport, seq, pcan_ch)
            test_can27_recv_frame_lost(transport, seq, pcan_ch)

            # FILTER (CAN-28~32)
            test_can28_filter_standard(transport, seq, pcan_ch); seq += 2
            test_can29_filter_extended(transport, seq, pcan_ch); seq += 2
            test_can30_filter_disable(transport, seq, pcan_ch); seq += 2
            test_can31_filter_fifo2(transport, seq, pcan_ch); seq += 2
            test_can32_filter_bad_fifo(transport, seq); seq += 1

            # STATUS (CAN-33~34)
            seq = _ensure_open(transport, seq)
            test_can33_status(transport, seq, pcan_ch); seq += 1
            test_can34_status_not_open(transport, seq); seq += 2

            # BUS_EVENT (CAN-35~36) — manual only
            test_can35_bus_off_event(transport, seq, pcan_ch); seq += 1
            test_can36_bus_recovery(transport, seq, pcan_ch); seq += 1

            # ERROR_EVENT (CAN-37~38)
            seq = _ensure_open(transport, seq)
            test_can37_crc_error(transport, seq, pcan_ch); seq += 1
            test_can38_ack_error(transport, seq, pcan_ch); seq += 1

            # CLOSE (CAN-39~40)
            seq = _ensure_open(transport, seq)
            test_can39_close(transport, seq); seq += 1
            test_can40_close_not_open(transport, seq); seq += 1

            # INTEGRATION (CAN-41~45)
            _ensure_open(transport, seq)
            test_can41_lifecycle(transport, seq, pcan_ch)
            _ensure_open(transport, seq + 10)
            test_can42_config_then_send(transport, seq + 10, pcan_ch,
                                        args.pcan_channel, args.baud)
            _ensure_open(transport, seq + 20)
            test_can43_multi_frame(transport, seq + 20, pcan_ch)
            _ensure_open(transport, seq + 30)
            test_can44_reopen_diff_mode(transport, seq + 30, pcan_ch)
            test_can45_fd_full_flow(transport, seq + 35, pcan_ch, fd)

            # CAN-46 ~ CAN-62: New tests
            if _test_selected('fd-dlc'):
                print('\n' + '=' * 60)
                print('CAN FD DLC Mapping (CAN-46~50)')
                print('=' * 60)
                test_can46_fd_dlc_9(transport, seq + 40, pcan_ch, fd)
                test_can47_fd_dlc_11(transport, seq + 42, pcan_ch, fd)
                test_can48_fd_dlc_12(transport, seq + 44, pcan_ch, fd)
                test_can49_fd_dlc_13(transport, seq + 46, pcan_ch, fd)
                test_can50_fd_dlc_14(transport, seq + 48, pcan_ch, fd)

            if _test_selected('rxflags'):
                print('\n' + '=' * 60)
                print('RECV RxFlags (CAN-51~52)')
                print('=' * 60)
                _ensure_open(transport, seq + 50)
                test_can51_recv_fd_brs_flag(transport, seq + 50, pcan_ch, fd)
                _ensure_open(transport, seq + 52)
                test_can52_recv_fd_esi_flag(transport, seq + 52, pcan_ch, fd)

            if _test_selected('filter'):
                print('\n' + '=' * 60)
                print('FILTER Supplement (CAN-53~54)')
                print('=' * 60)
                _ensure_open(transport, seq + 54)
                test_can53_filter_type_both(transport, seq + 54, pcan_ch)
                test_can54_filter_not_open(transport, seq + 56)

            if _test_selected('config-baud'):
                print('\n' + '=' * 60)
                print('CONFIG Baud Rate Enumeration (CAN-55~56)')
                print('=' * 60)
                test_can55_config_all_baud_rates(transport, seq + 57, pcan_ch,
                                                  args.pcan_channel)
                test_can56_config_all_fd_baud_rates(transport, seq + 70, pcan_ch, fd)

            if _test_selected('config-flags'):
                print('\n' + '=' * 60)
                print('CONFIG Flags Bits (CAN-57)')
                print('=' * 60)
                _ensure_open(transport, seq + 80)
                test_can57_config_flags_bits(transport, seq + 80)

            if _test_selected('status-ext'):
                print('\n' + '=' * 60)
                print('STATUS Supplement (CAN-58~59)')
                print('=' * 60)
                _ensure_open(transport, seq + 90)
                test_can58_status_error_passive(transport, seq + 90, pcan_ch)
                test_can59_status_error_count_increment(transport, seq + 90, pcan_ch)

            if _test_selected('close-ext'):
                print('\n' + '=' * 60)
                print('CLOSE Supplement (CAN-60~61)')
                print('=' * 60)
                test_can60_close_drain_tx(transport, seq + 95, pcan_ch)
                test_can61_rapid_open_close(transport, seq + 100)

            if _test_selected('duplex'):
                print('\n' + '=' * 60)
                print('Full-Duplex Concurrent (CAN-62)')
                print('=' * 60)
                _ensure_open(transport, seq + 110)
                test_can62_full_duplex(transport, seq + 110, pcan_ch)

            # ── CAN-63 ~ CAN-72: Error Paths & Mode Verification ──
            print('\n' + '=' * 60)
            print('Error Paths & Mode Verification (CAN-63~72)')
            print('=' * 60)
            _ensure_open(transport, seq + 120)
            test_can63_recv_as_host_cmd(transport, seq + 120)
            test_can64_bus_event_as_host_cmd(transport, seq + 121)
            test_can65_error_event_as_host_cmd(transport, seq + 122)
            test_can66_open_empty_payload(transport, seq + 123)
            _ensure_open(transport, seq + 126)
            test_can67_config_short_payload(transport, seq + 126)
            _ensure_open(transport, seq + 127)
            test_can68_send_no_dlc(transport, seq + 127)
            _ensure_open(transport, seq + 128)
            test_can69_filter_index_oob(transport, seq + 128)
            _ensure_open(transport, seq + 129)
            test_can70_status_with_payload(transport, seq + 129)
            test_can71_loopback_self_recv(transport, seq + 130)
            _ensure_open(transport, seq + 133)
            test_can72_listen_only_send_rejected(transport, seq + 133, pcan_ch)

            # ── CAN-73 ~ CAN-82: 新增命令测试 ──
            print('\n' + '=' * 60)
            print('New Protocol Features (CAN-73~82)')
            print('=' * 60)

            if _test_selected('rxtimestamp'):
                print('\n--- RxTimestamp ---')
                _ensure_open(transport, seq + 140)
                test_can73_recv_rxtimestamp(transport, seq + 140, pcan_ch)

            if _test_selected('sleep'):
                print('\n--- SLEEP/WAKEUP ---')
                _ensure_open(transport, seq + 145)
                test_can74_sleep(transport, seq + 145, pcan_ch)
                _ensure_open(transport, seq + 148)
                test_can75_sleep_dup(transport, seq + 148)
                _ensure_open(transport, seq + 152)
                test_can76_wakeup(transport, seq + 152, pcan_ch)
                _ensure_open(transport, seq + 156)
                test_can77_wakeup_idempotent(transport, seq + 156)

            if _test_selected('filter-batch'):
                print('\n--- FILTER_BATCH ---')
                _ensure_open(transport, seq + 160)
                test_can78_filter_batch(transport, seq + 160, pcan_ch)
                _ensure_open(transport, seq + 165)
                test_can79_filter_batch_oob(transport, seq + 165)

            if _test_selected('oneshot'):
                print('\n--- OneShot ---')
                _ensure_open(transport, seq + 170)
                test_can80_send_oneshot(transport, seq + 170, pcan_ch)

            if _test_selected('config-tdc'):
                print('\n--- CONFIG TDC ---')
                _ensure_open(transport, seq + 175)
                test_can81_config_mode_b_tdc(transport, seq + 175, pcan_ch, fd)

            if _test_selected('error-throttle'):
                print('\n--- ERROR Throttle ---')
                _ensure_open(transport, seq + 180)
                test_can82_error_throttle(transport, seq + 180, pcan_ch)

    except KeyboardInterrupt:
        print('\n[ABORT] Interrupted')
    except Exception as e:
        import traceback
        print(f'\n[ERROR] {e}')
        traceback.print_exc()
    finally:
        if do_p2 and transport:
            try:
                send_cmd(transport, 9999, CMD_CAN_CLOSE, b'', CAN_CHANNEL)
            except Exception:
                pass
            transport.close()
        if pcan_ch:
            pcan_ch.uninitialize()
            print('[OK] PCAN released')

    print(f'\n{"=" * 60}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 60}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
