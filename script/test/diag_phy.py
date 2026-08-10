"""诊断: PCAN 发帧时检查固件 REC 计数变化"""
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

def status():
    send(0x16, b'')
    f = recv_any(1.0)
    if f and f.cmd_code == 0x16 and len(f.payload) >= 28:
        return f.payload
    return None

# OPEN normal
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); recv_any(1.0)
send(0x12, bytes([0x06, 0x03, 32, 0])); recv_any(1.0)
t.flush_input()

# Baseline STATUS
st = status()
print('Baseline STATUS:', st.hex() if st else 'None')
if st:
    print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# PCAN send frames at 500k
ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
ch.initialize()
for i in range(50):
    ch.write(PcanMessage(id=0x100+i, data=bytes([i&0xFF])))
    time.sleep(0.005)
time.sleep(0.3)

st = status()
print('After PCAN 50x send:', st.hex() if st else 'None')
if st:
    print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# Now firmware send, PCAN listen
ch.read_all(timeout_ms=50)
t.flush_input()
send(0x13, (0x200).to_bytes(4, 'big') + bytes([1, 0xAA]))
recv_any(1.0)
time.sleep(0.3)
msgs = ch.read_all(timeout_ms=300)
print(f'Firmware SEND → PCAN got {len(msgs)}')

# PCAN loopback test: does PCAN see its own frames?
ch.read_all(timeout_ms=50)
ch.write(PcanMessage(id=0x300, data=b'\x55'))
time.sleep(0.2)
own = ch.read_all(timeout_ms=200)
print(f'PCAN loopback self-echo: {len(own)} frames')

st = status()
if st:
    print('Final STATUS: TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

ch.uninitialize()
t.close()
