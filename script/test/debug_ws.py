"""
Debug script: raw UBCP v2.0 PING + WS_CLIENT_CONNECT test over COM4.

Tests direct serial communication with HEX-Bridge device at UBCP protocol level.

Usage:
    python debug_ws.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from ubcp_client import UBCPBuilder, UBCPParser, Frame
from mcp_transport import MCPTransport

ERROR_MAP = {
    0x00: "SUCCESS",
    0x01: "ERR_UNKNOWN",
    0x02: "ERR_PARAM",
    0x03: "ERR_TIMEOUT",
    0x04: "ERR_BUSY",
    0x05: "ERR_NOT_OPEN",
    0x06: "ERR_NOT_SUPPORT",
    0x07: "ERR_BUFFER_FULL",
    0x08: "ERR_CRC",
    0x09: "ERR_FRAME",
    0x0A: "ERR_CHANNEL_INVALID",
    0x0B: "ERR_ALREADY_OPEN",
    0x0C: "ERR_PERMISSION",
    0x0D: "ERR_OVERFLOW",
    0x0E: "ERR_SEQ_MISMATCH",
    0x0F: "ERR_VERSION",
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


def decode_error(payload):
    if not payload:
        return "<empty>"
    code = payload[0]
    name = ERROR_MAP.get(code, f"UNKNOWN_0x{code:02X}")
    return f"0x{code:02X} ({name})"


def hexdump(data, indent="    "):
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        lines.append(f"{indent}{hex_part}")
    return "\n".join(lines)


def main():
    print("=" * 60)
    print("  UBCP v2.0 Raw Frame Debug")
    print("  Target: COM4 @ 921600 bps")
    print("=" * 60)
    print()

    transport = MCPTransport(port="COM4", baudrate=921600)

    try:
        transport.open()
    except Exception as e:
        print(f"[FAIL] Cannot open COM4: {e}")
        return 1

    print("[1] COM4 opened at 921600 bps")
    transport.flush_input()
    time.sleep(0.2)

    # ─── STEP 1: PING ───────────────────────────────────────────
    print()
    print("-" * 40)
    print("[2] Sending PING (cmd=0x00)")
    print("-" * 40)

    ping_payload = b"\x00"
    ping_wire = UBCPBuilder.build_request(
        seq_num=1, cmd_code=0x00, channel_id=0, payload=ping_payload
    )
    print(f"  PING REQ wire ({len(ping_wire)} bytes):")
    print(hexdump(ping_wire))
    transport.send(ping_wire)

    ping_resp = transport.recv_response(cmd_code=0x00, seq_num=1, timeout=5.0)

    if ping_resp is None:
        print("  => PING: NO RESPONSE (5.0s timeout)")
        print()
        print("[FAIL] Device not responding on COM4 at 921600 bps.")
        print("       The serial-monitor-mcp IDE process likely holds COM4")
        print("       exclusively for its HEX-Bridge management channel.")
        print("       hex_bridge_discover() confirms device fw=0.1.0 is alive,")
        print("       but Python pyserial cannot share the port for reads.")
        transport.close()
        return 1

    print(f"  => PING RESPONSE frame: {ping_resp}")
    print(f"     flags=0x{ping_resp.flags:02X} DIR={ping_resp.is_response}"
          f" EVT={ping_resp.is_event}")
    print(f"     seq=0x{ping_resp.seq_num:04X} cmd=0x{ping_resp.cmd_code:02X}"
          f" ch={ping_resp.channel_id} plen={ping_resp.payload_len}")
    print(f"     payload ({ping_resp.payload_len} bytes):")
    print(hexdump(ping_resp.payload))

    status = ping_resp.payload[0] if ping_resp.payload_len >= 1 else None
    if status == 0x00:
        print("  => PING SUCCESS")
    else:
        print(f"  => PING status: {decode_error(ping_resp.payload)}")
        transport.close()
        return 1

    # ─── STEP 2: WS_CLIENT_CONNECT ──────────────────────────────
    print()
    print("-" * 40)
    print("[3] Sending WS_CLIENT_CONNECT (cmd=0x72)")
    print("-" * 40)

    ip_bytes = bytes([0xC0, 0xA8, 0x01, 0x04])
    port_bytes = (9302).to_bytes(2, "big")
    path = b"/ws"
    path_len = len(path).to_bytes(1, "big")
    subproto_len = b"\x00"

    ws_payload = ip_bytes + port_bytes + path_len + path + subproto_len
    print(f"  WS payload ({len(ws_payload)} bytes):")
    print(f"    IP       : 192.168.1.4 ({' '.join(f'{b:02X}' for b in ip_bytes)})")
    print(f"    Port     : 9302 (0x{9302:04X})")
    print(f"    Path     : /ws (len=3)")
    print(f"    SubProto : none (len=0)")
    print(f"    Raw      : {' '.join(f'{b:02X}' for b in ws_payload)}")

    ws_wire = UBCPBuilder.build_request(
        seq_num=2, cmd_code=0x72, channel_id=0, payload=ws_payload
    )
    print(f"  WS_CLIENT_CONNECT wire ({len(ws_wire)} bytes):")
    print(hexdump(ws_wire))
    transport.send(ws_wire)

    print("  Waiting up to 15s for response...")
    ws_resp = transport.recv_response(cmd_code=0x72, seq_num=2, timeout=15.0)

    if ws_resp is None:
        print("  => WS_CLIENT_CONNECT: NO RESPONSE (15.0s timeout)")
        transport.close()
        return 1

    print(f"  => WS_CLIENT_CONNECT RESPONSE frame: {ws_resp}")
    print(f"     flags=0x{ws_resp.flags:02X} DIR={ws_resp.is_response}"
          f" EVT={ws_resp.is_event}")
    print(f"     seq=0x{ws_resp.seq_num:04X} cmd=0x{ws_resp.cmd_code:02X}"
          f" ch={ws_resp.channel_id} plen={ws_resp.payload_len}")
    print(f"     payload ({ws_resp.payload_len} bytes):")
    print(hexdump(ws_resp.payload))
    print(f"     decoded status: {decode_error(ws_resp.payload)}")

    if len(ws_resp.payload) >= 1:
        status = ws_resp.payload[0]
        if status == 0x00:
            print("  => WS_CLIENT_CONNECT: SUCCESS")
            if len(ws_resp.payload) >= 5:
                conn_handle = (ws_resp.payload[1] << 24) | (ws_resp.payload[2] << 16) | \
                              (ws_resp.payload[3] << 8) | ws_resp.payload[4]
                print(f"  => Connection handle: 0x{conn_handle:08X}")
            if len(ws_resp.payload) >= 7:
                server_handle = (ws_resp.payload[5] << 8) | ws_resp.payload[6]
                print(f"  => Server handle: 0x{server_handle:04X}")
        else:
            print(f"  => WS_CLIENT_CONNECT FAILED: {decode_error(ws_resp.payload)}")

    transport.close()
    print()
    print("=" * 60)
    print("  Done")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
