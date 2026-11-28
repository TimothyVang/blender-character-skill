"""blender-mcp-plus server side: the addon connection and running tools off the event loop."""

import asyncio
import json
import socket
import threading
import time

import pytest
from mcp.server.fastmcp import FastMCP

from blender_mcp import plus_tools


def _fake_addon(replies):
    """An IPv4-only addon on 127.0.0.1 that answers each connection with the next reply, split in two packets."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0)); srv.listen(4)
    received = []

    def serve():
        for reply in replies:
            conn, _ = srv.accept()
            with conn:
                received.append(json.loads(conn.recv(65536).decode()))
                data = json.dumps(reply).encode()
                conn.sendall(data[:7]); time.sleep(0.05); conn.sendall(data[7:])
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], received


def test_send_returns_the_addon_result_reassembled_and_reaches_an_ipv4_addon_quickly(monkeypatch):
    port, received = _fake_addon([{"status": "success", "result": {"pong": True, "big": "x" * 5000}}])
    monkeypatch.setattr(plus_tools, "_address", lambda: ("localhost", port))
    t = time.time()
    assert plus_tools.send("live", {"cmd": "ping", "req": {}}, timeout=5)["pong"] is True
    assert time.time() - t < 1.0
    assert received == [{"type": "live", "params": {"cmd": "ping", "req": {}}}]


def test_send_raises_the_addon_error(monkeypatch):
    port, _ = _fake_addon([{"status": "error", "message": "no object named 'Nope'"}])
    monkeypatch.setattr(plus_tools, "_address", lambda: ("127.0.0.1", port))
    with pytest.raises(RuntimeError, match="no object named 'Nope'"):
        plus_tools.send("scene_observe", {}, timeout=5)


def test_a_slow_plus_tool_does_not_stall_other_tools_and_keeps_its_schema():
    mcp = FastMCP("t")

    def slow_paint(object: str, tex_size: int = 1024) -> dict:
        """paints slowly"""
        time.sleep(0.8)
        return {"object": object, "tex_size": tex_size}

    async def quick() -> str:
        return "quick"

    mcp.tool()(plus_tools._off_loop(slow_paint))
    mcp.tool()(quick)

    async def both():
        done = []

        async def call(name, args):
            await mcp.call_tool(name, args); done.append(name)

        async def quick_later():
            await asyncio.sleep(0.1)
            await call("quick", {})

        await asyncio.gather(call("slow_paint", {"object": "CHARACTER", "tex_size": 512}), quick_later())
        return done

    assert asyncio.run(both()) == ["quick", "slow_paint"]
    schema = {t.name: t.inputSchema for t in asyncio.run(mcp.list_tools())}["slow_paint"]
    assert set(schema["properties"]) == {"object", "tex_size"} and schema["required"] == ["object"]
