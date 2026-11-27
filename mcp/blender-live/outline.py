"""Outline measuring for outline_match: pure numpy + Pillow, no Blender, so it can be tested on its own.

A view is passed only when a real reference picture and a real model capture were both turned into outlines and
their overlap reached the threshold. Anything that cannot be measured honestly raises instead of scoring.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

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


def _reduce(im: Image.Image) -> Image.Image:
    if max(im.size) > WORK:
        im = im.copy(); im.thumbnail((WORK, WORK), Image.LANCZOS)
    return im


def reference_mask(path: str) -> np.ndarray:
    """The subject in a reference picture: from transparency when the picture has real transparency, otherwise the
    region not connected to the border through background-coloured pixels. Separate marks under MIN_PART of the
    biggest part are dropped and holes are filled. Raises ValueError when the background cannot be found."""
    im = _reduce(Image.open(path))
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


def model_mask(grey: np.ndarray, view: str) -> np.ndarray:
    m = grey >= 128
    check_model_mask(m, view)
    return _fill_holes(m)          # every part of the model counts, however small


def fit(mask: np.ndarray, size: int = FIT) -> np.ndarray:
    """Crop to the subject and place it, uniformly scaled to touch two opposite sides minus one pixel, centred."""
    ys, xs = np.nonzero(mask)
    if not len(ys): return np.zeros((size, size), bool)
    crop = Image.fromarray((mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1] * 255).astype(np.uint8))
    s = (size - 2) / max(crop.size)
    crop = crop.resize((max(1, round(crop.size[0] * s)), max(1, round(crop.size[1] * s))), Image.LANCZOS)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(crop, ((size - crop.size[0]) // 2, (size - crop.size[1]) // 2))
    return np.asarray(canvas) >= 128


def score(ref_masks: dict, model_masks: dict, wanted: list, threshold: float) -> dict:
    """Per-view results for `wanted`, plus summary flags. all_views_passed always means all FIVE views passed."""
    views = {}
    for v in wanted:
        if v not in ref_masks:
            views[v] = {"status": "not_run", "reason": "no reference picture for this view"}; continue
        if v not in model_masks:
            views[v] = {"status": "not_run", "reason": "no model capture for this view"}; continue
        ref, model = fit(ref_masks[v]), fit(model_masks[v])
        union = int((ref | model).sum())
        iou = float((ref & model).sum()) / union if union else 0.0
        views[v] = {"status": "passed" if union and iou >= threshold else "failed", "iou": round(iou, 4),
                    "reference_only_pct": round(float((ref & ~model).sum()) / max(union, 1) * 100, 2),
                    "model_only_pct": round(float((model & ~ref).sum()) / max(union, 1) * 100, 2),
                    "_ref": ref, "_model": model}
    counts = {k: sum(1 for r in views.values() if r["status"] == k) for k in ("passed", "failed", "not_run")}
    passed_five = [v for v in FIVE if views.get(v, {}).get("status") == "passed"]
    return {"threshold": threshold, "views": views, "views_requested": list(wanted), **counts,
            "all_measured_passed": counts["failed"] == 0 and counts["passed"] > 0,
            "all_views_passed": len(passed_five) == len(FIVE),
            "unmeasured_of_five": [v for v in FIVE if views.get(v, {}).get("status") not in ("passed", "failed")],
            "measures": "outline overlap only"}
