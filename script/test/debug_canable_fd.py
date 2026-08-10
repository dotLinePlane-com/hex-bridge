"""Smoke test: canable <-> MCP CAN FD communication."""
import sys, time, struct
sys.path.insert(0, ".")
from canable_slcan import CanableChannel
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

CMD_CAN_OPEN = 0x10; CMD_CAN_CLOSE = 0x11; CMD_CAN_CONFIG = 0x12
CMD_CAN_SEND = 0x13; CMD_CAN_RECV = 0x14
CAN_CHANNEL = 3

print("=== canable FD smoke test ===")

can = CanableChannel(port='COM6')
can.open()
print("canable version:", can.get_version())

# canable: 500k nominal + 2M data, normal, open
can.set_bitrate(500000)
can.set_data_bitrate(2000000)
can.set_retransmit(True)
can.cmd_open()
print("canable opened 500k/2M FD")
time.sleep(0.3)

# MCP: open + FD config (flags=0x07 FdMode, fd_baud=0x02=2M)
transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 200
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP OPEN: status=0x{f.payload[0]:02x}")
seq += 1
# FD mode: flags=0x07 (AutoRetransmit|AutoBusOff|FdMode), fd_baud_idx=0x02 (2M)
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x07, 0x20, 0x02)))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP CONFIG FD 2M: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.3)

# Test 1: canable -> MCP FD 64-byte (no BRS)
print("\n--- canable -> MCP FD 64B (no BRS) ---")
can.recv_all(timeout=0.2)
data = bytes(range(64))
can.send(0x100, data, is_fd=True)
f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
if f:
    cid = struct.unpack('>I', f.payload[0:4])[0]
    dlc = f.payload[4]
    rxd = f.payload[5:5+dlc]
    fd_bit = bool(cid & 0x20000000)
    print(f"MCP RECV: ID=0x{cid & 0x7FF:X} FD={fd_bit} DLC={dlc} len={len(rxd)}")
    print(f"  data ok: {rxd == data}")
else:
    print("MCP RECV: NO EVENT!")

# Test 2: MCP -> canable FD 64-byte (with BRS)
print("\n--- MCP -> canable FD 64B (BRS) ---")
fd_id = 0x20000000 | 0x200  # FD flag + ID 0x200
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', fd_id, 0x0F) + bytes(range(64))))  # DLC=15=64B, FD
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP SEND FD: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.3)
msg = can.recv(timeout=1.0)
if msg:
    print(f"canable RECV: {msg}")
    print(f"  is_fd={msg.is_fd} is_brs={msg.is_brs} len={len(msg.data)}")
    print(f"  data ok: {msg.data == bytes(range(64))}")
else:
    print("canable RECV: NO FRAME!")

# Test 3: canable -> MCP FD BRS standard
print("\n--- canable -> MCP FD 16B (BRS) ---")
data16 = bytes([0xAA] * 16)
can.send(0x300, data16, is_fd=True, is_brs=True)
f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
if f:
    cid = struct.unpack('>I', f.payload[0:4])[0]
    dlc = f.payload[4]
    rxflags = f.payload[5+dlc] if len(f.payload) > 5+dlc else 0
    print(f"MCP RECV: ID=0x{cid & 0x7FF:X} DLC={dlc} len={dlc} brs_flag={bool(rxflags & 0x08)}")
else:
    print("MCP RECV: NO EVENT!")

# Cleanup
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
can.cmd_close()
can.close()
transport.close()
print("\nDone")
