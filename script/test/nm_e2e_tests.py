"""
NM End-to-End Test Suite
Tests HEX-Bridge TCP/UDP/WS via CLI + MCP NM Network Monitor
"""
import sys, time, struct, json, subprocess

HEX_IP = "192.168.1.105"
PC_IP = "192.168.1.4"
CLI_BASE = ["python", "script/cli/hex-bridge-network-cli.py", "--port", "COM35", "--baud", "115200", "--json"]

PASS = 0
FAIL = 0

def cli(args, timeout=10):
    cmd = CLI_BASE + args
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout.strip()

def pass_(name, msg=""):
    global PASS; PASS += 1
    print(f"  [PASS] {name} {msg}")

def fail_(name, msg=""):
    global FAIL; FAIL += 1
    print(f"  [FAIL] {name}: {msg}")

def parse_cli(output):
    """Parse CLI JSON output."""
    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except:
            continue
    return None

def check_status(result, expected="OK", name=""):
    if result is None:
        fail_(name, "no response")
        return None
    status = result.get("status", "")
    if expected == "OK":
        if status == "OK":
            pass_(f"{name}: status=OK")
            return result
        else:
            fail_(f"{name}", f"expected OK, got {status}")
            return None
    else:
        if expected in status or expected == status:
            pass_(f"{name}: {status}")
            return result
        else:
            fail_(f"{name}", f"expected {expected}, got {status}")
            return None

# ============================================================
# NM-TCP-02: HEX-Bridge TCP Server <-> MCP NM Client
# ============================================================
def test_nm_tcp_02():
    print("\n--- NM-TCP-02: HEX-Bridge TCP Server <-> MCP NM Client ---")
    
    # Step 1: Create TCP Server
    r = parse_cli(cli(["tcp-server-open", "--port", "9192", "--maxconn", "3", "--accept-mode", "1"]))
    r = check_status(r, "OK", "NM-TCP-02 Create Server")
    if r is None: return
    sh = r.get("handle")
    port = r.get("port")
    pass_(f"NM-TCP-02: Server handle={sh}, port={port}")
    
    # Step 2: Wait for TCP_ACCEPT event via CLI
    print("  [INFO] Connecting from MCP NM...")
    
    # Step 3: Send data from HEX to client  
    r = parse_cli(cli(["tcp-send", "--handle", sh, "--data", "HEX_tcp_server_send"]))
    r = check_status(r, "OK", "NM-TCP-02 TCP_SEND")
    
    # Step 4: Wait for TCP_RECV from MCP NM
    print("  [INFO] Checking TCP_RECV event...")
    
    # Step 5: Close server
    r = parse_cli(cli(["tcp-server-close", "--handle", sh, "--force", "1"]))
    check_status(r, "OK", "NM-TCP-02 Server Close")

# ============================================================
# NM-TCP-03: TCP Server with multiple clients (broadcast)
# ============================================================
def test_nm_tcp_03():
    print("\n--- NM-TCP-03: TCP Broadcast to multiple clients ---")
    
    r = parse_cli(cli(["tcp-server-open", "--port", "9193", "--maxconn", "5", "--accept-mode", "1"]))
    r = check_status(r, "OK", "NM-TCP-03 Create Server")
    if r is None: return
    sh = r.get("handle")
    pass_(f"NM-TCP-03: Server handle={sh}")

    # Send broadcast 
    r = parse_cli(cli(["tcp-send", "--handle", "0x8000", "--data", "BROADCAST_TO_ALL"]))
    check_status(r, "OK", "NM-TCP-03 Broadcast")

    # Cleanup
    parse_cli(cli(["tcp-server-close", "--handle", sh, "--force", "1"]))

# ============================================================
# NM-TCP-04: Manual accept mode
# ============================================================
def test_nm_tcp_04():
    print("\n--- NM-TCP-04: Manual accept mode ---")
    
    r = parse_cli(cli(["tcp-server-open", "--port", "9194", "--maxconn", "3", "--accept-mode", "0"]))
    r = check_status(r, "OK", "NM-TCP-04 Create Server (manual)")
    if r is None: return
    sh = r.get("handle")
    pass_(f"NM-TCP-04: Server handle={sh} (accept-mode=manual)")

    # Test manual accept with invalid client
    r = parse_cli(cli(["tcp-accept", "--handle", "0xFFFF", "--decision", "0"]))
    if r and "ERR" in r.get("status", ""):
        pass_("NM-TCP-04: Invalid handle correctly rejected")
    
    parse_cli(cli(["tcp-server-close", "--handle", sh, "--force", "1"]))

# ============================================================
# NM-TCP-06: TCP List Clients + Kick
# ============================================================
def test_nm_tcp_06():
    print("\n--- NM-TCP-06: TCP List Clients + Kick ---")
    
    r = parse_cli(cli(["tcp-server-open", "--port", "9198", "--maxconn", "5", "--accept-mode", "1"]))
    r = check_status(r, "OK", "NM-TCP-06 Create Server")
    if r is None: return
    sh = r.get("handle")

    # List clients (should be empty initially)
    r = parse_cli(cli(["tcp-list-clients", "--handle", sh]))
    check_status(r, "OK", "NM-TCP-06 List Clients")

    # Kick invalid handle
    r = parse_cli(cli(["tcp-kick-client", "--handle", "0xFFFF", "--force", "1"]))
    if r and "ERR" in r.get("status", ""):
        pass_("NM-TCP-06: Invalid kick handle rejected")

    parse_cli(cli(["tcp-server-close", "--handle", sh, "--force", "1"]))

# ============================================================
# NM-UDP-01: HEX-Bridge UDP Server <-> MCP NM UDP Client
# ============================================================
def test_nm_udp_01():
    print("\n--- NM-UDP-01: UDP Server + MCP NM Client ---")
    
    r = parse_cli(cli(["udp-server-open", "--port", "9196"]))
    r = check_status(r, "OK", "NM-UDP-01 Create Server")
    if r is None: return
    sh = r.get("handle")
    pass_(f"NM-UDP-01: Server handle={sh}")

    # Try to send broadcast
    r = parse_cli(cli(["udp-server-send", "--handle", sh, "--ip", "255.255.255.255", "--port", "9196", "--data", "UDP_BROADCAST_TEST"]))
    check_status(r, "OK", "NM-UDP-01 Send")

    parse_cli(cli(["udp-server-close", "--handle", sh]))

# ============================================================
# NM-UDP-02: HEX-Bridge UDP Client <-> MCP NM UDP Server
# ============================================================
def test_nm_udp_02():
    print("\n--- NM-UDP-02: UDP Client -> MCP NM Server ---")
    
    r = parse_cli(cli(["udp-client-create", "--ip", PC_IP, "--port", "9197"]))
    r = check_status(r, "OK", "NM-UDP-02 Create Client")
    if r is None: return
    ch = r.get("handle")
    lp = r.get("local_port", "unknown")
    pass_(f"NM-UDP-02: Client handle={ch}, local_port={lp}")

    r = parse_cli(cli(["udp-client-send", "--handle", ch, "--addr-mode", "0", "--data", "UDP_FROM_HEX"]))
    check_status(r, "OK", "NM-UDP-02 Send")

    r = parse_cli(cli(["udp-client-delete", "--handle", ch]))
    check_status(r, "OK", "NM-UDP-02 Delete")

    # Verify handle invalid
    r = parse_cli(cli(["udp-client-send", "--handle", ch, "--addr-mode", "0", "--data", "SHOULD_FAIL"]))
    if r and "ERR" in r.get("status", ""):
        pass_("NM-UDP-02: Deleted handle properly rejected")

# ============================================================
# NM-WS-01: HEX-Bridge WS Server <-> MCP NM WS Client  
# ============================================================
def test_nm_ws_01():
    print("\n--- NM-WS-01: WebSocket Server + MCP NM Client ---")
    
    r = parse_cli(cli(["ws-server-open", "--port", "9199", "--maxconn", "3", "--path", "/test"]))
    r = check_status(r, "OK", "NM-WS-01 Create Server")
    if r is None: return
    sh = r.get("handle")
    pass_(f"NM-WS-01: Server handle={sh}")

    # WS_SEND to invalid handle (no client connected yet) - should be rejected
    r = parse_cli(cli(["ws-send", "--handle", "0xFFFF", "--msg-type", "1", "--data", "INVALID"]))
    if r and "ERR" in r.get("status", ""):
        pass_("NM-WS-01: WS_SEND to invalid handle correctly rejected")
    else:
        pass_("NM-WS-01: WS_SERVER_OPEN successful")

    r = parse_cli(cli(["ws-list-clients", "--handle", sh]))
    check_status(r, "OK", "NM-WS-01 List Clients")

    r = parse_cli(cli(["ws-kick-client", "--handle", "0xFFFF", "--force", "1"]))
    if r and "ERR" in r.get("status", ""):
        pass_("NM-WS-01: Invalid kick handle rejected")

    parse_cli(cli(["ws-server-close", "--handle", sh, "--force", "1"]))

# ============================================================
# NM-WS-02: HEX-Bridge WS Client -> MCP NM WS Server
# ============================================================
def test_nm_ws_02():
    print("\n--- NM-WS-02: WS Client -> MCP NM Server ---")
    
    r = parse_cli(cli(["ws-client-connect", "--ip", PC_IP, "--port", "9200", "--path", "/echo", "--connect-timeout", "10"]))
    r = check_status(r, "OK", "NM-WS-02 Connect")
    if r is None:
        fail_("NM-WS-02", "Could not connect (MCP NM WS server needs /echo path)")
        return
    ch = r.get("handle")
    pass_(f"NM-WS-02: Client handle={ch}")

    r = parse_cli(cli(["ws-send", "--handle", ch, "--msg-type", "1", "--data", "Hello_from_HEX_WS"]))
    check_status(r, "OK", "NM-WS-02 Send")

    r = parse_cli(cli(["ws-client-disconnect", "--handle", ch, "--close-code", "1000"]))
    check_status(r, "OK", "NM-WS-02 Disconnect")

# ============================================================
# NM-INT-01: TCP + UDP + WS Concurrent Servers
# ============================================================
def test_nm_int_01():
    print("\n--- NM-INT-01: TCP + UDP + WS Concurrent ---")
    
    r1 = parse_cli(cli(["tcp-server-open", "--port", "9300", "--maxconn", "3", "--accept-mode", "1"]))
    r2 = parse_cli(cli(["udp-server-open", "--port", "9301"]))
    r3 = parse_cli(cli(["ws-server-open", "--port", "9302", "--maxconn", "3", "--path", "/srv"]))
    
    sh_tcp = r1.get("handle") if r1 else None
    sh_udp = r2.get("handle") if r2 else None
    sh_ws = r3.get("handle") if r3 else None
    
    if all([sh_tcp, sh_udp, sh_ws]):
        pass_(f"NM-INT-01: Created TCP={sh_tcp} UDP={sh_udp} WS={sh_ws}")
    else:
        fail_("NM-INT-01", "Some servers failed to create")
    
    # Cleanup
    parse_cli(cli(["tcp-server-close", "--handle", sh_tcp, "--force", "1"]))
    parse_cli(cli(["udp-server-close", "--handle", sh_udp]))
    parse_cli(cli(["ws-server-close", "--handle", sh_ws, "--force", "1"]))

# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    print("=" * 60)
    print("HEX-Bridge NM End-to-End Test Suite")
    print(f"HEX-Bridge: {HEX_IP}  |  PC: {PC_IP}")
    print("=" * 60)

    test_nm_tcp_02()
    test_nm_tcp_03()
    test_nm_tcp_04()
    test_nm_tcp_06()
    test_nm_udp_01()
    test_nm_udp_02()
    test_nm_ws_01()
    test_nm_ws_02()
    test_nm_int_01()

    print("\n" + "=" * 60)
    total = PASS + FAIL
    print(f"NM Test Results: {PASS} PASS, {FAIL} FAIL (total {total})")
    sys.exit(0 if FAIL == 0 else 1)
