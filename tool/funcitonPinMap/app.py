"""Chinese Tk desktop editor for the HEX-Bridge device profile."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from collections import deque
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from backend import ProfileService, ApplyOutcomeUnknown, SIGNALS
from overview import PinOverview

APP_VERSION = (Path(__file__).resolve().parents[2] / "version.txt").read_text(encoding="ascii").strip()

FEATURE_NAMES = {
    "serial": "UART1 串口控制", "control_tcp": "UBCP 网络控制（TCP 9500）", "can": "外置 MCP2518FD CAN / CAN FD",
    "uart": "UART2 普通串口", "wifi": "Wi-Fi STA", "tcp": "TCP 业务",
    "udp": "UDP 业务", "websocket": "WebSocket 业务", "dap": "DAPLink / SWD",
}
SIGNAL_NAMES = {
    "uart.tx": "UART2 发送 TX", "uart.rx": "UART2 接收 RX",
    "can.sck": "MCP2518FD SPI 时钟 SCK", "can.mosi": "MCP2518FD SPI 输出 MOSI",
    "can.miso": "MCP2518FD SPI 输入 MISO", "can.cs": "MCP2518FD 片选 CS", "can.int": "MCP2518FD 中断 INT",
    "dap.swclk": "DAP 时钟 SWCLK", "dap.swdio": "DAP 数据 SWDIO",
    **{f"spi{host}.{role}": f"SPI{host} {role.upper()}"
       for host in (2, 3) for role in ("sck", "mosi", "miso", "io2", "io3", "slave_cs")},
    "external.cs": "普通 SPI 设备 1 片选 CS",
    "external2.cs": "普通 SPI 设备 2 片选 CS",
    "spi2.slave_cs": "SPI2 从机片选 CS", "spi3.slave_cs": "SPI3 从机片选 CS",
}
OWNER_NAMES = {
    "uart0.tx": "UART0 烧录 / 日志 TX", "uart0.rx": "UART0 烧录 / 日志 RX",
    "uart1.tx": "UART1 控制 TX", "uart1.rx": "UART1 控制 RX", "flash": "内部 Flash",
    "psram": "内部 PSRAM", "spi2": "外部 SPI2", "eeprom": "板载 EEPROM", "strap": "启动配置",
    **SIGNAL_NAMES,
}
ROLE_NAMES = {"master": "主机", "slave": "从机"}
DIRECTION_NAMES = {"output": "输出", "input": "输入", "input_interrupt": "中断输入", "bidirectional": "双向"}
PHASE_NAMES = {"confirmed": "已确认", "staged": "已暂存候选", "armed": "等待重启试用", "trial": "试用中，需限时确认"}
NOTE_NAMES = {
    "CAN.CS only; external 10k pull-up, maintain boot high level": "仅 CAN 片选；外部 10kΩ 上拉，启动时保持高电平",
    "input only; no internal pull resistors, external bias required": "仅输入，无内部上下拉，需要外部偏置",
    "MTDI; external 4.7k pull-up, maintain boot high for PSRAM": "MTDI：外部 4.7kΩ 上拉，启动保持高电平以支持 PSRAM",
}


def owners_text(owners):
    return "、".join(OWNER_NAMES.get(o, o) for o in owners) or "空闲"


def gpio_text(gpio):
    return "不使用 CS（主机独占）" if gpio == 255 else f"GPIO {gpio}"


def saved_pin_text(pin, enabled):
    if pin == 255:
        return "无 CS"
    return gpio_text(pin) if enabled else "关闭"


def state_difference(active, candidate, draft):
    """The control shows the draft; annotate only meaningful differences."""
    def display(value):
        return ("开" if value else "关") if type(value) is bool else str(value)
    if candidate is not None and active == candidate and active != draft:
        return f"当前/候选 {display(active)}"
    details = [f"当前 {display(active)}"] if active != draft else []
    if candidate is not None and (candidate != active or candidate != draft):
        details.append(f"候选 {display(candidate)}")
    return " / ".join(details)


class ProfileApp(ttk.Frame):
    """All service calls run on one worker; only the Tk thread changes widgets."""

    def __init__(self, root, service=None):
        super().__init__(root, padding=14)
        self.root = root
        self.service = service if service is not None else ProfileService()
        self.view = None
        self.busy = False
        self._closed = False
        self._rendering = False
        self._results = queue.Queue()
        self.history = deque(maxlen=8)
        self.feature_vars = {}
        self.pin_vars = {}
        self.pin_boxes = {}
        self._pin_choices = {}
        self.parameter_vars = {}
        self.parameter_widgets = {}
        self.parameter_states = {}
        self.buttons = {}
        self.port_var = tk.StringVar(value="COM3")
        self.baud_var = tk.StringVar(value="115200")
        self.status_var = tk.StringVar(value="未读取设备 · 首次读取仅查询设备")
        self.identity_var = tk.StringVar(value="尚未读取设备")
        self.draft_var = tk.StringVar()
        self.warning_var = tk.StringVar()
        root.title(f"HEX-Bridge {APP_VERSION} · 功能与引脚配置")
        root.geometry("1180x700")
        root.minsize(980, 650)
        self.pack(fill="both", expand=True)
        self._build()
        self.port_var.trace_add("write", lambda *_: self._update_controls())
        self.baud_var.trace_add("write", lambda *_: self._update_controls())
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._poll_id = root.after(60, self._poll_queue)
        self._update_controls()

    def _button(self, parent, key, text, command, **pack):
        if key in ("cancel", "apply", "confirm", "load_candidate"):
            slot = ttk.Frame(parent)
            slot.pack(**pack)
            button = ttk.Button(slot, text=text, command=command)
            slot.configure(width=button.winfo_reqwidth(), height=button.winfo_reqheight())
            slot.pack_propagate(False)
            button.pack()
            self.buttons[key] = button
            return button
        button = ttk.Button(parent, text=text, command=command)
        button.pack(**pack)
        self.buttons[key] = button
        return button

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(6, weight=1)
        ttk.Label(self, text="功能与引脚配置", font=("Microsoft YaHei UI", 16, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 3))
        connection = ttk.LabelFrame(self, text="控制连接", padding=6)
        connection.grid(row=2, column=0, sticky="ew")
        ttk.Label(connection, text="串口 / 网络地址").pack(side="left")
        self.port_box = ttk.Combobox(connection, textvariable=self.port_var, width=32)
        try:
            from serial.tools import list_ports
            self.port_box["values"] = [p.device for p in list_ports.comports()]
        except ImportError:
            pass
        self.port_box.pack(side="left", padx=(8, 16))
        ttk.Label(connection, text="波特率").pack(side="left")
        self.baud_box = ttk.Combobox(connection, textvariable=self.baud_var, values=("115200", "460800", "921600"), width=10)
        self.baud_box.pack(side="left", padx=8)
        self._button(connection, "read", "读取 / 刷新设备", self.read_device, side="left", padx=6)
        ttk.Label(connection, text="支持 socket://设备IP:9500").pack(side="left", padx=8)
        device = ttk.Frame(self)
        device.grid(row=3, column=0, sticky="ew", pady=(5, 2))
        ttk.Label(device, textvariable=self.identity_var, font=("Microsoft YaHei UI", 10, "bold")).pack(side="left")
        self._button(device, "device_details", "设备详情", self.show_device_details, side="right")
        ttk.Label(device, textvariable=self.draft_var).pack(side="right", padx=10)
        self.overview = PinOverview(self)
        self.overview.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=6, column=0, sticky="nsew")
        self.function_tab, edit = self._scrolling_tab("  功能控制  ")
        self.pin_tab, pins = self._scrolling_tab("  引脚配置  ")
        self.feature_groups = {}
        group_layout = ttk.Frame(edit)
        group_layout.pack(fill="x", pady=(0, 6))
        group_layout.columnconfigure((0, 1), weight=1, uniform="feature")
        for key, title in (("management", "管理入口"), ("network", "网络连接与服务"),
                           ("serial", "串口与调试"), ("spi", "SPI 总线与设备")):
            frame = ttk.LabelFrame(group_layout, text=title, padding=(8, 5))
            row, column, span = {"management": (0, 0, 1), "network": (0, 1, 1),
                                 "serial": (1, 0, 2), "spi": (2, 0, 2)}[key]
            frame.grid(row=row, column=column, columnspan=span, sticky="nsew", padx=(0, 4) if key == "management" else 0, pady=(0, 6))
            self.feature_groups[key] = frame
        self.feature_checks = []
        self.feature_widgets = {}
        self.feature_states = {}
        ttk.Style(self).configure("Conflict.TCheckbutton", foreground="#b42318")
        ttk.Style(self).map("Conflict.TCheckbutton", foreground=[("disabled", "#b42318")])
        ttk.Style(self).configure("Conflict.TLabel", foreground="#b42318")
        groups = {"serial": ("management", 0), "control_tcp": ("management", 1),
                  "wifi": ("network", 0), "tcp": ("network", 1), "udp": ("network", 2), "websocket": ("network", 3),
                  "uart": ("serial", 1), "dap": ("serial", 2), "can": ("spi", 0)}
        for key, label in FEATURE_NAMES.items():
            group, column = groups[key]
            var = tk.BooleanVar()
            self.feature_vars[key] = var
            cb = ttk.Checkbutton(self.feature_groups[group], text=label, variable=var, command=lambda k=key: self._edit_feature(k))
            cb.grid(row=0, column=column, sticky="w", padx=8, pady=3)
            self.feature_checks.append(cb)
            self.feature_widgets[key] = cb
            state = ttk.Label(self.feature_groups[group], width=19 if group != "network" else 11, anchor="w")
            state.grid(row=1 if group != "spi" else 0, column=column if group != "spi" else 1, sticky="w", padx=8)
            self.feature_states[key] = state
        self.management_hint_var = tk.StringVar()
        self.management_summary_var = tk.StringVar()
        self.management_hint = ttk.Label(self.feature_groups["management"], textvariable=self.management_summary_var, width=51, foreground="#9a4800")
        self.management_hint.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(2, 0))
        self.management_hint.bind("<Button-1>", lambda event: self.show_function_details())
        self.management_hint.bind("<Return>", lambda event: self.show_function_details())
        self.management_hint.bind("<space>", lambda event: self.show_function_details())
        self.uart1_business_var = tk.BooleanVar()
        self.uart1_business_check = ttk.Checkbutton(self.feature_groups["serial"], text="UART1 普通串口", variable=self.uart1_business_var, command=self._edit_uart1_business)
        self.uart1_business_check.grid(row=0, column=0, sticky="w", padx=8, pady=3)
        self.uart1_state = ttk.Label(self.feature_groups["serial"], width=35)
        self.uart1_state.grid(row=1, column=0, sticky="w", padx=8)
        self.uart1_role_var = tk.StringVar(value="TX GPIO4 · RX GPIO34；读取设备后显示 UART1 角色。")
        ttk.Label(self.feature_groups["serial"], textvariable=self.uart1_role_var, foreground="#526475", width=120).grid(row=2, column=0, columnspan=3, sticky="w", padx=8)
        # CAN has one enable control, in the same group as its SPI host.
        self.extension = ttk.Frame(self.feature_groups["spi"])
        self.extension.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.function_details_button = ttk.Button(edit, text="状态与诊断详情", command=self.show_function_details)
        self.function_details_button.pack(anchor="w", pady=(0, 4))
        self.planned_var = tk.BooleanVar(value=False)
        self.planned_toggle = ttk.Checkbutton(edit, variable=self.planned_var, command=self._toggle_planned)
        self.planned_toggle.pack(anchor="w", pady=5)
        self.planned_frame = ttk.Frame(edit)
        self.twai_var = tk.BooleanVar(value=False)
        self.twai_check = ttk.Checkbutton(self.planned_frame,
            text="片上经典 CAN / TWAI（阶段 2 未实现，不可启用）", variable=self.twai_var, state="disabled")
        self._render_catalog(None)
        ttk.Label(pins, text="交换接线时可先选用已占用的 GPIO，再调整另一信号。", wraplength=1000).pack(anchor="w", pady=(0, 6))
        self.mapping_frame = ttk.LabelFrame(pins, text="已启用的信号", padding=8)
        self.mapping_frame.pack(fill="x")
        for col, text in enumerate(("信号", "方向", "草稿 GPIO")):
            ttk.Label(self.mapping_frame, text=text, font=("Microsoft YaHei UI", 9, "bold")).grid(row=0, column=col, sticky="w", padx=8, pady=3)
        self.actual_heading = ttk.Label(self.mapping_frame, text="当前接线", width=18, font=("Microsoft YaHei UI", 9, "bold"))
        self.actual_heading.grid(row=0, column=3, sticky="w", padx=8, pady=3)
        self.mapping_labels = {}
        self.visible_signals = []
        self._make_signal_rows(())
        self.mapping_frame.columnconfigure(2, weight=1)
        self.no_signals = ttk.Label(pins, text="读取设备后显示已启用功能的可配置引脚。")
        self.no_signals.pack(anchor="w", pady=8)
        self.fixed_var = tk.BooleanVar(value=False)
        self.fixed_toggle = ttk.Checkbutton(pins, text="固定引脚说明 · 只读", variable=self.fixed_var,
            command=lambda: self._toggle_section(self.fixed_frame, self.fixed_var, before=self.occupancy_toggle))
        self.fixed_toggle.pack(anchor="w", pady=(10, 3))
        self.fixed_frame = ttk.Frame(pins)
        self.fixed_tree = self._tree(self.fixed_frame, [("gpio", "引脚", 90), ("purpose", "固定用途", 260), ("direction", "方向", 90), ("notes", "电气要求", 490)])
        ttk.Label(self.fixed_frame, text="固定引脚及策略来自当前设备描述，不能通过 JSON 导入修改。UART1 始终在此显示；v1 外接 SPI2 为固定接线。").pack(anchor="w", pady=5)
        self.occupancy_var = tk.BooleanVar(value=False)
        self.occupancy_toggle = ttk.Checkbutton(pins, text="当前 / 设备候选 / 草稿占用明细", variable=self.occupancy_var,
            command=lambda: self._toggle_section(self.occupancy_frame, self.occupancy_var))
        self.occupancy_toggle.pack(anchor="w", pady=(8, 3))
        self.occupancy_frame = ttk.Frame(pins)
        self.occupancy_tree = self._tree(self.occupancy_frame, [("gpio", "引脚", 80), ("current", "当前生效占用", 270), ("candidate", "设备候选占用", 270), ("draft", "本地草稿预览", 270)])
        ttk.Label(self.occupancy_frame, text="草稿预览不会改变硬件；同一 GPIO 上多个信号以“冲突”标记。未引出引脚不可分配。").pack(anchor="w", pady=5)
        self.occupancy_tree.tag_configure("conflict", foreground="#b42318", background="#fff0ef")
        self.occupancy_tree.tag_configure("fixed", background="#edf2f7")
        self.occupancy_tree.tag_configure("unavailable", foreground="#818a96")
        notice = ttk.Frame(self)
        notice.grid(row=7, column=0, sticky="ew", pady=2)
        notice.columnconfigure(0, weight=1)
        self.warning_label = ttk.Label(notice, textvariable=self.warning_var, foreground="#b42318", width=1)
        self.warning_label.grid(row=0, column=0, sticky="ew")
        self.warning_details = ttk.Button(notice, text="查看提示", command=self._show_warnings)
        self.warning_details.grid(row=0, column=1)
        notice.rowconfigure(0, minsize=self.warning_details.winfo_reqheight())
        self.warning_details.grid_remove()
        files = ttk.Frame(self)
        files.grid(row=8, column=0, sticky="ew", pady=2)
        for key, label, callback in (("import", "导入 JSON 到草稿", self.import_config), ("export", "导出草稿 JSON", self.export_config), ("reset", "从当前映射重建草稿", self.reset_draft), ("load_candidate", "载入设备候选到草稿", self.load_candidate)):
            self._button(files, key, label, callback, side="left", padx=(0, 8))
        actions = ttk.Frame(self)
        actions.grid(row=9, column=0, sticky="ew", pady=2)
        for key, label in (("check", "1. 预检草稿"), ("save", "2. 保存候选"), ("cancel", "取消设备候选"), ("apply", "3. 重启并试用"), ("confirm", "4. 确认试用配置")):
            self._button(actions, key, label, lambda k=key: self.run_action(k), side="left", padx=(0, 8))
        ttk.Label(self, textvariable=self.status_var, width=1, foreground="#185c80").grid(row=10, column=0, sticky="ew", pady=(3, 2))

    def _show_warnings(self):
        messages = [self.warning_var.get(), *(label.cget("text") for label in self.conflict_labels.values())]
        messagebox.showinfo("配置提示", "\n\n".join(dict.fromkeys(msg for msg in messages if msg)), parent=self.root)

    def _scrolling_tab(self, title):
        tab = ttk.Frame(self.notebook)
        canvas = tk.Canvas(tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        body = ttk.Frame(canvas, padding=10)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        def wheel(event):
            if str(event.widget).startswith(str(tab)):
                canvas.yview_scroll(-int(event.delta / 120), "units")
        self.root.bind("<MouseWheel>", wheel, add="+")
        self.notebook.add(tab, text=title)
        return tab, body

    def _toggle_section(self, frame, variable, before=None):
        if variable.get():
            frame.pack(fill="x", pady=(0, 6), **({"before": before} if before else {}))
        else:
            frame.pack_forget()

    def _toggle_planned(self):
        self._toggle_section(self.planned_frame, self.planned_var)

    def _render_catalog(self, view):
        extended = bool(view and view["descriptor"]["schema"] >= 2 and view["descriptor"].get("capabilities", 0) & 4)
        signature = (bool(view), extended)
        if getattr(self, "_catalog_signature", None) == signature:
            return
        self._catalog_signature = signature
        for widget in self.planned_frame.winfo_children():
            if widget is not self.twai_check:
                widget.destroy()
        self.twai_check.pack_forget()
        self.planned_widgets = {"twai": self.twai_check}
        groups = [
            ("总线与设备", ([] if extended else [("spi2", "SPI2"), ("spi3", "SPI3"), ("external", "普通 SPI 业务")]) + [("twai", "片上经典 CAN / TWAI"), ("i2c0", "I2C0"), ("i2c1", "I2C1")]),
            ("数字接口、波形与计数", [("gpio", "通用 GPIO"), ("ledc", "LEDC PWM（最多 16 路）"), ("mcpwm", "MCPWM（两组）"), ("pcnt", "PCNT（最多 8 个单元）")]),
            ("有线网络", [("ethernet", "以太网（EMAC 与外部 PHY）")]),
        ]
        count = sum(len(entries) for _, entries in groups)
        self.planned_toggle.configure(text=f"计划支持（{count} 项）· 展开完整目录其余条目")
        for title, entries in groups:
            if not entries:
                continue
            ttk.Label(self.planned_frame, text=title, font=("Microsoft YaHei UI", 9, "bold")).pack(anchor="w", pady=(6, 2))
            for key, name in entries:
                if key == "twai":
                    self.twai_check.pack(anchor="w", padx=12, pady=2)
                else:
                    detail = "当前固件不支持配置" if view and key in ("spi2", "spi3", "external") else "读取设备后确认能力" if not view and key in ("spi2", "spi3", "external") else "规划中"
                    widget = ttk.Checkbutton(self.planned_frame, text=f"{name} · {detail}", state="disabled")
                    widget.pack(anchor="w", padx=12, pady=2)
                    self.planned_widgets[key] = widget

    def _make_signal_rows(self, signals):
        # grid_slaves omits rows hidden with grid_remove; destroy those too when
        # a device change replaces the v1/v2 signal set.
        for widgets in getattr(self, "signal_rows", {}).values():
            for widget in widgets:
                widget.destroy()
        self.pin_vars.clear(); self.pin_boxes.clear(); self.mapping_labels.clear()
        self.signal_rows = {}
        self.conflict_labels = {}
        for i, signal in enumerate(signals, 1):
            row_index = i
            label = SIGNAL_NAMES.get(signal, signal.upper())
            name_label = ttk.Label(self.mapping_frame, text=label)
            name_label.grid(row=row_index, column=0, sticky="w", padx=8, pady=4)
            direction = ttk.Label(self.mapping_frame)
            direction.grid(row=row_index, column=1, sticky="w", padx=8)
            var = tk.StringVar()
            self.pin_vars[signal] = var
            box = ttk.Combobox(self.mapping_frame, textvariable=var, state="readonly", width=39)
            box.grid(row=row_index, column=2, sticky="ew", padx=8, pady=4)
            box.bind("<<ComboboxSelected>>", lambda event, s=signal: self._edit_pin(s))
            self.pin_boxes[signal] = box
            actual = ttk.Label(self.mapping_frame, width=18)
            actual.grid(row=row_index, column=3, sticky="w", padx=8)
            self.mapping_labels[signal] = (direction, actual)
            conflict = ttk.Label(self.mapping_frame, foreground="#b42318", width=24)
            conflict.grid(row=row_index, column=4, sticky="w", padx=8)
            conflict.bind("<Button-1>", lambda event: self._show_warnings() if event.widget.cget("text") else None)
            self.conflict_labels[signal] = conflict
            self.signal_rows[signal] = (name_label, direction, box, actual, conflict)

    @staticmethod
    def _parameter_value(mapping, instance, field):
        if instance.startswith("spi"):
            return mapping["spi"][instance[-1]].get(field, "master" if field == "role" else None)
        return mapping[instance]["cs"] != 255 if field == "use_cs" else mapping[instance][field]

    def _render_parameters(self, view):
        desc = view["descriptor"]
        supported = desc["schema"] >= 2 and desc.get("capabilities", 0) & 4
        dual = supported and desc["schema"] >= 3 and bool(desc.get("capabilities", 0) & 16)
        optional_cs = supported and desc["schema"] >= 3 and bool(desc.get("capabilities", 0) & 32)
        signature = (bool(supported), bool(dual), bool(optional_cs))
        if getattr(self, "_parameter_signature", None) != signature:
            for widget in self.extension.winfo_children():
                widget.destroy()
            self.parameter_vars.clear()
            self.parameter_widgets.clear()
            self.parameter_states.clear()
            self.device_conflict_labels = {}
            self.parameter_name_widgets = {}
            self._parameter_signature = signature
        if not supported:
            self.extension.grid_remove()
            if not hasattr(self, 'legacy_role_hint'):
                self.legacy_role_hint = ttk.Label(self.feature_groups['spi'], text='SPI2 / SPI3 本机角色：主机（当前固件不支持角色配置）', foreground='#526475')
            self.legacy_role_hint.grid(row=1, column=0, columnspan=2, sticky='w', padx=8)
            self._render_device_conflicts(view)
            return
        if hasattr(self, 'legacy_role_hint'):
            self.legacy_role_hint.grid_remove()
        if not self.extension.winfo_manager():
            self.extension.grid(row=1, column=0, columnspan=2, sticky="ew")
        if not self.parameter_widgets:
            self.bus_parameters = ttk.Frame(self.extension)
            self.bus_parameters.grid(row=0, column=0, rowspan=2, columnspan=6, sticky='w')
            specifications = [("spi2", "enabled", 0, 0), ("spi2", "role", 0, 3), ("spi2", "width", 0, 6),
                              ("spi3", "enabled", 1, 0), ("spi3", "role", 1, 3), ("spi3", "width", 1, 6)]
            row = 2
            devices = ["external"] + (["external2"] if dual else [])
            for instance in devices:
                specifications.extend([(instance, "enabled", row, 0), (instance, "host", row, 3)])
                if optional_cs:
                    specifications.append((instance, "use_cs", row + 1, 0))
                warning = ttk.Label(self.extension, foreground="#b42318", width=54, anchor="w")
                warning.grid(row=row + 1, column=3 if optional_cs else 0, columnspan=3 if optional_cs else 6, sticky="w", padx=8)
                self.device_conflict_labels[instance] = warning
                row += 2
            specifications.append(("mcp2518fd", "host", row, 0))
            warning = ttk.Label(self.extension, foreground="#b42318", width=54, anchor="w")
            warning.grid(row=row, column=3, columnspan=3, sticky="w", padx=8)
            self.device_conflict_labels["mcp2518fd"] = warning
            for instance, field, row, column in specifications:
                key = (instance, field)
                parent = self.bus_parameters if instance.startswith('spi') else self.extension
                title = {"enabled": "启用", "width": "最大线宽", "host": "所属总线", "use_cs": "使用 CS", "role": "本机角色"}[field]
                instance_title = {"external": "普通 SPI 设备 1" if dual else "普通 SPI 业务",
                                  "external2": "普通 SPI 设备 2", "mcp2518fd": "MCP2518FD"}.get(instance, instance.upper())
                if field not in ("enabled", "use_cs"):
                    name = ttk.Label(parent, text=title if field in ("role", "width") else f"{instance_title} · {title}")
                    name.grid(row=row, column=column, sticky="w", padx=8)
                    self.parameter_name_widgets.setdefault(instance, []).append(name)
                var = tk.StringVar()
                self.parameter_vars[key] = var
                choices = ("关", "开") if field in ("enabled", "use_cs") else ("1", "4") if field == "width" else tuple(ROLE_NAMES.values()) if field == "role" else ("2", "3")
                if field in ("enabled", "use_cs"):
                    box = ttk.Checkbutton(parent, text=f"{instance_title} · {title}", variable=var, onvalue="开", offvalue="关", command=lambda k=key: self._edit_parameter(k))
                else:
                    box = ttk.Combobox(parent, textvariable=var, values=choices, state="readonly", width=21 if field == "role" else 3)
                    box.bind("<<ComboboxSelected>>", lambda event, k=key: self._edit_parameter(k))
                box.grid(row=row, column=column if field in ("enabled", "use_cs") else column + 1,
                         columnspan=2 if field in ("enabled", "use_cs") else 1, sticky="w", padx=8, pady=2)
                self.parameter_widgets[key] = box
                if field in ("enabled", "use_cs"):
                    self.parameter_name_widgets.setdefault(instance, []).append(box)
                state = ttk.Label(parent, width=(4 if field == "enabled" else 12 if field == "role" else 7) if instance.startswith("spi") else 18, anchor="w")
                state.grid(row=row, column=column + 2, sticky="w", padx=8)
                self.parameter_states[key] = state
            self.parameter_help = ttk.Label(self.extension,
                text="换主机仅修改草稿；请按所选主机信号重新接线。无 CS 设备须独占主机，不能与 MCP2518FD 或另一普通设备共享。" if optional_cs else "换主机仅修改草稿；请按所选主机信号重新接线。",
                wraplength=930, foreground="#526475")
            self.parameter_help.grid(row=row + 1, column=0, columnspan=9, sticky="w", padx=8, pady=(4, 0))
        for key, var in self.parameter_vars.items():
            instance, field = key
            draft = self._parameter_value(view["draft"], instance, field)
            display = lambda value: ("开" if value else "关") if type(value) is bool else ROLE_NAMES.get(value, str(value))
            var.set(display(draft))
            candidate = view["snapshot"]["candidate"]
            active = self._parameter_value(view["snapshot"]["active"], instance, field)
            proposed = self._parameter_value(candidate, instance, field) if candidate else None
            self.parameter_states[key].configure(text=state_difference(display(active), display(proposed) if candidate else None, display(draft)))
            if field == "width":
                self.parameter_widgets[key]["values"] = ("1", "4") if desc["capabilities"] & 8 and view["draft"]["spi"][instance[-1]].get("role", "master") == "master" else ("1",)
        self._render_device_conflicts(view)

    @staticmethod
    def _signal_device(signal):
        prefix = signal.split(".")[0]
        return "can" if prefix == "mcp2518fd" else prefix

    def _render_device_conflicts(self, view):
        messages = {}
        def add(device, text):
            device = "can" if device == "mcp2518fd" else device
            if text not in messages.setdefault(device, []):
                messages[device].append(text)
        preview, draft = view["preview_tables"], view["draft"]
        for row in preview.get("candidate_occupancy") or []:
            if len(row["owners"]) > 1:
                text = f"GPIO{row['gpio']} 同时用于 " + owners_text(row["owners"])
                for owner in row["owners"]:
                    add(self._signal_device(owner), text)
        for row in preview.get("invalid_pins", []):
            text = (f"{SIGNAL_NAMES.get(row['signal'], row['signal'])} 需要选择输入 GPIO" if row['signal'].endswith('.slave_cs') and row['gpio'] == 255 else
                    f"{SIGNAL_NAMES.get(row['signal'], row['signal'])} 的 GPIO{row['gpio']} 不符合板型或方向要求")
            add(self._signal_device(row["signal"]), text)
        for row in preview.get("attachment_conflicts", []):
            names = {"external": "普通 SPI 设备 1", "external2": "普通 SPI 设备 2", "mcp2518fd": "MCP2518FD"}
            text = f"SPI{row['host']} 上无 CS 的{names.get(row['device'], row['device'])}与{names.get(row['peer'], row['peer'])}冲突；请启用 CS，或更换主机并重新接线。"
            add(row["device"], text)
            add(row["peer"], text)
        for row in preview.get("role_conflicts", []):
            names = {"external": "普通 SPI 设备 1", "external2": "普通 SPI 设备 2", "mcp2518fd": "MCP2518FD"}
            text = f"SPI{row['host']} 为从机，不能挂载{names[row['device']]}；请停用设备或迁到已启用的主机总线。"
            add(row["device"], text)
            add(f"spi{row['host']}", text)
        if view["descriptor"]["schema"] >= 2:
            for instance in ("external", "external2", "mcp2518fd"):
                if instance not in draft:
                    continue
                enabled = draft["features"]["can"] if instance == "mcp2518fd" else draft[instance]["enabled"]
                host = draft[instance]["host"]
                if enabled and not draft["spi"][str(host)]["enabled"]:
                    text = f"所属 SPI{host} 尚未启用；请开启主机或更换主机并重新接线。"
                    add(instance, text)
                    add(f"spi{host}", text)
        self.device_diagnostics = messages
        self.conflicting_devices = set(messages)
        self.device_name_labels = {**self.feature_widgets, "uart1": self.uart1_business_check}
        for instance, widgets in getattr(self, "parameter_name_widgets", {}).items():
            if widgets:
                self.device_name_labels[instance] = widgets[0]
            bad = ("can" if instance == "mcp2518fd" else instance) in messages
            for widget in widgets:
                widget.configure(style=("Conflict.TCheckbutton" if isinstance(widget, ttk.Checkbutton) else "Conflict.TLabel") if bad else "")
        self.device_name_labels["mcp2518fd"] = self.feature_widgets["can"]
        for key, widget in self.feature_widgets.items():
            widget.configure(style="Conflict.TCheckbutton" if key in messages else "")
        for instance, label in getattr(self, "device_conflict_labels", {}).items():
            text = "；".join(messages.get("can" if instance == "mcp2518fd" else instance, []))
            label.configure(text=text)
            # Keep this one-line diagnostic slot even when it is empty.
            label.grid()

    def show_function_details(self):
        if not self.view:
            return
        view = self.view
        lines = [self.management_hint_var.get(), self.uart1_role_var.get(),
                 "UART1 普通串口：" + self.uart1_state.cget("text") if self.uart1_state.cget("text") else ""]
        snap = view["snapshot"]
        for key, title in FEATURE_NAMES.items():
            difference = state_difference(snap["active"]["features"][key], snap["candidate"]["features"][key] if snap["candidate"] else None, view["draft"]["features"][key])
            if difference:
                lines.append(f"{title}：{difference}")
        for key, state in self.parameter_states.items():
            if state.cget("text"):
                instance = {"external": "普通 SPI 设备 1", "external2": "普通 SPI 设备 2", "mcp2518fd": "MCP2518FD"}.get(key[0], key[0].upper())
                field = {"enabled": "启用", "host": "所属总线", "width": "最大线宽", "use_cs": "使用 CS", "role": "本机角色"}[key[1]]
                lines.append(f"{instance} {field}：{state.cget('text')}")
        for device, diagnostics in getattr(self, "device_diagnostics", {}).items():
            title = {"external": "普通 SPI 设备 1", "external2": "普通 SPI 设备 2", "spi2": "SPI2", "spi3": "SPI3"}.get(device, FEATURE_NAMES.get(device, device))
            lines.append(f"{title}：" + "；".join(diagnostics))
        previous = getattr(self, "function_details_window", None)
        if previous is not None and previous.winfo_exists():
            previous.destroy()
        window = tk.Toplevel(self.root)
        window.title("功能状态与诊断详情")
        window.transient(self.root)
        body = ttk.Frame(window, padding=12)
        body.pack(fill="both", expand=True)
        text = tk.Text(body, width=82, height=22, wrap="word", font=("Microsoft YaHei UI", 10))
        scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        text.insert("1.0", "\n\n".join(line for line in lines if line))
        text.configure(state="disabled")
        ttk.Button(window, text="关闭", command=window.destroy).pack(anchor="e", padx=12, pady=(0, 12))
        window.bind("<Escape>", lambda event: window.destroy())
        self.function_details_window = window

    @staticmethod
    def _uart1_role(mapping):
        if mapping["features"]["serial"]:
            return "串口控制"
        return "普通串口" if mapping.get("uart1_business", False) else "UART1 保留（停用）"

    def _render_uart1(self, view):
        desc, snap, draft = view["descriptor"], view["snapshot"], view["draft"]
        supported = desc["schema"] >= 4 and desc.get("capabilities", 0) & 64
        self.uart1_business_var.set(bool(draft.get("uart1_business", False)))
        text = "UART1 普通串口"
        if not supported:
            text += "（当前固件不支持配置）"
        elif draft["features"]["serial"]:
            text += "（由串口控制使用）"
        difference = state_difference(bool(snap["active"].get("uart1_business", False)),
            bool(snap["candidate"].get("uart1_business", False)) if snap["candidate"] else None,
            bool(draft.get("uart1_business", False)))
        self.uart1_business_check.configure(text="UART1 普通串口", width=33)
        self.uart1_state.configure(text=(text.removeprefix("UART1 普通串口") + " " + difference).strip())
        self.uart1_role_var.set(f"UART1 TX GPIO4 · RX GPIO34 · 草稿：{self._uart1_role(draft)}。业务串口参数与控制连接波特率、UART2 分别管理。")
        if draft["features"]["serial"]:
            self.management_hint_var.set("")
            self.management_summary_var.set("")
            self.management_hint.configure(cursor="", takefocus=False)
            self.management_hint.grid()
        else:
            missing = []
            if not draft["features"]["wifi"]:
                missing.append("Wi-Fi STA")
            if not draft["features"]["control_tcp"]:
                missing.append("TCP 9500 管理服务")
            prefix = "UART1 用于普通收发。" if draft.get("uart1_business", False) else "UART1 控制已关闭。"
            self.management_hint_var.set(prefix + ("请启用 " + "、".join(missing) + "。" if missing else "已选择 Wi-Fi 与 TCP 9500 管理入口。") + "固件将核对已保存的配网参数；普通 TCP 业务不能代替管理服务。试用后请通过 socket://设备IP:9500 读回并确认。")
            self.management_summary_var.set(("缺少 " + "、".join(missing) if missing else "已选择网络接管；固件需核对配网参数") + " · 点此查看")
            self.management_hint.configure(cursor="hand2", takefocus=True)
            self.management_hint.grid()

    def _edit_uart1_business(self):
        if not self._rendering and self._connection_matches() and not self.busy:
            value = self.uart1_business_var.get()
            self._submit("更新 UART1 角色草稿", lambda: self.service.set_parameter("uart1", "enabled", value), preview_mode="draft")

    def _edit_parameter(self, key):
        if not self._rendering and self._connection_matches():
            instance,field=key
            raw=self.parameter_vars[key].get()
            value=(raw in ("True", "开")) if field in ("enabled", "use_cs") else next((value for value, label in ROLE_NAMES.items() if label == raw), raw) if field == "role" else int(raw)
            self._submit("更新 SPI 草稿", lambda: self.service.set_parameter(instance,field,value), preview_mode="draft")

    def _tree(self, parent, columns):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", selectmode="browse")
        for key, title, width in columns:
            tree.heading(key, text=title)
            tree.column(key, width=width, minwidth=60, stretch=True)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        return tree

    def _connection_matches(self):
        if not self.view:
            return False
        con = self.view["connection"]
        return self.port_var.get().strip() == con["port"] and self.baud_var.get().strip() == str(con["baud"])

    def show_device_details(self):
        if self.view:
            snap = self.view["snapshot"]
            details = (
                f"板型　{self.view['descriptor']['board']}\n"
                f"设备修订　{snap['revision']}\n"
                f"草稿来源修订　{self.view['source_revision']}\n"
                f"配置阶段　{PHASE_NAMES.get(snap['phase'], snap['phase'])}\n"
                f"候选 ID　{snap['candidate_id'] if snap.get('candidate') is not None else '无'}"
            )
            if self.history:
                details += "\n\n最近操作\n" + "\n".join(self.history)
            messagebox.showinfo("设备详情", details, parent=self.root)

    def _update_controls(self):
        ready = bool(self.view) and not self.busy and self._connection_matches()
        phase = self.view["snapshot"]["phase"] if self.view else None
        candidate = self.view and self.view["snapshot"].get("candidate") is not None
        conditional = {
            "cancel": candidate and phase == "staged",
            "apply": candidate and phase == "staged",
            "load_candidate": candidate and phase == "staged",
            "confirm": phase == "trial",
        }
        for name, button in self.buttons.items():
            enabled = not self.busy if name == "read" else ready
            if name in conditional:
                enabled = enabled and conditional[name]
                if conditional[name]:
                    if not button.winfo_manager():
                        button.pack()
                else:
                    button.pack_forget()
            if name in ("cancel", "apply", "confirm", "save", "check") and self.view and self.view.get("requires_reconnect"):
                enabled = False
            if name in ("save", "check"):
                enabled = enabled and phase in ("confirmed", "staged")
            button.configure(state="normal" if enabled else "disabled")
        for widget in self.feature_checks:
            widget.configure(state="normal" if ready else "disabled")
        for widget in self.pin_boxes.values():
            widget.configure(state="readonly" if ready else "disabled")
        for key, widget in self.parameter_widgets.items():
            widget.configure(state=("normal" if isinstance(widget, ttk.Checkbutton) else "readonly") if ready else "disabled")
            if key[1] == "role" and self.view:
                desc = self.view["descriptor"]
                cap = 0x80 if key[0] == "spi2" else 0x100
                if desc["schema"] < 5 or not desc.get("capabilities", 0) & cap:
                    widget.configure(state="disabled")
        if self.view and (self.view["preview_tables"].get("role_conflicts") or
                          self.view["descriptor"]["schema"] >= 5 and self.view["preview_tables"].get("invalid_pins")):
            self.buttons["save"].configure(state="disabled")
        supported_uart1 = bool(self.view and self.view["descriptor"]["schema"] >= 4 and self.view["descriptor"].get("capabilities", 0) & 64)
        self.uart1_business_check.configure(state="normal" if ready and supported_uart1 and not self.view["draft"]["features"]["serial"] else "disabled")
        self.port_box.configure(state="disabled" if self.busy else "normal")
        self.baud_box.configure(state="disabled" if self.busy else "normal")
        if self.view and not self._connection_matches() and not self.busy:
            self.status_var.set("连接地址已更改；请读取新设备后再编辑或操作。旧草稿仍保留。")

    def _submit(self, label, operation, *, preview_mode=None):
        if self.busy:
            return
        self.busy = True
        self.status_var.set(label + "…")
        self._update_controls()
        def work():
            try:
                result = operation()
                self._results.put((label, result, None, preview_mode))
            except Exception as exc:
                self._results.put((label, None, exc, None))
        threading.Thread(target=work, name="profile-io", daemon=True).start()

    def _poll_queue(self):
        if self._closed:
            return
        try:
            while True:
                label, view, error, preview_mode = self._results.get_nowait()
                self.busy = False
                if error is not None:
                    if isinstance(error, ApplyOutcomeUnknown):
                        self.view = self.service.view()
                    self.status_var.set(f"{label}失败：" + " ".join(str(error).splitlines()))
                    self.history.append(f"{label}失败：{error}")
                    if self.view:
                        self._render(self.view)
                    messagebox.showerror("操作失败 · 草稿已保留", f"{label}失败\n\n{error}\n\n请修正草稿或重新读取设备。", parent=self.root)
                else:
                    self.view = view
                    if preview_mode is not None:
                        self.overview.mode_var.set(preview_mode)
                    self._render(view)
                    self.status_var.set(label + "完成")
                    self.history.append(label + "完成")
                    if label == "重启并试用":
                        self.status_var.set("已发起重启；请等待设备恢复后点击读取。仅设备显示“试用中”才能确认，确认期限为 120 秒。")
                self._update_controls()
        except queue.Empty:
            pass
        self._poll_id = self.root.after(60, self._poll_queue)

    def _render(self, view):
        self.overview.set_view(view)
        self._rendering = True
        desc, snap, draft = view["descriptor"], view["snapshot"], view["draft"]
        tables, preview = view["tables"], view["preview_tables"]
        signals = [row["signal"] for row in tables["editable"]]
        if list(self.pin_boxes) != signals:
            self._make_signal_rows(signals)
        self._render_parameters(view)
        self._render_catalog(view)
        draft_signals = {row["signal"]: row for row in preview["editable"]}
        stage = {"staged": "待试用", "armed": "等待重启试用", "trial": "试用中，需限时确认"}.get(snap["phase"])
        if view.get("requires_reconnect"):
            stage = "请重新读取设备，核对试用结果"
        self.identity_var.set(f"板型 {desc['board']}" + (f"  ·  {stage}" if stage else ""))
        self.draft_var.set("草稿有未保存修改" if view["dirty"] else "")
        self._render_uart1(view)
        for key, var in self.feature_vars.items():
            var.set(draft["features"][key])
            difference = state_difference(snap["active"]["features"][key],
                snap["candidate"]["features"][key] if snap["candidate"] is not None else None,
                draft["features"][key])
            note = "（UART1 用于普通收发）" if key == "serial" and draft.get("uart1_business", False) else ""
            self.feature_widgets[key].configure(text=FEATURE_NAMES[key])
            self.feature_states[key].configure(text=(note + " " + difference).strip())
        proposed_owners = {r["gpio"]: r["owners"] for r in preview["candidate_occupancy"] or []}
        invalid_signals = {r["signal"]: r for r in preview.get("invalid_pins", [])}
        self.visible_signals = []
        device_signals = {r["signal"]: r for r in tables["editable"]}
        self.actual_heading.configure(text="当前 / 已保存候选" if snap["candidate"] is not None else "当前接线")
        for row in preview["editable"]:
            signal = row["signal"]
            enabled = row["candidate_enabled"] and (row["candidate_gpio"] != 255 or signal.endswith(".slave_cs"))
            if enabled:
                self.visible_signals.append(signal)
            for widget in self.signal_rows[signal]:
                widget.grid() if enabled else widget.grid_remove()
            choices = {}
            for choice in row["candidates"]:
                current_owners = choice["owners"]
                draft_owners = proposed_owners.get(choice["gpio"], [])
                usage = owners_text(current_owners) if current_owners == draft_owners else f"当前 {owners_text(current_owners)} / 草稿 {owners_text(draft_owners)}"
                choices[f"GPIO {choice['gpio']}  ·  {usage}"] = choice["gpio"]
            gpio = row["candidate_gpio"]
            selected = next((label for label, pin in choices.items() if pin == gpio),
                            ('待分配从机 CS' if signal.endswith('.slave_cs') else gpio_text(gpio)) if gpio == 255 else f"GPIO {gpio}  ·  无效映射，待修正")
            self._pin_choices[signal] = choices
            self.pin_boxes[signal]["values"] = tuple(choices)
            self.pin_vars[signal].set(selected)
            direction, actual = self.mapping_labels[signal]
            direction_name = row.get("candidate_direction") or row["direction"]
            direction.configure(text=DIRECTION_NAMES.get(direction_name, direction_name))
            device_row = device_signals[signal]
            active_pin = saved_pin_text(device_row["gpio"], device_row["enabled"])
            if signal.endswith('.slave_cs') and device_row['gpio'] == 255 and device_row['enabled']:
                active_pin = '待分配'
            if desc['schema'] >= 5 and signal.startswith('spi') and device_row['enabled']:
                active_pin += ' ' + {'input': '入', 'output': '出', 'bidirectional': '双向'}.get(device_row['direction'], '')
            if device_row["candidate_gpio"] is not None:
                saved_pin = saved_pin_text(device_row["candidate_gpio"], device_row["candidate_enabled"])
                if signal.endswith('.slave_cs') and device_row['candidate_gpio'] == 255 and device_row['candidate_enabled']:
                    saved_pin = '待分配'
                if desc['schema'] >= 5 and signal.startswith('spi') and device_row['candidate_enabled']:
                    saved_pin += ' ' + {'input': '入', 'output': '出', 'bidirectional': '双向'}.get(device_row['candidate_direction'], '')
                active_pin += f" / {saved_pin}"
            actual.configure(text=active_pin)
            owners = proposed_owners.get(gpio, [])
            problem = f"⚠ GPIO{gpio} 同时用于 " + " 和 ".join(SIGNAL_NAMES.get(owner, owner) for owner in owners) if enabled and len(owners) > 1 else ""
            if enabled and signal in invalid_signals:
                problem = "⚠ 请选择从机片选输入 GPIO" if signal.endswith(".slave_cs") and gpio == 255 else f"⚠ GPIO{gpio} 不符合板型或方向要求"
            if enabled and not problem and preview.get("role_conflicts") and self._signal_device(signal) in self.conflicting_devices:
                problem = "⚠ 从机不能挂载设备；请停用或迁移设备"
            self.conflict_labels[signal].configure(text=problem)
            self.signal_rows[signal][0].configure(foreground="#b42318" if problem else "")
        if self.visible_signals:
            self.no_signals.pack_forget()
        else:
            self.no_signals.configure(text="草稿中没有启用的可配置信号。请在功能控制页开启功能。")
            self.no_signals.pack(anchor="w", pady=8, before=self.fixed_toggle)
        self.fixed_tree.delete(*self.fixed_tree.get_children())
        for row in tables["fixed"]:
            purpose = OWNER_NAMES.get(row["owner"], row["purpose"])
            if row["gpio"] in (4, 34):
                purpose = "UART1 " + ("TX" if row["gpio"] == 4 else "RX")
                purpose += f" · 当前 {self._uart1_role(snap['active'])}"
                if snap["candidate"]:
                    purpose += f" / 候选 {self._uart1_role(snap['candidate'])}"
                purpose += f" / 草稿 {self._uart1_role(draft)}"
            self.fixed_tree.insert("", "end", values=(f"GPIO {row['gpio']}", purpose, DIRECTION_NAMES.get(row["direction"], "—"), NOTE_NAMES.get(row["notes"], row["notes"])))
        self.occupancy_tree.delete(*self.occupancy_tree.get_children())
        current = {r["gpio"]: r for r in tables["occupancy"]}
        candidate = {r["gpio"]: r for r in tables["candidate_occupancy"] or []}
        proposed = {r["gpio"]: r for r in preview["candidate_occupancy"] or []}
        conflicts = []
        def cell(row):
            if row is None:
                return "—"
            names = ("UART1 " + {"control": "串口控制", "business": "普通串口", "reserved": "保留"}[row["uart1_role"]]
                     if row.get("uart1_role") else owners_text(row["owners"]))
            if len(row["owners"]) > 1:
                return "冲突：" + names
            return ("固定 · " if row["fixed"] else "") + names
        for gpio in sorted(set(current) | set(tables["unavailable"])):
            if gpio in tables["unavailable"]:
                self.occupancy_tree.insert("", "end", values=(f"GPIO {gpio}", "未引出 / 不可用", "未引出 / 不可用", "未引出 / 不可用"), tags=("unavailable",))
                continue
            row = proposed.get(gpio)
            conflict = row is not None and len(row["owners"]) > 1
            if conflict:
                conflicts.append(str(gpio))
            tag = "conflict" if conflict else "fixed" if current[gpio]["fixed"] else ""
            self.occupancy_tree.insert("", "end", values=(f"GPIO {gpio}", cell(current[gpio]), cell(candidate.get(gpio)), cell(row)), tags=(tag,))
        warnings = []
        if conflicts:
            warnings.append("草稿引脚冲突：GPIO " + "、".join(conflicts))
        for invalid in preview.get("invalid_pins", []):
            warnings.append(f"{SIGNAL_NAMES.get(invalid['signal'], invalid['signal'])} 的 GPIO {invalid['gpio']} 不符合板型或方向要求")
        if snap["phase"] == "trial":
            warnings.append("设备处于试用阶段：请在重启后 120 秒内确认；超时或再次复位可能回退。请重新读取核对最新阶段。")
        self.warning_var.set("；".join(warnings))
        if warnings:
            self.warning_details.grid()
        else:
            self.warning_details.grid_remove()
        self._rendering = False

    def read_device(self):
        port = self.port_var.get().strip()
        try:
            baud = int(self.baud_var.get())
            if not port or baud <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror("连接参数无效", "请输入串口 / socket 地址和有效的正整数波特率。", parent=self.root)
            return
        discard = False
        if self.view and self.view["dirty"] and not self.view.get("requires_reconnect"):
            if not messagebox.askyesno("读取前保留草稿", "读取设备将重建草稿。尚有未保存的本地修改，是否放弃这些修改并读取？\n\n可先取消并导出 JSON 保存草稿。", parent=self.root):
                return
            discard = True
        self._submit("读取设备", lambda: self.service.read(port, baud, discard_draft=discard), preview_mode="current")

    def _edit_feature(self, key):
        if not self._rendering and self._connection_matches():
            value = self.feature_vars[key].get()
            self._submit("更新功能草稿", lambda: self.service.set_feature(key, value), preview_mode="draft")

    def _edit_pin(self, signal):
        if not self._rendering and self._connection_matches():
            gpio = self._pin_choices[signal].get(self.pin_vars[signal].get())
            if gpio is not None:
                self._submit("更新引脚草稿", lambda: self.service.set_pin(signal, gpio), preview_mode="draft")

    def import_config(self):
        if not self._connection_matches() or self.busy:
            return
        path = filedialog.askopenfilename(parent=self.root, title="导入完整配置到本地草稿", filetypes=[("JSON 配置", "*.json"), ("所有文件", "*.*")])
        if path:
            if self.view["dirty"] and not messagebox.askyesno("替换草稿", "导入将替换尚未保存的草稿，是否继续？", parent=self.root):
                return
            self._submit("导入草稿", lambda: self.service.import_config(path), preview_mode="draft")

    def export_config(self):
        if not self._connection_matches() or self.busy:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="导出当前草稿", defaultextension=".json", filetypes=[("JSON 配置", "*.json")])
        if path:
            self._submit("导出草稿", lambda: self.service.export_config(path))

    def _replace_draft(self, method, label):
        if not self._connection_matches() or self.busy:
            return
        if self.view["dirty"] and not messagebox.askyesno("替换草稿", "此操作将替换尚未保存的本地修改，是否继续？", parent=self.root):
            return
        self._submit(label, getattr(self.service, method), preview_mode="draft")

    def load_candidate(self):
        self._replace_draft("load_candidate", "载入设备候选")

    def reset_draft(self):
        self._replace_draft("reset_draft", "重建草稿")

    def candidate_changes(self):
        """Summarize the saved device candidate, independent of the local draft."""
        if not self.view or self.view["snapshot"]["candidate"] is None:
            return "设备没有候选配置。"
        snap = self.view["snapshot"]
        active, candidate = snap["active"], snap["candidate"]
        changes = []
        if self._uart1_role(active) != self._uart1_role(candidate):
            changes.append(f"• UART1：{self._uart1_role(active)} → {self._uart1_role(candidate)}")
        for key, title in FEATURE_NAMES.items():
            if key == "serial":
                continue
            if active["features"][key] != candidate["features"][key]:
                before = "开启" if active["features"][key] else "关闭"
                after = "开启" if candidate["features"][key] else "关闭"
                changes.append(f"• {title}：{before} → {after}")
        for row in self.view["tables"]["editable"]:
            if row["gpio"] != row["candidate_gpio"]:
                title = SIGNAL_NAMES.get(row["signal"], row["signal"].upper())
                def pin_description(gpio):
                    return '待分配' if row['signal'].endswith('.slave_cs') and gpio == 255 else gpio_text(gpio)
                changes.append(f"• {title}：{pin_description(row['gpio'])} → {pin_description(row['candidate_gpio'])}")
        if self.view["descriptor"]["schema"] >= 2:
            specifications = [("spi2", ("enabled", "width", "role", "slave_cs") if self.view["descriptor"]["schema"] >= 5 else ("enabled", "width")), ("spi3", ("enabled", "width", "role", "slave_cs") if self.view["descriptor"]["schema"] >= 5 else ("enabled", "width")),
                              ("external", ("enabled", "host")), ("mcp2518fd", ("host",))]
            if self.view["descriptor"]["schema"] >= 3 and "external2" in candidate:
                specifications.append(("external2", ("enabled", "host")))
            for instance, fields in specifications:
                before = active["spi"][instance[-1]] if instance.startswith("spi") else active[instance]
                after = candidate["spi"][instance[-1]] if instance.startswith("spi") else candidate[instance]
                for field in fields:
                    if before[field] != after[field]:
                        title = {"external": "普通 SPI 设备 1", "external2": "普通 SPI 设备 2", "mcp2518fd": "MCP2518FD"}.get(instance, instance.upper())
                        field_title = {"enabled": "启用", "width": "最大线宽", "host": "所属总线", "role": "本机角色", "slave_cs": "从机 CS"}[field]
                        def display(value):
                            if field == "enabled":
                                return "开" if value else "关"
                            return f"SPI{value}" if field == "host" else ROLE_NAMES[value] if field == "role" else ('待分配' if value == 255 else gpio_text(value)) if field == "slave_cs" else str(value)
                        changes.append(f"• {title} {field_title}：{display(before[field])} → {display(after[field])}")
        return "\n".join(changes) if changes else "设备候选与当前生效配置无差异。"

    def run_action(self, name):
        if not self._connection_matches() or self.busy or name not in ("check", "save", "cancel", "apply", "confirm"):
            return
        if str(self.buttons[name]["state"]) == "disabled":
            return
        candidate = self.view["snapshot"].get("candidate")
        connection_hint = ("请改用 socket://设备IP:9500 网络管理连接读回并确认；普通 TCP 业务端口不能代替 TCP 9500。"
                           if candidate and not candidate["features"]["serial"] else "如恢复 UART1 串口控制，请从 UART1 控制连接重新读取并确认。")
        if name == "apply" and not messagebox.askyesno("重启并开始限时试用", f"将应用设备候选 ID {self.view['snapshot']['candidate_id']}：\n\n{self.candidate_changes()}\n\n本次使用上述设备候选，本地草稿中的其他修改不会随本次应用生效。\n\n设备将重启，通信可能中断。{connection_hint}\n请在重启后重新读取设备，确认进入试用阶段，并在 120 秒内点击“确认试用配置”。超时或再次复位将回退。\n\n是否重启并试用设备候选？", parent=self.root):
            return
        if name == "cancel" and not messagebox.askyesno("取消设备候选", "是否取消设备中已暂存的候选配置？\n\n尚未保存的本地修改会保留；若草稿没有未保存修改，则从当前生效映射重建草稿。", parent=self.root):
            return
        labels = {"check": "预检草稿", "save": "保存候选", "cancel": "取消设备候选", "apply": "重启并试用", "confirm": "确认试用配置"}
        self._submit(labels[name], getattr(self.service, name))

    def close(self):
        if self.busy:
            messagebox.showinfo("操作进行中", "请等待当前操作完成后关闭窗口。", parent=self.root)
            return
        if self.view and self.view["dirty"] and not messagebox.askyesno("关闭工具", "本地草稿尚有修改，关闭后将丢失。是否关闭？", parent=self.root):
            return
        self._closed = True
        self.root.after_cancel(self._poll_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        ttk.Style(root).theme_use("vista")
    except tk.TclError:
        ttk.Style(root).theme_use("clam")
    ProfileApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
