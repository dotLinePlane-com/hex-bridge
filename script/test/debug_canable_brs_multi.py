"""Test: send multiple FD+BRS frames from MCP, capture canable slcan output."""
import sys, time, struct
sys.path.insert(0, ".")
import serial
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3

s = serial.Serial(port='COM6', baudrate=115200, timeout=0.05)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b'S6\r'); s.write(b'Y2\r'); s.write(b'O\r')
time.sleep(0.3)

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

# Send 10 FD+BRS frames
print("Sending 10x FD+BRS 16B frames...")
fd_id = 0x20000000 | 0x10000000 | 0x100
for i in range(10):
    data = bytes([0xAA + i] * 16)
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
        struct.pack('>IB', fd_id, 10) + data))
    f = transport.recv_response(seq_num=seq, timeout=3)
    seq += 1
    time.sleep(0.1)
print("10 frames sent")

# Capture canable RX for 3s
print("\nCanable RX capture (3s):")
start = time.time()
total = b''
while time.time() - start < 3.0:
    d = s.read(500)
    if d:
        total += d
        print(f"  {d!r}")
print(f"\nTotal canable bytes: {len(total)}")

# Also send non-BRS FD frames for comparison
print("\nSending 3x FD no-BRS 16B frames...")
for i in range(3):
    data = bytes([0x10 + i] * 16)
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
        struct.pack('>IB', 0x20000000 | 0x200, 10) + data))
    transport.recv_response(seq_num=seq, timeout=3)
    seq += 1
    time.sleep(0.1)
time.sleep(0.5)
while True:
    d = s.read(500)
    if not d:
        break
    print(f"  {d!r}")

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
s.write(b'C\r')
s.close()
transport.close()
print("\nDone")
