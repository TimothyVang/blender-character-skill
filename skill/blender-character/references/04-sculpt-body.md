# 04 Sculpt the body, hands and feet

Course source: chapter 05 "Sculpting the Body of Your Character", 02:28:05 to 04:15:04.
(The course records in Blender 5.0.1; everything below was checked against 4.5.16.)

## Goal

Hands with five shaped fingers and feet with five toes exist as fused meshes. Legs, torso and arms have been
remeshed, shaped to the concept, joined into a few larger meshes and blended at the joints, with knees, elbows, rib
cage, spine curve and (if the character has them) breasts indicated. The whole figure's outline matches the concept
in each view that has a reference picture.

## Starting state

- Stage 03 finished: head with face, neck, ears.
- From stage 02: separate blockout meshes for chest, waist, pelvis, shoulder, upper arm, lower arm, upper leg,
  lower leg, and simple placeholder blocks for hand and foot. Limb parts carry a `Mirror` modifier; centre parts
  use X symmetry. The parts are the `BLK_` objects of stage 02 (`BLK_upper_leg`, `BLK_torso_mid`, ...), all parented to
  `CHARACTER`. This stage replaces `BLK_hand` and `BLK_foot` with real ones and joins the other parts into
  `BLK_leg`, `BLK_torso` and `BLK_arm` (step 20).
- A neutral A-pose: arms out and down at roughly 45 degrees, legs straight, feet flat. The course's concept drawing
  is a relaxed standing pose, but the sculpt stays in this stiff pose throughout (frames at 03:49:14, 04:13:34) and
  the course asks for rhythm in the forms despite it [02:33:50]. Keep it for rigging whatever your concept shows.
- Extra reference pictures for torso, hands and feet. The course adds them before starting [02:40:00] and treats
  the reference as its anatomy guide [02:29:40].
- Helpers `surface_point`, `flatten`, `mask_where` from 03-sculpt-face.md. The brush mapping table there applies
  here unchanged (`Grab` 0.400, `Crease Polish` 0.250, `Scrape/Fill` 0.700, `Clay Strips` 0.500, `Draw` 0.500).

## Form rules the course states

| Part | Rule | Timestamp |
|---|---|---|
| Method | Do not work from memorised anatomy. Look at the reference, copy what you see onto the sculpt. | 02:28:55 |
| Arm | A chain of interlocking links: shoulder locks over upper arm, upper arm over forearm, forearm over wrist. Forms overlap, they do not butt end to end. | 02:30:23 |
| Upper leg | From the side: front curved, back straighter. | 02:31:35 |
| Lower leg | From the side: back curved (calf), front straighter. The opposite of the thigh, which gives rhythm. | 02:31:48 |
| Calf | "Angry face" seen from the front: the outer calf bulge sits higher than the inner one. | 02:32:14 |
| Ankle | Inner ankle bone higher than outer. Never on one horizontal line. | 02:32:51 |
| Torso | Varies most between characters: take it from the reference. Forms must flow into each other and feel balanced even in a stiff pose. | 02:33:20 |
| Silhouette | Zoom out and check the outline often; a clean outline means the forms work together. | 02:34:04 |
| Hand | Start with a box for the palm and a wedge on its side for the thumb base. | 02:34:31 |
| Palm | Not flat: arched across its width so the fingers fan out relaxed. | 02:35:12 |
| Knuckles | Lie on an arc, not a straight line. Each row of finger joints lies on a steeper arc than the row before. | 02:35:36 |
| Finger joints | Knuckle to tip = 1. First joint at 1/2. Second joint halfway between first joint and tip (3/4). | 02:36:14 |
| Finger profile | Three segments at three slightly different angles, a gentle arch. Never one straight tube. | 02:37:05 |
| Foot | A right-angled triangle from the front and from the side; a plain rectangle from below, sides then pushed in. | 02:37:46 |
| Arch | From the side the sole lifts in the middle. | 02:38:45 |
| Toes | Stepped on top (each joint a small step down), so they flow into the foot. | 02:39:05 |

## Helpers (paste into the `exec_python` call that uses them)

`quad_ball` and `join_and_fuse` are in 03-sculpt-face.md's helper block, with `surface_point`, `flatten` and
`mask_where`; paste that block too. Every new object gets `ob.parent = D.objects["CHARACTER"]`.

```python
# verified in 4.5.16 background
import bpy, bmesh
from mathutils import Vector
C, D = bpy.context, bpy.data

def skin_digit(name, points, radii, subsurf=2):                    # finger or toe: edge chain + Skin + Subdivision
    me = D.meshes.new(name)                                        # points are LOCAL; first point (0,0,0) = knuckle
    me.from_pydata([tuple(p) for p in points], [(i, i + 1) for i in range(len(points) - 1)], [])
    ob = D.objects.new(name, me); C.scene.collection.objects.link(ob)
    ob.modifiers.new("Skin", "SKIN")
    sub = ob.modifiers.new("Subdivision", "SUBSURF"); sub.levels = sub.render_levels = subsurf
    for sv, r in zip(me.skin_vertices[0].data, radii): sv.radius = (r, r)
    me.skin_vertices[0].data[0].use_root = True; return ob

def bake_modifiers_linked(objs):                                   # "Visual Geometry to Mesh", data stays shared
    baked = D.meshes.new_from_object(objs[0].evaluated_get(C.evaluated_depsgraph_get()))
    for o in objs: o.modifiers.clear(); o.data = baked
    return baked

def plane_squash(ob, plane_co, plane_no):                          # stand-in for Line Project: flatten one side
    me = ob.data; co_l = ob.matrix_world.inverted() @ Vector(plane_co)
    no_l = (ob.matrix_world.to_3x3().transposed() @ Vector(plane_no)).normalized(); moved = 0
    for v in me.vertices:
        d = (v.co - co_l).dot(no_l)
        if d > 0: v.co -= no_l * d; moved += 1
    me.update(); return moved
```

`join_and_fuse` bakes a `Mirror` modifier into real geometry on both sides. If you want to keep working on one
side only (as the course does), remove the modifier from the list's objects first, join, and add `Mirror` back.
Linked duplicates (`ob.copy()` shares mesh data) survive `sculpt_remesh` and `sculpt_strokes`: a stroke on one
finger changes all of them, which is what the course uses them for.

## Order of work

The course's order is hands, feet, then body [02:40:30]. Sizes are given against `L` = length of the part being
worked (palm length, foot length, limb length).

### A. Hand

1. **Palm box** [02:40:38]. Course: a cube, in Edit Mode moved to the end of the forearm, rotated to the arm's
   direction, flattened, the wrist end scaled narrower. Hide the stage 02 hand placeholder (`BLK_hand`; rename it
   `BLK_hand_old`). Live: `quad_ball("BLK_hand", ...)` (03's helpers), parented to `CHARACTER`, or a
   cube via bpy, scaled about `(1.0, 0.85, 0.3) * palm_length` (mine), rotated to the forearm's direction.
2. **Arch the palm** [02:41:55]. Course: loop cuts along the length; raise the middle ones so the back of the hand
   is convex across its width. Live: one `grab` on the back of the palm, radius `0.6*L`, moved `0.08*L` along the
   back's normal; or move the middle rows in bmesh.
3. **Thumb wedge** [02:42:30]. Course: extrude the side faces near the wrist outward and shape them into a wedge
   pointing forward and down; slide loops to relax it; later drop two edges to hint the fleshy pad at the thumb
   base [02:46:29]. Live: `{"brush":"snake_hook","points":[side of palm near wrist, +0.35*L sideways and forward],"radius":0.3*L}`.
4. **Mirror and soften** [02:45:01]. Course: `Mirror` modifier, then `Subdivision` (viewport level 1), then `Grab`
   to thin and tidy. Check from front, side and above.
5. **One finger from one edge** [02:47:05]. Course: a cube merged to a single vertex at its origin, extruded along
   X; `Skin` modifier then `Subdivision` (levels 1, later 2); `Ctrl+A` in Edit Mode sets thickness. The first
   vertex never moves, so the object's origin stays at the knuckle and the finger rotates from the knuckle
   [02:48:45]. Live: `skin_digit("Finger_index", [(0,0,0),(0.5*f,0,0.03*f),(0.75*f,0,0),(f,0,-0.06*f)], [0.09*f,0.085*f,0.08*f,0.06*f])`
   where `f` = finger length. The extra points at 1/2 and 3/4 are the joints; their small Z offsets give the
   arched profile, and the smaller last radius narrows the tip [02:51:55].
6. **Place, then linked-duplicate** [02:49:15]. Course: position in Object Mode only (index finger first), then
   `Alt+D` three times so the four fingers share one mesh. Scale and rotate each object: little finger shortest,
   then ring, middle longest, index between; fan them slightly; raise the middle ones so the knuckles follow the
   palm's arc; leave a clear gap between neighbours [02:51:01]. Live: `dup = finger.copy()` (shares data), link
   it, set `location`, `rotation_euler`, `scale`.
7. **Thumb with its own data** [02:53:25]. Course: `Shift+D` (not linked), rotated to sit in the wedge, shortened,
   one joint dissolved, fattened, radii alternated in and out along its length. Reshape the palm wedge to meet it.
   Live: `skin_digit` again with three points and larger radii.
8. **Palm meets fingers** [02:56:25]. Course: apply the palm's `Subdivision`; `Grab` the palm toward the thumb and
   finger bases; `Inflate` then Smooth the two fleshy pads on the palm side; nudge the forearm end to meet the
   wrist; scale all fingers up a touch about their own origins if they look thin [02:57:44].
9. **Bake the digits, sculpt one for all** [02:58:18]. Course: applying modifiers fails on linked data, so select
   the fingers and use Object > Apply > `Visual Geometry to Mesh`; they stay linked. Sculpt one finger with
   symmetry across its width (Y for the course's finger): `Grab` the tip out, taper the sides [02:59:14]. Live:
   `bake_modifiers_linked([f1, f2, f3, f4])`, `sculpt_begin(object="Finger_index", symmetry="Y")`.
10. **Joint creases and nail bed** [03:00:14]. Course: on the underside, `Crease Polish` with a small radius at
    1/2 and at 3/4 of the length, carried a little up the sides; keep them faint [03:01:10]. `Scrape/Fill` the top
    of the last segment flat for the nail bed [03:01:24]. On top, short creases at the same two joints [03:01:58].
    Live: `{"brush":"crease","points":[underside point at 0.5*f, slightly left and right of it],"radius":0.06*f,"strength":0.25,"snap":true}`;
    `flatten(finger, top point at 0.88*f, 0.12*f, 0.7)`. Do the thumb the same way but with `symmetry=""`: its
    symmetry plane does not line up, so match both sides by hand [03:03:14].
11. **Remesh parts separately** [03:05:50]. Course: palm at `0.025`, Smooth; then copy the reference's palm
    lines with `Crease Polish`, build the pads with `Clay Strips`, flatten the back of the hand with `Scrape/Fill`
    [03:06:55 to 03:09:12]. Fingers at `0.01`, a light Smooth that keeps the forms, faint joint creases again,
    `Clay Strips` on the underside between creases for finger pads [03:09:21 to 03:10:45]. Thumb at `0.01`.
    Nails are optional: crease the outline, sharpen it, keep the nail flat [03:11:09].
12. **Join and fuse** [03:13:54]. Be satisfied with each finger first: after joining, every finger must be
    sculpted separately [03:14:49]. Course: select fingers and thumb, palm active, `Ctrl+J`, voxel about `0.01`
    (the viewport readout shows 0.00816 at 03:22:50), `Ctrl+R`. Too coarse a voxel webs the fingers together
    [03:14:23]. Live: `join_and_fuse([palm, thumb, f1, f2, f3, f4], palm, v)` with `palm` = `BLK_hand` and `v` no more than a third of the
    narrowest finger gap, then `mesh_report`: `loose_parts` 1.
13. **Blend the roots** [03:15:11]. Course: on the back of the hand, `Clay Strips` in straight strokes from the
    palm onto each finger root, then Smooth; the same on the sides and the palm side; `Crease Polish` the fold at
    the base of each finger on the palm side [03:17:56]; palm lines again [03:18:36]; a sharpened crease over each
    knuckle [03:21:21]; `Scrape/Fill` the sides of the hand flat [03:21:37]; clean the thumb-to-palm transition.
    Live per finger: `{"brush":"clay_strips","points":[0.25*L behind the knuckle, the knuckle, 0.1*f onto the finger],"radius":0.5*finger_width,"strength":0.5,"snap":true}`
    then `smooth` on the same path. Turn the hand and look from every side [03:21:52].

### B. Foot

14. **Sole first** [03:23:29]. Course: a round cube, scaled in Edit Mode to the foot's length, width and height;
    from below, `Grab` it into a rectangle [03:24:35].
15. **Triangle with the sole protected** [03:25:14]. Course: `Lasso Mask` the bottom half with `Front Faces Only`
    OFF (it was left on from the ear and masked only the near side) [03:26:19]; `Grab` the top up into the leg so
    the side view is a triangle; Smooth the top into a straight slope to the toes; clear the mask; lean the shape
    so it is a right-angled triangle [03:27:32]. Live: the new block is `quad_ball("BLK_foot", ...)` parented to `CHARACTER` (rename the stage 02 one
    `BLK_foot_old` and hide it); `sculpt_mask(object="BLK_foot", op="box", min=[...], max=[x,y,mid_z])`,
    `{"brush":"grab","points":[top of block above the ankle, +0.5*L in Z],"radius":0.6*L}`, `sculpt_mask(op="clear")`.
16. **Heel, sole cut, toe shelf** [03:28:11]. Course: `Inflate` the back so the heel is a teardrop seen from
    behind; refit the lower leg to the new ankle; from the side, `Line Project` to slice the sole flat
    [03:29:36]; `Grab` the front forward to where the toes start. Live: `inflate` at the heel, radius `0.25*L`;
    `plane_squash(foot, (0,0,ground_z), (0,0,-1))`.
17. **Toes like fingers** [03:30:23]. Course: single vertex extruded along Y, `Skin` + `Subdivision` level 2,
    moved in Object Mode. Big toe: extra loops slid back and lowered to make the stepped top, tip widened, sole
    side flat on the ground [03:31:49]. `Alt+D` for the other four, scaled along their own length, shortest at
    the outside, a gap left between each [03:33:07]. Then `Grab` the foot block down to meet them, push the arch
    in, round the inside edge [03:34:38]. Live: `skin_digit("Toe_big", [(0,0,0),(0,-0.5*t,-0.02*t),(0,-t,-0.06*t)], [...])`.
18. **Bake, sculpt, remesh, join** [03:36:48]. Course: `Visual Geometry to Mesh`; sculpt a small toe with
    symmetry (X here), crease its joints; remesh the foot block, Smooth, restore the arch and flat sole, `Inflate`
    the heel, carve the hollows on both sides behind the ankle with `Clay Strips` set to subtract, add volume
    beside them [03:39:54]; remesh the toes, crease, make them boxier, flatten the nail area [03:41:52]. Join toes
    to foot, voxel about `0.006`, remesh [03:43:06]. Blend each toe root with `Clay Strips` and Smooth on top and
    underneath, crease between toes [03:43:25 to 03:46:20]. Leave the toes spread wider than looks natural: the
    gaps make retopology possible and are closed afterwards [03:46:42]. Mirror the foot.

### C. Legs, torso, arms

19. **Each part alone: remesh, smooth, one or two big shape changes** [03:47:58]. No detail yet.
    - Upper leg: voxel `0.05` (readout 0.0563), Smooth; from the side `Grab` the front of the thigh into a clear
      curve, keep the back straighter; shape the hip [03:48:51].
    - Lower leg: remesh, Smooth; `Inflate` the calf to the reference's thickness; back curved, front straight;
      make it flow into the thigh [03:49:35]. Mark the knee on the upper leg with a crease and a small flattened
      plane [03:50:44].
    - Pelvis: remesh, Smooth; crease the split at the back and the fold toward the leg [03:51:46].
    - Waist: `Grab` it in to the reference's narrowness; remesh; Smooth [03:52:18].
    - Chest: remesh; crease the lower edge of the rib cage as an arch; `Scrape/Fill` below it; `Clay Strips`
      above [03:53:34].
    - Delete the stage 02 hand and foot placeholders (`BLK_hand_old`, `BLK_foot_old`); save under a new numbered
      name [03:54:26].
    - Lower arm `0.03`, Smooth; upper arm remesh, lengthen it, narrow it; elbow: `Grab` a bump out at the back,
      crease round it, flatten its top [03:54:38 to 03:55:59].
    - Shoulder and neck: remesh and Smooth only, so they merge with their neighbours [03:56:26].
    Live for each: `sculpt_remesh(object=part, voxel_size=part_length/40)` (mine), `smooth` passes with radius
    `0.3*L`, then `grab`. Limb parts with a `Mirror` modifier: `sculpt_begin(object=part, symmetry="")` and stroke
    the real side only. Example thigh curve:
    `{"brush":"grab","points":[front mid-thigh, same point -0.06*L in Y],"radius":0.5*L}`.
20. **Join in groups, coarse to fine, blending each joint as it appears.** Be happy with the shapes and save
    before each join [03:57:33].
    - Upper + lower leg, voxel `0.04` [03:57:19]. `Clay Strips` across the knee front and back, Smooth, faint
      creases above and below the kneecap; re-check straight against curve [03:59:47].
    - Lower back: `Grab` it in so the back makes an S from the side [04:00:10].
    - Three torso parts, voxel `0.03` [04:00:47]. Smooth the seams; drag the buttocks down to overlap the legs and
      lift the hip line [04:01:21]; S-curve again; crease the fold at the side of the waist and tighten it with
      `Pinch` [04:02:20]; pull the shoulders out for a V shape; `Clay Strips` and Smooth over every seam; crease
      the centre line of the belly [04:03:37]; navel with `Draw` set to subtract [04:03:55]; rib cage out in
      profile; a crease from the reference at the side of the stomach [04:04:33].
    - Breasts, if the character has them [04:05:00]: `Clay Strips` in a figure-6 path that starts at the shoulder
      and curls round the chest, built up in layers with Smooth between; `Inflate` for fullness; crease the
      underside and run that crease up toward the armpit [04:06:39]. A separate ball joined in is the alternative.
    - Upper + lower arm: remesh, blend the elbow, a faint crease between upper arm and forearm, `Inflate` if
      thinner than the reference [04:07:51 to 04:09:20].
    - Arm + shoulder: remesh; `Clay Strips` from shoulder down onto the arm, Smooth, so the shoulder overlaps the
      arm like a chain link [04:10:17 to 04:11:31].
    - From the side with a very large `Grab`, enlarge the buttocks [04:12:41].
    Live: `join_and_fuse([...], target, v)`, keeping these names (ours): upper + lower leg into `BLK_leg`
    (rename `BLK_upper_leg` after the join), the three torso parts into `BLK_torso`, shoulder + upper + lower arm
    into `BLK_arm`. Blends
    `{"brush":"clay_strips","points":[0.15*L above the seam, the seam, 0.15*L below],"radius":0.25*limb_width,"strength":0.5,"snap":true}`
    then `smooth`, radius the same. Navel: `{"brush":"draw","subtract":true,"points":[belly point],"radius":0.03*torso_h,"strength":0.6}`.
    Waist fold: `crease`, radius `0.03*torso_h`, strength 0.3.
21. **Proportion pass on the whole figure** [04:13:33]. Course: with everything visible, the head and feet look
    too small and are scaled up. Live: `turnaround_sheet(object="CHARACTER")` with the full-body
    references; scale whole objects about their joints with bpy, then re-run the measurement.

At the end of this chapter the figure is still several meshes, all under `CHARACTER`: `BLK_head` (with the nose),
`BLK_eye`, `BLK_neck`, `BLK_ears`, `BLK_torso`, `BLK_leg`, `BLK_arm`, `BLK_hand`, `BLK_foot`. The course does not
fuse them here; stage 06 does.

## Settings the course uses

| Setting | Value | Where | Timestamp |
|---|---|---|---|
| Finger/toe build | single-vertex edge + `Skin` + `Subdivision` | modifiers | 02:48:08 |
| `Subdivision` levels on digits | 1 at first, then 2 | modifier | 02:48:15, 03:31:06 |
| Palm `Subdivision` | viewport 1, render 2 | modifier | 02:45:48 |
| Duplicating fingers and toes | `Alt+D` (linked); thumb `Shift+D` (own data) | Object Mode | 02:49:47, 02:53:37 |
| Applying modifiers on linked digits | Apply > `Visual Geometry to Mesh` | Object Mode | 02:58:47 |
| Finger symmetry | Y (whichever axis crosses the finger); thumb none | Sculpt Mode | 02:59:14, 03:03:14 |
| Voxel size, palm | 0.025 | remesh | 03:05:59 |
| Voxel size, finger, thumb | 0.01 | remesh | 03:09:36, 03:12:17 |
| Voxel size, joined hand | about 0.01 (readout 0.00816) | remesh | 03:14:44, 03:22:50 |
| Voxel size, joined foot | about 0.006 | remesh | 03:43:14 |
| Voxel size, upper leg | 0.05 (readout 0.0563) | remesh | 03:48:18 |
| Voxel size, lower arm | 0.03 | remesh | 03:54:50 |
| Voxel size, joined legs | 0.04 | remesh | 03:57:54 |
| Voxel size, joined torso | 0.03 | remesh | 04:01:08 |
| Foot sole mask | `Lasso Mask`, `Front Faces Only` off | tool settings | 03:26:30 |
| Viewport clipping to isolate a part | `Alt+B` region | 3D viewport | 03:06:30 |

The course says voxel size depends on scene scale and to go higher or lower as needed [03:48:21].

## Mistakes the course warns about

- Sculpting anatomy from memory instead of copying the reference [02:29:08].
- A flat palm, knuckles in a straight row, or fingers as straight tubes [02:35:36], [02:37:30].
- Moving the first vertex of a finger or toe in Edit Mode: the origin leaves the knuckle and rotation breaks [02:48:45].
- Applying modifiers on linked fingers the normal way: it errors; use `Visual Geometry to Mesh` [02:58:28].
- Joint creases cut too deep. Keep them faint [03:10:09].
- Joining the hand before each finger is right; afterwards each finger is separate work [03:14:49].
- Remeshing the joined hand too coarsely: the fingers web together [03:14:23].
- Masking the foot sole with `Front Faces Only` still on: only the near side is protected [03:26:19].
- Inner and outer ankle at the same height [02:33:05].
- Toes packed tight before retopology; keep gaps [03:46:42].
- Accidental face sets (a new colour patch) from a mis-pressed key; clear them from the Face Sets menu [04:10:28].
- Never rotating the model: check each form from all sides [03:21:52], [04:08:26].

## What changes for a different character

- General: build digits as skinned edges with linked data, shape and remesh parts alone, join in groups from
  coarse to fine, blend each seam with build-up then smooth, crease last and lightly, check the outline often.
- Specific to the course character (slim stylised woman, bare skin): narrow waist, strong S-curve, V-shaped
  shoulders, large breasts and hips, knees only hinted because the concept barely shows them [03:59:04], no
  fingernails, soft muscle definition. Read every one of these off your concept instead.
- Heavier or muscular builds: same steps; use `inflate` and `clay_strips` at larger radii, and add muscle groups
  as separate overlapping masses before the join so they read as interlocking links.
- Clothed characters: sculpt the body only as far as it shows or shapes the clothes; hidden areas need volume, not
  detail. Clothes are the next stage.
- Mitten hands, three-finger hands, hooves, paws: keep the palm block and `skin_digit`, change the count and
  radii. A mitten is the palm plus thumb plus one wide digit.
- Creatures: digitigrade legs, tails and wings are more `skin_digit` chains or `quad_ball` links placed along the
  limb, joined and blended the same way. The human ratios in the table do not apply; measure the concept.
- Hard-surface limbs (armour, prosthetics, robot parts): do not sculpt them. Model them later as separate
  objects; here make only a simple volume underneath to hold proportions.
- Boots or gloves that are never removed: skip toes or fingers, sculpt the outer shape.

## Exit check

1. `mesh_report` on every body mesh: `loose_parts` 1 for each fused mesh (hand, foot, legs, torso, arm),
   `boundary_edges` 0, `non_manifold_edges` 0. More than one loose part after a join means the voxel remesh did
   not fuse: failed. `symmetry_error` below 0.002 for the torso.
2. Numbers, each reported with pass or fail: finger joint creases at 0.5 and 0.75 of knuckle-to-tip (within
   0.05); finger lengths ordered middle > ring and index > little; neighbouring fingers and toes separated by a
   gap of at least 3 voxels (cast rays between them: no hit); inner ankle higher than outer; foot sole flat on
   the ground plane (min Z spread under 1% of foot length); knuckle Z or Y positions not collinear.
3. `turnaround_sheet(object="CHARACTER")` with references, plus close sheets of `BLK_hand` and `BLK_foot`. Look for:
   thigh front curved and back straight in `LEFT`; calf the reverse; S-curve of the back; no visible seam ridge
   where parts were joined. This is looking, not measuring.
4. `outline_match(object="CHARACTER", references={...}, threshold=0.98)` for every view that has a
   real reference picture in the same A-pose. Below 0.98 is failed: fix with large-radius `grab` where the
   overlay is red or blue, then measure again. A view with no picture is `not_run`: report "looked at, not
   measured", never passed. If the concept is posed and no A-pose picture exists, no body view can be measured;
   say so plainly instead of matching a posed picture.
5. `save_file` under a new numbered name.

## Gaps

- **Add-ons**: `Extra Mesh Objects` (free, Blender extensions) for the round cube; `quad_ball` replaces it.
  `PureRef` for the reference board; `reference_setup` and `turnaround_sheet` replace it. No paid add-on is used.
- **Line Project** has no tool. `plane_squash` flattens to a plane; it does not trim geometry, so remesh after it.
- **Pinch** has no brush; a low-strength `crease` pinches as a side effect.
- **Scrape/Fill** and **Lasso Mask**: see the Gaps in 03-sculpt-face.md.
- `sculpt_strokes` symmetry mirrors about the named object's own local axis. A hand at the end of an angled arm
  has no useful symmetry plane; the course gets both hands from a `Mirror` modifier, so sculpt one hand and keep
  the modifier (or bake it at the end).
- Loop cuts, edge slides and skin-radius edits in Edit Mode are described here as their result (arched palm,
  stepped toe); reproduce them with `skin_digit` points and radii or with `grab`, not key presses.
- Several remesh sizes are not spoken or shown: the foot block, single toes, lower leg, pelvis, waist, chest,
  upper arm, shoulder, neck, and the two arm joins. Use the size of the neighbouring part.
- At 03:54:38 the narrator says "hands" while remeshing at 0.03; from the surrounding steps this is the lower
  arm. Treat that reading as mine.
- Which side of the foot is the upright side of the "right-angled triangle" in front view is drawn on screen but
  not said; the frames suggest the inner side is nearer vertical. Check your reference.
- Where exactly the foot's side hollows are carved [03:39:54] is shown only by cursor; "behind the ankle bones on
  both sides" is my reading of the frames.
- Scene scale is never stated (see 03-sculpt-face.md). The `part_length/40` voxel rule and all radii are mine.
- The course says it refines hands, feet and body further off camera [03:23:00], [03:47:19], [04:13:33]; the
  recorded result is a first pass, so matching the reference to 0.98 will need more grab passes than it shows.
