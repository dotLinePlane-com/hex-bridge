"""Debug: capture raw slcan frames from canable during FD send."""
import sys, time, struct
sys.path.insert(0, ".")
import serial
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13
CAN_CHANNEL=3

# Setup canable
s = serial.Serial(port='COM6', baudrate=115200, timeout=0.05)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b'S6\r'); s.write(b'Y2\r'); s.write(b'O\r')
time.sleep(0.3)

# MCP FD open
transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()
seq = 100
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2); transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0])))
transport.recv_response(seq_num=seq, timeout=3); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x07, 0x20, 0x02)))
transport.recv_response(seq_num=seq, timeout=3); seq += 1
time.sleep(0.3)

# Send FD 64-byte from MCP
print("Sending FD 64B from MCP...")
data = bytes(range(64))
fd_id = 0x20000000 | 0x100
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', fd_id, 0x0F) + data))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP SEND: 0x{f.payload[0]:02x}")
seq += 1

# Read raw slcan data for 1 second
print("\nRaw canable RX:")
start = time.time()
while time.time() - start < 1.5:
    d = s.read(500)
    if d:
        print(f"  {d!r}")
time.sleep(0.3)

# Also send a classic frame for comparison
print("\nSending classic 3B from MCP...")
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x123, 3) + b'\x01\x02\x03'))
f = transport.recv_response(seq_num=seq, timeout=3)
seq += 1
start = time.time()
while time.time() - start < 1.0:
    d = s.read(500)
    if d:
        print(f"  {d!r}")

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
s.write(b'C\r')
s.close()
transport.close()
print("\nDone")
