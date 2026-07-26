import sys, struct, time
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport

t = MCPTransport(port='COM35', baudrate=115200)
t.open()
t.flush_input()
# Don't close - just wait for any event
print('Waiting for ANY event on COM35 (5s)...')
evt = t.recv_event(timeout=5.0)
if evt:
    print(f'EVENT: cmd=0x{evt.cmd_code:02X} seq={evt.seq_num}')
    print(f'  payload ({len(evt.payload)} bytes): {evt.payload.hex()}')
    if evt.cmd_code == 0x56:  # TCP_ACCEPT
        sh = struct.unpack('>H', evt.payload[0:2])[0]
        ch = struct.unpack('>H', evt.payload[2:4])[0]
        ip = '.'.join(str(b) for b in evt.payload[4:8])
        port = struct.unpack('>H', evt.payload[8:10])[0]
        print(f'  TCP_ACCEPT: Server=0x{sh:04X} Client=0x{ch:04X} from {ip}:{port}')
    elif evt.cmd_code == 0x55:  # TCP_RECV
        ch = struct.unpack('>H', evt.payload[0:2])[0]
        dl = struct.unpack('>H', evt.payload[2:4])[0]
        data = bytes(evt.payload[4:4+dl])
        print(f'  TCP_RECV: ConnHandle=0x{ch:04X} DataLen={dl} Data={data}')
else:
    print('No events received')
t.close()
