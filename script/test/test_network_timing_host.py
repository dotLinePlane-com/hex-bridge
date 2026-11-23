"""No-hardware regression for pipeline correlation and Wi-Fi cycle cleanup."""
from collections import deque
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_network as network
import test_ubcp_sessions as sessions


def frame(seq, cmd=None, payload=b'\0', event=False):
    return SimpleNamespace(seq_num=seq, cmd_code=network.CMD_NET_STATUS if cmd is None else cmd,
                           channel_id=0, payload=payload, is_event=event, is_response=True)


class TimingTests(unittest.TestCase):
    def pipeline(self, frames):
        queue = deque(frames)
        transport = SimpleNamespace(send=lambda data: None,
                                    recv_frame=lambda timeout: queue.popleft() if queue else None)
        passed, failed = [], []
        with patch.object(network, 'transport', transport), \
                patch.object(network, 'next_seq', side_effect=range(10, 15)), \
                patch.object(network, 'pass_', side_effect=passed.append), \
                patch.object(network, 'fail_', side_effect=lambda *args: failed.append(args)):
            network.test_stress_08()
        return passed, failed

    def test_prior_dns_event_duplicate_and_out_of_order(self):
        passed, failed = self.pipeline([frame(9, 0x46), frame(99, event=True),
                                        frame(11), frame(11), frame(14), frame(10), frame(13), frame(12)])
        self.assertEqual(len(passed), 1)
        self.assertEqual(failed, [])

    def test_duplicate_does_not_replace_missing_response(self):
        passed, failed = self.pipeline([frame(10), frame(10), frame(11), frame(12), frame(13)])
        self.assertFalse(passed)
        self.assertIn('14', failed[0][1])

    def test_matching_wrong_command_status_and_empty_payload_fail(self):
        for invalid in (frame(10, 0x46), frame(10, payload=b'\2'), frame(10, payload=b'')):
            with self.subTest(invalid=invalid):
                passed, failed = self.pipeline([invalid])
                self.assertFalse(passed)
                self.assertEqual(len(failed), 1)

    def cycle(self, offline=True):
        suite = sessions.SessionTests(SimpleNamespace())
        closed = []
        old = SimpleNamespace(closed=False, send=lambda data: None, poll=lambda duration: None,
                              no_response=lambda seq: None, io=SimpleNamespace(close=lambda: closed.append(True)))
        uart, fresh = object(), object()
        pings, recoveries = [], []
        suite.ping = lambda ep: pings.append(ep)
        suite.request = lambda *args: SimpleNamespace(payload=b'\0\0' if offline else b'\0\3')
        suite.recover_wifi = lambda ep: recoveries.append(ep)
        suite.connect = lambda stack: fresh
        with patch.object(sessions.time, 'sleep'):
            if offline:
                self.assertIs(suite.cycle_wifi(None, uart, old), fresh)
                self.assertEqual(pings, [uart, fresh, fresh])
            else:
                with self.assertRaisesRegex(AssertionError, 'offline'):
                    suite.cycle_wifi(None, uart, old)
                self.assertEqual(closed, [True])
        self.assertEqual(recoveries, [uart])

    def test_wifi_recovery_without_remote_fin(self):
        self.cycle()

    def test_wifi_recovery_runs_after_failed_offline_assertion(self):
        self.cycle(False)

    def test_recovery_retries_uart_and_uses_temporary_connect(self):
        suite = sessions.SessionTests(SimpleNamespace(ssid='test-network', open_network=True))
        uart = object()
        pings = []
        requests = []
        def ping(ep):
            pings.append(ep)
            if len(pings) == 1:
                raise AssertionError('fallback pending')
        def request(ep, cmd, payload):
            requests.append((cmd, payload))
            return SimpleNamespace(payload=b'\0' if cmd == 0x46 else b'\0\3')
        suite.ping, suite.request = ping, request
        with patch.object(sessions.time, 'sleep'):
            suite.recover_wifi(uart)
        self.assertEqual(len(pings), 2)
        self.assertEqual(requests[0][0], 0x46)
        self.assertEqual(requests[0][1][:3], bytes([0, 0, 0]))
        self.assertEqual(requests[1], (0x47, b'\0'))


if __name__ == '__main__':
    unittest.main()
