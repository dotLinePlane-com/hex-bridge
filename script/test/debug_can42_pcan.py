"""
Debug CAN-42 with PCAN: Test baud switch 500k -> 250k with PCAN at both speeds.
"""
import sys
import time
import struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN = 0x10
CMD_CAN_CLOSE = 0x11
CMD_CAN_CONFIG = 0x12
CMD_CAN_SEND = 0x13
CMD_CAN_STATUS = 0x16
CAN_CHANNEL = 3
ERR_SUCCESS = 0x00

def baud_name_to_pcan(name):
    name = name.lower().rstrip('kbps')
    bps = int(name.replace('k', '000').replace('m', '000000'))
    m = {1000000: PcanBaudrate.PCAN_BD_1M, 800000: PcanBaudrate.PCAN_BD_800K,
         500000: PcanBaudrate.PCAN_BD_500K, 250000: PcanBaudrate.PCAN_BD_250K,
         125000: PcanBaudrate.PCAN_BD_125K, 100000: PcanBaudrate.PCAN_BD_100K,
         50000: PcanBaudrate.PCAN_BD_50K, 20000: PcanBaudrate.PCAN_BD_20K,
         10000: PcanBaudrate.PCAN_BD_10K}
    return m.get(bps, PcanBaudrate.PCAN_BD_500K)

# Init PCAN at 500k
print("Initializing PCAN at 500k...")
pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=baud_name_to_pcan('500k'))
s = pcan.initialize()
if s != PcanStatus.PCAN_ERROR_OK:
    print(f"PCAN init failed: {PcanChannel.error_text(s)}")
    sys.exit(1)
print(f"PCAN status: 0x{pcan.get_status():X}")

# Init MCP Transport
transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 100

# Close
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
transport.flush_input()
seq += 1

# Open
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"OPEN: status=0x{f.payload[0]:02x}")
seq += 1

# Config 500k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"CONFIG 500k: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.2)

# STEP 1: Send Hello at 500k (PCAN at 500k)
pcan.read_all(timeout_ms=50)
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x600, 5) + b'Hello'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"SEND Hello at 500k: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.1)
rx = pcan.read(timeout_ms=500)
if rx:
    print(f"  PCAN received: ID=0x{rx.id:X} data={rx.data}")
else:
    print(f"  PCAN: NO frame received at 500k!")
    print(f"  PCAN status: 0x{pcan.get_status():X}")
    # Check MCP errors
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
    f = transport.recv_response(seq_num=seq, timeout=3)
    print(f"  MCP STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
    seq += 1

# STEP 2: Config MCP to 250k
print("\nSwitching MCP to 250k...")
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"CONFIG 250k: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.2)

# STEP 3: Switch PCAN to 250k
print("Switching PCAN to 250k...")
pcan.uninitialize()
time.sleep(0.3)
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=baud_name_to_pcan('250k'))
s = pcan2.initialize()
if s != PcanStatus.PCAN_ERROR_OK:
    print(f"PCAN 250k init failed: {PcanChannel.error_text(s)}")
else:
    print(f"PCAN 250k initialized, status=0x{pcan2.get_status():X}")

pcan2.read_all(timeout_ms=100)
time.sleep(0.2)

# STEP 4: Send World at 250k
print("\nSending World at 250k...")
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x601, 5) + b'World'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"SEND World at 250k: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.2)

# Check PCAN received
rx = pcan2.read(timeout_ms=800)
if rx:
    print(f"  PCAN 250k received: ID=0x{rx.id:X} data={rx.data}")
else:
    print(f"  PCAN 250k: NO frame received!")
    # Try again
    rx = pcan2.read(timeout_ms=500)
    if rx:
        print(f"  PCAN 250k received (retry): ID=0x{rx.id:X} data={rx.data}")
    else:
        print(f"  PCAN 250k: Still nothing")

# Check MCP status
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
print(f"  Tx={struct.unpack('>H', f.payload[8:10])[0]} Rx={struct.unpack('>H', f.payload[10:12])[0]}")
print(f"  AckErr={struct.unpack('>H', f.payload[22:24])[0]}")

# Close
transport.send(UBCPBuilder.build_request(seq + 1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)

pcan2.uninitialize()
transport.close()
print("\nDone")
