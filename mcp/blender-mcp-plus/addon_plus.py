"""blender-mcp-plus additions served by the forked MCP for Blender addon (addon.py), on Blender's main thread.

- live: any blender-live command (sculpt, paint, likeness captures, viewport) from ../blender-live/live_core.py.
  A long one returns a generator; the addon runs it in slices so Blender keeps redrawing.
- scene_observe / scene_act: the app-automation-relay's verified scene actions (select, move, frame, save), each
  checked against the observed revision and read back, through its own Relay and Scene classes.
- relay_arm: start the relay's automatic attachment in this Blender, so the separate blender_scene MCP sees it too.

Paths: BLENDER_LIVE_DIR (default ../blender-live next to this file) and DMB_SCENE_ASSETS (default the installed
app-automation-relay assets).
"""
import os
import secrets
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
_INSTALLED = os.path.join(HERE, "live_dir.txt")          # written by install_addon.py next to an installed copy
LIVE_DIR = (os.environ.get("BLENDER_LIVE_DIR")
            or (open(_INSTALLED, encoding="utf-8").read().strip() if os.path.isfile(_INSTALLED) else "")
            or os.path.join(HERE, "..", "blender-live"))
RELAY_DIR = os.environ.get("DMB_SCENE_ASSETS") or os.path.join(
    os.path.expanduser("~"), ".omp", "agent", "skills", "app-automation-relay", "assets")


def _path(d):
    d = os.path.abspath(d)
    if not os.path.isdir(d):
        raise RuntimeError(f"{d} not found")
    if d not in sys.path:
        sys.path.insert(0, d)


def _live_core():
    _path(LIVE_DIR)
    import live_core
    return live_core


_JOBS = []


def jobs():
    """The addon's sliced-job runner (one per Blender session)."""
    if not _JOBS:
        _JOBS.append(_live_core().SlicedJobs("blender-mcp-plus"))
    return _JOBS[0]


def live(cmd, req=None):
    """Run a blender-live command: its result dict, or a generator for a long command."""
    return _live_core().run(str(cmd), dict(req or {}))


_RELAY = []


def _relay():
    """The relay pinned to the open document; re-pinned when the document changes."""
    import bpy
    if _RELAY:
        r = _RELAY[0]
        if not r.scene.closed and r.scene.path == bpy.data.filepath:
            return r
        r.scene.close(); _RELAY.clear()
    _path(RELAY_DIR)
    from scene_blender import Scene
    from scene_relay import Relay
    _RELAY.append(Relay("blender", Scene(), secrets.token_urlsafe(16)))
    return _RELAY[0]


def _dispatch(op, args):
    r = _relay()
    coro = r.dispatch({"engine": "blender", "expires": int(time.time() * 1000) + 5000, "op": op,
                       "args": {"targetId": r.target, **args}})
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    coro.close()
    raise RuntimeError(f"relay {op} did not complete in one step")


def scene_observe(include_text=False):
    """Elements (Save, Current frame, Select <object>, <object> position, Undo relay move) with ids and the revision."""
    return _dispatch("observe", {"includeText": bool(include_text)})


def scene_act(revision, id, op, value=None):
    """One advertised action on an observed element; refused on a stale revision, confirmed by readback."""
    return _dispatch("act", {"revision": int(revision), "id": int(id), "op": str(op),
                             **({"value": str(value)} if value is not None else {})})


def relay_arm():
    """Start the relay's automatic attachment here. Its startup hook skips any Blender started with --python;
    this one is interactive, so arm it explicitly."""
    import bpy
    _path(RELAY_DIR)
    import scene_startup
    from runpy import run_path
    if scene_startup._watcher is None:
        scene_startup._interactive_blender = lambda b: not b.app.background
        run_path(os.path.join(RELAY_DIR, "scene_bootstrap.py"))["install"]("blender")
    return {"armed": scene_startup._watcher is not None, "last_error": scene_startup.last_error,
            "document": bpy.data.filepath or None}


def handlers():
    return {"live": live, "scene_observe": scene_observe, "scene_act": scene_act, "relay_arm": relay_arm}
