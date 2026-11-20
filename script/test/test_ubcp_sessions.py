"""Opt-in board test for single-active UBCP UART1 / TCP9500 ownership.

Run only with an idle device (no other host clients):
  python script/test/test_ubcp_sessions.py --uart COM3 --host 192.168.1.42
Add --pcan for a PCAN-USB CAN peer at 500 kbit/s.
Add --event-uart COM4 for a USB adapter wired to UART2 RX/TX (115200).
Add --cycle-wifi --ssid NAME --key-env HEX_TEST_WIFI_KEY to leave and rejoin
Wi-Fi through UART1. Open networks use --open-network. Secrets are not logged.
No hardware is opened on import. An event adapter is optional; all event checks
report SKIP explicitly when it is absent. Slow DNS invalidation is best-effort
because a resolver may return before the deliberate disconnect.
"""
import argparse
import os
import socket
import time
from collections import deque
from contextlib import ExitStack
from ubcp_client import UBCPBuilder, UBCPParser


class Endpoint:
    def __init__(self, io, tcp=False):
        self.io, self.tcp = io, tcp
        self.parser = UBCPParser()
        self.frames = deque()
        self.closed = False

    def send(self, data):
        if self.tcp:
            self.io.sendall(data)
        else:
            self.io.write(data)
            self.io.flush()

    def poll(self, duration):
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            try:
                data = self.io.recv(4096) if self.tcp else self.io.read(4096)
            except (socket.timeout, TimeoutError):
                continue
            except (ConnectionError, OSError):
                if not self.tcp:
                    raise
                self.closed = True
                break
            if self.tcp and not data:
                self.closed = True
                break
            for byte in data:
                frame = self.parser.feed(byte)
                if frame is not None:
                    self.frames.append(frame)

    def response(self, seq, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in list(self.frames):
                if not frame.is_event and frame.seq_num == seq:
                    self.frames.remove(frame)
                    return frame
            self.poll(0.05)
        raise AssertionError(f'missing response seq={seq}')

    def no_response(self, seq, timeout=0.4):
        self.poll(timeout)
        assert not any(not f.is_event and f.seq_num == seq for f in self.frames), f'stale response seq={seq}'


class SessionTests:
    def __init__(self, args):
        self.args, self.seq = args, 1000

    def wire(self, cmd=0, payload=b'', channel=0):
        self.seq += 1
        return self.seq, UBCPBuilder.build_request(self.seq, cmd, channel, payload)

    def request(self, ep, cmd=0, payload=b'', channel=0):
        seq, wire = self.wire(cmd, payload, channel)
        ep.send(wire)
        return ep.response(seq)

    def ping(self, ep):
        frame = self.request(ep)
        assert len(frame.payload) == 7 and frame.payload[0] == 0

    def connect(self, stack):
        sock = stack.enter_context(socket.create_connection((self.args.host, self.args.port), 3))
        sock.settimeout(0.05)
        return Endpoint(sock, True)

    def event(self, active, inactive, adapter):
        marker = b'ownership-event-\x7d\x7e\n'
        active.frames.clear()
        inactive.frames.clear()
        adapter.write(marker)
        adapter.flush()
        active.poll(1)
        inactive.poll(0.2)
        events = [f for f in active.frames if f.is_event and f.cmd_code == 0xA4]
        assert events and any(marker in f.payload for f in events), 'UART2 event missing on active owner'
        assert not any(f.is_event for f in inactive.frames), 'event leaked to inactive owner'

    def can_event(self, active, inactive, pcan):
        from pcan_basic import PcanMessage
        # Unique marker distinguishes this event from any old hardware backlog.
        marker = (time.monotonic_ns() & ((1 << 64) - 1)).to_bytes(8, 'big')
        active.frames.clear()
        if inactive is not None:
            inactive.frames.clear()
        assert pcan.write(PcanMessage(id=0x5A7, data=marker)) == 0, 'PCAN transmit failed'
        active.poll(1)
        events = [f for f in active.frames if f.is_event and f.cmd_code == 0x14]
        assert any(len(f.payload) >= 13 and f.payload[5:13] == marker for f in events), 'CAN_RX event missing on active owner'
        if inactive is not None:
            inactive.poll(0.2)
            assert not any(f.is_event for f in inactive.frames), 'CAN event leaked to inactive owner'

    def run(self):
        import serial
        with ExitStack() as stack:
            port = stack.enter_context(serial.Serial(self.args.uart, self.args.baud, timeout=0.02))
            uart = Endpoint(port)
            port.reset_input_buffer()
            self.ping(uart)
            print('PASS UART1 baseline/provisioning path')
            pcan = None
            if self.args.pcan:
                from pcan_basic import PcanChannel, PcanHandle, PcanBaudrate
                pcan = PcanChannel(channel=PcanHandle.PCAN_USBBUS1 + self.args.pcan_channel - 1,
                                   baudrate=PcanBaudrate.PCAN_BD_500K)
                assert pcan.initialize() == 0, 'PCAN initialization failed'
                stack.callback(pcan.uninitialize)
                self.request(uart, 0x11, b'', 3)
                opened = self.request(uart, 0x10, b'\0', 3)
                assert opened.payload[0] in (0, 0x0B), f'CAN_OPEN status {opened.payload[0]}'
                assert self.request(uart, 0x12, bytes([6, 3, 32, 0]), 3).payload[0] == 0
                self.can_event(uart, None, pcan)
                print('PASS CAN events on initial UART1 owner')
            # Begin a UART half-frame before takeover; it must never complete.
            uart_half_seq, uart_half = self.wire()
            uart.send(uart_half[:6])
            tcp = self.connect(stack)
            self.ping(tcp)
            # Fragmented and coalesced requests use the original UBCP wire format.
            seq, wire = self.wire()
            for byte in wire:
                tcp.send(bytes([byte]))
            assert tcp.response(seq).payload[0] == 0
            seq1, wire1 = self.wire()
            seq2, wire2 = self.wire()
            tcp.send(wire1 + wire2)
            assert tcp.response(seq1).payload[0] == tcp.response(seq2).payload[0] == 0
            print('PASS takeover, fragmentation and coalescing')
            stale_seq, wire = self.wire()
            uart.send(wire + uart_half[6:])
            uart.no_response(stale_seq)
            uart.no_response(uart_half_seq, 0.1)
            print('PASS UART1 command suspension')
            other = self.connect(stack)
            try:
                other.send(self.wire()[1])
            except OSError:
                pass
            other.poll(0.5)
            assert other.closed and not other.frames, 'second TCP client was admitted'
            self.ping(tcp)
            print('PASS second client rejection preserves first owner')
            if pcan:
                self.can_event(tcp, uart, pcan)
                print('PASS CAN events exclusive to TCP')
            adapter = None
            if self.args.event_uart:
                adapter = stack.enter_context(serial.Serial(self.args.event_uart, 115200, timeout=0.02))
                opened = self.request(tcp, 0xA0, b'\0', 1)
                assert opened.payload[0] in (0, 0x0B), f'UART2 open status {opened.payload[0]}'
                self.event(tcp, uart, adapter)
                print('PASS events exclusive to TCP')
            else:
                print('SKIP events (provide --event-uart)')
            # DNS response may race close; any response after fallback on UART is
            # always a failure, regardless of resolver speed.
            # Build hostname length from bytes to avoid a malformed request.
            host = b'session-test.invalid.test'
            dns_seq, wire = self.wire(0x42, bytes([len(host)]) + host)
            tcp.send(wire)
            half_seq, half = self.wire()
            tcp.send(half[:7])
            tcp.io.close()
            time.sleep(0.25)
            uart.send(half[7:])
            uart.no_response(half_seq)
            uart.no_response(dns_seq, 1.5)
            self.ping(uart)
            print('PASS half-frame discard, delayed reply isolation and UART fallback')
            if pcan:
                self.can_event(uart, None, pcan)
                print('PASS CAN events restored to UART1')
            if adapter:
                # The old TCP endpoint is closed; only UART1 receives new events.
                uart.frames.clear()
                marker = b'fallback-event\n'
                adapter.write(marker)
                adapter.flush()
                uart.poll(1)
                assert any(f.is_event and f.cmd_code == 0xA4 and marker in f.payload for f in uart.frames)
                self.request(uart, 0xA1, b'', 1)
                print('PASS events restored to UART1')
            tcp = self.connect(stack)
            self.ping(tcp)
            print('PASS TCP reconnect starts clean')
            if pcan:
                self.can_event(tcp, uart, pcan)
                print('PASS CAN events exclusive after TCP reconnect')
            if self.args.cycle_wifi:
                seq, wire = self.wire(0x48, b'\0')
                tcp.send(wire)
                tcp.poll(3)
                assert tcp.closed, 'Wi-Fi leave did not close TCP session'
                self.ping(uart)
                status = self.request(uart, 0x47, b'\0')
                assert status.payload[0] == 0 and status.payload[1] == 0
                print('PASS Wi-Fi offline closes TCP and restores UART1 provisioning')
                if pcan:
                    self.can_event(uart, None, pcan)
                    print('PASS CAN events during Wi-Fi offline')
                ssid = self.args.ssid.encode('utf-8')
                key = b'' if self.args.open_network else os.environ[self.args.key_env].encode('ascii')
                payload = bytes([0, 0, 0 if self.args.open_network else 1, len(ssid), len(key)]) + ssid + key
                assert self.request(uart, 0x46, payload).payload[0] == 0
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    status = self.request(uart, 0x47, b'\0')
                    if status.payload[1] == 3:
                        break
                    time.sleep(0.2)
                else:
                    raise AssertionError('Wi-Fi recovery did not acquire IP')
                tcp = self.connect(stack)
                self.ping(tcp)
                print('PASS Wi-Fi recovery and fresh remote session')
                if pcan:
                    self.can_event(tcp, uart, pcan)
                    print('PASS CAN events exclusive after Wi-Fi recovery')
            else:
                print('SKIP Wi-Fi leave/recovery (provide --cycle-wifi and credentials)')
            if pcan:
                assert self.request(tcp, 0x11, b'', 3).payload[0] == 0
        print('PASS session suite')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uart', required=True)
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=9500)
    parser.add_argument('--event-uart')
    parser.add_argument('--pcan', action='store_true')
    parser.add_argument('--pcan-channel', type=int, choices=range(1, 5), default=1)
    parser.add_argument('--cycle-wifi', action='store_true')
    parser.add_argument('--ssid')
    parser.add_argument('--key-env', default='HEX_TEST_WIFI_KEY')
    parser.add_argument('--open-network', action='store_true')
    args = parser.parse_args()
    if args.cycle_wifi and (not args.ssid or (not args.open_network and args.key_env not in os.environ)):
        parser.error('--cycle-wifi requires --ssid and --key-env, or --open-network')
    SessionTests(args).run()


if __name__ == '__main__':
    main()
