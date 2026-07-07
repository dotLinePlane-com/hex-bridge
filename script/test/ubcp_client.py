"""
UBCP v2.0 Protocol Client Library

Features:
- CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF)
- Frame build with byte-stuffing (0x7E/0x7D escape)
- Frame parse with state machine (online de-escape + CRC)

Usage:
    from ubcp_client import UBCPClient
    client = UBCPClient()
    frame = client.build_request(seq=1, cmd=0x00, channel=0, payload=b'')
    result = client.feed(byte)
"""

SOF_0 = 0xAA
SOF_1 = 0x55
EOF   = 0x7E
ESC   = 0x7D
ESC_EOF = 0x5E
ESC_ESC = 0x5D

VERSION = 0x02
FLAG_DIR = 0x80
FLAG_ACK = 0x40
FLAG_TS  = 0x20
FLAG_EVT = 0x10
FLAG_FRAG = 0x08

class Frame:
    __slots__ = ('version', 'flags', 'seq_num', 'cmd_code',
                 'channel_id', 'payload_len', 'timestamp', 'has_timestamp',
                 'payload')

    def __init__(self):
        self.version = VERSION
        self.flags = 0
        self.seq_num = 0
        self.cmd_code = 0
        self.channel_id = 0
        self.payload_len = 0
        self.timestamp = 0
        self.has_timestamp = False
        self.payload = b''

    def __repr__(self):
        dir_str = 'RSP' if (self.flags & FLAG_DIR) else 'REQ'
        evt_str = ' EVT' if (self.flags & FLAG_EVT) else ''
        return (f'<Frame {dir_str}{evt_str} seq={self.seq_num:#06x} '
                f'cmd={self.cmd_code:#04x} ch={self.channel_id:#04x} '
                f'plen={self.payload_len}>')

    @property
    def is_response(self):
        return bool(self.flags & FLAG_DIR)

    @property
    def is_event(self):
        return bool(self.flags & FLAG_EVT)


CRC16_TABLE = [
    0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50A5, 0x60C6, 0x70E7,
    0x8108, 0x9129, 0xA14A, 0xB16B, 0xC18C, 0xD1AD, 0xE1CE, 0xF1EF,
    0x1231, 0x0210, 0x3273, 0x2252, 0x52B5, 0x4294, 0x72F7, 0x62D6,
    0x9339, 0x8318, 0xB37B, 0xA35A, 0xD3BD, 0xC39C, 0xF3FF, 0xE3DE,
    0x2462, 0x3443, 0x0420, 0x1401, 0x64E6, 0x74C7, 0x44A4, 0x5485,
    0xA56A, 0xB54B, 0x8528, 0x9509, 0xE5EE, 0xF5CF, 0xC5AC, 0xD58D,
    0x3653, 0x2672, 0x1611, 0x0630, 0x76D7, 0x66F6, 0x5695, 0x46B4,
    0xB75B, 0xA77A, 0x9719, 0x8738, 0xF7DF, 0xE7FE, 0xD79D, 0xC7BC,
    0x4864, 0x5845, 0x6826, 0x7807, 0x08E0, 0x18C1, 0x28A2, 0x38A3,
    0xC94C, 0xD96D, 0xE90E, 0xF92F, 0x89C8, 0x99E9, 0xA98A, 0xB9AB,
    0x5A75, 0x4A54, 0x7A37, 0x6A16, 0x1AF1, 0x0AD0, 0x3AB3, 0x2A92,
    0xDB7D, 0xCB5C, 0xFB3F, 0xEB1E, 0x9BF9, 0x8BD8, 0xBBBB, 0xAB9A,
    0x6CA6, 0x7C87, 0x4CE4, 0x5CC5, 0x2C22, 0x3C03, 0x0C60, 0x1C41,
    0xEDAE, 0xFD8F, 0xCDEC, 0xDDCD, 0xAD2A, 0xBD0B, 0x8D68, 0x9D49,
    0x7E97, 0x6EB6, 0x5ED5, 0x4EF4, 0x3E13, 0x2E32, 0x1E51, 0x0E70,
    0xFF9F, 0xEFBE, 0xDFDD, 0xCFFC, 0xBF1B, 0xAF3A, 0x9F59, 0x8F78,
    0x9188, 0x81A9, 0xB1CA, 0xA1EB, 0xD10C, 0xC12D, 0xF14E, 0xE16F,
    0x1080, 0x00A1, 0x30C2, 0x20E3, 0x5004, 0x4025, 0x7046, 0x6067,
    0x83B9, 0x9398, 0xA3FB, 0xB3DA, 0xC33D, 0xD31C, 0xE37F, 0xF35E,
    0x02B1, 0x1290, 0x22F3, 0x32D2, 0x4235, 0x5214, 0x6277, 0x7256,
    0xB5EA, 0xA5CB, 0x95A8, 0x8589, 0xF56E, 0xE54F, 0xD52C, 0xC50D,
    0x34E2, 0x24C3, 0x14A0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405,
    0xA7DB, 0xB7FA, 0x8799, 0x97B8, 0xE75F, 0xF77E, 0xC71D, 0xD73C,
    0x26D3, 0x36F2, 0x0691, 0x16B0, 0x6657, 0x7676, 0x4615, 0x5634,
    0xD94C, 0xC96D, 0xF90E, 0xE92F, 0x99C8, 0x89E9, 0xB98A, 0xA9AB,
    0x5844, 0x4865, 0x7806, 0x6827, 0x18C0, 0x08E1, 0x3882, 0x28A3,
    0xCB7D, 0xDB5C, 0xEB3F, 0xFB1E, 0x8BF9, 0x9BD8, 0xABBB, 0xBBAA,
    0x4A45, 0x5A64, 0x6A07, 0x7A26, 0x0AC1, 0x1AE0, 0x2A83, 0x3AA2,
    0xFD3E, 0xED1F, 0xDD7C, 0xCD5D, 0xBDBA, 0xAD9B, 0x9DF8, 0x8DD9,
    0x7C36, 0x6C17, 0x5C74, 0x4C55, 0x3CB2, 0x2C93, 0x1CF0, 0x0CD1,
    0xEF0F, 0xFF2E, 0xCF4D, 0xDF6C, 0xAF8B, 0xBFAA, 0x8FC9, 0x9FE8,
    0x6E07, 0x7E26, 0x4E45, 0x5E64, 0x2E83, 0x3EA2, 0x0EC1, 0x1EE0,
]


def crc16_update(crc, byte):
    return ((crc << 8) & 0xFFFF) ^ CRC16_TABLE[((crc >> 8) ^ byte) & 0xFF]


def crc16_calc(data):
    crc = 0xFFFF
    for b in data:
        crc = crc16_update(crc, b)
    return crc


class UBCPBuilder:
    """Builds UBCP v2.0 wire frames with CRC and byte-stuffing."""

    @staticmethod
    def build_request(seq_num, cmd_code, channel_id, payload):
        """Build a host-to-device request frame (DIR=0, ACK=1)."""
        return UBCPBuilder._build(
            flags=FLAG_ACK,
            seq_num=seq_num,
            cmd_code=cmd_code,
            channel_id=channel_id,
            payload=payload,
        )

    @staticmethod
    def _build(flags, seq_num, cmd_code, channel_id, payload):
        header = bytes([
            VERSION,
            flags,
            (seq_num >> 8) & 0xFF,
            seq_num & 0xFF,
            cmd_code,
            channel_id,
            (len(payload) >> 8) & 0xFF,
            len(payload) & 0xFF,
        ])
        raw = header + payload
        crc = crc16_calc(raw)
        crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

        wire = bytearray()
        wire.append(SOF_0)
        wire.append(SOF_1)
        UBCPBuilder._write_escaped(wire, raw)
        UBCPBuilder._write_escaped(wire, crc_bytes)
        wire.append(EOF)
        return bytes(wire)

    @staticmethod
    def build_raw_wire(header_and_payload):
        """Build wire frame from pre-assembled header+payload+crc bytes."""
        wire = bytearray()
        wire.append(SOF_0)
        wire.append(SOF_1)
        UBCPBuilder._write_escaped(wire, header_and_payload)
        wire.append(EOF)
        return bytes(wire)

    @staticmethod
    def build_raw_wire_with_crc(version, flags, seq_num, cmd_code,
                                channel_id, payload):
        """Build wire frame with auto-calculated CRC."""
        header = bytes([
            version,
            flags,
            (seq_num >> 8) & 0xFF,
            seq_num & 0xFF,
            cmd_code,
            channel_id,
            (len(payload) >> 8) & 0xFF,
            len(payload) & 0xFF,
        ])
        raw = header + payload
        crc = crc16_calc(raw)
        crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

        wire = bytearray()
        wire.append(SOF_0)
        wire.append(SOF_1)
        UBCPBuilder._write_escaped(wire, raw)
        UBCPBuilder._write_escaped(wire, crc_bytes)
        wire.append(EOF)
        return bytes(wire)

    @staticmethod
    def build_corrupted_crc(seq_num, cmd_code, channel_id, payload):
        """Build a frame with deliberately wrong CRC (last bit flipped)."""
        header = bytes([
            VERSION,
            FLAG_ACK,
            (seq_num >> 8) & 0xFF,
            seq_num & 0xFF,
            cmd_code,
            channel_id,
            (len(payload) >> 8) & 0xFF,
            len(payload) & 0xFF,
        ])
        raw = header + payload
        crc = crc16_calc(raw)
        crc ^= 0x0001  # corrupt
        crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

        wire = bytearray()
        wire.append(SOF_0)
        wire.append(SOF_1)
        UBCPBuilder._write_escaped(wire, raw)
        UBCPBuilder._write_escaped(wire, crc_bytes)
        wire.append(EOF)
        return bytes(wire)

    @staticmethod
    def _write_escaped(buf, data):
        for b in data:
            if b == EOF:
                buf.append(ESC)
                buf.append(ESC_EOF)
            elif b == ESC:
                buf.append(ESC)
                buf.append(ESC_ESC)
            else:
                buf.append(b)


class UBCPParser:
    """Streaming UBCP v2.0 frame parser with online de-escaping + CRC."""

    STATE_WAIT_SOF_0 = 0
    STATE_WAIT_SOF_1 = 1
    STATE_RECEIVING = 2

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = self.STATE_WAIT_SOF_0
        self.is_escaped = False
        self.crc = 0xFFFF
        self.buf = bytearray()

    def feed(self, byte):
        """Feed one byte. Returns Frame if complete, None otherwise."""
        if self.state == self.STATE_WAIT_SOF_0:
            if byte == SOF_0:
                self.state = self.STATE_WAIT_SOF_1
            return None

        if self.state == self.STATE_WAIT_SOF_1:
            if byte == SOF_1:
                self.state = self.STATE_RECEIVING
                self.is_escaped = False
                self.crc = 0xFFFF
                self.buf.clear()
            elif byte != SOF_0:
                self.state = self.STATE_WAIT_SOF_0
            return None

        # STATE_RECEIVING
        if not self.is_escaped and byte == EOF:
            if len(self.buf) < 10:
                self.reset()
                return None  # too short
            if self.crc != 0x0000:
                self.reset()
                return None  # CRC fail
            self.state = self.STATE_WAIT_SOF_0
            return self._extract_frame()

        if self.is_escaped:
            self.is_escaped = False
            if byte == ESC_EOF:
                byte = EOF
            elif byte == ESC_ESC:
                byte = ESC
            else:
                self.reset()
                return None  # bad escape
        elif byte == ESC:
            self.is_escaped = True
            return None

        self.buf.append(byte)
        self.crc = crc16_update(self.crc, byte)
        return None

    def _extract_frame(self):
        f = Frame()
        b = self.buf
        f.version = b[0]
        f.flags = b[1]
        f.seq_num = (b[2] << 8) | b[3]
        f.cmd_code = b[4]
        f.channel_id = b[5]
        f.payload_len = (b[6] << 8) | b[7]

        f.has_timestamp = bool(f.flags & FLAG_TS)
        pl_start = 12 if f.has_timestamp else 8
        if f.has_timestamp:
            f.timestamp = (b[8] << 24) | (b[9] << 16) | (b[10] << 8) | b[11]

        # Last 2 bytes are CRC (already verified)
        pl_end = len(b) - 2
        f.payload = bytes(b[pl_start:pl_end])
        return f
