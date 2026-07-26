import socket, threading, time, sys, struct
sys.path.insert(0, 'script/test')
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport
from ipaddress import IPv4Address

# Start server first
accepted_event = threading.Event()
result = [None]

def server():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', 9190))
    srv.listen(1)
    srv.settimeout(12)
    print('SERVER: listening on 0.0.0.0:9190')
    try:
        conn, addr = srv.accept()
        result[0] = f'ACCEPTED: {addr}'
        print(result[0])
        data = conn.recv(4096)
        print(f'SERVER: recv {len(data)} bytes')
        conn.send(b'HELLO from PC')
        conn.close()
    except socket.timeout:
        result[0] = 'TIMEOUT'
        print('SERVER: timeout')
    srv.close()

t = threading.Thread(target=server, daemon=True)
t.start()
time.sleep(0.5)

# Now HEX connect
transport = MCPTransport('COM35', 115200)
transport.open()
transport.flush_input()
time.sleep(0.2)

test_ip = struct.pack('>I', int(IPv4Address('192.168.1.4')))
test_ip_val = struct.unpack('>I', test_ip)[0]
payload = struct.pack('>IHBB', test_ip_val, 9190, 8, 0)
wire = UBCPBuilder.build_request(0x602, 0x52, 0, payload)
transport.send(wire)
f = transport.recv_frame(timeout=12.0)
if f:
    print(f'HEX: status={f.payload[0]:#04x} len={f.payload_len}')
    if f.payload[0] == 0 and len(f.payload) >= 9:
        ch = struct.unpack('>H', f.payload[1:3])[0]
        lip = f.payload[3:7]
        lp = struct.unpack('>H', f.payload[7:9])[0]
        print(f'HEX: handle={ch:#06x} local={lip.hex()} local_port={lp}')
elif result[0] is None:
    print('Waiting for server result...')
    t.join(5)
print(f'FINAL: server={result[0]}')

transport.close()
