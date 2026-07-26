import socket, threading, time, sys
sys.path.insert(0, 'script/test')
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
import struct

def test_server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 9190))
    srv.listen(1)
    srv.settimeout(15)
    print('Python server listening on 0.0.0.0:9190')
    try:
        conn, addr = srv.accept()
        print(f'ACCEPTED: {addr}')
        data = conn.recv(4096)
        print(f'RECV: {data[:200]}')
        conn.send(b'OK from Python server')
        conn.close()
    except socket.timeout:
        print('TIMEOUT: no connection received')
    srv.close()

t = threading.Thread(target=test_server, daemon=True)
t.start()
time.sleep(0.5)

transport = MCPTransport('COM35', 115200)
transport.open()
transport.flush_input()
time.sleep(0.2)

# TCP_CLIENT_CONNECT to 192.168.1.4:9190
from ipaddress import IPv4Address
test_ip = struct.pack('>I', int(IPv4Address('192.168.1.4')))
test_ip_val = struct.unpack('>I', test_ip)[0]
payload = struct.pack('>IHBB', test_ip_val, 9190, 8, 0)
wire = UBCPBuilder.build_request(0x601, 0x52, 0, payload)
transport.send(wire)
f = transport.recv_frame(timeout=12.0)
if f:
    print(f'HEX: status={f.payload[0]:#04x}')
    if f.payload[0] == 0 and len(f.payload) >= 9:
        ch = struct.unpack('>H', f.payload[1:3])[0]
        print(f'  handle={ch:#06x}, local_ip={f.payload[3:7].hex()}, local_port={struct.unpack(">H", f.payload[7:9])[0]}')
else:
    print('HEX: no response')

time.sleep(2)
transport.close()
