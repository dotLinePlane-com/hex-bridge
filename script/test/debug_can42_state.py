"""
Test CAN-42 after running a few prior tests to build up state.
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

def send_cmd(t, seq, cmd, payload=b''):
    t.send(UBCPBuilder.build_request(seq, cmd, CAN_CHANNEL, payload))
    return t.recv_response(seq_num=seq, timeout=3.0)

def status(t, seq):
    f = send_cmd(t, seq, CMD_CAN_STATUS)
    return f.payload[1], f.payload[2], f.payload[3]

# Simulate 5 OPEN/CLOSE cycles to build state
print("Building state with 5 OPEN/CLOSE cycles...")
for i in range(5):
    seq = 10 + i * 10
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'')
    transport.recv_frame(timeout=1)
    transport.flush_input()
    seq += 1
    send_cmd(transport, seq, CMD_CAN_OPEN, bytes([0x00]))
    f = transport.recv_response(seq_num=seq, timeout=3)
    seq += 1
    send_cmd(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00))
    transport.recv_response(seq_num=seq, timeout=3)
    seq += 1
    time.sleep(0.05)
    bs, tec, rec = status(transport, seq)
    print(f"  Cycle {i+1}: bs={bs} TEC={tec} REC={rec}")
    seq += 1
    send_cmd(transport, seq, CMD_CAN_CLOSE, b'')
    transport.recv_frame(timeout=1)
    transport.flush_input()

print(f"\nPcan status before CAN-42: 0x{pcan.get_status():X}")

# Now run CAN-42
seq = 100
send_cmd(transport, seq, CMD_CAN_CLOSE, b'')
transport.recv_frame(timeout=1)
transport.flush_input(); seq += 1

send_cmd(transport, seq, CMD_CAN_OPEN, bytes([0x00]))
f = transport.recv_response(seq_num=seq, timeout=3)
print(f"OPEN: 0x{f.payload[0]:02x}"); seq += 1

send_cmd(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00))
transport.recv_response(seq_num=seq, timeout=3); seq += 1
time.sleep(0.2)

# SEND Hello at 500k
pcan.read_all()
send_cmd(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x600, 5) + b'Hello')
transport.recv_response(seq_num=seq, timeout=3); seq += 1
time.sleep(0.1)
rx = pcan.read(timeout_ms=500)
print(f"Hello at 500k: {'OK' if rx else 'FAIL'}")

bs, tec, rec = status(transport, seq)
print(f"STATUS before 250k switch: bs={bs} TEC={tec} REC={rec}"); seq += 1

# CONFIG 250k
send_cmd(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00))
transport.recv_response(seq_num=seq, timeout=5); seq += 1

bs, tec, rec = status(transport, seq)
print(f"STATUS after 250k config: bs={bs} TEC={tec} REC={rec}"); seq += 1

time.sleep(0.5)
pcan.uninitialize()
time.sleep(0.5)
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
pcan2.initialize()
pcan2.read_all()
time.sleep(0.1)

# SEND World at 250k
send_cmd(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x601, 5) + b'World')
transport.recv_response(seq_num=seq, timeout=3); seq += 1
time.sleep(0.3)

rx = pcan2.read(timeout_ms=1000)
if rx is None:
    time.sleep(0.5)
    rx = pcan2.read(timeout_ms=500)

print(f"World at 250k: {'OK ID=0x%X' % rx.id if rx else 'FAIL'}")

bs, tec, rec = status(transport, seq)
print(f"STATUS after World: bs={bs} TEC={tec} REC={rec}")

send_cmd(transport, seq+1, CMD_CAN_CLOSE, b'')
transport.recv_frame(timeout=2)
pcan2.uninitialize()
transport.close()
print("Done")
