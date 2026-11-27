# 01 Concept and references

Course source: chapter 01 "Introduction", 00:00:00 to 00:09:24, and chapter 02 "Choosing a concept",
00:09:24 to 00:21:34.

## Goal

One concept picture is chosen and locked, and a small set of supporting pictures explains every part of it
that the concept leaves unclear (face, hair, each garment, shoes, body shapes, materials). The pictures the
agent will model against are on disk, cropped tight, checked for whether they can be measured, and placed in
the Blender scene as `REF_<VIEW>` image empties. A short written list says which views can be measured and
which can only be looked at.

## Starting state

- A live Blender 4.5 session reachable through `blender-live` (`blender_status` returns `reachable: true`).
- A concept picture, or a description from the user of the character they want.
- Nothing has to exist in the scene yet.

## Where this stage sits in the whole job

The course splits character work into eight sessions [00:01:11 to 00:04:16]. The skill follows the same order:

1. Concept and references (this file).
2. Sculpting and modelling: blockout, then face and head, then body, then clothes and accessories.
3. Retopology: theory, face, body (legs, hands, feet, mouth interior, teeth, tongue), clothes and accessories.
4. UV unwrapping.
5. Hair: the sculpted hair is replaced by strand hair made with Blender's geometry-nodes hair system.
6. Shading and texturing: eye and hair shaders, painted textures, normal maps and extra maps.
7. Rigging with Rigify, then poses.
8. Lighting and presentation: stills and a turntable-style animation.

Each course chapter opens with a short theory part before the Blender work. The course asks viewers not to
skip it [00:05:35]; the stage files in this skill carry that theory in their "Order of work" reasons.

## Order of work

### 1. Choose one concept and lock it [00:10:11 to 00:12:22]

Why: the course treats the concept as the thing every later decision is checked against. Without one, the
modelling has no target and the result is weak and confused [00:10:38]. The course's test for a good concept
is simple: the design is appealing to the person making it and they want to see it in 3D [00:11:28].

How the course does it: the teacher picks a single ink drawing of a standing girl (short top, short skirt,
tall boots, hair tied up), drawn by Jennifer Park and used with her permission [00:15:29]. It is one picture,
in a three-quarter view, in a relaxed pose with the hands behind the back. There is no front or side drawing.

Through blender-live: nothing to run. Record in your notes the file path of the concept, who made it, and
whether permission to use it is known. If the user supplies the concept, that question is theirs; ask once if
it is unclear and carry on.

Check before moving on: there is exactly one main concept. Extra pictures support it; they do not compete
with it.

### 2. Keep the first character simple [00:12:22 to 00:13:16]

Why: the course tells learners to avoid very detailed designs (heavy armour, many layered accessories)
because detail slows learning and causes confusion. For an agent the same advice has a different reason:
every extra garment and prop is another object to block out, sculpt, retopologise, unwrap and rig, and each
one adds outline that must match.

What to do: if the user's concept is complex, do not swap it for a simpler one. List the separate parts
(body, each garment, each accessory, hair) and plan them as separate objects from the start.

### 3. Where concepts come from, and permission [00:13:16 to 00:14:36]

The course names Instagram, ArtStation and Pinterest, and the teacher's own Pinterest board of more than 60
beginner-friendly concepts. It says twice to ask the artist before using their work [00:13:30, 00:14:22].
Carry that over: when the agent proposes a concept found online, it says where it came from and that the
user needs the artist's permission to publish work based on it.

### 4. Gather supporting pictures, one group per unclear part [00:14:36 to 00:19:11]

Why: the concept shows what the character looks like from one angle in one drawing style. It does not show
how a boot is built, how a pleated skirt hangs, or which way each lock of hair runs. The course is clear that
supporting pictures are chosen because they explain something, not because they look nice [00:15:03].

How the course does it [00:15:56 to 00:18:08]. For the main character the board has these groups:

| Group | What was collected | What it is used for |
| --- | --- | --- |
| Face | A close crop of the concept's head; one stylised 3D face chosen as the style target (large eyes, feature shapes); three more faces (two stylised, one photo of a real person) chosen because the character is East Asian | The style to aim for, and proportion guides for that kind of face |
| Boots | One clear product photo of the exact kind of boot; three more showing how the leather folds | The concept's boots are too loose to read; the photo is what actually gets modelled |
| Skirt | Pictures of the same kind of skirt | How the skirt is built and hangs, which the drawing does not show |
| Hair | Photos of the same hairstyle on real people | Direction of the hair and where one mass separates from another |
| Body | Stylised 3D bodies with simple, clean shapes; one of them stands in a neutral arms-out pose | Shape language for the body sculpt and the pose to model in |

A second example character [00:18:08 to 00:19:11] adds two more kinds of group: material references (what the
dress cloth looks like, used later to judge the shader) and jewellery.

Through blender-live: save each supporting picture to a folder next to the `.blend`, named by group
(`refs/face_01.png`, `refs/boots_01.png`, ...). Then, for each part of the concept, write one line: what is
unclear in the concept and which picture answers it. A part with no answer is a gap; find a picture or ask
the user.

Check before moving on: every visible part of the concept (head, hair, each garment, each shoe, hands,
any prop) has at least one supporting picture or a note that the concept alone is clear enough.

### 5. Read the proportions off the concept [00:23:32 to 00:24:51, from chapter 03's theory part]

Why: stylised characters break normal human proportions on purpose, and each one breaks them differently.
The course has the artist notice the main ratios before opening Blender. Its example is a character whose
head, torso and legs are all about the same height [00:24:00].

What to write down, as fractions of total standing height: head height (chin to top of skull, without
hair), neck length, shoulder line, waist, crotch, knee, ankle; and as fractions of head width: shoulder
width, waist width, hip width. Note the shape language too (round, boxy, angular) because the blockout must
repeat it in every part [00:26:53].

If the concept is a posed or three-quarter drawing, these are estimates by eye. Say so in the notes.

### 6. OUR REQUIREMENT (not the course's): get straight-on pictures that can be measured

The course never measures. The teacher keeps the picture board open in a floating window and compares by
eye. This skill has a stricter target: the model's outline must overlap the reference by 0.98 in every view
that has a real reference picture. `outline_match` can only measure a view when it is given a picture that
meets all of these:

1. Taken or drawn straight-on from that side, with no perspective tilt. A three-quarter drawing is not a
   FRONT picture.
2. FRONT and one side (LEFT or RIGHT) are desirable for a broader check; eligible views are measured independently.
3. A transparent background, or one plain colour. `outline_match` refuses a picture whose four corners
   differ in colour.
4. Cropped tight to the character.
5. Showing the same pose the model is built in. The model is built in a neutral pose for rigging (arms away
   from the body, legs slightly apart), whatever the concept shows. `outline_match` scales both outlines to
   their own bounding boxes before comparing, so an arm in a different place changes the whole score.
6. Showing the same things the model contains. A clothed reference compared with a bare body will not
   reach 0.98; that is expected until the clothes exist.

A view with no such picture can be looked at with `turnaround_sheet` but not measured. `outline_match`
reports it as `not_run`. Report such a view as "looked at, not measured". Never report it as passed.

The course's own concept fails points 1 and 5 and has no straight-on side view: it is a single
three-quarter drawing with the hands behind the back. For a concept like that, the agent has three honest choices:

- Ask the user for a turnaround (front, side, back) of the character in a neutral pose.
- Ask the user whether they (or an artist working for them) will draw straight-on neutral-pose views of the
  design. Pictures the user supplies count as real references; say plainly that the measured target is then those
  views, not the original drawing. Views you generate or draw yourself, or have an image model make, never count
  as references and must not be measured against.
- Go on with no measured views. Every view is then "looked at, not measured", and the final report must say
  the 0.98 target was not tested.

Check each candidate picture with this snippet before relying on it.

```python
# verified in 4.5.16 background
import bpy, numpy as np

def _pixels(path):
    img = bpy.data.images.load(path, check_existing=False)
    w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)                    # row 0 is the BOTTOM row of the picture

def _subject(px):
    """True where the picture shows the character: by transparency if the picture has it, otherwise by
    distance from the corner colour (the same two rules outline_match uses)."""
    if px[:, :, 3].min() < 0.5: return px[:, :, 3] >= 0.5, "transparent background"
    h, w = px.shape[:2]; k = max(2, min(h, w) // 50)
    corners = np.concatenate([px[:k, :k, :3].reshape(-1, 3), px[:k, -k:, :3].reshape(-1, 3),
                              px[-k:, :k, :3].reshape(-1, 3), px[-k:, -k:, :3].reshape(-1, 3)]) * 255
    if corners.std(axis=0).max() > 18: return None, "background is not plain: cut the character out first"
    return np.linalg.norm(px[:, :, :3] * 255 - np.median(corners, axis=0), axis=2) > 40, "plain background"

def check_reference(path):
    px = _pixels(path); h, w = px.shape[:2]
    mask, how = _subject(px)
    if mask is None: return {"measurable": False, "reason": how, "image_px": [w, h]}
    ys, xs = np.nonzero(mask)
    if not len(ys): return {"measurable": False, "reason": "no character found", "image_px": [w, h]}
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
    return {"measurable": True, "background": how, "image_px": [w, h],
            "subject_px": [box[2] - box[0] + 1, box[3] - box[1] + 1],
            "margin_px": {"left": box[0], "right": w - 1 - box[2], "bottom": box[1], "top": h - 1 - box[3]},
            "cropped_tight": max(box[0], w - 1 - box[2], box[1], h - 1 - box[3]) <= 0.02 * max(w, h)}

result = check_reference(r"C:\path\to\refs\front.png")
```

`measurable: True` only says the background can be separated. It cannot tell whether the picture is
straight-on or in the right pose; look at the picture for that.

If `cropped_tight` is false, crop it (this reuses `_pixels` and `_subject` from above):

```python
# verified in 4.5.16 background
def crop_reference(path, out_path, pad=2):
    px = _pixels(path); h, w = px.shape[:2]
    mask, how = _subject(px)
    if mask is None: raise ValueError(how)
    ys, xs = np.nonzero(mask)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + 1 + pad)
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + 1 + pad)
    crop = np.ascontiguousarray(px[y0:y1, x0:x1])
    img = bpy.data.images.new("crop_tmp", int(x1 - x0), int(y1 - y0), alpha=True)
    img.pixels.foreach_set(crop.ravel()); img.filepath_raw = out_path; img.file_format = "PNG"; img.save()
    bpy.data.images.remove(img)
    return {"saved": out_path, "size_px": [int(x1 - x0), int(y1 - y0)]}

result = crop_reference(r"C:\path\to\refs\front.png", r"C:\path\to\refs\front_cropped.png")
```

Front and side pictures must also agree with each other. After cropping, the landmarks (top of head, chin,
shoulder, crotch, knee, sole) should sit at the same fraction of the picture height in both. If they differ
by more than about 2% of the height (our figure), the pictures describe two different characters and no
model can match both; fix the pictures or pick the FRONT as the one that wins and say so.

### 7. Put the pictures into Blender [course: 00:35:17 to 00:36:11; ours: `reference_setup`]

How the course does it: it does not put any picture into the 3D scene. The board lives in PureRef, a
separate program, set to stay on top of other windows and parked in the lower-left corner of the screen
over a small second viewport [00:35:17 to 00:35:58]. The teacher zooms the board to the group that matters
for the part being worked on and keeps glancing at it [00:50:02].

An agent has no second window to glance at. Use the scene instead:

```
# not verified: a blender-live tool call, not run against a live Blender for this file
reference_setup(images={"FRONT": r"C:\path\to\refs\front_cropped.png",
                        "RIGHT": r"C:\path\to\refs\side_cropped.png"},
                height=1.7)
```

What that call does (from the tool's code): each picture becomes an image empty named `REF_FRONT`,
`REF_RIGHT` and so on, in a collection called `References`. It stands upright with its bottom edge on the
ground plane (Z = 0), `height` world units tall, pushed `height` units behind the model for that view, 60%
opaque, shown only in orthographic views, not selectable, and not rendered.

Rules for calling it:

- `height` is the character's height in world units, hair and shoes included, because the picture is
  cropped tight. Pick it once and use the same number for every view and for the blockout. Our
  recommendation: use the real height in metres (for example 1.7), so later stages (rig, cloth, export) do
  not need a rescale. The course works at an arbitrary large scale and fixes it after sculpting [01:16:10].
- View names are Blender's view names, not the character's sides. The character faces the FRONT view (it
  looks toward -Y). `RIGHT` is the view from +X: it shows the character's own left side, with the face
  pointing to the left edge of the picture. `LEFT` is the view from -X, face pointing to the right edge. If
  the side picture faces the other way, it is the other view: use the other view name. Do not flip a picture to
  fill the missing side; a view without its own real picture is `not_run`.
- Call it again with the same view name to replace a picture.

Supporting pictures (boots, hair, face style) do not belong in `REF_<VIEW>` slots. Keep them as files and
pass them to yourself by reading the file when working on that part. If one is wanted in the scene for a
capture, place it off to the side by hand:

```python
# verified in 4.5.16 background
import bpy, math
e = bpy.data.objects.new("REF_DETAIL_boots", None)
e.empty_display_type = "IMAGE"
e.data = bpy.data.images.load(r"C:\path\to\refs\boots_01.png", check_existing=True)
e.empty_display_size = 1.0                      # the picture's longer side, in world units
e.rotation_euler = (math.pi / 2, 0, 0)          # upright, facing the FRONT view
e.location = (2.5, 0, 0)                        # beside the character, not behind it
e.empty_image_offset = (-0.5, 0.0)              # bottom edge on the ground
e.show_empty_image_perspective = True
e.hide_select = True; e.hide_render = True
bpy.context.scene.collection.objects.link(e)
```

Check before moving on: use `viewport_capture` for each supplied view to inspect the picture's orientation
and ground line. `scene_tree` lists the `REF_` empties. Missing views remain unmeasured.

### 8. Save

`save_file(filepath=r"C:\path\to\<character>_00_refs.blend")`. The course saves late and admits it should
have said so sooner [01:34:28]. Save at the end of every stage under a new name.

## How the artist works on screen

This chapter shows slides, a browser and a PureRef board, not a Blender sculpting session.
The selected chapter frames do not show brush settings, strokes, symmetry or a measurement.
Do not transfer a screen-pixel brush radius from this material.
The following observations follow the numbered steps above; equivalents are our workflow.

### Step 1 — choose the target

- At 00:10:26 the slide pairs a stick drawing and a simple 3D stick figure,
  then a developed dress concept and front/back 3D results
  [qy-wwP-b9HY-02-001024]. This is a comparison, not a modelling demonstration.
- At 00:11:26 the slide changes from the comparison to a definition of a useful concept
  [qy-wwP-b9HY-02-001113].
- At 00:12:04 four different example designs appear together
  [qy-wwP-b9HY-02-001156]. They illustrate personal appeal, not four targets to combine.
- At 00:15:31 the artist's board shows one full-body drawing on the left,
  separated from the supporting face, boot, hair, body and skirt groups
  [qy-wwP-b9HY-02-001529].
- The drawing has a turned head and hands hidden behind the body.
  Its three-quarter pose is not a straight-on neutral-pose measurement target.
- The artist selects the drawing, then opens its credited artist's profile
  [qy-wwP-b9HY-02-001529, 00:15:38–00:15:42].
- **Reader equivalent:** read the user-supplied image; record one chosen design,
  its creator and permission status. Treat the rest as supporting evidence.

### Step 2 — control complexity

- The 00:12:38 slide shows three densely layered fantasy designs side by side
  [qy-wwP-b9HY-02-001222]. Their armour and accessories illustrate added work.
- These are presented as examples to avoid during this learning exercise,
  not a rule to change a user's chosen design.
- **Reader equivalent:** list garment, hair, prop and body objects separately;
  preserve an explicitly requested complex concept.

### Step 3 — source and permission

- At 00:13:44 a slide displays a curated Pinterest board link and thumbnail grid
  [qy-wwP-b9HY-02-001342].
- The artist opens the link, scrolls through a grid of character illustrations,
  then returns to the slide [qy-wwP-b9HY-02-001355, 00:13:56–00:14:05;
  qy-wwP-b9HY-02-001406, 00:14:08–00:14:18].
- The visible board address is https://www.pinterest.com/kennysarts_/concept-art-inspo/;
  the screenshot shows 70 pins at that moment, not a permanent count.
- At 00:15:45 the credited concept artist's Instagram profile is visible
  [qy-wwP-b9HY-02-001543]; the board credits `@jennifer.p_679`.
- The narration says permission was given for this course; that is not a grant to others.
- **Reader equivalent:** retain the original source and permission information;
  a saved pin is not itself evidence of permission.

### Step 4 — compare groups, not a generic mood board

- At 00:15:57 the whole first board is visible before the artist zooms into its concept
  [qy-wwP-b9HY-02-001556].
- A close-up of the concept head is placed beside several stylised faces and a photo.
  At 00:16:14–00:16:21 individual face images receive selection outlines
  [qy-wwP-b9HY-02-001609].
- The large-eyed stylised face is the stated style reference; the others support
  interpretation of facial proportions, rather than replacing the original face.
- At 00:16:34 the view moves to the boots, then back to the ambiguous sketch and
  into the product photograph [qy-wwP-b9HY-02-001623;
  qy-wwP-b9HY-02-001636, 00:16:37–00:16:47].
- One large image supplies the boot design; three smaller photographs illustrate
  leather creases [qy-wwP-b9HY-02-001648, 00:16:50–00:16:59].
- At 00:17:14 the skirt group shows a large pleated example with four smaller ones
  [qy-wwP-b9HY-02-001713]. The artist returns to the concept before changing groups.
- At 00:17:31–00:17:37 two side-view hair photographs are enlarged:
  inspect the crown flow, tie location and loose strands near the face
  [qy-wwP-b9HY-02-001726].
- At 00:17:47 the board moves to two stylised body examples, one with arms away
  from the torso [qy-wwP-b9HY-02-001739].
- At 00:18:02 a second board appears, with a different red-dress concept and
  groups for face, body, jewellery, hair, heels, dress and dress material
  [qy-wwP-b9HY-02-001752].
- The artist selects the face group, then the body images, including a torso shown
  from several directions [qy-wwP-b9HY-02-001808, 00:18:12–00:18:18;
  qy-wwP-b9HY-02-001820, 00:18:24–00:18:29].
- The dress construction photographs and the separate fabric appearance group serve
  different decisions: ruffle form versus shading
  [qy-wwP-b9HY-02-001830, 00:18:36–00:18:43;
  qy-wwP-b9HY-02-001845, 00:18:46–00:18:52].
- The artist returns to an overview after selecting hair and jewellery
  [qy-wwP-b9HY-02-001857, 00:18:59–00:19:09].
- This zoom-out, zoom-in rhythm keeps each detail tied to the selected concept;
  screenshots do not reveal the precise input gestures used for every navigation.
- **Reader equivalent:** read the original and each supporting file directly;
  record which uncertainty each one resolves. Do not measure against unrelated people.

### Step 5 — proportions

- The chapter 02 board sheets end at 00:21:34; the proportion exercise appears at the start of chapter 03,
  where the artist marks and compares head and torso heights over the concept [qy-wwP-b9HY-03-002359, 00:23:59].
- **Reader equivalent:** record estimated landmarks and ratios from the actual
  concept, labelling a posed or three-quarter estimate as an estimate.

### Step 6 — measurable views

- The board pictures are visual guides, not measured orthographic turnarounds.
  A multi-angle supporting character is not automatically a view of this design.
- **Reader equivalent:** inspect genuine design views for orientation and pose,
  run the existing background/crop checks, and retain the original reference.
- `outline_match` uses the unchanged 0.98 threshold on eligible views only.
  `not_run` means looked at, not measured; it is never a pass.

### Step 7 — put usable views in Blender

- The artist presents PureRef as a separate reference-board application; at
  00:19:33–00:19:47 the browser shows its download choices
  [qy-wwP-b9HY-02-001924; qy-wwP-b9HY-02-001938], and chapter 03 demonstrates
  pinning the PureRef window with Always on Top [qy-wwP-b9HY-03-003531, 00:35:31].
- Chapter 02 does not demonstrate adding an image empty to Blender.
- **Reader equivalent:** use `reference_setup` for each eligible real view,
  and read detail images as files. Keep Z up, feet at Z=0, facing -Y.
- Use `viewport_capture` to inspect only views for which images were provided.

### Step 8 — save

- Chapter 02 ends with a concept-and-reference checkpoint [qy-wwP-b9HY-02-002005, 00:20:07–00:20:23];
  saving the Blender project via the Save As dialog appears in chapter 03 [qy-wwP-b9HY-03-013428, 01:34:28].
- **Reader equivalent:** use `save_file` after reference setup; keep stage versions.

## Settings the course uses

| Setting | Value | Where | Timestamp |
| --- | --- | --- | --- |
| Number of main concepts | 1 | Picture board | 00:15:56 |
| Supporting groups, main example | face, boots, skirt, hair, body | Picture board | 00:15:56 to 00:18:08 |
| Extra groups, second example | dress structure, dress material, heels, hair, jewellery | Picture board | 00:18:08 to 00:19:11 |
| Pictures per group | about 2 to 5 (read from the frames) | Picture board | 00:15:40, 00:16:15 |
| Board window | always on top, lower-left corner under a small preview viewport | PureRef | 00:35:31 |
| Suggested time for the whole course | 13 chapters, one week each, about 3 months for a beginner | Introduction | 00:06:35 to 00:07:21 |

The course gives no numeric setting for picture size, resolution or scale in these chapters.

## Mistakes the course warns about

- Skipping the concept and starting in Blender with only an idea: weak results and confusion [00:10:38].
- Overthinking the choice. Appeal to the maker is enough [00:11:41].
- Starting with an overly detailed design while still learning the process [00:12:28].
- Using an artist's work without asking [00:13:30, 00:14:22].
- Collecting pictures because they are pretty. Each one must answer a question about the concept [00:15:03].
- Trusting the concept alone for parts it draws loosely (the course's examples: boots, skirt, hair
  direction) [00:16:36 to 00:17:39].

## What changes for a different character

General, keep for any character: one locked concept; one supporting group per unclear part; reading the
main ratios before modelling; modelling in a neutral pose whatever the concept shows.

Specific to the course's character: the groups themselves (boots, skirt, tied-up hair), and the choice of
face pictures that match the character's ethnicity as proportion guides.

- Creatures and animals: add anatomy references (skeleton and muscle diagrams of the nearest real animal),
  and get a TOP picture as well as FRONT and side, since four-legged bodies read mostly from the side and
  top. The neutral pose is standing square on all legs, tail and wings spread away from the body.
- Hard-surface parts (armour, weapons, robots): orthographic drawings matter more than for organic forms.
  Ask for front, side, top and back, and collect photos of the real mechanism (hinges, straps, buckles) so
  joints are built to move.
- Very stylised bodies (huge head, tiny legs): the ratio list in step 5 matters more, because nothing about
  normal human proportion can be assumed.
- Characters with long hair, cloaks or skirts that hide the body: get one reference of the body alone if
  possible. Otherwise the body under the cloth is a guess; say so.

## Exit check

Before starting the blockout, all of these are true and written down:

1. One concept file path, with its source.
2. A supporting picture, or a "clear enough" note, for every visible part.
3. The ratio list from step 5, marked "measured from a straight-on picture" or "estimated by eye".
4. `check_reference` has been run on every picture meant for measuring. For each of FRONT, BACK, LEFT,
   RIGHT, TOP the notes say one of: "measurable" (straight-on, plain or transparent background, cropped
   tight, neutral pose) or "no picture: looked at, not measured".
5. `reference_setup` has been called for every measurable view with one shared `height`, and captures of
   supplied views show the pictures upright and facing the right way.
6. The file is saved.

What counts as failed: no concept; a picture intended for measuring that `check_reference` reports as not
measurable; front and side pictures whose landmarks disagree by more than about 2% of height; a view listed
as measurable that is really a three-quarter or posed drawing. Having fewer than two measurable views
(FRONT plus one side) is not a failure of this stage; report which views can be tested and which cannot.
The 0.98 target can still be tested independently for each eligible view, but not for missing views.

## Gaps

- PureRef (pureref.com) is a separate program, not a Blender add-on. It is pay-what-you-want and can be
  downloaded for nothing [00:19:38]. The agent cannot use it. The route here is files on disk plus
  `reference_setup`.
- The course never sets up reference images inside Blender and never measures likeness. Everything about
  straight-on views, cropping, `check_reference` and `outline_match` in this file is ours.
- `blender-live` has no tool that looks at a picture and says whether it is straight-on or what pose it
  shows. The agent must judge that by reading the image itself.
- Making neutral-pose front and side views from a single posed drawing is outside these tools. It needs the
  user, an artist, or an image tool.
- The selected frames identify the concept artist and Pinterest board, but do not establish where to obtain
  the course project files.
- The proportion theory used in step 5 comes from the opening of chapter 03, not chapter 02. It is placed
  here because it has to happen before any geometry is made.
