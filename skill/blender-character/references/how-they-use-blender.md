# How the artists drive Blender

The stage files say *what* each artist builds. This file says *how they use the program*: which mode, which
tool, which settings, which habits, read off their screens. Each section ends with the agent equivalent (you have
no mouse or hotkeys: every action is a `blender-live` tool call or `exec_python`).

Three sources:

| Artist | Route | Videos studied | How it was read |
|---|---|---|---|
| Kenny Praise | sculpt route (stages 01 to 11) | the 20-hour masterclass `qy-wwP-b9HY` | narration plus 1,253 frame labels |
| Nhij Quang | low-poly game route | `mlnR-Eyazh0` (1 h 15 min, no narration) | key-cast overlay, redo panels, status bar: 157 sheets, 366 labels |
| YanSculpts | speed-sculpt route | five videos: two 22-minute timelapses, three narrated Shorts | frames, his narration (Whisper), 252 labels |

Kenny Praise's screen habits are already in each stage file under "How the artist works on screen". The other
two are here.

## Nhij Quang: box modelling in Edit Mode (low-poly game route)

**Set-up.** Blender 4.2.1, Layout workspace for all modelling. The concept sheet is in an Image Editor on the
left the whole time, and it is also set behind the model as two Image Empties (front and side, opacity 0.3,
depth Back). Units are metres.

**Views.** He switches between Front and Right Orthographic constantly. X-ray is on while tracing over the
reference and off to judge volume. He checks in Object Mode with Shade Smooth (Keep Sharp Edges).

**One half only.** Every object has a Mirror modifier (X, Clipping on, Merge 0.001 m), and Mirror Editing shows in
every redo panel. Clipping is switched off only to place a part off the centre line (the breast sphere, back
hair), then back on.

**The keys he uses, and what they do here:**

| Key (as shown on the key-cast overlay) | Operation | Agent equivalent |
|---|---|---|
| E | extrude (vertex, edge, region; often with S or G after) | `bmesh.ops.extrude_vert_indiv` / `extrude_edge_only` / `extrude_face_region` + `translate` |
| G, S, R (+ axis, + number) | move, scale, rotate; S Z 0 flattens | `bmesh.ops.translate` / `scale` / `rotate` |
| Ctrl R | loop cut, 1 cut, factor read in the panel | `bmesh.ops.subdivide_edges(edges=ring, cuts=1)` |
| F | fill a face between selected verts or edges | `bmesh.ops.contextual_create` |
| M | merge At Center (closes a sleeve end, a sole ring) | `bmesh.ops.pointmerge` |
| L | select linked, Delimit Normal or Seam | walk `link_faces` from a face |
| Alt-click, Shift-Alt-click | select an edge loop | walk the loop with bmesh |
| Ctrl-click | shortest path, extrude to cursor | — |
| K | knife a new edge across faces | `bmesh.ops.connect_verts` |
| J | connect a vertex pair (keeps quads) | `bmesh.ops.connect_verts` |
| V | rip (split strands) | `bmesh.ops.split_edges` |
| Shift D | duplicate a piece (belt loops, petals, strands) | `bmesh.ops.duplicate` |
| P | separate into a new object (waistband) | copy faces to a new mesh |
| Ctrl J | join (the hand into the mirrored body) | `bpy.ops.object.join` in an override, or merge meshes with bmesh |
| W | Shade Smooth, Keep Sharp Edges | `polygon.use_smooth` + sharp edges |
| Ctrl Z | undo, often 2 to 9 steps | save a `.blend` per part; there is no undo across tool calls |

**Two more tools he relies on.** Snapping set to **Face** lets new verts land on the body (the halter straps).
**Proportional editing** (Sharp or Root falloff, size about 0.18) moves a whole shoe or bends a long strand.

**Painting.** Texture Paint workspace, painted in the 2D Image Editor with the concept picture in a second Image
Editor. One brush, TexDraw at Blend Mix, strength 1.0, radius 1 to 170 px. The colours sit in a palette. His
recurring move: paint a soft blob, then move or scale the UV island onto it in UV Editing (Straighten X, Align
Horizontally). Agent equivalent: `project_paint` from reference pictures, or numpy writes into the image pixels
per UV island (`09-shading-texturing.md`, low-poly section).

## YanSculpts: separate spheres in Sculpt Mode (speed-sculpt route)

**Set-up.** He sculpts straight on a pen display. At least the Black-and-White timelapse and the Shorts are
filmed with a camera pointed at it, so small header text is often unreadable. He stays in Sculpt Mode almost the whole time, switching objects from the outliner or by
clicking. Edit Mode is used only for flat strips (brows, lashes) and an iris inset.

**Brushes and settings** (read from the header, where legible):

| Brush | Strength | What he uses it for | Agent equivalent |
|---|---|---|---|
| **Grab** | **0.45** (Black and White), **0.60** (Summer); radius about 40 px up to 500 px | in most frames: silhouettes, moving whole parts and hair locks, the face | `sculpt_strokes` brush `grab` (moves by (last − first) × strength) |
| Draw | 0.28 to 0.50, about 19 to 43 px | carving nostrils, lips, ears, clavicles | `draw` (subtract to carve) |
| Clay Strips | 0.44 | lids, nose, cheeks, lips | `clay_strips` |
| Crease Polish | 0.25, about 33 to 98 px | lid and lip lines, ear, folds, neck lines | `crease` |
| Snake Hook | 1.0 | each hair lock, shoulders | `snake_hook` |
| Inflate/Deflate | 0.5 | thicken locks, the ear | `inflate` |
| Mask | 1.0 | mark where clothes go | `sculpt_mask` |
| Paint Soft / Paint Soft Pressure (Blend Mix) | 1.0 for fills, lower for blush; radius 69 to 401 px | colour on the sculpt | `exec_python` colour attribute (`speed_sculpt.code_paint`) |

He uses no Smooth brush in Summer: the forms stay faceted right into painting.

**Objects, not one mesh.**
- Add > Mesh > UV Sphere (picked from the add menu, "Add UV Sphere" in the redo panel) for every part. The outliner
  climbs to `Sphere.040`, and nothing is joined.
- One remesh on the head early (Summer, 00:00:25); the Dyntopo and Remesh menus are otherwise never opened.
- Hair strands carry Subdivision modifiers, so the base stays low-poly.
- Hide and unhide: he hides the top to sculpt the body underneath.

**Modifiers instead of sculpt symmetry.** The ear has a Mirror modifier whose *mirror object is the head*. The head
has Subdivision + Mirror. Brow and lash planes have **Subdivision + Mirror + Shrinkwrap (target: head) + Solidify**.
Clothes have Mirror (X, Clipping, Merge 0.001 m).

**Clothes.** He paints a Mask on the torso, then uses Mask Extract: a new `Mesh.001` appears with a
`geometry_extract_solidify` modifier. Agent equivalent: `sculpt_mask(op="box")` + `speed_sculpt.code_extract_masked`.

**Colour.**
- **Paint in Sculpt Mode:** colour attributes, not Vertex Paint or Texture Paint mode. The colour is picked from
  the wheel.
- **Order:** a base colour on each part, then blocks, then edges. In Summer: hair purple, top olive, skin pale
  pink, then lips coral, blush, iris.
- **Ink:** **Grease Pencil** in Draw Mode, brush Ink Pen, colour Black, placement **Surface**, Stroke & Fill. The
  Grease Pencil objects have Mirror (object: head) and **Opacity** modifiers, and he lowers the opacity. White
  strokes make hair highlights.
- **Order in Black and White:** ink first, then soft painted values, then last ink touches.

**Presenting.**
- Viewport only, with Scene Lights and Scene World on, and the World background edited.
- Up to six lights in a `LIGHTS` collection: mostly Suns (Strength and Angle edited), one Area (Square). Warm peach,
  orange and red-orange, placed for rims.
- The black-and-white look is a material: `skin.001` has two Principled BSDFs mixed through a Color Ramp.
- He goes back to the face after lighting.
- Agent equivalent: `speed_sculpt.code_toon_material` and `code_rim_lights`, then `viewport_capture`.

**Order in the narrated Shorts** (his own words, condensed):
1. "Start with a sphere, pull down his face."
2. Carve the sockets, nose, mouth; pull the ears out.
3. Place the eyes, then sculpt the lids.
4. "Duplicate his head for his neck, duplicate his neck for his torso."
5. Arms from a duplicated part, inflated and placed.
6. Paint the base colour per part, then the eyes, then refine the edges.
7. Sketch emblems and webs rough first, then refine.
8. "Continue refining till satisfied", add lights.

## What carries over to an agent

- Brush *strengths* from the videos are used as given in `scripts/speed_sculpt.py`. Brush *radii* in px depend on
  the screen and zoom: convert to world units from the part's size (the scripts use fractions of the head height).
- Where an artist relies on undo, save a numbered `.blend` before each part instead.
- Every "looks right" moment in the videos is an orbit and a look. Do the same with `viewport_capture` from front,
  side and 3/4, and the likeness tools, after each part.
