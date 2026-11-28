"""blender-live core commands, run on Blender's main thread. No side effects on import: the blender-live bridge
(bridge.py) serves these.

Commands: ping, exec, scene_tree, object_info, capture, motion_preview, render, set_frame, open_file, save_file.
Captures go to BLENDER_LIVE_TMP, default <workspace>/.scratch/tmp/blender-live/<pid> (never the system temp folder).
"""
import base64, contextlib, importlib, inspect, io, json, os, sys, time, traceback

import bpy

TMP = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch", "tmp",
                                                          "blender-live", str(os.getpid()))
TMP = os.path.abspath(TMP); os.makedirs(TMP, exist_ok=True)


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


def cmd_watch_view(req):
    """Point the person's own 3D viewport at the work and put the reference picture beside it, so they watch what
    the agent does: perspective view from azimuth/elevation (0 = FRONT, 90 = Blender RIGHT) at `centre` (or the
    named object's centre) from `distance`, Material Preview; `reference` (an image path) opens in an Image
    Editor next to the viewport, splitting the largest 3D Viewport once if there is none. Changes no scene data."""
    import math
    from mathutils import Euler, Vector
    win, area, region = _view3d()
    r3d = area.spaces.active.region_3d
    if req.get("object"):
        o = bpy.data.objects[req["object"]]
        centre = sum((o.matrix_world @ Vector(c) for c in o.bound_box), Vector()) / 8.0
    else:
        centre = Vector(req.get("centre") or (0.0, 0.0, 1.0))
    az, el = float(req.get("azimuth", 0.0)), float(req.get("elevation", 0.0))
    r3d.view_rotation = Euler((math.radians(90.0 - el), 0.0, math.radians(az))).to_quaternion()
    r3d.view_location = centre
    r3d.view_distance = float(req.get("distance", 1.5))
    r3d.view_perspective = "PERSP"
    area.spaces.active.shading.type = req.get("shading") or "MATERIAL"
    shown = None
    if req.get("reference"):
        img = bpy.data.images.load(req["reference"], check_existing=True)
        scr = win.screen
        editors = [a for a in scr.areas if a.type == "IMAGE_EDITOR"]
        if not editors:
            with bpy.context.temp_override(window=win, screen=scr, area=area, region=region):
                bpy.ops.screen.area_split(direction="VERTICAL", factor=0.55)
            right = max((a for a in scr.areas if a.type == "VIEW_3D"), key=lambda a: a.x)
            right.type = "IMAGE_EDITOR"
            editors = [right]
            win, area, region = _view3d()
        for ed in editors:
            ed.spaces.active.image = img
            reg = next(r for r in ed.regions if r.type == "WINDOW")
            with bpy.context.temp_override(window=win, screen=scr, area=ed, region=reg):
                bpy.ops.image.view_all(fit_view=True)
            ed.tag_redraw()
        shown = img.name
    area.tag_redraw()
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
    return {"centre": list(centre), "azimuth": az, "elevation": el, "distance": r3d.view_distance, "reference": shown}


# ------------------------------------------------------------------ command registry and sliced jobs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sculpt_cmds

_REGISTRY = {}
_MTIME = [0.0]


def commands():
    """Core commands plus sculpt_cmds.py, reloaded (with projection.py, which it reloads) when either file changes,
    so tool edits need no Blender restart."""
    here = os.path.dirname(os.path.abspath(__file__))
    m = max(os.path.getmtime(os.path.join(here, f)) for f in ("sculpt_cmds.py", "projection.py"))
    if m != _MTIME[0] or not _REGISTRY:
        if _MTIME[0]: importlib.reload(sculpt_cmds)
        _MTIME[0] = m
        sculpt_cmds.capture, sculpt_cmds.view3d = cmd_capture, _view3d
        _REGISTRY.clear()
        _REGISTRY.update({k[4:]: v for k, v in globals().items() if k.startswith("cmd_")})
        _REGISTRY.update({k[4:]: v for k, v in vars(sculpt_cmds).items() if k.startswith("cmd_")})
    return _REGISTRY


def run(cmd, req):
    """Run one command: a dict for a short one, a generator for a long one (each yield is a progress line)."""
    cmds = commands()
    if cmd not in cmds: raise KeyError(f"unknown command {cmd!r}")
    return cmds[cmd](req)


def status(label, text):
    """Show a long command's progress in Blender's status bar (text None clears it)."""
    for win in bpy.context.window_manager.windows:
        with contextlib.suppress(Exception):
            win.workspace.status_text_set_internal(f"{label}: {text}" if text else None)


class SlicedJobs:
    """Long commands on Blender's main thread without freezing it. start() runs a command; a generator result is
    kept and advanced by step() about 0.15 s per timer tick, so Blender redraws between slices and the status bar
    shows each yielded progress line. on_done(result, exc, trace) gets exactly one call per command."""

    def __init__(self, label, budget=0.15):
        self.label, self.budget, self.active = label, budget, []

    def start(self, make, on_done):
        try:
            res = make()
        except Exception as exc:
            on_done(None, exc, traceback.format_exc()[-4000:]); return
        if inspect.isgenerator(res): self.active.append((res, on_done))
        else: on_done(res, None, None)

    def step(self):
        """Advance every running command by one slice; True while any is still running."""
        for job in list(self.active):
            gen, on_done = job
            t0 = time.time()
            try:
                while time.time() - t0 < self.budget:
                    msg = next(gen)
                    if msg: status(self.label, msg)
            except StopIteration as stop:
                self.active.remove(job); status(self.label, None); on_done(stop.value, None, None)
            except Exception as exc:
                self.active.remove(job); status(self.label, None); on_done(None, exc, traceback.format_exc()[-4000:])
        return bool(self.active)
