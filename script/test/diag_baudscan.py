"""波特率扫描 - 固件 CONFIG 500k, PCAN 各波特率发帧, 检测固件 RECV"""
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

# OPEN normal + CONFIG 500k
send(0x11, b''); recv_any(0.5)
send(0x10, bytes([0x00])); recv_any(1.0)
send(0x12, bytes([0x06, 0x03, 32, 0])); recv_any(1.0)
t.flush_input()

bauds = [('100k', PcanBaudrate.PCAN_BD_100K),
         ('125k', PcanBaudrate.PCAN_BD_125K),
         ('250k', PcanBaudrate.PCAN_BD_250K),
         ('500k', PcanBaudrate.PCAN_BD_500K),
         ('800k', PcanBaudrate.PCAN_BD_800K),
         ('1M', PcanBaudrate.PCAN_BD_1M)]

for name, bd in bauds:
    ch = PcanChannel(channel=PcanHandle.PCAN_USBBUS1, baudrate=bd)
    if ch.initialize() != PcanStatus.PCAN_ERROR_OK:
        print(f'{name}: PCAN init fail'); continue
    ch.read_all(timeout_ms=50)
    t.flush_input()
    ch.write(PcanMessage(id=0x123, data=b'\xAA\xBB\xCC'))
    time.sleep(0.3)
    f = recv_any(0.5)
    if f and f.cmd_code == 0x14:
        print(f'{name}: ✅ FIRMWARE RECEIVED! {f.payload.hex()}')
    else:
        got = hex(f.cmd_code) if f else 'none'
        print(f'{name}: ❌ no RECV (got {got})')
    ch.uninitialize()

t.close()
