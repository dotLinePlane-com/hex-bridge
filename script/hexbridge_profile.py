"""Shared HEX-Bridge profile codec, device access, validation and pin tables."""
import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "test"))
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

FEATURES = "serial control_tcp can uart wifi tcp udp websocket dap".split()
SIGNALS = "uart.tx uart.rx can.sck can.mosi can.miso can.cs can.int dap.swclk dap.swdio".split()
POLICIES = ["unavailable", "flexible", "input_only", "can.cs_only", "uart0.tx",
            "uart0.rx", "uart1.tx", "uart1.rx", "flash", "psram", "spi2", "eeprom", "strap"]
PHASES = ["confirmed", "staged", "armed", "trial"]
COMMANDS = ["describe", "read", "check", "save", "cancel", "apply", "confirm"]
SIZE = 2 + len(SIGNALS)
SIZE_V2 = 26
SIZE_V3 = 29
SIZE_V4 = 30
SIZE_V5 = 34
SPI_SLAVE_CAPS = {2: 0x80, 3: 0x100}
CAP_UART1_BUSINESS = 0x40
NO_CS = 0xff
CAP_DUAL_SPI = 0x10
CAP_OPTIONAL_CS = 0x20
SECOND_SPI_DEFAULT = {"enabled": False, "host": 2, "cs": NO_CS}
PROFILE_SIZES = {1: SIZE, 2: SIZE_V2, 3: SIZE_V3, 4: SIZE_V4, 5: SIZE_V5}
V2_BASE_SIGNALS = ("uart.tx", "uart.rx", "dap.swclk", "dap.swdio")
SPI_PIN_FIELDS = ("sck", "mosi", "miso", "io2", "io3")
SPI_FIELDS = ("enabled", "width", *SPI_PIN_FIELDS)
V2_SIGNALS = "uart.tx uart.rx dap.swclk dap.swdio spi2.sck spi2.mosi spi2.miso spi2.io2 spi2.io3 spi3.sck spi3.mosi spi3.miso spi3.io2 spi3.io3 external.cs can.cs can.int".split()
V3_SIGNALS = [*V2_SIGNALS, "external2.cs"]
V5_SIGNALS = [*V3_SIGNALS, "spi2.slave_cs", "spi3.slave_cs"]
V5_DIAGNOSTIC_FIELDS = [*V3_SIGNALS, "uart1_business", *V5_SIGNALS[-2:], "spi2.role", "spi3.role"]
V2_DIRECTIONS = ["output", "input", "output", "bidirectional"] + ["output", "output", "input", "bidirectional", "bidirectional"] * 2 + ["output", "output", "input_interrupt"]
SIGNAL_FEATURES = ["uart", "uart", "can", "can", "can", "can", "can", "dap", "dap"]
DIRECTIONS = ["output", "input", "output", "output", "input", "output", "input_interrupt",
              "output", "bidirectional"]
PURPOSES = {"uart0.tx": "UART0 flashing/log TX", "uart0.rx": "UART0 flashing/log RX",
            "uart1.tx": "UART1 computer control TX", "uart1.rx": "UART1 computer control RX",
            "flash": "internal Flash", "psram": "internal PSRAM",
            "spi2": "external SPI2", "eeprom": "board EEPROM", "strap": "boot strapping"}


def pin_notes(gpio, policy):
    if policy == "can.cs_only":
        return "CAN.CS only; external 10k pull-up, maintain boot high level"
    if policy == "input_only" or policy == "uart1.rx":
        return "input only; no internal pull resistors, external bias required"
    if gpio == 12 and policy == "eeprom":
        return "MTDI; external 4.7k pull-up, maintain boot high for PSRAM"
    return ""


def occupancy(desc, mapping):
    """Derive ownership from configuration, never peripheral OPEN or link state."""
    owners = {int(g): [p] if p in PURPOSES else []
              for g, p in desc["gpio_policy"].items() if p != "unavailable"}
    for index, (signal, feature) in enumerate(zip(SIGNALS, SIGNAL_FEATURES)):
        gpio = mapping["pins"][signal]
        if mapping["features"][feature] and legal_pin(desc, index, gpio):
            owners[gpio].append(signal)
    rows = []
    for gpio, users in sorted(owners.items()):
        fixed = desc["gpio_policy"][str(gpio)] in PURPOSES
        state = "occupied" if users else "free"
        rows.append({"gpio": gpio, "owners": users, "state": "fixed" if fixed else state, "fixed": fixed})
    return rows


def legal_pin(desc, index, gpio):
    policy = desc["gpio_policy"].get(str(gpio), "unavailable")
    return (policy == "flexible" or (policy == "input_only" and DIRECTIONS[index].startswith("input"))
            or (policy == "can.cs_only" and SIGNALS[index] == "can.cs"))


def build_tables_v1(desc, snapshot, candidate=None):
    """Read-only views derived from DESCRIBE and one READ snapshot."""
    policy = desc["gpio_policy"]
    active = snapshot["active"]
    candidate = candidate if candidate is not None else snapshot["candidate"]
    current = occupancy(desc, active)
    proposed = occupancy(desc, candidate) if candidate is not None else None
    current_owners = {r["gpio"]: r["owners"] for r in current}
    proposed_owners = {r["gpio"]: r["owners"] for r in proposed or []}
    fixed = _fixed_pins(desc)
    editable = []
    for index, (signal, feature, direction) in enumerate(zip(SIGNALS, SIGNAL_FEATURES, DIRECTIONS)):
        candidates = []
        for g, p in policy.items():
            if legal_pin(desc, index, int(g)):
                gpio = int(g)
                candidates.append({"gpio": gpio, "owners": current_owners.get(gpio, []),
                                   "candidate_owners": proposed_owners.get(gpio, []) if proposed is not None else None,
                                   "notes": pin_notes(gpio, p)})
        editable.append({"index": index, "signal": signal, "feature": feature,
                         "direction": direction, "gpio": active["pins"][signal],
                         "enabled": active["features"][feature],
                         "candidate_gpio": candidate["pins"][signal] if candidate is not None else None,
                         "candidate_enabled": candidate["features"][feature] if candidate is not None else None,
                         "candidates": sorted(candidates, key=lambda r: r["gpio"])})
    return {"fixed": sorted(fixed, key=lambda r: r["gpio"]), "editable": editable,
            "occupancy": current, "candidate_occupancy": proposed,
            "invalid_pins": [{"signal": signal, "gpio": candidate["pins"][signal],
                              "reason": "fixed, unavailable or incompatible direction"}
                             for index, signal in enumerate(SIGNALS)
                             if candidate is not None and not legal_pin(desc, index, candidate["pins"][signal])],
            "unavailable": sorted(int(g) for g, p in policy.items() if p == "unavailable")}


def render_human(desc, snapshot, tables, source="saved candidate"):
    def signal_name(name):
        return name.replace("uart.", "uart2.").upper()

    def pin_name(signal, gpio):
        if signal.endswith(".slave_cs") and gpio == NO_CS:
            return "unassigned"
        if desc["schema"] >= 3 and signal in ("external.cs", "external2.cs") and gpio == NO_CS:
            return "no CS"
        return f"GPIO{gpio}"

    def occupancy_line(row):
        owners = ", ".join(map(signal_name, row["owners"])) or "free"
        role = f", UART1 {row['uart1_role']}" if "uart1_role" in row else ""
        return f"  GPIO{row['gpio']}: {owners} [{row['state']}{role}]"

    lines = [f"Board {desc['board']} | revision {snapshot['revision']} | {snapshot['phase']}",
             f"Confirmed ID {snapshot['confirmed_id']} | candidate ID {snapshot['candidate_id']}",
             "Features: " + ", ".join(f"{name}={'on' if enabled else 'off'}"
                                       for name, enabled in snapshot["active"]["features"].items()),
             "System fixed pins (read-only; retained when a feature is disabled):"]
    for row in tables["fixed"]:
        lines.append(f"  GPIO{row['gpio']}: {row['owner']} ({row['purpose']})" +
                     (f"; {row['direction']}" if row["direction"] else ""))
    lines.append("Editable signals (candidates include occupied pins; submit the complete mapping):")
    for host, roles in tables.get("spi_roles", {}).items():
        after = f" -> {roles['candidate']}" if roles["candidate"] else ""
        lines.append(f"  SPI{host} controller role: {roles['current']}{after}")
    for issue in tables.get("role_conflicts", []):
        lines.append(f"  {issue['device']} requires a master controller; SPI{issue['host']} is a slave")
    for row in tables["editable"]:
        direction = row["direction"]
        if row.get("candidate_direction") not in (None, direction):
            direction += " -> " + row["candidate_direction"]
        candidates = ", ".join(f"{c['gpio']} ({', '.join(map(signal_name, c['owners'])) or 'free'})"
                               for c in row["candidates"])
        after = (f" -> {pin_name(row['signal'], row['candidate_gpio'])} ({'enabled' if row['candidate_enabled'] else 'disabled'})"
                 if row["candidate_gpio"] is not None else "")
        lines.append(f"  [{row['index']}] {signal_name(row['signal'])} {direction}: {pin_name(row['signal'], row['gpio'])} "
                     f"({'enabled' if row['enabled'] else 'disabled'}){after}; candidates: {candidates}")
    lines.append("Electrical requirements:")
    for g, policy in desc["gpio_policy"].items():
        note = pin_notes(int(g), policy)
        if note:
            lines.append(f"  GPIO{g}: {note}")
    lines.append("Current occupancy (active configuration):")
    for row in tables["occupancy"]:
        lines.append(occupancy_line(row))
    if tables["candidate_occupancy"] is not None:
        lines.append(f"Occupancy after applying {source} (preview; CHECK/SAVE do not change current ownership):")
        for row in tables["candidate_occupancy"]:
            lines.append(occupancy_line(row))
    for row in tables["invalid_pins"]:
        lines.append(f"Invalid preview: {row['signal']} GPIO{row['gpio']}: {row['reason']}")
    if source == "imported file":
        lines.append("Use check to validate the file, including dependencies and revision, on the device.")
    lines.append("Unavailable/unexposed GPIOs: " + ", ".join(map(str, tables["unavailable"])))
    lines.append("Disabled features retain their selected mappings without owning the editable pins.")
    return "\n".join(lines)


def load_config_v1(file, desc):
    config = json.loads(file.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or set(config) != set(desc) | {"revision", "features", "pins"}:
        raise ValueError("Unexpected or missing profile fields")
    if any(config[key] != value for key, value in desc.items()):
        raise ValueError("Board identity and GPIO policy are read-only; export a fresh profile")
    if type(config["schema"]) is not int:
        raise ValueError("Board schema is read-only; export a fresh profile")
    if type(config["revision"]) is not int or not 1 <= config["revision"] <= 0xffffffff:
        raise ValueError("revision must be an unsigned nonzero 32-bit integer")
    encode_mapping(config)
    return config


def decode_mapping_v1(data):
    if len(data) != SIZE:
        raise ValueError("Invalid device-profile mapping length")
    mask = int.from_bytes(data[:2], "big")
    if mask & ~511:
        raise ValueError("Unknown device-profile feature bits")
    return {"features": {f: bool(mask & (1 << i)) for i, f in enumerate(FEATURES)},
            "pins": dict(zip(SIGNALS, data[2:], strict=True))}


def encode_mapping_v1(config):
    features, pins = config["features"], config["pins"]
    if not isinstance(features, dict) or set(features) != set(FEATURES) or any(type(v) is not bool for v in features.values()):
        raise ValueError("features must contain all nine named boolean switches")
    if not isinstance(pins, dict) or set(pins) != set(SIGNALS) or any(type(p) is not int or not 0 <= p <= 255 for p in pins.values()):
        raise ValueError("pins must contain exactly the nine editable signals and integer GPIOs")
    mask = sum(1 << i for i, f in enumerate(FEATURES) if features[f])
    return struct.pack(">H", mask) + bytes(pins[s] for s in SIGNALS)


def decode_mapping(data):
    if len(data) == SIZE:
        return decode_mapping_v1(data)
    if len(data) not in (SIZE_V2, SIZE_V3, SIZE_V4, SIZE_V5):
        raise ValueError("Invalid device-profile mapping length")
    mask = int.from_bytes(data[:2], "big")
    if mask & ~511:
        raise ValueError("Unknown device-profile feature bits")
    if data[20] not in (0, 1):
        raise ValueError("Invalid external SPI enabled value")
    buses = {}
    for index, host in enumerate((2, 3)):
        fields = data[6 + 7 * index:13 + 7 * index]
        if fields[0] not in (0, 1) or fields[1] not in (1, 4):
            raise ValueError("Invalid SPI enabled value or width")
        buses[str(host)] = dict(zip(SPI_FIELDS, fields))
        buses[str(host)]["enabled"] = bool(fields[0])
    if data[21] not in (2, 3) or data[23] not in (2, 3):
        raise ValueError("Invalid SPI attachment host")
    mapping = {
        "features": {name: bool(mask & (1 << index)) for index, name in enumerate(FEATURES)},
        "pins": dict(zip(V2_BASE_SIGNALS, data[2:6])),
        "spi": buses,
        "external": {"enabled": bool(data[20]), "host": data[21], "cs": data[22]},
        "mcp2518fd": {"host": data[23], "cs": data[24], "int": data[25]},
    }
    if len(data) >= SIZE_V3:
        enabled, host, cs = data[26:29]
        if enabled not in (0, 1) or host not in (2, 3):
            raise ValueError("Invalid second SPI attachment")
        mapping["external2"] = {"enabled": bool(enabled), "host": host, "cs": cs}
    if len(data) >= SIZE_V4:
        if data[29] not in (0, 1):
            raise ValueError("Invalid UART1 business enable flag")
        mapping["uart1_business"] = bool(data[29])
    if len(data) == SIZE_V5:
        for host, (role, cs) in zip(("2", "3"), struct.iter_unpack("BB", data[30:])):
            if role not in (0, 1):
                raise ValueError("Invalid SPI controller role")
            buses[host].update(role=("master", "slave")[role], slave_cs=cs)
    return mapping


def encode_mapping(config):
    if "spi" not in config:
        return encode_mapping_v1(config)
    features, pins = config["features"], config["pins"]
    if set(features) != set(FEATURES) or any(type(value) is not bool for value in features.values()):
        raise ValueError("features must contain all nine boolean switches")
    if set(pins) != set(V2_BASE_SIGNALS) or set(config["spi"]) != {"2", "3"}:
        raise ValueError("Invalid v2 pins or SPI instances")
    values = [pins[name] for name in V2_BASE_SIGNALS]
    schema = config.get("schema")
    has_roles = any("role" in bus or "slave_cs" in bus for bus in config["spi"].values())
    if schema is not None and has_roles != (schema == 5):
        raise ValueError("SPI role fields do not match the profile version")
    expected_fields = set(SPI_FIELDS) | ({"role", "slave_cs"} if has_roles else set())
    for host in ("2", "3"):
        bus = config["spi"][host]
        if (set(bus) != expected_fields or type(bus["enabled"]) is not bool
                or type(bus["width"]) is not int or bus["width"] not in (1, 4)):
            raise ValueError("Invalid SPI bus fields")
        values.append(int(bus["enabled"]))
        values.extend(bus[name] for name in SPI_FIELDS[1:])
    external, can = config["external"], config["mcp2518fd"]
    if (set(external) != {"enabled", "host", "cs"} or set(can) != {"host", "cs", "int"}
            or type(external["enabled"]) is not bool
            or external["host"] not in (2, 3) or can["host"] not in (2, 3)):
        raise ValueError("Invalid SPI attachment")
    values.extend((int(external["enabled"]), external["host"], external["cs"],
                   can["host"], can["cs"], can["int"]))
    if "external2" in config:
        second = config["external2"]
        if (set(second) != {"enabled", "host", "cs"} or type(second["enabled"]) is not bool
                or second["host"] not in (2, 3)):
            raise ValueError("Invalid second SPI attachment")
        values.extend((int(second["enabled"]), second["host"], second["cs"]))
    if "uart1_business" in config:
        if type(config["uart1_business"]) is not bool or "external2" not in config:
            raise ValueError("Invalid v4 UART1 business configuration")
        values.append(int(config["uart1_business"]))
    if has_roles:
        if "uart1_business" not in config:
            raise ValueError("Missing v4 prefix in SPI role mapping")
        for host in ("2", "3"):
            bus = config["spi"][host]
            if bus["role"] not in ("master", "slave"):
                raise ValueError("Invalid SPI controller role")
            values.extend((int(bus["role"] == "slave"), bus["slave_cs"]))
    if any(type(value) is not int or not 0 <= value <= 255 for value in values):
        raise ValueError("GPIO and fields must be unsigned bytes")
    mask = sum(1 << index for index, name in enumerate(FEATURES) if features[name])
    return struct.pack(">H", mask) + bytes(values)


def load_config(file, desc):
    if desc["schema"] == 1:
        return load_config_v1(file, desc)
    config = json.loads(file.read_text(encoding="utf-8-sig"))
    if desc["schema"] == 5 and config.get("schema") in (1, 2, 3, 4):
        old_desc = {**desc, "schema": 4, "capabilities": desc["capabilities"] & 0x7f}
        legacy = load_config(file, old_desc)
        for bus in legacy["spi"].values():
            bus.update(role="master", slave_cs=NO_CS)
        return {**legacy, **desc}
    if desc["schema"] == 4 and config.get("schema") in (1, 2, 3):
        old_desc = {**desc, "schema": 3, "capabilities": desc["capabilities"] & 0x3f}
        return {**load_config(file, old_desc), **desc, "uart1_business": False}
    if config.get("schema") == 1:
        if desc["board"] != "HXB1":
            raise ValueError("No v1 migration for this board")
        old_desc = {k: v for k, v in desc.items() if k != "capabilities"}
        old_desc["schema"] = 1
        old_desc["gpio_policy"] = dict(desc["gpio_policy"])
        for gpio in (18, 19, 21, 22, 23, 27):
            old_desc["gpio_policy"][str(gpio)] = "spi2"
        old = load_config_v1(file, old_desc)
        mapping = migrate_v1(old)
        if desc["schema"] == 3:
            mapping = migrate_v2(mapping)
        return {**desc, "revision": old["revision"], **mapping}
    if config.get("schema") == 2 and desc["schema"] == 3:
        legacy_desc = {**desc, "schema": 2, "capabilities": desc["capabilities"] & 15}
        legacy = load_config(file, legacy_desc)
        if legacy["external"]["cs"] == NO_CS:
            raise ValueError("v2 profiles require a CS GPIO")
        return {**migrate_v2(legacy), **desc}
    expected = set(desc) | {"revision", "features", "pins", "spi", "external", "mcp2518fd"}
    if desc["schema"] >= 3:
        expected.add("external2")
    if desc["schema"] >= 4:
        expected.add("uart1_business")
    if set(config) != expected:
        raise ValueError("Unexpected or missing profile fields")
    if any(config[k] != v for k, v in desc.items()):
        raise ValueError("Board identity and GPIO policy are read-only")
    if type(config["revision"]) is not int or not 1 <= config["revision"] <= 0xffffffff:
        raise ValueError("Invalid revision")
    encode_mapping(config)
    if desc["schema"] >= 5:
        for host, cap in SPI_SLAVE_CAPS.items():
            if config["spi"][str(host)]["role"] == "slave" and not desc["capabilities"] & cap:
                raise ValueError(f"SPI{host} does not support slave mode")
    if desc["schema"] >= 3:
        caps = desc["capabilities"]
        if config.get("uart1_business") and not caps & CAP_UART1_BUSINESS:
            raise ValueError("This firmware does not support UART1 as a data port")
        if config.get("uart1_business") and config["features"]["serial"]:
            raise ValueError("UART1 serial control and ordinary UART1 are mutually exclusive")
        if not caps & CAP_DUAL_SPI and config["external2"] != SECOND_SPI_DEFAULT:
            raise ValueError("Second SPI device settings are unsupported by this firmware")
        if not caps & CAP_OPTIONAL_CS:
            devices = [config["external"]]
            if config["external2"]["enabled"]:
                devices.append(config["external2"])
            if any(device["cs"] == NO_CS for device in devices):
                raise ValueError("This firmware requires a CS GPIO")
    return config


def build_tables(desc, snapshot, candidate=None):
    if desc["schema"] == 1:
        return build_tables_v1(desc, snapshot, candidate)
    return build_tables_v2(desc, snapshot, candidate)


def migrate_v2(mapping):
    return {**mapping, "external2": SECOND_SPI_DEFAULT.copy()}


def migrate_v1(mapping):
    """Preserve v1 wiring and external Quad capability; only the model changes."""
    pins = mapping["pins"]
    return {
        "features": dict(mapping["features"]),
        "pins": {name: pins[name] for name in V2_BASE_SIGNALS},
        "spi": {
            "2": {
                "enabled": True, "width": 4, "sck": 18, "mosi": 19,
                "miso": 21, "io2": 22, "io3": 23,
            },
            "3": {
                "enabled": mapping["features"]["can"], "width": 1,
                "sck": pins["can.sck"], "mosi": pins["can.mosi"],
                "miso": pins["can.miso"], "io2": 22, "io3": 23,
            },
        },
        "external": {"enabled": True, "host": 2, "cs": 27},
        "mcp2518fd": {"host": 3, "cs": pins["can.cs"], "int": pins["can.int"]},
    }


def v2_signals(mapping):
    """Flatten configured instances in stable wire diagnostic order."""
    rows = []

    def add(name, gpio, enabled, direction, diagnostic_index=None):
        rows.append({
            "index": len(rows) if diagnostic_index is None else diagnostic_index, "signal": name, "gpio": gpio,
            "enabled": enabled, "direction": direction,
        })

    for name, direction in zip(V2_BASE_SIGNALS, V2_DIRECTIONS[:4]):
        feature = "uart" if name.startswith("uart") else "dap"
        add(name, mapping["pins"][name], mapping["features"][feature], direction)
    for host in (2, 3):
        bus = mapping["spi"][str(host)]
        for name, direction in zip(SPI_PIN_FIELDS, V2_DIRECTIONS[4:9]):
            slave = bus.get("role") == "slave"
            if slave:
                direction = "input" if name in ("sck", "mosi") else "output"
            elif bus["width"] == 4 and name in ("mosi", "miso"):
                direction = "bidirectional"
            enabled = bus["enabled"] and (name not in ("io2", "io3") or (not slave and bus["width"] == 4))
            add(f"spi{host}.{name}", bus[name], enabled, direction)
    external, can = mapping["external"], mapping["mcp2518fd"]
    v3 = "external2" in mapping
    add("external.cs", external["cs"], external["enabled"] and (not v3 or external["cs"] != NO_CS), "output")
    add("can.cs", can["cs"], mapping["features"]["can"], "output")
    add("can.int", can["int"], mapping["features"]["can"], "input_interrupt")
    if v3:
        second = mapping["external2"]
        add("external2.cs", second["cs"], second["enabled"] and second["cs"] != NO_CS, "output")
    for host in ("2", "3"):
        bus = mapping["spi"][host]
        if "slave_cs" in bus:
            name = f"spi{host}.slave_cs"
            add(name, bus["slave_cs"], bus["enabled"] and bus["role"] == "slave", "input",
                V5_DIAGNOSTIC_FIELDS.index(name))
    return rows


def _legal_v2_pin(desc, signal, gpio):
    policy = desc["gpio_policy"].get(str(gpio), "unavailable")
    return (
        policy == "flexible"
        or (policy == "input_only" and signal["direction"].startswith("input"))
        or (policy == "can.cs_only" and signal["signal"] == "can.cs")
    )


def _v2_occupancy(desc, signals):
    """Calculate one independent snapshot using already flattened signals."""
    rows = {}
    for gpio, policy in desc["gpio_policy"].items():
        if policy == "unavailable":
            continue
        fixed = policy in PURPOSES
        rows[int(gpio)] = {
            "gpio": int(gpio), "owners": [policy] if fixed else [],
            "fixed": fixed, "state": "fixed" if fixed else "free",
        }
    for signal in signals:
        gpio = signal["gpio"]
        if signal["enabled"] and _legal_v2_pin(desc, signal, gpio):
            rows[gpio]["owners"].append(signal["signal"])
            rows[gpio]["state"] = "occupied"
    return [rows[gpio] for gpio in sorted(rows)]


def _fixed_pins(desc):
    rows = []
    for gpio, policy in desc["gpio_policy"].items():
        if policy not in PURPOSES:
            continue
        direction = "output" if policy.endswith(".tx") else "input" if policy.endswith(".rx") else None
        rows.append({
            "gpio": int(gpio), "owner": policy, "purpose": PURPOSES[policy],
            "read_only": True, "direction": direction,
            "notes": pin_notes(int(gpio), policy),
        })
    return sorted(rows, key=lambda row: row["gpio"])


def attachment_conflicts(mapping):
    if mapping is None or "external2" not in mapping:
        return []
    devices = [(name, mapping[name]["host"], mapping[name]["cs"] == NO_CS)
               for name in ("external", "external2") if mapping[name]["enabled"]]
    if mapping["features"]["can"]:
        devices.append(("mcp2518fd", mapping["mcp2518fd"]["host"], False))
    conflicts = []
    for index, (name, host, no_cs) in enumerate(devices):
        for peer, peer_host, peer_no_cs in devices[index + 1:]:
            if host == peer_host and (no_cs or peer_no_cs):
                conflicts.append({"host": host, "device": name if no_cs else peer,
                                  "peer": peer if no_cs else name})
    return conflicts


def build_tables_v2(desc, snapshot, candidate=None):
    candidate = candidate if candidate is not None else snapshot["candidate"]
    active_signals = v2_signals(snapshot["active"])
    candidate_signals = v2_signals(candidate) if candidate is not None else None
    current = _v2_occupancy(desc, active_signals)
    proposed = _v2_occupancy(desc, candidate_signals) if candidate_signals is not None else None
    current_owners = {row["gpio"]: row["owners"] for row in current}
    proposed_owners = {row["gpio"]: row["owners"] for row in proposed or []}

    for position, row in enumerate(active_signals):
        other = candidate_signals[position] if candidate_signals is not None else None
        choices = []
        for gpio, policy in desc["gpio_policy"].items():
            gpio = int(gpio)
            if _legal_v2_pin(desc, other or row, gpio):
                choices.append({
                    "gpio": gpio, "owners": current_owners.get(gpio, []),
                    "candidate_owners": proposed_owners.get(gpio, []) if proposed is not None else None,
                    "notes": pin_notes(gpio, policy),
                })
        row.update(
            candidate_direction=other["direction"] if other else None,
            candidate_gpio=other["gpio"] if other else None,
            candidate_enabled=other["enabled"] if other else None,
            candidates=sorted(choices, key=lambda choice: choice["gpio"]),
        )

    invalid = []
    for row in candidate_signals or []:
        if row["enabled"] and not _legal_v2_pin(desc, row, row["gpio"]):
            invalid.append({
                "signal": row["signal"], "gpio": row["gpio"],
                "reason": "fixed, unavailable or incompatible direction",
            })
    tables = {
        "fixed": _fixed_pins(desc), "editable": active_signals,
        "occupancy": current, "candidate_occupancy": proposed, "invalid_pins": invalid,
        "unavailable": sorted(int(gpio) for gpio, policy in desc["gpio_policy"].items()
                              if policy == "unavailable"),
    }
    if desc["schema"] >= 3:
        tables["attachment_conflicts"] = attachment_conflicts(candidate)
    if desc["schema"] >= 5:
        tables["spi_roles"] = {
            host: {"current": snapshot["active"]["spi"][host]["role"],
                   "candidate": candidate["spi"][host]["role"] if candidate else None}
            for host in ("2", "3")
        }
        tables["role_conflicts"] = []
        if candidate:
            for device in ("external", "external2", "mcp2518fd"):
                host = candidate[device]["host"]
                enabled = candidate["features"]["can"] if device == "mcp2518fd" else candidate[device]["enabled"]
                if enabled and candidate["spi"][str(host)]["role"] == "slave":
                    tables["role_conflicts"].append({"host": host, "device": device})
    if desc["schema"] >= 4:
        for mapping, rows in ((snapshot["active"], tables["fixed"]), (snapshot["active"], current),
                              (candidate, proposed)):
            if mapping is None:
                continue
            role = "control" if mapping["features"]["serial"] else "business" if mapping["uart1_business"] else "reserved"
            for row in rows:
                if desc["gpio_policy"].get(str(row["gpio"])) in ("uart1.tx", "uart1.rx"):
                    row["uart1_role"] = role
                    if "purpose" in row:
                        row["purpose"] = f"UART1 {role} {row['owner'][-2:].upper()}"
    return tables


class ApplyOutcomeUnknown(ValueError):
    """APPLY was sent but no valid acknowledgement establishes its outcome."""




class Device:
    def __init__(self, transport):
        self.transport = transport
        self.seq = 0
        self.gpios = {}
        self.version = 1

    def request(self, op, data=b""):
        self.seq += 1
        packet = bytes([self.version, COMMANDS.index(op)]) + data
        if len(packet) > 2048:
            raise ValueError("Profile exceeds the single-frame 2048-byte payload limit")
        def unknown_apply():
            candidate = int.from_bytes(data, "big")
            return ApplyOutcomeUnknown(
                f"APPLY result unknown for candidate ID {candidate}; reconnect and READ to check "
                "phase and candidate ID before any further action. Do not automatically resend APPLY.")

        try:
            self.transport.send(UBCPBuilder.build_request(self.seq, 8, 0, packet))
            frame = self.transport.recv_response(8, self.seq, timeout=4)
        except OSError as exc:
            if op == "apply":
                raise unknown_apply() from exc
            raise
        if not frame or not frame.is_response or not frame.payload:
            if op == "apply":
                raise unknown_apply()
            raise ValueError("No valid device-profile response")
        status, *rest = frame.payload
        data = bytes(rest)
        if status == 2 and data and len(data) == 1 + 4 * data[0]:
            problems = []
            signals = {1: SIGNALS, 2: V2_SIGNALS, 3: V3_SIGNALS, 4: V3_SIGNALS, 5: V5_DIAGNOSTIC_FIELDS}[self.version]
            for reason, subject, pin, other in struct.iter_unpack("4B", data[1:]):
                if reason == 1: message = "unknown feature bits"
                elif reason == 2: message = "enable serial or control_tcp"
                elif reason == 3: message = (FEATURES[subject] if subject < len(FEATURES) else str(subject)) + " requires wifi"
                elif reason == 4: message = "save Wi-Fi credentials before disabling serial"
                elif reason == 5:
                    message = f"{signals[subject] if subject < len(signals) else subject} cannot use GPIO{pin} ({self.gpios.get(str(pin), 'unavailable')})"
                elif reason == 6: message = f"{signals[subject] if subject < len(signals) else subject} conflicts with {signals[other] if other < len(signals) else other} on GPIO{pin}"
                elif reason == 7 and subject == 18 and self.version >= 4: message = "invalid UART1 business enable flag"
                elif reason == 7 and self.version >= 5 and subject in (21, 22):
                    message = f"SPI{subject - 19} requires a valid role and single-line operation in slave mode"
                elif reason == 7: message = "invalid SPI instance, host or parameter"
                elif reason == 8: message = "attachment requires an enabled SPI host"
                elif reason == 9 and self.version >= 3:
                    message = f"{signals[subject]} requires exclusive SPI{pin} without CS; conflicts with {signals[other]}" if subject < len(signals) and other < len(signals) else "A no-CS device requires an exclusive SPI host"
                elif reason == 9: message = "CS is reserved for MCP2518FD"
                elif reason == 10 and self.version >= 4: message = "UART1 serial control and ordinary UART1 are mutually exclusive"
                elif reason == 11 and self.version >= 5:
                    name = signals[subject] if subject < len(signals) else str(subject)
                    message = f"{name} requires a master controller; SPI{pin} is a slave"
                else: message = f"unknown diagnostic {reason}"
                problems.append(message)
            raise ValueError("\n".join(problems))
        if status:
            reasons = {1: "profile persistence failed", 2: "invalid payload", 3: "trial expired",
                       4: "transaction busy", 6: "extension unsupported",
                       12: "confirm using the newly enabled control interface",
                       14: "stale revision or candidate ID; read the device again",
                       15: "profile version unsupported"}
            raise ValueError(f"{op}: 0x{status:02x} {reasons.get(status, 'device error')}")
        return data

    def descriptor(self, version=None):
        if version is not None and version not in PROFILE_SIZES:
            raise ValueError("profile version unsupported")
        for self.version in ((version,) if version is not None else reversed(PROFILE_SIZES)):
            try:
                data = self.request("describe")
                break
            except ValueError as exc:
                if version is not None or self.version == 1 or not str(exc).startswith(("describe: 0x0f ", "describe: 0x06 ")):
                    raise
        if self.version >= 2:
            size = PROFILE_SIZES[self.version]
            policies_start = 11 + size
            if len(data) != policies_start + 40 or data[0] != self.version:
                raise ValueError(f"Unsupported v{self.version} board descriptor")
            capabilities, size = struct.unpack_from(">IH", data, 5)
            if size != PROFILE_SIZES[self.version] or capabilities & 3 != 3:
                raise ValueError("Unsupported capabilities or mapping size")
            if any(v >= len(POLICIES) for v in data[policies_start:]):
                raise ValueError("Unsupported GPIO policy")
            decode_mapping(data[11:policies_start])
            self.gpios = {str(i): POLICIES[v] for i, v in enumerate(data[policies_start:])}
            return {"schema": self.version, "board": data[1:5].decode("ascii"),
                    "capabilities": capabilities, "gpio_policy": self.gpios}
        if len(data) != 5 + SIZE + 40 or data[0] != 1:
            raise ValueError("Unsupported board descriptor")
        if any(v >= len(POLICIES) for v in data[5 + SIZE:]):
            raise ValueError("Unsupported GPIO policy")
        self.gpios = {str(i): POLICIES[v] for i, v in enumerate(data[5 + SIZE:])}
        return {"schema": 1, "board": data[1:5].decode("ascii"), "gpio_policy": self.gpios}

    def snapshot(self):
        data = self.request("read")
        size = PROFILE_SIZES[self.version]
        if len(data) not in (13 + size, 13 + 2 * size):
            raise ValueError("Invalid device-profile snapshot")
        phase, revision, candidate, confirmed = struct.unpack_from(">BIII", data)
        if (phase >= len(PHASES) or not revision
                or bool(candidate) != (phase != 0)
                or len(data) != 13 + size * (2 if candidate else 1)):
            raise ValueError("Invalid device-profile snapshot state")
        return {"revision": revision, "phase": PHASES[phase], "candidate_id": candidate,
                "confirmed_id": confirmed, "active": decode_mapping(data[13:13 + size]),
                "candidate": decode_mapping(data[13 + size:]) if candidate else None}


def main(transport_factory=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM4", help="COM port or socket://HOST:9500")
    parser.add_argument("--baud", default=115200, type=int)
    parser.add_argument("--version", choices=("auto", *map(str, PROFILE_SIZES)), default="auto")
    subs = parser.add_subparsers(dest="op", required=True)
    for op in ("show", "pins"):
        sub = subs.add_parser(op, help="show profile and derived read-only pin tables")
        output = sub.add_mutually_exclusive_group()
        output.add_argument("--human", action="store_true", help="human-readable pin tables")
        output.add_argument("--json", action="store_true", help="structured profile and pin tables")
        sub.add_argument("--file", type=Path, help="preview an exported candidate without writing the device")
    subs.add_parser("export").add_argument("file", type=Path)
    for op in ("check", "save"):
        sub = subs.add_parser(op)
        sub.add_argument("file", type=Path)
        sub.add_argument("--human", action="store_true", help="also show current and proposed pin tables")
    for op in ("cancel", "apply", "confirm"):
        subs.add_parser(op).add_argument("id", type=int)
    args = parser.parse_args()
    with (transport_factory or MCPTransport)(args.port, args.baud) as transport:
        device = Device(transport)
        desc = device.descriptor(None if args.version == "auto" else int(args.version))
        if args.op in ("show", "pins", "export"):
            snapshot = device.snapshot()
            if args.op in ("show", "pins"):
                config = load_config(args.file, desc) if args.file else None
                tables = build_tables(desc, snapshot, config)
                if args.human or (args.op == "pins" and not args.json):
                    print(render_human(desc, snapshot, tables, "imported file" if config else "saved candidate"))
                else:
                    result = {**desc, **snapshot, "tables": tables}
                    if config is not None:
                        result["preview"] = config
                    print(json.dumps(result, indent=2))
            else:
                config = {**desc, "revision": snapshot["revision"], **snapshot["active"]}
                args.file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        elif args.op in ("check", "save"):
            config = load_config(args.file, desc)
            if args.human:
                snapshot = device.snapshot()
                print(render_human(desc, snapshot, build_tables(desc, snapshot, config), "submitted file"))
            data = device.request(args.op, struct.pack(">I", config["revision"]) + encode_mapping(config))
            if args.op == "save":
                print("candidate_id =", struct.unpack(">I", data)[0])
            else:
                print("OK")
        else:
            device.request(args.op, struct.pack(">I", args.id))
            print("Trial requested. Reconnect and confirm within 120 s." if args.op == "apply" else "OK")
