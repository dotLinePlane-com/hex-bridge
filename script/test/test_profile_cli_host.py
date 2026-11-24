"""Exercise the actual profile CLI entry point against compiled device_profile.c.

No board, serial port, network, or credentials are accessed. Only ESP platform
services (NVS, clock, tasks, transport) are replaced. GPIO validation and profile
transactions are always executed by the current firmware source.
Run from a VS developer prompt: python script/test/test_profile_cli_host.py
"""
import argparse
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from test_profile_host import HARNESS_PREFIX, MAIN, compiled_harness
from ubcp_client import UBCPParser, Frame, FLAG_DIR

CLI = MAIN.parent / "script/cli/hex-bridge-profile.py"
# Share the real firmware include/platform callbacks with the protocol regression.
SERVER = HARNESS_PREFIX + r'''
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    char line[512];
    credentials=true;
    profile_init();
    while(fgets(line,sizeof(line),stdin)) {
        if(line[0]=='B') { profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK"); }
        else if(line[0]=='T') {
            unsigned before=restarts;
            clock_us=deadline; trial_timeout(NULL);
            assert(restarts==before+1); profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='D') {
            unsigned before=restarts;
            profile_driver_failed(); assert(restarts==before+1);
            profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='C') {
            record_t *saved=(record_t*)disk;
            saved->confirmed.legacy.pin[SIG_UART_TX]=4;
            profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='I') {
            record_t *saved=(record_t*)disk;
            saved->candidate.legacy.pin[SIG_UART_TX]=4; saved->candidate_checksum=mapping_checksum(&saved->candidate); saved->checksum=checksum(saved);
            profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='L') {
            assert(disk_len); --disk_len; profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='N') {
            tcp=true;profile_network_ready();puts("OK");
        } else if(line[0]=='S') {
            tcp=false;puts("OK");
        } else if(line[0]=='F') {
            disk_len=0; clock_us=0; tcp=false; session_current=true; credentials=true; profile_init(); profile_boot_ready(); profile_network_ready(); puts("OK");
        } else if(line[0]=='Q') {
            printf("%u\n",restarts);
        } else {
            uint8_t p[128]; unsigned n=0, value;
            for(char *s=line; s[0] && s[1] && s[0]!='\n';s+=2) {
                assert(n<sizeof(p)); assert(sscanf(s,"%2x",&value)==1);p[n++]=value;
            }
            ubcp_frame_t req={.payload=p,.payload_len=(uint16_t)n};
            profile_command(&req);
            for(size_t i=0;i<length;i++)printf("%02x",reply[i]);puts("");
        }
        fflush(stdout);
    }
    return 0;
}
'''


@contextlib.contextmanager
def firmware(compiler):
    with compiled_harness(compiler, SERVER) as binary:
        with subprocess.Popen([str(binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, bufsize=1) as process:
            try:
                yield process
            finally:
                process.stdin.close()
                process.wait(timeout=5)


class ProfileCLI(unittest.TestCase):
    process = None

    def line(self, data):
        self.process.stdin.write(data + "\n")
        self.process.stdin.flush()
        response = self.process.stdout.readline().strip()
        self.assertTrue(response, "compiled firmware process exited unexpectedly")
        return response

    def wire(self, op, data=b""):
        return bytes.fromhex(self.line((bytes([1, op]) + data).hex()))

    def setUp(self):
        self.line("F")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profile.json"
        outer = self

        class Transport:
            def __init__(self, *args): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def send(self, packet):
                parser = UBCPParser()
                frames = [frame for byte in packet if (frame := parser.feed(byte))]
                outer.assertEqual(len(frames), 1)
                req = frames[0]
                outer.assertEqual((req.cmd_code, req.channel_id), (8, 0))
                self.response = Frame()
                self.response.flags = FLAG_DIR
                self.response.seq_num = req.seq_num
                self.response.cmd_code = 8
                self.response.payload = bytes.fromhex(outer.line(req.payload.hex()))
            def recv_response(self, cmd, seq, timeout):
                outer.assertEqual((cmd, seq), (8, self.response.seq_num))
                return self.response

        module = types.ModuleType("mcp_transport")
        module.MCPTransport = Transport
        self.transport_factory = Transport
        self.patch = patch.dict(sys.modules, {"mcp_transport": module})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.cli("export", self.path)
        self.config = json.loads(self.path.read_text())

    def cli(self, *arguments, error=False):
        output = io.StringIO()
        with patch.object(sys, "argv", [str(CLI), "--version", getattr(self, "version", "1"), *map(str, arguments)]), contextlib.redirect_stdout(output):
            try:
                runpy.run_path(str(CLI), run_name="__main__")
            except SystemExit as exc:
                if not error:
                    raise AssertionError(f"CLI failed: {exc}") from exc
                return str(exc)
        self.assertFalse(error, "CLI unexpectedly accepted invalid input")
        return output.getvalue()

    def write(self, config=None):
        self.path.write_text(json.dumps(config or self.config), encoding="utf-8")

    def test_v6_auto_negotiation_two_i2c_and_gpio_transaction(self):
        self.version = 'auto'
        self.cli('export', self.path)
        self.config = json.loads(self.path.read_text())
        self.assertEqual(self.config['schema'], 6)
        self.assertEqual(self.config['capabilities'], 0x7ff)
        self.assertEqual(set(self.config['i2c']), {'0', '1'})
        self.assertEqual(set(self.config['gpio_lines']), set(map(str, range(14))))
        for feature in ('can', 'uart', 'dap'):
            self.config['features'][feature] = False
        for bus in self.config['spi'].values():
            bus['enabled'] = False
        for attachment in ('external', 'external2'):
            self.config[attachment]['enabled'] = False
        self.config['i2c']['0'].update(enabled=True, scl=18, sda=19)
        self.config['i2c']['1'].update(enabled=True, scl=21, sda=22, clock_hz=400000)
        self.config['gpio_lines']['0'].update(enabled=True, pin=25, mode='open_drain', initial_level=1)
        self.config['gpio_lines']['13'].update(enabled=True, pin=35, trigger='both', debounce_ms=10)
        self.write()
        self.assertIn('OK', self.cli('check', self.path))
        saved = self.cli('save', self.path)
        candidate = int(saved.split('=')[1])
        staged = self.pins()
        self.assertEqual(staged['active']['i2c']['0']['enabled'], False)
        self.assertEqual(staged['candidate']['gpio_lines']['0']['mode'], 'open_drain')
        self.cli('apply', candidate)
        self.line('B')
        trial = self.pins()
        self.assertEqual(trial['phase'], 'trial')
        self.assertEqual(trial['active']['i2c']['1']['clock_hz'], 400000)
        self.cli('confirm', candidate)
        self.assertEqual(self.pins()['phase'], 'confirmed')

    def test_v6_tk_edit_and_check_against_actual_profile_handler(self):
        import tkinter as tk
        import time
        gui_path = str(MAIN.parent / 'tool/funcitonPinMap')
        with patch.object(sys, 'path', [gui_path, *sys.path]):
            import backend
            import app
        service = backend.ProfileService(transport_factory=self.transport_factory,
                                         identity_reader=lambda device:'compiled-HXB1')
        root = tk.Tk()
        gui = app.ProfileApp(root, service)
        root.geometry('980x650')
        self.addCleanup(lambda: root.destroy() if root.winfo_exists() else None)
        def pump():
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                root.update()
                if not gui.busy:
                    return
                time.sleep(0.01)
            self.fail('Tk worker did not finish')
        gui.port_var.set('compiled')
        gui.buttons['read'].invoke()
        pump()
        self.assertEqual(gui.view['descriptor']['schema'],6)
        gui.notebook.select(gui.stage2.tab)
        gui.stage2.fields[('i2c1','timeout_ms')].set('750')
        gui.stage2.edit(('i2c1','timeout_ms'))
        pump()
        self.assertEqual(service.draft['i2c']['1']['timeout_ms'],750)
        self.assertEqual(service.snapshot['active']['i2c']['1']['timeout_ms'],1000)
        gui.buttons['check'].invoke()
        pump()
        self.assertIn('完成',gui.status_var.get())
        self.assertEqual(service.snapshot['active']['i2c']['1']['timeout_ms'],1000)

    def pins(self):
        return json.loads(self.cli("pins", "--json"))

    def assert_gpio(self, tables, pin, owners, state, table="occupancy"):
        row = next(r for r in tables[table] if r["gpio"] == pin)
        self.assertEqual(row["owners"], owners)
        self.assertEqual(row["state"], state)

    def assert_uart1_role(self,tables,role,table="occupancy"):
        for gpio,owner in ((4,"uart1.tx"),(34,"uart1.rx")):
            row=next(r for r in tables[table] if r["gpio"]==gpio)
            self.assertTrue(row["fixed"])
            self.assertEqual(row["owners"],[owner])
            self.assertEqual(row["uart1_role"],role)
            if table=="occupancy":
                fixed=next(r for r in tables["fixed"] if r["gpio"]==gpio)
                self.assertEqual(fixed["uart1_role"],role)

    def save(self):
        self.write()
        text = self.cli("save", self.path)
        return int(text.split("=")[-1].strip())

    def test_defaults_fields_and_roundtrip(self):
        self.assertEqual(set(self.config), {"schema", "board", "gpio_policy", "revision", "features", "pins"})
        self.assertEqual(self.config["board"], "HXB1")
        self.assertEqual(list(self.config["pins"].values()), [32, 35, 14, 13, 36, 15, 39, 25, 26])
        self.assertEqual(self.cli("check", self.path).strip(), "OK")
        self.assertEqual(self.wire(0)[6:17].hex(), "01ff20230e0d240f27191a")
        self.assertIn("UART", self.cli("pins").upper())
        shown = json.loads(self.cli("show"))
        tables = self.pins()["tables"]
        self.assertEqual(shown["tables"], tables)
        expected_fixed = {0: "strap", 1: "uart0.tx", 2: "strap", 3: "uart0.rx",
                          4: "uart1.tx", 5: "strap", **dict.fromkeys(range(6, 12), "flash"),
                          12: "eeprom", 16: "psram", 17: "psram", 18: "spi2",
                          19: "spi2", 21: "spi2", 22: "spi2", 23: "spi2", 27: "spi2",
                          33: "eeprom", 34: "uart1.rx"}
        self.assertEqual({row["gpio"]: row["owner"] for row in tables["fixed"]}, expected_fixed)
        self.assertTrue(all(row["read_only"] for row in tables["fixed"]))
        self.assertEqual([row["index"] for row in tables["editable"]], list(range(9)))
        for row in tables["editable"]:
            expected = {13, 14, 25, 26, 32}
            if row["index"] in (1, 4, 6):
                expected |= {35, 36, 39}
            if row["index"] == 5:
                expected.add(15)
            self.assertEqual({p["gpio"] for p in row["candidates"]}, expected)
            self.assertEqual(row["gpio"], self.config["pins"][row["signal"]])
        self.assertEqual([row["direction"] for row in tables["editable"]],
                         ["output", "input", "output", "output", "input", "output",
                          "input_interrupt", "output", "bidirectional"])
        occupancy = {r["gpio"]: r["owners"] for r in tables["occupancy"]}
        for pin, owner in expected_fixed.items():
            self.assertEqual(occupancy[pin], [owner])
            self.assert_gpio(tables, pin, [owner], "fixed")
        for signal, pin in self.config["pins"].items():
            self.assertEqual(occupancy[pin], [signal])
        self.assertEqual(tables["invalid_pins"], [])

    def test_preview_and_disabled_release_are_read_only(self):
        self.config["features"]["can"] = False
        self.write()
        before = self.wire(1)
        preview = json.loads(self.cli("pins", "--file", self.path, "--json"))
        self.assertEqual(self.wire(1), before)
        self.assertIsNone(preview["candidate"])
        self.assertEqual(preview["tables"]["occupancy"], self.pins()["tables"]["occupancy"])
        projected = {r["gpio"]: r for r in preview["tables"]["candidate_occupancy"]}
        for pin in (14, 13, 36, 15, 39):
            self.assertEqual(projected[pin]["owners"], [])
            self.assertEqual(projected[pin]["state"], "free")
        candidate = self.save()
        self.cli("apply", candidate)
        self.line("B")
        self.assertEqual(self.pins()["tables"]["occupancy"], preview["tables"]["candidate_occupancy"])
        # Disabled CAN retains editable mappings and GPIO15's CS-only policy.
        self.assertEqual(json.loads(self.cli("show"))["active"]["pins"], self.config["pins"])
        self.assertEqual([r["gpio"] for r in self.pins()["tables"]["editable"] if r["signal"] == "can.cs"], [15])

    def test_import_cannot_change_fixed_metadata(self):
        for mutate in (
            lambda c: c["gpio_policy"].__setitem__("4", "flexible"),
            lambda c: c["pins"].__setitem__("uart1.tx", 25),
            lambda c: c.__setitem__("fixed", []),
        ):
            bad = copy.deepcopy(self.config)
            mutate(bad)
            self.write(bad)
            for op in ("check", "save"):
                self.assertTrue(self.cli(op, self.path, error=True))
        self.assertEqual(json.loads(self.cli("show"))["revision"], 1)

    def test_invalid_preview_does_not_claim_fixed_or_unavailable_gpio(self):
        for pin in (4, 37, 35):
            self.config["pins"]["can.sck"] = pin
            self.write()
            before = self.wire(1)
            tables = json.loads(self.cli("pins", "--file", self.path, "--json"))["tables"]
            self.assertEqual(self.wire(1), before)
            self.assertTrue(any(r["signal"] == "can.sck" and r["gpio"] == pin
                                for r in tables["invalid_pins"]))
            for row in tables["candidate_occupancy"]:
                self.assertNotIn("can.sck", row["owners"])
            self.assert_gpio(tables, 4, ["uart1.tx"], "fixed", "candidate_occupancy")

    def test_firmware_fixed_direction_conflict_and_swap(self):
        # Bypass all CLI import protection: firmware must reject fixed GPIOs.
        original = self.wire(0)[6:17]
        for signal in range(9):
            for pin in (0, 1, 2, 3, 4, 5, 6, 11, 12, 16, 17, 18, 19, 21, 22, 23, 27, 33, 34, 37, 38):
                mapping = bytearray(original)
                mapping[2 + signal] = pin
                for op in (2, 3):
                    reply = self.wire(op, struct.pack(">I", 1) + mapping)
                    self.assertEqual(reply[0], 2)
                    self.assertIn(bytes([5, signal, pin, 255]), reply[2:])
        for signal in (0, 2, 3, 5, 7, 8):
            for pin in (35, 36, 39):
                mapping = bytearray(original)
                mapping[signal + 2] = pin
                self.assertEqual(self.wire(2, struct.pack(">I", 1) + mapping)[0], 2)
        self.config["pins"]["can.sck"] = 25
        self.write()
        self.assertIn("conflict", self.cli("check", self.path, error=True).lower())
        self.config["pins"]["dap.swclk"] = 14
        self.write()
        self.assertEqual(self.cli("check", self.path).strip(), "OK")

    def test_uart1_disabled_still_reserves_gpio4(self):
        self.config["features"]["serial"] = False
        for signal in ("can.sck", "uart.tx"):
            bad = copy.deepcopy(self.config)
            bad["pins"][signal] = 4
            self.write(bad)
            for op in ("check", "save"):
                message = self.cli(op, self.path, error=True).lower()
                self.assertIn("gpio4", message)
                self.assertIn("uart1", message)

    def test_each_can_signal_independently_moves(self):
        self.config["features"]["dap"] = False
        for signal in ("can.sck", "can.mosi", "can.miso", "can.cs", "can.int"):
            moved = copy.deepcopy(self.config)
            moved["pins"][signal] = 25
            self.write(moved)
            self.assertEqual(self.cli("check", self.path).strip(), "OK", signal)
            # The remaining four CAN signals are byte-for-byte unchanged.
            self.assertEqual(self.wire(1)[14:25], self.wire(0)[6:17])
            candidate = int(self.cli("save", self.path).split("=")[-1].strip())
            self.cli("apply", candidate)
            self.line("B")
            active = json.loads(self.cli("show"))["active"]
            self.assertEqual(active["pins"], moved["pins"])
            occupancy = {row["gpio"]: row["owners"] for row in self.pins()["tables"]["occupancy"]}
            self.assertEqual(occupancy[25], [signal])
            self.line("T")
            self.config["revision"] = json.loads(self.cli("show"))["revision"]

    def test_save_trial_timeout_and_confirmation(self):
        self.config["features"]["dap"] = False
        self.config["pins"]["can.sck"] = 25
        before = self.pins()
        self.assert_gpio(before["tables"], 14, ["can.sck"], "occupied")
        self.assert_gpio(before["tables"], 25, ["dap.swclk"], "occupied")
        candidate = self.save()
        staged = self.pins()
        self.assert_gpio(staged["tables"], 14, ["can.sck"], "occupied")
        self.assert_gpio(staged["tables"], 25, ["dap.swclk"], "occupied")
        self.assert_gpio(staged["tables"], 14, [], "free", "candidate_occupancy")
        self.assert_gpio(staged["tables"], 25, ["can.sck"], "occupied", "candidate_occupancy")
        self.assertEqual(before["tables"]["occupancy"], staged["tables"]["occupancy"])
        self.assertNotEqual(staged["tables"]["occupancy"], staged["tables"]["candidate_occupancy"])
        self.cli("apply", candidate)
        self.line("B")
        trial = self.pins()
        self.assert_gpio(trial["tables"], 14, [], "free")
        self.assert_gpio(trial["tables"], 25, ["can.sck"], "occupied")
        self.assertEqual(trial["tables"]["occupancy"], staged["tables"]["candidate_occupancy"])
        self.assertEqual(trial["phase"], "trial")
        self.line("T")
        reverted = self.pins()
        self.assert_gpio(reverted["tables"], 14, ["can.sck"], "occupied")
        self.assert_gpio(reverted["tables"], 25, ["dap.swclk"], "occupied")
        self.assertEqual(reverted["tables"]["occupancy"], before["tables"]["occupancy"])
        self.assertEqual(reverted["phase"], "confirmed")
        self.cli("export", self.path)
        self.config["revision"] = json.loads(self.path.read_text())["revision"]
        candidate = self.save()
        self.cli("apply", candidate)
        self.line("B")
        self.cli("confirm", candidate)
        self.cli("confirm", candidate)
        self.line("B")
        confirmed = self.pins()
        self.assertEqual(confirmed["tables"]["occupancy"], trial["tables"]["occupancy"])
        self.assertEqual(confirmed["phase"], "confirmed")

    def test_driver_failure_and_unconfirmed_reset_revert(self):
        for reset in ("D", "B"):
            self.line("F")
            self.cli("export", self.path)
            self.config = json.loads(self.path.read_text())
            self.config["features"]["dap"] = False
            self.config["pins"]["can.sck"] = 25
            candidate = self.save()
            self.cli("apply", candidate)
            self.line("B")
            self.assertEqual(json.loads(self.cli("show"))["phase"], "trial")
            self.line(reset)
            snapshot = json.loads(self.cli("show"))
            self.assertEqual(snapshot["phase"], "confirmed")
            self.assertEqual(snapshot["active"]["pins"]["can.sck"], 14)

    def test_corrupt_old_persisted_mapping_and_length(self):
        for corruption in ("I", "C", "L"):
            self.line("F")
            self.cli("export", self.path)
            self.config = json.loads(self.path.read_text())
            self.config["features"]["dap"] = False
            self.config["pins"]["can.sck"] = 25
            confirmed = self.save()
            self.cli("apply", confirmed)
            self.line("B")
            self.cli("confirm", confirmed)
            self.config["revision"] = json.loads(self.cli("show"))["revision"]
            self.config["pins"]["can.mosi"] = 14
            candidate = self.save()
            self.cli("apply", candidate)
            # Inject an old board-invalid GPIO4 route in either persisted map,
            # or an incompatible truncated record, before startup validation.
            self.line(corruption)
            snapshot = json.loads(self.cli("show"))
            self.assertEqual(snapshot["phase"], "confirmed")
            self.assertEqual(snapshot["active"]["pins"]["can.sck"], 25 if corruption == "I" else 14)
            self.assertEqual(snapshot["active"]["pins"]["uart.tx"], 32)
            self.assertEqual(snapshot["candidate_id"], 0)
            self.assert_gpio(snapshot["tables"], 4, ["uart1.tx"], "fixed")

    def test_frozen_examples_against_actual_firmware(self):
        examples=json.loads((CLI.parent.parent / "test/fixtures/profile/wire-examples.json").read_text())
        for version in ("1", "2"):
            self.line("F")
            for operation in ("describe", "read", "check", "save"):
                example=examples[version]
                self.assertEqual(self.line(example[operation+"_request"]),example[operation+"_response"],f"v{version} {operation}")

    def test_v2_cli_transactions_and_occupancy(self):
        self.version = "2"
        self.cli("export", self.path)
        self.config = json.loads(self.path.read_text())
        self.assertEqual(self.config["schema"], 2)
        self.assertEqual(self.config["capabilities"], 15)
        self.assertIn("SPI2.SCK", self.cli("pins", "--human").upper())
        self.assertEqual(self.cli("check", CLI.parent.parent / "test/fixtures/profile/v1-nondefault.json").strip(), "OK")
        tables = self.pins()["tables"]
        business = [r for r in tables["occupancy"] if r["state"] == "occupied"]
        self.assertEqual(len(business), 15)
        self.config["spi"]["2"]["width"] = 1
        self.write()
        self.assertEqual(self.cli("check",self.path).strip(),"OK")
        before = self.pins()["tables"]["occupancy"]
        candidate = self.save()
        staged = self.pins()
        self.assertEqual(staged["tables"]["occupancy"],before)
        for pin in (22,23): self.assert_gpio(staged["tables"],pin,[],"free","candidate_occupancy")
        self.cli("apply",candidate); self.line("B")
        self.assertEqual(self.pins()["tables"]["occupancy"],staged["tables"]["candidate_occupancy"])
        self.line("T")
        self.assertEqual(self.pins()["tables"]["occupancy"],before)
        self.cli("export",self.path); self.config=json.loads(self.path.read_text())
        self.config["spi"]["2"]["width"]=1
        candidate=self.save(); self.cli("apply",candidate); self.line("B"); self.cli("confirm",candidate)
        self.line("B"); self.assertEqual(self.pins()["phase"],"confirmed")
        self.cli("export",self.path); self.config=json.loads(self.path.read_text())
        candidate=self.save(); self.cli("cancel",candidate)
        self.assertIsNone(self.pins()["candidate"])

    def test_v3_two_devices_roundtrip_and_independent_occupancy(self):
        self.version="3"
        self.cli("export",self.path)
        self.config=json.loads(self.path.read_text())
        self.assertEqual(self.config["schema"],3)
        self.assertEqual(self.config["capabilities"],63)
        self.assertEqual(self.config["external2"],{"enabled":False,"host":2,"cs":255})
        self.config["features"]["dap"]=False
        self.config["external2"]={"enabled":True,"host":3,"cs":25}
        self.write()
        before=self.pins()["tables"]["occupancy"]
        self.assertEqual(self.cli("check",self.path).strip(),"OK")
        candidate=self.save()
        staged=self.pins()
        self.assertEqual(staged["tables"]["occupancy"],before)
        self.assert_gpio(staged["tables"],25,["external2.cs"],"occupied","candidate_occupancy")
        self.cli("apply",candidate);self.line("B");self.cli("confirm",candidate);self.line("B")
        snapshot=json.loads(self.cli("show"))
        self.assertEqual(snapshot["active"]["external"],self.config["external"])
        self.assertEqual(snapshot["active"]["external2"],self.config["external2"])
        self.assert_gpio(snapshot["tables"],25,["external2.cs"],"occupied")
        # A v2 write cannot silently disable an existing second device.
        import hexbridge_profile as profile
        payload=struct.pack(">I",snapshot["revision"])+profile.encode_mapping({k:v for k,v in self.config.items() if k!="external2"})
        response=bytes.fromhex(self.line((bytes([2,3])+payload).hex()))
        self.assertEqual(response[0],6)
        self.assertEqual(json.loads(self.cli("show"))["revision"],snapshot["revision"])

    def test_v3_no_cs_has_no_gpio_owner_and_rejects_shared_host(self):
        self.version="3";self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.config["external"]["cs"]=255;self.write()
        self.assertEqual(self.cli("check",self.path).strip(),"OK")
        preview=json.loads(self.cli("pins","--file",self.path,"--json"))["tables"]
        self.assert_gpio(preview,27,[],"free","candidate_occupancy")
        self.assertFalse(any(row["gpio"]==255 for row in preview["candidate_occupancy"]))
        candidate=self.save();self.cli("apply",candidate);self.line("B");self.cli("confirm",candidate)
        self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.assertEqual(self.config["external"]["cs"],255)
        self.config["features"]["dap"]=False
        self.config["external2"]={"enabled":True,"host":2,"cs":25};self.write()
        before=json.loads(self.cli("show"))["revision"]
        for operation in ("check","save"):
            self.assertTrue(self.cli(operation,self.path,error=True))
        self.assertEqual(json.loads(self.cli("show"))["revision"],before)
        # A no-CS device may use the other host after CAN is disabled.
        self.config["external2"]={"enabled":True,"host":3,"cs":255}
        self.config["features"]["can"]=False;self.write()
        self.assertEqual(self.cli("check",self.path).strip(),"OK")
        self.config["features"]["can"]=True;self.write()
        self.assertTrue(self.cli("check",self.path,error=True))

    def test_v4_uart1_business_mutual_exclusion_and_network_confirmation(self):
        self.version="4";self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.assertEqual(self.config["schema"],4)
        self.assertEqual(self.config["capabilities"],127)
        self.assertIs(self.config["uart1_business"],False)
        self.config["uart1_business"]=True;self.write()
        self.assertTrue(self.cli("check",self.path,error=True))
        self.config["features"]["serial"]=False;self.write()
        self.assertEqual(self.cli("check",self.path).strip(),"OK")
        before=self.pins()["tables"]["occupancy"]
        candidate=self.save()
        staged=json.loads(self.cli("show"))
        self.assertFalse(staged["active"]["uart1_business"])
        self.assertTrue(staged["candidate"]["uart1_business"])
        self.assertEqual(staged["tables"]["occupancy"],before)
        self.assert_uart1_role(staged["tables"],"control")
        self.assert_uart1_role(staged["tables"],"business","candidate_occupancy")
        # Old clients can inspect projections but cannot mutate a v4-only candidate.
        for version in (1,2,3):
            reply=bytes.fromhex(self.line((bytes([version,4])+struct.pack(">I",candidate)).hex()))
            self.assertEqual(reply[0],6)
        self.cli("apply",candidate);self.line("B")
        self.assertTrue(self.cli("confirm",candidate,error=True))
        self.line("N");self.cli("confirm",candidate);self.line("B")
        shown=json.loads(self.cli("show"))
        self.assertTrue(shown["active"]["uart1_business"])
        self.assertFalse(shown["active"]["features"]["serial"])
        self.assertTrue(shown["active"]["features"]["uart"])
        self.assert_uart1_role(shown["tables"],"business")
        # The management connector remains a fixed reservation in the pin allocator.
        for gpio in (4,34):
            row=next(r for r in shown["tables"]["occupancy"] if r["gpio"]==gpio)
            self.assertTrue(row["fixed"])
        self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.config["uart1_business"]=False;self.config["features"]["serial"]=True
        candidate=self.save();self.cli("apply",candidate);self.line("B")
        self.assertTrue(self.cli("confirm",candidate,error=True))
        self.line("S");self.cli("confirm",candidate)
        restored=json.loads(self.cli("show"))
        self.assertFalse(restored["active"]["uart1_business"])
        self.assert_uart1_role(restored["tables"],"control")
        # Turning off both UART1 roles leaves fixed wiring reserved and undispatchable.
        self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.config["features"]["serial"]=False
        candidate=self.save();self.cli("apply",candidate);self.line("B");self.line("N")
        self.cli("confirm",candidate)
        self.assert_uart1_role(json.loads(self.cli("show"))["tables"],"reserved")

    def test_v4_network_requirements_and_legacy_file_migration(self):
        self.version="4";self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        for key in ("wifi","control_tcp"):
            bad=copy.deepcopy(self.config)
            bad["uart1_business"]=True;bad["features"]["serial"]=False;bad["features"][key]=False
            self.write(bad)
            self.assertTrue(self.cli("save",self.path,error=True))
        bad=copy.deepcopy(self.config);bad["uart1_business"]=1;self.write(bad)
        self.assertTrue(self.cli("save",self.path,error=True))
        legacy=CLI.parent.parent/"test/fixtures/profile/v2-default.json"
        self.assertEqual(self.cli("check",legacy).strip(),"OK")
        candidate=int(self.cli("save",legacy).split("=")[-1].strip())
        shown=json.loads(self.cli("show"))
        self.assertFalse(shown["candidate"]["uart1_business"])
        self.assertEqual(shown["candidate"]["external2"],{"enabled":False,"host":2,"cs":255})
        self.cli("cancel",candidate)

    def test_v4_uart1_unconfirmed_and_driver_failure_restore_management(self):
        self.version="4"
        for recovery in ("B","D","T"):
            self.line("F");self.cli("export",self.path);self.config=json.loads(self.path.read_text())
            self.config["uart1_business"]=True;self.config["features"]["serial"]=False
            candidate=self.save();self.cli("apply",candidate);self.line("B")
            self.assertTrue(json.loads(self.cli("show"))["active"]["uart1_business"])
            self.line(recovery)
            shown=json.loads(self.cli("show"))
            self.assertEqual(shown["phase"],"confirmed")
            self.assertFalse(shown["active"]["uart1_business"])
            self.assertTrue(shown["active"]["features"]["serial"])
            self.assertEqual(shown["candidate_id"],0)

    def test_v5_spi2_slave_check_stage_trial_and_confirm(self):
        self.version = "5"
        self.cli("export", self.path)
        self.config = json.loads(self.path.read_text())
        self.assertEqual(self.config["capabilities"], 0x1ff)
        self.config["spi"]["2"].update(role="slave", width=1, slave_cs=27)
        self.write()
        self.assertIn("requires a master controller", self.cli("check", self.path, error=True))
        self.config["external"]["enabled"] = False
        self.write()
        candidate = self.save()
        self.assertEqual(json.loads(self.cli("show"))["candidate"]["spi"]["2"]["role"], "slave")
        self.cli("apply", candidate)
        self.line("B")
        self.cli("confirm", candidate)
        self.line("B")
        shown = json.loads(self.cli("show"))
        self.assertEqual(shown["active"]["spi"]["2"]["role"], "slave")
        self.assertEqual(shown["active"]["spi"]["3"]["role"], "master")
        self.assertEqual(shown["tables"]["spi_roles"]["2"]["current"], "slave")

    def test_v2_invalid_bus_and_read_only_metadata(self):
        self.version="2";self.cli("export",self.path);self.config=json.loads(self.path.read_text())
        self.config["spi"]["3"]["enabled"]=False;self.write()
        self.assertIn("enabled SPI host",self.cli("check",self.path,error=True))
        self.config["capabilities"]=0;self.write()
        self.assertIn("read-only",self.cli("save",self.path,error=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", nargs="?", default="cl" if os.name == "nt" else "cc")
    args = parser.parse_args()
    with firmware(args.compiler) as process:
        ProfileCLI.process = process
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProfileCLI))
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
