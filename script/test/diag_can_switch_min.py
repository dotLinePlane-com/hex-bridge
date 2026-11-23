"""CANable/HEX-Bridge original-bench diagnostic or isolated minimum switch gate.

No device discovery, default ports, or hardware imports at module import time.
Run --help for the mandatory truthful bench acknowledgement. JSONL evidence
contains raw SLCAN bytes, feedback (silence is NOT an ACK), UBCP payloads,
per-round/direction verdicts and independent cleanup outcomes. Restore means
configure the explicitly selected baseline, then leave BOTH channels closed;
it does not claim to recover an unknown previous configuration or filters.

Reproduction baseline: flags=0x03, S/Y2/M0/A1/O, forward 0x600/Hello,
0x601/World, 0x602/Back at 500/250/500k. Diagnostic differences: reverse
0x610/RHello, 0x611/RWorld, 0x612/RBack; before/after_forward/after STATUS;
short control-feedback samples (default 20ms), separate data receive and
phase-boundary observation windows (default 1s). These replace the original
suite's 0.3s settling delay; they do not reproduce its exact timing. No E query.
Only isolated-bench + switch + >=3 successful rounds can pass the minimum
switch gate. This script never represents the full CAN acceptance suite.
"""

import argparse
import json
import math
import re
import struct
import time
from datetime import datetime, timezone

BENCHES = ("original-bench", "isolated-bench")
RATES = {250000: 5, 500000: 6}
PROBES = ((0x600, b"Hello"), (0x601, b"World"), (0x602, b"Back"))
REVERSE_PROBES = ((0x610, b"RHello"), (0x611, b"RWorld"), (0x612, b"RBack"))


def evidence_record(kind, **fields):
    return dict(t=time.monotonic(), utc=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                kind=kind, **fields)


class ControlError(RuntimeError):
    """A failed control transaction forbids further diagnostic probes."""


def repository_decode(raw):
    from canable_slcan import CanableChannel
    return CanableChannel._decode_frame(None, raw)


def strict_slcan(raw, ident, data):
    """Exact classic, standard, non-RTR, DLC and data; no ID masking."""
    if not re.fullmatch(rb"t[0-9a-fA-F]{3}[0-8][0-9a-fA-F]*", raw):
        raise ValueError("not a classic standard data frame")
    actual_id, dlc = int(raw[1:4], 16), int(raw[4:5], 16)
    if actual_id > 0x7FF or len(raw) != 5 + 2 * dlc:
        raise ValueError("invalid standard ID or DLC/length")
    if (actual_id, dlc, bytes.fromhex(raw[5:].decode())) != (ident, len(data), data):
        raise ValueError("SLCAN ID/DLC/data mismatch")


def strict_event(frame, ident, data):
    p = frame.payload
    if not frame.is_event or frame.cmd_code != 0x14 or frame.channel_id != 3:
        raise ValueError("wrong CAN event envelope")
    if len(p) != 10 + len(data):
        raise ValueError("CAN event length mismatch")
    if struct.unpack_from(">I", p)[0] != ident or p[4] != len(data):
        raise ValueError("CAN ID/flags/DLC mismatch")
    if p[5:5 + len(data)] != data or p[5 + len(data)] != 0:
        raise ValueError("CAN data/RxFlags mismatch")


class Slcan:
    def __init__(self, serial_port, emit, timeout, decoder=repository_decode, feedback_window=0.02):
        self.ser, self.emit, self.timeout = serial_port, emit, timeout
        self.decoder = decoder
        self.feedback_window = feedback_window
        self.buf = bytearray()
        self.lines = []

    def collect(self, duration):
        end = time.monotonic() + duration
        while time.monotonic() < end:
            raw = self.ser.read(256)
            if not raw:
                continue
            self.emit("slcan_rx", hex=raw.hex())
            for byte in raw:
                if byte == 7:
                    self.emit("slcan_feedback", value="BEL/rejected")
                    raise ControlError("SLCAN BEL")
                if byte == 13:
                    line = bytes(self.buf)
                    self.buf.clear()
                    self.lines.append(line)
                    self.emit("slcan_line", hex=line.hex(),
                              feedback_type="ack" if not line else "frame_or_feedback")
                elif byte != 10:
                    self.buf.append(byte)
                    if len(self.buf) > 256:
                        raise ValueError("overlong SLCAN record")

    def cmd(self, command):
        raw = command.encode("ascii") + b"\r"
        self.emit("slcan_tx", hex=raw.hex())
        try:
            if self.ser.write(raw) != len(raw):
                raise IOError("short SLCAN write")
            self.collect(self.feedback_window)
        except Exception as exc:
            raise ControlError(f"SLCAN {command}: {exc}") from exc
        self.emit("slcan_feedback_window", command=command,
                  note="raw feedback only; silence does not prove acceptance")

    def receive(self, ident, data):
        end = time.monotonic() + self.timeout
        while True:
            while self.lines:
                line = self.lines.pop(0)
                if line[:1] in (b"t", b"T", b"r", b"R", b"d", b"D", b"b", b"B"):
                    width = 3 if line[:1] in (b"t", b"r", b"d", b"b") else 8
                    try:
                        actual_id = int(line[1:1 + width], 16)
                    except ValueError:
                        self.emit("slcan_unparseable", hex=line.hex())
                        continue
                    if actual_id != ident:
                        self.emit("slcan_unrelated", hex=line.hex(), id=actual_id)
                        continue
                    self.emit("slcan_match_raw", hex=line.hex(), id=ident)
                    strict_slcan(line, ident, data)
                    msg = self.decoder(line)
                    if (msg is None or msg.id != ident or msg.dlc != len(data)
                            or msg.data != data or any((msg.is_extended, msg.is_rtr,
                                                       msg.is_fd, msg.is_brs))):
                        raise ValueError("repository SLCAN decoder mismatch")
                    self.emit("slcan_match_decoded", id=msg.id, dlc=msg.dlc,
                              data=msg.data.hex(), extended=msg.is_extended,
                              rtr=msg.is_rtr, fd=msg.is_fd, brs=msg.is_brs)
                    return
            if time.monotonic() >= end:
                raise TimeoutError("no exact SLCAN receive")
            self.collect(min(0.02, end - time.monotonic()))

    def boundary(self):
        self.collect(self.timeout)
        self.emit("slcan_boundary", discarded=[x.hex() for x in self.lines],
                  partial=self.buf.hex())
        # Keep a partial record so its eventual raw completion is preserved.
        self.lines.clear()


class Diagnostic:
    def __init__(self, mcp, slcan, emit, timeout):
        self.mcp, self.can, self.emit, self.timeout = mcp, slcan, emit, timeout
        self.seq = 0
        self.errors = 0

    def request(self, cmd, payload=b"", allowed=(0,)):
        from ubcp_client import UBCPBuilder
        self.seq += 1
        self.emit("ubcp_tx", seq=self.seq, cmd=cmd, payload=payload.hex())
        try:
            self.mcp.send(UBCPBuilder.build_request(self.seq, cmd, 3, payload))
            f = self.mcp.recv_response(cmd_code=cmd, seq_num=self.seq, timeout=self.timeout)
        except Exception as exc:
            raise ControlError(f"UBCP command {cmd:#x}: {exc}") from exc
        self.emit("ubcp_response", seq=self.seq, cmd=cmd,
                  payload=None if f is None else f.payload.hex())
        if (f is None or not f.is_response or f.is_event or f.channel_id != 3
                or f.cmd_code != cmd or f.seq_num != self.seq
                or not f.payload or f.payload[0] not in allowed):
            raise ControlError(f"UBCP command {cmd:#x} rejected/missing/mismatched")
        return f

    def configure(self, rate, initial=False):
        # Preserve the original bench flags, Y2 and retransmission settings.
        self.can.cmd("C")
        if initial:
            self.request(0x11, allowed=(0, 5))
            self.request(0x10, b"\0")
        self.request(0x12, bytes([RATES[rate], 0x03, 32, 0]))
        self.can.cmd(f"S{RATES[rate]}")
        self.can.cmd("Y2")
        self.can.cmd("M0")
        self.can.cmd("A1")
        self.can.cmd("O")
        self.can.boundary()
        self.drain_events()

    def drain_events(self):
        end = time.monotonic() + self.timeout
        while time.monotonic() < end:
            f = self.mcp.recv_event(timeout=max(0.001, end - time.monotonic()))
            if f is None:
                break
            self.emit("ubcp_boundary_event", cmd=f.cmd_code, channel=f.channel_id,
                      payload=f.payload.hex())

    def receive_event(self, ident, data):
        end = time.monotonic() + self.timeout
        while time.monotonic() < end:
            f = self.mcp.recv_event(cmd_code=0x14, timeout=max(0.001, end - time.monotonic()))
            self.emit("ubcp_event", payload=None if f is None else f.payload.hex())
            if f is None:
                break
            if len(f.payload) >= 4 and (struct.unpack_from(">I", f.payload)[0] & 0x1FFFFFFF) != ident:
                self.emit("ubcp_unrelated", payload=f.payload.hex())
                continue
            strict_event(f, ident, data)
            return
        raise TimeoutError("no exact CAN_RECV")

    def status(self, label):
        p = self.request(0x16).payload
        if len(p) != 28:
            raise ControlError("invalid CAN_STATUS length")
        self.emit("status", label=label, payload=p.hex(), bus=p[1], tec=p[2], rec=p[3])
        if any(p[1:4]):
            self.errors += 1
            self.emit("status_error", label=label, note="recorded; continuing diagnostic")

    def phase(self, round_num, phase_num, rate):
        self.emit("phase_start", round=round_num, phase=phase_num, rate=rate)
        phase_errors = self.errors
        self.status("before")
        for direction in (0, 1):
            probes = PROBES if direction == 0 else REVERSE_PROBES
            ident, data = probes[1 if rate == 250000 else phase_num]
            self.emit("probe", round=round_num, phase=phase_num, rate=rate,
                      direction=direction, id=ident, dlc=len(data), data=data.hex())
            # SEND feedback is a control gate, distinct from receive evidence.
            if direction == 0:
                self.request(0x13, struct.pack(">IB", ident, len(data)) + data)
            else:
                self.drain_events()
                self.can.cmd(f"t{ident:03X}{len(data)}{data.hex()}")
            try:
                if direction == 0:
                    self.can.receive(ident, data)
                else:
                    self.receive_event(ident, data)
            except ControlError:
                raise
            except Exception as exc:
                self.errors += 1
                self.emit("verdict", round=round_num, phase=phase_num,
                          direction=direction, ok=False, error=str(exc))
            else:
                self.emit("verdict", round=round_num, phase=phase_num, direction=direction, ok=True)
            if direction == 0:
                self.status("after_forward")
        self.status("after")
        self.emit("phase_result", round=round_num, phase=phase_num, rate=rate,
                  ok=self.errors == phase_errors)

    def cleanup(self, restore_rate):
        # Every operation is attempted independently, including after Ctrl-C.
        # Restoration never opens a CAN channel or transmits a probe.
        actions = [
            ("peer_stop", lambda: self.can.cmd("C")),
            ("dut_restore", lambda: self.request(0x12, bytes([RATES[restore_rate], 3, 32, 0]))),
            ("peer_restore", lambda: self.can.cmd(f"S{RATES[restore_rate]}")),
            ("peer_restore_y2", lambda: self.can.cmd("Y2")),
            ("dut_close", lambda: self.request(0x11, allowed=(0, 5))),
            ("peer_close", lambda: self.can.cmd("C")),
        ]
        ok = True
        for name, action in actions:
            try:
                action()
                self.emit("cleanup", action=name, ok=True)
            except BaseException as exc:
                ok = False
                self.emit("cleanup", action=name, ok=False, error=str(exc))
        return ok


def execute(args, factory, emit, decoder=repository_decode):
    """factory is injected by host tests; ownership starts before opening ports."""
    if args.confirm_bench not in BENCHES:
        raise ValueError("explicit original-bench or isolated-bench confirmation required")
    mcp = peer = diag = None
    ok = False
    try:
        mcp, peer = factory(args)
        mcp.open()
        peer.open()
        diag = Diagnostic(mcp, Slcan(peer, emit, args.timeout, decoder, args.feedback_window), emit, args.timeout)
        emit("session", mode=args.mode, mcp=args.mcp, canable=args.canable,
             restore_rate=args.restore_rate, bench=args.confirm_bench,
             purpose="diagnostic" if args.confirm_bench == "original-bench" else "minimum_switch_gate",
             data_timeout=args.timeout, control_feedback_window=args.feedback_window,
             correlation="original fixed ID/data; matching background traffic cannot be distinguished")
        rates = [250000] if args.mode == "direct250" else [500000, 250000, 500000]
        for round_num in range(1, args.rounds + 1):
            for phase_num, rate in enumerate(rates):
                diag.configure(rate, initial=round_num == 1 and phase_num == 0)
                diag.phase(round_num, phase_num, rate)
        ok = diag.errors == 0
    except BaseException as exc:
        emit("failure", error=repr(exc))
        if diag:
            try:
                diag.status("failure")
            except BaseException as status_exc:
                emit("failure_status", error=repr(status_exc))
    finally:
        if diag:
            ok = diag.cleanup(args.restore_rate) and ok
        for name, port in (("canable_serial", peer), ("mcp_serial", mcp)):
            if port is not None:
                try:
                    port.close()
                    emit("resource_close", name=name, ok=True)
                except BaseException as exc:
                    ok = False
                    emit("resource_close", name=name, ok=False, error=repr(exc))
    emit("result", ok=ok, bench=args.confirm_bench,
         scope="minimum_switch_gate_only", full_suite_run=False,
         minimum_switch_gate_pass=(ok and args.confirm_bench == "isolated-bench"
                                   and args.mode == "switch" and args.rounds >= 3))
    return 0 if ok else 1


def hardware(args):
    # Deliberately lazy; no enumeration and no implicit device selection.
    import serial
    from mcp_transport import MCPTransport

    class BoundedTransport(MCPTransport):
        def open(self):
            super().open()
            self.ser.write_timeout = args.timeout

        def send(self, data):
            # Avoid an unbounded serial flush if a confirmed bench disconnects.
            if self.ser.write(data) != len(data):
                raise IOError("short MCP write")

    peer = serial.Serial(port=None, baudrate=args.serial_baud, timeout=0.01,
                         write_timeout=args.timeout)
    peer.port = args.canable
    mcp = BoundedTransport(port=args.mcp, baudrate=args.mcp_baud)
    return mcp, peer


def main(argv=None, factory=hardware):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mcp", required=True, help="explicit confirmed bench UART")
    parser.add_argument("--canable", required=True, help="explicit confirmed bench SLCAN UART")
    parser.add_argument("--confirm-bench", required=True, choices=BENCHES,
                        help="explicitly confirm named ports/wiring: original-bench diagnostics or isolated-bench minimum gate")
    parser.add_argument("--mode", required=True, choices=["direct250", "switch"])
    parser.add_argument("--restore-rate", required=True, type=int, choices=RATES)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=1.0, help="data/boundary receive window in seconds")
    parser.add_argument("--feedback-window", type=float, default=0.02,
                        help="independent SLCAN control-feedback sample in seconds")
    parser.add_argument("--mcp-baud", type=int, default=115200)
    parser.add_argument("--serial-baud", type=int, default=115200)
    parser.add_argument("--evidence", required=True, help="new JSONL file; never overwrite")
    args = parser.parse_args(argv)
    if not (1 <= args.rounds <= 1000 and math.isfinite(args.timeout) and 0.05 <= args.timeout <= 5):
        parser.error("rounds must be 1..1000; timeout must be finite and 0.05..5 seconds")
    if not (math.isfinite(args.feedback_window) and 0.001 <= args.feedback_window <= 0.2):
        parser.error("feedback-window must be finite and 0.001..0.2 seconds")
    if args.mcp.strip().casefold() == args.canable.strip().casefold():
        parser.error("ports must be distinct")
    if min(args.mcp_baud, args.serial_baud) <= 0:
        parser.error("serial baud rates must be positive")
    with open(args.evidence, "x", encoding="utf-8") as stream:
        def emit(kind, **fields):
            line = json.dumps(evidence_record(kind, **fields))
            stream.write(line + "\n")
            stream.flush()
            print(line)
        return execute(args, factory, emit)


if __name__ == "__main__":
    raise SystemExit(main())
