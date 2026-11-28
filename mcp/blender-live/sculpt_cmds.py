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
import contextlib, importlib, math, os, time

import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

import projection
importlib.reload(projection)    # the bridge reloads this module on edit; keep the helpers in step with it

capture = None   # live_core.cmd_capture, set by live_core.commands()
view3d = None    # live_core._view3d, set by live_core.commands()

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
        return True
    except (RuntimeError, AttributeError):
        return False


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


def _nearest(c, samples, v_chunk=2048, s_chunk=64):
    c = np.asarray(c, dtype=np.float64)
    samples = np.asarray(samples, dtype=np.float64)
    n = len(c)
    best = np.full(n, np.inf, dtype=np.float64)
    idx = np.zeros(n, dtype=np.int64)
    if n == 0 or len(samples) == 0:
        return best, idx
    m = len(samples)
    for v0 in range(0, n, v_chunk):
        v1 = min(v0 + v_chunk, n)
        c_blk = c[v0:v1]
        rows = np.arange(v1 - v0)
        blk_best = np.full(v1 - v0, np.inf, dtype=np.float64)
        blk_idx = np.zeros(v1 - v0, dtype=np.int64)
        for s0 in range(0, m, s_chunk):
            s1 = min(s0 + s_chunk, m)
            diff = c_blk[:, None, :] - samples[s0:s1][None, :, :]
            d2 = np.einsum("ijk,ijk->ij", diff, diff)
            local_i = np.argmin(d2, axis=1)
            local_d2 = d2[rows, local_i]
            better = local_d2 < blk_best
            blk_best[better] = local_d2[better]
            blk_idx[better] = s0 + local_i[better]
        best[v0:v1] = np.sqrt(blk_best)
        idx[v0:v1] = blk_idx
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


def cmd_sculpt_relax(req):
    """Whole-mesh smoothing. method "taubin" (default) alternates lam / mu passes: removes lumps and fine stair
    steps without shrinking, but keeps waves several edges long by design. method "laplacian" (lam passes only)
    removes long waves too and shrinks convex tips, so pair it with `along`. along "X" / "Y" / "Z" averages each vert
    only with neighbours across edges pointing mostly along that world axis: along="Z" irons the horizontal ridges of
    a slice-lofted (ring-stacked) mesh while each ring keeps its own outline. Masked verts stay put; open-boundary
    verts stay put unless pin_boundary is false."""
    o = _mesh_obj(req["object"]); scale = _scale(o)
    its = int(req.get("iterations", 20)); lam = float(req.get("lam", 0.5)); mu = float(req.get("mu", -0.53))
    method = req.get("method", "taubin"); along = (req.get("along") or "").upper()
    if not (0 < its <= 1000): raise ValueError("iterations must be 1..1000")
    if method not in ("taubin", "laplacian"): raise ValueError("method must be 'taubin' or 'laplacian'")
    if along and along not in AXES: raise ValueError("along must be X, Y, Z or empty")
    if not (0 < lam < 1) or (method == "taubin" and not (-1 < mu < -lam)):
        raise ValueError("need 0 < lam < 1 and, for taubin, -1 < mu < -lam")
    with _in_object_mode():
        me = o.data; before = _co(me); e = _edges(me)
        keep = 1.0 - np.clip(_mask(me), 0, 1); keep[keep < 0.5] = 0.0
        if req.get("pin_boundary", True) and len(me.polygons):
            le = np.empty(len(me.loops), np.int32); me.loops.foreach_get("edge_index", le)
            uses = np.bincount(le, minlength=len(me.edges))
            keep[np.unique(e[uses == 1])] = 0.0
        if along:
            wv = _world(o, before)
            d = wv[e[:, 1]] - wv[e[:, 0]]
            e = e[np.abs(d[:, AXES[along]]) >= 0.7 * np.maximum(np.linalg.norm(d, axis=1), 1e-12)]
        cnt = np.zeros(len(before)); np.add.at(cnt, e[:, 0], 1); np.add.at(cnt, e[:, 1], 1)
        co = before.copy()
        passes = (lam, mu) if method == "taubin" else (lam,)
        for _ in range(its):
            for f in passes:
                sums = np.zeros_like(co)
                np.add.at(sums, e[:, 0], co[e[:, 1]]); np.add.at(sums, e[:, 1], co[e[:, 0]])
                avg = np.divide(sums, cnt[:, None], out=co.copy(), where=cnt[:, None] > 0)
                co = co + (avg - co) * (f * keep)[:, None]
        _set_co(me, co)
    _undo_push("blender-live: relax")
    move = np.linalg.norm(co - before, axis=1) * scale
    return {"object": o.name, "iterations": its, "moved_verts": int((move > 1e-6).sum()),
            "max_move": round(float(move.max()) if len(move) else 0.0, 6),
            "mean_move": round(float(move.mean()) if len(move) else 0.0, 6)}


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
    sym_err = sym_p95 = sym_max = None
    if n:
        kd = KDTree(n)
        for i, c in enumerate(co): kd.insert(c, i)
        kd.balance()
        step = max(1, n // 100000)
        mirrored = co[::step].copy(); mirrored[:, axis] *= -1
        diag = float(np.linalg.norm(co.max(0) - co.min(0))) or 1.0
        dists = np.fromiter((kd.find(m)[2] for m in mirrored), dtype=np.float64, count=len(mirrored)) / diag
        sym_err = round(float(dists.mean()), 6)
        sym_p95 = round(float(np.percentile(dists, 95)), 6)
        sym_max = round(float(dists.max()), 6)
    w = _world(o, co) if n else np.zeros((0, 3))
    return {"object": o.name, "verts": n, "faces": len(me.polygons), "edges": len(me.edges),
            "loose_parts": int(len(np.unique(labels))) if n else 0, "boundary_edges": int((uses == 1).sum()),
            "non_manifold_edges": int((uses > 2).sum()), "symmetry_error": sym_err,
            "symmetry_p95_error": sym_p95, "symmetry_max_error": sym_max,
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
    everything else hidden, under the Standard view transform (so an edge pixel's value encodes its coverage; AgX
    or Filmic would bend that and fatten the outline). The viewport, shading, selection, visibility and view
    transform are put back afterwards."""
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
    sc = bpy.context.scene; keep_vt = sc.view_settings.view_transform
    shots = []
    try:
        with _solo([o] + extra):
            sc.view_settings.view_transform = "Standard"
            sh.type = "SOLID"; sh.light = "FLAT"; sh.color_type = "SINGLE"; sh.single_color = (1, 1, 1); sh.show_cavity = False
            sh.background_type = "VIEWPORT"; sh.background_color = (0, 0, 0); sh.show_shadows = False
            sh.show_object_outline = False; sh.show_xray = False
            for v in views:
                r3d.view_perspective = "ORTHO"        # axis views keep it whatever the Auto Perspective preference
                c = capture({"view": v, "shading": "SOLID", "width": px, "height": px, "redraws": 2})
                shots.append({"view": v, "png_b64": c["png_b64"], "perspective": c["perspective"]})
    finally:
        sc.view_settings.view_transform = keep_vt
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


def cmd_visual_captures(req):
    """Orthographic silhouette + untextured MATCAP clay + Standard-transform MATERIAL capture per axis view,
    everything else hidden, restoring viewport, shading, lighting and view_transform afterwards."""
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
    win, area, region = view3d(); sp = area.spaces.active; r3d = sp.region_3d; sh = sp.shading; sc = bpy.context.scene
    keep_view = (r3d.view_rotation.copy(), r3d.view_location.copy(), r3d.view_distance, r3d.view_perspective)
    keep_shade = (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, tuple(sh.background_color),
                  tuple(sh.single_color), sh.show_shadows, sh.show_object_outline, sh.show_xray,
                  sh.use_scene_lights, sh.use_scene_world)
    keep_vt = sc.view_settings.view_transform
    shots = []
    try:
        with _solo([o] + extra):
            sc.view_settings.view_transform = "Standard"
            for v in views:
                # 1. Flat white-on-black orthographic silhouette
                sh.type = "SOLID"; sh.light = "FLAT"; sh.color_type = "SINGLE"; sh.single_color = (1, 1, 1)
                sh.show_cavity = False; sh.background_type = "VIEWPORT"; sh.background_color = (0, 0, 0)
                sh.show_shadows = False; sh.show_object_outline = False; sh.show_xray = False
                r3d.view_perspective = "ORTHO"
                sil = capture({"view": v, "shading": "SOLID", "width": px, "height": px, "redraws": 2})

                # 2. Untextured MATCAP clay pass (same exact framed ortho camera!)
                sh.type = "SOLID"; sh.light = "MATCAP"; sh.color_type = "SINGLE"; sh.single_color = (0.8, 0.8, 0.8)
                sh.show_cavity = True; sh.background_type = "VIEWPORT"; sh.background_color = (0.05, 0.05, 0.05)
                clay = capture({"shading": "SOLID", "width": px, "height": px, "redraws": 2})

                # 3. Material preview pass with neutral studio lighting (same exact framed ortho camera!)
                sh.type = "MATERIAL"; sh.use_scene_lights = False; sh.use_scene_world = False
                mat = capture({"shading": "MATERIAL", "width": px, "height": px, "redraws": 3})

                shots.append({
                    "view": v,
                    "perspective": sil["perspective"],
                    "silhouette_b64": sil["png_b64"],
                    "clay_b64": clay["png_b64"],
                    "material_b64": mat["png_b64"],
                })
    finally:
        sc.view_settings.view_transform = keep_vt
        (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, sh.background_color, sh.single_color,
         sh.show_shadows, sh.show_object_outline, sh.show_xray, sh.use_scene_lights, sh.use_scene_world) = keep_shade
        r3d.view_rotation, r3d.view_location, r3d.view_distance, r3d.view_perspective = keep_view
    return {"object": o.name, "also": [x.name for x in extra], "shots": shots, "px": px}


def cmd_orbit_captures(req):
    """Silhouette, untextured clay and material captures from any orbit angle (azimuth 0 = FRONT, 90 = Blender
    RIGHT, elevation up from the horizon), orthographic, everything else hidden; the viewport is put back."""
    o = bpy.data.objects.get(req["object"])
    if o is None: raise KeyError(f"no object named {req['object']!r}")
    extra = []
    for name in req.get("also") or []:
        x = bpy.data.objects.get(name)
        if x is None: raise KeyError(f"no object named {name!r} (in also)")
        extra.append(x)
    angles = [(float(a), float(e)) for a, e in (req.get("angles") or [])]
    if not angles: raise ValueError("angles is empty")
    px = int(req.get("px", 768))
    win, area, region = view3d(); sp = area.spaces.active; r3d = sp.region_3d; sh = sp.shading; sc = bpy.context.scene
    keep_view = (r3d.view_rotation.copy(), r3d.view_location.copy(), r3d.view_distance, r3d.view_perspective)
    keep_shade = (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, tuple(sh.background_color),
                  tuple(sh.single_color), sh.show_shadows, sh.show_object_outline, sh.show_xray,
                  sh.use_scene_lights, sh.use_scene_world)
    keep_vt = sc.view_settings.view_transform
    shots = []
    try:
        with _solo([o] + extra):
            sc.view_settings.view_transform = "Standard"
            for az, el in angles:
                r3d.view_rotation = Euler((math.radians(90.0 - el), 0.0, math.radians(az))).to_quaternion()
                r3d.view_perspective = "ORTHO"
                with bpy.context.temp_override(window=win, area=area, region=region):
                    bpy.ops.view3d.view_all()
                sh.type = "SOLID"; sh.light = "FLAT"; sh.color_type = "SINGLE"; sh.single_color = (1, 1, 1)
                sh.show_cavity = False; sh.background_type = "VIEWPORT"; sh.background_color = (0, 0, 0)
                sh.show_shadows = False; sh.show_object_outline = False; sh.show_xray = False
                sil = capture({"shading": "SOLID", "width": px, "height": px, "redraws": 2})
                sh.light = "MATCAP"; sh.single_color = (0.8, 0.8, 0.8); sh.show_cavity = True
                sh.background_color = (0.05, 0.05, 0.05)
                clay = capture({"shading": "SOLID", "width": px, "height": px, "redraws": 2})
                sh.type = "MATERIAL"; sh.use_scene_lights = False; sh.use_scene_world = False
                mat = capture({"shading": "MATERIAL", "width": px, "height": px, "redraws": 3})
                shots.append({"azimuth": az, "elevation": el, "perspective": sil["perspective"],
                              "silhouette_b64": sil["png_b64"], "clay_b64": clay["png_b64"], "material_b64": mat["png_b64"]})
    finally:
        sc.view_settings.view_transform = keep_vt
        (sh.type, sh.light, sh.color_type, sh.show_cavity, sh.background_type, sh.background_color, sh.single_color,
         sh.show_shadows, sh.show_object_outline, sh.show_xray, sh.use_scene_lights, sh.use_scene_world) = keep_shade
        r3d.view_rotation, r3d.view_location, r3d.view_distance, r3d.view_perspective = keep_view
    return {"object": o.name, "also": [x.name for x in extra], "shots": shots, "px": px}


def cmd_fit_outline(req):
    """Warp the model so its silhouette lands on reference outlines, one view after another. req["views"]: {VIEW:
    {"npy": signed distance field of the reference mask in its pixels (+ outside), "box": tight mask box}}. Per view
    the verts on the model's own outline (within rim_px of its edge, normal at least rim_angle off the view) say how
    far the outline must move (strength x distance along the field's gradient, clipped to max_px). Those moves are
    spread into a smooth picture-plane warp (Gaussian, sigma_px) and EVERY vert moves by the warp at its projected
    position, like a liquify in that view: sides stay round instead of being cut into flat slabs, and pixel noise in
    the outline is averaged away. Masked verts stay put. Assumes the rig is at rest."""
    views = {str(k).upper(): v for k, v in (req.get("views") or {}).items()}
    for v in views:
        if v not in projection.VIEW_AXES: raise ValueError(f"unknown view {v!r}")
    strength = float(req.get("strength", 0.8)); max_px = float(req.get("max_px", 8.0))
    rim_px = float(req.get("rim_px", 2.0)); rim_cos = math.cos(math.radians(float(req.get("rim_angle", 50.0))))
    sigma = float(req.get("sigma_px", 6.0))
    report = []
    with _in_object_mode():
        for v, spec in views.items():
            sdf = np.load(spec["npy"]).astype(np.float64)
            h, w = sdf.shape
            gy, gx = np.gradient(sdf)
            gn = np.maximum(np.hypot(gx, gy), 1e-9); gx, gy = gx / gn, gy / gn
            dg = bpy.context.evaluated_depsgraph_get()
            data = []
            for o in _paint_scope(req):
                if o.type != "MESH": continue
                ev = o.evaluated_get(dg); me = ev.to_mesh()
                try:
                    co = _get(me.vertices, "co", len(me.vertices), 3); nr = _get(me.vertex_normals, "vector", len(me.vertices), 3)
                finally:
                    ev.to_mesh_clear()
                if len(co) != len(o.data.vertices): continue      # topology-changing modifiers: skip
                mw = np.array(ev.matrix_world, np.float64)
                wn = nr @ np.linalg.inv(mw[:3, :3]); wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-12)
                data.append((o, co @ mw[:3, :3].T + mw[:3, 3], wn, _eval_tris(o, dg)[0]))
            if not data: raise ValueError("no visible mesh under the object")
            tri_all = np.concatenate([d[3] for d in data])
            mapping, reg, tri_sc = _register_view(v, tri_all, sdf, spec["box"])
            zb = projection.depth_buffer(tri_sc, mapping, w, h)
            model_sdf = projection.distance_field(np.isfinite(zb))
            acc = np.zeros((h, w, 2)); cnt = np.zeros((h, w))
            proj = []
            for o, wco, wn, _ in data:
                sc = projection.view_coords(wco, v)
                rx, ry = projection.to_ref_px(sc[:, 0], sc[:, 1], mapping)
                ix = np.clip(rx.astype(np.int64), 0, w - 1); iy = np.clip(ry.astype(np.int64), 0, h - 1)
                proj.append((rx, ry))
                ms = projection.sample_bilinear(model_sdf[..., None], rx, ry)[:, 0]
                rim = (np.abs(ms) <= rim_px) & (np.abs(wn @ np.asarray(projection.VIEW_AXES[v][0], np.float64)) <= rim_cos)
                # how far the reference outline lies from the model outline at this vertex: a vertex 1.5 px inside
                # the model's edge with the picture's edge in the same place must not move
                rs = projection.sample_bilinear(sdf[..., None], rx[rim], ry[rim])[:, 0]
                d = np.clip(rs - ms[rim], -max_px, max_px)
                mv = -strength * d[:, None] * np.stack([gx[iy[rim], ix[rim]], gy[iy[rim], ix[rim]]], axis=1)
                np.add.at(acc, (iy[rim], ix[rim]), mv); np.add.at(cnt, (iy[rim], ix[rim]), 1.0)
            field = projection.smooth_field(acc, cnt, sigma)
            toward, right, up = (np.asarray(a, np.float64) for a in projection.VIEW_AXES[v])
            moved = 0; peak = 0.0
            for (o, wco, wn, _), (rx, ry) in zip(data, proj):
                f = projection.sample_bilinear(field, rx, ry)
                disp = (f[:, :1] * right + (-f[:, 1:]) * up) / mapping[0]
                me = o.data
                keep = 1.0 - np.clip(_mask(me), 0, 1); keep[keep < 0.5] = 0.0
                disp *= keep[:, None]
                inv = np.linalg.inv(np.array(o.matrix_world, np.float64)[:3, :3])
                _set_co(me, _co(me) + disp @ inv.T)
                mag = np.linalg.norm(disp, axis=1)
                moved += int((mag > 1e-6).sum()); peak = max(peak, float(mag.max()) if len(mag) else 0.0)
            report.append({"view": v, "moved_verts": moved, "max_move": round(peak, 5), "registration": reg})
    _undo_push("blender-live fit_outline")
    return {"views": report}


def _register_view(v, tris_world, sdf, box):
    """Map the model's (n, 3, 3) world triangles onto one picture the way outline_match does: tight boxes, a refit
    on the rendered mask, then the shift that best overlays the picture's mask (sdf <= 0)."""
    h, w = sdf.shape
    tri_sc = projection.view_coords(tris_world.reshape(-1, 3), v).reshape(-1, 3, 3)
    pts = tri_sc.reshape(-1, 3)
    mapping = projection.fit_map((pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()), box)
    zb = projection.depth_buffer(tri_sc, mapping, w, h)
    mapping = projection.refit_mapping(mapping, np.isfinite(zb), box)
    zb = projection.depth_buffer(tri_sc, mapping, w, h)
    mapping, reg = projection.register_mapping(mapping, sdf <= 0, np.isfinite(zb))
    return mapping, reg, tri_sc


def cmd_part_map(req):
    """Which visible mesh under `object` is nearest the viewer at every pixel of each picture, registered as
    fit_outline registers. req["views"]: {VIEW: {"npy": picture outline distance field, "box": mask box, "out":
    .npy path for the label map}}. Labels index the returned names; -1 is no mesh. Assumes the rig is at rest."""
    views = {str(k).upper(): v for k, v in (req.get("views") or {}).items()}
    for v in views:
        if v not in projection.VIEW_AXES: raise ValueError(f"unknown view {v!r}")
    out = {}
    with _in_object_mode():
        dg = bpy.context.evaluated_depsgraph_get()
        tris = [(o.name, _eval_tris(o, dg)[0]) for o in _paint_scope(req) if o.type == "MESH"]
        if not tris: raise ValueError("no visible mesh under the object")
        tri_all = np.concatenate([t for _, t in tris])
        lab = np.concatenate([np.full(len(t), i, np.int32) for i, (_, t) in enumerate(tris)])
        for v, spec in views.items():
            sdf = np.load(spec["npy"]).astype(np.float64)
            mapping, reg, tri_sc = _register_view(v, tri_all, sdf, spec["box"])
            np.save(spec["out"], projection.label_buffer(tri_sc, lab, mapping, *sdf.shape[::-1]).astype(np.int16))
            out[v] = {"labels": spec["out"], "registration": reg}
    return {"names": [n for n, _ in tris], "views": out}


def cmd_part_carve(req):
    """Delete faces of req["meshes"] that are nearest the viewer in one picture where that picture shows another
    part: req["picture"] .npy label map (the picture's parts, same pixels as the outline field req["npy"]),
    req["where"] the label to carve at. A face goes when its centre lands on that label and nothing of the
    character is in front of it, so strands survive wherever the picture draws hair. Registered as fit_outline
    registers. Meshes with topology-changing modifiers are skipped."""
    v = str(req["view"]).upper()
    if v not in projection.VIEW_AXES: raise ValueError(f"unknown view {v!r}")
    targets = set(req.get("meshes") or []); where = int(req["where"])
    sdf = np.load(req["npy"]).astype(np.float64); pic = np.load(req["picture"]).astype(np.int32)
    h, w = sdf.shape
    report = {}
    with _in_object_mode():
        dg = bpy.context.evaluated_depsgraph_get()
        objs = [o for o in _paint_scope(req) if o.type == "MESH"]
        tri_all = np.concatenate([_eval_tris(o, dg)[0] for o in objs])
        mapping, reg, tri_sc = _register_view(v, tri_all, sdf, req["box"])
        zb = projection.depth_buffer(tri_sc, mapping, w, h)
        for o in objs:
            if o.name not in targets: continue
            ev = o.evaluated_get(dg); me_ev = ev.to_mesh()
            try: same = len(me_ev.polygons) == len(o.data.polygons)
            finally: ev.to_mesh_clear()
            if not same: report[o.name] = {"skipped": "topology-changing modifier"}; continue
            mw = np.array(o.matrix_world, np.float64); me = o.data
            cen = _get(me.polygons, "center", len(me.polygons), 3) @ mw[:3, :3].T + mw[:3, 3]
            sc = projection.view_coords(cen, v)
            rx, ry = projection.to_ref_px(sc[:, 0], sc[:, 1], mapping)
            ix = np.clip(rx.astype(np.int64), 0, w - 1); iy = np.clip(ry.astype(np.int64), 0, h - 1)
            inside = (rx >= 0) & (rx < w) & (ry >= 0) & (ry < h)
            front = sc[:, 2] >= zb[iy, ix] - 0.004                 # within 4 mm of the nearest surface there
            kill = np.nonzero(inside & front & (pic[iy, ix] == where))[0]
            if len(kill):
                import bmesh
                bm = bmesh.new(); bm.from_mesh(me); bm.faces.ensure_lookup_table()
                bmesh.ops.delete(bm, geom=[bm.faces[int(i)] for i in kill], context="FACES")
                bm.to_mesh(me); me.update(); bm.free()
            report[o.name] = {"deleted_faces": int(len(kill)), "faces_left": len(me.polygons)}
    _undo_push("blender-live part_carve")
    return {"view": v, "registration": reg, "meshes": report}


def _paint_scope(req):
    root = bpy.data.objects.get(req["object"])
    if root is None: raise KeyError(f"no object named {req['object']!r}")
    objs = [root] + list(root.children_recursive)
    for name in req.get("also") or []:
        x = bpy.data.objects.get(name)
        if x is None: raise KeyError(f"no object named {name!r} (in also)")
        objs += [x] + list(x.children_recursive)
    seen, out = set(), []
    for o in objs:
        if o.name not in seen and o.visible_get():
            seen.add(o.name); out.append(o)
    return out


def _eval_tris(o, dg):
    """World-space triangles, corner normals and UVs of the evaluated (posed, modified) mesh."""
    ev = o.evaluated_get(dg); me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        tv = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("vertices", tv)
        tl = np.empty(nt * 3, np.int32); me.loop_triangles.foreach_get("loops", tl)
        co = _get(me.vertices, "co", len(me.vertices), 3)
        mw = np.array(ev.matrix_world, np.float64)
        wco = co @ mw[:3, :3].T + mw[:3, 3]
        cn = _get(me.corner_normals, "vector", len(me.loops), 3)
        nmat = np.linalg.inv(mw[:3, :3]).T
        wn = cn @ nmat.T
        wn /= np.maximum(np.linalg.norm(wn, axis=1, keepdims=True), 1e-12)
        uv = None
        if me.uv_layers.active is not None:
            uv = _get(me.uv_layers.active.data, "uv", len(me.loops), 2)
        tv = tv.reshape(nt, 3); tl = tl.reshape(nt, 3)
        return wco[tv], wn[tl], (uv[tl] if uv is not None else None)
    finally:
        ev.to_mesh_clear()


def _flat_material(o, img):
    """One emission-only material showing img unchanged (projected painting already carries its own shading).
    The object's previous materials keep a fake user so they are not lost on save."""
    name = "PROJ_" + o.name
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img; tex.interpolation = "Cubic"   # sharper than Linear
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Strength"].default_value = 1.0
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"]); nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    for slot in o.material_slots:
        if slot.material is not None and slot.material is not mat: slot.material.use_fake_user = True
    o.data.materials.clear(); o.data.materials.append(mat)
    return mat.name


def cmd_show_paint(req):
    """Point every PROJ_<mesh> material under `object` at one picture's own colours (PVIEW_<view>_<mesh>, written
    by project_paint per_view=True; meshes without one show magenta) or, with view "", back at the painting.
    cleanup=True also deletes the PVIEW_ images."""
    view = str(req.get("view") or "").upper()
    if view:                                # the pictures show the rest pose; a posed rig measures another shape
        rigs = {m.object for o in _paint_scope(req) if o.type == "MESH"
                for m in o.modifiers if m.type == "ARMATURE" and m.object is not None}
        posed = [f"{r.name}:{b.name}" for r in rigs if r.data.pose_position == "POSE" for b in r.pose.bones
                 if b.rotation_quaternion.angle > 1e-4 or b.location.length > 1e-5 or any(abs(x) > 1e-4 for x in b.rotation_euler)]
        if posed:
            raise RuntimeError(f"rig is posed at frame {bpy.context.scene.frame_current} ({len(posed)} bones, e.g. "
                               f"{', '.join(posed[:3])}): go to the rest-pose frame or set the armature to Rest Position")
    blank = None
    if view:
        blank = bpy.data.images.get("PVIEW_NONE") or bpy.data.images.new("PVIEW_NONE", 4, 4, alpha=False)
        blank.pixels.foreach_set(np.tile(np.array([1.0, 0.0, 1.0, 1.0], np.float32), 16))
    shown = []
    for o in _paint_scope(req):
        mat = bpy.data.materials.get("PROJ_" + o.name)
        if o.type != "MESH" or mat is None or not mat.use_nodes or mat.name not in [m.name for m in o.data.materials if m]:
            continue
        tex = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE"), None)
        if tex is None: continue
        if view:
            tex.image = bpy.data.images.get(f"PVIEW_{view}_{o.name}") or blank
            tex.interpolation = "Closest"           # keep "not painted" magenta crisp at its edge
        else:
            tex.image = bpy.data.images.get("PROJ_" + o.name); tex.interpolation = "Cubic"
        shown.append(o.name)
    if req.get("cleanup"):
        for im in [i for i in bpy.data.images if i.name.startswith("PVIEW_")]:
            bpy.data.images.remove(im)
    return {"view": view, "meshes": shown}


OWNER_ORDER = ("FRONT", "LEFT", "BACK", "RIGHT", "TOP")
OWNER_COLOURS = np.array([[230, 40, 40], [40, 200, 60], [40, 90, 230], [240, 210, 30], [200, 60, 220]], np.float64)
FILL_COS = 0.5          # fill hidden texels only from paint a picture saw at least this squarely
FLAT_SHADE_NZ = -0.2    # flat_cos: a surface facing further down than this gets the part's shadow tone
FLAT_SHADE = 0.72       # flat_cos: shadow tone = base tone times this, when no shadow colour is given


def _hex_rgb(v):
    return np.array([int(str(v).lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], np.float64)


def _flat_tones(cols, given):
    """(base, shadow) sRGB 0-255 for one mesh: given colours first, else the median of its squarely seen paint
    without the drawing's dark ink lines."""
    if given is not None and len(given) >= 2: return given[0], given[1]
    if given is not None: base = given[0]
    else:
        keep = projection.srgb_to_lab(cols)[:, 0] > 30 if len(cols) else np.zeros(0, bool)
        pick = cols[keep] if keep.sum() >= 16 else cols
        base = np.median(pick, axis=0) if len(pick) else np.array([128.0, 128.0, 128.0])
    return base, base * FLAT_SHADE


def cmd_project_paint(req):
    """Project straight-on reference paintings onto the UVs of every visible mesh under `object`. A generator: the
    bridge runs it in slices with Blender redrawing in between, progress in the status bar.

    req["views"]: {VIEW: {"npy": path to (H, W, 4) uint8 RGBA, alpha = reference mask, colour already bled past the
    mask edge; "box": [x0, y0, x1, y1] tight mask box in that picture}}. Each picture is aligned to the model the
    way outline_match aligns them (tight boxes centred, one uniform scale). Per texel, a view contributes only where
    the surface faces it (cos > min_cos, weight cos**power) and where a depth buffer of the whole character says
    the texel is the nearest surface. Texels no view reaches (tops, undersides, between legs) take the colour of the
    nearest seen texel of the same mesh in 3D, not of whatever lies next to them in the UV layout; push-pull then
    fills the gutters between UV islands."""
    views = {str(k).upper(): v for k, v in (req.get("views") or {}).items()}
    if not views: raise ValueError("views is empty")
    for v in views:
        if v not in projection.VIEW_AXES: raise ValueError(f"unknown view {v!r}; use FRONT, BACK, LEFT, RIGHT or TOP")
    tex_size = int(req.get("tex_size", 2048)); power = float(req.get("power", 6.0))
    min_cos = float(req.get("min_cos", 0.12)); material = req.get("material", "flat")
    min_cos_other = float(req.get("min_cos_other", 0.35))
    underside_cos = float(req.get("underside_cos", 0.0))
    # flat_cos [lo, hi]: paint stays where the winning picture saw the surface at cos >= hi; below, it blends into
    # the mesh's flat tone (base, or shadow where the surface faces down), which every unseen texel takes too.
    # Level pictures only stretch a row of pixels over a grazing surface; a flat tone looks the same from any angle.
    flat_cos = [float(c) for c in (req.get("flat_cos") or [])]
    if flat_cos and not (len(flat_cos) == 2 and 0.0 <= flat_cos[0] < flat_cos[1] <= 1.0):
        raise ValueError("flat_cos must be [lo, hi] with 0 <= lo < hi <= 1")
    if material not in ("flat", "none"): raise ValueError("material must be 'flat' or 'none'")
    only = set(req.get("targets") or [])
    prio_names = [str(v).upper() for v in (req.get("priority_views") or [])]
    prio_cos = float(req.get("priority_cos", 0.45))
    bias = {str(k).upper(): float(v) for k, v in (req.get("view_bias") or {}).items()}
    warp = bool(req.get("warp", True)); warp_sigma = float(req.get("warp_sigma", 8.0))
    palette_de = float(req.get("palette_de", 28.0))
    palette_view = str(req.get("palette_view") or "").upper()
    save_dir = req.get("save_dir") or ""
    owner_debug = req.get("debug") == "owner"
    # mesh name -> "#rrggbb" or ["#base", "#shadow"]: texels no picture paints on that mesh take this flat colour
    # (skin under the chin, shadow on hair undersides) instead of copying the nearest painted texels, which smears
    # whatever is nearby; with flat_cos these are the mesh's base and shadow tones
    fill_colours = {str(k): np.array([_hex_rgb(c) for c in ([v] if isinstance(v, str) else v)], np.float64)
                    for k, v in (req.get("fill_colours") or {}).items()}
    # per_view: write each picture's own colours (PVIEW_<VIEW>_<mesh>, magenta where that picture does not paint)
    # instead of the blended painting, for three_quarter_check; the PROJ_ images and materials stay untouched
    per_view = bool(req.get("per_view"))
    if per_view: material = "none"
    t0 = time.time()
    with _in_object_mode():
        dg = bpy.context.evaluated_depsgraph_get()
        scope = _paint_scope(req)
        meshes = [o for o in scope if o.type == "MESH"]
        skipped = [{"object": o.name, "reason": f"{o.type} is not a mesh"} for o in scope
                   if o.type in ("CURVES", "CURVE", "SURFACE", "META", "FONT")]
        tris = {}
        for o in meshes:
            tris[o.name] = _eval_tris(o, dg)
            yield f"project_paint: read {o.name}"
        if not tris: raise ValueError("no visible mesh under the object")
        allp = np.concatenate([t[0].reshape(-1, 3) for t in tris.values()])
        alltri = np.concatenate([t[0] for t in tris.values()])
        refs, regs = {}, {}
        for v, spec in views.items():
            rgba = np.load(spec["npy"])
            h, w = rgba.shape[:2]
            sc = projection.view_coords(allp, v)
            mbox = (sc[:, 0].min(), sc[:, 1].min(), sc[:, 0].max(), sc[:, 1].max())
            mapping = projection.fit_map(mbox, spec["box"])
            tri_sc = projection.view_coords(alltri.reshape(-1, 3), v).reshape(-1, 3, 3)
            zbuf = projection.depth_buffer(tri_sc, mapping, w, h)
            yield f"project_paint: {v} depth"
            mapping = projection.refit_mapping(mapping, np.isfinite(zbuf), spec["box"])
            zbuf = projection.depth_buffer(tri_sc, mapping, w, h)
            yield f"project_paint: {v} fitted"
            mapping, reg = yield from projection.register_mapping_steps(mapping, rgba[..., 3] >= 128, np.isfinite(zbuf))
            yield f"project_paint: {v} registered"
            zbuf = projection.depth_buffer(tri_sc, mapping, w, h)
            yield f"project_paint: {v} depth"
            field = projection.warp_field(rgba[..., 3] >= 128, np.isfinite(zbuf), sigma=warp_sigma) if warp else None
            if field is not None:
                reg["warp_max_px"] = round(float(np.abs(field).max()), 2)
            # where a secondary picture may paint: 2 px inside the model's outline (its depth test flickers row by
            # row at the edge) and 2 px inside the drawn figure (outside it the colours are bled backdrop, which
            # streaks across a limb the drawing makes narrower than the model)
            drawn = rgba[..., 3] >= 128
            inner = ((np.abs(projection.distance_field(np.isfinite(zbuf))) >= 2.0)
                     & drawn & (np.abs(projection.distance_field(drawn)) >= 2.0))
            yield f"project_paint: {v} outlines"
            refs[v] = (rgba[..., :3].astype(np.float64), mapping, zbuf, field, inner, drawn)
            regs[v] = reg
            yield f"project_paint: lined up the {v} picture"
        names = list(refs)
        pal_view = palette_view or (prio_names[0] if prio_names else "")
        pal_view = pal_view if pal_view in refs else None

        def sample(v, p, nrm):
            """(seen, cos, colour) of view v at world points p with normals nrm."""
            rgb, mapping, zbuf, field, inner, drawn = refs[v]
            sc = projection.view_coords(p, v)
            cos = nrm @ np.asarray(projection.VIEW_AXES[v][0], np.float64)
            rx, ry = projection.to_ref_px(sc[:, 0], sc[:, 1], mapping)
            hh, ww = zbuf.shape
            ix = np.clip(rx.astype(np.int64), 0, ww - 1); iy = np.clip(ry.astype(np.int64), 0, hh - 1)
            eps = (1.5 / mapping[0]) / np.maximum(cos, 0.15) + 0.002
            primary = v in prio_names or not prio_names
            floor = min_cos if primary else max(min_cos, min_cos_other)
            seen = (cos > floor) & (sc[:, 2] >= zbuf[iy, ix] - eps)   # grazing paint smears one picture row over many texels
            if underside_cos > 0:                                   # an underside only a picture from below shows
                seen &= ~((nrm[:, 2] < -0.5) & (cos < underside_cos))
            if not primary:
                seen &= inner[iy, ix]
            else:
                seen &= drawn[iy, ix]
            col = np.zeros((len(p), 3))
            if seen.any():
                qx, qy = rx[seen], ry[seen]
                if field is not None:
                    dxy = projection.sample_bilinear(field, qx, qy); qx = qx + dxy[:, 0]; qy = qy + dxy[:, 1]
                col[seen] = projection.sample_bilinear(rgb, qx, qy)
            return seen, cos, col

        painted, all_hist = [], np.zeros(101)
        t_setup = round(time.time() - t0, 1)
        for o in meshes:
            if only and o.name not in only: continue
            t_obj = time.time()
            wt, wn, uv = tris[o.name]
            if uv is None:
                skipped.append({"object": o.name, "reason": "no UV map"}); continue
            size = tex_size if len(wt) >= 2000 else max(256, tex_size // 4)
            centres, rejected = None, 0
            if pal_view and palette_de > 0:                 # what colours does the main picture put on this mesh?
                trusted = []
                for ti, px, py, bary in projection.raster(uv * size, size, size):
                    pick = slice(None, None, 4)
                    p = np.einsum("ij,ijk->ik", bary[pick], wt[ti[pick]])
                    nrm = np.einsum("ij,ijk->ik", bary[pick], wn[ti[pick]])
                    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
                    seen, cos, col = sample(pal_view, p, nrm)
                    keep = seen & (cos >= 0.5)
                    if keep.any(): trusted.append(col[keep])
                    yield f"project_paint {o.name}: reading its colours"
                if trusted and sum(len(t) for t in trusted) >= 200:
                    centres = projection.palette(projection.srgb_to_lab(np.concatenate(trusted)))
            acc = np.zeros((size * size, 3), np.float32); wsum = np.zeros(size * size, np.float32)
            if per_view:
                acc_v = np.zeros((len(refs), size * size, 3), np.float32); cnt_v = np.zeros((len(refs), size * size), np.float32)
            best_cos = np.zeros(size * size, np.float32)          # how squarely the winning picture saw each texel
            share = {v: 0.0 for v in refs}
            de_hist = np.zeros(101)
            prio = [k for k, v in enumerate(names) if v in prio_names]
            covered = np.zeros(size * size, bool)
            all_idx, all_p, all_n = [], [], []
            n_done = 0
            for ti, px, py, bary in projection.raster(uv * size, size, size):
                idx = py * size + px
                covered[idx] = True
                p = np.einsum("ij,ijk->ik", bary, wt[ti])
                nrm = np.einsum("ij,ijk->ik", bary, wn[ti])
                nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
                all_idx.append(idx); all_p.append(p.astype(np.float32)); all_n.append(nrm[:, 2].astype(np.float32))
                n = len(idx); W = np.zeros((len(refs), n)); C = np.zeros((len(refs), n, 3)); COS = np.zeros((len(refs), n))
                for k, v in enumerate(names):
                    seen, cos, col = sample(v, p, nrm)
                    if centres is not None and v != pal_view and seen.any():
                        bad = np.zeros(n, bool)
                        bad[seen] = projection.foreign(projection.srgb_to_lab(col[seen]), centres, palette_de)
                        rejected += int(bad.sum()); seen &= ~bad
                    if not seen.any(): continue
                    W[k, seen] = np.clip(cos[seen], 0, 1) ** power * bias.get(v, 1.0)
                    C[k] = col
                    COS[k] = np.where(seen, cos, 0.0)
                if per_view:                     # every picture on its own, before priority picks a winner
                    u_v, inv_v = np.unique(idx, return_inverse=True)
                    for k in range(len(refs)):
                        sk = W[k] > 0
                        if not sk.any(): continue
                        for c in range(3):
                            acc_v[k, u_v, c] += np.bincount(inv_v, weights=np.where(sk, C[k][:, c], 0.0), minlength=len(u_v))
                        cnt_v[k, u_v] += np.bincount(inv_v, weights=sk.astype(np.float64), minlength=len(u_v))
                if prio:
                    own = np.zeros(n, bool)
                    for k in prio: own |= COS[k] >= prio_cos
                    for k in range(len(refs)):
                        if k not in prio: W[k, own] = 0.0
                both = np.zeros(n, bool)
                if len(refs) >= 2:
                    order = np.argsort(-W, axis=0)
                    w1 = np.take_along_axis(W, order[:1], 0)[0]; w2 = np.take_along_axis(W, order[1:2], 0)[0]
                    both = (w2 > 0) & (w2 >= 0.25 * w1)
                if both.any():
                    c1 = C[order[0, both], np.nonzero(both)[0]]; c2 = C[order[1, both], np.nonzero(both)[0]]
                    de = projection.delta_e00(projection.srgb_to_lab(c1), projection.srgb_to_lab(c2))
                    de_hist += np.bincount(np.clip(de, 0, 100).astype(np.int64), minlength=101)[:101]
                u, inv = np.unique(idx, return_inverse=True)
                col_w = (W[..., None] * C).sum(axis=0)
                if owner_debug:                  # every texel in the colour of the picture that won it
                    col_w = W.sum(axis=0)[:, None] * OWNER_COLOURS[np.array([OWNER_ORDER.index(v) for v in names])][W.argmax(axis=0)]
                for c in range(3): acc[u, c] += np.bincount(inv, weights=col_w[:, c], minlength=len(u))
                wsum[u] += np.bincount(inv, weights=W.sum(axis=0), minlength=len(u))
                won = np.where(W.max(axis=0) > 0, np.take_along_axis(COS, W.argmax(axis=0)[None], 0)[0], 0.0)
                np.maximum.at(best_cos, idx, won.astype(np.float32))
                for k, v in enumerate(names): share[v] += float(W[k].sum())
                n_done += len(idx)
                yield f"project_paint {o.name}: {n_done:,} texels painted"
            t_paint = time.time()
            if per_view:
                cov2 = covered.reshape(size, size); views_seen = {}
                for k, v in enumerate(names):
                    hv = cnt_v[k] > 0
                    rgbv = np.empty((size * size, 3)); rgbv[:] = (255.0, 0.0, 255.0)
                    rgbv[hv] = acc_v[k][hv] / cnt_v[k][hv, None]
                    padded, grown = projection.bleed(rgbv.reshape(size, size, 3), cov2, iterations=4, return_mask=True)
                    padded[~grown] = (255.0, 0.0, 255.0)
                    pname = f"PVIEW_{v}_{o.name}"
                    old = bpy.data.images.get(pname)
                    if old is not None: bpy.data.images.remove(old)
                    pimg = bpy.data.images.new(pname, size, size, alpha=False)
                    px4 = np.ones((size, size, 4), np.float32); px4[..., :3] = np.clip(padded / 255.0, 0, 1)
                    pimg.pixels.foreach_set(px4.ravel())
                    views_seen[v] = round(100.0 * int((hv & covered).sum()) / max(int(covered.sum()), 1), 2)
                painted.append({"object": o.name, "tex_px": size, "per_view_seen_pct": views_seen})
                del acc, wsum, all_idx, all_p, acc_v, cnt_v
                continue
            have = wsum > 0
            rgb = np.zeros((size * size, 3)); rgb[have] = acc[have] / wsum[have, None]
            n_seen = int((have & covered).sum())
            tones = None
            if all_idx and n_seen:
                ai = np.concatenate(all_idx); ap = np.concatenate(all_p); anz = np.concatenate(all_n)
                _, first = np.unique(ai, return_index=True); ai, ap, anz = ai[first], ap[first], anz[first]
                hit = have[ai]
                miss_i = ai[~hit]
                if flat_cos and not owner_debug:
                    lo, hi = flat_cos
                    square = hit & (best_cos[ai] >= hi)
                    base, shade = _flat_tones(rgb[ai[square]], fill_colours.get(o.name))
                    tone = np.where((anz < FLAT_SHADE_NZ)[:, None], shade[None], base[None])
                    w = np.where(hit, np.clip((best_cos[ai] - lo) / (hi - lo), 0.0, 1.0), 0.0)[:, None]
                    rgb[ai] = w * rgb[ai] + (1.0 - w) * tone
                    have[miss_i] = True
                    tones = {"base": "#%02x%02x%02x" % tuple(int(round(c)) for c in np.clip(base, 0, 255)),
                             "shadow": "#%02x%02x%02x" % tuple(int(round(c)) for c in np.clip(shade, 0, 255)),
                             "painted_pct": round(100.0 * float(square.sum()) / max(len(ai), 1), 1)}
                elif len(miss_i):
                    # fill only from paint some picture saw squarely: texels painted edge-on carry the picture's
                    # outline ink, and a fill from them streaks dark dashes along legs and sleeves
                    src = hit & (best_cos[ai] >= FILL_COS)
                    if src.sum() < 0.2 * hit.sum(): src = hit
                    if owner_debug:
                        rgb[miss_i] = np.array([128.0, 128.0, 128.0])
                    elif o.name in fill_colours:
                        rgb[miss_i] = fill_colours[o.name][0]
                    else:
                        rgb[miss_i] = projection.fill_3d(ap[src].astype(np.float64), rgb[ai[src]], ap[~hit].astype(np.float64))
                    have[miss_i] = True
            t_fill = time.time()
            yield f"project_paint {o.name}: filling hidden texels done, writing the image"
            # pad every UV island with its own edge colour first, so texture filtering at a seam never reads a
            # neighbouring island; push-pull then fills the rest of the gutter
            padded, grown = projection.bleed(rgb.reshape(size, size, 3), have.reshape(size, size), iterations=6,
                                             return_mask=True)
            filled = projection.push_pull(padded, grown.astype(np.float64))
            name = "PROJ_" + o.name
            old = bpy.data.images.get(name)
            if old is not None:                  # a packed image keeps its first packed copy: replace it, never reuse
                bpy.data.images.remove(old)
            img = bpy.data.images.new(name, size, size, alpha=False)
            px4 = np.ones((size, size, 4), np.float32); px4[..., :3] = np.clip(filled / 255.0, 0, 1)
            img.pixels.foreach_set(px4.ravel())
            if save_dir:
                os.makedirs(save_dir, exist_ok=True)
                img.filepath_raw = os.path.join(save_dir, name + ".png"); img.file_format = "PNG"; img.save()
            img.pack()
            tot = sum(share.values()) or 1.0
            all_hist += de_hist
            painted.append({"object": o.name, "tex_px": size, "uv_texels": int(covered.sum()),
                            "seconds": {"paint": round(t_paint - t_obj, 1), "fill": round(t_fill - t_paint, 1),
                                        "write": round(time.time() - t_fill, 1)},
                            "seen_pct": round(100.0 * n_seen / max(int(covered.sum()), 1), 2),
                            "view_share": {v: round(s / tot, 3) for v, s in share.items()},
                            "foreign_samples_dropped": rejected, "palette_colours": 0 if centres is None else len(centres),
                            "cross_view": projection.de_hist_stats(de_hist),
                            "image": img.name, "flat_tones": tones,
                            "material": _flat_material(o, img) if material == "flat" else None})
            del acc, wsum, all_idx, all_p, all_n
    _undo_push("blender-live project_paint")
    return {"painted": painted, "skipped": skipped, "registration": regs, "setup_seconds": t_setup,
            "cross_view": projection.de_hist_stats(all_hist), "seconds": round(time.time() - t0, 2)}
