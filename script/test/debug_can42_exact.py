"""
Simulate exact CAN-41->CAN-42 transition from the original test.
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

def send_cmd(t, seq, cmd, payload=b''):
    t.send(UBCPBuilder.build_request(seq, cmd, CAN_CHANNEL, payload))
    return t.recv_response(seq_num=seq, timeout=3.0)

def can_open(t, seq, mode=0):
    return send_cmd(t, seq, CMD_CAN_OPEN, bytes([mode]))

def can_close(t, seq):
    return send_cmd(t, seq, CMD_CAN_CLOSE, b'')

def can_config(t, seq, baud_idx, flags=0x03, fd_baud=0):
    return send_cmd(t, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', baud_idx, flags, 0x20, fd_baud))

def can_send(t, seq, can_id, data):
    return send_cmd(t, seq, CMD_CAN_SEND, struct.pack('>IB', can_id, len(data)) + data)

def can_status(t, seq):
    return send_cmd(t, seq, CMD_CAN_STATUS)

def ensure_open(t, seq, baud_idx=0x06):
    t.flush_input()
    send_cmd(t, seq, CMD_CAN_CLOSE, b'')
    t.recv_frame(timeout=1.0)
    t.flush_input()
    seq += 1
    can_open(t, seq, 0)
    seq += 1
    can_config(t, seq, baud_idx)
    seq += 1
    time.sleep(0.1)
    return seq

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

# PCAN at 500k
pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
pcan.initialize()

# Simulate CAN-41 ending (channel closed)
send_cmd(transport, 1, CMD_CAN_CLOSE, b'')
transport.recv_frame(timeout=1)
transport.flush_input()

seq = 10
base_seq = seq + 10  # 20

print("=== FIRST _ensure_open (from main) ===")
# This is what main does before calling test_can42
ensure_open(transport, base_seq)
# This consumes seq 20(close), 21(open), 22(config)
print("First _ensure_open done")

print("\n=== SECOND _ensure_open (inside test_can42) ===")
# Simulate test_can42 internal
seq2 = base_seq  # 20
transport.flush_input()
send_cmd(transport, seq2, CMD_CAN_CLOSE, b'')
transport.recv_frame(timeout=1.0)
transport.flush_input()
seq2 += 1
f = can_open(transport, seq2, 0)
print(f"OPEN seq={seq2}: status=0x{f.payload[0]:02x}")
seq2 += 1
f = can_config(transport, seq2, 0x06)
print(f"CONFIG 500k seq={seq2}: status=0x{f.payload[0]:02x}")
seq2 += 1
time.sleep(0.1)

# SEND Hello at 500k
pcan.read_all(timeout_ms=50)
f = can_send(transport, seq2, 0x600, b'Hello')
print(f"SEND Hello seq={seq2}: status=0x{f.payload[0]:02x}")
seq2 += 1

time.sleep(0.1)
rx = pcan.read(timeout_ms=500)
print(f"PCAN Hello: {'OK' if rx else 'FAIL'}")

# Config 250k
f = can_config(transport, seq2, 0x05)
print(f"CONFIG 250k seq={seq2}: status=0x{f.payload[0]:02x}")
seq2 += 1

time.sleep(0.15)
pcan.uninitialize()
time.sleep(0.2)
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
pcan2.initialize()
pcan2.read_all(timeout_ms=50)
time.sleep(0.1)

# Send World at 250k
f = can_send(transport, seq2, 0x601, b'World')
print(f"SEND World seq={seq2}: status=0x{f.payload[0]:02x}")
seq2 += 1

time.sleep(0.2)
rx = pcan2.read(timeout_ms=800)
if rx is None:
    time.sleep(0.3)
    rx = pcan2.read(timeout_ms=500)

print(f"PCAN World at 250k: {'OK ID=0x%X' % rx.id if rx else 'FAIL'}")

f = can_status(transport, seq2)
print(f"STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")

send_cmd(transport, seq2+1, CMD_CAN_CLOSE)
transport.recv_frame(timeout=1)
pcan2.uninitialize()
transport.close()
print("Done")
