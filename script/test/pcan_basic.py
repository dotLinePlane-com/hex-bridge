"""
PCAN Basic DLL Wrapper for PEAK-System PCAN-USB devices.

DLL: files/can-files/win64/PCANBasic.dll

Usage:
    from pcan_basic import PcanChannel, PcanBaudrate, PcanMessage, PcanMessageFD
    ch = PcanChannel(baudrate=PcanBaudrate.PCAN_BD_500K)
    ch.initialize()
    msg = PcanMessage(id=0x123, data=b'\x01\x02\x03')
    ch.write(msg)
    rx = ch.read(timeout_ms=100)
    ch.uninitialize()
"""

import ctypes
import os
import time
from enum import IntEnum


# ── DLL loading ────────────────────────────────────────────────────────────

_DLL_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'files',
                        'can-files', 'win64')
_dll_path = os.path.abspath(os.path.join(_DLL_DIR, 'PCANBasic.dll'))

try:
    _pcan = ctypes.WinDLL(_dll_path)
except Exception as e:
    raise ImportError(
        f"Cannot load PCANBasic.dll from {_dll_path}: {e}"
    ) from e


# ── Constants ──────────────────────────────────────────────────────────────

class PcanHandle(IntEnum):
    """PCAN channel handles."""
    PCAN_NONEBUS       = 0x00
    PCAN_ISABUS1       = 0x21
    PCAN_ISABUS2       = 0x22
    PCAN_ISABUS3       = 0x23
    PCAN_ISABUS4       = 0x24
    PCAN_ISABUS5       = 0x25
    PCAN_ISABUS6       = 0x26
    PCAN_ISABUS7       = 0x27
    PCAN_ISABUS8       = 0x28
    PCAN_DNGBUS1       = 0x31
    PCAN_PCIBUS1       = 0x41
    PCAN_PCIBUS2       = 0x42
    PCAN_PCIBUS3       = 0x43
    PCAN_PCIBUS4       = 0x44
    PCAN_PCIBUS5       = 0x45
    PCAN_PCIBUS6       = 0x46
    PCAN_PCIBUS7       = 0x47
    PCAN_PCIBUS8       = 0x48
    PCAN_USBBUS1       = 0x51
    PCAN_USBBUS2       = 0x52
    PCAN_USBBUS3       = 0x53
    PCAN_USBBUS4       = 0x54
    PCAN_USBBUS5       = 0x55
    PCAN_USBBUS6       = 0x56
    PCAN_USBBUS7       = 0x57
    PCAN_USBBUS8       = 0x58
    PCAN_USBBUS9       = 0x509
    PCAN_USBBUS10      = 0x50A
    PCAN_USBBUS11      = 0x50B
    PCAN_USBBUS12      = 0x50C
    PCAN_USBBUS13      = 0x50D
    PCAN_USBBUS14      = 0x50E
    PCAN_USBBUS15      = 0x50F
    PCAN_USBBUS16      = 0x510
    PCAN_LANBUS1       = 0x801
    PCAN_LANBUS2       = 0x802


class PcanBaudrate(IntEnum):
    """Canonical baud rate constants for CAN 2.0."""
    PCAN_BD_1M         = 0x0014  # 1    MBit/s
    PCAN_BD_800K       = 0x0016  # 800  kBit/s
    PCAN_BD_500K       = 0x001C  # 500  kBit/s
    PCAN_BD_250K       = 0x011C  # 250  kBit/s
    PCAN_BD_125K       = 0x031C  # 125  kBit/s
    PCAN_BD_100K       = 0x432F  # 100  kBit/s
    PCAN_BD_95K        = 0xC34E  # 95.2 kBit/s
    PCAN_BD_83K        = 0x852B  # 83.3 kBit/s
    PCAN_BD_50K        = 0x472F  # 50   kBit/s
    PCAN_BD_47K        = 0x1414  # 47.6 kBit/s
    PCAN_BD_33K        = 0x4B2F  # 33.3 kBit/s
    PCAN_BD_20K        = 0x532F  # 20   kBit/s
    PCAN_BD_10K        = 0x672F  # 10   kBit/s
    PCAN_BD_5K         = 0x7F7F  # 5    kBit/s


# FD-specific baud rate (used with CAN_InitializeFD)
PCAN_BR_CLOCK_20MHZ   = 0
PCAN_BR_CLOCK_40MHZ   = 1
PCAN_BR_CLOCK_80MHZ   = 2


class PcanMessageType(IntEnum):
    """Message type flags."""
    PCAN_MESSAGE_STANDARD  = 0x00  # Standard  11-bit
    PCAN_MESSAGE_RTR       = 0x01  # Remote request
    PCAN_MESSAGE_EXTENDED  = 0x02  # Extended  29-bit
    PCAN_MESSAGE_FD        = 0x04  # CAN FD frame (64 bytes max)
    PCAN_MESSAGE_BRS       = 0x08  # FD with bit rate switch
    PCAN_MESSAGE_ESI       = 0x10  # Error State Indicator
    PCAN_MESSAGE_ERRFRAME  = 0x40  # Error frame
    PCAN_MESSAGE_STATUS    = 0x80  # Status frame


class PcanStatus(IntEnum):
    """Return status codes."""
    PCAN_ERROR_OK          = 0x00000
    PCAN_ERROR_XMTFULL     = 0x00001
    PCAN_ERROR_OVERRUN     = 0x00002
    PCAN_ERROR_BUSLIGHT    = 0x00004
    PCAN_ERROR_BUSHEAVY    = 0x00008
    PCAN_ERROR_BUSOFF      = 0x00010
    PCAN_ERROR_QRCVEMPTY   = 0x00020
    PCAN_ERROR_QOVERRUN    = 0x00040
    PCAN_ERROR_QXMTFULL    = 0x00080
    PCAN_ERROR_REGTEST     = 0x00100
    PCAN_ERROR_NODRIVER    = 0x00200
    PCAN_ERROR_HWINUSE     = 0x00400
    PCAN_ERROR_NETINUSE    = 0x00800
    PCAN_ERROR_ILLHW       = 0x01400
    PCAN_ERROR_ILLNET      = 0x01800
    PCAN_ERROR_ILLCLIENT   = 0x01C00
    PCAN_ERROR_ILLHANDLE   = 0x02000
    PCAN_ERROR_RESOURCE    = 0x04000
    PCAN_ERROR_ILLPARAMTYPE = 0x08000
    PCAN_ERROR_ILLPARAMVAL = 0x10000
    PCAN_ERROR_ILLDATA     = 0x20000
    PCAN_ERROR_ILLMODE     = 0x40000
    PCAN_ERROR_CAUTION     = 0x80000
    PCAN_ERROR_INITIALIZE  = 0x100000
    PCAN_ERROR_ILLOPERATION = 0x200000


class PcanParameter(IntEnum):
    """PCAN parameters for SetValue/GetValue."""
    PCAN_DEVICE_NUMBER            = 0x01
    PCAN_5VOLTS_POWER             = 0x02
    PCAN_RECEIVE_EVENT            = 0x03
    PCAN_MESSAGE_FILTER           = 0x04
    PCAN_API_VERSION              = 0x05
    PCAN_CHANNEL_VERSION          = 0x06
    PCAN_BUSOFF_AUTORESET         = 0x07
    PCAN_LISTEN_ONLY              = 0x08
    PCAN_LOG_LOCATION             = 0x09
    PCAN_LOG_STATUS               = 0x0A
    PCAN_LOG_CONFIGURE            = 0x0B
    PCAN_LOG_TEXT                 = 0x0C
    PCAN_CHANNEL_CONDITION        = 0x0D
    PCAN_HARDWARE_NAME            = 0x0E
    PCAN_RECEIVE_STATUS           = 0x0F
    PCAN_CONTROLLER_NUMBER        = 0x10
    PCAN_TRACE_LOCATION           = 0x11
    PCAN_TRACE_STATUS             = 0x12
    PCAN_TRACE_SIZE               = 0x13
    PCAN_TRACE_CONFIGURE          = 0x14
    PCAN_CHANNEL_IDENTIFYING      = 0x15
    PCAN_CHANNEL_FEATURES         = 0x16
    PCAN_BITRATE_ADAPTING         = 0x17
    PCAN_BITRATE_INFO             = 0x18
    PCAN_BITRATE_INFO_FD          = 0x19
    PCAN_BUSSPEED_NOMINAL         = 0x1A
    PCAN_BUSSPEED_DATA            = 0x1B
    PCAN_IP_ADDRESS               = 0x1C
    PCAN_LAN_SERVICE_STATUS       = 0x1D
    PCAN_ALLOW_STATUS_FRAMES      = 0x1E
    PCAN_ALLOW_RTR_FRAMES         = 0x1F
    PCAN_ALLOW_ERROR_FRAMES       = 0x20
    PCAN_INTERFRAME_DELAY         = 0x21
    PCAN_ACCEPTANCE_FILTER_11BIT  = 0x22
    PCAN_ACCEPTANCE_FILTER_29BIT  = 0x23
    PCAN_IO_DIGITAL_CONFIGURATION = 0x24
    PCAN_IO_DIGITAL_VALUE         = 0x25
    PCAN_IO_DIGITAL_SET           = 0x26
    PCAN_IO_DIGITAL_CLEAR         = 0x27
    PCAN_IO_ANALOG_VALUE          = 0x28
    PCAN_FIRMWARE_VERSION         = 0x29
    PCAN_ATTACHED_CHANNELS_COUNT  = 0x2A
    PCAN_ATTACHED_CHANNELS        = 0x2B


class PcanFilterMode(IntEnum):
    """PCAN filter mode."""
    PCAN_FILTER_CLOSE = 0x00
    PCAN_FILTER_OPEN  = 0x01
    PCAN_FILTER_CUSTOM = 0x02


# ── ctypes Structures ──────────────────────────────────────────────────────

class TPCANMsg(ctypes.Structure):
    """Standard CAN 2.0 message (max 8 bytes data)."""
    _fields_ = [
        ("ID",      ctypes.c_uint32),
        ("MSGTYPE", ctypes.c_ubyte),
        ("LEN",     ctypes.c_ubyte),
        ("DATA",    ctypes.c_ubyte * 8),
    ]


class TPCANTimestamp(ctypes.Structure):
    """Timestamp returned with CAN_Read."""
    _fields_ = [
        ("millis",          ctypes.c_uint32),
        ("millis_overflow", ctypes.c_uint16),
        ("micros",          ctypes.c_uint16),
    ]


class TPCANMsgFD(ctypes.Structure):
    """CAN FD message (max 64 bytes data)."""
    _fields_ = [
        ("ID",      ctypes.c_uint32),
        ("DLC",     ctypes.c_uint16),
        ("MSGTYPE", ctypes.c_ubyte),
        ("DATA",    ctypes.c_ubyte * 64),
    ]


# ── Function Signatures ────────────────────────────────────────────────────

_pcan.CAN_Initialize.restype = ctypes.c_uint32
_pcan.CAN_Initialize.argtypes = [
    ctypes.c_uint16,  # Channel
    ctypes.c_uint16,  # Btr0Btr1
    ctypes.c_uint32,  # HwType (0 = auto)
    ctypes.c_uint32,  # IOPort (0)
    ctypes.c_uint16,  # Interrupt (0)
]

_pcan.CAN_InitializeFD.restype = ctypes.c_uint32
_pcan.CAN_InitializeFD.argtypes = [
    ctypes.c_uint16,  # Channel
    ctypes.c_char_p,  # BitrateFD string (e.g. b"f_clock_mhz=20,...")
]

_pcan.CAN_Uninitialize.restype = ctypes.c_uint32
_pcan.CAN_Uninitialize.argtypes = [ctypes.c_uint16]

_pcan.CAN_Write.restype = ctypes.c_uint32
_pcan.CAN_Write.argtypes = [ctypes.c_uint16, ctypes.POINTER(TPCANMsg)]

_pcan.CAN_WriteFD.restype = ctypes.c_uint32
_pcan.CAN_WriteFD.argtypes = [ctypes.c_uint16, ctypes.POINTER(TPCANMsgFD)]

_pcan.CAN_Read.restype = ctypes.c_uint32
_pcan.CAN_Read.argtypes = [
    ctypes.c_uint16,
    ctypes.POINTER(TPCANMsg),
    ctypes.POINTER(TPCANTimestamp),
]

_pcan.CAN_ReadFD.restype = ctypes.c_uint32
_pcan.CAN_ReadFD.argtypes = [
    ctypes.c_uint16,
    ctypes.POINTER(TPCANMsgFD),
    ctypes.POINTER(TPCANTimestamp),
]

_pcan.CAN_GetStatus.restype = ctypes.c_uint32
_pcan.CAN_GetStatus.argtypes = [ctypes.c_uint16]

_pcan.CAN_SetValue.restype = ctypes.c_uint32
_pcan.CAN_SetValue.argtypes = [
    ctypes.c_uint16,     # Channel
    ctypes.c_ubyte,      # Parameter
    ctypes.c_void_p,     # Buffer
    ctypes.c_uint32,     # BufferLength
]

_pcan.CAN_GetValue.restype = ctypes.c_uint32
_pcan.CAN_GetValue.argtypes = [
    ctypes.c_uint16,
    ctypes.c_ubyte,
    ctypes.c_void_p,
    ctypes.c_uint32,
]

_pcan.CAN_GetErrorText.restype = ctypes.c_uint32
_pcan.CAN_GetErrorText.argtypes = [
    ctypes.c_uint32,       # Error code
    ctypes.c_uint16,       # Language (0 = neutral)
    ctypes.c_char_p,       # Buffer
]

_pcan.CAN_SetValueFD.restype = ctypes.c_uint32
_pcan.CAN_SetValueFD.argtypes = [
    ctypes.c_uint16,
    ctypes.c_ubyte,
    ctypes.c_void_p,
    ctypes.c_uint32,
]

_pcan.CAN_GetValueFD.restype = ctypes.c_uint32
_pcan.CAN_GetValueFD.argtypes = [
    ctypes.c_uint16,
    ctypes.c_ubyte,
    ctypes.c_void_p,
    ctypes.c_uint32,
]

_pcan.CAN_FilterMessages.restype = ctypes.c_uint32
_pcan.CAN_FilterMessages.argtypes = [
    ctypes.c_uint16,       # Channel
    ctypes.c_uint32,       # FromID
    ctypes.c_uint32,       # ToID
    ctypes.c_uint32,       # Mode (0=close, 1=open, 2=custom)
]


# ── High-Level Wrapper ─────────────────────────────────────────────────────

STATUS_MESSAGES = {
    0x00000: "OK",
    0x00001: "XMTFULL",
    0x00002: "OVERRUN",
    0x00004: "BUSLIGHT",
    0x00008: "BUSHEAVY",
    0x00010: "BUSOFF",
    0x00020: "QRCVEMPTY",
    0x00040: "QOVERRUN",
    0x00080: "QXMTFULL",
    0x00200: "NODRIVER",
    0x00400: "HWINUSE",
    0x00800: "NETINUSE",
    0x01400: "ILLHW",
    0x01800: "ILLNET",
    0x01C00: "ILLCLIENT",
    0x02000: "ILLHANDLE",
    0x04000: "RESOURCE",
    0x08000: "ILLPARAMTYPE",
    0x10000: "ILLPARAMVAL",
    0x20000: "ILLDATA",
    0x40000: "ILLMODE",
    0x80000: "CAUTION",
    0x100000: "INITIALIZE",
    0x200000: "ILLOPERATION",
}


def status_name(status: int) -> str:
    return STATUS_MESSAGES.get(status, f"UNKNOWN(0x{status:X})")


class PcanMessage:
    """High-level CAN 2.0 message (max 8 bytes)."""

    __slots__ = ('id', 'is_extended', 'is_rtr', 'is_fd', 'is_brs',
                 'is_esi', 'data', 'timestamp_us')

    def __init__(self, id=0, data=b'', is_extended=False, is_rtr=False,
                 is_fd=False, is_brs=False, is_esi=False):
        self.id = id & 0x1FFFFFFF
        self.is_extended = bool(is_extended)
        self.is_rtr = bool(is_rtr)
        self.is_fd = bool(is_fd)
        self.is_brs = bool(is_brs)
        self.is_esi = bool(is_esi)
        self.data = bytes(data[:8])
        self.timestamp_us = 0

    @property
    def dlc(self) -> int:
        return len(self.data)

    @property
    def msgtype(self) -> int:
        t = 0
        if self.is_extended:
            t |= PcanMessageType.PCAN_MESSAGE_EXTENDED
        if self.is_rtr:
            t |= PcanMessageType.PCAN_MESSAGE_RTR
        if self.is_fd:
            t |= PcanMessageType.PCAN_MESSAGE_FD
        if self.is_brs:
            t |= PcanMessageType.PCAN_MESSAGE_BRS
        if self.is_esi:
            t |= PcanMessageType.PCAN_MESSAGE_ESI
        return t

    def to_struct(self):
        msg = TPCANMsg()
        msg.ID = self.id
        msg.MSGTYPE = self.msgtype
        msg.LEN = len(self.data)
        for i, b in enumerate(self.data):
            msg.DATA[i] = b
        return msg

    @classmethod
    def from_struct(cls, cmsg: TPCANMsg, ts: TPCANTimestamp = None):
        msg = cls()
        msg.id = cmsg.ID
        msg.is_extended = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_EXTENDED)
        msg.is_rtr = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_RTR)
        msg.is_fd = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_FD)
        msg.is_brs = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_BRS)
        msg.is_esi = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_ESI)
        msg.data = bytes(cmsg.DATA[:cmsg.LEN])
        if ts:
            msg.timestamp_us = (ts.millis * 1000 +
                                ts.millis_overflow * 1000 * 0x10000 +
                                ts.micros)
        return msg

    def __repr__(self):
        id_fmt = f"{self.id:08X}" if self.is_extended else f"{self.id:03X}"
        flags = []
        if self.is_extended:
            flags.append("EXT")
        if self.is_rtr:
            flags.append("RTR")
        if self.is_fd:
            flags.append("FD")
        if self.is_brs:
            flags.append("BRS")
        if self.is_esi:
            flags.append("ESI")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        data_str = self.data.hex(' ').upper() if self.data else "(empty)"
        ts_str = f" @{self.timestamp_us}us" if self.timestamp_us else ""
        return (f"<CAN {id_fmt}{flag_str} L={len(self.data)}"
                f"   {data_str}{ts_str}>")


class PcanMessageFD:
    """High-level CAN FD message (max 64 bytes)."""

    __slots__ = ('id', 'is_extended', 'is_fd', 'is_brs', 'is_esi',
                 'data', 'timestamp_us')

    def __init__(self, id=0, data=b'', is_extended=False, is_brs=False,
                 is_esi=False):
        self.id = id & 0x1FFFFFFF
        self.is_extended = bool(is_extended)
        self.is_fd = True
        self.is_brs = bool(is_brs)
        self.is_esi = bool(is_esi)
        self.data = bytes(data[:64])
        self.timestamp_us = 0

    @property
    def dlc(self) -> int:
        """Return actual DLC byte count including FD encoding."""
        n = len(self.data)
        if n <= 8:
            return n
        elif n <= 12:
            return 9
        elif n <= 16:
            return 10
        elif n <= 20:
            return 11
        elif n <= 24:
            return 12
        elif n <= 32:
            return 13
        elif n <= 48:
            return 14
        return 15

    @staticmethod
    def dlc_to_len(dlc: int) -> int:
        """Map FD DLC value to actual byte count."""
        if dlc <= 8:
            return dlc
        return [0, 0, 0, 0, 0, 0, 0, 0, 0,
                12, 16, 20, 24, 32, 48, 64][dlc]

    @property
    def msgtype(self) -> int:
        t = PcanMessageType.PCAN_MESSAGE_FD
        if self.is_extended:
            t |= PcanMessageType.PCAN_MESSAGE_EXTENDED
        if self.is_brs:
            t |= PcanMessageType.PCAN_MESSAGE_BRS
        if self.is_esi:
            t |= PcanMessageType.PCAN_MESSAGE_ESI
        return t

    def to_struct(self):
        msg = TPCANMsgFD()
        msg.ID = self.id
        msg.DLC = self.dlc
        msg.MSGTYPE = self.msgtype
        for i, b in enumerate(self.data):
            msg.DATA[i] = b
        return msg

    @classmethod
    def from_struct(cls, cmsg: TPCANMsgFD, ts: TPCANTimestamp = None):
        msg = cls()
        msg.id = cmsg.ID
        msg.is_extended = bool(
            cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_EXTENDED)
        msg.is_brs = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_BRS)
        msg.is_esi = bool(cmsg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_ESI)
        actual_len = PcanMessageFD.dlc_to_len(cmsg.DLC)
        raw = bytes(cmsg.DATA[:actual_len])
        msg.data = raw
        if ts:
            msg.timestamp_us = (ts.millis * 1000 +
                                ts.millis_overflow * 1000 * 0x10000 +
                                ts.micros)
        return msg

    def __repr__(self):
        id_fmt = f"{self.id:08X}" if self.is_extended else f"{self.id:03X}"
        flags = []
        if self.is_extended:
            flags.append("EXT")
        if self.is_brs:
            flags.append("BRS")
        if self.is_esi:
            flags.append("ESI")
        flag_str = f" [{','.join(flags)}]" if flags else ""
        data_str = self.data.hex(' ').upper() if self.data else "(empty)"
        ts_str = f" @{self.timestamp_us}us" if self.timestamp_us else ""
        return (f"<CANFD {id_fmt}{flag_str} L={len(self.data)}"
                f"   {data_str}{ts_str}>")


class PcanChannel:
    """A single PCAN channel with Pythonic interface."""

    def __init__(self, channel=PcanHandle.PCAN_USBBUS1,
                 baudrate=PcanBaudrate.PCAN_BD_500K,
                 hw_type=0, io_port=0, interrupt=0):
        self._channel = channel
        self._baudrate = baudrate
        self._hw_type = hw_type
        self._io_port = io_port
        self._interrupt = interrupt
        self._initialized = False

    @property
    def channel_id(self):
        return self._channel

    def initialize(self) -> int:
        """Initialize the PCAN channel. Returns status code."""
        if self._initialized:
            return 0
        status = _pcan.CAN_Initialize(
            self._channel, self._baudrate,
            self._hw_type, self._io_port, self._interrupt
        )
        if status == PcanStatus.PCAN_ERROR_OK:
            self._initialized = True
        return status

    def initialize_fd(self, bitrate_str: str) -> int:
        """Initialize PCAN channel for CAN FD with custom bitrate string.

        bitrate_str e.g.: b"f_clock_mhz=20, nom_brp=2, nom_tseg1=13, ..."
        """
        if self._initialized:
            return 0
        status = _pcan.CAN_InitializeFD(
            self._channel,
            ctypes.create_string_buffer(bitrate_str.encode('ascii'))
        )
        if status == PcanStatus.PCAN_ERROR_OK:
            self._initialized = True
        return status

    def uninitialize(self) -> int:
        if not self._initialized:
            return 0
        status = _pcan.CAN_Uninitialize(self._channel)
        if status == PcanStatus.PCAN_ERROR_OK:
            self._initialized = False
        return status

    def write(self, msg) -> int:
        """Write a CAN/CAN FD message. Returns status code."""
        if isinstance(msg, PcanMessageFD):
            cmsg = msg.to_struct()
            return _pcan.CAN_WriteFD(self._channel, ctypes.byref(cmsg))
        else:
            cmsg = msg.to_struct()
            return _pcan.CAN_Write(self._channel, ctypes.byref(cmsg))

    def read(self, timeout_ms=100) -> 'PcanMessage | PcanMessageFD | None':
        """Read a message. Returns None if no message available within timeout."""
        msg = TPCANMsg()
        ts = TPCANTimestamp()
        if timeout_ms > 0:
            end = time.time() + timeout_ms / 1000.0
            while True:
                status = _pcan.CAN_Read(self._channel,
                                        ctypes.byref(msg),
                                        ctypes.byref(ts))
                if status == PcanStatus.PCAN_ERROR_OK:
                    if msg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_FD:
                        # Read as FD message
                        return self._read_fd(timeout_ms=1)
                    return PcanMessage.from_struct(msg, ts)
                elif status != PcanStatus.PCAN_ERROR_QRCVEMPTY:
                    return None
                if time.time() >= end:
                    return None
                time.sleep(0.001)
        else:
            status = _pcan.CAN_Read(self._channel, ctypes.byref(msg),
                                    ctypes.byref(ts))
            if status == PcanStatus.PCAN_ERROR_OK:
                if msg.MSGTYPE & PcanMessageType.PCAN_MESSAGE_FD:
                    return self._read_fd(timeout_ms=1)
                return PcanMessage.from_struct(msg, ts)
            return None

    def _read_fd(self, timeout_ms=10) -> 'PcanMessageFD | None':
        """Read an FD message (called after detecting FD flag in CAN_Read)."""
        msg_fd = TPCANMsgFD()
        ts = TPCANTimestamp()
        end = time.time() + timeout_ms / 1000.0
        while True:
            status = _pcan.CAN_ReadFD(self._channel, ctypes.byref(msg_fd),
                                      ctypes.byref(ts))
            if status == PcanStatus.PCAN_ERROR_OK:
                return PcanMessageFD.from_struct(msg_fd, ts)
            elif status != PcanStatus.PCAN_ERROR_QRCVEMPTY:
                return None
            if time.time() >= end:
                return None
            time.sleep(0.001)

    def read_all(self, max_count=100, timeout_ms=200) -> list:
        """Read all available messages within timeout."""
        msgs = []
        end = time.time() + timeout_ms / 1000.0
        while len(msgs) < max_count and time.time() < end:
            msg = self.read(timeout_ms=10)
            if msg is None:
                break
            msgs.append(msg)
        return msgs

    def get_status(self) -> int:
        return _pcan.CAN_GetStatus(self._channel)

    def set_value(self, param: PcanParameter, value: int) -> int:
        buf = ctypes.c_uint32(value)
        return _pcan.CAN_SetValue(self._channel, param,
                                  ctypes.byref(buf), ctypes.sizeof(buf))

    def get_value(self, param: PcanParameter) -> tuple:
        """Returns (status, value)."""
        buf = ctypes.c_uint32(0)
        status = _pcan.CAN_GetValue(self._channel, param,
                                    ctypes.byref(buf), ctypes.sizeof(buf))
        return (status, buf.value)

    def set_filter(self, from_id: int, to_id: int,
                   mode=PcanFilterMode.PCAN_FILTER_OPEN) -> int:
        return _pcan.CAN_FilterMessages(self._channel, from_id, to_id, mode)

    def reset(self):
        """Reset the PCAN controller."""
        if self._initialized:
            self.set_value(PcanParameter.PCAN_BUSOFF_AUTORESET, 1)

    def bus_off_recovery(self):
        """Trigger bus-off recovery."""
        self.uninitialize()
        time.sleep(0.1)
        return self.initialize()

    @property
    def is_initialized(self):
        return self._initialized

    @staticmethod
    def error_text(status: int) -> str:
        buf = ctypes.create_string_buffer(256)
        _pcan.CAN_GetErrorText(status, 0, buf)
        return buf.value.decode('ascii', errors='replace')

    def __enter__(self):
        self.initialize()
        return self

    def __exit__(self, *args):
        self.uninitialize()
