# Speed-sculpt route: a posed, painted character from spheres

Source: YanSculpts, [How to Sculpt D.Va in 1 Minute](https://youtube.com/shorts/FGU0ZwYub-0), a 59 s timelapse of a
longer live sculpt, narrated in one fast run of short sentences. Read from frames every ~2 s and the narration
(auto-captions; "add a sphere" is captioned "at his fear"). It is filmed on a phone pointed at a pen display, so most
panel values cannot be read. Only the brush radius and strength fields in the header are readable. Times are marked
`YS`. Labels: `annotations/FGU0ZwYub-0/`.

Use this route when the job is a **single posed character for renders or a turntable** (a statue, fan art, a
portfolio still) that will not be rigged or exported to a game. The pose is built in from the first sphere, nothing
is retopologized, and colour is painted onto the sculpt's vertices without UVs. For anything that must deform, use
the sculpt route or the low-poly game route instead (see "Two routes" in `SKILL.md`).

## The idea

Every part is its own sphere: head, torso, each limb segment, eyeballs, hair mass, shoes, lashes. Each sphere is
scaled, placed in the final pose and sculpted. Clothes are duplicates of the body part they cover. Thin things
(loose strands, shoelaces) are bevelled curves. Colour is painted last, straight on the sculpt.

## Order of work

1. **Head from one sphere** [YS 00:00 to 00:05]. Scale a sphere into an egg. Pull the face plane and jaw down out
   of it, and the neck below. Carve the eye sockets, draw the nose, pull the ears out from the sides and carve into
   them, then sculpt the mouth and nostrils. Strength fields read 0.3 to 0.4 for this blocking.
2. **Eyeballs before eyelids** [YS 00:07 to 00:09]. Place a sphere in each socket as its own object, *then* sculpt
   the lids around it. The lid has to wrap the ball, so the ball comes first.
3. **Body, a sphere per part** [YS 00:11 to 00:14]. A new sphere for the torso, sculpted with a large brush. A sphere
   stretched into the upper leg, duplicated for the lower leg and for the other leg.
4. **Iris and gaze** [YS 00:16 to 00:18]. On each eyeball, select the front cap in Edit Mode and extrude/inset it
   into an iris, then rotate the eyeballs so the gaze matches.
5. **Shoes and arms** [YS 00:20 to 00:24]. Spheres for the shoes, sculpted. A sphere scaled into a capsule for the
   upper arm, duplicated for the forearm. The arms go straight into the **final pose** (bent over the head here).
6. **Hair mass** [YS 00:26 to 00:28]. A new sphere over the skull, sculpted into the front hair mass, then the back.
   Carve strand grooves into it with a crease-style brush to read as clumps.
7. **Clothes from the body** [YS 00:30 to 00:34]. Duplicate the torso to make the shirt, give it its own colour, and
   sculpt sleeves and folds on the copy. The shorts are sculpted the same way around the hips.
8. **Paint on the sculpt** [YS 00:36 to 00:41]. Brown hair; reds over the face; pink lips, cheeks and face marks;
   black eyes, then the iris colour. The brush header shows radius in pixels and strength: 78 px / 0.5 for the face,
   35 px for lips and cheeks, 81 px / 1.0 on the eye. No UV or image editor appears, so this is colour painted onto
   the mesh's vertices (Sculpt Mode Paint brush); that is inferred from the screen, not stated.
9. **Lashes and loose strands** [YS 00:43 to 00:45]. Eyelashes are sculpted from another small sphere on the lid line.
   Loose hair strands are drawn as **curves** in front of the face.
10. **Shoelaces, shoes, logo, smile** [YS 00:47 to 00:51]. Laces are curves too. Sculpt the shoe and shorts detail.
    Paint the shirt logo (22 px, strength 1.0). Reshape the mouth corners into a smile (35 px, strength 0.344).
11. **Refine, then light** [YS 00:53 to 00:59]. Smooth and refine the legs with a big brush (167 px, strength
    0.466), finish the hair, add lights, and show the coloured figure rendered.

## Doing it through the MCP tools

| Step in the video | Here |
|---|---|
| sphere per part, placed in the pose | `exec_python`: `bpy.ops.mesh.primitive_uv_sphere_add`, then scale/rotate/locate it; name it (`SS_head`, `SS_torso`, `SS_thigh_L`, ...) |
| even, sculptable surface on each sphere | `sculpt_remesh(object, voxel_size)`; repeat when strokes stretch the faces |
| pull, carve, draw, crease, smooth | `sculpt_strokes` with `grab`, `draw`, `crease`, `clay_strips`, `snake_hook`, `inflate`, `smooth`; `sculpt_relax` for whole-mesh smoothing |
| protect a region while working nearby | `sculpt_mask` |
| clothes from the torso | duplicate the object in `exec_python`, inflate it slightly, then `sculpt_strokes crease` for folds |
| loose strands, laces | Bezier curves with `bevel_depth` in `exec_python` |
| painting on the sculpt | a colour attribute written per vertex (below), or `project_paint` when the colours come from reference pictures |
| check | `viewport_capture` and the likeness tools, as on every route |

```python
# not run in Blender: colour the vertices of an object inside a sphere of influence (a "paint stroke" without UVs)
import bpy
from mathutils import Vector

def paint_sphere(obj_name, centre, radius, rgba, name="Col"):
    me = bpy.data.objects[obj_name].data
    attr = me.color_attributes.get(name) or me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    me.color_attributes.active_color = attr
    c, mw = Vector(centre), bpy.data.objects[obj_name].matrix_world
    for v in me.vertices:
        d = ((mw @ v.co) - c).length
        if d < radius:
            w = 1 - d / radius                      # soft edge, like a Smooth falloff
            old = attr.data[v.index].color
            attr.data[v.index].color = [old[i] * (1 - w) + rgba[i] * w for i in range(4)]
    me.update()

# show it: a material with a Color Attribute node (layer "Col") into Base Color, or Solid shading with
# shading.color_type = 'VERTEX'
```

## What the longer videos add (his last six months)

Four more videos (uploaded 2026-07-26 to 2026-08-30) were studied the same way:
- two 22-minute music-only timelapses, "Sculpting a Girl (Summer)" `umF8UhsczO4` and "(Black and White)" `huJs2R7JckM`, from 91 study sheets;
- two narrated Shorts, Venom `Yq9Dzaw2f1k` and Spider-Man `ainRAUwXMO4`, transcribed with Whisper because YouTube's captions were rate-limited.

The labels are 222 rows in `annotations/<video id>/`. What they add to the steps above:

- **Grab does nearly everything.** It is the active brush in most frames at strength **0.45** (Black and White) to
  **0.60** (Summer). The rest:

  | Brush | Use | Strength |
  |---|---|---|
  | Draw | carving | 0.28 to 0.5, about 19 to 43 px |
  | Clay Strips | lips, under the eyes | 0.44 |
  | Crease Polish | ear, folds | 0.25 |
  | Inflate/Deflate | | 0.5 |
  | Snake Hook | hair tips | 1.0 |

  No Smooth brush is seen in Summer; the forms stay faceted until painting.
- **Nothing is joined.** The outliner grows past 30 separate spheres (`Sphere` ... `Sphere.030`). The ear sphere has a
  Mirror modifier whose mirror object is the head, so one ear makes both. The head has Subdivision + Mirror. Remesh
  is seen once, on the head, early [YS umF8UhsczO4 00:00:25]. Dyntopo and Multires are never seen. In the
  Spider-Man Short alone he merges forearm into upper arm and neck into body near the end, then smooths the seam.
- **Each new part is a copy of its neighbour.** Head to neck to torso, upper arm to forearm, one tooth to the whole
  row, upper teeth to lower, tongue to saliva strands.
- **Brows and lash lines are not sculpted.** Each is a flat strip (a Plane edited in Edit Mode, the lash made with
  Extrude Region along the lid) with **Subdivision + Mirror + Shrinkwrap (target: head) + Solidify**.
- **Hair:** a cap sphere and a bun, then **one small sphere per lock** pulled out with Snake Hook (strength 1.0) and
  then Grab. Some locks carry Subdivision. Loose strands are curves only in the Shorts.
- **Clothes by mask and extract.** He paints a Mask on the torso where the top sits, and a new object `Mesh.001`
  appears with a `geometry_extract_solidify` modifier: Sculpt Mode's Mask Extract. Clothing pieces get a Mirror
  modifier (X, Clipping on, Merge 0.001 m). The Shorts still duplicate a body part for clothes.
- **Painting.** It is done in Sculpt Mode with the Paint brush ("Paint Soft", Blend Mix), strength 1.0 and a very
  large radius (69 to 401 px) for fills, softer for blush. The order is always:
  1. a flat base colour on each part;
  2. second colours in blocks;
  3. cleaned-up edges.

  He changes colours on the fly. Summer goes purple hair, olive top, pale pink skin, salmon lips
  [YS umF8UhsczO4 00:15:31], then cheeks.
- **Ink lines are Grease Pencil, drawn onto the surface** (Ink Pen, black, placement Surface): lid lines, irises,
  pupils, lashes, lip lines, cheek marks, hair highlights. The Grease Pencil objects have Mirror and Opacity
  modifiers, and he lowers the opacity.
- **The black-and-white look is a material, not paint.** `skin.001` puts a Mix Shader between two Principled BSDFs,
  switched by a Color Ramp, for a two-tone toon split.
- **Lighting is in the viewport.** Up to six lights in a `LIGHTS` collection, mostly Suns plus one Area. They are
  peach, orange and red-orange, placed for rims, with Scene Lights and Scene World on. No camera or final render is
  seen. He goes back to the face after lighting.

## As Python: `scripts/speed_sculpt.py`

The method above as a replayable plan: an ordered list of `blender-live` tool calls (`exec_python`,
`sculpt_remesh`, `sculpt_begin`, `sculpt_strokes`, `sculpt_mask`), each with the reason and the video time it comes
from.

```
python <skill>/scripts/speed_sculpt.py --height 1.6 --colors hair=#6b4a8a,top=#7a7a3a > plan.json
```

Call each step's `tool` with its `args`, in order, and look (`viewport_capture`) after each part. The plan builds:
- every part as its own `YS_<part>` sphere;
- the face strokes, eyeballs, then lids;
- Grab-led body strokes;
- brow and lash strips with his modifier stack;
- hair locks pulled with Snake Hook;
- the top by mask and extract;
- base colours, iris, lips and blush painted into a `Col` colour attribute;
- the two-tone toon material, and the rim lights.

The proportions (a figure about 7 heads tall) and the stroke distances are the module's defaults, not values from
the video. Replace them with what the reference pictures show; the module only fixes the *order and kind* of each
operation. The module is tested without Blender (`tests/test_speed_sculpt.py`):
- every step names a real server tool with real arguments;
- every stroke passes the server's stroke checks;
- every code block parses;
- the steps keep his order.

The generated `bpy` code has **not** been run in Blender here yet. Grease Pencil ink is not scripted. Use a thin
dark paint dab along the line (`code_paint` with a small radius) or draw it by hand.

## What this route trades away

- Separate overlapping spheres are fine for a still image; they do not deform. To rig it later you would need the
  sculpt route's join, remesh, retopology and UVs (stages 06 and 07).
- A pose built in from the start cannot be changed cheaply.
- Vertex colour detail is limited by the vertex count; the logo and face marks need a dense surface.

## Not visible in the frames

In the D.Va Short: the brush names. Across all five videos:
- the remesh voxel size;
- most brush radii;
- the sphere segment counts;
- the curves' bevel settings;
- exact colour values;
- light strengths;
- whether any final render is made.
