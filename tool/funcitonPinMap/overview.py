"""Read-only GPIO panorama derived exclusively from the existing profile tables."""
import tkinter as tk
from tkinter import messagebox, ttk


STATE_NAMES = {"free": "空闲", "occupied": "使用", "fixed": "固定", "unavailable": "未引出", "conflict": "冲突"}
COLORS = {
    "free": ("#15803D", "#ffffff"), "occupied": ("#1D4ED8", "#ffffff"),
    "fixed": ("#555e69", "#ffffff"), "unavailable": ("#edf0f3", "#68717b"),
    "conflict": ("#B91C1C", "#ffffff"),
}
MODE_NAMES = {"current": "当前接线", "candidate": "已保存候选", "draft": "草稿预览"}
SHORT_OWNERS = {
    "uart.tx": "UART2 TX", "uart.rx": "UART2 RX", "can.sck": "外置 CAN SCK",
    "can.mosi": "外置 CAN MOSI", "can.miso": "外置 CAN MISO", "can.cs": "外置 CAN CS",
    "can.int": "外置 CAN INT", "dap.swclk": "DAP SWCLK", "dap.swdio": "DAP SWDIO",
    "spi2.slave_cs": "SPI2 从机 CS", "spi3.slave_cs": "SPI3 从机 CS",
    "uart0.tx": "烧录 / 日志 TX", "uart0.rx": "烧录 / 日志 RX",
    "uart1.tx": "控制 UART1 TX", "uart1.rx": "控制 UART1 RX",
    "flash": "内部 Flash", "psram": "内部 PSRAM", "spi2": "外部 SPI2",
    "eeprom": "EEPROM", "strap": "启动配置",
}


class PinOverview(ttk.Frame):
    """Mode changes redraw local snapshots and never call the device service."""

    def __init__(self, parent):
        super().__init__(parent, padding=(2, 2))
        self.view = None
        self.cards = {}
        self.all_cards = {}
        self.visible_gpios = []
        self.card_bounds = {}
        self.counts = {state: 0 for state in STATE_NAMES}
        self.mode_var = tk.StringVar(value="current")
        self.show_all_var = tk.BooleanVar(value=False)
        self.summary_var = tk.StringVar(value="请先读取设备，查看可分配引脚。")
        self.detail_var = tk.StringVar(value="按 GPIO 编号排序，不代表排针位置。点击卡片可查看完整占用说明。")
        self.mode_buttons = {}
        self.focused_gpio = None
        self._tooltip = None
        self._tooltip_after = None
        self.mode_title_var = tk.StringVar(value=MODE_NAMES["current"])
        self.columnconfigure(0, weight=1)
        toolbar = self.toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(toolbar, textvariable=self.mode_title_var).pack(side="left")
        self.details_button = ttk.Button(toolbar, text="查看详情", command=self.open_details)
        self.details_button.pack(side="right")

        # Keep the controls alive while the details window is closed, so mode and
        # range survive tab changes and re-rendering of the shared draft.
        self.details_window = tk.Toplevel(self)
        self.details_window.withdraw()
        self.details_window.title("引脚全景详情")
        self.details_window.transient(self.winfo_toplevel())
        self.details_window.protocol("WM_DELETE_WINDOW", self.details_window.withdraw)
        details = ttk.Frame(self.details_window, padding=16)
        details.pack(fill="both", expand=True)
        ttk.Label(details, text="查看接线", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w")
        self.mode_bar = ttk.Frame(details)
        self.mode_bar.pack(anchor="w", pady=(6, 10))
        for col, (mode, title) in enumerate(MODE_NAMES.items()):
            button = ttk.Radiobutton(self.mode_bar, text=title, variable=self.mode_var, value=mode, command=self.refresh)
            button.grid(row=0, column=col, sticky="w", padx=(0, 8))
            self.mode_bar.columnconfigure(col, minsize=button.winfo_reqwidth() + 8)
            self.mode_buttons[mode] = button
            button.state(["disabled"])
        self.mode_buttons["candidate"].grid_remove()
        self.show_all_button = ttk.Checkbutton(details, text="显示全部引脚（GPIO0–39）", variable=self.show_all_var, command=self.refresh)
        self.show_all_button.pack(anchor="w")
        self.show_all_button.state(["disabled"])
        self.summary_label = ttk.Label(details, textvariable=self.summary_var, font=("Microsoft YaHei UI", 9))
        self.summary_label.pack(anchor="w", pady=(8, 12))
        legend = ttk.Frame(details)
        legend.pack(anchor="w")
        for state, name in STATE_NAMES.items():
            fill, ink = COLORS[state]
            tk.Label(legend, text=("! " if state == "conflict" else "") + name,
                     background=fill, foreground=ink, padx=8, pady=3).pack(side="left", padx=(0, 6))
        ttk.Label(details, text="按 GPIO 编号排列，不代表排针位置。\n鼠标悬停或键盘聚焦可读状态；方向键选脚，回车查看用途与限制。",
                  justify="left").pack(anchor="w", pady=(12, 6))
        ttk.Label(details, textvariable=self.detail_var, justify="left", wraplength=660).pack(anchor="w", pady=(0, 10))
        self.fixed_var = tk.StringVar(value="读取设备后显示固定用途。")
        ttk.Label(details, textvariable=self.fixed_var, justify="left", wraplength=660).pack(anchor="w")
        ttk.Button(details, text="关闭", command=self.details_window.withdraw).pack(anchor="e", pady=(12, 0))
        self.details_window.bind("<Escape>", lambda event: self.details_window.withdraw())
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#ffffff", height=44, takefocus=True)
        self.canvas.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<Configure>", lambda event: self._draw())
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Motion>", self._hover)
        self.canvas.bind("<Leave>", lambda event: self._hide_tooltip())
        self.canvas.bind("<FocusIn>", self._focus_in)
        self.canvas.bind("<FocusOut>", lambda event: self._lose_focus())
        for key in ("Left", "Right", "Up", "Down", "Home", "End"):
            self.canvas.bind(f"<{key}>", self._navigate)
        self.canvas.bind("<Return>", lambda event: self._open_pin(self.focused_gpio))
        self.canvas.bind("<space>", lambda event: self._open_pin(self.focused_gpio))
        self.canvas.bind("<Destroy>", lambda event: self._hide_tooltip())
        self._draw()

    def open_details(self):
        self.details_window.deiconify()
        self.details_window.lift()
        self.details_window.focus_set()

    def set_view(self, view):
        self.view = view
        has_candidate = bool(view and view["snapshot"].get("candidate") is not None)
        for mode, button in self.mode_buttons.items():
            enabled = view is not None and (mode != "candidate" or has_candidate)
            button.state(["!disabled"] if enabled else ["disabled"])
        self.show_all_button.state(["!disabled"] if view is not None else ["disabled"])
        if self.mode_var.get() == "candidate" and not has_candidate:
            self.mode_var.set("current")
        self.refresh()

    def refresh(self):
        self._hide_tooltip()
        self.canvas.configure(height=180 if self.show_all_var.get() else 44)
        self.cards = {}
        self.all_cards = {}
        self.visible_gpios = []
        self.counts = {state: 0 for state in STATE_NAMES}
        if self.view is None:
            self.summary_var.set("请先读取设备，查看可分配引脚。")
            self._draw()
            return
        mode = self.mode_var.get()
        tables = self.view["tables"]
        if mode == "candidate" and self.view["snapshot"].get("candidate") is None:
            self.mode_var.set("current")
            mode = "current"
        self.mode_title_var.set(MODE_NAMES[mode])
        # A missing candidate is omitted from the details view altogether.
        if self.view["snapshot"].get("candidate") is None:
            self.mode_buttons["candidate"].grid_remove()
        elif not self.mode_buttons["candidate"].winfo_manager():
            self.mode_buttons["candidate"].grid()
        rows = (tables["occupancy"] if mode == "current" else tables["candidate_occupancy"]
                if mode == "candidate" else self.view["preview_tables"]["candidate_occupancy"])
        occupied = {row["gpio"]: row for row in rows or []}
        selected_tables = self.view['preview_tables'] if mode == 'draft' else tables
        signal_rows = {row['signal']: row for row in selected_tables['editable']}
        mapping = (self.view['snapshot']['active'] if mode == 'current' else
                   self.view['snapshot']['candidate'] if mode == 'candidate' else self.view['draft'])
        policy = self.view["descriptor"]["gpio_policy"]
        for gpio in range(40):
            row = occupied.get(gpio)
            users = row["owners"] if row else []
            rule = policy.get(str(gpio), "unavailable")
            state = ("unavailable" if rule == "unavailable" else "conflict" if len(users) > 1
                     else "fixed" if row and row["fixed"] else "occupied" if users else "free")
            if users:
                owner = SHORT_OWNERS.get(users[0], users[0])
                if len(users) > 1:
                    owner = "多个信号争用"
            elif state == "unavailable":
                owner = "不可分配"
            elif rule == "input_only":
                owner = "仅输入 · 无内拉"
            elif rule == "can.cs_only":
                owner = "仅限 CAN.CS"
            else:
                owner = "可分配 · 输入/输出"
            full_owners = "、".join(SHORT_OWNERS.get(user, user) for user in users)
            if row and "uart1_role" in row:
                role = {"control": "串口控制", "business": "普通串口", "reserved": "保留"}[row["uart1_role"]]
                owner = f"UART1 {role} {rule[-2:].upper()}"
                full_owners = owner
            detail = f"GPIO {gpio} · {STATE_NAMES[state]}\n\n{full_owners or owner}"
            for user in users:
                bus_name = user.split('.')[0]
                if bus_name not in ('spi2', 'spi3') or self.view['descriptor']['schema'] < 5:
                    continue
                bus = mapping['spi'][bus_name[-1]]
                direction = signal_rows[user]['direction' if mode == 'current' else 'candidate_direction']
                detail += f"\n{bus_name.upper()} 本机角色：" + ('从机' if bus['role'] == 'slave' else '主机')
                detail += '；' + {'input': '输入', 'output': '输出', 'bidirectional': '双向'}.get(direction, direction)
            if state == "conflict":
                detail += f"\nGPIO{gpio} 同时用于 " + " 和 ".join(users) + "。"
            if rule == "flexible":
                detail += "\n支持数字输入/输出；具体功能由所选信号决定。"
            if rule == "input_only":
                detail += "\n仅输入，无内部上下拉，需要外部偏置。"
            if rule == "can.cs_only":
                detail += "\n仅可分配给外置 MCP2518FD CAN.CS；外部 10kΩ 上拉，启动保持高电平。"
            self.all_cards[gpio] = {"state": state, "owner": owner, "detail": detail, "owners": list(users)}
            if self.show_all_var.get() or rule in ("flexible", "input_only", "can.cs_only"):
                self.cards[gpio] = self.all_cards[gpio]
                self.visible_gpios.append(gpio)
                self.counts[state] += 1
        states = STATE_NAMES if self.show_all_var.get() else ("free", "occupied", "conflict")
        scope = "全部" if self.show_all_var.get() else "可分配"
        self.summary_var.set(f"{scope} {len(self.cards)}  ·  " + "  ".join(f"{STATE_NAMES[state]} {self.counts[state]}" for state in states))
        fixed = [f"GPIO{gpio}：{card['owner']}" for gpio, card in self.all_cards.items() if card["state"] == "fixed"]
        self.fixed_var.set("固定用途（只读）\n" + "；".join(fixed))
        if self.focused_gpio not in self.cards:
            self.focused_gpio = next(iter(self.cards), None)
        self.detail_var.set(self.cards[self.focused_gpio]["detail"] if self.focused_gpio is not None else "")
        self._draw()

    def _draw(self):
        canvas = self.canvas
        canvas.delete("all")
        self.card_bounds = {}
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if not self.cards:
            text = "请先读取设备 · 默认显示可分配引脚，点击查看详情" if self.view is None else "该设备没有可分配的业务引脚，可勾选“显示全部引脚”查看板级资源"
            canvas.create_text(max(width, 400) / 2, height / 2, text=text, justify="center", fill="#68717b", font=("Microsoft YaHei UI", 9))
            return
        columns = 8 if self.show_all_var.get() else max(1, len(self.visible_gpios))
        rows = (len(self.visible_gpios) + columns - 1) // columns
        grid_width = width
        cell_width, cell_height = grid_width / columns, height / rows
        left = (width - grid_width) / 2
        for index, (gpio, card) in enumerate(self.cards.items()):
            x = left + (index % columns) * cell_width
            y = (index // columns) * cell_height
            self.card_bounds[gpio] = (x + 2, y + 2, x + cell_width - 2, y + cell_height - 2)
            fill, ink = COLORS[card["state"]]
            tag = f"gpio-{gpio}"
            focused = self.focused_gpio == gpio and canvas.focus_get() == canvas
            canvas.create_rectangle(x + 2, y + 2, x + cell_width - 2, y + cell_height - 2, fill=fill,
                                    outline="#162c43" if focused else fill, width=2 if focused else 1, tags=(tag, "card"))
            canvas.create_text(x + cell_width / 2, y + cell_height / 2,
                               text=f"{gpio}" + (" !" if card["state"] == "conflict" else ""),
                               font=("Microsoft YaHei UI", 10, "bold"), fill=ink, tags=(tag, "card-title"))

    def _click(self, event):
        for gpio, (left, top, right, bottom) in self.card_bounds.items():
            if left <= event.x <= right and top <= event.y <= bottom:
                self.focused_gpio = gpio
                self.canvas.focus_set()
                self._open_pin(gpio)
                return

    def _open_pin(self, gpio):
        self._hide_tooltip()
        if gpio in self.cards:
            messagebox.showinfo(f"GPIO {gpio} 占用说明", self.cards[gpio]["detail"], parent=self.winfo_toplevel())
        return "break"

    def _focus_in(self, event):
        if self.focused_gpio not in self.cards:
            self.focused_gpio = next(iter(self.cards), None)
        self._draw()
        self._show_tooltip(self.focused_gpio)

    def _lose_focus(self):
        self._hide_tooltip()
        self._draw()

    def _navigate(self, event):
        if not self.visible_gpios:
            return "break"
        index = self.visible_gpios.index(self.focused_gpio) if self.focused_gpio in self.visible_gpios else 0
        columns = 8 if self.show_all_var.get() else len(self.visible_gpios)
        if event.keysym == "Home":
            index = 0
        elif event.keysym == "End":
            index = len(self.visible_gpios) - 1
        else:
            index += {"Left": -1, "Right": 1, "Up": -columns, "Down": columns}[event.keysym]
        self.focused_gpio = self.visible_gpios[max(0, min(index, len(self.visible_gpios) - 1))]
        self._draw()
        self._show_tooltip(self.focused_gpio)
        return "break"

    def _hover(self, event):
        gpio = next((gpio for gpio, (left, top, right, bottom) in self.card_bounds.items()
                     if left <= event.x <= right and top <= event.y <= bottom), None)
        if gpio == getattr(self, "_hover_gpio", None):
            return
        self._hide_tooltip()
        self._hover_gpio = gpio
        if gpio is not None:
            self._tooltip_after = self.after(300, lambda: self._show_tooltip(gpio))

    def _hide_tooltip(self):
        if self._tooltip_after is not None:
            self.after_cancel(self._tooltip_after)
            self._tooltip_after = None
        if self._tooltip is not None:
            self._tooltip.destroy()
            self._tooltip = None
        self._hover_gpio = None

    def _show_tooltip(self, gpio):
        self._hide_tooltip()
        if gpio not in self.cards or gpio not in self.card_bounds:
            return
        self._hover_gpio = gpio
        card = self.cards[gpio]
        self.detail_var.set(card["detail"])
        tooltip = self._tooltip = tk.Toplevel(self)
        tooltip.overrideredirect(True)
        tooltip.transient(self.winfo_toplevel())
        ttk.Label(tooltip, text=card["detail"], padding=8, wraplength=420, justify="left", relief="solid").pack()
        tooltip.update_idletasks()
        left, _, _, bottom = self.card_bounds[gpio]
        x = max(0, min(self.canvas.winfo_rootx() + int(left), self.winfo_screenwidth() - tooltip.winfo_reqwidth()))
        y = max(0, min(self.canvas.winfo_rooty() + int(bottom) + 3, self.winfo_screenheight() - tooltip.winfo_reqheight()))
        tooltip.geometry(f"+{x}+{y}")
