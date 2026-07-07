"""
HEX-Bridge Protocol Layer Tests (FRM-01 ~ FRM-08)

Run: python test_protocol.py
"""

import sys, time, struct, random
from ubcp_client import UBCPBuilder, UBCPParser, crc16_calc, VERSION, FLAG_ACK
from mcp_transport import MCPTransport

CMD_PING = 0x00
CMD_UART_SEND = 0xA3
CMD_UART_OPEN = 0xA0
CMD_UART_CLOSE = 0xA1
CMD_UART_CONFIG = 0xA2
ERR_SUCCESS = 0x00

passed = 0
failed = 0
skipped = 0


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
        pass_(f'{name}')
    else:
        fail_(f'{name}: expected {expected!r}, got {actual!r}')


def test_frm01(transport):
    """FRM-01: Valid PING frame round-trip"""
    print('\n--- FRM-01: PING round-trip ---')
    wire = UBCPBuilder.build_request(1, CMD_PING, 0, b'')
    transport.send(wire)
    f = transport.recv_frame(timeout=2.0)
    if f is None:
        fail_('FRM-01', 'no response')
        return
    assert_eq('Version', f.version, VERSION)
    assert_eq('Status', f.payload[0], ERR_SUCCESS)
    pass_('FRM-01 OK')


def test_frm02(transport):
    """FRM-02: Escape sequences in payload"""
    print('\n--- FRM-02: Escape sequences ---')
    # Send data containing 0x7E and 0x7D via UART_SEND
    # The MCP frame builder will escape these bytes in the payload

    # First open UART
    for seq, cmd, pl in [
        (1, 0xA0, bytes([0x00])),  # OPEN
        (2, 0xA2, struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x00, 1, 0)),  # CONFIG
    ]:
        wire = UBCPBuilder.build_request(seq, cmd, 0, pl)
        transport.send(wire)
        f = transport.recv_frame(timeout=2.0)
        if f is None or f.payload[0] != 0:
            fail_(f'FRM-02 setup cmd=0x{cmd:02X}', 'failed')
            return

    # SEND with special bytes in payload
    data = bytes([0x7E, 0x7D, 0x41, 0x42])
    payload = struct.pack('>H', len(data)) + data
    wire = UBCPBuilder.build_request(3, CMD_UART_SEND, 0, payload)
    transport.send(wire)
    f = transport.recv_frame(timeout=2.0)
    if f is None:
        fail_('FRM-02', 'no SEND response')
        return
    assert_eq('SEND Status', f.payload[0], ERR_SUCCESS)

    # Close UART
    wire = UBCPBuilder.build_request(4, CMD_UART_CLOSE, 0, b'')
    transport.send(wire)
    transport.recv_frame(timeout=2.0)

    pass_('FRM-02 OK')


def test_frm03(transport):
    """FRM-03: Large payload frame (1024 bytes)"""
    print('\n--- FRM-03: Large payload ---')
    # Open UART
    ops = [
        (1, 0xA0, bytes([0x00])),
        (2, 0xA2, struct.pack('>IBBBBHB', 115200, 0x08, 0x01, 0x00, 0x00, 1, 0)),
    ]
    for seq, cmd, pl in ops:
        wire = UBCPBuilder.build_request(seq, cmd, 0, pl)
        transport.send(wire)
        f = transport.recv_frame(timeout=2.0)
        if f is None or f.payload[0] != 0:
            fail_(f'FRM-03 setup', 'failed')
            return

    # Send 1024 bytes of data
    data = bytes(range(1024))
    payload = struct.pack('>H', len(data)) + data
    wire = UBCPBuilder.build_request(3, CMD_UART_SEND, 0, payload)
    transport.send(wire)
    f = transport.recv_frame(timeout=3.0)
    if f is None:
        fail_('FRM-03', 'no response')
        return
    assert_eq('SEND Status', f.payload[0], ERR_SUCCESS)
    if len(f.payload) >= 3:
        actual_len = struct.unpack('>H', f.payload[1:3])[0]
        assert_eq('ActualLen', actual_len, 1024)

    # Close
    wire = UBCPBuilder.build_request(4, CMD_UART_CLOSE, 0, b'')
    transport.send(wire)
    transport.recv_frame(timeout=2.0)

    pass_('FRM-03 OK')


def test_frm04(transport):
    """FRM-04: CRC error — corrupted frame discarded"""
    print('\n--- FRM-04: CRC error ---')
    wire = UBCPBuilder.build_corrupted_crc(5, CMD_PING, 0, b'')
    transport.send(wire)
    f = transport.recv_frame(timeout=0.5)
    if f is None:
        pass_('FRM-04: no response to corrupted frame')
    else:
        fail_('FRM-04', 'got response to corrupted frame')


def test_frm05(transport):
    """FRM-05: Illegal escape sequence"""
    print('\n--- FRM-05: Illegal escape ---')
    # Build a frame with illegal escape: SOF + header + 0x7D 0x99 + EOF
    import struct
    header = bytes([VERSION, FLAG_ACK, 0x00, 0x06, CMD_PING, 0x00, 0x00, 0x00])
    raw = header
    crc = crc16_calc(raw)
    crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    wire = bytearray([0xAA, 0x55])
    # write header normally
    for b in raw:
        wire.append(b)
    # inject illegal escape
    wire.append(0x7D)
    wire.append(0x99)
    # write CRC + EOF
    wire.extend(crc_bytes)
    wire.append(0x7E)

    transport.send(bytes(wire))

    # Wait a bit then verify normal frame still works
    time.sleep(0.1)
    transport.flush_input()
    wire_ok = UBCPBuilder.build_request(7, CMD_PING, 0, b'')
    transport.send(wire_ok)
    f = transport.recv_frame(timeout=2.0)
    if f and f.payload[0] == ERR_SUCCESS:
        pass_('FRM-05: recovered after bad escape')
    else:
        fail_('FRM-05', 'failed to recover')


def test_frm06(transport):
    """FRM-06: Buffer overflow — overly long frame"""
    print('\n--- FRM-06: Buffer overflow ---')
    # Build frame with large payload to test parser limits
    # Use valid structure but send a huge declared PayloadLen
    wire = bytearray([0xAA, 0x55])
    wire.extend([VERSION, FLAG_ACK, 0x00, 0x08, CMD_PING, 0x00, 0x08, 0x00])
    # PayloadLen = 2048, but we send garbage bytes then EOF early
    for _ in range(100):
        wire.append(0x00)
    wire.append(0x7E)
    transport.send(bytes(wire))

    time.sleep(0.1)
    transport.flush_input()
    wire_ok = UBCPBuilder.build_request(9, CMD_PING, 0, b'')
    transport.send(wire_ok)
    f = transport.recv_frame(timeout=2.0)
    if f and f.payload[0] == ERR_SUCCESS:
        pass_('FRM-06: recovered after overflow')
    else:
        fail_('FRM-06', 'failed to recover')


def test_frm07(transport):
    """FRM-07: Frame too short (SOF immediately EOF)"""
    print('\n--- FRM-07: Frame too short ---')
    wire = bytes([0xAA, 0x55, 0x7E])
    transport.send(wire)

    time.sleep(0.1)
    transport.flush_input()
    wire_ok = UBCPBuilder.build_request(10, CMD_PING, 0, b'')
    transport.send(wire_ok)
    f = transport.recv_frame(timeout=2.0)
    if f and f.payload[0] == ERR_SUCCESS:
        pass_('FRM-07: recovered after too-short frame')
    else:
        fail_('FRM-07', 'failed to recover')


def test_frm08(transport):
    """FRM-08: Resync after garbage data"""
    print('\n--- FRM-08: Resync after garbage ---')
    garbage1 = bytes([random.randint(0, 0xFF) for _ in range(5)])
    garbage2 = bytes([random.randint(0, 0xFF) for _ in range(3)])
    ping1 = UBCPBuilder.build_request(11, CMD_PING, 0, b'')
    ping2 = UBCPBuilder.build_request(12, CMD_PING, 0, b'')

    seq = garbage1 + ping1 + garbage2 + ping2
    transport.send(seq)

    f1 = transport.recv_frame(timeout=2.0)
    f2 = transport.recv_frame(timeout=2.0)
    assert_eq('Ping1', f1 is not None, True)
    assert_eq('Ping2', f2 is not None, True)
    if f1 and f2:
        assert_eq('Ping1 Status', f1.payload[0], ERR_SUCCESS)
        assert_eq('Ping2 Status', f2.payload[0], ERR_SUCCESS)


def main():
    global passed, failed, skipped
    print('=' * 50)
    print('HEX-Bridge Protocol Layer Tests')
    print('=' * 50)

    transport = MCPTransport()
    try:
        transport.open()
    except Exception as e:
        print(f'FATAL: Cannot open {transport.port}: {e}')
        return 1

    try:
        transport.flush_input()
        test_frm01(transport)
        test_frm02(transport)
        test_frm03(transport)
        test_frm04(transport)
        test_frm05(transport)
        test_frm06(transport)
        test_frm07(transport)
        test_frm08(transport)
    finally:
        transport.close()

    print(f'\n{"=" * 50}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 50}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
