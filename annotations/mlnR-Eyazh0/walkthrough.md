# How Nhij Quang made "Girl#01": the silent video in words

Video: [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0),
Nhij Quang, Blender 4.2.1 LTS, 1 h 15 min, music only.

How this was written: the video was cut into 157 clips of about 29 seconds, and four full-resolution frames from each
clip (about 630 frames, roughly one every 7 seconds) were read for the key-cast overlay in the corner of the viewport,
the operator redo panels, the modifier panels and the status-bar vertex and face counts. Numbers below were read off
the screen. Where a step had to be deduced from before-and-after frames, it says so. The time-by-time labels are in
the `.jsonl` files beside this one.

## The idea in one paragraph

He builds the whole character the way game artists box-model: one half of the body as a single low-poly mesh with a
Mirror modifier, traced straight over a front/side concept sheet, growing it face by face with extrude, loop cut,
knife and fill. Clothes are either copies of body faces lifted off the skin, or new shells built the same way, all
single-layer, no thickness modifier. The head is drawn as a face patch and closed into a skull. The hair is flat
one-face-wide ribbons. No sculpting, no subdivision, no retopology: the mesh he models is the game mesh. Then one
1024 px texture is hand-painted in flat colours onto an unlit material, the arms are rotated into a T-pose, Mixamo
rigs and animates it, and it goes into Godot as an FBX.

## 0. Preview [00:00 to 00:55]

The finished character first: a low-poly anime girl (about 9,400 vertices, 18,600 triangles with the mirror applied),
rigged with Mixamo bones, playing a walk cycle. Its vertex groups include one named "Outline" (probably for an
inverted-hull outline; it is never used on screen).

## 1. Reference set-up [00:55 to 01:36]

- One concept image holds front, side and back views of the girl.
- He adds it as an **Image Empty**: size 5 m, offset -0.5/-0.5, depth Back, opacity 0.3, and moves it so the front
  figure's feet sit on the world origin.
- He duplicates the Empty and slides the copy 5.29 m sideways so the **side** figure lines up with the origin, for
  use in the Right Orthographic view.
- The concept picture also stays open in an Image Editor on the left of the screen for the whole video.

## 2. Base shape: torso and legs [01:36 to 03:17]

- Adds a cube, deletes the face on the centre line, scales it to 0.211 and puts it on the chest.
- Adds a **Mirror** modifier: X axis, **Clipping on, Merge 0.001 m**. Every part of the character uses this same
  modifier. Mirror Editing is on throughout.
- In front view with X-ray on, drags vertices onto the torso outline (chest to crotch); then in side view sets the
  depth.
- Extrudes the bottom face straight down for the thigh, then again to the knee and ankle, scaling each end; rotates
  the shin ring about 10 degrees to follow the leg.
- One loop cut down the length turns the 4-sided legs and torso into 8-sided ones.
- Tidies the crotch from below, sets **Shade Smooth with Keep Sharp Edges**, and slims a leg loop (scale 0.785).
- End: about 107 vertices for half of the lower body.

## 3. Shoes and leg warmers [03:17 to 09:58]

- Still inside the body mesh: flattens the ankle ring onto the floor (scale Z 0).
- In side view, extrudes a chain of vertices 10 times to trace the **sole outline** from the drawing, fills faces
  with F, and merges the ends At Center to close the sole into a ring.
- Extrudes the sole's top edge in place and scales it 0.909 to make the inner rim.
- Extrudes up from the rim and places vertices one by one over the drawing to build the **toe box and instep**, fills
  the seven holes left with F, adds a loop cut, and extrudes the collar up the leg.
- Uses **proportional editing** (Sharp falloff, size 0.18) to slide the whole shoe under the leg.
- Extrudes the strap faces slightly out so the strap stands proud.
- Separates the shoe into its own object (`Cube.001`, 247 vertices); it keeps its own Mirror modifier. Narrows its
  bottom (scale X 0.726).
- **Leg warmer:** extrudes the shoe collar up to below the knee and tilts the top ring -14.6 degrees to match the
  slanted edge in the drawing.
- **Knee band** on the body: bevels a loop (1 segment), adds a loop cut, tilts it, scales it 1.084 to stand out, then
  knife-cuts a diagonal edge on the shin.
- A small ankle ribbon gets a loop cut, then is duplicated with Select Linked + Shift D.
- Shade Smooth (Keep Sharp Edges) on the shoe. Saves.

## 4. Shorts [09:58 to 13:58]

- Reshapes hips and buttocks on the body to the shorts outline from side, back and 3/4 views.
- Selects the body faces the shorts cover (48 vertices, 37 faces) and makes them a **new object** `Cube.002`, pushed
  a hair out from the skin. (Copy-then-separate is inferred from the outliner.)
- Moves the hem down, adds a loop cut slid to the very end to make a crisp hem cuff.
- Bevels the side and front edges (0.00285 m, 1 segment) to draw panel seams in the geometry.
- Separates the **waistband** with P into `Cube.003`, gives it a loop cut, extrudes **belt-loop flaps** out of it, and
  copies one flap around the waist with Shift D.
- **Pockets:** extrudes the hip faces where the drawing has pockets, then shapes them with the Knife and single
  vertex moves; back pockets the same way.

## 5. Chest and neck [13:58 to 16:22]

- A horizontal loop cut across the upper torso.
- **Breasts:** adds a low UV sphere inside the body, turns Mirror Clipping **off** so it can sit off the centre line,
  deletes its back half, scales the dome 0.874, sets it on the chest, and stitches its border into the chest faces.
- Evens the chest with **Vertex Slide** (0.355) and a few cuts, dissolves extra edges between the breasts.
- Turns Clipping back **on**, extrudes the **neck** up 0.032 m from the top of the torso and leans it back
  -11.8 degrees; vertex-slides the collarbone area.

## 6. Clothes: crop top, collar, jacket [16:22 to 28:32]

**Crop top** (`Cube.004`):
- Starts as just a row of 9 vertices under the bust, with its own Mirror modifier.
- In side view with X-ray, extrudes edge rows to trace the bra-like top; rotates the cup edge 36 degrees to follow
  the breast; fills each cup as a small quad grid just above the skin.
- Copies the under-band row (Shift D), cuts out its centre to leave two side blocks, notches a V between the cups,
  and builds a small **diamond ornament** at the front, extruded 0.011 m along its normal.
- **Halter straps:** switches snapping to **Face**, so new vertices stick to the body, then extrudes single vertices
  from the cup corners up to the neck, turns them into faces, and gives each strap a lengthwise loop cut.

**Stand collar** (`Cube.005`):
- Copies the top ring of the neck into a new object, pushes it out a little, extrudes it up and narrows the top
  (0.953). Undoes nine steps and rebuilds the front as a pointed flap folding down onto the chest, with knife cuts.
- Later leans the collar back about 34 degrees in side view.

**Jacket** (`Cube.006`):
- Copies the upper torso and shoulder faces, then cuts them down to a 15-vertex shoulder piece.
- Rotates the arm-hole edge 40 degrees to follow the arm, **extrudes the sleeve** down the arm (about 0.19 m), and
  shapes the puff with scales (0.842, 0.941, 0.857) and loop cuts.
- Extrudes a narrower **cuff**, and closes the sleeve end with **Merge At Center**.
- Bevels a few edges on the sleeve (0.0078 m) to draw a fold line; an upper-arm patch is cut out with a loop cut,
  scaled 0.727 and outlined with the Knife and a thin bevel (0.00226 m).
- Extrudes the back hem down 0.25 m into the back drop, leaving a slot at the centre back.
- No Solidify anywhere: the garments are single-layer shells; thickness exists only where an edge was extruded.

## 7. Hands [28:32 to 33:20]

- A separate cube (`Cube.007`, no modifiers) flattened into a **palm slab**; loop cuts split its front into **four
  finger columns**, and a 1-segment bevel (0.00197 m) separates them.
- Extrudes the four finger faces out into long boxes, tapers the tips (scale 0.513), sets finger lengths in top
  view and narrows the rows (0.759, 0.745).
- Adds knuckle loops so each finger has three joint rings; rounds each finger's section by moving vertices from the
  front.
- **Thumb:** knife-cuts the palm side, extrudes a face out, tilts it -13.7 degrees, extrudes again and tapers it.
- Shade Smooth. Whole hand: 261 vertices, 264 faces. Scales it 1.422, moves it to the wrist, and **joins it into the
  mirrored body (Ctrl J)**, so the Mirror modifier makes the left hand for free. Saves.

## 8. Head [33:20 to 42:03]

- A new empty mesh with a Mirror modifier (X, Clipping, Merge 0.001 m).
- In side view, places a **chain of vertices along the face profile** from brow to chin.
- Extrudes the chain sideways into a column of quads over forehead, eye and cheek, and drags every vertex onto the
  side drawing; then in front view slides them onto the front drawing: a centre strip, a band across the eyes, a jaw
  line. Evens the grid with Vertex Slide. Shade Smooth to check.
- Pulls the centre faces under the eyes forward into a **small pointed nose**; extends the centre strip to the chin.
- **Mouth:** extrudes the mouth row out to the corner and bevels the mouth edges once (0.0178 m, 1 segment) to make
  a ring of loops; the mouth is a shallow slit in the geometry. Fills the holes around it with F.
- **Skull:** extrudes the top edge up over the forehead and the side edge backwards round the head, adding rows until
  the back silhouette matches. Half-head: 123 vertices, 101 faces.
- Joins the head into the body object (deduced from the object count) and stitches the neck by hand: a loop cut on
  the neck, faces filled one patch at a time with F, a knife cut where the vertex counts differ, J to keep quads.
- **Ears:** two faces on the side of the head extruded 0.035 m along their normal and pulled into a pointed shape.
- **Eyes:** slides loops to the drawn eye shape, opens the eye into a hole, caps it again, adds a ring and scales the
  inner ring to 0.51 for the **iris**, and pushes the whole eye 0.0026 m back so it sits in a socket.
- **Upper lash** line: extrudes the upper lid edge out over the eye into a thick flap.
- **Eyebrows:** a strip extruded along the drawn brow and pulled 0.01 m forward off the forehead as a separate ridge.

## 9. Hair [42:03 to 51:20]

- Snaps the 3D cursor to the origin and starts a new empty mesh for the **fringe** (no mirror, so it can be
  asymmetric).
- Draws a single-row **band of quads along the hairline** from the centre to the temple, then extrudes edges down
  into **bang strands** hanging in front of the ears. Strands are flat ribbons one face wide, no thickness.
- Uses proportional editing (Root falloff) to bend long strands, and Rip (V) to split strands apart.
- **Cap:** a UV sphere (146 vertices) fitted to the skull and cut down, in a **second, mirrored** hair object.
- **Bun:** a small petal at the crown, copied and rotated around Z in top view (82.6, -75.5 degrees and so on) until
  the petals ring the crown.
- **Back hair:** extrudes strips from the cap down behind the ear, then copies strips and rotates each copy around
  the head's Z axis (-31.3 degrees and others) until the back is a bob of vertical strips; tips are scaled to a point
  and flicked outward (-19.5 degrees). Mirror Clipping on the back hair is turned off so strips can cross the centre.
- Extra layered strands in front of the side hair, spiky tips extruded and pointed.
- End: three objects in a "Model" collection, **Body** (with Mirror), **Hair1**, **Hair2**: 4,405 vertices,
  7,520 triangles in the scene.

## 10. UV unwrap [51:20 to 55:02]

- Marks seams where they will not show: down the boot fronts and round the cuffs, inside the arms and sleeves, down
  the back and the backs of the legs, round the tops of the thighs and the crotch, round each fingertip and across the
  knuckles.
- Unwraps **one connected piece at a time** (Select Linked, then UV > Unwrap); Smart UV Project is never picked in the frames.
- Deletes small faces nobody sees, under the belt and collar (body faces fall from 1,705 to 1,622; the delete itself
  is not shown).
- Creates a new image: **1024 x 1024, blank, with alpha**, later saved as `female_char1.png`.
- Moves the islands into the square **by hand** (no Pack Islands): big islands for torso and face, small pieces in the
  gaps.

## 11. Hand-painted texture [55:02 to 1:11:28]

- **Material:** the body's image goes straight into the Material Output's Surface, **no shader**. The model is unlit;
  all shading is painted. The image starts filled with flat peach skin colour.
- Paints in the **Texture Paint workspace in the 2D Image Editor**, with the concept picture open in a second Image
  Editor. One brush throughout: **TexDraw, Mix, strength 1.0**, radius anything from 1 to 170 px. A palette holds the
  costume colours.
- **The key trick, used again and again:** paint a rough soft blob of a colour anywhere in the image, then go to the
  UV Editor and **move or scale the UV island onto the blob**. Shorts, boots, jacket, hands and hair are all coloured
  this way. He also straightens islands (Straighten X, Align Horizontally) so straight painted bands land on straight
  rows of faces.
- **Order:** shorts navy with a red band and thin yellow trim stripes; belt charcoal with a brown buckle; boots navy
  with red front panels and a yellow cuff band; chest cups navy, brown pouches; jacket teal (from one big teal blob)
  with a red back yoke, red/navy cuffs, a yellow V-line on the back panel; collar navy with red borders and yellow
  trim.
- **Face:** first scales the eye UVs up so the eye gets more pixels. Eye: dark maroon surround, pale sclera crescent,
  cream iris with dark purple at the top (strength 0.57), orange at the sides, navy pupil, 1 px light highlights.
  Pink blush with a 60 px soft brush; nose a small pink mark; mouth a short dark-rose stroke (4 px). Brows and lashes
  are already dark geometry.
- **Skin shading:** Smooth falloff, big brushes (83 to 170 px), strength 0.3 to 0.8: rose shadows under the chest and
  at the waistband, navel and rib creases, rosy fingertips (by placing the hand island over soft rose spots), then
  skin colour at low strength over the top to soften.
- **Hair** is the only lit material: Principled BSDF -> Shader to RGB -> Color Ramp -> Mix (factor 0.925, with the
  painted texture) -> output, a simple toon shader in EEVEE. Hair UVs are moved onto navy and red patches for red
  streaks.
- Late changes: new pocket faces get UVs placed onto existing colour blobs; a pocket island scaled 0.799 to fit its
  patch. Saves the image as `female_char1.png`.

## 12. Mixamo rig [1:11:28 to 1:13:19]

- Works on copies of the three objects. In Edit Mode, rotates the arms up into a **T-pose** (Mixamo wants arms out).
- Uploads to **Mixamo** (the website), lets the Auto-Rigger run, accepts the review.
- Downloads **Running** with **In Place** on, and **Dwarf Idle**; both with Overdrive 50 and Arm-Space 50.
- Imports the FBX back into a fresh Blender scene: an Armature (rotation X 90 degrees, scale 0.01) with the meshes
  parented under it. The texture did not come across, so he relinks it in the material by hand.

## 13. Into Godot [1:13:19 to 1:15:28]

- Exports FBX straight into the Godot project folder: all object types, Scale 1.00, Apply Scalings All Local,
  Forward -Z, Up Y, Path Mode Auto.
- Godot 4.3: the FBX (with `female_char1.png`) is instanced as `MainChar`: Skeleton3D with the three meshes and an
  AnimationPlayer.
- Body material: albedo texture `female_char1`, **Rim on** (rim 0.08, tint 0.3) for a slight edge light.
- Plays `Armature|Idle` (6.67 s) and `Armature|Run` (0.7 s) in the AnimationPlayer.

## What the frames do not show

Things that could not be read and are not guessed above: the UV sphere's segment counts, the Unwrap method in its
redo panel, the colour values and the hair colour-ramp stops, the Mixamo marker placement and skeleton options, the
Mixamo upload export settings, and Godot's import options. Some scale values had an unreadable sign or digit.
