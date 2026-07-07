"""
MCP24 IPC Bridge — real-time COM24 via serial-monitor MCP tools

与 test_uart_mcp.py 配合使用:
  - 测试脚本只打开 COM35 (pyserial, UBCP)
  - COM24 操作通过文件 IPC 转发给 Kilo
  - Kilo 调用 serial-monitor-mcp_* 工具
  - MCP Serial Monitor UI 实时显示所有 COM24 数据流

IPC 协议:
  请求: %TEMP%/mcp24_req.txt  (JSON, 单行)
  响应: %TEMP%/mcp24_res.txt  (JSON, 单行)
  标记: %TEMP%/mcp24_replay.jsonl  (JSONL, 追加)

当 __MCP24_ACTIVE__=1 时启用 IPC 模式，
否则回退 pyserial 直连 (兼容独立运行)。
"""

import json
import os
import sys
import time
import tempfile


class MCP24IPCBridge:
    """COM24 通过 MCP 工具 IPC 实时操作"""

    REQ_FILE = os.path.join(tempfile.gettempdir(), "mcp24_req.txt")
    RES_FILE = os.path.join(tempfile.gettempdir(), "mcp24_res.txt")
    LOG_FILE = os.path.join(tempfile.gettempdir(), "mcp24_replay.jsonl")

    def __init__(self, port="COM24", baud=115200):
        self.port = port
        self.baud = baud
        self._id = 0
        self._ser = None
        self._is_active = os.environ.get("__MCP24_ACTIVE__") == "1"

        self._clear_files()
        self._init_log()

        if self._is_active:
            print(f"[MCP24] IPC bridge mode (Kilo -> MCP tools)", file=sys.stderr)
            # Request Kilo to open COM24 via MCP
            r = self._ipc("mcp_open", {"port": port, "baudRate": baud})
            if r and r.get("ok"):
                print(f"[MCP24] COM24 opened via MCP", file=sys.stderr)
        else:
            print("[MCP24] pyserial fallback (standalone mode)", file=sys.stderr)
            try:
                import serial
                self._ser = serial.Serial(
                    port=port, baudrate=baud,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1,
                )
                self._ser.flushInput()
            except Exception as e:
                print(f"[MCP24] pyserial FAIL: {e}", file=sys.stderr)

    def _clear_files(self):
        for f in (self.REQ_FILE, self.RES_FILE):
            try: open(f, 'w').close()
            except: pass

    def _init_log(self):
        try: open(self.LOG_FILE, 'w').close()
        except: pass

    def _log(self, action, params=None):
        entry = {"ts": round(time.time(), 3),
                 "action": action, "params": params or {}}
        try:
            with open(self.LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except: pass

    def _ipc(self, action, params=None):
        """发送 IPC 请求给 Kilo，阻塞等待响应"""
        self._id += 1
        req = {"id": self._id, "action": action, "params": params or {}}
        try:
            with open(self.REQ_FILE, 'w', encoding='utf-8') as f:
                f.write(json.dumps(req, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[MCP24] IPC write error: {e}", file=sys.stderr)
            return None

        deadline = time.time() + 15.0
        while time.time() < deadline:
            try:
                with open(self.RES_FILE, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    result = json.loads(content)
                    self._clear_files()
                    return result
            except (json.JSONDecodeError, OSError):
                pass
            time.sleep(0.05)

        print(f"[MCP24] IPC timeout: {action}", file=sys.stderr)
        return None

    # ── Public API (same as pyserial) ──

    def write(self, data):
        """向 COM24 发送数据 (通过 Kilo MCP 工具)"""
        hex_str = data.hex() if isinstance(data, bytes) else data
        self._log("send", {"data": hex_str, "format": "hex"})
        if self._is_active:
            self._ipc("mcp_send", {"data": hex_str, "format": "hex"})
            return len(data)
        elif self._ser:
            try:
                n = self._ser.write(data)
                self._ser.flush()
                return n
            except: return 0
        return 0

    def flush(self):
        if self._ser:
            self._ser.flush()

    def read(self, size=1):
        if self._ser:
            b = self._ser.read(size)
            if b: self._log("read", {"data": b.hex()})
            return b
        return b''

    @property
    def in_waiting(self):
        if self._ser: return self._ser.in_waiting
        return 0

    def flushInput(self):
        if self._ser: self._ser.flushInput()

    def close(self):
        self._log("close", {})
        if self._is_active:
            self._ipc("mcp_close", {"port": self.port})
        elif self._ser:
            self._ser.close()
            self._ser = None

    def marker(self, text):
        """记录标记到重放日志并通过 MCP 工具显示"""
        self._log("marker", {"text": text})
        if self._is_active:
            # Also send as readable text on COM24 via MCP
            self._ipc("mcp_marker", {"text": text})
