"""波特率探测 - PCAN 发帧, 固件测波特率匹配"""
import sys, time
sys.path.insert(0, r'D:\project\esp-idf-v6.0.1-project\hex-bridge\hex-bridge\script\test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder
from pcan_basic import PcanChannel, PcanBaudrate, PcanHandle, PcanStatus, PcanMessage

t = MCPTransport(port='COM4', baudrate=115200)
t.open()

CAN_CH = 3

def send(cmd, payload=b'', channel=CAN_CH, seq=10):
    wire = UBCPBuilder.build_request(seq, cmd, channel, payload)
    t.send(wire)

def recv_any(timeout=0.5):
    return t.recv_frame(timeout=timeout)

# OPEN normal + flush events
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); recv_any(1.0)
send(0x12, bytes([0x06, 0x03, 32, 0])); recv_any(1.0)
t.flush_input()

# PCAN send frames at various bauds, see which one firmware receives
for baud_name, baud in [('500k', PcanBaudrate.PCAN_BD_500K),
                        ('250k', PcanBaudrate.PCAN_BD_250K),
                        ('1M', PcanBaudrate.PCAN_BD_1M)]:
    ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=baud)
    if ch.initialize() != PcanStatus.PCAN_ERROR_OK:
        print(f'{baud_name}: init fail'); continue
    ch.read_all(timeout_ms=50)
    # flush firmware input
    t.flush_input()
    ch.write(PcanMessage(id=0x123, data=b'\xAA\xBB'))
    time.sleep(0.3)
    f = recv_any(0.5)
    if f and f.cmd_code == 0x14:
        print(f'{baud_name}: FIRMWARE RECEIVED! {f.payload.hex()}')
    else:
        print(f'{baud_name}: no RECV (got {hex(f.cmd_code) if f else "none"})')
    ch.uninitialize()

# Now firmware SEND at 500k, PCAN listen at 500k
ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=PcanBaudrate.PCAN_BD_500K)
ch.initialize()
ch.read_all(timeout_ms=50)
t.flush_input()
send(0x13, (0x555).to_bytes(4, 'big') + bytes([2, 0xDE, 0xAD]))
recv_any(1.0)  # SEND response
time.sleep(0.3)
msgs = ch.read_all(timeout_ms=300)
print(f'Firmware SEND 500k → PCAN got {len(msgs)}')
for m in msgs:
    print(f'  ID=0x{m.id:X} data={m.data.hex()}')
ch.uninitialize()

t.close()
