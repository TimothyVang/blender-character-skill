"""Run the anime-clay helpers exactly as written in references/anime-clay-planes.md and check what they make.

  blender -b --factory-startup --python scripts/anime_clay_check.py -- OUT_DIR

Takes the helper code blocks out of references/02-blockout.md (world_co, slice_flat) and
references/anime-clay-planes.md (anime_head_planes, almond_eye, hair_lock), builds a 0.23 m anime head the way the
route describes (sphere, planes, coarse remesh, soften, nose, finer remesh, eyes, locks), checks every mesh is
manifold, and renders grey clay from FRONT, 3/4, LEFT and below into OUT_DIR. Prints one JSON line of results and
exits 1 when a check fails.
"""
import json
import re
import sys
from math import radians
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

REFS = Path(__file__).resolve().parent.parent / "references"


def block_with(md: Path, needle: str) -> str:
    for code in re.findall(r"```python\n(.*?)```", md.read_text(encoding="utf-8"), re.S):
        if needle in code:
            return code
    raise SystemExit(f"no python block with {needle!r} in {md.name}")


def remesh(ob, voxel):
    ob.data.remesh_voxel_size = voxel
    with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob]):
        bpy.ops.object.voxel_remesh()


def relax(ob, iters=3, f=0.5):                     # stand-in for sculpt_relax: Taubin smoothing keeps volume
    bm = bmesh.new(); bm.from_mesh(ob.data)
    for _ in range(iters):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=f, use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=-0.53 * f, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(ob.data); bm.free(); ob.data.update()


def soften(ob, iters=40, f=0.5):                 # stand-in for `smooth` brush strokes: plain Laplacian rounds corners
    bm = bmesh.new(); bm.from_mesh(ob.data)
    for _ in range(iters):
        bmesh.ops.smooth_vert(bm, verts=bm.verts, factor=f, use_axis_x=True, use_axis_y=True, use_axis_z=True)
    bm.to_mesh(ob.data); bm.free(); ob.data.update()


def health(ob):
    dg = bpy.context.evaluated_depsgraph_get(); me = ob.evaluated_get(dg).to_mesh()
    bm = bmesh.new(); bm.from_mesh(me)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    parts, seen = 0, set()
    for v in bm.verts:
        if v.index in seen: continue
        parts += 1; stack = [v]
        while stack:
            x = stack.pop()
            if x.index in seen: continue
            seen.add(x.index); stack += [e.other_vert(x) for e in x.link_edges]
    out = {"faces": len(bm.faces), "non_manifold_edges": nm, "parts": parts}
    bm.free(); ob.evaluated_get(dg).to_mesh_clear(); return out


def render_views(out: Path, target, dist):
    sc = bpy.context.scene; sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading; sh.light = "STUDIO"; sh.color_type = "SINGLE"; sh.single_color = (0.62, 0.62, 0.62)
    sh.show_cavity = True; sh.cavity_type = "BOTH"
    sc.render.resolution_x = sc.render.resolution_y = 640
    cam = bpy.data.objects.new("CAM", bpy.data.cameras.new("CAM")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.lens = 85
    files = []
    for name, az, el in (("front", 0, 0), ("three_quarter", 35, 5), ("left", 90, 0), ("below", 20, -35)):
        d = Vector((0, -dist, 0)); d.rotate(Euler((radians(el), 0, radians(-az))))
        cam.location = Vector(target) + d
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(out / f"anime_clay_{name}.png"); bpy.ops.render.render(write_still=True)
        files.append(sc.render.filepath)
    return files


def main():
    out = Path(sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else ".").resolve(); out.mkdir(parents=True, exist_ok=True)
    g = {"__name__": "helpers"}
    exec(block_with(REFS / "02-blockout.md", "def slice_flat"), g)
    exec(block_with(REFS / "03-sculpt-face.md", "def join_and_fuse"), g)
    exec(block_with(REFS / "anime-clay-planes.md", "def almond_eye"), g)
    for ob in list(bpy.data.objects): bpy.data.objects.remove(ob)

    h, z0 = 0.23, 1.55                                      # head height, head centre height
    bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32, radius=0.5, location=(0, 0, z0))
    head = bpy.context.object; head.name = "BLK_head"
    head.scale = (0.17, 0.20, h); bpy.ops.object.transform_apply(scale=True)
    res = {"planes_moved": g["anime_head_planes"](head)}
    remesh(head, h / 90)                                     # cut, remesh, cut again: the re-cut removes voxel stairs
    g["anime_head_planes"](head); remesh(head, h / 90); res["planes"] = health(head)
    soften(head, 40); relax(head, 3)                         # soften: plane breaks must still read
    w = g["world_co"](head); face_y = float(w[np.abs(w[:, 0]) < 0.005, 1].min())
    nose = g["nose_wedge"]("BLK_nose", bridge=(0, face_y + 0.004, z0 - 0.005),
                           tip=(0, face_y - 0.06 * h, z0 - 0.13 * h), width=0.09 * h)
    g["join_and_fuse"]([head, nose], head, h / 220); soften(head, 25)
    w = g["world_co"](head); eye_x, eye_z = 0.042, z0 - 0.01
    near = (np.abs(w[:, 2] - eye_z) < 0.006) & (np.abs(w[:, 0] - eye_x) < 0.006)
    eye_y = float(w[near, 1].min())
    res["eye_moved"] = g["almond_eye"](head, center=(eye_x, eye_y, eye_z), width=0.24 * h, height=0.16 * h, depth=0.012 * h)
    res["head"] = health(head)
    sk = (0, 0.01, z0 + 0.02)
    def on_skull(x, y, z, bury=0.012 + 0.005):              # root sunk by the lock thickness + 5 mm
        p = np.array((x, y, z)); d = p - np.array(sk); d /= np.linalg.norm(d)
        hit = head.ray_cast(head.matrix_world.inverted() @ Vector(p + d * 0.2), Vector(-d))
        return tuple(np.array(head.matrix_world @ hit[1]) - d * bury)
    locks = [g["hair_lock"](f"HAIR_lock_{i:02d}", on_skull(*root), ctrl, tip, 0.035, 0.012, sk) for i, (root, ctrl, tip) in enumerate([
        ((0.0, -0.06, z0 + 0.10), (0.0, -0.13, z0 + 0.10), (0.01, -0.12, z0 + 0.03)),
        ((0.04, -0.05, z0 + 0.10), (0.07, -0.12, z0 + 0.09), (0.06, -0.11, z0 + 0.01)),
        ((0.07, -0.02, z0 + 0.09), (0.11, -0.06, z0 + 0.04), (0.10, -0.05, z0 - 0.06)),
        ((0.05, 0.05, z0 + 0.11), (0.12, 0.08, z0 + 0.05), (0.10, 0.12, z0 - 0.08)),
    ])]
    res["locks"] = [health(o) for o in locks]
    res["renders"] = render_views(out, (0, 0, z0), 0.95)
    ok = res["planes_moved"] > 0 and res["eye_moved"] > 0 and all(
        x["non_manifold_edges"] == 0 and x["parts"] == 1 for x in [res["planes"], res["head"], *res["locks"]])
    res["ok"] = ok
    print("ANIME_CLAY_CHECK " + json.dumps(res))
    sys.exit(0 if ok else 1)


main()
