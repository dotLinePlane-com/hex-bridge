"""
Reproduce CAN-41 -> CAN-42 back-to-back (within full test context).
"""
import sys, time, struct
sys.path.insert(0, ".")
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

CMD_CAN_OPEN=0x10; CMD_CAN_CLOSE=0x11; CMD_CAN_CONFIG=0x12
CMD_CAN_SEND=0x13; CMD_CAN_RECV=0x14; CMD_CAN_STATUS=0x16
CAN_CHANNEL=3; ERR_SUCCESS=0x00

transport = MCPTransport(port='COM4', baudrate=115200)
transport.open()
transport.flush_input()

pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
pcan.initialize()

def sc(t, seq, cmd, payload=b''):
    t.send(UBCPBuilder.build_request(seq, cmd, CAN_CHANNEL, payload))
    return t.recv_response(seq_num=seq, timeout=5)

def close_cmd(t, seq):
    t.send(UBCPBuilder.build_request(seq, CMD_CAN_CLOSE, CAN_CHANNEL, b''))
    t.recv_frame(timeout=2)
    t.flush_input()

print("=== CAN-41 lifecycle ===")
seq = 400
close_cmd(transport, seq); seq += 1
sc(transport, seq, CMD_CAN_OPEN, bytes([0])); seq += 1
sc(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)); seq += 1
time.sleep(0.1)
sc(transport, seq, CMD_CAN_STATUS); seq += 1
pcan.read_all()
sc(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x100, 6) + b'HELLO1'); seq += 1
rx = pcan.read(timeout_ms=1000)
print(f"CAN-41 SEND HELLO1: {'OK' if rx else 'FAIL'}")
transport.flush_input()
pcan.write(PcanMessage(id=0x200, data=b'WORLD2'))
transport.recv_event(cmd_code=CMD_CAN_RECV, timeout=2)
sc(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x2000 | 0x80000000, 7) + b'EXTEND2'); seq += 1
sc(transport, seq, CMD_CAN_STATUS); seq += 1
close_cmd(transport, seq); seq += 1
print("CAN-41 done (closed)")

print("\n=== CAN-42 immediately after ===")
close_cmd(transport, seq); seq += 1
sc(transport, seq, CMD_CAN_OPEN, bytes([0])); seq += 1
sc(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)); seq += 1
time.sleep(0.2)

pcan.read_all()
sc(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x600, 5) + b'Hello'); seq += 1
time.sleep(0.1)
rx = pcan.read(timeout_ms=500)
print(f"Hello at 500k: {'OK' if rx else 'FAIL'}")

sc(transport, seq, CMD_CAN_CONFIG, struct.pack('>BBBB', 0x05, 0x03, 0x20, 0x00)); seq += 1
time.sleep(0.3)

f = sc(transport, seq, CMD_CAN_STATUS)
print(f"After 250k config: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
seq += 1

pcan.uninitialize()
time.sleep(0.3)
pcan2 = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_250K)
pcan2.initialize()
pcan2.read_all()
time.sleep(0.2)

sc(transport, seq, CMD_CAN_SEND, struct.pack('>IB', 0x601, 5) + b'World'); seq += 1
time.sleep(0.3)
rx = pcan2.read(timeout_ms=1000)
if rx is None:
    time.sleep(0.5)
    rx = pcan2.read(timeout_ms=500)
print(f"World at 250k: {'OK ID=0x%X' % rx.id if rx else 'FAIL'}")

f = sc(transport, seq, CMD_CAN_STATUS)
ack = struct.unpack('>H', f.payload[22:24])[0]
print(f"After World: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]} AckErr={ack}")

close_cmd(transport, seq+1)
pcan2.uninitialize()
transport.close()
print("Done")
