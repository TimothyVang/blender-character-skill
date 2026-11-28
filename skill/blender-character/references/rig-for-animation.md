# Rig for animation

Source for the method: YanSculpts, [3D Character Creation Walkthrough - Part 2 - Rigging and Posing Tifa](https://www.youtube.com/watch?v=vPFRxvsOBb4)
(10 min 45 s, narrated, Blender). It is the only rigging video on the YanSculpts channel; times are marked `YT`.
It is filmed on a phone pointed at a pen display, so panel values cannot be read. Labels:
`annotations/vPFRxvsOBb4/`.

Yan rigs for a **still pose**, and says what changes for animation [YT 01:03]: "you will still need to do a lot of
cleanup especially if you plan to animate as opposed to just posing ... for Tifa we're going to use this just for
posing." He then applies the armature and sculpts every fix into the posed mesh [YT 01:43, 07:50]. That is the
right end for a statue and the wrong end for animation: a mesh with the armature applied can never move again.

This file takes his steps and his list of what breaks, and turns them into a rig that animates. Everything after
"What Yan does" is my own addition, not his: the snapping, the driven correctives, the cycle check, the actions
and the bake. Every code block marked `# verified in 4.5.16 background` was run on a generated Rigify rig with a
skinned test body (numbers in "How it was checked"). Times and the course's own stage file are in
`10-rigging-posing.md`.

## When to read this

After stage 10 steps 1 to 13 (`10-rigging-posing.md`): the Rigify `rig` is generated, the body and parts are bound,
weights and helpers are done, and the stage 10 test poses pass. Read it when the character will **move**: a shot,
a turntable with motion, a game, a loop. For a still render, stage 10 step 14 is enough.

## Posing rig versus animation rig

| | Posing (Yan, stage 10 step 14) | Animation (this file) |
|---|---|---|
| Armature | applied once the pose is final [YT 07:50] | never applied; it stays a live modifier |
| Pose fixes (elbow, fist, hips, cloth) | sculpted straight into the posed mesh with Multires [YT 04:18] | sculpted on a posed *copy*, turned into a shape key the joint switches on |
| Symmetry | lost after the armature is applied [YT 07:50] | kept: the rest mesh is untouched; fix each side as its own key |
| IK and FK | whichever reaches the pose | both, with snapping between them mid-shot |
| Hair, laces, skirt | sculpted to suit the one pose [YT 03:53, 04:05] | must follow every frame: bound to a bone, a helper (stage 10 step 12) or simulated |
| Checked by | looking at one pose | stage 10 test poses, plus a keyed cycle read frame by frame |
| Ends with | a sculpt ready for texturing (his part 3) | named actions on the NLA, optionally a baked copy for export |

## What Yan does [YT 00:34 to 01:42]

1. Adds an armature, "a skeleton for your character": bones go where real joints are [YT 00:37]. He uses Rigify,
   Blender's built-in add-on, rather than building bones by hand [YT 00:50]. On screen: the human metarig appears
   around the A-posed sculpt.
2. Fits the metarig from the side and front, then hips and thighs, then every finger bone inside the hand (all
   seen, values not readable) [YT 00:40 to 01:00]. Stage 10 steps 2 to 5 do the same by measurement.
3. Generates the rig and binds the character to it [YT 01:03]. The coloured IK and FK arm controls and the finger
   controls are visible on the arm [YT 01:20].
4. Moves her around to find bad deformations and corrects them before choosing the pose: he bends an arm and
   raises both arms to a T as a test [YT 01:16 to 01:30].
5. Does a test pose, then pushes it toward a closed-fist fighter stance [YT 01:30 to 01:42].

The rest of the video is the posed-sculpt pass. These are the places where he says the posed body went wrong.
Each one is a corrective an animation rig needs:

| Where it went wrong [YT time] | What he sculpts | Animation fix (step) |
|---|---|---|
| Elbow bent: the olecranon (top of the ulna) shows [02:23] | the elbow point pushed out | `elbow_bend` key on the elbow angle (3) |
| Forearm turning, pronation and supination twist the flexors and extensors [02:35] | the twist in the forearm muscles | Rigify already splits the forearm into `DEF-forearm.L` and `.L.001` for twist; check it (3), key only if it still collapses |
| Fist: knuckles stand out, skin compresses and stretches [03:00, 07:38] | inflated finger sections, knuckles | `fist` key on the finger curl (3) |
| Pelvis twisted and rotated [01:57] | the hip and groin forms | `hip_flex` key on the thigh angle (3) |
| Knees flexed: the knee region changes [06:52] | the knee forms | `knee_bend` key on the knee angle (3) |
| Arms raised: folds run from chest to arm [05:39] | shirt folds | shirt follows the body by copied weights (stage 10 step 11); key the shirt if the folds must change |
| Head tilted: hair rests differently under gravity [03:53] | the hair mass | scalp bound to the head (stage 10 step 11); long hair gets a bone chain or physics (Gaps) |
| Shoes tilted up: laces deform badly [04:05] | the laces | laces rigid on `DEF-foot.L` / `DEF-foot.R` (parent to bone) or follow the boot helper (stage 10 step 12) |
| Skirt [02:47] | the skirt corrections | skirt helper (stage 10 step 12) plus a key on the helper |

## Order of work

### 1. Keep the rig live

Never apply the `Armature` modifier, and never add Multires to a bound mesh to sculpt a pose. Keep `Armature` first
in every stack (stage 10 step 7). Keep the stage 10 file saved; the animation file is a new save on top of it
(`character_10b_anim.blend`). Rigify controls are the only bones you key: names without `DEF-`, `MCH-` or `ORG-`.

### 2. IK and FK, and snapping between them

The limbs have an `IK_FK` switch on `upper_arm_parent.L/R` and `thigh_parent.L/R`: 0 is IK, 1 is FK. Animators
use IK for planted feet and hands on props, FK for swinging arms, and switch mid-shot. Switching without snapping
makes the limb jump. Rigify ships snap buttons in its N panel, but each operator's name carries the rig's id
(`pose.rigify_limb_ik2fk_<rig_id>`, different for every generated rig) and takes the bone lists as JSON strings.
`snap_args` reads both from the rig's own `rig_ui.py`, so it always matches the rig.

```python
# verified in 4.5.16 background
import ast, math, re, statistics
import bpy
from mathutils import Matrix, Vector as V

def snap_args(rig, label):
    """Operator name and properties behind a button of the rig's Rigify panel, read from rig_ui.py.
    label: 'IK->FK (hand.L)', 'FK->IK (hand.L)', 'IK->FK (foot.R)', ..."""
    src = bpy.data.texts["rig_ui.py"].as_string().splitlines()
    for i, line in enumerate(src):
        m = re.search(r"operator\('pose\.(rigify_\w+)', text='" + re.escape(label) + "'", line)
        if m:
            props = {}
            for nxt in src[i + 1:]:
                p = re.match(r"\s*props\.(\w+) = (.+)$", nxt)
                if not p: break
                props[p.group(1)] = ast.literal_eval(p.group(2))
            return m.group(1), props
    raise KeyError(f"no Rigify button {label!r} in rig_ui.py")

def snap(rig, label):
    """Press a Rigify snap button, then hand the limb to the side that was snapped onto: 'IK->FK (hand.L)' moves
    the IK controls onto the FK pose and switches the arm to IK; 'FK->IK (hand.L)' the reverse. Rigify's own
    button only matches the pose; it leaves the IK_FK switch where it was."""
    op_name, props = snap_args(rig, label)
    with bpy.context.temp_override(active_object=rig, object=rig):
        getattr(bpy.ops.pose, op_name)(**props)
    prop_bone = snap_args(rig, "IK->FK " + label.split(" ", 1)[1])[1]["prop_bone"]
    rig.pose.bones[prop_bone]["IK_FK"] = 0.0 if label.startswith("IK->FK") else 1.0
    bpy.context.view_layer.update()

def org_matrices(rig, names):
    return {n: (rig.matrix_world @ rig.pose.bones[n].matrix).copy() for n in names}

def matrix_gap(a, b):
    """Largest distance between bone heads and tails (metres) of two matrix sets on the same bones."""
    return max(max((a[n].to_translation() - b[n].to_translation()).length,
                   ((a[n] @ V((0, 1, 0, 0))).xyz - (b[n] @ V((0, 1, 0, 0))).xyz).length) for n in a)
```

Labels are the panel's: `IK->FK (hand.L)`, `FK->IK (hand.L)`, `IK->FK (foot.L)`, `FK->IK (foot.L)`, and the same
with `.R`. Check each snap with the `ORG-` bones, which follow whichever side is in charge:
`before = org_matrices(rig, ["ORG-upper_arm.L", "ORG-forearm.L", "ORG-hand.L"])`, snap, then
`matrix_gap(before, org_matrices(rig, [...]))` must be under 0.001 m. To snap on a keyed frame, key the controls of
the side you switched to on that frame (step 4, `key_controls`) so the next frames do not drift back.

### 3. Correctives: sculpt on a posed copy, drive by the joint

This is Yan's posed-sculpt pass made reusable. For each row of the table above:

1. Pose the joint to its extreme (FK is easiest: `rotate_local` from stage 10 step 8), with Simplify on.
2. `posed_copy(body, "body_pose_fix")` makes a plain mesh of the body in that pose, vertex for vertex.
3. Sculpt the fix on the copy with `sculpt_strokes` (it refuses meshes with shape keys, so the copy has none). Only
   the area of the fix should move. Look at it with `viewport_capture` and against your own hand or a photo, as Yan
   does [YT 03:13].
4. `corrective_from_posed(body, fixed, "elbow_bend.L")` writes a rest-space shape key that reproduces the copy in
   this pose. It solves each vertex numerically, so it works with Rigify's B-bones. Then delete the copy.
5. `drive_by_angle(...)` switches the key on with the joint: 0 at rest, 1 at the posed angle. It reads the angle
   between two `ORG-` bones, so it works the same in IK and FK. The driver is a simple expression, so it runs even
   when the file's Python scripts are not trusted (`Auto Run Python Scripts` off).

```python
# verified in 4.5.16 background
def drive_by_angle(mesh, key_name, rig, bone_a, bone_b, rest_deg, full_deg):
    """Key goes 0 -> 1 as the angle between bone_a and bone_b grows from rest_deg to full_deg.
    Reads ORG- bones, so it follows the limb whether IK or FK is driving it."""
    kb = mesh.data.shape_keys.key_blocks[key_name]
    kb.driver_remove("value")
    fc = kb.driver_add("value")
    for m in list(fc.modifiers): fc.modifiers.remove(m)
    d = fc.driver
    d.type = "SCRIPTED"
    var = d.variables.new()
    var.name, var.type = "a", "ROTATION_DIFF"
    var.targets[0].id, var.targets[0].bone_target = rig, bone_a
    var.targets[1].id, var.targets[1].bone_target = rig, bone_b
    r0, r1 = math.radians(rest_deg), math.radians(full_deg)
    d.expression = f"clamp((a - {r0:.5f}) / {r1 - r0:.5f}, 0, 1)"
    return d.is_simple_expression          # True: runs without trusting Python scripts in the file

def joint_angle(rig, bone_a, bone_b):
    qa = (rig.matrix_world @ rig.pose.bones[bone_a].matrix).to_quaternion()
    qb = (rig.matrix_world @ rig.pose.bones[bone_b].matrix).to_quaternion()
    a = math.degrees(qa.rotation_difference(qb).angle) % 360
    return min(a, 360 - a)                 # 0..180, the same range the ROTATION_DIFF driver reads

def _armature_only(mesh):
    saved = {m.name: m.show_viewport for m in mesh.modifiers}
    for m in mesh.modifiers: m.show_viewport = m.type == "ARMATURE"
    return saved

def posed_points(mesh):
    ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    pts = [v.co.copy() for v in me.vertices]          # object space, after the armature
    ev.to_mesh_clear()
    return pts

def posed_copy(mesh, name):
    """A plain mesh of the body as it stands in the current pose, to sculpt the fix on (sculpt_strokes refuses
    meshes with shape keys). Same vertex order as the body."""
    saved = _armature_only(mesh); bpy.context.view_layer.update()
    me = bpy.data.meshes.new_from_object(mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    for n, s in saved.items(): mesh.modifiers[n].show_viewport = s
    ob = bpy.data.objects.new(name, me)
    ob.matrix_world = mesh.matrix_world.copy()
    for c in mesh.users_collection: c.objects.link(ob)
    return ob

def corrective_from_posed(mesh, fixed, key_name, iterations=4, eps=1e-3):
    """Turn a sculpted copy of the posed body into a rest-space shape key that reproduces it in this pose.
    The armature moves each vertex by (nearly) an affine map, so solve it per vertex: probe x, y, z with
    small offsets in the key, read the posed result, invert the 3x3, repeat. Key value is left at 1."""
    if mesh.data.shape_keys is None: mesh.shape_key_add(name="Basis", from_mix=False)
    kb = mesh.data.shape_keys.key_blocks.get(key_name) or mesh.shape_key_add(name=key_name, from_mix=False)
    keys = mesh.data.shape_keys.key_blocks
    saved_vals = {k.name: (k.value, k.mute) for k in keys}
    drv = mesh.data.shape_keys.animation_data
    muted = []
    if drv:
        for fc in drv.drivers:
            if not fc.mute: fc.mute = True; muted.append(fc)
    for k in keys:
        if k.name != "Basis": k.value = 0.0
    kb.value, kb.mute = 1.0, False
    saved_mods = _armature_only(mesh)
    target = [v.co.copy() for v in fixed.data.vertices]
    basis = [p.co.copy() for p in keys["Basis"].data]
    for p, b in zip(kb.data, basis): p.co = b.copy()

    def evaluate():
        mesh.data.update(); bpy.context.view_layer.update()
        return posed_points(mesh)

    for _ in range(iterations):
        cur = [p.co.copy() for p in kb.data]
        base = evaluate()
        cols = []
        for axis in range(3):
            d = V((0, 0, 0)); d[axis] = eps
            for p, c in zip(kb.data, cur): p.co = c + d
            cols.append([(q - b) / eps for q, b in zip(evaluate(), base)])
        for i, p in enumerate(kb.data):
            J = Matrix((cols[0][i], cols[1][i], cols[2][i])).transposed()
            try: step = J.inverted() @ (target[i] - base[i])
            except ValueError: step = target[i] - base[i]
            p.co = cur[i] + step
    final = evaluate()
    err = max((a - b).length for a, b in zip(final, target))
    for n, s in saved_mods.items(): mesh.modifiers[n].show_viewport = s
    for k in keys:
        if k.name in saved_vals and k.name != key_name: k.value, k.mute = saved_vals[k.name]
    for fc in muted: fc.mute = False
    return {"key": key_name, "max_error": round(err, 6),
            "moved_verts": sum(1 for p, b in zip(kb.data, basis) if (p.co - b).length > 1e-5)}
```

One elbow, start to end:

```python
# verified in 4.5.16 background
rest = joint_angle(rig, "ORG-upper_arm.L", "ORG-forearm.L")            # 21.5 deg on the test rig: the A-pose bend
rig.pose.bones["upper_arm_parent.L"]["IK_FK"] = 1.0
rig.pose.bones["forearm_fk.L"].rotation_quaternion = Matrix.Rotation(math.radians(110), 4, "X").to_quaternion()
bpy.context.view_layer.update()
full = joint_angle(rig, "ORG-upper_arm.L", "ORG-forearm.L")            # 131.5 deg
fixed = posed_copy(body, "body_pose_fix")
# ... sculpt the olecranon on `fixed` with sculpt_strokes ...
print(corrective_from_posed(body, fixed, "elbow_bend.L"))              # max_error must be under 0.0005 m
assert drive_by_angle(body, "elbow_bend.L", rig, "ORG-upper_arm.L", "ORG-forearm.L", rest, full)
bpy.data.objects.remove(fixed)
```

Which bones drive which key (left side; mirror the names for `.R`, and sculpt each side as its own key):

| Key | `bone_a`, `bone_b` | Posed angle to sculpt at |
|---|---|---|
| `elbow_bend.L` | `ORG-upper_arm.L`, `ORG-forearm.L` | about 130 deg |
| `knee_bend.L` | `ORG-thigh.L`, `ORG-shin.L` | about 120 deg (stage 10 `knees_deep`) |
| `hip_flex.L` | `ORG-spine`, `ORG-thigh.L` | thigh raised 90 deg |
| `shoulder_up.L` | `ORG-spine.003`, `ORG-upper_arm.L` | arm raised (stage 10 `arms_up`) |
| `fist.L` | `ORG-hand.L`, `ORG-f_middle.02.L` | fingers closed (scale `f_middle.01_master.L` as in stage 10 step 5) |

Rules:

- Always measure the rest angle with `joint_angle` at the rest pose; never assume 0. Bone roll counts in the
  angle: the fist pair reads 92 degrees at rest and 144 with the middle finger closed (test rig).
- Sculpt only the change the pose makes (the bone pushing out, the skin folding), not new detail. Detail belongs
  in the rest mesh, where every frame gets it.
- One key per joint per side. Each is solved with every other key off; when two fire together (elbow and
  shoulder) they add, so check the combined pose and soften the overlap if it doubles up.
- Forearm twist: rotate `hand_fk.L` 80 degrees about its own Y and run stage 10 `pose_report`. If the forearm's
  `volume_ratio` drops under 0.90, the twist is collapsing; make a `forearm_twist.L` key the same way, driven by
  the angle between `ORG-forearm.L` and `ORG-hand.L`.
- The keys must be 0 at rest. If `drive_by_angle` gets the rest angle from a pose that is not the rest pose, the
  rest mesh changes and stage 10 exit check 6 fails.

### 4. A test cycle, read frame by frame

Stage 10's test poses check single poses. Animation also breaks between poses: a limb flips when IK passes through
straight, a corrective pops on, a cycle does not close. Key a short cycle on the controls and read the deformed body
on every frame.

```python
# verified in 4.5.16 background
def key_controls(rig, bones, frame):
    for n in bones:
        pb = rig.pose.bones[n]
        rot = "rotation_quaternion" if pb.rotation_mode == "QUATERNION" else \
              "rotation_axis_angle" if pb.rotation_mode == "AXIS_ANGLE" else "rotation_euler"
        for path in ("location", rot, "scale"):
            pb.keyframe_insert(path, frame=frame, group=n)

def action_fcurves(action, slot=None):
    """F-curves of an action in 4.4+ (slotted actions) and earlier."""
    try:
        from bpy_extras.anim_utils import action_get_channelbag_for_slot
        slot = slot or (action.slots[0] if len(action.slots) else None)
        bag = action_get_channelbag_for_slot(action, slot) if slot else None
        return list(bag.fcurves) if bag else []
    except ImportError:
        return list(action.fcurves)

def make_cyclic(action):
    for fc in action_fcurves(action):
        if not any(m.type == "CYCLES" for m in fc.modifiers): fc.modifiers.new("CYCLES")
        for k in fc.keyframe_points: k.interpolation = "BEZIER"

def motion_report(mesh, start, end):
    """Per frame: how far the worst vertex moved since the previous frame. A pop is a frame whose step is far
    above its neighbours; a loop that does not close shows as a large step from the last frame to the first."""
    sc = bpy.context.scene
    saved = _armature_only(mesh)
    frames = list(range(start, end + 1))
    pts = []
    for f in frames:
        sc.frame_set(f); pts.append([mesh.matrix_world @ p for p in posed_points(mesh)])
    for n, s in saved.items(): mesh.modifiers[n].show_viewport = s
    steps = [max((a - b).length for a, b in zip(pts[i], pts[i - 1])) for i in range(1, len(pts))]
    med = statistics.median(steps) or 1e-9
    worst = max(range(len(steps)), key=lambda i: steps[i])
    sc.frame_set(start)
    return {"frames": [start, end], "median_step": round(med, 5), "max_step": round(steps[worst], 5),
            "max_step_frame": frames[worst + 1], "pop_ratio": round(steps[worst] / med, 2),
            "loop_gap": round(max((a - b).length for a, b in zip(pts[0], pts[-1])), 5)}
```

The test cycle: a 24-frame arm and leg swing in FK, keys on frames 1, 13 and 25 (25 repeats frame 1), so a full
loop is 1 to 25 at 24 fps.

```python
# verified in 4.5.16 background
sc = bpy.context.scene; sc.render.fps = 24; sc.frame_start, sc.frame_end = 1, 24
pb = rig.pose.bones
for n in ("upper_arm_parent.L", "upper_arm_parent.R", "thigh_parent.L", "thigh_parent.R"): pb[n]["IK_FK"] = 1.0
for f, deg in {1: 30, 13: -30, 25: 30}.items():
    for s, sign in (("L", 1), ("R", -1)):
        pb[f"upper_arm_fk.{s}"].rotation_quaternion = Matrix.Rotation(math.radians(deg * sign), 4, "X").to_quaternion()
        pb[f"thigh_fk.{s}"].rotation_quaternion = Matrix.Rotation(math.radians(-deg * sign), 4, "X").to_quaternion()
    key_controls(rig, [f"upper_arm_fk.{s}" for s in "LR"] + [f"thigh_fk.{s}" for s in "LR"], f)
make_cyclic(rig.animation_data.action)
print(motion_report(body, 1, 25))
```

Read it: `loop_gap` under 0.001 m (the loop closes); `pop_ratio` under 2.5. Above that, look at `max_step_frame`
with `viewport_capture(frame=...)` and the frame before it. On the test rig a clean swing scored 1.38; the same
swing with a forearm snapped 70 degrees for one frame scored 4.17 at that frame. The 2.5 limit is mine. A real walk
eases in and out, so its median step is smaller; judge `pop_ratio` with a capture, not alone. Then
`motion_preview(frames=[1, 4, 7, 10, 13, 16, 19, 22])` with every part visible: clothes, hair and helpers must
follow on every frame, not just on the keyed ones.

Also run the cycle once in IK: plant `foot_ik.L/R` (`IK_FK` 0), move `torso` down 5 percent of the height and back
over the cycle. Knees must not flip sideways as they straighten; if they do, the metarig knee bend is too small
(stage 10 step 3) or the IK pole needs `pole_vector` on (`thigh_parent.L["pole_vector"] = 1`, then place
`thigh_ik_target.L` in front of the knee).

### 5. Actions and the NLA

Each motion is its own action, named for what it is (`walk`, `idle`, `wave`). Keep every action with a fake user
so it survives being unused, and stack them on the NLA so they can be played one at a time or combined.

```python
# verified in 4.5.16 background
def stash_action(rig, name):
    """Name the current action, keep it when unused, and push it down to its own NLA track."""
    ad = rig.animation_data
    act = ad.action
    act.name, act.use_fake_user = name, True
    slot = getattr(ad, "action_slot", None)
    track = ad.nla_tracks.new(); track.name = name
    strip = track.strips.new(name, int(act.frame_range[0]), act)
    if slot is not None and hasattr(strip, "action_slot"): strip.action_slot = slot
    ad.action = None
    track.mute = True                     # solo it (or unmute) to play it; keeps stacked clips from adding up
    return strip

def play_action(rig, name):
    ad = rig.animation_data or rig.animation_data_create()
    for t in ad.nla_tracks: t.mute = True
    ad.action = bpy.data.actions[name]
    if hasattr(ad, "action_slot") and len(ad.action.slots): ad.action_slot = ad.action.slots[0]
```

`stash_action(rig, "walk")`, then key the next motion; `play_action(rig, "walk")` to work on it again. Blender 4.4
and later store keys in slotted actions; the functions handle both. The stage 10 test poses and the two
presentation poses are actions too: stash them as `test_poses` and `poses`.

### 6. Bake for export (only when it leaves Blender)

The Rigify rig is 918 bones of constraints and drivers; an exporter or game engine reads none of that. Bake a copy:
every bone gets plain keys, no constraints, and the rig you animate with stays as it is.

```python
# verified in 4.5.16 background
def bake_deform_copy(rig, start, end, name="rig_baked"):
    """A copy of the rig whose every bone carries plain baked keys and no constraints: what an exporter or a
    game engine can read. The original rig and its controls stay untouched."""
    copy = rig.copy(); copy.data = rig.data.copy(); copy.name = name
    copy.animation_data_clear()
    for c in rig.users_collection: c.objects.link(copy)
    copy.animation_data_create()
    copy.animation_data.action = rig.animation_data.action
    if hasattr(copy.animation_data, "action_slot") and rig.animation_data.action_slot:
        copy.animation_data.action_slot = rig.animation_data.action_slot
    if bpy.context.object and bpy.context.object.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    copy.select_set(True); bpy.context.view_layer.objects.active = copy
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.nla.bake(frame_start=start, frame_end=end, only_selected=False, visual_keying=True,
                     clear_constraints=True, clear_parents=False, use_current_action=False,
                     bake_types={"POSE"})
    bpy.ops.object.mode_set(mode="OBJECT")
    copy.animation_data.action.name = name + "_action"
    return copy
```

Play the action to bake first (`play_action`). Check: no constraints left on the copy, and on a few frames each
`DEF-` bone of the copy sits where the live rig's does (under 0.001 m). The copy still has every Rigify bone;
reducing it to a clean deform-only skeleton, renaming for an engine, and what does not export (Surface Deform,
Mask, drivers) are in stage 10 "For a game engine later". The shape keys export as morph targets; their drivers
do not, so an engine has to drive the correctives itself, or they are baked to keys on the mesh.

## How it was checked

Blender 4.5.16, background, factory settings: the `Human` metarig with the face upgraded, generated (918 bones),
and a test body of capped tubes along the spine, arms and legs (2,640 vertices, a ring every 2 cm) bound with
automatic weights. The test body's head is a plain tube with no face, so face bones were set not to deform for the
test. A first test body built with the Skin modifier failed bone heat weighting outright (every vertex unweighted);
the tube body bound cleanly. A real character is bound as in stage 10 step 7.

The seven code blocks above were also run exactly as written, pulled out of this file, in order, on that rig and
body (with a scripted 1 cm push standing in for the sculpt): elbow key 21.5 to 131.5 degrees, 0.0 at rest and 1.0
bent; snap gap 0.000 m; cycle `loop_gap` 0.0, `pop_ratio` 1.38; bake left 0 constraints. Every bone name in the
tables exists in the generated rig.

| Check | Result |
|---|---|
| `IK->FK` and `FK->IK (hand.L)`, `IK->FK (foot.L)`: `ORG-` gap after the snap | 0.000 m each; `IK_FK` ends 0, 1, 0 |
| `corrective_from_posed` on a 1 cm olecranon push (60 vertices) | `max_error` 0.000 m, 60 vertices in the key, 0.15 s |
| Driver at rest, half bend, full bend (FK) | 0.0, 0.5, 1.0; `is_simple_expression` True |
| Same bend reached through IK after a snap | key 0.999; body 2 mm from the sculpt (IK gives the forearm a slightly different twist) |
| Swing cycle 1 to 25 | `loop_gap` 0.0, `pop_ratio` 1.38; with a one-frame 70 deg snap, 4.17 at that frame |
| `stash_action`, then `play_action`, and the NLA strip alone | hand 0.000 m from the keyed pose |
| `bake_deform_copy` 1 to 25 | 0 constraints, DEF bones 0.000 m from the live rig on frames 1, 4, 7, 13, 19 |

Not checked: a full character with clothes and hair, Yan's own scene, and how the correctives look (only that they
reproduce the sculpt and switch on and off).

## Exit check

1. Stage 10 exit check still passes, with every corrective in place.
2. Snapping: for both arms and both legs, `IK->FK` then `FK->IK` leaves `matrix_gap` under 0.001 m.
3. Every corrective: `max_error` under 0.0005 m, `drive_by_angle` returned True, value 0.0 at rest and at least
   0.99 at its pose in FK **and** in IK.
4. Frame 1 at rest still gives the stage 09 `outline_match` result (the correctives are 0 at rest).
5. The test cycle: `loop_gap` under 0.001 m and `pop_ratio` under 2.5, plus the IK knee check, plus a
   `motion_preview` sheet with all parts visible. A sheet that was not made counts as not checked.
6. Every action named, fake user on, on its own NLA track; `play_action` brings back the same pose.
7. If exporting: the baked copy has no constraints and its `DEF-` bones sit within 0.001 m of the live rig.

## Gaps

- Yan's video stops at posing; nothing here about animation is from him. The snapping, correctives, cycle check,
  actions and bake are mine, checked on a test body, not on a finished character.
- He sculpts corrections by hand with a pen. Here that is `sculpt_strokes` on a posed copy, which is coarser.
- How a corrective *looks* is judged by eye, with your own hand or a mirror as reference, as he does
  [YT 03:13, 06:59]; `max_error` only proves the key reproduces the sculpt.
- Long hair, ponytails, capes, the skirt's swing: secondary motion needs a bone chain (Rigify `basic.copy_chain`
  or a spline IK chain) or a simulation. Not covered.
- Face animation (lip sync, expressions) beyond the stage 10 eyelid key: not covered.
- Rigify's own Action and Clear buttons beside each snap button bake a snap across a frame range; not scripted
  here.
