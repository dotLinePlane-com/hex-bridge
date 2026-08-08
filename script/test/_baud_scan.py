import sys
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

for b in [115200, 921600, 460800, 230400, 57600, 9600]:
    t = MCPTransport(port='COM4', baudrate=b)
    t.open()
    t.send(UBCPBuilder.build_request(1, 0x00, 0, b''))
    f = t.recv_response(cmd_code=0x00, timeout=1.5)
    print(f'BAUD {b}: {"OK" if f else "NO"}')
    t.close()
