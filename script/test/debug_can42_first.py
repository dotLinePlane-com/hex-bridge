"""
Test CAN-42 as first test (no cumulative state).
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

# Pre-clean
transport.send(UBCPBuilder.build_request(1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
transport.flush_input()

pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
pcan.initialize()

# Now run exactly what test_can42 does (my latest version)
seq = 50
# CLOSE + OPEN + CONFIG 500k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=1.0)
transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"OPEN: 0x{f.payload[0]:02x}"); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
time.sleep(0.2)

# SEND Hello at 500k
pcan.read_all()
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x600, 5) + b'Hello'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"SEND Hello: 0x{f.payload[0]:02x}"); seq += 1

# CONFIG 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=5)
print(f"CONFIG 250k: 0x{f.payload[0]:02x}"); seq += 1

time.sleep(0.3)
pcan.uninitialize()
time.sleep(0.3)
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
pcan2.initialize()
pcan2.read_all()
time.sleep(0.1)

# SEND World at 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x601, 5) + b'World'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"SEND World: 0x{f.payload[0]:02x}"); seq += 1
time.sleep(0.3)

rx = pcan2.read(timeout_ms=1000)
if rx is None:
    time.sleep(0.5)
    rx = pcan2.read(timeout_ms=500)

print(f"PCAN World at 250k: {'OK ID=0x%X' % rx.id if rx else 'FAIL'}")
if rx is None:
    transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
    f = transport.recv_response(seq_num=seq, timeout=3)
    print(f"STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")

# Cleanup
transport.send(UBCPBuilder.build_request(seq+1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
pcan2.uninitialize()
transport.close()
print("Done")
