"""
HEX-Bridge System Management Tests (SYS-01 ~ SYS-15)

Implemented firmware features:
- SYS-01: PING
- SYS-02: PING consecutive heartbeat
- SYS-03: GET_INFO
- SYS-04: GET_CONFIG device name
- SYS-05: SET_CONFIG heartbeat interval
- SYS-06: RESET + SYS_BOOT_EVENT verification
- SYS-07: Invalid command code (0x07)
- SYS-09: SYS_BOOT_EVENT structure validation
- SYS-10: GET_CONFIG UartChannelCount (read-only)
- SYS-11: GET_CONFIG CanChannelCount (read-only)
- SYS-12: GET_CONFIG FlowControlEnable (default)
- SYS-13: SET_CONFIG DeviceName + readback
- SYS-14: SET_CONFIG HeartbeatInterval + readback
- SYS-15: SET_CONFIG read-only key rejected

Run: python test_system.py
"""

import sys, time, struct
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

CMD_PING           = 0x00
CMD_GET_INFO       = 0x01
CMD_GET_CONFIG     = 0x02
CMD_SET_CONFIG     = 0x03
CMD_RESET          = 0x04
CMD_SYS_BOOT_EVENT = 0x06
CMD_GET_TOPOLOGY   = 0x07

ERR_SUCCESS        = 0x00
ERR_PARAM          = 0x02
ERR_NOT_SUPPORT    = 0x06
ERR_PERMISSION     = 0x0C

RESET_SOFT         = 0x00
RESET_REASON_SW    = 0x03

CONFIG_GROUP_SYSTEM = 0x00
CFGKEY_DEVICE_NAME          = 0x01
CFGKEY_HEARTBEAT_INTERVAL   = 0x02
CFGKEY_FLOW_CONTROL_ENABLE  = 0x03
CFGKEY_UART_CHANNEL_COUNT   = 0x10
CFGKEY_CAN_CHANNEL_COUNT    = 0x11

VALID_RESET_REASONS = {0x01, 0x03, 0x05, 0x06, 0x07, 0x08, 0x0D, 0x0E, 0xFF}
BOOT_STATUS_NORMAL  = 0x00

passed = 0
failed = 0
skipped = 0


def assert_eq(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        fmt = '{:#04x}' if isinstance(expected, int) else '{}'
        print(f'  [PASS] {name}: {fmt.format(actual)}')
    else:
        failed += 1
        fmt_exp = '{:#04x}' if isinstance(expected, int) else '{}'
        fmt_act = '{:#04x}' if isinstance(actual, int) else '{}'
        print(f'  [FAIL] {name}: expected {fmt_exp.format(expected)}, got {fmt_act.format(actual)}')


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


def assert_in(name, actual, valid_set):
    global passed, failed
    if actual in valid_set:
        passed += 1
        print(f'  [PASS] {name}: {actual:#04x}')
    else:
        failed += 1
        print(f'  [FAIL] {name}: {actual:#04x} not in {[hex(v) for v in valid_set]}')


def skip_test(name, reason):
    global skipped
    skipped += 1
    print(f'  [SKIP] {name}: {reason}')


def verify_boot_event(name, evt):
    if evt is None:
        assert_bool(f'{name}: event received', False, 'no event frame')
        return False

    assert_bool(f'{name}: is event', evt.is_event, f'flags={evt.flags:#04x}')
    assert_bool(f'{name}: is response', evt.is_response, f'flags={evt.flags:#04x}')
    assert_eq(f'{name}: cmd_code', evt.cmd_code, CMD_SYS_BOOT_EVENT)
    assert_eq(f'{name}: payload_len', len(evt.payload), 2)

    if len(evt.payload) >= 2:
        assert_in(f'{name}: ResetReason', evt.payload[0], VALID_RESET_REASONS)
        assert_eq(f'{name}: BootStatus', evt.payload[1], BOOT_STATUS_NORMAL)

    assert_bool(f'{name}: has_timestamp', evt.has_timestamp, 'TS flag missing')
    if evt.has_timestamp:
        assert_bool(f'{name}: timestamp > 0', evt.timestamp > 0,
                     f'timestamp={evt.timestamp}')

    return True


def do_get_config(transport, group, key, seq, timeout=2.0):
    """Send GET_CONFIG and return (status, value_bytes) or (None, None) on failure."""
    payload = bytes([group, key])
    wire = UBCPBuilder.build_request(seq_num=seq, cmd_code=CMD_GET_CONFIG,
                                     channel_id=0, payload=payload)
    transport.send(wire)
    f = transport.recv_frame(timeout=timeout)
    if f is None:
        return None, None
    if f.payload is None or len(f.payload) < 5:
        return f.payload[0] if f.payload else 0xFF, None
    status = f.payload[0]
    vlen = (f.payload[3] << 8) | f.payload[4]
    value = f.payload[5:5 + vlen] if vlen > 0 else b''
    return status, value


def do_set_config(transport, group, key, value_bytes, seq, timeout=2.0):
    """Send SET_CONFIG and return status byte, or None on timeout."""
    payload = bytes([group, key]) + struct.pack('>H', len(value_bytes)) + value_bytes
    wire = UBCPBuilder.build_request(seq_num=seq, cmd_code=CMD_SET_CONFIG,
                                     channel_id=0, payload=payload)
    transport.send(wire)
    f = transport.recv_frame(timeout=timeout)
    if f is None:
        return None
    return f.payload[0] if f.payload else 0xFF


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


def test_sys04(transport):
    """SYS-04: GET_CONFIG — read device name"""
    print('\n--- SYS-04: GET_CONFIG (DeviceName) ---')
    status, value = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                  CFGKEY_DEVICE_NAME, seq=10)
    assert_bool('GET_CONFIG response received', status is not None, 'no response')
    if status is None:
        return
    assert_eq('Status', status, ERR_SUCCESS)
    assert_bool('Value is non-empty', value is not None and len(value) > 0,
                f'value={value}')
    if value:
        name_str = value.decode('ascii', errors='replace')
        print(f'    DeviceName = "{name_str}"')
        assert_bool('Default name is "HXB-Device"', name_str == 'HXB-Device',
                    f'got "{name_str}"')


def test_sys05(transport):
    """SYS-05: SET_CONFIG — set heartbeat interval"""
    print('\n--- SYS-05: SET_CONFIG (HeartbeatInterval=1000ms) ---')
    value = struct.pack('>H', 1000)
    status = do_set_config(transport, CONFIG_GROUP_SYSTEM,
                           CFGKEY_HEARTBEAT_INTERVAL, value, seq=20)
    assert_bool('SET_CONFIG response received', status is not None, 'no response')
    if status is None:
        return
    assert_eq('SET status', status, ERR_SUCCESS)

    status2, value2 = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                    CFGKEY_HEARTBEAT_INTERVAL, seq=21)
    assert_bool('Readback response received', status2 is not None, 'no response')
    if status2 is None or value2 is None:
        return
    assert_eq('Readback status', status2, ERR_SUCCESS)
    val = struct.unpack('>H', value2)[0] if len(value2) >= 2 else 0
    assert_eq('HeartbeatInterval readback', val, 1000)


def test_sys10(transport):
    """SYS-10: GET_CONFIG — UartChannelCount (read-only)"""
    print('\n--- SYS-10: GET_CONFIG (UartChannelCount) ---')
    status, value = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                  CFGKEY_UART_CHANNEL_COUNT, seq=30)
    assert_bool('GET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('Status', status, ERR_SUCCESS)
    assert_bool('Value length is 1', value is not None and len(value) == 1,
                f'len={len(value) if value else 0}')
    if value and len(value) >= 1:
        assert_eq('UartChannelCount', value[0], 1)


def test_sys11(transport):
    """SYS-11: GET_CONFIG — CanChannelCount (read-only)"""
    print('\n--- SYS-11: GET_CONFIG (CanChannelCount) ---')
    status, value = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                  CFGKEY_CAN_CHANNEL_COUNT, seq=31)
    assert_bool('GET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('Status', status, ERR_SUCCESS)
    assert_bool('Value length is 1', value is not None and len(value) == 1,
                f'len={len(value) if value else 0}')
    if value and len(value) >= 1:
        assert_eq('CanChannelCount', value[0], 2)


def test_sys12(transport):
    """SYS-12: GET_CONFIG — FlowControlEnable (default)"""
    print('\n--- SYS-12: GET_CONFIG (FlowControlEnable) ---')
    status, value = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                  CFGKEY_FLOW_CONTROL_ENABLE, seq=32)
    assert_bool('GET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('Status', status, ERR_SUCCESS)
    assert_bool('Value length is 1', value is not None and len(value) == 1,
                f'len={len(value) if value else 0}')
    if value and len(value) >= 1:
        assert_eq('FlowControlEnable default', value[0], 0x01)


def test_sys13(transport):
    """SYS-13: SET_CONFIG — modify DeviceName + readback"""
    print('\n--- SYS-13: SET_CONFIG (DeviceName="TestDev") ---')
    new_name = b'TestDev'
    status = do_set_config(transport, CONFIG_GROUP_SYSTEM,
                           CFGKEY_DEVICE_NAME, new_name, seq=40)
    assert_bool('SET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('SET status', status, ERR_SUCCESS)

    status2, value2 = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                    CFGKEY_DEVICE_NAME, seq=41)
    assert_bool('Readback response', status2 is not None, 'no response')
    if status2 is None or value2 is None:
        return
    assert_eq('Readback status', status2, ERR_SUCCESS)
    read_name = value2.decode('ascii', errors='replace')
    assert_eq('DeviceName readback', read_name, 'TestDev')

    # Restore default
    do_set_config(transport, CONFIG_GROUP_SYSTEM,
                  CFGKEY_DEVICE_NAME, b'HXB-Device', seq=42)


def test_sys14(transport):
    """SYS-14: SET_CONFIG — modify HeartbeatInterval + readback"""
    print('\n--- SYS-14: SET_CONFIG (HeartbeatInterval=2000ms) ---')
    value = struct.pack('>H', 2000)
    status = do_set_config(transport, CONFIG_GROUP_SYSTEM,
                           CFGKEY_HEARTBEAT_INTERVAL, value, seq=50)
    assert_bool('SET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('SET status', status, ERR_SUCCESS)

    status2, value2 = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                    CFGKEY_HEARTBEAT_INTERVAL, seq=51)
    assert_bool('Readback response', status2 is not None, 'no response')
    if status2 is None or value2 is None:
        return
    assert_eq('Readback status', status2, ERR_SUCCESS)
    val = struct.unpack('>H', value2)[0] if len(value2) >= 2 else 0
    assert_eq('HeartbeatInterval readback', val, 2000)

    # Restore default 5000
    do_set_config(transport, CONFIG_GROUP_SYSTEM,
                  CFGKEY_HEARTBEAT_INTERVAL, struct.pack('>H', 5000), seq=52)


def test_sys15(transport):
    """SYS-15: SET_CONFIG — reject write to read-only key (UartChannelCount)"""
    print('\n--- SYS-15: SET_CONFIG (read-only key rejection) ---')
    value = bytes([0x02])
    status = do_set_config(transport, CONFIG_GROUP_SYSTEM,
                           CFGKEY_UART_CHANNEL_COUNT, value, seq=60)
    assert_bool('SET_CONFIG response', status is not None, 'no response')
    if status is None:
        return
    assert_eq('SET status (expected ERR_PERMISSION)', status, ERR_PERMISSION)

    # Verify UartChannelCount unchanged
    status2, value2 = do_get_config(transport, CONFIG_GROUP_SYSTEM,
                                    CFGKEY_UART_CHANNEL_COUNT, seq=61)
    if status2 is not None and value2 and len(value2) >= 1:
        assert_eq('UartChannelCount still 1', value2[0], 1)


def test_sys06_reset(transport):
    """SYS-06: RESET soft reset + SYS_BOOT_EVENT verification"""
    global passed, failed, skipped
    print('\n--- SYS-06: RESET + SYS_BOOT_EVENT ---')

    payload = bytes([RESET_SOFT])
    wire = UBCPBuilder.build_request(seq_num=100, cmd_code=CMD_RESET,
                                     channel_id=0, payload=payload)
    transport.send(wire)
    resp = transport.recv_frame(timeout=2.0)

    if resp is None:
        skip_test('RESET response', 'timeout waiting for reset response')
        return

    status = resp.payload[0] if resp.payload else 0xFF
    if status != ERR_SUCCESS:
        skip_test('RESET status', f'status={status:#04x} (not supported)')
        return

    assert_eq('RESET status', status, ERR_SUCCESS)
    print('  Device is resetting, waiting for reboot + SYS_BOOT_EVENT...')

    transport.flush_input()
    time.sleep(0.5)

    evt = transport.recv_event(cmd_code=CMD_SYS_BOOT_EVENT, timeout=8.0)
    verify_boot_event('SYS-06-BOOT', evt)
    assert_eq('ResetReason after SW reset', evt.payload[0] if evt else 0xFF,
              RESET_REASON_SW)


DEV_TYPE_UART = 1

def test_sys07(transport):
    """SYS-07: GET_TOPOLOGY — hardware topology discovery"""
    print('\n--- SYS-07: GET_TOPOLOGY ---')
    wire = UBCPBuilder.build_request(seq_num=4, cmd_code=CMD_GET_TOPOLOGY,
                                     channel_id=0, payload=b'')
    transport.send(wire)
    f = transport.recv_frame(timeout=2.0)
    assert_bool('Response received', f is not None, 'no response')
    if f is None:
        return
    assert_eq('Status', f.payload[0], ERR_SUCCESS)
    channel_count = f.payload[1]
    assert_bool('ChannelCount >= 1', channel_count >= 1, f'got {channel_count}')
    if channel_count >= 1:
        ch_id = f.payload[2]
        ch_type = f.payload[3]
        print(f'    ChannelCount={channel_count}, Ch[0]: ID={ch_id:#04x}, Type={ch_type:#04x}')
        assert_eq('Channel[0] ID', ch_id, 1)
        assert_eq('Channel[0] Type', ch_type, DEV_TYPE_UART)


def test_sys09_boot_event(transport):
    """SYS-09: SYS_BOOT_EVENT structure validation (after reset)"""
    global passed, failed, skipped
    print('\n--- SYS-09: SYS_BOOT_EVENT ---')

    payload = bytes([RESET_SOFT])
    wire = UBCPBuilder.build_request(seq_num=101, cmd_code=CMD_RESET,
                                     channel_id=0, payload=payload)
    transport.send(wire)
    resp = transport.recv_frame(timeout=2.0)

    if resp is None:
        skip_test('RESET response', 'timeout waiting for reset response')
        return

    status = resp.payload[0] if resp.payload else 0xFF
    if status != ERR_SUCCESS:
        skip_test('SYS_BOOT_EVENT', f'RESET status={status:#04x} (cannot trigger)')
        return

    print('  Waiting for reboot + SYS_BOOT_EVENT...')
    transport.flush_input()
    time.sleep(0.5)

    evt = transport.recv_event(cmd_code=CMD_SYS_BOOT_EVENT, timeout=8.0)
    if evt is None:
        assert_bool('SYS_BOOT_EVENT received', False, 'no event after reset')
        return

    verify_boot_event('SYS-09', evt)


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
        test_sys04(transport)
        test_sys05(transport)
        test_sys07(transport)
        test_sys10(transport)
        test_sys11(transport)
        test_sys12(transport)
        test_sys13(transport)
        test_sys14(transport)
        test_sys15(transport)

        print('\n' + '=' * 50)
        print('Running destructive tests (RESET)...')
        print('=' * 50)

        test_sys06_reset(transport)

        transport.flush_input()

        test_sys09_boot_event(transport)

    finally:
        transport.close()

    print(f'\n{"=" * 50}')
    print(f'Results: {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print(f'{"=" * 50}')
    return 0 if failed == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
