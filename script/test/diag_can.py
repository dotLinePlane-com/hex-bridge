"""CAN 模块诊断脚本 - 检查响应流"""
import sys, time
sys.path.insert(0, r'D:\project\esp-idf-v6.0.1-project\hex-bridge\hex-bridge\script\test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

t = MCPTransport(port='COM4', baudrate=115200)
t.open()
print('opened')

CAN_CH = 3

def send(cmd, payload=b'', channel=CAN_CH, seq=10):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    t.send(wire)
    return seq + 1

def recv_all(timeout=1.0):
    frames = []
    end = time.time() + timeout
    while time.time() < end:
        f = t.recv_frame(timeout=0.2)
        if f:
            frames.append(f)
    return frames

# 1. CLOSE (清理)
send(0x11, b'')
fs = recv_all(1.0)
print('CLOSE responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 2. OPEN normal
send(0x10, bytes([0x00]))
fs = recv_all(1.0)
print('OPEN responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 3. OPEN dup
send(0x10, bytes([0x00]))
fs = recv_all(1.0)
print('OPEN dup responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 4. CLOSE
send(0x11, b'')
fs = recv_all(1.0)
print('CLOSE responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 5. CONFIG 500k
send(0x10, bytes([0x00]))
recv_all(0.5)
send(0x12, bytes([0x06, 0x03, 32, 0]))
fs = recv_all(1.0)
print('CONFIG responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 6. STATUS
send(0x16, b'')
fs = recv_all(1.0)
print('STATUS responses:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

# 7. CLOSE
send(0x11, b'')
fs = recv_all(1.0)
print('CLOSE final:', [(hex(f.cmd_code), f.payload.hex(), 'EVT' if f.is_event else 'RSP') for f in fs])

t.close()
