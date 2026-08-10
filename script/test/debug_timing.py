"""
Debug: Read back CiNBTCFG after config to verify timing register write.
"""
import sys
import time
import struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN = 0x10; CMD_CAN_CLOSE = 0x11
CMD_CAN_CONFIG = 0x12; CMD_CAN_SEND = 0x13; CMD_CAN_STATUS = 0x16
CAN_CHANNEL = 3; ERR_SUCCESS = 0x00

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 100

# Close + Open + Config 500k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2); transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"OPEN: status=0x{f.payload[0]:02x}")

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"CONFIG 500k: status=0x{f.payload[0]:02x}")

time.sleep(0.2)

# Send at 500k with PCAN at 500k
pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
pcan.initialize()
pcan.read_all(timeout_ms=50)

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x100, 3) + b'\x01\x02\x03'))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"SEND at 500k: status=0x{f.payload[0]:02x}")
time.sleep(0.1)
rx = pcan.read(timeout_ms=500)
print(f"  PCAN 500k: {'OK ID=0x%X' % rx.id if rx else 'NO FRAME'}")

# Check TEC/REC
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS 500k: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
seq += 1

# Now config 250k  
print("\n--- Switching to 250k ---")
pcan.uninitialize()
time.sleep(0.1)

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=5); seq += 1
print(f"CONFIG 250k: status=0x{f.payload[0]:02x}")

time.sleep(0.2)

# Init PCAN at 250k
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
s = pcan2.initialize()
print(f"PCAN 250k init: status=0x{s:X}")
pcan2.read_all(timeout_ms=100)

# Check TEC/REC before sending
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS 250k: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
seq += 1

# Send World at 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x200, 5) + b'World'))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"SEND at 250k: status=0x{f.payload[0]:02x}")
time.sleep(0.2)

rx = pcan2.read(timeout_ms=1000)
if rx:
    print(f"  PCAN 250k: OK ID=0x{rx.id:X} data={rx.data}")
else:
    print(f"  PCAN 250k: NO FRAME")
    time.sleep(0.3)
    rx = pcan2.read(timeout_ms=500)
    if rx:
        print(f"  PCAN 250k retry: OK ID=0x{rx.id:X}")
    else:
        print(f"  PCAN 250k: STILL NO FRAME")

# Check final TEC/REC
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS final: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")

transport.send(UBCPBuilder.build_request(seq + 1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)

pcan2.uninitialize()
transport.close()
print("Done")
