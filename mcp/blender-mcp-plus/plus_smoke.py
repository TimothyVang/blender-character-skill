"""Live check of blender-mcp-plus over real MCP stdio, against a running Blender with the forked addon on port 9879
and a saved .blend containing CHARACTER open (the Ghibli test character). Prints {"passed", "of", "failed"} and writes
plus_smoke.json into the given folder (default .scratch/plus-smoke).

  uv run --project mcp/blender-mcp-plus python mcp/blender-mcp-plus/plus_smoke.py [out_dir] [reference.png]
"""
import asyncio
import json
import os
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "..", ".scratch", "plus-smoke"))
REF = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "..", ".scratch", "ghibli-character", "refs",
                                                        "front_clean.png")


def body(res):
    texts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
    images = [c for c in res.content if getattr(c, "type", "") == "image"]
    try:
        meta = json.loads(texts[0]) if texts else {}
    except json.JSONDecodeError:
        meta = {"text": texts[0]}
    if isinstance(meta, dict) and "result" in meta and len(meta) == 1:
        meta = meta["result"]
    return meta, images


async def main():
    os.makedirs(OUT, exist_ok=True)
    params = StdioServerParameters(command="uv", args=["run", "--project", HERE, "blender-mcp-plus"],
                                   env={**os.environ})
    checks, calls = {}, {}
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()

        async def run(tool, args):
            t = time.time()
            res = await s.call_tool(tool, args)
            meta, images = body(res)
            calls[tool + f"#{len(calls)}"] = {"seconds": round(time.time() - t, 2), "error": res.isError,
                                              "meta": meta if len(json.dumps(meta, default=str)) < 4000 else "…"}
            return meta, images, res.isError

        names = {t.name for t in (await s.list_tools()).tools}
        checks["upstream_tools_listed"] = {"execute_blender_code", "get_scene_info", "look"} <= names
        checks["plus_tools_listed"] = {"watch", "scene_observe", "scene_act", "relay_arm", "project_paint",
                                       "visual_match", "three_quarter_check", "orbit_check", "sculpt_strokes"} <= names

        m, _, err = await run("execute_blender_code", {"code": "import bpy\nprint(bpy.data.filepath)"})
        checks["upstream_execute_code"] = not err

        m, _, _ = await run("scene_observe", {})
        rev = m.get("revision")
        target = next((e for e in m.get("elements", []) if e["name"] == "Select Hair.Cap"), None)
        m2, _, err = await run("scene_act", {"revision": rev, "id": target["id"], "op": "invoke"})
        m3, _, _ = await run("scene_observe", {})
        now = next((e for e in m3.get("elements", []) if e["name"] == "Select Hair.Cap"), {})
        checks["relay_select_confirmed"] = (not err and m2.get("outcome") == "confirmed"
                                            and "selected" in now.get("states", []) and "active" in now.get("states", []))
        m4, _, err = await run("scene_act", {"revision": rev, "id": target["id"], "op": "invoke"})
        checks["relay_refuses_stale_revision"] = err and "STALE_REVISION" in json.dumps(m4)

        m, images, err = await run("watch", {"reference": REF, "azimuth": 45, "elevation": 0,
                                             "centre": [0.0, -0.02, 1.53], "distance": 1.1, "part": "head"})
        if images:
            import base64
            open(os.path.join(OUT, "watch.png"), "wb").write(base64.b64decode(images[0].data))
        m5, _, _ = await run("execute_blender_code", {"code": (
            "import bpy\nfor a in bpy.context.window.screen.areas:\n"
            "    if a.type=='VIEW_3D': r=a.spaces.active.region_3d; print(round(r.view_distance,3), round(r.view_location.z,3))\n"
            "print([a.type for a in bpy.context.window.screen.areas if a.type=='IMAGE_EDITOR'])")})
        checks["watch_moves_the_viewport_and_shows_reference"] = (not err and len(images) == 1
                                                                 and "1.1 1.53" in json.dumps(m5)
                                                                 and "IMAGE_EDITOR" in json.dumps(m5))

        refs = {v: os.path.join(os.path.dirname(REF), f"{v.lower()}_clean.png") for v in ("FRONT", "LEFT")}
        paint = asyncio.create_task(run("project_paint", {
            "object": "CHARACTER", "references": refs, "tex_size": 1024, "targets": ["body_retopo"],
            "priority_views": ["LEFT", "FRONT"], "palette_view": "FRONT", "power": 14, "priority_cos": 0.15,
            "warp": False, "view_bias": {"LEFT": 300}}))
        waits = []
        await asyncio.sleep(1.0)
        while not paint.done():
            t = time.time()
            await s.call_tool("get_scene_info", {})
            waits.append(round(time.time() - t, 2))
            await asyncio.sleep(1.0)
        pm, _, perr = await paint
        calls["upstream_answers_during_paint"] = waits
        checks["long_paint_does_not_block_other_tools"] = (not perr and pm.get("status") == "painted"
                                                           and len(waits) >= 3 and max(waits) < 3.0)

        m, _, err = await run("visual_match", {"object": "CHARACTER", "references": {"FRONT": refs["FRONT"]},
                                               "views": ["FRONT"]})
        f = (m.get("views") or {}).get("FRONT", {})
        checks["likeness_tools_measure"] = not err and f.get("iou", 0) > 0.9 and "ssim" in f

        m, _, err = await run("relay_arm", {})
        checks["relay_arm"] = not err and m.get("armed") is True

    json.dump({"checks": checks, "calls": calls}, open(os.path.join(OUT, "plus_smoke.json"), "w"), indent=1,
              default=str)
    bad = [k for k, v in checks.items() if not v]
    print(json.dumps({"passed": len(checks) - len(bad), "of": len(checks), "failed": bad}))
    sys.exit(1 if bad else 0)


asyncio.run(main())
