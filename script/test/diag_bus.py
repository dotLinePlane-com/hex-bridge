"""外部总线 SEND 测试 - 固件发帧, PCAN 收"""
import sys, time
sys.path.insert(0, r'D:\project\esp-idf-v6.0.1-project\hex-bridge\hex-bridge\script\test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

t = MCPTransport(port='COM4', baudrate=115200)
t.open()

ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
s = ch.initialize()
print('PCAN init:', hex(s))

CAN_CH = 3

def send(cmd, payload=b'', channel=CAN_CH, seq=10):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    t.send(wire)

def recv_any(timeout=0.5):
    return t.recv_frame(timeout=timeout)

# OPEN normal
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00]))
f = recv_any(1.0)
print('OPEN:', hex(f.cmd_code), f.payload.hex())

send(0x12, bytes([0x06, 0x03, 32, 0]))
f = recv_any(1.0)
print('CONFIG:', hex(f.cmd_code), f.payload.hex())

# SEND frames
ch.read_all(timeout_ms=50)
for i in range(3):
    send(0x13, (0x123).to_bytes(4, 'big') + bytes([3, 1, 2, 3]))
    f = recv_any(1.0)
    print(f'SEND {i}:', hex(f.cmd_code), f.payload.hex())

time.sleep(0.3)
msgs = ch.read_all(timeout_ms=300)
print(f'PCAN received {len(msgs)} frames')
for m in msgs:
    print(f'  ID=0x{m.id:X} data={m.data.hex()}')

st = ch.get_status()
print('PCAN status: 0x%X' % st)

# STATUS
send(0x16, b'')
f = recv_any(1.0)
if f:
    print('STATUS:', f.payload.hex())

ch.uninitialize()
t.close()
