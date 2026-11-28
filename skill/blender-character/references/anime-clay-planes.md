# Anime clay: planes first, then soften (MRScapsule)

How an anime figure sculptor gets stylised clay right: cut a sphere into hard planes on a very coarse mesh, place the
big features while it is still faceted, and only then raise the resolution and soften. Eyes are flat recessed
almonds with a crisp lid ledge, not eyeballs. Hair is many separate low-poly locks, each with a groove and a sharp
tip. Clothes are separate shells whose folds radiate from joints.

Read it with `clay-first.md` whenever the character is anime, manga, chibi or another stylised design with hard
planes and graphic eyes. It replaces the start of stage 03 (steps 1 to 6, the soft-head start) for those
characters. The clay gate in `clay-first.md` still applies unchanged.

**Source.** All 48 Shorts on [MRScapsule's channel](https://www.youtube.com/@MRScapsule/shorts), studied
2026-11-28. Each is under a minute, music only (Whisper found song lyrics, no speech), filmed with a phone pointed at
a pen display running ZBrush with a Spanish UI. Everything here was read off the screen: the stroke overlay
("SLICE Angle=162"), the DynaMesh "Resolución" field, the brush shelf, and the forms before and after. 285 frame
labels (200 seen, 85 inferred) are in `annotations/`; per-Short notes are in `notes/`. Both are local study
material, kept out of version control.

- **Tags** are `[MRS <video id> m:ss]`, e.g. `[MRS gNWARadhjOo 0:03]` is https://youtube.com/shorts/gNWARadhjOo at
  0:03.
- **He works in ZBrush, not Blender.** Every step below gives the `blender-live` call or `bpy` that does the same.
- **Numbers.** Header numbers were often unreadable, so few appear. The plane positions, voxel sizes and helper
  defaults are our own starting values, chosen so the helpers reproduce his shapes. Tune them to your concept.
- **Not every Short teaches clay.** Seven show printing, painting a print, laser engraving or a finished turntable
  only (`edSpP48sS8o`, `4ejOwACbArY`, `NNnMsFQ32p8`, `cXNcu1pGZx0`, `4ANMjdX954Y`, `JsCym90kVMA`, `51Rg_AGwxcs`).
  Their only clay lesson is under "Splitting for print".

## The idea

- **Planes before curves.** He never starts by pushing a soft ball around. A sphere becomes a box-like head with
  straight cuts: side planes, a front face plane, a chamfered forehead, a V jaw and a chin flat
  [MRS gNWARadhjOo 0:00-0:05], [MRS ITt7eUiRNMU 0:01-0:03], [MRS z-36nQJIqyc 0:05-0:06],
  [MRS kXZh6oOuNXQ 0:01-0:09], [MRS fvDubIJe1B4 0:13-0:15]. The planes are the anime look: a soft start never finds
  them again.
- **Resolution follows the stage.** Readable DynaMesh values climb as the work gets finer:
  - 64 → 368 → 1296 (Gojo) [MRS ITt7eUiRNMU 0:01, 0:05, 0:07];
  - 128 → 64 → 192 → 160 → 2144 → 3168 (Vegeta) [MRS z-36nQJIqyc 0:03-0:34];
  - 64 → 256 → 1776 [MRS fvDubIJe1B4 0:15, 0:16, 0:32]; 64 → 400 → 1000 [MRS Fo6_POBv3eU 0:02-0:07].

  Coarse while cutting, about 5× finer to soften and place features, 20× or more for line work.
- **The face is finished bald,** with hair added after it [MRS nPULrzd_mXQ 0:19], [MRS ITt7eUiRNMU 0:07].
- **Move parts, don't re-sculpt them.** He masks a feature (an ear, the mouth, a hand) and moves or rotates it with
  the Gizmo instead of redrawing it [MRS xZq4Gc9_oAI 0:07, 0:14], [MRS nPULrzd_mXQ 0:06-0:13],
  [MRS N-A0BX5UQUc 0:01].

## Helpers (paste into the `exec_python` call that uses them)

They need `world_co` and `slice_flat` from the helpers in `02-blockout.md`. The character faces -Y and is centred
on X = 0, as everywhere in this skill.

```python
# verified in 4.5.16 background
import bpy, bmesh, numpy as np
from math import pi, sin, cos, radians

def head_frame(ob):
    """World centre and half-sizes (X width, Y depth, Z height) of a part's bounding box."""
    w = world_co(ob); lo, hi = w.min(0), w.max(0)
    return (lo + hi) / 2, (hi - lo) / 2

# (point as fractions of the half-sizes from the centre, outward normal). Our starting values: tune to the concept.
ANIME_HEAD_PLANES = [
    ((0.80, 0.0, 0.05), (1, 0, 0)),           # side plane                       [MRS gNWARadhjOo 0:02]
    ((0.0, -0.82, 0.0), (0, -1, 0)),          # front face plane                 [MRS gNWARadhjOo 0:03]
    ((0.58, -0.58, 0.0), (1, -0.9, 0)),       # cheek/temple corner, front to side
    ((0.0, -0.55, 0.62), (0, -0.7, 1)),       # forehead-to-crown chamfer        [MRS fvDubIJe1B4 0:13]
    ((0.55, 0.0, 0.62), (1, 0, 1.1)),         # top corners
    ((0.32, -0.45, -0.50), (1, -0.35, -0.9)), # V jaw: side of the jaw toward the chin [MRS gNWARadhjOo 0:05]
    ((0.0, -0.55, -0.88), (0, -0.25, -1)),    # chin and under-jaw flat
]

def anime_head_planes(ob, planes=ANIME_HEAD_PLANES):
    """SliceCurve/TrimCurve on a sphere: flatten it onto each plane (mirrored when off-centre). Remesh afterwards:
    projection crowds vertices onto the plane."""
    c, h = head_frame(ob); moved = 0
    for frac, nrm in planes:
        pt = tuple(c + np.array(frac) * h)
        moved += slice_flat(ob, point=pt, normal=nrm, mirror_x=bool(frac[0] or nrm[0]))
    return moved

def nose_wedge(name, bridge, tip, width):
    """The anime nose as one pointed wedge block [MRS p-iHLZLWIhA 0:05], [MRS QUj_4xWbvB8 0:18]: a hull through the
    bridge point (on the face at eye level), the tip, two alae beside and behind the tip, and a point inside the
    head. Fuse it with join_and_fuse (03-sculpt-face.md helpers); a grab stroke only makes a round dome."""
    b, t = np.array(bridge, float), np.array(tip, float)
    pts = [b, t, t + (width / 2, 0.6 * width, 0.25 * width), t + (-width / 2, 0.6 * width, 0.25 * width),
           np.array((0.0, b[1] + 1.5 * width, t[2] + 0.3 * width))]
    bm = bmesh.new(); vs = [bm.verts.new(p) for p in pts]
    bmesh.ops.convex_hull(bm, input=vs)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    return ob

def almond_eye(ob, center, width, height, depth, tilt=8.0, lid=None, mirror_x=True):
    """Flat anime eye [MRS gNWARadhjOo 0:16-0:22]: push the almond (seen from the front) back to a flat floor
    `depth` behind the surface, following the face's turn, and raise a crisp upper-lid ledge along its top edge,
    heavier toward the outer corner. `center` is the +X eye in world space; `tilt` lifts the outer corner (degrees).
    lid = (ledge height, ledge width); default (0.3*depth, 0.22*height). Returns the number of vertices moved."""
    lid_h, lid_w = lid or (0.3 * depth, 0.22 * height)
    me = ob.data; inv = np.linalg.inv(np.array(ob.matrix_world))
    w = world_co(ob).astype(np.float64)
    n = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get("normal", n)
    n = n.reshape(-1, 3) @ np.array(ob.matrix_world)[:3, :3].T
    front = n[:, 1] < -0.15 * np.linalg.norm(n, axis=1)
    moved = np.zeros(len(w), bool); t = radians(tilt)
    for sx in ((1, -1) if mirror_x else (1,)):
        dx, dz = w[:, 0] * sx - center[0], w[:, 2] - center[2]           # mirror the -X eye into the +X frame
        u = (dx * cos(t) + dz * sin(t)) / (width / 2)                   # along the eye, +1 = outer corner
        v = (-dx * sin(t) + dz * cos(t)) / (height / 2)                 # across the eye, +1 = top
        arc = np.clip(1 - u ** 2, 0, None)
        top, bot = arc ** 0.55, -0.75 * arc ** 0.9                       # fuller upper arc than lower
        near = front & (np.abs(u) < 1) & (np.abs(w[:, 1] - center[1]) < 4 * depth + height)
        inside = near & (v < top) & (v > bot)
        if inside.sum() < 4: continue
        A = np.c_[np.ones(inside.sum()), w[inside, 0], w[inside, 2]]     # plane through the surface: y = a + b x + c z
        k = np.linalg.lstsq(A, w[inside, 1], rcond=None)[0]
        floor = k[0] + k[1] * w[:, 0] + k[2] * w[:, 2] + depth           # +Y is into the head
        edge = np.clip(np.minimum(top - v, v - bot) / 0.12, 0, 1)        # soften only the last 12 % at the rim
        y_in = w[:, 1] + (np.maximum(w[:, 1], floor) - w[:, 1]) * edge
        w[inside, 1] = y_in[inside]
        band = near & (v >= top) & (v < top + lid_w / (height / 2))      # upper lid ledge
        f = 1 - (v[band] - top[band]) / (lid_w / (height / 2))
        w[band, 1] -= lid_h * f * (0.65 + 0.35 * np.clip(u[band], 0, 1)) * (1 - np.abs(u[band]) ** 6)
        moved |= inside | band
    me.vertices.foreach_set("co", (w @ inv[:3, :3].T + inv[:3, 3]).astype(np.float32).ravel()); me.update()
    return int(moved.sum())

def hair_lock(name, root, ctrl, tip, width, thick, skull_c, groove=0.35, segs=6, levels=2):
    """One low-poly leaf lock, then Subdivision [MRS kXZh6oOuNXQ 0:26-0:35], [MRS S4Uh3LrrRkY 0:21]: a lens-section
    tube on a quadratic curve root -> ctrl -> tip. It is widest about a third of the way, closes to a sharp tip, and
    has a groove down its outer face. Sink `root` by `thick` + 5 mm below the cap surface."""
    P = lambda s: (1 - s) ** 2 * np.array(root) + 2 * (1 - s) * s * np.array(ctrl) + s ** 2 * np.array(tip)
    sec = [(1, 0), (0.45, 0.9), (0, 0.9 * (1 - groove)), (-0.45, 0.9), (-1, 0), (-0.45, -0.6), (0.45, -0.6)]
    bm = bmesh.new(); rings = []
    for i in range(segs + 1):
        s = i / segs; p = P(s)
        tan = P(min(s + 1e-3, 1)) - P(max(s - 1e-3, 0)); tan /= np.linalg.norm(tan)
        out = p - np.array(skull_c); out -= out.dot(tan) * tan; out /= np.linalg.norm(out)
        side = np.cross(tan, out)
        if i == segs:
            rings.append([bm.verts.new(p)]); break
        wd = width * (1 - s) ** 0.7 * (0.7 + 0.3 * sin(pi * min(1.5 * s, 1)))
        th = thick * (1 - s) ** 0.7
        rings.append([bm.verts.new(p + a * wd * side + b * th * out) for a, b in sec])
    bm.faces.new(rings[0][::-1])
    for r0, r1 in zip(rings[:-2], rings[1:-1]):
        for j in range(len(sec)):
            bm.faces.new((r0[j], r0[(j + 1) % len(sec)], r1[(j + 1) % len(sec)], r1[j]))
    for j in range(len(sec)):
        bm.faces.new((rings[-2][j], rings[-2][(j + 1) % len(sec)], rings[-1][0]))
    me = bpy.data.meshes.new(name); bm.normal_update(); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    sub = ob.modifiers.new("Subdivision", "SUBSURF"); sub.levels = sub.render_levels = levels
    return ob
```

How these were checked: `scripts/anime_clay_check.py` lifts these blocks out of this file and runs them in
Blender 4.5.16 in the background. It builds a 0.23 m head with steps 2 to 9 below:
- the head, all four locks, and the planes stage are each manifold and one part;
- the grey clay is captured from FRONT, 3/4, LEFT and 35° below.

It took four rounds to get clay that looks like his. Three of the lessons are Blender's, not his:
- **No very coarse remesh.** His DynaMesh 64 keeps a plane edge straight. A Blender voxel remesh at `h/24`
  turned the chin and jaw edges into stair-steps, and the softening carried them through as a torn edge. Remesh
  at `h/90` instead, **cut the planes again**, and remesh again. The second cut snaps the stairs back onto the
  plane.
- **`sculpt_relax` does not soften.** Taubin relax is built to keep the shape, so 30 passes still left gem-hard
  corners. Rounding the plane breaks takes the `smooth` brush (a plain Laplacian smooth in the test).
- **A grab stroke makes a round nose.** Its smooth falloff always gives a dome. The wedge has to be a block
  (`nose_wedge`) fused with `join_and_fuse`.

One more came from the test, about locks: a root buried 5 mm still showed its cap on the crown, because the lock is
thicker than that. Sink the root by **the lock's thickness plus 5 mm**.

## Order of work: the head

`h` is the head height (chin to crown). Get it from `mesh_report` or `head_frame(ob)[1][2] * 2`.
`sculpt_begin(object="BLK_head", symmetry="X")` throughout.

1. **Concept beside the clay.** He keeps the 2D drawing on a second monitor while cutting
   [MRS kXZh6oOuNXQ 0:01-0:05], [MRS fvDubIJe1B4 0:13], [MRS 3TW0wKxMhbM 0:01], and sometimes draws the pose
   himself first [MRS pelkVBXpjmk 0:01]. Live: `reference_setup`, and the Image Editor split from `clay-first.md`.
2. **A sphere at the head's size.** He starts from a DynaMesh sphere at resolution 64 to 128
   [MRS ITt7eUiRNMU 0:01], [MRS z-36nQJIqyc 0:03]. Live: a UV sphere (64 × 32) scaled to the concept's head width,
   depth and height, with the scale applied.
3. **Cut the planes** [MRS gNWARadhjOo 0:00-0:05].
   - In ZBrush he uses straight curve strokes; the overlay reads "SLICE Angle=…". The result is a flat trimmed
     face, so the stroke behaves as TrimCurve.
   - In Blender: `anime_head_planes(ob)`, `sculpt_remesh(voxel_size=h/90)`, `anime_head_planes(ob)` again, and
     `sculpt_remesh(voxel_size=h/90)` again.
     - The second cut cleans the stair-steps the first remesh leaves on every plane edge.
     - Do not go coarser than `h/90`; see "How these were checked".
   - Save `*_planes.blend`.
   - Read the planes against the concept from FRONT, LEFT and below.
     - A narrower anime jaw: move the V-jaw plane's point inward.
     - A rounder chibi skull needs fewer cuts: drop the top corners and keep the front plane
       [MRS S2XhDLNA1Rw 0:05].
4. **Steps for the brow and mouth while still faceted.** He cuts the brow as one hard horizontal shelf, so the eye
   band is a recessed strip, and puts the mouth in as a hard wedge [MRS kXZh6oOuNXQ 0:07],
   [MRS Md2esX8UGQU 0:04], [MRS 13pcbbTl8AY 0:03-0:05]. Live: two more `slice_flat` calls with the plane just
   behind the face plane, limited to the eye band by a `sculpt_mask` box first. Or one `crease` stroke along
   `brow_line` at radius `0.06*h`, strength 0.5.
5. **Soften without losing the planes** [MRS fvDubIJe1B4 0:16], [MRS z-36nQJIqyc 0:08]. He remeshes finer and
   rounds the block until the plane corners are soft but every plane still reads.
   - Live: `smooth` strokes along each plane break (radius `0.08*h`, strength 0.4 to 0.5, two or three passes),
     then `sculpt_relax` (2 to 3 iterations) to even the surface.
   - `sculpt_relax` alone does not round a corner (see "How these were checked").
   - Check a FRONT and a 3/4 capture: the face plane, cheek corners and V jaw must still read. If they have melted,
     reopen `*_planes.blend` and use fewer passes.
6. **Nose as one wedge, judged from the side and from below** [MRS mtQMrrS3EpY 0:03],
   [MRS gNWARadhjOo 0:07-0:10], [MRS p-iHLZLWIhA 0:05].
   - He pulls it out with a very large Move brush (size 206, read in mtQMrrS3EpY), then views it from under the
     chin.
   - A grab stroke only makes a dome. So, live:
     - make the wedge:
       `nose_wedge("BLK_nose", bridge=(0, face_y, eye_z), tip=(0, face_y - 0.06*h, eye_z - 0.13*h), width=0.09*h)`,
       where `face_y` is the face plane's Y at X = 0;
     - fuse it: `join_and_fuse([head, nose], head, h/220)`;
     - two `smooth` passes over it;
     - `viewport_capture` from LEFT and from 35° below.
   - Anime noses stay small and pointed, with almost no nostrils [MRS QUj_4xWbvB8 0:18],
     [MRS ITt7eUiRNMU 0:27]. A longer, adult nose: raise the `tip` offset, never the width.
7. **Guide lines before any carving.** He scratches light lines for the brows, eye corners and hairline onto the
   clay [MRS z-36nQJIqyc 0:08], [MRS xZq4Gc9_oAI 0:11], [MRS abVxPNIt2mc 0:23]. Live: `crease` at strength 0.15 and
   radius `0.015*h`. They are marks to judge from, not forms; check them in a FRONT capture against the concept.
8. **Ears as separate pieces,** placed afterwards [MRS mtQMrrS3EpY 0:17], [MRS uq9grb20Ohk 0:02]. Live: a flattened
   UV sphere `BLK_ears` with a Mirror modifier (mirror object `BLK_head`), shaped with `crease` for the rim.
9. **Raise the resolution, then do the eyes** [MRS kXZh6oOuNXQ 0:20], [MRS ITt7eUiRNMU 0:07]. The step 6 fuse
   already remeshed at `h/220`; otherwise `sculpt_remesh(voxel_size=h/220)` first.
   - He masks a large oval over each socket first [MRS gNWARadhjOo 0:16]. In Blender, `almond_eye` limits itself
     to the almond, so no mask is needed.
   - Then `almond_eye(ob, center=(eye_x, eye_y, eye_z), width=0.24*h, height=0.16*h, depth=0.012*h)`.
     At `height=0.12*h` the test eyes read as closed slits.
     - Anime eyes are big: about a quarter of the head height wide, set on the eye band from step 4.
     - Read `eye_x`, `eye_z` and the size off the concept; `eye_y` is the face surface there.
   - The result is a flat floor with a crisp edge and a thicker upper lid ledge flicking up at the outer corner.
     The lower edge is thin [MRS Y-_d_UJZGNo 0:26-0:32], [MRS abVxPNIt2mc 0:17-0:23].
   - **Iris rings and lash flicks are line relief on that floor** [MRS uq9grb20Ohk 0:05],
     [MRS kXZh6oOuNXQ 0:23]: `crease` strokes at strength 0.2 to 0.3 and radius `0.01*h`. Whether his darkest lines
     are carved or painted could not always be told; for clay, carve only the outline and the lid line.
10. **Expression as hard creases** [MRS 5MqQxvWUZ3w 0:01], [MRS ljcO0KMf0z4 0:03], [MRS QUj_4xWbvB8 0:19].
    - Anger: a sharp V of brow planes over the nose, plus two or three stacked furrows between the brows
      [MRS z-36nQJIqyc 0:18], [MRS wQosyucCd6c 0:05].
    - Live: `crease` with `"subtract": true` for a raised ridge and plain `crease` for the furrow, at radius
      `0.02*h`.
    - Push the expression early and big, at the step-5 resolution [MRS z-36nQJIqyc 0:09],
      [MRS Md2esX8UGQU 0:06]. A timid expression gets lost in the softening.
11. **Look from every side, including under the chin and behind** [MRS gNWARadhjOo 0:25],
    [MRS Y-_d_UJZGNo 0:10-0:12], [MRS F75YQr6v2_g 0:29]. Then run the clay pan from `clay-first.md`.

When you use this route, the stage 03 note "closed or stylised dot eyes: still place the eyeball" does not apply.
The flat almond is the socket.
- If the concept has round eyes that bulge in profile, use stage 03's eyeball and lids instead.
- If it is flat-drawn anime, use `almond_eye`, and from TOP check that the floor follows the face's turn (the
  fitted plane does this).
- If the job is a 1:1 match to specific drawings, `almond_eye` is only the block. Replace it with stage 03's
  drawn-eye carve (step 13, `scripts/face_draft_carve.py`), which traces the opening, lash rim and iris off the
  registered 2K pictures. `03-sculpt-face.md`, "Which eye method", compares all three.

## Hair

- **Two kinds of hair, chosen from the concept.**
  - **Tight or slicked-back hair is one mass on the skull.** Grooves are combed into it, with one graphic bang on
    top [MRS 7ZJQ8dykKXs 0:05], [MRS 5MqQxvWUZ3w 0:19]. Live: `extract_region` (stage 05) for the cap, `crease`
    strokes for the grooves, and one `hair_lock` for the bang.
  - **Everything else is separate locks over a smooth cap** [MRS abVxPNIt2mc 0:25-0:31],
    [MRS mUBPamyz5sY 0:04].
- **Each lock starts low-poly,** as a strip or tube with its own polygroup edited in ZModeler, and is subdivided
  after [MRS S4Uh3LrrRkY 0:21-0:26], [MRS 7ZJQ8dykKXs 0:06], [MRS kXZh6oOuNXQ 0:26-0:35]. Spiky hair starts as
  faceted cones that are softened later [MRS z-36nQJIqyc 0:27-0:30], [MRS nPULrzd_mXQ 0:20]. Live: `hair_lock`,
  one object per lock, named `HAIR_lock_NN`.
- **Shape language.** Locks are thick at the root and needle-sharp at the tip. They are leaf, claw or crescent
  shaped, each with a groove down its length, and layered like scales
  [MRS u9_EO62ikm4 0:11], [MRS whL56jhQImY 0:14], [MRS Fo6_POBv3eU 0:12], [MRS F75YQr6v2_g 0:01]. Long hair has
  S-curved ribbons ending in thin whip tails [MRS KZl96kqY7-4 0:03, 0:11]. Bangs are thin, with gaps between them
  [MRS VnTOaAfc_sc 0:12].
- **Order:** front bangs first, then the outer locks [MRS nPULrzd_mXQ 0:20]. Each is placed and turned with the
  Gizmo [MRS Fo6_POBv3eU 0:28], [MRS ITt7eUiRNMU 0:11]. Live: set `location` and `rotation_euler`, or give
  `hair_lock` a different `ctrl` point to bend it.
- **Clay checks still apply.**
  - Sink each root by the lock's `thick` plus about 5 mm below the cap surface. At 5 mm alone, the root cap of a
    12 mm lock showed on the crown in the test.
  - Find the surface point with `ray_cast` toward the skull centre.
  - Look from +35° and −35°. Locks are separate objects, so the pan shows any lock that floats off the cap.

## Body, hands, clothes

- **Anatomy under clothes.** He sculpts the back muscles, scapulae and spine even where cloth will cover them
  [MRS ITt7eUiRNMU 0:21], [MRS mUBPamyz5sY 0:02]. Muscles are round bulges separated by creases
  [MRS whL56jhQImY 0:28-0:32]. Live: `clay_strips` for the bulge, `crease` for the separation.
- **Hands from boxes.** A box palm and box fingers, posed by masking the rest and rotating with Transpose or the
  Gizmo [MRS uq9grb20Ohk 0:16-0:20], [MRS N-A0BX5UQUc 0:01].
  - Then carve deep separations between the fingers, cut nail edges, and add knuckle wrinkles with light
    subtractive strokes (Intensidad Z 22 read) [MRS Y-_d_UJZGNo 0:04-0:23], [MRS 9M0wp0WRmlM 0:05-0:14].
  - Live: stage 04's hand blockout, then `crease` at strength 0.2 for wrinkles. Rotate the finger groups about
    their knuckles in `exec_python`, not with brushes.
- **Clothes are separate low-poly shells with real thickness** [MRS ITt7eUiRNMU 0:16-0:25],
  [MRS I70-mhEPZdk 0:26], [MRS N-A0BX5UQUc 0:03]. In his Shorts:
  - trims (zips, sashes, cuffs) are their own groups, flat and hard-edged [MRS N-A0BX5UQUc 0:22],
    [MRS vBjjR5U8jnI 0:04], [MRS uq9grb20Ohk 0:30];
  - the shell is subdivided before folds go in;
  - folds are a few big ones radiating from tension points: shoulder, bent elbow, armpit, a hand in a pocket
    [MRS N-A0BX5UQUc 0:08-0:13], [MRS nNsBmHtTOgk 0:04-0:11], [MRS pelkVBXpjmk 0:10];
  - each fold is a long ridge that tapers into a pinched valley [MRS KZl96kqY7-4 0:12-0:15];
  - robes hang in long vertical folds [MRS VnTOaAfc_sc 0:10].

  Live:
  - stage 05's `extract_region` or a box-modelled shell, with a Solidify modifier for the thickness;
  - for each fold, `clay_strips` along the ridge from the tension point outward, then `crease` along the valley
    beside it;
  - check the folds from below at the armpit.
- **Torn cloth:** a jagged hem of pulled points with flaps folded back, and holes that keep the cloth's thickness
  [MRS whL56jhQImY 0:17], [MRS Fo6_POBv3eU 0:21-0:26]. Live: `snake_hook` for each point; cut holes before the
  Solidify modifier, so the rim keeps its thickness.
- **Hard accessories are modelled, not sculpted.** Chokers, swords, staples and earrings are low-poly pieces with
  edge loops, placed with the Gizmo [MRS kXZh6oOuNXQ 0:37-0:42], [MRS I70-mhEPZdk 0:05-0:08],
  [MRS wQosyucCd6c 0:03]. Repeated hard parts sit along a seam, with the skin pressed down around each one
  [MRS F75YQr6v2_g 0:03-0:21]. Live: `exec_python` primitives plus bevel. Press the skin with a `crease` ring
  around each part.

## Splitting for print (the print Shorts)

His printed figures are cut at clothing seams: trouser leg, boot sole, cuff, collar, hat. The parts are keyed with
square pegs [MRS NNnMsFQ32p8 0:05, 0:14], [MRS 4ejOwACbArY 0:02-0:10], [MRS cXNcu1pGZx0 0:24]. When a
character is for print, keep each garment a separate closed shell, so the cuts fall on real seams.

## Not visible in any Short

- how the hair locks were first generated (an `SK_Hair` curve brush is on the shelf and is used once
  [MRS jjiJFmZSLJ8 0:23], but the set-up is never shown);
- any ZRemesher or retopology step;
- symmetry settings;
- the exact plane cut tool (Slice, Trim or Clip curve) for most cuts;
- whether the darkest eye and tattoo lines are carved or painted;
- how ears are built step by step.
