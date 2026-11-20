import argparse
import ipaddress
import os
from pathlib import Path
import subprocess
import sys
import time

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT / "script" / "test"))
from mcp_transport import MCPTransport
from ubcp_client import UBCPBuilder

SSID = b"CU_Jm2v"
REASONS = ["none", "AP not found", "authentication failed", "link lost",
           "IP timeout", "driver error", "profile save failed"]


def credential():
    value = os.environ.get("HEX_BRIDGE_WIFI_PASSWORD")
    if value is not None:
        key = value.encode("ascii")
    else:
        path = PROJECT.parent / ".hex-bridge-private" / "CU_Jm2v.dpapi"
        if not path.is_file():
            raise ValueError("Local Wi-Fi credential unavailable")
        command = ("$ErrorActionPreference='Stop'; "
                   "$b=[IO.File]::ReadAllBytes($env:HEX_WIFI_BLOB); "
                   "$k=[Security.Cryptography.ProtectedData]::Unprotect($b,$null,'LocalMachine'); "
                   "[Console]::OpenStandardOutput().Write($k,0,$k.Length)")
        key = subprocess.check_output(["pwsh", "-NoProfile", "-Command", command],
                                      env=dict(os.environ, HEX_WIFI_BLOB=str(path)))
    if not 8 <= len(key) <= 63 or not all(32 <= c <= 126 for c in key):
        raise ValueError("Invalid WPA2 credential")
    return key


def run(port, save, status_only):
    with MCPTransport(port, 115200) as uart:
        seq = 0

        def request(cmd, payload=b""):
            nonlocal seq
            seq = (seq + 1) % 256
            uart.send(UBCPBuilder.build_request(seq, cmd, 0, payload))
            frame = uart.recv_response(cmd_code=cmd, seq_num=seq)
            if not frame or not frame.is_response or not frame.payload:
                raise ValueError(f"No valid response to {cmd:#04x}")
            if frame.payload[0]:
                raise ValueError(f"Command {cmd:#04x} returned {frame.payload[0]:#04x}")
            return frame.payload

        info = request(0x01)
        if len(info) < 14 or not int.from_bytes(info[12:14], "big") & (1 << 12):
            raise ValueError("Firmware does not advertise WIFI_STA (bit 12)")
        deadline = time.monotonic() + 45
        submitted = False
        while True:
            wifi = request(0x47, b"\0")
            if len(wifi) < 6 or len(wifi) != 6 + wifi[5]:
                raise ValueError("Invalid WIFI_STATUS length")
            state, reason = wifi[1:3]
            target = wifi[6:] == SSID
            detail = REASONS[reason] if reason < len(REASONS) else str(reason)
            if target and state == 3:
                net = request(0x41, b"\0")
                if len(net) == 19 and net[1:5] == bytes([1, 0, 1, 1]) and any(net[5:9]):
                    if save and submitted and reason == 6:
                        raise ValueError("Connected, but saving profile failed")
                    if status_only or not save or submitted:
                        print("CU_Jm2v IPv4", ipaddress.IPv4Address(bytes(net[5:9])))
                        return
            if status_only:
                print(f"state={state} reason={detail} target_match={target} IPv4 unverified")
                return
            if not submitted:
                key = credential()
                request(0x46, bytes([0, int(save), 1, len(SSID), len(key)]) + SSID + key)
                submitted = True
            elif state == 5 or time.monotonic() >= deadline:
                raise ValueError(f"Wi-Fi join unverified: state={state}, reason={detail}")
            time.sleep(0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="COM3")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--save", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = parser.parse_args()
    try:
        run(args.port, args.save, args.status)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        sys.exit(str(exc))
