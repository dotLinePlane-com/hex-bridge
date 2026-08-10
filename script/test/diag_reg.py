"""读取 MCP2518FD 寄存器验证配置"""
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

# OPEN normal
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); f = recv_any(1.0)
print('OPEN:', f.payload.hex())
send(0x12, bytes([0x06, 0x03, 32, 0])); f = recv_any(1.0)
print('CONFIG:', f.payload.hex())

# STATUS
send(0x16, b''); f = recv_any(1.0)
print('STATUS:', f.payload.hex())
if f:
    print('  BusState=%d TEC=%d REC=%d' % (f.payload[1], f.payload[2], f.payload[3]))

# Try to read registers via debug - check DEVID and NBTCFG via SPI not accessible from here
# Check the firmware log instead via COM5
t.close()
