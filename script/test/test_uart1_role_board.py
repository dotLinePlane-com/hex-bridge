"""Real-board UART1 control/business acceptance, with Profile restoration.

Run with exclusive port access, provisioned Wi-Fi and an already reachable TCP
management endpoint. Credentials are never read, changed or restored here.
Example: python script/test/test_uart1_role_board.py --ip 192.168.1.20 --port COM3
--baseline may name an existing v4 export; it must match the initial active map.
An optional --uart2-port additionally verifies UART2 physically in both directions.
No hardware is accessed by importing this module or by --help.
"""

import argparse
from copy import deepcopy
from pathlib import Path
import struct
import tempfile
import time

import serial
from test_profile_board import Board, DifferentBoard
import hexbridge_profile as cli

OPEN, CLOSE, CONFIG, SEND, RECV, STATUS, FLUSH = (
    0xA0,
    0xA1,
    0xA2,
    0xA3,
    0xA4,
    0xA6,
    0xA7,
)
UART2, UART1 = 1, 2


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def apply_once(board, candidate):
    try:
        board.run("apply", candidate)
    except cli.ApplyOutcomeUnknown:
        print(
            f"APPLY acknowledgement unknown for candidate {candidate}; reconnecting without retry",
            flush=True,
        )


class UARTSession:
    def __init__(self, transport):
        self.transport = transport
        self.seq = 100

    def request(self, cmd, channel, payload=b"", allowed=(0,)):
        self.seq += 1
        self.transport.send(
            cli.UBCPBuilder.build_request(self.seq, cmd, channel, payload)
        )
        frame = self.transport.recv_response(cmd, self.seq, timeout=4)
        require(
            frame is not None and frame.is_response and not frame.is_event,
            "Missing UART response",
        )
        require(
            frame.channel_id == channel, "UART response returned on the wrong channel"
        )
        require(
            frame.payload and frame.payload[0] in allowed,
            f"UART cmd={cmd:#x} ch={channel} response={frame.payload.hex()}",
        )
        return frame.payload

    def configure(self, channel, baud):
        response = self.request(
            CONFIG, channel, struct.pack(">IBBBBHB", baud, 8, 1, 0, 0, 1, 0)
        )
        require(len(response) == 5, "CONFIG response length mismatch")
        actual = int.from_bytes(response[1:5], "big")
        require(
            abs(actual - baud) <= max(1, baud // 100),
            f"CONFIG actual baud mismatch: {actual} vs {baud}",
        )

    def status(self, channel, baud):
        response = self.request(STATUS, channel)
        require(
            len(response) == 19 and int.from_bytes(response[1:5], "big") == baud,
            "STATUS baud mismatch",
        )
        return response

    def exchange(self, channel, raw, tag):
        """Compare physical TX and RX bytes; management frames travel only over TCP."""
        self.request(FLUSH, channel, b"\x02")
        raw.reset_input_buffer()
        outgoing = b"\x00\xffESP-to-PC:" + tag + b"\x55\xaa"
        result = self.request(
            SEND, channel, struct.pack(">H", len(outgoing)) + outgoing
        )
        require(
            len(result) == 3 and int.from_bytes(result[1:3], "big") == len(outgoing),
            "SEND byte count mismatch",
        )
        deadline = time.monotonic() + 3
        received = bytearray()
        while len(received) < len(outgoing) and time.monotonic() < deadline:
            received.extend(raw.read(len(outgoing) - len(received)))
        require(
            bytes(received) == outgoing,
            f"Physical UART TX mismatch: {bytes(received)!r}",
        )
        # A complete valid PING is ordinary business RX data, never a control command.
        incoming = (
            cli.UBCPBuilder.build_request(0xCAFE, 0x00, 0, b"")
            + b"PC-to-ESP:"
            + tag
            + b"\xff\x55"
        )
        raw.write(incoming)
        raw.flush()
        deadline = time.monotonic() + 4
        reported = bytearray()
        while len(reported) < len(incoming) and time.monotonic() < deadline:
            frame = self.transport.recv_event(RECV, timeout=0.5)
            if frame is None:
                continue
            require(
                frame.channel_id == channel,
                f"RX event crossed UART channel {frame.channel_id}",
            )
            payload = frame.payload
            require(
                len(payload) >= 3 and payload[0] == 0, "UART RX flags/length invalid"
            )
            size = int.from_bytes(payload[1:3], "big")
            require(len(payload) == 3 + size, "UART RX declared length mismatch")
            reported.extend(payload[3:])
        require(
            bytes(reported) == incoming,
            f"Physical UART RX mismatch: {bytes(reported)!r}",
        )
        print(
            f"PASS physical bidirectional channel={channel} tag={tag.decode()}",
            flush=True,
        )


def open_raw(port, baud):
    return serial.Serial(port, baudrate=baud, timeout=0.1, write_timeout=3)


def exercise_runtime(board, args, uart2_enabled=True):
    # Keep one TCP management session for OPEN/configuration and all RX events.
    with board.transport() as transport, open_raw(args.port, args.uart1_baud) as raw:
        session = UARTSession(transport)
        session.request(CLOSE, UART1, allowed=(0, 5))
        session.request(OPEN, UART1, b"\x00")
        session.configure(UART1, args.uart1_baud)
        session.status(UART1, args.uart1_baud)
        session.exchange(UART1, raw, b"UART1-baseline")
        if uart2_enabled:
            session.request(CLOSE, UART2, allowed=(0, 5))
            session.request(OPEN, UART2, b"\x00")
            for baud in (args.uart2_baud, 9600):
                session.configure(UART2, baud)
                session.status(UART2, baud)
                session.status(UART1, args.uart1_baud)
                raw.reset_input_buffer()
                token = b"UART2-must-not-appear-on-UART1"
                session.request(SEND, UART2, struct.pack(">H", len(token)) + token)
                require(
                    raw.read(1) == b"",
                    "UART2 TX leaked onto the physical UART1 connector",
                )
                if args.uart2_port:
                    with open_raw(args.uart2_port, baud) as raw2:
                        session.exchange(UART2, raw2, f"UART2-{baud}".encode())
                session.exchange(UART1, raw, f"UART2-configured-{baud}".encode())
            session.request(CLOSE, UART2)
            session.request(STATUS, UART2, allowed=(5,))
            session.status(UART1, args.uart1_baud)
            session.exchange(UART1, raw, b"UART2-CLOSE")
            print(
                "PASS UART2 independent baud/config/CLOSE; UART1 remains operational",
                flush=True,
            )
        else:
            rejected = session.request(OPEN, UART2, b"\x00", allowed=(0x0C,))
            print(
                f"PASS Profile-disabled UART2 OPEN rejected status=0x{rejected[0]:02x}",
                flush=True,
            )
            session.exchange(UART1, raw, b"UART2-profile-disabled")
        session.request(CLOSE, UART1)


def restore(serial_board, tcp_board, path, baseline):
    """Restore over a live management route; never confirm an unverified trial."""
    deadline = time.monotonic() + 165
    current = source = None
    while time.monotonic() < deadline:
        for board in (tcp_board, serial_board):
            try:
                current = board.snapshot()
                source = board
                break
            except DifferentBoard:
                raise
            except (OSError, ValueError):
                continue
        if current is not None and current["phase"] != "armed":
            break
        time.sleep(1)
    require(current is not None, "Restoration cannot reconnect to the original board")
    if current["phase"] == "staged":
        source.run("cancel", current["candidate_id"])
        current = source.snapshot()
    if current["phase"] == "trial":
        # Original confirmed mapping remains protected by the device watchdog.
        # A failed physical test never earns a permanent confirmation.
        deadline = time.monotonic() + 155
        while time.monotonic() < deadline:
            time.sleep(1)
            for board in (serial_board, tcp_board):
                try:
                    current = board.snapshot()
                    source = board
                    if current["phase"] == "confirmed":
                        break
                except DifferentBoard:
                    raise
                except (OSError, ValueError):
                    continue
            if current["phase"] == "confirmed":
                break
        require(
            current["phase"] == "confirmed",
            "Trial did not roll back during restoration",
        )
    if current["active"] != baseline:
        candidate = source.save(path, baseline)
        apply_once(source, candidate)
        target = (
            tcp_board
            if baseline["uart1_business"] or not baseline["features"]["serial"]
            else serial_board
        )
        trial = target.wait("trial", 45)
        require(
            trial["active"] == baseline,
            "Restoration trial differs from captured baseline",
        )
        target.confirm(candidate, baseline)
    # Re-read the restored serial management path and its exact mapping.
    final = serial_board.wait("confirmed", 45)
    require(
        final["active"] == baseline and not final["candidate_id"],
        "Profile restoration read-back failed",
    )
    print(
        f'RESTORED identity={serial_board.identity} revision={final["revision"]} UART1 control role',
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ip", required=True, help="Already provisioned device IPv4 address"
    )
    parser.add_argument("--tcp-port", type=int, default=9500)
    parser.add_argument(
        "--port", default="COM3", help="UART1 management/business physical adapter"
    )
    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Initial/restored UART1 management baud",
    )
    parser.add_argument("--uart1-baud", type=int, default=115200)
    parser.add_argument("--uart2-baud", type=int, default=57600)
    parser.add_argument(
        "--uart2-port", help="Optional physical UART2 adapter, distinct from --port"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Existing v4 export matching the initial active mapping",
    )
    parser.add_argument("--expect-identity", help="Expected GET_INFO identity hex")
    args = parser.parse_args()
    if args.uart1_baud == args.uart2_baud:
        parser.error("UART1 and UART2 test baud rates must differ")
    if args.uart2_port and args.uart2_port.lower() == args.port.lower():
        parser.error("UART adapters must be distinct")
    serial_board = Board(args.port, args.baud, args.expect_identity, version=4)
    initial = serial_board.snapshot()
    baseline = deepcopy(initial["active"])
    require(
        initial["schema"] == 4
        and initial["phase"] == "confirmed"
        and not initial["candidate_id"],
        "Requires v4 firmware and a confirmed profile without a pending candidate",
    )
    require(
        baseline["features"]["serial"] and not baseline["uart1_business"],
        "Start with UART1 in management role",
    )
    require(
        baseline["features"]["wifi"] and baseline["features"]["control_tcp"],
        "Wi-Fi/TCP management must already be enabled",
    )
    if args.baseline:
        desc = {
            k: initial[k] for k in ("schema", "board", "capabilities", "gpio_policy")
        }
        document = cli.load_config(args.baseline, desc)
        require(
            {k: document[k] for k in baseline} == baseline,
            "Saved baseline does not match initial active mapping",
        )
    tcp_board = Board(
        f"socket://{args.ip}:{args.tcp_port}",
        args.baud,
        serial_board.identity,
        version=4,
    )
    require(
        tcp_board.snapshot()["active"] == baseline,
        "TCP endpoint does not match the UART1 board/profile",
    )
    print(
        f"PRECHECK identity={serial_board.identity} v4, baseline and TCP management verified",
        flush=True,
    )
    with tempfile.TemporaryDirectory(prefix="uart1-role-board-") as tmp:
        path = Path(tmp) / "candidate.json"
        try:
            business = deepcopy(baseline)
            business["uart1_business"] = True
            business["features"]["serial"] = False
            business["features"]["uart"] = True
            candidate = serial_board.save(path, business)
            apply_once(serial_board, candidate)
            trial = tcp_board.wait("trial", 45)
            require(
                trial["active"] == business, "UART1 business trial mapping mismatch"
            )
            exercise_runtime(tcp_board, args)
            tcp_board.confirm(candidate, business)
            print(
                "PASS UART1 business trial confirmed through TCP after physical verification",
                flush=True,
            )
            disabled = deepcopy(business)
            disabled["features"]["uart"] = False
            candidate = tcp_board.save(path, disabled)
            apply_once(tcp_board, candidate)
            trial = tcp_board.wait("trial", 45)
            require(
                trial["active"] == disabled, "UART2-disabled trial mapping mismatch"
            )
            exercise_runtime(tcp_board, args, uart2_enabled=False)
            tcp_board.confirm(candidate, disabled)
            print(
                "PASS disabling UART2 in Profile preserves physical UART1 business",
                flush=True,
            )
        finally:
            restore(serial_board, tcp_board, path, baseline)
    print(
        "PASS UART1 role acceptance; original Profile restored; credentials untouched",
        flush=True,
    )


if __name__ == "__main__":
    main()
