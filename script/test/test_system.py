"""
HEX-Bridge System Management Tests (SYS-01 ~ SYS-03, SYS-07)

Implemented firmware features:
- SYS-01: PING
- SYS-02: PING consecutive heartbeat
- SYS-03: GET_INFO
- SYS-07: Invalid command code

Run: python test_system.py
"""

import sys, time, struct
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

CMD_PING     = 0x00
CMD_GET_INFO = 0x01
ERR_SUCCESS     = 0x00
ERR_NOT_SUPPORT = 0x06

passed = 0
failed = 0
skipped = 0


def assert_eq(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f'  [PASS] {name}: {actual:#04x}')
    else:
        failed += 1
        print(f'  [FAIL] {name}: expected {expected:#04x}, got {actual:#04x}')


def assert_range(name, actual, lo, hi):
    global passed, failed
    if lo <= actual <= hi:
        passed += 1
        print(f'  [PASS] {name}: {actual} (range [{lo}, {hi}])')
    else:
        failed += 1
        print(f'  [FAIL] {name}: {actual} out of range [{lo}, {hi}]')


def assert_bool(name, cond, msg=''):
    global passed, failed
    if cond:
        passed += 1
        print(f'  [PASS] {name}')
    else:
        failed += 1
        print(f'  [FAIL] {name}: {msg}')


def test_sys01(transport):
    """SYS-01: PING — heartbeat check"""
    print('\n--- SYS-01: PING ---')
    wire = UBCPBuilder.build_request(seq_num=1, cmd_code=CMD_PING,
                                     channel_id=0, payload=b'')
    transport.send(wire)
    f = transport.recv_frame(timeout=2.0)
    assert_bool('Response received', f is not None, 'no response')
    if f is None:
        return
    assert_eq('Status', f.payload[0], ERR_SUCCESS)
    if len(f.payload) >= 7:
        uptime = struct.unpack('>I', f.payload[1:5])[0]
        load = f.payload[5]
        heap = f.payload[6]
        assert_bool('Uptime > 0', uptime > 0, f'uptime={uptime}')
        assert_range('Load', load, 0, 100)
        assert_bool('FreeHeap > 0', heap > 0, f'heap={heap}')


def test_sys02(transport):
    """SYS-02: PING consecutive heartbeat"""
    print('\n--- SYS-02: PING consecutive ---')
    transport.send(UBCPBuilder.build_request(1, CMD_PING, 0, b''))
    f1 = transport.recv_frame(timeout=2.0)
    time.sleep(0.25)
    transport.send(UBCPBuilder.build_request(2, CMD_PING, 0, b''))
    f2 = transport.recv_frame(timeout=2.0)

    if f1 is None or f2 is None:
        assert_bool('Both responses received', f1 is not None and f2 is not None)
        return
    uptime1 = struct.unpack('>I', f1.payload[1:5])[0]
    uptime2 = struct.unpack('>I', f2.payload[1:5])[0]
    assert_bool('Uptime2 > Uptime1', uptime2 > uptime1,
                f'{uptime1} -> {uptime2}')
    assert_eq('Status1', f1.payload[0], ERR_SUCCESS)
    assert_eq('Status2', f2.payload[0], ERR_SUCCESS)


def test_sys03(transport):
    """SYS-03: GET_INFO — device identification"""
    print('\n--- SYS-03: GET_INFO ---')
    transport.send(UBCPBuilder.build_request(3, CMD_GET_INFO, 0, b''))
    f = transport.recv_frame(timeout=2.0)
    assert_bool('Response received', f is not None, 'no response')
    if f is None:
        return

    p = f.payload
    assert_eq('Status', p[0], ERR_SUCCESS)
    if len(p) < 17:
        assert_bool('Payload length >= 17', False, f'got {len(p)}')
        return

    fw = f'{p[1]}.{p[2]}.{p[3]}'
    model = p[8:12].decode('ascii', errors='replace')
    capabilities = struct.unpack('>H', p[12:14])[0]
    max_payload = struct.unpack('>H', p[14:16])[0]
    proto = p[16]

    print(f'    FW={fw} Model={model} Caps=0x{capabilities:04X} '
          f'MaxPL={max_payload} Proto=0x{proto:02X}')

    assert_eq('ModelID', model, 'HXB1')
    assert_eq('ProtoVersion', proto, 0x02)
    assert_eq('MaxPayload', max_payload, 2048)
    assert_bool('Capabilities has UART', capabilities & (1 << 4),
                f'caps=0x{capabilities:04X}')


def test_sys07(transport):
    """SYS-07: Invalid command code"""
    print('\n--- SYS-07: Invalid command ---')
    wire = UBCPBuilder.build_request(4, cmd_code=0x06, channel_id=0, payload=b'')
    transport.send(wire)
    f = transport.recv_frame(timeout=2.0)
    assert_bool('Response received', f is not None, 'no response')
    if f is None:
        return
    assert_eq('Status', f.payload[0], ERR_NOT_SUPPORT)


def main():
    global passed, failed, skipped
    print('=' * 50)
    print('HEX-Bridge System Management Tests')
    print('=' * 50)

    transport = MCPTransport()
    try:
        transport.open()
    except Exception as e:
        print(f'FATAL: Cannot open {transport.port}: {e}')
        return 1

    try:
        transport.flush_input()
        test_sys01(transport)
        test_sys02(transport)
        test_sys03(transport)
        test_sys07(transport)
    finally:
        transport.close()

    print(f'\n{"=" * 50}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 50}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
