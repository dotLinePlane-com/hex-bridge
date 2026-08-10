"""
Debug: Test 250k directly without baud switch.
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

# Init PCAN at 250k first
print("Init PCAN at 250k...")
pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
s = pcan.initialize()
print(f"PCAN init: 0x{s:X} status=0x{pcan.get_status():X}")

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 100
# Close + Open + Config 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2); transport.flush_input(); seq += 1

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"OPEN: status=0x{f.payload[0]:02x}")

# Config directly to 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"CONFIG 250k: status=0x{f.payload[0]:02x}")
time.sleep(0.2)

# Check status
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
seq += 1

# Try PCAN -> MCP
pcan.read_all(timeout_ms=50)
s = pcan.write(PcanMessage(id=0x100, data=b'PCAN25'))
print(f"PCAN write 0x100: 0x{s:X}")
time.sleep(0.2)

# Check MCP received via RECV event
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS after PCAN send: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]} Rx={struct.unpack('>H', f.payload[10:12])[0]}")
seq += 1

# Try MCP -> PCAN
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x200, 5) + b'MCP25'))
f = transport.recv_response(seq_num=seq, timeout=3); seq += 1
print(f"SEND MCP at 250k: status=0x{f.payload[0]:02x}")
time.sleep(0.2)
rx = pcan.read(timeout_ms=1000)
print(f"PCAN recv: {'OK ID=0x%X data=%s' % (rx.id, rx.data) if rx else 'NO FRAME'}")

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"STATUS final: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")

transport.send(UBCPBuilder.build_request(seq+1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)

pcan.uninitialize()
transport.close()
print("Done")
