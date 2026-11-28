# 1:1 likeness proof

`outline_match` proves the outline. This file is the rest of the **proof**: the model's pixels, colours and
surface against the reference pictures, from every angle. For a 1:1 job, its Landmarks step (loop step 2) shapes
the model from stage 02 on; the measured proof runs from stage 09 on (once UVs exist), and again after any later
change to shape, UVs or materials.

The proof has two kinds of evidence, reported separately:

- **Measured**: numbers from `visual_match`, `orbit_check`, `three_quarter_check` and `project_paint`. Pass or fail
  against the gates below.
- **Judged by eye**: your own AI-vision review of the sheets those tools return, against the checklist below. It
  catches what no number here sees (a flat face, a second eye painted on a cheek). Report it as judged, with the
  sheet path, never as measured.

## Gates

| Tool | Gate | Pass | What it catches |
|------|------|------|-----------------|
| `visual_match` | `iou` | `>= 0.98` | outline, after the reported `registration` |
| | `ssim` | `>= 0.78` | structure of the picture inside the outline (masked to the character) |
| | `interior_edge_f1` | `>= 0.60` | drawn lines, hems and colour boundaries in the right place (2 px tolerance) |
| | `delta_e_mean` | `<= 10` | colour: CIEDE2000 per pixel on the shared interior, like a print proof |
| | `clay_banding_ratio` | `<= 1.60` | terraces: repeated horizontal ridges in the untextured clay; paint cannot hide them |
| `orbit_check` | `clay_banding_ratio`, `missing_texture_pct` | `<= 1.60`, `<= 0.5 %` per angle | the same surface faults from every azimuth and elevation, and magenta missing images |
| `three_quarter_check` | `delta_e_mean` per region (head, body, legs) of each in-between angle | `<= 12` | the two neighbouring pictures painted on their own disagree at 45/135/225/315 degrees: a feature they put on different surfaces (side eye on the cheek, hair on bare skin, a head too wide in front of the ear) |
| `project_paint` | `cross_view.conflict_pct` | report it | share of texels where the two strongest pictures disagree by more than delta E 15 |

`visual_match` also returns, per view, `delta_e_p90`, `within_de5_pct`, `within_de10_pct` and `inks`: the
reference's dominant colours as hex next to the model's mean colour on the same pixels and their delta E. Read the
inks like a printer's colour bar: a skin ink at delta E 1.5 is right; a skirt ink at delta E 18 names the part to
fix. Delta E about 1 is a just-noticeable difference; 2 to 5 reads as the same colour; above 10 is a different one.

What the numbers looked like on a real job (Ghibli-style girl, Midjourney front, back and side pictures):

| Model | view | iou | ssim | edge F1 | delta E | banding |
|-------|------|-----|------|---------|---------|---------|
| ring-stacked slice loft, vertex colours | FRONT | 0.972 | 0.43 | 0.66 | 13.8 | 14.3 |
| remeshed, relaxed, `fit_outline`, sculpted, `project_paint` | FRONT | 0.980 | 0.79 | 0.96 | 1.35 | 0.60 |
| same | LEFT | 0.983 | 0.70 | 0.90 | 2.85 | 0.53 |

## The loop

Work the biggest failure first, in this order, and re-measure after each step:

1. **Pictures.** Read `reference_pairs` from `outline_match`. A pair below 0.98 cannot both pass: choose the view
   the person cares about (usually FRONT, and LEFT or RIGHT), leave the other out of `fit_outline` and
   `project_paint`'s priority, and report the pair number. Leave posed pictures (a T-pose TOP for an A-pose model)
   out of everything but the report.
2. **Landmarks.** Measure the pictures before shaping, and shape the model so every pair of neighbouring pictures
   puts the same feature on the same surface; at stage 02 for the blockout, and again before every paint. Read
   numbers from the pictures, never by eye: map picture pixels to world through the figure's tight box against the
   model's (front: x and z; side: depth y and z, the face toward the picture's front edge); the iris the front
   picture paints onto the model confirms the mapping. Per height, read: the front picture's skin width at cheek and
   temple; each side picture's hair line (walk back from the face until skin turns into a solid run of hair); the
   iris (front gives x, each side gives depth). Then, on each side with that side's own picture (left and right
   pictures of one character disagree by centimetres):
   - at the side iris's depth, the face's front surface sits at the front iris's x. A face too round there puts the
     side eye on the cheek: three-quarter views show two faces. Narrow the front half toward the centre line.
   - in front of the side hair line the head is no wider than the front picture's skin edge. Wider, and the front
     picture paints its hair onto the side of the head while the side picture paints skin there.
   - hair vertices in front of the side hair line move back onto it, below the fringe. Hair left in front stands
     beside the cheek like a flap: skin from the side, hair from the front, a lock down the cheek at three-quarter.
   Move only along the axis the gated views do not see (x for FRONT/side, y for hair), re-check `outline_match`
   after each move. Find the head's real heights (chin, eye row, fringe) in the side picture before choosing ranges.
3. **Outline.** `outline_match` until every chosen view is `>= 0.98`. For the last few percent, alternate
   `fit_outline(views=["FRONT"])` and `fit_outline(views=["LEFT"])` with `strength` 0.6 to 0.8 and `sigma_px` 5 to
   8; stop when two rounds gain less than 0.002. A larger `sigma_px` keeps sides round; a smaller one follows
   fingers and hair tips.
4. **Clay.** `visual_match`: any view with `clay_banding_ratio` above 1.60 has terraces. Fix with `sculpt_remesh`,
   `sculpt_relax(method="laplacian")` with thin tips masked, then step 3 again. `sculpt_relax` that only uses
   `taubin` keeps waves several edges long: that is its design, not a failure of the call.
5. **Relief.** Look at the CLAY row and the `orbit_check` clay cells. Sculpt every feature the picture draws as a
   line: nose ridge (`draw`), brow (`clay_strips`), eye sockets (`draw` subtract), lip line (`crease`), collar
   and lapels (`crease`), skirt pleats (`crease` from waist to hem around the skirt), hair clumps (`crease` from
   crown to tips), boot folds (`crease` rings). Radius 5 to 12 mm on a 1.7 m character; `snap: true`.
5b. **Clay gate (mandatory before UVs or paint).** Switch the 3D viewport to untextured single-colour studio clay
    with cavity shading (`show_cavity = True`, `cavity_type = 'BOTH'`) and capture a **360-degree up-and-down clay
    pan**: 8 azimuths (every 45°) × 3 elevations (`-35°`, `0°`, `+35°`) = 24 close-up head views and 24 full-body
    views. Inspect every panel before moving on. Do NOT move to UVs or paint while the clay has boxy/slabbed
    crowns or chests, jagged hems, crumpled fingers, floating locks, buried/poking fringe roots, flat noses, or
    inner shells visible from below. Keep `fit_outline` broad (`sigma_px >= 6.0`) and always mask the sculpted
    face and hands, followed by Taubin `sculpt_relax` and a fresh 48-view clay pan: narrow repeated `fit_outline`
    passes stamp FRONT × LEFT cardboard boxes onto curved clay that straight-on outline scores hide.

6. **Paint.** `project_paint(object="CHARACTER", references={...}, priority_views=[...], palette_view="FRONT")`
   with every picture that shows the model's pose, after step 2's landmarks hold. Before painting, make sure each
   picture's features have their own surface: a hair mesh that closes over the face must have the face cut out of
   it (the side picture's profile lands on the hair otherwise), and eyeball or mouth spheres that poke out of a
   painted face are hidden (the paint already carries the eyes). Then:
   - `priority_views` lets the listed pictures own the surfaces they face. List the view that fails SSIM first;
     `view_bias` (e.g. `{"LEFT": 300}`) moves the hand-over on surfaces angled between two views toward the other
     view. Re-measure both views after each change: what one view gains the other loses.
   - `palette_view` is the picture where the parts do not overlap (usually FRONT: arms clear of the skirt). Colours
     another picture puts on a part that are not in that part's FRONT colours are dropped, so an arm drawn over
     the skirt in the side picture cannot leave a ghost arm on the skirt seen from behind. When that costs the side
     view SSIM, move the model's arm onto the drawn arm (check by giving the body a flat colour and comparing).
   - Read `cross_view.conflict_pct`: above about 25 % the pictures or the geometry disagree in 3D; the orbit sheet
     shows where. Painting is the last step of a round: re-run it after any change to shape.
   - Texture sharpness comes from the pictures, not `tex_size`: `project_paint` returns each picture's
     `figure_px_tall` and warns below 1,800 px. Go back to stage 01 (requirement 7) for 2K art; `ref_scale` only
     smooths the resampling of a small picture, it adds no detail.
   - `project_paint` blocks Blender for one to two minutes on a full character; the window does not redraw until
     it returns. Run it as its own call, not inside a loop of other long calls.
   - Stripes on surfaces between the legs or on boot sides come from pictures seen nearly edge-on and from leftover
     ring terraces: relax the legs (`sculpt_relax` laplacian `along="Z"`, everything else masked), keep `min_cos`
     at 0.12 and `min_cos_other` at 0.35; those texels then take the smooth 3D fill. Pictures paint only where the
     texel lands inside their drawn figure (secondary pictures 2 px inside it and inside the model's outline), and
     the fill only copies paint a picture saw squarely, so bled backdrop and outline ink do not streak.
   - A stray mark you cannot explain: repaint with `debug="owner"` (FRONT red, LEFT green, BACK blue, RIGHT
     yellow, filled grey), look at the same angle, then repaint normally. Find the owner of the mark before changing
     any painter setting: on this character four guessed fixes in a row missed.
7. **Proof.** Put the rig at rest first (the rest-pose frame): the pictures show the rest pose, and an animation
   left on another frame silently measures a raised arm (`three_quarter_check` refuses a posed rig; the others do
   not). Then `visual_match` on every referenced view, `orbit_check(object="CHARACTER", elevations=[-30, 0, 30])`
   (45 degree steps; -30 looks up under the hair and chin, where no picture paints), `three_quarter_check` with the
   same `priority_views` / `palette_view` as the paint, close `watch` views of the head (distance about 0.9 m on a
   1.7 m character) at every 45 degrees at elevations -35 and 0, and the eye review below. A whole-body orbit cell
   is too small to show a face; the close views are where a fringe floating over the eyes or a shell showing
   under the hair is seen. Done when every chosen view passes every gate, `orbit_check` reports `failed: 0`, every
   `three_quarter_check` pair passes, and the checklist has no open finding, or when a gate has stalled for two
   rounds and you can name why (a disagreeing picture pair, a pose difference, a feature the scripted brushes cannot
   make).
8. **Fixing a failed in-between angle.** Open the pair's sheet: red on the delta E map is where the two pictures
   disagree about one surface; the zoomed head row shows what each puts there. Go back to step 2 on that side of
   the character, with that side's picture: which landmark condition fails there? Fix that one, repaint, re-run
   the check, and revert a change that does not lower the failing region's delta E.

## Working rules

- One long call per message: `project_paint` and `three_quarter_check` take one to two minutes each and Blender
  does not redraw meanwhile. Report the numbers after each call.
- Before painting: the rig at its rest frame, and Windows commit headroom (a `MemoryError` from Blender on a small
  allocation is the system commit limit filled by other processes, not Blender).
- Diagnose before changing: `debug="owner"` for a paint mark, step 2's measurements for a geometry conflict. One
  change per measurement; revert what does not move the number the right way.
- Save every passing state under a new name, reopen it and re-measure before reporting it as passing.

## Eye review checklist

Open the `visual_sheet_path`, `orbit_sheet_path` and `three_quarter_check` `sheet_path` images and look at them;
answer every line with the angle or view and the place, or "none":

- CLAY: horizontal bands or terraces; a face with no nose ridge, brow or eye sockets; hair as one smooth helmet;
  garments without collar, pleats, hems or boot folds; spikes, dents or holes.
- FROM BELOW (elevation -30 and the close head views at -35): an inner layer showing (scalp or band shell under
  the hair, a second face), hair floating off the forehead or cheek with a gap you can see into, holes to the
  background beside the face, blotches or smears under the chin, jaw and hair (give hidden texels a flat colour
  with `project_paint(fill_colours={...})`, sampled from the picture: skin under the chin, hair shadow on hair).
- MATERIAL: grey or magenta parts; smeared or stretched paint; a doubled feature (second eye, profile face or
  hand painted on a cheek, hair side or skirt) at a three-quarter angle; paint on the wrong part (skin on hair,
  sleeve on skirt); visible seams.
- Against REF: features in a different place or size; delta-E heat cells that are red over a whole part, not just
  along lines.

When a second model or a reviewer agent is available, give it the same two sheets and this checklist with no other
context, and report its findings next to yours. Fix findings in loop order: shape before relief before paint.

## Limits

- Untextured relief is judged by eye. A number for "drawn features exist as geometry" was tried (recall of drawn
  lines in clay shading) and did not tell a smooth mannequin from a sculpted one, so it is not a gate.
- In-between angles have no picture of their own. `three_quarter_check` measures whether the two neighbouring
  pictures agree on the model there, not whether the model looks like a picture drawn at that angle; `orbit_check`
  proves surface quality and the eye review covers the rest. Report an in-between angle as consistent, not matched.
- The 12 delta E threshold comes from one character: untouched regions of the Ghibli test character measured 5 to
  10 between neighbouring pictures (drawing style alone), its double face 17 to 24, its hair flap 17. A character
  drawn with heavier shading may need its own style baseline: measure untouched regions first, never raise the
  threshold to pass a region that shows red.
- `project_paint` paints what the pictures show from their side. Surfaces no picture faces (tops of shoulders,
  undersides) take the colour of the nearest painted texel on the same mesh: plausible, not drawn.
