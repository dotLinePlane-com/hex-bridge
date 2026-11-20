"""Hardware TCP checks (no target writes): python script/test/test_dap_tcp.py --host IP.

Tests DAP_Info only. Wi-Fi outage/recovery and UBCP/CAN/UART activity must be
coordinated externally; --ubcp checks concurrent TCP9500 PING responses.
"""
import argparse
import concurrent.futures
import socket
import struct
import time


def frame(payload):
    return b"DAP\0" + struct.pack("<HBB", len(payload), 1, 0) + payload


def exact(sock, count):
    data = bytearray()
    while len(data) < count:
        block = sock.recv(count - len(data))
        if not block:
            raise EOFError("unexpected DAP disconnect")
        data.extend(block)
    return bytes(data)


def response(sock):
    header = exact(sock, 8)
    size, kind, reserved = struct.unpack("<HBB", header[4:])
    assert header[:4] == b"DAP\0" and kind == 2 and reserved == 0
    assert 1 <= size <= 1024
    return exact(sock, size)


def closed(sock):
    try:
        assert sock.recv(1) == b"", "expected disconnect"
    except ConnectionResetError:
        pass


def run(host, port):
    connect = lambda: socket.create_connection((host, port), timeout=3)
    request = frame(b"\x00\xff")
    with connect() as active:
        for byte in request:
            active.sendall(bytes([byte]))
        packet_size = response(active)
        assert packet_size == b"\x00\x02\x00\x04", packet_size.hex()
        active.sendall(request * 10)
        for _ in range(10):
            assert response(active) == packet_size
        with connect() as busy:
            closed(busy)
        active.sendall(request)
        assert response(active) == packet_size
    time.sleep(.15)
    bad_headers = [b"BAD\0\x02\0\x01\0", b"DAP\0\0\0\x01\0",
                   b"DAP\0\x01\x04\x01\0", b"DAP\0\x02\0\x02\0",
                   b"DAP\0\x02\0\x01\x01"]
    for bad in bad_headers:
        with connect() as sock:
            sock.sendall(bad)
            closed(sock)
        time.sleep(.15)
    with connect() as partial:
        partial.sendall(request[:9])
    time.sleep(.15)
    with connect() as recovered:
        recovered.sendall(request)
        assert response(recovered) == packet_size
    print("DAP TCP framing, busy client, malformed rejection and disconnect/reconnect PASS")


def concurrent_ubcp(host, dap_port):
    from ubcp_client import UBCPBuilder, UBCPParser
    def ping_loop():
        parser = UBCPParser()
        with socket.create_connection((host, 9500), timeout=3) as sock:
            for seq in range(1, 31):
                sock.sendall(UBCPBuilder.build_request(seq, 0, 0, b""))
                deadline = time.monotonic() + 3
                matched = False
                while time.monotonic() < deadline and not matched:
                    block = sock.recv(2048)
                    assert block, "UBCP disconnected during concurrent DAP test"
                    for byte in block:
                        result = parser.feed(byte)
                        if result and result.is_response and not result.is_event and result.seq_num == seq:
                            assert result.cmd_code == 0 and len(result.payload) == 7 and result.payload[0] == 0
                            matched = True
                assert matched, f"UBCP PING timeout {seq}"
    def dap_loop():
        with socket.create_connection((host, dap_port), timeout=3) as sock:
            for _ in range(100):
                sock.sendall(frame(b"\x00\xff"))
                assert response(sock) == b"\x00\x02\x00\x04"
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(ping_loop), pool.submit(dap_loop)]
        for future in futures:
            future.result()
    print("Concurrent TCP9500 UBCP PING and TCP4441 DAP_Info PASS")


def link_cycle(host, port, timeout):
    """Observe an externally coordinated Wi-Fi outage, then verify fresh state."""
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=3) as old:
        # A lost wireless link can also lose FIN. Probe the idle connection
        # so that a peer which has discarded its socket can return a reset.
        old.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if hasattr(socket, "TCP_KEEPIDLE"):
            old.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 2)
            old.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
        elif hasattr(socket, "SIO_KEEPALIVE_VALS"):
            old.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 2000, 1000))
        old.settimeout(.5)
        old.sendall(frame(b"\x00\xff")[:9])
        print("Waiting for externally triggered Wi-Fi link loss...", flush=True)
        while time.monotonic() < deadline:
            try:
                assert old.recv(1) == b"", "unexpected response to partial request"
                break
            except (ConnectionResetError, ConnectionAbortedError):
                break
            except socket.timeout:
                pass
        else:
            raise TimeoutError("old DAP session did not close on Wi-Fi outage")
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1) as fresh:
                fresh.sendall(frame(b"\x00\xff"))
                assert response(fresh) == b"\x00\x02\x00\x04"
                print("Wi-Fi outage cleanup and listener restart PASS")
                return
        except OSError:
            time.sleep(.2)
    raise TimeoutError("DAP listener did not restart after Wi-Fi recovery")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=4441)
    parser.add_argument("--ubcp", action="store_true", help="exercise TCP9500 PING concurrently")
    parser.add_argument("--link-cycle-timeout", type=float, default=0,
                        help="seconds to wait for an externally triggered Wi-Fi loss and recovery")
    args = parser.parse_args()
    run(args.host, args.port)
    if args.ubcp:
        time.sleep(.15)
        concurrent_ubcp(args.host, args.port)
    if args.link_cycle_timeout:
        time.sleep(.15)
        link_cycle(args.host, args.port, args.link_cycle_timeout)
