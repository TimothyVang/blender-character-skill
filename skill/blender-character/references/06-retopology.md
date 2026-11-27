# 06 Retopology

Course source: chapter 07 "Intro to Retopology (Face Retopology)", chapter 08 "Retopologizing the Body", chapter 09
"Retopologizing the Clothes & Accessories", 06:02:34 to 10:44:02. The course screen shows Blender 5.0.1; everything
below was checked in 4.5.16.

## Goal

Every part of the character exists a second time as a light, all-quad mesh whose edge loops follow the way the part
bends: a body of about 10,000 faces with loops round the eyes, mouth, shoulders, elbows, wrists, knees and hips, eye
sockets and a mouth bag, eyeballs and teeth in place, and one low-poly mesh per garment that copies the body's edge
layout underneath it. Each low-poly mesh, subdivided, lies on its sculpt, and the sculpts are kept (hidden) for baking.

## Starting state

- The finished sculpts from stages 04 and 05, all parented to `CHARACTER`: `BLK_head`, `BLK_eye`, `BLK_neck`,
  `BLK_ears`, `BLK_torso`, `BLK_leg`, `BLK_arm`, `BLK_hand`, `BLK_foot`, and the pieces `Shirt`, `Skirt`, `Boot.L`,
  `Boot.R`, `Hair.Cap`, `Hair.Lock`. They are still separate objects, in a neutral pose, symmetric across X, facing
  -Y, at real size (stage 01).
- The reference pictures used for `outline_match` so far.
- Nothing has been named or sorted yet. The course fixes that first (step 1).

## Why this stage exists

- A sculpt is millions of faces in no order (the course's reads 2 million triangles at [06:08:07]). It cannot be
  rigged, unwrapped or textured in practice. Retopology rebuilds the same surface with few faces placed on purpose
  [06:07:53].
- The course builds for animation and offline rendering, not games [06:07:11]: the mesh will carry a Subdivision
  modifier at render time, so a moderate face count is fine, but it must be quads, because quads subdivide
  predictably and let a loop cut run through [06:12:12].
- Words used below [06:09:04 to 06:18:20]. Triangle, quad, n-gon: faces with 3, 4, 5 or more edges. Edge loop: a
  chain of edges that runs on across the mesh. Edge flow: the direction the loops take over a form. Pole: a vertex
  where the number of edges is not 4. Poles are how loops turn and how the loop count changes; the course allows
  3-poles and 5-poles only, because 6 and more pinch and stretch [06:16:16].

## The helpers

The course places vertices by hand with face snapping. The reader cannot, so these functions do the same jobs from
coordinates. Run this block once: it stores the code in a text block (saved with the file). Start every later
`exec_python` call with `exec(D.texts["retopo_lib"].as_string())`, because each call gets a fresh namespace.

```python
# [helpers] verified in 4.5.16 background
LIB = r'''
import bpy, bmesh, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

class Surf:
    """Nearest-point and ray queries on a sculpt, in world space."""
    def __init__(self, obj):
        self.M = obj.matrix_world.copy(); self.Mi = self.M.inverted(); self.R = self.Mi.to_3x3()
        self.tree = BVHTree.FromObject(obj, bpy.context.evaluated_depsgraph_get())
    def near(self, p):
        return self.M @ self.tree.find_nearest(self.Mi @ Vector(p))[0]
    def ray(self, origin, direction, dist=10.0):
        co = self.tree.ray_cast(self.Mi @ Vector(origin), (self.R @ Vector(direction)).normalized(), dist)[0]
        return None if co is None else self.M @ co
    def ring(self, centre, axis, n, ref=(0, -1, 0), half=False):
        """n points round a limb: rays from `centre` (inside the sculpt) outward, square to `axis`, first ray along `ref`.
        half=True: n/2+1 points from `ref` round through +X to the opposite side, both ends pinned to x=0 (for Mirror)."""
        c, a = Vector(centre), Vector(axis).normalized()
        u = Vector(ref); u = (u - a * u.dot(a)).normalized(); v = a.cross(u)
        if half and v.x < 0: v = -v
        out = []
        for j in range(n // 2 + 1 if half else n):
            t = 2 * math.pi * j / n; d = u * math.cos(t) + v * math.sin(t)
            p = self.ray(c, d)
            if p is None: p = self.near(c + d * 0.05)
            if half and j in (0, n // 2): p.x = 0.0
            out.append(p)
        return out
    def drop(self, pts, direction, back=0.5):
        """Push points onto the surface along `direction`, each ray starting `back` metres before its point."""
        d = Vector(direction).normalized(); out = []
        for p in pts:
            q = self.ray(Vector(p) - d * back, d)
            out.append(self.near(p) if q is None else q)
        return out

def ellipse(centre, rx, rz, n, half=False):
    """Points on an ellipse in the XZ plane (a ring seen from the front). Full: n points. half=True: n/2+1 points
    from the top, round through +X, to the bottom, both ends on the centre's x (give a centre with x=0)."""
    c = Vector(centre)
    return [c + Vector((rx * math.sin(2 * math.pi * j / n), 0, rz * math.cos(2 * math.pi * j / n))) for j in range(n // 2 + 1 if half else n)]

def new_lowpoly(name, collection="Lowpoly"):
    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection); bpy.context.scene.collection.children.link(col)
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name)); col.objects.link(obj)
    obj.show_wire = True; obj.show_all_edges = True
    root = bpy.data.objects.get("CHARACTER")
    if root is not None: obj.parent = root               # the whole-character checks include every low-poly
    return obj

def act(obj):
    """Make obj the only selected, active object (what the bpy.ops.object operators act on)."""
    for o in bpy.context.view_layer.objects: o.select_set(False)
    obj.select_set(True); bpy.context.view_layer.objects.active = obj

def _write(bm, obj):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(obj.data); bm.free(); obj.data.update()

def add_grid(obj, rows, closed=False, tol=1e-4):
    """Add quads between consecutive rows of world points (rows of equal length). closed=True wraps each row into a
    ring. A point within `tol` of an existing vertex is welded to it: pass a border's exact coordinates to stitch."""
    bm = bmesh.new(); bm.from_mesh(obj.data); Mi = obj.matrix_world.inverted()
    vs = [[bm.verts.new(Mi @ Vector(p)) for p in row] for row in rows]; m = len(rows[0])
    for i in range(len(rows) - 1):
        for j in range(m if closed else m - 1):
            k = (j + 1) % m
            try: bm.faces.new((vs[i][j], vs[i][k], vs[i + 1][k], vs[i + 1][j]))
            except ValueError: pass
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=tol)
    _write(bm, obj)

def snap(obj, surf, skip_group=""):
    """Put every vertex on the nearest point of the sculpt (what applying a Shrinkwrap does). Verts in `skip_group`
    stay; centre-line verts keep x=0."""
    M, Mi = obj.matrix_world, obj.matrix_world.inverted()
    gi = obj.vertex_groups[skip_group].index if skip_group else -1
    for v in obj.data.vertices:
        if gi >= 0 and any(g.group == gi and g.weight > 0.5 for g in v.groups): continue
        mid = abs(v.co.x) < 1e-5
        v.co = Mi @ surf.near(M @ v.co)
        if mid: v.co.x = 0.0
    obj.data.update()

def relax(obj, surf, iters=10, factor=0.5, skip_group=""):
    """Even out the quads, then put the verts back on the sculpt: the stand-in for the Relax Slide brush with Shift.
    Open borders stay put; centre-line verts (x=0 under a Mirror) slide only along the centre line."""
    mid = lambda v: abs(v.co.x) < 1e-5
    for _ in range(iters):
        bm = bmesh.new(); bm.from_mesh(obj.data)
        vs = [v for v in bm.verts if not v.is_boundary or
              (mid(v) and all(mid(e.other_vert(v)) for e in v.link_edges if e.is_boundary))]
        bmesh.ops.smooth_vert(bm, verts=vs, factor=factor, mirror_clip_x=True, clip_dist=1e-5,
                              use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.to_mesh(obj.data); bm.free()
        snap(obj, surf, skip_group)

def borders(bm, obj=None, point=None):
    """Open borders as ordered edge lists; with `point` (world), the border with the closest vertex comes first."""
    left = {e for e in bm.edges if e.is_boundary}; loops = []
    while left:
        e = left.pop(); loop = [e]; v = e.verts[1]
        while True:
            nxt = [x for x in v.link_edges if x in left]
            if not nxt: break
            e = nxt[0]; left.discard(e); loop.append(e); v = e.other_vert(v)
        loops.append(loop)
    if point is not None:
        p = obj.matrix_world.inverted() @ Vector(point)
        loops.sort(key=lambda l: min((v.co - p).length for e in l for v in e.verts))
    return loops

def border_points(obj, point, start, toward):
    """World coordinates of the open border nearest `point`, in order, beginning at the border vertex nearest
    `start` and walking in the direction of `toward`. Slice it to get the exact points to stitch to."""
    bm = bmesh.new(); bm.from_mesh(obj.data); loop = borders(bm, obj, point)[0]; M = obj.matrix_world
    vs = [loop[i].verts[0] if loop[i].verts[0] in loop[i - 1].verts else loop[i].verts[1] for i in range(len(loop))]
    pts = [M @ v.co for v in vs]; bm.free()
    i = min(range(len(pts)), key=lambda k: (pts[k] - Vector(start)).length); pts = pts[i:] + pts[:i]
    if len(pts) > 2 and (pts[-1] - Vector(toward)).length < (pts[1] - Vector(toward)).length: pts = pts[:1] + pts[:0:-1]
    return pts

def bridge_near(obj, point):
    """Bridge the open border nearest `point` to the next nearest border with the same edge count."""
    bm = bmesh.new(); bm.from_mesh(obj.data); loops = borders(bm, obj, point)
    pair = loops[:1] + [l for l in loops[1:] if len(l) == len(loops[0])][:1]
    if len(pair) < 2:
        n = [len(l) for l in loops]; bm.free(); raise ValueError(f"no second border with the same edge count: {n}")
    bmesh.ops.bridge_loops(bm, edges=pair[0] + pair[1])
    _write(bm, obj)

def cap(obj, point, span=2, offset=0):
    """Close the open border nearest `point` with a quad grid `span` faces wide (Grid Fill). Needs an even edge
    count. `offset` turns the grid round the border by that many edges."""
    bm = bmesh.new(); bm.from_mesh(obj.data); loop = borders(bm, obj, point)[0]; n = len(loop)
    if n % 2: bm.free(); raise ValueError(f"border has {n} edges; grid fill needs an even count")
    loop = loop[offset:] + loop[:offset]
    bmesh.ops.grid_fill(bm, edges=loop[:span] + loop[n // 2:n // 2 + span], use_interp_simple=True)
    _write(bm, obj)

def extrude_border(obj, point, moves, group=""):
    """Extrude the open border nearest `point` once per entry of moves = [(scale, (dx, dy, dz)), ...]: each new ring
    is the last one scaled about its own centre, then shifted (world units). New verts are put in `group`."""
    bm = bmesh.new(); bm.from_mesh(obj.data); loop = borders(bm, obj, point)[0]
    dl = bm.verts.layers.deform.verify()
    gi = (obj.vertex_groups.get(group) or obj.vertex_groups.new(name=group)).index if group else -1
    for s, d in moves:
        new = bmesh.ops.extrude_edge_only(bm, edges=loop)["geom"]
        vs = [g for g in new if isinstance(g, bmesh.types.BMVert)]; loop = [g for g in new if isinstance(g, bmesh.types.BMEdge)]
        c = sum((v.co for v in vs), Vector()) / len(vs)
        for v in vs:
            v.co = c + (v.co - c) * s + Vector(d)
            if gi >= 0: v[dl][gi] = 1.0
    _write(bm, obj)

def joint_patch(obj, pick, offset):
    """Turn the picked edges into three parallel edge runs (bevel, 2 segments) and close the ends as quads: the
    course's Ctrl+B, slide-to-merge, dissolve. A run that stops inside the mesh ends in one 3-pole and one 5-pole;
    a closed loop, or an end on an open border, ends clean. pick(mid_world, edge) -> bool. Returns edges picked."""
    bm = bmesh.new(); bm.from_mesh(obj.data); M = obj.matrix_world
    es = [e for e in bm.edges if pick(M @ ((e.verts[0].co + e.verts[1].co) / 2), e)]
    bmesh.ops.bevel(bm, geom=es, offset=offset, offset_type="OFFSET", segments=2, profile=0.5, affect="EDGES")
    def tri_pairs(): return [e for e in bm.edges if len(e.link_faces) == 2 and all(len(f.verts) == 3 for f in e.link_faces)]
    merges = []
    for e in tri_pairs():
        tv = {v for f in e.link_faces for v in f.verts}
        tip = next(v for v in e.verts if any(len(f.verts) > 4 for f in v.link_faces))
        merges.append((next(x.other_vert(tip) for x in tip.link_edges if x.other_vert(tip) not in tv), tip))
    for far, tip in merges: bmesh.ops.pointmerge(bm, verts=[far, tip], merge_co=far.co)
    bmesh.ops.dissolve_edges(bm, edges=tri_pairs(), use_verts=False)
    _write(bm, obj)
    return len(es)

def census(obj):
    """Topology in numbers. valence counts interior verts by edge count: 4 is regular, 3 and 5 are the allowed poles."""
    bm = bmesh.new(); bm.from_mesh(obj.data); val = {}
    for v in bm.verts:
        if not v.is_boundary: val[len(v.link_edges)] = val.get(len(v.link_edges), 0) + 1
    r = {"verts": len(bm.verts), "faces": len(bm.faces),
         "tris": sum(len(f.verts) == 3 for f in bm.faces), "ngons": sum(len(f.verts) > 4 for f in bm.faces),
         "valence": dict(sorted(val.items())), "bad_poles": sum(n for k, n in val.items() if k > 5 or k < 3),
         "open_borders": sorted(len(l) for l in borders(bm)),
         "non_manifold": sum(1 for e in bm.edges if not e.is_manifold and not e.is_boundary)}
    bm.free(); return r

def deviation(low, sculpt, levels=2, samples=20000):
    """Distance in metres between the sculpt and the low-poly as it will render (its modifiers plus `levels` more
    subdivision). sculpt_to_low finds parts the low-poly does not cover; low_to_sculpt finds low-poly off the surface."""
    tmp = low.modifiers.new("_dev", "SUBSURF"); tmp.levels = levels
    dg = bpy.context.evaluated_depsgraph_get(); dg.update()
    ev = low.evaluated_get(dg)
    t_low, t_hi = BVHTree.FromObject(low, dg), BVHTree.FromObject(sculpt, dg)
    Ml, Ms = low.matrix_world, sculpt.matrix_world
    def side(pts, tree, Mi):
        d = np.array([tree.find_nearest(Mi @ p)[3] for p in pts])
        return {"max": round(float(d.max()), 5), "p99": round(float(np.percentile(d, 99)), 5), "mean": round(float(d.mean()), 5)}
    hv = sculpt.data.vertices; lv = ev.data.vertices
    a = side([Ms @ hv[i].co for i in range(0, len(hv), max(1, len(hv) // samples))], t_low, Ml.inverted())
    b = side([Ml @ lv[i].co for i in range(0, len(lv), max(1, len(lv) // samples))], t_hi, Ms.inverted())
    low.modifiers.remove(tmp)
    return {"sculpt_to_low": a, "low_to_sculpt": b}
'''
t = bpy.data.texts.get("retopo_lib") or bpy.data.texts.new("retopo_lib")
t.clear(); t.write(LIB); result = "retopo_lib stored"
```

All coordinates in the examples below belong to a 1.65 m test dummy (arms along X at z 1.25, head centre z 1.53).
Replace them with points measured on your sculpt: `Surf(sculpt).drop([(x, -1, z)], (0, 1, 0))` gives the surface
point seen from the front at (x, z), and a `viewport_capture` after each call shows whether the new faces sit right.

## Order of work

### A. Prepare the sculpt [06:21:13 to 06:43:27]

1. **Sort and name.** The course moves sculpts into a collection `Highpoly` (with `cloths` and `hair` inside) and
   makes an empty collection `Lowpoly` for all new meshes [06:21:32, 06:43:15]. Why: from here on every part exists
   twice and the two must never be confused. `new_lowpoly()` creates `Lowpoly` on first use.
2. **Set real size, only if it is not already** [06:22:52]. This skill works at real size from stage 01, so check
   `mesh_report` bounds first and skip this step when the figure is already about 1.7 m. The course's sculpt was made
   at an arbitrary size (about ten times too big): it adds a 2 m cube as a ruler, scales everything about the 3D
   cursor at the floor until the figure is about 1.6 to 1.7 m, then applies all transforms. Why now: modifier distances, the rig and cloth all read real units. After scaling,
   Solidify thickness and Skin radii are wrong and are corrected by hand (0.003 on the skirt sculpt [06:26:16]).

```python
# [scale] verified in 4.5.16 background
from mathutils import Vector, Matrix
HEIGHT = 1.7                                          # this skill's default; the course: "about 1.6 or 1.7"
bpy.context.view_layer.update()
objs = [o for o in bpy.context.scene.objects if o.name != "CHARACTER"]   # the root stays at the origin
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
zs = [(o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box]
s = HEIGHT / (max(zs) - min(zs)); T = Matrix.Translation((0, 0, -min(zs) * s)) @ Matrix.Scale(s, 4)
olds = {o.name: o.matrix_world.copy() for o in objs}  # read every transform before changing any
for o in objs:
    new = T @ olds[o.name]
    if o.type == "MESH" and o.data.users == 1:           # linked duplicates cannot be applied; the course skips them too
        o.data.transform(new); o.matrix_world = Matrix.Identity(4)
    else: o.matrix_world = new
for o in meshes:
    for m in o.modifiers:
        if m.type == "SOLIDIFY": m.thickness *= s        # the course retypes these by hand
bpy.context.view_layer.update()
result = {"scale": round(s, 5)}
```

3. **Fuse the body into one sculpt** [06:27:44 to 06:43:09]. Apply modifiers on head, ears, neck, torso, legs and
   arms, join them, voxel remesh so they become one skin, then repair what the remesh softened. The course's voxel
   size is 0.008 m; 0.076 wiped the detail [06:29:27]. Hands and feet are left out of the remesh because they need a
   much finer voxel than the rest; they are added with two Boolean (Union) modifiers instead, then applied [06:38:12].
   The joins are smoothed (Clay Strips to add volume, Smooth), and lids, nostril edge, lip line, ear folds, armpit,
   under-bust and rib lines are re-cut with Crease Polish, because vertices are about to be placed on those lines
   [06:31:37]. Ankle bones are added, the inner one higher than the outer [06:42:11]. The result is named `Body`
   (it stays under `CHARACTER`). `BLK_eye` stays separate and is replaced by `Eye.L` and `Eye.R` in step 17.

```python
# [fuse] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
parts = [D.objects[n] for n in ("BLK_head", "BLK_ears", "BLK_neck", "BLK_torso", "BLK_leg", "BLK_arm")]
for o in bpy.context.view_layer.objects: o.select_set(False)
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.convert(target="MESH")                 # applies every modifier ("Visual Geometry to Mesh")
bpy.ops.object.join(); body = bpy.context.object; body.name = "Body"
result = len(body.data.vertices)
```

   Then `sculpt_remesh(object="Body", voxel_size=0.008)`, and after it:

```python
# [union] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
body = D.objects["Body"]; act(body)
for name in ("BLK_hand", "BLK_foot"):
    m = body.modifiers.new(name, "BOOLEAN"); m.operation = "UNION"; m.object = D.objects[name]; m.solver = "EXACT"
    bpy.ops.object.modifier_apply(modifier=m.name)       # slow on a dense sculpt: save first, as the course says
    D.objects[name].hide_set(True)
result = len(body.data.vertices)
```

   Smooth the seams with `sculpt_strokes` (`smooth`, radius about twice the seam width) and re-cut the lines with
   `crease`. Check: `mesh_report("Body")` shows `loose_parts` 1 and `non_manifold_edges` 0.
4. **Plan the loops** [06:43:41]. The course draws them on the sculpt with the Annotate tool (placement `Surface`,
   opacity 0.3). Do the same on paper: for each loop in the tables below, read the landmark points off the sculpt and
   keep them in a dict. Every later step uses them.

### B. Head [06:43:41 to 07:20:20]

What the loops are for [06:18:20 to 06:21:01]: rings round the eye let the lids close; rings round the mouth let the
lips open and purse; a ring round the nose lets it move; the nasolabial loop (nose wing, round the mouth corner, to
the chin) carries the smile line; the face contour (forehead, temple, in front of the ear, jaw, chin) frames the
mask; a ring round the ear base lets the ear move and separates face from skull.

5. **Lay the five loop sets, one face wide, on the +X half** [06:45:51 to 06:54:00]. The course starts every set
   with **8 edges** so that sets meet with equal counts, extrudes each ring outward once (E, S), and mirrors with a
   Mirror modifier (X, `Clipping` on, `On Cage` on) so centre vertices stay on x = 0.

   | Loop set | Runs through | Edges (half) | Course |
   |---|---|---|---|
   | Eye | on the lid edge, all the way round | 8, closed ring | [06:45:51] |
   | Nasolabial | centre of the nose, outside the wing, outside the mouth corner, centre of the chin | 8 | [06:47:48] |
   | Mouth | upper lip centre, mouth corner, lower lip centre | 8 | [06:49:23] |
   | Face contour | forehead centre, temple, front of ear, jaw, under the chin | 4 above + 4 below | [06:51:01] |
   | Ear | round the ear base; two edges lie on the front rim | 8, closed ring | [06:52:34] |

```python
# [face-loops] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
S = Surf(D.objects["Body"]); face = new_lowpoly("body_retopo")
eye, mouth, FRONT = (0.04, -0.3, 1.55), (0, -0.3, 1.47), (0, 1, 0)       # ring centres, in front of the face
add_grid(face, [S.drop(ellipse(eye, rx, rz, 16), FRONT) for rx, rz in ((0.016, 0.008), (0.023, 0.014), (0.030, 0.020))], closed=True)
rings = [S.drop(ellipse(mouth, rx, rz, 16, half=True), FRONT) for rx, rz in ((0.018, 0.005), (0.026, 0.011), (0.034, 0.017))]
for r in rings: r[0].x = r[-1].x = 0.0                                   # centre line, for the Mirror
add_grid(face, rings)
m = face.modifiers.new("Mirror", "MIRROR"); m.use_axis = (True, False, False)
m.use_clip = True; m.use_mirror_merge = True; m.merge_threshold = 0.001; m.show_on_cage = True
result = census(face)
```

   An ellipse only fits a simple eye. For a real lid line pass your own ring: 16 points read off the lid edge, then
   the same points pushed outward for the next rings. The first ring must sit **on** the lid edge and the lip line.
6. **Join the sets** [06:54:05 to 06:58:30]. The course fills between neighbouring sets face by face (select two
   edges, F), merges vertices that meet (M, At Center) and adds a loop cut wherever one side has fewer edges than the
   other. Order: mouth to nasolabial, nasolabial to eye, eye to contour, contour to ear. Scripted: read the two
   borders, slice the stretches that face each other, and add a strip. Equal point counts on both rows, or it fails.

```python
# [stitch] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
S = Surf(D.objects["Body"]); face = D.objects["body_retopo"]
a = border_points(face, (0.04, -0.11, 1.528), start=(0.02, -0.11, 1.53), toward=(0.06, -0.11, 1.53))[:5]  # under the eye
b = S.drop([p + Vector((0, 0, -0.012)) for p in a], (0, 1, 0))       # here: a new row; normally a slice of another border
add_grid(face, [a, b]); relax(face, S, iters=3)
result = census(face)
```

7. **Keep it on the surface, keep it even.** The course adds a Shrinkwrap modifier (`Nearest Surface Point`,
   `On Surface`, target `Body`, offset 0) below the Mirror, and whenever the cage sinks into the sculpt it duplicates
   the modifier and applies the copy, so the edit cage itself moves onto the surface [06:58:44, 06:59:25]. It evens
   the quads in Sculpt Mode with the Relax Slide brush held with Shift [07:00:06]. Scripted: `snap(obj, S)` and
   `relax(obj, S)`. The modifier route, if you prefer it:

```python
# [shrinkwrap] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
face = D.objects["body_retopo"]; act(face)
sw = face.modifiers.new("Shrinkwrap", "SHRINKWRAP"); sw.target = D.objects["Body"]
sw.wrap_method = "NEAREST_SURFACEPOINT"; sw.wrap_mode = "ON_SURFACE"; sw.offset = 0.0
bpy.ops.object.modifier_move_to_index(modifier="Mirror", index=0)     # Mirror above Shrinkwrap [07:20:02]
bpy.ops.object.modifier_copy(modifier="Shrinkwrap"); bpy.ops.object.modifier_apply(modifier="Shrinkwrap")
face.modifiers.remove(face.modifiers["Shrinkwrap.001"])               # the helpers do the snapping from here on
for v in face.data.vertices:
    if abs(v.co.x) < 1e-3: v.co.x = 0.0                               # centre line back onto the mirror plane
result = [m.name for m in face.modifiers]
```

8. **Fill the rest of the head**, in the course's order:
   - Mouth: extrude the inner mouth ring inward and flatten it onto the lip line [07:01:15].
   - Nose: two edges, one from the loop below and one from the lid loop, are extruded over the bridge; the ring of
     vertices round the nose tip must be **even** (8 in the course), is inset twice and closed with Grid Fill, span 2
     [07:02:01 to 07:04:33]. Scripted: `cap(obj, nose_tip_point, span=2)`.
   - Forehead and under the chin: extrude rows with the same edge count as the row they leave [07:05:01].
   - Back of the head: the edges behind the ear are extruded to the centre line at the back and cut 7 times, then the
     crown is filled row by row [07:06:49 to 07:08:19].
   - Ear [07:09:02]: it barely deforms, so the only rule is to follow its shapes. Extrude the base ring over the
     back of the ear, inset twice, Grid Fill (even count); in front, one ring on the rim, one inside, fill the bowl.
   - Neck [07:17:22]: make the lower border even, extrude it straight down (scale Z to 0), cut 5 times.
   Scripted: `Surf.ring` rows for the skull and neck (half rings, axis up the neck), strips for the rest.
9. **Fix the centre line** [07:18:49]. Smoothing under a Mirror drags the centre vertices up or down. The course
   applies the Mirror, turns on X symmetry, relaxes, and adds the Mirror again (Auto Mirror add-on). `relax()` already
   lets centre vertices slide along the centre line only, so this step is built in.
   Head at this point in the course: 1,933 vertices, 1,896 faces [07:19:30].

### C. Body [07:21:25 to 09:21:51]

Loops the body needs [07:24:34 to 07:26:45]: one loop running over the shoulder and round to the back plus one round
the armpit, so the shoulder keeps its volume when the arm lifts; a patch of extra loops on the back of the elbow and
the front of the knee, so the joint keeps its point when bent; plain rings at the wrist; loops along the hip crease.

10. **Torso and shoulder** [07:27:20 to 07:36:00]. The course puts a 10-vertex circle under the armpit and a second
    one where the arm starts, extrudes both, bridges them (Ctrl+E, Bridge Edge Loops: only works with equal counts),
    runs the shoulder loop to the centre line front and back, then subdivides so the arm has 20 round it. The lower
    neck border is cut to the head's count (14 vertices on the half) before the two are joined [07:33:12].
    Scripted: half rings up the torso, a hole with as many border edges as the arm has, the arm as closed rings,
    then a bridge. The hole's border is the loop round the shoulder.

```python
# [torso-arm] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
import bmesh
S = Surf(D.objects["Body"]); low = D.objects["body_retopo"]
n0 = len(low.data.polygons); N, ARM = 24, 20
zs = [0.86 + 0.04 * i for i in range(13)]                                 # hip line to base of neck
add_grid(low, [S.ring((0, 0, z), (0, 0, 1), N, ref=(0, -1, 0), half=True) for z in zs])
bm = bmesh.new(); bm.from_mesh(low.data); bm.faces.ensure_lookup_table()  # new faces: n0 + row * (N/2) + column
hole = [bm.faces[n0 + i * (N // 2) + j] for i in range(7, 11) for j in range(3, 9)]   # 4 x 6 faces: 2 * (4 + 6) = 20 edges
bmesh.ops.delete(bm, geom=hole, context="FACES"); bm.to_mesh(low.data); bm.free()
add_grid(low, [S.ring((x, 0, 1.25), (1, 0, 0), ARM, ref=(0, 0, 1)) for x in [0.16 + 0.04 * i for i in range(12)]], closed=True)
bridge_near(low, (0.14, 0, 1.25)); relax(low, S, iters=8)
result = census(low)
```

    Chest [07:36:01]: one loop circles each breast or pectoral; inside it the course insets rings and Grid Fills (a
    flat chest is Grid Filled straight away). Rib line and other sculpted edges get extra loops with the bevel trick
    of step 12 [07:42:18].
11. **Hips and legs** [07:44:44 to 07:52:26]. The course extrudes a band along the hip crease to the back, then
    extrudes the leg opening down as a tube: rings at knee and ankle rotated to the joint, 4, 4, 4 and 7 cuts
    between, an even number of faces down the leg. Scripted: a strip under the crotch closes the torso's lower
    border into a leg opening, then the leg is bridged on. Count rule (mine): `leg ring = N/2 - 2*w + m`, with the
    strip `w` faces wide and `m` faces long.

```python
# [hips-leg] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
S = Surf(D.objects["Body"]); low = D.objects["body_retopo"]; W, M_, LEG = 1, 10, 20      # 24/2 - 2*1 + 10 = 20
front = border_points(low, (0, 0, 0.86), start=(0, -0.08, 0.86), toward=(0.1, -0.08, 0.86))[:W + 1]   # lower border, front centre
back = border_points(low, (0, 0, 0.86), start=(0, 0.08, 0.86), toward=(0.1, 0.08, 0.86))[:W + 1]      # and back centre
rows = [front]
for i in range(1, M_):
    t = i / M_; row = []
    for a, b in zip(front, back):
        p = S.near(a.lerp(b, t) - Vector((0, 0, 0.10 * math.sin(math.pi * t))))            # dip under the crotch
        if abs(a.x) < 1e-5: p.x = 0.0
        row.append(p)
    rows.append(row)
add_grid(low, rows + [back])
add_grid(low, [S.ring((0.09, 0, z), (0, 0, 1), LEG, ref=(0, -1, 0)) for z in [0.72 - 0.06 * i for i in range(12)]], closed=True)
bridge_near(low, (0.09, 0, 0.72)); relax(low, S, iters=8)
result = census(low)
```

12. **Elbow and knee patches** [07:56:46 to 08:00:30]. The course selects a few edges across the back of the elbow
    (front of the knee, and again just above it), bevels them with 2 segments, slides the stray end vertices onto
    their neighbours with Auto Merge on, and dissolves the leftover triangle edge. That adds two loops only where
    the joint stretches, ending in a 3-pole and 5-pole pair on the side of the limb. `joint_patch` does all of it.
    The same move on edges that run **along** a limb and end on its open border raises the border count by 2: use
    it to step the wrist's 20 up toward the knuckles (the course goes the other way, collapsing 34 down to 22).

```python
# [joint] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
S = Surf(D.objects["Body"]); low = D.objects["body_retopo"]
across = lambda e: abs((e.verts[0].co - e.verts[1].co).normalized().x) < 0.3      # edges that go round the arm
before = census(low)["valence"]
n = joint_patch(low, lambda m, e: abs(m.x - 0.40) < 0.006 and m.y > 0.012 and across(e), 0.012)   # back of the elbow
snap(low, S); relax(low, S, iters=3)
result = {"picked": n, "before": before, **census(low)}
```

13. **Hands** [08:01:53 to 08:29:28]. Each finger starts as a cube laid along it: 2 faces across the top, 3 down each
    side (10 round), the end face kept as the fingertip, a ring at each joint. It is duplicated for the other
    fingers; the thumb loses one joint. Faces are added between neighbouring fingers and cut once [08:08:22]. The
    ring round all four finger roots (34 vertices) is extruded back over the palm and reduced by collapsing pairs of
    edges onto the edge between them until it is 22 [08:11:47], the thumb is tied in, one palm loop is turned back
    on itself (26 to 22) and one more pair removed to reach the arm's 20 [08:17:28 to 08:19:54]. Knuckles get the
    bevel patch on the two top faces [08:20:55]. Fingertips get two more cuts and an inset where the nail sits
    [08:25:25]. The wrist is bridged and cut twice, because the wrist needs rings [08:28:58].

```python
# [finger] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
S = Surf(D.objects["Body"]); f = new_lowpoly("finger_test")
add_grid(f, [S.ring((x, 0, 1.25), (1, 0, 0), 10, ref=(0, 0, 1)) for x in (0.50, 0.53, 0.56, 0.59)], closed=True)
cap(f, (0.59, 0, 1.25), span=2)                        # 10-edge border closed as a 2 x 3 grid, like the cube's end
result = census(f)
```

14. **Feet** [08:29:32 to 08:45:25]: the same method. Toes get few cuts because they barely bend. The sole is closed
    by running the side loops round the heel and back, and the ankle ring is reduced (26, 24, 22) to the leg's 22.
    Ankle bones get the bevel patch.
15. **Join and tidy** [08:00:43, 08:45:32]. Head and body are joined and their neck borders bridged. Then the course
    adds what closing eyes and a moving mouth need: three more rings round the eye, one more round the mouth corner
    with the corner vertices pulled closer together.
16. **Eye sockets and mouth bag** [08:48:45 to 08:59:10]. The lid border is inset for lid thickness, pushed back,
    then widened and pushed further back so an eyeball can turn inside it. The lip border is extruded back along Y
    into a bag, with the first ring overlapped so no gap shows from the front, wide enough for the teeth. Its normals
    face inward on purpose. These vertices go in a vertex group so nothing snaps them to the skin later.

```python
# [socket] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
low = D.objects["body_retopo"]
extrude_border(low, (0.04, -0.11, 1.55), [(0.9, (0, 0.004, 0)), (1.25, (0, 0.012, 0)), (1.0, (0, 0.02, 0))], group="no_shrinkwrap")
result = census(low)
```

17. **Eyeballs, teeth, tongue** [08:59:21 to 09:06:05]. The course does not model them. It appends `Eye - Stylized`
    and `Jaw - Stylized` from the free Blender Studio "Human Base Meshes" bundle (blender.org, Download, Demo Files),
    scales them into place (the eye where the sculpt's eye was), mirrors the eye, deletes the faces of teeth and
    tongue that can never be seen, and checks that the eyeball can rotate without poking through the socket.
    Names from here on (ours): the eye becomes `Eye.L` (on +X), its mirrored copy `Eye.R`, and the jaw piece with
    teeth, gums and tongue `Mouth`; parent all three to `CHARACTER` and hide `BLK_eye`.
18. **Bring the sculpt's shape back** [09:06:10 to 09:20:57]. Vertices on the surface are not enough: once
    subdivided, the mesh shrinks inside the sculpt. The course applies the Mirror, adds a Multires above a Shrinkwrap
    whose vertex group `no shrinkwrap` is inverted, subdivides twice, applies the Shrinkwrap (the detail lands in the
    Multires), tidies with brushes without adding anything new, then uses Multires, Shape, **Apply Base** so the
    low-poly cage itself moves to where its subdivided surface matches. It says "reproject", not bake. The Multires is
    then removed and a Subdivision modifier added (Catmull-Clark, viewport 1, render 2).

```python
# [reproject] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
low, sculpt = D.objects["body_retopo"], D.objects["Body"]; act(low)
before = deviation(low, sculpt, levels=2)["low_to_sculpt"]
bpy.ops.object.modifier_apply(modifier="Mirror")
if "no_shrinkwrap" not in low.vertex_groups: low.vertex_groups.new(name="no_shrinkwrap")
low.modifiers.new("Multires", "MULTIRES")
for _ in range(2): bpy.ops.object.multires_subdivide(modifier="Multires", mode="CATMULL_CLARK")
sw = low.modifiers.new("Shrinkwrap", "SHRINKWRAP"); sw.target = sculpt
sw.wrap_method = "NEAREST_SURFACEPOINT"; sw.wrap_mode = "ON_SURFACE"
sw.vertex_group = "no_shrinkwrap"; sw.invert_vertex_group = True
bpy.ops.object.modifier_apply(modifier="Shrinkwrap")          # reports "Applied modifier was not first": expected
bpy.ops.object.multires_base_apply(modifier="Multires")
low.modifiers.remove(low.modifiers["Multires"])
ss = low.modifiers.new("Subdivision", "SUBSURF"); ss.subdivision_type = "CATMULL_CLARK"; ss.levels = 1; ss.render_levels = 2
result = {"before": before, "after": deviation(low, sculpt, levels=1)["low_to_sculpt"], **census(low)}   # 1 on the stack + 1
```

    Course numbers at this point: body with sockets and mouth bag 10,449 vertices and 10,422 faces [09:08:15].

### D. Clothes and accessories [09:21:51 to 10:44:02]

The one rule [09:22:42]: a garment must have the same, or nearly the same, edge layout as the body under it. Then both
bend at the same places and the body does not poke through. The course's six steps, shown on screen at [09:26:08]:

19. **Base topology from the body** [09:27:20]. Duplicate `body_retopo` as `Shirt_retopo` (collection
    `cloths_retopo`), delete every face the garment does not cover, remove the Subdivision modifier, shrinkwrap it
    onto the cloth sculpt (with the sculpt's own Solidify off, so it lands on the outer face), and remove the
    body-only extras such as rib and elbow patches [09:30:46] and any pole that serves nothing [09:36:48].
    Where the garment leaves the body (sleeve end, skirt), delete and extrude new rings [09:35:29, 09:57:30].
20. **Seams** [09:33:33]: slide existing loops onto every sculpted seam (collar, sleeve hem, panel lines).
21. **Folds** [09:38:22]: mark each fold's ridge and valley, slide a loop onto each, and bevel the ridge loops for
    more edges where a fold needs them [09:41:32]. Loops that crowd at a sleeve end are collapsed in pairs [09:46:02].
22. **Reinforce seams** [09:48:10]: bevel each seam loop into three so it stays crisp when subdivided. Where two
    seams cross, the small bevel face is scaled to zero and merged [09:49:03]. `joint_patch` on a closed loop.
23. **Thickness** [09:51:15]: apply the Mirror, add Solidify (0.007 m on the shirt, judged with a temporary
    Subdivision), with new vertex groups `shell` and `rim` set as its output groups, apply it, put shell and rim
    in one group and give that group, inverted, to the Shrinkwrap, so only the outer face keeps snapping
    [09:52:21]. Round the rim with one loop pushed out (Alt+S) and delete inner faces nobody will see [09:54:24].
24. **Reproject** [09:55:53]: Multires above the Shrinkwrap, subdivide (2 on shirt and boots, 1 on the skirt),
    apply the Shrinkwrap. **No Apply Base on clothes**: the Multires stays, because its detail is baked to a normal
    map in a later stage [09:56:23].

```python
# [cloth] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
import bmesh
body_low, cloth = D.objects["body_retopo"], D.objects["Shirt"]; Sc = Surf(cloth)
shirt = body_low.copy(); shirt.data = body_low.data.copy(); shirt.name = "Shirt_retopo"
col = D.collections.get("cloths_retopo") or D.collections.new("cloths_retopo")
if col.name not in D.collections["Lowpoly"].children: D.collections["Lowpoly"].children.link(col)
col.objects.link(shirt)
for m in list(shirt.modifiers): shirt.modifiers.remove(m)
M = shirt.matrix_world; bm = bmesh.new(); bm.from_mesh(shirt.data)
far = [f for f in bm.faces if (Sc.near(M @ f.calc_center_median()) - M @ f.calc_center_median()).length > 0.012]
bmesh.ops.delete(bm, geom=far, context="FACES"); bm.to_mesh(shirt.data); bm.free()   # keep faces lying under the cloth (mine)
snap(shirt, Sc); relax(shirt, Sc, iters=3); base = census(shirt)
act(shirt); shirt.vertex_groups.new(name="shell"); shirt.vertex_groups.new(name="rim")
so = shirt.modifiers.new("Solidify", "SOLIDIFY"); so.thickness = 0.007; so.offset = -1.0
so.shell_vertex_group = "shell"; so.rim_vertex_group = "rim"
bpy.ops.object.modifier_apply(modifier="Solidify")
gi = {shirt.vertex_groups[n].index for n in ("shell", "rim")}
shirt.vertex_groups.new(name="Group").add([v.index for v in shirt.data.vertices if any(g.group in gi and g.weight > 0.5 for g in v.groups)], 1.0, "REPLACE")
shirt.modifiers.new("Multires", "MULTIRES")
for _ in range(2): bpy.ops.object.multires_subdivide(modifier="Multires", mode="CATMULL_CLARK")
sw = shirt.modifiers.new("Shrinkwrap", "SHRINKWRAP"); sw.target = cloth
sw.vertex_group = "Group"; sw.invert_vertex_group = True
bpy.ops.object.modifier_apply(modifier="Shrinkwrap")
result = {"base": base, "final": census(shirt), "modifiers": [m.name for m in shirt.modifiers]}
```

25. **Skirt** [09:57:18 to 10:17:15]: the body cannot give its shape, so only the hip band is borrowed and the rest
    is extruded ring by ring down the skirt, with loops on the pleat edges. Where a pleat leaves a gap that would
    need a triangle, the course leaves it open until a later cut makes a quad fit [10:03:21]. Inner faces are kept
    higher up than on the shirt because a skirt's inside can be seen [10:14:04]. Name it `Skirt_retopo`; the
    course's skirt route is not scripted here: start it as the `cloth` block does with `D.objects["Skirt"]`, keep only
    the hip band, and extrude the rings with bmesh.
26. **Boots** [10:17:21 to 10:38:30]: from the body's foot and shin. The toes are merged away and the toe cap is
    rebuilt from the centre edge outward [10:20:26]; loops follow the boot's stitched panel; fold ridges are bevelled.
    Name them `Boot.L_retopo` and `Boot.R_retopo` (not scripted here; the `cloth` block's route applies).
27. **Parts that were modelled, not sculpted** (boot flap, sole, ring) [10:38:35]: duplicate the original into
    `Lowpoly`, apply or remove its modifiers, dissolve loops it does not need. No retopology. The closing rule
    [10:42:36]: each cloth object keeps a Multires or a Subdivision modifier and nothing else. The course leaves paired
    items (boots) on one side until after UV unwrapping [10:42:48].

## Which scripted route gives what

| Route | Use for | Loops for animation? |
|---|---|---|
| `Surf.ring` rows + `add_grid`, holes + `bridge_near`, `joint_patch` | torso, neck, arms, legs, fingers, toes, sleeves, boots | Yes. Rings square to the bone are what the course builds. Verified on a dummy; counts are yours to plan. |
| Ring patches (`ellipse` or your own rings) + strips stitched with `border_points` | eyes, mouth, nose, ear, face mask | Yes if the first ring is on the lid edge or lip line and the five loop sets are kept. Slow: one small call at a time with a capture after each. The single calls are verified; a whole face built this way is not. |
| Duplicate the body low-poly, delete, snap to the cloth | fitted clothes | Yes. It is the course's own method. |
| `bpy.ops.object.quadriflow_remesh` | props, rigid accessories, hair blocks, a first look at density | No. All quads, but poles land anywhere and nothing circles the eyes, mouth or joints. Do not rig a face or a limb made this way. |
| Subdivide and shrinkwrap a primitive (cube, UV sphere) | eyeball-like and helmet-like shapes | Only for parts that do not bend. |

```python
# [quadriflow] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
src = D.objects["Body"]; q = src.copy(); q.data = src.data.copy(); q.name = "body_quadriflow"
D.collections["Lowpoly"].objects.link(q); act(q)
q.data.remesh_voxel_size = 0.008; bpy.ops.object.voxel_remesh()   # QuadriFlow refuses a mesh that is not manifold,
                                                                  # which the Boolean union can leave; this closes it
bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=3000, use_mesh_symmetry=True,
                                 use_preserve_sharp=False, use_preserve_boundary=False, smooth_normals=False, seed=0)
result = census(q)       # on the dummy: 0 tris, 0 n-gons, about 36 poles scattered with no relation to the joints
```

Poles. The course gives one rule (3 and 5 only) and no positions. Where they end up in its mesh, read from the
frames: on the cheek where eye rings, nasolabial loop and contour meet; beside the nose bridge; at the ends of every
bevel patch (side of elbow, knee, knuckle, ankle); at the four corners of every Grid Fill (nose tip, breast, back of
ear, fingertip); round the shoulder hole. My rule for placing them: on flat areas that slide rather than fold (cheek,
temple, side of a limb), never on a lid edge, a lip edge, or the inside of a bend.

## Settings the course uses

| Setting | Value | Where | Time |
|---|---|---|---|
| Character height | about 1.6 to 1.7 m | scale about 3D cursor, then apply all transforms | 06:24:15 |
| Voxel size, body fuse | 0.008 m (0.076 was too coarse) | Sculpt Mode remesh | 06:29:40 |
| Hands and feet onto body | Boolean, Union, two modifiers | on `Body` | 06:38:12 |
| Annotate | placement `Surface`, opacity 0.3 | plan the loops | 06:43:54 |
| Snapping | `Face Project`, plus rotate and scale | Edit Mode header; off before a free extrude | 06:45:45 |
| Edges per starting loop | 8 | every face loop set | 06:46:04 |
| Mirror | axis X, `Clipping` on, Merge 0.001 m, `On Cage` on, above Shrinkwrap | low-poly | 06:48:13 |
| Shrinkwrap | `Nearest Surface Point`, `On Surface`, offset 0 m | low-poly, target the sculpt | 06:58:50 |
| Relax Slide brush with Shift | strength 1.0 | Sculpt Mode on the low-poly, object `Wireframe` display on | 07:00:11 |
| Grid Fill span | 2 | nose tip, ear | 07:04:20 |
| Back of head cuts | 7 | after extruding to the back centre | 07:07:12 |
| Neck cuts | 5 | after extruding the neck border down | 07:18:25 |
| Shoulder and arm circles | 10 vertices each, later 20 round the arm | Add Mesh, Circle | 07:27:37, 07:32:20 |
| Neck border, half | 14 vertices, 13 edges, same on head and body | before joining | 07:34:05 |
| Leg cuts | 4, 4, 4, 7 | between hip, knee and ankle rings | 07:49:38 |
| Arm cuts | 9, 8 | either side of the elbow ring | 07:53:35 |
| Bevel for patches and seams | 2 segments, Auto Merge on for the clean-up | Ctrl+B | 07:42:43 |
| Finger section | 2 faces on top, 3 on each side | from a cube | 08:08:13 |
| Counts at the hand | 34 at the finger roots, 22, then 20 at the wrist | collapse pairs | 08:11:47 |
| Counts at the foot | 42 at the toes; 26, 24, 22 at the ankle | collapse and fill | 08:34:57, 08:41:16 |
| Multires, body | 2 levels, then Apply Base, then removed | above Shrinkwrap | 09:08:38 |
| Subdivision, final body | Catmull-Clark, viewport 1, render 2 | modifier | 09:20:45 |
| Solidify, shirt | thickness 0.007 m, output groups `shell` and `rim` | before reprojection | 09:51:45 |
| Multires, clothes | 2 (shirt, boots), 1 (skirt), kept | above Shrinkwrap | 09:56:10, 10:16:40 |

Face counts seen on screen, as a guide to density: head 1,896 faces [07:19:30]; half body without head, hands and
feet 1,815 [08:00:35]; one hand and forearm about 1,160 [08:28:30]; whole body 10,422 [09:08:15]; shirt before
Multires 2,542 [09:53:40]. The course never states a target; my reading is 8,000 to 12,000 faces for a body, with
the smallest quads at the eyes, lips and fingers and the largest on the skull, back and thighs.

## Mistakes the course warns about

- Sculpting at an arbitrary scale and never fixing it. Scale and apply before the first low-poly vertex [06:22:52].
- Remeshing hands and feet together with the body: either the body becomes far too dense or the fingers melt [06:37:47].
- Soft lid, lip and nose lines on the fused sculpt. Vertices have nothing to follow. Re-cut them first [06:31:37].
- Triangles and n-gons. A loop cut stops at both [06:12:26]. Add a cut to fix the count instead of closing with a
  triangle [07:30:11]; leave a hole open rather than fill it wrong [10:03:27].
- Poles with 6 or more edges [06:16:16].
- Bridging or Grid Filling with unequal or odd counts. Count first (the course turns on `Statistics`) [07:04:06].
- Extruding with snapping on: the new ring collapses onto the surface it left. Snapping off, extrude, on again [07:40:47].
- Smoothing a mesh that is still being pulled by an unapplied Shrinkwrap gives lumps: apply a copy first [07:54:00].
- Smoothing under a Mirror without fixing the centre line [07:18:49].
- Faces showing dark in the Retopology overlay have flipped normals: recalculate (Shift+N) [06:47:22].
- A mouth you can see through from the front: overlap the first ring of the mouth bag [08:53:28].
- Applying the Multires on the body. It would bake in all subdivisions; use Apply Base and remove it [09:19:25].
- Solidify applied while the whole mesh still shrinkwraps: the inner shell collapses onto the outer one [09:52:03].
- Auto Merge left on while duplicating or mirroring pieces welds them together [10:42:05].
- Clothes with an edge layout unrelated to the body: they break and clip when posed [09:23:29].

## What changes for a different character

- General: the reasons for the loops, quads only, 3- and 5-poles only, equal counts before joining, snapping then
  relaxing, the reprojection through Multires, clothes copied from the body.
- Specific to this character: the counts (8 per face loop, 10 and 20 at the arm, 22 at the leg), five fingers and
  five toes, an inset-and-fill breast, a simple ear, no fingernails (with nails, add a ring round each nail
  [08:25:59]), a T-shirt, pleated skirt and boots.
- Bigger or more realistic heads need more rings round eye and mouth; keep ring counts even so Grid Fill works.
- Creatures: put a ring set round every opening that moves (extra eyes, nostrils, gills) and rings square to the bone
  along every limb, tail or tentacle (`Surf.ring` with the axis along it). Joints that bend one way get a bevel patch
  on the outside of the bend; joints that bend both ways get plain rings, three close together.
- Hard-surface parts (armour, weapons, buckles) do not deform: keep the modelled mesh if there is one, otherwise
  QuadriFlow is acceptable, with support loops (`joint_patch` on closed loops) beside every hard edge.
- A mouth that never opens or eyes that are painted on still need their rings if the face is to be subdivided
  cleanly, but the socket, mouth bag, eyeballs and teeth can be left out.

## Exit check

Run for every low-poly object and report the numbers. Any failed line means the stage is not finished.

```python
# [check] verified in 4.5.16 background
exec(D.texts["retopo_lib"].as_string())
low, sculpt = D.objects["body_retopo"], D.objects["Body"]
result = {"census": census(low), "deviation": deviation(low, sculpt, levels=1)}    # 1 more level on top of viewport 1
```

- `census`: `tris` 0, `ngons` 0, `bad_poles` 0, `non_manifold` 0. `open_borders` must be empty on the body (eye
  sockets and mouth bag are closed sacks) and hold only real openings on clothes (neck, cuffs, hem). Failed otherwise.
- `mesh_report("body_retopo")`: `loose_parts` 1, `symmetry_error` below 0.001.
- `deviation`: my limits, not the course's: `sculpt_to_low` `p99` under 0.3 % of the character's height and `max`
  under 1 % (a larger `max` means a part is not covered: a finger, an ear); `low_to_sculpt` `p99` under 0.3 %. Sockets
  and the mouth bag are meant to be off the surface and raise `low_to_sculpt` `max`; say so rather than hide it.
- Hide the sculpts (every object in `Highpoly`, `hide_set(True)`: hidden children are left out of the capture),
  then `outline_match(object="CHARACTER", references={...}, threshold=0.98)` with the same pictures as the sculpt
  stages: it now measures the low-poly character as it is dressed. A view below 0.98 is failed.
  A view with no reference picture is `not_run`: report it as "looked at, not measured", never as passed.
- `turnaround_sheet("body_retopo")` for the surface, and `viewport_capture(view="FRONT", shading="WIREFRAME",
  frame_object="body_retopo")` plus close views of face, shoulder, elbow, hand and knee for the loops. Look for: a
  closed ring on the lid edge and the lip line, the shoulder loop, the elbow and knee patches, no long thin quads.
- Counts: report faces per object against the density guide above. More than twice the guide is failed.
- Eyeball test: rotate each eye 30 degrees up, down, left, right; it must not come through the lids [09:03:51].

## Gaps

- **Hand placement.** The course's method is thousands of small hand moves judged by eye. The helpers reproduce each
  kind of move, verified on a dummy made of ellipsoids and cylinders, not on a sculpted character. A full face, hand
  or foot built with them was not run; expect many small calls and several restarts of a patch.
- **Count reductions** (34 to 22 at the hand, 42 down at the foot, loops turned back on themselves on palm and sole)
  have no one-call helper. Plan counts so few are needed, and use lengthwise `joint_patch` runs to change a count.
- **Brushes on Multires.** After reprojection the course sharpens lids, lips, ears, knuckles and closes the lip gap
  with Crease Polish, Inflate and Grab on the Multires levels [09:09:00 to 09:19:20]. `sculpt_strokes` moves base
  vertices only and refuses nothing here, but it cannot reach Multires levels. Route: do that clean-up on the sculpt
  before step 18, so the reprojection carries it.
- **Relax Slide** has no equal among the `sculpt_strokes` brushes; `relax()` replaces it (smooth, then re-snap).
- **Annotate** lines cannot be drawn; landmark coordinates replace them.
- **Add-ons the course uses**, all free, none needed by the scripted route: F2 (F makes a face from one vertex or
  edge) [06:57:01], LoopTools (Relax on a selected loop) [08:10:07], Auto Mirror [07:19:45], Screencast Keys (shows
  key presses only). In Blender 4.2 and later they are extensions that must be downloaded.
- **Human Base Meshes bundle** (free, Blender Studio): not on this machine, so step 17 was not run. Without it,
  model the eye as a UV sphere and leave teeth for later. The bundle also holds whole body and head base meshes;
  wrapping one onto the sculpt could replace hand-built face loops, but I did not test that.
- **Live session.** Every block was run in background Blender with the active object set by `act()`. Through
  `exec_python` the `bpy.ops.object.*` calls should behave the same; if one reports a context error, that operator
  needs a window override and the block should be run with `headless_run` on a saved copy instead.
- **Not stated in the course:** ring counts round the torso, how many faces a finished garment should have, where
  poles should go, and how close the low-poly must lie to the sculpt. Values given for those are marked as mine.
