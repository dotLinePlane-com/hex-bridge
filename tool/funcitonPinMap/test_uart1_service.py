"""Hardware-free UART1 role service regressions, independent of the Tk suite.

Only MemoryBoard transports are opened. Firmware-side validation, persistence
and network confirmation are covered by script/test/test_profile_v4_host.py.
Run: python tool/funcitonPinMap/test_uart1_service.py
"""

from copy import deepcopy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from test_app import MemoryBoard, HERE
import backend


class UART1ServiceTests(unittest.TestCase):
    def setUp(self):
        self.board = MemoryBoard()
        document = json.loads(
            (
                HERE.parents[1] / "script/test/fixtures/profile/v2-default.json"
            ).read_text()
        )
        self.board.desc = {
            k: document[k] for k in ("schema", "board", "capabilities", "gpio_policy")
        }
        self.board.desc.update(schema=4, capabilities=127)
        mapping = {
            k: document[k] for k in ("features", "pins", "spi", "external", "mcp2518fd")
        }
        mapping.update(
            external2={"enabled": False, "host": 2, "cs": 255}, uart1_business=False
        )
        self.board.state.update(active=deepcopy(mapping), candidate=None)
        self.board.confirmed = deepcopy(mapping)
        self.service = backend.ProfileService(
            transport_factory=lambda port, baud: self.board,
            device_factory=lambda transport: transport,
            identity_reader=lambda device: device.identity,
        )
        self.service.read("mock:uart1", 115200)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "profile.json"

    def business(self):
        self.service.set_feature("serial", False)
        return self.service.set_parameter("uart1", "enabled", True)

    def write(self, document):
        self.path.write_text(json.dumps(document), encoding="utf8")

    def assert_role(self, view, role, preview=False):
        tables = view["preview_tables"] if preview else view["tables"]
        table = "candidate_occupancy" if preview else "occupancy"
        for gpio, owner in ((4, "uart1.tx"), (34, "uart1.rx")):
            row = next(r for r in tables[table] if r["gpio"] == gpio)
            self.assertTrue(row["fixed"])
            self.assertEqual(row["owners"], [owner])
            self.assertEqual(row["uart1_role"], role)

    def test_mutual_exclusion_and_strict_values_leave_rejected_draft_untouched(self):
        before = self.service.view()
        for field, value in (
            ("enabled", True),
            ("enabled", 1),
            ("enabled", "true"),
            ("host", False),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.service.set_parameter("uart1", field, value)
            self.assertEqual(self.service.view(), before)
        view = self.business()
        self.assertTrue(view["draft"]["uart1_business"])
        self.assertFalse(view["draft"]["features"]["serial"])
        view = self.service.set_feature("serial", True)
        self.assertTrue(view["draft"]["features"]["serial"])
        self.assertFalse(view["draft"]["uart1_business"])
        self.assertFalse(view["dirty"])
        self.assertFalse(self.board.calls)

    def test_legacy_versions_and_missing_capability_reject_role_without_mutation(self):
        for schema, caps in ((1, 0), (2, 15), (3, 63), (4, 63)):
            self.service.descriptor.update(schema=schema, capabilities=caps)
            draft = deepcopy(self.service.draft)
            for enabled in (False, True):
                with self.assertRaises(ValueError):
                    self.service.set_parameter("uart1", "enabled", enabled)
                self.assertEqual(self.service.draft, draft)
        self.assertFalse(self.board.calls)

    def test_control_reserved_and_business_preview_keep_both_pins_fixed(self):
        before = self.service.view()
        self.assert_role(before, "control")
        reserved = self.service.set_feature("serial", False)
        self.assert_role(reserved, "reserved", preview=True)
        self.assert_role(reserved, "control")
        business = self.service.set_parameter("uart1", "enabled", True)
        self.assert_role(business, "business", preview=True)
        self.assert_role(business, "control")
        self.assertEqual(business["tables"], before["tables"])
        self.assertEqual(
            business["descriptor"]["gpio_policy"], before["descriptor"]["gpio_policy"]
        )
        self.service.set_parameter("uart1", "enabled", False)
        self.assert_role(self.service.view(), "reserved", preview=True)
        self.assertFalse(self.board.calls)

    def test_candidate_trial_confirmation_and_restoration_roundtrip(self):
        original = deepcopy(self.board.state["active"])
        self.business()
        self.service.check()
        staged = self.service.save()
        op, data, _ = self.board.calls[-1]
        self.assertEqual(op, "save")
        self.assertEqual(len(data), 34)
        self.assertEqual(data[-1], 1)
        self.assertEqual(struct.unpack_from(">I", data)[0], 1)
        self.assertEqual(self.board.state["active"], original)
        self.assert_role(staged, "control")
        self.service.apply()
        for operation in (
            self.service.check,
            self.service.save,
            self.service.apply,
            self.service.cancel,
            self.service.confirm,
        ):
            with self.assertRaises(ValueError):
                operation()
        self.board.reboot()
        trial = self.service.read("mock:uart1", 115200)
        self.assertEqual(trial["snapshot"]["phase"], "trial")
        self.assert_role(trial, "business")
        confirmed = self.service.confirm()
        self.assertTrue(confirmed["snapshot"]["active"]["uart1_business"])
        self.service.set_feature("serial", True)
        self.assertFalse(self.service.draft["uart1_business"])
        self.service.save()
        self.service.apply()
        self.board.reboot()
        self.service.read("mock:uart1", 115200)
        restored = self.service.confirm()
        self.assertEqual(restored["snapshot"]["active"], original)
        self.assert_role(restored, "control")

    def test_failed_import_preserves_dirty_draft_fixed_tables_and_cs_memory(self):
        self.business()
        self.service.set_feature("dap", False)
        self.service.set_pin("external.cs", 25)
        self.service.set_parameter("external", "use_cs", False)
        before = self.service.view()
        good = deepcopy(before["draft"])
        cases = []
        conflict = deepcopy(good)
        conflict["features"]["serial"] = True
        cases.append(conflict)
        malformed = deepcopy(good)
        malformed["uart1_business"] = 1
        cases.append(malformed)
        fixed = deepcopy(good)
        fixed["gpio_policy"]["4"] = "flexible"
        cases.append(fixed)
        extra = deepcopy(good)
        extra["pins"]["uart1.tx"] = 25
        cases.append(extra)
        for document in cases:
            self.write(document)
            with self.assertRaises(ValueError):
                self.service.import_config(self.path)
            self.assertEqual(self.service.view(), before)
        self.service.set_parameter("external", "use_cs", True)
        self.assertEqual(self.service.draft["external"]["cs"], 25)
        self.assertFalse(self.board.calls)

    def test_imported_gpio_conflict_stays_correctable_and_cannot_claim_fixed_uart1(
        self,
    ):
        self.business()
        document = deepcopy(self.service.draft)
        document["pins"]["uart.tx"] = 4
        self.write(document)
        loaded = self.service.import_config(self.path)
        self.assertTrue(loaded["dirty"])
        self.assertTrue(loaded["preview_tables"]["invalid_pins"])
        self.assert_role(loaded, "business", preview=True)
        before = self.service.view()
        with self.assertRaises(ValueError):
            self.service.check()
        self.assertEqual(self.service.view(), before)
        self.service.set_pin("uart.tx", 32)
        self.service.check()
        self.assert_role(self.service.view(), "business", preview=True)

    def test_legacy_import_defaults_role_off_and_is_only_a_draft_change(self):
        self.business()
        fixture = HERE.parents[1] / "script/test/fixtures/profile/v2-default.json"
        imported = self.service.import_config(fixture)
        self.assertEqual(imported["draft"]["schema"], 4)
        self.assertIs(imported["draft"]["uart1_business"], False)
        self.assertTrue(imported["draft"]["features"]["serial"])
        self.assert_role(imported, "control", preview=True)
        self.assertFalse(self.board.calls)
        self.business()
        self.service.export_config(self.path)
        document = json.loads(self.path.read_text(encoding="utf8"))
        self.assertIs(document["uart1_business"], True)
        self.assertEqual(len(backend.cli.encode_mapping(document)), 30)
        self.service.reset_draft()
        self.service.import_config(self.path)
        self.assertTrue(self.service.draft["uart1_business"])
        self.assertFalse(self.board.state["active"]["uart1_business"])

    def test_failed_read_and_changed_capabilities_preserve_draft_and_prevent_write(
        self,
    ):
        self.business()
        before = self.service.view()
        describe = self.board.descriptor

        def offline():
            raise OSError("simulated disconnect")

        self.board.descriptor = offline
        with self.assertRaises(OSError):
            self.service.read("mock:uart1", 115200, discard_draft=True)
        self.assertEqual(self.service.view(), before)
        self.board.descriptor = describe
        self.board.desc["capabilities"] = 63
        with self.assertRaises(ValueError):
            self.service.save()
        self.assertEqual(self.service.view(), before)
        self.assertFalse(self.board.calls)

    def test_unknown_apply_preserves_later_draft_and_requires_identity_safe_reconnect(
        self,
    ):
        self.business()
        self.service.save()
        self.service.set_parameter("uart1", "enabled", False)
        draft = deepcopy(self.service.draft)
        original = self.board.request

        def lost_ack(op, data=b""):
            result = original(op, data)
            if op == "apply":
                raise backend.ApplyOutcomeUnknown("lost acknowledgement")
            return result

        self.board.request = lost_ack
        with self.assertRaises(backend.ApplyOutcomeUnknown):
            self.service.apply()
        self.assertTrue(self.service.requires_reconnect)
        with self.assertRaises(ValueError):
            self.service.apply()
        self.board.reboot()
        self.board.identity = "replacement"
        with self.assertRaises(ValueError):
            self.service.read("mock:uart1", 115200)
        self.assertEqual(self.service.draft, draft)
        self.board.identity = "board-A"
        view = self.service.read("mock:uart1", 115200)
        self.assertFalse(view["requires_reconnect"])
        self.assertEqual(view["draft"], draft)
        self.assert_role(view, "business")
        self.assert_role(view, "reserved", preview=True)
        self.assertEqual(sum(op == "apply" for op, *_ in self.board.calls), 1)

    def test_device_busy_error_keeps_correctable_trial_draft_and_current_tables(self):
        self.business()
        self.service.save()
        self.service.apply()
        self.board.reboot()
        self.service.read("mock:uart1", 115200)
        self.service.set_feature("serial", True)
        before = self.service.view()
        self.board.fail_next = "transaction busy"
        with self.assertRaisesRegex(ValueError, "busy"):
            self.service.save()
        self.assertEqual(self.service.view(), before)
        self.assert_role(before, "business")
        self.assert_role(before, "control", preview=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
