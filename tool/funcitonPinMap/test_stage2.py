"""Profile v6 codec, routing, session lifetime and real Tk Stage2 controls."""
import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'script'))
import hexbridge_profile as profile
import hexbridge_io as business
import backend
import test_app as existing


def mapping():
    m = json.loads((Path(__file__).resolve().parents[2] / 'script/test/fixtures/profile/v2-default.json').read_text())
    m = {key: value for key, value in m.items() if key in ('features', 'pins', 'spi', 'external', 'mcp2518fd')}
    m['external2'] = dict(profile.SECOND_SPI_DEFAULT)
    m['uart1_business'] = False
    for row in m['spi'].values():
        row.update(role='master', slave_cs=255)
    return profile.migrate_v5(m)


class CodecTests(unittest.TestCase):
    def test_v6_roundtrip_exact_wire_layout_and_all_instances(self):
        m = mapping()
        m['i2c']['1'].update(enabled=True, scl=25, sda=26, clock_hz=400000, timeout_ms=750)
        m['gpio_lines']['13'].update(enabled=True, pin=35, trigger='both', debounce_ms=10)
        wire = profile.encode_mapping(m)
        self.assertEqual(len(wire), 116)
        self.assertEqual(wire[40:46], struct.pack('>4BH', 1, 25, 26, 1, 750))
        self.assertEqual(wire[111:], bytes((35, 1, 0, 3, 10)))
        self.assertEqual(profile.decode_mapping(wire), m)
        self.assertEqual(profile.decode_mapping(wire[:34]), {k: v for k, v in m.items() if k not in ('i2c', 'gpio_lines')})

    def test_reserved_bits_invalid_enums_and_trigger_debounce(self):
        m = mapping()
        for offset, value in ((34, 2), (37, 2), (47, 16), (48, 4), (49, 5)):
            wire = bytearray(profile.encode_mapping(m)); wire[offset] = value
            with self.assertRaises(ValueError): profile.decode_mapping(wire)
        m['gpio_lines']['0']['trigger'] = 'both'
        with self.assertRaises(ValueError): profile.encode_mapping(m)
        m = mapping(); del m['gpio_lines']['13']
        with self.assertRaises(ValueError): profile.encode_mapping(m)

    def test_profile_import_v5_migrates_and_preserves_fields(self):
        m = mapping()
        desc = dict(schema=6, board='HXB1', capabilities=0x7ff, gpio_policy={})
        old = {**desc, 'schema':5, 'capabilities':0x1ff, 'revision':9, **{k:v for k,v in m.items() if k not in ('i2c','gpio_lines')}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'; path.write_text(json.dumps(old))
            result = profile.load_config(path, desc)
        self.assertEqual(result['revision'], 9)
        self.assertEqual(result['gpio_lines'], m['gpio_lines'])


class MockTransport:
    def __init__(self):
        self.frames = []
        self.sent = []
        self.statuses = {}
        self.closed = False
    def close(self): self.closed = True
    def send(self, packet):
        parser = profile.UBCPBuilder # parse real serialized request
        from ubcp_client import UBCPParser
        p = UBCPParser(); frame = None
        for byte in packet:
            frame = p.feed(byte) or frame
        self.sent.append(frame)
        cmd, channel = frame.cmd_code, frame.channel_id
        status = self.statuses.get((cmd, channel), 0)
        data = bytes(16) if cmd == 1 else bytes((4, 8, 4, 9, 4, 10, 5, 11, 5)) if cmd == 7 else b'\x01' if cmd == 0x82 else b'\x00\x02\xab\xcd' if cmd in (0x34, 0x35) else b'\x01\x50' if cmd == 0x36 else b''
        self.frames.append(SimpleNamespace(is_response=True, is_event=False, cmd_code=cmd, channel_id=channel, seq_num=frame.seq_num, payload=bytes((status,))+data))
    def recv_frame(self, timeout=0): return self.frames.pop(0) if self.frames else None


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.m = mapping()
        for bus in self.m['i2c'].values(): bus.update(enabled=True, scl=25, sda=26)
        self.m['gpio_lines']['0'].update(enabled=True, pin=25, mode='output')
        self.m['gpio_lines']['1'].update(enabled=True, pin=32, mode='open_drain')
        self.m['gpio_lines']['2'].update(enabled=True, pin=35)
        snapshot = dict(active=self.m)
        device = SimpleNamespace(seq=0, descriptor=lambda:dict(schema=6), snapshot=lambda:snapshot)
        self.transport = MockTransport()
        with patch.object(business, 'Device', return_value=device):
            self.session = business.BusinessSession(self.transport)

    def test_two_i2c_sessions_raw_address_and_repeated_start_payload(self):
        self.session.i2c('open', bus=0)
        self.session.i2c('open', bus=1, addr_bits=10)
        result = self.session.i2c('read-reg', bus=1, addr=0x2ab, register=b'\x01\x02', length=2)
        self.assertEqual(result['data'], b'\xab\xcd')
        self.assertEqual(self.transport.sent[-1].payload, b'\x02\xab\x02\x01\x02\x00\x02')
        self.assertEqual(self.transport.sent[-1].channel_id, 9)
        self.session.i2c('close', bus=0)
        self.assertEqual(self.session.open_buses, {'1': 10})
        with self.assertRaises(ValueError): self.session.i2c('scan', bus=1)

    def test_gpio_cross_group_partial_failure_and_preflight(self):
        plan = self.session.plan_write({'0':1,'1':0})
        self.assertEqual([(p['channel'],p['mask']) for p in plan],[(10,1<<25),(11,1)])
        self.transport.statuses[(0x86,11)] = 0x80
        result = self.session.write_many({'0':1,'1':0})
        self.assertEqual([r['status'] for r in result],[0,0x80])
        before = len(self.transport.sent)
        with self.assertRaises(ValueError): self.session.write_many({'0':1,'2':0})
        self.assertEqual(len(self.transport.sent),before)

    def test_interleaved_events_use_current_mapping_and_old_events_discarded(self):
        self.transport.frames.append(SimpleNamespace(is_response=False,is_event=True,cmd_code=0x85,channel_id=11,seq_num=0,payload=b'\x03\x01\x01',timestamp=1234))
        result = self.session.gpio('read',line=2)
        self.assertEqual(result['level'],1)
        events = self.session.poll_events(0)
        self.assertEqual((events[0]['line'],events[0]['pin'],events[0]['timestamp']),(2,35,1234))
        self.session.disconnect()
        self.assertFalse(self.session.open_buses)
        self.assertFalse(self.session.events)
        with self.assertRaises(OSError): self.session.request(0x81,10)

    def test_cli_commands_share_open_state(self):
        business.execute(self.session,['i2c','open','--bus','0'])
        result = business.execute(self.session,['i2c','read-reg','--bus','0','--addr','0x50','--reg','00','--length','2'])
        self.assertEqual(result['address'],0x50)
        self.assertEqual(result['data'],b'\xab\xcd')

    def test_batch_cli_returns_nonzero_status_for_partial_failure(self):
        self.transport.statuses[(0x86,11)] = 0x80
        result = business.execute(self.session,['gpio','write-many','{"0":1,"1":0}'])
        self.assertEqual(result['status'],0x80)
        self.assertEqual([r['status'] for r in result['data']],[0,0x80])

    def test_disconnection_clears_open_state_and_does_not_retry_write(self):
        self.session.i2c('open')
        before = len(self.transport.sent)
        def fail(packet):
            self.transport.sent.append(packet)
            raise OSError('connection lost during write')
        self.transport.send = fail
        with self.assertRaises(OSError):
            self.session.i2c('write',data=b'\x01')
        self.assertEqual(len(self.transport.sent),before+1)
        self.assertFalse(self.session.open_buses)
        self.assertFalse(self.session.connected)

    def test_topology_gates_business_and_disabled_mapping_is_not_draft(self):
        del self.session.topology[9]
        with self.assertRaises(ValueError): self.session.i2c('open',bus=1)
        with self.assertRaises(ValueError): self.session.gpio('read',line=13)

    def test_explicit_close_recovers_device_state_unknown_to_host(self):
        self.assertFalse(self.session.open_buses)
        result = self.session.i2c('close',bus=1)
        self.assertEqual(result['status'],0)
        self.assertEqual((self.transport.sent[-1].cmd_code,self.transport.sent[-1].channel_id),(0x31,9))
        self.session.i2c('open',bus=1)
        self.assertEqual(self.session.open_buses,{'1':7})
        self.session.disconnect()
        self.assertEqual(self.transport.sent[-1].cmd_code,0x31)
        self.assertTrue(self.transport.closed)

    def test_read_many_duplicate_lines_do_not_shift_mask(self):
        self.session.request = lambda command, channel, payload, instance=None: dict(status=0,data=bytes(8),payload=payload)
        result = self.session.read_many([0,0,2,2])
        self.assertEqual(result[0]['payload'], struct.pack('>I',1<<25))
        self.assertEqual(result[1]['payload'], struct.pack('>I',1<<3))
        self.assertEqual(len(result[0]['lines']),1)

    def test_get_info_error_and_malformed_identity_are_rejected(self):
        for status, data in ((1,bytes(16)),(0,bytes(15))):
            response = dict(status=status,data=data)
            device = SimpleNamespace(seq=0,descriptor=lambda:dict(schema=6),snapshot=lambda:dict(active=self.m))
            with patch.object(business,'Device',return_value=device), patch.object(business.BusinessSession,'request',return_value=response):
                with self.assertRaisesRegex(ValueError,'GET_INFO'):
                    business.BusinessSession(MockTransport())


class Stage2TkTests(unittest.TestCase):
    destroy_window = existing.TkTests.destroy_window
    pump = existing.TkTests.pump
    click = existing.TkTests.click
    def setUp(self):
        existing.V3TkTests.setUp(self)
        self.board.desc.update(schema=6, capabilities=0x7ff)
        m = self.board.state['active']
        m['uart1_business'] = False
        for row in m['spi'].values(): row.update(role='master',slave_cs=255)
        self.board.state['active'] = profile.migrate_v5(m)
        self.board.confirmed = copy.deepcopy(self.board.state['active'])
        self.click('read')

    def edit(self, instance, field, value):
        key = instance, field
        self.gui.stage2.fields[key].set(value)
        self.gui.stage2.edit(key)
        self.pump()

    def test_independent_i2c_controls_fourteen_gpio_rows_and_draft_only(self):
        initial = copy.deepcopy(self.board.state)
        self.edit('i2c0','timeout_ms','500')
        self.edit('i2c1','clock_hz','400000')
        self.edit('gpio.13','pin','35')
        self.edit('gpio.13','enabled',True)
        self.assertEqual(self.service.draft['i2c']['0']['timeout_ms'],500)
        self.assertEqual(self.service.draft['i2c']['1']['clock_hz'],400000)
        self.assertEqual(self.service.draft['i2c']['0']['clock_hz'],100000)
        self.assertEqual(self.board.state,initial)
        self.assertEqual(self.board.calls,[])
        self.assertIn(('gpio.13','pin'),self.gui.stage2.widgets)
        self.assertEqual(tuple(self.gui.stage2.widgets[('gpio.13','pull')]['values']),('none',))
        self.edit('gpio.13','enabled',False)
        self.edit('gpio.13','enabled',True)
        self.assertEqual(self.service.draft['gpio_lines']['13']['pin'],35)

    def test_local_edit_keeps_serial_controls_enabled_and_recoverable(self):
        key = 'i2c0', 'timeout_ms'
        self.gui.stage2.fields[key].set('500')
        self.gui.stage2.edit(key)
        # A local draft edit must not lock the serial address or baud rate,
        # including while focus leaves the edited field.
        self.assertFalse(self.gui.port_box.instate(['disabled']))
        self.assertFalse(self.gui.baud_box.instate(['disabled']))
        self.pump()
        self.assertEqual(self.service.draft['i2c']['0']['timeout_ms'],500)

        self.gui.stage2.fields[key].set('invalid')
        self.gui.stage2.edit(key)
        self.pump()
        self.assertFalse(self.gui.port_box.instate(['disabled']))
        self.assertFalse(self.gui.baud_box.instate(['disabled']))
        self.assertFalse(self.gui.busy)
        self.edit('i2c0','timeout_ms','750')
        self.assertEqual(self.service.draft['i2c']['0']['timeout_ms'],750)

    def test_conflicts_reach_existing_occupancy_and_unassigned_is_not_gpio_zero(self):
        self.edit('gpio.0','pin','25')
        self.edit('gpio.0','enabled',True)
        owners = {r['gpio']:r['owners'] for r in self.service.view()['preview_tables']['candidate_occupancy']}
        self.assertIn('gpio.0',owners[25])
        self.assertGreater(len(owners[25]),1)
        self.assertEqual(self.gui.stage2.fields[('gpio.1','pin')].get(),'未分配')

    def test_old_firmware_controls_are_readonly_not_reported_disabled_mapping(self):
        self.board.desc.update(schema=5,capabilities=0x1ff)
        self.board.state['active'].pop('i2c')
        self.board.state['active'].pop('gpio_lines')
        self.click('read')
        self.assertIn('不支持',self.gui.stage2.support.cget('text'))
        self.assertTrue(all(widget.instate(['disabled']) for widget in self.gui.stage2.widgets.values()))
        with self.assertRaises(ValueError): self.service.set_parameter('i2c0','enabled',True)

    def test_json_export_import_keeps_fourteen_rows_and_both_controllers(self):
        self.edit('i2c1','timeout_ms','750')
        self.edit('gpio.13','pin','39')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            self.service.export_config(path)
            exported = json.loads(path.read_text(encoding='utf8'))
            self.assertEqual(set(exported['gpio_lines']),set(map(str,range(14))))
            self.service.reset_draft()
            self.service.import_config(path)
        self.assertEqual(self.service.draft['i2c']['1']['timeout_ms'],750)
        self.assertEqual(self.service.draft['gpio_lines']['13']['pin'],39)

    def test_stale_save_refreshes_snapshot_and_preserves_local_draft(self):
        self.edit('i2c1','timeout_ms','750')
        draft = copy.deepcopy(self.service.draft)
        self.board.state['revision'] += 1
        with self.assertRaisesRegex(ValueError,'已刷新'):
            self.service.check()
        self.assertEqual(self.service.draft,draft)
        self.assertEqual(self.service.snapshot['revision'],self.board.state['revision'])

    def test_compact_window_and_selected_line_detail_editor(self):
        self.root.geometry('980x650')
        self.gui.notebook.select(self.gui.stage2.tab)
        self.gui.stage2.select_line(13)
        self.pump()
        self.assertTrue(self.gui.stage2.detail_frames[13].winfo_ismapped())
        self.assertFalse(self.gui.stage2.detail_frames[0].winfo_ismapped())
        for widget in self.gui.stage2.widgets.values():
            if widget.winfo_ismapped():
                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width())


if __name__ == '__main__': unittest.main()
