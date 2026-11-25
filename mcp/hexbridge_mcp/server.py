import argparse
import socket
import struct
from contextlib import contextmanager
from threading import Lock
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .catalog import ASSETS, EVENTS, GUIDES, REQUEST_GROUPS, REQUESTS
from .link import Link


def create_server(args):
    server = FastMCP("HEX-Bridge", instructions="Use catalog for commands and protocol_guide for payload layouts. Query device_info and GET_TOPOLOGY for the attached board.")
    lock = Lock()
    link = None

    def close():
        nonlocal link
        if link is not None:
            link.close()
            link = None

    @contextmanager
    def session():
        nonlocal link
        with lock:
            if link is None:
                link = Link(args.serial, args.baud, args.host, args.tcp_port)
            try:
                yield link
            except TimeoutError:
                raise
            except OSError:
                close()
                raise

    @server.tool()
    def catalog() -> dict[str, Any]:
        """List supported requests by module, incoming event names, and protocol guide topics (offline)."""
        return {"requests": {k: v.split() for k, v in REQUEST_GROUPS.items()},
                "events": list(EVENTS.values()), "guides": list(GUIDES)}

    @server.tool()
    def protocol_guide(topic: str, offset: Annotated[int, Field(ge=0)] = 0) -> dict[str, Any]:
        """Read the bundled protocol chapter by topic from catalog. Continue at next_offset."""
        if topic not in GUIDES:
            raise ValueError("Unknown topic. See catalog.guides")
        doc = ASSETS.joinpath("protocol", GUIDES[topic] + ".md").read_text(encoding="utf-8")
        end = offset + 8000
        return {"text": doc[offset:end], "next_offset": end if end < len(doc) else None}

    @server.tool()
    def request(command: str, channel: Annotated[int, Field(ge=0, le=255)] = 0,
                payload_hex: Annotated[str, Field(max_length=8192)] = "",
                timeout_s: Annotated[float, Field(gt=0, le=60)] = 5) -> dict[str, Any]:
        """Send one named UBCP request. Use protocol_guide for payload and channel. Status 0 means success. Nonzero status is a firmware error. payload_hex in the reply includes status."""
        name = command.upper()
        if name not in REQUESTS:
            raise ValueError("Unknown request. See catalog.requests")
        data = bytes.fromhex(payload_hex)
        if len(data) > 2048:
            raise ValueError("UBCP payload exceeds 2048 bytes")
        with session() as device:
            frame = device.request(REQUESTS[name], channel, data, timeout_s)
        if not frame.payload:
            raise ValueError("Empty device response")
        return {"command": name, "channel": frame.channel_id, "seq": frame.seq_num,
                "status": frame.payload[0], "payload_hex": frame.payload.hex()}

    @server.tool()
    def device_info() -> dict[str, Any]:
        """Read model, firmware version, serial number, capabilities and UBCP version."""
        result = request("GET_INFO")
        if result["status"]:
            return result
        raw = bytes.fromhex(result["payload_hex"])
        if len(raw) < 17:
            raise ValueError("Truncated GET_INFO response")
        return {"model": raw[8:12].decode("ascii"), "serial_number": raw[4:8].hex(),
                "firmware": ".".join(map(str, raw[1:4])), "protocol": raw[16],
                "capabilities": int.from_bytes(raw[12:14], "big"),
                "max_payload": int.from_bytes(raw[14:16], "big")}

    @server.tool()
    def next_event(timeout_s: Annotated[float, Field(ge=0, le=60)] = 0) -> dict[str, Any]:
        """Read the oldest queued device event. Null means no event before timeout."""
        with session() as device:
            frame, dropped = device.next_event(timeout_s)
        event = None
        if frame:
            event = {"name": EVENTS.get(frame.cmd_code), "code": frame.cmd_code,
                     "seq": frame.seq_num, "channel": frame.channel_id,
                     "timestamp": frame.timestamp, "payload_hex": frame.payload.hex()}
        return {"event": event, "dropped_since_last_read": dropped}

    @server.tool()
    def dap_info(info_id: Annotated[int, Field(ge=0, le=255)] = 255) -> dict[str, Any]:
        """Read CMSIS-DAP probe metadata over its separate TCP service (default ID 255 queries packet size)."""
        host = args.dap_host or args.host
        if not host:
            raise ValueError("Set --dap-host to the board IP for the TCP probe")
        with socket.create_connection((host, args.dap_port), timeout=3) as sock:
            sock.sendall(struct.pack("<4sHBBBB", b"DAP\0", 2, 1, 0, 0, info_id))
            with sock.makefile("rb") as stream:
                header = stream.read(8)
                if len(header) != 8:
                    raise ConnectionError("Truncated DAP header")
                magic, size, kind, reserved = struct.unpack("<4sHBB", header)
                if magic != b"DAP\0" or kind != 2 or reserved or not 2 <= size <= 1024:
                    raise ValueError("Invalid DAP response header")
                data = stream.read(size)
        if len(data) != size or data[0] != 0 or data[1] != size - 2:
            raise ValueError("Invalid DAP_Info response")
        return {"info_id": info_id, "data_hex": data[2:].hex()}

    @server.tool()
    def disconnect() -> str:
        """Close the active hardware connection and discard its queued events."""
        with lock:
            close()
        return "Disconnected"

    return server, disconnect


def main():
    parser = argparse.ArgumentParser(description="HEX-Bridge stdio MCP server")
    endpoint = parser.add_mutually_exclusive_group()
    endpoint.add_argument("--serial", default="COM4")
    endpoint.add_argument("--host", help="Board hostname/IP for UBCP over TCP")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--tcp-port", type=int, default=9500)
    parser.add_argument("--dap-host", help="CMSIS-DAP board address (defaults to --host)")
    parser.add_argument("--dap-port", type=int, default=4441)
    server, close = create_server(parser.parse_args())
    try:
        server.run(transport="stdio")
    finally:
        close()
