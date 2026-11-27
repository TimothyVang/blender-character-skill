# 02 Blockout

Course source: chapter 03 "Blocking out your character", 00:21:34 to 01:36:09.

## Goal

The whole body exists as 13 separate, very low-resolution parts (head, neck, ears, three torso parts, and per side
upper leg, lower leg, foot, shoulder, upper arm, lower arm, hand), standing in a neutral pose, with the proportions
and outline of the concept and no detail. Neighbouring parts overlap and flow into each other. No clothes, hair,
face features or fingers yet.

## Starting state

- Stage 01 is finished: the ratio list exists, and `REF_<VIEW>` empties are in the scene at one shared `height`
  for every view that has a measurable picture.
- No character geometry yet. `H` below is the character's height in world units (the `height` given to
  `reference_setup`). Sizes are fractions of `H` or are read from the references.

## The five rules the course gives for a blockout [00:22:21 to 00:31:23]

1. Simple shapes only: detail added now hides wrong proportions and has to be redone [00:22:21, 00:28:34].
2. One object per body part, so each form can be resized or turned on its own [00:27:53].
3. Repeat the concept's shape language (round, boxy, angular, long) in every part [00:26:53].
4. Straight against curve: a limb gets one fairly straight side and one curved side, not two matching bulges. From
   the side the body follows a gentle S: rib cage tipped back, pelvis tipped forward [00:29:20 to 00:30:06].
5. Keep checking the silhouette: a good blockout reads clearly as a flat black shape [00:30:19].

## Order of work

Helpers are defined in "Helper code"; paste the ones a step needs at the top of each `exec_python` call. After
every new part, go back and adjust the parts it touches, as the course does throughout [00:49:02, 00:58:49].

### 0. Setup [00:31:35 to 00:37:38]

Course: deletes everything, installs the free "Extra Mesh Objects" extension (Edit > Preferences > Get Extensions)
and adds its `Round Cube` with default settings [00:32:10 to 00:32:38]. A round cube is a sphere built from a cube:
all quads, no poles, 8 quads along each cube edge (counted in the wireframe at [00:42:30]). Then the Sculpting
workspace, viewport focal length `150` so the view is nearly flat [00:34:14], a second small viewport with gizmos
and overlays off to watch the whole figure [00:34:26], the Grab brush, and X symmetry on [00:37:31].

blender-live: the extension is not in the reader's Blender (`bpy.ops.mesh.primitive_round_cube_add` does not exist
there); `round_cube()` builds the same mesh (386 vertices) and parents it to `CHARACTER`, an empty at the origin that
`character()` makes on first use. Every later part, garment and lowpoly hangs under `CHARACTER` (see the names table
in SKILL.md), so `turnaround_sheet(object="CHARACTER")` and `outline_match(object="CHARACTER")` always show the
whole figure. For perspective captures set
`area.spaces.active.lens = 150` on each `VIEW_3D` area of `bpy.data.screens` (verified in 4.5.16 background);
`turnaround_sheet` and `outline_match` are orthographic and do not need it.

### 1. Head [00:37:40 to 00:40:48]

Why first: the rest of the body is sized against the head. Course, in order: (a) Grab the bottom of the round cube down into an egg, narrow end at the chin. (b) Side view:
pull the lower front forward for the jaw. (c) Front view: `Line Project` slices the left and right sides flat so
the head is not round from the front. (d) Side view: `Crease Polish` marks a line between jaw and skull, and Grab
lifts the skull above it. (e) Smooth the back of the head, then pull it back so it is not a perfect ball.
(f) `Scrape/Fill` (strength 0.7) flattens the side plane of the head.

blender-live: `head = round_cube("BLK_head")`, then
`place(head, location=(0, 0, chin_z + head_h / 2), scale=(head_w / 2, head_d / 2, head_h / 2))`, then
`sculpt_begin(object="BLK_head", symmetry="X")`. Example for (a), (b), (e) and (c) with `H = 1.7`:

```
# stroke maths verified through sculpt_cmds.py in 4.5.16 background; the tool call itself was not run live
sculpt_strokes(object="BLK_head", strokes=[
  {"brush": "grab", "points": [[0, 0, 1.43], [0, 0, 1.39]], "radius": 0.12},          # chin down: egg
  {"brush": "grab", "points": [[0, -0.08, 1.45], [0, -0.11, 1.45]], "radius": 0.08},  # jaw forward (-Y is front)
  {"brush": "grab", "points": [[0, 0.10, 1.58], [0, 0.13, 1.59]], "radius": 0.10}     # back of skull back
], capture=True, view="RIGHT")
exec_python: slice_flat(bpy.data.objects["BLK_head"], point=(0.095, 0, 1.52), normal=(1, 0, 0.1), mirror_x=True)
```

For (d) use a `crease` stroke with `"snap": true`, radius about 0.03, strength about 0.25, along the jaw line. For
(f) use `slice_flat` with the plane just inside the surface, or a `smooth` stroke.

Look (FRONT, RIGHT): an egg with flat-ish sides; from the side the jaw sits forward of and below a rounder skull.

### 2. Neck [00:40:52 to 00:45:15]

Course: new round cube, scaled small and moved under the head. With X-ray on, the lower half is selected and
extruded down into a capsule. The capsule is tilted so its lower end sits further back than its upper end (about 15
degrees from upright in the side view at [00:43:44]); a neck leans forward as it rises. The extruded wall has no
edges across it and cannot be shaped, so 6 loop cuts are added [00:43:28]. Grab then pulls the lower front out
toward the chest, the lower back toward the upper back, the lower sides toward the shoulders, and widens the top
into the underside of the head. `Line Project` trims the bottom flat.

```python
neck = round_cube("BLK_neck")                 # verified in 4.5.16 background
stretch_half(neck, length=2.0, cuts=6)        # capsule along Z at radius 1: runs from Z=1 down to Z=-3
place(neck, location=(0, neck_y, neck_top_z), scale=(neck_r,) * 3, rotation_deg=(15, 0, 0), pivot=(0, 0, 0))
```

Pivot `(0, 0, 0)` is the centre of the capsule's upper ball, so `location` is where the neck enters the skull, and
the positive X rotation swings the lower end toward +Y (the back). Then `sculpt_begin(object="BLK_neck",
symmetry="X")` and grab strokes starting at `outline_point(neck, z, "-Y")`, `"+Y"` and `"+X"` near the bottom,
moving 0.01 to 0.03 outward and down.

Look (side view): the neck enters the skull behind the jaw with no visible step.

### 3. Ears [00:45:45 to 00:49:15]

Course: the jaw line on the head is creased up to where the ear will sit. A round cube is scaled into a small flat
disc and placed on the side of the head at +X, on that line. `Line Project` trims its back and one more edge.
Sculpt > Symmetrize with direction `+X to -X` copies it to the other side, X symmetry goes on, and Grab shapes
both. Last, the ear is turned in Edit Mode so it angles outward instead of facing straight ahead [00:48:37].

blender-live: build the +X ear only and add a Mirror modifier (ours; same result as symmetrising):

```python
ear = round_cube("BLK_ears")                  # verified in 4.5.16 background
place(ear, location=(ear_x, ear_y, ear_z), scale=(0.006 * H, 0.016 * H, 0.022 * H), rotation_deg=(0, 0, -20))
mirror_x(ear)
```

The sizes and the 20 degrees (back edge swung outward) are ours, a starting guess; read the real ear from the
concept. Every part with a Mirror modifier is sculpted with `sculpt_begin(object=..., symmetry="")`.

### 4. Torso, three parts [00:49:50 to 00:58:37]

Why three: rib cage, waist and pelvis tilt differently, and the S curve comes from those tilts [00:52:40].
- Upper torso (rib cage and shoulder line) [00:50:08]: round cube under the neck, made thinner front to back (scale
  Y), tipped so its top leans back, scaled up. Grab: top back pulled up into the neck, upper sides pulled out into
  the shoulder line, bottom pulled down for the ribs with the centre front lifted, back pushed in so it is not a ball.
- Middle torso (waist) [00:52:05]: round cube scaled on Y and Z, sides pulled in, top and bottom worked until it
  flows into its neighbours. `Line Project` trims the bottom.
- Pelvis [00:54:45]: round cube scaled on Y and tipped the opposite way to the rib cage. Grab pulls the bottom down
  and the sides out for the hips. Two diagonal `Line Project` cuts remove the lower outer corners: these flat faces
  are where the legs attach [00:56:23]. `Crease Polish` marks the centre line of the back; Grab pulls the seat out.
- All three are compared with the reference and widened together (scale X, then Y) [00:58:03].

blender-live: `round_cube` + `place` for `BLK_torso_upper`, `BLK_torso_mid`, `BLK_pelvis`. `rotation_deg=(-10, 0,
0)` leans the top of the rib cage back and `(10, 0, 0)` leans the top of the pelvis forward (the 10 is ours; read
the real angle from the side reference). Leg cuts and group resize:

```python
# verified in 4.5.16 background
slice_flat(bpy.data.objects["BLK_pelvis"], point=(hip_x, 0, crotch_z + 0.03 * H), normal=(1, 0, -1), mirror_x=True)
scale_parts(["BLK_torso_upper", "BLK_torso_mid", "BLK_pelvis"], scale=(1.1, 1.05, 1))
```

Look: the S from the side; shoulders, waist and hips at the ratio-list widths from the front; no part sits on the
next like stacked beads [00:53:26], each sinks into its neighbour.

### 5. Legs and feet [00:59:10 to 01:14:58]

- Upper leg [00:59:10]: round cube made tall (scale Z), placed under a pelvis cut at +X, Mirror modifier [00:59:43].
  Grab: top outside pulled up and out into the hip, bottom pulled down, lower end narrowed toward the knee; one
  `Line Project` trim. Side view: tipped back to keep the S, the front curved and the back kept straighter
  [01:01:17], and the seat of the pelvis made to overlap the top of the leg at the back.
- Lower leg [01:02:51]: round cube, tall, set slightly further back than the thigh, Mirror modifier. Bottom narrowed
  toward the ankle and trimmed flat. Front view, the "angry eyebrows" rule [01:04:33]: the calf's widest point is
  higher on the outside than on the inside, and the ankle bump is higher on the inside than on the outside. Side
  view: thinned, calf curved at the back, shin straighter. The thigh's lower end is then shaped to sit over the top
  of the lower leg as the knee [01:07:09].
- Foot [01:08:25]: round cube, small, flattened (Z), lengthened (Y), Mirror modifier. From below it is pushed into a
  rounded rectangle; `Line Project` flattens the sole. The lower part is masked with `Lasso Mask` from the side so
  the sole stays put while Grab lifts the top back of the foot into the ankle, then the mask is cleared [01:10:36 to
  01:11:21]. Target: from the side a wedge, tall at the ankle and low at the toe; from the front a right-angled
  triangle, one side upright and the other sloping out to a wider sole [01:11:34] (the narration does not say which
  side is which). Heel rounded, everything smoothed.
- Then leg length is compared with the reference and thigh, shin and foot are resized together [01:14:19].

blender-live: `place`, `mirror_x`, `symmetry=""`. Foot lift with the sole held (`H = 1.7`), then the group resize:

```
# mask and stroke maths verified through sculpt_cmds.py in 4.5.16 background; tool calls not run live
sculpt_mask(object="BLK_foot", op="box", min=[-1, -1, -1], max=[1, 1, 0.03])
sculpt_strokes(object="BLK_foot", strokes=[{"brush": "grab", "points": [[0.09, 0.03, 0.08], [0.09, 0.03, 0.14]], "radius": 0.09}])
sculpt_mask(object="BLK_foot", op="clear")
exec_python: scale_parts(["BLK_upper_leg", "BLK_lower_leg", "BLK_foot"], scale=(1, 1, 0.95), pivot=(0, 0, crotch_z))
```

### 6. Arms [01:15:12 to 01:24:35]

Pose: arms held out and down, about 45 degrees from the body (read from the frame at [01:20:20]), clear of the
torso so the rig can deform them, with a slight forward bend at the elbow so the rig knows which way it folds
[01:17:13, 01:19:25]. This is the pose even when the concept shows another.
- First a `Line Project` cut on each side of the upper torso makes a flat face where the arm attaches [01:15:12].
- Upper arm: round cube, lower half extruded into a capsule like the neck, rotated into the pose, scaled down,
  lined up with the shoulder in the side view, Mirror modifier. Later 8 loop cuts [01:21:44], then Grab raises a low
  bulge on the front of the arm that ends in a V pointing at the elbow [01:23:08].
- Lower arm: a duplicate of the upper arm moved down the arm. Its far half is scaled down so it tapers to the wrist;
  it is turned a little about Z for the elbow bend [01:19:25]; ring by ring it is made widest just below the elbow
  and narrow at the wrist; 3 loop cuts go into each of the three stretches between those rings [01:20:46]; one
  `Line Project` cut flattens a side [01:23:40].
- Both are scaled down together and the lower arm lengthened after a look at the reference [01:23:54].

```python
arm = round_cube("BLK_upper_arm")             # verified in 4.5.16 background
stretch_half(arm, length=4.0, cuts=8)         # along Z at radius 1: from Z=1 down to Z=-5
place(arm, location=(shoulder_x, 0, shoulder_z), scale=(r,) * 3, rotation_deg=(0, -45, 0), pivot=(0, 0, 0))
mirror_x(arm)                                 # -45 about Y swings the lower end out toward +X
```

`stretch_half` works along a world axis, so it comes before the rotation. Build `BLK_lower_arm` the same way with
its pivot placed at the elbow and a smaller `r`; add a few degrees of Z rotation for the bend. The captions call
the pose "E pose"; the frames show what is normally called an A-pose, and no exact angle is stated.

### 7. Shoulders and hands [01:24:40 to 01:30:54]

- Shoulder [01:24:40]: a small round cube at each shoulder joint (Mirror modifier) hides the gap between torso and
  arm. Grab pulls it out and down over the top of the upper arm, in toward the chest at the front, and into the back
  behind. `Scrape/Fill` flattens its front. Kept small because this character is slight [01:26:04]. Then `Crease
  Polish` runs the centre line of the back down the torso parts [01:27:39].
- Hand [01:28:10]: a round cube at the wrist, sliced flat on the back and the palm with `Line Project`, turned to
  continue the line of the forearm, shaped into a rounded rectangle (a mitten, no fingers). `Inflate` (strength 0.5)
  fattens the two long edges of the palm; Grab pulls a small bump where the thumb will grow. Mirror modifier. Hands
  and feet get their own chapters later; stop here.

blender-live: `round_cube("BLK_shoulder")` and `round_cube("BLK_hand")`, `place`, `mirror_x`; two `slice_flat`
calls for the hand; `inflate` with `"snap": true`.

### 8. Proportion pass [01:30:56 to 01:34:20]

Why: only with every part present can the whole be judged. The course selects groups of parts, enters Edit Mode on
all of them at once and scales or moves them together: legs longer and wider, shoulders up and out then back in,
head larger, forearm shorter. It is judged by eye against the board, with a break before a second look [01:34:01].
blender-live can measure instead:
1. `proxy = build_proxy(voxel_size=0.01 * H)` makes `BLOCKOUT_PROXY`, a fused throwaway copy for the numbers that
   need one mesh (`mesh_report`, `width_profile`). Rebuild it each time. It is not under `CHARACTER`.
2. `turnaround_sheet(object="CHARACTER", references={"FRONT": ..., "RIGHT": ...})` to look.
3. `outline_match(object="CHARACTER", references={...})` to measure. In the overlay, red is reference with no
   model (grow the model there) and blue is model with no reference (shrink it). Outstretched arms set the width of
   the bounding box, so match the arm angle to the reference before trusting a score.
4. `width_profile(proxy, rows=20)` against `picture_profile(front_path, rows=20)`: outline width at 20 heights for
   model and picture, as fractions of height. A row that differs by more than 0.02 (ours) names the height that
   needs work. `axis=1` with the side picture does the same for depth.
5. Fix with `scale_parts` (groups), `place` (one part) or grab strokes (local), then go back to 1.

### 9. Save, and when to join [01:34:28; 00:25:59]

`save_file(filepath=r"...\<character>_01_blockout.blend")`. Keep it: it is the only version with separate parts.
The course does not join or remesh in this chapter. Its theory part shows on a finished example, then undoes, what
comes next: select all parts, join (Ctrl+J), voxel remesh, and the result takes sculpting strokes cleanly because
the big forms are already right [00:25:59 to 00:26:28]. In practice the course keeps the parts separate through
the face, body and clothes chapters, joining only small pieces locally (nose into head, fingers into hand), and fuses
the body at the start of retopology (stage 06). Do the same: sculpt the `BLK_` parts in place, and leave
`join_parts` for stage 06.

## Helper code

```python
# verified in 4.5.16 background (every function in this block)
import bpy, bmesh, math
import numpy as np
from mathutils import Matrix, Vector
def character():
    """The `CHARACTER` empty at the origin that every part is parented to (made on first use)."""
    root = bpy.data.objects.get("CHARACTER")
    if root is None:
        root = bpy.data.objects.new("CHARACTER", None); root.empty_display_type = "PLAIN_AXES"
        bpy.context.scene.collection.objects.link(root)
    return root
def round_cube(name, radius=1.0, div=8):
    """Sphere made from a cube: div x div quads per side (386 verts at div=8). The object stays at the origin,
    parented to CHARACTER."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=div - 1, use_grid_fill=True)
    for v in bm.verts: v.co = v.co.normalized() * radius
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    ob.parent = character()
    return ob
def place(ob, location=None, scale=(1, 1, 1), rotation_deg=(0, 0, 0), pivot=None):
    """Scale, rotate the VERTICES about `pivot` (default: their centre), then move the pivot to `location`."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(-1, 3)
    c = Vector(pivot) if pivot is not None else Vector(co.mean(0).tolist())
    rx, ry, rz = (math.radians(a) for a in rotation_deg)
    rot = Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(ry, 4, "Y") @ Matrix.Rotation(rx, 4, "X")
    to = c if location is None else Vector(location)
    me.transform(Matrix.Translation(to) @ rot @ Matrix.Diagonal((*scale, 1.0)) @ Matrix.Translation(-c)); me.update()
def stretch_half(ob, length, cuts=6, axis=2, side=-1):
    """Extrude one half of a round cube along `axis` by `length` (a capsule), with `cuts` rings on the new wall."""
    me = ob.data; bm = bmesh.new(); bm.from_mesh(me)
    c = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
    faces = [f for f in bm.faces if (f.calc_center_median()[axis] - c[axis]) * side > 1e-6]
    new = [g for g in bmesh.ops.extrude_face_region(bm, geom=faces)["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.delete(bm, geom=faces, context="FACES")     # the extrude leaves the old faces behind as an inner wall
    d = Vector((0, 0, 0)); d[axis] = side * length
    bmesh.ops.translate(bm, verts=new, vec=d)
    newset = set(new)
    walls = [e for e in bm.edges if (e.verts[0] in newset) != (e.verts[1] in newset)]
    if cuts: bmesh.ops.subdivide_edges(bm, edges=walls, cuts=cuts, use_grid_fill=True)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free(); me.update()
def mirror_x(ob):
    m = ob.modifiers.new("Mirror", "MIRROR")
    m.use_axis = (True, False, False); m.use_clip = False; m.use_mirror_merge = True; m.merge_threshold = 0.001
def world_co(ob):
    co = np.empty(len(ob.data.vertices) * 3, np.float32); ob.data.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world); return co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]
def slice_flat(ob, point, normal, mirror_x=False):
    """Line Project: push everything on the side `normal` points to flat onto the plane through `point` (world)."""
    me = ob.data; inv = np.linalg.inv(np.array(ob.matrix_world))
    w = world_co(ob).astype(np.float64); moved = 0
    for sx in ((1, -1) if mirror_x else (1,)):
        p = np.array(point, float) * (sx, 1, 1); n = np.array(normal, float) * (sx, 1, 1); n /= np.linalg.norm(n)
        d = (w - p) @ n; sel = d > 0
        w[sel] -= d[sel, None] * n; moved += int(sel.sum())
    me.vertices.foreach_set("co", (w @ inv[:3, :3].T + inv[:3, 3]).astype(np.float32).ravel()); me.update()
    return moved
def outline_point(ob, z, side="+X", band=0.02):
    """Outermost point of the part at height z on +X, -X, +Y or -Y: where a grab stroke should start."""
    w = world_co(ob); axis = "XY".index(side[1]); sign = 1 if side[0] == "+" else -1
    near = w[np.abs(w[:, 2] - z) <= band]
    if not len(near): near = w[np.argsort(np.abs(w[:, 2] - z))[:8]]
    return [round(float(v), 5) for v in near[np.argmax(near[:, axis] * sign)]]
def scale_parts(names, scale=(1, 1, 1), move=(0, 0, 0), pivot=None):
    """Scale and move several parts together about one pivot (default: middle of their shared box, on X=0)."""
    obs = [bpy.data.objects[n] for n in names]
    a = np.concatenate([np.array([v.co[:] for v in o.data.vertices]) for o in obs])
    c = Vector(pivot) if pivot is not None else Vector((0.0, float(a[:, 1].min() + a[:, 1].max()) / 2,
                                                         float(a[:, 2].min() + a[:, 2].max()) / 2))
    m = Matrix.Translation(c + Vector(move)) @ Matrix.Diagonal((*scale, 1.0)) @ Matrix.Translation(-c)
    for o in obs: o.data.transform(m); o.data.update()
def build_proxy(prefix="BLK_", name="BLOCKOUT_PROXY", voxel_size=0.0):
    """One joined copy of every part, modifiers applied; parts untouched. voxel_size > 0 fuses it into one skin."""
    old = bpy.data.objects.get(name)
    if old: bpy.data.objects.remove(old, do_unlink=True)
    dg = bpy.context.evaluated_depsgraph_get(); bm = bmesh.new()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.name.startswith(prefix): continue
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        me.transform(ob.matrix_world); bm.from_mesh(me); bpy.data.meshes.remove(me)
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free()
    proxy = bpy.data.objects.new(name, out); bpy.context.scene.collection.objects.link(proxy)
    if voxel_size > 0:
        out.remesh_voxel_size = voxel_size
        with bpy.context.temp_override(active_object=proxy, object=proxy, selected_objects=[proxy]):
            bpy.ops.object.voxel_remesh()
    return proxy
def width_profile(ob, rows=20, axis=0):
    """Outline width at `rows` heights, bottom to top, as fractions of height. axis=0: X (FRONT); 1: Y (side)."""
    w = world_co(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    z0, z1 = w[:, 2].min(), w[:, 2].max(); h = z1 - z0
    band = np.clip(((w[:, 2] - z0) / h * rows).astype(int), 0, rows - 1); out = []
    for r in range(rows):
        s = w[band == r, axis]; out.append(round(float((s.max() - s.min()) / h), 4) if len(s) else 0.0)
    return out
def picture_profile(path, rows=20):
    """The same numbers from a straight-on picture with a transparent or plain background."""
    img = bpy.data.images.load(path, check_existing=True); w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)   # row 0 = bottom
    if px[:, :, 3].min() < 0.5: mask = px[:, :, 3] >= 0.5
    else:
        bg = np.median(np.concatenate([px[:4, :4, :3].reshape(-1, 3), px[-4:, -4:, :3].reshape(-1, 3)]), axis=0)
        mask = np.linalg.norm(px[:, :, :3] - bg, axis=2) > 0.16
    ys, xs = np.nonzero(mask); y0 = ys.min(); height = ys.max() - y0 + 1; out = []
    for r in range(rows):
        a = y0 + height * r // rows; b = max(a + 1, y0 + height * (r + 1) // rows)
        cols = np.nonzero(mask[a:b].any(axis=0))[0]
        out.append(round(float((cols.max() - cols.min() + 1) / height), 4) if len(cols) else 0.0)
    return out
def join_parts(prefix="BLK_", name="Body", skip=()):
    """Apply every part's modifiers and join the parts into one object (stage 06). Save the parts file first."""
    parts = [o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(prefix) and o.name not in skip]
    for o in parts:
        with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
            for m in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
    with bpy.context.temp_override(active_object=parts[0], object=parts[0], selected_objects=parts,
                                   selected_editable_objects=parts):
        bpy.ops.object.join()
    parts[0].name = name; parts[0].data.name = name
    return parts[0]
```

## How strokes behave here (checked against `sculpt_cmds.py`)

- `grab` moves every vertex within `radius` of the FIRST point by (last point minus first point), fading to nothing
  at the radius. Start on the surface (`outline_point`) and use a radius of a third to a half of the part's size
  for form changes; the course's Grab brush is likewise very large.
- `"snap": true` on a `grab` or `snake_hook` moves the whole path so its first point lies on the surface, keeping
  its length and direction; on the other brushes it puts every point on the surface.
- `moved_verts: 0` means the stroke missed; check it after every call. `symmetry="X"` is for centre-line parts only.
- A stroke radius smaller than the gap between vertices (about 0.03 `H` on a torso part) moves one vertex or none.
  Do not `sculpt_remesh` single parts to get finer strokes; coarse is the point of this stage.

## Settings the course uses

| Setting | Value | Where | Timestamp |
| --- | --- | --- | --- |
| Primitive | `Round Cube`, default settings, one per part | Add > Mesh (Extra Mesh Objects) | 00:32:34 |
| Viewport focal length | 150 | Sidebar (N) > View | 00:34:14 |
| Symmetry | X on for centre parts; off on mirrored parts | Sculpt header | 00:37:38; frame 01:06:41 |
| Brush strength | Grab 0.400; Scrape/Fill 0.700; Inflate 0.500 | Brush header (read from frames) | 00:49:28; 00:40:36; 01:30:05 |
| Loop cuts | neck 6; upper arm 8; lower arm 3 in each of three stretches | Edit Mode, Ctrl+R | 00:43:28; 01:21:44; 01:20:46 |
| Symmetrize | direction `+X to -X`, merge distance 0.0005 | Sculpt symmetry popover | 00:48:12 |
| Mirror modifier | axis X, merge on at 0.001 m, clipping off (defaults) | Modifier panel | frame 01:06:41 |
| Clip start | 0.1 | Sidebar (N) > View | 01:16:10 |
| Silhouette check | Solid shading, object colour black, Specular Lighting off | Viewport Shading popover | 00:30:40 |

Clip start only hides flicker from the course's oversized scene (2 m round cubes). Leave it alone at real scale.

## Mistakes the course warns about

- Moving, rotating or scaling a part in Object Mode: sculpt symmetry and the Mirror modifier then stop using the
  body's centre line. The course transforms only in Edit Mode [00:41:19] and repairs a slip with Apply All
  Transforms [01:18:41]. `place` and `scale_parts` avoid it. Repair: `bpy.ops.object.transform_apply(location=True,
  rotation=True, scale=True)` inside `bpy.context.temp_override(active_object=o, object=o, selected_objects=[o],
  selected_editable_objects=[o])` (verified in 4.5.16 background).
- Trying to shape a stretched section that has no edges across it [00:43:18]. `stretch_half(cuts=...)` adds them.
- A dead-upright neck [00:42:51]; a ball-shaped back of the head [00:40:05]; a ball-shaped back [00:51:51].
- Parts stacked end to end, or floating apart, instead of sunk into each other [00:53:26, 00:57:31].
- Arms too close to the body, or dead straight at the elbow [01:17:13, 01:19:25].
- Multi-object Edit Mode with the wrong active object, which drags in an unintended part [01:31:22].
- Judging from one view. A part that is right from the front can be badly off from another side [01:29:06].
- Adding detail now [01:22:14], and moving on before the blockout looks right [01:34:42].

## What changes for a different character

General: one low-resolution primitive per body mass; head first, then down the centre, then out along the limbs;
overlap between neighbours; neutral pose; a proportion pass at the end; never transform the objects themselves.
Specific to this character: a slim young woman with small shoulders, three torso parts, mitten hands and wedge feet;
the straight-against-curve placements and the calf and ankle rule describe human legs.

- Heavy or muscular bodies: same parts, other scales; the course's own examples include both [00:22:48, 00:28:52].
- Children and big-headed styles (ours): place the head at its true size first; two torso parts may be enough.
- Four-legged creatures (ours): the spine parts lie along Y; build capsules with `stretch_half(axis=1)`; each leg is
  three parts plus a paw; tails, wings and horns are one capsule or flattened round cube each, spread out.
- Hard-surface parts (ours): block them with `bpy.ops.mesh.primitive_cube_add` and `primitive_cylinder_add`, keep
  them as separate objects parented to `CHARACTER`, and never put them in the body join or a voxel remesh, which
  rounds every edge.
- Clothes and hair are not blocked out in this chapter. If the measurable references are clothed, add crude shapes
  named `BLKC_...` (ours) parented to `CHARACTER`, so `outline_match(object="CHARACTER")` includes them; keep them
  out of the body join and delete them when stage 05 builds the real pieces.

## Exit check

Run on a fresh `build_proxy(voxel_size=0.01 * H)`:

1. `scene_tree`: 13 `BLK_` mesh objects, each parented to `CHARACTER`, each at location 0, rotation 0, scale 1. The 8 paired parts (ears, upper
   leg, lower leg, foot, shoulder, upper arm, lower arm, hand) each carry one Mirror modifier.
2. `mesh_report` on each part: `loose_parts` 1, `boundary_edges` 0, `non_manifold_edges` 0. On the five centre
   parts `symmetry_error` is at most 0.002 (ours).
3. `mesh_report(object="BLOCKOUT_PROXY")`: `loose_parts` 1 (every part touches its neighbours), `boundary_edges` 0,
   `symmetry_error` at most 0.005 (ours), and `bounds_min` Z within 0.01 `H` of 0 (feet on the ground).
4. `turnaround_sheet(object="CHARACTER", references={...})`, looked at for: the S curve from the side, arms
   clear of the body with a slight elbow bend, no stacked or floating parts, a readable outline.
5. `outline_match(object="CHARACTER", references={...}, threshold=0.98)`. Record the `iou` of every measured
   view. A view with no picture is `not_run`: report it as "looked at, not measured".
6. `width_profile` against `picture_profile` for each measured view: no row differs by more than 0.02 (ours),
   except rows the notes explain by something not built yet (hair, skirt, boots).

What counts as failed: any number in 1 to 3 outside its limit; a measured view whose overlay shows red or blue
areas that come from the body itself (limb length, shoulder or hip width, head size, arm angle) and not from
clothes or hair still to be built; any unexplained row in 6. A bare blockout measured against a clothed, haired
reference will not reach 0.98. Report such a view as "failed at 0.98, iou N; body proportions accepted; the
remaining difference is hair and clothes". Never report it as passed. If the reference shows the bare body in the
neutral pose, the gap to 0.98 is a proportion error: fix it now, while the parts are still simple.

## Gaps

- Add-on: "Extra Mesh Objects" (free, Blender's extension site) supplies `Round Cube`; not installed in the reader's
  4.5.16, replaced by `round_cube()`. Quick Favorites and the extra shading pie items are hand-speed aids only.
- `Line Project` becomes `slice_flat` (same flat cut, given as a plane). `Scrape/Fill` has no equivalent; use
  `slice_flat` close to the surface, or `smooth`. `Crease Polish` is approximated by `crease`, which cuts the groove
  but does not polish the faces beside it. `Lasso Mask` becomes a `sculpt_mask` box: no slanted mask edges.
- The course judges every proportion by eye against a posed three-quarter drawing and gives no numbers for part
  sizes, positions or angles. Every size, angle and tolerance here marked "ours" or read from a frame is a starting
  point, not the course's instruction.
- The live tools were not run against a GUI Blender for this file; the stroke maths was checked by calling
  `sculpt_cmds.py` in background Blender. Example coordinates assume `H = 1.7`; recompute them with `outline_point`.
- `turnaround_sheet`, `outline_match` and `mesh_report` take one object, hence `build_proxy` before every check.
