"""Pure host regression: no serial imports, port opens, DLLs or real devices.

    python -B script/test/test_diag_can_switch_min_host.py
"""

import contextlib
import io
import json
import struct
import tempfile
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import diag_can_switch_min as d
from ubcp_client import UBCPParser

# Load the actual repository decoder with an inert serial module. This prevents
# even a pyserial import while executing the unchanged repository parser code.
with patch.dict(sys.modules, {"serial": SimpleNamespace()}):
    spec = importlib.util.spec_from_file_location("host_repository_slcan", Path(__file__).with_name("canable_slcan.py"))
    repository = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(repository)


def decode(raw):
    return repository.CanableChannel._decode_frame(None, raw)


def event(ident=0x622, data=b"12345678", rxflags=0):
    return SimpleNamespace(is_event=True, cmd_code=0x14, channel_id=3,
                           payload=struct.pack(">IB", ident, len(data)) + data
                           + bytes([rxflags]) + b"\0" * 4)


class Bench:
    """Local wire simulation, intentionally unrelated to pyserial."""
    def __init__(self, fail_cmd=None, corruption=None, open_failure=None,
                 cleanup_failure=False):
        self.now = 0
        self.calls = []
        self.commands = []
        self.serial_rx = bytearray()
        self.events = []
        self.fail_cmd = fail_cmd
        self.corruption = corruption
        self.open_failure = open_failure
        self.cleanup_failure = cleanup_failure
        self.last = None
        self.mcp = self.Mcp(self)
        self.peer = self.Peer(self)

    def factory(self, args):
        return self.mcp, self.peer

    def clock(self):
        return self.now

    class Mcp:
        def __init__(self, b):
            self.b = b

        def open(self):
            self.b.calls.append("mcp.open")
            if self.b.open_failure == "mcp":
                raise IOError("open MCP")

        def close(self):
            self.b.calls.append("mcp.close")

        def send(self, raw):
            parser = UBCPParser()
            frames = [f for byte in raw if (f := parser.feed(byte)) is not None]
            if len(frames) != 1:
                raise AssertionError("bad request wire")
            f = frames[0]
            self.b.last = f
            self.b.commands.append((f.cmd_code, f.payload))
            if f.cmd_code == 0x13:
                ident, dlc = struct.unpack_from(">IB", f.payload)
                assert dlc == len(f.payload[5:]) and ident <= 0x7FF
                line = f"t{ident:03X}{dlc}{f.payload[5:].hex()}".encode()
                if self.b.corruption == "slcan":
                    line = b"T" + b"00000" + line[1:]
                self.b.serial_rx.extend(line + b"\r")

        def recv_response(self, cmd_code, seq_num, timeout):
            if cmd_code == self.b.fail_cmd:
                return None
            p = b"\0" * (28 if cmd_code == 0x16 else 1)
            return SimpleNamespace(is_response=True, is_event=False, cmd_code=cmd_code,
                                   seq_num=seq_num, channel_id=3, payload=p)

        def recv_event(self, cmd_code=None, timeout=0.05):
            if not self.b.events:
                return None
            return self.b.events.pop(0)

    class Peer:
        def __init__(self, b):
            self.b = b

        def open(self):
            self.b.calls.append("peer.open")
            if self.b.open_failure == "peer":
                raise IOError("open peer")

        def close(self):
            self.b.calls.append("peer.close")

        def write(self, raw):
            self.b.calls.append(raw)
            if self.b.cleanup_failure and raw == b"C\r":
                raise IOError("C failed")
            if raw.startswith(b"t"):
                ident = int(raw[1:4], 16)
                data = bytes.fromhex(raw[5:-1].decode())
                f = event(ident, data)
                if self.b.corruption == "self_echo":
                    forward = [p for cmd, p in self.b.commands if cmd == 0x13][-1]
                    f = event(struct.unpack_from(">I", forward)[0], forward[5:])
                if self.b.corruption == "ubcp":
                    f.payload = bytes([f.payload[0] | 0x40]) + f.payload[1:]
                self.b.events.append(f)
            # Fragmented command ACKs, E feedback and mixed frame/ACK data.
            self.b.serial_rx.extend(b"E00\r" if raw == b"E\r" else b"\r")
            return len(raw)

        def read(self, size):
            self.b.now += 0.001
            raw = bytes(self.b.serial_rx[:3])
            del self.b.serial_rx[:3]
            return raw


def args(**kw):
    values = dict(confirm_bench="original-bench", mode="switch", rounds=2, timeout=0.05,
                  feedback_window=0.02,
                  restore_rate=500000, mcp="FAKE_MCP", canable="FAKE_PEER")
    values.update(kw)
    return SimpleNamespace(**values)


class Regression(unittest.TestCase):
    def run_bench(self, bench, **kw):
        records = []
        with patch.object(d.time, "monotonic", bench.clock):
            code = d.execute(args(**kw), bench.factory,
                             lambda kind, **fields: records.append(dict(kind=kind, **fields)), decoder=decode)
        return code, records

    def test_switch_rounds_both_directions_and_restore(self):
        b = Bench()
        code, records = self.run_bench(b)
        self.assertEqual(code, 0)
        self.assertEqual([p[0] for cmd, p in b.commands if cmd == 0x12],
                         [6, 5, 6, 6, 5, 6, 6])
        self.assertEqual(len([r for r in records if r["kind"] == "phase_result"]), 6)
        verdicts = [r for r in records if r["kind"] == "verdict"]
        self.assertEqual(len(verdicts), 12)
        self.assertTrue(all(v["ok"] for v in verdicts))
        probes = [r for r in records if r["kind"] == "probe"]
        self.assertEqual([(p["id"], bytes.fromhex(p["data"])) for p in probes],
                         [pair for _ in range(2) for phase in range(3)
                          for pair in (d.PROBES[phase], d.REVERSE_PROBES[phase])])
        self.assertTrue(all(p[1][1] == 3 for p in b.commands if p[0] == 0x12))
        serial_commands = [c for c in b.calls if isinstance(c, bytes)]
        self.assertNotIn(b"E\r", serial_commands)
        self.assertEqual(serial_commands[:7], [b"C\r", b"S6\r", b"Y2\r", b"M0\r", b"A1\r", b"O\r", b"t61065248656c6c6f\r"])
        self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])
        cleanup = [r for r in records if r["kind"] == "cleanup"]
        self.assertEqual(len(cleanup), 6)
        self.assertTrue(all(r["ok"] for r in cleanup))
        kinds = {r["kind"] for r in records}
        self.assertTrue({"slcan_tx", "slcan_rx", "slcan_feedback_window",
                         "status", "ubcp_response", "ubcp_event"} <= kinds)
        self.assertEqual(b.commands[-1][0], 0x11)
        self.assertEqual([c for c in b.calls if isinstance(c, bytes)][-1], b"C\r")

    def test_direct250_has_no_baseline_probe(self):
        b = Bench()
        code, records = self.run_bench(b, mode="direct250")
        self.assertEqual(code, 0)
        self.assertEqual([r["rate"] for r in records if r["kind"] == "phase_result"],
                         [250000, 250000])
        self.assertEqual([p[0] for cmd, p in b.commands if cmd == 0x12], [5, 5, 6])

    def test_strict_slcan_rejections(self):
        d.strict_slcan(b"t12320102", 0x123, b"\1\2")
        d.strict_slcan(b"t0000", 0, b"")
        for raw in (b"T0000012320102", b"r1232", b"d12320102", b"b12320102",
                    b"t92320102", b"t12390102", b"t12310102", b"t123201",
                    b"t12320103", b"t12420102", b"t123201 02", b"t12320102FFFF"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                d.strict_slcan(raw, 0x123, b"\1\2")

    def test_strict_ubcp_rejections(self):
        d.strict_event(event(), 0x622, b"12345678")
        base = event().payload
        bad = [struct.pack(">I", 0x622 | flag) + base[4:]
               for flag in (0x80000000, 0x40000000, 0x20000000, 0x10000000, 0x800)]
        bad += [base[:4] + b"\7" + base[5:], base[:-1], base + b"\0",
                base[:5] + b"X" + base[6:], event(rxflags=8).payload]
        for p in bad:
            f = event()
            f.payload = p
            with self.subTest(p=p), self.assertRaises(ValueError):
                d.strict_event(f, 0x622, b"12345678")
        for attr, value in (("is_event", False), ("cmd_code", 0x13), ("channel_id", 2)):
            f = event()
            setattr(f, attr, value)
            with self.assertRaises(ValueError):
                d.strict_event(f, 0x622, b"12345678")

    def test_failed_config_gates_all_probes_and_still_closes(self):
        b = Bench(fail_cmd=0x12)
        code, records = self.run_bench(b)
        self.assertEqual(code, 1)
        self.assertFalse(any(cmd == 0x13 for cmd, _ in b.commands))
        self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])
        self.assertTrue(any(r["kind"] == "cleanup" and not r["ok"] for r in records))

    def test_wrong_frames_fail_and_capture_failure_status(self):
        for corruption in ("slcan", "ubcp"):
            b = Bench(corruption=corruption)
            code, records = self.run_bench(b)
            self.assertEqual(code, 1)
            self.assertTrue(any(r["kind"] == "verdict" and not r["ok"] for r in records))
            self.assertEqual(len([r for r in records if r["kind"] == "verdict"]), 12)
            self.assertEqual(len([r for r in records if r["kind"] == "phase_result"]), 6)
            self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])

    def test_partial_open_failure_closes_both_resources(self):
        for target in ("mcp", "peer"):
            b = Bench(open_failure=target)
            code, _ = self.run_bench(b)
            self.assertEqual(code, 1)
            self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])
            self.assertFalse(b.commands)

    def test_cleanup_failures_are_independent(self):
        b = Bench(cleanup_failure=True)
        code, records = self.run_bench(b)
        self.assertEqual(code, 1)
        self.assertEqual(len([r for r in records if r["kind"] == "cleanup"]), 6)
        self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])
        self.assertEqual(b.commands[-1][0], 0x11)

    def test_confirmation_precedes_factory(self):
        with self.assertRaises(ValueError):
            d.execute(args(confirm_bench=""), lambda _: self.fail("factory called"),
                      lambda *a, **kw: None)

    def test_cli_guards_before_hardware(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "evidence.jsonl")
            base = ["--mcp", "FAKE_MCP", "--canable", "FAKE_PEER", "--mode", "switch",
                    "--restore-rate", "500000", "--evidence", target]
            cases = [base, base + ["--confirm-bench", "YES"],
                     base + ["--confirm-bench", "original-bench", "--timeout", "nan"],
                     base + ["--confirm-bench", "original-bench", "--rounds", "0"],
                     base + ["--confirm-bench", "original-bench", "--canable", "fake_mcp"]]
            for argv in cases:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    d.main(argv, factory=lambda _: self.fail("hardware factory called"))
            Path(target).touch()
            with self.assertRaises(FileExistsError):
                d.main(base + ["--confirm-bench", "original-bench"],
                       factory=lambda _: self.fail("hardware factory called"))

    def test_feedback_bel_partial_and_timeout(self):
        for raw, error in ((b"\7", d.ControlError),):
            b = Bench()
            b.serial_rx.extend(raw)
            can = d.Slcan(b.peer, lambda *a, **kw: None, 0.05)
            with patch.object(d.time, "monotonic", b.clock), self.assertRaises(error):
                can.boundary()
        b = Bench()
        can = d.Slcan(b.peer, lambda *a, **kw: None, 0.05)
        with patch.object(d.time, "monotonic", b.clock), self.assertRaises(TimeoutError):
            can.receive(0x123, b"1")

    def test_background_skipped_and_repository_decoder_used(self):
        b = Bench()
        b.serial_rx.extend(b"t1111FF\rT000001112AA\rt600548656C6C6F\r")
        rows = []
        decoder_calls = []

        def checked_decoder(raw):
            decoder_calls.append(raw)
            return decode(raw)

        can = d.Slcan(b.peer, lambda kind, **kw: rows.append((kind, kw)), 0.1, checked_decoder)
        with patch.object(d.time, "monotonic", b.clock):
            can.receive(0x600, b"Hello")
        self.assertEqual(decoder_calls, [b"t600548656C6C6F"])
        self.assertEqual(len([r for r in rows if r[0] == "slcan_unrelated"]), 2)
        self.assertTrue(any(r[0] == "slcan_match_raw" for r in rows))
        self.assertTrue(any(r[0] == "slcan_match_decoded" for r in rows))
        b.events.extend([event(0x123), event(0x600, b"Hello")])
        diag = d.Diagnostic(b.mcp, can, lambda *a, **kw: None, 0.1)
        with patch.object(d.time, "monotonic", b.clock):
            diag.receive_event(0x600, b"Hello")

    def test_repository_decoder_disagreement_fails(self):
        b = Bench()
        b.serial_rx.extend(b"t600548656C6C6F\r")
        can = d.Slcan(b.peer, lambda *a, **kw: None, 0.1,
                      lambda _: repository.CanableMessage(0x600, b"Hello", is_rtr=True))
        with patch.object(d.time, "monotonic", b.clock), self.assertRaises(ValueError):
            can.receive(0x600, b"Hello")

    def test_rec_does_not_block_reverse_or_back_and_truthful_bench_labels(self):
        for bench_label in d.BENCHES:
            b = Bench()
            original = b.mcp.recv_response

            def unhealthy(**kw):
                f = original(**kw)
                if kw["cmd_code"] == 0x16:
                    f.payload = f.payload[:3] + b"\1" + f.payload[4:]
                return f

            b.mcp.recv_response = unhealthy
            code, rows = self.run_bench(b, confirm_bench=bench_label)
            self.assertEqual(code, 1)
            self.assertEqual(len([r for r in rows if r["kind"] == "verdict"]), 12)
            self.assertEqual(len([r for r in rows if r["kind"] == "status_error"]), 18)
            self.assertEqual(rows[-1]["bench"], bench_label)
            self.assertFalse(rows[-1]["minimum_switch_gate_pass"])
        for bench_label in d.BENCHES:
            code, rows = self.run_bench(Bench(), confirm_bench=bench_label)
            self.assertEqual(code, 0)
            self.assertFalse(rows[-1]["minimum_switch_gate_pass"])

    def test_minimum_switch_gate_matrix_and_failure_gates(self):
        for bench_label in d.BENCHES:
            for mode in ("direct250", "switch"):
                for rounds in (1, 2, 3, 4):
                    with self.subTest(bench=bench_label, mode=mode, rounds=rounds):
                        code, rows = self.run_bench(Bench(), confirm_bench=bench_label,
                                                    mode=mode, rounds=rounds)
                        self.assertEqual(code, 0)
                        result = rows[-1]
                        self.assertEqual(result["minimum_switch_gate_pass"],
                                         bench_label == "isolated-bench" and mode == "switch" and rounds >= 3)
                        self.assertNotIn("acceptance_pass", result)
                        self.assertFalse(result["full_suite_run"])
                        self.assertEqual(result["scope"], "minimum_switch_gate_only")
        for b in (Bench(corruption="ubcp"), Bench(fail_cmd=0x12), Bench(cleanup_failure=True)):
            code, rows = self.run_bench(b, confirm_bench="isolated-bench", rounds=3)
            self.assertEqual(code, 1)
            self.assertFalse(rows[-1]["minimum_switch_gate_pass"])

    def test_reverse_differs_and_forward_self_echo_cannot_pass(self):
        self.assertTrue({p[0] for p in d.PROBES}.isdisjoint(p[0] for p in d.REVERSE_PROBES))
        self.assertTrue({p[1] for p in d.PROBES}.isdisjoint(p[1] for p in d.REVERSE_PROBES))
        for mode in ("switch", "direct250"):
            code, rows = self.run_bench(Bench(corruption="self_echo"), mode=mode,
                                        confirm_bench="isolated-bench", rounds=3)
            self.assertEqual(code, 1)
            verdicts = [r for r in rows if r["kind"] == "verdict"]
            self.assertTrue(all(v["ok"] == (v["direction"] == 0) for v in verdicts))
            self.assertFalse(rows[-1]["minimum_switch_gate_pass"])

    def test_after_forward_status_order_even_on_receive_failure(self):
        for corruption in (None, "slcan"):
            code, rows = self.run_bench(Bench(corruption=corruption), rounds=1)
            self.assertEqual(code, 0 if corruption is None else 1)
            for phase in range(3):
                forward = next(i for i, r in enumerate(rows) if r["kind"] == "verdict"
                               and r["phase"] == phase and r["direction"] == 0)
                reverse = next(i for i, r in enumerate(rows) if r["kind"] == "probe"
                               and r["phase"] == phase and r["direction"] == 1)
                self.assertEqual([r["label"] for r in rows[forward:reverse]
                                  if r["kind"] == "status"], ["after_forward"])

    def test_short_control_sample_independent_of_data_timeout(self):
        b = Bench()
        can = d.Slcan(b.peer, lambda *a, **kw: None, timeout=1.0, feedback_window=0.02)
        with patch.object(d.time, "monotonic", b.clock):
            for cmd in ("S6", "Y2", "M0", "A1", "O"):
                start = b.now
                can.cmd(cmd)
                self.assertAlmostEqual(b.now - start, 0.02, delta=0.0011)
        self.assertLess(b.now, 0.11)

    def test_cli_defaults_and_utc_evidence_without_hardware(self):
        captured = []

        def fake_factory(options):
            captured.append(options)
            raise RuntimeError("host-only factory, no devices")

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "evidence.jsonl"
            argv = ["--mcp", "FAKE_MCP", "--canable", "FAKE_PEER", "--mode", "switch",
                    "--restore-rate", "500000", "--confirm-bench", "original-bench",
                    "--evidence", str(target)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(d.main(argv, factory=fake_factory), 1)
            self.assertEqual(captured[0].mcp_baud, 115200)
            self.assertEqual(captured[0].timeout, 1.0)
            self.assertEqual(captured[0].feedback_window, 0.02)
            rows = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines()]
            for row in rows:
                self.assertIsInstance(row["t"], (int, float))
                self.assertEqual(d.datetime.fromisoformat(row["utc"]).utcoffset().total_seconds(), 0)

    def test_send_control_failure_stops_probes_but_restores(self):
        b = Bench(fail_cmd=0x13)
        code, rows = self.run_bench(b)
        self.assertEqual(code, 1)
        self.assertEqual(len([r for r in rows if r["kind"] == "probe"]), 1)
        self.assertEqual([cmd for cmd, _ in b.commands][-1], 0x11)
        self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])

    def test_interrupt_still_restores_and_closes(self):
        b = Bench()
        b.mcp.recv_event = lambda **kw: (_ for _ in ()).throw(KeyboardInterrupt())
        code, rows = self.run_bench(b)
        self.assertEqual(code, 1)
        self.assertEqual(len([r for r in rows if r["kind"] == "cleanup"]), 6)
        self.assertEqual(b.calls[-2:], ["peer.close", "mcp.close"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
