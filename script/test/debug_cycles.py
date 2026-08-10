import sys, time, struct
sys.path.insert(0, 'script/test')
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

CMD_OPEN=0x10; CMD_CLOSE=0x11; CMD_CONFIG=0x12; CMD_STATUS=0x16
CH=3

t = MCPTransport(port='COM4', baudrate=115200)
t.open()
t.flush_input()

# Pre-clean
t.send(UBCPBuilder.build_request(1, CMD_CLOSE, CH, b''))
t.recv_frame(timeout=1)
t.flush_input()
print("Pre-clean done")

for i in range(3):
    s = 100 + i * 10
    t.send(UBCPBuilder.build_request(s, CMD_CLOSE, CH, b''))
    f = t.recv_frame(timeout=5)
    print(f"CLOSE{1} seq={s}: {'ok' if f else 'TIMEOUT'}")
    t.flush_input()
    s += 1

    t.send(UBCPBuilder.build_request(s, CMD_OPEN, CH, bytes([0x00])))
    f = t.recv_response(seq_num=s, timeout=10)
    if f is None:
        print(f"OPEN seq={s}: TIMEOUT!")
        break
    print(f"OPEN seq={s}: status=0x{f.payload[0]:02x}")
    s += 1

    t.send(UBCPBuilder.build_request(s, CMD_CONFIG, CH,
        struct.pack('>BBBB', 0x06, 0x03, 0x20, 0x00)))
    f = t.recv_response(seq_num=s, timeout=10)
    if f is None:
        print(f"CONFIG seq={s}: TIMEOUT!")
        break
    print(f"CONFIG seq={s}: status=0x{f.payload[0]:02x}")
    s += 1

    t.send(UBCPBuilder.build_request(s, CMD_STATUS, CH, b''))
    f = t.recv_response(seq_num=s, timeout=5)
    if f is None:
        print(f"STATUS seq={s}: TIMEOUT!")
        break
    print(f"STATUS: bs={f.payload[1]} TEC={f.payload[2]} REC={f.payload[3]}")
    s += 1

    t.send(UBCPBuilder.build_request(s, CMD_CLOSE, CH, b''))
    f = t.recv_frame(timeout=5)
    print(f"CLOSE2 seq={s}: {'ok' if f else 'TIMEOUT'}")
    t.flush_input()

print(f"\nCycle {i+1} done")

t.close()
print("Done")
