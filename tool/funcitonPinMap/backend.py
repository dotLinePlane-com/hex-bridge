"""Device profile editing without Tk dependencies or implicit device writes.

All I/O is synchronous; the GUI runs calls on its single worker. The CLI owns
the wire format, profile file validation and derived pin tables.
"""
from copy import deepcopy
import sys
import json
from pathlib import Path
import struct
import threading


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "script"))
import hexbridge_profile as cli
ApplyOutcomeUnknown = cli.ApplyOutcomeUnknown
FEATURES = cli.FEATURES
SIGNALS = cli.SIGNALS
DIRECTIONS = cli.DIRECTIONS


def _hardware_identity(device):
    """GET_INFO's factory MAC-derived serial and model, independent of profile."""
    device.seq += 1
    device.transport.send(cli.UBCPBuilder.build_request(device.seq, 1, 0, b""))
    frame = device.transport.recv_response(1, device.seq, timeout=4)
    if (not frame or not frame.is_response or len(frame.payload) != 17
            or frame.payload[0] != 0):
        raise ValueError("无法读取设备硬件身份；请重新读取设备")
    return bytes(frame.payload[4:12]).hex()


class ProfileService:
    def __init__(self, transport_factory=None, device_factory=None, identity_reader=None):
        self.transport_factory = transport_factory or cli.MCPTransport
        self.device_factory = device_factory or cli.Device
        self.identity_reader = identity_reader or _hardware_identity
        self.descriptor = self.snapshot = self.draft = self.connection = None
        self.identity = None
        self._baseline = None
        self._cs_memory = {}
        self._io_lock = threading.Lock()
        self.requires_reconnect = False

    @property
    def dirty(self):
        return self.draft is not None and self.draft != self._baseline

    def _require_read(self):
        if self.snapshot is None:
            raise ValueError("请先读取设备")

    def _config(self, mapping, revision=None):
        return {**deepcopy(self.descriptor),
                "revision": self.snapshot["revision"] if revision is None else revision,
                **deepcopy(mapping)}

    def _reset_cs_memory(self):
        """A replacement draft owns its own history, including an empty history."""
        self._cs_memory = {name: self.draft[name]["cs"]
                           for name in ("external", "external2")
                           if name in self.draft and self.draft[name]["cs"] != cli.NO_CS}

    def _require_spi_device(self, instance):
        if instance not in ("external", "external2"):
            raise ValueError("Invalid SPI device")
        if instance == "external2" and (self.descriptor["schema"] < 3 or
                                       not self.descriptor.get("capabilities", 0) & cli.CAP_DUAL_SPI):
            raise ValueError("Device does not support a second SPI device")

    def _default_cs(self, instance):
        # A newly loaded no-CS draft has no remembered pin. Prefer a legal,
        # unused output, retaining the normal conflict workflow if all are used.
        candidates = sorted(int(gpio) for gpio, policy in self.descriptor["gpio_policy"].items()
                            if policy == "flexible")
        if not candidates:
            raise ValueError("设备没有可用的片选输出 GPIO")
        tables = cli.build_tables(self.descriptor, self.snapshot, self.draft)
        occupied = {row["gpio"] for row in tables["candidate_occupancy"] or [] if row["owners"]}
        free = [gpio for gpio in candidates if gpio not in occupied]
        choices = free or candidates
        preferred = 27 if instance == "external" else 26
        return preferred if preferred in choices else choices[0]

    def view(self):
        self._require_read()
        return deepcopy({"descriptor": self.descriptor, "snapshot": self.snapshot,
                         "draft": self.draft, "dirty": self.dirty,
                         "connection": self.connection, "identity": self.identity,
                         "source_revision": self.draft["revision"],
                         "requires_reconnect": self.requires_reconnect,
                         "tables": cli.build_tables(self.descriptor, self.snapshot),
                         "preview_tables": cli.build_tables(self.descriptor, self.snapshot, self.draft)})

    def read(self, port, baud=115200, discard_draft=False):
        preserve_draft = self.dirty and self.requires_reconnect and not discard_draft
        if self.dirty and not discard_draft and not preserve_draft:
            raise ValueError("存在未保存草稿；请先导出，或确认丢弃草稿后重新读取")
        port = str(port).strip()
        if not port or type(baud) is not int or baud <= 0:
            raise ValueError("请输入连接地址和有效波特率")
        if not self._io_lock.acquire(blocking=False):
            raise ValueError("设备操作正在进行")
        try:
            with self.transport_factory(port, baud) as transport:
                device = self.device_factory(transport)
                identity = self.identity_reader(device)
                descriptor, snapshot = device.descriptor(), device.snapshot()
            if preserve_draft and (identity != self.identity or descriptor != self.descriptor):
                raise ValueError("重连设备身份或能力已改变；草稿已保留，请导出后重新读取")
            # Publish only a complete successful read; failed connections retain drafts.
            self.descriptor, self.snapshot, self.identity = descriptor, snapshot, identity
            self.connection = {"port": port, "baud": baud}
            self.requires_reconnect = False
            if not preserve_draft:
                self.draft = self._config(snapshot["active"])
                self._baseline = deepcopy(self.draft)
                self._reset_cs_memory()
            return self.view()
        finally:
            self._io_lock.release()

    def set_feature(self, name, enabled):
        self._require_read()
        if name not in FEATURES or type(enabled) is not bool:
            raise ValueError("无效功能开关")
        self.draft["features"][name] = enabled
        if name == "serial" and enabled and "uart1_business" in self.draft:
            self.draft["uart1_business"] = False
        return self.view()

    def set_pin(self, signal, gpio):
        self._require_read()
        schema = self.descriptor["schema"]
        allowed = [*cli.V5_SIGNALS, *cli.V6_SIGNALS] if schema >= 6 else cli.V5_SIGNALS if schema >= 5 else cli.V3_SIGNALS if schema >= 3 else cli.V2_SIGNALS if schema == 2 else SIGNALS
        if signal not in allowed or type(gpio) is not int or not 0 <= gpio <= 255:
            raise ValueError("Invalid signal or GPIO")
        if signal.startswith(('i2c', 'gpio.')):
            cap = cli.CAP_I2C if signal.startswith('i2c') else cli.CAP_GPIO
            if not self.descriptor.get('capabilities', 0) & cap:
                raise ValueError('当前固件不支持此 Stage2 配置')
        if signal.startswith("i2c"):
            bus, field = signal.split(".")
            self.draft["i2c"][bus[-1]][field] = gpio
        elif signal.startswith("gpio."):
            self.draft["gpio_lines"][signal.split(".")[1]]["pin"] = gpio
        elif signal in ("external.cs", "external2.cs"):
            instance = signal.split(".")[0]
            self._require_spi_device(instance)
            if gpio == cli.NO_CS:
                return self.set_parameter(instance, "use_cs", False)
            self.draft[instance]["cs"] = gpio
            self._cs_memory[instance] = gpio
        elif schema == 1 or signal in self.draft["pins"]:
            self.draft["pins"][signal] = gpio
        elif signal.startswith("spi"):
            bus, role = signal.split(".")
            self.draft["spi"][bus[-1]][role] = gpio
        else:
            self.draft["mcp2518fd"]["cs" if signal == "can.cs" else "int"] = gpio
        return self.view()

    def set_parameter(self, instance, field, value):
        self._require_read()
        if instance in ("i2c0", "i2c1") or instance.startswith("gpio."):
            kind = "i2c" if instance.startswith("i2c") else "gpio_lines"
            capability = cli.CAP_I2C if kind == "i2c" else cli.CAP_GPIO
            if self.descriptor["schema"] < 6 or not self.descriptor.get("capabilities", 0) & capability:
                raise ValueError("当前固件不支持此 Stage2 配置")
            key = instance[-1] if kind == "i2c" else instance.split(".")[1]
            if key not in self.draft[kind] or field not in self.draft[kind][key]:
                raise ValueError("Invalid Stage2 instance or field")
            proposed = deepcopy(self.draft)
            proposed[kind][key][field] = value
            if kind == "gpio_lines" and field == "trigger":
                proposed[kind][key]["debounce_ms"] = 10 if value != "none" else 0
            cli.encode_mapping(proposed)
            self.draft = proposed
            return self.view()
        if instance == "uart1":
            if self.descriptor["schema"] < 4 or not self.descriptor.get("capabilities", 0) & cli.CAP_UART1_BUSINESS:
                raise ValueError("当前固件不支持 UART1 普通串口")
            if field != "enabled" or type(value) is not bool:
                raise ValueError("无效的 UART1 普通串口开关")
            if value and self.draft["features"]["serial"]:
                raise ValueError("请先关闭 UART1 串口控制")
            self.draft["uart1_business"] = value
            return self.view()
        if self.descriptor["schema"] < 2 or not self.descriptor.get("capabilities", 0) & 4:
            raise ValueError("Device does not support dual SPI configuration")
        if instance in ("external", "external2"):
            self._require_spi_device(instance)
        if instance in ("external", "external2") and field == "use_cs":
            if (self.descriptor["schema"] < 3 or
                    not self.descriptor.get("capabilities", 0) & cli.CAP_OPTIONAL_CS):
                raise ValueError("Device does not support optional SPI chip select")
            if type(value) is not bool:
                raise ValueError("use_cs must be boolean")
            cs = self.draft[instance]["cs"]
            if value and cs == cli.NO_CS:
                self.draft[instance]["cs"] = (self._cs_memory[instance] if instance in self._cs_memory
                                                else self._default_cs(instance))
            elif not value and cs != cli.NO_CS:
                self._cs_memory[instance] = cs
                self.draft[instance]["cs"] = cli.NO_CS
            return self.view()
        if instance in ("spi2", "spi3") and field == "role":
            capability = 0x80 if instance == "spi2" else 0x100
            if (self.descriptor["schema"] < 5 or
                    not self.descriptor.get("capabilities", 0) & capability):
                raise ValueError("当前固件不支持此控制器的从机角色")
            if value not in ("master", "slave"):
                raise ValueError("Invalid SPI role")
            bus = self.draft["spi"][instance[-1]]
            bus["role"] = value
            if value == "slave":
                bus["width"] = 1
        elif instance in ("spi2", "spi3") and field in ("enabled", "width"):
            if field == "enabled" and type(value) is not bool:
                raise ValueError("enabled must be boolean")
            if field == "width" and (type(value) is not int or value not in (1, 4) or (value == 4 and not self.descriptor["capabilities"] & 8)):
                raise ValueError("Unsupported SPI width")
            if field == "width" and value != 1 and self.draft["spi"][instance[-1]].get("role") == "slave":
                raise ValueError("SPI 从机仅支持单线")
            self.draft["spi"][instance[-1]][field] = value
        elif instance in ("external", "external2", "mcp2518fd") and field == "host" and type(value) is int and value in (2, 3):
            self.draft[instance][field] = value
        elif instance in ("external", "external2") and field == "enabled" and type(value) is bool:
            if value and self.draft[instance]["cs"] == cli.NO_CS and not self.descriptor["capabilities"] & cli.CAP_OPTIONAL_CS:
                gpio = self._default_cs(instance)
                self.draft[instance]["cs"] = gpio
                self._cs_memory[instance] = gpio
            self.draft[instance][field] = value
        else:
            raise ValueError("Invalid SPI instance or parameter")
        return self.view()

    def reset_draft(self):
        self._require_read()
        self.draft = self._config(self.snapshot["active"])
        self._baseline = deepcopy(self.draft)
        self._reset_cs_memory()
        return self.view()

    def load_candidate(self):
        self._require_read()
        if self.snapshot["candidate"] is None:
            raise ValueError("设备没有已暂存候选")
        self.draft = self._config(self.snapshot["candidate"])
        self._reset_cs_memory()
        return self.view()

    def import_config(self, path):
        self._require_read()
        self.draft = deepcopy(cli.load_config(Path(path), self.descriptor))
        self._reset_cs_memory()
        return self.view()

    def export_config(self, path):
        self._require_read()
        cli.encode_mapping(self.draft)
        Path(path).write_text(json.dumps(self.draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self.view()

    def _operate(self, op):
        self._require_read()
        if self.requires_reconnect:
            raise ValueError("已请求试用重启，请重新读取设备后继续")
        if not self._io_lock.acquire(blocking=False):
            raise ValueError("设备操作正在进行")
        try:
            with self.transport_factory(self.connection["port"], self.connection["baud"]) as transport:
                device = self.device_factory(transport)
                if self.identity_reader(device) != self.identity:
                    raise ValueError("硬件设备已改变，禁止将旧草稿写入新设备；请重新读取")
                desc, latest = device.descriptor(), device.snapshot()
                if desc != self.descriptor:
                    raise ValueError("设备板型或引脚策略已改变，请重新读取")
                if latest != self.snapshot:
                    self.snapshot = latest
                    raise ValueError("设备修订号、阶段或候选已改变；已刷新设备快照并保留草稿，请比较差异后合并")
                if op in ("check", "save"):
                    if self.draft["revision"] != latest["revision"]:
                        raise ValueError("草稿修订号已过期，请重新读取或重新导出配置")
                    payload = struct.pack(">I", self.draft["revision"]) + cli.encode_mapping(self.draft)
                else:
                    phase = "trial" if op == "confirm" else "staged"
                    if latest["phase"] != phase or not latest["candidate_id"]:
                        raise ValueError("确认需要试用阶段" if op == "confirm" else "操作需要已暂存候选阶段")
                    payload = struct.pack(">I", latest["candidate_id"])
                try:
                    data = device.request(op, payload)
                except ApplyOutcomeUnknown as exc:
                    self.requires_reconnect = True
                    raise ApplyOutcomeUnknown(
                        f"APPLY 结果未知（候选 ID {latest['candidate_id']}），草稿已保留。"
                        "请等待设备恢复并重新读取，核对阶段及候选 ID；不要重复应用。") from exc
                if op == "check":
                    return self.view()
                if op == "apply":
                    # The response acknowledges a reboot request, not entry into trial.
                    self.requires_reconnect = True
                    return self.view()
                if op == "save" and len(data) != 4:
                    raise ValueError("无效候选 ID 响应；请重新读取设备")
                fresh = device.snapshot()
                if op == "save" and fresh["candidate_id"] != struct.unpack(">I", data)[0]:
                    raise ValueError("保存后的候选已改变，请重新读取设备")
                was_dirty = self.dirty
                self.snapshot = fresh
                if op == "save":
                    self.draft["revision"] = fresh["revision"]
                    self._baseline = deepcopy(self.draft)
                elif not was_dirty:
                    self.reset_draft()
                # Existing unsaved drafts retain their original revision after a
                # transaction, so a later write cannot silently rebase them.
                return self.view()
        finally:
            self._io_lock.release()

    def check(self):
        return self._operate("check")

    def save(self):
        self._require_read()
        preview = self.view()["preview_tables"]
        if preview.get("role_conflicts"):
            raise ValueError("从机总线仍挂载已启用设备；请停用设备或迁到主机总线")
        if self.descriptor["schema"] >= 5 and preview.get("invalid_pins"):
            raise ValueError("请修正引脚方向或选择从机片选输入 GPIO")
        return self._operate("save")

    def cancel(self):
        return self._operate("cancel")

    def apply(self):
        return self._operate("apply")

    def confirm(self):
        return self._operate("confirm")
