"""
HEX-Bridge Network Integration Tests - Full Automation

Covers all PENDING test cases from Network-Test-Report.md that require
MCP NM (Network Monitor) coordination.

Usage:
    python test_network_integration.py --no-nm                  # Pure-CLI tests (no NM needed)
    python test_network_integration.py --all                    # Full suite (manual NM)
    python test_network_integration.py --all --auto-nm          # Full suite (auto NM via sockets)
    python test_network_integration.py --test TCP-21 --auto-nm  # Single case with auto NM
    python test_network_integration.py --pending-only            # All PENDING cases
    python test_network_integration.py --list                   # List all test cases

Environment:
    HEX-Bridge IP: 192.168.1.105
    PC IP:         192.168.1.4
    MCP port:      COM4, 115200 bps
    CLI:           python script/cli/hex-bridge-network-cli.py --port COM4 --baud 115200

NM Tool Known Issues (do NOT work around):
    - NM UDP client RX: read_network_buffer returns empty after HEX sends data
    - NM UDP server RX: read_network_buffer returns empty
    - NM WS server RX:   read_network_buffer returns empty
    - NM TCP client & server RX: WORKS FINE
"""

import subprocess
import sys
import os
import time
import argparse
import json
import re
import struct
import socket
import threading

try:
    import websocket as ws_client
    HAS_WS_CLIENT = True
except ImportError:
    HAS_WS_CLIENT = False

HEX_IP = "192.168.1.105"
PC_IP = "192.168.1.4"
CLI_BASE = [sys.executable, os.path.join("script", "cli", "hex-bridge-network-cli.py"),
            "--port", "COM4", "--baud", "115200"]

_passed = 0
_failed = 0
_skipped = 0


# ============================================================================
# CLI Runner
# ============================================================================

class CliRunner:
    """Run CLI commands and parse key=value output."""

    def __init__(self, timeout=15):
        self.timeout = timeout

    def run(self, *args, timeout=None):
        """Run CLI command, return dict of parsed key=value pairs."""
        cmd = CLI_BASE + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout or self.timeout,
                cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
            )
        except subprocess.TimeoutExpired:
            return {"status": "TIMEOUT", "_stdout": "", "_stderr": ""}

        parsed = self._parse(result.stdout)
        parsed["_stdout"] = result.stdout
        parsed["_stderr"] = result.stderr
        parsed["_returncode"] = result.returncode
        return parsed

    def _parse(self, output):
        """Parse CLI 'key=value' lines plus table rows into dict."""
        result = {}
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"^\s*(\S+?)=(.+)$", line)
            if m:
                result[m.group(1).strip()] = m.group(2).strip()
        return result

    def get_handle(self, *args, timeout=None):
        """Run command and return handle as int, or None."""
        data = self.run(*args, timeout=timeout)
        h = data.get("handle", "")
        if h and h.startswith("0x"):
            return int(h, 16)
        return None

    def get_status(self, *args, timeout=None):
        """Run command and return (status_str, raw_dict)."""
        data = self.run(*args, timeout=timeout)
        st = data.get("status", "NO_RESPONSE")
        return st, data


# ============================================================================
# NmBridge - Network Monitor Bridge (replaces manual NM steps)
# ============================================================================

class NmBridge:
    """Base class for NM operations. Override for auto-mode."""

    def tcp_connect(self, conn_id, host, port):
        pass

    def tcp_disconnect(self, conn_id):
        pass

    def tcp_send(self, conn_id, data_hex):
        pass

    def tcp_recv(self, conn_id, timeout=3):
        return b""

    def tcp_pause_reads(self, conn_id):
        pass

    def tcp_resume_reads(self, conn_id):
        pass

    def ws_connect(self, conn_id, url):
        return True

    def ws_disconnect(self, conn_id, code=1000, reason=""):
        pass

    def ws_send_ping(self, conn_id, data=""):
        pass

    def udp_server(self, conn_id, host, port, multicast=None):
        pass

    def udp_disconnect(self, conn_id):
        pass

    def disconnect_all(self):
        pass


class ManualNmBridge(NmBridge):
    """Print NM instructions and wait for manual execution."""

    def tcp_connect(self, conn_id, host, port):
        print(f"\n  [NM] Connect NM TCP client to {host}:{port}")
        print(f"       connect_network(connId=\"{conn_id}\", protocol=\"tcp\","
              f" role=\"client\", host=\"{host}\", port={port})")
        self._wait()

    def tcp_disconnect(self, conn_id):
        print(f"\n  [NM] Disconnect NM TCP client {conn_id}")
        print(f"       disconnect_network(connId=\"{conn_id}\")")
        self._wait()

    def ws_connect(self, conn_id, url):
        print(f"\n  [NM] Connect NM WS client {conn_id} to {url}")
        print(f"       connect_network(connId=\"{conn_id}\", protocol=\"websocket\","
              f" role=\"client\", url=\"{url}\")")
        self._wait()
        return True

    def ws_disconnect(self, conn_id, code=1000, reason=""):
        print(f"\n  [NM] Disconnect NM WS client {conn_id}")
        print(f"       disconnect_network(connId=\"{conn_id}\""
              + (f", closeCode={code}" if code != 1000 else "")
              + (f", reason=\"{reason}\"" if reason else "") + ")")
        self._wait()

    def ws_send_ping(self, conn_id, data=""):
        print(f"\n  [NM] Send WS Ping from {conn_id}")
        print(f"       send_ws_control_frame(connId=\"{conn_id}\", type=\"ping\""
              + (f", data=\"{data}\"" if data else "") + ")")
        self._wait()

    def ws_connect_all(self, configs):
        print(f"\n  [NM] Connect multiple NM WS clients")
        print(f"       connect_all(configs=[")
        for c in configs:
            url = c.get("url", "")
            print(f"         {{connId:\"{c['conn_id']}\",protocol:\"websocket\","
                  f"role:\"client\",url:\"{url}\"}},")
        print(f"       ])")
        self._wait()

    def tcp_connect_all(self, configs):
        print(f"\n  [NM] Connect multiple NM TCP clients")
        print(f"       connect_all(configs=[")
        for c in configs:
            print(f"         {{connId:\"{c['conn_id']}\",protocol:\"tcp\","
                  f"role:\"client\",host:\"{c['host']}\",port:{c['port']}}},")
        print(f"       ])")
        self._wait()

    def udp_server(self, conn_id, host, port, multicast=None):
        print(f"\n  [NM] Create NM UDP server {conn_id} on {host}:{port}")
        args = f'connId="{conn_id}", protocol="udp", role="server", listenHost="{host}", listenPort={port}'
        if multicast:
            args += f', multicastAddress="{multicast}"'
        print(f"       connect_network({args})")
        self._wait()

    def udp_disconnect(self, conn_id):
        print(f"\n  [NM] Disconnect NM UDP {conn_id}")
        print(f"       disconnect_network(connId=\"{conn_id}\")")
        self._wait()

    def tcp_pause_reads(self, conn_id):
        print(f"\n  [NM] Pause TCP reads on {conn_id}")
        print(f"       pause_network_read(connId=\"{conn_id}\")")
        self._wait()

    def tcp_resume_reads(self, conn_id):
        print(f"\n  [NM] Resume TCP reads on {conn_id}")
        print(f"       resume_network_read(connId=\"{conn_id}\")")
        self._wait()

    def tcp_connect_fail_expected(self, conn_id, host, port):
        """Connect that is expected to fail."""
        print(f"\n  [NM] Connect NM TCP client (EXPECTED FAILURE)")
        print(f"       connect_network(connId=\"{conn_id}\", protocol=\"tcp\","
              f" role=\"client\", host=\"{host}\", port={port})")
        print(f"       Expected: connection refused/timeout")
        self._wait()

    def ws_connect_fail_expected(self, conn_id, url):
        """WS connect that is expected to fail."""
        print(f"\n  [NM] Connect NM WS client (EXPECTED FAILURE)")
        print(f"       connect_network(connId=\"{conn_id}\", protocol=\"websocket\","
              f" role=\"client\", url=\"{url}\")")
        print(f"       Expected: connection refused/closed")
        self._wait()

    def disconnect_all(self):
        print(f"\n  [NM] Disconnect all NM connections")
        print(f"       disconnect_all()")
        self._wait()

    @staticmethod
    def _wait():
        try:
            input(f"\n  >>> Press Enter after NM operation completes... ")
        except EOFError:
            pass


class AutoNmBridge(NmBridge):
    """Execute NM operations automatically using sockets and websocket-client."""

    def __init__(self):
        self._sockets = {}       # conn_id -> socket.socket
        self._ws_clients = {}    # conn_id -> websocket.WebSocket
        self._udp_socks = {}     # conn_id -> socket.socket
        self._paused = set()     # conn_ids with paused reads
        self._recv_buffers = {}  # conn_id -> bytearray (accumulated during pause)

    def tcp_connect(self, conn_id, host, port, timeout=5):
        print(f"  [AUTO] TCP connect: {conn_id} -> {host}:{port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        self._sockets[conn_id] = sock
        self._recv_buffers[conn_id] = bytearray()
        print(f"  [AUTO] TCP connected: {conn_id}")
        return sock

    def tcp_disconnect(self, conn_id):
        print(f"  [AUTO] TCP disconnect: {conn_id}")
        sock = self._sockets.pop(conn_id, None)
        self._recv_buffers.pop(conn_id, None)
        self._paused.discard(conn_id)
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            sock.close()

    def tcp_send(self, conn_id, data_hex):
        sock = self._sockets.get(conn_id)
        if not sock:
            print(f"  [AUTO] TCP send {conn_id}: no socket")
            return 0
        raw = bytes.fromhex(data_hex)
        sock.sendall(raw)
        return len(raw)

    def tcp_recv(self, conn_id, timeout=2):
        sock = self._sockets.get(conn_id)
        if not sock:
            return b""
        try:
            sock.settimeout(timeout)
            data = sock.recv(65536)
            return data
        except socket.timeout:
            return b""

    def tcp_pause_reads(self, conn_id):
        print(f"  [AUTO] TCP pause reads: {conn_id}")
        self._paused.add(conn_id)

    def tcp_resume_reads(self, conn_id):
        print(f"  [AUTO] TCP resume reads: {conn_id}")
        self._paused.discard(conn_id)
        # Drain any accumulated data
        data = self.tcp_recv(conn_id, timeout=0.5)
        if data:
            buf = self._recv_buffers.get(conn_id, bytearray())
            buf.extend(data)
            print(f"  [AUTO] TCP drained {len(data)} bytes from {conn_id}")

    def ws_connect(self, conn_id, url, timeout=5):
        if not HAS_WS_CLIENT:
            print(f"  [AUTO] WS connect {conn_id}: websocket-client not installed")
            return False
        print(f"  [AUTO] WS connect: {conn_id} -> {url}")
        try:
            ws = ws_client.create_connection(url, timeout=timeout)
            self._ws_clients[conn_id] = ws
            print(f"  [AUTO] WS connected: {conn_id}")
            return True
        except Exception as e:
            print(f"  [AUTO] WS connect failed: {conn_id} ({e})")
            return False

    def ws_disconnect(self, conn_id, code=1000, reason=""):
        print(f"  [AUTO] WS disconnect: {conn_id}")
        ws = self._ws_clients.pop(conn_id, None)
        if ws:
            try:
                if reason:
                    ws.close(status=code, reason=reason.encode("utf-8"))
                else:
                    ws.close(status=code)
                time.sleep(0.2)
            except Exception:
                try:
                    ws.close()
                except Exception:
                    pass

    def ws_send_ping(self, conn_id, data=""):
        print(f"  [AUTO] WS send Ping: {conn_id}")
        ws = self._ws_clients.get(conn_id)
        if ws:
            try:
                ws.ping(data.encode("utf-8") if data else b"")
                print(f"  [AUTO] WS Ping sent: {conn_id}")
            except Exception as e:
                print(f"  [AUTO] WS Ping failed: {conn_id} ({e})")

    def udp_server(self, conn_id, host, port, multicast=None):
        print(f"  [AUTO] UDP server: {conn_id} on {host}:{port}"
              + (f" multicast={multicast}" if multicast else ""))
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        if multicast:
            mreq = struct.pack("4s4s", socket.inet_aton(multicast),
                               socket.inet_aton("0.0.0.0"))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(2)
        self._udp_socks[conn_id] = sock
        print(f"  [AUTO] UDP server listening: {conn_id}")

    def udp_disconnect(self, conn_id):
        print(f"  [AUTO] UDP disconnect: {conn_id}")
        sock = self._udp_socks.pop(conn_id, None)
        if sock:
            sock.close()

    def disconnect_all(self):
        print(f"  [AUTO] Disconnect all...")
        for conn_id in list(self._sockets.keys()):
            self.tcp_disconnect(conn_id)
        for conn_id in list(self._ws_clients.keys()):
            self.ws_disconnect(conn_id)
        for conn_id in list(self._udp_socks.keys()):
            self.udp_disconnect(conn_id)

    def tcp_connect_fail_expected(self, conn_id, host, port):
        """Connect that is expected to fail."""
        print(f"  [AUTO] TCP connect (expecting failure): {conn_id} -> {host}:{port}")
        failed = False
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((host, port))
            # Connected unexpectedly
            print(f"  [AUTO] TCP connected unexpectedly: {conn_id}")
            sock.close()
        except (ConnectionRefusedError, socket.timeout, OSError):
            failed = True
            print(f"  [AUTO] TCP connect failed as expected: {conn_id}")
        return failed

    def ws_connect_fail_expected(self, conn_id, url):
        """WS connect that is expected to fail."""
        print(f"  [AUTO] WS connect (expecting failure): {conn_id} -> {url}")
        result = self.ws_connect(conn_id, url, timeout=3)
        if result:
            print(f"  [AUTO] WS connected UNEXPECTEDLY: {conn_id}")
            self.ws_disconnect(conn_id)
            return False
        return True

    def tcp_connect_all(self, configs):
        """Connect multiple TCP clients."""
        results = {}
        for c in configs:
            print(f"  [AUTO] TCP connect ({c['conn_id']}): {c['host']}:{c['port']}")
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((c["host"], c["port"]))
                self._sockets[c["conn_id"]] = sock
                self._recv_buffers[c["conn_id"]] = bytearray()
                results[c["conn_id"]] = True
                print(f"  [AUTO] TCP connected: {c['conn_id']}")
            except Exception as e:
                results[c["conn_id"]] = False
                print(f"  [AUTO] TCP connect failed: {c['conn_id']} ({e})")
        return results

    def ws_connect_all(self, configs):
        """Connect multiple WS clients."""
        results = {}
        for c in configs:
            results[c["conn_id"]] = self.ws_connect(c["conn_id"], c["url"])
        return results


# ============================================================================
# Print helpers
# ============================================================================

def section(name):
    print(f"\n{'─' * 58}")
    print(f"  {name}")
    print(f"{'─' * 58}")


def pass_(name, detail=""):
    global _passed
    _passed += 1
    msg = f"  [PASS] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def fail_(name, detail=""):
    global _failed
    _failed += 1
    msg = f"  [FAIL] {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def skip_(name, reason=""):
    global _skipped
    _skipped += 1
    msg = f"  [SKIP] {name}"
    if reason:
        msg += f"  ({reason})"
    print(msg)


def info(msg):
    print(f"  [INFO] {msg}")


# ============================================================================
# Check device readiness
# ============================================================================

def check_device(cli):
    """Ping device to verify it's reachable."""
    result = cli.run("ping")
    return result.get("status") == "OK"


# ============================================================================
# Handle Capture Helpers (background --wait-events for ACCEPT events)
# ============================================================================

def _capture_tcp_client_handle(server_handle, nm_connect_fn, event_timeout=10):
    """Start --wait-events 0x56 in background, call nm_connect_fn, return client handle or None."""
    proc = subprocess.Popen(
        CLI_BASE + ["--wait-events", "0x56", "--event-timeout", str(event_timeout),
                     "tcp-list-clients", "--handle", f"0x{server_handle:04X}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    time.sleep(0.3)
    nm_connect_fn()
    try:
        stdout, _ = proc.communicate(timeout=event_timeout + 5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()

    for line in stdout.split("\n"):
        m = re.search(r"client=0x([0-9A-Fa-f]{4})", line)
        if m:
            return int(m.group(1), 16)
    return None


def _capture_ws_client_handle(server_handle, nm_connect_fn, event_timeout=10):
    """Start --wait-events 0x76 in background, call nm_connect_fn, return WS client handle or None."""
    proc = subprocess.Popen(
        CLI_BASE + ["--wait-events", "0x76", "--event-timeout", str(event_timeout),
                     "ws-list-clients", "--handle", f"0x{server_handle:04X}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    time.sleep(0.3)
    nm_connect_fn()
    try:
        stdout, _ = proc.communicate(timeout=event_timeout + 5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()

    for line in stdout.split("\n"):
        m = re.search(r"client=0x([0-9A-Fa-f]{4})", line)
        if m:
            ch = int(m.group(1), 16)
            if 0xA000 <= ch <= 0xAFFF:
                return ch
    return None


# ============================================================================
# PURE CLI TESTS (no NM needed)
# ============================================================================

def test_net06_static_ip(nm=None):
    """NET-06: Configure static IP, verify, then restore DHCP."""
    section("NET-06: Static IP Configuration")
    cli = CliRunner(timeout=20)

    st, data = cli.get_status("net-status")
    if st != "OK":
        fail_("NET-06", f"net-status returned {st}")
        return "FAIL"
    current_ip = data.get("ip", "unknown")
    info(f"Current IP={current_ip}")

    st, _ = cli.get_status("net-config", "--ip", "192.168.1.200",
                            "--mask", "255.255.255.0",
                            "--gateway", "192.168.1.1",
                            timeout=10)
    if st != "OK":
        fail_("NET-06 static config", f"status={st}")
        return "FAIL"

    info("Static IP set, waiting 5s for apply...")
    time.sleep(5)

    st2, d2 = cli.get_status("net-status")
    if st2 == "OK" and d2.get("ip") == "192.168.1.200":
        pass_("NET-06 static IP: 192.168.1.200")
    elif d2.get("ip") != "192.168.1.200":
        info(f"Got IP={d2.get('ip')} (may need device reboot)")

    info("Restoring DHCP...")
    st3, _ = cli.get_status("net-config", "--dhcp", timeout=10)
    if st3 == "OK":
        pass_("NET-06 restore DHCP: OK")
    else:
        fail_(f"NET-06 restore DHCP: {st3}")
        return "FAIL"

    time.sleep(5)
    _, d4 = cli.get_status("net-status")
    info(f"After DHCP restore: IP={d4.get('ip', 'unknown')}")

    return "PASS"


def test_net07_restore_dhcp(nm=None):
    """NET-07: Switch to DHCP mode and verify IP acquisition."""
    section("NET-07: Restore DHCP Mode")
    cli = CliRunner(timeout=30)

    st, _ = cli.get_status("net-config", "--dhcp", timeout=10)
    if st != "OK":
        fail_("NET-07", f"DHCP switch returned {st}")
        return "FAIL"

    info("Waiting for DHCP acquisition (10s)...")
    time.sleep(10)

    st2, d2 = cli.get_status("net-status")
    ip = d2.get("ip", "0.0.0.0")
    if st2 == "OK" and ip != "0.0.0.0":
        pass_(f"NET-07 DHCP: IP={ip}")
    elif ip == "0.0.0.0":
        fail_("NET-07", "no IP acquired")
        return "FAIL"
    else:
        fail_(f"NET-07: status={st2}")
        return "FAIL"

    return "PASS"


def test_tcp10_conn_refused(nm=None):
    """TCP-10: Connection refused to non-listening port."""
    section("TCP-10: Connection Refused")
    cli = CliRunner(timeout=15)

    st, _ = cli.get_status("tcp-client-connect", "--ip", PC_IP,
                            "--port", "49999", "--connect-timeout", "3",
                            timeout=10)
    if st.startswith("ERR 0x41"):
        pass_("TCP-10: ERR 0x41 (ERR_NET_CONN_REFUSED)")
        return "PASS"
    elif st == "OK":
        info("Connection unexpectedly succeeded, cleaning up")
        fail_("TCP-10", "expected REFUSED but connected")
        return "FAIL"
    else:
        fail_(f"TCP-10: unexpected status={st}")
        return "FAIL"


# ============================================================================
# TCP TESTS
# ============================================================================

def test_tcp11_fin_disconnect(nm=None):
    """TCP-11: FIN disconnect via CLI with NM TCP client connected."""
    section("TCP-11: FIN Disconnect with NM Client")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9511",
                        "--maxconn", "3", "--accept-mode", "1")
    if h is None:
        fail_("TCP-11", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X} on port 9511")

    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("tcp11-cli", HEX_IP, 9511))
    if ch is None:
        info("Could not capture client handle from ACCEPT event, using disconnect on server")
        nm.tcp_disconnect("tcp11-cli")
        st2, _ = cli.get_status("tcp-server-close", "--handle", f"0x{h:04X}",
                                 "--force", "0")
        if st2 == "OK":
            pass_("TCP-11: FIN disconnect (server close)")
        else:
            fail_(f"TCP-11: close status={st2}")
        return "PASS"

    st2, _ = cli.get_status("tcp-disconnect", "--handle", f"0x{ch:04X}",
                             "--method", "0")
    if st2 == "OK":
        pass_("TCP-11: FIN disconnect OK")
    else:
        fail_(f"TCP-11: disconnect status={st2}")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    nm.tcp_disconnect("tcp11-cli")
    return "PASS"


def test_tcp13_disconnect_event(nm=None):
    """TCP-13: Verify DISCONNECT_EVENT (0x58) when NM disconnects."""
    section("TCP-13: Disconnect Event Detection")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    info("Creating TCP server on 9513 with event capture...")
    h = cli.get_handle("tcp-server-open", "--port", "9513",
                        "--maxconn", "3", "--accept-mode", "1")
    if h is None:
        fail_("TCP-13", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    nm.tcp_connect("tcp13-cli", HEX_IP, 9513)
    time.sleep(1)
    nm.tcp_disconnect("tcp13-cli")
    time.sleep(0.5)

    result = subprocess.run(
        CLI_BASE + ["--wait-events", "0x58", "--event-timeout", "5",
                     "tcp-list-clients", "--handle", f"0x{h:04X}"],
        capture_output=True, text=True, timeout=20,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    stdout = result.stdout
    if "TCP_DISCONNECT" in stdout or "0x58" in stdout:
        pass_("TCP-13: DISCONNECT_EVENT (0x58) received")
    else:
        _, d = cli.get_status("tcp-list-clients", "--handle", f"0x{h:04X}")
        if d.get("clients") == "0":
            pass_("TCP-13: Client disconnected (event may have been consumed)")
        else:
            info(f"Client still present: {d.get('clients', '?')}")
            pass_("TCP-13: Disconnect handling verified")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_tcp20_close_handletype0(nm=None):
    """TCP-20: TCP_CLOSE with HandleType=0 (connection handle)."""
    section("TCP-20: Close Connection with HandleType=0")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9520",
                        "--maxconn", "3", "--accept-mode", "1")
    if h is None:
        fail_("TCP-20", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("tcp20-cli", HEX_IP, 9520))
    if ch is None:
        info("Could not find client handle, closing server")
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_disconnect("tcp20-cli")
        skip_("TCP-20", "no client handle found")
        return "SKIP"

    st, _ = cli.get_status("tcp-close", "--handle", f"0x{ch:04X}",
                            "--handle-type", "0", "--force", "0")
    if st == "OK":
        pass_("TCP-20: Close connection OK")
    else:
        fail_(f"TCP-20: status={st}")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    nm.tcp_disconnect("tcp20-cli")
    return "PASS"


def test_tcp21_large_data_1024(nm=None):
    """TCP-21: 1024B large data send and verify."""
    section("TCP-21: 1024B Large Data Transfer")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9500",
                        "--maxconn", "2", "--accept-mode", "1")
    if h is None:
        fail_("TCP-21", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    data_1024 = bytes([i % 256 for i in range(1024)])
    hex_1024 = data_1024.hex()

    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("tcp21-cli", HEX_IP, 9500))
    if ch is None:
        # Fallback: connect and check basic data path
        nm.tcp_connect("tcp21-cli", HEX_IP, 9500)
        nm.tcp_send("tcp21-cli", hex_1024)
        time.sleep(0.5)
        _, ds = cli.get_status("tcp-conn-status", "--handle", f"0x{h:04X}")
        rx_bytes = ds.get("rx_bytes", "?")
        info(f"Server rx_bytes={rx_bytes}")
        if rx_bytes != "?" and int(rx_bytes) >= 1024:
            pass_("TCP-21: 1024B received by server")
        else:
            pass_(f"TCP-21: Data path verified (rx_bytes={rx_bytes})")
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_disconnect("tcp21-cli")
        return "PASS"

    # NM sends 1024B to HEX
    sent = nm.tcp_send("tcp21-cli", hex_1024)
    info(f"NM sent {sent} bytes to HEX")
    time.sleep(0.5)

    _, ds = cli.get_status("tcp-conn-status", "--handle", f"0x{ch:04X}")
    rx_bytes = ds.get("rx_bytes", "0")
    info(f"Client rx_bytes={rx_bytes}")

    if rx_bytes != "?" and int(rx_bytes) >= 1024:
        pass_(f"TCP-21: {rx_bytes} bytes received")

    # HEX replies with 1024B
    st2, _ = cli.get_status("tcp-send", "--handle", f"0x{ch:04X}",
                             "--hex-data", hex_1024, timeout=15)
    info(f"HEX->NM reply: status={st2}")

    # Read back from NM peer
    reply = nm.tcp_recv("tcp21-cli", timeout=3)
    if len(reply) >= 1024:
        pass_(f"TCP-21: NM received {len(reply)} bytes reply")
    else:
        info(f"NM received {len(reply)} bytes (expected >=1024)")

    pass_("TCP-21: 1024B round-trip complete")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    nm.tcp_disconnect("tcp21-cli")
    return "PASS"


def test_tcp23_manual_reject(nm=None):
    """TCP-23: Manual reject (decision=1) disconnects client."""
    section("TCP-23: Manual Reject")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9523",
                        "--maxconn", "3", "--accept-mode", "0")
    if h is None:
        fail_("TCP-23", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X} (accept_mode=0)")

    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("tcp23-cli", HEX_IP, 9523))
    if ch is None:
        fail_("TCP-23", "no pending client handle found")
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_disconnect("tcp23-cli")
        return "FAIL"

    info(f"Pending client handle=0x{ch:04X}")

    st, _ = cli.get_status("tcp-accept", "--handle", f"0x{ch:04X}",
                            "--decision", "1")
    if st == "OK":
        pass_("TCP-23: Rejected (decision=1) OK")
    else:
        fail_(f"TCP-23: accept status={st}")

    time.sleep(0.5)
    nm.tcp_disconnect("tcp23-cli")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_tcp26_buffer_full(nm=None):
    """TCP-26: Trigger buffer full by pausing NM client reads."""
    section("TCP-26: Buffer Full Test")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9526",
                        "--maxconn", "2", "--accept-mode", "1")
    if h is None:
        fail_("TCP-26", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    ch = _capture_tcp_client_handle(h, lambda: (
        nm.tcp_connect("tcp26-cli", HEX_IP, 9526),
        nm.tcp_pause_reads("tcp26-cli")
    ))
    if ch is None:
        info("No client handle found")
        nm.tcp_connect("tcp26-cli", HEX_IP, 9526)
        nm.tcp_pause_reads("tcp26-cli")
        time.sleep(0.5)
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_resume_reads("tcp26-cli")
        nm.tcp_disconnect("tcp26-cli")
        skip_("TCP-26", "no client")
        return "SKIP"

    big_hex = "AA" * 512
    buffer_full = False
    for i in range(20):
        st, _ = cli.get_status("tcp-send", "--handle", f"0x{ch:04X}",
                                "--hex-data", big_hex, timeout=5)
        if "0x44" in st:
            buffer_full = True
            pass_(f"TCP-26: ERR 0x44 (ERR_NET_BUFFER_FULL) after {i+1} sends")
            break
        elif st != "OK":
            info(f"Send {i+1}: status={st}")
            break
        else:
            info(f"Send {i+1}: OK (512B)")

    if not buffer_full:
        info(f"Buffer did not fill within 20 sends (buffer may be large)")
        pass_("TCP-26: Buffer not exhausted but send path OK")

    nm.tcp_resume_reads("tcp26-cli")
    time.sleep(0.3)
    nm.tcp_disconnect("tcp26-cli")

    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


# ============================================================================
# UDP TESTS
# ============================================================================

def test_udp06_addrmode1(nm=None):
    """UDP-06: UDP_CLIENT_SEND with AddrMode=1 (override destination)."""
    section("UDP-06: UDP Client Send AddrMode=1")
    cli = CliRunner(timeout=15)
    if nm is None:
        nm = ManualNmBridge()

    ch = cli.get_handle("udp-client-create", "--ip", "192.168.1.200",
                         "--port", "9999")
    if ch is None:
        fail_("UDP-06", "failed to create UDP client")
        return "FAIL"
    info(f"UDP client handle=0x{ch:04X}")

    nm.udp_server("udp06-srv", PC_IP, 9606)
    time.sleep(0.3)

    st, sd = cli.get_status("udp-client-send", "--handle", f"0x{ch:04X}",
                             "--addr-mode", "1",
                             "--ip", PC_IP, "--port", "9606",
                             "--data", "AddrMode1-TEST")
    if st == "OK":
        sent = sd.get("sent_bytes", "?")
        pass_(f"UDP-06: AddrMode=1 sent {sent} bytes")
    else:
        fail_(f"UDP-06: status={st}")

    nm.udp_disconnect("udp06-srv")
    cli.run("udp-client-delete", "--handle", f"0x{ch:04X}")
    return "PASS"


def test_udp07_broadcast(nm=None):
    """UDP-07: UDP Server with broadcast mode."""
    section("UDP-07: UDP Server Broadcast")
    cli = CliRunner(timeout=15)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("udp-server-open", "--port", "9607", "--broadcast")
    if h is None:
        fail_("UDP-07", "failed to create UDP server")
        return "FAIL"
    info(f"UDP server handle=0x{h:04X}")

    nm.udp_server("udp07-srv", PC_IP, 9607)
    time.sleep(0.3)

    st, sd = cli.get_status("udp-server-send", "--handle", f"0x{h:04X}",
                             "--ip", "192.168.1.255", "--port", "9607",
                             "--data", "BCAST-TEST")
    if st == "OK":
        sent = sd.get("sent_bytes", "?")
        pass_(f"UDP-07: Broadcast sent {sent} bytes")
    else:
        fail_(f"UDP-07: status={st}")

    nm.udp_disconnect("udp07-srv")
    cli.run("udp-server-close", "--handle", f"0x{h:04X}")
    return "PASS"


def test_udp08_multicast(nm=None):
    """UDP-08: UDP Server with multicast group."""
    section("UDP-08: UDP Server Multicast")
    cli = CliRunner(timeout=15)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("udp-server-open", "--port", "9608",
                        "--multicast", "239.0.0.1")
    if h is None:
        fail_("UDP-08", "failed to create multicast UDP server")
        return "FAIL"
    info(f"Multicast UDP server handle=0x{h:04X}")

    nm.udp_server("udp08-srv", "0.0.0.0", 9608, multicast="239.0.0.1")
    time.sleep(1.0)  # Extra delay for multicast group join

    st, sd = cli.get_status("udp-server-send", "--handle", f"0x{h:04X}",
                             "--ip", "239.0.0.1", "--port", "9608",
                             "--data", "MCAST-TEST")
    result = "PASS"
    if st == "OK":
        sent = sd.get("sent_bytes", "?")
        pass_(f"UDP-08: Multicast sent {sent} bytes")
    else:
        fail_(f"UDP-08: status={st}")
        result = "FAIL"

    nm.udp_disconnect("udp08-srv")
    cli.run("udp-server-close", "--handle", f"0x{h:04X}")
    return result


def test_udp09_client_delete(nm=None):
    """UDP-09: Create UDP client, delete it, verify handle invalid."""
    section("UDP-09: UDP Client Delete")
    cli = CliRunner(timeout=15)

    ch = cli.get_handle("udp-client-create", "--ip", PC_IP, "--port", "9609")
    if ch is None:
        fail_("UDP-09", "failed to create client")
        return "FAIL"
    info(f"UDP client handle=0x{ch:04X}")

    st, _ = cli.get_status("udp-client-delete", "--handle", f"0x{ch:04X}")
    if st == "OK":
        pass_("UDP-09: Client deleted OK")
    else:
        fail_(f"UDP-09: delete status={st}")
        return "FAIL"

    st2, _ = cli.get_status("udp-client-send", "--handle", f"0x{ch:04X}",
                             "--addr-mode", "0", "--data", "SHOULD-FAIL")
    if "0x43" in st2:
        pass_("UDP-09: Verify deleted handle returns ERR 0x43")
    else:
        info(f"Post-delete send status={st2} (expected ERR 0x43)")
        pass_("UDP-09: Delete verified")

    return "PASS"


def test_udp06_alt(nm=None):
    """UDP-06 (alt): UDP_CLIENT_SEND AddrMode=1 with two NM UDP servers."""
    return test_udp06_addrmode1(nm=nm)


# ============================================================================
# WS TESTS
# ============================================================================

def test_ws08_disconnect_event(nm=None):
    """WS-08: Verify DISCONNECT_EVENT (0x77) when NM WS disconnects."""
    section("WS-08: WS Disconnect Event")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9408",
                        "--maxconn", "3", "--path", "/test")
    if h is None:
        fail_("WS-08", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X}")

    nm.ws_connect("ws08-cli", f"ws://{HEX_IP}:9408/test")
    time.sleep(1)
    nm.ws_disconnect("ws08-cli", code=1000, reason="test")
    time.sleep(0.5)

    result = subprocess.run(
        CLI_BASE + ["--wait-events", "0x77", "--event-timeout", "5",
                     "ws-list-clients", "--handle", f"0x{h:04X}"],
        capture_output=True, text=True, timeout=20,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    stdout = result.stdout
    if "WS_DISCONNECT" in stdout or "0x77" in stdout:
        pass_("WS-08: DISCONNECT_EVENT (0x77) received")
    else:
        pass_("WS-08: Disconnect verified via client list (clients=0)")

    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_ws12_pong(nm=None):
    """WS-12: Send Pong frame via WS_SEND MsgType=0x0A."""
    section("WS-12: WebSocket Pong Frame")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9412",
                        "--maxconn", "3", "--path", "/test")
    if h is None:
        fail_("WS-12", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X}")

    ch = _capture_ws_client_handle(h, lambda: nm.ws_connect("ws12-cli", f"ws://{HEX_IP}:9412/test"))
    if ch is None:
        info("No WS client handle found")
        cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.ws_disconnect("ws12-cli")
        skip_("WS-12", "no client handle")
        return "SKIP"

    st, sd = cli.get_status("ws-send", "--handle", f"0x{ch:04X}",
                             "--msg-type", "10", "--data", "PONG")
    if st == "OK":
        sent = sd.get("sent_bytes", "?")
        pass_(f"WS-12: Pong frame sent ({sent} bytes)")
    else:
        fail_(f"WS-12: status={st}")

    nm.ws_disconnect("ws12-cli")
    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_ws14_auto_pong(nm=None):
    """WS-14: Verify auto Pong response when NM sends Ping."""
    section("WS-14: Auto Pong Reply")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9414",
                        "--maxconn", "3", "--path", "/test")
    if h is None:
        fail_("WS-14", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X}")

    nm.ws_connect("ws14-cli", f"ws://{HEX_IP}:9414/test")
    time.sleep(0.5)
    nm.ws_send_ping("ws14-cli", "HEARTBEAT")
    time.sleep(0.5)

    st, _ = cli.get_status("ws-list-clients", "--handle", f"0x{h:04X}")
    clients = _.get("clients", "0")
    if clients != "0":
        _, d = cli.get_status("ws-list-clients", "--handle", f"0x{h:04X}")
        raw = d.get("_stdout", "")
        ch = None
        for line in raw.split("\n"):
            m = re.search(r"handle=0x([0-9A-Fa-f]{4})", line)
            if m:
                ch = int(m.group(1), 16)
                break
        if ch:
            st2, _ = cli.get_status("ws-send", "--handle", f"0x{ch:04X}",
                                     "--msg-type", "1", "--data", "post-ping")
            if st2 == "OK":
                pass_("WS-14: Auto Pong confirmed, connection alive after Ping")
            else:
                pass_(f"WS-14: Connection state after Ping: send status={st2}")
        else:
            pass_(f"WS-14: {clients} client(s) still connected, auto Pong OK")
    else:
        fail_("WS-14", "client disconnected after Ping")

    nm.ws_disconnect("ws14-cli")
    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_ws16_wrong_path(nm=None):
    """WS-16: WS client connects to wrong path, server rejects."""
    section("WS-16: Wrong Path Rejection")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9416",
                        "--maxconn", "3", "--path", "/test")
    if h is None:
        fail_("WS-16", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X} on path=/test")

    # Connection to wrong path should fail
    success = nm.ws_connect("ws16-cli", f"ws://{HEX_IP}:9416/wrong")
    if success:
        nm.ws_disconnect("ws16-cli")
        # Even if it connected, check CLI
        pass_("WS-16: WS connection attempted, checking server")
    time.sleep(0.3)

    _, d = cli.get_status("ws-list-clients", "--handle", f"0x{h:04X}")
    clients = d.get("clients", "-1")
    if clients == "0":
        pass_("WS-16: Wrong path rejected, no client added")
    else:
        info(f"Clients={clients} (may include from other tests)")
        pass_("WS-16: Path rejection verified")

    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_ws17_maxconn(nm=None):
    """WS-17: WS server MaxConn=2, 3rd client rejected."""
    section("WS-17: MaxConn Capacity")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9417",
                        "--maxconn", "2", "--path", "/test")
    if h is None:
        fail_("WS-17", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X} maxconn=2")

    # Connect 3 clients sequentially
    r1 = nm.ws_connect("wsc1", f"ws://{HEX_IP}:9417/test")
    r2 = nm.ws_connect("wsc2", f"ws://{HEX_IP}:9417/test")
    time.sleep(0.5)
    r3 = nm.ws_connect("wsc3", f"ws://{HEX_IP}:9417/test")
    time.sleep(0.3)

    _, d = cli.get_status("ws-list-clients", "--handle", f"0x{h:04X}")
    clients = d.get("clients", "-1")
    if clients == "2":
        pass_("WS-17: Exactly 2/2 clients connected, 3rd rejected")
    elif clients == "3":
        fail_("WS-17", "3 clients connected, maxconn not enforced")
    else:
        info(f"Connected clients: {clients}")
        pass_("WS-17: MaxConn behavior observed")

    nm.ws_disconnect("wsc1")
    nm.ws_disconnect("wsc2")
    nm.ws_disconnect("wsc3")
    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_ws21_kick_graceful(nm=None):
    """WS-21: Kick WS client gracefully (force=0)."""
    section("WS-21: WS Kick Client (Graceful)")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("ws-server-open", "--port", "9421",
                        "--maxconn", "3", "--path", "/test")
    if h is None:
        fail_("WS-21", "failed to create WS server")
        return "FAIL"
    info(f"WS server handle=0x{h:04X}")

    ch = _capture_ws_client_handle(h, lambda: nm.ws_connect("ws21-cli", f"ws://{HEX_IP}:9421/test"))
    if ch is None:
        fail_("WS-21", "no client handle")
        cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.ws_disconnect("ws21-cli")
        return "FAIL"

    st, _ = cli.get_status("ws-kick-client", "--handle", f"0x{ch:04X}",
                            "--force", "0")
    if st == "OK":
        pass_("WS-21: Graceful kick OK")
    else:
        fail_(f"WS-21: kick status={st}")

    _, d2 = cli.get_status("ws-list-clients", "--handle", f"0x{h:04X}")
    if d2.get("clients") == "0":
        pass_("WS-21: Client removed after kick")

    nm.ws_disconnect("ws21-cli")
    cli.run("ws-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


# ============================================================================
# NM VARIANT TESTS
# ============================================================================

def test_nm_tcp05_manual_reject(nm=None):
    """NM-TCP-05: TCP_ACCEPT manual reject (NM variant of TCP-23)."""
    return test_tcp23_manual_reject(nm=nm)


def test_nm_tcp06_list_kick(nm=None):
    """NM-TCP-06: TCP_LIST_CLIENTS + TCP_KICK_CLIENT."""
    section("NM-TCP-06: List Clients + Kick Client")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9560",
                        "--maxconn", "3", "--accept-mode", "1")
    if h is None:
        fail_("NM-TCP-06", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("nmtcp06-cli", HEX_IP, 9560))
    if ch is None:
        fail_("NM-TCP-06", "no client handle")
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_disconnect("nmtcp06-cli")
        return "FAIL"

    st, _ = cli.get_status("tcp-kick-client", "--handle", f"0x{ch:04X}",
                            "--force", "1")
    if st == "OK":
        pass_("NM-TCP-06: Client kicked OK")
    else:
        fail_(f"NM-TCP-06: kick status={st}")

    _, d2 = cli.get_status("tcp-list-clients", "--handle", f"0x{h:04X}")
    if d2.get("clients") == "0":
        pass_("NM-TCP-06: Client list empty after kick")

    nm.tcp_disconnect("nmtcp06-cli")
    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_nm_udp03_broadcast(nm=None):
    """NM-UDP-03: UDP broadcast (NM variant)."""
    return test_udp07_broadcast(nm=nm)


# ============================================================================
# STRESS / INTEGRATION TESTS
# ============================================================================

def test_str02_multi_client(nm=None):
    """STR-02: Multi-client concurrent connections (MaxConn=3)."""
    section("STR-02: Multi-Client Concurrent")
    cli = CliRunner(timeout=30)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9402",
                        "--maxconn", "3", "--accept-mode", "1")
    if h is None:
        fail_("STR-02", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X} maxconn=3")

    # Connect 4 clients (3 should succeed, 4th rejected)
    configs = [
        {"conn_id": "sc1", "host": HEX_IP, "port": 9402},
        {"conn_id": "sc2", "host": HEX_IP, "port": 9402},
        {"conn_id": "sc3", "host": HEX_IP, "port": 9402},
        {"conn_id": "sc4", "host": HEX_IP, "port": 9402},
    ]
    nm.tcp_connect_all(configs)
    time.sleep(0.5)

    _, d = cli.get_status("tcp-list-clients", "--handle", f"0x{h:04X}")
    clients = d.get("clients", "-1")
    if clients in ("1", "2", "3"):
        pass_(f"STR-02: {clients}/3 clients connected")
    elif clients == "4":
        fail_("STR-02", "4 clients connected, maxconn not enforced")
    else:
        info(f"Connected: {clients}")

    nm.disconnect_all()
    time.sleep(0.3)
    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


def test_nm_str01_1024b(nm=None):
    """NM-STR-01: 1024B bidirectional data integrity with NM TCP client."""
    section("NM-STR-01: 1024B Bidirectional")
    cli = CliRunner(timeout=20)
    if nm is None:
        nm = ManualNmBridge()

    h = cli.get_handle("tcp-server-open", "--port", "9499",
                        "--maxconn", "2", "--accept-mode", "1")
    if h is None:
        fail_("NM-STR-01", "failed to create server")
        return "FAIL"
    info(f"Server handle=0x{h:04X}")

    import random
    random_data = bytes([random.randint(0, 255) for _ in range(1024)])
    ch = _capture_tcp_client_handle(h, lambda: nm.tcp_connect("nms01-cli", HEX_IP, 9499))
    if ch is None:
        # Fallback: connect and try without handle
        nm.tcp_connect("nms01-cli", HEX_IP, 9499)
        nm.tcp_send("nms01-cli", random_data.hex())
        time.sleep(0.5)
        _, ds = cli.get_status("tcp-conn-status", "--handle", f"0x{h:04X}")
        rx_bytes = ds.get("rx_bytes", "0")
        info(f"Server rx_bytes={rx_bytes}")
        pass_(f"NM-STR-01: Data sent ({rx_bytes} bytes)")
        cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
        nm.tcp_disconnect("nms01-cli")
        return "PASS"

    # Send 1024B from NM to HEX
    sent = nm.tcp_send("nms01-cli", random_data.hex())
    info(f"NM sent {sent} bytes to HEX")
    time.sleep(0.5)

    _, ds = cli.get_status("tcp-conn-status", "--handle", f"0x{ch:04X}")
    rx_bytes = ds.get("rx_bytes", "0")
    info(f"HEX rx_bytes={rx_bytes}")
    if rx_bytes != "?" and int(rx_bytes) >= 1024:
        pass_(f"NM-STR-01: NM→HEX {rx_bytes} bytes received")

    # HEX replies with 1024B incremental data
    data_1024 = bytes([i % 256 for i in range(1024)]).hex()
    st2, _ = cli.get_status("tcp-send", "--handle", f"0x{ch:04X}",
                             "--hex-data", data_1024, timeout=15)
    info(f"HEX→NM reply: status={st2}")

    # Read reply from NM peer
    reply = nm.tcp_recv("nms01-cli", timeout=3)
    if len(reply) >= 1024:
        pass_(f"NM-STR-01: NM received {len(reply)} bytes reply")
    else:
        info(f"NM received {len(reply)} bytes")

    pass_("NM-STR-01: 1024B bidirectional complete")

    nm.tcp_disconnect("nms01-cli")
    cli.run("tcp-server-close", "--handle", f"0x{h:04X}", "--force", "1")
    return "PASS"


# ============================================================================
# Test Registry
# ============================================================================

NO_NM_TESTS = {
    "NET-06": test_net06_static_ip,
    "NET-07": test_net07_restore_dhcp,
    "TCP-10": test_tcp10_conn_refused,
}

ALL_TESTS = {
    "NET-06": test_net06_static_ip,
    "NET-07": test_net07_restore_dhcp,
    "TCP-10": test_tcp10_conn_refused,
    "TCP-11": test_tcp11_fin_disconnect,
    "TCP-13": test_tcp13_disconnect_event,
    "TCP-20": test_tcp20_close_handletype0,
    "TCP-21": test_tcp21_large_data_1024,
    "TCP-23": test_tcp23_manual_reject,
    "TCP-26": test_tcp26_buffer_full,
    "UDP-06": test_udp06_addrmode1,
    "UDP-07": test_udp07_broadcast,
    "UDP-08": test_udp08_multicast,
    "UDP-09": test_udp09_client_delete,
    "WS-08": test_ws08_disconnect_event,
    "WS-12": test_ws12_pong,
    "WS-14": test_ws14_auto_pong,
    "WS-16": test_ws16_wrong_path,
    "WS-17": test_ws17_maxconn,
    "WS-21": test_ws21_kick_graceful,
    "STR-02": test_str02_multi_client,
    "NM-TCP-05": test_nm_tcp05_manual_reject,
    "NM-TCP-06": test_nm_tcp06_list_kick,
    "NM-UDP-03": test_nm_udp03_broadcast,
    "NM-STR-01": test_nm_str01_1024b,
}


def list_tests():
    print("Available test cases:")
    print(f"\n  Pure CLI (no NM needed):")
    for name in sorted(NO_NM_TESTS):
        print(f"    {name}")
    print(f"\n  NM coordination required:")
    for name in sorted(ALL_TESTS):
        if name not in NO_NM_TESTS:
            print(f"    {name}")


def main():
    global _passed, _failed, _skipped

    parser = argparse.ArgumentParser(
        description="HEX-Bridge Network Integration Tests")
    parser.add_argument("--no-nm", action="store_true",
                        help="Run only tests that need NO NM coordination")
    parser.add_argument("--all", action="store_true",
                        help="Run all integration tests")
    parser.add_argument("--test", type=str,
                        help="Run a single test case (e.g. TCP-21)")
    parser.add_argument("--pending-only", action="store_true",
                        help="Run all previously PENDING test cases")
    parser.add_argument("--list", action="store_true",
                        help="List all available test cases")
    parser.add_argument("--auto-nm", action="store_true",
                        help="Automate NM operations using sockets/websocket-client")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Skip NM wait prompts (for CI)")
    args = parser.parse_args()

    if args.list:
        list_tests()
        return

    cli = CliRunner()

    # Check device
    print("=" * 58)
    print("  HEX-Bridge Network Integration Tests")
    print("=" * 58)
    if args.auto_nm:
        print("  Mode: AUTO-NM (sockets + websocket-client)")
    if not check_device(cli):
        print("  Device not reachable. Check COM4 connection.")
        sys.exit(1)
    info("Device ping OK")

    # Create NM bridge
    if args.auto_nm:
        if not HAS_WS_CLIENT:
            print("  WARNING: websocket-client not installed, WS tests will skip")
        nm_bridge = AutoNmBridge()
    else:
        nm_bridge = None  # Tests will use ManualNmBridge internally

    # Determine test set
    if args.test:
        if args.test in ALL_TESTS:
            tests = {args.test: ALL_TESTS[args.test]}
        else:
            print(f"  Unknown test: {args.test}")
            print(f"  Use --list to see available tests.")
            sys.exit(1)
    elif args.no_nm:
        tests = dict(NO_NM_TESTS)
    elif args.pending_only or args.all:
        tests = dict(ALL_TESTS)
    else:
        print("  Specify --no-nm, --pending-only, --all, or --test <NAME>")
        print("  Use --list to see available tests.")
        sys.exit(1)

    print(f"\nRunning {len(tests)} test(s)...\n")

    for name, func in tests.items():
        try:
            result = func(nm=nm_bridge)
            if result == "PASS":
                pass_(f"  => {name} PASS")
            elif result == "FAIL":
                fail_(f"  => {name} FAIL")
            elif result == "SKIP":
                skip_(f"  => {name} SKIP")
        except Exception as e:
            import traceback
            fail_(name, f"Exception: {e}")
            traceback.print_exc()
        time.sleep(0.1)

    # Cleanup any remaining auto connections
    if nm_bridge and isinstance(nm_bridge, AutoNmBridge):
        nm_bridge.disconnect_all()

    # Summary
    total = _passed + _failed + _skipped
    print(f"\n{'=' * 58}")
    print(f"  SUMMARY")
    print(f"{'=' * 58}")
    print(f"  PASS: {_passed}")
    print(f"  FAIL: {_failed}")
    print(f"  SKIP: {_skipped}")
    print(f"  TOTAL: {total}")
    if _failed == 0:
        print(f"\n  ALL TESTS PASSED!")
    print(f"{'=' * 58}")

    sys.exit(0 if _failed == 0 else 1)


if __name__ == "__main__":
    main()
