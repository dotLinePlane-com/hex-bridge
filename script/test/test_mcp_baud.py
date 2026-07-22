"""
HEX-Bridge MCP Baud Rate Tests (SYS-16 ~ SYS-20)

Run: python test_mcp_baud.py [--port COM35] [--baud 115200]
"""

import sys, time, struct
from ubcp_client import UBCPBuilder, Frame
from mcp_transport import MCPTransport

CMD_PING       = 0x00
CMD_GET_INFO   = 0x01
CMD_GET_CONFIG = 0x02
CMD_SET_CONFIG = 0x03
CMD_RESET      = 0x04

ERR_SUCCESS     = 0x00
ERR_PARAM       = 0x02
ERR_PERMISSION  = 0x0C

CONFIG_GROUP_SYSTEM = 0x00
CFGKEY_MCP_BAUD     = 0x12

SEQ = 0x1000

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
        if isinstance(actual, bytes):
            pass_(f'{name}: {actual.hex()}')
        else:
            pass_(f'{name}: {actual:#04x}')
    else:
        if isinstance(actual, bytes):
            fail_(f'{name}: expected {expected.hex()}, got {actual.hex()}')
        else:
            fail_(f'{name}: expected {expected:#04x}, got {actual:#04x}')


def send_cmd(transport, seq, cmd, payload=b'', channel=0):
    global SEQ
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    transport.send(wire)
    return transport.recv_frame(timeout=2.0)


def get_config(transport, group, key):
    global SEQ
    payload = bytes([group, key])
    resp = send_cmd(transport, SEQ, CMD_GET_CONFIG, payload)
    SEQ += 1
    return resp


def set_config(transport, group, key, value):
    global SEQ
    payload = bytes([group, key,
                     (len(value) >> 8) & 0xFF, len(value) & 0xFF]) + value
    resp = send_cmd(transport, SEQ, CMD_SET_CONFIG, payload)
    SEQ += 1
    return resp


def test_sys16_get_default_baud(transport):
    """SYS-16: GET_CONFIG — 读取 McpBaudRate 默认值"""
    print('\n--- SYS-16: GET_CONFIG McpBaudRate (默认值) ---')
    resp = get_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD)
    if resp is None:
        fail_('SYS-16', '超时无响应')
        return None

    assert_eq('SYS-16 Status', resp.payload[0], ERR_SUCCESS)
    group = resp.payload[1]
    key   = resp.payload[2]
    vallen = (resp.payload[3] << 8) | resp.payload[4]
    assert_eq('SYS-16 ValueLen', vallen, 4)

    baud = (resp.payload[5] << 24) | (resp.payload[6] << 16) | \
           (resp.payload[7] << 8)  | resp.payload[8]
    print(f'  [INFO] 当前 MCP 波特率: {baud} bps')
    pass_(f'SYS-16 McpBaudRate = {baud}')
    return baud


def test_sys17_set_and_readback(transport):
    """SYS-17: SET_CONFIG — 修改 McpBaudRate 并回读验证"""
    print('\n--- SYS-17: SET_CONFIG + GET_CONFIG 回读 McpBaudRate ---')

    # 先读取当前值
    resp = get_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD)
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        fail_('SYS-17', '读取当前值失败')
        return
    original = (resp.payload[5] << 24) | (resp.payload[6] << 16) | \
               (resp.payload[7] << 8)  | resp.payload[8]

    # 使用 115200 作为测试值（如果不等于当前值）
    test_baud = 115200 if original != 115200 else 230400

    value = bytes([
        (test_baud >> 24) & 0xFF,
        (test_baud >> 16) & 0xFF,
        (test_baud >> 8) & 0xFF,
        test_baud & 0xFF,
    ])
    resp = set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, value)
    if resp is None:
        fail_('SYS-17', 'SET_CONFIG 超时')
        return
    assert_eq('SYS-17 SET Status', resp.payload[0], ERR_SUCCESS)

    # 回读验证
    resp = get_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD)
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        fail_('SYS-17', '回读失败')
        return
    actual = (resp.payload[5] << 24) | (resp.payload[6] << 16) | \
             (resp.payload[7] << 8)  | resp.payload[8]
    assert_eq(f'SYS-17 BaudRate', actual, test_baud)

    # 恢复原值
    orig_value = bytes([
        (original >> 24) & 0xFF,
        (original >> 16) & 0xFF,
        (original >> 8) & 0xFF,
        original & 0xFF,
    ])
    resp = set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, orig_value)
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        print(f'  [WARN] 恢复原始波特率 {original} 失败')


def test_sys18_reject_too_low(transport):
    """SYS-18: SET_CONFIG — 拒绝无效 McpBaudRate (200 < 9600)"""
    print('\n--- SYS-18: SET_CONFIG 拒绝过低波特率 (200 bps) ---')
    value = bytes([0x00, 0x00, 0x00, 0xC8])  # 200
    resp = set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, value)
    if resp is None:
        fail_('SYS-18', '超时')
        return
    assert_eq('SYS-18 Status (expect ERR_PARAM)', resp.payload[0], ERR_PARAM)


def test_sys19_reject_too_high(transport):
    """SYS-19: SET_CONFIG — 拒绝过高 McpBaudRate (100M > 5M)"""
    print('\n--- SYS-19: SET_CONFIG 拒绝过高波特率 (100,000,000) ---')
    value = bytes([0x05, 0xF5, 0xE1, 0x00])  # 100,000,000
    resp = set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, value)
    if resp is None:
        fail_('SYS-19', '超时')
        return
    assert_eq('SYS-19 Status (expect ERR_PARAM)', resp.payload[0], ERR_PARAM)


def test_sys20_e2e_baud_switch(transport, original_baud, port):
    """SYS-20: SET_CONFIG → 软复位 → 新波特率验证 (端到端)"""
    global SEQ
    print('\n--- SYS-20: SET_CONFIG → 软复位 → 新波特率重连 ---')

    target_baud = 115200 if original_baud != 115200 else 230400
    print(f'  [INFO] 原始波特率: {original_baud}, 目标波特率: {target_baud}')

    # Step 1: 写入目标波特率
    value = bytes([
        (target_baud >> 24) & 0xFF,
        (target_baud >> 16) & 0xFF,
        (target_baud >> 8) & 0xFF,
        target_baud & 0xFF,
    ])
    resp = set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, value)
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        status_str = f'{resp.payload[0]:#04x}' if resp else 'timeout'
        fail_('SYS-20', f'SET_CONFIG 失败: {status_str}')
        return

    pass_('SYS-20 SET_CONFIG OK')

    # Step 2: 发送软复位
    print('  [INFO] 发送软复位 RESET(0x00)...')
    resp = send_cmd(transport, SEQ, CMD_RESET, bytes([0x00]))
    SEQ += 1
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        print(f'  [WARN] RESET 响应异常 (正常行为): {resp}')
    transport.close()
    pass_('SYS-20 RESET sent')

    # Step 3: 等待设备重启
    print('  [INFO] 等待设备重启 (2s)...')
    time.sleep(2.0)

    # Step 4: 以新波特率重连
    print(f'  [INFO] 以 {target_baud} bps 重新连接 {port}...')
    transport2 = MCPTransport(port=port, baudrate=target_baud)
    transport2.open()
    transport2.flush_input()

    # Step 5: 接收 SYS_BOOT_EVENT
    evt = transport2.recv_event(cmd_code=0x06, timeout=5.0)
    if evt is None:
        print('  [WARN] 未收到 SYS_BOOT_EVENT (可能已被消费)')

    # Step 6: PING 验证链路
    resp = send_cmd(transport2, SEQ, CMD_PING, b'', 0)
    SEQ += 1
    if resp is None or resp.payload[0] != ERR_SUCCESS:
        fail_('SYS-20', f'新波特率 PING 失败: {resp.payload[0] if resp else "timeout":#04x}')
        transport2.close()

        # 尝试以原始波特率恢复
        print(f'  [INFO] 尝试以 {original_baud} bps 恢复连接...')
        time.sleep(1.0)
        transport = MCPTransport(port=port, baudrate=original_baud)
        transport.open()
        transport.flush_input()

        # 如果恢复成功，修正波特率
        orig_value = bytes([
            (original_baud >> 24) & 0xFF, (original_baud >> 16) & 0xFF,
            (original_baud >> 8) & 0xFF,  original_baud & 0xFF,
        ])
        set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, orig_value)
        transport.close()
        return

    pass_(f'SYS-20 PING OK at {target_baud} bps')

    # Step 7: GET_INFO 验证
    resp = send_cmd(transport2, SEQ, CMD_GET_INFO, b'', 0)
    SEQ += 1
    if resp is None:
        fail_('SYS-20', '新波特率 GET_INFO 超时')
    elif resp.payload[0] == ERR_SUCCESS:
        model = bytes(resp.payload[8:12]).decode('ascii', errors='replace')
        pass_(f'SYS-20 GET_INFO: ModelID={model}, ProtoVersion={resp.payload[16]:#04x}')
    else:
        fail_('SYS-20', f'GET_INFO Status={resp.payload[0]:#04x}')

    # Step 8: 恢复原始波特率
    print(f'  [INFO] 恢复原始波特率 {original_baud}...')
    orig_value = bytes([
        (original_baud >> 24) & 0xFF, (original_baud >> 16) & 0xFF,
        (original_baud >> 8) & 0xFF,  original_baud & 0xFF,
    ])
    resp = set_config(transport2, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, orig_value)
    if resp and resp.payload[0] == ERR_SUCCESS:
        pass_('SYS-20 SET_CONFIG 恢复原始波特率 OK')
    resp = send_cmd(transport2, SEQ, CMD_RESET, bytes([0x00]))
    SEQ += 1
    time.sleep(2.0)
    transport2.close()

    # 以原始波特率重新连接
    transport = MCPTransport(port=port, baudrate=original_baud)
    transport.open()
    transport.flush_input()
    time.sleep(0.5)
    transport.recv_event(timeout=2.0)  # 消费 boot event
    resp = send_cmd(transport, SEQ, CMD_PING, b'', 0)
    SEQ += 1
    if resp and resp.payload[0] == ERR_SUCCESS:
        pass_(f'SYS-20 恢复原始波特率 {original_baud} 成功')
    else:
        fail_('SYS-20', '恢复原始波特率失败！请手动重置设备')

    transport.close()


def main():
    global SEQ
    import argparse
    p = argparse.ArgumentParser(description='HEX-Bridge MCP Baud Rate Tests')
    p.add_argument('--port', default='COM35', help='MCP serial port')
    p.add_argument('--baud', type=int, default=115200, help='MCP baud rate')
    p.add_argument('--e2e', action='store_true', help='Run end-to-end baud switch test')
    args = p.parse_args()

    print('=' * 60)
    print('HEX-Bridge MCP Baud Rate Tests (SYS-16 ~ SYS-20)')
    print(f'Port: {args.port}, Baud: {args.baud}')
    print('=' * 60)

    transport = MCPTransport(port=args.port, baudrate=args.baud)
    try:
        transport.open()
    except Exception as e:
        print(f'[FATAL] 无法打开串口 {args.port}: {e}')
        sys.exit(1)

    transport.flush_input()
    time.sleep(0.2)

    # Consume any pending boot event
    boot_evt = transport.recv_event(timeout=1.0)
    if boot_evt:
        print(f'[INFO] 收到启动事件: ResetReason={boot_evt.payload[0]:#04x}')

    SEQ = 0x1000

    # SYS-16
    original_baud = test_sys16_get_default_baud(transport)

    # SYS-17
    test_sys17_set_and_readback(transport)

    # SYS-18
    test_sys18_reject_too_low(transport)

    # SYS-19
    test_sys19_reject_too_high(transport)

    # SYS-20 (optional, destructive)
    if args.e2e and original_baud:
        transport.close()
        transport = MCPTransport(port=args.port, baudrate=args.baud)
        transport.open()
        transport.flush_input()
        time.sleep(0.2)
        transport.recv_event(timeout=1.0)

        if original_baud != args.baud:
            print(f'  [INFO] 修复 NVS 波特率: {original_baud} → {args.baud}')
            value = bytes([
                (args.baud >> 24) & 0xFF, (args.baud >> 16) & 0xFF,
                (args.baud >> 8) & 0xFF,  args.baud & 0xFF,
            ])
            set_config(transport, CONFIG_GROUP_SYSTEM, CFGKEY_MCP_BAUD, value)
            original_baud = args.baud

        SEQ = 0x2000
        test_sys20_e2e_baud_switch(transport, original_baud, args.port)
    elif not args.e2e:
        skip_('SYS-20', '跳过端到端测试（使用 --e2e 启用）')
        transport.close()

    # Summary
    total = passed + failed + skipped
    print('\n' + '=' * 60)
    print(f'Results: {total} tests, {passed} PASS, {failed} FAIL, {skipped} SKIP')
    print('=' * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
