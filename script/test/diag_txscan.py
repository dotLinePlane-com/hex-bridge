"""MCP 发送, PCAN 各波特率监听"""
import sys, time
sys.path.insert(0, r'D:\project\esp-idf-v6.0.1-project\hex-bridge\hex-bridge\script\test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

t = MCPTransport(port='COM4', baudrate=115200)
t.open()
CAN_CH = 3

def send(cmd, payload=b'', channel=CAN_CH, seq=10):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    t.send(wire)

def recv_any(timeout=0.5):
    return t.recv_frame(timeout=timeout)

# OPEN normal + CONFIG 500k
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); recv_any(1.0)
send(0x12, bytes([0x06, 0x03, 32, 0])); recv_any(1.0)
t.flush_input()

bauds = [('10k', PcanBaudrate.PCAN_BD_10K),
         ('20k', PcanBaudrate.PCAN_BD_20K),
         ('50k', PcanBaudrate.PCAN_BD_50K),
         ('100k', PcanBaudrate.PCAN_BD_100K),
         ('125k', PcanBaudrate.PCAN_BD_125K),
         ('250k', PcanBaudrate.PCAN_BD_250K),
         ('500k', PcanBaudrate.PCAN_BD_500K),
         ('800k', PcanBaudrate.PCAN_BD_800K),
         ('1M', PcanBaudrate.PCAN_BD_1M)]

for name, bd in bauds:
    ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=bd)
    if ch.initialize() != PcanStatus.PCAN_ERROR_OK:
        print(f'{name}: init fail'); continue
    ch.read_all(timeout_ms=50)
    t.flush_input()
    send(0x13, (0x555).to_bytes(4, 'big') + bytes([2, 0xDE, 0xAD]))
    recv_any(1.0)
    time.sleep(0.2)
    msgs = ch.read_all(timeout_ms=300)
    if msgs:
        print(f'{name}: RECEIVED {len(msgs)} frames!')
        for m in msgs[:2]:
            print(f'    ID=0x{m.id:X} data={m.data.hex()}')
    else:
        print(f'{name}: no frames')
    ch.uninitialize()

t.close()
