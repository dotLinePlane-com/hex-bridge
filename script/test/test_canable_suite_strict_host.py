"""Offline regression of the real suite switch path; never open serial ports.

Run: python -m unittest discover -s script/test -p test_canable_suite_strict_host.py -v
These fakes prove host correlation/ordering only, not controller timing or ACKs.
"""
from collections import deque
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import serial
import test_canable as suite
from ubcp_client import UBCPParser


class Adapter:
    def __init__(self, events, corrupt=None, missing=None):
        self.events = events
        self.pending = deque([suite.CanableMessage(0x600, b'Hello')])
        self.corrupt = corrupt
        self.missing = missing

    def cmd_close(self):
        self.events.append(('close',))

    def set_bitrate(self, baud):
        self.events.append(('bitrate', baud))

    def set_data_bitrate(self, baud):
        self.events.append(('data_bitrate', baud))

    def cmd_open(self):
        self.events.append(('open',))

    def recv_all(self, timeout):
        self.events.append(('drain',))
        messages = list(self.pending)
        self.pending.clear()
        return messages

    def recv(self, timeout):
        return self.pending.popleft() if self.pending else None

    def transmitted(self, ident, data):
        # Noise must be ignored, but a wrong same-ID frame must be checked.
        self.pending.append(suite.CanableMessage(0x321, b'noise'))
        if ident == self.missing:
            return
        msg = suite.CanableMessage(ident, data)
        if self.corrupt:
            self.corrupt(msg)
        self.pending.append(msg)
        self.pending.append(suite.CanableMessage(ident, data))


class Transport:
    def __init__(self, adapter, events, corrupt=None):
        self.adapter = adapter
        self.events = events
        self.corrupt = corrupt

    def send(self, wire):
        parser = UBCPParser()
        frames = [f for byte in wire if (f := parser.feed(byte)) is not None]
        assert len(frames) == 1
        self.request = request = frames[0]
        self.events.append(('request', request.seq_num, request.cmd_code, request.payload))
        if request.cmd_code == suite.CMD_CAN_SEND:
            ident = int.from_bytes(request.payload[:4], 'big')
            self.adapter.transmitted(ident, request.payload[5:])

    def recv_response(self, *, cmd_code, seq_num, timeout):
        request = self.request
        assert (cmd_code, seq_num) == (request.cmd_code, request.seq_num)
        payload = b'\0\0\0\0\0' if cmd_code == suite.CMD_CAN_SEND else b'\0'
        response = SimpleNamespace(seq_num=seq_num, cmd_code=cmd_code,
                                   channel_id=suite.CAN_CHANNEL, is_event=False,
                                   is_response=True, payload=payload)
        return self.corrupt(response) if self.corrupt else response


class StrictSwitchTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # Catch accidental access even if a future implementation adds preflight.
        for name in ('Serial', 'serial_for_url'):
            self.stack.enter_context(patch.object(serial, name, side_effect=AssertionError('hardware forbidden')))
        self.stack.enter_context(patch.object(suite.time, 'sleep'))
        self.stack.enter_context(patch.multiple(suite, passed=0, failed=0, skipped=0))
        self.output = StringIO()
        self.stack.enter_context(redirect_stdout(self.output))

    def prepare(self, *, response=None, message=None, missing=None):
        self.events = []
        adapter = Adapter(self.events, message, missing)
        transport = Transport(adapter, self.events, response)
        return transport, adapter

    def run_switch(self, *, baseline=(500000, 6), **kwargs):
        transport, adapter = self.prepare(**kwargs)
        return suite.test_can_baud_switch(transport, 10, adapter, *baseline)

    def test_all_cli_baselines_keep_250k_control_and_restore(self):
        for baud, index, target, target_index in ((500000, 6, 250000, 5),
                                                  (250000, 5, 250000, 5),
                                                  (1000000, 8, 250000, 5)):
            with self.subTest(baud=baud):
                self.assertEqual(self.run_switch(baseline=(baud, index)), 15)
                requests = [e for e in self.events if e[0] == 'request']
                self.assertEqual([e[1] for e in requests], list(range(10, 15)))
                self.assertEqual([e[2] for e in requests], [0x13, 0x12, 0x13, 0x12, 0x13])
                self.assertEqual([e[3] for e in requests if e[2] == 0x12],
                                 [bytes([target_index, 3, 32, 0]), bytes([index, 3, 32, 0])])
                self.assertEqual([e for e in self.events if e[0] == 'bitrate'],
                                 [('bitrate', target), ('bitrate', baud)])
                self.assertEqual(self.events[0], ('drain',))
                for pos, event in enumerate(self.events):
                    if event[0] == 'request' and event[2] == 0x12:
                        self.assertEqual(self.events[pos - 1], ('close',))
                        self.assertEqual(self.events[pos + 1][0], 'bitrate')
                self.assertEqual(suite.failed, 0)
                self.assertEqual(suite.passed, 26)
                suite.passed = 0

    def test_mismatched_baseline_rejected_before_any_operations(self):
        for baseline in ((500000, 5), (125000, 4)):
            with self.subTest(baseline=baseline), self.assertRaises(ValueError):
                self.run_switch(baseline=baseline)
            self.assertEqual(self.events, [])

    def test_bad_send_response_records_failure_and_continues_restoration(self):
        variants = [None, {'seq_num': 99}, {'cmd_code': 0x16},
                    {'channel_id': 2}, {'is_event': True}, {'is_response': False},
                    {'payload': b''}, {'payload': b'\x17'},
                    {'payload': b'\0\0'}, {'payload': b'\0' * 6}]
        for seq in (10, 12, 14):
            for change in variants:
                with self.subTest(seq=seq, change=change):
                    def corrupt(response):
                        if response.seq_num != seq:
                            return response
                        if change is None:
                            return None
                        response.__dict__.update(change)
                        return response
                    failures_before = suite.failed
                    self.assertEqual(self.run_switch(response=corrupt), 15)
                    requests = [e for e in self.events if e[0] == 'request']
                    self.assertEqual(requests[-1][1], 14)
                    self.assertGreater(suite.failed, failures_before)

    def test_unconfirmed_target_config_skips_world_but_restores_and_checks_back(self):
        for payload in (None, b'', b'\x17', b'\0\0'):
            with self.subTest(payload=payload):
                def corrupt(response):
                    if response.seq_num == 11:
                        if payload is None:
                            return None
                        response.payload = payload
                    return response
                self.assertEqual(self.run_switch(response=corrupt), 14)
                requests = [e for e in self.events if e[0] == 'request']
                self.assertEqual([e[2] for e in requests], [0x13, 0x12, 0x12, 0x13])
                self.assertEqual(requests[-1][3], b'\0\0\x06\x02\x04Back')
                self.assertEqual([e for e in self.events if e[0] == 'bitrate'], [('bitrate', 500000)])

    def test_unconfirmed_baseline_config_raises_without_commands_or_back(self):
        for payload in (None, b'', b'\x17', b'\0\0'):
            with self.subTest(payload=payload):
                def corrupt(response):
                    if response.seq_num == 13:
                        if payload is None:
                            return None
                        response.payload = payload
                    return response
                with patch.object(suite, 'can_close', side_effect=AssertionError('cleanup belongs to suite finally')):
                    with self.assertRaisesRegex(RuntimeError, 'Baseline CONFIG failed'):
                        self.run_switch(response=corrupt)
                self.assertEqual(self.events[-2:], [
                    ('close',), ('request', 13, 0x12, b'\x06\x03\x20\0')])
                self.assertNotIn(('bitrate', 500000), self.events)

    def test_same_id_wrong_frame_fails_without_skipping_remaining_stages(self):
        variants = {'is_extended': True, 'is_rtr': True, 'is_fd': True,
                    'is_brs': True, 'dlc': 0, 'data': b'wrong'}
        for ident in (0x600, 0x601, 0x602):
            for attr, value in variants.items():
                with self.subTest(ident=ident, attr=attr):
                    def corrupt(msg):
                        if msg.id == ident:
                            setattr(msg, attr, value)
                    failures_before = suite.failed
                    self.assertEqual(self.run_switch(message=corrupt), 15)
                    requests = [e for e in self.events if e[0] == 'request']
                    self.assertEqual(int.from_bytes(requests[-1][3][:4], 'big'), 0x602)
                    self.assertGreater(suite.failed, failures_before)

    def test_missing_probe_cannot_be_replaced_by_stale_or_unrelated_frames(self):
        for ident in (0x600, 0x601, 0x602):
            with self.subTest(ident=ident):
                failures_before = suite.failed
                self.assertEqual(self.run_switch(missing=ident), 15)
                self.assertEqual(suite.failed, failures_before + 1)
                self.assertIn(('bitrate', 500000), self.events)

    def test_complete_entry_keeps_back_fd_and_cleanup_after_missing_world(self):
        transport, adapter = self.prepare(missing=0x601)
        adapter.open = lambda: None
        adapter.get_version = lambda: 'offline fake'
        adapter.close = lambda: self.events.append(('adapter_release',))
        transport.open = lambda: None
        transport.recv_frame = lambda timeout: None
        transport.flush_input = lambda: None
        transport.close = lambda: self.events.append(('transport_release',))
        other_classic_tests = ('test_can_send_std', 'test_can_send_ext', 'test_can_send_rtr',
                               'test_can_recv_std', 'test_can_recv_ext', 'test_can_multi_frame',
                               'test_can_filter', 'test_can_filter_both', 'test_can_status',
                               'test_can_loopback', 'test_can_error_paths')
        fd_tests = ('test_fd_send_64', 'test_fd_send_brs', 'test_fd_recv_64',
                    'test_fd_recv_brs', 'test_fd_dlc_map', 'test_fd_loopback')
        with ExitStack() as stack:
            stack.enter_context(patch.object(suite.sys, 'argv', ['test_canable.py']))
            stack.enter_context(patch.object(suite, 'CanableChannel', return_value=adapter))
            stack.enter_context(patch.object(suite, 'MCPTransport', return_value=transport))
            stack.enter_context(patch.object(suite, 'canable_setup'))
            stack.enter_context(patch.object(suite, 'mcp_open_classic', side_effect=lambda t, seq, **kw: seq))
            fd_setup = stack.enter_context(patch.object(suite, 'mcp_open_fd', side_effect=lambda t, seq, **kw: seq))
            for name in other_classic_tests:
                stack.enter_context(patch.object(suite, name, side_effect=lambda t, seq, *args: seq))
            fd_mocks = [stack.enter_context(patch.object(suite, name, side_effect=lambda t, seq, *args: seq))
                        for name in fd_tests]
            self.assertEqual(suite.main(), 1)
        fd_setup.assert_called_once()
        for mock in fd_mocks:
            mock.assert_called_once()
        self.assertIn('[FAIL] World at 250k:', self.output.getvalue())
        self.assertIn('[PASS] Hello before switch data:', self.output.getvalue())
        self.assertIn('[PASS] Back at 500000 data:', self.output.getvalue())
        self.assertNotIn('Suite exception', self.output.getvalue())
        self.assertEqual(suite.failed, 1)
        self.assertIn(('bitrate', 500000), self.events)
        self.assertEqual(self.events[-2:], [('transport_release',), ('adapter_release',)])

    def test_matching_uses_one_deadline_for_unrelated_traffic(self):
        clock = SimpleNamespace(now=0.0)
        timeouts = []

        def receive(timeout):
            timeouts.append(timeout)
            clock.now += 0.4
            return suite.CanableMessage(0x321)

        adapter = SimpleNamespace(recv=receive)
        with patch.object(suite.time, 'monotonic', side_effect=lambda: clock.now):
            self.assertIsNone(suite.recv_canable(adapter, 0x600, timeout=1.0))
        self.assertEqual(len(timeouts), 3)
        for actual, expected in zip(timeouts, (1.0, 0.6, 0.2)):
            self.assertAlmostEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
