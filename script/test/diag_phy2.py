"""诊断: 检查 PCAN 发帧时固件 REC/事件反应"""
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
    # read until we get a real STATUS response
    end = time.time() + 1.5
    while time.time() < end:
        f = recv_any(0.3)
        if f and f.cmd_code == 0x16 and len(f.payload) >= 28:
            return f.payload
    return None

# OPEN normal
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); recv_any(1.0)
send(0x12, bytes([0x06, 0x03, 32, 0])); recv_any(1.0)
t.flush_input()

st = status()
print('Baseline:', st.hex() if st else 'None')
if st: print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# PCAN init and send - check if firmware detects bus activity
ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
s = ch.initialize()
print('PCAN init status: 0x%X' % s)

# send frames from PCAN continuously
t.flush_input()
ch.read_all(timeout_ms=50)
for i in range(100):
    st_p = ch.write(PcanMessage(id=0x123, data=bytes([i & 0xFF])))
    if st_p != PcanStatus.PCAN_ERROR_OK:
        print(f'PCAN write error at {i}: {hex(st_p)}'); break
    time.sleep(0.003)
print('PCAN sent 100 frames')

time.sleep(0.5)
st = status()
print('After PCAN:', st.hex() if st else 'None')
if st: print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# Check for any events (RECV/ERROR) received
t.flush_input()

ch.uninitialize()
t.close()
