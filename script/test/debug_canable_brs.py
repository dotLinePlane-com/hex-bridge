"""Debug: capture raw slcan for FD BRS frame from MCP."""
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

# Send FD+BRS 16-byte frame
print("Sending FD+BRS 16B from MCP...")
data = bytes([0xAA] * 16)
fd_id = 0x20000000 | 0x10000000 | 0x100  # FD + BRS + ID
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', fd_id, 10) + data))  # DLC=10 = 16B
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP SEND FD+BRS: 0x{f.payload[0]:02x}")
seq += 1

print("\nRaw canable RX:")
start = time.time()
while time.time() - start < 1.5:
    d = s.read(500)
    if d:
        print(f"  {d!r}")

# Check MCP error state
print("\nMCP STATUS:")
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
if f:
    print(f"  bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]} "
          f"ack={struct.unpack('>H', f.payload[22:24])[0]} "
          f"stuff={struct.unpack('>H', f.payload[26:28])[0]}")
seq += 1

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
s.write(b'C\r')
s.close()
transport.close()
print("\nDone")
