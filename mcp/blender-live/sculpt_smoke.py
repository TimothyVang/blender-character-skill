# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.30.0", "pillow>=10"]
# ///
"""End-to-end check of the sculpt and review tools over real MCP stdio, against a live GUI Blender.

  uv run --script mcp/blender-live/sculpt_smoke.py OUT_DIR

Set BLENDER_EXE (and BLENDER_LIVE_PORT if 9876 is taken). Starts Blender with the bridge when none answers.
Writes OUT_DIR/sculpt_smoke.json (`checks`: one boolean per behaviour) and the images. Exit 1 if any check is false.
"""
import asyncio, base64, ctypes, io, json, os, sys
from ctypes import wintypes

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image

out = os.path.abspath(sys.argv[1]); os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = ["reference_setup", "sculpt_begin", "sculpt_strokes", "sculpt_remesh", "sculpt_mask", "mesh_report", "turnaround_sheet",
         "outline_match"]
SPHERE = """
import bpy
if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
for o in list(bpy.data.objects):
    if o.name.startswith('SculptTest') or o.name.startswith('REF_'): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.0)
bpy.context.active_object.name = 'SculptTest'
result = len(bpy.context.active_object.data.vertices)
"""
VIEW_STATE = """
import bpy
a = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')
r = a.spaces.active.region_3d
result = [[round(v, 4) for v in r.view_rotation], r.view_perspective, round(r.view_distance, 3),
          round(a.spaces.active.clip_end, 3), sorted(o.name for o in bpy.context.selected_objects),
          a.spaces.active.shading.light, [o.name for o in bpy.context.view_layer.objects if o.hide_get()]]
"""
U32 = ctypes.windll.user32 if os.name == "nt" else None


def windows_of(pid):
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        p = wintypes.DWORD(); U32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and U32.IsWindowVisible(h): found.append(h)
        return True
    U32.EnumWindows(cb, 0); return found


async def main():
    params = StdioServerParameters(command="uv", args=["run", "--script", os.path.join(HERE, "server.py")],
                                   env={**os.environ, "BLENDER_LIVE_TMP": out})
    report, checks = {}, {}
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        listed = sorted(t.name for t in (await s.list_tools()).tools)
        checks["all_sculpt_tools_listed"] = all(t in listed for t in TOOLS)

        async def run_raw(name, args, img_name=None):
            res = await s.call_tool(name, args)
            meta = next((c.text for c in res.content if c.type == "text"), "")
            try: meta = json.loads(meta)
            except ValueError: pass
            imgs = [c for c in res.content if c.type == "image"]
            if img_name and imgs: open(os.path.join(out, img_name), "wb").write(base64.b64decode(imgs[0].data))
            report[f"{len(report):02d}_{name}"] = {"isError": res.isError, "meta": meta if not isinstance(meta, str) else meta[:800]}
            print(name, "error" if res.isError or (isinstance(meta, dict) and meta.get("status") == "error") else "ok", flush=True)
            return meta, imgs, bool(res.isError)

        async def run(name, args, img_name=None):
            meta, imgs, _ = await run_raw(name, args, img_name)
            return meta, imgs

        async def py(code):
            m, _ = await run("exec_python", {"code": code}); return (m or {}).get("result")

        async def grab(sym=None):
            m, _ = await run("sculpt_strokes", {"object": "SculptTest", "symmetry": sym, "strokes": [
                {"brush": "grab", "radius": 0.3, "points": [[1, 0, 0], [1.3, 0, 0]]}]})
            return m["strokes"][0]

        m, _ = await run("blender_launch", {"wait_s": 120})
        if not m.get("reachable"): raise SystemExit("no bridged Blender: set BLENDER_EXE")

        await py(SPHERE)
        m, _ = await run("sculpt_begin", {"object": "SculptTest", "symmetry": "X"})
        checks["begin_reports_engine_and_symmetry"] = m.get("engine") == "direct" and m.get("symmetry") == "X" and m.get("verts", 0) > 5000

        g = await grab()
        checks["grab_moves_vertices"] = g["moved_verts"] > 0 and 0.05 < g["max_move"] < 0.6
        rep, _ = await run("mesh_report", {"object": "SculptTest"})
        checks["symmetry_mirrors_the_stroke"] = rep["symmetry_error"] < 0.002 and rep["bounds_max"][0] > 1.2 and rep["bounds_min"][0] < -1.2
        checks["mesh_report_symmetry_percentiles"] = (
            isinstance(rep.get("symmetry_p95_error"), (int, float))
            and isinstance(rep.get("symmetry_max_error"), (int, float))
            and 0 <= rep["symmetry_error"] <= rep["symmetry_p95_error"] <= rep["symmetry_max_error"]
        )
        await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": "X"})
        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [
            {"brush": "draw", "radius": 0.3, "strength": 1.0, "points": [[-0.3, -0.95, 0.0], [0.3, -0.95, 0.0]], "snap": True}]})
        rep, _ = await run("mesh_report", {"object": "SculptTest"})
        checks["stroke_over_centre_line_stays_symmetric"] = m["strokes"][0]["moved_verts"] > 0 and rep["symmetry_error"] < 0.002

        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [
            {"brush": "grab", "radius": 0.3, "points": [[5, 5, 5], [5.3, 5, 5]]}]})
        checks["missed_stroke_reports_zero"] = isinstance(m, dict) and m.get("strokes", [{}])[0].get("moved_verts") == 0

        await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": ""})
        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [
            {"brush": "clay_strips", "radius": 0.25, "strength": 1.0, "subtract": True, "points": [[0, -1, -0.3], [0, -1, 0.3]], "snap": True}]})
        radius = await py("import bpy\nfrom mathutils import Vector\no = bpy.data.objects['SculptTest']\n"
                          "near = [v.co.length for v in o.data.vertices if (v.co - Vector((0, -1, 0))).length < 0.15]\n"
                          "result = sum(near) / len(near)")
        checks["subtract_goes_inward"] = m["strokes"][0]["moved_verts"] > 0 and radius < 0.99

        brushes = ("snake_hook", "inflate", "crease", "smooth")
        await py(
            "import bpy\n"
            "if bpy.context.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')\n"
            "for o in list(bpy.data.objects):\n"
            "    if o.name.startswith('SculptTest'): bpy.data.objects.remove(o, do_unlink=True)\n"
            "for i, name in enumerate(('snake_hook', 'inflate', 'crease', 'smooth')):\n"
            "    bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.0, location=(i * 4.0, 0, 0))\n"
            "    bpy.context.active_object.name = f'SculptTest_{name}'\n"
            "result = 4"
        )
        brush_calls = []
        for i, brush in enumerate(brushes):
            ox = i * 4.0
            pre = []
            if brush == "smooth":
                pre = [{"brush": "crease", "radius": 0.2, "strength": 1.0, "points": [[ox, -1, -0.3], [ox, -1, 0.3]], "snap": True}]
            pts = [[ox, -1, 0], [ox, -1.3, 0.1], [ox, -1.6, 0.3]] if brush == "snake_hook" else [[ox, -1, -0.3], [ox, -1, 0.3]]
            brush_calls.append(run("sculpt_strokes", {"object": f"SculptTest_{brush}", "symmetry": "", "strokes": pre + [
                {"brush": brush, "radius": 0.25, "strength": 1.0, "points": pts, "snap": brush != "snake_hook"}]}))
        brush_results = await asyncio.gather(*brush_calls)
        for brush, (m, _) in zip(brushes, brush_results):
            checks[f"{brush}_moves_vertices"] = m["strokes"][-1]["moved_verts"] > 0 and m["strokes"][-1]["max_move"] < 1.0
        await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": ""})
        await grab("")
        m, _ = await run("sculpt_remesh", {"object": "SculptTest", "voxel_size": 0.05})
        rep, _ = await run("mesh_report", {"object": "SculptTest"})
        checks["remesh_changes_vertex_count"] = m.get("verts_after", 0) > 0 and m["verts_after"] != m["verts_before"] \
            and rep["boundary_edges"] == 0 and rep["loose_parts"] == 1
        m, _, remesh_err = await run_raw("sculpt_remesh", {"object": "SculptTest", "voxel_size": 0.0001})
        checks["remesh_refuses_freezing_sizes"] = remesh_err and m.get("status") == "error" and "too small" in m.get("detail", "")

        await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": ""})
        m, _ = await run("sculpt_mask", {"object": "SculptTest", "op": "box", "min": [0.001, -2, -2], "max": [2, 2, 2]})
        g = await grab("")
        checks["box_mask_protects_vertices"] = m["masked_verts"] > 1000 and g["moved_verts"] == 0
        await run("sculpt_mask", {"object": "SculptTest", "op": "clear"})
        g = await grab("")
        checks["clearing_mask_unprotects"] = g["moved_verts"] > 0

        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [{"brush": "nope", "radius": 0.2, "points": [[1, 0, 0]]}]})
        checks["unknown_brush_is_an_error"] = m.get("status") == "error" and "nope" in m.get("detail", "")
        m, _, unknown_err = await run_raw("sculpt_begin", {"object": "NoSuchObject"})
        checks["unknown_object_is_an_error"] = unknown_err and m.get("status") == "error" and "NoSuchObject" in m.get("detail", "")

        if U32:
            pid = await py("import os\nresult = os.getpid()")
            await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": ""})
            for h in windows_of(pid): U32.ShowWindow(h, 6)
            await asyncio.sleep(1.5)
            g = await grab("")
            checks["works_minimized"] = g["moved_verts"] > 0 and 0.05 < g["max_move"] < 0.6
            for h in windows_of(pid): U32.ShowWindow(h, 9)
            await asyncio.sleep(1.0)

        await py(SPHERE)
        red = os.path.join(out, "red_reference.png"); Image.new("RGB", (200, 400), (255, 0, 0)).save(red)
        m, _ = await run("reference_setup", {"images": {"FRONT": red}, "height": 2.0})
        shown = await py("import bpy\ne = bpy.data.objects['REF_FRONT']\nw, h = e.data.size\n"
                         "result = [e.empty_display_size * h / max(w, h), e.hide_select, list(e.location)]")
        checks["reference_setup_creates_empty"] = m.get("created") == ["REF_FRONT"] and abs(shown[0] - 2.0) < 0.02 and shown[1] is True

        before = await py(VIEW_STATE)
        m, imgs = await run("turnaround_sheet", {"object": "SculptTest", "references": {"FRONT": red}, "cell_px": 256}, "turnaround.png")
        after = await py(VIEW_STATE)
        sheet = Image.open(io.BytesIO(base64.b64decode(imgs[0].data))).convert("RGB") if imgs else None
        checks["turnaround_has_all_cells"] = bool(sheet) and m.get("size") == [256 * 7, 256] and len(m.get("cells", [])) == 7 \
            and m["cells"][1] == "FRONT_REFERENCE"
        if sheet:
            full = Image.open(m["path"]).convert("RGB")
            front = full.crop((0, 20, 256, 256)); px = list(front.getdata())
            redness = sum(1 for p in px if p[0] > 200 and p[1] < 60 and p[2] < 60) / len(px)
            grey = front.convert("L"); lo, hi = grey.getextrema()
            checks["turnaround_hides_reference"] = redness < 0.01
            checks["turnaround_shows_the_object"] = hi - lo > 40
            refcell = full.crop((256, 20, 512, 256)); rp = list(refcell.getdata())
            checks["turnaround_shows_reference_cell"] = sum(1 for p in rp if p[0] > 200 and p[1] < 60) / len(rp) > 0.2
        checks["turnaround_restores_view"] = before == after
        orig_clip = await py(
            "import bpy\n"
            "a = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
            "keep = a.spaces.active.clip_end\n"
            "a.spaces.active.clip_end = 500.0\n"
            "result = keep"
        )
        await run("viewport_capture", {"view": "FRONT", "shading": "SOLID"})
        after_clip = await py(
            "import bpy\n"
            "a = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
            "got = a.spaces.active.clip_end\n"
            f"a.spaces.active.clip_end = {float(orig_clip)!r}\n"
            "result = got"
        )
        checks["capture_restores_clip_end"] = abs(after_clip - 500.0) < 1e-3

        from PIL import ImageDraw
        circle = os.path.join(out, "ref_circle.png"); im = Image.new("RGB", (600, 600), (30, 30, 30))
        ImageDraw.Draw(im).ellipse((100, 100, 500, 500), fill=(220, 200, 180)); im.save(circle)
        square = os.path.join(out, "ref_square.png"); im = Image.new("RGBA", (600, 600), (0, 0, 0, 0))
        ImageDraw.Draw(im).rectangle((100, 100, 500, 500), fill=(220, 200, 180, 255)); im.save(square)
        busy_bg = os.path.join(out, "ref_busy.png"); im = Image.new("RGB", (600, 600), (30, 30, 30))
        ImageDraw.Draw(im).rectangle((0, 0, 300, 300), fill=(250, 250, 250)); im.save(busy_bg)
        before = await py(VIEW_STATE)
        m, imgs = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle, "RIGHT": square}}, "outline.png")
        after = await py(VIEW_STATE)
        v = m.get("views", {})
        checks["outline_sphere_matches_circle"] = v.get("FRONT", {}).get("status") == "passed" and v["FRONT"]["iou"] >= 0.98
        checks["outline_sphere_fails_square"] = v.get("RIGHT", {}).get("status") == "failed" and 0.6 < v["RIGHT"]["iou"] < 0.9
        checks["outline_unreferenced_views_are_not_run"] = all(v.get(k, {}).get("status") == "not_run" for k in ("BACK", "LEFT", "TOP")) \
            and m.get("not_run") == 3 and m.get("all_views_passed") is False and m.get("all_measured_passed") is False
        checks["outline_returns_overlay"] = len(imgs) == 1
        checks["outline_restores_view"] = before == after
        m, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle}})
        checks["outline_one_view_never_claims_all_views"] = m.get("all_measured_passed") is True and m.get("all_views_passed") is False
        m, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": busy_bg}})
        checks["outline_refuses_busy_background"] = m.get("status") == "error" and "not plain" in m.get("detail", "")

        # review fixes ------------------------------------------------------------------------------------------
        m, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle}, "views": ["FRONT"]})
        checks["outline_fewer_views_never_claims_all_views"] = m.get("all_measured_passed") is True and m.get("all_views_passed") is False \
            and m.get("views_requested") == ["FRONT"] and len(m.get("unmeasured_of_five", [])) == 4
        m, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle, "SIDE": circle}})
        checks["outline_refuses_unknown_view_name"] = m.get("status") == "error" and "SIDE" in m.get("detail", "")
        m, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle}, "threshold": 0.5})
        checks["outline_refuses_low_threshold"] = m.get("status") == "error" and "threshold" in m.get("detail", "")

        # a cube seen in perspective is not a square; in orthographic it is
        sq_ref = os.path.join(out, "ref_square_plain.png"); im = Image.new("RGB", (600, 600), (30, 30, 30))
        ImageDraw.Draw(im).rectangle((100, 100, 500, 500), fill=(220, 200, 180)); im.save(sq_ref)
        await py("import bpy\nbpy.context.preferences.inputs.use_auto_perspective = False\n"
                 "a = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
                 "a.spaces.active.region_3d.view_perspective = 'PERSP'\n"
                 "bpy.ops.mesh.primitive_cube_add(size=2)\nbpy.context.active_object.name = 'SculptTestCube'")
        m, _ = await run("outline_match", {"object": "SculptTestCube", "references": {"FRONT": sq_ref}})
        await py("import bpy\nbpy.context.preferences.inputs.use_auto_perspective = True")
        checks["outline_is_orthographic_without_auto_perspective"] = m.get("views", {}).get("FRONT", {}).get("iou", 0) >= 0.98

        two = os.path.join(out, "ref_two_circles.png"); im = Image.new("RGB", (900, 500), (30, 30, 30))
        d = ImageDraw.Draw(im); d.ellipse((50, 50, 450, 450), fill=(220, 200, 180)); d.ellipse((450, 50, 850, 450), fill=(220, 200, 180)); im.save(two)
        await py("import bpy\nbpy.data.objects.remove(bpy.data.objects['SculptTestCube'])\n"
                 "bpy.ops.mesh.primitive_uv_sphere_add(segments=128, ring_count=64, radius=1.0, location=(2, 0, 0))\n"
                 "bpy.context.active_object.name = 'SculptTest2'")
        m_one, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": two}})
        m_two, _ = await run("outline_match", {"object": "SculptTest", "also": ["SculptTest2"], "references": {"FRONT": two}})
        checks["outline_also_measures_several_objects"] = m_one["views"]["FRONT"]["status"] == "failed" \
            and m_two["views"]["FRONT"]["iou"] >= 0.97

        await py("import bpy\no = bpy.data.objects['SculptTest2']\nfor x in bpy.context.view_layer.objects: x.select_set(False)\n"
                 "o.select_set(True)\nbpy.data.objects['SculptTest'].select_set(True)\nbpy.context.view_layer.objects.active = o")
        sel_before = await py("import bpy\nresult = sorted(o.name for o in bpy.context.selected_objects)")
        await run("turnaround_sheet", {"object": "SculptTest", "cell_px": 128})
        await run("outline_match", {"object": "SculptTest", "references": {"FRONT": circle}})
        sel_after = await py("import bpy\nresult = [sorted(o.name for o in bpy.context.selected_objects), bpy.context.view_layer.objects.active.name]")
        checks["captures_keep_selection_of_hidden_objects"] = sel_after == [sel_before, "SculptTest2"] and "SculptTest2" in sel_before

        await py("import bpy\nbpy.data.objects['SculptTest2'].scale = (1, 1, 3)")
        m, _ = await run("sculpt_strokes", {"object": "SculptTest2", "strokes": [{"brush": "draw", "radius": 0.2, "points": [[2, -1, 0]], "snap": True}]})
        checks["non_uniform_scale_is_refused"] = m.get("status") == "error" and "non-uniform" in m.get("detail", "")

        await py("import bpy\nfor x in bpy.context.view_layer.objects: x.select_set(False)\n"
                 "o = bpy.data.objects['SculptTest']\no.select_set(True)\nbpy.context.view_layer.objects.active = o\n"
                 "a = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
                 "r = next(r for r in a.regions if r.type == 'WINDOW')\n"
                 "with bpy.context.temp_override(area=a, region=r):\n    bpy.ops.object.mode_set(mode='EDIT')\nresult = bpy.context.mode")
        await run("mesh_report", {"object": "SculptTest"})
        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [{"brush": "draw", "radius": 0.2, "points": [[0, -1, 0]], "snap": True}]})
        mode = await py("import bpy\nresult = bpy.context.mode")
        checks["user_mode_is_restored"] = mode == "EDIT_MESH" and m["strokes"][0]["moved_verts"] > 0
        await py("import bpy\na = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
                 "r = next(r for r in a.regions if r.type == 'WINDOW')\n"
                 "with bpy.context.temp_override(area=a, region=r):\n    bpy.ops.object.mode_set(mode='OBJECT')")

        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [
            {"brush": "draw", "radius": 0.2, "points": [[0, -1, 0]], "snap": True}, {"brush": "grab", "radius": 0.3, "points": [[1, 0, 0]]}]})
        checks["bad_stroke_in_batch_applies_none"] = m.get("status") == "error" and "stroke 1" in m.get("detail", "")
        await py(SPHERE); await run("sculpt_begin", {"object": "SculptTest", "symmetry": ""})
        m, _ = await run("sculpt_strokes", {"object": "SculptTest", "strokes": [
            {"brush": "grab", "radius": 0.3, "snap": True, "points": [[1.05, 0, 0], [1.35, 0, 0]]}]})
        checks["snapped_grab_still_moves"] = m["strokes"][0]["moved_verts"] > 0 and m["strokes"][0]["max_move"] > 0.2

        await py("import bpy\nbpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(3, 0, 0))\nbpy.context.active_object.name = 'SculptTest3'")
        m, imgs = await run("turnaround_sheet", {"object": "SculptTest", "also": ["SculptTest3"], "views": ["FRONT"], "cell_px": 256}, "turnaround_also.png")
        if imgs:
            g = Image.open(m["path"]).convert("L").crop((0, 20, 256, 256)); bbox = g.point(lambda v: 255 if v > 110 else 0).getbbox()
            checks["turnaround_also_shows_both_objects"] = bool(bbox) and (bbox[2] - bbox[0]) > 1.6 * (bbox[3] - bbox[1])
        else:
            checks["turnaround_also_shows_both_objects"] = False

        await py("import bpy\nr = bpy.data.objects.new('SmokeRoot', None); bpy.context.scene.collection.objects.link(r)\n"
                 "for n in ('SculptTest', 'SculptTest3'):\n    o = bpy.data.objects[n]; o.parent = r")
        m, _ = await run("outline_match", {"object": "SmokeRoot", "references": {"FRONT": two}})
        m_also, _ = await run("outline_match", {"object": "SculptTest", "also": ["SculptTest3"], "references": {"FRONT": two}})
        m_alone, _ = await run("outline_match", {"object": "SculptTest", "references": {"FRONT": two}})
        a, b, c = (x.get("views", {}).get("FRONT", {}).get("iou", -1) for x in (m, m_also, m_alone))
        checks["outline_on_empty_root_measures_children"] = a > 0 and abs(a - b) < 0.01 and abs(a - c) > 0.05
        m, imgs = await run("turnaround_sheet", {"object": "SmokeRoot", "views": ["FRONT"], "cell_px": 256})
        if imgs:
            g = Image.open(m["path"]).convert("L").crop((0, 20, 256, 256)); bbox = g.point(lambda v: 255 if v > 110 else 0).getbbox()
            checks["turnaround_on_empty_root_shows_children"] = bool(bbox) and (bbox[2] - bbox[0]) > 1.6 * (bbox[3] - bbox[1])
        else:
            checks["turnaround_on_empty_root_shows_children"] = False
        await py("import bpy\nfor n in ('SculptTest', 'SculptTest3'): bpy.data.objects[n].parent = None\n"
                 "bpy.data.objects.remove(bpy.data.objects['SmokeRoot'])")

        m, _, mask_err = await run_raw("sculpt_mask", {"object": "SculptTest", "op": "box"})
        checks["box_mask_without_bounds_is_refused"] = mask_err and m.get("status") == "error" and "min and max" in m.get("detail", "")
        checks["bridge_errors_set_is_error"] = bool(remesh_err and unknown_err and mask_err)

    json.dump({"tools": listed, "checks": checks, "calls": report}, open(os.path.join(out, "sculpt_smoke.json"), "w"), indent=1)
    bad = [k for k, v in checks.items() if not v]
    print(json.dumps({"passed": len(checks) - len(bad), "of": len(checks), "failed": bad}))
    sys.exit(1 if bad else 0)


asyncio.run(main())
