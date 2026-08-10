"""
Debug CAN-42: Test baud switch 500k -> 250k.
"""
import sys
import time
import struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

CMD_CAN_OPEN = 0x10
CMD_CAN_CLOSE = 0x11
CMD_CAN_CONFIG = 0x12
CMD_CAN_SEND = 0x13
CMD_CAN_STATUS = 0x16
CAN_CHANNEL = 3
ERR_SUCCESS = 0x00

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 100

# Close first
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
transport.flush_input()
seq += 1

# Open
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3)
caps = struct.unpack(">I", f.payload[4:8])[0] if len(f.payload) >= 8 else 0
print(f"OPEN: status=0x{f.payload[0]:02x} caps=0x{caps:08x}")
seq += 1

# Config 500k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"CONFIG 500k: status=0x{f.payload[0]:02x}")
seq += 1

time.sleep(0.1)

# Send Hello at 500k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x600, 5) + b'Hello'))
f = transport.recv_response(seq_num=seq, timeout=3)
ts = struct.unpack(">I", f.payload[1:5])[0] if len(f.payload) >= 5 else 0
print(f"SEND Hello at 500k: status=0x{f.payload[0]:02x} ts={ts}")
seq += 1

# Check status before baud switch
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS before switch: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
seq += 1

# Config 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"CONFIG 250k: status=0x{f.payload[0]:02x}")
seq += 1

time.sleep(0.2)

# Read OPMOD via STATUS
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
bs = f.payload[1]; tec = f.payload[2]; rec = f.payload[3]
tx = struct.unpack(">H", f.payload[8:10])[0]
rx = struct.unpack(">H", f.payload[10:12])[0]
print(f"STATUS after 250k switch: bs={bs} TEC={tec} REC={rec} Tx={tx} Rx={rx}")
seq += 1

# Send World at 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x601, 5) + b'World'))
f = transport.recv_response(seq_num=seq, timeout=3)
ts2 = struct.unpack(">I", f.payload[1:5])[0] if len(f.payload) >= 5 else 0
print(f"SEND World at 250k: status=0x{f.payload[0]:02x} ts={ts2}")
seq += 1

# Check status after send
time.sleep(0.2)
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
bs = f.payload[1]; tec = f.payload[2]; rec = f.payload[3]
tx = struct.unpack(">H", f.payload[8:10])[0]
rx = struct.unpack(">H", f.payload[10:12])[0]
print(f"STATUS after 250k send: bs={bs} TEC={tec} REC={rec} Tx={tx} Rx={rx}")
seq += 1

# Close
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
f = transport.recv_frame(timeout=2)
print("CLOSE OK" if f else "CLOSE no response")

transport.close()
print("Done")
