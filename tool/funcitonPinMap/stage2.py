"""Stage2 profile controls and business operations, using the application's worker."""
import tkinter as tk
from tkinter import ttk
import json
from backend import cli
from hexbridge_io import BusinessSession, json_output


class Stage2Pane:
    def __init__(self, app):
        self.app = app
        self.session = None
        self.result = ''
        self.watching = False
        self.fields = {}
        self.widgets = {}
        self.tab, self.body = app._scrolling_tab('  I²C / GPIO  ')
        self.support = ttk.Label(self.body, text='读取设备以确认 v6 能力；配置编辑仅修改草稿。')
        self.support.pack(anchor='w')
        i2c = ttk.LabelFrame(self.body, text='I²C 控制器 · 本地草稿', padding=6)
        i2c.pack(fill='x', pady=6)
        for bus in range(2):
            frame = ttk.Frame(i2c)
            frame.pack(fill='x', pady=3)
            ttk.Label(frame, text=f'I2C{bus}', width=8).pack(side='left')
            self._field(frame, f'i2c{bus}', 'enabled', '启用', boolean=True)
            for name, title, values in (('scl', 'SCL', ()), ('sda', 'SDA', ()), ('clock_hz', 'Hz', (100000, 400000)), ('timeout_ms', '超时 ms', (100, 500, 1000))):
                self._field(frame, f'i2c{bus}', name, title, values)
        gpio = ttk.LabelFrame(self.body, text='GPIO 逻辑路 0–13 · 本地草稿（初始电平独立于读回）', padding=6)
        gpio.pack(fill='x', pady=6)
        ttk.Label(gpio, text='“未分配”是停用引脚占位（255）；启用前请选择 GPIO。引脚可先选择，再启用；修改模式后请核对引脚与偏置。').pack(anchor='w')
        self.selected_line = 0
        self.gpio_details = ttk.LabelFrame(gpio, text='逻辑路 0 · 详细配置', padding=5)
        self.detail_frames = {}
        for line in range(14):
            frame = ttk.Frame(gpio)
            frame.pack(fill='x', pady=2)
            instance = f'gpio.{line}'
            ttk.Button(frame, text=f'{line:02} 详情', width=8, command=lambda selected=line: self.select_line(selected)).pack(side='left')
            self._field(frame, instance, 'enabled', '启用', boolean=True)
            self._field(frame, instance, 'pin', 'GPIO', ())
            self._field(frame, instance, 'mode', '模式', cli.GPIO_MODES)
            details = ttk.Frame(self.gpio_details)
            self.detail_frames[line] = details
            for field, title, values in (('initial_level', '初始', (0, 1)), ('pull', '偏置', cli.GPIO_PULLS), ('trigger', '触发', tuple(cli.GPIO_TRIGGERS)), ('debounce_ms', '消抖ms', (0, 1, 10, 50, 255))):
                self._field(details, instance, field, title, values)
        self.gpio_details.pack(fill='x', pady=5)
        self.detail_frames[0].pack(fill='x')
        business = ttk.LabelFrame(self.body, text='业务操作 · 仅使用当前生效映射 / 当前会话', padding=8)
        business.pack(fill='x', pady=6)
        self.connection_label = ttk.Label(business, text='未连接；重新读取或配置事务会关闭业务会话。')
        self.connection_label.pack(anchor='w')
        top = ttk.Frame(business)
        top.pack(fill='x')
        self.business_buttons = []
        self._button(top, '连接业务会话', self.connect)
        self._button(top, '断开', lambda: self._run('断开', lambda: self.disconnect() or {'disconnected': True}))
        self.bus = self._input(top, 'I2C', '0', ('0', '1'))
        self.addr_bits = self._input(top, '地址位数', '7', ('7', '10'))
        for action in ('open', 'close', 'scan'):
            self._button(top, action.upper(), lambda a=action: self.i2c(a))
        row = ttk.Frame(business)
        row.pack(fill='x', pady=4)
        self.address = self._input(row, '原始地址', '0x50')
        self.register = self._input(row, '寄存器(hex)', '00')
        self.data = self._input(row, '数据(hex)', '')
        self.length = self._input(row, '读长度', '4')
        for action in ('read-reg', 'write-read', 'write'):
            self._button(row, action, lambda a=action: self.i2c(a))
        row = ttk.Frame(business)
        row.pack(fill='x', pady=4)
        self.line = self._input(row, 'GPIO逻辑路', '0', tuple(map(str, range(14))))
        self.level = self._input(row, '电平', '1', ('0', '1'))
        self.edge = self._input(row, '订阅触发', 'both', tuple(cli.GPIO_TRIGGERS))
        self.debounce = self._input(row, '消抖ms', '10')
        for action in ('read', 'write', 'watch', 'unwatch'):
            button = self._button(row, action, lambda a=action: self.gpio(a))
            if action == 'write':
                self.gpio_write_button = button
        self.line.trace_add('write', lambda *_: self.app._update_controls())
        row = ttk.Frame(business)
        row.pack(fill='x', pady=4)
        self.batch = self._input(row, '批写 JSON', '{"0": 1}')
        self._button(row, '预览分组', self.preview_batch)
        self._button(row, '执行批写', self.batch_write)
        self.output = tk.Text(business, height=8, wrap='word', state='disabled')
        self.output.pack(fill='x', pady=5)
        for widget in (*self.widgets.values(), *self.business_buttons):
            widget.configure(state='disabled')
        self._batch_preview = None
        self._tick_id = app.root.after(250, self._tick)
        self.tab.bind('<Destroy>', self._destroy, add='+')

    def _input(self, parent, title, value, values=()):
        ttk.Label(parent, text=title).pack(side='left', padx=(5, 2))
        var = tk.StringVar(value=value)
        ttk.Combobox(parent, textvariable=var, values=values, width=10, state='readonly' if values else 'normal').pack(side='left')
        return var

    def select_line(self, line):
        self.detail_frames[self.selected_line].pack_forget()
        self.selected_line = line
        self.detail_frames[line].pack(fill='x')
        self.gpio_details.configure(text=f'逻辑路 {line} · 详细配置；开漏初始高电平表示释放')

    def _button(self, parent, text, callback):
        button = ttk.Button(parent, text=text, command=callback)
        button.pack(side='left', padx=3)
        self.business_buttons.append(button)
        return button

    def _field(self, parent, instance, field, title, values=(), boolean=False):
        key = (instance, field)
        var = tk.BooleanVar() if boolean else tk.StringVar()
        self.fields[key] = var
        if boolean:
            widget = ttk.Checkbutton(parent, text=title, variable=var, command=lambda k=key: self.edit(k))
        else:
            ttk.Label(parent, text=title).pack(side='left', padx=(5, 2))
            widget = ttk.Combobox(parent, textvariable=var, values=values, width=10 if field == 'mode' else 7)
            widget.bind('<<ComboboxSelected>>', lambda event, k=key: self.edit(k))
            widget.bind('<Return>', lambda event, k=key: self.edit(k))
            widget.bind('<FocusOut>', lambda event, k=key: self.edit(k))
        widget.pack(side='left', padx=2)
        self.widgets[key] = widget

    def edit(self, key):
        if self.app.busy or self.app._rendering or not self.app.view or not self.app._connection_matches():
            return
        instance, field = key
        value = self.fields[key].get()
        if field not in ('enabled', 'mode', 'pull', 'trigger'):
            if value == '未分配':
                value = 255
            else:
                try:
                    value = int(value, 0)
                except ValueError:
                    self.app.status_var.set('请输入有效整数；未分配引脚使用 255')
                    return
        if field in ('scl', 'sda', 'pin'):
            signal = instance + '.' + field if field != 'pin' else instance
            operation = lambda: self.app.service.set_pin(signal, value)
        else:
            operation = lambda: self.app.service.set_parameter(instance, field, value)
        kind = 'i2c' if instance.startswith('i2c') else 'gpio_lines'
        row_key = instance[-1] if kind == 'i2c' else instance.split('.')[1]
        current = self.app.view['draft'].get(kind, {}).get(row_key, {})
        if current.get(field) == value:
            return
        self.app._edit_local_draft('更新 Stage2 草稿', operation)

    def render(self, view):
        desc = view['descriptor']
        supported = desc['schema'] >= 6
        self.support.configure(text='v6：配置只修改草稿，CHECK / SAVE / APPLY 后生效。' if supported else f'当前 v{desc["schema"]} 固件不支持 I²C / GPIO 配置；规划项只读。')
        signals = {row['signal']: row for row in view['preview_tables']['editable']}
        for (instance, field), widget in self.widgets.items():
            kind = 'i2c' if instance.startswith('i2c') else 'gpio_lines'
            cap = cli.CAP_I2C if kind == 'i2c' else cli.CAP_GPIO
            key = instance[-1] if kind == 'i2c' else instance.split('.')[1]
            row = view['draft'].get(kind, {}).get(key)
            enabled = bool(supported and desc.get('capabilities', 0) & cap and not self.app.busy and self.app._connection_matches())
            if row is not None:
                value = row[field]
                self.fields[(instance, field)].set('未分配' if field in ('scl', 'sda', 'pin') and value == 255 else value)
                if field in ('scl', 'sda', 'pin'):
                    signal = instance + '.' + field if field != 'pin' else instance
                    widget.configure(values=('未分配', *(str(r['gpio']) for r in signals[signal]['candidates'])))
                if field == 'pull':
                    widget.configure(values=('none',) if 34 <= row['pin'] <= 39 else cli.GPIO_PULLS)
                if field in ('initial_level',) and row.get('mode') == 'input':
                    enabled = False
            widget.configure(state=('normal' if isinstance(widget, ttk.Checkbutton) else 'readonly' if field in ('scl', 'sda', 'pin', 'mode', 'pull', 'trigger', 'clock_hz', 'initial_level') else 'normal') if enabled else 'disabled')
        for button in self.business_buttons:
            button.configure(state='normal' if supported and not self.app.busy and self.app._connection_matches() else 'disabled')
        active_line = view['snapshot']['active'].get('gpio_lines', {}).get(self.line.get(), {})
        if active_line.get('enabled') and active_line.get('mode') != 'input':
            if not self.gpio_write_button.winfo_manager():
                self.gpio_write_button.pack(side='left', padx=3)
        else:
            self.gpio_write_button.pack_forget()
        self.connection_label.configure(text=f'已连接 · OPEN {self.session.open_buses}' if self.session and self.session.connected else '未连接 · OPEN 状态已丢弃')
        self.output.configure(state='normal')
        self.output.delete('1.0', 'end')
        self.output.insert('end', self.result)
        self.output.configure(state='disabled')

    def _run(self, label, action):
        def operation():
            value = action()
            self.result = json_output(value)
            return self.app.service.view()
        self.app._submit('业务 ' + label, operation)

    def connect(self):
        port, baud = self.app.port_var.get(), int(self.app.baud_var.get())
        def action():
            self.disconnect()
            transport = self.app.service.transport_factory(port, baud)
            transport.open()
            try:
                session = BusinessSession(transport)
                if session.descriptor != self.app.service.descriptor or session.identity != self.app.service.identity or session.mapping != self.app.service.snapshot['active']:
                    raise ValueError('设备身份或活动映射已改变；请重新读取')
                self.session = session
            except Exception:
                transport.close()
                raise
            return dict(connected=True, topology=session.topology)
        self._run('连接', action)

    def disconnect(self):
        if self.session:
            self.session.disconnect()
        self.session = None
        self.watching = False

    def _session(self):
        if not self.session or not self.session.connected:
            raise ValueError('请先连接业务会话')
        return self.session

    def i2c(self, action):
        try:
            args = dict(bus=int(self.bus.get()), addr_bits=int(self.addr_bits.get()), addr=int(self.address.get(), 0), register=bytes.fromhex(self.register.get().removeprefix('0x')), data=bytes.fromhex(self.data.get().removeprefix('0x')), length=int(self.length.get()))
        except ValueError as exc:
            self.app.status_var.set('I2C 参数无效：' + str(exc))
            return
        self._run('I2C ' + action, lambda: self._session().i2c(action, **args))

    def gpio(self, action):
        try:
            args = dict(line=int(self.line.get()), level=int(self.level.get()), edge=self.edge.get(), debounce_ms=int(self.debounce.get()))
        except ValueError as exc:
            self.app.status_var.set('GPIO 参数无效：' + str(exc))
            return
        def run():
            result = self._session().gpio(action, **args)
            if not result['status'] and action in ('watch', 'unwatch'):
                self.watching = action == 'watch'
            return result
        self._run('GPIO ' + action, run)

    def preview_batch(self):
        try:
            values = json.loads(self.batch.get())
            if not isinstance(values, dict):
                raise ValueError('批写需要 JSON 逻辑路到电平对象')
        except ValueError as exc:
            self.app.status_var.set(str(exc))
            return
        self._run('分组预览', lambda: self._session().plan_write(values))

    def batch_write(self):
        try:
            values = json.loads(self.batch.get())
            if not isinstance(values, dict):
                raise ValueError('批写需要 JSON 逻辑路到电平对象')
        except ValueError as exc:
            self.app.status_var.set(str(exc))
            return
        def run():
            session = self._session()
            plan = session.plan_write(values)
            if self._batch_preview != plan:
                self._batch_preview = plan
                return dict(plan=plan, message='请核对分组，再次点击执行批写。跨组分别返回成功或失败。')
            self._batch_preview = None
            return dict(plan=plan, results=session.write_many(values))
        self._run('分组写入', run)

    def _destroy(self, event):
        if event.widget == self.tab:
            self.app.root.after_cancel(self._tick_id)

    def _tick(self):
        if self.app._closed:
            return
        if self.watching and self.session and self.session.connected and not self.app.busy and self.app._connection_matches():
            def poll():
                events = self.session.poll_events(0.02)
                if events:
                    self.result = '\n'.join(json_output({'event': event}) for event in events)
                return self.app.service.view()
            self.app._submit('业务 事件', poll)
        self._tick_id = self.app.root.after(250, self._tick)
