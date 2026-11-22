"""HXB1 four-wire test: SPI3 master channel 4 to SPI2 slave channel 6.

Connect GPIO14-18, 13-19, 21-36 and 22-27 with the matching profile active.
Checks the active map before opening the master. Does not write the profile.
"""
import argparse
import struct
import time

from test_profile_board import Board, cli


def exercise(board):
    with board.transport() as transport:
        device = cli.Device(transport)
        device.descriptor(5)
        mapping = device.snapshot()["active"]
        for host, role, pins in (("3", "master", (14, 13, 36)), ("2", "slave", (18, 19, 21))):
            bus = mapping["spi"][host]
            if not (bus["enabled"] and bus["role"] == role and bus["width"] == 1
                    and tuple(bus[k] for k in ("sck", "mosi", "miso")) == pins):
                raise ValueError(f"SPI{host} mapping differs from the fixture")
        if (mapping["spi"]["2"]["slave_cs"] != 27 or mapping["features"]["can"]
                or mapping["external"] != {"enabled": True, "host": 3, "cs": 22}
                or mapping["external2"]["enabled"]):
            raise ValueError("Device or CS routing differs from the fixture")
        seq = 100

        def request(cmd, channel, payload=b"", allowed=(0,)):
            nonlocal seq
            seq += 1
            transport.send(cli.UBCPBuilder.build_request(seq, cmd, channel, payload))
            frame = transport.recv_response(cmd, seq, timeout=3)
            if not frame or not frame.is_response or frame.channel_id != channel:
                raise RuntimeError(f"Missing response for {cmd:#x} on channel {channel}")
            reply = bytes(frame.payload)
            if not reply or reply[0] not in allowed:
                raise RuntimeError(f"{cmd:#x} channel {channel} returned {reply.hex()}")
            return reply

        request(0x20, 4, bytes([22, 0]))
        try:
            for hz in (100_000, 1_000_000):
                request(0x22, 4, struct.pack(">BIBBBB", 0, hz, 0, 0, 0, 1))
                for n, capacity in ((2, 2), (1, 1), (3, 8), (64, 64)):
                    master = bytes((0x12 + i * 34) & 255 for i in range(n))
                    slave = bytes((0xa5 - i * 75) & 255 for i in range(capacity))
                    request(0x27, 6, bytes([capacity]) + slave)
                    request(0x28, 6, allowed=(4,))  # pending before external clock
                    miso = request(0x23, 4, struct.pack(">H", n) + master)
                    deadline = time.monotonic() + 2
                    while True:
                        mosi = request(0x28, 6, allowed=(0, 4))
                        if mosi[0] == 0 or time.monotonic() >= deadline:
                            break
                        time.sleep(.01)
                    if miso != struct.pack(">BH", 0, n) + slave[:n] or mosi != struct.pack(">BH", 0, 8*n) + master:
                        raise AssertionError(f"{hz} Hz N={n} MISO response={miso.hex()} MOSI response={mosi.hex()}")
                    request(0x28, 6, allowed=(5,))  # consumed exactly once
                    print(f"PASS {hz} Hz {8*n} bits, capacity={capacity}, "
                          f"master RX={miso[3:7].hex()} slave RX={mosi[3:7].hex()}", flush=True)
        finally:
            request(0x21, 4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()
    exercise(Board(args.port, args.baud, version=5))
