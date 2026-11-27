---
name: blender-character
description: Build a whole character in Blender from concept pictures by hand, stage by stage - blockout, sculpt, clothes, retopology, UVs, hair, shading, rig, lighting - through the blender-live MCP tools, measuring likeness against the references after each stage. Use when asked to sculpt, model, retopologize, unwrap, groom, shade, rig or present a character (human, creature, stylized) in Blender, or to make a 3D character from a concept image, reference sheet or turnaround.
---

# Blender character from concept pictures

You are going to build a character the way a character artist does, in a live Blender you drive through the
`blender-live` MCP tools. You cannot use the mouse or hotkeys. Everything is a tool call or Python (`bpy`) run with
`exec_python`.

The method comes from a 20-hour character course, condensed into one reference file per stage. Read a stage's file
when you start that stage, not before. Each ends with an exit check; do the check before moving on.

## Before you start

1. Call `blender_status`. If no Blender answers, call `blender_launch`. If the `blender-live` tools are missing,
   stop and say so: this skill needs that MCP server (see the repository README for setup).
2. Find out what reference pictures exist. Ask for them if none were given.
3. Read `references/01-concept-and-references.md` and set the references up.
4. Save the file to a new `.blend` right away, and save again at the end of every stage under a new name
   (`character_02_blockout.blend`, `character_03_face.blend`, ...). There is no undo across tool calls; a saved
   stage is your undo.

## Stages

| # | Stage | Read | Ends with |
|---|-------|------|-----------|
| 01 | Concept and references | `references/01-concept-and-references.md` | references placed, views listed as measured or not |
| 02 | Blockout | `references/02-blockout.md` | big forms match the references |
| 03 | Sculpt the face | `references/03-sculpt-face.md` | face reads as the character |
| 04 | Sculpt the body | `references/04-sculpt-body.md` | body forms and anatomy |
| 05 | Clothes and accessories | `references/05-clothes-accessories.md` | separate named pieces |
| 06 | Retopology | `references/06-retopology.md` | clean low-poly mesh that deforms |
| 07 | UVs | `references/07-uv.md` | unwrapped, no overlap |
| 08 | Hair | `references/08-hair.md` | groomed hair, brows, lashes |
| 09 | Shading and texturing | `references/09-shading-texturing.md` | materials on every piece |
| 10 | Rigging and posing | `references/10-rigging-posing.md` | rig that survives the test poses |
| 11 | Lighting and presenting | `references/11-lighting-presenting.md` | final renders |

Do them in order. Stages 02 to 05 decide the likeness; do not move past 05 with a failing outline, because every
later stage copies the shape it is given.

## Conventions

- Z is up. The character stands on Z = 0 and faces -Y, so Blender's FRONT view sees its face.
- View names are Blender's. RIGHT looks from +X, which shows the character's LEFT side. Label reference pictures by
  the Blender view they were drawn from, not by the character's left and right.
- Model in a neutral pose (arms away from the body, legs slightly apart), whatever pose the concept shows. A posed
  model cannot be rigged well. Posing happens in stage 10.
- Work symmetric (`sculpt_begin(object, symmetry="X")`) until the design itself is asymmetric.
- Real size from the start: the character is about 1.7 m tall unless the design says otherwise. Stage files give
  sizes as fractions of height `H`, so other heights work.
- Use the names below. Later stages find objects by these names; a different name breaks their code.
- Sizes in the stage files are given relative to the feature or the character's height. Get real numbers from
  `mesh_report` (`bounds_min`, `bounds_max`) or `object_info` before choosing a brush radius.

### Names

| Name | What | Made in | Used until |
|------|------|---------|------------|
| `REF_FRONT`, `REF_RIGHT`, ... | reference picture empties, one per view with a real picture | 01 | the end |
| `CHARACTER` | an empty at the origin; every part, garment, eye, hair and lowpoly object is parented to it, keeping its transform | 02, before the first part | the end |
| `BLK_head`, `BLK_neck`, `BLK_ears`, `BLK_torso_upper`, `BLK_torso_mid`, `BLK_pelvis`, `BLK_upper_leg`, `BLK_lower_leg`, `BLK_foot`, `BLK_shoulder`, `BLK_upper_arm`, `BLK_lower_arm`, `BLK_hand` | the 13 blockout parts, sculpted in place; paired parts carry a `Mirror` modifier | 02 | 06 |
| `BLK_nose`, `BLK_eye` | parts stage 03 adds; the nose is joined into `BLK_head`; `BLK_eye` is mirrored | 03 | 06 |
| `BLK_leg`, `BLK_torso`, `BLK_arm`; new `BLK_hand`, `BLK_foot` | stage 04 joins upper + lower leg, the three torso parts, and shoulder + upper + lower arm; it rebuilds hand and foot with fingers and toes | 04 | 06 |
| `Shirt`, `Trousers`, `Skirt`, `Boot.L`, `Boot.R`, `Hair.Cap`, `Hair.Lock` | garments and placeholder hair, one object each | 05 | 06 (cloth) and 08 (hair) |
| `Body` | the body parts fused into one sculpt (hands and feet added by Boolean) | 06, first step | 06 |
| `body_retopo`, `Shirt_retopo`, `Skirt_retopo`, `Boot.L_retopo`, `Boot.R_retopo` | the lowpoly meshes that go on to UVs, shading and the rig | 06 | the end |
| `Eye.L`, `Eye.R`, `Mouth` | eyeballs; teeth, gums and tongue in one object | 06 | the end |
| `hair_scalp` and the other scalp meshes, hair curves on them | the groom | 08 | the end |
| `Hair.Band` | the band where the hair is gathered | 08 | the end |
| `rig` | the generated Rigify rig (fitted from `metarig`), with Rigify's own `WGT-*` widget meshes in `WGTS_rig` | 10 | the end |
| camera, lights, `backdrop` | the presentation set | 11 | the end |

Temporary objects: some stages make throwaway objects for one job and delete or hide them after: `BLOCKOUT_PROXY`
(02, a fused copy for `mesh_report` numbers only), `BLKC_*` (02, clothing stand-ins), `BLK_hand_old`,
`BLK_foot_old`, `Finger_*`, `Toe_*` (04, joined or deleted), `BODY_TMP` (05, a hidden fused copy cloth is fitted
to), `*_blockout` (05, undo copies), `body_quadriflow` (06), `HAIR_OUTLINE_PROXY` and `hair_proxy_tubes` (08, a
mesh stand-in so hair can be measured), `*_rig_helper` (10, 11). A fused copy is never the character itself: the
parts stay separate until stage 06.

`turnaround_sheet(object="CHARACTER")` and `outline_match(object="CHARACTER", ...)` show and measure the whole
character, because an object's children are always included. `also` is still there for an object that is not under
`CHARACTER`. When the course's own names differ (it keeps Blender's defaults, or renames to `GEO_<name>_<part>` in
its shading chapter), the stage files say so and keep the names above.

## The sculpting loop

The sculpt tools move vertices directly. They do not depend on the viewport and they give the same result every
time. Work in short loops:

1. **Look.** `turnaround_sheet(object, references={...})` puts every side next to its reference picture.
2. **Decide one change.** Biggest error first: overall proportion before a limb's shape, a limb's shape before a
   muscle, a muscle before a wrinkle. If the silhouette is wrong, no surface detail will fix it.
3. **Stroke.** `sculpt_strokes` with a few strokes. Start points on the surface (`"snap": true`). Read the result:
   `moved_verts` of 0 means the stroke missed. `max_move` tells you how far it went.
4. **Look again**, from the view where the change should show and from one view at a right angle to it. A change
   that fixes the front often breaks the side.
5. **Measure** with `outline_match` once the forms are close. Use the overlay: red is where the model is missing
   shape the reference has, blue is where the model has extra.

Brush choice:

| Job | Brush |
|-----|-------|
| Move a whole region, fix proportion, set the silhouette | `grab` with a large radius (a third to half of the part) |
| Pull out a limb, ear, horn, finger, tail | `snake_hook` |
| Build up a broad form (cheek, muscle mass, brow ridge) | `clay_strips` |
| Raise or lower a smaller form | `draw` |
| Swell a volume evenly | `inflate` |
| Cut a fold, lid line, lip line, muscle separation | `crease` |
| Calm lumps and blend strokes together | `smooth` |

When strokes have stretched the faces so they no longer hold detail (long thin triangles, faceted curves), call
`sculpt_remesh`. Halve the voxel size only when the current density cannot hold the next level of detail; every
halving multiplies the vertex count by about four.

Use `sculpt_mask(op="box", ...)` to protect what is already right before large moves nearby, and clear it after.

`"snap": true` moves a `grab` or `snake_hook` path so its first point sits on the surface and keeps its shape; for
the other brushes it puts every point on the surface. Objects must have uniform scale (apply scale first).

The course keeps the body as separate parts through the blockout, sculpting and clothes (stages 02 to 05). It joins
only locally: the nose into the head (stage 03); fingers into the hand, toes into the foot, and each limb's pieces
and the torso's three parts into `BLK_leg`, `BLK_arm` and `BLK_torso` (stage 04). The body is fused into one mesh, `Body`,
at the start of retopology (stage 06). Until then, look and measure with `object="CHARACTER"` so the whole
character is seen, not one part.

## Measuring likeness

The target is an outline overlap of **0.98 in every view that has a real reference picture**.

- `outline_match(object="CHARACTER", references, threshold=0.98)` is the only tool here that measures. Measure
  the whole character: the object, its children and every `also` object form one outline. Measuring one part
  against a crop is a diagnostic, never a stage result. It compares the model's
  orthographic outline with each reference picture and returns `passed`, `failed` or `not_run` per view.
- `not_run` means there is no reference picture for that view, so nothing was checked. Report such a view as
  "looked at, not measured". Never report it as passed, and never report the character as matching "in 3D" when
  only one view was measured: one picture fixes the shape from one direction and says nothing about depth.
- A reference only counts if it is a real picture of the design from that side: supplied by the person, or cut
  from their own turnaround. Do not draw or generate the missing views and then measure against them.
- A posed or perspective concept cannot be measured against a neutral-pose model. Say so; do not bend the model
  to fit it and do not lower the threshold.
- `failed` at 0.97 is failed. Report the number. Keep working or say where it stalled and why.
- `turnaround_sheet` and `viewport_capture` are for looking. Looking is necessary, but it is not a measurement.

`outline_match` sees outline only. Depth inside the outline, surface detail and colour are judged by eye from the
turnaround against the references, and reported as judged by eye.

## Reporting

At the end of each stage, and at the end of the job, report as a list:

- each view: measured overlap and `passed` / `failed`, or "looked at, not measured"
- `mesh_report` numbers that matter for the stage (holes, loose parts, face count, and symmetry: `symmetry_error`, `symmetry_p95_error`, `symmetry_max_error`)
- what was saved and where
- what is not done, and what was skipped or simplified, said plainly

The person asking is the final judge of likeness. Show them the turnaround sheet and the outline overlay, not a
summary of them.

## Tools at a glance

| Tool | Use |
|------|-----|
| `blender_status`, `blender_launch`, `open_file`, `save_file`, `set_frame` | session, files and timeline |
| `exec_python` | anything `bpy` can do: primitives, modifiers, joins, bmesh, nodes, rigs |
| `scene_tree`, `object_info`, `mesh_report` | read the scene and mesh health as numbers |
| `reference_setup` | place concept pictures as `REF_<VIEW>` image empties |
| `sculpt_begin`, `sculpt_strokes`, `sculpt_remesh`, `sculpt_mask` | sculpting |
| `viewport_capture`, `turnaround_sheet`, `render_image`, `motion_preview` | look |
| `outline_match`, `compare_images` | measure |
| `headless_run` | long background jobs (bakes, renders) |

Blender's own interactive tools (its sculpt brushes, snapping while drawing vertices, weight painting by hand) are
not available to you. Each stage file gives the scripted route for the steps where the course uses one, and says
plainly where the scripted route is weaker.
