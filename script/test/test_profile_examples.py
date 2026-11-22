"""Executable frozen v1/v2 examples and host negotiation checks; no hardware I/O."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hexbridge_profile as profile

FIXTURES=Path(__file__).with_name('fixtures')/'profile'

class Examples(unittest.TestCase):
    def v4_config(self):
        old = json.loads((FIXTURES / "v2-default.json").read_text())
        desc = {key: old[key] for key in ("schema", "board", "capabilities", "gpio_policy")}
        desc.update(schema=4, capabilities=127)
        return desc, profile.load_config(FIXTURES / "v2-default.json", desc)

    def load_json(self, config, desc):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "profile.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            return profile.load_config(path, desc)

    def test_frozen_wire_formats(self):
        examples=json.loads((FIXTURES/'wire-examples.json').read_text())
        for version in (1,2):
            e=examples[str(version)]
            self.assertEqual(bytes.fromhex(e['describe_request']),bytes([version,0]))
            raw=bytes.fromhex(e['read_response'])[14:]
            self.assertEqual(len(raw),11 if version==1 else 26)
            self.assertEqual(profile.encode_mapping(profile.decode_mapping(raw)),raw)
            self.assertEqual(len(bytes.fromhex(e['check_request'])),17 if version==1 else 32)
            self.assertEqual(bytes.fromhex(e['save_request'])[:2],bytes([version,3]))
            self.assertEqual(bytes.fromhex(e['save_response']),b'\0'+struct.pack('>I',2))

    def test_nondefault_v1_occupancy_and_migration(self):
        config=json.loads((FIXTURES/'v1-nondefault.json').read_text())
        desc={k:config[k] for k in ('schema','board','gpio_policy')}
        loaded=profile.load_config(FIXTURES/'v1-nondefault.json',desc)
        self.assertEqual(profile.encode_mapping(loaded).hex(),'00ff191a0e0d240f27191a')
        rows=profile.occupancy(desc,loaded)
        self.assertEqual(sum(r['state']=='occupied' for r in rows),7)
        self.assertEqual(next(r['owners'] for r in rows if r['gpio']==25),['uart.tx'])
        self.assertEqual(next(r['owners'] for r in rows if r['gpio']==32),[])
        target=json.loads((FIXTURES/'v2-default.json').read_text())
        desc2={k:target[k] for k in ('schema','board','capabilities','gpio_policy')}
        migrated=profile.load_config(FIXTURES/'v1-nondefault.json',desc2)
        self.assertEqual(migrated['pins']['uart.tx'],25)
        self.assertEqual(migrated['spi']['2']['width'],4)
        self.assertFalse(migrated['features']['dap'])

    def test_invalid_wire_fields_are_rejected_before_boolean_conversion(self):
        wire=json.loads((FIXTURES/'wire-examples.json').read_text())
        raw=bytes.fromhex(wire['2']['read_response'])[14:]
        for offset,value in ((0,128),(6,2),(7,2),(20,2),(21,4),(23,0)):
            malformed=bytearray(raw);malformed[offset]=value
            with self.assertRaises(ValueError):profile.decode_mapping(malformed)
        with self.assertRaises(ValueError):profile.decode_mapping(bytes.fromhex('ffff20230e0d240f27191a'))

    def test_snapshot_rejects_inconsistent_phase_and_candidate(self):
        examples=json.loads((FIXTURES/'wire-examples.json').read_text())
        class Peer(profile.Device):
            def request(self,op,data=b''):
                return self.response
        for version in (1,2):
            mapping=bytes.fromhex(examples[str(version)]['read_response'])[14:]
            peer=Peer(None);peer.version=version
            for phase,candidate in ((0,1),(1,0),(2,0),(3,0),(4,0)):
                peer.response=struct.pack('>BIII',phase,1,candidate,0)+mapping*(2 if candidate else 1)
                with self.assertRaises(ValueError):peer.snapshot()
            for phase,candidate in ((0,0),(1,1),(2,1),(3,1)):
                peer.response=struct.pack('>BIII',phase,1,candidate,0)+mapping*(2 if candidate else 1)
                self.assertEqual(peer.snapshot()['phase'],profile.PHASES[phase])

    def test_v2_table_metadata_matches_v1_semantics(self):
        config=json.loads((FIXTURES/'v2-default.json').read_text())
        desc={key:config[key] for key in ('schema','board','capabilities','gpio_policy')}
        mapping={key:config[key] for key in ('features','pins','spi','external','mcp2518fd')}
        import copy
        candidate=copy.deepcopy(mapping);candidate['spi']['2']['width']=1
        snapshot={'phase':'staged','revision':2,'candidate_id':2,'confirmed_id':0,
                  'active':mapping,'candidate':candidate}
        tables=profile.build_tables(desc,snapshot)
        fixed={row['gpio']:row for row in tables['fixed']}
        self.assertEqual(fixed[4]['direction'],'output')
        self.assertEqual(fixed[34]['direction'],'input')
        for row in tables['editable']:
            for choice in row['candidates']:
                self.assertIn('candidate_owners',choice)
        io2=next(row for row in tables['editable'] if row['signal']=='spi2.io2')
        selected=next(choice for choice in io2['candidates'] if choice['gpio']==22)
        self.assertEqual(selected['owners'],['spi2.io2'])
        self.assertEqual(selected['candidate_owners'],[])
        text=profile.render_human(desc,snapshot,tables)
        self.assertIn('UART1 computer control TX); output',text)
        self.assertIn('Current occupancy',text)

    def test_cli_apply_missing_ack_is_unknown_and_explicit_errors_remain_errors(self):
        import contextlib
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        examples=json.loads((FIXTURES/'wire-examples.json').read_text())

        class Transport:
            def __init__(self,response):
                self.response=response
                self.sent=[]
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def send(self,packet): self.sent.append(packet)
            def recv_response(self,cmd,seq,timeout):
                if len(self.sent)==1:
                    return SimpleNamespace(is_response=True,payload=bytes.fromhex(examples['1']['describe_response']))
                return self.response

        cases=((None,profile.ApplyOutcomeUnknown,'result unknown'),
               (SimpleNamespace(is_response=True,payload=b'\x04'),ValueError,'transaction busy'))
        for response,error,message in cases:
            transport=Transport(response)
            output=io.StringIO()
            with patch.object(sys,'argv',['profile','--version','1','apply','2']), contextlib.redirect_stdout(output):
                with self.assertRaises(error) as caught:
                    profile.main(transport_factory=lambda *args:transport)
            self.assertIn(message,str(caught.exception))
            if response is not None:
                self.assertNotIsInstance(caught.exception,profile.ApplyOutcomeUnknown)
            self.assertEqual(len(transport.sent),2)
            self.assertNotIn('Trial requested',output.getvalue())

    def test_negotiation_falls_back_only_for_explicit_rejection(self):
        wire=json.loads((FIXTURES/'wire-examples.json').read_text())
        class Peer(profile.Device):
            def __init__(self, reject):
                super().__init__(None);self.reject=reject;self.versions=[]
            def request(self,op,data=b''):
                self.versions.append(self.version)
                if self.version >= 2:raise ValueError(self.reject)
                return bytes.fromhex(wire['1']['describe_response'])[1:]
        peer=Peer('describe: 0x0f profile version unsupported')
        self.assertEqual(peer.descriptor()['schema'],1)
        self.assertEqual(peer.versions,[5,4,3,2,1])
        peer=Peer('No valid device-profile response')
        with self.assertRaises(ValueError):peer.descriptor()
        self.assertEqual(peer.versions,[5])
        peer=Peer('describe: 0x0f profile version unsupported')
        with self.assertRaises(ValueError):peer.descriptor(2)
        self.assertEqual(peer.versions,[2])
        with self.assertRaises(ValueError):peer.descriptor(6)

    def test_v5_role_direction_and_wire_order(self):
        old = json.loads((FIXTURES / "v2-default.json").read_text())
        desc = {key: old[key] for key in ("board", "gpio_policy")}
        desc.update(schema=5, capabilities=0x1ff)
        config = profile.load_config(FIXTURES / "v2-default.json", desc)
        raw = profile.encode_mapping(config)
        self.assertEqual((len(raw), raw[30:]), (34, bytes.fromhex("00ff00ff")))
        active = profile.decode_mapping(raw)
        draft = profile.decode_mapping(raw)
        draft["spi"]["3"].update(role="slave", slave_cs=39)
        draft["spi"] = dict(reversed(draft["spi"].items()))
        self.assertEqual(profile.encode_mapping(draft)[30:], bytes.fromhex("00ff0127"))
        tables = profile.build_tables(desc, {"active": active, "candidate": None}, draft)
        self.assertEqual(tables["role_conflicts"], [{"host": 3, "device": "mcp2518fd"}])
        self.assertIn("spi3.miso", {issue["signal"] for issue in tables["invalid_pins"]})
        rows = {r["signal"]: r for r in tables["editable"]}
        self.assertEqual(rows["spi3.miso"]["candidate_direction"], "output")
        self.assertEqual(rows["spi3.sck"]["candidate_direction"], "input")
        self.assertEqual(rows["spi3.slave_cs"]["candidate_gpio"], 39)
        self.assertEqual(rows["spi2.slave_cs"]["index"], 19)
        self.assertEqual(rows["spi3.slave_cs"]["index"], 20)
        self.assertFalse(rows["spi2.slave_cs"]["candidate_enabled"])
        with self.assertRaises(ValueError):
            profile.decode_mapping(raw[:30] + bytes.fromhex("02ff00ff"))

    def test_v3_optional_cs_migration_and_occupancy(self):
        old = json.loads((FIXTURES / "v2-default.json").read_text())
        desc = {key: old[key] for key in ("schema", "board", "capabilities", "gpio_policy")}
        desc.update(schema=3, capabilities=63)
        for name in ("v2-default.json", "v1-nondefault.json"):
            config = profile.load_config(FIXTURES / name, desc)
            self.assertEqual(config["external2"], {"enabled": False, "host": 2, "cs": 255})
            self.assertEqual(config["external"]["cs"], 27)
        config = profile.load_config(FIXTURES / "v2-default.json", desc)
        config["external"]["cs"] = profile.NO_CS
        config["external2"].update(enabled=True, host=3, cs=27)
        config["features"]["can"] = False
        data = profile.encode_mapping(config)
        self.assertEqual(data[22], 255)
        self.assertEqual(data[26:], bytes([1, 3, 27]))
        mapping = profile.decode_mapping(data)
        tables = profile.build_tables(desc, {"active": mapping, "candidate": None})
        pins = {row["gpio"]: row["owners"] for row in tables["occupancy"]}
        self.assertEqual(pins[27], ["external2.cs"])
        self.assertFalse(tables["editable"][14]["enabled"])
        self.assertEqual(tables["editable"][17]["signal"], "external2.cs")
        for index, value in ((26, 2), (27, 4)):
            broken = bytearray(data)
            broken[index] = value
            with self.assertRaises(ValueError):
                profile.decode_mapping(broken)

    def test_v4_three_roles_roundtrip_and_exact_wire_extension(self):
        desc, config = self.v4_config()
        for serial, business, role in ((True, False, "control"),
                                       (False, True, "business"),
                                       (False, False, "reserved")):
            with self.subTest(role=role):
                candidate = copy.deepcopy(config)
                candidate["features"]["serial"] = serial
                candidate["uart1_business"] = business
                loaded = self.load_json(candidate, desc)
                self.assertEqual(loaded, candidate)
                raw = profile.encode_mapping(loaded)
                self.assertEqual(len(raw), 30)
                self.assertEqual(raw[29], int(business))
                self.assertEqual(bool(int.from_bytes(raw[:2], "big") & 1), serial)
                legacy = {key: value for key, value in loaded.items() if key != "uart1_business"}
                self.assertEqual(raw[:29], profile.encode_mapping(legacy))
                decoded = profile.decode_mapping(raw)
                self.assertIs(decoded["uart1_business"], business)
                self.assertIs(decoded["features"]["serial"], serial)
                self.assertEqual(profile.encode_mapping(decoded), raw)
                self.assertEqual(decoded["pins"], loaded["pins"])

    def test_v4_active_candidate_and_draft_roles_keep_fixed_resources(self):
        desc, active = self.v4_config()
        saved = copy.deepcopy(active)
        saved["features"]["serial"] = False
        saved["uart1_business"] = True
        draft = copy.deepcopy(saved)
        draft["uart1_business"] = False
        snapshot = {"active": active, "candidate": saved}
        frozen = copy.deepcopy((desc, snapshot, draft))
        tables = profile.build_tables(desc, snapshot)
        preview = profile.build_tables(desc, snapshot, draft)
        for table, candidate_role in ((tables, "business"), (preview, "reserved")):
            for key, role in (("fixed", "control"), ("occupancy", "control"),
                              ("candidate_occupancy", candidate_role)):
                pins = {row["gpio"]: row for row in table[key]}
                for gpio, owner in ((4, "uart1.tx"), (34, "uart1.rx")):
                    self.assertEqual(pins[gpio]["uart1_role"], role)
                    if key != "fixed":
                        self.assertEqual(pins[gpio]["state"], "fixed")
                        self.assertEqual(pins[gpio]["owners"], [owner])
            for row in table["editable"]:
                self.assertNotIn(row["signal"], ("uart1.tx", "uart1.rx"))
                self.assertTrue({choice["gpio"] for choice in row["candidates"]}.isdisjoint({4, 34}))
        self.assertEqual((desc, snapshot, draft), frozen)
        for source in (active, saved, draft):
            rows = profile.build_tables(desc, {"active": source, "candidate": None})
            fixed = {row["gpio"]: row for row in rows["fixed"]}
            self.assertEqual(fixed[4]["direction"], "output")
            self.assertEqual(fixed[34]["direction"], "input")
            text = profile.render_human(desc, {"revision": 1, "phase": "confirmed",
                                        "confirmed_id": 1, "candidate_id": 0,
                                        "active": source, "candidate": None}, rows)
            role = "control" if source["features"]["serial"] else "business" if source["uart1_business"] else "reserved"
            self.assertIn("UART1 " + role, text)

    def test_v4_import_legacy_versions_preserves_wiring_and_disables_business(self):
        desc, config = self.v4_config()
        for name in ("v1-nondefault.json", "v2-default.json"):
            with self.subTest(source=name):
                old_desc = {**desc, "schema": 3, "capabilities": 63}
                old = profile.load_config(FIXTURES / name, old_desc)
                loaded = profile.load_config(FIXTURES / name, desc)
                self.assertFalse(loaded["uart1_business"])
                self.assertEqual(profile.encode_mapping(loaded)[:29], profile.encode_mapping(old))
                self.assertEqual(loaded["revision"], old["revision"])
                self.assertEqual(loaded["gpio_policy"], desc["gpio_policy"])
        v3 = {key: value for key, value in config.items() if key != "uart1_business"}
        v3.update(schema=3, capabilities=63)
        v3["features"]["serial"] = False
        v3["external"].update(host=3, cs=profile.NO_CS)
        v3["external2"].update(enabled=True, host=2, cs=25)
        loaded = self.load_json(v3, desc)
        self.assertFalse(loaded["uart1_business"])
        self.assertFalse(loaded["features"]["serial"])
        self.assertEqual(profile.encode_mapping(loaded)[:29], profile.encode_mapping(v3))

    def test_v4_malicious_json_roles_capabilities_and_fixed_pin_changes_rejected(self):
        desc, config = self.v4_config()
        broken = copy.deepcopy(config)
        broken["uart1_business"] = True
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            self.load_json(broken, desc)
        for value in (1, "true", None, [], {}):
            broken = copy.deepcopy(config)
            broken["uart1_business"] = value
            with self.subTest(business=value), self.assertRaises(ValueError):
                self.load_json(broken, desc)
        unsupported = {**desc, "capabilities": 63}
        broken = {**copy.deepcopy(config), **unsupported, "uart1_business": True}
        broken["features"]["serial"] = False
        with self.assertRaisesRegex(ValueError, "does not support UART1"):
            self.load_json(broken, unsupported)
        for mutate in (lambda c: c["gpio_policy"].__setitem__("4", "flexible"),
                       lambda c: c["gpio_policy"].__setitem__("34", "input_only"),
                       lambda c: c.__setitem__("board", "EVIL"),
                       lambda c: c.__setitem__("uart1_pins", {"tx": 25, "rx": 35})):
            broken = copy.deepcopy(config)
            mutate(broken)
            with self.assertRaises(ValueError):
                self.load_json(broken, desc)
        self.assertFalse(config["uart1_business"])
        self.assertEqual(desc["gpio_policy"]["4"], "uart1.tx")

    def test_v4_descriptor_snapshot_sizes_and_invalid_boolean_wire(self):
        desc, config = self.v4_config()
        raw = profile.encode_mapping(config)
        for value in (2, 255):
            broken = bytearray(raw)
            broken[29] = value
            with self.assertRaisesRegex(ValueError, "UART1 business"):
                profile.decode_mapping(broken)

        class Peer(profile.Device):
            def request(self, op, data=b""):
                return self.response

        peer = Peer(None)
        policies = bytes(profile.POLICIES.index(desc["gpio_policy"][str(i)]) for i in range(40))
        descriptor = b"\x04HXB1" + struct.pack(">IH", 127, 30) + raw + policies
        peer.response = descriptor
        self.assertEqual(peer.descriptor(4), desc)
        for size in (29, 31):
            peer.response = descriptor[:9] + struct.pack(">H", size) + descriptor[11:]
            with self.assertRaises(ValueError):
                peer.descriptor(4)
        candidate = bytearray(raw)
        candidate[1] &= ~1
        candidate[29] = 1
        peer.response = struct.pack(">BIII", 1, 7, 9, 3) + raw + candidate
        snapshot = peer.snapshot()
        self.assertFalse(snapshot["active"]["uart1_business"])
        self.assertTrue(snapshot["candidate"]["uart1_business"])
        self.assertEqual(snapshot["revision"], 7)
        peer.response = struct.pack(">BIII", 0, 7, 0, 3) + raw[:29]
        with self.assertRaisesRegex(ValueError, "snapshot"):
            peer.snapshot()

    def test_cli_v4_json_three_roles_uses_real_read_codec_without_writes(self):
        import contextlib
        import io
        from types import SimpleNamespace
        from unittest.mock import patch
        desc, config = self.v4_config()
        policies = bytes(profile.POLICIES.index(desc["gpio_policy"][str(i)]) for i in range(40))

        class Transport:
            def __init__(self, raw):
                self.responses = [b"\0\x04HXB1" + struct.pack(">IH", 127, 30) + raw + policies,
                                  b"\0" + struct.pack(">BIII", 0, 1, 0, 1) + raw]
                self.sent = []
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def send(self, packet): self.sent.append(packet)
            def recv_response(self, cmd, seq, timeout):
                return SimpleNamespace(is_response=True, payload=self.responses.pop(0))

        for serial, business, role in ((True, False, "control"),
                                       (False, True, "business"),
                                       (False, False, "reserved")):
            config["features"]["serial"], config["uart1_business"] = serial, business
            transport = Transport(profile.encode_mapping(config))
            output = io.StringIO()
            with patch.object(sys, "argv", ["profile", "--version", "4", "show", "--json"]), contextlib.redirect_stdout(output):
                profile.main(transport_factory=lambda *args: transport)
            result = json.loads(output.getvalue())
            self.assertEqual(result["schema"], 4)
            self.assertIs(result["active"]["uart1_business"], business)
            rows = {row["gpio"]: row for row in result["tables"]["occupancy"]}
            for gpio in (4, 34):
                self.assertEqual(rows[gpio]["uart1_role"], role)
                self.assertEqual(rows[gpio]["state"], "fixed")
            self.assertEqual(len(transport.sent), 2)
            self.assertFalse(transport.responses)

if __name__=='__main__': unittest.main(verbosity=2)
