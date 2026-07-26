import sys, time, struct
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport

t = MCPTransport(port='COM35', baudrate=115200)
t.open()
# DO NOT flush - events might already be buffered
print('Checking for TCP_RECV event (3s)...')
evt = t.recv_event(cmd_code=0x55, timeout=3.0)
if evt:
    h = struct.unpack('>H', evt.payload[0:2])[0]
    dl = struct.unpack('>H', evt.payload[2:4])[0]
    data = evt.payload[4:4+dl]
    print(f'GOT RECV: Handle=0x{h:04X}, DataLen={dl}, Data={data}')
    # Check if this is our connection
    if h in (0x9000, 0x9001):
        print('NM-TCP-01 RECV: PASS')
    else:
        print(f'NM-TCP-01 RECV: unexpected handle 0x{h:04X}')
else:
    print('NM-TCP-01 RECV: No event received')
t.close()
