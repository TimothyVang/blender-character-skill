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
   X; `Skin` modifier then `Subdivision` (levels 1, later 2); `Ctrl+A` in Edit Mode (Skin Resize) sets thickness. The first
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
   (the viewport readout shows 0.0100 m at 03:14:46 and 03:22:48), `Ctrl+R`. Too coarse a voxel webs the fingers together
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
    - Upper leg: voxel `0.05` (readouts 0.0563 and, on the frame at 03:48:19, 0.0495), Smooth; from the side `Grab` the front of the thigh into a clear
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
    `{"brush":"grab","points":[front mid-thigh, same point -0.06*L in Y],"radius":0.3*L}` (ring measured on the frames at
    about 0.2 to 0.3 of thigh length; use 0.5*L only for a whole-part curve).
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

## How the artist works on screen

Studied from the course frames (120 clips, chapter 05, `qy-wwP-b9HY-05-HHMMSS`, ids cite the clip start). Blender 5.0.1,
Sculpting workspace: viewport in the middle, concept and reference board docked in a small pane at the left (the
board app is PureRef, title bar visible at 02:37:05), outliner and Properties on the right. The figure stays in its
stiff A-pose the whole chapter (`[qy-wwP-b9HY-05-041323]` 04:13:23). Header values below are as shown; a brush's Size is
in screen pixels, so it does not carry over: I (not the course) estimate world radii from the ring drawn around the
cursor in the same frame.

**Habits that repeat everywhere**
- Mode toggling: `Ctrl+Tab` swaps Object and Sculpt Mode constantly; every edit-mode job ends with `Tab` back.
- Brush values never change from the defaults the 03 stage already lists: `Grab` Strength 0.400, `Crease Polish` 0.250,
  `Scrape/Fill` 0.700, `Clay Strips` 0.500, `Inflate/Deflate` 0.500 (`[qy-wwP-b9HY-05-033938]` 03:39:40). Only Size changes
  (54 px for creases up to about 540 px for whole-limb pulls).
- Smooth is `Shift` held over the same spot, almost always right after a `Clay Strips` or `Grab` stroke.
- Orbit constantly (`Alt` drag, `Numpad 1/3`, the viewport gizmo), and zoom to the whole figure before moving on
  (`[qy-wwP-b9HY-05-040822]` 04:08:22: "rotate around your whole sculpt").
- Heavy use of the Annotate tool: a quick pen line over the viewport marks a joint position or a curve, then it is
  erased (`[qy-wwP-b9HY-05-030108]` 03:01:10; `[qy-wwP-b9HY-05-034847]` 03:48:49; `[qy-wwP-b9HY-05-041333]` 04:13:38).
  Reader's equivalent: `reference_setup` or `turnaround_sheet` overlays and your own numbers; no annotation tool.
- Clipping: `Alt+B` isolates a part; the viewport title then reads "(Clipped)" (`[qy-wwP-b9HY-05-030616]` 03:06:19).
  `Alt+Z` is X-ray, `H`/`Alt+H` hide and unhide other parts (`[qy-wwP-b9HY-05-034847]`).
- Remesh: select the part, Sculpt Mode, press `R` and drag to preview the voxel grid in metres
  (e.g. 0.0998 down to 0.0114 on a finger, `[qy-wwP-b9HY-05-030921]` 03:09:30-03:09:34), then `Ctrl+R` to apply
  the remesh. The scene is in metres.
- Ring-to-part ratios measured on the frames (mine): finger `Grab` ring radius about 0.4 to 0.5 of finger length
  (`[qy-wwP-b9HY-05-025901]` 02:59:06-02:59:12); foot `Grab` about 0.65 of foot length (`[qy-wwP-b9HY-05-032509]` 03:25:17);
  thigh `Grab` about 0.2 to 0.3 of thigh length (`[qy-wwP-b9HY-05-034904]` 03:49:15). Use these over the 0.5*L above for thigh work.

**Method, shown in the slides (02:28:05 to 02:39:20)**: no live sculpting yet. The red strokes drawn over the side-view
leg photo mark thigh front curved and back straight, calf back curved and front straight (`[qy-wwP-b9HY-05-023142]`
02:31:47-02:31:53); the angry-face collage and the ankle drawing with a level red line (wrong) versus a tilted one
(right) (`[qy-wwP-b9HY-05-023310]` 02:33:12-02:33:16); arcs over a hand photo, each row of knuckles steeper (`[qy-wwP-b9HY-05-023601]`
02:36:03-02:36:09); ticks on a finger side view at halves (`[qy-wwP-b9HY-05-023656]` 02:36:58-02:37:01).

**Step 1 Palm box.** Add > Mesh > Cube in Object Mode at 02:40:44 (the cube arrives huge over the face and is scaled down
beside the figure), moved to the forearm end and flattened (`[qy-wwP-b9HY-05-024034]`, `[qy-wwP-b9HY-05-024151]` 02:41:54). Seen from the side in Edit Mode.
Reader: `quad_ball("BLK_hand", ...)` scaled about `(1.0, 0.85, 0.3) * palm_length`, rotated to the forearm.

**Step 2 Arch.** One `Ctrl+R` loop cut across the middle raised with `G` (02:42:00), then two more cuts at 02:42:25 and 02:42:34
(`[qy-wwP-b9HY-05-024218]`). Reader: one `grab` on the back of the palm, radius `0.6*L`, 0.08*L along the normal.

**Step 3 Thumb wedge.** Pulled down and out in Edit Mode on the Mirror-modified cube, with a pad pulled lower to hint
the fleshy side (`[qy-wwP-b9HY-05-024644]` 02:46:46). Reader: `snake_hook` from the side of the palm near the wrist,
0.35*L sideways, radius `0.3*L`.

**Step 4 Mirror and soften.** Mirror panel: axis X, Merge 0.001 m (`[qy-wwP-b9HY-05-024536]` 02:45:40); `Add Modifier`
search "sub" gives Subdivision Surface, panel reads viewport 1, render 2 (`[qy-wwP-b9HY-05-024617]` 02:46:18). `Grab`
Size 284 px at 02:44:59 and 200 px at 02:46:18, Strength 0.400; checks the shape from front, side and above. Reader:
`ob.modifiers.new("Subdivision", "SUBSURF")`, then `grab` strokes with strength 0.4.

**Step 5 Finger from one edge.** A cube is created near the head, extruded along X, then Add Modifier: Skin first,
then Subdivision Surface; levels set from 1 to 2 (`[qy-wwP-b9HY-05-024808]` 02:48:10-02:48:19). The Skin panel shows
Symmetry X ticked. Thickness: `Ctrl+A` is Skin Resize; the tool panel at the bottom-left reads "Skin Resize" while the
header shows Scale X 0.3757 (`[qy-wwP-b9HY-05-024836]` 02:48:38-02:48:41). Back in Object Mode the first vertex is
untouched so `R` rotates about the knuckle (`[qy-wwP-b9HY-05-024904]` 02:49:09). Reader: `skin_digit(...)` as above; the
radii param is the thickness.

**Step 6 Place and duplicate.** `G` then `R` in Object Mode; four near-parallel fingers appear at 02:51:53; one is
fattened with a loop cut (`Ctrl+R`, 02:52:03, `[qy-wwP-b9HY-05-025151]`). The four are later given different lengths and
a fan (`[qy-wwP-b9HY-05-025319]` 02:53:35).

**Step 7 Thumb.** A copy of a finger is rotated into the wedge and shortened (02:53:21 to 02:53:35). Reader: `skin_digit`
with three points.

**Step 8 Palm meets fingers.** The Subdivision dropdown's Apply is used on the palm (`[qy-wwP-b9HY-05-025615]` 02:56:30).
`Grab` Size 540 px (about the forearm width scale), Strength 0.400, drags the forearm end to the wrist
(`[qy-wwP-b9HY-05-025732]` 02:57:34); then all fingers selected (02:57:43). Reader: `grab` from forearm end to wrist,
radius about `0.6*L`.

**Step 9 Bake and sculpt one for all.** Pivot is reset to Median Point (02:58:11). Applying a modifier on a linked finger
shows an "Apply Modifier" box that makes data single-user; instead `Ctrl+A` opens the Apply menu and the choice is
Visual Geometry to Mesh, and all four fingers lose the stack at once (`[qy-wwP-b9HY-05-025841]` 02:58:43-02:58:59). In
Sculpt Mode a `Grab` of 324 px, Strength 0.400, on one finger moves all four (`[qy-wwP-b9HY-05-025901]` 02:59:03).
Reader: `bake_modifiers_linked(...)`, then `sculpt_begin(object="Finger_index", symmetry="Y")`.

**Step 10 Joint creases.** The artist draws two short Annotate lines across the finger for the joint heights, draws them
"all the way to the bottom of the fingers", then erases them (`[qy-wwP-b9HY-05-030108]` 03:01:10-03:01:22). `Crease
Polish` Size 84 then 68 px, Strength 0.250, with only a faint line. Nails are skipped
for this character (`[qy-wwP-b9HY-05-030150]` 03:02:00). The thumb is checked for symmetry and found not to work (`[qy-wwP-b9HY-05-030311]`).
Reader: `{"brush":"crease","points":[underside at 0.5*f],"radius":0.06*f,"strength":0.25,"snap":true}`.

**Step 11 Remesh parts separately.** The reference palm is docked at the left while the artist works (03:06:50-03:07:00).
`Scrape/Fill` Size 160 to 196 px, Strength 0.700, red ring, flattens the top of the palm with broad sweeps
(`[qy-wwP-b9HY-05-030856]` 03:08:58). Finger voxel drag reads 0.0998 down to 0.0114 m (`[qy-wwP-b9HY-05-030921]`);
`Clay Strips` Size 112 then 286 px adds pad volume on the underside and `Shift` smooths it
(`[qy-wwP-b9HY-05-031033]` 03:10:34-03:10:43); `Crease Polish` Size 110-120 px, kept faint (`[qy-wwP-b9HY-05-031056]`). The thumb
reads 0.0106 m and is smoothed lightly (`[qy-wwP-b9HY-05-031214]` 03:12:20). Reader: `sculpt_remesh(object=finger,
voxel_size=0.011)`; `flatten(...)`; `crease` with strength 0.25.

**Step 12 Join and fuse.** Fingers and thumb are selected and the palm made active, then `Ctrl+J` (the narrator says
Ctrl G, the on-screen key is `Ctrl+J`) (`[qy-wwP-b9HY-05-031407]` 03:14:17). The voxel preview reads 0.0160, 0.0145,
0.0129, 0.0100 m as it is dragged down (`[qy-wwP-b9HY-05-031437]` 03:14:38-03:14:46); the fuse leaves ragged stair-steps at
  the finger roots (`[qy-wwP-b9HY-05-031503]` 03:15:10). Reader: `join_and_fuse([...], palm, voxel_size)` with
  `voxel_size` at most one-third of the narrowest finger gap (keep `0.01` only when the gap is at least 30 mm).

**Step 13 Blend the roots.** `Clay Strips` Size 60-176 px, Strength 0.500, pulls the palm onto each finger and
`Shift` smooths (`[qy-wwP-b9HY-05-031742]` 03:17:43-03:17:54). Palm lines: `Crease Polish` Size 208-344 px then 80 px at
0.250 (`[qy-wwP-b9HY-05-031829]` 03:18:31-03:18:40). Knuckles: `Crease Polish` Size 56-82 px with `Ctrl` held
(`[qy-wwP-b9HY-05-032116]` 03:21:18; `[qy-wwP-b9HY-05-032130]` 03:21:32); `Scrape/Fill` Size 144-274 px flattens the sides
(03:21:38-03:21:49). A last pass at 0.0100 m is possible but skipped (`[qy-wwP-b9HY-05-032243]` 03:22:48).
Reader: per finger `clay_strips` then `smooth`; `crease` 0.25 on the knuckle row.

**Step 14 Sole first.** A rounded cube (named Roundcube in the outliner) lies near the legs; the artist enters the bottom
orthographic view by clicking the gizmo's -Z, then `Grab` Size 284 px, Strength 0.400, shapes the rectangle
(`[qy-wwP-b9HY-05-032429]` 03:24:30-03:24:40). Reader: `quad_ball("BLK_foot", ...)` scaled to length, width and height.

**Step 15 Triangle with sole protected.** After the failed mask, `Ctrl+Z` and the tool-header tick box "Front Faces Only"
is cleared (`[qy-wwP-b9HY-05-032619]` 03:26:21-03:26:31). `Grab` Size 434 px, Strength 0.400, pulls the foot top up into the
leg; an Annotate sketch in front view shows the unwanted symmetric triangle and is erased with `Ctrl+Z` x6
(`[qy-wwP-b9HY-05-032726]` 03:27:28-03:27:43). Reader: `sculpt_mask(op="box", ...)`, `grab` radius about `0.6*L`.

**Step 16 Heel and toe shelf.** Smoothing at the ankle junction so it is not sharp (`[qy-wwP-b9HY-05-032800]` 03:28:01);
side orthographic via `Numpad 3` with the foot as a flat wedge (`[qy-wwP-b9HY-05-032933]` 03:29:34-03:29:40). The Line
Project action is not legible in the frames, so the mapping stays as the stage's own. Heel `Inflate/Deflate` Size 420 px,
Strength 0.500, is shown at 03:39:40 (`[qy-wwP-b9HY-05-033938]`).

**Step 17 Toes.** Annotate sketch of where the toes begin, seen from below, then the toe is created like a finger: Skin
and Subdivision, panel viewport 1 then 2 (`[qy-wwP-b9HY-05-033102]` 03:31:04-03:31:13), moved into place (03:31:47) and
stepped in Edit Mode while a green foot reference sits docked left (`[qy-wwP-b9HY-05-033145]` 03:31:55). `Alt+D` then `S Y`
shortens each duplicate (`[qy-wwP-b9HY-05-033259]` 03:33:07-03:33:17). Reader: `skin_digit("Toe_big", ...)`, then `copy()` and
`scale.y`.

**Step 18 Bake, remesh, join.** Toes selected together (03:36:46, `[qy-wwP-b9HY-05-033637]`); heel and symmetry check
(03:39:40-03:39:52). Toe remesh preview 0.0752 then 0.0103 m (`[qy-wwP-b9HY-05-034139]` 03:41:47-03:41:50); join with
`Ctrl+J` and a voxel preview 0.0132 then 0.00642 m (`[qy-wwP-b9HY-05-034306]` 03:43:14-03:43:17); `Scrape/Fill` Size 114 px
and `Clay Strips` Size 54 px blend toe roots (`[qy-wwP-b9HY-05-034319]` 03:43:31-03:43:36); toes are kept apart with a wide
gap (`[qy-wwP-b9HY-05-034709]` 03:47:10). Reader: `sculpt_remesh(object=toe, voxel_size=0.0103)`, `join_and_fuse(...,
0.006)`.

**Step 19 Each part alone.** Upper leg: right orthographic with other pieces hidden (`H`), Annotate marks, `Grab` Size
412 px, Strength 0.400 (`[qy-wwP-b9HY-05-034847]` 03:48:49-03:49:02); voxel readout 0.0495 m (`[qy-wwP-b9HY-05-034807]`
03:48:19). Lower leg: smoothing with `Shift`, Annotate along the calf (`[qy-wwP-b9HY-05-035027]` 03:50:29-03:50:42).
Pelvis: `Ctrl+R`, smooth, `Crease Polish` Size 88 px for the gluteal split (`[qy-wwP-b9HY-05-035137]` 03:51:41;
`[qy-wwP-b9HY-05-035156]` 03:51:59). Chest: the rib-cage edge is `Crease Polish` Size 186 px then 80 px at 0.250
(`[qy-wwP-b9HY-05-035326]` 03:53:34-03:53:38). Placeholders deleted with `X`, then File > Save Incremental, which writes
the next numbered name (`[qy-wwP-b9HY-05-035426]` 03:54:37; `[qy-wwP-b9HY-05-035438]` 03:54:40). Arm voxel preview 0.0526 m
(03:54:49); elbow: `Crease Polish` Size 54-70 px with `Ctrl` held, then `Scrape/Fill` Size 114 px
(`[qy-wwP-b9HY-05-035546]` 03:55:47-03:55:58). Shoulder: `Grab` Size 244 px, `Ctrl+R`, smooth (`[qy-wwP-b9HY-05-035622]`).
Reader: remesh voxel `part_length/40` stays mine; strokes as in the step.

**Step 20 Join in groups.** Legs: `Ctrl+J` (the narrator says Ctrl G), `Ctrl+S`, remesh preview 0.0405 m
(`[qy-wwP-b9HY-05-035712]` 03:57:30; `[qy-wwP-b9HY-05-035746]` 03:57:54). Knee: `Clay Strips` Size 56-238 px (`[qy-wwP-b9HY-05-035856]`
03:58:57-03:59:03), then `Crease Polish` Size 100 px and `Grab` Size 280-320 px pull the back of the knee
(`[qy-wwP-b9HY-05-035936]` 03:59:38-03:59:45). Lower back S: `Grab` Size 358-442 px from the side with an Annotate guide
(`[qy-wwP-b9HY-05-040035]` 04:00:37-04:00:45). Torso: three parts joined, voxel narrated as 0.03 (no readout seen)
(`[qy-wwP-b9HY-05-040100]` 04:01:02-04:01:15); buttocks dragged down to overlap the legs (`[qy-wwP-b9HY-05-040117]`
04:01:20-04:01:34). Waist fold: `Crease Polish` Size 114 px at 0.250 copied from the reference docked at left
(`[qy-wwP-b9HY-05-040216]` 04:02:27); belly centre line `Crease Polish` Size 82 px (`[qy-wwP-b9HY-05-040329]`
04:03:40; `[qy-wwP-b9HY-05-040341]`). Stomach: `Crease Polish` Size 60-70 px (`[qy-wwP-b9HY-05-040428]` 04:04:40) then `Clay Strips` Size 76-344 px adds low belly volume
(`[qy-wwP-b9HY-05-040447]` 04:04:49-04:04:55). Chest: `Grab` Size 224-329 px lowers the breasts, then `Inflate/Deflate` Size
270 px, Strength 0.500 (`[qy-wwP-b9HY-05-040629]` 04:06:30-04:06:38). Arms: elbow smoothing and `Inflate` Size
504 px (`[qy-wwP-b9HY-05-040822]` 04:08:24-04:08:34); arms plus shoulder joined with `Ctrl+J`, `Ctrl+R`, and a blue
Face Set patch from a stray key (`[qy-wwP-b9HY-05-041009]` 04:10:17-04:10:28); `Clay Strips` Size 120-424 px
with `Shift` smooths shoulder onto arm (`[qy-wwP-b9HY-05-041111]` 04:11:13-04:11:29). Back centre line: `Crease Polish`
Size 64-88 px, one stroke undone (`[qy-wwP-b9HY-05-041232]` 04:12:33). Reader: `join_and_fuse(...)`, `clay_strips`
then `smooth` on the same path, `crease` strength 0.25, `inflate` strength 0.5.

**Step 21 Proportion pass.** `Ctrl+Tab`, `Alt+H`, zoom out to the whole figure (`[qy-wwP-b9HY-05-041323]` 04:13:23-04:13:32).
The artist circles the head with Annotate in front and side views and says the head and the feet are too small
(`[qy-wwP-b9HY-05-041333]` 04:13:35-04:13:44). Reader: `turnaround_sheet(object="CHARACTER")`, scale whole objects
about their joint, re-run `outline_match`.

**What the artist treats as done.** Only by eye against the docked reference or a zoomed-out view; nothing is measured. The
stage's exit check is therefore ours, not the course's.

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
| Voxel size, joined hand | about 0.01 (readout 0.0100) | remesh | 03:14:46, 03:22:48 |
| Voxel size, joined foot | about 0.006 (readout 0.00642); a single toe reads 0.0103 | remesh | 03:43:17, 03:41:50 |
| Voxel size, upper leg | 0.05 (readouts 0.0563, 0.0495) | remesh | 03:48:19 |
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
   not fuse: failed. `symmetry_error` below 0.002 for the torso (and report `symmetry_p95_error` and `symmetry_max_error`).
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

## Low-poly game route (second course: Nhij Quang, Girl#01)

Second source: Nhij Quang, [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), Blender 4.2.1 LTS, 1 h 15 min, no narration (music only). Everything here was read off the screen: the key-cast overlay, redo panels, modifier panels and status-bar counts, from 157 study sheets; labels are in `annotations/mlnR-Eyazh0/`. Times marked `NQ` point into that video, not the main course. Use this route instead of the sculpt route when the job is a low-poly game character (box/poly modelled, hand-painted, Mixamo-rigged); see "Two routes" in `SKILL.md`. Values that could not be read are listed as not visible, never guessed. Python blocks marked `# not run in Blender` were not executed.

Note: in this video the "sculpt body" stage is done by box/poly modelling, not with sculpt brushes. These steps come from chapter 6 (Chest Modeling, 00:13:58 to 00:16:22) and chapter 8 (Hand Modeling, 00:28:32 to 00:33:20). At chapter 6 the outliner already holds Cube (body), Cube.001, Cube.002, Cube.003; by chapter 8 it holds Cube to Cube.006 plus the new hand Cube.007.

Order of work:
1. [NQ 00:14:01 to 00:14:16] Body "Cube" in Edit Mode, Front Orthographic, X-ray. Loop cut (Ctrl R) across the upper torso, Move X -0.007316 m. Side check in Right Orthographic. Key overlay "X", "Z"; vertex count drops 216 -> 215 (one vertex removed). Mirror Clipping is on, Merge 0.001 m.
2. [NQ 00:14:23] A low-poly UV sphere is added inside the body mesh; it appears on both sides because of the mirror. Mirror Clipping is switched off. Verts 273, Faces 267.
3. [NQ 00:14:30] The back half of the sphere is removed; the remaining dome (25 verts, 25 faces selected) is scaled 0.874 and moved onto the chest in Right Orthographic. Overlay "G", "S", "Alt". Body is now Verts 240, Faces 228.
4. [NQ 00:14:37 to 00:14:52] Select Linked (Delimit Normal) picks each dome. Scaled/moved in front view. Shading pie (Wireframe / Solid / Material Preview / Rendered) is shown, view goes to wireframe, and border verts are moved (Move Y -0.0042 m, repeated x3).
5. [NQ 00:14:59 to 00:15:13] The dome is connected into the chest surface: a new edge runs from the dome down the torso (x4 repeats). Verts 240, Edges 473, Faces 233. Object Mode check with smooth shading (scene Verts 1,465, Faces 1,314). Back in Edit Mode, Move X 0.017165 m. Verts 240, Faces 236.
6. [NQ 00:15:20 to 00:15:49] Edge flow around the breast is tidied: side view X-ray check (x4), Move Y/Z 0.005443 m, Vertex Slide factor 0.355 (Clamp on, Correct UVs on), Shift-select under-breast edges, more cuts and slides ("b x2"). Verts 241 -> 243, Faces 238 -> 241.
7. [NQ 00:15:56] Dissolve Edges between the breasts: Dissolve Vertices on, Face Split off. Verts 243, Faces 241.
8. [NQ 00:16:04 to 00:16:22] Neck: Mirror Clipping is back on. In Right Orthographic the top ring is extruded up (Move Z 0.031935 m) and rotated -11.8 degrees (Orientation View). Vertex Slide factor 0.289 on the collarbone verts (x3). Result Verts 252, Edges 498, Faces 247, Tris 475 (half mesh).
9. [NQ 00:28:35] Hand starts as a new separate cube "Cube.007" (no modifiers) in Front Orthographic; Tab, G. Verts 8, Faces 6.
10. [NQ 00:28:42] The cube is flattened into a palm slab (Resize panel shows 3.248 on x, y, z) and loop cut (Ctrl R) into four finger columns. Verts 20, Faces 18.
11. [NQ 00:28:50 to 00:28:57] One palm corner is moved to taper the palm. Bevel on the edges between finger columns at the front: Affect Edges, Width Type Offset, Width 0.00197 m, Segments 1, Shape 0.500, Loop Slide on, Clamp Overlap off, Harden Normals off, Miter Outer/Inner Sharp, Intersection Type Grid Fill, Face Strength None, Profile Superellipse. Verts 32, Faces 27.
12. [NQ 00:29:04 to 00:29:33] Face select ("4" then "3" on the overlay). The palm is placed by the hip in Front Orthographic (Move X 0.039919 m). The finger root faces are shaped from the front (G x2, Move Y -0.001945 m, Z 0.007292 m) and extruded into four long finger boxes. Verts 48 -> 69, Faces 43 -> 64.
13. [NQ 00:29:40 to 00:30:16] Finger tips scaled 0.5128 (S x9). Top Orthographic with X-ray: tips moved to set lengths (D -0.01872 m), fingers narrowed with Resize 0.7587 and 0.7449. Verts 69, Faces 64.
14. [NQ 00:30:23 to 00:31:21] Knuckle loops: Ctrl R across the fingers, S x2 on the new loops; finger sections rounded by moving corner verts (Move Y 0.001963 m and -0.002607 m). Size check in Object Mode beside the thigh. More joint loops are added. Verts 69 -> 117 -> 213, Faces 64 -> 112 -> 208.
15. [NQ 00:31:28 to 00:31:42] Object Mode, W menu, Shade Smooth. Ctrl R loop cut across the palm (Edge Slide 0.3160). Knife tool cuts on the palm side for the thumb base. Verts 216 -> 225, Faces 210 -> 220.
16. [NQ 00:31:50 to 00:32:40] Thumb: faces on the palm side selected (Faces 4 selected), moved (Move Y -0.012285 m), extruded out (Move X 0.024978, Y -0.003142, Z -0.002637 m), rotated (R, header -13.74) in Right Orthographic, extruded again, tip scaled ("S", "1"), nudged (Move 0.000081, -0.000985, 0.003155 m). Verts 225 -> 261, Faces 228 -> 264.
17. [NQ 00:32:47 to 00:33:02] All 261 verts selected, hand moved to the wrist and scaled 1.422 in Front Orthographic. Then Ctrl J joins Cube.007 into the body "Cube" (Tab x2). Object Mode count: Verts 2,950, Faces 2,780, Tris 5,402, Objects 1/9. The body's Mirror modifier (Clipping on, Merge 0.001 m) gives the second hand.
18. [NQ 00:33:09 to 00:33:16] Ctrl S, status "Saved female_char1.blend". At 00:33:16 the outliner shows Empty, Empty.001 and a "Model" collection, and the status bar reads Verts 0, so the model parts were moved into a collection named Model (how is not shown).

How it looks on screen:
- All work is in Edit Mode on low-poly meshes with direct vertex moves, loop cuts, extrudes, slides and the knife. No sculpt brushes, no Subdivision modifier is visible in the modifier panel.
- Front, Right and Top Orthographic for placement against the reference; User Orthographic for shape checks.
- X-ray / wireframe is turned on when tracing or reaching hidden verts (14:01, 14:52, 15:20, 29:54) and off for shape checks.
- Mirror Clipping is turned off while a loose part (the breast sphere) is added near the centre, and turned back on afterwards.
- The hand is built as its own object without a mirror, then joined into the mirrored body so it is duplicated for free.
- Short checks in Object Mode with Shade Smooth between edits.
- Small move values (millimetres to a few centimetres) are typical; the model is roughly real-world scale.

Python route:
```python
# not run in Blender
import bpy, bmesh
from math import radians
from mathutils import Matrix, Vector

body = bpy.data.objects["Cube"]
mirror = body.modifiers["Mirror"]

# step 2-3: breast dome inside the body mesh
mirror.use_clip = False
bm = bmesh.new(); bm.from_mesh(body.data)
center = Vector((0.06, -0.08, 1.30))  # read from reference; not on screen
ret = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=0.05,
                                matrix=Matrix.Translation(center))
sphere = ret["verts"]
back = [v for v in sphere if v.co.y > center.y + 1e-5]
bmesh.ops.delete(bm, geom=back, context='VERTS')
dome = [v for v in sphere if v.is_valid]
bmesh.ops.scale(bm, vec=(0.874,)*3, space=Matrix.Translation(-center), verts=dome)
bm.to_mesh(body.data); bm.free()
# step 5: join the dome border to the chest with bmesh.ops.bridge_loops or connect_verts
# step 7
# bmesh.ops.dissolve_edges(bm, edges=extra_edges, use_verts=True, use_face_split=False)
mirror.use_clip = True

# step 8: neck
# top = verts of the top ring; extrude then:
# bmesh.ops.translate(bm, verts=neck, vec=(0, 0, 0.031935))
# bmesh.ops.rotate(bm, verts=neck, cent=ring_center, matrix=Matrix.Rotation(radians(-11.8), 3, 'X'))

# steps 9-11: hand slab with four finger columns
bpy.ops.mesh.primitive_cube_add(size=1, location=(0.25, 0, 0.85))  # placement from reference
hand = bpy.context.object; hand.name = "Cube.007"
hand.scale = (0.09, 0.03, 0.012)  # flat palm; real values not visible
bpy.ops.object.transform_apply(scale=True)
bm = bmesh.new(); bm.from_mesh(hand.data)
long_edges = [e for e in bm.edges
              if abs((e.verts[0].co - e.verts[1].co).normalized().x) > 0.9]
bmesh.ops.subdivide_edges(bm, edges=long_edges, cuts=3, use_grid_fill=True)
# bevel the three column-separating edges at the front, width 0.00197, 1 segment
# then extrude each front finger face separately:
# r = bmesh.ops.extrude_discrete_faces(bm, faces=finger_faces)
# translate each new face along the finger axis; scale tips by 0.5128
bm.to_mesh(hand.data); bm.free()

# step 17: scale and join into the mirrored body
hand.scale = (1.422,)*3
bpy.ops.object.transform_apply(scale=True)
bpy.ops.object.select_all(action='DESELECT')
hand.select_set(True); body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
bpy.ops.wm.save_mainfile()
```

Settings read on screen:
- Chest: Move X -0.007316 m; Resize 0.874; Select Linked Delimit Normal; Move Y -0.0042 m; Move X 0.017165 m; Move Y/Z 0.005443 m; Vertex Slide 0.355 (Clamp on, Correct UVs on); Dissolve Edges (Dissolve Vertices on, Face Split off); Neck Move Z 0.031935 m; Rotate -11.8 degrees, Orientation View; Vertex Slide 0.289
- Mirror Clipping off from 00:14:23 to about 00:15:56, on again by 00:16:04
- Chest counts (half mesh): 216 -> 215 -> 273 (sphere added) -> 240 -> 243 -> 252 verts; faces 207 -> 228 -> 241 -> 247
- Hand: Resize 3.248; Bevel Edges, Offset, 0.00197 m, 1 segment, shape 0.5, Loop Slide on, Miter Sharp, Grid Fill, Superellipse; Move X 0.039919 m; Move Y -0.001945 / Z 0.007292 m; Resize 0.5128; D -0.01872 m; Resize 0.7587, 0.7449; Move Y 0.001963, -0.002607 m; Edge Slide 0.3160; thumb Move Y -0.012285 m, Move (0.024978, -0.003142, -0.002637) m, rotation -13.74; Move (0.000081, -0.000985, 0.003155) m; final Resize 1.422
- Hand counts: 8 -> 20 -> 32 -> 48 -> 69 -> 117 -> 213 -> 216 -> 225 -> 261 verts; final 261 verts / 523 edges / 264 faces / 518 tris
- After join: Verts 2,950, Faces 2,780, Tris 5,402 (Object Mode, mirror evaluated)
- File name female_char1.blend

Not visible in the frames:
- The UV sphere's segment and ring counts and radius (only the 25-vertex dome after trimming is readable).
- Exactly how the dome was connected to the torso (knife, J connect, or bridge); the frames only show the result.
- What removed one vertex at 00:14:16.
- The axis of the -13.74 thumb rotation and of the -11.8 degree neck rotation (the neck panel says Axis Z in View orientation, which in Right Orthographic is the screen-normal axis).
- How the finger faces were extruded (individual faces or region); and the meaning of "I x2" / "b x2" overlay entries.
- The thumb segment count beyond what the vertex count implies.
- Whether a Subdivision Surface modifier was ever on; none appears in the modifier panel, and the Object Mode count at 00:15:06 (1,465 verts) is for the whole scene.
- How the objects were moved into the "Model" collection at 00:33:16.

## Gaps

- **Add-ons**: `Extra Mesh Objects` (free, Blender extensions) for the round cube; `quad_ball` replaces it.
  `PureRef` for the reference board; `reference_setup` and `turnaround_sheet` replace it. No paid add-on is used.
- **Line Project** has no tool. `plane_squash` flattens to a plane; it does not trim geometry, so remesh after it.
- **Pinch** has no brush; a low-strength `crease` pinches as a side effect.
- **Scrape/Fill** and **Lasso Mask**: see the Gaps in 03-sculpt-face.md.
- `sculpt_strokes` symmetry mirrors about the named object's own local axis. A hand at the end of an angled arm
  has no useful symmetry plane; the course gets both hands from a `Mirror` modifier, so sculpt one hand and keep
  the modifier (or bake it at the end).
- Loop cuts, edge slides and skin-radius edits in Edit Mode are now seen on screen (loop cuts across the palm at
  02:41:58 to 02:42:34, Skin Resize at 02:48:41, stepped toe at 03:31:55) but still have no tool; reproduce the
  result with `skin_digit` points and radii or with `grab`, not key presses.
- Remesh sizes the frames settle (now in the table above): single toe 0.0103, joined foot 0.00642, upper leg 0.0495,
  joined legs 0.0405, finger 0.0114, thumb 0.0106, joined hand 0.0100. Arm remesh previews 0.0526 at 03:54:49; the final
  arm and pelvis, waist, chest, shoulder, neck and torso-join sizes are narrated only (torso 0.03) or not shown. Use the
  size of the neighbouring part for those.
- At 03:54:38 the narrator says "hands" while selecting arm pieces after deleting the placeholders; the frames show
  arm meshes outlined, so the lower-arm reading stays mine.
- Which side of the foot is the upright side of the "right-angled triangle" in front view: the Annotate sketch at
  03:27:38 is not legible. Still open; check your reference.
- Where exactly the foot's side hollows are carved [03:39:54]: still open. The frames at 03:39:40 show only `Inflate`
  on the heel and `Grab`; "behind the ankle bones on both sides" remains my reading.
- Scene scale is never stated, but remesh previews read in metres (finger voxel 0.0114 m) and the figure is human-sized.
  The `part_length/40` voxel rule and all world radii are still mine; use the ring-to-part ratios in the
  on-screen section.
- The course says it refines hands, feet and body further off camera [03:23:00], [03:47:19], [04:13:33]; the
  recorded result is a first pass, so matching the reference to 0.98 will need more grab passes than it shows.
- The Line Project action at 03:29:34 and the navel (`Draw` subtract) at 04:03:55 are not legible in the sampled frames;
  keep the stage's own mappings for both.
