"""
After full test failure, test 250k bidirectional with fresh PCAN init.
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

print("=== 250k bidirectional check after full-test failure ===")

# PCAN at 250k
pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
s = pcan.initialize()
print(f"PCAN 250k init: 0x{s:X} status=0x{pcan.get_status():X}")

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 200
# Close + Open + Config 250k
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=3); transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=5)
print(f"OPEN: 0x{f.payload[0]:02x}"); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)))
f = transport.recv_response(seq_num=seq, timeout=5)
print(f"CONFIG 250k: 0x{f.payload[0]:02x}"); seq += 1
time.sleep(0.3)

# Direction 1: PCAN -> MCP
pcan.read_all(timeout_ms=100)
pcan.write(PcanMessage(id=0x100, data=b'PC2M'))
time.sleep(0.2)
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
rx_cnt = struct.unpack('>H', f.payload[10:12])[0]
print(f"PCAN->MCP: MCP Rx={rx_cnt} (bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]})")
seq += 1

# Direction 2: MCP -> PCAN
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x200, 5) + b'M2PCX'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP SEND: 0x{f.payload[0]:02x}"); seq += 1
time.sleep(0.3)
rx = pcan.read(timeout_ms=1000)
print(f"MCP->PCAN: {'OK ID=0x%X' % rx.id if rx else 'NO FRAME'}")

transport.send(UBCPBuilder.build_request(seq, CMD_CAN_STATUS, CAN_CHANNEL, b''))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"FINAL STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")

transport.send(UBCPBuilder.build_request(seq+1, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
pcan.uninitialize()
transport.close()
print("Done")
