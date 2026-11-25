"""One live UBCP session. The reader owns the parser; callers serialize requests."""
import socket
import threading
from collections import deque

import serial

from .codec import UBCPBuilder, UBCPParser


class Link:
    def __init__(self, port, baud, host, tcp_port):
        self.cv = threading.Condition()
        self.events = deque(maxlen=256)
        self.dropped = 0
        self.seq = 0
        self.pending = self.reply = self.error = None
        self.closed = False
        self.sock = self.serial = None
        if host:
            self.sock = socket.create_connection((host, tcp_port), timeout=3)
            self.sock.settimeout(0.25)
        else:
            self.serial = serial.Serial(port, baud, timeout=0.25, write_timeout=3)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        parser = UBCPParser()
        try:
            while not self.closed:
                if self.sock:
                    try:
                        data = self.sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        raise ConnectionError("Device closed the TCP connection")
                else:
                    data = self.serial.read(min(4096, self.serial.in_waiting) or 1)
                for byte in data:
                    if len(parser.buf) > 2062:
                        parser.reset()
                    try:
                        frame = parser.feed(byte)
                    except IndexError:  # truncated timestamp in a malformed frame
                        parser.reset()
                        continue
                    if not frame or frame.version != 2 or len(frame.payload) != frame.payload_len:
                        continue
                    with self.cv:
                        if frame.is_event:
                            if len(self.events) == self.events.maxlen:
                                self.dropped += 1
                            self.events.append(frame)
                        elif frame.is_response and self.pending == (frame.seq_num, frame.cmd_code):
                            self.reply = frame
                        else:
                            continue
                        self.cv.notify_all()
        except (OSError, serial.SerialException) as exc:
            with self.cv:
                self.error = str(exc)
                self.cv.notify_all()

    def request(self, code, channel, data, timeout):
        with self.cv:
            self.seq = self.seq % 65535 + 1
            self.pending = (self.seq, code)
            self.reply = None
            wire = UBCPBuilder.build_request(self.seq, code, channel, data)
            try:
                if self.sock:
                    self.sock.sendall(wire)
                else:
                    self.serial.write(wire)
                self.cv.wait_for(lambda: self.reply or self.error, timeout)
                if self.reply:
                    return self.reply
                if self.error:
                    raise ConnectionError(self.error)
                raise TimeoutError("UBCP response timeout; device outcome unknown")
            finally:
                self.pending = None

    def next_event(self, timeout):
        with self.cv:
            self.cv.wait_for(lambda: self.events or self.error, timeout)
            if self.error and not self.events:
                raise ConnectionError(self.error)
            lost, self.dropped = self.dropped, 0
            return (self.events.popleft() if self.events else None), lost

    def close(self):
        self.closed = True
        self.reader.join()
        if self.sock:
            self.sock.close()
        else:
            self.serial.close()
