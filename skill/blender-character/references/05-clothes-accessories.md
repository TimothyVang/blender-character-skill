# 05 Clothes and accessories

Course source: chapter 06 "Sculpting the Clothes & Accessories", 04:15:04 to 06:02:34. The course records in
Blender 5.0.1; every Python block here was run in 4.5.16.

## Goal

Every garment and accessory in the concept is its own named object, parented to `CHARACTER`, just outside the
skin with no skin poking through, with a clean big shape and only a few deliberate folds and seams on top. A
rough placeholder hair mass is in place, and the dressed character's outline matches the references.

## Starting state

- The finished body sculpt from stage 04: separate `BLK_` parts under `CHARACTER` (the course fuses the body only
  at retopology, stage 06), neutral pose, feet on Z = 0, facing -Y, scale applied. Cloth is fitted against
  `body = body_target()`: a hidden, fused copy of the parts named `BODY_TMP`, rebuilt after any body change and
  deleted at the end of this stage. Every piece is parented to `CHARACTER`.
- `REF_<VIEW>` reference empties from stage 01, and the list of which views have a real picture.
- A saved `character_04_body.blend`. This stage also edits the body (steps 8 and 11), so that file is your undo.

## Order of work

### 1. Read the cloth before making any [04:15:40 to 04:24:20]

Cloth takes the shape of what is under it, so the body decides most of a garment's form. Every fold comes from
two forces. **Tension**: cloth pulled from a point (bust, shoulder, a hand gripping a skirt) makes straight
folds that fan out from that point. **Compression**: cloth pushed into itself or the body (sleeve at the elbow,
a waist tucked into trousers, the back of a knee) bunches into zigzags and spirals. The course lists seven
named fold types [04:18:51] and then says not to memorise them: find the pull points and squeeze zones instead.
A character that will be animated gets few, shallow folds, only where those forces act [04:23:13]. For each
piece note first where it is tight, where it hangs free, its pull points and its squeeze zones.

### 2. Decide how each piece starts

| Piece | Course start | Route here |
|-------|--------------|------------|
| Tight top (T-shirt) [04:25:31] | Cube, box-modelled round the torso, `Mirror` modifier | `extract_region` from the body (step 3) |
| Trousers [04:51:47] | Cube, box-modelled, legs extruded down | `extract_region`, then widen loose parts (step 6) |
| Pleated skirt [05:17:15] | 33-vertex mesh circle, every third vertex tucked in | `pleated_skirt` (step 7) |
| Boots, shoes [05:31:33] | Cube, box-modelled round a re-posed foot | `loft_tube` plus `Shrinkwrap` on the shaft (step 8) |
| Hair cap [05:47:13] | Lasso mask on the head, `Mask > Mask Extract` | `extract_region` on the head (step 9) |
| Hair locks, bun [05:53:55] | Single vertex extruded into a chain, `Skin` modifier | `skin_strand` (step 9) |

The course draws nothing as curves in this chapter and adds no `Shrinkwrap` modifier by hand; it fits cloth to
the body with the Grab and Inflate brushes. `Shrinkwrap` and `push_out` below replace that hand fitting because
they give a measured gap. Paste this block once per session with `exec_python`; later steps call its functions.

```python
# verified in 4.5.16 background
import bpy, bmesh, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
def apply_modifier(o, name):
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
        bpy.ops.object.modifier_apply(modifier=name)
def world_co(o):
    a = np.empty(len(o.data.vertices) * 3, np.float32); o.data.vertices.foreach_get("co", a)
    m = np.array(o.matrix_world)
    return a.reshape(-1, 3).astype(np.float64) @ m[:3, :3].T + m[:3, 3]
def set_world_co(o, w):
    m = np.array(o.matrix_world.inverted())
    o.data.vertices.foreach_set("co", (w @ m[:3, :3].T + m[:3, 3]).astype(np.float32).ravel()); o.data.update()
def adopt(piece, color):             # parent to CHARACTER without moving, and set a viewport colour (r, g, b, 1)
    root = bpy.data.objects["CHARACTER"]
    piece.parent = root; piece.matrix_parent_inverse = root.matrix_world.inverted(); piece.color = color
def body_target(name="BODY_TMP", voxel=0.008, skip=("BLK_eye",)):
    """Hidden copy of the BLK_ body parts, modifiers applied, fused into one skin by a voxel remesh (overlapping
    parts would otherwise leave buried faces). Cloth is fitted to it; the parts themselves are untouched. The copy
    is exact to about half a voxel: after rebuilding it, run push_out again before the clearance count."""
    old = bpy.data.objects.get(name)
    if old: bpy.data.objects.remove(old, do_unlink=True)
    dg = bpy.context.evaluated_depsgraph_get(); bm = bmesh.new()
    for ob in bpy.data.objects:
        if ob.type != "MESH" or not ob.name.startswith("BLK_") or ob.name in skip: continue
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg)); me.transform(ob.matrix_world)
        bm.from_mesh(me); bpy.data.meshes.remove(me)
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free()
    o = bpy.data.objects.new(name, out); bpy.context.scene.collection.objects.link(o)
    if voxel > 0:
        out.remesh_voxel_size = voxel
        with bpy.context.temp_override(active_object=o, object=o, selected_objects=[o]):
            bpy.ops.object.voxel_remesh()
    o.hide_set(True)
    return o
def extract_region(body, name, keep, lift=0.004):
    """New object from the body faces whose centre passes keep(world_point), pushed out by lift along normals."""
    bm = bmesh.new(); bm.from_mesh(body.data); bm.transform(body.matrix_world)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f.calc_center_median())], context="FACES")
    bm.normal_update()
    for v in bm.verts: v.co += v.normal * lift
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); body.users_collection[0].objects.link(o)
    return o
def loft_tube(name, rings, segments=16):
    """rings: [(cx, cy, z, rx, ry), ...] bottom to top. Open-ended quad tube, normals outward."""
    bm = bmesh.new(); loops = []
    for cx, cy, z, rx, ry in rings:
        loops.append([bm.verts.new((cx + rx * math.cos(2 * math.pi * i / segments),
                                    cy + ry * math.sin(2 * math.pi * i / segments), z)) for i in range(segments)])
    for a, b in zip(loops[:-1], loops[1:]):
        for i in range(segments):
            j = (i + 1) % segments; bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    return o
def clearance(piece, body):
    """Signed distance of each piece vertex from the body surface, world units. Negative = inside the body."""
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    inv = body.matrix_world.inverted(); out = []
    for p in world_co(piece):
        lp = inv @ Vector(p); q, nrm, _, d = bvh.find_nearest(lp)
        out.append(d if (lp - q).dot(nrm) >= 0 else -d)
    return np.array(out)
def push_out(piece, body, gap=0.003, passes=3):
    """Move piece vertices inside the body, or closer than gap, out to gap above it. Returns moved count per pass."""
    bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
    inv, mw = body.matrix_world.inverted(), body.matrix_world
    w = world_co(piece); counts = []
    for _ in range(passes):
        moved = 0
        for i, p in enumerate(w):
            lp = inv @ Vector(p); q, nrm, _, d = bvh.find_nearest(lp)
            if (lp - q).dot(nrm) < gap * 0.98: w[i] = mw @ (q + nrm * gap); moved += 1
        counts.append(moved)
        if not moved: break
    set_world_co(piece, w)
    return counts
```

### 3. Start a tight garment from the body (the mask-extract route) [04:25:31, 05:48:22]

Course, for the shirt: add a cube, move it to the chest in Edit Mode, extrude down to the hem, add loop cuts,
mirror it with the free Auto Mirror add-on, inset and delete the faces for the neck hole and the open bottom,
extrude short slanted sleeves and delete their end faces, then pull every loop in toward the body
[04:25:44 to 04:30:50]. A long sleeve is the same extrusion taken to the wrist with more loops [04:33:21]. The
only mask extraction in the chapter is the hair cap (step 9).
Route here: copy the body faces the garment covers. The copy already follows the body, so nothing needs
fitting. `keep` is any test on a world-space point; build it from heights read off the body with `mesh_report`.

```python
# verified in 4.5.16 background
body = body_target()                               # rebuild after any change to the BLK_ parts
hem_z, neck_z, sleeve_x = 0.98, 1.46, 0.30        # example numbers: read yours from the body
shirt = extract_region(body, "Shirt", lambda p: hem_z < p.z < neck_z and abs(p.x) < sleeve_x, lift=0.004)
adopt(shirt, (0.9, 0.5, 0.45, 1))
result = {"faces": len(shirt.data.polygons), "inside_body": int((clearance(shirt, body) < 0).sum())}
```

- `lift` is the gap between skin and cloth. Make it about the fold depth you plan (step 5) so valleys have room.
- An `abs(p.x)` limit cuts an A-pose sleeve at a slant; test distance along the arm for a square sleeve end.
- The cut edges are stepped by one body face. Run `smooth` strokes along them; stage 06 redraws them anyway.
- Check with `mesh_report("Shirt")`: `loose_parts` 1, `non_manifold_edges` 0; `boundary_edges` above 0 (open ends).

Blender's own operator also runs from a script (verified in 4.5.16 background, not tried through the live
bridge, so prefer `extract_region`): with the body active and in Sculpt Mode (`bpy.ops.object.mode_set`),
`bpy.ops.sculpt.paint_mask_extract(mask_threshold=0.5, add_solidify=True)` turns the sculpt mask into an object
named `Mesh` carrying a `geometry_extract_solidify` modifier (thickness 0.01, offset -1). It is not under
`bpy.ops.mesh`.

### 4. Shape the blockout, then give it density and thickness [04:30:55 to 04:39:10, 04:50:56]

Course: in Sculpt Mode, Grab moves the cloth onto the body, Smooth evens it, Inflate pushes out any spot where
skin shows through; small intersections are accepted while the mesh is coarse [04:32:42]. Each piece gets its
own viewport colour so cloth reads against skin [04:31:24]. Then: subdivide once in Edit Mode with `Smoothness`
1 [04:33:42], reshape, even out bunched faces with the Relax Slide brush [04:36:45], apply the `Mirror`
modifier, symmetrize and merge stray centre-line vertices [04:38:02], add a `Multires` modifier and subdivide
twice [04:39:17], and add a `Solidify` modifier below it for thickness [04:50:56].

Route here. Multires is no use to you: `sculpt_strokes` moves base-mesh vertices only, so levels above the base
cannot be sculpted. Make the density real, and keep `Solidify` as a live modifier (strokes still reach the base
surface under it).

```python
# verified in 4.5.16 background
bpy.context.scene.collection.objects.link(bpy.data.objects.new("Shirt_blockout", shirt.data.copy()))  # undo copy
bpy.data.objects["Shirt_blockout"].hide_set(True)
m = shirt.modifiers.new("Subdivision", "SUBSURF"); m.levels = 1      # each level multiplies faces by 4
apply_modifier(shirt, "Subdivision")
sol = shirt.modifiers.new("Solidify", "SOLIDIFY")
sol.thickness = 0.022; sol.offset = -1.0; sol.use_rim = True         # course values for the shirt
for p in shirt.data.polygons: p.use_smooth = True                    # the course shades smooth [04:47:57]
result = push_out(shirt, body, gap=0.003)
```

- `offset = -1.0` (the course's value on every garment) grows the thickness inward, toward the skin: the
  surface you sculpt stays the outer one and the outline does not change. `offset = 1.0` grows it outward and
  widens the outline by the thickness. Both were measured.
- Fit with `sculpt_begin("Shirt", symmetry="X")` and `grab`, `smooth`, `inflate`, as on the body. After each
  round of strokes call `push_out` again and look with `turnaround_sheet("CHARACTER")` (children are shown).
- Density rule (mine): mean edge length at most a third of the smallest stroke radius you will use. With edges
  of 0.005, a `draw` stroke of radius 0.02 and strength 0.5 raised a clean ridge 0.005 high.

### 5. Folds and seams [04:40:57 to 04:50:40, 05:04:50 to 05:15:50]

Course method, the same on every piece:

1. X symmetry **off**, so left and right folds differ [04:41:25]; on only to rough in both armpits [04:46:00].
2. Draw brush: stroke a raised ridge along each fold, branch a second ridge off it, join ridges where cloth
   gathers; with Ctrl held, dig the valley beside each [04:41:50 to 04:42:39]. Smooth lightly [04:43:14].
3. Sharpen, for a stylized look: Crease Polish brush with Ctrl held, along each valley and the foot of each
   ridge [04:43:25 to 04:45:30]. Add one subdivision level and sharpen again [04:48:02].
4. Seams and the waistband line: Draw Sharp along the line, then Pinch/Magnify to tighten it [05:06:26, 05:14:17].
5. A raised panel (the trouser fly): Clay to build it, Scrape to flatten, Crease Polish for its edges [05:07:59].

Where the course puts them. Shirt: bunching at the waist where it tucks in, short folds from the armpit, a few
on the sleeve [04:41:07, 04:45:36]. Trousers: a fan from the crotch, zigzags behind the knee, a couple under
the seat, long straight folds down the loose lower leg [05:04:50, 05:09:59, 05:11:44]. Boots: bunching at the
ankle and the top of the shaft [05:45:05]. Vary angle, length and spacing; use curves and diagonals [04:44:34].
Work from a photo of the same garment type [04:42:53].

Route here (`symmetry` empty; points from `mesh_report` bounds or vertex positions):

```json
{"object": "Shirt", "symmetry": "", "capture": true, "view": "FRONT", "strokes": [
 {"brush": "draw",   "points": [[-0.10,-0.11,1.06],[0.0,-0.12,1.05],[0.09,-0.11,1.07]], "radius": 0.02,  "strength": 0.5, "snap": true},
 {"brush": "crease", "points": [[-0.10,-0.11,1.04],[0.0,-0.12,1.03],[0.09,-0.11,1.05]], "radius": 0.012, "strength": 0.5, "snap": true},
 {"brush": "smooth", "points": [[-0.10,-0.11,1.05],[0.09,-0.11,1.06]], "radius": 0.03, "strength": 0.3}]}
```

- Ridge = `draw`. Valley and seam = `crease`: it cuts and pinches in one stroke, so it stands in for Crease
  Polish, Draw Sharp and Pinch. A sharper ridge top = `crease` with `"subtract": true` at low strength.
- A valley can sink below the skin: in the test, one `crease` stroke left 132 shirt vertices inside the body.
  Call `push_out` after each fold pass. It clamps valleys at `gap`, so if a fold vanishes the cloth was too
  close to the skin: `inflate` that area first, then cut again.

### 6. Trousers [04:51:47 to 05:16:50]

Course: cube at the hips, overlapping the shirt's hem so the shirt tucks in; Auto Mirror; the bottom faces
extruded to the knee and the end faces deleted; the knee loop made round with LoopTools `Circle` [04:54:25];
extruded again to the floor and scaled out, because this pair flares below the knee [04:58:17]. Then one
subdivide, `Solidify` 0.037, apply `Mirror`, `Multires` two levels and a third for folds [05:03:13 to 05:05:28].
Where the trousers are tight the body is pushed in a little under them [05:04:41].
Route here: `extract_region(body, "Trousers", lambda p: ankle_z < p.z < waist_z)` gives legs and seat already
joined. Widen the loose part: per leg, scale the vertices below the knee away from that leg's centre line in X
and Y by a factor that grows toward the hem (numpy on `world_co`, written back with `set_world_co`), `smooth`,
then steps 4 and 5. Set `waist_z` above the shirt's hem so the two overlap.

### 7. Pleated skirt [05:17:15 to 05:24:10]

Course: mesh circle with 33 vertices; `Select > Checker Deselect` with `Selected` 2, then invert, so every third
vertex is selected; scale those in and rotate them about Z so each tucks under its neighbour [05:17:56]; cut
the long edges once and push the new vertices out a little; extrude up and scale in for the waist; LoopTools
`Relax` on the top loop, extrude once more and LoopTools `Circle` for a round waistband [05:19:30]; recalculate
normals; `Subdivision Surface` level 2; fit to the hips in Edit Mode; `Solidify` 0.03. No Multires and no
sculpted folds: the pleats are the folds [05:23:55].

```python
# verified in 4.5.16 background (and looked at in a render: reads as a knife-pleated skirt)
def pleated_skirt(name, pleats=11, waist_z=1.0, hem_z=0.72, waist_r=(0.19, 0.14), hem_r=(0.30, 0.26),
                  tuck=0.82, twist=0.55, band=0.03):
    """3 vertices per pleat; every third is pulled in to `tuck` of the radius and turned by `twist` of a pleat's
    angle. Pleats fade toward the waist and are gone at the band. waist_r, hem_r are (x radius, y radius)."""
    n = pleats * 3; step = 2 * math.pi / n
    def ring(z, r, amount):
        pts = []
        for i in range(n):
            a, k = i * step, 1.0
            if i % 3 == 0: a += twist * 3 * step * amount; k = 1 - (1 - tuck) * amount
            pts.append((r[0] * k * math.cos(a), r[1] * k * math.sin(a), z))
        return pts
    mid_r = ((waist_r[0] + hem_r[0]) / 2, (waist_r[1] + hem_r[1]) / 2)
    rows = [ring(hem_z, hem_r, 1.0), ring((hem_z + waist_z) / 2, mid_r, 0.8), ring(waist_z, waist_r, 0.35),
            ring(waist_z + band, waist_r, 0.0)]
    bm = bmesh.new(); loops = [[bm.verts.new(p) for p in row] for row in rows]
    for a, b in zip(loops[:-1], loops[1:]):
        for i in range(n):
            j = (i + 1) % n; bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    for p in me.polygons: p.use_smooth = True
    s = o.modifiers.new("Subdivision", "SUBSURF"); s.levels = 2; s.render_levels = 2
    t = o.modifiers.new("Solidify", "SOLIDIFY"); t.thickness = 0.03; t.offset = -1.0
    return o
skirt = pleated_skirt("Skirt"); adopt(skirt, (0.9, 0.5, 0.45, 1))
```

The skirt is centred on the world origin: pass hip radii and heights read from the body, or move the object.
The waistband must cover the shirt's hem [05:21:37]. For an uneven hem move hem vertices up or down, front and
back differently [05:22:31]. `twist=0` with a smaller `tuck` gives gathers; `loft_tube` gives a plain skirt.

### 8. Boots and shoes [05:24:14 to 05:47:05]

Feet first. A heeled shoe needs the foot tilted, toes down. The course rotates the foot's vertices about the
ankle in Edit Mode, repairs the stretched ankle and sole in Sculpt Mode and voxel-remeshes, deflating the toes
first so they do not fuse [05:24:27 to 05:31:30]. For flat shoes leave the foot alone [05:24:41].

```python
# verified in 4.5.16 background
def tilt_foot(body, ankle, angle_deg, side=1, blend=0.05):
    """Rotate one foot (side=1 is +X) about the X axis through `ankle`. Positive = toes down when facing -Y."""
    w = world_co(body); sel = (w[:, 0] * side > 0) & (w[:, 2] < ankle[2])
    f = np.clip((ankle[2] - w[sel, 2]) / blend, 0, 1); ang = math.radians(angle_deg) * f * f * (3 - 2 * f)
    y, z = w[sel, 1] - ankle[1], w[sel, 2] - ankle[2]
    w[sel, 1] = ankle[1] + y * np.cos(ang) - z * np.sin(ang)
    w[sel, 2] = ankle[2] + y * np.sin(ang) + z * np.cos(ang)
    set_world_co(body, w); return int(sel.sum())
```

Call it as `tilt_foot(bpy.data.objects["BLK_foot"], ankle, angle)`: its `Mirror` modifier makes the other foot,
so once is enough. `smooth` the ankle, `sculpt_remesh` the foot, then rebuild `body = body_target()`. The toes now
sit below Z = 0. In a heeled shoe the character stands on its soles, as the reference picture shows it: when the
boots exist, raise every child of `CHARACTER` together by the same amount (`for o in
bpy.data.objects["CHARACTER"].children: o.location.z += lift`) until the lowest sole point is on Z = 0 again, and
leave `CHARACTER` and the `REF_` empties where they are. The character then stands on Z = 0 in its shoes (my
advice).

The shoe. Course: a cube at the shin, extruded down to the ankle, to the sole and forward to the toe in side
view; the sole made dead flat by scaling to zero on Z (`S Z 0`); Auto Mirror for the shoe's own left-right
symmetry; then that mirror is applied and a second `Mirror` modifier with `Mirror Object` set to the body makes
the other boot [05:36:16]. The heel is a block extruded down from the back of the sole and flattened the same
way [05:36:42]. `Solidify`, then `Multires` up to level 4 [05:41:07 to 05:42:39]. Details: a Draw Sharp line
round the join of sole and upper, pinched tight [05:42:14]; the underside cut flat with the Line Project tool
and its rim sharpened with Crease Polish [05:44:13]; a few folds at the ankle [05:45:05].

```python
# verified in 4.5.16 background
boot = loft_tube("Boot.L", [(0.1, 0, 0.06, 0.11, 0.12), (0.1, 0, 0.25, 0.11, 0.11), (0.1, 0, 0.45, 0.12, 0.12)])
s = boot.modifiers.new("Subdivision", "SUBSURF"); s.levels = 2; apply_modifier(boot, "Subdivision")
vg = boot.vertex_groups.new(name="fit")            # weight 0 at the sole, 1 from 0.2 above it: the foot part stays free
for i, p in enumerate(world_co(boot)): vg.add([i], float(np.clip((p[2] - 0.06) / 0.2, 0, 1)), "REPLACE")
sw = boot.modifiers.new("Shrinkwrap", "SHRINKWRAP")
sw.target = body; sw.wrap_method = "NEAREST_SURFACEPOINT"; sw.wrap_mode = "ABOVE_SURFACE"
sw.offset = 0.006; sw.vertex_group = "fit"         # measured: fully weighted vertices end exactly 0.006 off the skin
apply_modifier(boot, "Shrinkwrap")
# ... shape toe, sole and heel (grab strokes, symmetry ""), add Solidify as in step 4, then make the other boot:
right = boot.copy(); right.data = boot.data.copy(); right.name = "Boot.R"
boot.users_collection[0].objects.link(right)
w = world_co(right); w[:, 0] *= -1; set_world_co(right, w); right.data.flip_normals()
adopt(boot, (0.25, 0.25, 0.25, 1)); adopt(right, (0.25, 0.25, 0.25, 1))
```

Use a larger `offset` for a loose shaft. Flatten the sole by setting the Z of every vertex below the sole line
to one value with numpy (the scripted `S Z 0`). Build heel block and sole plate as boxes. Copy to `Boot.R` last.

### 9. Placeholder hair [05:47:05 to 06:00:00]

This hair only stands in for the groom of stage 08, so the head can be judged with hair on [05:52:42]. Break
the hairstyle into three or four big masses first (here: a skull cap, a lock each side, a bun) [05:48:40].

Cap. Course: lasso-mask the scalp from the side view, `Mask > Mask Extract` with default options, set the new
`Solidify` offset to 0 and raise its thickness, pull the edges in with Grab, apply the modifier, voxel remesh
at 0.015, flatten the hairline rim with Scrape, then stroke Clay Strips along the hair's flow toward the point
where it is tied [05:47:25 to 05:52:30]. Here, run the block, then `sculpt_remesh("Hair.Cap", voxel_size)` with
a voxel under a third of the thickness, then `clay_strips` strokes along the flow.

```python
# verified in 4.5.16 background (result: closed mesh, 0 boundary edges)
head = bpy.data.objects["BLK_head"]
cap = extract_region(head, "Hair.Cap", lambda p: p.z > 1.70 or (p.z > 1.62 and p.y > 0.0), lift=0.0)
s = cap.modifiers.new("Solidify", "SOLIDIFY"); s.thickness = 0.03; s.offset = 1.0   # outward only
apply_modifier(cap, "Solidify"); adopt(cap, (0.12, 0.1, 0.1, 1))
```

Locks and bun. Course: a single vertex (free Extra Mesh Objects add-on) extruded into a chain along the lock;
`Skin` modifier and `Subdivision Surface` level 2; thickness per vertex with `Ctrl A`; `Mirror` for the other
side; on a new separate chain, `Mark Root` on one vertex, or the skin fails with "no valid root vertex"
[05:57:49]; convert to mesh, voxel remesh, Clay Strips for direction [05:58:45 to 05:59:40].

```python
# verified in 4.5.16 background (result: closed mesh, modifiers baked in)
def skin_strand(name, points, radii, mirror=False, levels=2):
    """Tapering tube along world `points` with one radius per point. mirror=True adds the -X copy."""
    me = bpy.data.meshes.new(name); me.from_pydata(points, [(i, i + 1) for i in range(len(points) - 1)], [])
    o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
    o.modifiers.new("Skin", "SKIN")
    for i, sv in enumerate(me.skin_vertices[0].data): sv.radius = (radii[i], radii[i]); sv.use_root = (i == 0)
    o.modifiers.new("Subdivision", "SUBSURF").levels = levels
    if mirror: o.modifiers.new("Mirror", "MIRROR").use_axis = (True, False, False)
    baked = bpy.data.meshes.new_from_object(o.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    o.modifiers.clear(); o.data = baked; bpy.data.meshes.remove(me)
    return o
lock = skin_strand("Hair.Lock", [(0.09,-0.11,1.78), (0.12,-0.12,1.68), (0.125,-0.11,1.58), (0.11,-0.10,1.50)],
                   [0.03, 0.028, 0.02, 0.006], mirror=True)
adopt(lock, (0.12, 0.1, 0.1, 1))
```

### 10. Hard-surface accessories

The course makes none in this chapter: no buckle, button, belt object, jewellery or prop. The nearest it comes
is the boot's sole and heel, kept planar by box modelling and `S Z 0`, and the remark that a shoe can be
finished by polygon modelling instead of sculpting [05:44:43]. My recommendation for rigid pieces: build each
as polygons (`bmesh` or primitives), one object per piece, edges held by a `Bevel` modifier or a creased
`Subdivision Surface`; never voxel-remesh or stroke them; set them just off the cloth and `adopt` them too.

### 11. Names, parenting, and fixing the body to suit the clothes

The course leaves default names (`Cube.001` shirt, `Cube.002` trousers, `Circle` skirt, `Cube.003` boots, `Mesh`
hair cap, `Vert` and `Vert.001` hair). Do not. Later stages find pieces by name: `Shirt`, `Trousers`, `Skirt`,
`Boot.L`, `Boot.R`, `Hair.Cap`, `Hair.Lock`. A bun is described but not scripted here: if the concept has one,
make it as `Hair.Bun`, a `skin_strand` with two or three thick points or a `quad_ball`, and `adopt` it. One object
per piece, never joined to the body or to each other. `turnaround_sheet` and `outline_match` show an object together with its children, so an outfit
parented with `adopt` is measured as worn.
With the clothes on, compare proportions with the concept again and change the body where it is now wrong; the
course thickens the thighs and notes the head must be scaled up [06:00:04 to 06:00:40]. After any body change,
run `push_out` again on every piece near it.

## How the artist works on screen

The numbered observations correspond to the order above. Pixel sizes belong to the displayed zoom,
not world space; choose world radii from the actual garment dimensions and inspect after each pass.

### 1. Read the cloth

- The artist shows a dress pulled sideways and uses its held point to explain radiating tension
  [qy-wwP-b9HY-06-041738, 04:17:39].
- On a reference board, red guide lines run away from raised corners of hanging cloth
  [qy-wwP-b9HY-06-042208, 04:22:16–04:22:19].
- The board mixes close-up cloth examples with full garments, so the comparison includes both
  individual fold direction and the larger drape [qy-wwP-b9HY-06-042233, 04:22:35–04:22:44].
- An animated character is shown from the front with a mostly smooth shirt and a few folds
  near its hem [qy-wwP-b9HY-06-042311, 04:23:13–04:23:24].
- Reader equivalent: identify anchors and compression zones on the actual references first;
  use `turnaround_sheet` to judge the overall garment before sculpting details.

### 2. Choose the starting shape

- The clothing photo board is kept visible beside the whole neutral body, then the artist opens
  the Add menu and starts a shirt with a cube [qy-wwP-b9HY-06-042531, 04:25:33–04:25:43].
- Reader equivalent: choose `extract_region` for close cloth, or a polygon shell for a looser shape;
  these are scripted alternatives, not a claim that the course extracted its shirt.
- The separate orange garment makes intersections against the grey body easy to see later.

### 3. Shirt blockout

- In Edit Mode the shirt starts as a very coarse torso shell with horizontal bands and a center
  line; Auto Mirror appears in the sidebar [qy-wwP-b9HY-06-042701, 04:27:03–04:27:14].
- The artist pulls the side outward near the shoulder and adds loops for the sleeve,
  keeping the opposite half mirrored [qy-wwP-b9HY-06-042729, 04:27:30–04:27:40].
- They orbit to side and back, adding loops and checking that the shell wraps the torso
  [qy-wwP-b9HY-06-043047, 04:30:48–04:30:59].
- A long sleeve is briefly extruded to the wrist and then undone for the short-sleeve design
  [qy-wwP-b9HY-06-043334, 04:33:35–04:33:41].
- Reader equivalent: `extract_region` selects the torso and sleeve region from `BODY_TMP`;
  inspect the open neckline, hem and sleeve ends rather than treating extraction as finished.

### 4. Fit before detail

- In Sculpt Mode, Grab at strength 0.400 moves the coarse collar and shoulder;
  the cursor is large relative to the shoulder [qy-wwP-b9HY-06-043111, 04:31:12–04:31:22].
- They rotate behind the shoulder, dragging and smoothing the sleeve transition while some skin
  still shows through the coarse shell [qy-wwP-b9HY-06-043237, 04:32:39–04:32:49].
- Near the collar they alternate broad Grab adjustments and smoothing from oblique and front views
  [qy-wwP-b9HY-06-043417, 04:34:20–04:34:33].
- They zoom under the arm, pull the edge into place and inspect it from below before moving on
  [qy-wwP-b9HY-06-043732, 04:37:33–04:37:44].
- The Mirror modifier is applied before the next sculpting pass
  [qy-wwP-b9HY-06-043800, 04:38:02–04:38:12].
- Multires is then added and subdivided; the smooth silhouette appears before the waist folds
  [qy-wwP-b9HY-06-043917, 04:39:18–04:39:25; qy-wwP-b9HY-06-043926, 04:39:27–04:39:38].
- Reader equivalent: use `sculpt_strokes` Grab and Smooth with a radius initially a substantial
  fraction of the shoulder width, then `push_out` and inspect front and side with `turnaround_sheet`.
- Apply real subdivision as in step 4; the bridge cannot sculpt higher Multires levels.

### 5. Folds and seams

- The artist first draws guides near the tucked waist, then switches back to sculpting
  [qy-wwP-b9HY-06-044112, 04:41:13–04:41:23].
- The Draw header shows observed screen Size 80 px and strength 0.500 as the artist prepares the smooth waist
  for folds [qy-wwP-b9HY-06-044138, 04:41:39–04:41:49].
- Use asymmetric fold paths rather than copying the guides onto both sides;
  the guide lines indicate where compression would gather, not a required number of folds.
- Reader equivalent: `sculpt_begin("Shirt", symmetry="")`, then short `draw` and `crease`
  paths in world coordinates; start with a radius small relative to the waist width.
- Follow each set with `push_out`, and compare front and perpendicular views.
- At the front crotch, the artist forms a small fan and then softens and sharpens individual
  ridges [qy-wwP-b9HY-06-050521, 05:05:22–05:05:32; qy-wwP-b9HY-06-050533, 05:05:35–05:05:47].
- The back of each knee receives short crosswise compression folds, checked from behind
  [qy-wwP-b9HY-06-051223, 05:12:25–05:12:40].

### 6. Trousers

- The course separately demonstrates a trouser shell, with seat and legs shaped before the
  smaller fold and fly details; the final outfit returns to the skirt.
- The coarse trouser shell is fitted with Grab and Inflate around the hips and inner thighs;
  protruding skin remains visible during this rough stage [qy-wwP-b9HY-06-045606, 04:56:08–04:56:20].
- After fitting, they switch to the body and push an exposed thigh in under the cloth
  [qy-wwP-b9HY-06-050433, 05:04:35–05:04:43].
- Reader equivalent: rebuild `BODY_TMP` after body edits and check clearance rather than accepting
  the temporary coarse-stage intersections at the exit check.
- Reader equivalent: extract the covered body region, widen the lower legs from their own
  center lines, and use restrained crease paths after fitting.

### 7. Pleated skirt

- Pleats are built into the ring-based silhouette rather than added as sculpt marks.
- In isolation the artist raises the pleated ring toward the waist and extrudes a narrow band
  [qy-wwP-b9HY-06-051915, 05:19:17–05:19:32].
- After the skirt is returned to the body, a large Grab brush adjusts the waistband overlap and
  uneven hem [qy-wwP-b9HY-06-052134, 05:21:36–05:21:43; qy-wwP-b9HY-06-052235, 05:22:36–05:22:43].
- The pleats themselves come from the modeled ring; these broad Grab movements adjust the shape,
  not a separate sculpted wrinkle pass.
- Reader equivalent: `pleated_skirt` produces the repeated folded ring and waistband;
  compare the flare and hem against the actual reference before choosing radii.

### 8. Foot and boots

- During foot remesh sizing, the overlay at 05:29:45 reads **0.00733 m**; this is the displayed
  interactive value, not a universal setting [qy-wwP-b9HY-06-052937].
- In right orthographic Edit Mode the artist moves the boot shell around the foot and flattens
  the sole on Z [qy-wwP-b9HY-06-053227, 05:32:29–05:32:40].
- Later, the sole line is traced from the side and the Stroke menu is opened for stabilization
  [qy-wwP-b9HY-06-054322, 05:43:24–05:43:37]; Pinch tightens it around the toe
  [qy-wwP-b9HY-06-054403, 05:44:05–05:44:12].
- Reader equivalent: select a voxel size relative to the foot and toe spacing; inspect separation
  after remeshing and do not copy the course's number without scaling it to the model.
- Fit the boot shaft and its planar sole separately; use `loft_tube`, measured clearance and
  coordinate edits rather than assuming Blender's interactive brushes are available.

### 9. Hair masses

- In right orthographic Sculpt Mode, the scalp mask starts at the high forehead and falls in
  front of the ear; the dark selected region covers the crown and back of the head
  [qy-wwP-b9HY-06-054739, 05:47:41–05:47:53].
- The artist orbits through front and side views to inspect the masked hairline before extraction
  [qy-wwP-b9HY-06-054808, 05:48:09–05:48:20].
- Solidify offset is set to zero and the thickness is increased while the cap is viewed from
  the front; the exact final thickness remains obscured [qy-wwP-b9HY-06-054834, 05:48:36–05:48:44].
- Clay Strips at strength 0.500 makes repeated strokes from the hairline around toward the back;
  the artist rotates above the head to check flow [qy-wwP-b9HY-06-055137, 05:51:40–05:51:59].
- The front locks are mirrored and checked from front and three-quarter views
  [qy-wwP-b9HY-06-055621, 05:56:24–05:56:37].
- A separate rear chain initially shows the Skin modifier's missing-root warning
  [qy-wwP-b9HY-06-055735, 05:57:37–05:57:47].
- Reader equivalent: shape `Hair.Cap` with `extract_region`, remesh at a size relative to cap
  thickness, and use `clay_strips` in short paths following the intended gathering direction.
- Use `skin_strand` with a root for each separate chain and compare the silhouette from the side.

### 10. Rigid accessories

- No separate jewellery construction is established by these observations.
- Reader equivalent: model each required rigid item separately with polygons and controlled bevels;
  keep this as a recommendation, not an observed course operation.

### 11. Recheck the dressed figure

- With the skirt and boots visible, the artist compares the legs against the concept, inflates
  the thighs and changes Grab radius while inspecting the knees
  [qy-wwP-b9HY-06-060028, 06:00:30–06:00:42].
- Reader equivalent: change `BLK_leg` with broad `inflate` or `grab` strokes, rebuild
  `BODY_TMP`, and rerun `push_out` for nearby cloth.
- Measure the entire `CHARACTER` against each real usable reference at 0.98; an unavailable view
  remains `not_run`, never a pass. Keep Z up, feet on Z=0, and the character facing -Y.

## Settings the course uses

| Setting | Value | Where | Time |
|---------|-------|-------|------|
| Auto Mirror | axis `X`, `Positive`, `Threshold` 0, `Cut and Mirror` on, `Use Clip` on | sidebar `Edit` tab | 04:27:16 |
| `Mirror` modifier | axis `X`, `Clipping` on, `Merge` 0.001 m | shirt, trousers blockout | 04:30:57 |
| Edit Mode `Subdivide` | 1 cut, `Smoothness` 1 | shirt, trousers, before Multires | 04:33:42 |
| `Multires` levels | 2, then 3 to sharpen (boots up to 4) | shirt, trousers, boots | 04:39:26, 04:48:11, 05:42:39 |
| `Solidify` | `Simple`, offset -1, rim `Fill`; thickness 0.022 shirt, 0.037 trousers, 0.03 skirt, about 0.08 boots | below Multires | 04:51:14, 05:03:22, 05:23:06, 05:41:26 |
| Brush strengths on screen | Draw 0.5, Crease Polish 0.25, Grab 0.4, Pinch/Magnify 0.5, Scrape/Fill 0.7, Clay Strips 0.5 | Sculpt Mode header | 04:39:36, 04:44:05, 04:47:56, 05:07:50, 05:50:34, 05:59:52 |
| Skirt circle | 33 vertices; `Checker Deselect` `Selected` 2, inverted (11 pleats) | skirt start | 05:17:38 |
| `Subdivision Surface` | Catmull-Clark, levels 2 | skirt, hair chains | 05:20:22, 05:54:47 |
| Boot `Mirror` | `Mirror Object` = body, `Clipping` off, `Merge` 0.001 m | second boot | 05:36:34 |
| Hair cap extract | default options; `Solidify` offset 0, thickness raised by eye | `Mask > Mask Extract` | 05:48:22 |
| Voxel remesh | 0.015 hair cap; 0.00733 m shown during foot voxel-size adjustment | Sculpt Mode | 05:50:30, 05:29:45 |

Brush sizes are in screen pixels and change with zoom, so none are listed. The course never states the
character's height: treat its metre values as proportions of its character, not absolutes.

## Mistakes the course warns about

- Too many folds, or deep ones, on a character meant to move [04:23:13, 04:47:45, 05:13:42].
- Folds that are parallel and evenly spaced [04:44:34]; folds sculpted from memory with no photo [04:42:53].
- Symmetric folds, both sides alike [04:41:25]; folds cut before the big shape is right [04:37:32, 04:49:39].
- Leaving symmetry off by accident during blockout [04:38:20]; centre-line vertices stuck together by mirror
  clipping (turn `Clipping` off, move them, turn it on) [04:58:42].
- Expecting a `Subdivision Surface` modifier to add sculptable geometry; Multires does, it does not [04:39:40].
  `Solidify` is not drawn in Sculpt Mode while Multires is active; that is normal [04:51:08].
- Remeshing a foot whose toes touch: they fuse [05:29:58]. A new `Skin` chain with no root vertex [05:57:49].
- Wobbly freehand seam lines; the course points to the brush's `Stabilize Stroke` option [05:43:27].

## What changes for a different character

General, for any character: tension and compression as the causes of folds; few folds on anything animated;
shape first, density second, folds last; one object per piece; thickness from `Solidify`, not from modelling
both sides; garments overlap where one tucks into another; placeholder hair as three or four masses.
Specific to the course's character (a slim stylized girl in a tight T-shirt, pleated mini skirt and block-heel
knee boots, hair tied in a bun): the fold positions in step 5, the 11 pleats, the heel tilt, the thicknesses.

- Loose or heavy garments (coat, robe, cape, wide sleeves): do not extract from the body. Use `loft_tube` or a
  box-modelled shell held off the body, fit only the anchor zones (shoulders, waistband) with a `Shrinkwrap`
  vertex group, and let the rest hang straight from them. Their folds are long tension folds from the anchors.
- Heavier bodies and creatures: `extract_region` works on any closed skin; set `lift` relative to body size and
  take the `keep` limits along each limb's own axis, not the world axes.
- Armour, helmets, props: step 10. Shape them to their own reference outline; they do not follow the skin.
- Fur, feathers or manes that define the outline: block them as masses like the hair in step 9. Asymmetric
  designs (one sleeve, a sash): build without symmetry from the start.

## Exit check

1. `scene_tree`: every piece in the concept exists under its own name, parented to `CHARACTER`. List them.
2. Per piece, `mesh_report`: `loose_parts` 1 and `non_manifold_edges` 0, else failed. `boundary_edges` above 0
   is expected on open cloth and must be 0 on closed pieces (`Hair.Cap`, `Hair.Lock`, anything voxel-remeshed).
3. Per cloth piece, with a fresh `body = body_target()`, `int((clearance(piece, body) < 0).sum())` must be 0. Any vertex inside the body is failed.
4. `turnaround_sheet("CHARACTER", references={...})`: look for skin showing through, folds that are parallel or
   everywhere, garments that do not overlap where one tucks into another. This is looking, not measuring.
5. `outline_match("CHARACTER", references={...}, threshold=0.98)` on the dressed character. Report each view's
   number with `passed` or `failed`; below 0.98 is failed. A view with no reference picture is `not_run`:
   report it as "looked at, not measured", never as passed. Fix the big shape of the piece under the red or
   blue area, not its folds. The placeholder hair is part of this outline.
6. Delete `BODY_TMP` (`bpy.data.objects.remove(bpy.data.objects["BODY_TMP"])`) and save as
   `character_05_clothes.blend`.

## Gaps

- **Multires.** The course's fold workflow sits on `Multires` levels, which `sculpt_strokes` cannot reach. Real
  subdivision (step 4) replaces it; you cannot step back down a level, so keep the `<name>_blockout` copy.
- **Brushes with no equivalent.** Crease Polish, Draw Sharp and Pinch/Magnify are approximated by `crease`;
  Scrape/Fill and the Line Project tool by setting vertex coordinates with numpy; Relax Slide by `smooth`; the
  lasso mask by `extract_region`'s point test. Expect stylized fold edges to be less crisp than the course's.
- **Fitting.** `push_out` and `Shrinkwrap` fit to a measured gap but know nothing about how cloth hangs. Loose
  parts must be shaped by you. The course uses no cloth simulation or Cloth brush either.
- **Add-ons the course uses**, all free from Blender's extensions site: Auto Mirror (use a `Mirror` modifier or
  build both sides), LoopTools `Circle` and `Relax` (build rings round, as `loft_tube` does), Extra Mesh Objects
  `Single Vert` (use `from_pydata`). Its reference board is a PureRef file [04:22:20]; PureRef is not needed.
- **Not verified.** Step 5's strokes ran on the stroke code in background Blender, not through MCP; nothing ran live.
- **Still uncertain.** The hair cap's final `Solidify` thickness is obscured at 05:48:38. The mask
  silhouette is visible from front and right, but the exact surface boundary cannot be recovered from
  those views alone. The trousers are a demonstration only: by 05:36:34 they are hidden and the
  character wears the skirt. Belts, buckles, buttons and the concept's necklace are not made here.
