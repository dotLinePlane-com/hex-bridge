"""Manage the HEX-Bridge v1 device profile over UART or socket://HOST:9500."""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "test"))
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

FEATURES = "serial control_tcp can uart wifi tcp udp websocket dap".split()
SIGNALS = "uart.tx uart.rx can.sck can.mosi can.miso can.cs can.int dap.swclk dap.swdio".split()
POLICIES = ["unavailable", "flexible", "input_only", "can.cs_only", "uart0.tx",
            "uart0.rx", "uart1.tx", "uart1.rx", "flash", "psram", "spi2", "eeprom", "strap"]
PHASES = ["confirmed", "staged", "armed", "trial"]
COMMANDS = ["describe", "read", "check", "save", "cancel", "apply", "confirm"]
SIZE = 2 + len(SIGNALS)


def decode_mapping(data):
    mask = int.from_bytes(data[:2], "big")
    return {"features": {f: bool(mask & (1 << i)) for i, f in enumerate(FEATURES)},
            "pins": dict(zip(SIGNALS, data[2:], strict=True))}


def encode_mapping(config):
    features, pins = config["features"], config["pins"]
    if set(features) != set(FEATURES) or any(type(v) is not bool for v in features.values()):
        raise ValueError("features must contain all nine named boolean switches")
    if set(pins) != set(SIGNALS) or any(type(p) is not int or not 0 <= p <= 255 for p in pins.values()):
        raise ValueError("pins must contain exactly the nine editable signals and integer GPIOs")
    mask = sum(1 << i for i, f in enumerate(FEATURES) if features[f])
    return struct.pack(">H", mask) + bytes(pins[s] for s in SIGNALS)


class Device:
    def __init__(self, transport):
        self.transport = transport
        self.seq = 0
        self.gpios = {}

    def request(self, op, data=b""):
        self.seq += 1
        packet = bytes([1, COMMANDS.index(op)]) + data
        self.transport.send(UBCPBuilder.build_request(self.seq, 8, 0, packet))
        frame = self.transport.recv_response(8, self.seq, timeout=4)
        if not frame or not frame.is_response or not frame.payload:
            raise ValueError("No valid device-profile response")
        status, *rest = frame.payload
        data = bytes(rest)
        if status == 2 and data and len(data) == 1 + 4 * data[0]:
            problems = []
            for reason, subject, pin, other in struct.iter_unpack("4B", data[1:]):
                if reason == 1: message = "unknown feature bits"
                elif reason == 2: message = "enable serial or control_tcp"
                elif reason == 3: message = FEATURES[subject] + " requires wifi"
                elif reason == 4: message = "save Wi-Fi credentials before disabling serial"
                elif reason == 5:
                    message = f"{SIGNALS[subject]} cannot use GPIO{pin} ({self.gpios.get(str(pin), 'unavailable')})"
                elif reason == 6: message = f"{SIGNALS[subject]} conflicts with {SIGNALS[other]} on GPIO{pin}"
                else: message = f"unknown diagnostic {reason}"
                problems.append(message)
            raise ValueError("\n".join(problems))
        if status:
            reasons = {2: "invalid payload", 4: "transaction busy", 6: "extension unsupported",
                       12: "confirm using the newly enabled control interface",
                       14: "stale revision or candidate ID; read the device again"}
            raise ValueError(f"{op}: 0x{status:02x} {reasons.get(status, 'device error')}")
        return data

    def descriptor(self):
        data = self.request("describe")
        if len(data) != 5 + SIZE + 40 or data[0] != 1:
            raise ValueError("Unsupported board descriptor")
        self.gpios = {str(i): POLICIES[v] for i, v in enumerate(data[5 + SIZE:])}
        return {"schema": 1, "board": data[1:5].decode("ascii"), "gpio_policy": self.gpios}

    def snapshot(self):
        data = self.request("read")
        if len(data) not in (13 + SIZE, 13 + 2 * SIZE):
            raise ValueError("Invalid device-profile snapshot")
        phase, revision, candidate, confirmed = struct.unpack_from(">BIII", data)
        return {"revision": revision, "phase": PHASES[phase], "candidate_id": candidate,
                "confirmed_id": confirmed, "active": decode_mapping(data[13:13 + SIZE]),
                "candidate": decode_mapping(data[13 + SIZE:]) if candidate else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4", help="COM port or socket://HOST:9500")
    parser.add_argument("--baud", default=115200, type=int)
    subs = parser.add_subparsers(dest="op", required=True)
    subs.add_parser("show")
    subs.add_parser("export").add_argument("file", type=Path)
    for op in ("check", "save"):
        subs.add_parser(op).add_argument("file", type=Path)
    for op in ("cancel", "apply", "confirm"):
        subs.add_parser(op).add_argument("id", type=int)
    args = parser.parse_args()
    with MCPTransport(args.port, args.baud) as transport:
        device = Device(transport)
        desc = device.descriptor()
        if args.op in ("show", "export"):
            snapshot = device.snapshot()
            if args.op == "show":
                print(json.dumps({**desc, **snapshot}, indent=2))
            else:
                config = {**desc, "revision": snapshot["revision"], **snapshot["active"]}
                args.file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        elif args.op in ("check", "save"):
            config = json.loads(args.file.read_text(encoding="utf-8-sig"))
            if set(config) != set(desc) | {"revision", "features", "pins"}:
                raise ValueError("Unexpected or missing profile fields")
            if any(config[key] != value for key, value in desc.items()):
                raise ValueError("Board identity and GPIO policy are read-only; export a fresh profile")
            data = device.request(args.op, struct.pack(">I", config["revision"]) + encode_mapping(config))
            if args.op == "save":
                print("candidate_id =", struct.unpack(">I", data)[0])
            else:
                print("OK")
        else:
            device.request(args.op, struct.pack(">I", args.id))
            print("Trial requested. Reconnect and confirm within 120 s." if args.op == "apply" else "OK")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error) as exc:
        sys.exit(str(exc))
