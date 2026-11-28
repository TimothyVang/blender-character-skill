# 03 Sculpt the face

Course source: chapter 04 "Sculpting the Face of Your Character", 01:36:09 to 02:28:05.
(The course records in Blender 5.0.1; code-block verification is noted on each block.)
For a posed, render-only character built from spheres, see `speed-sculpt.md`. It does the face in the order
sphere, face plane, sockets, nose, ears, mouth, then eyeballs, then lids [YS 00:00 to 00:09].

## Goal

The head blockout has become a readable face: planes of the head, nose, eye sockets with eyeballs, eyelids that
wrap the eyeballs, a mouth that wraps the teeth, ears with a rim and inner forms, and placeholder brows and lashes.
Every feature sits on the proportion lines below and the head outline matches the concept in each view that has a
reference picture.

## Starting state

- From stage 02: `BLK_head` (one closed mesh, cranium plus jaw wedge), `BLK_neck`, and `BLK_ears` (one ear with a
  `Mirror` modifier), each built from a round cube and parented to `CHARACTER`. This stage adds `BLK_nose` (joined
  into `BLK_head` in step 9) and `BLK_eye` (one eyeball with a `Mirror` modifier).
- Origins at the world centre line (the course only moves blockout parts in Edit Mode so that X symmetry keeps
  working). Check `object_info`: location X must be 0 for `BLK_head`.
- Concept pictures placed with `reference_setup`, plus face close-ups if you have them. The course keeps a board
  of face references open the whole time (front, three-quarter, a line drawing, a photo) [01:49:36].
- Axes used below: the character faces -Y, up is +Z, left/right is X. `H` = head height (top of skull to bottom of
  jaw), `W` = head width, both read from `mesh_report(object="BLK_head")` bounds.

## Proportion rules the course states

Measure these before any stroke. All are stated on the slides at [01:37:16] to [01:42:40].

| Landmark | Rule | Timestamp |
|---|---|---|
| Eye line | Halfway between top of head and bottom of jaw. First landmark; everything else hangs off it. | 01:37:19 |
| Brow line, nose base | Pick a hairline. Hairline to jaw in three equal parts: upper cut = brow line, lower cut = bottom of nose. | 01:38:10 |
| Ear | Sits between brow line and nose base. | 01:39:00 |
| Back of skull | At brow-line height on the back, the skull turns in and runs into the neck. | 01:39:15 |
| Side depth | Outer eye corner to front of eye = 1 unit; front of eye to nose bridge = 1 unit; bridge to nose tip = 1 unit. Stops a flat face. | 01:39:48 |
| Mouth | Halfway between nose base and jaw bottom is the BOTTOM of the lower lip. | 01:40:55 |
| Eye spacing | Gap between the eyes = one eye width (eye, gap, eye are three equal spans). | 01:41:31 |
| Mouth width | Mouth corners never go wider than the centre of each eye (the pupil). | 01:42:06 |

The hairline itself is chosen for the design rather than fixed by the thirds rule
[qy-wwP-b9HY-04-013759, 01:37:59; qy-wwP-b9HY-04-013810, 01:38:10].

Form rules: the head is a cranium with a jaw wedge attached [01:42:57]. The planes to sculpt are forehead, temples
(both sides), eye line, brow line, side of the face, chin; the nose is added as a separate block, not a plane
[01:43:50]. Eyes sit in sockets, never on a flat face [01:44:49]. Lids wrap the ball and have three edges: the
rim touching the ball, the lid fold, and the edge where the lid meets the face [01:45:29]. The nose starts as a
rounded triangular block [01:46:41]. Lips wrap the teeth, so build a mound before cutting a mouth [01:47:27]. The
ear is a wedge from the front and from above; its detail is a question-mark rim plus a Y inside [01:48:32].

## Helpers (paste into the `exec_python` call that uses them)

```python
# verified in 4.5.16 background
import bpy, bmesh, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
C, D = bpy.context, bpy.data

def surface_point(ob, origin, direction):           # world-space ray onto the mesh
    bvh = BVHTree.FromObject(ob, C.evaluated_depsgraph_get()); inv = ob.matrix_world.inverted()
    hit = bvh.ray_cast(inv @ Vector(origin), (inv.to_3x3() @ Vector(direction)).normalized())
    return None if hit[0] is None else tuple(ob.matrix_world @ hit[0])

def face_pt(ob, x, z):                              # the point on the FRONT of the face at side x, height z
    return surface_point(ob, (x, -1e3, z), (0, 1, 0))

def face_landmarks(ob, hairline_frac=0.88):         # hairline_frac is a choice; read it off the concept
    zs = [(ob.matrix_world @ v.co).z for v in ob.data.vertices]; top, chin = max(zs), min(zs)
    hair = chin + (top - chin) * hairline_frac; third = (hair - chin) / 3; nose = chin + third
    return {"top": top, "chin": chin, "eye_line": (top + chin) / 2, "hairline": hair,
            "brow_line": chin + 2 * third, "nose_base": nose, "lip_bottom": (chin + nose) / 2}

def flatten(ob, center, radius, strength=0.7, only_above=False):   # stand-in for Scrape/Fill
    me = ob.data; n = len(me.vertices)
    co = np.empty(n * 3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(n, 3).astype(np.float64)
    c = np.array(ob.matrix_world.inverted() @ Vector(center)); r = radius / max(ob.matrix_world.to_scale())
    d = np.linalg.norm(co - c, axis=1); sel = d < r
    if sel.sum() < 3: return 0
    w = (1 - (d[sel] / r) ** 2) ** 2
    mean = (co[sel] * w[:, None]).sum(0) / w.sum()
    nrm = np.linalg.svd((co[sel] - mean) * np.sqrt(w)[:, None], full_matrices=False)[2][2]
    if np.dot(nrm, mean - co.mean(0)) < 0: nrm = -nrm
    dist = (co[sel] - mean) @ nrm
    if only_above: dist = np.maximum(dist, 0)                       # scrape only, do not fill hollows
    co[sel] -= nrm * (dist * w * strength)[:, None]
    me.vertices.foreach_set("co", co.astype(np.float32).ravel()); me.update(); return int(sel.sum())

def mask_where(ob, rule):                           # stand-in for Lasso Mask; rule(world_pos, world_normal) -> bool
    me = ob.data; a = me.attributes.get(".sculpt_mask") or me.attributes.new(".sculpt_mask", "FLOAT", "POINT")
    mw = ob.matrix_world; rot = mw.to_3x3()
    vals = [1.0 if rule(mw @ v.co, (rot @ v.normal).normalized()) else 0.0 for v in me.vertices]
    a.data.foreach_set("value", vals); me.update(); return int(sum(vals))

def quad_ball(name, radius=1.0, levels=3, location=(0, 0, 0)):     # built-in stand-in for the round cube
    me = D.meshes.new(name); bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=2.0)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=2 ** levels - 1, use_grid_fill=True)
    for v in bm.verts: v.co = v.co.normalized() * radius
    bm.to_mesh(me); bm.free()
    ob = D.objects.new(name, me); C.scene.collection.objects.link(ob); ob.location = location; return ob

def join_and_fuse(objs, target, voxel):                            # Ctrl+J then voxel remesh; target must be in objs
    dg = C.evaluated_depsgraph_get()
    for o in objs:                                                 # bakes Mirror etc. and unlinks shared data
        if o.modifiers or o.data.users > 1:
            m = D.meshes.new_from_object(o.evaluated_get(dg)); o.modifiers.clear(); o.data = m
    with C.temp_override(active_object=target, object=target, selected_objects=objs, selected_editable_objects=objs):
        bpy.ops.object.join()
    target.data.remesh_voxel_size = voxel
    with C.temp_override(active_object=target, object=target, selected_objects=[target]):
        bpy.ops.object.voxel_remesh()
    return len(target.data.vertices)
```

Every new object you make (`quad_ball`, the eyeball, later the fingers and toes) gets
`ob.parent = D.objects["CHARACTER"]` right after it is made, so the whole-character checks include it.
`join_and_fuse` keeps the target's name and parent.

## How course brushes map to `sculpt_strokes`

Course brush sizes are in screen pixels, so they do not convert; radii below are given against `H`. Strengths are
read from the brush panel in the video. The `blender-live` brushes move vertices by a known amount, which helps you
choose arguments: `draw` lifts the centre by `0.5 * radius * strength`, `clay_strips` by `0.3 * radius * strength`
with a flatter top, `crease` cuts `0.5 * radius * strength` deep and pinches, `grab` moves the centre by exactly
`(last point - first point) * strength` fading to nothing at `radius`.

| Course brush (strength seen) | Job in this chapter | `sculpt_strokes` |
|---|---|---|
| `Grab` (0.400) | Every proportion and silhouette change. Big radius for big forms. | `grab`, `strength` 1.0, give the real displacement |
| `Smooth` (hold Shift) | After every remesh, and after every build-up stroke | `smooth`, `strength` 0.3 to 0.6 |
| `Crease Polish` (0.250, `Pinch` 0.500) | Marking lines: jaw break, eye line, brow, mouth line, lid edges, nostril, ear rim | `crease` for a groove; `crease` with `"subtract": true` for a sharp raised edge |
| `Scrape/Fill` (0.700) | Flat planes: temple, side of face, underside of lid | `flatten(...)` helper above |
| `Clay Strips` (0.500) | Adding mass: nose-to-brow blend, mouth mound, cheeks, ear Y | `clay_strips`, `strength` 0.5 |
| `Draw` (0.500) | Lid ridges; with Ctrl, digging nostrils | `draw`; `"subtract": true` to dig |
| `Inflate` | Lower lip | `inflate` |
| `Lasso Mask`, `Front Faces Only` | Protecting all but the ear bowl | `mask_where(...)` or `sculpt_mask` box |

Use `"snap": true` on build-up and crease strokes so points land on the surface. On `grab` and `snake_hook`, snap
moves the whole path so its first point is on the surface and keeps its length. After any call check
`moved_verts`: 0 means the stroke missed.

## Order of work

Begin with `sculpt_begin(object="BLK_head", symmetry="X")`. With X symmetry on, give points on the +X side only; a
stroke that crosses X=0 stays symmetric.

1. **Add resolution, then smooth everything** [01:50:18]. The blockout is too coarse to hold planes. Course:
   voxel size `0.04` to `0.05`, `Ctrl+R`, then Smooth over the whole head. Live:
   `sculpt_remesh(object="BLK_head", voxel_size=H/50)`, then several `smooth` strokes with radius `0.3*H` covering the
   head. Look: one capture; no faceting, cranium and jaw still read as two masses.

2. **Re-mark the cranium/jaw break** [01:51:04]. It gives the jaw wedge a clear start. Course: `Crease Polish`
   along the back edge of the jaw, from under the ear position down toward the chin. Live:
   `{"brush":"crease","points":[side point under the ear, jaw angle, halfway to chin],"radius":0.05*H,"strength":0.4,"snap":true}`.

3. **Eye line** [01:51:21]. The foundation landmark. Compute `eye_line` with `face_landmarks`. Course: a
   `Crease Polish` band across the front at that height, stopping near the temple, not carried round the back;
   then `Grab` the middle of the band inward so the sockets sit behind where the nose will be [01:52:10]. Live:
   `{"brush":"crease","points":[face_pt(0,eye), face_pt(0.2*W,eye), face_pt(0.38*W,eye)],"radius":0.06*H,"strength":0.5,"snap":true}`
   then `{"brush":"grab","points":[face_pt(0.2*W,eye), same point moved +0.04*H in Y],"radius":0.2*H}`.
   Check from `LEFT`: a clear step in at half height.

4. **Brow line** [01:52:37]. Course: Smooth the area above the eye line first (that alone starts a brow shelf),
   find the brow height by the thirds rule, then `Crease Polish` along it [01:53:39]. Live: `smooth` at
   `brow_line`, then a `crease` stroke like step 3 at `z = brow_line`, radius `0.04*H`. The band between the two
   lines is now the eye plane.

5. **Temples** [01:53:52]. Course: `Scrape/Fill` the side of the head flat above the eye line, Smooth it, and
   re-cut the eye line if the scrape softened it. Live: `flatten(head, surface_point(head,(1e3,cy,brow+0.1*H),(-1,0,0)), 0.25*H, 0.7)`
   for the +X side and the mirrored call for -X (the helper has no symmetry), then repeat the step 3 crease.

6. **Side of the face and chin** [01:54:35]. Course: `Scrape/Fill` the cheek side below the eye line into one
   plane running to the jaw; a short `Crease Polish` mark under the lower lip area for the chin [01:54:52]. Live:
   `flatten` centred at a side point at `z = nose_base`, radius `0.25*H`; `crease` across `face_pt(0..0.1*W, chin + 0.12*H)`.
   Keep it this simple; the course says it deliberately uses fewer planes than anatomy charts show [01:55:48].

7. **First reference check** [01:55:04]. Compare front and side with the concept before adding parts. The course
   finds its cheeks too narrow and pulls them out with `Grab`, and pulls the brow in at the side. Live:
   `turnaround_sheet(object="CHARACTER", references={...})`, then `grab` with radius `0.3*H` for each difference.

8. **Nose as its own block** [01:55:48]. Course: new round cube, scaled down in Edit Mode, placed between eye line
   and `nose_base`, rotated so it leans with the profile. In Sculpt Mode with X symmetry: `Grab` its back into the
   face, pull the tip down and out, and make it a triangle seen from below [01:56:39]; mark nostrils with `Draw`
   held to subtract [01:57:22]. Live: make the block `BLK_nose` with `quad_ball` (helpers above), parented to `CHARACTER`,
   radius about `0.07*H`, at `face_pt(0, (eye+nose_base)/2)`; shape with `grab`; nostrils
   `{"brush":"draw","subtract":true,"points":[under-tip point at x=0.03*H],"radius":0.02*H,"strength":0.6}`.
   Side-depth rule: tip, bridge and eye front are one unit apart each.

9. **Join nose and head, remesh finer, blend** [01:57:45]. Course: select nose then head, `Ctrl+J`, voxel `0.03`,
   `Ctrl+R`. Then `Clay Strips` from the bridge up toward the brow and on both flanks so the nose grows out of the
   face, Smooth, and re-cut the brow line [01:58:11]. Live: `join_and_fuse([D.objects["BLK_nose"], head], head, H/65)`
   (helpers above) with `head = D.objects["BLK_head"]`;
   `{"brush":"clay_strips","points":[face_pt(0.02*W, eye), face_pt(0.06*W, brow)],"radius":0.05*H,"strength":0.5,"snap":true}`
   and a `smooth` over the same path. `mesh_report`: `loose_parts` must be 1.

10. **Eyeballs before lids** [01:59:04]. Lids are sculpted against a real ball. Course: UV sphere, rotate 90
    degrees on X (pole faces forward), scale, place at the eye line, push forward until it shows, Shade Smooth,
    `Mirror` modifier with `Mirror Object` = the head; then set the gap from the reference (the course character
    has wide-set eyes) [02:00:14]. Live:

    ```python
    # verified in 4.5.16 background
    def add_eyes(head, center, radius):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=center,
                                             rotation=(math.radians(90), 0, 0))
        eye = C.active_object; eye.name = "BLK_eye"; eye.parent = D.objects["CHARACTER"]
        for p in eye.data.polygons: p.use_smooth = True
        m = eye.modifiers.new("Mirror", "MIRROR"); m.mirror_object = head; m.use_axis[0] = True
        return eye
    ```
    Start from eye width = `W/5` only as a first guess (mine); the stated rule is gap = one eye width.

11. **Sockets** [02:00:28]. Course: `Grab` the surface around each ball backward so the ball sits in a hollow,
    Smooth; then tilt the eye shape to the concept (outer corner higher than inner for this character) [02:00:55].
    Live: `{"brush":"grab","points":[face_pt(ex, eye), that point +0.03*H in Y],"radius":0.12*H}`.

12. **Lid ridges** [02:01:10]. Course: remesh at `0.02`, Smooth all, then `Draw` a ridge over the top of the ball
    for the upper lid and under it for the lower lid, each followed by `Grab` to match the concept's eye shape.
    Live: `sculpt_remesh(object="BLK_head", voxel_size=H/100)`; upper lid
    `{"brush":"draw","points":[inner corner, top of ball, outer corner],"radius":0.03*H,"strength":0.5,"snap":true}`,
    lower lid the same along the bottom of the ball. Get the three points by ray casting just above and below the
    ball. The course then smooths its upper lid nearly away because the concept has almost no lid fold [02:02:52];
    do what your concept shows.

13. **The three lid edges** [02:03:20]. Course, upper lid: `Crease Polish` to sharpen the rim that touches the
    ball; `Scrape/Fill` the underside of the lid flat; `Grab` the lid ends backward so the lid wraps the ball
    instead of lying flat; then the same on the lower lid [02:04:15]; last, `Crease Polish` the edge where lid
    meets face [02:04:55]. Live: rim `{"brush":"crease","subtract":true,...,"radius":0.015*H,"strength":0.4}` along
    the lid path; `flatten` on the lid underside with radius `0.03*H`; `grab` the inner and outer corners by
    `+0.02*H` in Y; transition edge `{"brush":"crease",...,"radius":0.025*H,"strength":0.3}` one lid-thickness
    outside the rim. Look from `TOP` and three-quarter: lid ends must curve back round the ball.

14. **Second nose pass, brows, chin** [02:05:30]. With eyes in, the course sees its nose is too big: `Grab` it
    smaller and narrower from the front, give the bridge a concave curve into the forehead in profile, pull the
    wings out, `Crease Polish` round each nostril wing, round the underside, Smooth [02:05:37 to 02:06:42]. Then
    the brow shape gets a `Crease Polish` pass to the concept's brow arc and the chin a crease plus `Grab`
    [02:06:42 to 02:07:22].

15. **Mouth mound first** [02:07:35]. The mouth area is flat until you add the teeth volume. Course: broad
    `Clay Strips` over the whole muzzle between nose base and chin, Smooth, check in profile and front. Live:
    `{"brush":"clay_strips","points":[face_pt(-0.1*W..0.1*W, lip_bottom + 0.06*H)],"radius":0.1*H,"strength":0.5,"snap":true}`, then `smooth`.

16. **Mouth corners, line, lips** [02:08:26]. Course order: (a) mark each corner with `Crease Polish`, no wider
    than the eye centre; (b) `Grab` the corners backward so the mouth wraps [02:09:10]; (c) `Crease Polish` a line
    from each corner to the middle [02:09:28]; (d) if the whole mouth is too high or low, move it with `Grab` now
    [02:09:55]; (e) upper lip: `Crease Polish` its upper border, `Grab` it forward so it overhangs the lower lip
    [02:10:10]; (f) lower lip: `Inflate` just under the line, Smooth the corners, `Crease Polish` the groove under
    the lip [02:10:52]. Live for (c):
    `{"brush":"crease","points":[face_pt(0, mz), face_pt(ex*0.5, mz), face_pt(ex*0.9, mz)],"radius":0.02*H,"strength":0.5,"snap":true}`
    with `mz` about `lip_bottom + 0.05*H` (mine; the stated rule only fixes the lip bottom). For (f):
    `{"brush":"inflate","points":[face_pt(0, mz-0.03*H), face_pt(ex*0.4, mz-0.025*H)],"radius":0.04*H,"strength":0.4}`.

17. **Whole-face pass** [02:11:40]. Eyes, nose and mouth now exist, so judge them together against the concept:
    jaw shape and length with `Grab`, cheek mass with `Clay Strips` plus Smooth, lip corners up or down.

18. **Finer remesh and sharpen** [02:12:44]. The voxel-size preview reaches `0.0128 m`; the preview alone
    does not prove the final applied value. After remeshing, the course uses `Crease Polish` again on the mouth
    line and corners, rounds the nostrils, uses subtractive `Draw` to dig the nostril holes and marks the wing;
    then fills the old eye-line groove on the forehead side with `Clay Strips` and Smooth, since it was only a guide
    [02:14:15]. Live: `sculpt_remesh(object="BLK_head", voxel_size=H/165)`; repeat the step 13 and 16 creases at
    two-thirds of their earlier radius.

19. **Iris colour, then lids again** [02:14:35]. A dark iris tells you where the character looks and exposes lid
    errors. Course: select the pole vertex of the eyeball, grow the selection, paint those faces dark in Vertex
    Paint, set viewport shading colour to `Attribute`, rotate the eyeballs to aim them, then refine the lid edges
    [02:15:40]. Live (4.5 calls the shading option `VERTEX`):

    ```python
    # verified in 4.5.16 background (the shading line needs a 3D viewport, so it is: not verified)
    col = eye.data.color_attributes.new("Col", "FLOAT_COLOR", "POINT"); mw = eye.matrix_world
    front = min((mw @ v.co).y for v in eye.data.vertices); r = eye.dimensions.x / 2
    for v in eye.data.vertices:
        col.data[v.index].color = (0.02, 0.02, 0.02, 1) if (mw @ v.co).y < front + r * 0.25 else (0.9, 0.9, 0.9, 1)
    # for a in C.screen.areas: if a.type == "VIEW_3D": a.spaces.active.shading.color_type = "VERTEX"
    ```

20. **Placeholder brows and lashes** [02:16:49]. They are stand-ins to judge the face; real hair replaces them in
    the hair stage. Course: a plane turned upright, with face-project snapping on, extruded along the brow line as
    a thin strip; `Mirror` (object = head) and `Solidify` (`Thickness` -0.01 m, `Offset` -1.0); Shade Smooth;
    vertex colour dark grey, value about 0.25, not black, so the form still shades [02:18:37]. Lashes: a second
    strip in the same object following the upper lid rim, normals recalculated [02:19:25]. Live:

    ```python
    # verified in 4.5.16 background
    def surface_strip(name, head, path, width, thickness=0.01):
        bvh = BVHTree.FromObject(head, C.evaluated_depsgraph_get()); inv = head.matrix_world.inverted(); mw = head.matrix_world
        verts = []
        for p in path:
            for dz in (-width / 2, width / 2):
                loc, nor, _, _ = bvh.find_nearest(inv @ (Vector(p) + Vector((0, 0, dz))))
                verts.append(tuple(mw @ (loc + nor * 0.002)))
        me = D.meshes.new(name); me.from_pydata(verts, [], [(2*i, 2*i+2, 2*i+3, 2*i+1) for i in range(len(path) - 1)])
        ob = D.objects.new(name, me); C.scene.collection.objects.link(ob)
        ob.modifiers.new("Mirror", "MIRROR").mirror_object = head
        s = ob.modifiers.new("Solidify", "SOLIDIFY"); s.thickness = -thickness; s.offset = -1.0
        ca = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        for d in ca.data: d.color = (0.25, 0.25, 0.25, 1)
        return ob
    ```
    Scale `thickness` to your head: the course's -0.01 is on a head roughly 2 units tall (see Gaps).

21. **Ears** [02:20:47]. In the course the ear stays a separate object through this chapter. Order: Smooth the ear
    blockout and place it between brow line and nose base; remesh at `0.02`, Smooth [02:21:19]; mask a bean-shaped
    bowl on the outer face only (`Lasso Mask` with `Front Faces Only` so the back of the ear is not caught)
    [02:21:46]; invert the mask; `Grab` with a very large radius to push the bowl inward and slightly down
    [02:22:50]; clear the mask, remesh, Smooth; `Crease Polish` the inner edge of the rim (the question mark) and
    sharpen the rim's outer edge [02:23:17]; `Clay Strips` two short ridges for the two arms of the Y, Smooth, then
    crease beside them [02:24:30]; remesh finer, Smooth, final crease pass [02:25:25]. Live:

    ```python
    # verified in 4.5.16 background (mask_where from the helper block; ear on the +X side)
    c = Vector(ear_center); rx, rz = 0.25 * ear_w, 0.3 * ear_h              # bowl size: my starting values
    mask_where(ear, lambda p, n: not (n.x > 0.3 and ((p.y - c.y) / rx) ** 2 + ((p.z - c.z) / rz) ** 2 < 1))
    ```
    This masks everything except the outward-facing bowl (the mask-then-invert of the course in one step). Then
    `{"brush":"grab","points":[ear_center, ear_center moved -0.3*ear_depth in X],"radius":ear_h,"strength":1.0}`,
    `sculpt_mask(object="BLK_ears", op="clear")`, `sculpt_remesh`, `smooth`. If the ear is mirrored by a modifier, use
    `symmetry=""` and sculpt the real side only.

22. **Final comparison** [02:26:21]. Course: study the concept against the sculpt feature by feature, and come
    back after a break because fresh eyes find errors. For you: run the exit check, then run it again after the
    next stage and fix what the second look shows.

## How the artist works on screen

The artist keeps a small whole-head view and a reference board beside a larger working viewport.
The large view is frequently orbited and zoomed; a screenshot does not establish every stroke direction
or number of passes. The pixel radii below are examples at the displayed zoom, not world distances.
The following world-space radii are starting recommendations, not conversions of those pixels.
Use the existing `face_pt` and `flatten` helpers; surface coordinates must be measured on your own mesh.
`H` and `W` are the measured head dimensions, and +Y points into the face.
The artist commonly holds Shift to smooth without permanently switching brushes, resizes the
brush between passes, and uses X-ray while adjusting the nose
[qy-wwP-b9HY-04-015632, 01:56:45]. The reader's strokes are world-space operations,
not interactive brush emulations; inspect `moved_verts` and recheck after short batches.

**1 — Resolve the large masses.** The artist looks at the coarse head from front and profile,
then sketches the cranium and jaw relationship on the side before smoothing the remesh
[qy-wwP-b9HY-04-015005, 01:50:05]. In the working viewport the head is isolated for close work,
while the small view keeps the neck and ears visible. Reader: remesh at `H/50`, then use
`sculpt_strokes` with broad `smooth` paths and radius about `0.3*H`; inspect the profile again.

**2 — Separate jaw and cranium.** The artist rotates down and around the isolated head to inspect
the break behind the jaw; Crease Polish is selected before returning to a frontal view
[qy-wwP-b9HY-04-015117, 01:51:17]. Reader: use a short `crease` path on the jaw side,
radius `0.05*H`, and look from the side; do not cut a line across the back of the skull.

**3 — Establish the eye band.** Front orthographic makes the halfway height easy to judge;
the artist draws a wide, shallow band before checking its depth obliquely
[qy-wwP-b9HY-04-015117, 01:51:28; qy-wwP-b9HY-04-015157, 01:51:57].
Reader: `crease` from the center toward the temple, radius `0.06*H`, then `grab`
the eye plane toward +Y with a `0.2*H` radius; compare front and profile.

**4 — Make the brow shelf.** The artist softens the transition above the band and marks the
next horizontal boundary, checking the reference rather than treating the mark as an eyebrow
[qy-wwP-b9HY-04-015237, 01:52:37; qy-wwP-b9HY-04-015339, 01:53:39].
Reader: `smooth` around the measured brow height, then a `crease` with radius `0.04*H`.

**5 — Flatten the temple.** In a close oblique view, Scrape/Fill moves over the side of the
cranium, not over the entire eye band; the artist changes the brush size while working.
The panel shows strength `0.700`; a later frame shows size `188 px`
[qy-wwP-b9HY-04-015405, 01:54:12]. Reader: `flatten` each temple separately at
radius `0.25*H`; it is a fitted-plane approximation, not Blender's dragged brush.

**6 — Define cheek and chin planes.** The artist keeps the cheek side broad and uses a short
mark at the chin rather than dividing the lower face into many small facets
[qy-wwP-b9HY-04-015429, 01:54:29; qy-wwP-b9HY-04-015452, 01:54:52].
Reader: `flatten` both cheek sides at `0.25*H`, then make a small central `crease`;
capture the head in front and three-quarter views.

**7 — Compare the blockout.** The front view and the reference board remain visible together
as the artist checks width and profile before introducing the next object
[qy-wwP-b9HY-04-015535, 01:55:35]. Reader: use `turnaround_sheet` and make a
large-radius `grab` only where the actual reference shows a mismatch.

**8 — Shape the separate nose.** After placing a round block, the artist enables X symmetry
in Sculpt Mode, views it from the front and side, and pulls the block into the face with Grab.
The nose develops a tapered upper end and a rounder lower end
[qy-wwP-b9HY-04-015632, 01:56:32]. Grab strength `0.400` is visible; size changes
with zoom. Reader: parent `BLK_nose` to `CHARACTER`, use `grab` with world-space paths
relative to `H`, and use a small subtractive `draw` under the tip for nostrils.

**9 — Fuse and blend.** The separate nose and head become one remeshed surface; the artist
works the bridge and its sides back into the brow, then softens the join
[qy-wwP-b9HY-04-015758, 01:57:58; qy-wwP-b9HY-04-015839, 01:58:39].
Reader: `join_and_fuse` at `H/65`, followed by short `clay_strips` paths from bridge
to brow, radius `0.05*H`, and `smooth`. Check `loose_parts` is one.

**10 — Place eyeballs.** The artist introduces a sphere and checks its position against the
head, then uses a mirror for the opposite eye
[qy-wwP-b9HY-04-015928, 01:59:28; qy-wwP-b9HY-04-020000, 02:00:00].
Reader: use `add_eyes`, parent `BLK_eye` to `CHARACTER`, and adjust the actual gap to
the design; compare front and side before committing to lid shapes.

**11 — Recess the eye region.** With the balls visible, the artist uses broad adjustments around
them rather than placing eyelids on a flat front plane
[qy-wwP-b9HY-04-020028, 02:00:28]. Reader: `grab` the surrounding head surface toward
+Y with radius about `0.12*H`; check that the ball remains visible from three-quarter view.

**12 — Build and reshape lids.** Draw adds an upper ridge against the sphere; a close-up then
shows a switch to Grab while the concept remains alongside the sculpt. The observed screen headers read
Draw at Size `94 px`, Strength `0.500` in Add mode, then Grab at Size `300 px` and `258 px`, Strength `0.400`
[qy-wwP-b9HY-04-020154, 02:01:54].
Reader: `draw` an arc at radius `0.03*H`, then `grab` its ends and peak to fit the reference.
Repeat below the ball, smoothing away excessive folds for a design that has little lid fold.

**13 — Give lids depth.** The working view turns around the ball while the artist works the
rim and transition, so the outer contour is judged from more than the frontal projection
[qy-wwP-b9HY-04-020332, 02:03:32; qy-wwP-b9HY-04-020400, 02:04:00].
Reader: a small `crease` or raised-edge approximation at `0.015*H`, `flatten` under
the lid, and `grab` the ends back toward +Y. Confirm the wrap from above and obliquely.

**14 — Revisit nose, brows and chin.** The artist adjusts the nose once the eyes exist and
checks its silhouette in profile, then moves attention to the brow and chin
[qy-wwP-b9HY-04-020537, 02:05:37; qy-wwP-b9HY-04-020656, 02:06:56].
Reader: use restrained `grab` moves with radii suited to each feature, then a small
`crease` around the wings; compare against the supplied concept after each change.

**15 — Build the mouth support.** Clay Strips adds a broad mound before any mouth slit.
The artist turns from profile to front to check its projection and width
[qy-wwP-b9HY-04-020819, 02:08:22]. Reader: `clay_strips` across the muzzle with
radius about `0.1*H`, then `smooth`; do not cut the mouth into a flat plane.

**16 — Locate corners before lips.** In front orthographic, the artist switches from Clay
Strips to a much smaller Crease Polish brush and locates the mouth corners first
[qy-wwP-b9HY-04-020819, 02:08:27; qy-wwP-b9HY-04-020839, 02:08:39].
After setting the line, the artist checks its curvature and builds upper and lower lip volume
[qy-wwP-b9HY-04-020942, 02:09:42; qy-wwP-b9HY-04-021052, 02:10:52].
Reader: `crease` at `0.02*H` for the line, `grab` corners toward +Y and `inflate`
under the line at `0.04*H`; the two sides should wrap the muzzle.

**17 — Judge the whole face.** The artist zooms out to compare the features together and
returns to broad silhouette and cheek adjustments
[qy-wwP-b9HY-04-021127, 02:11:27; qy-wwP-b9HY-04-021218, 02:12:18].
Reader: use `turnaround_sheet`, then local `grab`, `clay_strips` and `smooth` strokes;
no single close-up is enough to judge the head.

**18 — Refine at finer density.** The artist remeshes again and sharpens features only after
the broad forms are established, cleaning nostrils and old construction lines
[qy-wwP-b9HY-04-021244, 02:12:44; qy-wwP-b9HY-04-021405, 02:14:05].
Reader: `sculpt_remesh` at `H/165`, then use smaller `crease` and subtractive `draw`
paths; smooth only the construction groove, not the intended lid or lip boundary.

**19 — Use iris contrast to judge gaze.** A dark patch on the eye makes its aiming and the
lid opening easier to compare; the artist returns to the lids after the eye treatment
[qy-wwP-b9HY-04-021432, 02:14:32; qy-wwP-b9HY-04-021538, 02:15:38].
Reader: use the existing eye color-attribute block; the optional viewport color setting
requires a 3D viewport and is not verified by the background script.

**20 — Temporary brows and lashes.** A thin surfaced strip and its modifiers give a readable
brow, and a second strip follows the upper lid; the dark color is not treated as final hair
[qy-wwP-b9HY-04-021811, 02:18:11; qy-wwP-b9HY-04-021918, 02:19:18].
Reader: use `surface_strip`, parent the object to `CHARACTER`, and scale its world-unit
width and thickness to the head. Nearest-surface placement approximates face snapping.

**21 — Work the ear separately.** In the close ear view the first mask reaches the back;
the artist undoes it and enables Front Faces Only before drawing the bowl again
[qy-wwP-b9HY-04-022212, 02:22:12]. The inner patch is then isolated, pushed in,
and surrounded by a rim and internal raised branches
[qy-wwP-b9HY-04-022242, 02:22:42; qy-wwP-b9HY-04-022424, 02:24:24].
Reader: `mask_where` the complement of the outward bowl, `grab` in by a fraction of
ear depth, clear the mask, and use `crease` and `clay_strips` at ear-relative radii.
With a Mirror modifier sculpt only the real ear, not a second symmetric mesh stroke.

**22 — Compare again.** The artist steps back to review the face as a whole rather than
declaring success from the final ear close-up [qy-wwP-b9HY-04-022608, 02:26:08].
Reader: run the exit check: `outline_match` at `0.98` for real reference views only;
`not_run` is never a pass, and references must not be altered.


## Settings the course uses

| Setting | Value | Where | Timestamp |
|---|---|---|---|
| Voxel size, head planes | 0.04 to 0.05 | Sculpt Mode remesh (`R` to size, `Ctrl+R` to apply) | 01:50:18 |
| Voxel size after joining nose | 0.03 | same | 01:58:11 |
| Voxel size for eyelids | 0.02 | same | 02:01:21 |
| Voxel size for final face detail | preview 0.0128 m, applied value not established by that frame | same | 02:12:44 |
| Voxel size, ear detail | preview 0.00867 m, applied value not established by that frame | ear object | 02:25:14 |
| Symmetry | X on, for head and nose | Sculpt Mode header | 01:56:39 |
| `Grab` strength | 0.400 | brush panel | 01:50:36 |
| `Crease Polish` strength / pinch | 0.250 / 0.500 | brush panel | 01:51:20 |
| `Scrape/Fill` strength | 0.700 | brush panel | 01:54:14 |
| `Clay Strips` strength | 0.500 | brush panel | 01:58:52 |
| `Draw` strength | 0.500 | brush panel | 02:02:00 |
| Eyeball | UV sphere, rotated 90 degrees on X, Shade Smooth | Object Mode | 01:59:06 |
| `Mirror` on eyes, brows | axis X, `Mirror Object` = head | modifier | 02:00:00 |
| `Solidify` on brows/lashes | `Thickness` -0.01 m, `Offset` -1.0 | modifier | 02:18:14 |
| Brow/lash vertex colour | value about 0.25, not black | Vertex Paint | 02:18:37 |
| `Front Faces Only` | on, for the ear bowl mask | Lasso Mask tool settings | 02:22:18 |
| Viewport focal length | 150 (set in stage 02) so faces are not distorted | N panel, View | 00:34:05 |

## Mistakes the course warns about

- Eyes on a flat surface. Cut the eye line and push the sockets back before adding lids [01:44:49].
- Flat profile. Check the three equal side-depth units: eye corner, eye front, nose bridge, nose tip [01:39:48].
- Flat lids. Lid ends must curve back round the ball; lids radiate from the ball's centre [01:45:16].
- Cutting lips into a flat muzzle. Build the mound first [01:47:42].
- Mouth wider than the eye centres [01:42:18].
- Carrying the eye line round the back of the head; stop near the temple [01:52:00].
- Scraping the temple so far that the eye line is lost; re-cut it [01:54:16].
- Black brows: the form disappears. Use dark grey [02:18:40].
- Lasso mask catching the back of the ear when `Front Faces Only` is off [02:22:12].
- Over-detailing the planes; a simplified set is enough [01:55:48].
- Skipping the reference. Nose and ear shape vary too much to invent [01:47:10], [01:49:10].

## What changes for a different character

- General: the proportion table, the order (planes, nose block, eyeballs, sockets, lids, mouth mound, mouth,
  finer remesh, ears), remesh-then-smooth before each finer pass, and building lids against a real eyeball.
- Specific to the course character (a slim stylised young woman): wide-set eyes, a small nose with a concave
  bridge, almost no upper lid fold, wide cheeks, a pointed chin, thin brows. Read each of these off your concept.
- Stylised heads break the rules on purpose. Measure the concept first: if its eye line sits at 40% instead of
  50%, use 40% and keep the other rules relative to it. The course says the eye-spacing rule in particular varies
  with style [01:41:52].
- Creatures: keep the method (planes, then features as separate blocks joined and remeshed), drop the human
  ratios. A snout is the nose block and mouth mound made as one larger block; horns and crests are extra blocks,
  or `snake_hook` pulls after a remesh.
- Masks, helmets, hard-surface face parts: do not sculpt them into the head. Model them as separate objects in a
  later stage; sculpt only what the concept shows as skin.
- Closed or stylised dot eyes: still place the eyeball to shape the socket and lid, then hide it.
- Anime, manga and chibi heads with hard planes and flat-drawn eyes: replace steps 1 to 6 with
  `anime-clay-planes.md` (MRScapsule, 48 Shorts). The steps there:
  - planar cuts on a sphere;
  - brow and mouth steps while still faceted;
  - softening with `smooth` strokes;
  - a fused `nose_wedge`;
  - `almond_eye` (a flat recessed almond with a lid ledge) in place of the eyeball and wrapped lids.

  Use the eyeball route above only when the concept's eyes bulge in profile.

## Exit check

1. `mesh_report(object="BLK_head")`: `loose_parts` 1, `boundary_edges` 0, `non_manifold_edges` 0, `symmetry_error`
   below 0.002 (and report `symmetry_p95_error` and `symmetry_max_error` to catch local spikes) unless the concept is asymmetric (say so if it is). Any other result is failed.
2. Landmark numbers, from ray casts and bounds, each within `0.02*H` of the rule or of the concept's own measured
   ratio: eye centres on the eye line; nose base and brow on the thirds; lower-lip bottom at the halfway point;
   mouth corner X not beyond eye centre X; gap between eyeballs equal to one eye width; ear top and bottom inside
   brow line to nose base. Report each as a number with pass or fail.
3. `turnaround_sheet(object="CHARACTER", references={...})` with the eyes, brows and ears visible. Look at `LEFT`: the
   profile must show brow, eye, nose and lips at different depths. This is looking, not measuring.
4. `outline_match(object="CHARACTER", references={...}, threshold=0.98)` for each view that has a real reference
   picture. This is the stage result. A view below 0.98 is failed: fix with `grab` where the overlay is red (model
   missing) or blue (model extra) and measure again. A view with no reference picture is `not_run`; report it as
   "looked at, not measured", never as passed. While the head is bald and the concept has hair, the head's part of
   the outline cannot match; say that is why the number is short, and do not paint the hair out of the reference
   (a changed picture is no longer the reference). A head-only `outline_match(object="BLK_head", ...)` against a
   head crop of a real picture is allowed as a diagnostic, never as the stage result.
5. Save with `save_file` under a new numbered name (the course saves incrementally).

## Low-poly game route (second course: Nhij Quang, Girl#01)

Second source: Nhij Quang, [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), Blender 4.2.1 LTS, 1 h 15 min, no narration (music only). Everything here was read off the screen: the key-cast overlay, redo panels, modifier panels and status-bar counts, from 157 study sheets; labels are in `annotations/mlnR-Eyazh0/`. Times marked `NQ` point into that video, not the main course. Use this route instead of the sculpt route when the job is a low-poly game character (box/poly modelled, hand-painted, Mixamo-rigged); see "Two routes" in `SKILL.md`. Values that could not be read are listed as not visible, never guessed. Python blocks marked `# not run in Blender` were not executed.

Source: Nhij Quang, "Blender 3D Quick Modeling Character For Game - Girl#01", chapter 9 "Head Modeling", 00:33:20 to 00:42:03 (18 clips). Nothing is sculpted. The head is box/poly-modelled strip by strip over the turnaround sheet, using a half mesh with a Mirror modifier. Each step below lists what the frames show.

### Order of work

1. [NQ 00:33:20 to 00:33:30] Start from an empty mesh object (Cube.007, status bar Verts 0/0) in Edit Mode. Add a Mirror modifier: Axis X, Clipping on, Merge on at 0.001 m. Result: a half-object setup. How the empty mesh was made is not shown.
2. [NQ 00:33:30 to 00:33:52] Switch to Right Orthographic over the side reference. Build a vertex chain along the face profile (brow, nose, mouth, chin), about 6 vertices (Verts 6/6, Edges 5/5). Extrude the chain sideways into a first column of quads and drag each vertex onto the drawing (G x5, Move Y -0.00871 m). Result: 13 verts, 3 faces.
3. [NQ 00:33:52 to 00:34:14] Switch to Front Orthographic and slide the vertices in X so the strips follow the front outline: a centre column, a band across the eyes, and a jaw line down to the chin. Check from Top Orthographic, where the patch should read as a shallow V (face curves back). Result: 28 verts, 16 faces (status Tris 32).
4. [NQ 00:34:14 to 00:34:36] Refine the eye-region quads in side view (Move X 0.009073, Y -0.008065 m) and even out the spacing with Vertex Slide (G G, value 0.0495). Layout: the rows around the eye are horizontal bands that follow the brow, eye and cheek lines on the reference. There are no proper radial loops around the eye yet. Result: 33 verts, 20 faces.
5. [NQ 00:34:36 to 00:34:58] In Object Mode run Shade Smooth with Keep Sharp Edges on to read the forms (59 verts, 40 faces, 80 tris with the mirror). Back in Edit Mode, pull the centre faces under the eyes forward into a small wedge nose.
6. [NQ 00:34:58 to 00:35:19] Extrude the centre strip down from the nose to the chin. Scale the mouth row (0.8665 uniform), extrude the mouth-row edge out to the mouth corner, and merge stray vertices (M). Result: 58 verts, 38 faces.
7. [NQ 00:35:19 to 00:35:48] Bevel the mouth edges: Affect Edges, Width Type Offset, Width 0.0178 m, Segments 1, Shape 0.5, Loop Slide on, Miter Outer/Inner Sharp, Intersection Grid Fill, Profile Superellipse. Then move the ring vertices onto the drawn lip line (Move X 0.002674, Z 0.000243 m). Result: one edge ring around a shallow mouth slit. The mouth is geometry, but only a slit or crease, not an open mouth with an interior. 64 verts, 45 faces.
8. [NQ 00:35:48 to 00:36:03] Fill the holes between the mouth ring, cheek and jaw with Make Face (F), switching between edge and vertex select (keys 2, X, 1, F x2). Result: 75 verts, 59 faces.
9. [NQ 00:36:03 to 00:36:17] Extrude the top edge of the face up over the forehead, then rotate and move it in side view (Move Y 0.005544, Z 0.002016 m). Result: 85 verts, 68 faces.
10. [NQ 00:36:17 to 00:37:01] Extrude the side boundary of the face backward as a wide strip and keep adding rows until the skull and back of the head are closed (Move Y -0.001815/-0.003388, Z -0.008448 m). Result: closed half head shell, 123 verts, 101 faces (201 tris).
11. [NQ 00:37:01 to 00:38:21] Join the head into the body object "Cube" (inferred from the frames: the outliner loses Cube.007 and the object count goes from 1/10 to 1/9). On the neck, add a Loop Cut (1 cut, Smoothness 0, Falloff Inverse Square, Factor 0, Clamp on, Correct UVs on). Bridge head and neck by filling faces one patch at a time (F). Use the Knife (K) and Connect Vertex Path (J) where vertex counts differ, and undo once (Ctrl+Z). Result: head and body are one mirrored mesh. Edit-mode half count about 663 verts / 655 faces. Scene total 3,209 verts / 3,066 faces / 5,894 tris.
12. [NQ 00:38:21 to 00:38:57] Ear: select 2 faces on the side of the head and use Extrude Region and Move along the Normal (0.035349 m). Shape the block into a pointed ear (Move Z 0.007778, X -0.004305 m). The ear is part of the head mesh. Result: about 675 verts.
13. [NQ 00:38:57 to 00:40:39] Eyes. Turn on see-through (Z pie) in Front Orthographic and slide the vertices around the eye onto the drawn eye outline (Vertex Slide factor 0.527, Clamp on, Correct UVs on). Then:
    - Open the eye area into a hole (the reference shows through) and shape the opening.
    - Cap it again with faces, add a loop cut and scale (header Scale 2.0161).
    - Pick the inner ring with Ctrl-click shortest path and scale it to 0.51 uniform. This makes an iris ring with a centre fan.
    - Select the eye patch (Select Linked; Seam looks highlighted in Delimit) and Alt-loop-select the ring. Push it back into the head (Move Y 0.002605 m) so the eye sits recessed inside a rim.
    The eye is an oval recessed patch with concentric rings, made in geometry. No separate eyeball sphere is seen. Iris colour presumably comes from the painted texture later (not shown in this chapter). Result: about 771 verts / 752 faces.
14. [NQ 00:40:39 to 00:41:08] Upper lid/lash: Shift+Alt loop-select the upper eyelid edge and extrude it outward and forward into a thick overhanging flap. Check it in side view and wireframe. Result: about 808 verts / 784 faces.
15. [NQ 00:41:08 to 00:42:03] Eyebrow: in see-through front view, extrude vertices along the drawn brow (E x3). Select the brow faces with Select Linked, extend with Ctrl-click extrude to cursor, and move them forward off the forehead (Move Y 0.002434, then 0.009789 m) into a raised brow block. There is one more small extrusion and crease near the eye whose purpose cannot be read. End of chapter: 854 verts / 822 faces / 1,581 tris on the body+head half.

### How it looks on screen

- Layout workspace. The image editor on the left holds the turnaround sheet. A copy of the sheet is also placed in the viewport behind the model; the outliner shows Empty and Empty.001, so these are probably image empties.
- Most edits happen in Right Orthographic or Front Orthographic over the reference. Top Orthographic is used to check depth, and User Orthographic for 3/4 checks.
- The Mirror modifier stays on the whole time (X, Clipping, Merge 0.001 m), and "Mirror Editing" shows checked in the Move redo panels.
- Solid shading. See-through/X-ray (Z pie) is turned on when fitting the eye and brow over the front drawing.
- Work is vertex by vertex: G, G G (vertex slide), E, F, M, J, K, Ctrl+R. No sculpt brushes, no Subdivision Surface, no Shrinkwrap.
- The status bar counts rise slowly: about 120 verts for the half head shell before joining to the body.

### Python route

```python
# not run in Blender
import bpy, bmesh
from mathutils import Vector

# Step 1: empty half-mesh with Mirror X
me = bpy.data.meshes.new("Head"); ob = bpy.data.objects.new("Head", me)
bpy.context.collection.objects.link(ob)
m = ob.modifiers.new("Mirror", 'MIRROR')
m.use_axis[0] = True; m.use_clip = True
m.use_mirror_merge = True; m.merge_threshold = 0.001
```

```python
# not run in Blender
# Step 2-3: profile chain on x=0 (y,z read from the side reference), then extrude strips outward
bm = bmesh.new()
profile = [(0.0, -0.08, 1.80), (0.0, -0.09, 1.76), (0.0, -0.10, 1.73), (0.0, -0.09, 1.70), (0.0, -0.07, 1.67)]  # placeholder coords
vs = [bm.verts.new(p) for p in profile]
edges = [bm.edges.new((vs[i], vs[i+1])) for i in range(len(vs)-1)]
ret = bmesh.ops.extrude_edge_only(bm, edges=edges)
new_verts = [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=new_verts, vec=Vector((0.02, 0.01, 0.0)))
# then set each new vert's x from the front reference, y from side
bm.to_mesh(ob.data); bm.free()
```

```python
# not run in Blender
# Step 7: bevel the mouth edges (edit mode, mouth edges selected)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.bevel(offset_type='OFFSET', offset=0.0178, segments=1, profile=0.5,
                   affect='EDGES', loop_slide=True, miter_outer='SHARP', miter_inner='SHARP')
```

```python
# not run in Blender
# Step 8/11: fill a gap or bridge head to neck from selected border verts
bm = bmesh.from_edit_mesh(ob.data)
sel = [v for v in bm.verts if v.select]
bmesh.ops.contextual_create(bm, geom=sel)          # like F
bmesh.update_edit_mesh(ob.data)
# join head into body (object mode): body active, both selected
# bpy.ops.object.join()
```

```python
# not run in Blender
# Step 12: ear = extrude 2 side faces along their normal by 0.035
bm = bmesh.from_edit_mesh(ob.data)
faces = [f for f in bm.faces if f.select]
n = sum((f.normal for f in faces), Vector()).normalized()
ret = bmesh.ops.extrude_face_region(bm, geom=faces)
verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=verts, vec=n * 0.035349)
bmesh.update_edit_mesh(ob.data)
```

```python
# not run in Blender
# Step 13: iris ring = inset the eye cap, scale ring 0.51, push patch into head
bm = bmesh.from_edit_mesh(ob.data)
eye_faces = [f for f in bm.faces if f.select]
bmesh.ops.inset_region(bm, faces=eye_faces, thickness=0.002, depth=0.0)
ring = list({v for f in eye_faces for v in f.verts})
c = sum((v.co for v in ring), Vector()) / len(ring)
from mathutils import Matrix
bmesh.ops.scale(bm, vec=Vector((0.51, 0.51, 0.51)), space=Matrix.Translation(-c), verts=ring)
bmesh.ops.translate(bm, verts=ring, vec=Vector((0, 0.002605, 0)))  # +Y = into head when face looks -Y
bmesh.update_edit_mesh(ob.data)
```

```python
# not run in Blender
# Step 14/15: lash flap / brow = extrude an edge loop or face strip and move it forward
bm = bmesh.from_edit_mesh(ob.data)
lid = [e for e in bm.edges if e.select]
ret = bmesh.ops.extrude_edge_only(bm, edges=lid)
bmesh.ops.translate(bm, verts=[g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)],
                    vec=Vector((0, -0.004, 0.001)))
bmesh.update_edit_mesh(ob.data)
```

### Settings read on screen

- Mirror modifier: Axis X, Bisect off, Clipping on, Merge on, 0.001 m. Same on the body "Cube" after joining.
- Move redo values: Y -0.00871; Y 0.004839 / Z -0.002419; X 0.009073 / Y -0.008065; X -0.00175; Y -0.000506; X 0.002674 / Z 0.000243; Y 0.005544 / Z 0.002016; Y -0.001815 / Z -0.008448; Y -0.003388; X 0.002446; Z 0.007778; X -0.004305; X 0.002188 / Z 0.001702; Y 0.001167 / Z -0.001458; X -0.000141 / Z 0.001829; Y 0.002605; X -0.000405 / Z 0.000405; Y -0.000828; Y 0.002434; Y 0.009789; Y 0.001937 (all m).
- Vertex Slide 0.0495 (header). Vertex Slide Factor 0.527, Even off, Flipped off, Clamp on, Mirror Editing on, Correct UVs on.
- Scale 0.8665 uniform (mouth row). Scale 0.510 uniform (iris ring). Header Scale X 2.0161 (eye cap).
- Shade Smooth: Keep Sharp Edges on.
- Bevel: Affect Edges, Width Type Offset, Width 0.0178 m, Segments 1, Shape 0.500, Material Index -1, Harden Normals off, Clamp Overlap off, Loop Slide on, Mark Seams off, Mark Sharp off, Miter Outer Sharp, Inner Sharp, Intersection Type Grid Fill, Face Strength None, Profile Type Superellipse.
- Loop Cut and Slide: Number of Cuts 1, Smoothness 0.000, Falloff Inverse Square, Factor 0.000, Even off, Flipped off, Clamp on, Mirror Editing off, Correct UVs on.
- Extrude Region and Move (ear): Orientation Normal, Move Z 0.035349.
- Select Linked: Deselect off; Delimit list Normal/Material/Seam/Sharp/UVs, with Seam looking highlighted (low confidence).
- Units switch between Centimeters and Millimeters in the viewport overlay (grid scale display).
- Counts: half head shell 123 verts / 101 faces / 201 tris. After joining with the body, chapter end 854 verts / 822 faces / 1,581 tris (edit mode). Scene object-mode totals: 3,209 verts / 3,066 faces / 5,894 tris at 00:38:21.

### Not visible in the frames

- How the empty Cube.007 was created (delete-all on a cube, or a merged single vertex).
- Exact keystrokes between frames (the 7-second gaps hide many single-vertex moves). The order inside each step is inferred.
- Whether the head was joined with Ctrl+J. Only the outliner and object-count change are seen.
- Whether the eye hole was made with Delete Faces or Dissolve.
- Whether the eye/iris colour, pupil and lashes come from texture. Painting is not in these chapters.
- No mouth interior, teeth or tongue are seen; nothing indicates any.
- The purpose of the small extrusion near the eye at 00:41:52 to 00:41:59.
- The image empties' settings (opacity, depth). The sheet appears semi-transparent behind the mesh, but no values are visible.

## Gaps

- **Add-ons**: `Extra Mesh Objects` (free, from Blender's extensions list) supplies the round cube used for the
  nose block; the built-in route is `quad_ball` in the helpers above. `PureRef` (separate reference-board
  program, pay-what-you-want) holds the references; the route here is `reference_setup` and `turnaround_sheet`.
- **Scrape/Fill** has no `sculpt_strokes` brush. `flatten` above fits one plane per call; it does not follow a
  dragged path and has no symmetry, so call it once per side.
- **Lasso Mask** is replaced by a rule on position and normal. Free-form outlines need a rule you write yourself.
- **Crease direction**: the brush panel shows `Crease Polish` set to `Subtract` in every frame checked, and the
  narrator also holds Ctrl for some strokes. Whether a given stroke cut a groove or raised an edge was judged from
  the resulting shape in the video, not from a setting.
- **Brush sizes** in the video are screen pixels and depend on zoom. The radii given against `H` are mine.
- **Scene scale**: the course never states the head size. Its voxel sizes fit a head about 2 units tall (the
  round cube's default size), which is how the `H/50` to `H/165` ratios were derived. If your head is a different
  size, use the ratios, not the course's numbers.
- **Face-project snapping** for the brow strip is replaced by nearest-surface placement in `surface_strip`.
