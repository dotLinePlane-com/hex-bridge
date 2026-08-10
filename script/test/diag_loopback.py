"""Loopback 自测 - 验证 MCP2518FD 内部通信"""
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

# CLOSE then OPEN loopback
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x02]))   # loopback mode
f = recv_any(1.0)
print('OPEN loopback:', hex(f.cmd_code), f.payload.hex())

send(0x12, bytes([0x06, 0x03, 32, 0]))  # CONFIG 500k
f = recv_any(1.0)
print('CONFIG:', hex(f.cmd_code), f.payload.hex())

# SEND a frame
send(0x13, (0x100).to_bytes(4, 'big') + bytes([3, 1, 2, 3]))
f = recv_any(1.0)
print('SEND:', hex(f.cmd_code), f.payload.hex())

# expect RECV event (loopback self-receive)
f = recv_any(2.0)
if f:
    print('RECV event:', hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP')
else:
    print('No RECV event!')

# STATUS
send(0x16, b'')
f = recv_any(1.0)
if f:
    print('STATUS:', hex(f.cmd_code), f.payload.hex())
else:
    print('No STATUS')

t.close()
