# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.30.0", "pillow>=10"]
# ///
"""Replay the whole speed-sculpt plan (skill/blender-character/scripts/speed_sculpt.py) in a live GUI Blender over
real MCP stdio, and check what each step did.

  uv run --script mcp/blender-live/speed_sculpt_smoke.py OUT_DIR [--height 1.6] [--hair-locks 8]

Set BLENDER_EXE. Uses its own bridge port (BLENDER_LIVE_PORT, default here 9891) so it never touches a Blender you
already have open; it clears only the scene of the Blender it starts. Writes OUT_DIR/speed_sculpt_smoke.json
(`checks`: one boolean per behaviour, `steps`: every call's result), front/side/3-4 captures and the .blend.
Exit 1 if any check is false.
"""
import asyncio, base64, json, os, sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "skill", "blender-character", "scripts"))
import speed_sculpt as ss  # noqa: E402

args = sys.argv[1:]
out = os.path.abspath(args[0]); os.makedirs(out, exist_ok=True)
opt = dict(zip(args[1::2], args[2::2]))
HEIGHT = float(opt.get("--height", 1.6)); LOCKS = int(opt.get("--hair-locks", 8))

CLEAR = """
import bpy
if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections): bpy.data.collections.remove(c)
result = {'objects': len(bpy.data.objects)}
"""
SURVEY = """
import bpy
objs = {o.name: {'type': o.type, 'verts': len(o.data.vertices) if o.type == 'MESH' else 0,
                 'mods': [m.type for m in o.modifiers],
                 'mat': (o.data.materials[0].name if o.type == 'MESH' and o.data.materials else ''),
                 'col': (o.data.color_attributes.active_color.name if o.type == 'MESH' and o.data.color_attributes.active_color else '')}
        for o in bpy.data.objects}
lights = [o.name for o in bpy.data.objects if o.type == 'LIGHT']
from mathutils import Vector
pts = [o.matrix_world @ Vector(c) for o in bpy.data.objects if o.type == 'MESH' for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
lo.x = min(lo.x, -hi.x); hi.x = max(hi.x, -lo.x)                     # mirrored halves are not in bound_box
result = {'objects': objs, 'lights': lights, 'LIGHTS': 'LIGHTS' in bpy.data.collections, 'extent': {'min': list(lo), 'max': list(hi)}}
"""
FRAME = """
import bpy, bmesh
from mathutils import Vector
pts = [o.matrix_world @ Vector(c) for o in bpy.data.objects if o.type == 'MESH' for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
x = max(abs(lo.x), abs(hi.x))
me = bpy.data.meshes.new('YS_frame'); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0); bm.to_mesh(me); bm.free()
o = bpy.data.objects.new('YS_frame', me); bpy.context.scene.collection.objects.link(o)
o.location = (0, (lo.y + hi.y) / 2, (lo.z + hi.z) / 2); o.scale = (2 * x, hi.y - lo.y, hi.z - lo.z)
o.display_type = 'BOUNDS'; o.hide_render = True
result = {'height': hi.z - lo.z}
"""


async def main():
    env = {**os.environ, "BLENDER_LIVE_TMP": out, "BLENDER_LIVE_PORT": os.environ.get("BLENDER_LIVE_PORT", "9891")}
    params = StdioServerParameters(command="uv", args=["run", "--script", os.path.join(HERE, "server.py")], env=env)
    steps, checks = [], {}
    plan = ss.plan(HEIGHT, None, LOCKS)
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()

        async def call(name, a, img=None):
            res = await s.call_tool(name, a)
            meta = next((c.text for c in res.content if c.type == "text"), "")
            try: meta = json.loads(meta)
            except ValueError: pass
            ims = [c for c in res.content if c.type == "image"]
            if img and ims: open(os.path.join(out, img), "wb").write(base64.b64decode(ims[0].data))
            bad = res.isError or (isinstance(meta, dict) and meta.get("status") == "error")
            return meta, bad

        m, _ = await call("blender_launch", {"wait_s": 180})
        if not (isinstance(m, dict) and m.get("reachable")): raise SystemExit(f"no bridged Blender: {m}")
        m, bad = await call("exec_python", {"code": CLEAR})
        checks["scene_cleared"] = not bad and (m.get("result") or {}).get("objects") == 0

        for i, st in enumerate(plan):
            m, bad = await call(st["tool"], st["args"])
            rec = {"i": i, "tool": st["tool"], "why": st["why"], "error": bad,
                   "object": st["args"].get("object", ""),
                   "result": (m.get("result") if st["tool"] == "exec_python" and isinstance(m, dict) else m)}
            if bad: rec["detail"] = str(m)[:1500]
            steps.append(rec)
            print(f"{i:02d} {st['tool']:<15} {'ERROR' if bad else 'ok'}  {st['why'][:60]}", flush=True)

        m, _ = await call("exec_python", {"code": SURVEY})
        survey = m.get("result") or {}
        objs = survey.get("objects", {})
        await call("exec_python", {"code": FRAME})          # a bounds-only box round the whole figure, to frame on
        for v, obj, name in (("FRONT", "YS_frame", "front.png"), ("RIGHT", "YS_frame", "side.png"),
                             ("", "YS_frame", "three_quarter.png"), ("FRONT", "YS_head", "head_front.png")):
            await call("viewport_capture", {"view": v, "frame_object": obj, "shading": "MATERIAL", "max_px": 1024}, name)
        await call("exec_python", {"code": "import bpy; bpy.data.objects.remove(bpy.data.objects['YS_frame']); result=1"})
        await call("exec_python", {"code": f"import bpy; bpy.ops.wm.save_as_mainfile(filepath={os.path.join(out, 'speed_sculpt.blend')!r}); result=1"})

    strokes = [x for x in steps if x["tool"] == "sculpt_strokes"]
    paints = [x for x in steps if x["tool"] == "exec_python" and isinstance(x["result"], dict) and "painted_verts" in x["result"]]
    checks["every_step_ran_without_error"] = not any(x["error"] for x in steps)
    checks["every_stroke_moved_verts"] = bool(strokes) and all(
        all(sr.get("moved_verts", 0) > 0 for sr in (x["result"] or {}).get("strokes", [])) for x in strokes)
    parts = [k for k in objs if k.startswith("YS_")]
    checks["all_parts_exist"] = all(f"YS_{p}" in objs for p in ss.proportions(HEIGHT)) and \
        all(f"YS_hair_lock_{i:02d}" in objs for i in range(LOCKS))
    checks["one_sided_parts_mirrored"] = all("MIRROR" in objs[f"YS_{n}"]["mods"] for n, p in ss.proportions(HEIGHT).items()
                                             if p["side"] == "L" and f"YS_{n}" in objs)
    checks["brow_lash_modifier_stack"] = all(objs.get(f"YS_{n}", {}).get("mods") == ["SUBSURF", "MIRROR", "SHRINKWRAP", "SOLIDIFY"]
                                             for n in ("brow", "lash"))
    checks["top_extracted_from_mask"] = objs.get("YS_top", {}).get("verts", 0) > 0 and "SOLIDIFY" in objs.get("YS_top", {}).get("mods", [])
    checks["paint_reached_verts"] = bool(paints) and all(x["result"]["painted_verts"] > 0 for x in paints)
    checks["toon_material_on_every_part"] = all(objs[k]["mat"] == "YS_toon" for k in parts if objs[k]["type"] == "MESH")
    checks["rim_lights"] = survey.get("LIGHTS") and len(survey.get("lights", [])) == 4
    ext = survey.get("extent") or {"min": [0, 0, 9], "max": [0, 0, 0]}
    checks["figure_stands_at_height"] = abs(ext["min"][2]) < 0.03 * HEIGHT and abs(ext["max"][2] - HEIGHT) < 0.05 * HEIGHT
    checks["captures_written"] = all(os.path.getsize(os.path.join(out, f)) > 10000 for f in ("front.png", "side.png", "three_quarter.png")
                                     if os.path.exists(os.path.join(out, f))) and os.path.exists(os.path.join(out, "front.png"))
    json.dump({"checks": checks, "objects": objs, "steps": steps}, open(os.path.join(out, "speed_sculpt_smoke.json"), "w"), indent=1)
    print(json.dumps(checks, indent=1))
    sys.exit(0 if all(checks.values()) else 1)


asyncio.run(main())
