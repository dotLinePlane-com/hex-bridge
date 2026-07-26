"""
Test HEX TCP Client connecting to a Python TCP echo server on PC.
"""
import sys, socket, threading, time, struct
sys.path.insert(0, r'script/test')
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from ipaddress import IPv4Address

def echo_server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 9198))
    srv.listen(1)
    srv.settimeout(8)
    try:
        conn, addr = srv.accept()
        print(f'PC server accepted: {addr}')
        data = conn.recv(1024)
        print(f'PC server received: {data}')
        conn.send(b'Reply from PC server')
        conn.close()
    except Exception as e:
        print(f'No connection accepted: {e}')
    print('Server done')
    srv.close()

t = threading.Thread(target=echo_server, daemon=True)
t.start()
time.sleep(0.5)

transport = MCPTransport('COM35', 115200)
transport.open()
transport.flush_input()
time.sleep(0.2)

# TCP_CLIENT_CONNECT
test_ip_bytes = struct.pack('>I', int(IPv4Address('192.168.1.4')))
test_ip_val = struct.unpack('>I', test_ip_bytes)[0]
payload = struct.pack('>IHBB', test_ip_val, 9198, 8, 0)
wire = UBCPBuilder.build_request(0x101, 0x52, 0, payload)
transport.send(wire)
f = transport.recv_frame(timeout=10.0)
if f:
    print(f'HEX response: status={f.payload[0]:#04x}')
    if f.payload[0] == 0x00 and len(f.payload) >= 9:
        ch = struct.unpack('>H', f.payload[1:3])[0]
        lip = f.payload[3:7]
        lp = struct.unpack('>H', f.payload[7:9])[0]
        print(f'  conn_handle={ch:#06x}')
        print(f'  local_ip={lip.hex()}')
        print(f'  local_port={lp}')
else:
    print('No response from HEX')

time.sleep(2)
transport.close()
