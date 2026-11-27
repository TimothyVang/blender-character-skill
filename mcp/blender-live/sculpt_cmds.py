"""Sculpt and review commands for the blender-live bridge. Loaded by bridge.py, which fills in `capture` and `view3d`.

Strokes move vertices directly (numpy), not through Blender's brush operator: a scripted
bpy.ops.sculpt.brush_stroke crashed Blender 4.5.16 when driven from the bridge timer. Direct strokes do not depend on
the viewport, give the same result every run, and work on the mesh in Object Mode. The brushes share Blender's names
but are simpler:

  grab         verts near the first point move by (last point - first point), fading with distance
  snake_hook   grab that follows the path, picking up verts as it goes (pulls out horns, fingers, tails)
  draw         raise (or with subtract, lower) along the surface's average normal under the path
  clay_strips  draw with a flatter top (builds up broad forms)
  inflate      each vert moves along its own normal (swells rather than raises)
  crease       cut a narrow valley and pinch verts toward the path (subtract makes a ridge)
  smooth       relax verts toward their neighbours' average

Points and radius are in world units. Masked verts (Blender's own `.sculpt_mask` attribute above 0.5) do not move.
Symmetry mirrors the path across the object's local axis and blends both sides from one snapshot, so a stroke over
the centre line stays symmetric.
"""
import contextlib, math, os, time

import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

capture = None   # bridge.cmd_capture, set by bridge.py
view3d = None    # bridge._view3d, set by bridge.py

ENGINE = "direct"
BRUSHES = ("grab", "snake_hook", "draw", "clay_strips", "inflate", "crease", "smooth")
SYM_PROP = "blender_live_symmetry"
MASK = ".sculpt_mask"
AXES = {"X": 0, "Y": 1, "Z": 2}
MAX_REMESH_CELLS = 700          # longest side / voxel size above this is refused (it would freeze Blender)
VIEWS = ("FRONT", "BACK", "LEFT", "RIGHT", "TOP", "THREE_QUARTER")


# ------------------------------------------------------------------ helpers
def _mesh_obj(name):
    o = bpy.data.objects.get(name)
    if o is None: raise KeyError(f"no object named {name!r}")
    if o.type != "MESH": raise ValueError(f"{name!r} is a {o.type}, not a mesh")
    if o.data.shape_keys: raise ValueError(f"{name!r} has shape keys; sculpt commands only edit a plain mesh")
    return o


_MODE_BACK = {"EDIT_MESH": "EDIT", "SCULPT": "SCULPT", "PAINT_WEIGHT": "WEIGHT_PAINT", "PAINT_VERTEX": "VERTEX_PAINT",
              "PAINT_TEXTURE": "TEXTURE_PAINT", "POSE": "POSE", "EDIT_ARMATURE": "EDIT"}


def _mode_set(mode):
    win, area, region = view3d()
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.object.mode_set(mode=mode)


@contextlib.contextmanager
def _in_object_mode():
    """Object Mode for the command (mesh data is only safe to edit there), then back to the user's mode."""
    before = bpy.context.mode
    active = bpy.context.view_layer.objects.active
    if before != "OBJECT": _mode_set("OBJECT")
    try:
        yield
    finally:
        back = _MODE_BACK.get(before)
        if back and active is not None and bpy.context.view_layer.objects.active is active:
            try: _mode_set(back)
            except RuntimeError: pass


def _undo_push(message):
    """A Ctrl-Z step for the user, so their undo does not jump past the tool's edits."""
    try:
        win, area, region = view3d()
        with bpy.context.temp_override(window=win, area=area, region=region):
            bpy.ops.ed.undo_push(message=message)
    except Exception:
        pass


@contextlib.contextmanager
def _solo(keep):
    """Hide every other object for a capture; afterwards unhide them and put the selection and active object back."""
    keep = set(keep)
    for o in list(keep): keep.update(o.children_recursive)
    selected = [o for o in bpy.context.view_layer.objects if o.select_get()]
    active = bpy.context.view_layer.objects.active
    hidden = []
    try:
        for other in bpy.context.view_layer.objects:
            if other not in keep and not other.hide_get():
                other.hide_set(True); hidden.append(other)
        yield
    finally:
        for other in hidden:
            try: other.hide_set(False)
            except ReferenceError: pass
        for o in bpy.context.view_layer.objects:
            try: o.select_set(o in selected)
            except RuntimeError: pass
        bpy.context.view_layer.objects.active = active


def _get(coll, attr, n, width):
    a = np.empty(n * width, dtype=np.float32)
    coll.foreach_get(attr, a)
    return a.reshape(n, width).astype(np.float64) if width > 1 else a.astype(np.float64)


def _co(me): return _get(me.vertices, "co", len(me.vertices), 3)
def _normals(me): return _get(me.vertex_normals, "vector", len(me.vertices), 3)


def _set_co(me, co):
    me.vertices.foreach_set("co", co.astype(np.float32).ravel())
    me.update()


def _edges(me):
    e = np.empty(len(me.edges) * 2, dtype=np.int32)
    me.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def _mask(me):
    a = me.attributes.get(MASK)
    if a is None or a.domain != "POINT": return np.zeros(len(me.vertices))
    return _get(a.data, "value", len(me.vertices), 1)


def _set_mask(me, values):
    a = me.attributes.get(MASK)
    if a is None: a = me.attributes.new(MASK, "FLOAT", "POINT")
    a.data.foreach_set("value", values.astype(np.float32))
    me.update()


def _scale(o):
    """The object's world scale. Non-uniform scale is refused: brush radius and reported moves would be wrong."""
    s = [abs(v) for v in o.matrix_world.to_scale()]
    if min(s) <= 0 or max(s) / min(s) > 1.01:
        raise ValueError(f"{o.name!r} (or a parent) has non-uniform scale {tuple(round(v, 4) for v in s)}; "
                         "apply the scale first (Object > Apply > Scale)")
    return sum(s) / 3


def _to_local(o, points):
    inv = o.matrix_world.inverted()
    return np.array([tuple(inv @ Vector(p)) for p in points], dtype=np.float64)


def _world(o, co):
    m = np.array(o.matrix_world)
    return co @ m[:3, :3].T + m[:3, 3]


def _falloff(d, r):
    t = np.clip(1.0 - (d / r) ** 2, 0.0, 1.0)
    return t * t


def _densify(pts, step):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(1, int(math.ceil(float(np.linalg.norm(b - a)) / step)))
        out += [a + (b - a) * i / n for i in range(1, n + 1)]
    return np.array(out)


def _nearest(c, samples):
    best = np.full(len(c), np.inf); idx = np.zeros(len(c), dtype=np.int64)
    for i, s in enumerate(samples):
        d = np.linalg.norm(c - s, axis=1)
        m = d < best
        best[m] = d[m]; idx[m] = i
    return best, idx


# ------------------------------------------------------------------ brushes
def _field(brush, co, nor, pts, r, strength, sign):
    """Weights (N,) and displacement (N,3) for one path against the current mesh state."""
    n = len(co)
    w = np.zeros(n); disp = np.zeros((n, 3))
    sub = np.nonzero(np.all((co >= pts.min(0) - r) & (co <= pts.max(0) + r), axis=1))[0]
    if not len(sub): return w, disp
    c = co[sub]
    if brush == "grab":
        ws = _falloff(np.linalg.norm(c - pts[0], axis=1), r)
        w[sub] = ws; disp[sub] = ws[:, None] * (pts[-1] - pts[0]) * strength
        return w, disp
    samples = _densify(pts, r / 4)
    d, idx = _nearest(c, samples)
    ws = _falloff(d, r)
    inside = ws > 0
    if brush == "smooth":
        w[sub] = ws * strength
        return w, disp
    if brush == "inflate":
        dirs = nor[sub]
    else:                                       # the average surface normal under each path sample
        an = np.zeros((len(samples), 3))
        np.add.at(an, idx[inside], nor[sub][inside] * ws[inside, None])
        ln = np.linalg.norm(an, axis=1, keepdims=True)
        dirs = np.divide(an, ln, out=np.zeros_like(an), where=ln > 0)[idx]
    if brush in ("draw", "inflate"): amount = ws * strength * r * 0.5 * sign
    elif brush == "clay_strips": amount = np.sqrt(ws) * strength * r * 0.3 * sign
    elif brush == "crease": amount = -(ws ** 3) * strength * r * 0.5 * sign
    else: raise ValueError(f"unknown brush {brush!r}; use one of {', '.join(BRUSHES)}")
    dv = dirs * amount[:, None]
    if brush == "crease":                       # pinch toward the path, along the surface
        toward = samples[idx] - c
        toward -= dirs * np.sum(toward * dirs, axis=1, keepdims=True)
        dv += toward * (ws * 0.4 * strength)[:, None]
    w[sub] = ws; disp[sub] = dv
    return w, disp


def _both_sides(brush, co, nor, pts, r, strength, sign, axis):
    w, disp = _field(brush, co, nor, pts, r, strength, sign)
    if axis is None: return w, disp
    mirror = pts.copy(); mirror[:, axis] *= -1
    w2, d2 = _field(brush, co, nor, mirror, r, strength, sign)
    total = w + w2
    blended = np.divide(disp * w[:, None] + d2 * w2[:, None], total[:, None], out=np.zeros_like(disp), where=total[:, None] > 0)
    return np.maximum(w, w2), blended


def _smooth(co, edges, w, keep, iterations=4):
    active = (w > 0) & (keep > 0)
    if not active.any(): return co
    e = edges[active[edges[:, 0]] | active[edges[:, 1]]]
    for _ in range(iterations):
        sums = np.zeros_like(co); cnt = np.zeros(len(co))
        np.add.at(sums, e[:, 0], co[e[:, 1]]); np.add.at(sums, e[:, 1], co[e[:, 0]])
        np.add.at(cnt, e[:, 0], 1); np.add.at(cnt, e[:, 1], 1)
        avg = np.divide(sums, cnt[:, None], out=co.copy(), where=cnt[:, None] > 0)
        co = co + (avg - co) * (np.clip(w, 0, 1) * keep * active)[:, None]
    return co


def _check_stroke(i, stroke):
    brush = stroke.get("brush")
    if brush not in BRUSHES: raise ValueError(f"stroke {i}: unknown brush {brush!r}; use one of {', '.join(BRUSHES)}")
    points = stroke.get("points") or []
    need = 2 if brush in ("grab", "snake_hook") else 1
    if len(points) < need: raise ValueError(f"stroke {i}: {brush} needs at least {need} points: where to start and where to move to")
    if any(len(p) != 3 for p in points): raise ValueError(f"stroke {i}: every point needs x, y, z")
    if float(stroke.get("radius", 0.1)) <= 0: raise ValueError(f"stroke {i}: radius must be above 0")


def _apply_stroke(o, stroke, axis):
    me = o.data
    brush = stroke.get("brush")
    points = stroke.get("points")
    if stroke.get("snap"):                      # put points on the nearest spot of the surface
        dg = bpy.context.evaluated_depsgraph_get()
        bvh = BVHTree.FromObject(o, dg)
        inv, mw = o.matrix_world.inverted(), o.matrix_world
        def near(p): return mw @ (bvh.find_nearest(inv @ Vector(p))[0] or (inv @ Vector(p)))
        if brush in ("grab", "snake_hook"):     # move only the start onto the surface; the path keeps its shape and length
            off = near(points[0]) - Vector(points[0])
            points = [tuple(Vector(p) + off) for p in points]
        else:
            points = [tuple(near(p)) for p in points]
    scale = _scale(o)
    pts = _to_local(o, points)
    r = float(stroke.get("radius", 0.1)) / scale
    if r <= 0: raise ValueError("radius must be above 0")
    strength = float(stroke.get("strength", 1.0 if brush in ("grab", "snake_hook") else 0.5))
    sign = -1.0 if stroke.get("subtract") else 1.0
    keep = 1.0 - np.clip(_mask(me), 0, 1)
    keep[keep < 0.5] = 0.0
    before = _co(me); co = before.copy()
    if brush == "snake_hook":
        steps = _densify(pts, r / 2)
        for a, b in zip(steps[:-1], steps[1:]):
            _, d = _both_sides("grab", co, None, np.array([a, b]), r, strength, sign, axis)
            co = co + d * keep[:, None]
    elif brush == "smooth":
        w, _ = _both_sides(brush, co, None, pts, r, strength, sign, axis)
        co = _smooth(co, _edges(me), w, keep)
    else:
        nor = None if brush == "grab" else _normals(me)
        _, d = _both_sides(brush, co, nor, pts, r, strength, sign, axis)
        co = co + d * keep[:, None]
    _set_co(me, co)
    move = np.linalg.norm(co - before, axis=1) * scale
    moved = move > 1e-6
    return {"brush": brush, "moved_verts": int(moved.sum()), "max_move": round(float(move.max()) if len(move) else 0.0, 6),
            "mean_move": round(float(move[moved].mean()) if moved.any() else 0.0, 6)}


# ------------------------------------------------------------------ commands
def cmd_sculpt_begin(req):
    """Choose the object to sculpt and its symmetry axis ("X", "Y", "Z" or "" for none). Remembers both on the object."""
    o = _mesh_obj(req["object"]); _scale(o)
    sym = (req.get("symmetry") or "").upper()
    if sym and sym not in AXES: raise ValueError(f"symmetry must be X, Y, Z or empty, not {sym!r}")
    o[SYM_PROP] = sym
    if req.get("voxel_size"): o.data.remesh_voxel_size = float(req["voxel_size"])
    for other in bpy.context.view_layer.objects: other.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o
    return {"object": o.name, "engine": ENGINE, "mode": bpy.context.mode, "verts": len(o.data.vertices), "symmetry": sym,
            "voxel_size": o.data.remesh_voxel_size, "brushes": list(BRUSHES)}


def cmd_sculpt_strokes(req):
    """Apply strokes in order. Each: brush, points [[x,y,z],...] in world space, radius, strength, subtract, snap."""
    o = _mesh_obj(req["object"]); _scale(o)
    sym = o.get(SYM_PROP, "") if req.get("symmetry") is None else (req.get("symmetry") or "").upper()
    axis = AXES.get(sym)
    strokes = req.get("strokes") or []
    for i, s in enumerate(strokes): _check_stroke(i, s)     # all checked before any is applied
    t0 = time.time()
    with _in_object_mode():
        done = [_apply_stroke(o, s, axis) for s in strokes]
    _undo_push(f"blender-live: {len(done)} sculpt strokes")
    return {"engine": ENGINE, "symmetry": sym, "strokes": done, "verts": len(o.data.vertices), "seconds": round(time.time() - t0, 3)}


def cmd_sculpt_remesh(req):
    """Voxel remesh: rebuilds the surface as even quads at voxel_size (world units). Clears the mask."""
    o = _mesh_obj(req["object"]); scale = _scale(o)
    size = float(req["voxel_size"])
    longest = max(o.dimensions)
    if size <= 0 or longest / size > MAX_REMESH_CELLS:
        raise ValueError(f"voxel_size {size} is too small for an object {longest:.3f} long; use at least {longest / MAX_REMESH_CELLS:.5f}")
    before = len(o.data.vertices)
    o.data.remesh_voxel_size = size / scale
    win, area, region = view3d()
    with _in_object_mode(), bpy.context.temp_override(window=win, area=area, region=region, active_object=o, object=o,
                                                      selected_objects=[o], selected_editable_objects=[o]):
        bpy.ops.object.voxel_remesh()
    _undo_push("blender-live: voxel remesh")
    return {"verts_before": before, "verts_after": len(o.data.vertices), "voxel_size": size}


def cmd_sculpt_mask(req):
    """op "box": protect verts inside the world-space box min..max. "clear": unprotect all. "invert": swap."""
    o = _mesh_obj(req["object"])
    me = o.data; op = req.get("op", "clear")
    if op == "box" and (not req.get("min") or not req.get("max") or len(req["min"]) != 3 or len(req["max"]) != 3):
        raise ValueError("op 'box' needs min and max, each [x, y, z] in world units")
    with _in_object_mode():
        return _mask_op(o, me, op, req)


def _mask_op(o, me, op, req):
    m = _mask(me)
    if op == "clear": m[:] = 0
    elif op == "invert": m = 1.0 - np.clip(m, 0, 1)
    elif op == "box":
        w = _world(o, _co(me))
        lo, hi = np.minimum(req["min"], req["max"]), np.maximum(req["min"], req["max"])
        m[np.all((w >= lo) & (w <= hi), axis=1)] = 1.0
    else: raise ValueError(f"unknown mask op {op!r}; use box, clear or invert")
    _set_mask(me, m)
    _undo_push("blender-live: mask " + op)
    return {"masked_verts": int((m > 0.5).sum()), "verts": len(m)}


def cmd_mesh_report(req):
    """Counts and health: loose parts, open (boundary) edges, edges shared by 3+ faces, and how symmetric it is in X."""
    o = _mesh_obj(req["object"])
    with _in_object_mode():
        return _report(o, req)


def _report(o, req):
    me = o.data; n = len(me.vertices)
    co = _co(me); edges = _edges(me)
    labels = np.arange(n)
    while True:
        low = np.minimum(labels[edges[:, 0]], labels[edges[:, 1]]) if len(edges) else np.array([], dtype=np.int64)
        new = labels.copy()
        if len(edges):
            np.minimum.at(new, edges[:, 0], low); np.minimum.at(new, edges[:, 1], low)
        new = new[new]
        if np.array_equal(new, labels): break
        labels = new
    loop_edges = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("edge_index", loop_edges)
    uses = np.bincount(loop_edges, minlength=len(me.edges)) if len(me.edges) else np.array([], dtype=np.int64)
    axis = AXES.get((req.get("axis") or "X").upper(), 0)
    sym_err = None
    if n:
        kd = KDTree(n)
        for i, c in enumerate(co): kd.insert(c, i)
        kd.balance()
        step = max(1, n // 20000)
        mirrored = co[::step].copy(); mirrored[:, axis] *= -1
        diag = float(np.linalg.norm(co.max(0) - co.min(0))) or 1.0
        sym_err = round(float(np.mean([kd.find(m)[2] for m in mirrored])) / diag, 6)
    w = _world(o, co) if n else np.zeros((0, 3))
    return {"object": o.name, "verts": n, "faces": len(me.polygons), "edges": len(me.edges),
            "loose_parts": int(len(np.unique(labels))) if n else 0, "boundary_edges": int((uses == 1).sum()),
            "non_manifold_edges": int((uses > 2).sum()), "symmetry_error": sym_err,
            "bounds_min": [round(float(v), 5) for v in w.min(0)] if n else None,
            "bounds_max": [round(float(v), 5) for v in w.max(0)] if n else None,
            "masked_verts": int((_mask(me) > 0.5).sum())}


_REF_POSE = {   # view -> (rotation euler, axis index the picture sits behind the model on, sign)
    "FRONT": ((math.pi / 2, 0, 0), 1, 1), "BACK": ((math.pi / 2, 0, math.pi), 1, -1),
    "RIGHT": ((math.pi / 2, 0, math.pi / 2), 0, -1), "LEFT": ((math.pi / 2, 0, -math.pi / 2), 0, 1),
    "TOP": ((0, 0, 0), 2, -1),
}


def cmd_reference_setup(req):
    """Put concept pictures in the scene as REF_<VIEW> image empties: upright, feet on the ground plane, `height` tall,
    behind the model for that view, shown only in orthographic views, not selectable."""
    height = float(req.get("height", 2.0)); depth = float(req.get("depth", height))
    coll = bpy.data.collections.get("References")
    if coll is None:
        coll = bpy.data.collections.new("References"); bpy.context.scene.collection.children.link(coll)
    images = {str(k).upper(): v for k, v in (req.get("images") or {}).items()}
    for view, path in images.items():                      # all checked before anything is created
        if view not in _REF_POSE: raise ValueError(f"unknown view {view!r}; use one of {', '.join(_REF_POSE)}")
        if not os.path.isfile(path): raise FileNotFoundError(path)
    created = []
    for view, path in images.items():
        img = bpy.data.images.load(path, check_existing=True)
        old = bpy.data.objects.get("REF_" + view)
        if old: bpy.data.objects.remove(old, do_unlink=True)
        e = bpy.data.objects.new("REF_" + view, None)
        e.empty_display_type = "IMAGE"; e.data = img
        w, h = img.size
        e.empty_display_size = height * max(w, h) / h if h else height   # Blender scales the longer side to this size
        rot, ax, sign = _REF_POSE[view]
        e.rotation_euler = Euler(rot)
        e.empty_image_offset = (-0.5, -0.5) if view == "TOP" else (-0.5, 0.0)
        loc = [0.0, 0.0, 0.0]; loc[ax] = sign * depth; e.location = loc
        e.show_empty_image_perspective = False
        e.use_empty_image_alpha = True; e.color[3] = 0.6
        e.hide_select = True; e.hide_render = True
        e.empty_image_side = "FRONT"                       # not drawn from behind, so it never covers the model
        e["reference_height"] = height
        coll.objects.link(e); created.append(e.name)
    return {"created": created, "height": height}


def cmd_silhouettes(req):
    """Flat white-on-black orthographic capture per axis view of the object, its children and the `also` objects,
    everything else hidden. The viewport, shading, selection and visibility are put back afterwards."""
    o = bpy.data.objects.get(req["object"])
    if o is None: raise KeyError(f"no object named {req['object']!r}")
    extra = []
    for name in req.get("also") or []:
        x = bpy.data.objects.get(name)
        if x is None: raise KeyError(f"no object named {name!r} (in also)")
        extra.append(x)
    views = [v.upper() for v in (req.get("views") or ("FRONT", "BACK", "LEFT", "RIGHT", "TOP"))]
    for v in views:
        if v not in VIEWS or v == "THREE_QUARTER": raise ValueError(f"unknown view {v!r}; use FRONT, BACK, LEFT, RIGHT or TOP")
    px = int(req.get("px", 1024))
    win, area, region = view3d(); sp = area.spaces.active; r3d = sp.region_3d; sh = sp.shading
    keep_view = (r3d.view_rotation.copy(), r3d.view_location.copy(), r3d.view_distance, r3d.view_perspective)
    keep_shade = (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, tuple(sh.background_color),
                  tuple(sh.single_color), sh.show_shadows, sh.show_object_outline, sh.show_xray)
    shots = []
    try:
        with _solo([o] + extra):
            sh.type = "SOLID"; sh.light = "FLAT"; sh.color_type = "SINGLE"; sh.single_color = (1, 1, 1); sh.show_cavity = False
            sh.background_type = "VIEWPORT"; sh.background_color = (0, 0, 0); sh.show_shadows = False
            sh.show_object_outline = False; sh.show_xray = False
            for v in views:
                r3d.view_perspective = "ORTHO"        # axis views keep it whatever the Auto Perspective preference
                c = capture({"view": v, "shading": "SOLID", "width": px, "height": px, "redraws": 2})
                shots.append({"view": v, "png_b64": c["png_b64"], "perspective": c["perspective"]})
    finally:
        (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, sh.background_color, sh.single_color,
         sh.show_shadows, sh.show_object_outline, sh.show_xray) = keep_shade
        r3d.view_rotation, r3d.view_location, r3d.view_distance, r3d.view_perspective = keep_view
    return {"object": o.name, "also": [x.name for x in extra], "shots": shots, "px": px}


def cmd_turnaround(req):
    """One clean capture of the object per view, same shading for all, everything else hidden. The viewport is put back."""
    o = bpy.data.objects.get(req["object"])
    if o is None: raise KeyError(f"no object named {req['object']!r}")
    extra = []
    for name in req.get("also") or []:
        x = bpy.data.objects.get(name)
        if x is None: raise KeyError(f"no object named {name!r} (in also)")
        extra.append(x)
    views = [v.upper() for v in (req.get("views") or VIEWS)]
    for v in views:
        if v not in VIEWS: raise ValueError(f"unknown view {v!r}; use one of {', '.join(VIEWS)}")
    px = int(req.get("cell_px", 512))
    win, area, region = view3d(); sp = area.spaces.active; r3d = sp.region_3d; sh = sp.shading
    keep_view = (r3d.view_rotation.copy(), r3d.view_location.copy(), r3d.view_distance, r3d.view_perspective)
    keep_shade = (sh.type, sh.light, sh.color_type, sh.show_cavity)
    shots = []
    solo = _solo([o] + extra); solo.__enter__()
    try:
        sh.type = "SOLID"; sh.light = "MATCAP"; sh.color_type = "SINGLE"; sh.show_cavity = True
        for v in views:
            r3d.view_perspective = "ORTHO"
            if v == "THREE_QUARTER":
                r3d.view_rotation = Euler((math.radians(72), 0, math.radians(35))).to_quaternion()
            else:
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.view3d.view_axis(type=v)
            with bpy.context.temp_override(window=win, area=area, region=region):
                bpy.ops.view3d.view_all()           # frames everything still visible: the object, its children, `also`
            c = capture({"shading": "SOLID", "width": px, "height": px, "redraws": 2})
            shots.append({"view": v, "png_b64": c["png_b64"]})
    finally:
        solo.__exit__(None, None, None)
        sh.type, sh.light, sh.color_type, sh.show_cavity = keep_shade
        r3d.view_rotation, r3d.view_location, r3d.view_distance, r3d.view_perspective = keep_view
    return {"object": o.name, "also": [x.name for x in extra], "shots": shots, "cell_px": px}
