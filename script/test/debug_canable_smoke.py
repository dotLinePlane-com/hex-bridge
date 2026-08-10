"""Smoke test: canable -> MCP basic communication at 500k."""
import sys, time, struct
sys.path.insert(0, ".")
from canable_slcan import CanableChannel
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

CMD_CAN_OPEN = 0x10; CMD_CAN_CLOSE = 0x11; CMD_CAN_CONFIG = 0x12
CMD_CAN_SEND = 0x13; CMD_CAN_RECV = 0x14
CAN_CHANNEL = 3

print("=== canable smoke test ===")

# Open canable
can = CanableChannel(port='COM6')
can.open()
print("canable version:", can.get_version())

# Configure canable at 500k, normal mode, open
can.set_bitrate(500000)
can.set_retransmit(True)
can.set_silent(False)
can.cmd_open()
print("canable opened at 500k")
time.sleep(0.3)

# Open MCP
transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

seq = 100
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
transport.flush_input(); seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_OPEN, CAN_CHANNEL, bytes([0x00])))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP OPEN: status=0x{f.payload[0]:02x}")
seq += 1
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CONFIG, CAN_CHANNEL,
    struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))  # 500k classic
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP CONFIG 500k: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.3)

# Test 1: canable -> MCP (standard frame)
print("\n--- canable -> MCP (std 0x123, 3 bytes) ---")
can.recv_all(timeout=0.2)
can.send(0x123, b'\x01\x02\x03')
f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
if f:
    cid = struct.unpack('>I', f.payload[0:4])[0]
    dlc = f.payload[4]
    data = f.payload[5:5+dlc]
    print(f"MCP RECV: ID=0x{cid & 0x7FF:X} DLC={dlc} data={data.hex()}")
else:
    print("MCP RECV: NO EVENT!")

# Test 2: MCP -> canable (standard frame)
print("\n--- MCP -> canable (std 0x456, 4 bytes) ---")
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_SEND, CAN_CHANNEL,
    struct.pack('>IB', 0x456, 4) + b'\xAA\xBB\xCC\xDD'))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"MCP SEND: status=0x{f.payload[0]:02x}")
seq += 1
time.sleep(0.3)
msg = can.recv(timeout=1.0)
if msg:
    print(f"canable RECV: {msg}")
else:
    print("canable RECV: NO FRAME!")

# Test 3: canable -> MCP (extended frame)
print("\n--- canable -> MCP (ext 0x1ABCDEF, 5 bytes) ---")
can.send(0x1ABCDEF, b'\x10\x20\x30\x40\x50', is_extended=True)
f = transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2.0)
if f:
    cid = struct.unpack('>I', f.payload[0:4])[0]
    ext = bool(cid & 0x80000000)
    print(f"MCP RECV: ID=0x{cid & 0x1FFFFFFF:X} EXT={ext}")
else:
    print("MCP RECV: NO EVENT!")

# Cleanup
transport.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
transport.recv_frame(timeout=2)
can.cmd_close()
can.close()
transport.close()
print("\nDone")
