"""Outline measuring for outline_match: pure numpy + Pillow, no Blender, so it can be tested on its own.

A view is passed only when a real reference picture and a real model capture were both turned into outlines and
their overlap reached the threshold. Anything that cannot be measured honestly raises instead of scoring.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from projection import delta_e00, srgb_to_lab

FIVE = ("FRONT", "BACK", "LEFT", "RIGHT", "TOP")
THRESHOLD_MIN, THRESHOLD_MAX = 0.90, 1.0
WORK = 512           # pictures are reduced to at most this before masking
FIT = 512            # both outlines are placed on a FIT x FIT canvas before comparing
MAX_FILL = 0.90      # a subject covering more of its picture than this means the background was not found


def check_request(references: dict, views: list | None, threshold: float) -> tuple[dict, list]:
    """Upper-cased references and views, or ValueError for names outside the five views or a bad threshold."""
    refs = {str(k).upper(): v for k, v in (references or {}).items()}
    bad = [k for k in refs if k not in FIVE]
    if bad: raise ValueError(f"unknown view name(s) in references: {', '.join(bad)}; use {', '.join(FIVE)}")
    wanted = [str(v).upper() for v in (views or FIVE)]
    bad = [v for v in wanted if v not in FIVE]
    if bad: raise ValueError(f"unknown view name(s) in views: {', '.join(bad)}; use {', '.join(FIVE)}")
    if not (THRESHOLD_MIN <= float(threshold) <= THRESHOLD_MAX):
        raise ValueError(f"threshold {threshold} is outside {THRESHOLD_MIN}..{THRESHOLD_MAX}")
    return refs, list(dict.fromkeys(wanted))


def _components(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connected labels (0 = not in mask) and the label count via scanline-run Union-Find."""
    mask_b = np.asarray(mask, dtype=bool)
    h, w = mask_b.shape
    lab = np.zeros((h, w), np.int32)
    if h == 0 or w == 0 or not mask_b.any():
        return lab, 0
    padded = np.zeros((h, w + 2), dtype=np.uint8)
    padded[:, 1:-1] = mask_b
    mid = padded[:, 1:-1] == 1
    starts_y, starts_x = np.nonzero(mid & (padded[:, :-2] == 0))
    _, ends_x = np.nonzero(mid & (padded[:, 2:] == 0))
    sy = starts_y.tolist()
    sx = starts_x.tolist()
    ex = (ends_x + 1).tolist()
    n_runs = len(sy)
    parent = list(range(n_runs))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    prev_y = -2
    prev_lo = prev_hi = 0
    cur_lo = 0
    while cur_lo < n_runs:
        y = sy[cur_lo]
        cur_hi = cur_lo + 1
        while cur_hi < n_runs and sy[cur_hi] == y:
            cur_hi += 1
        if y == prev_y + 1:
            p, c = prev_lo, cur_lo
            while p < prev_hi and c < cur_hi:
                if ex[p] <= sx[c]:
                    p += 1
                elif ex[c] <= sx[p]:
                    c += 1
                else:
                    ra, rb = find(p), find(c)
                    if ra != rb:
                        if ra < rb:
                            parent[rb] = ra
                        else:
                            parent[ra] = rb
                    if ex[p] < ex[c]:
                        p += 1
                    elif ex[c] < ex[p]:
                        c += 1
                    else:
                        p += 1
                        c += 1
        prev_y, prev_lo, prev_hi = y, cur_lo, cur_hi
        cur_lo = cur_hi

    root_to_label: dict[int, int] = {}
    n = 0
    for i in range(n_runs):
        r = find(i)
        lbl = root_to_label.get(r)
        if lbl is None:
            n += 1
            lbl = n
            root_to_label[r] = lbl
        lab[sy[i], sx[i]:ex[i]] = lbl
    return lab, n


MIN_PART = 0.02     # in a reference, separate marks smaller than this share of the biggest part are dropped


def _drop_specks(mask: np.ndarray) -> np.ndarray:
    """Keep every separate part at least MIN_PART of the biggest one: a character can have parts that do not touch
    (a held prop, floating hair), but a signature or a speck of dirt is far smaller."""
    lab, n = _components(mask)
    if n <= 1: return mask
    sizes = np.bincount(lab.ravel())[1:]
    keep = np.nonzero(sizes >= MIN_PART * sizes.max())[0] + 1
    return np.isin(lab, keep)


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    """Background = the part of ~mask connected to the border; everything else is the subject."""
    lab, _ = _components(~mask)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return ~np.isin(lab, border[border > 0])


def _reduce(im: Image.Image, work: int = WORK) -> Image.Image:
    if max(im.size) > work:
        im = im.copy(); im.thumbnail((work, work), Image.LANCZOS)
    return im


def reference_mask(path: str, work: int = WORK) -> np.ndarray:
    """The subject in a reference picture: from transparency when the picture has real transparency, otherwise the
    region not connected to the border through background-coloured pixels. Separate marks under MIN_PART of the
    biggest part are dropped and holes are filled. Raises ValueError when the background cannot be found. The
    picture is first reduced to at most `work` pixels; outline scoring uses 2 x WORK so edges stay sub-pixel."""
    im = _reduce(Image.open(path), work)
    alpha = np.asarray(im.convert("RGBA"))[:, :, 3]
    transparent = alpha < 128
    if transparent.mean() > 0.05:                   # real transparency, not one stray pixel
        candidate = ~transparent
    else:
        rgb = np.asarray(im.convert("RGB"), np.float64)
        k = max(2, min(rgb.shape[:2]) // 50)
        band = max(2, min(rgb.shape[:2]) // 40)   # a thin frame around the picture is not the subject or the background
        inner = rgb[band:-band, band:-band]
        patches = [inner[:k, :k], inner[:k, -k:], inner[-k:, :k], inner[-k:, -k:]]
        meds = [np.median(p.reshape(-1, 3), axis=0) for p in patches]
        flat = [p.reshape(-1, 3).std(axis=0).max() <= 18 for p in patches]
        bg_field = None
        tol = 40.0
        for i, m in enumerate(meds):      # the background is the colour at least three flat corners agree on
            agree = [j for j in range(4) if flat[j] and np.linalg.norm(meds[j] - m) <= 30]
            if flat[i] and len(agree) >= 3:
                bg_field = np.median(np.array([meds[j] for j in agree]), axis=0)[None, None, :]
                break
        if bg_field is None and all(flat):
            top_d = float(np.linalg.norm(meds[0] - meds[1]))
            bot_d = float(np.linalg.norm(meds[2] - meds[3]))
            vert_d = float(np.linalg.norm(0.5 * (meds[0] + meds[1]) - 0.5 * (meds[2] + meds[3])))
            if top_d <= 25 and bot_d <= 25 and vert_d <= 90:
                left_strip = np.median(rgb[:, band:band + k], axis=1)
                right_strip = np.median(rgb[:, -band - k:-band], axis=1)
                lr_diff = np.linalg.norm(left_strip - right_strip, axis=1)
                if float(np.percentile(lr_diff, 95)) <= 20 and float(lr_diff.max()) <= 30:
                    bg_field = (0.5 * (left_strip + right_strip))[:, None, :]
                    tol = 22.0
        if bg_field is None:
            raise ValueError(f"{path}: the background is not plain (corner colours differ); cut the subject out first")
        bg_like = np.linalg.norm(rgb - bg_field, axis=2) <= tol
        unframed = (
            bg_like[0].mean() >= 0.9 and bg_like[-1].mean() >= 0.9
            and bg_like[:, 0].mean() >= 0.9 and bg_like[:, -1].mean() >= 0.9
        )
        if not unframed:
            bg_like[:band, :] = bg_like[-band:, :] = True
            bg_like[:, :band] = bg_like[:, -band:] = True
        lab, _ = _components(bg_like)
        border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        candidate = ~np.isin(lab, border[border > 0])
        b = 0 if unframed else band + 1
        if candidate[b].any() or candidate[-b - 1].any() or candidate[:, b].any() or candidate[:, -b - 1].any():
            raise ValueError(f"{path}: the background is not plain, or the subject is cut off at the picture's edge; "
                             "give it a plain background with space around the subject")
    if not candidate.any(): raise ValueError(f"{path}: no subject found")
    subject = _fill_holes(_drop_specks(candidate))
    if subject.mean() > MAX_FILL:
        raise ValueError(f"{path}: the subject fills {subject.mean():.0%} of the picture, so its background was not found; "
                         "give it a plain or transparent background with space around the subject")
    return subject


def check_model_mask(mask: np.ndarray, view: str) -> None:
    """A model capture must show the whole model with space around it."""
    if not mask.any(): raise ValueError(f"{view}: the model capture is empty")
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        raise ValueError(f"{view}: the model touches the edge of the capture, so part of it may be cut off")


COVERAGE_HALF = 188   # sRGB-encoded value of a pixel half covered by white on black (Standard view transform)


def model_coverage(grey: np.ndarray, view: str) -> np.ndarray:
    """Per-pixel coverage 0..1 of the model in a white-on-black Standard-view-transform capture (edge pixels are
    sRGB-encoded coverage, so they are linearised). Enclosed holes count as covered."""
    check_model_mask(grey >= 128, view)
    c = grey.astype(np.float64) / 255.0
    cov = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    solid = grey >= COVERAGE_HALF
    cov[_fill_holes(solid) & ~solid] = 1.0
    return np.clip(cov, 0.0, 1.0)


def model_mask(grey: np.ndarray, view: str) -> np.ndarray:
    """The model in a white-on-black Standard-view-transform capture: pixels at least half covered, holes filled."""
    return model_coverage(grey, view) >= 0.5


def fit(mask: np.ndarray, size: int = FIT) -> np.ndarray:
    """Crop to the subject and place it, uniformly scaled to touch two opposite sides minus one pixel, centred."""
    return fit_soft(mask.astype(np.float64), size) >= 0.5


def fit_soft(cov: np.ndarray, size: int = FIT) -> np.ndarray:
    """fit() for a 0..1 coverage image (box from the half-covered pixels), returning coverage, not a threshold, so
    edges keep their sub-pixel position."""
    ys, xs = np.nonzero(cov >= 0.5)
    if not len(ys): return np.zeros((size, size))
    crop = Image.fromarray(cov[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32))
    s = (size - 2) / max(crop.size)
    crop = crop.resize((max(1, round(crop.size[0] * s)), max(1, round(crop.size[1] * s))), Image.LANCZOS)
    canvas = np.zeros((size, size), np.float64)
    ox, oy = (size - crop.size[0]) // 2, (size - crop.size[1]) // 2
    canvas[oy:oy + crop.size[1], ox:ox + crop.size[0]] = np.asarray(crop)
    return np.clip(canvas, 0.0, 1.0)


def score(ref_masks: dict, model_masks: dict, wanted: list, threshold: float) -> dict:
    """Per-view results for `wanted`, plus summary flags. all_views_passed always means all FIVE views passed.
    model_masks may hold coverage (0..1) images (model_coverage); they are fitted with their edge coverage and cut
    at half coverage, so each model edge is placed once, to a fraction of a pixel."""
    views = {}
    for v in wanted:
        if v not in ref_masks:
            views[v] = {"status": "not_run", "reason": "no reference picture for this view"}; continue
        if v not in model_masks:
            views[v] = {"status": "not_run", "reason": "no model capture for this view"}; continue
        ref, model = fit(ref_masks[v]), fit_soft(model_masks[v].astype(np.float64)) >= 0.5
        reg = register(ref, model)
        model = transform(model, reg)
        union = int((ref | model).sum())
        iou = float((ref & model).sum()) / union if union else 0.0
        views[v] = {"status": "passed" if union and iou >= threshold else "failed", "iou": round(iou, 4),
                    "reference_only_pct": round(float((ref & ~model).sum()) / max(union, 1) * 100, 2),
                    "model_only_pct": round(float((model & ~ref).sum()) / max(union, 1) * 100, 2),
                    "registration": reg, "_ref": ref, "_model": model}
    counts = {k: sum(1 for r in views.values() if r["status"] == k) for k in ("passed", "failed", "not_run")}
    passed_five = [v for v in FIVE if views.get(v, {}).get("status") == "passed"]
    return {"threshold": threshold, "reference_pairs": reference_pairs(ref_masks), "views": views,
            "views_requested": list(wanted), **counts,
            "all_measured_passed": counts["failed"] == 0 and counts["passed"] > 0,
            "all_views_passed": len(passed_five) == len(FIVE),
            "unmeasured_of_five": [v for v in FIVE if views.get(v, {}).get("status") not in ("passed", "failed")],
            "measures": "outline overlap only"}


def _erode(mask: np.ndarray, radius: int) -> np.ndarray:
    m = mask.astype(bool, copy=True)
    for _ in range(max(0, int(radius))):
        if not m.any():
            break
        nxt = np.zeros_like(m)
        nxt[1:-1, 1:-1] = (
            m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
            & m[:-2, :-2] & m[:-2, 2:] & m[2:, :-2] & m[2:, 2:]
        )
        m = nxt
    return m


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    m = mask.astype(bool, copy=True)
    for _ in range(max(0, int(radius))):
        p = np.pad(m, 1, mode="constant", constant_values=False)
        m = (
            p[1:-1, 1:-1] | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
            | p[:-2, :-2] | p[:-2, 2:] | p[2:, :-2] | p[2:, 2:]
        )
    return m


def reference_rgb(path: str, work: int = WORK) -> np.ndarray:
    """RGB uint8 array reduced the same way as reference_mask so pixels align 1:1 with the mask."""
    im = _reduce(Image.open(path), work)
    rgba = np.asarray(im.convert("RGBA"))
    if (rgba[:, :, 3] < 128).mean() > 0.05:
        comp = np.full((rgba.shape[0], rgba.shape[1], 3), 255, dtype=np.uint8)
        alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
        comp = np.clip(rgba[:, :, :3] * alpha + comp * (1.0 - alpha), 0, 255).astype(np.uint8)
        return comp
    return np.asarray(im.convert("RGB"), dtype=np.uint8)


def fit_rgb(rgb: np.ndarray, mask: np.ndarray, size: int = FIT) -> tuple[np.ndarray, np.ndarray]:
    """Crop rgb and mask to mask's tight box, scale uniformly to size-2, centre on size x size, zero outside mask."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return np.zeros((size, size, 3), np.uint8), np.zeros((size, size), bool)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    crop_m = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8))
    crop_c = Image.fromarray(rgb[y0:y1, x0:x1].astype(np.uint8))
    s = (size - 2) / max(crop_m.size)
    nw, nh = max(1, round(crop_m.size[0] * s)), max(1, round(crop_m.size[1] * s))
    ox, oy = (size - nw) // 2, (size - nh) // 2
    can_m = Image.new("L", (size, size), 0)
    can_m.paste(crop_m.resize((nw, nh), Image.LANCZOS), (ox, oy))
    fm = np.asarray(can_m) >= 128
    can_c = Image.new("RGB", (size, size), (0, 0, 0))
    can_c.paste(crop_c.resize((nw, nh), Image.LANCZOS), (ox, oy))
    fc = np.asarray(can_c, dtype=np.uint8).copy()
    fc[~fm] = 0
    return fc, fm


REG_SHIFT = 4                                            # px on the FIT canvas, each way
REG_SCALES = tuple(round(1.0 + 0.0025 * k, 4) for k in range(-6, 7))     # 0.985 .. 1.015 in 0.25 % steps


def transform(arr: np.ndarray, reg: dict) -> np.ndarray:
    """Apply a registration (dx, dy px; scale about the canvas centre) to a FIT-canvas mask, grey or RGB image."""
    dx, dy, s = reg["dx"], reg["dy"], reg["scale"]
    if dx == 0 and dy == 0 and s == 1.0:
        return arr
    h, w = arr.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    coeffs = (1 / s, 0, cx - (cx + dx) / s, 0, 1 / s, cy - (cy + dy) / s)
    if arr.dtype == bool:
        im = Image.fromarray(arr.astype(np.uint8) * 255).transform((w, h), Image.AFFINE, coeffs, Image.BILINEAR)
        return np.asarray(im) >= 128
    if arr.dtype.kind == "f" and arr.ndim == 2:
        im = Image.fromarray(arr.astype(np.float32)).transform((w, h), Image.AFFINE, coeffs, Image.BILINEAR)
        return np.asarray(im).astype(np.float64)
    im = Image.fromarray(arr).transform((w, h), Image.AFFINE, coeffs, Image.BILINEAR)
    return np.asarray(im)


def register(ref: np.ndarray, model: np.ndarray) -> dict:
    """Small rigid search (shift up to REG_SHIFT px, scale within REG_SCALES) that best overlays the model outline on
    the reference after bounding-box fitting: one stray vertex or a trimmed tip moves the box and would otherwise
    misregister every pixel, like a printing plate out of register. The result is reported, never hidden."""
    best = {"dx": 0, "dy": 0, "scale": 1.0, "iou": -1.0}
    p = REG_SHIFT
    rp = np.pad(ref, p)
    shifts = sorted(((dx, dy) for dy in range(-p, p + 1) for dx in range(-p, p + 1)), key=lambda d: abs(d[0]) + abs(d[1]))
    for s in sorted(REG_SCALES, key=lambda s: abs(s - 1.0)):      # ties keep the smallest change
        m = transform(model, {"dx": 0, "dy": 0, "scale": s})
        for dx, dy in shifts:
            r = rp[p + dy:p + dy + ref.shape[0], p + dx:p + dx + ref.shape[1]]   # ref moved by -d == model by +d
            u = int((r | m).sum())
            iou = float((r & m).sum()) / u if u else 0.0
            if iou > best["iou"] + 1e-9:
                best = {"dx": dx, "dy": dy, "scale": s, "iou": iou}
    coarse = dict(best)                                       # then half-pixel steps around the best whole pixel
    for hy in (-0.5, 0.0, 0.5):
        for hx in (-0.5, 0.0, 0.5):
            if hx == 0.0 and hy == 0.0:
                continue
            cand = {"dx": coarse["dx"] + hx, "dy": coarse["dy"] + hy, "scale": coarse["scale"]}
            m = transform(model, cand)
            u = int((ref | m).sum())
            iou = float((ref & m).sum()) / u if u else 0.0
            if iou > best["iou"] + 1e-9:
                best = {**cand, "iou": iou}
    best["iou"] = round(best["iou"], 4)
    return best


def _ridges(d2: np.ndarray, axis: int, lo: int = 3, hi: int = 8) -> np.ndarray:
    """Keep a second-difference response only where another ridge sits lo..hi px away along axis: repeated bands
    survive, a single hem, belt or cuff line does not."""
    nb = np.zeros_like(d2)
    for k in range(lo, hi + 1):
        nb = np.maximum(nb, np.maximum(np.roll(d2, k, axis=axis), np.roll(d2, -k, axis=axis)))
    return np.minimum(d2, nb)


def banding_of(lum: np.ndarray, inner: np.ndarray) -> float:
    """Repeated horizontal-ridge energy over repeated vertical-ridge energy. lum (H, W) float, inner (H-2, W-2)."""
    if int(inner.sum()) < 64:
        return 0.0
    d2y = np.abs(lum[2:, 1:-1] - 2.0 * lum[1:-1, 1:-1] + lum[:-2, 1:-1]) * inner
    d2x = np.abs(lum[1:-1, 2:] - 2.0 * lum[1:-1, 1:-1] + lum[1:-1, :-2]) * inner
    return round(float(_ridges(d2y, 0)[inner].mean()) / max(float(_ridges(d2x, 1)[inner].mean()), 0.5), 4)


def banding_ratio(clay_grey: np.ndarray, mask: np.ndarray, size: int = FIT) -> float:
    """Untextured clay banding: repeated horizontal ridges (stacked slice-loft rings, stair steps) against repeated
    vertical ones inside the eroded silhouette. A smooth sculpt with garment hems scores well under 1.6; ring-stacked
    lofts score 5 and up. Single hem or belt lines are ignored because a ridge only counts when another one repeats
    it 3..8 px away."""
    rgb3 = np.repeat(clay_grey[:, :, None], 3, axis=2) if clay_grey.ndim == 2 else clay_grey
    fc, fm = fit_rgb(rgb3, mask, size=size)
    return banding_of(fc[:, :, 0].astype(np.float64), _erode(fm, 6)[1:-1, 1:-1])


def _box3(rgb: np.ndarray) -> np.ndarray:
    """3x3 box blur, so a line drawn 1 px off its painted place is not scored as a wrong colour."""
    f = np.pad(rgb.astype(np.float64), ((1, 1), (1, 1), (0, 0)), mode="edge")
    out = sum(f[dy:dy + rgb.shape[0], dx:dx + rgb.shape[1]] for dy in range(3) for dx in range(3)) / 9.0
    return np.clip(out, 0, 255).astype(np.uint8)


def colour_proof(ref_rgb: np.ndarray, mod_rgb: np.ndarray, region: np.ndarray, inks: int = 8) -> dict:
    """Print-style proof inside region: per-pixel CIEDE2000 (mean, p90, share within 5 and 10), plus the reference's
    `inks` dominant colours as hex with the model's mean colour over the same pixels and their delta E."""
    if int(region.sum()) < 32:
        return {"delta_e_mean": 100.0, "delta_e_p90": 100.0, "within_de5_pct": 0.0, "within_de10_pct": 0.0, "inks": []}
    rb, mb = _box3(ref_rgb), _box3(mod_rgb)
    de = delta_e00(srgb_to_lab(rb[region]), srgb_to_lab(mb[region]))
    px = rb[region]
    pal_img = Image.fromarray(px.reshape(-1, 1, 3)).quantize(colors=inks, method=Image.Quantize.MEDIANCUT)
    idx = np.asarray(pal_img).reshape(-1)
    rows = []
    for k in np.unique(idx):
        sel = idx == k
        share = float(sel.mean())
        if share < 0.01:
            continue
        rc = px[sel].mean(axis=0); mc = mb[region][sel].astype(np.float64).mean(axis=0)
        d = float(delta_e00(srgb_to_lab(np.round(rc).astype(np.uint8)), srgb_to_lab(np.round(mc).astype(np.uint8))))
        rows.append({"ref_hex": "#%02x%02x%02x" % tuple(int(round(x)) for x in rc),
                     "model_hex": "#%02x%02x%02x" % tuple(int(round(x)) for x in mc),
                     "share_pct": round(100 * share, 1), "delta_e": round(d, 2)})
    rows.sort(key=lambda r: -r["share_pct"])
    return {"delta_e_mean": round(float(de.mean()), 3), "delta_e_p90": round(float(np.percentile(de, 90)), 3),
            "within_de5_pct": round(100 * float((de <= 5).mean()), 2),
            "within_de10_pct": round(100 * float((de <= 10).mean()), 2), "inks": rows}


def interior_edge_f1(ref_rgb: np.ndarray, mod_rgb: np.ndarray, inner_mask: np.ndarray,
                     tol_px: int = 2, edge_thresh: float = 14.0) -> float:
    """tol_px-tolerant precision/recall F1 of interior structural colour/luminance edges inside inner_mask."""
    core = inner_mask[1:-1, 1:-1]
    if int(core.sum()) < 32:
        return 1.0

    def _edges(arr: np.ndarray) -> np.ndarray:
        f = arr.astype(np.float64)
        gx = 0.5 * np.max(np.abs(f[1:-1, 2:] - f[1:-1, :-2]), axis=2)
        gy = 0.5 * np.max(np.abs(f[2:, 1:-1] - f[:-2, 1:-1]), axis=2)
        return (np.hypot(gx, gy) >= edge_thresh) & core

    re_m, me_m = _edges(ref_rgb), _edges(mod_rgb)
    rn, mn = int(re_m.sum()), int(me_m.sum())
    if rn == 0 and mn == 0:
        return 1.0
    if rn == 0 or mn == 0:
        return 0.0
    rec = float((re_m & _dilate(me_m, tol_px)).sum()) / rn
    prec = float((me_m & _dilate(re_m, tol_px)).sum()) / mn
    return round(2.0 * prec * rec / max(prec + rec, 1e-9), 4)


def _masked_ssim(ref_rgb: np.ndarray, mod_rgb: np.ndarray, union_mask: np.ndarray) -> float:
    """Foreground-only luminance SSIM over union_mask (prevents blank background from inflating SSIM)."""
    if not union_mask.any():
        return 0.0
    rl = 0.299 * ref_rgb[:, :, 0] + 0.587 * ref_rgb[:, :, 1] + 0.114 * ref_rgb[:, :, 2]
    ml = 0.299 * mod_rgb[:, :, 0] + 0.587 * mod_rgb[:, :, 1] + 0.114 * mod_rgb[:, :, 2]
    k = np.ones(7, dtype=np.float64) / 7.0

    def _blur(z: np.ndarray) -> np.ndarray:
        h = np.apply_along_axis(lambda r: np.convolve(r, k, mode="same"), 1, z)
        return np.apply_along_axis(lambda c: np.convolve(c, k, mode="same"), 0, h)

    mx, my = _blur(rl), _blur(ml)
    sx = np.maximum(0.0, _blur(rl * rl) - mx * mx)
    sy = np.maximum(0.0, _blur(ml * ml) - my * my)
    sxy = _blur(rl * ml) - mx * my
    c1, c2 = 6.5025, 58.5225
    ssim_map = ((2.0 * mx * my + c1) * (2.0 * sxy + c2)) / ((mx * mx + my * my + c1) * (sx + sy + c2))
    return round(float(ssim_map[union_mask].mean()), 4)


def reference_pairs(ref_masks: dict) -> dict:
    """Do opposite pictures agree? An orthographic BACK outline is the FRONT outline mirrored, RIGHT is LEFT mirrored;
    their registered overlap is the most any single 3D model can reach in both views of the pair. Below the
    threshold, at most one view of the pair can pass however good the model is: the pictures disagree."""
    out = {}
    for a, b in (("FRONT", "BACK"), ("LEFT", "RIGHT")):
        if a in ref_masks and b in ref_masks:
            fa, fb = fit(ref_masks[a]), fit(np.asarray(ref_masks[b])[:, ::-1])
            out[f"{a}/{b}"] = register(fa, fb)["iou"]
    return out


def visual_score(ref_rgbs: dict, ref_masks: dict, mat_rgbs: dict, clay_greys: dict, model_masks: dict,
                 wanted: list, *, outline_threshold: float = 0.98, ssim_threshold: float = 0.78,
                 edge_f1_threshold: float = 0.60, max_delta_e: float = 10.0, max_banding: float = 1.60) -> dict:
    """Per-view 1:1 score after registering the model outline onto the reference (registration reported). Gates:
    outline IoU, masked foreground SSIM, interior edge F1, CIEDE2000 colour proof (mean delta E on the shared
    interior, print-style, with the reference's dominant inks as hex) and untextured clay banding. Whether drawn
    features exist as geometry (nose, folds, hair clumps) is not measured here: review the CLAY row by eye."""
    if not (THRESHOLD_MIN <= outline_threshold <= THRESHOLD_MAX):
        raise ValueError(f"outline_threshold must be between {THRESHOLD_MIN} and {THRESHOLD_MAX}, got {outline_threshold}")
    views = {}
    for v in wanted:
        if v not in ref_masks or v not in ref_rgbs:
            views[v] = {"status": "not_run", "reason": "no reference picture for this view"}
            continue
        if v not in model_masks or v not in mat_rgbs or v not in clay_greys:
            views[v] = {"status": "not_run", "reason": "no model capture for this view"}
            continue
        rc, rm = fit_rgb(ref_rgbs[v], ref_masks[v])
        cov = model_masks[v].astype(np.float64)        # a bool mask or model_coverage (0..1)
        solid = cov >= 0.5
        mc, _ = fit_rgb(mat_rgbs[v], solid)
        mm = fit_soft(cov) >= 0.5                       # the same model outline outline_match scores
        clay = clay_greys[v] if clay_greys[v].ndim == 3 else np.repeat(clay_greys[v][:, :, None], 3, axis=2)
        cc, _ = fit_rgb(clay, solid)
        band = banding_ratio(clay_greys[v], solid)
        reg = register(rm, mm)
        mm, mc, cc = transform(mm, reg), transform(mc, reg), transform(cc, reg)
        mc = mc.copy(); mc[~mm] = 0; cc = cc.copy(); cc[~mm] = 0
        union, inter = rm | mm, rm & mm
        u_cnt = int(union.sum())
        iou = round(float(inter.sum()) / u_cnt, 4) if u_cnt else 0.0
        inner = _erode(inter, 5)
        ssim = _masked_ssim(rc, mc, union)
        ef1 = interior_edge_f1(rc, mc, inner)
        proof = colour_proof(rc, mc, inner)

        failed_checks = []
        if iou < outline_threshold: failed_checks.append("iou")
        if ssim < ssim_threshold: failed_checks.append("ssim")
        if ef1 < edge_f1_threshold: failed_checks.append("interior_edge_f1")
        if proof["delta_e_mean"] > max_delta_e: failed_checks.append("delta_e")
        if band > max_banding: failed_checks.append("clay_banding_ratio")

        views[v] = {
            "status": "passed" if not failed_checks else "failed",
            "iou": iou, "ssim": ssim, "interior_edge_f1": ef1,
            "delta_e_mean": proof["delta_e_mean"], "delta_e_p90": proof["delta_e_p90"],
            "within_de5_pct": proof["within_de5_pct"], "within_de10_pct": proof["within_de10_pct"],
            "clay_banding_ratio": band,
            "inks": proof["inks"], "registration": reg, "failed_checks": failed_checks,
            "_ref_rgb": rc, "_mat_rgb": mc, "_clay_rgb": cc, "_union": union,
        }
    counts = {k: sum(1 for r in views.values() if r["status"] == k) for k in ("passed", "failed", "not_run")}
    passed_five = [v for v in FIVE if views.get(v, {}).get("status") == "passed"]
    return {
        "thresholds": {"outline_threshold": outline_threshold, "ssim_threshold": ssim_threshold,
                       "edge_f1_threshold": edge_f1_threshold, "max_delta_e": max_delta_e,
                       "max_banding": max_banding},
        "reference_pairs": reference_pairs(ref_masks),
        "views": views,
        "views_requested": list(wanted),
        **counts,
        "all_measured_passed": counts["failed"] == 0 and counts["passed"] > 0,
        "all_views_passed": len(passed_five) == len(FIVE),
        "unmeasured_of_five": [v for v in FIVE if views.get(v, {}).get("status") not in ("passed", "failed")],
        "measures": "outline IoU + SSIM + interior edge F1 + CIEDE2000 colour proof + clay banding",
    }


def missing_texture_pct(mat_rgb: np.ndarray, mask: np.ndarray) -> float:
    """Share of the model's pixels in Blender's missing-image magenta."""
    if not mask.any():
        return 0.0
    f = mat_rgb.astype(np.int32)
    pink = (f[..., 0] > 200) & (f[..., 1] < 80) & (f[..., 2] > 200)
    return round(100.0 * float((pink & mask).sum()) / int(mask.sum()), 3)


# Rows of a standing figure's silhouette that count as head and legs for three_quarter_check (fractions of the
# silhouette height from the top and from the bottom); the rest is body.
HEAD_FRAC, LEGS_FRAC = 0.20, 0.30
# Two pictures that both fit the model still differ in drawing style: regions of the Ghibli test character the fixes
# never touched measured CIEDE2000 5-10 between neighbouring pictures; its double face measured 17-24 and its hair
# flap 17 (head, 2048 px). 12 sits just above the style-only spread.
THREE_QUARTER_MAX_DE = 12.0


def _not_painted(rgb: np.ndarray) -> np.ndarray:
    """Pixels showing the 'this picture does not paint here' magenta (or Blender's missing-image magenta)."""
    f = rgb.astype(np.int32)
    return (f[..., 0] > 180) & (f[..., 1] < 110) & (f[..., 2] > 180)


def consistency_score(mat_a: np.ndarray, mat_b: np.ndarray, sil: np.ndarray, label: str,
                      max_delta_e: float = THREE_QUARTER_MAX_DE, min_cover: float = 0.03) -> dict:
    """Two renders of the model from one in-between angle, one painted only from picture A, one only from picture B.
    Where both pictures paint (2 px inside), a model that fits both shows the same colours in both (CIEDE2000 mean,
    3x3 box); a feature the pictures put on different surfaces (a side eye on the cheek, hair painted on bare skin)
    raises it. Scored per region (head, body, legs), so a wrong face is not averaged away by a large skirt; regions
    both pictures cover on less than min_cover of their pixels are reported as not covered, not passed.
    conflict_pct: share of those pixels with delta E above 20 (where to look on the sheet)."""
    m = model_mask(sil, label)
    both = _erode(m & ~_not_painted(mat_a) & ~_not_painted(mat_b), 2)
    ys = np.nonzero(m)[0]
    y0, y1 = int(ys.min()), int(ys.max()); h = y1 - y0 + 1
    rows = np.arange(m.shape[0])[:, None]
    regions = {"head": rows < y0 + HEAD_FRAC * h, "legs": rows > y1 - LEGS_FRAC * h}
    regions["body"] = ~regions["head"] & ~regions["legs"]
    ab, bb = _box3(mat_a), _box3(mat_b)
    de_map = np.zeros(m.shape)
    if both.any():
        de_map[both] = delta_e00(srgb_to_lab(ab[both]), srgb_to_lab(bb[both]))
    out, failed = {}, []
    for name, reg in regions.items():
        reg = np.broadcast_to(reg, m.shape)
        r = both & reg
        cover = float(r.sum()) / max(int((m & reg).sum()), 1)
        if cover < min_cover or int(r.sum()) < 64:
            out[name] = {"cover_pct": round(100 * cover, 1), "status": "not covered"}
            continue
        de = float(de_map[r].mean())
        bad = de > max_delta_e
        if bad: failed.append(f"{name}.delta_e")
        out[name] = {"cover_pct": round(100 * cover, 1), "delta_e_mean": round(de, 2),
                     "conflict_pct": round(100 * float((de_map[r] > 20).mean()), 1),
                     "status": "failed" if bad else "passed"}
    return {"regions": out, "status": "failed" if failed else "passed", "failed_gates": failed,
            "both_painted": both, "delta_e_map": de_map}


def orbit_score(shots: list, max_banding: float = 1.60, max_missing_pct: float = 0.5) -> dict:
    """Reference-free surface checks from every orbit angle: clay banding and missing-texture magenta. shots items:
    {azimuth, elevation, sil (grey), clay (grey), mat (RGB)}. No likeness is claimed: there is no picture to compare
    an in-between angle with."""
    rows = []
    for s in shots:
        m = model_mask(s["sil"], f"az {s['azimuth']:g} el {s['elevation']:g}")
        band = banding_ratio(s["clay"], m)
        miss = missing_texture_pct(s["mat"], m)
        failed = (["clay_banding_ratio"] if band > max_banding else []) + (["missing_texture"] if miss > max_missing_pct else [])
        rows.append({"azimuth": s["azimuth"], "elevation": s["elevation"], "clay_banding_ratio": band,
                     "missing_texture_pct": miss, "status": "failed" if failed else "passed", "failed_checks": failed})
    return {"angles": rows, "passed": sum(r["status"] == "passed" for r in rows),
            "failed": sum(r["status"] == "failed" for r in rows),
            "thresholds": {"max_banding": max_banding, "max_missing_pct": max_missing_pct},
            "measures": "surface quality from every angle (clay banding, missing textures); not likeness"}
