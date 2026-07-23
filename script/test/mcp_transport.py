"""
MCP Transport — Serial port wrapper for HEX-Bridge testing.

Connects to COM35 at 921600 bps for MCP communication.

Usage:
    from mcp_transport import MCPTransport
    transport = MCPTransport()
    transport.open()
    transport.send(build_frame(...))
    frame = transport.recv_frame(timeout=1.0)
"""

import serial
import time
from ubcp_client import UBCPParser


class MCPTransport:
    def __init__(self, port='COM35', baudrate=921600):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.parser = UBCPParser()

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

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

    def send(self, data):
        """Send raw wire bytes."""
        self.ser.write(data)
        self.ser.flush()

    def recv_frame(self, timeout=2.0):
        """Block until a complete frame is parsed or timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            b = self.ser.read(1)
            if not b:
                continue
            frame = self.parser.feed(b[0])
            if frame is not None:
                return frame
        return None

    def recv_response(self, cmd_code=None, seq_num=None, timeout=2.0):
        """Receive next response frame (DIR=true,EVT=false) matching filters."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = self.recv_frame(timeout=0.5)
            if frame is None:
                continue
            if not frame.is_response or frame.is_event:
                continue
            if cmd_code is not None and frame.cmd_code != cmd_code:
                continue
            if seq_num is not None and frame.seq_num != seq_num:
                continue
            return frame
        return None

    def recv_event(self, cmd_code=None, timeout=2.0):
        """Receive next event frame (optional filter by cmd_code)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            frame = self.recv_frame(timeout=0.5)
            if frame is None:
                continue
            if frame.is_event:
                if cmd_code is None or frame.cmd_code == cmd_code:
                    return frame
        return None

    def flush_input(self):
        """Discard any buffered input data."""
        if self.ser:
            self.ser.reset_input_buffer()
        self.parser.reset()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *args):
        self.close()
