"""Hardware-free regressions for the profile service and real Tk button events.

Run: python tool/funcitonPinMap/test_app.py
Only MemoryBoard is opened: no serial ports, sockets, credentials or board writes.
The simulator deliberately models reboot separately from APPLY.
"""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ASSIGNABLE_GPIO = [13, 14, 15, 25, 26, 32, 35, 36, 39]
sys.path.insert(0, str(HERE))
import backend
import app


class MemoryBoard:
    def __init__(self, identity="board-A"):
        self.identity = identity
        policy = dict.fromkeys(map(str, range(40)), "unavailable")
        policy.update(dict.fromkeys(map(str, (13, 14, 25, 26, 32)), "flexible"))
        policy.update(dict.fromkeys(map(str, (35, 36, 39)), "input_only"))
        for pin, owner in {0: "strap", 1: "uart0.tx", 2: "strap", 3: "uart0.rx",
                           4: "uart1.tx", 5: "strap", 12: "eeprom", 15: "can.cs_only",
                           16: "psram", 17: "psram", 33: "eeprom", 34: "uart1.rx",
                           **dict.fromkeys(range(6, 12), "flash"),
                           **dict.fromkeys((18, 19, 21, 22, 23, 27), "spi2")}.items():
            policy[str(pin)] = owner
        self.desc = {"schema": 1, "board": "HXB1", "gpio_policy": policy}
        mapping = {"features": dict.fromkeys("serial control_tcp can uart wifi tcp udp websocket dap".split(), True),
                   "pins": dict(zip("uart.tx uart.rx can.sck can.mosi can.miso can.cs can.int dap.swclk dap.swdio".split(),
                                    (32, 35, 14, 13, 36, 15, 39, 25, 26)))}
        self.state = {"revision": 1, "phase": "confirmed", "candidate_id": 0,
                      "confirmed_id": 0, "active": mapping, "candidate": None}
        self.confirmed = copy.deepcopy(mapping)
        self.calls = []
        self.reads = []
        self.fail_next = None

    def __enter__(self): return self
    def __exit__(self, *args): pass
    def descriptor(self):
        self.reads.append("describe")
        return copy.deepcopy(self.desc)

    def snapshot(self):
        self.reads.append("read")
        return copy.deepcopy(self.state)

    def request(self, op, data=b""):
        self.calls.append((op, bytes(data), threading.get_ident()))
        if self.fail_next:
            error, self.fail_next = self.fail_next, None
            raise ValueError(error)
        ident = struct.unpack_from(">I", data)[0]
        if op in ("check", "save"):
            if ident != self.state["revision"]:
                raise ValueError("stale revision or candidate ID; read the device again")
            mapping = backend.cli.decode_mapping(data[4:])
            if self.desc["schema"] >= 2:
                snapshot = {**self.state, "active":mapping, "candidate":None}
                tables = backend.cli.build_tables(self.desc,snapshot,mapping)
                if tables["invalid_pins"] or any(len(r["owners"]) > 1 for r in tables["occupancy"]):
                    raise ValueError("GPIO conflict or invalid direction")
                devices = ("external", "external2", "mcp2518fd") if self.desc["schema"] >= 3 else ("external", "mcp2518fd")
                for device in devices:
                    enabled = mapping["features"]["can"] if device == "mcp2518fd" else mapping[device]["enabled"]
                    if enabled and not mapping["spi"][str(mapping[device]["host"])]["enabled"]:
                        raise ValueError("attachment requires enabled SPI host")
                for device in devices:
                    if device == "mcp2518fd" or not mapping[device]["enabled"] or mapping[device]["cs"] != 255:
                        continue
                    for peer in devices:
                        enabled = mapping["features"]["can"] if peer == "mcp2518fd" else mapping[peer]["enabled"]
                        if peer != device and enabled and mapping[peer]["host"] == mapping[device]["host"]:
                            raise ValueError("A no-CS device requires an exclusive SPI host")
            else:
                for index, (signal, gpio) in enumerate(mapping["pins"].items()):
                    if not backend.cli.legal_pin(self.desc, index, gpio):
                        raise ValueError(f"{signal} cannot use GPIO{gpio}")
                rows = backend.cli.occupancy(self.desc, mapping)
                if any(not r["fixed"] and len(r["owners"]) > 1 for r in rows):
                    raise ValueError("GPIO conflict")
            if op == "save":
                self.state.update(candidate=copy.deepcopy(mapping), candidate_id=101,
                                  revision=self.state["revision"] + 1, phase="staged")
                return struct.pack(">I", 101)
        else:
            if ident != self.state["candidate_id"]:
                raise ValueError("stale candidate ID")
            if op == "apply":
                self.state["phase"] = "armed"
            elif op == "cancel":
                self.state.update(phase="confirmed", candidate=None, candidate_id=0,
                                  revision=self.state["revision"] + 1)
            elif op == "confirm":
                if self.state["phase"] != "trial":
                    raise ValueError("not in trial")
                self.confirmed = copy.deepcopy(self.state["active"])
                self.state.update(phase="confirmed", confirmed_id=ident, candidate=None, candidate_id=0,
                                  revision=self.state["revision"] + 1)
        return b""

    def reboot(self):
        if self.state["phase"] == "armed":
            self.state.update(phase="trial", active=copy.deepcopy(self.state["candidate"]))
        elif self.state["phase"] == "trial":
            self.state.update(phase="confirmed", active=copy.deepcopy(self.confirmed),
                              candidate=None, candidate_id=0, revision=self.state["revision"] + 1)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.board = MemoryBoard()
        self.other = MemoryBoard("board-B")
        self.boards = {"mock:A": self.board, "mock:B": self.other}
        self.service = backend.ProfileService(
            transport_factory=lambda port, baud: self.boards[port],
            device_factory=lambda transport: transport,
            identity_reader=lambda device: device.identity)
        self.service.read("mock:A", 115200)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "profile.json"

    def view(self):
        return self.service.view()

    def move_can(self):
        self.service.set_feature("dap", False)
        return self.service.set_pin("can.sck", 25)

    def test_draft_preview_does_not_change_device_or_fixed_table(self):
        initial = self.view()
        edited = self.move_can()
        self.assertTrue(edited["dirty"])
        self.assertEqual(edited["snapshot"], initial["snapshot"])
        self.assertEqual(edited["tables"]["occupancy"], initial["tables"]["occupancy"])
        self.assertNotEqual(edited["preview_tables"]["candidate_occupancy"], initial["tables"]["occupancy"])
        self.assertEqual(edited["preview_tables"]["fixed"], initial["tables"]["fixed"])
        self.assertEqual(self.board.calls, [])

    def test_complete_mapping_and_revision_check_save_trial_confirm(self):
        edited = self.move_can()
        self.service.check()
        self.assertEqual(self.board.calls[-1][0:2], ("check", struct.pack(">I", 1) + backend.cli.encode_mapping(edited["draft"])))
        staged = self.service.save()
        self.assertEqual(staged["snapshot"]["phase"], "staged")
        self.assertEqual(staged["snapshot"]["active"]["pins"]["can.sck"], 14)
        self.assertEqual(staged["snapshot"]["candidate"]["pins"]["can.sck"], 25)
        with self.assertRaises((ValueError, RuntimeError)):
            self.service.confirm()
        self.service.apply()
        self.assertEqual(self.board.calls[-1][0:2], ("apply", struct.pack(">I", 101)))
        self.board.reboot()
        trial = self.service.read("mock:A", 115200, discard_draft=True)
        self.assertEqual(trial["snapshot"]["phase"], "trial")
        confirmed = self.service.confirm()
        self.assertEqual(confirmed["snapshot"]["phase"], "confirmed")
        self.assertEqual(confirmed["snapshot"]["active"]["pins"]["can.sck"], 25)

    def test_cancel_uses_latest_candidate(self):
        self.move_can()
        self.service.save()
        result = self.service.cancel()
        self.assertEqual(self.board.calls[-1][0:2], ("cancel", struct.pack(">I", 101)))
        self.assertIsNone(result["snapshot"]["candidate"])

    def test_trial_reset_is_reflected_by_fresh_read(self):
        self.move_can()
        self.service.save()
        self.service.apply()
        self.board.reboot()
        self.service.read("mock:A", 115200, discard_draft=True)
        self.board.reboot()
        reverted = self.service.read("mock:A", 115200, discard_draft=True)
        self.assertEqual(reverted["snapshot"]["phase"], "confirmed")
        self.assertEqual(reverted["snapshot"]["active"]["pins"]["can.sck"], 14)

    def test_error_keeps_draft_and_can_retry(self):
        draft = self.move_can()["draft"]
        self.board.fail_next = "profile persistence failed"
        with self.assertRaisesRegex(ValueError, "persistence"):
            self.service.save()
        self.assertEqual(self.view()["draft"], draft)
        self.assertEqual(self.service.save()["snapshot"]["phase"], "staged")

    def test_stale_revision_blocks_write_and_retains_draft(self):
        draft = self.move_can()["draft"]
        self.board.state["revision"] += 1
        with self.assertRaises((ValueError, RuntimeError)):
            self.service.save()
        self.assertEqual(self.view()["draft"], draft)
        self.assertFalse(any(op == "save" for op, *_ in self.board.calls))

    def test_same_port_replaced_device_blocks_write(self):
        self.move_can()
        self.boards["mock:A"] = self.other
        with self.assertRaises((ValueError, RuntimeError)):
            self.service.save()
        self.assertEqual(self.other.calls, [])

    def test_dirty_refresh_and_device_switch_require_explicit_discard(self):
        draft = self.move_can()["draft"]
        for port in ("mock:A", "mock:B"):
            with self.assertRaises((ValueError, RuntimeError)):
                self.service.read(port, 115200)
            self.assertEqual(self.view()["draft"], draft)
        changed = self.service.read("mock:B", 115200, discard_draft=True)
        self.assertFalse(changed["dirty"])
        self.assertEqual(changed["draft"]["pins"]["can.sck"], 14)
        self.assertEqual(self.other.calls, [])

    def test_json_roundtrip_is_draft_only_and_fixed_protection(self):
        self.move_can()
        self.service.export_config(self.path)
        exported = json.loads(self.path.read_text(encoding="utf-8"))
        self.service.reset_draft()
        imported = self.service.import_config(self.path)
        self.assertEqual(imported["draft"], exported)
        self.assertEqual(self.board.calls, [])
        for mutate in (lambda c: c["gpio_policy"].__setitem__("4", "flexible"),
                       lambda c: c["pins"].__setitem__("uart1.tx", 25),
                       lambda c: c.__setitem__("fixed", []),
                       lambda c: c.__setitem__("board", "OTHER")):
            invalid = copy.deepcopy(exported)
            mutate(invalid)
            self.path.write_text(json.dumps(invalid), encoding="utf-8")
            with self.assertRaises((ValueError, KeyError, TypeError)):
                self.service.import_config(self.path)
            self.assertEqual(self.view()["draft"], exported)

    def test_disabled_feature_mapping_remains_editable_and_swaps_work(self):
        self.service.set_feature("can", False)
        edited = self.service.set_pin("can.sck", 25)
        self.assertEqual(edited["draft"]["pins"]["can.sck"], 25)
        self.service.set_feature("can", True)
        self.service.set_pin("dap.swclk", 14)
        self.service.check()

    def test_onchip_can_has_no_feature_or_pin_in_legacy_profile(self):
        before = self.view()["draft"]
        for feature in ("twai", "can_internal"):
            with self.assertRaises(ValueError):
                self.service.set_feature(feature, True)
        for signal in ("twai.tx", "twai.rx", "can.tx", "can.rx"):
            with self.assertRaises(ValueError):
                self.service.set_pin(signal, 25)
        self.assertEqual(self.view()["draft"], before)
        self.assertFalse(self.board.calls)

    def test_invalid_fixed_and_input_only_gpio_preserve_correctable_draft(self):
        for gpio in (4, 35, 37):
            draft = self.service.set_pin("can.sck", gpio)["draft"]
            with self.assertRaisesRegex(ValueError, "cannot use GPIO"):
                self.service.check()
            self.assertEqual(self.view()["draft"], draft)
            self.assertTrue(self.view()["preview_tables"]["invalid_pins"])
            self.assertEqual(next(r for r in self.view()["preview_tables"]["candidate_occupancy"]
                                  if r["gpio"] == 4)["owners"], ["uart1.tx"])
        self.service.set_pin("can.sck", 14)
        self.service.check()

    def test_loading_candidate_and_read_snapshots_do_not_alias_state(self):
        self.move_can()
        self.service.save()
        self.service.reset_draft()
        self.assertEqual(self.view()["draft"]["pins"]["can.sck"], 14)
        loaded = self.service.load_candidate()
        self.assertEqual(loaded["draft"]["pins"]["can.sck"], 25)
        loaded["snapshot"]["candidate"]["pins"]["can.sck"] = 4
        loaded["draft"]["pins"]["can.sck"] = 4
        self.assertEqual(self.view()["draft"]["pins"]["can.sck"], 25)
        self.assertEqual(self.board.state["candidate"]["pins"]["can.sck"], 25)

    def test_changed_candidate_and_phase_are_rejected_before_request(self):
        self.move_can()
        self.service.save()
        for key, value in (("candidate_id", 999), ("phase", "trial")):
            original = self.board.state[key]
            self.board.state[key] = value
            count = len(self.board.calls)
            with self.assertRaises((ValueError, RuntimeError)):
                self.service.apply()
            self.assertEqual(len(self.board.calls), count)
            self.board.state[key] = original


class TkTests(unittest.TestCase):
    def setUp(self):
        ServiceTests.setUp(self)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.destroy_window)
        self.gui = app.ProfileApp(self.root, self.service)
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.dialog = patch.object(app.messagebox, "askyesno", return_value=True).start()
        self.showerror = patch.object(app.messagebox, "showerror").start()
        self.addCleanup(patch.stopall)
        self.gui.port_var.set("mock:A")
        self.click("read")

    def destroy_window(self):
        if self.root.winfo_exists():
            if hasattr(self, "gui"):
                self.gui._closed = True
                self.root.after_cancel(self.gui._poll_id)
            self.root.destroy()

    def pump(self):
        """Run Tk's actual event loop, including worker queue polling, with a deadline."""
        end = time.monotonic() + 5
        timed_out = []
        def poll():
            if not self.gui.busy:
                self.root.quit()
            elif time.monotonic() >= end:
                timed_out.append(True)
                self.root.quit()
            else:
                self.root.after(10, poll)
        self.root.after(20, poll)
        self.root.mainloop()
        self.assertFalse(timed_out, "GUI worker failed to finish within 5 seconds")
        self.assertFalse(self.errors, f"Tk callback exception: {self.errors}")

    def click(self, name):
        self.gui.buttons[name].invoke()
        self.pump()

    def feature(self, name):
        self.gui.feature_checks[list(app.FEATURE_NAMES).index(name)].invoke()
        self.pump()

    def pin(self, signal, gpio):
        label = next(label for label, pin in self.gui._pin_choices[signal].items() if pin == gpio)
        self.gui.pin_vars[signal].set(label)
        self.gui.pin_boxes[signal].event_generate("<<ComboboxSelected>>")
        self.pump()

    def visible_signals(self):
        return {signal for signal, box in self.gui.pin_boxes.items() if box.winfo_manager()}

    def test_redesign_v1_disable_move_and_restore_conflict(self):
        """Acceptance 1/2: one draft links both tabs and the panorama."""
        overview = self.gui.overview
        def gpio25_fill():
            rectangle = next(item for item in overview.canvas.find_withtag("gpio-25")
                             if overview.canvas.type(item) == "rectangle")
            return overview.canvas.itemcget(rectangle, "fill")
        self.assertEqual(gpio25_fill(), "#1D4ED8")
        self.assertEqual(overview.mode_var.get(), "current")
        self.assertEqual(overview.counts["occupied"], 9)
        before = (list(self.board.calls), list(self.board.reads))
        self.feature("dap")
        self.assertEqual(overview.mode_var.get(), "draft")
        self.assertEqual(overview.cards[25]["state"], "free")
        self.assertEqual(overview.cards[26]["state"], "free")
        self.assertEqual(gpio25_fill(), "#15803D")
        self.gui.notebook.select(1)
        self.pump()
        self.assertFalse({"dap.swclk", "dap.swdio"} & self.visible_signals())
        self.pin("uart.tx", 25)
        self.assertEqual(overview.cards[25]["state"], "occupied")
        self.assertEqual(overview.cards[32]["state"], "free")
        self.assertEqual(self.service.draft["pins"]["dap.swclk"], 25)
        self.overview_mode("current")
        self.assertEqual(overview.counts["occupied"], 9)
        self.gui.notebook.select(0)
        self.feature("dap")
        self.assertEqual(overview.mode_var.get(), "draft")
        self.assertEqual(overview.cards[25]["state"], "conflict")
        self.assertEqual(gpio25_fill(), "#B91C1C")
        self.assertEqual(self.service.draft["pins"]["dap.swclk"], 25)
        self.gui.notebook.select(1)
        self.pump()
        self.assertTrue({"dap.swclk", "dap.swdio"} <= self.visible_signals())
        for signal in ("uart.tx", "dap.swclk"):
            reason = self.gui.conflict_labels[signal].cget("text")
            self.assertIn("GPIO25", reason.replace(" ", ""))
            self.assertIn("UART2", reason)
            self.assertIn("SWCLK", reason)
        self.assertTrue(any("!" in str(overview.canvas.itemcget(item, "text"))
                            or "\u26a0" in str(overview.canvas.itemcget(item, "text"))
                            for item in overview.canvas.find_all()
                            if overview.canvas.type(item) == "text"))
        self.pin("uart.tx", 32)
        self.assertEqual(gpio25_fill(), "#1D4ED8")
        self.assertEqual(overview.cards[25]["state"], "occupied")
        for signal in ("uart.tx", "dap.swclk"):
            self.assertEqual(self.gui.conflict_labels[signal].cget("text"), "")
        self.assertEqual((self.board.calls, self.board.reads), before)

    def test_redesign_catalog_and_disabled_feature_restore_mapping(self):
        """Acceptance 4: planned entries stay disabled, supported off entries remain usable."""
        self.assertFalse(self.gui.planned_var.get())
        self.gui.planned_toggle.invoke()
        self.pump()
        self.assertTrue(self.gui.planned_var.get())
        for name in ("twai", "i2c0", "i2c1", "gpio", "ledc", "mcpwm", "pcnt", "ethernet"):
            self.assertIn(name, self.gui.planned_widgets)
            self.assertTrue(self.gui.planned_widgets[name].instate(["disabled"]), name)
        original = copy.deepcopy(self.service.draft["pins"])
        self.feature("uart")
        self.assertFalse({"uart.tx", "uart.rx"} & self.visible_signals())
        self.assertFalse(self.gui.feature_widgets["uart"].instate(["disabled"]))
        self.feature("uart")
        self.assertTrue({"uart.tx", "uart.rx"} <= self.visible_signals())
        self.assertEqual(self.service.draft["pins"], original)
        self.assertFalse(self.board.calls)

    def test_redesign_details_ranges_colors_and_candidate_availability(self):
        """Acceptance 5/6: details are local, and candidate exists only after a read-back."""
        overview = self.gui.overview
        self.assertEqual(overview.summary_label.winfo_toplevel(), overview.details_window)
        self.assertEqual(overview.details_window.state(), "withdrawn")
        self.assertFalse(overview.mode_buttons["candidate"].winfo_manager())
        self.assertFalse(self.gui.buttons["apply"].winfo_manager())
        before = (list(self.board.calls), list(self.board.reads))
        overview.open_details()
        self.pump()
        self.assertTrue(overview.details_window.winfo_exists())
        self.overview_toggle_all()
        self.assertEqual(list(overview.cards), list(range(40)))
        self.assertEqual(overview.cards[4]["state"], "fixed")
        self.assertEqual(overview.cards[20]["state"], "unavailable")
        from overview import COLORS
        self.assertNotEqual(COLORS["fixed"][0], COLORS["unavailable"][0])
        self.assertIn("\u8f93\u5165", overview.cards[35]["detail"])
        self.assertIn("MCP2518FD", overview.cards[15]["detail"])
        self.assertEqual((self.board.calls, self.board.reads), before)
        self.feature("dap")
        self.click("save")
        self.assertTrue(overview.mode_buttons["candidate"].winfo_manager())
        self.assertTrue(self.gui.buttons["apply"].winfo_manager())
        self.assertIn("\u5f85\u8bd5\u7528", self.gui.identity_var.get())
        with patch.object(app.messagebox, "showinfo") as showinfo:
            self.click("device_details")
        self.assertTrue(showinfo.called)
        self.assertIn(str(self.gui.view["snapshot"]["revision"]), showinfo.call_args.args[1])
        self.assertIn("101", showinfo.call_args.args[1])

    def test_can_controllers_are_distinct_and_twai_stays_disabled(self):
        text = str(self.gui.feature_widgets["can"]["text"])
        self.assertIn("外置 MCP2518FD", text)
        self.assertIn("CAN FD", text)
        self.assertIn("片上经典 CAN / TWAI", str(self.gui.twai_check["text"]))
        self.assertIn("阶段 2 未实现", str(self.gui.twai_check["text"]))
        before = copy.deepcopy(self.gui.view["draft"])
        for ready in (False, True):
            self.gui.busy = not ready
            self.gui._update_controls()
            self.assertTrue(self.gui.twai_check.instate(["disabled"]))
            self.gui.twai_check.invoke()
            self.assertFalse(self.gui.twai_var.get())
        self.assertEqual(self.service.draft, before)
        self.assertFalse(self.board.calls)
        for enabled in (False, True):
            self.feature("can")
            self.assertEqual(self.gui.view["draft"]["features"]["can"], enabled)
            self.assertTrue(self.gui.twai_check.instate(["disabled"]))
            self.assertFalse(self.gui.twai_var.get())
        self.assertEqual(set(self.gui.feature_vars), set(backend.FEATURES))
        self.assertFalse(any(s.startswith("twai.") or s in ("can.tx", "can.rx")
                             for s in self.gui.pin_boxes))
        self.assertFalse(self.showerror.called)

    def test_buttons_edit_save_reconnect_confirm_and_three_tables(self):
        self.assertEqual(len(self.gui.feature_vars), 9)
        self.assertEqual(len(self.gui.pin_boxes), 9)
        self.assertEqual(len(self.gui.notebook.tabs()), 3)
        self.assertEqual(len(self.gui.occupancy_tree.get_children()), 40)
        fixed = [self.gui.fixed_tree.item(i, "values") for i in self.gui.fixed_tree.get_children()]
        self.assertTrue(any("GPIO 4" in row for row in fixed))
        self.feature("dap")
        self.pin("can.sck", 25)
        self.assertEqual(self.gui.view["draft"]["pins"]["can.sck"], 25)
        self.assertEqual(self.gui.view["snapshot"]["active"]["pins"]["can.sck"], 14)
        self.click("check")
        self.click("save")
        self.assertFalse(self.gui.buttons["apply"].instate(["disabled"]))
        self.assertTrue(self.gui.buttons["confirm"].instate(["disabled"]))
        self.click("apply")
        self.assertTrue(self.dialog.called)
        self.assertIn("120", self.dialog.call_args.args[1])
        for name in ("check", "save", "apply", "confirm", "cancel"):
            self.assertTrue(self.gui.buttons[name].instate(["disabled"]), name)
        self.board.reboot()
        self.click("read")
        self.assertFalse(self.gui.buttons["confirm"].instate(["disabled"]))
        self.click("confirm")
        self.assertEqual(self.gui.view["snapshot"]["phase"], "confirmed")
        self.assertTrue(all(thread_id != threading.get_ident() for _, _, thread_id in self.board.calls))
        self.assertFalse(self.showerror.called)

    def test_error_shown_and_draft_can_be_corrected(self):
        self.pin("can.sck", 25)
        self.assertIn("冲突", self.gui.warning_var.get())
        self.click("check")
        self.assertTrue(self.showerror.called)
        self.assertIn("conflict", str(self.showerror.call_args))
        self.assertEqual(self.gui.view["draft"]["pins"]["can.sck"], 25)
        self.pin("dap.swclk", 14)
        self.showerror.reset_mock()
        self.click("check")
        self.assertFalse(self.showerror.called)
        self.assertNotIn("冲突", self.gui.warning_var.get())

    def test_switch_address_disables_old_draft_writes_and_cancel_read_keeps_it(self):
        self.feature("dap")
        draft = copy.deepcopy(self.gui.view["draft"])
        self.gui.port_var.set("mock:B")
        self.assertTrue(self.gui.buttons["save"].instate(["disabled"]))
        self.assertTrue(self.gui.pin_boxes["can.sck"].instate(["disabled"]))
        self.dialog.return_value = False
        self.click("read")
        self.assertEqual(self.gui.view["draft"], draft)
        self.assertEqual(self.gui.view["connection"]["port"], "mock:A")
        self.dialog.return_value = True
        self.click("read")
        self.assertEqual(self.gui.view["connection"]["port"], "mock:B")
        self.assertFalse(self.gui.view["dirty"])
        self.assertEqual(self.other.calls, [])

    def test_json_buttons_and_invalid_import_keep_current_fixed_table(self):
        self.feature("can")
        self.pin("can.sck", 25)
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(self.path)):
            self.click("export")
        exported = json.loads(self.path.read_text(encoding="utf-8"))
        self.click("reset")
        with patch.object(app.filedialog, "askopenfilename", return_value=str(self.path)):
            self.click("import")
        self.assertEqual(self.gui.view["draft"], exported)
        fixed = self.gui.view["tables"]["fixed"]
        exported["gpio_policy"]["4"] = "flexible"
        self.path.write_text(json.dumps(exported), encoding="utf-8")
        with patch.object(app.filedialog, "askopenfilename", return_value=str(self.path)):
            self.click("import")
        self.assertTrue(self.showerror.called)
        self.assertEqual(self.gui.view["tables"]["fixed"], fixed)
        self.assertEqual(self.gui.view["draft"]["gpio_policy"]["4"], "uart1.tx")
        self.assertEqual(self.board.calls, [])

    def test_feature_only_candidate_summary_and_apply_confirmation(self):
        self.feature("can")
        self.click("save")
        summary = self.gui.candidate_changes()
        self.assertIn(app.FEATURE_NAMES["can"], summary)
        self.assertNotIn("GPIO", summary)
        self.dialog.return_value = False
        self.click("apply")
        self.assertIn(summary, self.dialog.call_args.args[1])
        self.assertFalse(any(op == "apply" for op, *_ in self.board.calls))

    def test_apply_dialog_uses_saved_candidate_instead_of_later_local_draft(self):
        self.feature("dap")
        self.pin("can.sck", 25)
        self.click("save")
        saved_summary = self.gui.candidate_changes()
        self.assertIn("GPIO 25", saved_summary)
        self.pin("can.sck", 13)
        self.assertTrue(self.gui.view["dirty"])
        self.assertEqual(self.gui.candidate_changes(), saved_summary)
        self.dialog.return_value = False
        self.click("apply")
        dialog_body = self.dialog.call_args.args[1]
        self.assertIn(saved_summary, dialog_body)
        self.assertNotIn("GPIO 13", dialog_body)
        self.assertFalse(any(op == "apply" for op, *_ in self.board.calls))

    def overview_mode(self, mode):
        before = (list(self.board.calls), list(self.board.reads))
        self.gui.overview.mode_buttons[mode].invoke()
        self.pump()
        self.assertEqual((self.board.calls, self.board.reads), before,
                         "changing overview mode must not access the device")
        self.assertEqual(self.gui.overview.mode_var.get(), mode)
        return self.gui.overview

    def overview_toggle_all(self):
        before = (list(self.board.calls), list(self.board.reads))
        self.gui.overview.show_all_button.invoke()
        self.pump()
        self.assertEqual((self.board.calls, self.board.reads), before,
                         "changing pin filter must not access the device")
        return self.gui.overview

    def test_persistent_pin_bar_shows_nine_assignable_gpio_and_all_filter_totals(self):
        overview = self.gui.overview
        self.assertNotIn(str(overview), self.gui.notebook.tabs())
        self.assertEqual(len(self.gui.notebook.tabs()), 3)
        self.assertEqual(overview.mode_var.get(), "current")
        self.assertFalse(overview.show_all_var.get())
        self.assertEqual(list(overview.cards), ASSIGNABLE_GPIO)
        self.assertEqual(overview.visible_gpios, ASSIGNABLE_GPIO)
        self.assertEqual(overview.counts,
                         {"free": 0, "occupied": 9, "fixed": 0, "unavailable": 0, "conflict": 0})
        self.assertEqual(sum(overview.counts.values()), 9)
        self.assertTrue(overview.mode_buttons["candidate"].instate(["disabled"]))
        for gpio, owner in ((14, "CAN"), (25, "DAP"), (32, "UART2")):
            self.assertEqual(overview.cards[gpio]["state"], "occupied")
            self.assertIn(owner, overview.cards[gpio]["owner"].upper())
        self.overview_toggle_all()
        self.assertTrue(overview.show_all_var.get())
        self.assertEqual(list(overview.cards), list(range(40)))
        self.assertEqual(overview.visible_gpios, list(range(40)))
        self.assertEqual(overview.counts,
                         {"free": 0, "occupied": 9, "fixed": 23, "unavailable": 8, "conflict": 0})
        self.assertEqual(sum(overview.counts.values()), 40)
        for gpio in (4, 12, 34):
            self.assertEqual(overview.cards[gpio]["state"], "fixed")
        for gpio in (20, 24, 28, 29, 30, 31, 37, 38):
            self.assertEqual(overview.cards[gpio]["state"], "unavailable")
        self.overview_toggle_all()
        self.assertEqual(list(overview.cards), ASSIGNABLE_GPIO)
        self.assertEqual(sum(overview.counts.values()), 9)
        # Query-only startup must leave all actual transaction requests absent.
        self.assertEqual(self.board.calls, [])

    def test_overview_current_isolated_from_draft_conflicts_and_fixed_resources(self):
        self.overview_toggle_all()
        initial = copy.deepcopy(self.gui.overview.cards)
        self.pin("can.sck", 25)
        self.assertEqual(self.gui.overview.mode_var.get(), "draft")
        self.overview_mode("current")
        self.assertEqual(self.gui.overview.cards, initial)
        overview = self.overview_mode("draft")
        self.assertEqual(overview.cards[25]["state"], "conflict")
        self.assertIn("CAN", (overview.cards[25]["owner"] + overview.cards[25]["detail"]).upper())
        self.assertIn("DAP", (overview.cards[25]["owner"] + overview.cards[25]["detail"]).upper())
        self.assertEqual(overview.cards[14]["state"], "free")
        self.assertEqual(overview.counts["conflict"], 1)
        self.assertEqual(sum(overview.counts.values()), 40)
        self.assertEqual(overview.cards[4], initial[4])
        self.pin("dap.swclk", 14)
        self.assertEqual(overview.cards[25]["state"], "occupied")
        self.assertEqual(overview.counts["conflict"], 0)
        self.overview_mode("current")
        self.assertEqual(overview.cards, initial)

    def test_overview_disabled_can_releases_pins_with_electrical_limits(self):
        initial = copy.deepcopy(self.gui.overview.cards)
        self.feature("can")
        self.assertEqual(self.gui.overview.mode_var.get(), "draft")
        self.overview_mode("current")
        self.assertEqual(self.gui.overview.cards, initial)
        overview = self.overview_mode("draft")
        self.assertEqual(overview.counts["free"], 5)
        self.assertEqual(overview.counts["occupied"], 4)
        for gpio in (14, 13, 36, 15, 39):
            self.assertEqual(overview.cards[gpio]["state"], "free")
        self.assertIn("输入", overview.cards[36]["detail"])
        self.assertIn("输入", overview.cards[39]["detail"])
        self.assertIn("CAN", overview.cards[15]["detail"].upper())
        self.assertTrue("CS" in overview.cards[15]["detail"].upper() or "片选" in overview.cards[15]["detail"])
        self.feature("serial")
        self.assertEqual(overview.counts["fixed"], 0)
        self.overview_toggle_all()
        self.assertEqual(overview.cards[4]["state"], "fixed")
        self.assertEqual(overview.cards[34]["state"], "fixed")
        self.assertEqual(overview.counts["fixed"], 23)

    def test_overview_filter_persists_across_modes_and_candidate_fallback(self):
        self.feature("dap")
        self.pin("can.sck", 25)
        self.click("save")
        for mode in ("draft", "candidate", "current"):
            overview = self.overview_mode(mode)
            self.assertFalse(overview.show_all_var.get())
            self.assertEqual(overview.visible_gpios, ASSIGNABLE_GPIO)
            self.assertEqual(sum(overview.counts.values()), 9)
        self.overview_toggle_all()
        for mode in ("candidate", "draft", "current", "candidate"):
            overview = self.overview_mode(mode)
            self.assertTrue(overview.show_all_var.get())
            self.assertEqual(overview.visible_gpios, list(range(40)))
            self.assertEqual(sum(overview.counts.values()), 40)
        self.click("cancel")
        self.assertEqual(overview.mode_var.get(), "current")
        self.assertTrue(overview.show_all_var.get())
        self.assertEqual(overview.visible_gpios, list(range(40)))
        self.overview_toggle_all()
        self.assertEqual(overview.visible_gpios, ASSIGNABLE_GPIO)

    def test_apply_lost_ack_preserves_draft_requires_read_and_never_retries(self):
        self.feature("dap")
        self.pin("can.sck",25)
        self.click("save")
        self.pin("uart.tx",26)
        draft=copy.deepcopy(self.service.draft)
        original=self.board.request

        def missing_ack(op,data=b""):
            result=original(op,data)
            if op=="apply":
                raise backend.cli.ApplyOutcomeUnknown("APPLY result unknown")
            return result

        self.board.request=missing_ack
        self.click("apply")
        self.assertEqual(self.service.draft,draft)
        self.assertTrue(self.gui.view["requires_reconnect"])
        self.assertEqual(sum(op=="apply" for op,*_ in self.board.calls),1)
        self.assertTrue(self.gui.buttons["apply"].instate(["disabled"]))
        self.assertTrue(self.gui.buttons["save"].instate(["disabled"]))
        self.click("apply")
        self.assertEqual(sum(op=="apply" for op,*_ in self.board.calls),1)
        self.assertIn("ID 101",self.gui.status_var.get())
        self.board.reboot()
        self.click("read")
        self.assertEqual(self.gui.view["snapshot"]["phase"],"trial")
        self.assertEqual(self.service.draft,draft)
        self.assertTrue(self.gui.view["dirty"])
        self.assertFalse(self.gui.view["requires_reconnect"])
        self.assertEqual(sum(op=="apply" for op,*_ in self.board.calls),1)

    def test_overview_sparse_grid_clicks_open_real_gpio_details(self):
        self.root.deiconify()
        self.root.geometry("1024x650")
        overview = self.gui.overview
        before = (list(self.board.calls), list(self.board.reads))

        def wait_for_ui(predicate, description):
            deadline = time.monotonic() + 5
            complete = []

            def poll():
                if predicate():
                    complete.append(True)
                    self.root.quit()
                elif time.monotonic() >= deadline:
                    self.root.quit()
                else:
                    self.root.after(10, poll)

            self.root.after(10, poll)
            self.root.mainloop()
            self.assertTrue(complete, description)
            self.assertFalse(self.errors, f"Tk callback exception: {self.errors}")

        def wait_for_geometry():
            previous = None
            stable = 0

            def ready():
                nonlocal previous, stable
                canvas = overview.canvas
                if not self.root.winfo_viewable() or not canvas.winfo_viewable():
                    stable = 0
                    return False
                geometry = (canvas.winfo_width(), canvas.winfo_height(),
                            tuple(sorted(overview.card_bounds.items())))
                stable = stable + 1 if geometry == previous else 0
                previous = geometry
                expected_height = overview.card_height * (5 if overview.show_all_var.get() else 1)
                return (stable >= 2 and geometry[0] > 1 and geometry[1] == expected_height
                        and set(overview.card_bounds) == set(overview.cards))

            wait_for_ui(ready, "Canvas must be mapped with stable card geometry before clicking")

        with patch.object(app.messagebox, "showinfo") as showinfo:
            def click_card(gpio):
                wait_for_geometry()
                showinfo.reset_mock()
                x0, y0, x1, y1 = overview.card_bounds[gpio]
                overview.canvas.event_generate(
                    "<Button-1>", x=int((x0 + x1) / 2), y=int((y0 + y1) / 2), when="tail")
                wait_for_ui(lambda: showinfo.called, f"GPIO {gpio} click must open its details")
                showinfo.assert_called_once()
                self.assertIn(f"GPIO {gpio}", showinfo.call_args.args[0])
                self.assertEqual(showinfo.call_args.args[1], overview.cards[gpio]["detail"])

            for gpio in (13, 25, 39):
                click_card(gpio)
            self.overview_toggle_all()
            for gpio in (4, 39):
                click_card(gpio)
        self.assertEqual((self.board.calls, self.board.reads), before)

    def test_overview_keyboard_focus_and_return_open_pin_limits_without_io(self):
        self.root.deiconify()
        self.root.geometry("1024x650")
        self.root.update()
        overview = self.gui.overview
        before = (list(self.board.calls), list(self.board.reads))
        overview.canvas.focus_force()
        self.root.update()
        with patch.object(app.messagebox, "showinfo") as showinfo:
            overview.canvas.event_generate("<Home>")
            self.root.update()
            self.assertEqual(overview.focused_gpio, ASSIGNABLE_GPIO[0])
            overview.canvas.event_generate("<End>")
            self.root.update()
            self.assertEqual(overview.focused_gpio, 39)
            self.assertIn("\u8f93\u5165", overview.detail_var.get())
            overview.canvas.event_generate("<Return>")
            self.root.update()
            showinfo.assert_called_once()
            self.assertIn("GPIO 39", showinfo.call_args.args[0])
            self.assertIn("\u8f93\u5165", showinfo.call_args.args[1])
        self.assertEqual((self.board.calls, self.board.reads), before)

    def test_pin_bar_stays_visible_above_every_tab_with_compact_single_row(self):
        self.root.deiconify()
        self.root.geometry("1024x650")
        self.root.update_idletasks()
        self.pump()
        overview = self.gui.overview
        self.assertNotIn(str(overview), self.gui.notebook.tabs())
        self.assertEqual(len(self.gui.notebook.tabs()), 3)
        self.assertLessEqual(overview.winfo_height(), 80)
        self.assertEqual(overview.canvas.winfo_height(), overview.card_height)
        self.assertEqual(len({round(bounds[1], 1) for bounds in overview.card_bounds.values()}), 1)
        self.assertLessEqual(overview.winfo_rooty() + overview.winfo_height(), self.gui.notebook.winfo_rooty())
        before = (list(self.board.calls), list(self.board.reads))
        for tab in self.gui.notebook.tabs():
            self.gui.notebook.select(tab)
            self.pump()
            self.assertTrue(overview.winfo_ismapped())
            self.assertTrue(overview.canvas.winfo_ismapped())
            self.assertEqual(overview.visible_gpios, ASSIGNABLE_GPIO)
            self.assertLessEqual(overview.winfo_height(), 80)
        self.assertEqual((self.board.calls, self.board.reads), before)

    def test_pin_bar_expansion_reclaims_height_and_keeps_modes_across_tabs(self):
        self.root.deiconify()
        self.root.geometry("1024x650")
        self.root.update_idletasks()
        self.pump()
        overview = self.gui.overview
        compact_height = overview.winfo_height()
        compact_notebook_height = self.gui.notebook.winfo_height()
        self.feature("dap")
        self.pin("can.sck", 25)
        self.click("save")
        self.overview_mode("candidate")
        self.overview_toggle_all()
        self.root.update_idletasks()
        self.assertGreater(overview.winfo_height(), compact_height)
        self.assertEqual(len(overview.card_bounds), 40)
        self.assertGreater(len({round(b[1], 1) for b in overview.card_bounds.values()}), 1)
        before = (list(self.board.calls), list(self.board.reads))
        for tab in self.gui.notebook.tabs():
            self.gui.notebook.select(tab)
            self.pump()
            self.assertTrue(overview.winfo_ismapped())
            self.assertEqual(overview.mode_var.get(), "candidate")
            self.assertTrue(overview.show_all_var.get())
            self.assertEqual(len(overview.cards), 40)
        self.assertEqual((self.board.calls, self.board.reads), before)
        self.overview_toggle_all()
        self.root.update_idletasks()
        self.assertEqual(overview.mode_var.get(), "candidate")
        self.assertEqual(overview.visible_gpios, ASSIGNABLE_GPIO)
        self.assertEqual(overview.winfo_height(), compact_height)
        self.assertGreaterEqual(self.gui.notebook.winfo_height(), compact_notebook_height)
        self.assertEqual(len({round(bounds[1], 1) for bounds in overview.card_bounds.values()}), 1)

    def test_overview_candidate_mode_saves_without_changing_current_then_disables_after_cancel(self):
        initial = copy.deepcopy(self.gui.overview.cards)
        self.feature("dap")
        self.pin("can.sck", 25)
        self.click("save")
        self.assertEqual(self.gui.overview.mode_var.get(), "draft")
        self.overview_mode("current")
        self.assertEqual(self.gui.overview.cards, initial)
        self.assertFalse(self.gui.overview.mode_buttons["candidate"].instate(["disabled"]))
        overview = self.overview_mode("candidate")
        self.assertEqual(overview.cards[14]["state"], "free")
        self.assertEqual(overview.cards[25]["state"], "occupied")
        self.assertIn("CAN", overview.cards[25]["owner"].upper())
        candidate = copy.deepcopy(overview.cards)
        self.pin("can.sck", 13)
        self.assertEqual(overview.mode_var.get(), "draft")
        self.overview_mode("candidate")
        self.assertEqual(overview.cards, candidate)
        self.overview_mode("current")
        self.assertEqual(overview.cards, initial)
        self.overview_mode("candidate")
        self.click("cancel")
        self.assertTrue(overview.mode_buttons["candidate"].instate(["disabled"]))
        self.assertEqual(overview.mode_var.get(), "current")
        self.assertEqual(overview.cards, initial)

    def test_overview_refresh_tracks_trial_and_reset_rollback(self):
        initial = copy.deepcopy(self.gui.overview.cards)
        self.feature("dap")
        self.pin("can.sck", 25)
        self.click("save")
        self.click("apply")
        self.board.reboot()
        self.click("read")
        self.assertEqual(self.gui.view["snapshot"]["phase"], "trial")
        self.assertEqual(self.gui.overview.cards[14]["state"], "free")
        self.assertIn("CAN", self.gui.overview.cards[25]["owner"].upper())
        self.board.reboot()
        self.click("read")
        self.assertEqual(self.gui.view["snapshot"]["phase"], "confirmed")
        self.assertEqual(self.gui.overview.cards, initial)
        self.assertTrue(self.gui.overview.mode_buttons["candidate"].instate(["disabled"]))


class V2TkTests(unittest.TestCase):
    destroy_window = TkTests.destroy_window
    pump = TkTests.pump
    click = TkTests.click
    feature = TkTests.feature
    pin = TkTests.pin
    visible_signals = TkTests.visible_signals
    test_can_controllers_are_distinct_and_twai_stays_disabled = TkTests.test_can_controllers_are_distinct_and_twai_stays_disabled
    test_onchip_can_has_no_feature_or_pin_in_v2_profile = ServiceTests.test_onchip_can_has_no_feature_or_pin_in_legacy_profile
    view = ServiceTests.view

    def setUp(self):
        TkTests.setUp(self)
        fixture = HERE.parents[1] / "script/test/fixtures/profile/v2-default.json"
        config=json.loads(fixture.read_text())
        self.board.desc={k:config[k] for k in ("schema","board","gpio_policy","capabilities")}
        mapping={k:config[k] for k in ("features","pins","spi","external","mcp2518fd")}
        self.board.state.update(active=copy.deepcopy(mapping),candidate=None)
        self.board.confirmed=copy.deepcopy(mapping)
        self.click("read")

    def parameter(self, instance, field, value):
        key=(instance,field)
        widget = self.gui.parameter_widgets[key]
        if isinstance(widget, app.ttk.Checkbutton):
            desired = "开" if value else "关"
            if self.gui.parameter_vars[key].get() != desired:
                widget.invoke()
        else:
            self.gui.parameter_vars[key].set(str(value))
            widget.event_generate("<<ComboboxSelected>>")
        self.pump()

    def test_external_can_selects_either_spi_host_and_roundtrips(self):
        box = self.gui.parameter_widgets[("mcp2518fd", "host")]
        self.assertEqual(tuple(box["values"]), ("2", "3"))
        self.assertTrue(box.instate(["readonly"]))
        initial = copy.deepcopy(self.board.state["active"])
        for host in (2, 3):
            with self.subTest(host=host):
                self.parameter("mcp2518fd", "host", host)
                self.assertEqual(self.service.draft["mcp2518fd"]["host"], host)
                self.assertEqual(self.board.state["active"], initial)
                self.assertTrue(self.service.draft["features"]["can"])
                self.assertTrue(self.gui.twai_check.instate(["disabled"]))
                self.click("check")
                self.click("save")
                self.assertEqual(self.board.state["candidate"]["mcp2518fd"]["host"], host)
                saved = backend.cli.decode_mapping(self.board.calls[-1][1][4:])
                self.assertEqual(saved["mcp2518fd"]["host"], host)
                self.assertEqual(set(saved["features"]), set(backend.FEATURES))
                self.click("cancel")
        self.assertFalse(self.showerror.called)

    def test_same_fixture_width_candidate_trial_confirm_and_release(self):
        self.assertEqual(len(self.gui.pin_boxes),17)
        self.assertEqual(len(self.gui.overview.cards),15)
        self.assertEqual(self.gui.overview.counts["occupied"],15)
        initial=copy.deepcopy(self.gui.overview.cards)
        self.parameter("spi2","width",1)
        self.assertEqual(self.gui.overview.mode_var.get(),"draft")
        self.gui.overview.mode_buttons["current"].invoke()
        self.assertEqual(self.gui.overview.cards,initial)
        self.gui.overview.mode_var.set("draft");self.gui.overview.refresh()
        self.assertEqual(self.gui.overview.counts["occupied"],13)
        self.assertEqual(self.gui.overview.cards[22]["state"],"free")
        self.click("check");self.click("save")
        self.assertIn("\u6700\u5927\u7ebf\u5bbd",self.gui.candidate_changes())
        self.assertIn("4",self.gui.candidate_changes())
        self.click("apply");self.board.reboot();self.click("read")
        self.assertEqual(self.gui.view["snapshot"]["phase"],"trial")
        self.click("confirm")
        self.gui.overview.mode_var.set("current");self.gui.overview.refresh()
        self.assertEqual(self.gui.overview.counts["occupied"],13)
        self.parameter("external","enabled",False);self.parameter("spi2","enabled",False)
        self.gui.overview.mode_var.set("draft");self.gui.overview.refresh()
        self.assertEqual(self.gui.overview.counts["occupied"],9)

    def test_redesign_spi_rows_follow_owners_width_and_preserve_tab_state(self):
        """Acceptance 3: device CS and host buses have independent visibility."""
        overview = self.gui.overview
        self.parameter("external", "enabled", False)
        self.assertNotIn("external.cs", self.visible_signals())
        self.assertTrue({"spi2.sck", "spi2.mosi", "spi2.miso", "spi2.io2", "spi2.io3"} <= self.visible_signals())
        self.parameter("spi2", "enabled", False)
        self.assertFalse(any(s.startswith("spi2.") for s in self.visible_signals()))
        self.assertEqual(overview.counts["occupied"], 9)
        self.assertEqual(overview.counts["free"], 6)
        overview.open_details()
        overview.show_all_button.invoke()
        draft = copy.deepcopy(self.service.draft)
        before = (list(self.board.calls), list(self.board.reads))
        for tab in self.gui.notebook.tabs():
            self.gui.notebook.select(tab)
            self.pump()
            self.assertEqual(self.service.draft, draft)
            self.assertEqual(overview.mode_var.get(), "draft")
            self.assertTrue(overview.show_all_var.get())
            self.assertEqual(len(overview.cards), 40)
        self.assertEqual((self.board.calls, self.board.reads), before)
        self.parameter("spi2", "enabled", True)
        self.parameter("spi2", "width", 1)
        self.assertFalse({"spi2.io2", "spi2.io3"} & self.visible_signals())
        self.parameter("spi2", "width", 4)
        self.assertTrue({"spi2.io2", "spi2.io3"} <= self.visible_signals())
        self.feature("can")
        self.assertFalse({"can.cs", "can.int"} & self.visible_signals())
        self.assertTrue({"spi3.sck", "spi3.mosi", "spi3.miso"} <= self.visible_signals())

    def test_v1_import_and_revision_identity_guards(self):
        path=HERE.parents[1] / "script/test/fixtures/profile/v1-nondefault.json"
        self.gui._submit("Import",lambda:self.service.import_config(path));self.pump()
        self.assertEqual(self.gui.view["draft"]["pins"]["uart.tx"],25)
        self.assertEqual(self.gui.view["draft"]["spi"]["2"]["width"],4)
        self.assertFalse(self.board.calls)
        draft=copy.deepcopy(self.service.draft)
        self.board.identity="replacement"
        self.click("save")
        self.assertEqual(self.service.draft,draft)
        self.assertFalse(self.board.calls)
        self.board.identity="board-A";self.board.state["revision"]+=1
        self.click("save")
        self.assertEqual(self.service.draft,draft)
        self.assertFalse(self.board.calls)

    def test_quad_candidate_excludes_input_only_data_and_old_board_hides_extension(self):
        self.parameter("spi3","width",4)
        for signal in ("spi3.mosi","spi3.miso","spi3.io2","spi3.io3"):
            self.assertNotIn(36,self.gui._pin_choices[signal].values())
        self.assertIn("SPI3",self.gui.warning_var.get().upper())
        self.service.read("mock:B",115200,discard_draft=True)
        self.gui.port_var.set("mock:B");self.click("read")
        self.assertEqual(len(self.gui.pin_boxes),9)
        self.assertFalse(self.gui.extension.winfo_manager())


class V3ServiceTests(unittest.TestCase):
    def setUp(self):
        ServiceTests.setUp(self)
        config=json.loads((HERE.parents[1]/"script/test/fixtures/profile/v2-default.json").read_text())
        self.board.desc={k:config[k] for k in ("schema","board","gpio_policy","capabilities")}
        self.board.desc.update(schema=3,capabilities=63)
        mapping={k:config[k] for k in ("features","pins","spi","external","mcp2518fd")}
        mapping["external2"]={"enabled":False,"host":2,"cs":255}
        self.board.state.update(active=mapping,candidate=None)
        self.service.read("mock:A",115200)

    def test_capability_gates_reject_unsupported_no_cs_and_second_device(self):
        for schema,caps in ((1,0),(2,15),(3,15)):
            self.service.descriptor.update(schema=schema,capabilities=caps)
            before=copy.deepcopy(self.service.draft)
            for operation in (
                lambda:self.service.set_parameter("external2","enabled",True),
                lambda:self.service.set_parameter("external","use_cs",False),
                lambda:self.service.set_pin("external.cs",255),
            ):
                with self.assertRaises(ValueError):operation()
                self.assertEqual(self.service.draft,before)
        self.service.descriptor.update(schema=3,capabilities=31)
        self.service.set_parameter("external2","enabled",True)
        with self.assertRaises(ValueError):self.service.set_parameter("external2","use_cs",False)
        self.assertFalse(self.board.calls)

    def test_reset_and_new_read_replace_cs_memory_with_snapshot(self):
        self.service.set_feature("dap",False)
        self.service.set_pin("external.cs",25)
        self.service.set_parameter("external","use_cs",False)
        self.service.reset_draft()
        self.service.set_parameter("external","use_cs",False)
        self.service.set_parameter("external","use_cs",True)
        self.assertEqual(self.service.draft["external"]["cs"],27)
        self.service.set_pin("external.cs",26)
        self.service.set_parameter("external","use_cs",False)
        self.service.read("mock:A",115200,discard_draft=True)
        self.service.set_parameter("external","use_cs",False)
        self.service.set_parameter("external","use_cs",True)
        self.assertEqual(self.service.draft["external"]["cs"],27)
        self.assertFalse(self.board.calls)

    def test_load_candidate_replaces_later_cs_memory(self):
        self.service.set_feature("dap",False)
        self.service.set_pin("external.cs",25)
        self.service.save()
        self.service.set_pin("external.cs",26)
        self.service.set_parameter("external","use_cs",False)
        self.service.load_candidate()
        self.service.set_parameter("external","use_cs",False)
        self.service.set_parameter("external","use_cs",True)
        self.assertEqual(self.service.draft["external"]["cs"],25)
        self.assertEqual(self.board.state["candidate"]["external"]["cs"],25)
        self.assertEqual(sum(op=="save" for op,*_ in self.board.calls),1)

    def test_unknown_apply_reconnect_preserves_unsaved_cs_memory(self):
        self.service.set_feature("dap",False)
        self.service.save()
        self.service.set_pin("external.cs",25)
        self.service.set_parameter("external","use_cs",False)
        original=self.board.request
        def lost_ack(op,data=b""):
            result=original(op,data)
            if op=="apply":raise backend.ApplyOutcomeUnknown("lost acknowledgement")
            return result
        self.board.request=lost_ack
        with self.assertRaises(backend.ApplyOutcomeUnknown):self.service.apply()
        self.board.reboot();self.service.read("mock:A",115200)
        self.assertTrue(self.service.dirty)
        self.assertEqual(self.service.draft["external"]["cs"],255)
        self.service.set_parameter("external","use_cs",True)
        self.assertEqual(self.service.draft["external"]["cs"],25)
        self.assertEqual(sum(op=="apply" for op,*_ in self.board.calls),1)


class V3TkTests(unittest.TestCase):
    destroy_window = TkTests.destroy_window
    pump = TkTests.pump
    click = TkTests.click
    feature = TkTests.feature
    pin = TkTests.pin
    visible_signals = TkTests.visible_signals
    overview_mode = TkTests.overview_mode
    parameter = V2TkTests.parameter

    def setUp(self):
        V2TkTests.setUp(self)
        self.board.desc.update(schema=3, capabilities=63)
        self.board.state["active"]["external2"]={"enabled":False,"host":2,"cs":255}
        self.board.confirmed=copy.deepcopy(self.board.state["active"])
        self.click("read")

    def test_capabilities_expose_two_devices_without_inventing_a_cs(self):
        self.assertEqual(len(self.gui.pin_boxes),18)
        self.assertIn(("external2","enabled"),self.gui.parameter_widgets)
        for device in ("external","external2"):
            self.assertIn((device,"use_cs"),self.gui.parameter_widgets)
        self.assertNotIn("external2.cs",self.visible_signals())
        self.assertEqual(self.gui.overview.counts["occupied"],15)
        self.parameter("external2","enabled",True)
        self.assertEqual(self.service.draft["external2"]["cs"],255)
        self.assertNotIn("external2.cs",self.visible_signals())
        self.assertFalse(self.board.calls)

    def test_capability_refresh_rebuilds_optional_controls_on_the_same_schema(self):
        for caps,dual,no_cs in ((15,False,False),(31,True,False),(63,True,True)):
            self.board.desc["capabilities"]=caps
            self.click("read")
            self.assertEqual(("external2","enabled") in self.gui.parameter_widgets,dual)
            self.assertEqual(("external","use_cs") in self.gui.parameter_widgets,no_cs)
            self.assertEqual(("external2","use_cs") in self.gui.parameter_widgets,dual and no_cs)
            if dual and not no_cs:
                self.parameter("external2", "enabled", True)
                self.assertNotEqual(self.service.draft["external2"]["cs"], 255)
                self.assertIn("external2.cs", self.visible_signals())
        self.assertFalse(self.board.calls)
        self.assertFalse(self.showerror.called)

    def test_cs_toggle_releases_restores_each_devices_last_gpio_without_io(self):
        self.feature("dap")
        self.parameter("external2","enabled",True)
        self.parameter("external2","host",3)
        self.parameter("external2","use_cs",True)
        self.pin("external2.cs",25)
        self.pin("external.cs",26)
        before=(list(self.board.calls),list(self.board.reads))
        for device,gpio in (("external",26),("external2",25)):
            with self.subTest(device=device):
                self.parameter(device,"use_cs",False)
                self.assertEqual(self.service.draft[device]["cs"],255)
                self.assertNotIn(device+".cs",self.visible_signals())
                self.assertEqual(self.gui.overview.cards[gpio]["state"],"free")
                self.parameter(device,"use_cs",True)
                self.assertEqual(self.service.draft[device]["cs"],gpio)
                self.assertIn(device+".cs",self.visible_signals())
                self.assertEqual(self.gui.overview.cards[gpio]["state"],"occupied")
        self.assertEqual((self.board.calls,self.board.reads),before)
        self.assertFalse(self.showerror.called)

    def test_no_cs_shared_host_warns_both_devices_and_can_then_clears(self):
        self.parameter("external","use_cs",False)
        self.parameter("external2","enabled",True)
        for device in ("external","external2"):
            warning=self.gui.device_conflict_labels[device].cget("text")
            self.assertTrue(warning,device)
            self.assertIn("SPI2",warning)
        self.click("check")
        self.assertTrue(self.showerror.called)
        self.parameter("external2","enabled",False)
        for device in ("external","external2"):
            self.assertEqual(self.gui.device_conflict_labels[device].cget("text"),"")
        self.parameter("external","host",3)
        for device in ("external","mcp2518fd"):
            self.assertIn("SPI3",self.gui.device_conflict_labels[device].cget("text"))
        self.feature("can")
        self.assertEqual(self.gui.device_conflict_labels["external"].cget("text"),"")
        self.assertEqual(self.gui.device_conflict_labels["mcp2518fd"].cget("text"),"")
        self.showerror.reset_mock()
        self.click("check")
        self.assertFalse(self.showerror.called)

    def test_no_cs_candidate_snapshot_import_and_trial_confirmation(self):
        self.parameter("external","use_cs",False)
        self.click("save")
        self.assertEqual(len(self.board.calls[-1][1]),33)
        self.assertEqual(self.board.state["candidate"]["external"]["cs"],255)
        self.assertEqual(self.board.state["active"]["external"]["cs"],27)
        self.overview_mode("current")
        self.assertEqual(self.gui.overview.cards[27]["state"],"occupied")
        self.overview_mode("candidate")
        self.assertEqual(self.gui.overview.cards[27]["state"],"free")
        saved=self.gui.candidate_changes()
        self.assertTrue(saved)
        self.assertNotIn("GPIO 255",saved)
        self.assertNotIn("GPIO255",saved)
        self.parameter("external","use_cs",True)
        self.assertEqual(self.gui.candidate_changes(),saved)
        self.click("load_candidate")
        self.assertEqual(self.service.draft["external"]["cs"],255)
        self.assertNotIn("external.cs",self.visible_signals())
        with patch.object(app.filedialog,"asksaveasfilename",return_value=str(self.path)):
            self.click("export")
        exported=json.loads(self.path.read_text(encoding="utf8"))
        self.assertEqual(exported["external"]["cs"],255)
        self.assertEqual(exported["external2"],{"enabled":False,"host":2,"cs":255})
        self.click("apply");self.board.reboot();self.click("read");self.click("confirm")
        self.assertEqual(self.board.state["active"]["external"]["cs"],255)
        self.assertEqual(self.gui.view["snapshot"]["phase"],"confirmed")
        self.assertEqual(self.gui.overview.cards[27]["state"],"free")
        self.assertFalse(self.showerror.called)

    def test_legacy_import_upgrades_draft_only_and_replaces_cs_memory(self):
        self.feature("dap")
        self.pin("external.cs",25)
        self.parameter("external","use_cs",False)
        path=HERE.parents[1]/"script/test/fixtures/profile/v2-default.json"
        with patch.object(app.filedialog,"askopenfilename",return_value=str(path)):
            self.click("import")
        self.assertEqual(self.service.draft["schema"],3)
        self.assertEqual(self.service.draft["external"]["cs"],27)
        self.assertEqual(self.service.draft["external2"]["cs"],255)
        self.parameter("external","use_cs",False)
        self.parameter("external","use_cs",True)
        self.assertEqual(self.service.draft["external"]["cs"],27)
        self.assertFalse(self.board.calls)
        self.assertFalse(self.showerror.called)

    def test_switching_v3_v2_v1_destroys_unsupported_controls_and_old_memory(self):
        self.parameter("external","use_cs",False)
        fixture=HERE.parents[1]/"script/test/fixtures/profile/v2-default.json"
        config=json.loads(fixture.read_text())
        self.board.desc={k:config[k] for k in ("schema","board","gpio_policy","capabilities")}
        mapping={k:config[k] for k in ("features","pins","spi","external","mcp2518fd")}
        self.board.state.update(active=mapping,candidate=None)
        self.click("read")
        self.assertNotIn(("external2","enabled"),self.gui.parameter_widgets)
        self.assertNotIn(("external","use_cs"),self.gui.parameter_widgets)
        self.assertEqual(len(self.gui.pin_boxes),17)
        for instance,field in (("external2","enabled"),("external","use_cs")):
            with self.assertRaises(ValueError):
                self.service.set_parameter(instance,field,True)
        self.gui.port_var.set("mock:B");self.click("read")
        self.assertEqual(len(self.gui.pin_boxes),9)
        self.assertFalse(self.gui.extension.winfo_manager())
        self.assertEqual(self.gui.parameter_widgets,{})
        self.assertFalse(self.showerror.called)


class V4TkTests(unittest.TestCase):
    destroy_window = TkTests.destroy_window
    pump = TkTests.pump
    click = TkTests.click
    feature = TkTests.feature
    parameter = V2TkTests.parameter
    overview_mode = TkTests.overview_mode

    def setUp(self):
        V3TkTests.setUp(self)
        self.board.desc.update(schema=4, capabilities=127)
        self.board.state["active"]["uart1_business"] = False
        self.board.confirmed = copy.deepcopy(self.board.state["active"])
        self.click("read")

    def business(self):
        self.gui.uart1_business_check.invoke()
        self.pump()

    def test_groups_spi_checkboxes_and_unique_can_entry(self):
        self.assertEqual(set(self.gui.feature_groups), {"management", "network", "serial", "spi"})
        self.assertIs(self.gui.feature_widgets["can"].master, self.gui.feature_groups["spi"])
        self.assertIs(self.gui.feature_widgets["serial"].master, self.gui.feature_groups["management"])
        for key, widget in self.gui.parameter_widgets.items():
            expected = app.ttk.Checkbutton if key[1] in ("enabled", "use_cs") else app.ttk.Combobox
            self.assertIsInstance(widget, expected, key)
        self.assertEqual(sum(widget is self.gui.feature_widgets["can"] for widget in self.gui.feature_checks), 1)

    def test_uart1_three_roles_are_atomic_and_uart2_stays_independent(self):
        original = copy.deepcopy(self.board.state["active"])
        before = (list(self.board.calls), list(self.board.reads))
        self.assertTrue(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertIn("由串口控制使用", self.gui.uart1_state.cget("text"))
        self.business()
        self.assertFalse(self.service.draft["uart1_business"])
        self.feature("serial")
        self.assertFalse(self.service.draft["uart1_business"])
        self.assertFalse(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertIn("UART1 保留", self.gui.uart1_role_var.get())
        self.business()
        self.assertTrue(self.service.draft["uart1_business"])
        self.assertIn("UART1 用于普通收发", self.gui.feature_states["serial"].cget("text"))
        self.feature("uart")
        self.assertTrue(self.service.draft["uart1_business"])
        self.assertFalse(self.service.draft["features"]["uart"])
        self.feature("serial")
        self.assertFalse(self.service.draft["uart1_business"])
        self.assertTrue(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertFalse(self.service.draft["features"]["uart"])
        self.assertEqual(self.board.state["active"], original)
        self.assertEqual((self.board.calls, self.board.reads), before)
        self.assertFalse(self.showerror.called)

    def test_uart1_candidate_roles_fixed_pins_and_network_trial_hint(self):
        self.feature("serial")
        self.business()
        self.gui.overview.show_all_button.invoke()
        self.overview_mode("draft")
        self.assertIn("普通串口", self.gui.overview.cards[4]["owner"])
        self.overview_mode("current")
        self.assertIn("串口控制", self.gui.overview.cards[4]["owner"])
        self.click("save")
        self.assertEqual(len(self.board.calls[-1][1]), 34)
        self.assertTrue(self.board.state["candidate"]["uart1_business"])
        self.assertIn("UART1：串口控制 → 普通串口", self.gui.candidate_changes())
        self.overview_mode("candidate")
        self.assertIn("普通串口", self.gui.overview.cards[34]["owner"])
        fixed = [self.gui.fixed_tree.item(i,"values") for i in self.gui.fixed_tree.get_children()]
        uart1 = next(row for row in fixed if row[0] == "GPIO 4")
        self.assertIn("当前 串口控制", uart1[1])
        self.assertIn("候选 普通串口", uart1[1])
        saved = self.gui.candidate_changes()
        self.feature("serial")
        self.assertEqual(self.gui.candidate_changes(), saved)
        self.click("apply")
        self.assertIn("socket://设备IP:9500", self.dialog.call_args.args[1])
        self.board.reboot()
        self.click("read")
        self.assertTrue(self.gui.view["snapshot"]["active"]["uart1_business"])
        self.click("confirm")
        self.assertEqual(self.gui.view["snapshot"]["phase"], "confirmed")
        self.assertFalse(self.showerror.called)

    def test_uart1_management_conditions_import_and_old_capability(self):
        self.feature("serial")
        self.feature("control_tcp")
        self.assertIn("请启用 TCP 9500", self.gui.management_hint_var.get())
        self.feature("wifi")
        self.assertIn("Wi-Fi STA", self.gui.management_hint_var.get())
        fixture = HERE.parents[1] / "script/test/fixtures/profile/v2-default.json"
        with patch.object(app.filedialog, "askopenfilename", return_value=str(fixture)):
            self.click("import")
        self.assertEqual(self.service.draft["schema"], 4)
        self.assertFalse(self.service.draft["uart1_business"])
        self.assertTrue(self.service.draft["features"]["serial"])
        self.board.desc["capabilities"] = 63
        self.click("read")
        self.assertTrue(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertIn("当前固件不支持", self.gui.uart1_state.cget("text"))
        with self.assertRaises(ValueError):
            self.service.set_parameter("uart1", "enabled", True)
        self.board.desc.update(schema=3, capabilities=63)
        self.board.state["active"].pop("uart1_business")
        self.click("read")
        self.assertNotIn("uart1_business", self.service.draft)
        self.assertTrue(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertFalse(self.showerror.called)

    def test_uart1_json_candidate_replace_and_interrupted_trial_rollback(self):
        self.feature("serial")
        self.business()
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(self.path)):
            self.click("export")
        exported = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(exported["uart1_business"])
        self.assertFalse(exported["features"]["serial"])
        self.click("reset")
        self.assertFalse(self.gui.uart1_business_var.get())
        with patch.object(app.filedialog, "askopenfilename", return_value=str(self.path)):
            self.click("import")
        self.assertTrue(self.gui.uart1_business_var.get())
        self.assertEqual(self.gui.overview.mode_var.get(), "draft")
        for signal in ("uart.tx", "uart.rx"):
            self.assertNotIn(4, self.gui._pin_choices[signal].values())
            self.assertNotIn(34, self.gui._pin_choices[signal].values())
        self.click("save")
        self.click("reset")
        self.assertFalse(self.gui.uart1_business_var.get())
        self.click("load_candidate")
        self.assertTrue(self.gui.uart1_business_var.get())
        self.click("apply")
        self.board.reboot()
        self.click("read")
        self.assertTrue(self.gui.view["snapshot"]["active"]["uart1_business"])
        self.board.reboot()
        self.click("read")
        self.assertFalse(self.gui.view["snapshot"]["active"]["uart1_business"])
        self.assertTrue(self.gui.feature_vars["serial"].get())
        self.assertTrue(self.gui.uart1_business_check.instate(["disabled"]))
        self.assertFalse(self.showerror.called)


class FeedbackTkTests(unittest.TestCase):
    """Mapped Tk geometry and effective widget colors, with real control events."""
    destroy_window = TkTests.destroy_window
    pump = TkTests.pump
    click = TkTests.click
    feature = TkTests.feature
    pin = TkTests.pin
    parameter = V2TkTests.parameter
    business = V4TkTests.business

    def setUp(self):
        V4TkTests.setUp(self)
        self.root.deiconify()
        self.root.geometry("1024x650")
        self.gui.notebook.select(0)
        self.root.update()
        self.pump()

    def geometry(self,widgets):
        self.root.update_idletasks()
        result={}
        for name,widget in widgets.items():
            self.assertTrue(widget.winfo_ismapped(),name)
            result[name]=(widget.winfo_rootx(),widget.winfo_rooty(),widget.winfo_width(),widget.winfo_height())
        return result

    def controls(self):
        return {**{"feature:"+k:v for k,v in self.gui.feature_widgets.items()},
                **{"parameter:"+str(k):v for k,v in self.gui.parameter_widgets.items()},
                "uart1":self.gui.uart1_business_check,"notebook":self.gui.notebook,
                **{"button:"+k:self.gui.buttons[k] for k in ("check","save","reset","export","device_details")}}

    def color(self,widget):
        # Resolve the options actually consumed by this live Tk widget/theme.
        explicit=widget.cget("foreground") if "foreground" in widget.keys() else ""
        value=explicit or app.ttk.Style(self.root).lookup(
            widget.cget("style") or widget.winfo_class(),"foreground",widget.state())
        self.assertTrue(value,f"No effective foreground for {widget}")
        return self.root.winfo_rgb(str(value))

    def assert_red(self,widget):
        self.assertEqual(self.color(widget),self.root.winfo_rgb("#b42318"))

    def test_gpio_both_parties_restore_independently_and_unrelated_names_do_not_change(self):
        features={k:self.gui.device_name_labels[k] for k in ("uart","dap","can","wifi","udp")}
        normal={k:self.color(v) for k,v in features.items()}
        self.pin("uart.tx",25)
        for key in ("uart","dap"):self.assert_red(features[key])
        for key in ("can","wifi","udp"):self.assertEqual(self.color(features[key]),normal[key])
        self.pin("can.cs",26)
        for key in ("uart","dap","can"):self.assert_red(features[key])
        self.gui.notebook.select(1);self.pump()
        for signal in ("uart.tx","dap.swclk","can.cs","dap.swdio"):
            label=self.gui.signal_rows[signal][0]
            self.assertTrue(label.winfo_ismapped())
            self.assert_red(label)
        unaffected=self.color(self.gui.signal_rows["uart.rx"][0])
        self.pin("uart.tx",32)
        self.gui.notebook.select(0);self.pump()
        self.assertEqual(self.color(features["uart"]),normal["uart"])
        for key in ("dap","can"):self.assert_red(features[key])
        self.pin("can.cs",15)
        for key in features:self.assertEqual(self.color(features[key]),normal[key])
        self.gui.notebook.select(1);self.pump()
        for signal in ("uart.tx","dap.swclk","can.cs","dap.swdio"):
            self.assertNotEqual(self.color(self.gui.signal_rows[signal][0]),self.root.winfo_rgb("#b42318"))
        self.assertEqual(self.color(self.gui.signal_rows["uart.rx"][0]),unaffected)
        self.assertFalse(self.board.calls)

    def test_gpio_edit_and_warning_do_not_move_mapped_rows_or_action_buttons(self):
        self.gui.notebook.select(1);self.pump()
        widgets={"signal:"+s:self.gui.pin_boxes[s] for s in self.gui.visible_signals}
        widgets.update({"button:"+k:self.gui.buttons[k] for k in ("check","save","export","reset")})
        initial=self.geometry(widgets)
        self.pin("uart.tx",25)
        self.assertEqual(self.geometry(widgets),initial)
        self.pin("can.cs",26)
        self.assertEqual(self.geometry(widgets),initial)
        self.pin("uart.tx",32);self.pin("can.cs",15)
        self.assertEqual(self.geometry(widgets),initial)
        self.assertFalse(self.board.calls)

    def test_uart1_roles_and_saved_candidate_keep_control_and_button_positions(self):
        widgets=self.controls()
        initial=self.geometry(widgets)
        independent=copy.deepcopy(self.service.draft["features"])
        self.feature("serial")
        self.assertEqual(self.geometry(widgets),initial)
        self.business()
        self.assertEqual(self.geometry(widgets),initial)
        self.assertTrue(self.service.draft["uart1_business"])
        self.assertEqual(self.service.draft["features"]["uart"],independent["uart"])
        self.click("save")
        self.assertEqual(self.geometry(widgets),initial)
        conditional={k:self.gui.buttons[k] for k in ("apply","cancel","load_candidate")}
        staged=self.geometry(conditional)
        self.feature("serial")
        self.assertEqual(self.geometry(widgets),initial)
        self.assertEqual(self.geometry(conditional),staged)
        self.click("cancel")
        self.assertEqual(self.geometry(widgets),initial)
        self.assertFalse(self.showerror.called)

    def test_no_cs_conflict_changes_only_participating_device_colors_and_not_positions(self):
        self.feature("dap")
        self.parameter("external2","enabled",True)
        self.parameter("external2","use_cs",True)
        self.pin("external2.cs",25)
        self.gui.notebook.select(0);self.pump()
        devices={k:self.gui.device_name_labels[k] for k in ("external","external2","mcp2518fd")}
        normal={k:self.color(v) for k,v in devices.items()}
        wifi=self.color(self.gui.feature_widgets["wifi"])
        controls=self.controls();initial=self.geometry(controls)
        independent={key:copy.deepcopy(self.service.draft[key]) for key in ("spi","features","uart1_business")}
        self.parameter("external","use_cs",False)
        self.assert_red(devices["external"]);self.assert_red(devices["external2"])
        self.assertEqual(self.color(devices["mcp2518fd"]),normal["mcp2518fd"])
        self.assertEqual(self.geometry(controls),initial)
        self.parameter("external2","host",3)
        for key in devices:self.assertEqual(self.color(devices[key]),normal[key])
        self.assertEqual(self.geometry(controls),initial)
        self.parameter("external","host",3)
        for key in devices:self.assert_red(devices[key])
        self.assertEqual(self.geometry(controls),initial)
        self.parameter("external","use_cs",True)
        for key in devices:self.assertEqual(self.color(devices[key]),normal[key])
        self.assertEqual(self.color(self.gui.feature_widgets["wifi"]),wifi)
        self.assertEqual(self.geometry(controls),initial)
        for key,value in independent.items():self.assertEqual(self.service.draft[key],value)
        self.assertFalse(self.board.calls)


class LifecycleTkTests(unittest.TestCase):
    """Closing and recovering from worker failures must leave Tk responsive."""
    setUp = TkTests.setUp
    pump = TkTests.pump
    click = TkTests.click

    def destroy_window(self):
        try:
            TkTests.destroy_window(self)
        except tk.TclError:
            # The lifecycle tests intentionally destroy the Tcl application.
            pass

    def assert_close_during_operation(self, error=None):
        entered, release, finished = (threading.Event() for _ in range(3))
        before = copy.deepcopy(self.gui.view)

        def blocked_read(*args, **kwargs):
            entered.set()
            try:
                if not release.wait(5):
                    raise TimeoutError("test did not release the blocked read")
                if error is not None:
                    raise error
                return before
            finally:
                finished.set()

        self.addCleanup(release.set)
        with patch.object(self.service, "read", side_effect=blocked_read), \
                patch.object(app.messagebox, "showinfo") as showinfo:
            self.gui.buttons["read"].invoke()
            self.assertTrue(entered.wait(2), "read worker did not start")
            worker = next(thread for thread in threading.enumerate() if thread.name == "profile-io")
            self.assertTrue(self.gui.busy)
            close_command = self.root.protocol("WM_DELETE_WINDOW")
            self.dialog.reset_mock()
            self.root.tk.call(close_command)
            self.dialog.assert_not_called()
            self.assertTrue(self.gui._closed)
            self.assertFalse(finished.is_set(), "close must not wait for the operation")
            with self.assertRaises(tk.TclError):
                self.root.winfo_exists()
            showinfo.assert_not_called()

            # A completion arriving after destruction must never render or open
            # a dialog against the dead Tk interpreter.
            release.set()
            self.assertTrue(finished.wait(2))
            worker.join(2)
            self.assertFalse(worker.is_alive())
            with patch.object(self.gui, "_render") as render, \
                    patch.object(self.gui, "_update_controls") as controls:
                self.gui._poll_queue()
            render.assert_not_called()
            controls.assert_not_called()
            self.showerror.assert_not_called()
            self.assertFalse(self.errors)

    def test_close_immediately_destroys_window_during_read(self):
        self.assert_close_during_operation()

    def test_late_failed_read_is_harmless_after_close(self):
        self.assert_close_during_operation(OSError("serial connection lost"))

    def test_failed_read_restores_serial_controls_and_allows_new_connection(self):
        draft = copy.deepcopy(self.gui.view["draft"])
        with patch.object(self.service, "read", side_effect=OSError("serial read failed")):
            self.click("read")
        self.assertTrue(self.showerror.called)
        self.assertFalse(self.gui.busy)
        self.assertFalse(self.gui.port_box.instate(["disabled"]))
        self.assertFalse(self.gui.baud_box.instate(["disabled"]))
        self.assertFalse(self.gui.buttons["read"].instate(["disabled"]))
        self.assertEqual(self.gui.view["draft"], draft)

        self.showerror.reset_mock()
        self.gui.port_var.set("mock:B")
        self.gui.baud_var.set("230400")
        self.click("read")
        self.assertEqual(self.gui.view["connection"]["port"], "mock:B")
        self.assertEqual(self.gui.view["connection"]["baud"], 230400)
        self.assertFalse(self.showerror.called)


class EntryPointTests(unittest.TestCase):
    def test_entrypoint_from_unrelated_working_directory(self):
        # Match Python's direct-script search path, then run the actual main entry
        # point with an injected in-memory service and a real button invocation.
        code = """
import runpy, sys, time, tkinter as tk
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
import backend
from test_app import MemoryBoard, ASSIGNABLE_GPIO
board = MemoryBoard()
service = backend.ProfileService(transport_factory=lambda port, baud: board,
                                device_factory=lambda transport: transport,
                                identity_reader=lambda device: device.identity)
original = tk.Tk.mainloop
def close_idle_window(root, *args):
    version = (Path(sys.argv[1]).resolve().parents[1] / 'version.txt').read_text().strip()
    assert root.title().startswith(f'HEX-Bridge {version} ·')
    gui = next(iter(root.children.values()))
    assert len(gui.notebook.tabs()) == 3
    assert str(gui.overview) not in gui.notebook.tabs(), 'pin bar must be outside tabs'
    assert gui.overview.mode_var.get() == 'current'
    assert not gui.overview.show_all_var.get()
    assert not gui.overview.cards, 'unread device must have no invented pin data'
    assert gui.overview.mode_buttons['candidate'].instate(['disabled'])
    assert '读取' in gui.overview.summary_var.get() + gui.overview.detail_var.get()
    gui.port_var.set('mock:A')
    gui.buttons['read'].invoke()
    deadline = time.monotonic() + 5
    previous = None
    stable = 0
    def check_loaded():
        nonlocal previous, stable
        geometry = (gui.overview.winfo_width(), gui.overview.winfo_height(),
                    tuple(sorted(gui.overview.card_bounds.items())))
        stable = stable + 1 if geometry == previous else 0
        previous = geometry
        ready = (not gui.busy and gui.overview.winfo_viewable()
                 and gui.overview.canvas.winfo_height() == gui.overview.card_height
                 and set(gui.overview.card_bounds) == set(ASSIGNABLE_GPIO)
                 and geometry[0] > 1 and stable >= 2)
        if not ready and time.monotonic() < deadline:
            root.after(20, check_loaded)
            return
        try:
            assert ready, 'real entrypoint window must finish mapping and layout'
            assert list(gui.overview.cards) == ASSIGNABLE_GPIO
            assert gui.overview.counts == {'free': 0, 'occupied': 9, 'fixed': 0,
                                          'unavailable': 0, 'conflict': 0}
            assert gui.overview.cards[14]['state'] == 'occupied'
            assert gui.overview.winfo_ismapped()
            assert gui.overview.winfo_height() <= 80
            assert len({round(b[1], 1) for b in gui.overview.card_bounds.values()}) == 1
            gui.overview.show_all_button.invoke()
            assert list(gui.overview.cards) == list(range(40))
            assert sum(gui.overview.counts.values()) == 40
            assert not board.calls, 'initial read must not send mutations'
            print('ENTRY_OVERVIEW_OK')
        finally:
            gui._closed = True
            root.destroy()
    root.after(20, check_loaded)
    return original(root, *args)
with patch.object(tk.Tk, 'mainloop', close_idle_window), patch('app.ProfileService', return_value=service):
    runpy.run_path(sys.argv[2], run_name='__main__')
"""
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run([sys.executable, "-c", code, str(HERE), str(HERE / "app.pyw")],
                                    cwd=cwd, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("ENTRY_OVERVIEW_OK", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
