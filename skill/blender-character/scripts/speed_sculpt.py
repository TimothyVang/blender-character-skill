"""YanSculpts' speed-sculpt method as a replayable plan of blender-live MCP tool calls.

  python <skill>/scripts/speed_sculpt.py [--height 1.6] [--colors hair=#6b4a8a,top=#7a7a3a] > plan.json

Source: five YanSculpts videos studied frame by frame (annotations/FGU0ZwYub-0, umF8UhsczO4, huJs2R7JckM,
Yq9Dzaw2f1k, ainRAUwXMO4 in the source repository; notes in references/speed-sculpt.md). What the method is, as seen:

  * every part is its own low UV sphere: head, neck, torso, each limb segment, ears, eyeballs, hair cap, each hair
    lock. The next part usually starts as a copy of the nearest one (head -> neck -> torso, upper arm -> forearm)
  * parts are never joined; one-sided parts carry a Mirror modifier whose mirror object is the head
  * the head is remeshed once early; after that almost every stroke is Grab at strength ~0.45 to 0.6, with Draw,
    Clay Strips, Crease, Inflate and Snake Hook (hair tips) for the rest
  * eyeballs go in before the lids; brows and lash lines are thin strips with Subdivision + Mirror + Shrinkwrap
    (onto the head) + Solidify, not sculpted
  * clothes: mask the body where the garment sits and extract the masked faces as a shell with thickness
  * colour is painted on the sculpt itself (Sculpt Mode Paint brush, full strength, big radius): a flat base colour
    per part first, then colour blocks, then cleaned-up edges; ink lines are Grease Pencil drawn onto the surface
  * presented with a two-tone toon material (Shader to RGB -> constant Color Ramp mixing two shaders) and several
    coloured Sun/Area lights for rims, in the viewport

Each step is {"tool": <blender-live tool name>, "args": {...}, "why": ..., "source": "[YS ...]"}. Coordinates are
world metres, the character stands on z = 0 and faces -Y (Blender's front view). The proportions are this module's
defaults for a stylised figure about 7 heads tall: the videos do not show numbers for them. Brush strengths come
from the videos; radii and distances are fractions of the head height, chosen here.

This module never imports bpy: the plan is data, and the `exec_python` steps carry their code as text. It runs and
is tested without Blender. The generated code has not been run in Blender in this repository yet.
"""
from __future__ import annotations

import argparse
import json
import sys

BRUSHES = ("grab", "snake_hook", "draw", "clay_strips", "inflate", "crease", "smooth")  # = sculpt_cmds.BRUSHES
PREFIX = "YS_"

# Brush strengths read off the screen in the timelapses (header fields). Grab dominates.
STRENGTH = {"grab": 0.5, "snake_hook": 1.0, "draw": 0.5, "clay_strips": 0.44, "inflate": 0.5, "crease": 0.25,
            "smooth": 0.5}

DEFAULT_COLORS = {"skin": "#f2d3c9", "hair": "#6b4a8a", "eye_white": "#f4f1ec", "iris": "#3b2a24",
                  "lips": "#e58e86", "blush": "#ef9fa6", "top": "#7a7a3a", "ink": "#151515"}


# ------------------------------------------------------------------ proportions
def proportions(height: float = 1.6) -> dict[str, dict]:
    """Part name -> {"center": (x, y, z), "radii": (rx, ry, rz), "side": "L" | "C"} for a figure `height` tall.
    L parts sit at +X and are mirrored across the head's X by a Mirror modifier."""
    if height <= 0:
        raise ValueError("height must be above 0")
    h = height / 7.0                                   # one head
    top = height
    head_c = top - h * 0.5
    p = {
        "head":       ((0, 0, head_c),                   (h * 0.38, h * 0.43, h * 0.5), "C"),
        "neck":       ((0, h * 0.02, top - h * 1.12),     (h * 0.16, h * 0.16, h * 0.28), "C"),
        "torso":      ((0, 0, top - h * 2.0),            (h * 0.62, h * 0.38, h * 0.85), "C"),
        "pelvis":     ((0, 0, top - h * 3.15),           (h * 0.64, h * 0.42, h * 0.5), "C"),
        "ear":        ((h * 0.38, h * 0.05, head_c),      (h * 0.06, h * 0.1, h * 0.16), "L"),
        "eye":        ((h * 0.16, -h * 0.33, head_c - h * 0.04), (h * 0.1, h * 0.1, h * 0.1), "L"),
        "arm_upper":  ((h * 0.85, 0, top - h * 2.0),     (h * 0.17, h * 0.17, h * 0.72), "L"),
        "arm_lower":  ((h * 0.92, 0, top - h * 3.35),    (h * 0.14, h * 0.14, h * 0.65), "L"),
        "hand":       ((h * 0.95, 0, top - h * 4.2),     (h * 0.11, h * 0.06, h * 0.22), "L"),
        "leg_upper":  ((h * 0.32, 0, top - h * 4.15),    (h * 0.26, h * 0.26, h * 0.98), "L"),
        "leg_lower":  ((h * 0.3, h * 0.04, top - h * 5.75), (h * 0.18, h * 0.18, h * 0.88), "L"),
        "foot":       ((h * 0.3, -h * 0.12, h * 0.12),   (h * 0.14, h * 0.32, h * 0.12), "L"),
        "hair_cap":   ((0, h * 0.04, head_c + h * 0.08), (h * 0.41, h * 0.46, h * 0.46), "C"),
    }
    return {k: {"center": tuple(round(v, 5) for v in c), "radii": tuple(round(v, 5) for v in r), "side": s}
            for k, (c, r, s) in p.items()}


def _hex(rgb: str) -> tuple[float, float, float, float]:
    s = rgb.lstrip("#")
    if len(s) != 6:
        raise ValueError(f"colour {rgb!r} must be #rrggbb")
    srgb = [int(s[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]   # colour attributes are linear
    return (round(lin[0], 4), round(lin[1], 4), round(lin[2], 4), 1.0)


# ------------------------------------------------------------------ code generators (text run by exec_python)
def code_add_part(name: str, center, radii, side: str, segments: int = 16, rings: int = 8) -> str:
    """A low UV sphere scaled into the part; one-sided parts get a Mirror modifier across the head."""
    obj = PREFIX + name
    mirror = ""
    if side == "L":
        mirror = (f"m = o.modifiers.new('Mirror', 'MIRROR'); m.use_axis = (True, False, False)\n"
                  f"m.mirror_object = bpy.data.objects.get('{PREFIX}head')\n")
    return (
        "import bpy\n"
        f"old = bpy.data.objects.get('{obj}')\n"
        "if old: bpy.data.objects.remove(old, do_unlink=True)\n"
        f"me = bpy.data.meshes.new('{obj}')\n"
        f"o = bpy.data.objects.new('{obj}', me); bpy.context.scene.collection.objects.link(o)\n"
        "import bmesh\n"
        "bm = bmesh.new()\n"
        f"bmesh.ops.create_uvsphere(bm, u_segments={segments}, v_segments={rings}, radius=1.0)\n"
        f"bmesh.ops.scale(bm, vec={tuple(radii)}, verts=bm.verts)   # radii baked in: object scale stays 1\n"
        "bm.to_mesh(me); bm.free()\n"
        f"o.location = {tuple(center)}\n"
        f"{mirror}"
        "for p in me.polygons: p.use_smooth = True\n"
        f"result = {{'object': '{obj}', 'verts': len(me.vertices)}}\n"
    )


def code_strip_on_surface(name: str, points, width: float, target: str, thickness: float) -> str:
    """Brow or lash line: a one-face-wide strip along `points`, Subdivision + Mirror + Shrinkwrap onto `target` +
    Solidify, the stack seen in both timelapses."""
    pts = [tuple(round(c, 5) for c in p) for p in points]
    obj = PREFIX + name
    return (
        "import bpy, bmesh\n"
        "from mathutils import Vector\n"
        f"old = bpy.data.objects.get('{obj}')\n"
        "if old: bpy.data.objects.remove(old, do_unlink=True)\n"
        f"pts = [Vector(p) for p in {pts}]\n"
        f"w = {width} / 2\n"
        "bm = bmesh.new()\n"
        "up = [bm.verts.new(p + Vector((0, 0, w))) for p in pts]\n"
        "dn = [bm.verts.new(p - Vector((0, 0, w))) for p in pts]\n"
        "for i in range(len(pts) - 1): bm.faces.new((up[i], up[i + 1], dn[i + 1], dn[i]))\n"
        f"me = bpy.data.meshes.new('{obj}'); bm.to_mesh(me); bm.free()\n"
        f"o = bpy.data.objects.new('{obj}', me); bpy.context.scene.collection.objects.link(o)\n"
        "o.modifiers.new('Subdivision', 'SUBSURF').levels = 2\n"
        "m = o.modifiers.new('Mirror', 'MIRROR'); m.use_axis = (True, False, False)\n"
        f"m.mirror_object = bpy.data.objects.get('{PREFIX}head')\n"
        f"s = o.modifiers.new('Shrinkwrap', 'SHRINKWRAP'); s.target = bpy.data.objects.get('{target}')\n"
        "s.wrap_mode = 'OUTSIDE_SURFACE'; s.offset = 0.0005\n"
        f"o.modifiers.new('Solidify', 'SOLIDIFY').thickness = {thickness}\n"
        f"result = {{'object': '{obj}', 'faces': len(me.polygons)}}\n"
    )


def code_extract_masked(source: str, name: str, thickness: float) -> str:
    """Clothes: copy the faces whose verts are all masked (sculpt_mask) into a new shell object with Solidify, the
    mask-and-extract seen in the Summer timelapse. Clears the mask afterwards."""
    obj = PREFIX + name
    return (
        "import bpy, bmesh\n"
        f"src = bpy.data.objects['{source}']\n"
        "me = src.data\n"
        "mask = me.attributes.get('.sculpt_mask')\n"
        "if mask is None: raise RuntimeError('no mask: call sculpt_mask(op=\"box\") first')\n"
        "m = [d.value > 0.5 for d in mask.data]\n"
        "bm = bmesh.new(); bm.from_mesh(me)\n"
        "drop = [f for f in bm.faces if not all(m[v.index] for v in f.verts)]\n"
        "bmesh.ops.delete(bm, geom=drop, context='FACES')\n"
        "if not bm.faces: raise RuntimeError('the mask covers no whole face')\n"
        f"new = bpy.data.meshes.new('{obj}'); bm.to_mesh(new); bm.free()\n"
        f"old = bpy.data.objects.get('{obj}')\n"
        "if old: bpy.data.objects.remove(old, do_unlink=True)\n"
        f"o = bpy.data.objects.new('{obj}', new); bpy.context.scene.collection.objects.link(o)\n"
        "o.matrix_world = src.matrix_world.copy()\n"
        f"s = o.modifiers.new('geometry_extract_solidify', 'SOLIDIFY'); s.thickness = {thickness}; s.offset = 1.0\n"
        "for d in mask.data: d.value = 0.0\n"
        "me.update()\n"
        f"result = {{'object': '{obj}', 'faces': len(new.polygons)}}\n"
    )


def code_paint(obj: str, rgba, center=None, radius: float | None = None, strength: float = 1.0,
               name: str = "Col") -> str:
    """Paint on the sculpt without UVs: fill the whole object (center None) or a soft round dab, into a point colour
    attribute. His Paint brush runs at strength 1.0 with a large radius for fills."""
    where = "None" if center is None else str(tuple(round(c, 5) for c in center))
    return (
        "import bpy\n"
        "from mathutils import Vector\n"
        f"o = bpy.data.objects['{obj}']; me = o.data\n"
        f"a = me.color_attributes.get('{name}') or me.color_attributes.new('{name}', 'FLOAT_COLOR', 'POINT')\n"
        "me.color_attributes.active_color = a\n"
        f"rgba, where, r, k = {tuple(rgba)}, {where}, {radius}, {strength}\n"
        "mw = o.matrix_world; n = 0\n"
        "for v in me.vertices:\n"
        "    if where is None: w = k\n"
        "    else:\n"
        "        d = ((mw @ v.co) - Vector(where)).length\n"
        "        if d >= r: continue\n"
        "        t = 1 - (d / r) ** 2; w = t * t * k\n"
        "    c = a.data[v.index].color\n"
        "    a.data[v.index].color = [c[i] * (1 - w) + rgba[i] * w for i in range(4)]\n"
        "    n += 1\n"
        "me.update()\n"
        f"result = {{'object': '{obj}', 'painted_verts': n}}\n"
    )


def code_toon_material(objs, dark: float = 0.35, name: str = "YS_toon") -> str:
    """Two-tone look of the black-and-white timelapse: Shader to RGB -> constant Color Ramp -> Mix Shader between a
    dark and a light Principled, both coloured by the painted attribute. EEVEE only (Shader to RGB)."""
    return (
        "import bpy\n"
        f"mat = bpy.data.materials.get('{name}') or bpy.data.materials.new('{name}')\n"
        "mat.use_nodes = True; nt = mat.node_tree; nt.nodes.clear()\n"
        "N = lambda t: nt.nodes.new(t)\n"
        "attr = N('ShaderNodeVertexColor'); attr.layer_name = 'Col'\n"
        "probe = N('ShaderNodeBsdfDiffuse'); s2r = N('ShaderNodeShaderToRGB')\n"
        "ramp = N('ShaderNodeValToRGB'); ramp.color_ramp.interpolation = 'CONSTANT'\n"
        "ramp.color_ramp.elements[0].color = (0, 0, 0, 1); ramp.color_ramp.elements[1].position = 0.3\n"
        "dark = N('ShaderNodeBsdfPrincipled'); light = N('ShaderNodeBsdfPrincipled')\n"
        f"mul = N('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs[0].default_value = 1.0\n"
        f"mul.inputs[7].default_value = ({dark}, {dark}, {dark}, 1)\n"
        "mix = N('ShaderNodeMixShader'); out = N('ShaderNodeOutputMaterial')\n"
        "L = nt.links.new\n"
        "L(probe.outputs[0], s2r.inputs[0]); L(s2r.outputs[0], ramp.inputs[0]); L(ramp.outputs[0], mix.inputs[0])\n"
        "L(attr.outputs[0], light.inputs['Base Color']); L(attr.outputs[0], mul.inputs[6])\n"
        "L(mul.outputs[2], dark.inputs['Base Color'])\n"
        "L(dark.outputs[0], mix.inputs[1]); L(light.outputs[0], mix.inputs[2]); L(mix.outputs[0], out.inputs[0])\n"
        f"for n in {list(objs)}:\n"
        "    o = bpy.data.objects.get(n)\n"
        "    if o and o.type == 'MESH':\n"
        "        o.data.materials.clear(); o.data.materials.append(mat)\n"
        "result = {'material': mat.name}\n"
    )


def code_rim_lights(height: float, colors=("#ffd2b0", "#ff9a5a", "#ff6040", "#ffe8d0")) -> str:
    """Several coloured lights in a LIGHTS collection around and behind the figure, for rims (both timelapses use
    up to six Suns/Areas, warm peach to red-orange, presented in the viewport)."""
    cols = [_hex(c)[:3] for c in colors]
    return (
        "import bpy, math\n"
        "coll = bpy.data.collections.get('LIGHTS') or bpy.data.collections.new('LIGHTS')\n"
        "if coll.name not in bpy.context.scene.collection.children: bpy.context.scene.collection.children.link(coll)\n"
        f"cols = {cols}\n"
        "for i, c in enumerate(cols):\n"
        "    name = f'YS_sun_{i}'\n"
        "    L = bpy.data.lights.get(name) or bpy.data.lights.new(name, 'SUN')\n"
        "    L.color = c; L.energy = 3.0 if i == 0 else 2.0\n"
        "    o = bpy.data.objects.get(name) or bpy.data.objects.new(name, L)\n"
        "    if o.name not in coll.objects: coll.objects.link(o)\n"
        "    a = math.radians(-35 + i * (250 / max(1, len(cols) - 1)))   # key from front-left, rims round the back\n"
        f"    o.location = (2 * math.sin(a), 2 * math.cos(a), {height})\n"
        "    o.rotation_euler = (math.radians(60), 0, math.pi - a)\n"
        "result = {'lights': len(cols)}\n"
    )


# ------------------------------------------------------------------ strokes
def check_stroke(stroke: dict) -> None:
    """The same rules sculpt_cmds._check_stroke enforces, so a plan fails here rather than in Blender."""
    brush = stroke.get("brush")
    if brush not in BRUSHES:
        raise ValueError(f"unknown brush {brush!r}")
    pts = stroke.get("points") or []
    if len(pts) < (2 if brush in ("grab", "snake_hook") else 1):
        raise ValueError(f"{brush} needs more points")
    if any(len(p) != 3 for p in pts):
        raise ValueError("every point needs x, y, z")
    if float(stroke.get("radius", 0.1)) <= 0:
        raise ValueError("radius must be above 0")


def _s(brush, pts, radius, strength=None, subtract=False, snap=True):
    st = {"brush": brush, "points": [[round(c, 5) for c in p] for p in pts], "radius": round(radius, 5),
          "strength": STRENGTH[brush] if strength is None else strength, "subtract": subtract, "snap": snap}
    check_stroke(st)
    return st


def face_strokes(parts: dict) -> list[dict]:
    """Head order from the shorts and timelapses: pull the face and jaw down, push the temples, carve the sockets,
    draw the nose, carve and pull up the mouth corners. Grab does the big moves. Symmetry X is set by sculpt_begin."""
    x0, y0, z0 = parts["head"]["center"]
    rx, ry, rz = parts["head"]["radii"]
    front = y0 - ry
    eye = parts["eye"]["center"]
    return [
        _s("grab", [(0, front, z0 - rz * 0.3), (0, front - ry * 0.12, z0 - rz * 0.75)], rz * 0.7),    # face down
        _s("grab", [(rx * 0.55, front + ry * 0.4, z0 - rz * 0.6), (rx * 0.42, front + ry * 0.45, z0 - rz * 0.85)], rz * 0.45),  # jaw
        _s("grab", [(rx * 0.95, y0 - ry * 0.3, z0 + rz * 0.15), (rx * 0.82, y0 - ry * 0.3, z0 + rz * 0.15)], rz * 0.35),  # temples in
        _s("crease", [(eye[0], front + ry * 0.05, eye[2])], rx * 0.3, subtract=False),                   # socket
        _s("draw", [(eye[0], front + ry * 0.05, eye[2])], rx * 0.28, subtract=True),                     # deepen socket
        _s("draw", [(0, front, z0 - rz * 0.1), (0, front, z0 - rz * 0.32)], rx * 0.14),                   # nose ridge
        _s("clay_strips", [(0, front, z0 - rz * 0.33)], rx * 0.12),                                       # nose tip
        _s("crease", [(-rx * 0.22, front, z0 - rz * 0.5), (rx * 0.22, front, z0 - rz * 0.5)], rx * 0.08),  # mouth line
        _s("grab", [(rx * 0.22, front, z0 - rz * 0.5), (rx * 0.24, front, z0 - rz * 0.47)], rx * 0.08),    # corners up
        _s("clay_strips", [(-rx * 0.15, front, z0 - rz * 0.56), (rx * 0.15, front, z0 - rz * 0.56)], rx * 0.07),  # lower lip
    ]


def lid_strokes(parts: dict) -> list[dict]:
    """After the eyeballs are placed: build the upper lid over the ball and a lower lid under it."""
    ex, ey, ez = parts["eye"]["center"]
    r = parts["eye"]["radii"][0]
    return [
        _s("clay_strips", [(ex - r, ey - r * 0.6, ez + r * 0.7), (ex + r, ey - r * 0.6, ez + r * 0.75)], r * 0.6),
        _s("draw", [(ex - r * 0.8, ey - r * 0.5, ez - r * 0.85), (ex + r * 0.8, ey - r * 0.5, ez - r * 0.8)], r * 0.45),
    ]


def body_strokes(parts: dict) -> dict[str, list[dict]]:
    """Per part: Grab-led shaping (waist in, chest and hips out, shoulders), as he does on each separate sphere."""
    t = parts["torso"]; tx, ty, tz = t["center"]; trx, try_, trz = t["radii"]
    p = parts["pelvis"]; px, py, pz = p["center"]; prx, pry, prz = p["radii"]
    return {
        "torso": [
            _s("grab", [(trx, ty, tz - trz * 0.55), (trx * 0.78, ty, tz - trz * 0.55)], trz * 0.5),     # waist in
            _s("grab", [(trx * 0.9, ty, tz + trz * 0.6), (trx * 1.02, ty, tz + trz * 0.72)], trz * 0.4),  # shoulder
            _s("clay_strips", [(trx * 0.35, ty - try_, tz + trz * 0.15)], trz * 0.3),                    # chest
            _s("draw", [(trx * 0.3, ty - try_ * 0.9, tz + trz * 0.62), (trx * 0.8, ty - try_ * 0.7, tz + trz * 0.7)],
               trz * 0.08),                                                                              # clavicle
        ],
        "pelvis": [
            _s("grab", [(prx, py, pz), (prx * 1.08, py, pz - prz * 0.1)], prz * 0.6),                    # hip out
            _s("inflate", [(prx * 0.45, py + pry, pz - prz * 0.2)], prz * 0.5),                          # seat
        ],
    }


def hair_lock_steps(parts: dict, n_locks: int = 8) -> list[dict]:
    """Hair: the cap is a sphere; each lock is a small separate sphere at the hairline pulled out with Snake Hook
    (strength 1.0), as in the Summer timelapse (Sphere.0xx per lock)."""
    hx, hy, hz = parts["head"]["center"]; hrx, hry, hrz = parts["head"]["radii"]
    steps = []
    for i in range(n_locks):
        side = 1 if i % 2 == 0 else -1
        k = i // 2
        x = side * hrx * (0.15 + 0.22 * k)
        root = (x, hy - hry * 0.85 + k * hry * 0.25, hz + hrz * 0.55)
        tip = (x * 1.15, root[1] - hry * 0.05, hz - hrz * (0.2 + 0.18 * k))
        name = f"hair_lock_{i:02d}"
        steps.append(_step("exec_python", {"code": code_add_part(name, root, (hrx * 0.12,) * 3, "C", 12, 6)},
                           f"lock {i}: a small sphere at the hairline", "[YS umF8UhsczO4 00:05 to 00:11]"))
        steps.append(_step("sculpt_begin", {"object": PREFIX + name, "symmetry": ""}, "sculpt the lock on its own",
                           "[YS umF8UhsczO4]"))
        steps.append(_step("sculpt_strokes", {"object": PREFIX + name,
                                              "strokes": [_s("snake_hook", [root, tip], hrx * 0.13, snap=False)]},
                           "pull the lock down along the hair flow", "[YS umF8UhsczO4, Snake Hook 1.000]"))
    return steps


# ------------------------------------------------------------------ plan
def _step(tool: str, args: dict, why: str, source: str) -> dict:
    return {"tool": tool, "args": args, "why": why, "source": source}


def plan(height: float = 1.6, colors: dict | None = None, hair_locks: int = 8) -> list[dict]:
    """The whole speed-sculpt, in his order: head first to likeness, eyes, body parts, brows/lashes, hair, clothes,
    paint, toon material, lights."""
    parts = proportions(height)
    col = {**DEFAULT_COLORS, **(colors or {})}
    h = height / 7.0
    steps: list[dict] = []
    add = lambda name, why, src: steps.append(_step("exec_python", {"code": code_add_part(
        name, parts[name]["center"], parts[name]["radii"], parts[name]["side"])}, why, src))

    add("head", "start with a sphere for the head", "[YS all videos 00:00]")
    steps.append(_step("sculpt_remesh", {"object": PREFIX + "head", "voxel_size": round(h / 60, 5)},
                       "one remesh early so the head can take detail", "[YS umF8UhsczO4 00:00:25]"))
    steps.append(_step("sculpt_begin", {"object": PREFIX + "head", "symmetry": "X"}, "symmetric face", "[YS]"))
    steps.append(_step("sculpt_strokes", {"object": PREFIX + "head", "strokes": face_strokes(parts)},
                       "pull the face down, temples in, sockets, nose, mouth", "[YS FGU0ZwYub-0 00:00 to 00:07]"))
    add("ear", "ear as its own sphere, mirrored across the head", "[YS huJs2R7JckM, umF8UhsczO4]")
    add("eye", "eyeballs go in before the lids", "[YS FGU0ZwYub-0 00:07]")
    steps.append(_step("sculpt_strokes", {"object": PREFIX + "head", "strokes": lid_strokes(parts)},
                       "lids wrap the placed eyeball", "[YS FGU0ZwYub-0 00:09]"))
    for name, src in (("neck", "[YS Yq9Dzaw2f1k 00:13: duplicate the head for the neck]"),
                      ("torso", "[YS ainRAUwXMO4: duplicate the neck for the torso]"),
                      ("pelvis", "[YS ainRAUwXMO4: pull it down for the lower torso]"),
                      ("arm_upper", "[YS ainRAUwXMO4: a sphere for the arm]"),
                      ("arm_lower", "[YS ainRAUwXMO4: duplicate the upper arm for the forearm]"),
                      ("hand", "[YS]"), ("leg_upper", "[YS FGU0ZwYub-0 00:13]"),
                      ("leg_lower", "[YS FGU0ZwYub-0 00:14: duplicate for the rest of the leg]"),
                      ("foot", "[YS FGU0ZwYub-0 00:20]")):
        add(name, f"{name}: its own sphere, never joined", src)
    for name, strokes in body_strokes(parts).items():
        steps.append(_step("sculpt_begin", {"object": PREFIX + name, "symmetry": "X"}, f"sculpt {name}", "[YS]"))
        steps.append(_step("sculpt_strokes", {"object": PREFIX + name, "strokes": strokes},
                           "Grab-led shaping: waist, shoulders, chest, hips", "[YS Grab ~0.45 to 0.6]"))
    ex, ey, ez = parts["eye"]["center"]; er = parts["eye"]["radii"][0]
    brow = [(ex - er * 1.3, ey - er * 0.2, ez + er * 1.9), (ex, ey - er * 0.4, ez + er * 2.2), (ex + er * 1.4, ey, ez + er * 1.8)]
    lash = [(ex - er * 1.05, ey - er * 0.75, ez + er * 0.6), (ex, ey - er * 0.95, ez + er * 0.85), (ex + er * 1.1, ey - er * 0.6, ez + er * 0.5)]
    steps.append(_step("exec_python", {"code": code_strip_on_surface("brow", brow, er * 0.35, PREFIX + "head", er * 0.08)},
                       "brow: strip + Subdivision + Mirror + Shrinkwrap + Solidify", "[YS huJs2R7JckM, umF8UhsczO4]"))
    steps.append(_step("exec_python", {"code": code_strip_on_surface("lash", lash, er * 0.2, PREFIX + "head", er * 0.06)},
                       "lash line: the same strip stack along the upper lid", "[YS huJs2R7JckM 00:05]"))
    add("hair_cap", "hair cap: a sphere over the skull", "[YS FGU0ZwYub-0 00:26]")
    steps += hair_lock_steps(parts, hair_locks)
    t = parts["torso"]; (tx, ty, tz), (trx, try_, trz) = t["center"], t["radii"]
    steps.append(_step("sculpt_mask", {"object": PREFIX + "torso", "op": "box",
                                       "min": [-trx * 1.1, -try_ * 1.1, tz - trz * 0.6],
                                       "max": [trx * 1.1, try_ * 1.1, tz + trz * 0.55]},
                       "mask the torso where the top sits", "[YS umF8UhsczO4 00:11]"))
    steps.append(_step("exec_python", {"code": code_extract_masked(PREFIX + "torso", "top", round(h * 0.02, 5))},
                       "extract the masked faces as the top, with thickness", "[YS umF8UhsczO4 00:11 to 00:12]"))
    skin = [n for n in ("head", "ear", "neck", "torso", "pelvis", "arm_upper", "arm_lower", "hand", "leg_upper",
                        "leg_lower", "foot")]
    for n in skin:
        steps.append(_step("exec_python", {"code": code_paint(PREFIX + n, _hex(col["skin"]))},
                           f"base colour fill on {n}", "[YS shorts: base colour per part first, strength 1.0]"))
    for n, c in (("hair_cap", "hair"), ("eye", "eye_white"), ("brow", "hair"), ("lash", "ink"), ("top", "top")):
        steps.append(_step("exec_python", {"code": code_paint(PREFIX + n, _hex(col[c]))}, f"base colour on {n}",
                           "[YS umF8UhsczO4: hair, top, skin]"))
    for i in range(hair_locks):
        steps.append(_step("exec_python", {"code": code_paint(f"{PREFIX}hair_lock_{i:02d}", _hex(col["hair"]))},
                           "hair colour", "[YS]"))
    hx, hy, hz = parts["head"]["center"]; hrx, hry, hrz = parts["head"]["radii"]
    front = hy - hry
    steps.append(_step("exec_python", {"code": code_paint(PREFIX + "eye", _hex(col["iris"]), (ex, ey - er, ez), er * 0.55)},
                       "iris colour on the front of the eyeball", "[YS FGU0ZwYub-0 00:39 to 00:41]"))
    steps.append(_step("exec_python", {"code": code_paint(PREFIX + "head", _hex(col["lips"]), (0, front, hz - hrz * 0.53), hrx * 0.2)},
                       "lips", "[YS umF8UhsczO4 00:15:31]"))
    for sx in (1, -1):
        steps.append(_step("exec_python", {"code": code_paint(PREFIX + "head", _hex(col["blush"]),
                                                              (sx * hrx * 0.45, front + hry * 0.15, hz - hrz * 0.3), hrx * 0.25, 0.6)},
                           "cheek blush, soft", "[YS umF8UhsczO4 cheeks after lips]"))
    meshes = [PREFIX + n for n in skin + ["hair_cap", "eye", "brow", "lash", "top"]] + \
             [f"{PREFIX}hair_lock_{i:02d}" for i in range(hair_locks)]
    steps.append(_step("exec_python", {"code": code_toon_material(meshes)},
                       "two-tone toon material driven by the painted colour", "[YS huJs2R7JckM skin.001]"))
    steps.append(_step("exec_python", {"code": code_rim_lights(height)},
                       "coloured suns for rims, presented in the viewport", "[YS umF8UhsczO4, huJs2R7JckM LIGHTS]"))
    return steps


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--height", type=float, default=1.6)
    ap.add_argument("--hair-locks", type=int, default=8)
    ap.add_argument("--colors", default="", help="part=#rrggbb,... (skin, hair, eye_white, iris, lips, blush, top, ink)")
    a = ap.parse_args(argv)
    colors = dict(kv.split("=", 1) for kv in a.colors.split(",") if kv)
    json.dump(plan(a.height, colors, a.hair_locks), sys.stdout, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
