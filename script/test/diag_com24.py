"""COM24 诊断: SEND + BREAK 观测"""
import serial, time, struct, sys
sys.path.insert(0, 'D:/project/esp-idf-v6.0.1-project/hex-bridge/script/test')
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

CMD_OPEN   = 0xA0
CMD_CONFIG = 0xA2
CMD_SEND   = 0xA3
CMD_BREAK  = 0xA5

print('=== COM24 Diagnostic: SEND + BREAK ===')
print()

transport = MCPTransport()
transport.open()
com24 = serial.Serial(port='COM24', baudrate=115200, timeout=0.05)
com24.flushInput()

def send_cmd(seq, cmd, payload=b''):
    wire = UBCPBuilder.build_request(seq, cmd, 0, payload)
    transport.send(wire)
    return transport.recv_frame(timeout=2.0)

def read_com24(label):
    time.sleep(0.3)
    buf = bytearray()
    t0 = time.time()
    while time.time() - t0 < 0.3:
        nb = com24.in_waiting
        if nb:
            b = com24.read(nb)
            if b:
                buf.extend(b)
        else:
            time.sleep(0.02)
    hex_str = buf.hex() if buf else '(empty)'
    print(f'  [{label}] COM24: {len(buf)}B = {hex_str}')

# Setup
send_cmd(1, CMD_OPEN, bytes([0]))
send_cmd(2, CMD_CONFIG, struct.pack('>IBBBBHB', 115200, 8, 1, 0, 0, 1, 0))
read_com24('after init')

# 1) SEND Hello World
data = b'Hello World'
send_cmd(3, CMD_SEND, struct.pack('>H', len(data)) + data)
read_com24('SEND HelloWorld')

# 2) SEND empty
send_cmd(4, CMD_SEND, struct.pack('>H', 0))
read_com24('SEND empty')

# 3) SET_BREAK 15ms
send_cmd(5, CMD_BREAK, struct.pack('>H', 15))
read_com24('SET_BREAK 15ms')

# 4) Flush and re-read
com24.flushInput()
time.sleep(0.3)
read_com24('after flush')

# 5) SET_BREAK again (to confirm)
send_cmd(6, CMD_BREAK, struct.pack('>H', 10))
read_com24('SET_BREAK 10ms')

transport.close()
com24.close()
print()
print('=== Done ===')
