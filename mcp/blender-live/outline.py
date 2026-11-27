"""Outline measuring for outline_match: pure numpy + Pillow, no Blender, so it can be tested on its own.

A view is passed only when a real reference picture and a real model capture were both turned into outlines and
their overlap reached the threshold. Anything that cannot be measured honestly raises instead of scoring.
"""
from __future__ import annotations

from collections import deque

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
    """4-connected labels (0 = not in mask) and the label count."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32); n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]: continue
        n += 1; lab[y0, x0] = n; q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n; q.append((yy, xx))
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
        bg = None
        for i, m in enumerate(meds):      # the background is the colour at least three flat corners agree on
            agree = [j for j in range(4) if flat[j] and np.linalg.norm(meds[j] - m) <= 30]
            if flat[i] and len(agree) >= 3:
                bg = np.median(np.array([meds[j] for j in agree]), axis=0); break
        if bg is None:
            raise ValueError(f"{path}: the background is not plain (corner colours differ); cut the subject out first")
        bg_like = np.linalg.norm(rgb - bg, axis=2) <= 40
        bg_like[:band, :] = bg_like[-band:, :] = True; bg_like[:, :band] = bg_like[:, -band:] = True
        lab, _ = _components(bg_like)
        border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        candidate = ~np.isin(lab, border[border > 0])
        b = band + 1
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
