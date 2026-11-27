# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.30.0", "pillow>=10", "numpy>=1.26"]
# ///
"""blender-live MCP server: drive a running GUI Blender (through bridge.py) and headless Blender jobs.

Start from the workspace root (see features.json). The GUI side is tools/blender-live/bridge.py, which
blender_launch starts for you. Images come back as MCP image content (PNG), downscaled to max_px.
"""
import base64, io, json, os, socket, subprocess, sys, time
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outline

HOST, PORT = "127.0.0.1", int(os.environ.get("BLENDER_LIVE_PORT", "9876"))
TOKEN = os.environ.get("BLENDER_LIVE_TOKEN", "")
HERE = os.path.dirname(os.path.abspath(__file__))
import shutil
_LOCAL = os.path.join(HERE, "blender_exe.txt")                     # optional, git-ignored: one line, the path to blender
BLENDER = (os.environ.get("BLENDER_EXE") or (open(_LOCAL, encoding="utf-8").read().strip() if os.path.isfile(_LOCAL) else "")
           or shutil.which("blender") or "blender")
mcp = FastMCP("blender-live", instructions=(
    "Drive the user's open Blender. blender_status first; blender_launch opens a .blend with the bridge if none is "
    "reachable. Inspect with scene_tree/object_info, act with exec_python (set `result`), see with viewport_capture "
    "or render_image. Edits are live and unsaved until save_file. headless_run runs a script in background Blender "
    "and reports exit code and RESULT-style marker lines. To sculpt: reference_setup places concept pictures, "
    "sculpt_begin picks the mesh and symmetry, sculpt_strokes moves the surface and reports how many vertices moved, "
    "sculpt_remesh evens the faces, sculpt_mask protects areas, mesh_report gives health numbers, and "
    "turnaround_sheet shows every side next to the references."))


def call(cmd: str, timeout: float = 300, **args) -> dict:
    payload = {"cmd": cmd, "timeout": timeout, **args}
    if TOKEN:
        payload["token"] = TOKEN
    with socket.create_connection((HOST, PORT), timeout=10) as s:
        s.settimeout(timeout + 10)
        s.sendall(json.dumps(payload).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(1 << 20)
            if not chunk: break
            buf += chunk
    rep = json.loads(buf)
    if not rep.get("ok"): raise RuntimeError(rep.get("error", "bridge error") + "\n" + rep.get("trace", "")[-1500:])
    return rep


def image(b64: str, max_px: int) -> ImageContent:
    im = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    if max(im.size) > max_px: im.thumbnail((max_px, max_px))
    out = io.BytesIO(); im.save(out, "PNG")
    return ImageContent(type="image", mimeType="image/png", data=base64.b64encode(out.getvalue()).decode())


def reply(meta: dict, *images: ImageContent, error: bool = False) -> CallToolResult:
    return CallToolResult(isError=error, content=[TextContent(type="text", text=json.dumps(meta, default=str)), *images])


@mcp.tool()
def blender_status() -> dict:
    """Is a GUI Blender with the bridge reachable? Returns version, open file, dirty flag, scene, frame, camera, counts."""
    try:
        r = call("ping", timeout=20); r.pop("ok", None); return {"reachable": True, **r}
    except OSError as exc:
        return {"reachable": False, "detail": str(exc), "hint": "call blender_launch"}


@mcp.tool()
def blender_launch(blend_path: str = "", wait_s: int = 90) -> dict:
    """Start the GUI Blender (BLENDER_EXE, blender_exe.txt, or blender on PATH) on blend_path with the bridge loaded,
    and wait until it answers. Does nothing if a bridge already answers."""
    st = blender_status()
    if st.get("reachable"): return {"started": False, **st}
    args = [BLENDER] + ([os.path.abspath(blend_path)] if blend_path else []) + ["--python", os.path.join(HERE, "bridge.py")]
    # DETACHED_PROCESS made Blender start on an unsaved file (the .blend argument was lost); a new process group
    # keeps it independent of this server without that side effect
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(args, creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    t0 = time.time()
    while time.time() - t0 < wait_s:
        time.sleep(2); st = blender_status()
        if st.get("reachable"): return {"started": True, "seconds": round(time.time() - t0, 1), **st}
    return {"started": True, "reachable": False, "detail": f"no bridge after {wait_s}s"}


@mcp.tool()
def exec_python(code: str, capture: bool = False, shading: str = "", max_px: int = 1280, timeout: float = 300) -> CallToolResult:
    """Run Python in the live Blender (bpy, C=context, D=data in scope). Assign `result` to return a JSON value;
    stdout is returned too. capture=True adds a viewport screenshot taken right after (edit-and-see)."""
    try:
        r = call("exec", timeout=timeout, code=code)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    meta = {"status": "ok", "result": r.get("result"), "stdout": r.get("stdout", "")}
    if not capture: return reply(meta)
    try:
        c = call("capture", shading=shading or None)
        return reply({**meta, "capture": {k: c[k] for k in ("shading", "perspective", "camera")}}, image(c["png_b64"], max_px))
    except Exception as exc:
        return reply({**meta, "capture_error": str(exc)[:1500]})


@mcp.tool()
def scene_tree(depth: int = 3, max_objects: int = 300) -> dict:
    """Collections and objects of the current scene (type, faces, collection instances, hidden flags), bounded."""
    r = call("scene_tree", depth=depth, max_objects=max_objects); r.pop("ok", None); return r


@mcp.tool()
def object_info(name: str) -> dict:
    """Transform, world bounds, dimensions, modifiers, materials, mesh counts, UV layers; camera/light settings."""
    r = call("object_info", name=name); r.pop("ok", None); return r


@mcp.tool()
def viewport_capture(camera: str = "", view: Literal["", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"] = "",
                     frame_object: str = "", shading: Literal["", "WIREFRAME", "SOLID", "MATERIAL", "RENDERED"] = "",
                     frame: int | None = None, redraws: int = 6, overlays: bool = False, max_px: int = 1280) -> CallToolResult:
    """Screenshot the live 3D Viewport. Optionally look through `camera`, switch to an axis `view`, frame an object,
    change shading, or jump to `frame` first. This changes the viewport (not the scene data)."""
    try:
        c = call("capture", camera=camera or None, view=view or None, frame_object=frame_object or None,
                 shading=shading or None, frame=frame, redraws=redraws, overlays=overlays)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    return reply({"status": "captured", **{k: c[k] for k in ("shading", "perspective", "camera", "path")}}, image(c["png_b64"], max_px))


@mcp.tool()
def motion_preview(frames: list[int] | None = None, start: int | None = None, end: int | None = None, count: int = 6,
                   camera: str = "", shading: Literal["", "WIREFRAME", "SOLID", "MATERIAL", "RENDERED"] = "",
                   width: int = 640, max_px: int = 640) -> CallToolResult:
    """Ordered viewport images at several frames in one call, to judge motion (animation, camera paths, simulations).
    Give `frames`, or start/end/count (default: the scene range, 6 frames). Looks through `camera` if given."""
    args = {"frames": frames or [], "count": count, "camera": camera or None, "shading": shading or None, "width": width}
    if start is not None: args["start"] = start
    if end is not None: args["end"] = end
    try:
        r = call("motion_preview", timeout=600, **args)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    return reply({"status": "captured", "frames": [s["frame"] for s in r["shots"]], "camera": r.get("camera")},
                 *[image(s["png_b64"], max_px) for s in r["shots"]])


@mcp.tool()
def render_image(camera: str = "", engine: Literal["", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT", "BLENDER_WORKBENCH", "CYCLES"] = "",
                 width: int = 0, height: int = 0, samples: int = 0, frame: int | None = None, filepath: str = "",
                 keep_settings: bool = False, max_px: int = 1280) -> CallToolResult:
    """Render a still in the live Blender (blocks its UI while rendering). Render settings are restored afterwards
    unless keep_settings. Returns the image and the PNG path."""
    try:
        r = call("render", camera=camera or None, engine=engine or None, width=width or None, height=height or None,
                 samples=samples or None, frame=frame, filepath=filepath or None, keep_settings=keep_settings, timeout=1800)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    return reply({"status": "rendered", **{k: r[k] for k in ("path", "seconds", "engine", "size", "camera")}}, image(r["png_b64"], max_px))


@mcp.tool()
def set_frame(frame: int) -> dict:
    """Set the scene's current frame (animations, camera paths)."""
    r = call("set_frame", frame=frame); r.pop("ok", None); return r


@mcp.tool()
def open_file(filepath: str) -> dict:
    """Open a .blend in the live Blender. Unsaved changes in the current file are lost; check blender_status.dirty first."""
    r = call("open_file", filepath=os.path.abspath(filepath)); r.pop("ok", None); return r


@mcp.tool()
def save_file(filepath: str = "") -> dict:
    """Save the open file, or save as filepath."""
    r = call("save_file", filepath=os.path.abspath(filepath) if filepath else None); r.pop("ok", None); return r


@mcp.tool()
def headless_run(script: str, args: list[str] | None = None, blend: str = "", timeout_s: int = 1800) -> dict:
    """Run a Python script in background Blender (-b --factory-startup unless blend is given, --python-exit-code 3).
    Returns the exit code, marker lines (lines starting with an UPPERCASE word and a JSON object), and the log tail."""
    cmd = [BLENDER, "-b"] + ([os.path.abspath(blend)] if blend else ["--factory-startup"]) + \
          ["--python-exit-code", "3", "--python", os.path.abspath(script), "--", *(args or [])]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s, stdin=subprocess.DEVNULL)   # never the MCP pipe
    except FileNotFoundError as exc:
        return {"exit_code": -1, "seconds": round(time.time() - t0, 1), "markers": [], "errors": [f"Blender executable not found: {exc}"], "tail": ""}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "seconds": round(time.time() - t0, 1), "markers": [], "errors": [f"Blender headless_run timed out after {timeout_s}s"], "tail": ""}
    lines = (p.stdout or "").splitlines()
    markers = [l for l in lines if l[:1].isupper() and " {" in l[:40] and l.split(" ", 1)[0].isupper()]
    errs = [l for l in lines + (p.stderr or "").splitlines() if "Traceback" in l or l.startswith("Error")][:20]
    return {"exit_code": p.returncode, "seconds": round(time.time() - t0, 1), "markers": markers[-20:], "errors": errs,
            "tail": "\n".join(lines[-30:])}


@mcp.tool()
def compare_images(reference: str, candidate: str, max_px: int = 1600) -> CallToolResult:
    """Compare two images (candidate resized to reference): exact-pixel %, mean abs error, grey SSIM (256 px),
    and a side-by-side reference | candidate | difference image."""
    a = Image.open(reference).convert("RGB"); b = Image.open(candidate).convert("RGB").resize(a.size)
    A, B = np.asarray(a, np.int32), np.asarray(b, np.int32); ad = np.abs(A - B).max(2)
    def grey(im): return np.asarray(im.convert("L").resize((256, max(1, int(256 * a.size[1] / a.size[0])))), np.float64)
    x, y = grey(a), grey(b); C1, C2 = 6.5025, 58.5225
    def blur(z):                                             # 7x7 box blur, enough for a global SSIM summary
        k = np.ones(7) / 7; z = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, z)
        return np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, z)
    mx, my = blur(x), blur(y); sx, sy, sxy = blur(x * x) - mx ** 2, blur(y * y) - my ** 2, blur(x * y) - mx * my
    ssim = float((((2 * mx * my + C1) * (2 * sxy + C2)) / ((mx ** 2 + my ** 2 + C1) * (sx + sy + C2))).mean())
    diff = Image.fromarray(np.clip(ad * 3, 0, 255).astype(np.uint8)).convert("RGB")
    side = Image.new("RGB", (a.size[0] * 3, a.size[1])); side.paste(a, (0, 0)); side.paste(b, (a.size[0], 0)); side.paste(diff, (2 * a.size[0], 0))
    out = io.BytesIO(); side.save(out, "PNG")
    meta = {"exact_pct": round(float((ad == 0).mean() * 100), 4), "within8_pct": round(float((ad <= 8).mean() * 100), 4),
            "mean_abs_error": round(float(np.abs(A - B).mean()), 3), "ssim": round(ssim, 4), "size": list(a.size)}
    return reply(meta, image(base64.b64encode(out.getvalue()).decode(), max_px))


# ------------------------------------------------------------------ sculpt and review (bridge side: sculpt_cmds.py)
Brush = Literal["grab", "snake_hook", "draw", "clay_strips", "inflate", "crease", "smooth"]


def _bridge(cmd: str, timeout: float = 300, **args) -> dict:
    try:
        r = call(cmd, timeout=timeout, **args); r.pop("ok", None); return r
    except Exception as exc:
        return {"status": "error", "detail": str(exc)[:3000]}


@mcp.tool()
def reference_setup(images: dict[str, str], height: float = 2.0) -> dict:
    """Place concept pictures as REF_<VIEW> image empties. images maps FRONT/BACK/LEFT/RIGHT/TOP to a file path.
    Each stands upright with its bottom edge on the ground plane, `height` world units tall, behind the model for that
    view, visible only in orthographic views. Crop each picture tight to the character first so `height` is its height."""
    return _bridge("reference_setup", images=images, height=height)


@mcp.tool()
def sculpt_begin(object: str, symmetry: Literal["", "X", "Y", "Z"] = "X", voxel_size: float | None = None) -> dict:
    """Pick the mesh to sculpt and its symmetry axis (object-local; "" for none). The choice is stored on the object and
    used by sculpt_strokes. Returns vertex count and the brush list."""
    return _bridge("sculpt_begin", object=object, symmetry=symmetry, voxel_size=voxel_size)


@mcp.tool()
def sculpt_strokes(object: str, strokes: list[dict], symmetry: str | None = None, capture: bool = False,
                   view: Literal["", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"] = "", max_px: int = 1024) -> CallToolResult:
    """Apply sculpt strokes in order. Each stroke is {"brush", "points": [[x,y,z],...], "radius", "strength",
    "subtract", "snap"}: points and radius in world units; snap=true moves each point onto the nearest surface spot.
    Brushes: grab (one move: verts near the FIRST point shift by last minus first), snake_hook (pulls along the path),
    draw, clay_strips, inflate (raise; subtract lowers), crease (cuts a valley; subtract makes a ridge), smooth.
    Returns per stroke moved_verts, max_move and mean_move: moved_verts 0 means the stroke missed the mesh.
    capture=True adds a viewport image afterwards (optionally from an axis `view`)."""
    try:
        r = call("sculpt_strokes", timeout=600, object=object, strokes=strokes, symmetry=symmetry); r.pop("ok", None)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    if not capture: return reply(r)
    try:   # the turnaround command restores the viewport afterwards, unlike a plain capture
        c = call("turnaround", timeout=300, object=object, views=[view or "FRONT"], cell_px=768)["shots"][0]
        return reply(r, image(c["png_b64"], max_px))
    except Exception as exc:
        return reply({**r, "capture_error": str(exc)[:1500]})


@mcp.tool()
def sculpt_remesh(object: str, voxel_size: float) -> dict:
    """Voxel remesh: rebuild the surface as even quads of about voxel_size (world units), fusing overlapping parts
    into one skin. Use after a blockout and whenever strokes have stretched the faces. Clears the mask."""
    return _bridge("sculpt_remesh", timeout=900, object=object, voxel_size=voxel_size)


@mcp.tool()
def sculpt_mask(object: str, op: Literal["box", "clear", "invert"] = "clear", min: list[float] | None = None,
                max: list[float] | None = None) -> dict:
    """Protect vertices from strokes. box: mask everything inside the world-space box min..max; invert; clear."""
    return _bridge("sculpt_mask", object=object, op=op, min=min, max=max)


@mcp.tool()
def mesh_report(object: str) -> dict:
    """Mesh health in numbers: verts, faces, loose_parts, boundary_edges (holes), non_manifold_edges, symmetry_error
    (0 = perfectly mirrored in X; fraction of the bounding-box diagonal), world bounds, masked_verts."""
    return _bridge("mesh_report", object=object)


def _label(cell: Image.Image, text: str) -> Image.Image:
    from PIL import ImageDraw
    d = ImageDraw.Draw(cell); d.rectangle((0, 0, 8 + 7 * len(text), 16), fill=(0, 0, 0)); d.text((4, 2), text, fill=(255, 255, 255))
    return cell


@mcp.tool()
def turnaround_sheet(object: str, views: list[str] | None = None, references: dict[str, str] | None = None,
                     also: list[str] | None = None, cell_px: int = 512, max_px: int = 2048) -> CallToolResult:
    """One labelled image of the object from FRONT, BACK, LEFT, RIGHT, TOP and THREE_QUARTER (or the `views` given), in
    one fixed clay shading with everything else hidden. `also` lists more objects to show with it (other body parts,
    clothes); the object's children are always shown. `references` maps a view to a picture file; that picture is
    placed in the cell right after its view so the two can be compared. The viewport is restored afterwards.
    This is for looking. It measures nothing."""
    refs = {k.upper(): v for k, v in (references or {}).items()}
    try:
        r = call("turnaround", timeout=600, object=object, views=views, also=also or [], cell_px=cell_px)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    cells, order = [], []
    for s in r["shots"]:
        im = Image.open(io.BytesIO(base64.b64decode(s["png_b64"]))).convert("RGB").resize((cell_px, cell_px))
        cells.append(_label(im, s["view"])); order.append(s["view"])
        if s["view"] in refs:
            cell = Image.new("RGB", (cell_px, cell_px), (40, 40, 40))
            ref = Image.open(refs[s["view"]]).convert("RGB"); ref.thumbnail((cell_px, cell_px))
            cell.paste(ref, ((cell_px - ref.size[0]) // 2, (cell_px - ref.size[1]) // 2))
            cells.append(_label(cell, s["view"] + " REFERENCE")); order.append(s["view"] + "_REFERENCE")
    sheet = Image.new("RGB", (cell_px * len(cells), cell_px))
    for i, c in enumerate(cells): sheet.paste(c, (i * cell_px, 0))
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"turnaround_{int(time.time() * 1000)}.png"); sheet.save(path)
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    meta = {"status": "captured", "object": r["object"], "cells": order, "referenced": [v for v in order if v in refs],
            "path": path, "size": list(sheet.size), "measured": False}
    return reply(meta, image(base64.b64encode(buf.getvalue()).decode(), max_px))


@mcp.tool()
def outline_match(object: str, references: dict[str, str], threshold: float = 0.98, views: list[str] | None = None,
                  also: list[str] | None = None, max_px: int = 2048) -> CallToolResult:
    """MEASURE how closely the model's outline matches reference pictures. references maps a Blender view name
    (FRONT, BACK, LEFT, RIGHT, TOP; anything else is refused) to a picture taken straight-on from that side, on a
    plain or transparent background with space around the subject. `also` lists more objects that are part of the
    character (head, clothes, hair...); the object, its children and those are measured together as one outline.
    For each view the model is captured orthographically as a flat silhouette, both outlines are cropped, scaled the
    same way and overlaid, and the overlap (intersection over union, 0..1) is compared to `threshold` (0.90 to 1.0).
    Each requested view gets passed, failed, or not_run (no reference). all_views_passed is true only when all FIVE
    views were measured and passed, whatever `views` asked for; unmeasured_of_five lists the rest. A not_run view was
    not checked and must never be reported as passing. Overlay per measured view: white = both agree, red = reference
    only (model is missing this), blue = model only (model has extra here).
    Measures outline only: not depth inside the outline, not colour, not surface detail."""
    try:
        refs, wanted = outline.check_request(references, views, threshold)
        measured = [v for v in wanted if v in refs]
        ref_masks = {v: outline.reference_mask(refs[v]) for v in measured}
        shots = call("silhouettes", timeout=600, object=object, also=also or [], views=measured)["shots"] if measured else []
        model_masks = {}
        for s in shots:
            if s.get("perspective") != "ORTHO": raise RuntimeError(f"{s['view']}: capture was not orthographic")
            grey = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["png_b64"]))).convert("L"))
            model_masks[s["view"]] = outline.model_mask(grey, s["view"])
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    res = outline.score(ref_masks, model_masks, wanted, threshold)
    overlays = []
    for v, r in res["views"].items():
        ref, model = r.pop("_ref", None), r.pop("_model", None)
        if ref is None: continue
        rgb = np.zeros((*model.shape, 3), np.uint8)
        rgb[model & ref] = (255, 255, 255); rgb[ref & ~model] = (230, 40, 40); rgb[model & ~ref] = (40, 90, 230)
        overlays.append(_label(Image.fromarray(rgb), f"{v} iou {r['iou']:.4f} {r['status']}"))
    meta = {"object": object, "also": also or [], **res}
    if not overlays: return reply(meta)
    sheet = Image.new("RGB", (outline.FIT * len(overlays), outline.FIT))
    for i, c in enumerate(overlays): sheet.paste(c, (i * outline.FIT, 0))
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    os.makedirs(out_dir, exist_ok=True)
    meta["overlay_path"] = os.path.join(out_dir, f"outline_{int(time.time() * 1000)}.png"); sheet.save(meta["overlay_path"])
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    return reply(meta, image(base64.b64encode(buf.getvalue()).decode(), max_px))


if __name__ == "__main__":
    mcp.run(transport="stdio")
