"""Explicit hardware SPI command smoke; no DUT data/electrical claims.

Run only after verifying wiring and active profile, e.g.:
python script/test/test_spi_smoke.py --mcp COM4 --cs 27 --max-width 1
Use --loopback only with verified MOSI/MISO loopback, CAN on a different host.
"""
import argparse
import struct
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mcp", required=True, help="Serial port or socket://IP:9500")
    p.add_argument("--baud", type=int, default=921600)
    p.add_argument("--cs", required=True, type=int, help="Active external CS GPIO")
    p.add_argument("--max-width", required=True, type=int, choices=(1, 4))
    p.add_argument("--loopback", action="store_true")
    args = p.parse_args()
    t = MCPTransport(args.mcp, args.baud)
    seq = 0

    def request(cmd, payload=b"", expected=0, size=1):
        nonlocal seq
        seq += 1
        t.send(UBCPBuilder.build_request(seq, cmd, 4, payload))
        frame = t.recv_response(cmd, seq, timeout=3)
        assert frame is not None, f"timeout CMD={cmd:02x}"
        assert frame.channel_id == 4 and len(frame.payload) == size, repr(frame)
        assert frame.payload[0] == expected, f"CMD={cmd:02x} status={frame.payload[0]:02x} expected={expected:02x}"
        return frame.payload

    t.open()
    opened = False
    try:
        request(0x20, bytes([args.cs, 0]))
        opened = True
        config = bytes([0]) + struct.pack(">I", 1000000) + bytes([0, 0, 0, 1])
        request(0x22, config)
        # Length zero must fail before starting a wire transaction.
        request(0x23, b"\0\0", expected=0x02)
        data = bytes([0x55, 0xAA, 0x00, 0xFF])
        reply = request(0x23, struct.pack(">H", len(data)) + data, size=3 + len(data))
        assert reply[1:3] == struct.pack(">H", len(data))
        if args.loopback:
            assert reply[3:] == data, "Verified loopback data mismatch"
        quad = config[:-1] + bytes([4])
        request(0x22, quad, expected=0x06 if args.max_width == 1 else 0)
        if args.max_width == 4:
            request(0x23, b"\0\1\xff", expected=0x06)
        request(0x22, config)
        request(0x21)
        opened = False
        print("SPI command/status/length/width smoke PASS; " +
              ("verified single-line loopback PASS" if args.loopback else
               "DUT contents and electrical timing remain unverified"))
    finally:
        if opened:
            try:
                request(0x21)
            except Exception:
                pass
        t.close()


if __name__ == "__main__":
    main()
