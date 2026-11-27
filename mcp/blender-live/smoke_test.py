# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.30.0", "pillow>=10"]
# ///
"""End-to-end check of blender-live over real MCP stdio: launch Blender with the bridge, call every tool, and assert
each behaviour features.json claims.

  uv run --script tools/blender-live/smoke_test.py BLEND_FILE CAMERA REFERENCE_PNG OUT_DIR

Writes OUT_DIR/smoke.json (each call: isError, image count, meta; `checks`: one boolean per claimed behaviour;
`missing_tools`) and the returned images. Exit 1 if any check is false.
"""
import asyncio, base64, ctypes, io, json, os, sys
from ctypes import wintypes

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from PIL import Image, ImageStat

blend, camera, ref, out = sys.argv[1:5]; os.makedirs(out, exist_ok=True)
HERE = os.path.dirname(os.path.abspath(__file__))
U32 = ctypes.windll.user32


def windows_of(pid):
    """Top-level visible windows of one process (this smoke test's own Blender only)."""
    found = []
    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        p = wintypes.DWORD(); U32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and U32.IsWindowVisible(h): found.append(h)
        return True
    U32.EnumWindows(cb, 0); return found


def busy(img_b64):
    """An image with real content: grey standard deviation above 8 (a blank or 1x1 capture fails)."""
    im = Image.open(io.BytesIO(base64.b64decode(img_b64))).convert("L")
    return im.size[0] > 64 and ImageStat.Stat(im).stddev[0] > 8


async def main():
    params = StdioServerParameters(command="uv", args=["run", "--script", os.path.join(HERE, "server.py")])
    report, checks = {}, {}
    async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
        await s.initialize()
        report["tools"] = sorted(t.name for t in (await s.list_tools()).tools)

        async def run(name, args, img_name=None):
            res = await s.call_tool(name, args)
            meta = next((c.text for c in res.content if c.type == "text"), "")
            try: meta = json.loads(meta)
            except ValueError: pass
            imgs = [c for c in res.content if c.type == "image"]
            if img_name and imgs:
                stem, ext = os.path.splitext(img_name)
                for i, im in enumerate(imgs):
                    open(os.path.join(out, img_name if i == 0 else f"{stem}_{i}{ext}"), "wb").write(base64.b64decode(im.data))
            report[name if name not in report else f"{name}_{len(report)}"] = {"isError": res.isError, "images": len(imgs),
                                                                               "meta": meta if not isinstance(meta, str) else meta[:600]}
            print(name, "error" if res.isError else "ok", flush=True)
            return meta, imgs, res.isError

        async def py(code):
            m, _, _ = await run("exec_python", {"code": code}); return (m or {}).get("result")

        m, _, e = await run("blender_launch", {"blend_path": blend, "wait_s": 120})
        checks["launch_starts_blender_on_file"] = not e and m.get("reachable") is True and os.path.samefile(m.get("file"), blend)
        m, _, e = await run("blender_launch", {"blend_path": blend, "wait_s": 30})
        checks["launch_is_noop_when_bridge_answers"] = not e and m.get("started") is False and m.get("reachable") is True
        m, _, e = await run("blender_status", {})
        checks["status_fields"] = not e and all(k in m for k in ("blender", "file", "dirty", "scene", "frame_range", "camera", "objects"))
        m, _, e = await run("scene_tree", {"depth": 1, "max_objects": 40})
        checks["scene_tree_lists_objects"] = not e and isinstance(m, dict) and len(json.dumps(m)) > 200
        m, _, e = await run("object_info", {"name": camera})
        checks["object_info_camera"] = not e and m.get("type") == "CAMERA" and all(k in m for k in ("location", "bounds_min", "lens"))
        m, _, e = await run("exec_python", {"code": "import bpy\nresult = {'objects': len(bpy.data.objects)}\nprint('hello from blender')"})
        checks["exec_returns_result_and_stdout"] = not e and (m.get("result") or {}).get("objects", 0) > 0 and "hello from blender" in m.get("stdout", "")
        m, imgs, e = await run("viewport_capture", {"camera": camera, "shading": "MATERIAL", "redraws": 12}, "viewport_camera.png")
        checks["capture_through_camera"] = not e and m.get("perspective") == "CAMERA" and len(imgs) == 1 and busy(imgs[0].data)
        m, imgs, e = await run("exec_python", {"code": "import bpy\nbpy.data.objects['TowerM'].hide_viewport = True\nresult = 'hid TowerM'",
                                               "capture": True}, "edit_and_see.png")
        checks["exec_capture_edit_and_see"] = not e and len(imgs) == 1 and busy(imgs[0].data)
        await py("import bpy\nbpy.data.objects['TowerM'].hide_viewport = False\nresult = 'restored'")
        m, imgs, e = await run("viewport_capture", {"view": "TOP", "shading": "SOLID"}, "viewport_top.png")
        checks["capture_axis_view"] = not e and m.get("perspective") in ("ORTHO", "PERSP") and len(imgs) == 1 and busy(imgs[0].data)
        overlays = await py("import bpy\na = next(a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'VIEW_3D')\n"
                            "result = a.spaces.active.overlay.show_overlays")
        checks["capture_restores_overlay_setting"] = overlays is True

        # minimized window: this smoke test's own Blender (its pid comes from the bridge), never another process
        pid = await py("import os\nresult = os.getpid()")
        hw = windows_of(int(pid)) if pid else []
        for h in hw: U32.ShowWindow(h, 6)                                    # SW_MINIMIZE
        await asyncio.sleep(1.0)
        minimized = bool(hw) and all(U32.IsIconic(h) for h in hw)
        m, imgs, e = await run("viewport_capture", {"camera": camera, "shading": "SOLID"}, "viewport_minimized.png")
        checks["capture_works_minimized"] = minimized and not e and len(imgs) == 1 and busy(imgs[0].data)
        for h in hw: U32.ShowWindow(h, 9)                                    # SW_RESTORE

        before = await py("import bpy\nr = bpy.context.scene.render\nresult = [r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, bpy.context.scene.camera.name]")
        m, imgs, e = await run("render_image", {"camera": camera, "engine": "BLENDER_WORKBENCH", "width": 672, "height": 448}, "render.png")
        after = await py("import bpy\nr = bpy.context.scene.render\nresult = [r.engine, r.resolution_x, r.resolution_y, r.resolution_percentage, r.filepath, bpy.context.scene.camera.name]")
        checks["render_returns_image"] = not e and len(imgs) == 1 and busy(imgs[0].data) and m.get("size") == [672, 448]
        checks["render_restores_settings"] = before is not None and before == after
        m, imgs, e = await run("compare_images", {"reference": ref, "candidate": os.path.join(out, "render.png")}, "compare.png")
        checks["compare_metrics_and_image"] = not e and all(k in m for k in ("exact_pct", "within8_pct", "mean_abs_error", "ssim")) and len(imgs) == 1
        m, _, e = await run("set_frame", {"frame": 2})
        checks["set_frame"] = not e and m.get("frame") == 2 and await py("import bpy\nresult = bpy.context.scene.frame_current") == 2
        m, imgs, e = await run("motion_preview", {"camera": "FlyCam", "frames": [1, 60, 120], "shading": "SOLID", "width": 480}, "motion_preview.png")
        distinct = len({im.data for im in imgs}) == 3
        checks["motion_preview_ordered_frames"] = not e and m.get("frames") == [1, 60, 120] and len(imgs) == 3 and distinct and all(busy(i.data) for i in imgs)
        checks["motion_preview_restores_frame"] = await py("import bpy\nresult = bpy.context.scene.frame_current") == 2
        copy = os.path.abspath(os.path.join(HERE, "..", "..", ".scratch", "tmp", "blender-live-smoke-copy.blend"))
        os.makedirs(os.path.dirname(copy), exist_ok=True)
        m, _, e = await run("save_file", {"filepath": copy})
        st, _, _ = await run("blender_status", {})
        checks["save_as_copy_switches_session"] = not e and os.path.exists(copy) and os.path.samefile(st.get("file"), copy)
        m, _, e = await run("open_file", {"filepath": blend})
        checks["open_file_switches_back"] = not e and os.path.samefile(m.get("file"), blend)
        capdir = os.path.dirname(report["viewport_capture"]["meta"].get("path", ""))
        root = os.path.abspath(os.path.join(HERE, "..", ".."))
        checks["captures_inside_workspace"] = bool(capdir) and os.path.abspath(capdir).startswith(os.path.join(root, ".scratch", "tmp", "blender-live"))
        m, _, e = await run("headless_run", {"script": os.path.join(HERE, "smoke_headless.py"), "args": ["--n", "3"]})
        checks["headless_exit_code_and_markers"] = not e and m.get("exit_code") == 0 and any(x.startswith("HEADLESS ") for x in m.get("markers", []))
        for f in (copy, copy + "1"):
            if os.path.exists(f): os.remove(f)
    report["missing_tools"] = sorted(set(report["tools"]) - {k.rsplit("_", 1)[0] if k.rsplit("_", 1)[-1].isdigit() else k
                                                             for k in report if k not in ("tools", "checks", "missing_tools")})
    report["checks"] = checks
    json.dump(report, open(os.path.join(out, "smoke.json"), "w"), indent=1, default=str)
    print("CHECKS " + json.dumps(checks))
    sys.exit(0 if all(checks.values()) and not report["missing_tools"] else 1)

asyncio.run(main())
