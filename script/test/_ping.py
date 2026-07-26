import sys
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

t = MCPTransport(port='COM35', baudrate=115200)
t.open()
t.send(UBCPBuilder.build_request(1, 0x00, 0, b''))
f = t.recv_response(cmd_code=0x00, timeout=5.0)
if f:
    import struct
    uptime = struct.unpack('>I', f.payload[1:5])[0]
    print(f'PING OK, uptime={uptime}us')
else:
    print('NO PING at 115200')
    # Try 921600
    t.close()
    t = MCPTransport(port='COM35', baudrate=921600)
    t.open()
    t.send(UBCPBuilder.build_request(1, 0x00, 0, b''))
    f = t.recv_response(cmd_code=0x00, timeout=5.0)
    if f:
        print('PING OK at 921600')
    else:
        print('NO PING at any baud')
t.close()
