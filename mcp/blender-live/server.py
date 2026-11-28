# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp==1.30.0", "pillow>=10", "numpy>=1.26"]
# ///
"""blender-live MCP server: drive a running GUI Blender (through bridge.py) and headless Blender jobs.

Start from the workspace root (see features.json). The GUI side is tools/blender-live/bridge.py, which
blender_launch starts for you. Images come back as MCP image content (PNG), downscaled to max_px.
"""
import base64, contextlib, io, json, os, socket, subprocess, sys, time
from typing import Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent
from PIL import Image, ImageDraw
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import outline
import projection

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
    "sculpt_remesh evens the faces, sculpt_relax irons ripples and stair steps, sculpt_mask protects areas, "
    "mesh_report gives health numbers, and turnaround_sheet shows every side next to the references. To measure and "
    "match 1:1: outline_match (outline), fit_outline (warp the outline onto the pictures), project_paint (paint the "
    "pictures onto the UVs), visual_match (pixels per referenced view: outline, SSIM, edges, CIEDE2000 colour, clay "
    "banding) and orbit_check (surface quality and a review sheet from every angle)."))


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


def _bridge(cmd: str, timeout: float = 300, **args) -> CallToolResult:
    try:
        r = call(cmd, timeout=timeout, **args); r.pop("ok", None); return reply(r)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)


@mcp.tool()
def reference_setup(images: dict[str, str], height: float = 2.0) -> CallToolResult:
    """Place concept pictures as REF_<VIEW> image empties. images maps FRONT/BACK/LEFT/RIGHT/TOP to a file path.
    Each stands upright with its bottom edge on the ground plane, `height` world units tall, behind the model for that
    view, visible only in orthographic views. Crop each picture tight to the character first so `height` is its height."""
    return _bridge("reference_setup", images=images, height=height)


@mcp.tool()
def sculpt_begin(object: str, symmetry: Literal["", "X", "Y", "Z"] = "X", voxel_size: float | None = None) -> CallToolResult:
    """Pick the mesh to sculpt and its symmetry axis (object-local; "" for none). The choice is stored on the object and
    used by sculpt_strokes. Returns vertex count and the brush list."""
    return _bridge("sculpt_begin", object=object, symmetry=symmetry, voxel_size=voxel_size)


@mcp.tool()
def sculpt_strokes(object: str, strokes: list[dict], symmetry: str | None = None, capture: bool = False,
                   view: Literal["", "TOP", "BOTTOM", "FRONT", "BACK", "LEFT", "RIGHT"] = "", max_px: int = 1024) -> CallToolResult:
    """Apply strokes in order. Each stroke is {"brush", "points": [[x,y,z],...], "radius", "strength",
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
def sculpt_remesh(object: str, voxel_size: float) -> CallToolResult:
    """Voxel remesh: rebuild the surface as even quads of about voxel_size (world units), fusing overlapping parts
    into one skin. Use after a blockout and whenever strokes have stretched the faces. Clears the mask."""
    return _bridge("sculpt_remesh", timeout=900, object=object, voxel_size=voxel_size)


@mcp.tool()
def sculpt_relax(object: str, iterations: int = 20, method: Literal["taubin", "laplacian"] = "taubin",
                 along: Literal["", "X", "Y", "Z"] = "", lam: float = 0.5, mu: float = -0.53,
                 pin_boundary: bool = True) -> CallToolResult:
    """Smooth the whole mesh. taubin (default) alternates lam / mu passes: irons out lumps and fine stair steps
    without shrinking, but by design keeps waves several edges long. laplacian removes those long waves too but
    shrinks convex tips; pair it with along. along X / Y / Z averages each vertex only with neighbours across edges
    pointing mostly along that world axis: along="Z" + laplacian flattens the horizontal ridges of a slice-lofted
    (ring-stacked) mesh that visual_match reports as clay banding, while each ring keeps its outline. Masked verts
    and (by default) open-boundary verts stay put. Returns moved_verts, max_move, mean_move (world units).
    Re-check outline_match afterwards."""
    return _bridge("sculpt_relax", timeout=600, object=object, iterations=iterations, method=method, along=along,
                   lam=lam, mu=mu, pin_boundary=pin_boundary)


@mcp.tool()
def sculpt_mask(object: str, op: Literal["box", "clear", "invert"] = "clear", min: list[float] | None = None,
                max: list[float] | None = None) -> CallToolResult:
    """Protect vertices from strokes. box: mask everything inside the world-space box min..max; invert; clear."""
    return _bridge("sculpt_mask", object=object, op=op, min=min, max=max)


@mcp.tool()
def mesh_report(object: str) -> CallToolResult:
    """Mesh health in numbers: verts, faces, loose_parts, boundary_edges (holes), non_manifold_edges, symmetry_error
    (mean), symmetry_p95_error (95th percentile), symmetry_max_error (worst sampled vertex, exact up to 100k verts;
    0 = perfectly mirrored in X, fraction of the bounding-box diagonal), world bounds, masked_verts."""
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
        ref_masks = {v: outline.reference_mask(refs[v], work=2 * outline.WORK) for v in measured}
        shots = call("silhouettes", timeout=600, object=object, also=also or [], views=measured)["shots"] if measured else []
        model_masks = {}
        for s in shots:
            if s.get("perspective") != "ORTHO": raise RuntimeError(f"{s['view']}: capture was not orthographic")
            grey = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["png_b64"]))).convert("L"))
            model_masks[s["view"]] = outline.model_coverage(grey, s["view"])
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


@mcp.tool()
def visual_match(object: str, references: dict[str, str], outline_threshold: float = 0.98,
                 ssim_threshold: float = 0.78, edge_f1_threshold: float = 0.60,
                 max_delta_e: float = 10.0, max_banding: float = 1.60,
                 views: list[str] | None = None, also: list[str] | None = None, max_px: int = 2048) -> CallToolResult:
    """MEASURE 1:1 likeness pixel by pixel against straight-on reference pictures. Per view the model is captured
    three ways from the same orthographic camera (flat silhouette, untextured clay, material), its outline is
    registered onto the reference (a small shift/scale search, reported as `registration`), and five gates must all
    pass: outline IoU >= outline_threshold; masked foreground SSIM >= ssim_threshold; interior edge F1 >=
    edge_f1_threshold; CIEDE2000 colour proof mean delta E <= max_delta_e on the shared interior (plus p90, the share
    within delta E 5 / 10, and the reference's dominant inks as hex next to the model's colour on the same pixels);
    untextured clay banding <= max_banding (repeated horizontal ridges: slice-loft rings, stair steps; a projected
    texture cannot hide them). reference_pairs gives how well opposite pictures (FRONT/BACK, LEFT/RIGHT mirrored)
    agree: below the threshold no single model can pass both. Whether drawn features exist as geometry (nose, collar,
    folds) is not a number: judge the CLAY row. Returns per-view metrics, failed_checks and a sheet (REF | MATERIAL
    | CLAY | delta-E heat, black <= 2, yellow ~13, red >= 25) to review by eye. Views without a reference are
    not_run."""
    try:
        refs, wanted = outline.check_request(references, views, outline_threshold)
        measured = [v for v in wanted if v in refs]
        ref_masks = {v: outline.reference_mask(refs[v], work=2 * outline.WORK) for v in measured}
        ref_rgbs = {v: outline.reference_rgb(refs[v], work=2 * outline.WORK) for v in measured}
        shots = call("visual_captures", timeout=900, object=object, also=also or [], views=measured)["shots"] if measured else []
        model_masks, clay_greys, mat_rgbs = {}, {}, {}
        for s in shots:
            if s.get("perspective") != "ORTHO":
                raise RuntimeError(f"{s['view']}: capture was not orthographic")
            v = s["view"]
            sil_g = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["silhouette_b64"]))).convert("L"))
            model_masks[v] = outline.model_coverage(sil_g, v)
            clay_greys[v] = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["clay_b64"]))).convert("L"))
            mat_rgbs[v] = np.asarray(Image.open(io.BytesIO(base64.b64decode(s["material_b64"]))).convert("RGB"))
        res = outline.visual_score(
            ref_rgbs, ref_masks, mat_rgbs, clay_greys, model_masks, wanted,
            outline_threshold=outline_threshold, ssim_threshold=ssim_threshold, edge_f1_threshold=edge_f1_threshold,
            max_delta_e=max_delta_e, max_banding=max_banding,
        )
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)

    cols = []
    cell = 384
    for v, r in res["views"].items():
        rc = r.pop("_ref_rgb", None)
        mc = r.pop("_mat_rgb", None)
        cc = r.pop("_clay_rgb", None)
        un = r.pop("_union", None)
        if rc is None:
            continue
        de = projection.delta_e00(projection.srgb_to_lab(rc), projection.srgb_to_lab(mc))
        t = np.clip((de - 2.0) / 23.0, 0, 1)
        heat = np.stack([np.clip(t * 2, 0, 1), np.clip(t * 2, 0, 1) * np.clip(2 - t * 2, 0, 1), np.zeros_like(t)], -1)
        heat = (heat * 255).astype(np.uint8); heat[~un] = 0
        col = Image.new("RGB", (cell, cell * 4), (20, 20, 24))
        panels = [
            (rc, f"{v} REF"),
            (mc, f"{v} MAT ssim={r['ssim']:.2f} ef1={r['interior_edge_f1']:.2f} iou={r['iou']:.3f}"),
            (cc, f"{v} CLAY band={r['clay_banding_ratio']:.2f}"),
            (heat, f"{v} {r['status']} dE={r['delta_e_mean']:.1f} <=10:{r['within_de10_pct']:.0f}%"),
        ]
        for idx, (arr, lbl) in enumerate(panels):
            im_p = Image.fromarray(arr).resize((cell, cell), Image.LANCZOS)
            col.paste(_label(im_p, lbl), (0, idx * cell))
        cols.append(col)
    meta = {"object": object, "also": also or [], **res}
    if not cols:
        return reply(meta)
    sheet = Image.new("RGB", (cell * len(cols), cell * 4))
    for i, c in enumerate(cols):
        sheet.paste(c, (i * cell, 0))
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    os.makedirs(out_dir, exist_ok=True)
    meta["visual_sheet_path"] = os.path.join(out_dir, f"visual_{int(time.time() * 1000)}.png")
    sheet.save(meta["visual_sheet_path"])
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    return reply(meta, image(base64.b64encode(buf.getvalue()).decode(), max_px))


@mcp.tool()
def orbit_check(object: str, azimuth_step: float = 45.0, elevations: list[float] | None = None,
                max_banding: float = 1.60, also: list[str] | None = None, px: int = 768,
                max_px: int = 2048) -> CallToolResult:
    """MEASURE surface quality from all around: orthographic captures every azimuth_step degrees (0 = FRONT, 90 =
    Blender RIGHT) at each elevation (default 0 and 30), each scored without a reference for untextured clay banding
    (stair-stepped or ring-stacked geometry) and missing-texture magenta. Returns per-angle numbers and a sheet with
    MATERIAL and CLAY for every angle, for reviewing by eye the angles no reference picture covers (three-quarter
    views show texture smears, seams and paint projected onto the wrong surface). It does not measure likeness."""
    try:
        step = float(azimuth_step)
        if not (5.0 <= step <= 180.0): raise ValueError("azimuth_step must be 5..180 degrees")
        els = [float(e) for e in (elevations if elevations is not None else [0.0, 30.0])]
        if not els or any(not (-89.0 <= e <= 89.0) for e in els): raise ValueError("elevations must be within -89..89")
        angles = [[a, e] for e in els for a in np.arange(0.0, 360.0 - 1e-6, step).tolist()]
        r = call("orbit_captures", timeout=1800, object=object, also=also or [], angles=angles, px=int(px))
        shots, cells = [], []
        for s in r["shots"]:
            if s.get("perspective") != "ORTHO": raise RuntimeError("orbit capture was not orthographic")
            dec = lambda k, mode: np.asarray(Image.open(io.BytesIO(base64.b64decode(s[k]))).convert(mode))
            shots.append({"azimuth": s["azimuth"], "elevation": s["elevation"], "sil": dec("silhouette_b64", "L"),
                          "clay": dec("clay_b64", "L"), "mat": dec("material_b64", "RGB")})
        res = outline.orbit_score(shots, max_banding=max_banding)
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    cell = 320
    for s, row in zip(shots, res["angles"]):
        m = outline.model_mask(s["sil"], f"az {s['azimuth']:g}")
        fm, _ = outline.fit_rgb(s["mat"], m); fc, _ = outline.fit_rgb(np.repeat(s["clay"][..., None], 3, 2), m)
        pair = Image.new("RGB", (cell * 2, cell))
        pair.paste(_label(Image.fromarray(fm).resize((cell, cell), Image.LANCZOS),
                          f"az{s['azimuth']:g} el{s['elevation']:g} MAT"), (0, 0))
        pair.paste(_label(Image.fromarray(fc).resize((cell, cell), Image.LANCZOS),
                          f"CLAY band={row['clay_banding_ratio']:.2f} {row['status']}"), (cell, 0))
        cells.append(pair)
    per_row = 4
    rows_n = (len(cells) + per_row - 1) // per_row
    sheet = Image.new("RGB", (cell * 2 * per_row, cell * rows_n), (20, 20, 24))
    for i, c in enumerate(cells):
        sheet.paste(c, ((i % per_row) * cell * 2, (i // per_row) * cell))
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    os.makedirs(out_dir, exist_ok=True)
    meta = {"object": object, "also": also or [], **res,
            "orbit_sheet_path": os.path.join(out_dir, f"orbit_{int(time.time() * 1000)}.png")}
    sheet.save(meta["orbit_sheet_path"])
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    return reply(meta, image(base64.b64encode(buf.getvalue()).decode(), max_px))


THREE_QUARTER_PAIRS = (("FRONT", "RIGHT", 45.0), ("BACK", "RIGHT", 135.0), ("BACK", "LEFT", 225.0),
                       ("FRONT", "LEFT", 315.0))


@mcp.tool()
def three_quarter_check(object: str, references: dict[str, str], max_delta_e: float = outline.THREE_QUARTER_MAX_DE,
                        elevation: float = 0.0, tex_size: int = 2048, px: int = 2048,
                        priority_views: list[str] | None = None, palette_view: str = "", min_cos: float = 0.12,
                        min_cos_other: float = 0.35, also: list[str] | None = None,
                        max_px: int = 2048) -> CallToolResult:
    """MEASURE likeness at the angles between two reference pictures, where no picture exists. Each picture is
    painted onto the model on its own (project_paint's rules, no blending, no fill), and the model is rendered from
    the angle halfway between two neighbouring pictures (45 FRONT/RIGHT, 135 BACK/RIGHT, 225 BACK/LEFT, 315
    FRONT/LEFT) once with each. Where both pictures paint, a model that fits both shows the same colours in both
    renders; a feature the pictures put on different surfaces (a side eye on the cheek, hair painted on bare skin)
    fails, per region (head, body, legs): CIEDE2000 mean above max_delta_e (default 12: two pictures that both fit
    differ by 5-10 in drawing style alone). Pass the same priority_views / palette_view / min_cos / min_cos_other as
    project_paint, and keep the rig at rest (frame of the rest pose). Returns per pair and region: cover_pct,
    delta_e_mean, conflict_pct (share above 20), status; and a sheet per pair: A | B | CIEDE2000 map (green agrees,
    red conflicts, grey = only one picture paints), the head zoomed underneath. The painting is left as it was.
    A pair whose two pictures disagree (outline_match reference_pairs well below 0.9) measures the pictures as much
    as the model: read its failures against the sheet."""
    spec = {}
    try:
        refs, _ = outline.check_request(references, None, 0.98)
        pairs = [(a, b, az) for a, b, az in THREE_QUARTER_PAIRS if a in refs and b in refs]
        if not pairs: raise ValueError("needs two neighbouring pictures (FRONT or BACK with LEFT or RIGHT)")
        use = sorted({v for a, b, _ in pairs for v in (a, b)})
        out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
        os.makedirs(out_dir, exist_ok=True)
        spec = {v: _paint_reference(refs[v], out_dir, v) for v in use}
        call("project_paint", timeout=1800, object=object, also=also or [], views=spec, tex_size=int(tex_size),
             per_view=True, min_cos=float(min_cos), min_cos_other=float(min_cos_other),
             priority_views=[str(v).upper() for v in priority_views or []], palette_view=str(palette_view).upper(),
             warp=False)
        shots = {}
        try:
            for v in use:
                call("show_paint", object=object, also=also or [], view=v)
                angles = [[az, float(elevation)] for a, b, az in pairs if v in (a, b)]
                r = call("orbit_captures", timeout=900, object=object, also=also or [], angles=angles, px=int(px))
                for s in r["shots"]:
                    dec = lambda k, mode: np.asarray(Image.open(io.BytesIO(base64.b64decode(s[k]))).convert(mode))
                    shots[(v, s["azimuth"])] = (dec("material_b64", "RGB"), dec("silhouette_b64", "L"))
        finally:
            call("show_paint", object=object, also=also or [], view="", cleanup=True)
        rows, cells = [], []
        for a, b, az in pairs:
            (ma, sil), (mb, _) = shots[(a, az)], shots[(b, az)]
            ys, xs = np.nonzero(outline.model_mask(sil, f"az {az:g}"))      # score the figure, not the empty frame
            y0, y1 = max(int(ys.min()) - 8, 0), int(ys.max()) + 9; x0, x1 = max(int(xs.min()) - 8, 0), int(xs.max()) + 9
            ma, mb, sil = ma[y0:y1, x0:x1], mb[y0:y1, x0:x1], sil[y0:y1, x0:x1]
            sc = outline.consistency_score(ma, mb, sil, f"az {az:g}", float(max_delta_e))
            heat = np.zeros(ma.shape, np.uint8); heat[outline.model_mask(sil, f"az {az:g}")] = 70
            d = np.clip(sc.pop("delta_e_map") / 30.0, 0, 1); both = sc.pop("both_painted")
            heat[both] = np.stack([255 * d, 255 * (1 - d), 40 * np.ones_like(d)], -1)[both].astype(np.uint8)
            hh = int(outline.HEAD_FRAC * ma.shape[0]) + 8           # head rows, zoomed, under the full figures
            cell_h, head_h = 480, 360
            fw = int(ma.shape[1] * cell_h / ma.shape[0]); hw = int(ma.shape[1] * head_h / hh)
            trio = Image.new("RGB", (max(3 * fw, 3 * hw), cell_h + head_h), (20, 20, 24))
            for i, (im, txt) in enumerate(((ma, f"az{az:g} {a} only"), (mb, f"{b} only"),
                                           (heat, f"dE00 {sc['status']}"))):
                trio.paste(_label(Image.fromarray(im).resize((fw, cell_h), Image.LANCZOS), txt), (i * fw, 0))
                trio.paste(Image.fromarray(im[:hh]).resize((hw, head_h), Image.LANCZOS), (i * hw, cell_h))
            cells.append(trio)
            rows.append({"pair": f"{a}/{b}", "azimuth": az, "elevation": float(elevation), **sc})
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    finally:
        for s in spec.values():
            with contextlib.suppress(OSError): os.remove(s["npy"])
    sheet = Image.new("RGB", (max(c.width for c in cells), sum(c.height for c in cells)), (20, 20, 24))
    y = 0
    for c in cells: sheet.paste(c, (0, y)); y += c.height
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    meta = {"object": object, "pairs": rows, "passed": sum(r["status"] == "passed" for r in rows),
            "failed": sum(r["status"] == "failed" for r in rows),
            "thresholds": {"max_delta_e": max_delta_e},
            "sheet_path": os.path.join(out_dir, f"threequarter_{int(time.time() * 1000)}.png")}
    sheet.save(meta["sheet_path"])
    buf = io.BytesIO(); sheet.save(buf, "PNG")
    return reply(meta, image(base64.b64encode(buf.getvalue()).decode(), max_px))


@mcp.tool()
def fit_outline(object: str, references: dict[str, str], views: list[str] | None = None, strength: float = 0.8,
                max_px: float = 8.0, rim_angle: float = 50.0, sigma_px: float = 6.0,
                also: list[str] | None = None) -> CallToolResult:
    """SCULPT the outline onto the reference outlines, like a liquify per view: for each listed view (in order) the
    verts on the model's own silhouette measure how far the outline must move toward the reference's outline
    (strength x the signed distance, clipped to max_px reference pixels); those moves become a smooth picture-plane
    warp (Gaussian, sigma_px) that every vert follows, so sides stay round and pixel noise averages out. The model is
    registered onto the picture first, as outline_match does. Use it for the last few percent of outline overlap
    once the forms are right, alternating FRONT and LEFT, and re-measure with outline_match after each round: it
    moves surface, it does not invent forms. Only use views whose picture shows the model's pose. Masked verts stay
    put; the rig must be at rest."""
    tmp_files = []
    try:
        refs, wanted = outline.check_request(references, views, 0.98)
        use = [v for v in wanted if v in refs]
        if not use: raise ValueError("no reference picture for the requested views")
        out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
        os.makedirs(out_dir, exist_ok=True)
        spec = {}
        for v in use:
            m = outline.reference_mask(refs[v], work=2 * outline.WORK)
            ys, xs = np.nonzero(m)
            npy = os.path.join(out_dir, f"sdf_{v}_{int(time.time() * 1000)}.npy"); tmp_files.append(npy)
            np.save(npy, projection.distance_field(m).astype(np.float32))
            spec[v] = {"npy": npy, "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]}
        res = call("fit_outline", timeout=1800, object=object, also=also or [], views=spec, strength=float(strength),
                   max_px=float(max_px), rim_angle=float(rim_angle), sigma_px=float(sigma_px))
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    finally:
        for f in tmp_files:
            with contextlib.suppress(OSError): os.remove(f)
    res.pop("ok", None)
    return reply({"status": "fitted", "object": object, **res})


PART_COLOURS = np.array([[230, 60, 60], [60, 160, 240], [250, 200, 40], [70, 200, 90], [200, 90, 220],
                         [250, 140, 40], [40, 200, 200], [150, 110, 70], [240, 120, 170], [120, 120, 250]], np.uint8)


def _fill_unknown(lab: np.ndarray, known: np.ndarray, inside: np.ndarray, rounds: int = 400) -> np.ndarray:
    """Grow known labels into unknown pixels (ink lines, eyes) inside the subject, one pixel ring per round."""
    lab = lab.copy(); todo = inside & ~known
    h, w = lab.shape
    shifts = ((slice(0, h), slice(1, w), slice(0, h), slice(0, w - 1)), (slice(0, h), slice(0, w - 1), slice(0, h), slice(1, w)),
              (slice(1, h), slice(0, w), slice(0, h - 1), slice(0, w)), (slice(0, h - 1), slice(0, w), slice(1, h), slice(0, w)))
    for _ in range(rounds):
        if not todo.any(): break
        grow = np.full(lab.shape, -1, lab.dtype)
        for dy, dx, sy, sx in shifts:                  # neighbour at (sy, sx) offers its label to (dy, dx)
            src = lab[sy, sx]; dst = grow[dy, dx]
            ok = (dst < 0) & (src >= 0) & todo[dy, dx]
            dst[ok] = src[ok]
        new = grow >= 0
        if not new.any(): break
        lab[new] = grow[new]; todo &= ~new
    return lab


def _part_maps(object, refs, use, groups, work, also, ink_l, ink_chroma, tmp_files) -> dict:
    """Per view: the picture's subject mask m, the model's nearest group per pixel gm and the picture's group per
    pixel gd (part_match explains how), plus the outline field spec the Blender side registers with."""
    out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
    os.makedirs(out_dir, exist_ok=True)
    spec, masks = {}, {}
    for v in use:
        m = outline.reference_mask(refs[v], work=int(work)); masks[v] = m
        ys, xs = np.nonzero(m); stamp = int(time.time() * 1000)
        npy = os.path.join(out_dir, f"sdf_{v}_{stamp}.npy"); lab_npy = os.path.join(out_dir, f"parts_{v}_{stamp}.npy")
        tmp_files += [npy, lab_npy]
        np.save(npy, projection.distance_field(m).astype(np.float32))
        spec[v] = {"npy": npy, "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1], "out": lab_npy}
    res = call("part_map", timeout=900, object=object, also=also or [], views=spec)
    names = res["names"]
    group_of = {n: n for n in names}
    for g, members in (groups or {}).items():
        for n in members:
            if n in group_of: group_of[n] = g
    gnames = list(dict.fromkeys(group_of[n] for n in names))
    to_g = np.array([gnames.index(group_of[n]) for n in names] + [-1], np.int32)   # label -1 -> -1
    views = {}
    for v in use:
        m = masks[v]
        raw = np.load(res["views"][v]["labels"]).astype(np.int32)
        gm = to_g[np.where(raw < 0, len(names), raw)]
        rgb = np.asarray(outline._reduce(Image.open(refs[v]), int(work)).convert("RGB"), np.float64)
        lab = projection.srgb_to_lab(rgb.reshape(-1, 3)).reshape(rgb.shape)
        chroma = np.hypot(lab[..., 1], lab[..., 2])
        clear = m & ~((lab[..., 0] < ink_l) & (chroma < ink_chroma))
        cols, present = [], []
        for gi in range(len(gnames)):
            sel = clear & (gm == gi)
            if sel.sum() >= 30: cols.append(np.median(lab[sel], axis=0)); present.append(gi)
        if not present: raise ValueError(f"{v}: the model covers none of the picture")
        best = np.full(m.shape, np.inf); near = np.full(m.shape, -1, np.int32)
        for gi, c in zip(present, cols):                # one group at a time: a full stack is too big at 2K
            dist = np.linalg.norm(lab - c, axis=-1)
            closer = dist < best; best[closer] = dist[closer]; near[closer] = gi
        gd = np.full(m.shape, -1, np.int32)
        known = clear & (best <= 30.0)
        gd[known] = near[known]
        gd = _fill_unknown(gd, known, m)
        gd[~m] = -1
        views[v] = {"m": m, "gm": gm, "gd": gd, "rgb": rgb}
    return {"names": names, "gnames": gnames, "group_of": group_of, "spec": spec, "views": views, "res": res,
            "out_dir": out_dir}


@mcp.tool()
def part_match(object: str, references: dict[str, str], views: list[str] | None = None,
               groups: dict[str, list[str]] | None = None, work: int = 2048, also: list[str] | None = None,
               ink_l: float = 35.0, ink_chroma: float = 10.0, rows: list[float] | None = None) -> CallToolResult:
    """MEASURE the shape inside the outline: which part is where. Each picture is split into parts by the parts'
    own colours (each group's colour = the picture's median over the pixels the model gives that group, ink left
    out; every subject pixel then takes the nearest group colour, and ink lines and eyes take their surroundings').
    The model's nearest mesh per pixel, registered as outline_match registers, is compared with it. outline_match
    can pass while hair floats over the face or a face is narrower than its hair opening; this cannot. groups
    {name: [mesh, ...]} joins meshes the picture paints as one material (all hair shells); other meshes are their
    own group. Returns per view the agreement (share of subject pixels with the same group in both), each group's
    IoU, the largest confusions (picture says A, model shows B), and a sheet per view: the picture's parts, the
    model's parts, and where they disagree in the model's colour over the greyed picture. Ink is a pixel darker than
    ink_l and greyer than ink_chroma (a navy skirt is dark but coloured, so it stays a part). rows [top, bottom]
    measures one band of the figure, as fractions of the subject's height from its top (the head: [0, 0.22]).
    The rig must be at rest."""
    tmp_files = []
    try:
        refs, wanted = outline.check_request(references, views, 0.98)
        use = [v for v in wanted if v in refs]
        if not use: raise ValueError("no reference picture for the requested views")
        pm = _part_maps(object, refs, use, groups, work, also, ink_l, ink_chroma, tmp_files)
        names, gnames, group_of = pm["names"], pm["gnames"], pm["group_of"]
        out, sheets = {"status": "measured", "object": object, "groups": {g: [n for n in names if group_of[n] == g] for g in gnames}, "views": {}}, []
        out_dir = pm["out_dir"]; res = pm["res"]
        for v in use:
            m, gm, gd, rgb = (pm["views"][v][k] for k in ("m", "gm", "gd", "rgb"))
            subj = m | (gm >= 0)
            if rows:
                ys_, _ = np.nonzero(subj); top, bot = ys_.min(), ys_.max() + 1
                band = np.zeros_like(subj); band[top + int(rows[0] * (bot - top)):top + int(rows[1] * (bot - top))] = True
                subj &= band
            agree = float(((gd == gm) & subj).sum() / max(int(subj.sum()), 1))
            per = {}
            for gi, g in enumerate(gnames):
                a, b = gd == gi, gm == gi
                if a.any() or b.any():
                    per[g] = {"iou": round(float((a & b).sum() / max(int((a | b).sum()), 1)), 4),
                              "picture_px": int(a.sum()), "model_px": int(b.sum())}
            conf = {}
            wrong = subj & (gd != gm)
            pairs, counts = np.unique(np.stack([gd[wrong], gm[wrong]], 1), axis=0, return_counts=True)
            for (a_, b_), c_ in zip(pairs, counts):
                conf[f"{gnames[a_] if a_ >= 0 else 'background'} -> {gnames[b_] if b_ >= 0 else 'background'}"] = int(c_)
            out["views"][v] = {"agreement": round(agree, 4), "groups": per,
                               "confusions_px": dict(sorted(conf.items(), key=lambda kv: -kv[1])[:8]),
                               "registration": res["views"][v]["registration"]}
            paint = lambda g: np.where((g >= 0)[..., None], PART_COLOURS[np.clip(g, 0, None) % len(PART_COLOURS)], 255).astype(np.uint8)
            grey = (0.35 * rgb.mean(-1, keepdims=True) + 0.65 * 255).repeat(3, -1).astype(np.uint8)
            diff = np.where(wrong[..., None], paint(gm), grey).astype(np.uint8)
            ys, xs = np.nonzero(subj); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            row = [Image.fromarray(a[y0:y1, x0:x1]) for a in (paint(gd), paint(gm), diff)]
            cell = Image.new("RGB", (sum(r.width for r in row) + 16, row[0].height + 22), "white")
            dr = ImageDraw.Draw(cell); x = 0
            for r, t in zip(row, (f"{v} picture parts", "model parts", "disagree (model colour)")):
                cell.paste(r, (x, 22)); dr.text((x + 4, 4), t, fill=(0, 0, 0)); x += r.width + 8
            sheets.append(cell)
        out["legend"] = {g: "#%02x%02x%02x" % tuple(PART_COLOURS[i % len(PART_COLOURS)]) for i, g in enumerate(gnames)}
        sheet = Image.new("RGB", (max(s.width for s in sheets), sum(s.height for s in sheets)), "white"); y = 0
        for s in sheets: sheet.paste(s, (0, y)); y += s.height
        path = os.path.join(out_dir, f"part_match_{int(time.time() * 1000)}.png"); sheet.save(path)
        out["sheet_path"] = path
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    finally:
        for f in tmp_files:
            with contextlib.suppress(OSError): os.remove(f)
    return reply(out)


@mcp.tool()
def part_carve(object: str, references: dict[str, str], view: str, carve: str, where: str,
               groups: dict[str, list[str]] | None = None, passes: int = 3, rows: list[float] | None = None,
               work: int = 2048, also: list[str] | None = None, ink_l: float = 35.0, ink_chroma: float = 10.0) -> CallToolResult:
    """SCULPT by the picture's parts: delete faces of group `carve` (e.g. "hair") that are nearest the viewer in
    `view` where that picture shows group `where` (e.g. the skin mesh), so the model shows what the picture shows
    there: forehead between drawn strands instead of a solid fringe. Repeats up to `passes` times, because a shell
    behind the carved one (a scalp under the fringe) then becomes the nearest. rows [top, bottom] limits it to a band
    of the figure (fractions of its height from the top), e.g. [0, 0.22] for the head. Groups and segmentation as
    part_match. Strands survive wherever the picture draws `carve`; re-check the other views' outline_match after,
    since a carved shell may have formed another view's outline."""
    tmp_files, rounds = [], []
    try:
        refs, wanted = outline.check_request(references, [view], 0.98)
        v = wanted[0]
        if v not in refs: raise ValueError(f"no reference picture for {v}")
        pm = None
        for _ in range(max(1, int(passes))):
            fresh = _part_maps(object, refs, [v], groups, work, also, ink_l, ink_chroma, tmp_files)
            if pm is None: pm = fresh                     # the picture's parts come from the model before carving
            gn = fresh["gnames"]
            if carve not in gn or where not in gn: raise ValueError(f"groups are {gn}; carve and where must be two of them")
            gd = pm["views"][v]["gd"].copy()
            if pm["gnames"] != gn: raise ValueError("the meshes changed between passes")
            if rows:
                ys_, _ = np.nonzero(gd >= 0); top, bot = ys_.min(), ys_.max() + 1
                band = np.zeros(gd.shape, bool); band[top + int(rows[0] * (bot - top)):top + int(rows[1] * (bot - top))] = True
                gd[~band] = -1
            pic = os.path.join(fresh["out_dir"], f"carve_{v}_{int(time.time() * 1000)}.npy"); tmp_files.append(pic)
            np.save(pic, gd.astype(np.int16))
            meshes = [n for n in fresh["names"] if fresh["group_of"][n] == carve]
            r = call("part_carve", timeout=900, object=object, also=also or [], view=v, npy=fresh["spec"][v]["npy"],
                     box=fresh["spec"][v]["box"], picture=pic, where=gn.index(where), meshes=meshes)
            r.pop("ok", None); rounds.append(r)
            if sum(x.get("deleted_faces", 0) for x in r["meshes"].values()) == 0: break
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000], "rounds": rounds}, error=True)
    finally:
        for f in tmp_files:
            with contextlib.suppress(OSError): os.remove(f)
    return reply({"status": "carved", "view": view, "carve": carve, "where": where, "rounds": rounds})


def _paint_reference(path: str, out_dir: str, view: str, scale: int = 1) -> dict:
    """Full-resolution RGB for painting, alpha = outline_match's mask scaled up, saved as .npy. Only solid subject
    pixels keep their colour: the anti-aliased rim (half transparent, or half backdrop on a plain background) is
    replaced by the nearest solid colour, and that colour is bled past the subject, so no backdrop or white halo
    is painted onto surfaces at the picture's edge (a ribbon or hair tip on the outline). scale > 1 resamples the
    picture that many times larger (Lanczos) first: no new detail, but the texture samples a sharp edge instead of
    stretching each picture pixel bilinearly over several texels."""
    full = Image.open(path)
    if scale > 1:
        full = full.convert("RGBA").resize((full.width * scale, full.height * scale), Image.LANCZOS)
    small = outline.reference_mask(path, work=2 * outline.WORK)
    w, h = full.size
    mask = np.asarray(Image.fromarray(small.astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)) >= 128
    rgba = np.asarray(full.convert("RGBA"))
    solid = outline._erode(mask, scale)
    if (rgba[..., 3] < 128).mean() > 0.05:          # transparent cut-out: partly transparent pixels are rim too
        solid &= rgba[..., 3] >= 250
    rgb = projection.bleed(rgba[..., :3].astype(np.float64), solid, iterations=48 * scale)
    ys, xs = np.nonzero(mask)
    out = np.zeros((h, w, 4), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8); out[..., 3] = mask * 255
    npy = os.path.join(out_dir, f"paint_{view}_{int(time.time() * 1000)}.npy")
    np.save(npy, out)
    return {"npy": npy, "box": [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]}


# A picture's character must be at least this many pixels tall for a sharp painted texture (2K source art).
PICTURE_MIN_PX = 1800


@mcp.tool()
def project_paint(object: str, references: dict[str, str], views: list[str] | None = None, tex_size: int = 2048,
                  power: float = 6.0, min_cos: float = 0.12, min_cos_other: float = 0.35,
                  priority_views: list[str] | None = None,
                  priority_cos: float = 0.45, warp: bool = True, warp_sigma: float = 8.0, palette_de: float = 28.0,
                  palette_view: str = "", view_bias: dict[str, float] | None = None,
                  material: Literal["flat", "none"] = "flat",
                  targets: list[str] | None = None, also: list[str] | None = None, save_dir: str = "",
                  debug: Literal["", "owner"] = "", ref_scale: int = 1,
                  fill_colours: dict[str, str | list[str]] | None = None, underside_cos: float = 0.0,
                  flat_cos: list[float] | None = None) -> CallToolResult:
    """PAINT the reference pictures onto the model: every visible mesh under `object` (plus `also`) gets an image
    PROJ_<mesh> on its active UV map. references are the same straight-on pictures outline_match measures
    (FRONT, BACK, LEFT, RIGHT, TOP), registered onto the model as outline_match registers them, so run it only once
    the outline passes in those views. Per texel a view counts where the surface faces it (weight cos**power: higher
    = harder seams, less ghosting) and where a depth buffer of the whole character shows the texel is the nearest
    surface (no paint through arms or hair). warp bends each picture so its outline lands on the model's outline
    (moves spread inward over warp_sigma px; the largest is reported as warp_max_px): a picture drawing the arms or
    skirt a little wider than the model still paints arm on arm. priority_views (e.g. ["FRONT"]) own every texel
    they face at cos >= priority_cos, so a side picture cannot paint a second profile eye onto a flat cheek.
    palette_view (default: the first priority view) sets each mesh's colour list; other pictures' colours further
    than palette_de (CIE76) from it are dropped. Pick the view where the parts do not overlap (usually FRONT, arms
    clear of the skirt), so an arm drawn over the skirt in a side picture cannot paint the skirt; 0 turns this off.
    view_bias multiplies a view's weight (e.g. {"LEFT": 50}): where two pictures disagree about a surface angled
    between them, it moves the hand-over from 45 degrees toward the other view, trading likeness between the two.
    Views not in priority_views only paint surfaces they face at cos > min_cos_other: a picture seen nearly edge-on
    smears one row over many texels (stripes between the legs, on boot sides); those texels take the nearest
    well-painted colour instead.
    Texels no view sees take the colour of the nearest seen texel of the same mesh in 3D. Returns cross_view:
    CIEDE2000 between the two strongest views on every texel both see (delta_e_mean, p90, conflict_pct = share
    above 15): the pictures and the model disagreeing in 3D. material='flat' replaces each mesh's materials with one
    emission material showing the image unchanged (old materials keep a fake user); 'none' only writes the images.
    Leave out views whose picture shows another pose. Meshes without UVs and hair curves are skipped and listed.
    Painting changes colour only: banding or missing forms still fail visual_match's clay checks. debug='owner'
    paints every texel in the colour of the picture that won it (FRONT red, LEFT green, BACK blue, RIGHT yellow,
    TOP magenta, filled from neighbours grey) to find which picture put a stray mark somewhere; repaint after.
    ref_scale (1-4) resamples low-resolution pictures that many times larger before painting (sharper edges, no
    new detail); pair it with a larger tex_size. fill_colours ({mesh: "#rrggbb"}) gives the texels no picture paints
    on that mesh one flat colour (skin under the chin, shadow on hair undersides and inner hair shells) instead of
    copying the nearest painted texels, which smears whatever lies nearby into places seen only from below.
    underside_cos (0 = off) is the stricter floor for surfaces facing down (normal z < -0.5): no level picture
    shows an underside, and below this cos it only stretches the jaw line or the fringe's tips across it in
    streaks and blocks; those texels get the fill (pair with fill_colours). 0.5 suits a level picture set.
    flat_cos [lo, hi] is the cel look that holds from every angle: paint stays only where the winning picture saw
    the surface at cos >= hi (eyes, mouth, strand lines), blends below that into the mesh's flat tone, and every
    unseen texel takes the tone. The tone is the mesh's base colour, or its shadow where the surface faces down;
    both come from the median of the mesh's squarely seen paint without ink, unless fill_colours gives "#base" or
    ["#base", "#shadow"]. flat_tones in the result reports them. [0.45, 0.7] suits four level pictures."""
    spec = {}
    try:
        refs, wanted = outline.check_request(references, views, 0.98)
        use = [v for v in wanted if v in refs]
        if not use: raise ValueError("no reference picture for the requested views")
        out_dir = os.environ.get("BLENDER_LIVE_TMP") or os.path.join(HERE, ".scratch")
        os.makedirs(out_dir, exist_ok=True)
        rs = max(1, min(4, int(ref_scale)))
        spec = {v: _paint_reference(refs[v], out_dir, v, rs) for v in use}
        res = call("project_paint", timeout=1800, object=object, also=also or [], views=spec, tex_size=int(tex_size),
                   power=float(power), min_cos=float(min_cos), min_cos_other=float(min_cos_other),
                   priority_views=[str(v).upper() for v in priority_views or []],
                   priority_cos=float(priority_cos), warp=bool(warp), warp_sigma=float(warp_sigma),
                   palette_de=float(palette_de), palette_view=str(palette_view).upper(), material=material,
                   view_bias={str(k).upper(): float(v) for k, v in (view_bias or {}).items()},
                   targets=targets or [], save_dir=save_dir, debug=debug, fill_colours=fill_colours or {},
                   underside_cos=float(underside_cos), flat_cos=[float(c) for c in flat_cos or []])
    except Exception as exc:
        return reply({"status": "error", "detail": str(exc)[:3000]}, error=True)
    finally:
        for s in spec.values():
            with contextlib.suppress(OSError): os.remove(s["npy"])
    res.pop("ok", None)
    # the texture is never sharper than the pictures: say so when a picture is below 2K art
    pictures = {v: {"figure_px_tall": (s["box"][3] - s["box"][1]) // rs} for v, s in spec.items()}
    for p in pictures.values(): p["sharp_enough"] = p["figure_px_tall"] >= PICTURE_MIN_PX
    soft = sorted(v for v, p in pictures.items() if not p["sharp_enough"])
    out = {"status": "painted", "object": object, "pictures": pictures, **res}
    if soft:
        out["warning"] = (f"{', '.join(soft)}: character under {PICTURE_MIN_PX} px tall in the picture, so the "
                          "texture is soft at any tex_size; get 2K art (references/01, requirement 7)")
    return reply(out)


if __name__ == "__main__":
    mcp.run(transport="stdio")
