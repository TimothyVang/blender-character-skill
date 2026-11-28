# Clay first: get the untextured shape to 1:1 before any paint

A sculptor finishes the clay, then paints. Do the same. No UVs, no `project_paint`, no colour of any kind until the
grey clay matches the pictures from every angle. This file is the rule and how to meet it. It was learnt the hard
way on the Ghibli-style test character (omp sessions, 2026-11-27 and 28). The numbers below come from that run.

## Why: paint hides wrong shapes

The first attempt projected the drawings onto the model and tuned the paint until FRONT and LEFT passed every gate
(`iou` 0.984, SSIM 0.82, delta E 1.6). It still looked wrong from angles the drawings do not cover:
- a fringe floating in front of the face;
- hair made of three nested shells ("a head inside a head" from below);
- a jaw too narrow;
- a second face at three-quarter view.

Paint from four level pictures cannot fix a wrong surface. It stretches one row of drawing pixels across any
surface it sees edge-on. Every later stage copies the shape it is given.

Mistakes to avoid:
- **Do not shape by looking at paint.** Carving the model to where the drawing's colours land is the same mistake.
- **Moving, rotating or scaling a whole part is alignment, not sculpting.** Use it for proportions, then sculpt the
  forms.

## The bar: what "clay 1:1" means

All of these, measured on untextured grey clay (paint and textures off), before stage 06/07:

1. **Outline:** `outline_match` `>= 0.98` on every chosen view (usually FRONT and LEFT; see `reference_pairs`).
2. **The 48-view clay pan is clean:** no open finding (below).
3. **`orbit_check(elevations=[-30, 0, 30])`:** `failed: 0`, `clay_banding_ratio <= 1.60` everywhere.
4. **Landmarks:** chin, mouth, nose tip, eye centre, brow and ear sit at the heights and depths measured on the 2K
   front and side pictures (loop step 2 of `likeness-1to1.md`). The front and side pictures must agree on every
   height first.
5. **`mesh_report`:** no holes, no stray loose parts, symmetry where the design is symmetric.

**A target like "99.99 %" means zero open findings on the clay pan and every number above passed.** It does not mean
an outline IoU of 0.9999. Outline IoU has a ceiling set by the pictures:
- they disagree with each other (`reference_pairs` FRONT/BACK 0.889, LEFT/RIGHT 0.878 on the test character);
- the edge pixels are anti-aliased.

Report the IoU you reached, the ceiling, and the pixels left, never a rounded-up pass.

## The 48-view clay pan (the gate the level views miss)

The level FRONT and LEFT views passed while the clay above and behind was ruined. Only a pan from above and below
showed it. Run the pan after every shaping round, not just at the end.

```python
# not a tool: run with exec_python. Neutral grey studio clay with cavity, in every 3D viewport.
import bpy
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        sh = area.spaces.active.shading
        sh.type = 'SOLID'; sh.light = 'STUDIO'; sh.color_type = 'SINGLE'
        sh.single_color = (0.62, 0.62, 0.62); sh.show_cavity = True; sh.cavity_type = 'BOTH'
        sh.show_backface_culling = False          # see shells and holes as they are
result = 'clay'
```

- **What to capture:** 8 azimuths (every 45°) × 3 elevations (−35°, 0°, +35°), once framed on the head (about 0.9 m
  away for a 1.7 m character) and once on the whole body. That is 24 + 24 views; tile them into two sheets.
- **How to capture:** snap the view rotation directly before each capture. `view_axis` animates, and a capture
  taken mid-turn shows the wrong angle without the reference behind it.
- **Look at every cell:**
  - boxy or slab-sided crowns, chests and bows ("cardboard");
  - horizontal shelves or bands;
  - jagged or wavy hems;
  - crumpled, pinched or claw-like fingers;
  - kinked or buried straps;
  - floating locks, or locks that read as separate pods;
  - fringe roots poking through the cap;
  - inner shells or a second face visible from below;
  - holes beside the face;
  - parts poking through clothes (a shoulder through an armhole);
  - flat noses or bulging eyeballs.
- **Show the person the sheets.** Show the hero views (front, side, 3/4, from below) and the two pan sheets as PNGs
  in the chat. They asked to see the clay without colour.

## Order of work

1. **2K pictures first (stage 01).** Upscale small art 4× with an anime upscaler (`realesrgan-x4plus-anime` worked),
   crop tight, and scale to about 2,048 px tall. Stage 01's `check_reference` must report `cropped_tight` and
   `sharp_enough`.
   Measure landmarks off these.
2. **Keep the reference beside the clay.** Split an Image Editor with the drawing next to the viewport, the
   reference empties behind the model, and the view framed on the part being worked, so the person (and you) can
   watch. Work in short visible steps and report numbers after each.
3. **Blockout parts sink into each other.** Stacked balls (a round egg skirt, sphere sleeves, detached hands) are
   the stage 02 mistake. Measure the blockout outline at once: on the test it read 0.807/0.820, and fixing the
   proportions it named took it to 0.853/0.863.
4. **Proportions by moving whole parts** (shift, rotate about the joint, scale), read off the overlay: about
   1 to 2 cm per move. It took the clean rebuild from 0.868 to 0.871/0.875 with zero distortion, and the overlay
   names the next move each time.
5. **Sculpt the forms**, face first, each checked from front, side, 3/4 and below. Then hands, hair and clothes
   (rules below).
6. **Close the last percent without wrecking the clay.** In order of preference:
   - **Fit each part to the pictures' own profile.** For each part, cut its region out of the 2K FRONT and side
     pictures by its colour (skirt navy, hair brown, bow red, shirt cream, boots brown), so an arm drawn over the
     skirt cannot leak into the skirt's curve. Read per height the centre and half-width (front: `cx(z)`, `rx(z)`;
     side: `cy(z)`, `ry(z)`), Gaussian-smooth the curves, and shape the clean subdivided mesh to them.
     - On the test this rebuilt hair, hands, skirt and boots clean in all 48 views, with the body already about
       0.97 with no `fit_outline` at all.
     - Whether it alone reaches 0.98 was still being measured when this was written.
   - **Surgical moves** for small parts: rotate a hand about its wrist (hands were off by 6° to 16° again and again),
     lower a bow 2 cm, nod the head 2.5°, nudge a profile 3 to 5 mm.
   - **`fit_outline` only as a last, bounded step** (rules below), and run the clay pan right after it.
7. **Clay gate passed:** save under a new name, reopen, re-measure, show the sheets. Only then go to stages 06/07 and
   paint.

## `fit_outline`: what it does to clay, and the only safe way to use it

`fit_outline` warps the surface in the picture plane to the drawn outline. Level views reward it. The pan showed
what it does elsewhere:
- **narrow `sigma_px` (1.2 to 3.5):** cardboard-box crowns, chests and bows; a hem torn into teeth; fingers crumpled
  into twigs; a horizontal shelf across the back of the hair; a headband buried at the sides;
- **even broad and masked:** a shelf on the back of the hair, a ballooned skirt above a masked hem, pinched hands.

If you use it at all:
- **Broad only:** `sigma_px` 6 to 10 (10, then 7). Follow every round with Taubin `sculpt_relax`, then the clay pan.
- **Mask what must stay as sculpted:**
  - always: the face and head, eyeballs, brows and lashes, the hands, the top of the crown;
  - during side (LEFT) passes, also the hands: they are edge-on and get pulled thin.
- **Apply Mirror modifiers first.** The warp moves the evaluated surface.
- **Damp it.**
  - `strength` 0.3 to 0.5, with `max_px` about 2.5 (about 3.5 mm).
  - At 0.75 to 0.9 with a small sigma it overshot one-pixel edges and oscillated (0.9747 to 0.9759 and back).
- **Keep `rim_angle` at 50 to 60°.** At 20° front-facing interior vertices count as rim and drown the real
  silhouette (FRONT fell 0.9745 to 0.9712).
- **Decouple the views.** A FRONT pass moves X and Z, and a side pass moves Y and Z. Both move Z, so each can undo
  the other.
  - `fit_outline` has no axis option. Snapshot the vertex positions before a side pass and put X and Z back after
    it, so only Y changes. That keeps FRONT exactly where it was.
  - When FRONT stalls, restore Z after a FRONT pass instead: if it then barely moves, the error is in Z.
- **Hill-climb.** Snapshot the best `min(FRONT, LEFT)` state and return to it when a pass makes things worse.
- **Stop when it plateaus** (the test sat at 0.9768/0.9786 through eight passes) or when the pan shows damage. Go
  back to step 6's part fitting; do not grind.

## Reading the outline overlay

`outline_match` returns an overlay: white where model and picture agree, **red where the picture has shape the model
lacks, blue where the model has shape the picture does not**. Read it before every move; it names the part and the
direction ("hands 12° too far up: blue on thumbs, red on lower fingers").
- **When a number moves the wrong way,** check `registration` (`dx`, `dy`, `scale`) for its clamp before blaming
  the shape.
- **Count where the error is:** on the test, 65 % of the last FRONT error sat on the fingers. Fix the part that holds
  most of it.

## Shape rules that came out of the pan

- **Hair is one continuous volume sitting on the skull** (stage 08's "split into volumes" means masses, not
  stacked shells):
  - no nested shells, no separate pods stuck on a dome;
  - the fringe is broad, flat, overlapping ribbons of varied width, with roots buried about 5 mm under the cap;
  - check the crown from +35° and the underside from −35°;
  - a hair mesh over the face needs the face cut out of it, and backface culling on hair materials hides inner
    faces seen from below.
- **Hands:** keep them plump. Build them at the drawn finger angle and mask them from warps. When warps pinch them,
  rebuild rather than repair.
- **Clothes:** tuck body parts inside clothes so nothing pokes through. Keep hems one even ring, and cuffs smooth.
- **Placeholder strips** (stage 03 brows and lashes) render as jagged lines. Delete them before paint when the paint
  carries brows and lashes.

## Keeping Blender alive while you work

- Long commands block Blender's main thread: it looks frozen and the person cannot watch. Use short steps, one long
  call per message.
- Set `undo_steps = 8` and `undo_memory_limit = 2048` after every file open.
- Save a numbered `.blend` before each risky pass (`*_prefit`, `*_clean_clay`). When a pass damages the clay, reopen
  the clean file rather than repair.
- A `MemoryError` on a small allocation is Windows commit headroom, not Blender. A capture that times out can leave
  Blender hung: check `ping`, restart on the last saved file.

## After the clay gate

Paint as `09-shading-texturing.md` and `likeness-1to1.md` step 6 describe:
- a flat colour per part first;
- drawn details only where a picture faces the surface squarely;
- undersides as flat sampled colours.

The paint gates (SSIM, delta E, three-quarter) are judged on a shape that is already right. When paint fails a gate
because the shape is wrong, go back to clay, not to painter settings.
