"""Real-board CLI profile acceptance on the default HXB1 wiring.

Reboots the board and waits for the real 120-second trial timeout. Run with
exclusive access to the management port. Optional tests retain physical wires:
--shared routes SPI2 through the original CAN pins; --wrong-host verifies that
selecting SPI2's original, unconnected pins for CAN causes driver rollback.
No Wi-Fi credentials are read. Each CLI connection checks GET_INFO identity.
"""
import argparse
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hexbridge_profile as cli


class DifferentBoard(RuntimeError):
    pass


class Board:
    def __init__(self, port, baud, identity=None, version=2):
        self.port, self.baud, self.identity = port, baud, identity
        self.version = version

    def transport(self, port=None, baud=None):
        board = self

        class GuardedTransport(cli.MCPTransport):
            def __enter__(self):
                super().__enter__()
                try:
                    self.send(cli.UBCPBuilder.build_request(0xFFFE, 1, 0, b""))
                    frame = self.recv_response(1, 0xFFFE, timeout=4)
                    if not frame or not frame.is_response or len(frame.payload) != 17 or frame.payload[0]:
                        raise ValueError("GET_INFO identity response missing or invalid")
                    identity = bytes(frame.payload[4:12]).hex()
                    if board.identity is None:
                        board.identity = identity
                    if identity != board.identity:
                        raise DifferentBoard("Hardware identity changed; refusing all profile actions/restoration")
                    return self
                except BaseException:
                    self.close()
                    raise

        return GuardedTransport(self.port, self.baud)

    def run(self, *args):
        output = io.StringIO()
        argv = ["hex-bridge-profile.py", "--port", self.port, "--baud", str(self.baud), "--version", str(self.version), *map(str, args)]
        # Execute the actual shared CLI, with its real parser/file/codec path.
        # The factory verifies identity on the same connection before requests.
        with patch.object(sys, "argv", argv), redirect_stdout(output):
            cli.main(transport_factory=self.transport)
        return output.getvalue().strip()

    def snapshot(self):
        return json.loads(self.run("show"))

    def reconnect(self, timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                return self.snapshot()
            except DifferentBoard:
                raise
            except (OSError, ValueError):
                time.sleep(1)
        raise TimeoutError("Could not reconnect to the original board for restoration")

    def wait(self, phase, timeout=25):
        phases = (phase,) if isinstance(phase, str) else phase
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                result = self.snapshot()
                if result["phase"] in phases:
                    return result
            except DifferentBoard:
                raise
            except (OSError, ValueError):
                pass  # reboot can temporarily remove the serial/TCP endpoint
            time.sleep(1)
        raise TimeoutError(f"Timed out waiting for {phase}")

    def topology(self):
        with self.transport() as transport:
            transport.send(cli.UBCPBuilder.build_request(0xFFFD, 7, 0, b""))
            frame = transport.recv_response(7, 0xFFFD, timeout=4)
            if not frame or not frame.is_response or len(frame.payload) < 2:
                raise ValueError("GET_TOPOLOGY response missing")
            data = frame.payload
            if data[0] or len(data) != 2 + 2 * data[1]:
                raise ValueError("GET_TOPOLOGY response invalid")
            return sorted(zip(data[2::2], data[3::2]))

    def save(self, path, mapping):
        self.run("export", path)  # refresh identity/descriptor/revision via CLI
        document = json.loads(path.read_text(encoding="utf-8"))
        document.update(deepcopy(mapping))
        path.write_text(json.dumps(document, indent=2), encoding="utf-8")
        assert self.run("check", path) == "OK"
        result = re.fullmatch(r"candidate_id = (\d+)", self.run("save", path))
        if not result:
            raise ValueError("SAVE returned an invalid candidate ID")
        return int(result[1])

    def apply(self, candidate):
        self.run("apply", candidate)
        return self.wait("trial")

    def confirm(self, candidate, mapping):
        self.run("confirm", candidate)
        result = self.snapshot()
        assert result["phase"] == "confirmed" and result["active"] == mapping
        assert not result["candidate_id"] and result["candidate"] is None
        return result

    def restore(self, path, baseline):
        current = self.reconnect()
        if current["phase"] == "armed":
            current = self.wait(("trial", "confirmed"))
        if current["phase"] == "staged":
            self.run("cancel", current["candidate_id"])
            current = self.snapshot()
        if current["phase"] == "trial":
            # Wait for real rollback; confirming an unexpected trial would
            # persist a test mapping that restoration has not verified.
            current = self.wait("confirmed", 155)
        if current["active"] != baseline:
            candidate = self.save(path, baseline)
            self.apply(candidate)
            current = self.confirm(candidate, baseline)
        assert current["phase"] == "confirmed" and current["active"] == baseline
        assert current["candidate"] is None and not current["candidate_id"]
        assert self.topology() == [(1, 1), (3, 2), (4, 3)]
        print(f"RESTORED identity={self.identity} revision={current['revision']}", flush=True)


def free(snapshot, table="occupancy"):
    return [r["gpio"] for r in snapshot["tables"][table] if r["state"] == "free"]


def default_mapping():
    return cli.migrate_v1({"features": dict.fromkeys(cli.FEATURES, True), "pins": {
        "uart.tx": 32, "uart.rx": 35, "can.sck": 14, "can.mosi": 13,
        "can.miso": 36, "can.cs": 15, "can.int": 39,
        "dap.swclk": 25, "dap.swdio": 26}})


def exercise(board, path, baseline, args):
    single = deepcopy(baseline)
    single["spi"]["2"]["width"] = 1
    candidate = board.save(path, single)
    staged = board.snapshot()
    assert staged["phase"] == "staged" and staged["active"] == baseline
    assert free(staged) == [] and free(staged, "candidate_occupancy") == [22, 23]
    board.run("cancel", candidate)
    assert board.snapshot()["candidate"] is None
    print("PASS CHECK/SAVE/staged occupancy/CANCEL", flush=True)

    candidate = board.save(path, single)
    trial = board.apply(candidate)
    assert trial["active"] == single and free(trial) == [22, 23]
    assert board.topology() == [(1, 1), (3, 2), (4, 3)]
    print("PASS single-line 13 occupied / 2 free; waiting for real watchdog", flush=True)
    rolled_back = board.wait("confirmed", 155)
    assert rolled_back["active"] == baseline and free(rolled_back) == []
    assert not rolled_back["candidate_id"] and rolled_back["candidate"] is None
    print("PASS real timeout rollback to Quad 15 occupied / 0 free", flush=True)

    disabled = deepcopy(baseline)
    disabled["spi"]["2"]["enabled"] = False
    disabled["external"]["enabled"] = False
    candidate = board.save(path, disabled)
    trial = board.apply(candidate)
    assert trial["active"] == disabled and free(trial) == [18, 19, 21, 22, 23, 27]
    assert board.topology() == [(1, 1), (3, 2)]
    board.confirm(candidate, disabled)
    print("PASS disabled SPI2 confirmed: 9 occupied / 6 free", flush=True)
    board.restore(path, baseline)

    if args.wrong_host:
        disconnected = deepcopy(baseline)
        disconnected["mcp2518fd"]["host"] = 2
        candidate = board.save(path, disconnected)
        board.run("apply", candidate)
        rolled_back = board.wait("confirmed", 45)
        assert rolled_back["active"] == baseline and not rolled_back["candidate_id"]
        print("PASS wrong-host chip probe caused driver rollback on unchanged wires", flush=True)

    if args.shared:
        shared = deepcopy(baseline)
        shared["spi"]["2"] = deepcopy(shared["spi"]["3"])
        shared["spi"]["3"]["enabled"] = False
        shared["mcp2518fd"]["host"] = 2
        candidate = board.save(path, shared)
        trial = board.apply(candidate)
        assert trial["active"] == shared
        assert board.topology() == [(1, 1), (3, 2), (4, 3)]
        board.confirm(candidate, shared)
        print("PASS shared SPI2 on original CAN wires: chip probe/profile/topology; SPI DUT/CAN traffic not tested", flush=True)
        board.restore(path, baseline)


def exercise_dual_spi(board, path, baseline, loopback):
    mapping = deepcopy(baseline)
    mapping["features"]["can"] = False
    mapping["external"]["cs"] = cli.NO_CS
    mapping["external2"].update(enabled=True, host=3, cs=27)
    candidate = board.save(path, mapping)
    trial = board.apply(candidate)
    assert trial["active"] == mapping
    assert board.topology() == [(1, 1), (4, 3), (5, 3)]
    print("PASS dual SPI trial, CAN off; topology reports both SPI channels", flush=True)
    with board.transport() as transport:
        sequence = 0

        def command(ch, cmd, data=b"", status=0):
            nonlocal sequence
            sequence += 1
            transport.send(cli.UBCPBuilder.build_request(sequence, cmd, ch, data))
            reply = transport.recv_response(cmd, sequence, timeout=3)
            assert reply and reply.is_response and reply.channel_id == ch, (ch, cmd, reply)
            assert reply.payload and reply.payload[0] == status, (ch, cmd, reply.payload)
            return reply.payload[1:]

        def transfer(ch, tx):
            size = struct.pack(">H", len(tx))
            reply = command(ch, 0x23, size + tx)
            assert reply[:2] == size and len(reply[2:]) == len(tx)
            if loopback:
                assert reply[2:] == tx, (ch, tx.hex(), reply[2:].hex())
            print(f"channel {ch} TX={tx.hex()} RX={reply[2:].hex()}", flush=True)

        command(4, 0x20, bytes([cli.NO_CS, 0]))
        command(5, 0x20, bytes([27, 0]))
        command(4, 0x22, struct.pack(">BIBBBB", 0, 500000, 0, 0, 0, 1))
        command(5, 0x22, struct.pack(">BIBBBB", 3, 1000000, 0, 0, 0, 1))
        command(4, 0x26, b"\x01", status=6)
        transfer(4, b"\x55\xaa")
        transfer(5, b"\x33\xcc")
        command(4, 0x21)
        transfer(5, b"\xa5\x5a")
        command(5, 0x21)
    print("PASS independent OPEN/CONFIG/TRANSFER/CLOSE; waiting for automatic rollback", flush=True)
    restored = board.wait("confirmed", 155)
    assert restored["active"] == baseline and restored["candidate"] is None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--expect-identity", help="Optional GET_INFO serial+model hex from an earlier run")
    parser.add_argument("--shared", action="store_true")
    parser.add_argument("--wrong-host", action="store_true")
    parser.add_argument("--dual-spi", action="store_true", help="Run only the v3 two-channel trial and rollback")
    parser.add_argument("--dual-loopback", action="store_true", help="Verify RX data with both MOSI/MISO loopbacks physically connected")
    args = parser.parse_args()
    if args.expect_identity:
        if not re.fullmatch(r"[0-9a-fA-F]{16}", args.expect_identity):
            parser.error("--expect-identity must contain 16 hex characters (serial+model)")
        args.expect_identity = args.expect_identity.lower()
    if args.dual_loopback and not args.dual_spi:
        parser.error("--dual-loopback requires --dual-spi")
    board = Board(args.port, args.baud, args.expect_identity, version=3 if args.dual_spi else 2)
    initial = board.snapshot()
    baseline = default_mapping()
    if args.dual_spi:
        baseline = cli.migrate_v2(baseline)
    assert initial["board"] == "HXB1" and initial["schema"] == board.version
    assert initial["phase"] == "confirmed" and initial["candidate"] is None and not initial["candidate_id"]
    assert initial["active"] == baseline and free(initial) == [], "Requires the complete default Quad profile"
    assert board.topology() == [(1, 1), (3, 2), (4, 3)], "Requires complete default topology"
    print(f"PRECHECK identity={board.identity} default Quad profile/topology and no candidate verified", flush=True)
    with tempfile.TemporaryDirectory(prefix="hex-profile-board-") as tmp:
        path = Path(tmp) / "candidate.json"
        try:
            if args.dual_spi:
                exercise_dual_spi(board, path, baseline, args.dual_loopback)
            else:
                exercise(board, path, baseline, args)
        finally:
            # Never restore a board that differs from the initial GET_INFO.
            # Preserve any original test exception while still making cleanup
            # failure visible to the operator and in the process exit status.
            board.restore(path, baseline)
    print("PASS board CLI acceptance; original mapping and topology read back", flush=True)


if __name__ == "__main__":
    main()
