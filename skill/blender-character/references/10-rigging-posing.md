# 10 Rigging and posing

Course source: chapter 13 "Rigging & Posing Your Character", 17:25:10 to 19:05:43.
The course records in Blender 5.0.1; everything below is written and checked for Blender 4.5.16.

## Goal

The character has a Rigify control rig (`rig`) generated from a fitted `metarig`. The body follows it through
weights; eyes, teeth, tongue, hair, clothes and boots follow it too, each by the method that suits the part. A fixed
set of test poses deforms without spikes, collapsed joints or parts left behind, and at least two presentation
poses are stored.

If the character will be animated, not only posed, continue with `rig-for-animation.md` (stage 10b) after step 13:
IK/FK snapping, corrective shape keys driven by the joints, a test cycle checked frame by frame, actions on the NLA
and a baked copy for export. Do not apply the armature or sculpt a pose into the bound mesh in that case.

## Starting state

- Finished, textured meshes in a neutral A-pose or T-pose, facing -Y, feet on Z = 0, object scale applied
  (`bpy.ops.object.transform_apply(scale=True)`); the course's character is in an A-pose [17:43:28].
- Names follow SKILL.md: `body_retopo`, `Eye.L`, `Eye.R` (each with its cornea), `Mouth` (teeth, gums, tongue),
  the scalps `hair_scalp`, `brow_scalp`, `lashes_scalp` and any ponytail scalp, `Hair.Band`, `Shirt_retopo`,
  `Skirt_retopo`, `Boot.L_retopo`, `Boot.R_retopo`, all under `CHARACTER`. The course's own names at this point are
  `GEO_<name>_<part>` (it renames in its shading chapter); this skill keeps the names above. Rigify needs no
  particular mesh names.
- Body and clothes carry only a light `Subdivision` modifier (sculpt detail was baked to normal maps in stage 09).

## Order of work

### 1. Collections and a fast viewport [17:42:02]

The course makes two child collections under `CH_<name>`: `CH_<name>_rig` (armatures and helpers) and
`CH_<name>_model` (all geometry, including the cloth and hair-scalp collections). Later it adds
`CH_<name>_rig_helpers` inside the rig collection [18:50:20].

Posing a subdivided, haired character is slow. The course turns on `Render Properties > Simplify` with
`Max Subdivision` 0 while rigging and posing, and lowers the hair `Viewport Amount` (0.02) [18:17:19, 18:48:41]:
`bpy.context.scene.render.use_simplify = True; bpy.context.scene.render.simplify_subdivision = 0`.
Turn Simplify off again before any render.
On screen he also right-clicks the `Use Simplify` checkbox and adds it to Quick Favorites, so `Q` toggles it in the
viewport while posing [18:17:35 to 18:17:50].

### 2. Add the Rigify human metarig [17:32:17, 17:43:10]

Rigify ships with Blender (free). It gives a template skeleton, the metarig, that you fit to the character; from it
Rigify generates the full control rig with controls, mechanism bones and deform bones. The course uses
`Add > Armature > Rigify Meta-Rigs > Human`. Before generating, the course clicks `Upgrade Face Rig` on the warning
shown in the Rigify panel, which swaps the old face rig for the newer one and adds bones such as `jaw_master`
[18:04:15]. Do the upgrade first, so the bones you fit are the final set.

```python
# verified in 4.5.16 background
import bpy, bmesh, math
from mathutils import Vector as V, Matrix

def add_metarig(collection_name):
    bpy.ops.preferences.addon_enable(module="rigify")
    col = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
    if col.name not in bpy.context.scene.collection.children_recursive:
        bpy.context.scene.collection.children.link(col)
    bpy.ops.object.armature_human_metarig_add()            # object "metarig", 159 bones
    meta = bpy.context.object
    for c in list(meta.users_collection): c.objects.unlink(meta)
    col.objects.link(meta)
    meta.show_in_front = True                              # bones stay visible through the mesh [17:44:16]
    bpy.context.view_layer.objects.active = meta
    bpy.ops.pose.rigify_upgrade_face()                     # now 174 bones, with jaw_master and nose_master
    return meta
```

### 3. Measure the landmarks on the mesh

The course places bones by eye in front and side views and reads each bone's name to know what it is for
[17:45:14]. You cannot drag, so measure instead. A joint belongs at the centre of the limb's cross-section, not on
the skin. `band` returns the box and centre of the vertices inside a region; slice a leg by height, an A-pose arm by
X. Check each number against a `viewport_capture(view="FRONT")` and `view="RIGHT"` before using it.

```python
# verified in 4.5.16 background
def band(obj, zmin, zmax, xmin=-1e9, xmax=1e9, ymin=-1e9, ymax=1e9):
    mw = obj.matrix_world
    pts = [p for p in (mw @ v.co for v in obj.data.vertices)
           if zmin <= p.z <= zmax and xmin <= p.x <= xmax and ymin <= p.y <= ymax]
    if not pts: return None
    lo, hi = (V([f(p[i] for p in pts) for i in range(3)]) for f in (min, max))
    return {"min": tuple(lo), "max": tuple(hi), "centre": tuple((lo + hi) / 2), "count": len(pts)}
```

Fill a dictionary `L` of world-space points, left side only (+X is the character's left):

| Key | Where it is | Bones it drives |
|---|---|---|
| `crown` | top of the skull (not the hair) | height scale, `spine.006` tail |
| `hips` | centre of the pelvis at hip-joint height, X = 0 | `spine` head, `pelvis.L/R` |
| `chest` | centre of the ribcage, X = 0 | middle of the spine curve, `breast.L/R` |
| `neck` | centre of the neck at its base | `spine.003` tail, `spine.004` head |
| `head` | centre of the neck where it meets the skull | `spine.005` tail, `spine.006` and `face` head |
| `shoulder`, `elbow`, `wrist` | centres of the arm's cross-section | `upper_arm.L`, `forearm.L`, `hand.L` |
| `hand_end` | base knuckle of the middle finger | `hand.L` tail |
| `hip`, `knee`, `ankle` | centres of the leg's cross-section | `thigh.L`, `shin.L`, `foot.L` head |
| `ball`, `toe_tip` | where the toes hinge; tip of the shoe | `foot.L` tail, `toe.L` |
| `heel` | back-bottom of the heel on the floor (Z = floor) | `heel.02.L` (pivot for foot roll) [17:47:20] |
| `heel_half_width` | half the width of the sole (a number) | length of `heel.02.L` |
| `fingers` | `{"f_index": (base knuckle, fingertip), "f_middle": ..., "f_ring": ..., "f_pinky": ..., "thumb": ...}` | finger chains |
| `hand_back` | unit vector pointing out of the back of the hand | finger bend and roll |
| `eye` | centre of the left eyeball object | `eye.L` |
| `face_min`, `face_max` | box from ear to ear (X), nose tip to back of the ear (Y), chin to hairline (Z) | every bone under `face` |

Two rules from the course decide whether the limbs work at all:

- Leave a slight bend at the knee and the elbow. Rigify reads the bend to know which way the joint folds; a
  perfectly straight leg can fold the wrong way [17:48:06]. Knee slightly forward (-Y) of the hip-to-ankle line,
  elbow slightly behind (+Y) the shoulder-to-wrist line.
- Fit the metarig in Edit Mode. Never scale or move the metarig object; its object transform must stay at
  identity or the generated rig inherits the offset [17:43:36].

### 4. Fit the metarig [17:43:36 to 18:04:50]

Course order: scale all bones to the character's height; spine and legs first, viewed from the side; foot, toe and
heel; neck and head; breast bones; shoulder following the collarbone, then elbow and wrist; fingers; face; eye,
tongue and teeth last because they are easy to forget [18:02:58]. It works on one side with X-Axis Mirror on.

Many metarig bones only touch (their ends share a point without being connected). Dragging one end pulls them
apart, and Rigify then refuses to generate; the course box-selects the joint so every end moves together
[17:46:09, 17:57:00]. In a script, read every position before writing any, and map equal points to equal points.
That is what `apply_map` and `move_joint` do. (I hit this for real: a naive loop that scaled each bone in turn
moved shared ends twice, and generation failed with `Could not match control node for ORG-brow_glue.B.L.002`.)

```python
# verified in 4.5.16 background
def edit_bones(meta):
    if bpy.context.object and bpy.context.object.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    meta.hide_set(False); meta.select_set(True)
    bpy.context.view_layer.objects.active = meta
    bpy.ops.object.mode_set(mode="EDIT")
    return meta.data.edit_bones

def apply_map(bones, f):
    key = lambda p: (round(p.x, 5), round(p.y, 5), round(p.z, 5))
    done = {}
    for b in bones:
        for p in (b.head, b.tail): done.setdefault(key(p), None)
    for b in bones:
        for p in (b.head, b.tail):
            if done[key(p)] is None: done[key(p)] = V(f(p.copy()))
    new = [(b, done[key(b.head)], done[key(b.tail)]) for b in bones]     # read all, then write all
    for b, h, t in new: b.head, b.tail = h, t

def move_joint(ebs, bone, end, new, eps=1e-4):
    old = getattr(ebs[bone], end).copy()
    for eb in ebs:                                         # every bone end sitting on this joint
        if (eb.head - old).length < eps: eb.head = V(new)
        if (eb.tail - old).length < eps: eb.tail = V(new)

def under(ebs, root):
    out, todo = [], [ebs[root]]
    while todo:
        b = todo.pop(); out.append(b); todo.extend(b.children)
    return out

def fit_metarig(meta, L):
    ebs = edit_bones(meta)
    P = {k: V(v) for k, v in L.items() if k not in ("fingers", "heel_half_width")}
    k = P["crown"].z / max(b.tail.z for b in ebs)
    apply_map(list(ebs), lambda p: p * k)                  # scale in Edit Mode; object scale stays 1 [17:43:36]
    face = under(ebs, "face")
    # spine: four bones along hips -> chest -> neck, keeping the metarig's own spacing
    names = ["spine", "spine.001", "spine.002", "spine.003"]
    lens = [ebs[n].length for n in names]
    a, b = (P["chest"] - P["hips"]).length, (P["neck"] - P["chest"]).length
    def along(t):
        d = t * (a + b)
        return P["hips"].lerp(P["chest"], d / a) if d <= a else P["chest"].lerp(P["neck"], (d - a) / b)
    d_hips, chest_old = P["hips"] - ebs["spine"].head, ebs["spine.003"].head.copy()
    ebs["spine"].head = P["hips"]
    apply_map([ebs["pelvis.L"], ebs["pelvis.R"]], lambda p: p + d_hips)
    acc = 0.0
    for n, ln in zip(names, lens):
        acc += ln
        move_joint(ebs, n, "tail", along(acc / sum(lens)))
    d_chest = ebs["spine.003"].head - chest_old
    apply_map([ebs["breast.L"], ebs["breast.R"]], lambda p: p + d_chest)
    # neck (two bones), head, face block
    ebs["spine.004"].head = P["neck"]
    move_joint(ebs, "spine.004", "tail", P["neck"].lerp(P["head"], 0.5))
    move_joint(ebs, "spine.005", "tail", P["head"])
    ebs["spine.006"].tail = P["crown"]
    pts = [p for e in face for p in (e.head, e.tail)]
    lo, hi = (V([f(p[i] for p in pts) for i in range(3)]) for f in (min, max))
    apply_map(face, lambda p: V([P["face_min"][i] + (p[i] - lo[i]) / (hi[i] - lo[i]) * (P["face_max"][i] - P["face_min"][i])
                                 for i in range(3)]))
    for e in face:                                         # centre-line bones stay on the centre line [17:58:41]
        if ".L" not in e.name and ".R" not in e.name: e.head.x = e.tail.x = 0.0
    ebs["face"].head, ebs["face"].tail = P["head"], P["head"].lerp(P["crown"], 0.45)
    r = ebs["eye.L"].length                                # eye bone: eyeball centre, pointing straight forward [18:02:00]
    ebs["eye.L"].head, ebs["eye.L"].tail = P["eye"], P["eye"] + V((0, -r, 0))
    # leg and foot
    ebs["thigh.L"].head = P["hip"]
    move_joint(ebs, "thigh.L", "tail", P["knee"]); move_joint(ebs, "shin.L", "tail", P["ankle"])
    move_joint(ebs, "foot.L", "tail", P["ball"]); ebs["toe.L"].tail = P["toe_tip"]
    w = L.get("heel_half_width", 0.04 * k)
    ebs["heel.02.L"].head, ebs["heel.02.L"].tail = P["heel"] - V((w, 0, 0)), P["heel"] + V((w, 0, 0))
    # shoulder, arm, hand; the palm and finger bones ride along with the hand bone
    hand = under(ebs, "hand.L")[1:]
    a0, a1 = ebs["hand.L"].head.copy(), ebs["hand.L"].tail.copy()
    sh = ebs["shoulder.L"]
    sh.head = P["clavicle"] if "clavicle" in P else P["neck"] + V((0.018, -0.079, -0.053)) * k
    sh.tail = sh.head.lerp(P["shoulder"], 0.88)
    ebs["upper_arm.L"].head = P["shoulder"]
    move_joint(ebs, "upper_arm.L", "tail", P["elbow"]); move_joint(ebs, "forearm.L", "tail", P["wrist"])
    ebs["hand.L"].tail = P["hand_end"]
    rot = (a1 - a0).rotation_difference(P["hand_end"] - P["wrist"]).to_matrix()
    s = (P["hand_end"] - P["wrist"]).length / (a1 - a0).length
    apply_map(hand, lambda p: P["wrist"] + rot @ (p - a0) * s)
    # fingers: straight line knuckle -> tip, middle joints lifted 2% toward the back of the hand, Z axes to the palm
    back = P["hand_back"].normalized()
    palms = {"f_index": "palm.01.L", "f_middle": "palm.02.L", "f_ring": "palm.03.L", "f_pinky": "palm.04.L"}
    for finger, (base, tip) in L.get("fingers", {}).items():
        chain = [ebs[f"{finger}.0{i}.L"] for i in (1, 2, 3)]
        base, tip, total, acc = V(base), V(tip), sum(c.length for c in chain), 0.0
        pts = [base.copy()]
        for c in chain:
            acc += c.length; pts.append(base.lerp(tip, acc / total))
        for i in (1, 2): pts[i] += back * (tip - base).length * 0.02
        for i, c in enumerate(chain):
            c.head, c.tail = pts[i], pts[i + 1]; c.align_roll(-back)
        if finger in palms: ebs[palms[finger]].tail = base
    for eb in ebs:                                         # mirror left onto right
        o = ebs.get(eb.name.replace(".L", ".R")) if ".L" in eb.name else None
        if o: o.head, o.tail, o.roll = eb.head * V((-1, 1, 1)), eb.tail * V((-1, 1, 1)), -eb.roll
    bpy.ops.object.mode_set(mode="OBJECT")
    return check_metarig(meta)

def check_metarig(meta):
    b, out = meta.data.bones, {}
    for s in ("L", "R"):
        hip, knee, ank = b["thigh." + s].head_local, b["shin." + s].head_local, b["shin." + s].tail_local
        out["knee_forward_" + s] = round(hip.y + (ank.y - hip.y) * (knee.z - hip.z) / (ank.z - hip.z) - knee.y, 4)
        sh, el, wr = b["upper_arm." + s].head_local, b["forearm." + s].head_local, b["forearm." + s].tail_local
        t = (el - sh).dot(wr - sh) / (wr - sh).length_squared
        out["elbow_back_" + s] = round(el.y - (sh.y + (wr.y - sh.y) * t), 4)
    out["broken_connections"] = [x.name for x in b if x.use_connect and (x.head_local - x.parent.tail_local).length > 1e-4]
    out["object_scale_is_1"] = all(abs(v - 1) < 1e-6 for v in meta.scale)
    out["ok"] = all(v > 0 for k2, v in out.items() if k2[:4] in ("knee", "elbo")) and not out["broken_connections"] \
        and out["object_scale_is_1"]
    return out
```

`check_metarig` must return `ok: True`: both `knee_forward` and both `elbow_back` values positive (aim for 2 to 3
percent of the limb length; move the `knee` or `elbow` landmark if not), no broken connections, object scale 1.

Face bones. The block fit above only puts the face bones in the right region. The course then snaps each one to
the skin with face snapping (`Face Project`, with rotate and scale options on) [17:55:48], except the centre-line
bones, which it moves only in the side view with snapping off so they stay at X = 0 [17:58:41]. Where each goes:
ear chain around the ear rim (three bones up the outside, two back down); `temple`, `jaw.L`, `chin.L` down the
side of the face to the chin; lip bones meeting at the mouth corner; `cheek.B` and `cheek.T` under and over the
cheek; `forehead` bones high enough to clear the eyebrows; `brow.T` just above the brow, `brow.B` just under it;
`lid.T` and `lid.B` along the eyelid edges, corner to corner; `nose` bones down the bridge to the tip and on to
the top lip; `tongue` (three bones) and `teeth.T`, `teeth.B` inside the mouth; `jaw_master` moved down and back to
just in front of the ear, which is where the jaw hinges [18:04:33].

```python
# verified in 4.5.16 background
def snap_face_to_surface(meta, body, skip=("face", "eye.", "teeth", "tongue", "jaw_master")):
    ebs = edit_bones(meta)
    inv, mw, mwi = body.matrix_world.inverted(), meta.matrix_world, meta.matrix_world.inverted()
    def f(p):
        ok, loc, _n, _i = body.closest_point_on_mesh(inv @ (mw @ p))
        q = mwi @ (body.matrix_world @ loc) if ok else p
        if abs(p.x) < 1e-5: q.x = 0.0
        return q
    apply_map([e for e in under(ebs, "face") if not e.name.startswith(skip)], f)
    for eb in ebs:
        o = ebs.get(eb.name.replace(".L", ".R")) if ".L" in eb.name else None
        if o: o.head, o.tail, o.roll = eb.head * V((-1, 1, 1)), eb.tail * V((-1, 1, 1)), -eb.roll
    bpy.ops.object.mode_set(mode="OBJECT")
```

Nearest-surface snapping does not know where the eyelid edge or mouth corner is. After it, capture the face from
the front with the metarig in front, and correct the lid corners, lid middles, mouth corners and brow ends with
`move_joint(ebs, "lid.T.L", "head", (x, y, z))` using points read from the mesh.

### 5. Fingers: straight, slightly bent, rolled the same way [18:07:20 to 18:13:50]

The course first places each finger joint at the centre of its knuckle ring (select the edge loop, `Cursor to
Selected`, then `Selection to Cursor` on the joint) [17:52:38], generates, and shows the result: scaling a finger
control curls the fingers sideways [18:07:25]. Its fix has three parts, all done by `fit_metarig` above:

- Roll: every finger bone has its X axis across the finger and its Z axis toward the palm side [18:08:17].
- Flatten: set the transform orientation to `Normal`, select a finger chain, and press `S Z 0 Enter` so the joints are
  flattened into one plane [18:12:32]. (The narration says "x axis"; the frames show Z along the bone's normal.)
- Then lift the middle joints a tiny amount toward the back of the hand, so the curl direction is unambiguous
  [18:12:44]. (Rigify's finger rig derives the hinge axis from the plane of this bend; with a perfectly straight
  chain it falls back on the roll.)

Test after generating: set `rig.pose.bones["f_index.01_master.L"].scale = (0.6, 0.6, 0.6)`; the tip of
`DEF-f_index.03.L` must move toward the palm (negative dot product with `hand_back`). Reset the scale after.

### 6. Generate, and regenerate when needed [18:04:52, 18:07:58]

```python
# verified in 4.5.16 background
def generate_rig(meta):
    edit_bones(meta); bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.pose.rigify_generate()            # object "rig" (918 bones here) plus a "WGTS_rig" widget collection
    rig = meta.data.rigify_target_rig
    rig.show_in_front = True
    root = bpy.data.objects.get("CHARACTER")              # meshes bound to the rig stay under CHARACTER, so the
    if root is not None and rig.parent is None:           # whole-character checks still include them
        rig.parent = root
    return rig
```

Generating again after changing the metarig rebuilds the same `rig` object in place; meshes stay parented and
keep their weights (checked). Pose only `rig`, and only in Pose Mode; leave its Edit Mode alone [18:05:25]. Hide
`metarig` once the rig is right. Bone names in `rig`: controls have plain names (`torso`, `chest`, `hips`, `head`,
`neck`, `hand_ik.L`, `foot_ik.L`, `upper_arm_fk.L`, `f_index.01_master.L`, `jaw_master`, `eye_common`,
`lid.T.L.002`); `DEF-` bones deform the mesh (171 of them); `MCH-` and `ORG-` are internals, hidden.

After the first generation the Rigify panel button reads `Re-Generate Rig`; use it each time the metarig changes. The
N panel Rigify tab of `rig` carries Rig Main Properties (Neck Follow 0.500, Head Follow 0, Torso Parent Root) and the
Rig Layers buttons [18:07:08].

### 7. Bind the body with automatic weights [18:06:06]

Weights say how much each deform bone moves each vertex, 0 to 1, shown blue to red in Weight Paint
[17:30:54]. The course selects the body, then the rig, and uses `Ctrl P > With Automatic Weights`. The `Armature`
modifier must sit above `Subdivision`, so the low mesh deforms first and is smoothed after [18:28:03].

```python
# verified in 4.5.16 background
def bind(meshes, rig, how="ARMATURE_AUTO"):   # "ARMATURE_NAME" = With Empty Groups
    if bpy.context.object and bpy.context.object.mode != "OBJECT": bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    for m in meshes: m.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type=how)
    for m in meshes:
        if m.modifiers.find("Armature") > 0:
            with bpy.context.temp_override(object=m, active_object=m):
                bpy.ops.object.modifier_move_to_index(modifier="Armature", index=0)
    return {m.name: weight_report(m, rig) for m in meshes}

def weight_report(mesh, rig):
    idx = {g.index for g in mesh.vertex_groups if g.name in {b.name for b in rig.data.bones if b.use_deform}}
    loose = sum(1 for v in mesh.data.vertices if sum(g.weight for g in v.groups if g.group in idx) < 1e-4)
    return {"verts": len(mesh.data.vertices), "deform_groups": len(idx), "unweighted_verts": loose}
```

`unweighted_verts` must be 0 for a mesh bound with automatic weights. If Blender reports that bone heat weighting
failed, the mesh has overlapping shells, holes or loose parts: bind a clean copy and transfer the weights (step 11),
or use a rig helper (step 12).

### 8. Test poses (my addition; the course only tries controls by hand [18:15:27])

The rig has to survive animation, so put it through the same fixed poses every time. The limbs default to IK;
switching them to FK lets a script turn each joint by a known angle. `rotate_world` turns a pose bone about a world
axis through its own head, so it does not depend on bone roll; elbows, knees and fingers hinge on their local X.

```python
# verified in 4.5.16 background
def set_fk(rig, value=1.0):
    for n in ("upper_arm_parent.L", "upper_arm_parent.R", "thigh_parent.L", "thigh_parent.R"):
        rig.pose.bones[n]["IK_FK"] = value
    rig.update_tag(); bpy.context.view_layer.update()

def rotate_world(rig, bone, axis, degrees):                # pose parents before children
    pb = rig.pose.bones[bone]
    head = pb.matrix.to_translation()
    ax = (rig.matrix_world.inverted().to_3x3() @ V(axis)).normalized()
    pb.matrix = Matrix.Translation(head) @ Matrix.Rotation(math.radians(degrees), 4, ax) @ Matrix.Translation(-head) @ pb.matrix
    bpy.context.view_layer.update()

def rotate_local(rig, bone, axis, degrees):
    pb = rig.pose.bones[bone]
    pb.matrix = pb.matrix @ Matrix.Rotation(math.radians(degrees), 4, axis)
    bpy.context.view_layer.update()

def reset_pose(rig):                                       # the course's Alt G, Alt R, Alt S [18:14:11]
    for pb in rig.pose.bones:
        pb.location, pb.rotation_quaternion, pb.rotation_euler, pb.scale = (0, 0, 0), (1, 0, 0, 0), (0, 0, 0), (1, 1, 1)
    bpy.context.view_layer.update()

TEST_POSES = {      # frame: (name, [(bone, axis, degrees)]); a tuple is a world axis, "X" is the bone's own hinge
    1: ("rest", []),
    10: ("arms_up", [("upper_arm_fk.L", (0, 1, 0), -110), ("upper_arm_fk.R", (0, 1, 0), 110)]),
    20: ("elbows_deep", [("forearm_fk.L", "X", 130), ("forearm_fk.R", "X", 130)]),
    30: ("knees_deep", [("thigh_fk.L", (1, 0, 0), -90), ("thigh_fk.R", (1, 0, 0), -90),
                        ("shin_fk.L", "X", 120), ("shin_fk.R", "X", 120)]),
    40: ("head_turn", [("head", (0, 0, 1), 70)]),
    50: ("torso_twist", [("chest", (0, 0, 1), 45)]),
}

def build_test_poses(rig, poses=TEST_POSES):
    set_fk(rig, 1.0)
    for frame, (_name, moves) in poses.items():
        reset_pose(rig)
        for bone, axis, deg in moves:
            (rotate_local if isinstance(axis, str) else rotate_world)(rig, bone, axis, deg)
        for pb in rig.pose.bones:
            if not pb.name.startswith(("DEF-", "MCH-", "ORG-")):
                for path in ("location", "rotation_quaternion" if pb.rotation_mode == "QUATERNION" else "rotation_euler", "scale"):
                    pb.keyframe_insert(path, frame=frame)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = min(poses), max(poses); sc.frame_set(min(poses))

def deformed(mesh):
    ev = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me, bm = ev.to_mesh(), bmesh.new()
    bm.from_mesh(me)
    pts, vol = [ev.matrix_world @ v.co for v in me.vertices], abs(bm.calc_volume())
    bm.free(); ev.to_mesh_clear()
    return pts, vol

def pose_report(mesh, still, poses=TEST_POSES):
    sc = bpy.context.scene
    sc.frame_set(min(poses)); rest, vol0 = deformed(mesh)
    out = {}
    for frame, (name, _m) in poses.items():
        sc.frame_set(frame); pts, vol = deformed(mesh)
        d = [(a - b).length for a, b in zip(pts, rest)]
        out[name] = {"max_move": round(max(d), 4), "volume_ratio": round(vol / vol0, 3)}
        if name in still:
            out[name]["stray_move"] = round(max((x for x, p in zip(d, rest) if still[name](p)), default=0.0), 4)
    sc.frame_set(min(poses))
    return out
```

`still` maps a pose name to a test on a rest-position point that is true for vertices that must not move in that
pose. With `neck_z` and `hips_z` from the landmarks: `"head_turn": lambda p: p.z < neck_z - 0.07 * H`;
`"knees_deep": lambda p: p.z > hips_z + 0.1 * H`; `"arms_up"` and `"torso_twist"`:
`lambda p: p.z < hips_z - 0.05 * H and abs(p.x) < 0.18 * H` (the X limit keeps A-pose hands out of the leg test).
Run `pose_report` with the `Mask` modifier of step 13 switched off, and Simplify on.

Then look: `motion_preview(frames=[1, 10, 20, 30, 40, 50], shading="SOLID")`, and for any pose in doubt
`viewport_capture(view="FRONT", frame=10)` and `view="RIGHT"`. What a failed pose looks like:

| Sign | Cause | Fix |
|---|---|---|
| Spikes: a few vertices stay at the rest position | unweighted vertices | `unweighted_verts` > 0; rebind or transfer weights |
| Elbow or knee pinches flat like a bent straw | joint landmark off-centre, or too few edge loops at the joint | move the landmark, regenerate; add loops in retopology |
| Knee folds backward or sideways, fingers curl sideways | no bend in the metarig chain, or wrong roll | steps 3 and 5, regenerate |
| Head turn drags the shoulders; brow control moves the scalp | weights bleed to distant bones (`stray_move` high) | step 9 |
| Arms up: armpit web, chest pulled out, shoulder caves in | shoulder landmark too far out or in | move `shoulder`, regenerate |
| Skin pokes through clothes; eyes, teeth or hair left behind | part not bound, or bound by the wrong method | steps 10 to 13 |

### 9. Fix weights where automatic weights are wrong [18:16:23 to 18:25:00]

The course finds two problems. Moving a brow control dragged the top of the head, so it painted `DEF-spine.006`
(the head bone) to 1.0 over the skull with `Auto Normalize` on, which strips the other bones from those vertices
[18:19:10]. The upper eyelid did not close cleanly, so it added weight to `DEF-lid.T.L.*`, removed brow weight
from the lid, restricted painting to selected faces to protect the lower lid, and blurred [18:21:46]. It calls
weight painting a guessing game and, for the lids, switches to a shape key (step 10).

The brush header reads Weight 1.000 and Strength 1.000 in every weight-paint clip; Size moves between 100 and 326 px
with zoom, and the Options popover has `Mirror` X and `Auto Normalize` ticked [18:19:10 to 18:22:57].

Without a brush, set weights by region: `paint(body, "DEF-spine.006", lambda p: p.z > brow_z + margin)`.

```python
# verified in 4.5.16 background
def paint(mesh, group, test, weight=1.0, exclusive=True):
    ids = [v.index for v in mesh.data.vertices if test(mesh.matrix_world @ v.co)]
    if exclusive:                                          # the effect of painting with Auto Normalize on
        for g in mesh.vertex_groups:
            if g.name.startswith("DEF-") and g.name != group: g.remove(ids)
    (mesh.vertex_groups.get(group) or mesh.vertex_groups.new(name=group)).add(ids, weight, "REPLACE")
    return len(ids)
```

A hard edge of weight 1 next to weight 0 creases when posed. Soften it: make the mesh active, select the region in
Edit Mode, then `bpy.ops.object.vertex_group_smooth(group_select_mode='BONE_DEFORM', factor=0.5, repeat=3)` and
`bpy.ops.object.vertex_group_normalize_all(lock_active=False)` (verified in 4.5.16 background).

### 10. Corrective shape key on a driver: the closed eyelid [18:25:07 to 18:37:00]

When weights cannot give the shape, sculpt the shape and let the control switch it on. The course moves the lid
control `lid.T.L.002` down in its local Y until the eye is shut, notes the value (-0.024 on its character), adds a
shape key `eye_close` at value 1, sculpts the closed lid with Grab while the lower lid is masked, then adds a
driver on the key's value: type `Averaged Value`, one `Transform Channel` variable reading that bone's `Y
Location`; in the Drivers Editor it sets the second key's frame to -0.024 with value 1 and both keys to `Linear`,
so the key is 0 at rest and 1 when shut [18:30:23 to 18:33:34]. To split left and right it makes two vertex
groups, `left_side` and `right_side` (weight 1 on each side, 0.5 on the centre loop), sets the key's `Vertex
Group` to `left_side`, duplicates the key for the right and repoints its driver at `lid.T.R.002` [18:34:03].

```python
# verified in 4.5.16 background
def drive_key(mesh, key_name, rig, bone, value_at_one, channel="LOC_Y"):
    kb = mesh.data.shape_keys.key_blocks[key_name]
    kb.driver_remove("value")
    fc = kb.driver_add("value")
    fc.driver.type = "AVERAGE"
    var = fc.driver.variables.new()
    var.type = "TRANSFORMS"
    t = var.targets[0]
    t.id, t.bone_target, t.transform_type, t.transform_space = rig, bone, channel, "TRANSFORM_SPACE"
    for m in list(fc.modifiers): fc.modifiers.remove(m)
    for x, y in ((0.0, 0.0), (value_at_one, 1.0)):
        fc.keyframe_points.insert(x, y).interpolation = "LINEAR"
    fc.extrapolation = "CONSTANT"
```

The course picks `Local Space`. I use `TRANSFORM_SPACE`: the lid controls carry a `Limit Distance` constraint, and
in `LOCAL_SPACE` the driver saw only 0.24 when the bone's own Y location was at the recorded value; in
`TRANSFORM_SPACE` it reads exactly the number in `pose.bones[...].location` (0, 0.5, 1.0 at 0, half, full).

Making the key without a brush: `sculpt_strokes` refuses meshes that have shape keys. Add the keys with
`mesh.shape_key_add(name="Basis")` then `mesh.shape_key_add(name="eye_close_L")` and write positions straight into
`kb.data[i].co` (rest-space coordinates) for the lid vertices, with the control held at the closed value and a
capture after each change. New keys start at value 0 in 4.5 (1 in 5.0); set `kb.value = 1` while shaping.

### 11. Eyes, teeth, tongue, hair, shirt: empty groups, then the right weights [18:37:27 to 18:48:30]

Automatic weights on small or layered parts pick up nearby face bones (the temple bone would tug the eyeball).
The course parents these with `Ctrl P > With Empty Groups` (`bind(..., "ARMATURE_NAME")`): every deform group is
created, empty, and it fills in only what the part needs.

| Part | Weights |
|---|---|
| Eyeball and cornea, per side | all vertices 1.0 on `DEF-eye.L` / `DEF-eye.R` [18:39:08] |
| Upper teeth and gums; lower teeth and gums | 1.0 on `DEF-teeth.T`; 1.0 on `DEF-teeth.B` [18:41:08] |
| Tongue | automatic weights limited to `DEF-tongue`, `DEF-tongue.001`, `DEF-tongue.002` (`Weights > Assign Automatic from Bones` with only those selected) [18:41:30] |
| `hair_scalp`, the ponytail scalp, `Hair.Band` | 1.0 on `DEF-spine.006` (the head) [18:44:46, 18:46:52] |
| Brow and lash scalps | copied from the body, so they follow lids and brows [18:45:10] |
| Shirt (close-fitting cloth) | copied from the body [18:47:55] |

Parent the scalp meshes, never the generated hair curves [18:44:01]. The copy is `Weights > Transfer Weights` with
`Vertex Mapping: Nearest Face Interpolated` and the layer option that matches groups by name [18:45:50].

```python
# verified in 4.5.16 background
def assign_all(mesh, group, weight=1.0):
    for g in mesh.vertex_groups:
        if g.name.startswith("DEF-"): g.remove(range(len(mesh.data.vertices)))
    (mesh.vertex_groups.get(group) or mesh.vertex_groups.new(name=group)).add(range(len(mesh.data.vertices)), weight, "REPLACE")

def copy_weights(src, dst):                                # dst already bound with empty groups
    m = dst.modifiers.new("WeightCopy", "DATA_TRANSFER")
    m.object, m.use_vert_data, m.data_types_verts = src, True, {"VGROUP_WEIGHTS"}
    m.vert_mapping, m.layers_vgroup_select_src, m.layers_vgroup_select_dst = "POLYINTERP_NEAREST", "ALL", "NAME"
    with bpy.context.temp_override(object=dst, active_object=dst, selected_objects=[dst]):
        bpy.ops.object.modifier_move_to_index(modifier=m.name, index=0)
        bpy.ops.object.datalayout_transfer(modifier=m.name)
        bpy.ops.object.modifier_apply(modifier=m.name)
```

For objects that hold several parts (the jaw object), pass only that part's vertices: use `paint` with a test, or
`bmesh` linked-island selection. For the tongue without the operator, blend the three tongue groups linearly along
the tongue's length (check each bone's `head_local.y` to see which one is the tip).

### 12. Boots, skirt, necklace: a rig helper and Surface Deform [18:48:56 to 18:58:30]

Parts made of several separate shells (sole, upper, buckles) or stiff pleats deform badly with automatic weights.
The course builds a low, closed proxy that wraps the whole part (a cube box-modelled around the boot, with a few
loop cuts, smoothed, kept just outside the surface; mirrored for the other side), names it
`Boot.L_rig_helper` (ours; the course's is `GEO_<name>_shoe_rig_helper`), binds the proxy with automatic weights, and makes the real part follow the proxy with
a `Surface Deform` modifier. The real part is also parented to the rig with empty groups that stay empty. Modifier
order on the part: `Armature`, `SurfaceDeform`, then `Subdivision`. Bind with Simplify on (max subdivision 0);
binding with subdivision active throws an error [18:55:10]. The proxy is shown as `Wire` and hidden from renders
[18:54:05, 18:56:18]. The skirt follows the same recipe and the video does show it, sped up four times [18:56:47 to
18:57:47]; the necklace is only said to go the same way [19:01:46]. On screen the boot's stack reads `Mirror`,
`Armature`, `SurfaceDeform`, `Subdivision`; the helper has `Mirror` then `Armature`.

```python
# verified in 4.5.16 background
def follow_helper(part, helper, rig):
    bpy.context.scene.render.use_simplify, bpy.context.scene.render.simplify_subdivision = True, 0
    bind([helper], rig, "ARMATURE_AUTO")
    helper.display_type, helper.hide_render = "WIRE", True
    sd = part.modifiers.new("SurfaceDeform", "SURFACE_DEFORM")
    sd.target = helper
    with bpy.context.temp_override(object=part, active_object=part):
        bpy.ops.object.modifier_move_to_index(modifier="SurfaceDeform", index=part.modifiers.find("Armature") + 1)
        bpy.ops.object.surfacedeform_bind(modifier="SurfaceDeform")
    return sd.is_bound
```

Build the helper with bpy: a cube scaled to the part's bounding box plus 3 to 5 percent, a `SIMPLE` subdivision of
2 applied, then each vertex pulled to just outside the part (nearest point on the part plus a small offset along
the normal). To reshape the real part later (the course pushes the skirt out where a raised leg clips), unbind
first, edit, bind again; edits made while bound do not show [18:59:00].

### 13. Hide the skin under the clothes [18:59:30]

Skin that can never be seen will poke through cloth in strong poses and costs time. The course selects those body
faces (torso under the shirt and skirt, keeping the shoulders), puts them in a vertex group `mask`, and adds a
`Mask` modifier with that group and the invert button on, placed above `Subdivision`. Verified: `m =
body.modifiers.new("Mask", "MASK"); m.vertex_group = "mask"; m.invert_vertex_group = True`. Turn it off
(`m.show_viewport = False`) while posing the bare body.
On screen the body stack reads `Armature`, `Mask`, `Subdivision`, and the bare body is shown by switching the Mask
modifier's viewport icon off [19:02:28, 19:02:36].

### 14. Pose [17:34:28 to 17:41:46, 19:02:00 to 19:04:30]

The course says the pose matters more than the rig: a good model in a stiff pose still reads as a bad render.
Its rules:

- Work from a pose reference; the concept picture is one, and extra photos help [17:35:00].
- Find the line of action first, one curve from head through to the supporting leg [17:36:05].
- Find where the weight sits; the character must look balanced over its feet [17:37:15].
- Exaggerate past the reference; realistic motion can look flat on a stylized character [17:38:10].
- Break symmetry: the two hands, arms and legs never mirror each other [17:38:30].
- Contrapposto: weight on one leg, hips tilted one way, shoulders the other, one side of the torso stretched and
  the other squashed. Hips and shoulders never parallel [17:39:04].
- Pose the bare body first, clothes hidden, then check the clothes [19:02:25].
- If the rig cannot reach a shape, finish it with a shape key made for that pose [17:40:56]; the course does this
  on the skirt helper for its final pose [19:22:10].

Set a pose with the same functions as the test poses (`rotate_world`, `rotate_local`, or IK: move `hand_ik.L`,
`foot_ik.L`, `torso` by setting `pose.bones[...].location`, with `set_fk(rig, 0.0)`). Work in the bones' own
axes [18:14:30]. The course saves each pose as a pose asset in the current file, with a camera in the scene so the
asset gets a thumbnail (`Asset > Create Pose Asset` in the Asset Browser) [19:02:44]; it stores `concept_pose` and
`happy_pose` and asks for at least two [19:04:20]. Through blender-live, key each pose on its own frame (as
`build_test_poses` does) on frames after the test range, for example 101 and 102, and record the frame numbers;
`motion_preview(frames=[101, 102])` shows them.

The Asset Browser is an editor switched on beside the viewport (library `Current File`, catalog `Unassigned`); a camera
object appears in the outliner when the pose asset gets its thumbnail [19:02:49 to 19:04:22].

## How the artist works on screen

What the sheets of chapter 13 show, step by step (Blender 5.0.1 on screen; the reader works in 4.5.16). Clip ids are
`qy-wwP-b9HY-13-HHMMSS`; times are video clock times. Values marked "read" are legible on screen; the rest were
seen but not readable. Nothing here replaces the code above. "Reader" lines say what to call. Where I convert
screen pixels to world units, the conversion is my own estimate.

### Layout the artist works in (all steps)

- One 3D viewport on the left, outliner (top right) and Properties editor (bottom right) as in the default
  Layout workspace, plus the N panel when needed. Shading is Solid with the real textures shown, and `In Front` on
  for the metarig and later the rig [qy-wwP-b9HY-13-174404 17:44:14, qy-wwP-b9HY-13-175224 17:52:26].
- Views: front and right orthographic (Numpad 1, 3) for joint placement, with the grid in centimetres or
  millimetres at high zoom; a perspective view for rolls and the face. X-ray (Alt Z) is toggled constantly so the
  bone shows through the skin or hides behind it [qy-wwP-b9HY-13-175654 17:56:56, qy-wwP-b9HY-13-175735 17:57:39].
- Local view (Slash) isolates the body and the rig; Shift H hides unselected bones [qy-wwP-b9HY-13-174458
  17:45:08, qy-wwP-b9HY-13-175827 17:58:36].
- Reader: `viewport_capture(view="FRONT")`, `view="RIGHT"`; the isolation is `hide_set(True)` on the other objects.

### 1. Collections and a fast viewport

- Outliner drag and drop: the artist drags every geometry and cloth collection into `CH_<name>_model`, leaves
  `CH_<name>_rig` empty, then selects the rig collection before adding the metarig so it lands in it
  [qy-wwP-b9HY-13-174239 17:42:41, qy-wwP-b9HY-13-174304 17:43:06]. `CH_<name>_rig_helpers` is created later and the
  helper proxies are dragged into it [qy-wwP-b9HY-13-185007 18:50:19].
- Simplify: in Render Properties the artist ticks `Simplify`, sets the Viewport `Max Subdivision` to 0 (read), and
  right-clicks the checkbox to add it to Quick Favorites, so `Q` toggles it while posing [qy-wwP-b9HY-13-181733
  18:17:35 to 18:17:50]. He turns it off to judge the finished lid shape and on again to bind Surface Deform
  [qy-wwP-b9HY-13-182756 18:27:58, qy-wwP-b9HY-13-185505 18:55:18].
  Reader: `bpy.data.collections.new(...)`, `scene.render.use_simplify = True`, `simplify_subdivision = 0`.

### 2. The metarig

- `Shift A > Armature > Rigify Meta-Rigs` offers `Human`, `Animals` and `Basic`; he picks Human with the rig
  collection active [qy-wwP-b9HY-13-173245 17:32:46, qy-wwP-b9HY-13-174318 17:43:19]. A skeleton with a gold face
  block appears, far too big, around the character.
- The N panel Item tab for the metarig shows location 0, rotation 0, scale 1 and dimensions of about 1.58 by 0.285 by
  1.98 m (read); the artist keeps these and works in Edit Mode only [qy-wwP-b9HY-13-174330 17:43:42].
- Reader: `add_metarig(collection_name)` (step 2); `check_metarig(meta)["object_scale_is_1"]` must stay True.

### 3 and 4. Measuring and fitting the metarig

- Order on screen: scale and move the whole skeleton to height (S, G Y, G Z), pelvis, spine in the side view, leg,
  foot, heel, shoulder, arm, hand, fingers, face, eyes. Mirror is on: the tool options show `X-Axis Mirror` and the
  header shows an X toggle [qy-wwP-b9HY-13-174542 17:45:48].
- Spine and pelvis: he selects the spine bones with `L` (linked) in the right view and drags joints along Y so the
  chain follows the back; the pelvis bone is moved forward by a few millimetres, header showing the move
  [qy-wwP-b9HY-13-174558 17:46:05, qy-wwP-b9HY-13-174635 17:46:40 to 17:46:47]. Reader: `move_joint(ebs, "spine", "tail", along(t))`.
- Leg and foot: the knee joint goes to the middle of the knee, the foot bone to the ankle, the toe bone to the ball
  of the foot, all in the right view with `G` or `G Y` [qy-wwP-b9HY-13-174703 17:47:05 to 17:47:18]. Heel: the
  `heel.02` bone lies on the floor line at the back of the sole; in the front view he presses `S X` to widen it to the
  shoe width, after switching the pivot pie (period key: Median Point, Active Element, Bounding Box Center, 3D Cursor,
  Individual Origins) [qy-wwP-b9HY-13-174734 17:47:36 to 17:47:54, qy-wwP-b9HY-13-174747 17:47:50]. Reader: `P["heel"] +/- (w, 0, 0)` with `heel_half_width`.
- Shoulder and clavicle: moved in the front view along the collarbone, then in Y in a 3/4 view so the bone sits back
  in the shoulder [qy-wwP-b9HY-13-175026 17:50:27 to 17:50:35].
- Hand: the palm bones go to the middle of the palm; each finger joint is snapped exactly to the middle of its
  knuckle ring: select the loop in the body's Edit Mode, `Shift S > Cursor to Selected`, back to the metarig,
  select the joint, `Shift S > Selection to Cursor` (the header says "Snap Selection to Cursor") [qy-wwP-b9HY-13-175238 17:52:49,
  qy-wwP-b9HY-13-175251 17:52:53 to 17:53:03]. Reader: `band(body, ...)["centre"]` then `move_joint`.
- Face: with the face bones shown he moves forehead, temple and ear bones first. Snapping is set from the header
  popover: Snap To `Face Project` (Face Nearest sits beside it); Affect shows Move, Rotate and Scale all on
  [qy-wwP-b9HY-13-175548 17:55:56 to 17:55:59]. Lip, chin, cheek and nose bones are moved with `G`, cancelling with
  `Esc` when the result is wrong. Whole joints are moved by box-selecting the joint (all ends) in side view; this is
  the "very important" disconnected-bones warning [qy-wwP-b9HY-13-175654 17:56:56, qy-wwP-b9HY-13-175907 17:59:10 to 17:59:23].
  Reader: `snap_face_to_surface(meta, body)` then `move_joint` per lid, lip and brow point.
- Chin and jaw: moved in side view in several `G` passes; snapping is turned back on only for the bones along the
  side of the face [qy-wwP-b9HY-13-175939 17:59:41 to 17:59:51]. `jaw_master` is set by the transcript to the hinge.
- Eye: the head and tail of `eye.L` are each snapped to the cursor placed at the eyeball centre (`Shift S`), then
  snapping is turned off and the tail is moved straight forward in Y and a little in X [qy-wwP-b9HY-13-180233
  18:02:34 to 18:02:43, qy-wwP-b9HY-13-180245 18:02:47 to 18:02:50]. Reader: `ebs["eye.L"].head/.tail = P["eye"], P["eye"] + V((0, -r, 0))`.

### 5. Fingers

- First test, on the generated rig: in Pose Mode he scales `f_index.01_master.L` with `S` (header scale about
  0.69 to 0.88, read) and the fingers curl sideways instead of toward the palm [qy-wwP-b9HY-13-180720 18:07:22 to
  18:07:33, qy-wwP-b9HY-13-180734 18:07:36 to 18:07:45]. Reader: scale the master to 0.6 and compare the
  tip direction with `hand_back`.
- Fix, in Edit Mode on the metarig: he selects a finger bone and reads Head, Tail and Roll in the N panel (rolls
  like -142 and -135 degrees are legible), then rolls bones with `Ctrl R` one by one until the axes agree
  [qy-wwP-b9HY-13-180807 18:08:08, qy-wwP-b9HY-13-180927 18:09:29 to 18:09:40]. Transform orientation is
  `Normal`: `S Z 0 Enter` flattens each chain along its normal Z, `R X` turns the thumb about its normal X (header
  reads a few degrees) [qy-wwP-b9HY-13-181231 18:12:32 to 18:12:42]. Finally he lifts the middle joints a little
  with `G Z` so there is a bend [qy-wwP-b9HY-13-181244 18:12:55, qy-wwP-b9HY-13-181333 18:13:36 to 18:13:41].
- He regenerates (the Rigify panel now reads `Re-Generate Rig`) and repeats the scale test; this time the fingers
  close into a fist when the master is scaled in Y (about 0.45 to 0.49) after a small `R X` [qy-wwP-b9HY-13-181517 18:15:18 to 18:15:25]. Reader: `fit_metarig(meta, L)` (all three fixes) then the finger curl test in step 5.

### 6. Generate and the rig panel

- Object Data properties of the metarig: the Rigify panel first shows a note that it uses the old face rig, with
  `Upgrade Face Rig` and `Generate Rig`; after upgrading only `Generate Rig` remains, and a status line reports
  success. The new `rig` has big circle controls around the feet [qy-wwP-b9HY-13-180405 18:04:10, qy-wwP-b9HY-13-180419 18:04:24,
  qy-wwP-b9HY-13-180445 18:04:58 to 18:05:03].
- With `rig` selected the N panel has a Rigify tab with Rig Main Properties (Neck Follow 0.500, Head Follow 0, Torso
  Parent Root, all read) and Rig Layers buttons: Face, (Primary), (Secondary), Torso, (Tweak), Fingers, (Detail),
  Arm.L/R (IK, FK, Tweak), Leg.L/R, Root. He leaves them on but says they can be turned off to reduce clutter
  [qy-wwP-b9HY-13-180706 18:07:08 to 18:07:18]. Reader: `generate_rig(meta)`; hide groups with `rig.data.collections_all[n].is_visible`.
- Pose reset: `Alt R`, `Alt G`, `Alt S` clear rotation, location and scale of the selected bones; transform
  orientation is changed from Normal to `Local` for posing [qy-wwP-b9HY-13-181406 18:14:08, qy-wwP-b9HY-13-181424
  18:14:35]. Reader: `reset_pose(rig)`.

### 7. Binding the body

- Select the body then the rig, `Ctrl P > With Automatic Weights` [qy-wwP-b9HY-13-180554 18:05:56]. The video then
  moves limb controls to test; nothing is measured. Reader: `bind([body], rig)`; `weight_report` must show 0 unweighted vertices.

### 9. Weight painting

- Weight Paint on the body, vertex groups panel searched by name (`lid`, `brow`, `spine`). The header reads
  Weight 1.000 and Strength 1.000 throughout; Size (radius) changes between 100, 118, 182, 320 and 326 px as he
  zooms [qy-wwP-b9HY-13-181909 18:19:10, qy-wwP-b9HY-13-182132 18:21:44, qy-wwP-b9HY-13-182240 18:22:53]. Options
  popover: `Mirror` X on, `Auto Normalize` ticked [qy-wwP-b9HY-13-181909 18:19:10 to 18:19:17].
- Order: paint the head group `DEF-spine.006` over the skull above the brows (red cap on blue) so a brow control stops
  moving the scalp [qy-wwP-b9HY-13-182132 18:21:44]; then compare the `DEF-lid.T.L` groups, undo with `Ctrl Z`, and
  cycle the heat map between lid and brow groups [qy-wwP-b9HY-13-182240 18:22:43 to 18:22:57, qy-wwP-b9HY-13-182453
  18:24:55]. The artist moves on to the shape key because he wants a specific lid shape.
- On a 1.7 m character a 118 px brush on a head filling a third of the viewport covers roughly 5 to 8 cm: my estimate.
  Reader: `paint(body, "DEF-spine.006", lambda p: p.z > brow_z + margin)`; soften with `vertex_group_smooth`.

### 10. Corrective eyelid key and driver

- Find the value: in Pose Mode he moves `lid.T.L.002` in local Y until the lid is shut (header shows about 0.027 m
  of travel), opens the N panel, reads -0.02367 and types -0.024 (read) [qy-wwP-b9HY-13-182520 18:25:33, qy-wwP-b9HY-13-182554
  18:25:56 to 18:26:06]. Rig Main Properties for the lid shows `Eyelids Follow` 1.000.
- Key: Object Data > Shape Keys > plus (adds `Basis`), plus again for `eye_close`, Value 1.000, Range 0 to 1
  [qy-wwP-b9HY-13-182621 18:26:23 to 18:26:37]. Sculpt Mode, `Grab` brush, header Size 354 px then 392 and 460 px,
  Strength 0.400, `F` to resize, `G` to nudge the lid edge, lower lid untouched [qy-wwP-b9HY-13-182743 18:27:44
  to 18:27:55]. Reader: write `kb.data[i].co` for the lid vertices (the reader has no Grab brush).
- Driver: right-click the Value field > `Add Driver`; the popover starts as Scripted Expression, he changes it to
  `Averaged Value`, fills the variable with the rig object, the bone and `Y Location` (the default is X Location,
  World Space; the later popover reads `Local Space`) [qy-wwP-b9HY-13-183023 18:30:25 to 18:30:40,
  qy-wwP-b9HY-13-183652 18:36:54]. The Drivers Editor opens as a floating window: active key frame -0.024 and value
  1.0, interpolation switched to Linear [qy-wwP-b9HY-13-183243 18:32:44]. Reader: `drive_key(...)` (step 10; I read
  the bone's Y in `TRANSFORM_SPACE`).
- Test: moving the lid control with `G Y` leaves the key off until the recorded distance, then it is fully on
  [qy-wwP-b9HY-13-183322 18:33:23 to 18:33:33]. Both eyes close together at first [qy-wwP-b9HY-13-183350 18:33:51].
- Split: vertex groups `left_side` and `right_side`; the centre loop of the body is set to 0.500 with Auto Normalize
  on, shown as a red-blue weight view [qy-wwP-b9HY-13-183530 18:35:32, 18:35:37]. Key renamed `eye_close_L`, its
  `Vertex Group` field set to `left_side`; `Duplicate Shape Key` gives the right key, with `right_side` and the
  driver bone changed to `lid.T.R.002` [qy-wwP-b9HY-13-183601 18:36:03 to 18:36:14, qy-wwP-b9HY-13-183652 18:36:54].

### 11. Eyes, teeth, tongue, hair, shirt

- Eyes: select the eyeball and cornea objects, then the rig, `Ctrl P > With Empty Groups` [qy-wwP-b9HY-13-183742
  18:37:53]. In Edit Mode he searches `eye` in the groups list, picks `DEF-eye.L`, checks Weight 1.000, selects all,
  `Assign`; same for the right eye [qy-wwP-b9HY-13-183902 18:39:05 to 18:39:19]. Reader: `bind(..., "ARMATURE_NAME")`, `assign_all(mesh, "DEF-eye.L")`.
- Teeth: in the jaw object (`Mouth`) he works in the right orthographic view, mm grid, X-ray on. `Ctrl L` selects the upper
  teeth island, group `DEF-teeth.T`, Assign at weight 1.000; `Ctrl I` inverts the selection for the lower teeth,
  `DEF-teeth.B` [qy-wwP-b9HY-13-184104 18:41:06 to 18:41:15, qy-wwP-b9HY-13-184117 18:41:18 to 18:41:29].
- Tongue: in Weight Paint, `Weights > Assign Automatic from Bones` (its tooltip says it weights to the selected
  bones only) with the tongue bones selected [qy-wwP-b9HY-13-184239 18:42:40]. Reader: blend the three tongue groups linearly.
- Scalps: he selects the scalp meshes (brow, hair, lashes, ponytail) plus the rig, `Ctrl P > With Empty Groups`, and
  assigns the main hair scalp to the head group in Edit Mode [qy-wwP-b9HY-13-184431 18:44:33 to 18:44:44]. The
  curves' Surface field names the scalp, which is why the scalp, not the curve, is parented [qy-wwP-b9HY-13-184353
  18:44:05]. Reader: `assign_all(scalp, "DEF-spine.006")`.
- Transfer: body active, scalp selected, `Weights > Transfer Weights` in Weight Paint; the redo panel reads Data Type
  `Vertex Group(s)`, Create Data on, Object Transform on, Vertex Mapping `Nearest Face Interpolated`, source layers
  `By Name` [qy-wwP-b9HY-13-184548 18:45:49 to 18:46:00]. Lashes and brows then close with the lid
  [qy-wwP-b9HY-13-184640 18:46:44 to 18:46:51]. The same recipe is used for the shirt: `With Empty Groups`, then
  transfer from the body (transcript; the frames only show the finished test) [qy-wwP-b9HY-13-184823 18:48:25].
  Reader: `copy_weights(body, scalp)` and `copy_weights(body, shirt)`.

### 12. Boots and skirt: helper proxies

- Boot helper: a cube is added (far larger than the character), renamed with `F2` after pasting the shoe's name,
  and dragged into `CH_..._rig_helpers` [qy-wwP-b9HY-13-184950 18:49:52 to 18:50:19]. It is shaped with
  `Ctrl R` loop cuts, then `Grab` in Sculpt Mode (Size 322 to 482 px, Strength 0.400 read) and a smooth pass until it
  hugs the boot just outside, kept clear of the boot surface [qy-wwP-b9HY-13-185234 18:52:36 to 18:52:50].
- Binding: the helper (modifiers `Mirror`, `Armature`) is parented to the rig with automatic weights
  [qy-wwP-b9HY-13-185357 18:53:59 to 18:54:07]. The real boot's stack reads `Mirror`, `Armature`, `SurfaceDeform`,
  `Subdivision`. In the SurfaceDeform panel the Target is the helper; Interpolation Falloff 4.000 and Strength 1.00
  are the defaults (read), then Bind [qy-wwP-b9HY-13-185505 18:55:07 to 18:55:18, qy-wwP-b9HY-13-185519 18:55:21].
  Simplify is on before binding.
- Test and hide: foot IK control moved and rotated; helper hidden via the outliner eye and camera icons, display as
  Wire [qy-wwP-b9HY-13-185603 18:56:05, qy-wwP-b9HY-13-185618 18:56:20 to 18:56:27]. The artist says automatic weights
  would not give this result.
- Skirt helper: shown at 4x speed. A cube is scaled and moved in the front view (`S`, `G Z`, X-ray) into a flat
  skirt, rotated around, loop-cut and shaped to hug the pleats; it carries a `Mirror` modifier; then `Ctrl P > With
  Automatic Weights` to the rig [qy-wwP-b9HY-13-185645 18:56:47 to 18:57:01, qy-wwP-b9HY-13-185728 18:57:31 to 18:57:47].
  Hips control rotated about 17 to 22 degrees (read) shows the skirt swing; clipping remains when a leg is raised
  [qy-wwP-b9HY-13-185827 18:58:29 to 18:58:41, qy-wwP-b9HY-13-185843 18:58:45 to 18:58:58]; the fix is to unbind,
  push the skirt out, rebind. The necklace is not shown; only said to be the same [qy-wwP-b9HY-13-190136 19:01:46].
  Reader: `follow_helper(part, helper, rig)`.

### 13. Hide skin under clothes

- The body stack reads `Armature`, `Mask`, `Subdivision` (Catmull-Clark, Levels Viewport 1, Render 2 read)
  [qy-wwP-b9HY-13-190211 19:02:28, qy-wwP-b9HY-13-185926 18:59:31]. Selecting the faces and the group are not on the sheets
  I read. To see the bare body he switches the Mask modifier's viewport icon off [qy-wwP-b9HY-13-190231 19:02:36].
  Reader: `body.modifiers["Mask"].show_viewport = False`.

### 14. Pose

- He poses the bare body first, with the helper collections hidden, using `G`, `R` and `Z` on foot, hips and chest
  controls; the rig's circle controls stay visible [qy-wwP-b9HY-13-190211 19:02:14 to 19:02:23].
- Pose asset: an editor next to the 3D viewport is switched to the Asset Browser (editor type menu), library
  `Current File`, catalog `Unassigned` [qy-wwP-b9HY-13-190244 19:02:49 to 19:02:55]. Creating the asset adds a thumbnail
  with the pose name and a camera appears in the outliner [qy-wwP-b9HY-13-190403 19:04:05 to 19:04:18,
  qy-wwP-b9HY-13-190420 19:04:22]. At least two poses are asked for. Reader: key two poses on frames 101 and 102
  as in step 14 and capture each with `viewport_capture(frame=...)`.

## Settings the course uses

| Setting | Value | Where | Time |
|---|---|---|---|
| Rig system | Rigify, `Human` metarig, face rig upgraded | Add menu; Armature data > Rigify | 17:43:10, 18:04:15 |
| Metarig display | `In Front` on; X-Axis Mirror on | Armature data > Viewport Display; tool options | 17:44:16, 17:45:47 |
| Face snapping | `Face Project`, rotate and scale options on | snapping menu | 17:55:55 |
| Body binding | `With Automatic Weights` | `Ctrl P` | 18:06:06 |
| Pose transforms | orientation `Local`, pivot `Individual Origins` | header | 18:14:30 |
| Simplify | on, `Max Subdivision` 0 | Render Properties | 18:17:19 |
| Weight paint | `Auto Normalize` on, X symmetry on | Weight Paint options | 18:19:10 |
| Lid control value for shut eye | Y location -0.024 (this character) | `lid.T.L.002` | 18:26:00 |
| Driver | `Averaged Value`, Y Location, `Local Space`, keys Linear | Drivers Editor | 18:30:29 |
| Weight transfer | `Nearest Face Interpolated`, match by name | Weights > Transfer Weights | 18:45:50 |
| Hair in viewport | `Viewport Amount` 0.02 | hair modifier input | 18:48:41 |
| Surface Deform | falloff 4.0, strength 1.0 (defaults), bound with Simplify on | modifier | 18:55:25 |
| Helper display | `Display As: Wire`, hidden in renders | Object > Viewport Display | 18:54:05 |
| Shape-key sculpt | `Grab`, Size 354 to 460 px, Strength 0.400 | Sculpt Mode header | 18:27:44 |
| Weight-paint header | Weight 1.000, Strength 1.000, Size 100 to 326 px | Weight Paint header | 18:19:10 to 18:25:05 |
| Finger rig edit | orientation `Normal`, `S Z 0`, `Ctrl R` roll | Edit Mode | 18:09:29, 18:12:32 |
| Helper sculpt | `Grab`, Size 322 to 482 px, Strength 0.400 | Sculpt Mode header | 18:52:46 |

## Mistakes the course warns about

- Scaling the metarig in Object Mode [17:43:36]. Moving one end of bones that only touch [17:46:09, 17:57:00].
- Pressing `F` between bone ends, which creates an extra bone [17:50:36].
- A perfectly straight knee, elbow or finger chain [17:48:06, 18:10:00].
- Forgetting the tongue and teeth bones [18:02:58], or the `face` bone inside the head bone [17:45:01].
- Editing the generated rig in Edit Mode [18:05:25].
- Automatic weights on eyes, teeth, layered boots [18:38:18, 18:49:09].
- `Armature` below `Subdivision` [18:28:03]. Binding Surface Deform with subdivision active [18:55:10].
- Parenting hair curves instead of the scalp meshes [18:44:01].

## What changes for a different character

General: Rigify, fit in Edit Mode, bent limbs, shared joints moved together, empty groups for rigid parts, weight
copy for tight cloth, helper plus Surface Deform for layered or stiff parts, the test poses.
Specific to this character: a stylized girl with a large head (the face box is wide, forehead bones sit high), a
skirt, tall boots, a ponytail.

- Other bipeds: same metarig. Very short limbs need a larger knee and elbow offset to keep the bend readable.
- No fingers, or mitten hands: delete the unused finger chains from the metarig before generating.
- Simple or mask-like face: delete every bone under `face` except `eye.L/R`, `jaw_master`, `teeth.*` and bind the
  head to `DEF-spine.006`; fewer bones give cleaner automatic weights.
- Creatures: `Add > Armature > Rigify Meta-Rigs` also has animal metarigs (the course mentions them, 17:32:57) and
  basic building blocks. `fit_metarig` here only knows the human bone names.
- Hard-surface parts (armour plates, weapons, props): no weights at all. Parent each to one bone
  (`part.parent = rig; part.parent_type = "BONE"; part.parent_bone = "DEF-forearm.L"`) so it stays rigid.
- Long hair, tails, capes: beyond the course. Add bone chains to the metarig (Rigify sample `basic.copy_chain`) or
  simulate; note it as a gap.

## Exit check

1. `check_metarig(meta)["ok"]` is True and `bpy.ops.pose.rigify_generate()` finishes.
2. `weight_report` shows `unweighted_verts` 0 for every bound mesh. Rigid parts: all weight on one bone.
3. Finger curl test moves each fingertip toward the palm, both hands.
4. `pose_report` on the body, mask off. Failed if any `stray_move` is above 1 percent of the character's height
   or any `volume_ratio` is below 0.80; between 0.80 and 0.90 look closely at that joint. These limits are mine: a
   crude test figure scored 0.87 on `knees_deep` and at most 0.008 m stray on a 1.1 m figure.
5. `motion_preview(frames=[1, 10, 20, 30, 40, 50])` with every part visible: none of the signs in the step 8
   table. A capture that was not made counts as not checked, not as passed.
6. On frame 1 the rig is at rest: `outline_match(object="CHARACTER", ...)` against the concept references (threshold 0.98) gives the same
   result as at the end of stage 09 for every view that has a real reference. Binding must not change the rest
   shape. A view with no reference is `not_run`: report it as looked at, not measured.
7. Two presentation poses keyed, frame numbers recorded, `turnaround_sheet` made for each. The posed outline is
   not compared with a neutral-pose reference; if the concept shows the same pose from the front, report that
   overlap as extra information only.

## For a game engine later

My notes, not from the course; a later pass will work these out.

- Control rig versus deform skeleton: `rig` has 918 bones, of which 171 `DEF-` bones deform. A game engine wants
  only a deform skeleton with one clean parent chain. Rigify's `DEF-` bones are parented to `ORG-`/`MCH-` bones,
  not to each other, so the hierarchy must be rebuilt or a game-oriented rig used instead.
- Bone count and stretch: limb segments are split in two for twist (`DEF-upper_arm.L`, `.L.001`) and use stretch
  and B-bone tricks that do not export; the face has dozens of small bones.
- Naming: `DEF-thigh.L` style names will not match the Unreal mannequin (`thigh_l`), which matters for retargeting.
- Scale and axes: Blender metres and Z-up versus Unreal centimetres; armature scale must export as 1.0.
- Corrective shape keys and their drivers: the keys export as morph targets, the drivers do not.
- `Surface Deform`, `Mask` and `Data Transfer` modifiers do not export; boots and skirt need real skin weights.
- Hair: curves and Geometry Nodes hair do not export as is; needs hair cards or a groom export.
- Root: Rigify's `root` control is not a deform bone; Unreal expects a root joint at the origin.

## Low-poly game route (second course: Nhij Quang, Girl#01)

Second source: Nhij Quang, [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), Blender 4.2.1 LTS, 1 h 15 min, no narration (music only). Everything here was read off the screen: the key-cast overlay, redo panels, modifier panels and status-bar counts, from 157 study sheets; labels are in `annotations/mlnR-Eyazh0/`. Times marked `NQ` point into that video, not the main course. Use this route instead of the sculpt route when the job is a low-poly game character (box/poly modelled, hand-painted, Mixamo-rigged); see "Two routes" in `SKILL.md`. Values that could not be read are listed as not visible, never guessed. Python blocks marked `# not run in Blender` were not executed.

Source: chapter 13 "Mixamo Rigging", 01:11:28 to 01:13:19. Mixamo is a website; the upload form, marker placement and Skeleton LOD screens are not in these frames.

Order of work
1. [NQ 01:11:28 to 01:11:45] Work on copies of the meshes: Body.001, Hair1.001, Hair2.001. In Edit Mode, front orthographic, select the arms and sleeves and rotate them up so the arms point straight out (a rotate value of 9.77 is visible). The reference sheet stays open in an Image Editor on the left. Result: textured T-pose. Material texture node reads female_char1, Linear, Flat, Repeat, Single Image, sRGB, Alpha Straight; Backface Culling off.
2. [NQ 01:11:52 to 01:12:06] Mixamo: the character FEMALE_CHAR1 is uploaded; the AUTO-RIGGER dialog shows "Processing upload", then "Auto-Rigging...", then "Review" with the rigged T-pose. Artist clicks Next.
3. [NQ 01:12:13 to 01:12:33] Pick animations in Mixamo. Search "run", choose Running: Overdrive 50, Character Arm-Space 50, Mirror off, In Place on. Download gives Running.fbx. Search "idle", choose Dwarf Idle: Overdrive 50, Character Arm-Space 50, Mirror off. Download gives Dwarf Idle.fbx.
4. [NQ 01:12:40 to 01:12:54] In a new Blender scene import the Mixamo FBX. Outliner: Armature with Animation, Pose, Armature, Body.001, Hair1.001, Hair2.001. Scene 4,458 verts / 3,805 faces / 7,372 tris. In the Shading workspace an Image Texture node is added to the hair material ("Shader") and the texture is reopened, then linked to the Principled BSDF. Result: textured, rigged character in Blender.
5. [NQ 01:13:01 to 01:13:08] Animation workspace, Pose Mode on the Armature. Action Editor shows action "Idle" with mixamorig:Hips, Spine, Spine1, Spine2, Neck, Head, LeftShoulder, LeftArm, LeftForeArm, LeftHand channels. Armature transform: Rotation X 90°, Scale 0.010 (as imported). 65 bones. End frame set (201 shown; 250 typed in one frame).
6. [NQ 01:13:15 to 01:13:19] File > Export > FBX into the Godot project folder (contains .godot, Asset, Scene). Options: Path Mode Auto, Batch Mode Off, Limit to (Selected Objects, Visible Objects, Active Collection) all off, Object Types all on (Empty, Camera, Lamp, Armature, Mesh, Other), Custom Properties off, Scale 1.00, Apply Scalings All Local, Forward -Z Forward, Up Y Up. File name field still "untitled.fbx" in the frame; in Godot the file is female_char1.fbx.

How it looks on screen
- Mesh copies (.001) are used for the rig, keeping the originals.
- Arms are posed out to a T-pose in Edit Mode before upload.
- Animations are previewed on the character in Mixamo before download.
- The run is downloaded with In Place on.
- The texture has to be relinked by hand after the round trip through Mixamo.
- Export goes straight into the game project folder.

Python route
Mixamo has no public API. The agent can prepare the upload file and handle the downloads; a person (or a browser session they are signed into) must do the Mixamo steps.
```python
# not run in Blender
import bpy
# Export the T-posed meshes for Mixamo upload (export settings for this upload
# are not shown in the video; embedding the texture is a guess).
bpy.ops.export_scene.fbx(
    filepath="//female_char1_mixamo_upload.fbx",
    use_selection=True,
    object_types={'MESH'},
    path_mode='COPY',
    embed_textures=True,
)
```
Hand to a person or a signed-in browser:
- mixamo.com > Upload Character > choose the FBX > wait for Auto-Rigging > Review > Next.
- Animations: search "run", pick "Running", tick In Place, Download. Search "idle", pick "Dwarf Idle", Download. Leave Overdrive 50 and Character Arm-Space 50.
- Return the downloaded FBX files to the agent.
```python
# not run in Blender
import bpy
bpy.ops.import_scene.fbx(filepath=r"C:\path\Running.fbx")
arm = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
# Expect rotation_euler.x = 90 deg and scale 0.01, as seen on screen.

# Relink the texture on each imported material
img = bpy.data.images.load(r"C:\path\female_char1.png", check_existing=True)
for ob in arm.children:
    for slot in ob.material_slots:
        nt = slot.material.node_tree
        bsdf = nt.nodes.get("Principled BSDF")
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

arm.animation_data.action = bpy.data.actions.get("Idle") or arm.animation_data.action
bpy.context.scene.frame_end = 201

bpy.ops.export_scene.fbx(
    filepath=r"C:\path\GodotProject\Asset\3d\female_char1.fbx",
    path_mode='AUTO',
    batch_mode='OFF',
    use_selection=False,
    use_visible=False,
    use_active_collection=False,
    object_types={'EMPTY', 'CAMERA', 'LIGHT', 'ARMATURE', 'MESH', 'OTHER'},
    use_custom_props=False,
    global_scale=1.0,
    apply_scale_options='FBX_SCALE_NONE',  # "All Local" in the UI
    axis_forward='-Z',
    axis_up='Y',
)
```
The Godot scene later shows both Armature|Run and Armature|Idle, so both actions end up in the exported file. How they were combined is not shown; one way is to import both FBX files and keep both actions on the one armature (for example as NLA strips) before export.

Settings read on screen
- Mesh copies: Body.001, Hair1.001, Hair2.001.
- Edit-mode rotate value seen: 9.77.
- Texture node: female_char1, Linear, Flat, Repeat, Single Image, sRGB, Alpha Straight.
- Mixamo Running: Overdrive 50, Character Arm-Space 50, Mirror off, In Place on.
- Mixamo Dwarf Idle: Overdrive 50, Character Arm-Space 50, Mirror off.
- Downloads: Running.fbx, Dwarf Idle.fbx.
- Imported armature: Rotation X 90°, Scale 0.010, 65 bones, mixamorig: bone names, action "Idle".
- FBX export: Path Mode Auto, Batch Mode Off, Limit to all off, Object Types all on, Custom Properties off, Scale 1.00, Apply Scalings All Local, Forward -Z, Up Y.

Not visible in the frames
- The FBX export settings used for the Mixamo upload.
- Mixamo marker placement (chin, wrists, elbows, knees, groin), Symmetry and Skeleton LOD choice.
- Mixamo download options (format, Skin with/without, frames per second, keyframe reduction).
- The FBX import options in Blender.
- How the Run and Idle actions were merged into one file, and the export file name at the moment of saving.
- The Bake Animation / Add Leaf Bones / Armature section of the export dialog (not scrolled into view).

## Gaps

- Add-ons: Rigify (built in, free) is what the course uses. It mentions Auto-Rig Pro (paid) as an alternative that
  can guess joint markers, and does not use it [17:33:40].
- Weight painting by brush (pressure, blur, subtract) has no blender-live equivalent; `paint` plus
  `vertex_group_smooth` is coarser. Sculpting a shape key with Grab is replaced by writing key coordinates.
- Face-bone placement is the weakest scripted step: the block fit and nearest-surface snap get close, but lid,
  lip and brow points need individual measured corrections, and nobody can measure "looks right" for a blink.
- `Assign Automatic from Bones` for the tongue needs Weight Paint mode with bones selected; not scripted here.
- Pose assets and their thumbnails need the Asset Browser UI; keyed frames stand in for them.
- The necklace helper is only mentioned, not shown [19:01:46]; the skirt helper is shown (sped up), see step 12.
  The final cleaned-up poses are made off-camera [19:22:00]. How the body faces for the `Mask` group are chosen
  [18:59:30] was not on the sheets I read.
- The course does not test the rig beyond trying controls; the test poses and all pass limits are mine.
- Checked on a simple test figure, not on a full character with face geometry; expect to adjust landmarks.
