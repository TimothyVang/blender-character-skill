"""blender-mcp-plus tools registered on top of MCP for Blender's server.

- blender-live's likeness, paint and sculpt tools (outline_match, visual_match, orbit_check, three_quarter_check,
  project_paint, fit_outline, sculpt_*, mesh_report, reference_setup, turnaround_sheet, compare_images), the same
  functions as blender-live's own server, sent to the forked addon's `live` handler.
- scene_observe / scene_act: the app-automation-relay's verified scene actions, through the addon.
- watch: point the person's viewport at the work with the reference picture beside it, and return what they see.

Each call opens its own connection to the addon with its own timeout, so a long paint never holds the shared
connection the upstream tools use; the addon runs long commands in slices, so those tools keep answering meanwhile.
"""
import base64
import functools
import inspect
import io
import json
import os
import socket
import sys
from typing import Callable

import anyio

from mcp.types import CallToolResult, ImageContent, TextContent

HERE = os.path.dirname(os.path.abspath(__file__))
LIVE_DIR = os.environ.get("BLENDER_LIVE_DIR") or os.path.join(HERE, "..", "..", "..", "blender-live")
LIVE_TOOLS = ("outline_match", "visual_match", "orbit_check", "three_quarter_check", "project_paint", "fit_outline",
              "sculpt_begin", "sculpt_strokes", "sculpt_remesh", "sculpt_relax", "sculpt_mask", "mesh_report",
              "reference_setup", "turnaround_sheet", "compare_images")
# Parts of a standing figure for watch(): fraction of its height from the top (start, end).
PARTS = {"full": (0.0, 1.0), "head": (0.0, 0.24), "body": (0.18, 0.62), "legs": (0.55, 1.0)}

_address: Callable[[], tuple] = lambda: ("localhost", 9879)


def send(command_type: str, params: dict, timeout: float = 300.0) -> dict:
    """One command to the forked addon on a connection of its own; the addon's result, or RuntimeError."""
    host, port = _address()
    if host == "localhost":
        host = "127.0.0.1"          # the addon listens on IPv4; "localhost" tries ::1 first and stalls 2 s on Windows
    with socket.create_connection((host, port), timeout=10.0) as s:
        s.settimeout(timeout)
        s.sendall(json.dumps({"type": command_type, "params": params}).encode("utf-8"))
        buf = b""
        while True:
            chunk = s.recv(1 << 20)
            if not chunk:
                raise ConnectionError("Blender closed the connection before replying")
            buf += chunk
            try:
                reply = json.loads(buf.decode("utf-8"))
                break
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    if reply.get("status") == "error":
        raise RuntimeError(reply.get("message", "Blender reported an error"))
    return reply.get("result") or {}


def live_call(cmd: str, timeout: float = 300.0, **req) -> dict:
    """blender-live's `call` contract (raise on failure, return the reply dict) over the forked addon."""
    return {"ok": True, **send("live", {"cmd": cmd, "req": req}, timeout=float(timeout))}


def _blender_live_server():
    d = os.path.abspath(LIVE_DIR)
    if d not in sys.path:
        sys.path.insert(0, d)
    import importlib.util
    spec = importlib.util.spec_from_file_location("blender_live_server", os.path.join(d, "server.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.call = live_call
    return mod


def watch(reference: str = "", azimuth: float = 0.0, elevation: float = 0.0, object: str = "",
          centre: list[float] | None = None, distance: float = 1.5, part: str = "full",
          max_px: int = 1600) -> CallToolResult:
    """SHOW the work to the person and to yourself: points the person's own 3D viewport (Material Preview, perspective)
    at `object` (or `centre`) from azimuth/elevation (0 = FRONT, 90 = Blender RIGHT) and `distance`, opens
    `reference` (the picture being matched, a file path) in an Image Editor beside it, and returns what they now
    see: the viewport next to the same `part` of the picture (full, head, body, legs). Call it before and after a
    change, from the angle the change shows at; nothing in the scene changes."""
    from PIL import Image
    try:
        view = send("live", {"cmd": "watch_view", "req": {
            "reference": reference, "azimuth": azimuth, "elevation": elevation, "object": object,
            "centre": centre, "distance": distance}}, timeout=60)
        shot = send("live", {"cmd": "capture", "req": {"redraws": 3, "overlays": True}}, timeout=60)
    except Exception as exc:
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({"status": "error", "detail": str(exc)}))],
                              isError=True)
    vp = Image.open(io.BytesIO(base64.b64decode(shot["png_b64"]))).convert("RGB")
    panels = [vp]
    if reference:
        ref = Image.open(reference).convert("RGBA")
        bbox = ref.getchannel("A").point(lambda a: 255 if a > 128 else 0).getbbox() or (0, 0, ref.width, ref.height)
        top, bottom = PARTS.get(part, PARTS["full"])
        h = bbox[3] - bbox[1]
        crop = ref.crop((bbox[0], bbox[1] + int(top * h), bbox[2], bbox[1] + int(bottom * h)))
        bg = Image.new("RGB", crop.size, (255, 255, 255)); bg.paste(crop, mask=crop.getchannel("A"))
        panels.append(bg)
    height = min(max(p.height for p in panels), max_px)
    panels = [p.resize((max(1, int(p.width * height / p.height)), height), Image.LANCZOS) for p in panels]
    sheet = Image.new("RGB", (sum(p.width for p in panels) + 8 * (len(panels) - 1), height), (24, 24, 28))
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0)); x += p.width + 8
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    meta = {"status": "shown", **view, "capture_path": shot.get("path")}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(meta)),
                                   ImageContent(type="image", data=base64.b64encode(buf.getvalue()).decode(),
                                                mimeType="image/png")])


def scene_observe(include_text: bool = False) -> dict:
    """OBSERVE the open .blend through the scene relay: elements (Save, Current frame, Select <object>,
    <object> position, Undo relay move), each with an id, its advertised actions and states, and the revision every
    scene_act must quote. Re-observe after any change or a stale-revision refusal."""
    return send("scene_observe", {"include_text": bool(include_text)}, timeout=60)


def scene_act(revision: int, id: int, op: str, value: str | None = None) -> dict:
    """ACT on one observed element with one of its advertised actions (invoke Select/Save/Undo, fill a position as a
    JSON [x, y, z] string or the frame as an integer string). Refused when `revision` is stale; on success Blender
    has applied it and read it back (outcome "confirmed"). An unknown outcome means observe before acting again."""
    args = {"revision": int(revision), "id": int(id), "op": str(op)}
    if value is not None:
        args["value"] = str(value)
    return send("scene_act", args, timeout=60)


def relay_arm() -> dict:
    """Start the scene relay's automatic attachment in this Blender, so the separate blender_scene MCP lists it."""
    return send("relay_arm", {}, timeout=60)


def _off_loop(fn):
    """`fn` as an async tool that runs in a worker thread: FastMCP calls a plain function on its event loop, so a
    paint waiting a minute on Blender would stall every other tool call (upstream's included) until it returned."""
    @functools.wraps(fn)
    async def tool(**kwargs):
        return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))
    tool.__signature__ = inspect.signature(fn)
    return tool


def register(mcp, address: Callable[[], tuple]) -> list[str]:
    """Register the plus tools on `mcp`; `address()` gives the addon's (host, port). Returns the tool names."""
    global _address
    _address = address
    bl = _blender_live_server()
    fns = [watch, scene_observe, scene_act, relay_arm] + [getattr(bl, name) for name in LIVE_TOOLS]
    for fn in fns:
        mcp.tool()(_off_loop(fn))
    return [fn.__name__ for fn in fns]
