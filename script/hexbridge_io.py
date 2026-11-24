"""Persistent I2C/GPIO UBCP session shared by the desktop and command line."""
import argparse
import json
import shlex
import struct
import sys
import time
from collections import deque

from hexbridge_profile import Device, MCPTransport, UBCPBuilder, GPIO_TRIGGERS


class BusinessSession:
    """One receive entry point; requests and event polling are serialized by caller."""
    def __init__(self, transport):
        self.transport = transport
        self.device = Device(transport)
        self.events = deque(maxlen=512)
        self.dropped_events = 0
        self.open_buses = {}
        self.connected = True
        self.descriptor = self.device.descriptor()
        self.snapshot = self.device.snapshot()
        self.mapping = self.snapshot['active']
        info_result = self.request(1, 0)
        if info_result['status'] or len(info_result['data']) != 16:
            raise ValueError('Invalid GET_INFO response; hardware identity is unavailable')
        info = info_result['data']
        self.identity = info[3:11].hex()
        topology_result = self.request(7, 0)
        data = topology_result['data']
        if topology_result['status'] or not data or len(data) != 1 + 2 * data[0]:
            raise ValueError('Invalid topology response')
        self.topology = dict(struct.iter_unpack('BB', data[1:]))

    def disconnect(self):
        # UART device sessions can outlive the host handle. Release the buses
        # we own on a graceful close, without replaying any external transfer.
        for bus in tuple(self.open_buses):
            if not self.connected:
                break
            try:
                self.request(0x31, 8 + int(bus), timeout=0.5)
            except (OSError, ValueError):
                break
        self._abort()

    def _abort(self):
        self.connected = False
        self.open_buses.clear()
        self.events.clear()
        self.transport.close()

    def _receive(self, timeout):
        frame = self.transport.recv_frame(timeout=timeout)
        if frame and frame.is_event:
            if len(self.events) == self.events.maxlen:
                self.dropped_events += 1
            self.events.append(self.decode_event(frame))
        return frame

    def request(self, command, channel, payload=b'', instance=None, timeout=6):
        if not self.connected:
            raise OSError('Disconnected; reconnect and rebuild active mapping')
        self.device.seq = self.device.seq % 65535 + 1
        seq = self.device.seq
        try:
            self.transport.send(UBCPBuilder.build_request(seq, command, channel, payload))
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                frame = self._receive(min(0.2, max(0, deadline - time.monotonic())))
                if frame and frame.is_response and not frame.is_event and frame.cmd_code == command and frame.seq_num == seq and frame.channel_id == channel:
                    if not frame.payload:
                        raise ValueError('Empty business response')
                    return dict(instance=instance, channel=channel, sequence=seq, status=frame.payload[0], status_hex=f'0x{frame.payload[0]:02x}', data=bytes(frame.payload[1:]))
            raise TimeoutError('No response; operation outcome unknown; writes are never retried')
        except (OSError, TimeoutError):
            self._abort()
            raise

    def _channel(self, channel, kind):
        if self.topology.get(channel) != kind:
            raise ValueError('Active channel is unavailable or failed initialization')
        return channel

    def _bus(self, bus):
        bus = str(bus)
        if not self.mapping.get('i2c', {}).get(bus, {}).get('enabled'):
            raise ValueError('I2C controller is disabled in the active mapping')
        return self._channel(8 + int(bus), 4)

    def i2c(self, action, bus=0, addr=0x50, register=b'', data=b'', length=1, addr_bits=7, clock_hz=100000, timeout_ms=1000, start=8, end=0x77):
        channel = self._bus(bus)
        bus = str(bus)
        commands = {'open': 0x30, 'close': 0x31, 'config': 0x32, 'write': 0x33, 'read-reg': 0x34, 'read': 0x34, 'write-read': 0x35, 'scan': 0x36}
        if action not in commands:
            raise ValueError('Unknown I2C operation')
        if action not in ('open', 'close') and bus not in self.open_buses:
            raise ValueError('OPEN this I2C controller in the current session first')
        if action == 'open':
            if addr_bits not in (7, 10):
                raise ValueError('Address width must be 7 or 10')
            payload = bytes((int(addr_bits == 10),))
        elif action == 'close':
            payload = b''
        elif action == 'config':
            if clock_hz not in (100000, 400000) or not 1 <= timeout_ms <= 1000:
                raise ValueError('Unsupported clock or timeout')
            payload = struct.pack('>IH', clock_hz, timeout_ms)
        elif action == 'scan':
            if self.open_buses[bus] != 7 or not 8 <= start <= end <= 0x77:
                raise ValueError('SCAN requires 7-bit addresses in 0x08..0x77')
            payload = bytes((start, end))
        else:
            if not 0 <= addr < 1 << self.open_buses[bus] or len(register) > 4 or not 1 <= length <= 2045:
                raise ValueError('Invalid raw slave address, register prefix or read length')
            if action == 'write-read':
                payload = struct.pack('>HHH', addr, len(data), length) + data
            else:
                payload = struct.pack('>HB', addr, len(register)) + register + struct.pack('>H', len(data) if action == 'write' else length)
                if action == 'write':
                    payload += data
            if len(payload) > 2048:
                raise ValueError('Transfer exceeds single-frame payload')
        result = self.request(commands[action], channel, payload, 'i2c' + bus, timeout=7)
        if result['status'] == 0:
            if action == 'open':
                self.open_buses[bus] = addr_bits
            elif action == 'close':
                self.open_buses.pop(bus, None)
            elif action in ('read', 'read-reg', 'write-read', 'write'):
                response = result['data']
                if len(response) < 2:
                    raise ValueError('Missing transfer length')
                actual = int.from_bytes(response[:2], 'big')
                if action != 'write' and len(response) != 2 + actual:
                    raise ValueError('Invalid transfer length')
                result.update(actual_length=actual, data=response[2:] if action != 'write' else b'')
            elif action == 'scan':
                response = result['data']
                if not response or len(response) != 1 + response[0]:
                    raise ValueError('Invalid SCAN response')
                result['addresses'] = list(response[1:])
                result['addresses_hex'] = [f'0x{value:02x}' for value in response[1:]]
        result['address'] = addr if action not in ('open', 'close', 'config', 'scan') else None
        if result['address'] is not None:
            result['address_hex'] = f'0x{addr:02x}'
        return result

    def line(self, line):
        row = self.mapping.get('gpio_lines', {}).get(str(line))
        if not row or not row['enabled']:
            raise ValueError('GPIO line is disabled in the active mapping')
        pin = row['pin']
        channel = self._channel(10 + int(pin >= 32), 5)
        return row, channel, pin % 32

    def gpio(self, action, line=0, level=0, edge='both', debounce_ms=10):
        row, channel, pin = self.line(line)
        if action == 'read':
            command, payload = 0x82, bytes((pin,))
        elif action == 'write':
            if row['mode'] == 'input' or level not in (0, 1):
                raise ValueError('WRITE requires an output and level 0/1')
            command, payload = 0x81, bytes((pin, level))
        elif action in ('watch', 'unwatch'):
            trigger = GPIO_TRIGGERS.get(edge) if action == 'watch' else 0
            if trigger is None or row['mode'] != 'input' or (trigger and not 1 <= debounce_ms <= 255):
                raise ValueError('Invalid GPIO input subscription')
            command, payload = 0x84, bytes((pin, trigger, debounce_ms if trigger else 0))
        else:
            raise ValueError('Unknown GPIO operation')
        result = self.request(command, channel, payload, 'gpio.' + str(line))
        result.update(line=int(line), pin=row['pin'])
        if action == 'read' and result['status'] == 0:
            if len(result['data']) != 1 or result['data'][0] > 1:
                raise ValueError('Invalid GPIO level response')
            result['level'] = result['data'][0]
        return result

    def plan_write(self, values):
        groups = {}
        for line, level in values.items():
            row, channel, bit = self.line(line)
            if row['mode'] == 'input' or level not in (0, 1):
                raise ValueError('Batch requires output lines and levels 0/1')
            group = groups.setdefault(channel, dict(channel=channel, mask=0, values=0, lines=[]))
            group['mask'] |= 1 << bit
            group['values'] |= level << bit
            group['lines'].append(int(line))
        return list(groups.values())

    def write_many(self, values):
        # Preflight every group before the first external write, then expose each result.
        plan = self.plan_write(values)
        return [self.request(0x86, item['channel'], struct.pack('>II', item['mask'], item['values']), item['lines']) for item in plan]

    def read_many(self, lines):
        groups = {}
        for line in dict.fromkeys(map(str, lines)):
            row, channel, bit = self.line(line)
            groups.setdefault(channel, []).append((int(line), bit, row['pin']))
        results = []
        for channel, group in groups.items():
            mask = 0
            for _, bit, _ in group:
                mask |= 1 << bit
            result = self.request(0x87, channel, struct.pack('>I', mask), [line for line, _, _ in group])
            if result['status'] == 0:
                if len(result['data']) != 8:
                    raise ValueError('Invalid GPIO READ_ALL response')
                levels, directions = struct.unpack('>II', result['data'])
                result['lines'] = [dict(line=line, pin=pin, level=levels >> bit & 1, output=bool(directions >> bit & 1)) for line, bit, pin in group]
            results.append(result)
        return results

    def decode_event(self, frame):
        result = dict(channel=frame.channel_id, command=frame.cmd_code, timestamp=frame.timestamp, data=bytes(frame.payload))
        if frame.cmd_code == 0x85 and len(frame.payload) == 3 and frame.channel_id in (10, 11):
            bit, trigger, level = frame.payload
            pin = bit + (32 if frame.channel_id == 11 else 0)
            line = next((int(key) for key, row in self.mapping.get('gpio_lines', {}).items() if row['enabled'] and row['pin'] == pin), None)
            result.update(line=line, pin=pin, trigger=trigger, level=level)
        result['host_overflow'] = self.dropped_events
        return result

    def poll_events(self, timeout=0.05):
        try:
            self._receive(timeout)
        except OSError:
            self._abort()
            raise
        result = list(self.events)
        self.events.clear()
        return result


def command_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    kinds = parser.add_subparsers(dest='kind', required=True)
    i2c = kinds.add_parser('i2c').add_subparsers(dest='action', required=True)
    for action in ('open', 'close', 'config', 'read-reg', 'read', 'write', 'write-read', 'scan'):
        sub = i2c.add_parser(action)
        sub.add_argument('--bus', type=int, choices=(0, 1), default=0)
        sub.add_argument('--addr', type=lambda v: int(v, 0), default=0x50)
        sub.add_argument('--addr-bits', type=int, choices=(7, 10), default=7)
        sub.add_argument('--reg', default='', help='hex register bytes, in wire order')
        sub.add_argument('--data', default='', help='hex write bytes')
        sub.add_argument('--length', type=int, default=1)
        sub.add_argument('--clock-hz', type=int, default=100000)
        sub.add_argument('--timeout-ms', type=int, default=1000)
        sub.add_argument('--start', type=lambda v: int(v, 0), default=8)
        sub.add_argument('--end', type=lambda v: int(v, 0), default=0x77)
    gpio = kinds.add_parser('gpio').add_subparsers(dest='action', required=True)
    for action in ('read', 'write', 'watch', 'unwatch'):
        sub = gpio.add_parser(action)
        sub.add_argument('--line', type=int, required=True)
        sub.add_argument('--level', type=int, choices=(0, 1), default=0)
        sub.add_argument('--edge', choices=tuple(GPIO_TRIGGERS), default='both')
        sub.add_argument('--debounce-ms', type=int, default=10)
        if action == 'watch':
            sub.add_argument('--seconds', type=float, default=5, help='receive events for this duration before the next command')
    for action in ('plan-write', 'write-many', 'read-many'):
        sub = gpio.add_parser(action)
        sub.add_argument('values', help='JSON line-to-level object, or JSON line list for read-many')
    return parser


def execute(session, words):
    args = vars(command_parser().parse_args(words))
    kind, action = args.pop('kind'), args.pop('action')
    if kind == 'gpio' and action in ('plan-write', 'write-many', 'read-many'):
        data = getattr(session, action.replace('-', '_') if action != 'plan-write' else 'plan_write')(json.loads(args['values']))
        return dict(instance='gpio', status=max((item.get('status', 0) for item in data), default=0), data=data)
    seconds = args.pop('seconds', 0)
    if not 0 <= seconds <= 3600:
        raise ValueError('Watch duration must be 0..3600 seconds')
    if kind == 'i2c':
        args['register'] = bytes.fromhex(args.pop('reg').removeprefix('0x'))
        args['data'] = bytes.fromhex(args['data'].removeprefix('0x'))
    result = getattr(session, kind)(action, **args)
    if seconds and not result['status']:
        deadline = time.monotonic() + seconds
        result['events'] = []
        while time.monotonic() < deadline:
            result['events'].extend(session.poll_events(min(0.1, deadline - time.monotonic())))
    return result


def json_output(value):
    return json.dumps(value, default=lambda v: v.hex() if isinstance(v, bytes) else str(v))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Persistent I2C/GPIO session; stdin accepts one command per line')
    parser.add_argument('--port', default='COM4')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--batch', action='store_true', help='read all commands from stdin on one connection')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    failed = False
    with MCPTransport(args.port, args.baud) as transport:
        session = BusinessSession(transport)
        try:
            commands = (line for line in sys.stdin if line.strip()) if args.batch or not args.command else [shlex.join(args.command)]
            for line in commands:
                try:
                    result = execute(session, shlex.split(line))
                    print(json_output(result), flush=True)
                    failed |= bool(result['status'])
                    for event in session.poll_events(0.01):
                        print(json_output({'event': event}), flush=True)
                except (ValueError, OSError) as exc:
                    print(json.dumps({'error': str(exc)}), flush=True)
                    failed = True
                    if not session.connected:
                        break
        finally:
            session.disconnect()
    return int(failed)
