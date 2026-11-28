# 11 Lighting and presenting

Course source: chapter 14 "Lighting & Presenting Your Character", 19:05:43 to 20:01:38, and chapter 15 "My Final
Renders", 20:01:38 to 20:03:16.
The course records in Blender 5.0.1; everything below is written and checked for Blender 4.5.16.

## Goal

The posed character stands on a seamless backdrop, lit by a three-point setup (key, fill, rim) plus the helper
lights the course adds, with a dim world for ambient light. Named cameras frame a wide shot and a close-up, a
turntable camera circles the character with the lights travelling along, and Cycles stills are rendered, checked
for exposure, and finished with a light grading pass.

## Starting state

- Stage 10 finished: `rig` generated, every part following it, at least one presentation pose keyed on a known
  frame. Set that frame before building anything here, because the lights are placed around the posed character.
- Materials and hair from stages 08 and 09.
- Hide `rig`, `metarig` and rig helper meshes from the viewport and renders. The course shows the viewport
  visibility change [19:23:01]; render visibility is a reader precaution. Rigify `WGT-...` widgets in
  `WGTS_rig` are not part of the character (see step 1).

## What the course says lighting is for [19:07:07 to 19:11:15]

- Lighting carries the mood. The same model reads as menacing or gentle depending only on the light [19:08:36].
- It must do three jobs: set the mood, show that the form has depth, and steer the eye (usually to the face and
  eyes) [19:08:24, 19:09:44].
- Lighting and framing are judged together. A setup that works from one camera can fall flat from another, so
  the camera comes first [19:09:57].
- Use reference for lighting and composition too: film stills, animation frames. Copy what already works
  [19:10:22].
- Light types [19:11:15 to 19:17:10]: an HDRI lights the scene from an image; the whole environment can rotate,
  but its individual light sources cannot be repositioned independently. The course uses it as dim ambient light;
  a point shines in all directions; a sun cares only about rotation; a spot is a cone with `Spot Size` and
  `Blend`; an area light is a soft box and the main character-lighting tool. A larger emitter softens shadows.
- Three-point lighting is the dependable start, not the destination. The key is the brightest light and draws
  the form with shadow. The fill sits on the opposite side and lifts those shadows without removing them. The
  rim sits behind and draws a bright edge that separates the character from the background [19:18:37 to
  19:20:35]. The course's own final renders leave it for a moodier coloured setup (see "Shots").

## Order of work

### 1. Measure the posed character

Everything below is placed relative to the character's box, so it works at any size. Pass only the character's
own render meshes. The Rigify widget meshes (`WGT-...`) sit in the scene too; in my test they widened the box
from 1.03 m to 1.62 m until they were filtered out.

```python
# verified in 4.5.16 background
import bpy, bmesh, math
from mathutils import Vector as V

def character_box(objects):
    dg = bpy.context.evaluated_depsgraph_get()
    pts = [o.evaluated_get(dg).matrix_world @ V(c) for o in objects for c in o.evaluated_get(dg).bound_box]
    lo, hi = (V([f(p[i] for p in pts) for i in range(3)]) for f in (min, max))
    return {"min": lo, "max": hi, "centre": (lo + hi) / 2, "height": hi.z - lo.z, "width": hi.x - lo.x,
            "floor": V(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))}

def character_meshes():
    return [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.hide_render
            and not o.name.startswith("WGT-") and "rig_helper" not in o.name and o.name != "backdrop"]

def collection(name, parent=None):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    par = parent or bpy.context.scene.collection
    if col.name not in par.children: par.children.link(col)
    return col

def aim(obj, target):                      # lights and cameras look along their own -Z
    obj.rotation_euler = (V(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

def polar(box, azimuth_deg, distance, height_f):
    """A point around the character: azimuth 0 = straight in front (it faces -Y), positive = toward its left (+X),
    180 = behind. height_f is a fraction of the character's height above the floor."""
    a = math.radians(azimuth_deg)
    f = box["floor"]
    return V((f.x + math.sin(a) * distance, f.y - math.cos(a) * distance, f.z + height_f * box["height"]))
```

### 2. Render size and a first camera [19:23:13 to 19:25:40]

The course sets the camera before any light. Resolution depends on where the picture goes: 1920 x 1080 for
ArtStation or video, 1200 x 1500 (portrait, 4:5) for Instagram, which is what it uses [19:23:52]. Focal length:
it gives 80 to 90 mm as the usual portrait range and then goes longer because it looks better; its cameras read
138 mm [19:24:45, frame at 19:25:05]. A long lens flattens the face and keeps a big stylized head from bulging.
It locks the camera to the view to steer it, and in the camera's `Viewport Display` sets `Passepartout` to 1 so
nothing outside the frame shows [19:37:23].

`add_camera` solves the distance from the lens, the picture's shape and the part of the character to be framed,
so set the resolution first (step 8 sets it; or set `scene.render.resolution_x/y` now).

```python
# verified in 4.5.16 background
def add_camera(name, box, zmin_f, zmax_f, azimuth_deg=15.0, lens=138.0, margin=1.12, half_width=None, height_f=None):
    """Frame the slice of the character between two height fractions (0 = floor, 1 = top of the box)."""
    sc = bpy.context.scene
    cd = bpy.data.cameras.new(name)
    cd.lens, cd.passepartout_alpha = lens, 1.0
    ob = bpy.data.objects.new(name, cd)
    collection("RENDER").objects.link(ob)
    rx, ry = sc.render.resolution_x, sc.render.resolution_y
    half_long = math.atan(cd.sensor_width / 2 / lens)      # sensor fit AUTO: 36 mm spans the longer image side
    half_v = half_long if ry >= rx else math.atan(math.tan(half_long) * ry / rx)
    half_h = half_long if rx > ry else math.atan(math.tan(half_long) * rx / ry)
    tall = (zmax_f - zmin_f) * box["height"] * margin
    wide = (half_width * 2 if half_width else box["width"]) * margin
    dist = max(tall / 2 / math.tan(half_v), wide / 2 / math.tan(half_h))
    mid = (zmin_f + zmax_f) / 2
    ob.location = polar(box, azimuth_deg, dist, mid if height_f is None else height_f)
    aim(ob, box["floor"] + V((0, 0, mid * box["height"])))
    cd.clip_end = max(cd.clip_end, dist * 10)
    return ob

def in_frame(cam, points):                 # fraction of world points inside the camera frame
    from bpy_extras.object_utils import world_to_camera_view
    bpy.context.view_layer.update()
    cs = [world_to_camera_view(bpy.context.scene, cam, V(p)) for p in points]
    return sum(0 <= c.x <= 1 and 0 <= c.y <= 1 and c.z > 0 for c in cs) / max(len(cs), 1)
```

Wide shot: `add_camera("camera_wideshot", box, 0.0, 1.0, azimuth_deg=15)`. Close-up (head to chest):
`add_camera("camera_closeup", box, 0.68, 1.02, azimuth_deg=25, half_width=0.2 * box["height"])`. The azimuths
are my starting values; the course chooses angles by eye and says the right one differs per character
[19:25:11]. If the head is turned in the pose, put the camera on the side the face looks toward.

### 3. Backdrop [19:26:54 to 19:29:17]

A studio sweep: floor and back wall in one curved surface, so there is no horizon line. The course first shows a
plane with its back edge extruded up and bevelled, then rejects it because a camera to the side sees the plane's
edge. Its choice is a scaled filled circle; the visible extrusion makes a cylindrical wall around the rim. The
floor-wall edge is bevelled with six segments and shaded smooth [qy-wwP-b9HY-14-192822, 19:28:22].
The scripted half-wall below is a practical reconstruction, not the exact demonstrated mesh.
It goes in a new collection `RENDER` together with the cameras; lights go in a child collection `lights`.

Material [19:36:29 to 19:37:06]: one dark colour chosen to suit the character, high roughness (0.895 in the
frame) and specular turned down, so the backdrop takes light softly and shows no hot spot. Later the course
darkens the colour again [19:43:06].

```python
# verified in 4.5.16 background
def make_backdrop(box, radius_f=1.6, wall_f=2.5, colour=(0.05, 0.03, 0.025, 1.0)):
    H, f, seg, sweep = box["height"], box["floor"], 64, 8
    R, rb = radius_f * H, 0.35 * H
    bm = bmesh.new()
    ring = lambda r, z, ids: [bm.verts.new((f.x + r * math.cos(2 * math.pi * i / seg),
                                            f.y + r * math.sin(2 * math.pi * i / seg), f.z + z)) for i in ids]
    centre, floor = bm.verts.new(f), ring(R, 0.0, range(seg))
    for i in range(seg): bm.faces.new((centre, floor[i], floor[(i + 1) % seg]))
    back = list(range(seg // 2 + 1))                       # the +Y half: behind the character
    prev = [floor[i % seg] for i in back]
    rows = [(R + rb * math.sin(math.pi / 2 * s / sweep), rb * (1 - math.cos(math.pi / 2 * s / sweep))) for s in range(1, sweep + 1)]
    for r, z in rows + [(R + rb, wall_f * H)]:             # quarter-circle sweep, then the straight wall
        cur = ring(r, z, back)
        for j in range(len(back) - 1): bm.faces.new((prev[j], prev[j + 1], cur[j + 1], cur[j]))
        prev = cur
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new("backdrop")
    bm.to_mesh(me); bm.free()
    for p in me.polygons: p.use_smooth = True
    ob = bpy.data.objects.new("backdrop", me)
    collection("RENDER").objects.link(ob)
    mat = bpy.data.materials.new("backdrop")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = colour
    bsdf.inputs["Roughness"].default_value = 0.9
    bsdf.inputs["Specular IOR Level"].default_value = 0.1
    me.materials.append(mat)
    return ob
```

### 4. The lights [19:29:40 to 19:42:35]

Before adding lights the course switches the rendered viewport to use the scene's own lights and world; during
shading it had been using the viewport's built-in studio light [19:26:11]. Through blender-live,
`viewport_capture(camera="camera_wideshot", shading="RENDERED")` shows the same thing, and `render_image` is the
real check. It also lowers the hair `Viewport Amount` (0.05, later 0.01) while lighting and sets it back to full
before judging the result [19:30:26, 19:42:40, 19:45:16].

What the course builds, in order, each judged by switching it off and on [19:32:22]:

| Light | Type, size | Where, relative to the character | Power in the course | Colour | Job |
|---|---|---|---|---|---|
| `light_key` | area, 1 m square | in front, to one side, above head height, turned down onto the face | 16.7 W while adjusting, later 18.2 W, then 13.4 W once two lights share it | white | main light; shades the far side of the face [19:31:08, 19:31:44] |
| `light_fill` | area, 1 m, object scaled up | in front on the opposite side | 1.36 W | white | lifts the shadows; large so it casts no shadow of its own [19:33:20] |
| `light_rim` | area, 1 m, scaled narrow in X and tall in Z | behind, off to one side, reaching down to the legs | 49.4 W | orange-red, `#FF8859` | bright edge on one side of the body [19:33:48, 19:39:20] |
| `light_key.001` | copy of the key sharing its light data | same side, lower, aimed at the legs | shared | white | the legs were too dark [19:37:58] |
| `light_fill.001` | copy of the fill | same side as the fill, lower | shared | white | lifts leg shadows [19:38:50] |
| `light_backdrop` | point, radius 0 | behind the character, hidden from the camera by the body | 14.5 W, then raised | orange | a glow on the backdrop behind the figure [19:40:58] |
| `light_fill.002` | copy of the fill | low, off to the side, near the backdrop | fill power, adjusted | white | washes out the character's shadows on the backdrop [19:41:56] |

Rules the course applies while placing them:

- Do not blow out the key. Raise power until the lit side is bright, not white [19:30:52].
- First key position split the face into a lit half and a dark half. The course moved it toward the camera until
  some light reached the far cheek [19:40:06]. Hide the fill while judging the key [19:39:50].
- With the fill at key strength the picture goes flat. Drop it until the shadows are lighter but still there
  [19:32:02]. The ratio in the course is about 12 to 1.
- Scaling an area light down sharpens its shadows; scaling up softens them. Same as changing `Size` [19:32:43].
- The rim is much stronger than the key, narrow, and turned so it only grazes one side [19:34:23 to 19:35:00].
- The rim also hits the backdrop behind the character and makes a hot patch. The course fixes this with light
  linking: on the rim light, `Object > Shading > Light Linking`, new collection, add the backdrop, set it to
  exclude [19:35:28].
- Linked copies: duplicate the light, then `Ctrl L > Link Object Data`, so one power value drives both [19:38:24].
- A coloured rim reads better than a white one. Choose the colour against the character's palette [19:39:20].

The course gives no positions in numbers. The placements and distances below are mine, read off its viewport
frames [19:31:28, 19:40:30, 19:41:58]. Its character is about 1.9 m tall by my estimate from the 1 m light
gizmo, so the powers are scaled by (height / 1.9) squared to keep the same brightness at another size.

```python
# verified in 4.5.16 background
def add_light(name, kind, location, target=None, power=10.0, colour=(1, 1, 1), size=1.0, size_y=None, data=None):
    ld = data or bpy.data.lights.new(name, kind)
    if data is None:
        ld.energy, ld.color = power, colour
        if kind == "AREA":
            ld.shape, ld.size = ("RECTANGLE" if size_y else "SQUARE"), size
            if size_y: ld.size_y = size_y
        else:
            ld.shadow_soft_size = size
    ob = bpy.data.objects.new(name, ld)
    collection("lights", collection("RENDER")).objects.link(ob)
    ob.location = location
    if target is not None: aim(ob, target)
    return ob

def exclude_from_light(light_obj, objects):                # light linking; Cycles, and EEVEE from 4.3
    lc = bpy.data.collections.new("LL_" + light_obj.name)
    for o in objects: lc.objects.link(o)
    light_obj.light_linking.receiver_collection = lc
    for co in lc.collection_objects: co.light_linking.link_state = "EXCLUDE"

def three_point_rig(box, backdrop=None, key_side=1, power_scale=1.0,
                    rim_colour=(1.0, 0.246, 0.100), back_colour=(1.0, 0.38, 0.15)):
    """key_side +1: key on the character's left (+X); -1: on its right. Put the key on the side the face turns to."""
    H, s = box["height"], key_side
    k = (H / 1.9) ** 2 * power_scale
    head, chest, legs = (box["floor"] + V((0, 0, z * H)) for z in (0.88, 0.62, 0.25))
    L = {}
    L["key"] = add_light("light_key", "AREA", polar(box, 40 * s, 0.75 * H, 1.15), head, 15.0 * k, size=0.55 * H)
    L["key_low"] = add_light("light_key.001", "AREA", polar(box, 35 * s, 0.8 * H, 0.45), legs, data=L["key"].data)
    L["fill"] = add_light("light_fill", "AREA", polar(box, -55 * s, 1.0 * H, 0.85), chest, 1.4 * k, size=1.3 * H)
    L["fill_low"] = add_light("light_fill.001", "AREA", polar(box, -50 * s, 1.0 * H, 0.3), legs, data=L["fill"].data)
    L["rim"] = add_light("light_rim", "AREA", polar(box, -145 * s, 0.9 * H, 0.7), chest, 50.0 * k, rim_colour,
                         size=0.3 * H, size_y=1.3 * H)
    L["backdrop_light"] = add_light("light_backdrop", "POINT", polar(box, 180, 0.9 * H, 0.55), None, 15.0 * k, back_colour, size=0.0)
    L["backdrop_fill"] = add_light("light_fill.002", "AREA", polar(box, 120 * s, 1.3 * H, 0.2),
                                   polar(box, 180, 1.6 * H, 0.1), 1.4 * k, size=1.3 * H)
    if backdrop is not None: exclude_from_light(L["rim"], [backdrop])
    return L
```

`#FF8859` is a display (sRGB) hex; as the linear RGB that `light.color` takes it is (1.0, 0.246, 0.100). The
course's light panel also shows `Exposure` 0 and `Normalize` ticked, both untouched; 4.5.16 has the same two
properties (`light.exposure`, `light.normalize`). After building, adjust in this order, one light visible at a time:
key position and power, then fill power, then rim position, then backdrop.

### 5. World: dim ambient light only [19:43:10 to 19:44:36]

The course lights with a flat dark world, then switches to a dim outdoor HDRI using Poly Haven's
`lauter_waterfall` asset (1K) and lowers its Strength (EVs) to about −2.1 to −2.3 EV
[qy-wwP-b9HY-14-194424, 19:44:26–19:44:33]. A brief remark at 19:44:01–19:44:10 shows switching back to the original
world only to explain the route without the add-on. Without the add-on, load a downloaded HDRI into an
`Environment Texture` node. The bundled forest HDRI and strength below are reader starting points, not measured course settings.

```python
# verified in 4.5.16 background
def set_world(strength=0.2, hdri_path="builtin:forest.exr", rotation_deg=0.0, colour=(0.05, 0.05, 0.05)):
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world, w.use_nodes = w, True
    nt = w.node_tree
    nt.nodes.clear()
    out, bg = nt.nodes.new("ShaderNodeOutputWorld"), nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    bg.inputs["Color"].default_value = (*colour, 1.0)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    if hdri_path.startswith("builtin:"):   # bundled: city, courtyard, forest, interior, night, studio, sunrise, sunset
        import os
        hdri_path = os.path.join(bpy.utils.system_resource("DATAFILES", path="studiolights/world"), hdri_path[8:])
    if hdri_path:
        tex, mp, tc = (nt.nodes.new(t) for t in ("ShaderNodeTexEnvironment", "ShaderNodeMapping", "ShaderNodeTexCoord"))
        tex.image = bpy.data.images.load(hdri_path, check_existing=True)
        mp.inputs["Rotation"].default_value[2] = math.radians(rotation_deg)
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
    return w
```

Pass `hdri_path=""` for the flat colour.

### 6. More cameras [19:45:03 to 19:46:40]

Rename the first camera `camera_wideshot`, duplicate it as `camera_closeup` and reframe. The course suggests a
wide shot and a close-up as the minimum, plus detail shots of the parts that took work (shoes, skirt) [19:46:13].
Both of its cameras keep the 138 mm lens [frame at 19:46:00].

### 7. Turntable and one timeline for every shot [19:46:36 to 19:52:35]

A 360 degree turnaround. Duplicate the wide camera as `camera_turnaround`, add a sphere empty
`camera_turnaround_CTRL`, parent the camera to it, and rotate the empty. Two problems appear: from behind, the
backdrop wall blocks the camera, and from the side the lighting is no longer the designed one. The fix is to
parent the backdrop and all lights to the same empty, so the whole studio turns around the character and the
light is identical from every side [19:48:13 to 19:49:10].

Cameras are bound to frames with timeline markers (`Ctrl B` over the timeline): frame 1 `camera_closeup`, frame 2
`camera_wideshot`, frame 3 onward `camera_turnaround` [19:49:29 to 19:50:38]. One animation render then gives
both stills and the turntable. Length: 24 fps x 8 s = 192 frames, plus the start offset of 3, so the course sets
the end frame to 195 [19:50:51]. It keys the empty's rotation at the first frame and 360 degrees on Z at the last
[19:51:38].

```python
# verified in 4.5.16 background
def bind_cameras(cams_by_frame):
    sc = bpy.context.scene
    for frame, cam in cams_by_frame.items():
        sc.timeline_markers.new(cam.name, frame=frame).camera = cam
    sc.camera = cams_by_frame[min(cams_by_frame)]

def turntable(box, camera, riders, start=3, seconds=8):
    sc = bpy.context.scene
    ctrl = bpy.data.objects.new("camera_turnaround_CTRL", None)
    ctrl.empty_display_type, ctrl.location = "SPHERE", box["floor"]
    collection("RENDER").objects.link(ctrl)
    bpy.context.view_layer.update()
    for o in [camera, *riders]:            # parent, keeping each object where it is
        mw = o.matrix_world.copy()
        o.parent, o.matrix_parent_inverse = ctrl, ctrl.matrix_world.inverted()
        o.matrix_world = mw
    end = start + sc.render.fps * seconds
    for frame, angle in ((start, 0.0), (end, 2 * math.pi)):
        ctrl.rotation_euler = (0, 0, angle)
        ctrl.keyframe_insert("rotation_euler", index=2, frame=frame)
    act = ctrl.animation_data.action
    curves = [fc for layer in act.layers for strip in layer.strips for bag in strip.channelbags for fc in bag.fcurves]
    for fc in curves:
        for kp in fc.keyframe_points: kp.interpolation = "LINEAR"      # constant speed, so the loop has no hitch
    sc.frame_start, sc.frame_end = 1, end - 1                          # frame `end` repeats frame `start`
    return ctrl
```

My version keys the turn from frame 3 with linear keys and stops one frame short of the full circle, so the video
loops cleanly; the course's last frame is 195. Call it as
`turntable(box, cam_turn, [backdrop, *lights.values()])`, then `bind_cameras({1: close, 2: wide, 3: cam_turn})`.
Check with `motion_preview(frames=[3, 51, 99, 147], shading="MATERIAL")`: the character turns by quarter circles
and the lit side stays on the same side of the picture.

### 8. Render settings [19:52:53 to 19:55:20]

```python
# verified in 4.5.16 background
def render_settings(out_dir, res=(1200, 1500), percent=150, samples=200, fps=24, gpu=True):
    sc = bpy.context.scene
    r = sc.render
    r.engine, r.fps, r.resolution_percentage = "CYCLES", fps, percent
    r.resolution_x, r.resolution_y = res
    r.image_settings.file_format = "PNG"
    r.filepath = out_dir.rstrip("/\\") + "/"
    r.use_simplify = False                 # Simplify was on for posing; renders need the real subdivision
    sc.frame_step, sc.cycles.samples, sc.cycles.use_denoising, sc.cycles.device = 1, samples, True, "CPU"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in (("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL") if gpu else ()):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
        except Exception:
            continue
        if any(d.type == kind for d in prefs.devices):
            for d in prefs.devices: d.use = True
            sc.cycles.device = "GPU"
            break
    return {"device": sc.cycles.device, "samples": sc.cycles.samples, "view_transform": sc.view_settings.view_transform}
```

Then render test stills before any animation; the course renders single frames at random points first, because
lighting is a loop of render, adjust, render again, and it shows a past project that took many passes
[19:55:25 to 19:56:50]. Through blender-live: `render_image(camera="camera_closeup", engine="CYCLES", samples=64)`
for quick looks, then full settings. Measure what you see:

```python
# verified in 4.5.16 background
def exposure_report(png_path):
    import numpy as np
    img = bpy.data.images.load(png_path, check_existing=False)
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    rgb = a.reshape(-1, 4)[:, :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return {"mean": round(float(lum.mean()), 3), "clipped_fraction": round(float((rgb.max(axis=1) >= 0.98).mean()), 4),
            "black_fraction": round(float((lum <= 0.02).mean()), 4), "p99": round(float(np.percentile(lum, 99)), 3)}
```

My limits, since the course judges by eye: `clipped_fraction` above 0.005 means something is blown out (lower
the key, or the rim if the clipping is on the edge); `p99` below 0.45 means the character is under-lit. A large
`black_fraction` is normal on a dark backdrop. On my grey test figure the rig above gave `p99` 0.69 to 0.74 with
no clipping in all three shots; real skin and cloth are darker or lighter than that grey, so expect to move power.

The full sequence takes hours; the course leaves it overnight [19:57:00]. Use `headless_run` with a script that
opens the saved file and calls `bpy.ops.render.render(animation=True)`, or render frames 1 and 2 first for the
stills.

### 9. Finishing [19:20:50, 19:57:08 to 20:01:30]

The course does this outside Blender. Stills go into Photoshop as a smart object with the Camera Raw filter:
white balance (temperature, tint), exposure, contrast, highlights, saturation of single colours in the colour
mixer, then film grain and a vignette, all by eye, comparing before and after [19:59:20 to 20:01:10]. The
turntable frames (frame 3 onward) go into DaVinci Resolve as an image sequence, are graded in its colour page and
exported as video [19:57:46]. The reason it gives: grain, slight lens distortion, colour fringing, glow and
vignette are what a real camera adds, and a render without them looks too clean [19:21:10].

The built-in stand-in is the compositor. It covers glow, fringing and vignette; it has no film-grain node.

```python
# verified in 4.5.16 background
def finishing_nodes(bloom=True, dispersion=0.01, vignette=0.35):
    sc = bpy.context.scene
    sc.use_nodes = True
    nt = sc.node_tree                      # 4.5 API; Blender 5.0 moved the scene compositor to a node group
    nt.nodes.clear()
    last = nt.nodes.new("CompositorNodeRLayers").outputs["Image"]
    if bloom:
        g = nt.nodes.new("CompositorNodeGlare")
        g.glare_type = "BLOOM"
        nt.links.new(last, g.inputs["Image"]); last = g.outputs["Image"]
    if dispersion:
        ld = nt.nodes.new("CompositorNodeLensdist")
        ld.inputs["Dispersion"].default_value = dispersion
        nt.links.new(last, ld.inputs["Image"]); last = ld.outputs["Image"]
    if vignette:
        em, bl, mx = (nt.nodes.new("CompositorNode" + t) for t in ("EllipseMask", "Blur", "MixRGB"))
        em.width = em.height = 0.95
        bl.filter_type, bl.use_relative, bl.factor_x, bl.factor_y = "FAST_GAUSS", True, 25, 25
        mx.blend_type, mx.inputs[0].default_value = "MULTIPLY", vignette
        nt.links.new(em.outputs["Mask"], bl.inputs["Image"])
        nt.links.new(last, mx.inputs[1]); nt.links.new(bl.outputs["Image"], mx.inputs[2]); last = mx.outputs["Image"]
    nt.links.new(last, nt.nodes.new("CompositorNodeComposite").inputs["Image"])
```

The course never opens Colour Management. A new 4.5 scene uses the `AgX` view transform with look `None`
(checked); for more contrast set `scene.view_settings.look = "AgX - Medium High Contrast"` (the name is
accepted in 4.5.16) and compare. Turn the turntable PNGs into a video with ffmpeg or Blender's Video Sequencer.

## How the artist works on screen

The lesson uses a split layout: a solid perspective view of the set beside a rendered camera view.
The camera image is the judgment view; the other view exposes the lights and backdrop.
The artist moves objects in Object Mode, rather than sculpting, and waits for the render preview to resolve.
The equivalents below use the functions in the numbered steps; placements are starting points, not measured course coordinates.

### Step 1 — posed subject and bounds

- The posed character is already in the viewport when the lighting demonstration begins
  [qy-wwP-b9HY-14-192150, 19:21:50].
- Rig controls are hidden so the presentation view is not cluttered
  [qy-wwP-b9HY-14-192259, 19:22:59].
- The course does not demonstrate the bounding-box calculation: that is this skill's scale-independent adaptation.
- Reader equivalent: use `character_meshes()` and `character_box(...)` from step 1 on the evaluated pose.
- Exclude widgets and the backdrop; keep the posed figure's actual renderable pieces.
- Keep the skill's Z-up, -Y-facing convention; do not modify reference images.

### Step 2 — frame before lighting

- The artist starts from the existing camera and frames the posed subject before building lights
  [qy-wwP-b9HY-14-192313, 19:23:13].
- Locking the camera to the view lets viewport navigation change the composition
  [qy-wwP-b9HY-14-192339, 19:23:39].
- A portrait frame is used for the demonstration; the subject is framed with room around the body.
- The lens is adjusted while the artist judges facial distortion and composition in camera view
  [qy-wwP-b9HY-14-192458, 19:24:58].
- The camera is unlocked again to avoid accidentally changing the chosen shot
  [qy-wwP-b9HY-14-192556, 19:25:56].
- Reader equivalent: set portrait resolution, call `add_camera`, and inspect with `viewport_capture`.
- Adjust camera position rather than changing the character or any reference to force a fit.

### Step 3 — build the sweep

- Scene world and lights are enabled for the rendered preview before the studio is evaluated
  [qy-wwP-b9HY-14-192639, 19:26:39].
- The artist demonstrates a plane, extrudes its rear edge up, and rounds the floor-wall corner
  [qy-wwP-b9HY-14-192719, 19:27:19].
- Orbiting the view reveals the flat plane's side edge, so this first attempt is discarded
  [qy-wwP-b9HY-14-192733, 19:27:33].
- A filled circle replaces it; the rim is extruded into a cylindrical wall
  [qy-wwP-b9HY-14-192822, 19:28:22].
- The floor-wall edge bevel shows six segments and profile 0.5, followed by smooth shading.
- Judge from the chosen camera, then from the side: neither the horizon nor an edge should intrude.
- Reader equivalent: `make_backdrop(box)` constructs a smooth sweep using the posed height.
- Its radius is a starting proportion; enlarge it if the subject or camera would reveal an edge.

### Step 4 — construct light by light

- The lights are edited in a perspective view while their effect is checked in the rendered camera view.
- The artist first establishes a key on one side above the figure, directed toward the face
  [qy-wwP-b9HY-14-193121, 19:31:21], adjusting its power toward 18.2 W [qy-wwP-b9HY-14-193142, 19:31:44].
- Power is tuned against the bright cheek, not chosen independently of the camera and material.
- The fill is placed on the other side and reduced until it lifts, but does not erase, the key's shadow
  [qy-wwP-b9HY-14-193202, 19:32:02; qy-wwP-b9HY-14-193310, 19:33:10].
- The artist toggles lights for comparison instead of evaluating only their combined result.
- A larger area emitter makes the fill softer; a smaller emitter makes sharper shadows.
- The rim is positioned behind the figure and stretched to reach a long section of the silhouette (19:35:28).
- When it brightens the wall as well as the figure, the backdrop is excluded from that light's receivers.
- Reader equivalent: `three_point_rig(box, backdrop)` and `exclude_from_light` in step 4.
- Inspect the key, fill and rim separately with `render_image`, then together.
- Duplicate the key and fill lower down when the legs need separate illumination; linked data shares their power (19:40:30).
- The warm rim (`#FF8859`, 19:39:38) and the background point light (14.5 W orange, 19:41:58) are adjusted against the clothing and hair, not copied blindly.
- If the key divides the face too starkly, bring it closer to the camera axis before compensating with fill.
- A separate lower fill can wash an unwanted cast shadow off the background.
- Reader equivalent: adjust the light objects' location, aim and energy through `exec_python`, followed by a render.

### Step 5 — a restrained world

- After working with a dark world, the artist enables Poly Haven's `lauter_waterfall` (1K) HDRI and dims its
  Strength (EVs) to about −2.1 to −2.2 EV [qy-wwP-b9HY-14-194424, 19:44:26–19:44:33]; switching back at
  19:44:04–19:44:10 is only an aside on working without the add-on [qy-wwP-b9HY-14-194400].
- Reader equivalent: `set_world` with a legally obtained environment texture, then compare a rendered camera view.
- The HDRI choice and strength are artistic starting points; check that the face still has directional shading.

### Step 6 — compare shots

- The artist switches between the closer portrait and a full-body portrait in the camera view
  [qy-wwP-b9HY-14-194625, 19:46:25].
- The close view emphasizes face and torso; the wide view includes both boots and the backdrop glow.
- The camera data panel shows the same long lens for the two views.
- Reader equivalent: call `add_camera` for `camera_closeup` and `camera_wideshot`; render each.
- Check for unintended cropping independently; lighting judged on one framing may need adjustment on the other.

### Step 7 — turntable and camera markers

- The wide camera is selected as the starting point for a turntable
  [qy-wwP-b9HY-14-194639, 19:46:39].
- A sphere empty is added and named as the turnaround control in the render collection
  [qy-wwP-b9HY-14-194720, 19:47:20].
- Rotating the camera alone exposes the problem: the wall can block the image and the light changes with angle
  [qy-wwP-b9HY-14-194813, 19:48:13].
- The backdrop and lights travel with the camera; rotating the controller now preserves their relation to the shot
  [qy-wwP-b9HY-14-194855, 19:48:55].
- The rotation is cleared before setting up the timeline.
- At frame 1 the artist binds the close-up camera using a timeline marker
  [qy-wwP-b9HY-14-194941, 19:49:41].
- The wide camera is assigned to frame 2 and the turnaround camera to frame 3
  [qy-wwP-b9HY-14-195031, 19:50:31].
- The controller is animated around Z; scrubbing checks both the moving wall and the rendered silhouette
  [qy-wwP-b9HY-14-195227, 19:52:27].
- The timeline start is restored to 1 so the two stills are not omitted
  [qy-wwP-b9HY-14-195240, 19:52:40].
- Reader equivalent: `turntable(...)`, then `bind_cameras(...)` and `motion_preview` at quarter turns.
- The supplied helper deliberately uses linear keys and omits the duplicate loop endpoint; that differs from the lesson.

### Step 8 — render and inspect

- In Output Properties the artist reviews 1200 × 1500 portrait dimensions and chooses 150% scale
  [qy-wwP-b9HY-14-195308, 19:53:08].
- The frame rate is 24 fps, the course end is 195, and step stays at 1
  [qy-wwP-b9HY-14-195321, 19:53:21; qy-wwP-b9HY-14-195336, 19:53:36].
- An output folder is chosen for the image sequence; the individual frames are PNGs.
- Render Properties selects Cycles and GPU where available; the visible render sample count is 200
  [qy-wwP-b9HY-14-195431, 19:54:31; qy-wwP-b9HY-14-195459, 19:54:59].
- The artist scrubs to a side angle and points to Render Image before rendering the complete animation
  [qy-wwP-b9HY-14-195531, 19:55:31].
- Iteration is render, inspect, adjust, and render again; only then is the animation submitted.
- Reader equivalent: `render_settings`, test with `render_image`, and use `headless_run` for the sequence.
- `exposure_report` is this skill's numeric aid, not a measurement demonstrated by the course.

### Step 9 — finish still and sequence

- Numbered frames are shown as thumbnails before the sequence is imported into a video editor
  [qy-wwP-b9HY-14-195733, 19:57:33].
- Resolve recognizes the numbered images as one clip in the Media page
  [qy-wwP-b9HY-14-195811, 19:58:11].
- For the still demonstration the artist converts the image layer to a smart object
  [qy-wwP-b9HY-14-195914, 19:59:14].
- Camera Raw is used to adjust and compare the finish, including grain and vignette
  [qy-wwP-b9HY-14-200103, 20:01:03].
- The filter remains visible under the smart object after returning to the layer view
  [qy-wwP-b9HY-14-200119, 20:01:19].
- This grading example uses a different character; do not treat its appearance as this character's final render.
- Reader equivalent: `finishing_nodes` covers some effects; assemble the sequence in the Video Sequencer or ffmpeg.
- The supplied compositor route is not equivalent to Camera Raw's grain and per-colour controls.

## Shots the course renders

- In the lesson [19:25 to 19:46]: `camera_wideshot`, full body from slightly to one side on a warm dark-brown
  backdrop with an orange glow behind the figure, white key, orange rim; and `camera_closeup`, head to waist from
  further round to the side. Portrait 1200 x 1500. Plus the 8 second turntable.
- Final renders in chapter 15 [20:01:40 to 20:02:10] use a different setup made off-camera, as the course said it
  would [19:44:52]: widescreen 16:9; the character lit in cool blue-violet from the front, a hot orange-red rim on
  hair and limbs, an orange glow on the backdrop fading to near black. Shots seen: an opening silhouette with
  only the backdrop glow on; the full body, centred and small in frame; an extreme close-up of the face filling
  the frame; a detail of the hands against skirt and thighs.
- To get that look from the rig above (my reading of the frames, not the course's numbers): key and fill colour
  about (0.25, 0.35, 1.0), key power down by half, `rim_colour` kept warm, `light_backdrop` raised until the
  glow reads, world strength near 0.05, resolution 1920 x 1080.

## Settings the course uses

| Setting | Value | Where | Time |
|---|---|---|---|
| Resolution | 1200 x 1500 at 150 % (200 % would be about 4K) | Output Properties | 19:23:52, 19:52:55 |
| Frame rate, range, step | 24 fps, 1 to 195, step 1 | Output Properties | 19:50:51, 19:53:36 |
| File format, folder | PNG, a `renders` folder beside the project | Output Properties | 19:53:50 |
| Focal length | 138 mm (says 80 to 90 mm is the usual portrait range) | Camera data > Lens | 19:24:45 |
| Passepartout | 1.0 | Camera data > Viewport Display | 19:37:30 |
| Engine, device | Cycles, GPU if there is one | Render Properties | 19:54:31 |
| Render max samples | 200 (says 200 to 500; default 4096 is too many) | Render > Sampling | 19:54:46 |
| Denoise, noise threshold | on, 0.01 (left at defaults) | Render > Sampling | frame at 19:55:00 |
| Key / fill / rim power | 16.7 W while adjusting, 18.2 W later (13.4 W shared) / 1.36 W / 49.4 W | Light data | 19:31:00, 19:31:44, 19:40:30, 19:33:30, 19:35:28 |
| Area light size | 1 m square, resized by object scale | Light data | 19:31:28 |
| Rim colour | `#FF8859` (HSV 0.047, 0.65, 1.0) | Light data | frame at 19:39:38 |
| Backdrop point light | 14.5 W, radius 0, orange | Light data | frame at 19:41:58 |
| Backdrop material | dark colour, roughness 0.895, specular lowered | Material | 19:36:55 |
| World | Dark background, then Poly Haven `lauter_waterfall` 1K dimmed to about −2.1 to −2.3 EV | World / asset browser | 19:43:11, 19:44:26–19:44:33 |
| Hair while lighting | `Viewport Amount` 0.05, then 0.01; full for checks | hair modifier input | 19:30:35, 19:45:16 |

## Mistakes the course warns about

- Lighting with no reference and no fixed camera [19:10:22, 19:09:57].
- A backdrop made from a plane, whose edge shows from side angles [19:27:40].
- Viewport still set to ignore scene lights and scene world, so new lights seem to do nothing [19:26:11].
- An over-bright key [19:30:52]. A fill as strong as the key, which flattens everything [19:32:02].
- A key so far to the side that the face is cut into a lit half and a black half [19:40:06].
- The rim spilling onto the backdrop [19:35:28]. Selecting the backdrop instead of the light when setting up
  light linking [19:36:05].
- Relying on an HDRI alone when you need control [19:12:00].
- Turntable with only the camera moving: the wall blocks the view and the lighting changes [19:48:13].
- Rendering the animation before test stills [19:55:25]. Skipping finishing [19:21:26].
- Stopping at three-point lighting; it is the starting point [19:18:08].

## What changes for a different character

General: camera before lights; key, fill, rim and their jobs; fill far weaker than key; rim excluded from the
backdrop; world as dim ambient; studio riding on the turntable empty; test stills first.
Specific to this character: the brown backdrop and orange rim were chosen against her brown clothes and pale
hair; pale hair catches a rim strongly. Dark hair or dark skin needs a stronger rim and more fill; glossy
hard-surface parts (armour, visors) show the shape of each area light as a reflection, so make the lights larger
and check the highlights; very wide creatures (wings, tails) need the backdrop radius and the fill size raised,
which `box["width"]` does not drive here, so pass a larger `radius_f`. A long lens suits big stylized heads; a
realistic head can use 85 mm. For a pose that looks to one side, key from that side.

## Exit check

1. `in_frame(camera_wideshot, all character vertices)` is 1.0; `in_frame(camera_closeup, head vertices)` is 1.0.
   Failed if any part of the framed subject is cut off unintentionally.
2. One Cycles still per camera at full settings, each with `exposure_report`: failed if `clipped_fraction` is
   above 0.005 or `p99` is below 0.45 (my limits). Report the numbers.
3. Three more stills of the wide shot with one light group visible each (key only, fill only, rim only). Looked
   at, not measured: key shades the far side without splitting the face; fill alone is dim and shadowless; rim
   alone draws an edge and leaves the backdrop dark.
4. `compare_images` between the close-up render and the lighting reference if one was chosen: report the
   numbers as a guide. Different subjects never match closely; this is not a pass or fail.
5. Turntable: `motion_preview(frames=[3, 51, 99, 147])` shows four quarter turns with the same lighting; the
   markers switch cameras on frames 1, 2 and 3.
6. Likeness, last time: with the rig at rest (frame 1), `outline_match(object="CHARACTER")` against the concept references,
   threshold 0.98, for every view with a real reference; a view with none is `not_run` and reported as looked
   at, not measured. If the concept shows the presentation pose, add a `compare_images` of the posed wide render
   against it as extra information.
7. Files saved: the `.blend`, the stills, and the PNG sequence or a note that the sequence was not rendered.

## Low-poly game route (second course: Nhij Quang, Girl#01)

Second source: Nhij Quang, [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), Blender 4.2.1 LTS, 1 h 15 min, no narration (music only). Everything here was read off the screen: the key-cast overlay, redo panels, modifier panels and status-bar counts, from 157 study sheets; labels are in `annotations/mlnR-Eyazh0/`. Times marked `NQ` point into that video, not the main course. Use this route instead of the sculpt route when the job is a low-poly game character (box/poly modelled, hand-painted, Mixamo-rigged); see "Two routes" in `SKILL.md`. Values that could not be read are listed as not visible, never guessed. Python blocks marked `# not run in Blender` were not executed.

Source: chapter 14 "Import to Godot", 01:13:19 to 01:15:28. Godot 4.3.stable, Forward+ renderer. The Import dock tab exists but is never opened in these frames.

Order of work
1. [NQ 01:13:19 to 01:13:28] The FBX female_char1.fbx and the texture female_char1.png are in res://Asset/3d/ of an existing game project (other files there: anim.fbx, asset.fbx, base_char_3.fbx, building1.fbx, building1.png, tent.fbx, tree_asset.fbx, untitled.fbx). The FBX is instanced in the Root scene as "MainChar": Armature > Skeleton3D > Hair1_001, Hair2_001, Body_001, plus AnimationPlayer. Skeleton3D bones start at mixamorig_Hips. Skeleton3D: Motion Scale 1, Show Rest Only off, Callback Mode Process Idle, Animate Physical Bones On.
2. [NQ 01:13:28 to 01:13:41] Select Body_001 and set the mesh material: Albedo Color white, Albedo Texture set to the character texture, Texture Force sRGB Off, Disable Ambient Off, Disable Fog Off, Rim Enabled On, Rim 0.08, Tint 0.3. Result: textured character in T-pose on the green ground with a cast shadow.
3. [NQ 01:13:48 to 01:14:33] Select AnimationPlayer: Current Animation Armature|Idle, Speed Scale 1, Active On, Deterministic off, Reset on Save On, Root Node MainChar. Play Armature|Idle (6.6667 s) and orbit around it, then switch to Armature|Run (0.7 s) and watch it.
4. [NQ 01:14:39 to 01:15:28] Toggle viewport View options (View Origin and View Grid checked in the menu), watch the in-place run from several angles, then switch back to Armature|Idle for a final look from side and front.
Result: the Mixamo-rigged character is in the game scene with a textured rim-lit material and two working animations.

How it looks on screen
- The character goes into an existing scene (Root with UI, Environment, Camera > CamGimbal > Camera3D > PixelShader, Game > World > Ground) rather than a new test scene.
- The imported FBX node is renamed MainChar.
- Material is edited per mesh in the Inspector, not in a shader.
- Animations are checked with the bottom Animation panel and its dropdown.
- Animation snap is 0.0333 s (30 fps).

Python route
Godot is not driven from Blender. What the agent can do from Python is write the files the Godot project needs; the import and play test happen in Godot (by a person, or by running godot --headless with a GDScript).
```python
# not run in Blender
import shutil
proj = r"C:\path\GodotProject\Asset\3d"
shutil.copy(r"C:\path\female_char1.fbx", proj)
shutil.copy(r"C:\path\female_char1.png", proj)
```
Godot side (GDScript, not Python), matching the values seen:
```gdscript
# not run in Godot
var mat := StandardMaterial3D.new()
mat.albedo_texture = load("res://Asset/3d/female_char1.png")
mat.rim_enabled = true
mat.rim = 0.08
mat.rim_tint = 0.3
$MainChar/Armature/Skeleton3D/Body_001.material_override = mat
$MainChar/AnimationPlayer.play("Armature|Idle")
```
If Godot's FBX import is not available, the same export can be done as glTF with bpy.ops.export_scene.gltf(export_format='GLB', export_animations=True); this is an alternative, not what the video shows.

Settings read on screen
- Godot 4.3.stable, Forward+.
- Files: res://Asset/3d/female_char1.fbx, female_char1.png.
- Scene path: Root > MainChar > Armature > Skeleton3D > Hair1_001, Hair2_001, Body_001; MainChar > AnimationPlayer.
- Skeleton3D: Motion Scale 1, Show Rest Only off, Callback Mode Process Idle, Animate Physical Bones On.
- Body_001 material: Albedo Color white, Albedo Texture set, Texture Force sRGB Off, Disable Ambient Off, Disable Fog Off, Rim Enabled On, Rim 0.08, Rim Tint 0.3.
- AnimationPlayer: Speed Scale 1, Active On, Deterministic off, Reset on Save On, Root Node MainChar.
- Animations: Armature|Idle 6.6667 s, Armature|Run 0.7 s; snap 0.0333 s.

Not visible in the frames
- Godot's Import dock settings for the FBX (FBX importer type, loop modes, root motion, mesh/material extraction).
- Whether the material is a material_override, a surface override or saved as a resource.
- Whether loop was set on Idle and Run (the loop icon state is too small to read reliably).
- Lighting and environment settings (DirectionalLight, WorldEnvironment) were not opened.
- Any in-game play test (the game was not run in these frames).

## Gaps

- Add-ons and outside programs: the Poly Haven asset-browser add-on (paid; the HDRIs themselves are free at
  polyhaven.com), Photoshop Camera Raw (paid) and DaVinci Resolve (free version exists). Built-in routes:
  `set_world` with a bundled or downloaded HDRI; the compositor nodes above; ffmpeg or the Video Sequencer.
- No film-grain node in the 4.5 compositor, and no per-colour saturation mixer as simple as Camera Raw's. Grain
  can be faked with a noise texture mixed in at low strength (not written here).
- The course places every light by eye in a live rendered viewport and gives no positions. The rig here is my
  reconstruction; treat its angles and distances as a first guess and iterate with renders.
- The final cinematic setup of chapter 15 is never shown being built; only the results are seen.
- Whether a picture has the right mood, or leads the eye to the face, cannot be measured with the tools here.
  `exposure_report` only catches blown-out and under-lit renders.
- Exact light positions and most final object scales are not readable; the fill's temporary uniform scale changes
  are visible, but should not be treated as universal values.
- Tested on a grey test figure without hair or skin shading; hair in Cycles needs more samples and time.
