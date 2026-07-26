import time
import sys
sys.path.insert(0, '.')
from ubcp_client import UBCPBuilder
from mcp_transport import MCPTransport

CMD_WS_CLIENT_CONN = 0x72
ERR_PARAM          = 0x02

def hexstr(data):
    return ' '.join(f'{b:02X}' for b in data)

def decode_status(payload):
    if len(payload) == 0:
        return "ERROR: empty payload"
    status = payload[0]
    names = {
        0x00: "ERR_SUCCESS",
        0x01: "ERR_UNKNOWN",
        0x02: "ERR_PARAM",
        0x03: "ERR_TIMEOUT",
        0x04: "ERR_BUSY",
        0x05: "ERR_NOT_OPEN",
        0x06: "ERR_NOT_SUPPORT",
        0x40: "ERR_NET_DISCONNECTED",
        0x41: "ERR_NET_CONN_REFUSED",
        0x42: "ERR_NET_TIMEOUT",
        0x43: "ERR_NET_HANDLE_INVALID",
        0x44: "ERR_NET_BUFFER_FULL",
        0x45: "ERR_NET_PORT_IN_USE",
        0x46: "ERR_NET_DNS_FAIL",
        0x47: "ERR_NET_NO_IP",
        0x48: "ERR_NET_MAX_CONN",
        0x49: "ERR_NET_WS_HANDSHAKE",
        0x4A: "ERR_NET_WS_PROTOCOL",
    }
    name = names.get(status, f"UNKNOWN(0x{status:02X})")
    return f"0x{status:02X} ({name})"

def main():
    transport = MCPTransport(port='COM35', baudrate=115200)
    transport.open()
    print("=== COM35 opened at 115200 bps ===\n")

    # ── Test 1: Malformed short payload (3 bytes, < required 7) ──
    print("── Test 1: Malformed WS_CLIENT_CONNECT (3-byte payload) ──")
    malformed_payload = b'\x01\x02\x03'
    wire1 = UBCPBuilder.build_request(
        seq_num=1, cmd_code=CMD_WS_CLIENT_CONN,
        channel_id=0, payload=malformed_payload)
    print(f"  Sent ({len(wire1)} bytes): {hexstr(wire1)}")
    print(f"  Payload: {hexstr(malformed_payload)}")

    transport.send(wire1)
    frame1 = transport.recv_frame(timeout=3.0)

    if frame1 is None:
        print("  Result: *** NO RESPONSE (timeout) ***\n")
    else:
        print(f"  Recv: {hexstr(frame1.payload)}")
        print(f"  Status byte: {decode_status(frame1.payload)}")
        print(f"  Frame: {frame1}\n")

    # ── Drain any stale data between tests ──
    transport.flush_input()
    time.sleep(0.2)

    # ── Test 2: Proper WS_CLIENT_CONNECT ──
    print("── Test 2: Proper WS_CLIENT_CONNECT (192.168.1.4:9302, /ws) ──")
    ip_bytes    = b'\xC0\xA8\x01\x04'       # 192.168.1.4 big-endian
    port_bytes  = (9302).to_bytes(2, 'big')  # 0x2456
    path_str    = b'/ws'
    path_len    = len(path_str).to_bytes(1, 'big')   # 0x03
    subproto_len = b'\x00'

    proper_payload = ip_bytes + port_bytes + path_len + path_str + subproto_len
    print(f"  Payload ({len(proper_payload)} bytes): {hexstr(proper_payload)}")
    print(f"    IP   : {'.'.join(str(b) for b in ip_bytes)}")
    print(f"    Port : 9302 (0x{9302:04X})")
    print(f"    Path : \"/ws\" (len=3)")
    print(f"    SubProto : (none, len=0)")

    wire2 = UBCPBuilder.build_request(
        seq_num=2, cmd_code=CMD_WS_CLIENT_CONN,
        channel_id=0, payload=proper_payload)
    print(f"  Sent ({len(wire2)} bytes): {hexstr(wire2)}")

    transport.send(wire2)
    print("  Waiting up to 15s for response...")
    frame2 = transport.recv_frame(timeout=15.0)

    if frame2 is None:
        print("  Result: *** NO RESPONSE (15s timeout) ***")
    else:
        print(f"  Recv payload ({frame2.payload_len} bytes): {hexstr(frame2.payload)}")
        print(f"  Status byte: {decode_status(frame2.payload)}")
        print(f"  Frame: {frame2}")

    transport.close()
    print("\n=== Done ===")

if __name__ == '__main__':
    main()
