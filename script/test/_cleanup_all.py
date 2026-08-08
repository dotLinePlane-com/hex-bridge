import sys, struct, time
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

t = MCPTransport(port='COM4', baudrate=115200)
t.open()

# List all and close
s = 1
t.send(UBCPBuilder.build_request(s, 0x44, 0, b''))
f = t.recv_response(cmd_code=0x44, timeout=3.0)
if f:
    count = f.payload[1]
    print(f'Found {count} connections before cleanup')
    for i in range(count):
        offset = 2 + i * 10
        ct = f.payload[offset]
        h = struct.unpack('>H', f.payload[offset+1:offset+3])[0]
        types = {0:'TCP_SRV', 1:'TCP_CONN', 2:'UDP_SRV', 3:'UDP_CLI', 4:'WS_SRV', 5:'WS_CLI'}
        tname = types.get(ct, 'UNK')
        print(f'  Closing {tname} 0x{h:04X}')
        try:
            if ct == 0:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x57, 0, struct.pack('>HBB', h, 1, 1)))
                t.recv_frame(timeout=1.0)
            elif ct == 1:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x57, 0, struct.pack('>HBB', h, 0, 1)))
                t.recv_frame(timeout=1.0)
            elif ct == 2:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x61, 0, struct.pack('>H', h)))
                t.recv_frame(timeout=1.0)
            elif ct == 3:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x63, 0, struct.pack('>H', h)))
                t.recv_frame(timeout=1.0)
            elif ct == 4:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x71, 0, struct.pack('>HB', h, 1)))
                t.recv_frame(timeout=1.0)
            elif ct == 5:
                s += 1; t.send(UBCPBuilder.build_request(s, 0x73, 0, struct.pack('>HH', h, 1000)))
                t.recv_frame(timeout=1.0)
        except Exception as e:
            print(f'    Error: {e}')

# Verify empty
t.flush_input()
time.sleep(0.5)
s += 1; t.send(UBCPBuilder.build_request(s, 0x44, 0, b''))
f2 = t.recv_response(cmd_code=0x44, timeout=3.0)
if f2:
    print(f'After cleanup: {f2.payload[1]} connection(s)')
else:
    print('After cleanup: no response')

t.close()
