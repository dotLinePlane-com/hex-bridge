"""Offline tests for Wi-Fi host wire formats, capability gating and secrecy."""
import argparse
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import subprocess
import unittest
from unittest.mock import patch

CLI = Path(__file__).resolve().parents[1] / 'cli'
sys.path.insert(0, str(CLI))
from wifi_utils import build_wifi_join, parse_wifi_status, require_wifi_capability

spec = importlib.util.spec_from_file_location('network_cli', CLI / 'hex-bridge-network-cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)
from ubcp_client import Frame, UBCPParser


def response(cmd, payload, seq=1):
    frame = Frame()
    frame.cmd_code, frame.seq_num, frame.flags = cmd, seq, 0x80
    frame.payload, frame.payload_len = payload, len(payload)
    return frame


class FakeTransport:
    def __init__(self, caps=1 << 12):
        self.caps, self.requests, self.frames = caps, [], []

    def flush_input(self):
        pass

    def send(self, wire):
        parser = UBCPParser()
        frame = None
        for byte in wire:
            parsed = parser.feed(byte)
            if parsed is not None:
                frame = parsed
        self.requests.append(frame)
        payload = b'\0'
        if frame.cmd_code == 1:
            payload = b'\0' * 12 + self.caps.to_bytes(2, 'big')
        if frame.cmd_code == 0x47:
            payload = bytes([0, 3, 6, 11, 200, 3]) + b'net'
        self.frames.append(response(frame.cmd_code, payload, frame.seq_num))

    def recv_frame(self, timeout):
        return self.frames.pop(0) if self.frames else None


class WifiHostTests(unittest.TestCase):
    def setUp(self):
        self.parser = argparse.ArgumentParser()
        cli._register_subcommands(self.parser)
        cli._json_mode = True

    def dispatch(self, transport, tokens):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            cli._dispatch(transport, self.parser.parse_args(tokens))
        return captured.getvalue()

    def test_join_boundaries_and_byte_lengths(self):
        ssid = '\u7f51' * 10
        payload = build_wifi_join(ssid, '12345678', True)
        self.assertEqual(payload[:5], bytes([0, 1, 1, 30, 8]))
        for invalid in ['', 'a' * 33, '\u7f51' * 11]:
            with self.assertRaises(ValueError):
                build_wifi_join(invalid, '12345678')
        for key in ['short', 'x' * 64, '1234567\n', '1234567\u00e9']:
            with self.assertRaises(ValueError):
                build_wifi_join('net', key)
        self.assertEqual(build_wifi_join('net', auth=0), b'\0\0\0\3\0net')
        with self.assertRaises(ValueError):
            build_wifi_join('net', '12345678', auth=0)

    def test_capability_gate_precedes_all_wifi_commands(self):
        for command in ['wifi-status', 'wifi-leave', 'wifi-forget', 'wifi-join']:
            transport = FakeTransport(caps=0)
            tokens = [command] + (['--ssid', 'net', '--open'] if command == 'wifi-join' else [])
            with self.assertRaisesRegex(ValueError, 'WIFI_STA'):
                self.dispatch(transport, tokens)
            self.assertEqual([f.cmd_code for f in transport.requests], [1])

    def test_join_and_output_never_contain_password(self):
        transport = FakeTransport()
        with patch.dict(os.environ, HEX_BRIDGE_WIFI_PASSWORD='secret123'):
            text = self.dispatch(transport, ['wifi-join', '--ssid', 'net', '--save'])
        self.assertNotIn('secret123', text)
        request = transport.requests[-1]
        self.assertEqual(request.channel_id, 0)
        self.assertEqual(request.payload, b'\0\1\1\3\x09netsecret123')
        self.assertIn('accepted', text)

    def test_status_and_control_commands(self):
        transport = FakeTransport()
        text = self.dispatch(transport, ['wifi-status'])
        self.assertIn('IPV4_READY', text)
        self.assertIn('SAVE_FAILED', text)
        self.assertIn('-56', text)
        for cmd, code in [('wifi-leave', 0x48), ('wifi-forget', 0x49)]:
            self.dispatch(transport, [cmd])
            self.assertEqual(transport.requests[-1].cmd_code, code)
            self.assertEqual(transport.requests[-1].payload, b'\0')

    def test_malformed_status_rejected(self):
        for payload in [b'', b'\2', b'\0', bytes([0, 1, 0, 0, 128, 3]),
                        bytes([0, 6, 0, 0, 128, 0])]:
            with self.assertRaises(ValueError):
                parse_wifi_status(payload)

    def test_join_timeout_queries_without_resubmitting(self):
        transport = FakeTransport()
        real = cli.expect_response

        def request(uart, cmd, payload=b'', **kwargs):
            if cmd == 0x46:
                raise TimeoutError('lost acknowledgement')
            return real(uart, cmd, payload, **kwargs)

        with patch.object(cli, 'expect_response', side_effect=request):
            text = self.dispatch(transport, ['wifi-join', '--ssid', 'net', '--open'])
        self.assertIn('UNKNOWN', text)
        self.assertEqual([f.cmd_code for f in transport.requests], [1, 0x47])

    def test_event_logs_redact_wifi_payloads(self):
        with patch.object(cli, '_write_event_log') as log:
            cli._forward_event_to_log(response(0x46, b'secret123'))
        self.assertEqual(log.call_args.args[0]['payload_hex'], '')

    def test_responses_match_sequence_and_direction(self):
        transport = FakeTransport()
        transport.frames = [response(0x48, b'\x04', seq=0), response(0x48, b'')]
        transport.frames[1].flags = 0
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_wifi_leave(transport, self.parser.parse_args(['wifi-leave']))
        self.assertEqual(transport.frames, [])

    def test_legacy_net_does_not_require_wifi(self):
        transport = FakeTransport(caps=0)
        self.dispatch(transport, ['net-close-all'])
        self.assertEqual([f.cmd_code for f in transport.requests], [0x45])

    def test_help_runs_with_default_windows_output_encoding(self):
        env = {key: value for key, value in os.environ.items()
               if key not in ('PYTHONIOENCODING', 'PYTHONUTF8')}
        for args in [['--help'], ['wifi-join', '--help'], []]:
            result = subprocess.run([sys.executable, '-B', str(CLI / 'hex-bridge-network-cli.py'), *args],
                                    env=env, capture_output=True, check=True)
            self.assertEqual(result.stderr, b'')
            self.assertIn(b'wifi-join', result.stdout)
            result.stdout.decode('ascii')

    def test_human_status_and_interactive_banner_are_printable(self):
        cli._json_mode = False
        text = self.dispatch(FakeTransport(), ['wifi-status'])
        text.encode('ascii')
        captured = io.StringIO()
        with patch('builtins.input', return_value='quit'), contextlib.redirect_stdout(captured):
            cli.interactive_session(None, argparse.Namespace(port='COM4', baud=115200))
        captured.getvalue().encode('ascii')


if __name__ == '__main__':
    unittest.main()
