"""决定性诊断: MCP 发送后检查 TEC, 验证 TX 路径"""
import sys, time
sys.path.insert(0, r'D:\project\esp-idf-v6.0.1-project\hex-bridge\hex-bridge\script\test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

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
print('Before SEND:', st.hex() if st else 'None')
if st: print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# SEND one frame (PCAN not connected on bus... but PCAN IS connected per earlier)
t.flush_input()
send(0x13, (0x123).to_bytes(4, 'big') + bytes([1, 0xAA]))
f = recv_any(1.0)
print('SEND resp:', hex(f.cmd_code) if f else 'none', f.payload.hex() if f else '')

time.sleep(0.3)
st = status()
print('After SEND:', st.hex() if st else 'None')
if st: print('  TEC=%d REC=%d BusState=%d' % (st[2], st[3], st[1]))

# Now check: does TEC increase if we send many frames? (no ACK → TEC grows)
t.flush_input()
for i in range(20):
    send(0x13, (0x100+i).to_bytes(4, 'big') + bytes([1, i]))
    recv_any(0.5)
    time.sleep(0.01)
time.sleep(0.5)
st = status()
print('After 20x SEND:', st.hex() if st else 'None')
if st: print('  TEC=%d REC=%d BusState=%d TxCount=%d' % (st[2], st[3], st[1], int.from_bytes(st[8:10],'big')))

t.close()
