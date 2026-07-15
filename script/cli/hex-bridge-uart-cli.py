#!/usr/bin/env python3
"""
hex-bridge-uart-cli.py — HEX-Bridge UART 扩展口 CLI 工具

通过 MCP 通信口 (UART1, 默认 COM35 @ 921600 bps) 发送 UBCP v2.0 协议命令，
控制 ESP32 上的 UART2 扩展口 (GPIO32/GPIO35)，实现远程串口收发。

============================================================================
使用示例 (Usage Examples)
============================================================================

  # 1. 安装依赖
  #    pip install pyserial

  # 2. 测试连通性
  #    python hex-bridge-uart-cli.py --port COM35 ping

  # 3. 获取设备信息
  #    python hex-bridge-uart-cli.py --port COM35 info

  # 4. 打开 UART 通道 (被动上报模式)
  #    python hex-bridge-uart-cli.py --port COM35 open --rxmode passive

  # 5. 配置波特率为 115200 8N1
  #    python hex-bridge-uart-cli.py --port COM35 config --baud 115200

  # 6. 发送 hex 数据
  #    python hex-bridge-uart-cli.py --port COM35 send --hex "48 65 6C 6C 6F"

  # 7. 发送字符串
  #    python hex-bridge-uart-cli.py --port COM35 send --text "Hello World\r\n"

  # 8. 持续接收数据 (默认 10 秒)
  #    python hex-bridge-uart-cli.py --port COM35 recv --timeout 10

  # 9. 查看 UART 状态
  #    python hex-bridge-uart-cli.py --port COM35 status

  # 10. 发送 Break 信号 100ms
  #     python hex-bridge-uart-cli.py --port COM35 break --duration 100

  # 11. 清空 RX 缓冲区
  #     python hex-bridge-uart-cli.py --port COM35 flush --type rx

  # 12. 发送数据后等待回显
  #     python hex-bridge-uart-cli.py --port COM35 sendrecv --text "AT\r\n" --timeout 3

  # 13. 一键完整流程 (打开→配置→发送→接收→状态→关闭)
  #     python hex-bridge-uart-cli.py --port COM35 quick --text "ping\r\n" --timeout 3

  # 14. 交互模式
  #     python hex-bridge-uart-cli.py --port COM35 interactive

============================================================================
硬件连接说明
============================================================================

  上位机                    ESP32 HEX-Bridge
  ┌──────┐                  ┌──────────────┐
  │ COM35├──────────────────┤UART1(MCP通信) │  GPIO4(TX), GPIO34(RX)
  │      │   921600 8N1     │              │
  │      │                  │  UART2(扩展口) │  GPIO32(TX), GPIO35(RX)
  │      │                  └──────┬───────┘
  └──────┘                         │
                             ┌─────┴─────┐
                             │  目标设备   │
                             └───────────┘

============================================================================
RxMode 说明
============================================================================

  passive (0x00) — 被动模式：收到数据立即上报
  line    (0x01) — 行模式：  缓冲到 \\n 或 \\r\\n 后上报
  fixed   (0x02) — 定长模式：累积到指定字节数后上报 (需配合 --threshold)
  timeout (0x03) — 超时模式：首字节后空闲超时即上报 (需配合 --rx-timeout)
"""

import argparse
import serial
import struct
import sys
import time

# ============================================================================
# UBCP v2.0 Protocol Constants
# ============================================================================

SOF_0 = 0xAA
SOF_1 = 0x55
EOF_B = 0x7E
ESC = 0x7D
ESC_EOF = 0x5E
ESC_ESC = 0x5D

VERSION = 0x02
FLAG_DIR = 0x80
FLAG_ACK = 0x40
FLAG_TS = 0x20
FLAG_EVT = 0x10
FLAG_FRAG = 0x08

CMD_PING = 0x00
CMD_GET_INFO = 0x01
CMD_FLOW_CONTROL = 0x05
CMD_UART_OPEN = 0xA0
CMD_UART_CLOSE = 0xA1
CMD_UART_CONFIG = 0xA2
CMD_UART_SEND = 0xA3
CMD_UART_RECV = 0xA4
CMD_UART_SET_BREAK = 0xA5
CMD_UART_STATUS = 0xA6
CMD_UART_FLUSH = 0xA7

RXMODE_PASSIVE = 0x00
RXMODE_LINE = 0x01
RXMODE_FIXED = 0x02
RXMODE_TIMEOUT = 0x03

FLUSH_RX = 0x00
FLUSH_TX = 0x01
FLUSH_ALL = 0x02
FLUSH_DRAIN = 0x03

ERR_SUCCESS = 0x00
ERR_PARAM = 0x02
ERR_NOT_OPEN = 0x05
ERR_NOT_SUPPORT = 0x06
ERR_ALREADY_OPEN = 0x0B

ERROR_NAMES = {
    0x00: "SUCCESS", 0x01: "ERR_UNKNOWN", 0x02: "ERR_PARAM",
    0x03: "ERR_TIMEOUT", 0x04: "ERR_BUSY", 0x05: "ERR_NOT_OPEN",
    0x06: "ERR_NOT_SUPPORT", 0x07: "ERR_BUFFER_FULL", 0x08: "ERR_CRC",
    0x09: "ERR_FRAME", 0x0A: "ERR_CHANNEL_INVALID", 0x0B: "ERR_ALREADY_OPEN",
    0x0C: "ERR_PERMISSION", 0x0D: "ERR_OVERFLOW", 0x0E: "ERR_SEQ_MISMATCH",
    0x0F: "ERR_VERSION",
    0xA0: "ERR_UART_PARITY", 0xA1: "ERR_UART_FRAME",
    0xA2: "ERR_UART_OVERFLOW", 0xA3: "ERR_UART_BAUD", 0xA4: "ERR_UART_BREAK",
}

# ============================================================================
# CRC-16/CCITT-FALSE (poly=0x1021, init=0xFFFF)
# ============================================================================

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

# ============================================================================
# UBCP Frame Builder
# ============================================================================

def build_request(seq_num, cmd_code, channel_id, payload):
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
    crc_bytes = bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    wire = bytearray([SOF_0, SOF_1])
    data = raw + crc_bytes
    for b in data:
        if b == EOF_B:
            wire.append(ESC)
            wire.append(ESC_EOF)
        elif b == ESC:
            wire.append(ESC)
            wire.append(ESC_ESC)
        else:
            wire.append(b)
    wire.append(EOF_B)
    return bytes(wire)

# ============================================================================
# UBCP Frame Parser (streaming state machine)
# ============================================================================

STATE_WAIT_SOF_0 = 0
STATE_WAIT_SOF_1 = 1
STATE_RECEIVING = 2

class Frame:
    __slots__ = ('version', 'flags', 'seq_num', 'cmd_code',
                 'channel_id', 'payload_len', 'payload',
                 'is_response', 'is_event')

    def __init__(self):
        self.version = VERSION
        self.flags = 0
        self.seq_num = 0
        self.cmd_code = 0
        self.channel_id = 0
        self.payload_len = 0
        self.payload = b''
        self.is_response = False
        self.is_event = False

class UBCPParser:
    def __init__(self):
        self.reset()

    def reset(self):
        self._state = STATE_WAIT_SOF_0
        self._escaped = False
        self._crc = 0xFFFF
        self._buf = bytearray()

    def feed(self, byte):
        if self._state == STATE_WAIT_SOF_0:
            if byte == SOF_0:
                self._state = STATE_WAIT_SOF_1
            return None

        if self._state == STATE_WAIT_SOF_1:
            if byte == SOF_1:
                self._state = STATE_RECEIVING
                self._escaped = False
                self._crc = 0xFFFF
                self._buf.clear()
            elif byte != SOF_0:
                self._state = STATE_WAIT_SOF_0
            return None

        if not self._escaped and byte == EOF_B:
            if len(self._buf) < 10:
                self.reset()
                return None
            if self._crc != 0x0000:
                self.reset()
                return None
            self._state = STATE_WAIT_SOF_0
            return self._extract_frame()

        if self._escaped:
            self._escaped = False
            if byte == ESC_EOF:
                byte = EOF_B
            elif byte == ESC_ESC:
                byte = ESC
            else:
                self.reset()
                return None
        elif byte == ESC:
            self._escaped = True
            return None

        self._buf.append(byte)
        self._crc = crc16_update(self._crc, byte)
        return None

    def _extract_frame(self):
        f = Frame()
        b = self._buf
        f.version = b[0]
        f.flags = b[1]
        f.seq_num = (b[2] << 8) | b[3]
        f.cmd_code = b[4]
        f.channel_id = b[5]
        f.payload_len = (b[6] << 8) | b[7]

        pl_start = 12 if (f.flags & FLAG_TS) else 8
        pl_end = len(b) - 2
        f.payload = bytes(b[pl_start:pl_end])
        f.is_response = bool(f.flags & FLAG_DIR)
        f.is_event = bool(f.flags & FLAG_EVT)
        return f

# ============================================================================
# Serial Transport
# ============================================================================

class HexBridgeTransport:
    def __init__(self, port, baudrate=921600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.parser = UBCPParser()
        self._pending_event = None
        self._pending_event_cmd = None

    def open(self):
        self.ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=0.05,
        )
        self.parser.reset()
        print(f"[INFO] 已打开 {self.port} @ {self.baudrate} 8N1", file=sys.stderr)

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[INFO] 已关闭 {self.port}", file=sys.stderr)

    def send_sync(self, data):
        self.ser.write(data)
        self.ser.flush()

    def send_request(self, seq_num, cmd_code, channel_id, payload):
        wire = build_request(seq_num, cmd_code, channel_id, payload)
        self.send_sync(wire)

    def recv_frame(self, timeout_s=2.0):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            b = self.ser.read(1)
            if not b:
                continue
            frame = self.parser.feed(b[0])
            if frame is not None:
                return frame
        return None

    def recv_event(self, cmd_code=None, timeout_s=2.0):
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            frame = self.recv_frame(timeout_s=min(0.5, timeout_s))
            if frame is None:
                continue
            if frame.is_event:
                if cmd_code is None or frame.cmd_code == cmd_code:
                    return frame
        return None

    def flush_input(self):
        if self.ser:
            self.ser.reset_input_buffer()
        self.parser.reset()

# ============================================================================
# ProtocoCommands — UART module
# ============================================================================

def cmd_ping(transport, seq, channel):
    transport.send_request(seq, CMD_PING, channel, b'')
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("PING 超时无响应")
    if not resp.is_response:
        raise RuntimeError("PING 响应方向错误")
    return resp

def cmd_get_info(transport, seq, channel):
    transport.send_request(seq, CMD_GET_INFO, channel, b'')
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("GET_INFO 超时无响应")
    if not resp.is_response:
        raise RuntimeError("GET_INFO 响应方向错误")
    return resp

def cmd_uart_open(transport, seq, channel, rx_mode):
    transport.send_request(seq, CMD_UART_OPEN, channel, bytes([rx_mode]))
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_OPEN 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_OPEN 响应方向错误")
    return resp

def cmd_uart_close(transport, seq, channel):
    transport.send_request(seq, CMD_UART_CLOSE, channel, b'')
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_CLOSE 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_CLOSE 响应方向错误")
    return resp

def cmd_uart_config(transport, seq, channel, baud_rate, data_bits, stop_bits,
                    parity, flow_ctrl, rx_threshold, rx_timeout_ms):
    payload = struct.pack('>IBBBBHB', baud_rate, data_bits, stop_bits, parity,
                          flow_ctrl, rx_threshold, rx_timeout_ms)
    transport.send_request(seq, CMD_UART_CONFIG, channel, payload)
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_CONFIG 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_CONFIG 响应方向错误")
    return resp

def cmd_uart_send(transport, seq, channel, data):
    payload = struct.pack('>H', len(data)) + data
    transport.send_request(seq, CMD_UART_SEND, channel, payload)
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_SEND 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_SEND 响应方向错误")
    return resp

def cmd_uart_status(transport, seq, channel):
    transport.send_request(seq, CMD_UART_STATUS, channel, b'')
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_STATUS 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_STATUS 响应方向错误")
    return resp

def cmd_uart_break(transport, seq, channel, duration_ms):
    payload = struct.pack('>H', duration_ms)
    transport.send_request(seq, CMD_UART_SET_BREAK, channel, payload)
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_BREAK 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_BREAK 响应方向错误")
    return resp

def cmd_uart_flush(transport, seq, channel, flush_type):
    transport.send_request(seq, CMD_UART_FLUSH, channel, bytes([flush_type]))
    resp = transport.recv_frame(2.0)
    if not resp:
        raise RuntimeError("UART_FLUSH 超时无响应")
    if not resp.is_response:
        raise RuntimeError("UART_FLUSH 响应方向错误")
    return resp

# ============================================================================
# Response Parsers
# ============================================================================

def parse_status(resp):
    return resp.payload[0] if resp.payload else -1

def parse_open_resp(resp):
    p = resp.payload
    if len(p) < 5:
        return (p[0] if p else -1, 0, 0)
    return (p[0], struct.unpack('>H', p[1:3])[0], struct.unpack('>H', p[3:5])[0])

def parse_config_resp(resp):
    p = resp.payload
    if len(p) < 5:
        return (p[0] if p else -1, 0)
    return (p[0], struct.unpack('>I', p[1:5])[0])

def parse_send_resp(resp):
    p = resp.payload
    if len(p) < 3:
        return (p[0] if p else -1, 0)
    return (p[0], struct.unpack('>H', p[1:3])[0])

def parse_status_resp(resp):
    p = resp.payload
    if len(p) < 19:
        return {"status": p[0] if p else -1}
    return {
        "status": p[0],
        "baud_rate": struct.unpack('>I', p[1:5])[0],
        "line_state": {"tx_idle": bool(p[5] & 0x01), "rx_active": bool(p[5] & 0x02)},
        "tx_buf_used": struct.unpack('>H', p[6:8])[0],
        "rx_buf_used": struct.unpack('>H', p[8:10])[0],
        "tx_total": struct.unpack('>I', p[10:14])[0],
        "rx_total": struct.unpack('>I', p[14:18])[0],
        "error_count": p[18],
    }

def parse_recv_event(frame):
    p = frame.payload
    if len(p) < 3:
        return {"data_len": 0, "data": b""}
    rx_flags = p[0]
    data_len = struct.unpack('>H', p[1:3])[0]
    return {
        "rx_flags": rx_flags,
        "data_len": data_len,
        "data": p[3:3 + data_len],
    }

# ============================================================================
# CLI Helpers
# ============================================================================

def parse_rx_mode(s):
    m = str(s).lower()
    mapping = {"passive": 0, "line": 1, "fixed": 2, "timeout": 3}
    if m in mapping:
        return mapping[m]
    return int(m)

def parse_parity(s):
    if isinstance(s, int):
        return s
    m = str(s).lower()
    mapping = {"none": 0, "odd": 1, "even": 2}
    return mapping.get(m, 0)

def parse_stop_bits(s):
    if s == 1.5 or str(s) == "1.5":
        return 2
    if int(float(s)) == 1:
        return 1
    if int(float(s)) == 2:
        return 3
    return 1

def parse_flush_type(s):
    m = str(s).lower()
    mapping = {"rx": 0, "tx": 1, "all": 2, "drain": 3}
    return mapping.get(m, int(m) if m.isdigit() else 0)

def parse_hex(hex_str):
    cleaned = hex_str.replace(" ", "").replace(",", "").replace(";", "").replace(":", "")
    if len(cleaned) % 2 != 0:
        raise ValueError(f"hex 字符串长度需为偶数: '{hex_str}'")
    return bytes.fromhex(cleaned)

def buffer_to_printable(buf):
    s = ""
    for b in buf:
        if 0x20 <= b <= 0x7E:
            s += chr(b)
        elif b == 0x0A:
            s += "\\n"
        elif b == 0x0D:
            s += "\\r"
        elif b == 0x09:
            s += "\\t"
    return s

def fmt_frame(frame):
    s = "RSP" if frame.is_response else "REQ"
    if frame.is_event:
        s += " EVT"
    return (f"{s} seq=0x{frame.seq_num:04X} cmd=0x{frame.cmd_code:02X} "
            f"ch=0x{frame.channel_id:02X} plen={frame.payload_len}")

def status_name(code):
    return ERROR_NAMES.get(code, f"0x{code:02X}")

def check_status(resp):
    if not resp or not resp.is_response:
        return -1
    status = resp.payload[0]
    name = status_name(status)
    if status != ERR_SUCCESS:
        print(f"[FAIL] {fmt_frame(resp)} status=0x{status:02X} ({name})", file=sys.stderr)
    return status

# ============================================================================
# Argument Parser
# ============================================================================

def build_parser():
    parser = argparse.ArgumentParser(
        description="HEX-Bridge UART 扩展口 CLI 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="更多示例见脚本文件头部注释。",
    )

    parser.add_argument("--port", default="COM35", help="MCP 通信串口 (默认: COM35)")
    parser.add_argument("--mcp-baud", type=int, default=921600, help="MCP 波特率 (默认: 921600)")
    parser.add_argument("--channel", type=int, default=0, help="通道号 (默认: 0)")
    parser.add_argument("--seq", type=int, default=1, dest="seq_start", help="起始序列号 (默认: 1)")
    parser.add_argument("--baud", type=int, default=115200, help="扩展口波特率 (默认: 115200)")
    parser.add_argument("--data-bits", type=int, default=8, choices=[5, 6, 7, 8], help="数据位 (默认: 8)")
    parser.add_argument("--stop-bits", type=float, default=1, choices=[1, 1.5, 2], help="停止位 (默认: 1)")
    parser.add_argument("--parity", default="none", choices=["none", "odd", "even"], help="校验位 (默认: none)")
    parser.add_argument("--rxmode", default="passive", choices=["passive", "line", "fixed", "timeout"],
                        help="接收模式 (默认: passive)")
    parser.add_argument("--threshold", type=int, default=256, help="定长模式阈值 (默认: 256)")
    parser.add_argument("--rx-timeout", type=int, default=50, help="超时模式超时 ms (默认: 50)")

    sub = parser.add_subparsers(dest="command", help="子命令")

    p_ping = sub.add_parser("ping", help="测试设备连通性")

    p_info = sub.add_parser("info", help="获取设备信息")

    p_open = sub.add_parser("open", help="打开 UART 通道")
    p_open.add_argument("--rxmode", default=None, choices=["passive", "line", "fixed", "timeout"],
                        help="接收模式, 覆盖全局设置")
    p_open.add_argument("--threshold", type=int, help="定长阈值")
    p_open.add_argument("--rx-timeout", type=int, help="超时时间")

    p_close = sub.add_parser("close", help="关闭 UART 通道")

    p_config = sub.add_parser("config", help="配置 UART 参数")
    p_config.add_argument("--baud", type=int, dest="cfg_baud", help="波特率 (覆盖全局 --baud)")
    p_config.add_argument("--data-bits", type=int, choices=[5, 6, 7, 8], dest="cfg_data_bits", help="数据位")
    p_config.add_argument("--stop-bits", type=float, choices=[1, 1.5, 2], dest="cfg_stop_bits", help="停止位")
    p_config.add_argument("--parity", choices=["none", "odd", "even"], dest="cfg_parity", help="校验位")

    p_send = sub.add_parser("send", help="发送数据")
    p_send_group = p_send.add_mutually_exclusive_group(required=True)
    p_send_group.add_argument("--hex", help="hex 数据 (如 '48 65 6C 6C 6F')")
    p_send_group.add_argument("--text", help="文本数据")

    p_recv = sub.add_parser("recv", help="接收数据")
    p_recv.add_argument("--timeout", type=float, default=10, help="超时秒数 (默认: 10)")

    p_status = sub.add_parser("status", help="查看 UART 状态")

    p_break = sub.add_parser("break", help="发送 Break 信号")
    p_break.add_argument("--duration", type=int, default=0, help="持续时间 ms (默认: 10)")

    p_flush = sub.add_parser("flush", help="清空缓冲区")
    p_flush.add_argument("--type", default="rx", choices=["rx", "tx", "all", "drain"], help="清空类型 (默认: rx)")

    p_sendrecv = sub.add_parser("sendrecv", help="发送数据后等待回显")
    p_sr_group = p_sendrecv.add_mutually_exclusive_group(required=True)
    p_sr_group.add_argument("--hex", help="hex 数据")
    p_sr_group.add_argument("--text", help="文本数据")
    p_sendrecv.add_argument("--timeout", type=float, default=5, help="等待回显超时秒数 (默认: 5)")

    p_quick = sub.add_parser("quick", help="一键完整流程 (打开→配置→发送→接收→状态→关闭)")
    p_q_group = p_quick.add_mutually_exclusive_group(required=True)
    p_q_group.add_argument("--hex", help="hex 数据")
    p_q_group.add_argument("--text", help="文本数据")
    p_quick.add_argument("--timeout", type=float, default=3, help="等待回显超时秒数 (默认: 3)")

    p_inter = sub.add_parser("interactive", help="交互模式")

    return parser

# ============================================================================
# Command Implementations
# ============================================================================

def cmd_ping_fn(transport, seq, channel, args):
    resp = cmd_ping(transport, seq(), channel)
    status = resp.payload[0]
    print(f"PING {fmt_frame(resp)} status=0x{status:02X}")
    sys.exit(0 if status == 0 else 1)

def cmd_info_fn(transport, seq, channel, args):
    resp = cmd_get_info(transport, seq(), channel)
    p = resp.payload
    if len(p) < 17:
        print(f"GET_INFO 响应过短: {len(p)} 字节", file=sys.stderr)
        sys.exit(1)

    status = p[0]
    fw_ver = f"{p[1]}.{p[2]}.{p[3]}"
    serial = f"{p[4]:02X}{p[5]:02X}{p[6]:02X}{p[7]:02X}"
    model = p[8:12].decode("ascii", errors="replace")
    caps = struct.unpack('>H', p[12:14])[0]
    max_pl = struct.unpack('>H', p[14:16])[0]
    proto_ver = p[16]
    print("=== HEX-Bridge 设备信息 ===")
    print(f"  型号:       {model}")
    print(f"  序列号:     {serial}")
    print(f"  固件版本:   {fw_ver}")
    print(f"  协议版本:   0x{proto_ver:02X}")
    print(f"  最大载荷:   {max_pl} bytes")
    print(f"  能力:       0x{caps:04X}")
    print(f"  MCP 串口:   {transport.port} @ {transport.baudrate}")

def cmd_open_fn(transport, seq, channel, args):
    rx_mode = parse_rx_mode(args.rxmode) if args.rxmode else RXMODE_PASSIVE
    mode_names = ["passive", "line", "fixed", "timeout"]

    resp = cmd_uart_open(transport, seq(), channel, rx_mode)
    status, rx_buf, tx_buf = parse_open_resp(resp)
    name = status_name(status)
    print(f"UART_OPEN 模式={mode_names[rx_mode]} status=0x{status:02X} ({name})")
    print(f"  RX Buffer: {rx_buf} bytes")
    print(f"  TX Buffer: {tx_buf} bytes")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_close_fn(transport, seq, channel, args):
    resp = cmd_uart_close(transport, seq(), channel)
    status = check_status(resp)
    print("UART_CLOSE 通道已关闭")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_config_fn(transport, seq, channel, args):
    baud = args.cfg_baud if getattr(args, 'cfg_baud', None) is not None else args.baud
    db = args.cfg_data_bits if getattr(args, 'cfg_data_bits', None) is not None else args.data_bits
    sb = args.cfg_stop_bits if getattr(args, 'cfg_stop_bits', None) is not None else args.stop_bits
    parity = args.cfg_parity if getattr(args, 'cfg_parity', None) is not None else args.parity

    resp = cmd_uart_config(transport, seq(), channel, baud,
                           db, parse_stop_bits(sb), parse_parity(parity), 0, 256, 50)
    status, actual_baud = parse_config_resp(resp)
    name = status_name(status)
    print(f"UART_CONFIG 请求={baud} 实际={actual_baud} status=0x{status:02X} ({name})")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_send_fn(transport, seq, channel, args):
    if args.hex:
        data = parse_hex(args.hex)
    else:
        data = args.text.encode("utf-8")

    resp = cmd_uart_send(transport, seq(), channel, data)
    status, actual_len = parse_send_resp(resp)
    name = status_name(status)
    print(f"UART_SEND 发送={actual_len}/{len(data)}B hex={data.hex().upper()}")
    if len(data) <= 256:
        print(f"  可打印: {buffer_to_printable(data)}")
    print(f"  status=0x{status:02X} ({name})")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_recv_fn(transport, seq, channel, args):
    timeout_s = args.timeout
    print(f"UART_RECV 等待接收数据 (超时 {timeout_s}s)...")

    frame = transport.recv_event(cmd_code=CMD_UART_RECV, timeout_s=timeout_s)
    if frame is None:
        print("超时未收到数据", file=sys.stderr)
        sys.exit(1)

    info = parse_recv_event(frame)
    print(f"UART_RECV 长度={info['data_len']}")
    print(f"  HEX: {info['data'].hex().upper()}")
    print(f"  可打印: {buffer_to_printable(info['data'])}")

def cmd_status_fn(transport, seq, channel, args):
    resp = cmd_uart_status(transport, seq(), channel)
    s = parse_status_resp(resp)
    name = status_name(s.get("status", -1))
    print("=== UART 状态 ===")
    print(f"  status:      0x{s['status']:02X} ({name})" if "status" in s else "N/A")
    if "baud_rate" in s:
        print(f"  波特率:      {s['baud_rate']}")
        print(f"  TX 空闲:     {'是' if s['line_state']['tx_idle'] else '否'}")
        print(f"  RX 活跃:     {'是' if s['line_state']['rx_active'] else '否'}")
        print(f"  TX buf:      {s['tx_buf_used']} / —")
        print(f"  RX buf:      {s['rx_buf_used']} / —")
        print(f"  TX 总字节:   {s['tx_total']}")
        print(f"  RX 总字节:   {s['rx_total']}")
        print(f"  错误计数:    {s['error_count']}")

def cmd_break_fn(transport, seq, channel, args):
    resp = cmd_uart_break(transport, seq(), channel, args.duration)
    status = check_status(resp)
    print(f"UART_BREAK duration={args.duration or 10}ms status=0x{status:02X}")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_flush_fn(transport, seq, channel, args):
    ftype = parse_flush_type(args.type)
    type_names = ["RX", "TX", "ALL", "DRAIN"]
    resp = cmd_uart_flush(transport, seq(), channel, ftype)
    status = check_status(resp)
    print(f"UART_FLUSH type={type_names[ftype]} status=0x{status:02X}")
    sys.exit(0 if status == ERR_SUCCESS else 1)

def cmd_sendrecv_fn(transport, seq, channel, args):
    if args.hex:
        data = parse_hex(args.hex)
    else:
        data = args.text.encode("utf-8")

    timeout_s = args.timeout

    resp = cmd_uart_send(transport, seq(), channel, data)
    status, actual_len = parse_send_resp(resp)
    if status != ERR_SUCCESS:
        print(f"UART_SEND 失败: status=0x{status:02X} ({status_name(status)})", file=sys.stderr)
        sys.exit(1)
    print(f"SEND {actual_len}B hex={data.hex().upper()}")

    print(f"等待回显 (超时 {timeout_s}s)...")
    frame = transport.recv_event(cmd_code=CMD_UART_RECV, timeout_s=timeout_s)
    if frame is None:
        print("超时未收到回显", file=sys.stderr)
        sys.exit(1)

    info = parse_recv_event(frame)
    print(f"RECV {info['data_len']}B hex={info['data'].hex().upper()}")
    print(f"     可打印: {buffer_to_printable(info['data'])}")

def cmd_quick_fn(transport, seq, channel, args):
    if args.hex:
        data = parse_hex(args.hex)
    else:
        data = args.text.encode("utf-8")

    timeout_s = args.timeout
    rx_mode = parse_rx_mode("passive")

    print(f">>> quick 模式: port={transport.port} channel={channel} baud=115200")

    # 1. OPEN
    resp = cmd_uart_open(transport, seq(), channel, rx_mode)
    status, rx_buf, tx_buf = parse_open_resp(resp)
    if status != ERR_SUCCESS:
        print(f"  打开失败: {status_name(status)}", file=sys.stderr)
        sys.exit(1)
    print(f"  1. OPEN rxBuf={rx_buf} txBuf={tx_buf}")

    # 2. CONFIG
    resp = cmd_uart_config(transport, seq(), channel, 115200, 8, 1, 0, 0, 256, 50)
    status, actual_baud = parse_config_resp(resp)
    if status != ERR_SUCCESS:
        print(f"  配置失败: {status_name(status)}", file=sys.stderr)
        sys.exit(1)
    print(f"  2. CONFIG 115200bps OK (实际={actual_baud})")

    # 3. SEND
    resp = cmd_uart_send(transport, seq(), channel, data)
    status, actual_len = parse_send_resp(resp)
    if status != ERR_SUCCESS:
        print(f"  发送失败: {status_name(status)}", file=sys.stderr)
        sys.exit(1)
    print(f"  3. SEND {actual_len}B -> {data.hex().upper()}")

    # 4. RECV
    print(f"  4. 等待回显 ({timeout_s}s)...")
    frame = transport.recv_event(cmd_code=CMD_UART_RECV, timeout_s=timeout_s)
    if frame is not None:
        info = parse_recv_event(frame)
        print(f"     RECV {info['data_len']}B <- {info['data'].hex().upper()}")
    else:
        print("     (超时，无回显)")

    # 5. STATUS
    resp = cmd_uart_status(transport, seq(), channel)
    s = parse_status_resp(resp)
    print(f"  5. STATUS tx={s.get('tx_total', 0)} rx={s.get('rx_total', 0)} err={s.get('error_count', 0)}")

    # 6. CLOSE
    cmd_uart_close(transport, seq(), channel)
    print("  6. CLOSE OK")

def cmd_interactive_fn(transport, seq, channel, args):
    print("=== HEX-Bridge UART 交互模式 ===")
    print("命令: open [rxmode] | close | config <baud> | send <hex/text>")
    print("      recv [s] | status | break [ms] | flush <type> | quit")
    print()

    def nxt():
        return seq()

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        try:
            if cmd == "quit" or cmd == "exit":
                break
            elif cmd == "open":
                mode = parse_rx_mode(parts[1]) if len(parts) > 1 else RXMODE_PASSIVE
                mode_names = ["passive", "line", "fixed", "timeout"]
                resp = cmd_uart_open(transport, nxt(), channel, mode)
                status, rx_buf, tx_buf = parse_open_resp(resp)
                print(f"OPEN {mode_names[mode]} -> status=0x{status:02X} rxBuf={rx_buf} txBuf={tx_buf}")
            elif cmd == "close":
                cmd_uart_close(transport, nxt(), channel)
                print("CLOSE OK")
            elif cmd == "config":
                baud = int(parts[1]) if len(parts) > 1 else 115200
                resp = cmd_uart_config(transport, nxt(), channel, baud, 8, 1, 0, 0, 256, 50)
                status, actual = parse_config_resp(resp)
                print(f"CONFIG {baud} -> 实际={actual} status=0x{status:02X}")
            elif cmd == "send":
                if len(parts) > 2 and parts[1] == "hex":
                    data = parse_hex(" ".join(parts[2:]))
                else:
                    data = " ".join(parts[1:]).encode("utf-8")
                resp = cmd_uart_send(transport, nxt(), channel, data)
                status, alen = parse_send_resp(resp)
                print(f"SEND {alen}B -> {data.hex().upper()} status=0x{status:02X}")
            elif cmd == "recv":
                timeout = float(parts[1]) if len(parts) > 1 else 10
                print(f"等待数据 ({timeout}s)...")
                frame = transport.recv_event(cmd_code=CMD_UART_RECV, timeout_s=timeout)
                if frame:
                    info = parse_recv_event(frame)
                    print(f"RECV {info['data_len']}B <- {info['data'].hex().upper()}")
                    print(f"     可打印: {buffer_to_printable(info['data'])}")
                else:
                    print("超时")
            elif cmd == "status":
                resp = cmd_uart_status(transport, nxt(), channel)
                s = parse_status_resp(resp)
                print(f"STATUS {s.get('baud_rate', '?')}bps tx={s.get('tx_total', 0)} rx={s.get('rx_total', 0)} err={s.get('error_count', 0)}")
            elif cmd == "break":
                dur = int(parts[1]) if len(parts) > 1 else 0
                cmd_uart_break(transport, nxt(), channel, dur)
                print(f"BREAK {dur or 10}ms")
            elif cmd == "flush":
                ftype = parse_flush_type(parts[1]) if len(parts) > 1 else 0
                names = ["RX", "TX", "ALL", "DRAIN"]
                resp = cmd_uart_flush(transport, nxt(), channel, ftype)
                print(f"FLUSH {names[ftype]} -> status=0x{resp.payload[0]:02X}")
            elif cmd == "info":
                cmd_info_fn(transport, seq, channel, None)
            elif cmd == "ping":
                resp = cmd_ping(transport, nxt(), channel)
                print(f"PING status=0x{resp.payload[0]:02X}")
            elif cmd == "help":
                print("命令: open|close|config|send|recv|status|break|flush|info|ping|quit")
            else:
                print(f"未知命令: {cmd} (输入 help 查看帮助)")
        except Exception as e:
            print(f"错误: {e}", file=sys.stderr)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = build_parser()

    if len(sys.argv) == 1 or sys.argv[1] in ("--help", "-h"):
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    transport = HexBridgeTransport(args.port, args.mcp_baud)
    try:
        transport.open()
    except Exception as e:
        print(f"错误: 无法打开 {args.port}: {e}", file=sys.stderr)
        print("\n请确保:", file=sys.stderr)
        print("  1. 已安装 pyserial: pip install pyserial", file=sys.stderr)
        print("  2. 设备已连接且串口号正确", file=sys.stderr)
        print("  3. 串口未被其他程序占用", file=sys.stderr)
        sys.exit(1)

    seq_num = args.seq_start
    def next_seq():
        nonlocal seq_num
        s = seq_num
        seq_num = (seq_num + 1) & 0xFFFE or 1
        return s

    try:
        commands = {
            "ping":        cmd_ping_fn,
            "info":        cmd_info_fn,
            "open":        cmd_open_fn,
            "close":       cmd_close_fn,
            "config":      cmd_config_fn,
            "send":        cmd_send_fn,
            "recv":        cmd_recv_fn,
            "status":      cmd_status_fn,
            "break":       cmd_break_fn,
            "flush":       cmd_flush_fn,
            "sendrecv":    cmd_sendrecv_fn,
            "quick":       cmd_quick_fn,
            "interactive": cmd_interactive_fn,
        }

        fn = commands.get(args.command)
        if fn:
            fn(transport, next_seq, args.channel, args)
        else:
            print(f"未知命令: {args.command}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        transport.close()


if __name__ == "__main__":
    main()
