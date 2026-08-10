"""
CANable 2.0 slcan Protocol Wrapper

CANable 2.0 (normaldotcom/canable2-fw) implements a LAWICEL-style slcan
command set with CAN FD extensions. Commands are fire-and-forget (no ACK).

Commands:
  O/C        Open/Close channel
  S0..S9     Nominal bitrate (10k/20k/50k/100k/125k/250k/500k/750k/1M/83.3k)
  Y2/Y5      Data bitrate 2M/5M (CAN FD only)
  M0/M1      Normal/Silent mode
  A0/A1      Disable/Enable auto retransmission
  tIIILDD..  Transmit standard data frame
  TIIIIIIIILDD.. Transmit extended data frame
  rIIIL / RIIIIIIIIL  Remote frames
  dIIILDD..  CAN FD standard (no BRS)
  DIIIIIIIILDD.. CAN FD extended (no BRS)
  bIIILDD..  CAN FD standard (BRS)
  BIIIIIIIILDD.. CAN FD extended (BRS)
  V          Firmware version
  E          Error register

FD DLC map: 0-8 same, 9=12, A=16, B=20, C=24, D=32, E=48, F=64

Received frames are pushed as slcan frame strings (t/T/d/D/b/B/r/R).

Usage:
    from canable_slcan import CanableChannel
    ch = CanableChannel(port='COM6')
    ch.open_channel(baud=500000)
    ch.send(0x123, b'\x01\x02', fd=True)
    msg = ch.recv(timeout=1.0)
    ch.close_channel()
"""

import serial
import time

# Nominal bitrate index -> baud (slcan S-command)
BAUD_INDEX = {
    10000: '0', 20000: '1', 50000: '2', 100000: '3', 125000: '4',
    250000: '5', 500000: '6', 750000: '7', 1000000: '8', 83333: '9',
}

# FD data bitrate index
FD_BAUD_INDEX = {2000000: '2', 5000000: '5'}

# FD DLC (hex nibble) -> actual byte length
FD_DLC_LEN = {9: 12, 0xA: 16, 0xB: 20, 0xC: 24, 0xD: 32, 0xE: 48, 0xF: 64}


class CanableMessage:
    """Parsed CAN message received from canable (or to transmit)."""

    __slots__ = ('id', 'is_extended', 'is_fd', 'is_brs', 'is_rtr',
                 'data', 'dlc')

    def __init__(self, msg_id=0, data=b'', is_extended=False, is_fd=False,
                 is_brs=False, is_rtr=False):
        self.id = msg_id & 0x1FFFFFFF
        self.is_extended = bool(is_extended)
        self.is_fd = bool(is_fd)
        self.is_brs = bool(is_brs)
        self.is_rtr = bool(is_rtr)
        self.data = bytes(data)
        self.dlc = len(self.data)

    @property
    def fd_dlc_code(self) -> int:
        """Return the hex DLC code used on the wire."""
        n = len(self.data)
        if n <= 8:
            return n
        elif n <= 12:
            return 9
        elif n <= 16:
            return 0xA
        elif n <= 20:
            return 0xB
        elif n <= 24:
            return 0xC
        elif n <= 32:
            return 0xD
        elif n <= 48:
            return 0xE
        else:
            return 0xF

    def __repr__(self):
        flags = []
        if self.is_extended:
            flags.append('EXT')
        if self.is_fd:
            flags.append('FD')
        if self.is_brs:
            flags.append('BRS')
        if self.is_rtr:
            flags.append('RTR')
        flag_str = f" [{','.join(flags)}]" if flags else ''
        id_fmt = f"{self.id:08X}" if self.is_extended else f"{self.id:03X}"
        data_str = self.data.hex(' ').upper() if self.data else "(empty)"
        return f"<CAN {id_fmt}{flag_str} L={len(self.data)} {data_str}>"


class CanableChannel:
    """A CANable 2.0 channel driven over slcan serial."""

    def __init__(self, port='COM6', serial_baud=115200):
        self.port = port
        self.serial_baud = serial_baud
        self.ser = None
        self._rx_buf = b''

    # ------------------------------------------------------------------
    # Serial / protocol basics
    # ------------------------------------------------------------------

    def open(self):
        self.ser = serial.Serial(port=self.port, baudrate=self.serial_baud,
                                 timeout=0.05)
        self._rx_buf = b''
        time.sleep(0.2)
        self.ser.reset_input_buffer()

    def close(self):
        try:
            self.cmd_close()
        except Exception:
            pass
        if self.ser and self.ser.is_open:
            self.ser.close()

    def _write(self, cmd: bytes):
        self.ser.write(cmd + b'\r')
        self.ser.flush()

    def cmd(self, command: str):
        """Send a fire-and-forget slcan command."""
        self._write(command.encode('ascii'))

    # ------------------------------------------------------------------
    # Channel lifecycle
    # ------------------------------------------------------------------

    def set_bitrate(self, baud: int):
        idx = BAUD_INDEX.get(baud)
        if idx is None:
            raise ValueError(f'Unsupported nominal bitrate {baud}')
        self.cmd(f'S{idx}')

    def set_data_bitrate(self, data_baud: int):
        idx = FD_BAUD_INDEX.get(data_baud)
        if idx is None:
            raise ValueError(f'Unsupported FD data bitrate {data_baud}')
        self.cmd(f'Y{idx}')

    def set_silent(self, silent: bool):
        self.cmd('M1' if silent else 'M0')

    def set_retransmit(self, enable: bool):
        self.cmd('A1' if enable else 'A0')

    def cmd_open(self):
        self.ser.reset_input_buffer()
        self._rx_buf = b''
        self.cmd('O')

    def cmd_close(self):
        self.cmd('C')

    def get_version(self) -> str:
        self.ser.reset_input_buffer()
        self._write(b'V')
        deadline = time.time() + 1.0
        while time.time() < deadline:
            data = self.ser.read(200)
            if data:
                return data.decode('ascii', errors='replace').strip()
            time.sleep(0.05)
        return ''

    def get_error_register(self) -> int:
        self.ser.reset_input_buffer()
        self._write(b'E')
        deadline = time.time() + 1.0
        while time.time() < deadline:
            data = self.ser.read(200)
            if data:
                txt = data.decode('ascii', errors='replace').strip()
                try:
                    return int(txt, 16)
                except ValueError:
                    return 0
            time.sleep(0.05)
        return 0

    # ------------------------------------------------------------------
    # Transmit
    # ------------------------------------------------------------------

    def send(self, msg_id: int, data=b'', is_extended=False, is_fd=False,
             is_brs=False, is_rtr=False):
        """Encode and transmit a frame over slcan."""
        msg_id &= 0x1FFFFFFF
        if is_rtr:
            if is_extended:
                self.cmd(f'R{msg_id:08X}{len(data):X}')
            else:
                self.cmd(f'r{msg_id:03X}{len(data):X}')
            return

        if is_fd:
            dlc = self._fd_dlc_code(len(data))
            if is_brs:
                prefix = 'B' if is_extended else 'b'
            else:
                prefix = 'D' if is_extended else 'd'
        else:
            dlc = len(data)
            prefix = 'T' if is_extended else 't'

        if is_extended:
            frame = f'{prefix}{msg_id:08X}{dlc:X}'
        else:
            frame = f'{prefix}{msg_id:03X}{dlc:X}'
        frame += data.hex()
        self.cmd(frame)

    @staticmethod
    def _fd_dlc_code(n: int) -> int:
        if n <= 8:
            return n
        for code, length in FD_DLC_LEN.items():
            if n <= length:
                return code
        return 0xF

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    def recv(self, timeout=1.0):
        """Read one CAN message. Returns CanableMessage or None."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            data = self.ser.read(200)
            if data:
                self._rx_buf += data
            # Always attempt to parse buffered frames, even with no new data
            msg = self._parse_buffer()
            if msg:
                return msg
            time.sleep(0.005)
        return None

    def recv_all(self, timeout=0.5, max_count=100):
        msgs = []
        end = time.time() + timeout
        while len(msgs) < max_count and time.time() < end:
            msg = self.recv(timeout=0.05)
            if msg is None:
                break
            msgs.append(msg)
        return msgs

    def _parse_buffer(self):
        """Extract a complete slcan frame from the RX buffer."""
        while len(self._rx_buf) > 0:
            frame = self._extract_frame()
            if frame is None:
                break
            msg = self._decode_frame(frame)
            if msg is not None:
                return msg
        return None

    def _extract_frame(self):
        """Find a complete slcan frame string; return it or None."""
        buf = self._rx_buf
        # slcan frame: first char is type, ends with CR
        if buf[0:1] not in (b't', b'T', b'r', b'R', b'd', b'D', b'b', b'B'):
            # skip garbage byte
            self._rx_buf = buf[1:]
            return None
        # find CR or LF terminator
        end = -1
        for i in range(1, len(buf)):
            if buf[i:i+1] in (b'\r', b'\n'):
                end = i
                break
        if end < 0:
            if len(buf) > 40:  # malformed, drop first byte
                self._rx_buf = buf[1:]
                return None
            return None  # wait for more
        frame = buf[:end]
        self._rx_buf = buf[end+1:]
        return frame

    def _decode_frame(self, frame: bytes):
        """Decode an slcan frame byte-string into CanableMessage."""
        try:
            txt = frame.decode('ascii')
        except UnicodeDecodeError:
            return None
        if not txt:
            return None
        c = txt[0]
        if c in 'tTrRdDbB':
            msg_id = int(txt[1:4], 16) if c in 'trdb' else int(txt[1:9], 16)
            dlc_code = int(txt[4] if c in 'trdb' else txt[9], 16)
            if c in 'rR':
                data = b''
            else:
                data = bytes.fromhex(txt[5:] if c in 'trdb' else txt[10:])
                # slcan may zero-pad data for FD; trim to actual length
                if c in 'dbDB':
                    actual = FD_DLC_LEN.get(dlc_code, dlc_code)
                    data = data[:actual]
            return CanableMessage(
                msg_id=msg_id,
                data=data,
                is_extended=(c in 'TRDB'),
                is_fd=(c in 'dbDB'),
                is_brs=(c in 'bB'),
                is_rtr=(c in 'rR'),
            )
        return None


if __name__ == '__main__':
    ch = CanableChannel(port='COM6')
    ch.open()
    print('Version:', ch.get_version())
    ch.close()
