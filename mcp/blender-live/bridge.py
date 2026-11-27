"""blender-live bridge: runs INSIDE a GUI Blender and serves JSON requests on 127.0.0.1:BLENDER_LIVE_PORT (9876).

  blender.exe [file.blend] --python tools/blender-live/bridge.py

Newline-delimited JSON over TCP. A socket thread queues each request; a persistent bpy.app.timers pump runs it on
Blender's main thread (bpy is not thread-safe) and hands the reply back. Loopback only. Survives file loads.
Commands: ping, exec, scene_tree, object_info, capture, motion_preview, render, set_frame, open_file, save_file,
plus the sculpt and review commands in sculpt_cmds.py (sculpt_begin, sculpt_strokes, sculpt_remesh, sculpt_mask,
mesh_report, reference_setup, turnaround).
Captures go to BLENDER_LIVE_TMP, default <workspace>/.scratch/tmp/blender-live/<pid> (never the system temp folder).
"""
import base64, contextlib, hmac, io, json, os, queue, socket, threading, time, traceback

import bpy

HOST, PORT = "127.0.0.1", int(os.environ.get("BLENDER_LIVE_PORT", "9876"))
TOKEN = os.environ.get("BLENDER_LIVE_TOKEN", "")
REQ: "queue.Queue" = queue.Queue()
TMP = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch", "tmp",
                                                          "blender-live", str(os.getpid()))
TMP = os.path.abspath(TMP); os.makedirs(TMP, exist_ok=True)


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


# ------------------------------------------------------------------ helpers (main thread)
def _view3d():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                region = next(r for r in area.regions if r.type == "WINDOW")
                return win, area, region
    raise RuntimeError("no 3D Viewport is open in any window")


def _png_b64(path):
    with open(path, "rb") as f: return base64.b64encode(f.read()).decode()


def _counts():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    return {"objects": len(bpy.context.scene.objects), "meshes": len(meshes),
            "cameras": [o.name for o in bpy.context.scene.objects if o.type == "CAMERA"][:50],
            "collections": len(bpy.data.collections)}


def cmd_ping(req):
    sc = bpy.context.scene
    return {"blender": bpy.app.version_string, "file": bpy.data.filepath or None, "dirty": bpy.data.is_dirty,
            "scene": sc.name, "frame": sc.frame_current, "frame_range": [sc.frame_start, sc.frame_end],
            "camera": sc.camera.name if sc.camera else None, "engine": sc.render.engine, **_counts()}


def cmd_exec(req):
    ns = {"bpy": bpy, "C": bpy.context, "D": bpy.data, "result": None}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(req["code"], "<blender-live>", "exec"), ns)
    res = ns.get("result")
    try: json.dumps(res)
    except TypeError: res = repr(res)
    return {"result": res, "stdout": out.getvalue()[-20000:]}


def cmd_scene_tree(req):
    depth, limit = int(req.get("depth", 3)), int(req.get("max_objects", 300)); n = [0]
    def walk(c, d):
        node = {"collection": c.name, "objects": [], "children": []}
        if getattr(c, "hide_render", False): node["hide_render"] = True
        for o in c.objects:
            if n[0] >= limit: node["truncated"] = True; break
            n[0] += 1
            e = {"name": o.name, "type": o.type}
            if o.type == "MESH": e["faces"] = len(o.data.polygons)
            if o.instance_type == "COLLECTION" and o.instance_collection: e["instances"] = o.instance_collection.name
            if o.hide_get() or o.hide_render: e["hidden"] = True
            node["objects"].append(e)
        if d < depth: node["children"] = [walk(ch, d + 1) for ch in c.children]
        else: node["children_count"] = len(c.children)
        return node
    return {"tree": walk(bpy.context.scene.collection, 0), "listed": n[0], **_counts()}


def cmd_object_info(req):
    o = bpy.data.objects.get(req["name"])
    if o is None: raise KeyError(f"no object named {req['name']!r}")
    from mathutils import Vector
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    info = {"name": o.name, "type": o.type, "location": list(o.location), "rotation_euler_deg": [round(v * 57.29578, 4) for v in o.rotation_euler],
            "scale": list(o.scale), "dimensions": list(o.dimensions), "parent": o.parent.name if o.parent else None,
            "collections": [c.name for c in o.users_collection], "bounds_min": [min(v[i] for v in bb) for i in range(3)],
            "bounds_max": [max(v[i] for v in bb) for i in range(3)], "hidden": o.hide_get(), "hide_render": o.hide_render,
            "modifiers": [m.type for m in o.modifiers]}
    if o.type == "MESH":
        me = o.data; info.update(vertices=len(me.vertices), faces=len(me.polygons), materials=[m.name if m else None for m in me.materials],
                                uv_layers=[u.name for u in me.uv_layers])
    if o.type == "CAMERA":
        d = o.data; info.update(lens=d.lens, angle_deg=round(d.angle * 57.29578, 4), cam_type=d.type, ortho_scale=d.ortho_scale,
                                shift=[d.shift_x, d.shift_y], clip=[d.clip_start, d.clip_end])
    if o.type == "LIGHT": info.update(light=o.data.type, energy=o.data.energy, color=list(o.data.color))
    return info


def cmd_capture(req):
    """Image of the 3D Viewport after optional view changes: camera, axis view, frame an object, shading, frame.
    Uses the viewport render (render.opengl, view_context) so it works when the window is covered or minimized;
    screen.screenshot_area returned a 1x1 image in that case."""
    win, area, region = _view3d(); sp = area.spaces.active; r3d = sp.region_3d; sc = bpy.context.scene
    keep_camera = sc.camera
    keep_frame = sc.frame_current
    keep_perspective = r3d.view_perspective
    keep_clip_end = sp.clip_end
    keep_selected = list(bpy.context.selected_objects)
    keep_active = bpy.context.view_layer.objects.active
    with bpy.context.temp_override(window=win, area=area, region=region):
        try:
            if req.get("shading"): sp.shading.type = req["shading"]           # WIREFRAME / SOLID / MATERIAL / RENDERED
            if req.get("camera"):
                sc.camera = bpy.data.objects[req["camera"]]
                if r3d.view_perspective != "CAMERA": bpy.ops.view3d.view_camera()
            elif req.get("view"):                                             # TOP / BOTTOM / FRONT / BACK / LEFT / RIGHT
                bpy.ops.view3d.view_axis(type=req["view"])
                bpy.ops.view3d.view_all()
            if req.get("frame_object"):
                o = bpy.data.objects[req["frame_object"]]
                for s in bpy.context.selected_objects: s.select_set(False)
                o.select_set(True); bpy.context.view_layer.objects.active = o
                if r3d.view_perspective == "CAMERA": r3d.view_perspective = "PERSP"
                bpy.ops.view3d.view_selected()
            if req.get("frame") is not None: sc.frame_set(int(req["frame"]))
            sp.clip_end = max(sp.clip_end, float(req.get("clip_end", 20000)))
            for _ in range(int(req.get("redraws", 2))):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            path = os.path.join(TMP, f"capture_{int(time.time() * 1000)}.png")
            r = sc.render; keep = (r.resolution_x, r.resolution_y, r.resolution_percentage); ov = sp.overlay.show_overlays
            if req.get("width"): r.resolution_x, r.resolution_y, r.resolution_percentage = int(req["width"]), int(req["height"]), 100
            sp.overlay.show_overlays = bool(req.get("overlays", False))       # clean image unless overlays are asked for
            try:
                bpy.ops.render.opengl(write_still=False, view_context=True)
                bpy.data.images["Render Result"].save_render(path)
            finally:
                r.resolution_x, r.resolution_y, r.resolution_percentage = keep; sp.overlay.show_overlays = ov
            return {"png_b64": _png_b64(path), "path": path, "shading": sp.shading.type, "perspective": r3d.view_perspective,
                    "camera": sc.camera.name if sc.camera else None}
        finally:
            sc.camera = keep_camera
            sc.frame_set(keep_frame)
            r3d.view_perspective = keep_perspective
            sp.clip_end = keep_clip_end
            for s in list(bpy.context.selected_objects): s.select_set(False)
            for s in keep_selected:
                try: s.select_set(True)
                except ReferenceError: pass
            bpy.context.view_layer.objects.active = keep_active


def cmd_render(req):
    sc = bpy.context.scene; r = sc.render
    keep = (
        r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage,
        r.filepath, sc.camera, r.image_settings.file_format, sc.frame_current,
        sc.eevee.taa_render_samples if hasattr(sc, "eevee") else None,
        sc.cycles.samples if hasattr(sc, "cycles") else None,
    )
    try:
        if req.get("camera"): sc.camera = bpy.data.objects[req["camera"]]
        if req.get("engine"): r.engine = req["engine"]
        if req.get("width"): r.resolution_x = int(req["width"])
        if req.get("height"): r.resolution_y = int(req["height"])
        r.resolution_percentage = int(req.get("percent", 100))
        if req.get("samples") and r.engine.startswith("BLENDER_EEVEE"): sc.eevee.taa_render_samples = int(req["samples"])
        if req.get("samples") and r.engine == "CYCLES": sc.cycles.samples = int(req["samples"])
        if req.get("frame") is not None: sc.frame_set(int(req["frame"]))
        path = req.get("filepath") or os.path.join(TMP, f"render_{int(time.time() * 1000)}.png")
        r.image_settings.file_format = "PNG"; r.filepath = path
        t0 = time.time(); bpy.ops.render.render(write_still=True)
        return {"png_b64": _png_b64(path), "path": path, "seconds": round(time.time() - t0, 2), "engine": r.engine,
                "size": [r.resolution_x, r.resolution_y], "camera": sc.camera.name if sc.camera else None}
    finally:
        if not req.get("keep_settings"):
            (r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage,
             r.filepath, sc.camera, r.image_settings.file_format, keep_frame,
             keep_eevee_samples, keep_cycles_samples) = keep
            sc.frame_set(keep_frame)
            if keep_eevee_samples is not None and hasattr(sc, "eevee"):
                sc.eevee.taa_render_samples = keep_eevee_samples
            if keep_cycles_samples is not None and hasattr(sc, "cycles"):
                sc.cycles.samples = keep_cycles_samples


def cmd_motion_preview(req):
    """Ordered viewport captures at several frames (check animation, camera paths): frames list, or start/end/count."""
    sc = bpy.context.scene
    frames = req.get("frames") or []
    if not frames:
        a, b, n = int(req.get("start", sc.frame_start)), int(req.get("end", sc.frame_end)), max(2, int(req.get("count", 6)))
        frames = sorted({round(a + (b - a) * i / (n - 1)) for i in range(n)})
    keep = sc.frame_current; shots = []
    try:
        for i, f in enumerate(frames):
            c = cmd_capture({**req, "frame": int(f), "camera": req.get("camera") if i == 0 else None, "view": None, "frame_object": None,
                             "width": int(req.get("width", 640)), "height": int(req.get("height", 0)) or round(int(req.get("width", 640)) * sc.render.resolution_y / sc.render.resolution_x)})
            shots.append({"frame": int(f), "png_b64": c["png_b64"]})
    finally:
        sc.frame_set(keep)
    return {"shots": shots, "camera": sc.camera.name if sc.camera else None}


def cmd_set_frame(req):
    bpy.context.scene.frame_set(int(req["frame"])); return {"frame": bpy.context.scene.frame_current}


def cmd_open_file(req):
    bpy.ops.wm.open_mainfile(filepath=req["filepath"]); return cmd_ping(req)


def cmd_save_file(req):
    if req.get("filepath"): bpy.ops.wm.save_as_mainfile(filepath=req["filepath"])
    else: bpy.ops.wm.save_mainfile()
    return {"file": bpy.data.filepath}


COMMANDS = {k[4:]: v for k, v in globals().items() if k.startswith("cmd_")}

import importlib, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sculpt_cmds
_SCULPT_MTIME = [0.0]


def _commands():
    """Core commands plus sculpt_cmds.py, which is reloaded when its file changes (no Blender restart to pick up edits)."""
    m = os.path.getmtime(sculpt_cmds.__file__)
    if m != _SCULPT_MTIME[0]:
        if _SCULPT_MTIME[0]: importlib.reload(sculpt_cmds)
        _SCULPT_MTIME[0] = m
        sculpt_cmds.capture, sculpt_cmds.view3d = cmd_capture, _view3d
        COMMANDS.update({k[4:]: v for k, v in vars(sculpt_cmds).items() if k.startswith("cmd_")})
    return COMMANDS


def _pump():
    while not REQ.empty():
        req, done, box = REQ.get()
        try:
            cmds = _commands()
            if req["cmd"] not in cmds: raise KeyError(f"unknown command {req['cmd']!r}")
            box.update({"ok": True, **cmds[req["cmd"]](req)})
        except Exception as exc:
            box.update({"ok": False, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-4000:]})
        finally:
            done.set()
    return 0.05


if not bpy.app.driver_namespace.get("_blender_live_started"):         # bpy.app is read-only; driver_namespace persists per session
    threading.Thread(target=_serve, daemon=True).start()
    bpy.app.timers.register(_pump, persistent=True)
    bpy.app.driver_namespace["_blender_live_started"] = True
    print(f"BLENDER_LIVE_READY {HOST}:{PORT} tmp={TMP}")
