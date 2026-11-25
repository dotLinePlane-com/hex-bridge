"""Run against the installed wheel. Simulates device replies on local TCP."""
import asyncio
import sysconfig
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from hexbridge_mcp.codec import FLAG_DIR, FLAG_EVT, UBCPBuilder, UBCPParser


async def peer(reader, writer):
    parser = UBCPParser()
    try:
        while data := await reader.read(4096):
            for byte in data:
                req = parser.feed(byte)
                if not req:
                    continue
                if req.cmd_code == 1:
                    payload = bytes.fromhex("00 010203 01020304 48584231 0102 0800 02")
                else:
                    payload = b"\x00" + req.payload
                recv_code = {0x54: 0x55, 0x66: 0x65, 0x74: 0x75}.get(req.cmd_code)
                if recv_code:
                    writer.write(UBCPBuilder._build(FLAG_DIR | FLAG_EVT, 0, recv_code, 0, req.payload))
                writer.write(UBCPBuilder._build(FLAG_DIR, req.seq_num, req.cmd_code, req.channel_id, payload))
                await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def run():
    async def dap_peer(reader, writer):
        assert await reader.readexactly(10) == bytes.fromhex("44415000 0200 0100 00ff")
        writer.write(bytes.fromhex("44415000 0400 0200 00020004"))
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    listener = await asyncio.start_server(peer, "127.0.0.1", 0)
    dap = await asyncio.start_server(dap_peer, "127.0.0.1", 0)
    port = listener.sockets[0].getsockname()[1]
    exe = Path(sysconfig.get_path("scripts")) / "hexbridge-mcp"
    params = StdioServerParameters(command=str(exe), args=[
        "--host", "127.0.0.1", "--tcp-port", str(port), "--dap-port", str(dap.sockets[0].getsockname()[1])])
    async with dap, listener, stdio_client(params) as (rx, tx), ClientSession(rx, tx) as client:
        await client.initialize()
        tools = await client.list_tools()
        assert {t.name for t in tools.tools} == {
            "catalog", "device_info", "protocol_guide", "request", "next_event", "disconnect", "dap_info"}

        async def call(name, **args):
            result = await client.call_tool(name, args)
            assert not result.isError, result.content
            return result.structuredContent

        info = await call("catalog")
        for topic in info["guides"]:
            assert (await call("protocol_guide", topic=topic))["text"]
        assert (await call("device_info"))["model"] == "HXB1"
        assert (await call("dap_info"))["data_hex"] == "0004"
        for cmd, event in [("TCP_SEND", "TCP_RECV"), ("UDP_CLIENT_SEND", "UDP_RECV"), ("WS_SEND", "WS_RECV")]:
            reply = await call("request", command=cmd, payload_hex="7e7d")
            assert reply["payload_hex"] == "007e7d"
            received = (await call("next_event"))["event"]
            assert received["name"] == event and received["payload_hex"] == "7e7d"
        assert (await call("next_event"))["event"] is None
        for cmd in ["TCP_RECV", "BULK_START", "OTA_BEGIN"]:
            assert (await client.call_tool("request", {"command": cmd})).isError
        await call("disconnect")
        assert (await call("device_info"))["protocol"] == 2
    print("PASS: installed wheel, MCP stdio, protocol guides, simulated UBCP socket requests/events, reconnect")


if __name__ == "__main__":
    asyncio.run(run())
