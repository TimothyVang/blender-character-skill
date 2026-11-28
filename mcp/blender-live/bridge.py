"""blender-live bridge: runs INSIDE a GUI Blender and serves JSON requests on 127.0.0.1:BLENDER_LIVE_PORT (9876).

  blender.exe [file.blend] --python tools/blender-live/bridge.py

Newline-delimited JSON over TCP. A socket thread queues each request; a persistent bpy.app.timers pump runs it on
Blender's main thread (bpy is not thread-safe) and hands the reply back. Loopback only. Survives file loads.
The commands live in live_core.py (core) and sculpt_cmds.py (sculpt, paint, review); long ones run in slices so
Blender keeps redrawing. blender-mcp-plus serves the same commands from its addon.
"""
import hmac, json, os, queue, socket, threading

import bpy

HOST, PORT = "127.0.0.1", int(os.environ.get("BLENDER_LIVE_PORT", "9876"))
TOKEN = os.environ.get("BLENDER_LIVE_TOKEN", "")
REQ: "queue.Queue" = queue.Queue()


# ------------------------------------------------------------------ socket side (background thread)
def _handle(conn):
    with conn:
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(1 << 20)
            if not chunk: return
            buf += chunk
        req = json.loads(buf.split(b"\n", 1)[0])
        if TOKEN and not hmac.compare_digest(str(req.get("token", "")), TOKEN):
            conn.sendall(json.dumps({"ok": False, "error": "unauthorized: invalid BLENDER_LIVE_TOKEN"}).encode() + b"\n")
            return
        done, box = threading.Event(), {}
        REQ.put((req, done, box))
        if not done.wait(timeout=float(req.get("timeout", 300))):
            box = {"ok": False, "error": "timed out waiting for Blender's main thread (a modal operator or long render?)"}
        conn.sendall(json.dumps(box).encode() + b"\n")


def _serve():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT)); s.listen(8)
    while True:
        conn, _ = s.accept()
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_core

JOBS = live_core.SlicedJobs("blender-live")


def _reply(done, box):
    def on_done(result, exc, trace):
        if exc is None: box.update({"ok": True, **(result or {})})
        else: box.update({"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": trace})
        done.set()
    return on_done


def _pump():
    """Run queued commands on Blender's main thread; long (generator) commands run in slices between redraws."""
    while not REQ.empty():
        req, done, box = REQ.get()
        JOBS.start(lambda req=req: live_core.run(req["cmd"], req), _reply(done, box))
    return 0.01 if JOBS.step() else 0.05


if not bpy.app.driver_namespace.get("_blender_live_started"):         # bpy.app is read-only; driver_namespace persists per session
    threading.Thread(target=_serve, daemon=True).start()
    bpy.app.timers.register(_pump, persistent=True)
    bpy.app.driver_namespace["_blender_live_started"] = True
    print(f"BLENDER_LIVE_READY {HOST}:{PORT} tmp={live_core.TMP}")
