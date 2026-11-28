"""Pure-numpy helpers for multi-view orthographic projection painting (no bpy, so they are unit-testable).

project_paint in sculpt_cmds.py uses them: rasterize the character's triangles into a per-view depth buffer,
rasterize each mesh's UV triangles into texels, look every texel up in each reference picture it faces and can be
seen from, and fill the texels no view reached with push-pull so seams and hidden areas carry nearby colour.
"""
import numpy as np

# Blender axis views: (towards-viewer, screen-right, screen-up) as world unit vectors.
VIEW_AXES = {
    "FRONT": ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
    "BACK": ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
    "RIGHT": ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "LEFT": ((-1, 0, 0), (0, -1, 0), (0, 0, 1)),
    "TOP": ((0, 0, 1), (1, 0, 0), (0, 1, 0)),
}


def view_coords(points: np.ndarray, view: str) -> np.ndarray:
    """(n, 3) world points -> (n, 3): screen-right, screen-up, depth (larger = nearer the viewer)."""
    toward, right, up = (np.asarray(a, np.float64) for a in VIEW_AXES[view])
    return np.stack([points @ right, points @ up, points @ toward], axis=-1)


def fit_map(model_box, ref_box):
    """Map screen (right, up) metres to reference pixels (x right, y down) the way outline.fit_rgb aligns pictures:
    tight boxes centred on each other, one uniform scale set by the longer side. Boxes: (x0, y0, x1, y1) with
    model y up and reference y down; returns (scale, (mcx, mcy), (rcx, rcy))."""
    mx0, my0, mx1, my1 = (float(v) for v in model_box)
    rx0, ry0, rx1, ry1 = (float(v) for v in ref_box)
    m_side = max(mx1 - mx0, my1 - my0)
    if m_side <= 0:
        raise ValueError("model box is empty")
    scale = max(rx1 - rx0, ry1 - ry0) / m_side
    return scale, ((mx0 + mx1) / 2, (my0 + my1) / 2), ((rx0 + rx1) / 2, (ry0 + ry1) / 2)


def to_ref_px(sx, sy, mapping):
    """Screen metres (right, up) -> reference pixel coordinates (x, y down), continuous."""
    scale, (mcx, mcy), (rcx, rcy) = mapping
    return rcx + (sx - mcx) * scale, rcy - (sy - mcy) * scale


def raster(tri_xy: np.ndarray, width: int, height: int, chunk: int = 16384, max_px: int = 1 << 20,
           budget: int = 1 << 20):
    """Rasterize (n, 3, 2) triangles given in pixel units (x right, y down; pixel i covers [i, i+1)).
    Yields (tri_index, px, py, bary) per batch, bary (m, 3), for every pixel centre inside or on a triangle.
    Batches hold about `budget` candidate pixels so large UV islands never spike memory. Triangles whose box
    exceeds max_px pixels are skipped (degenerate or off-scale)."""
    tri_xy = np.asarray(tri_xy, np.float64)
    n = len(tri_xy)
    for s0 in range(0, n, chunk):
        t_all = tri_xy[s0:s0 + chunk]
        lo, hi = t_all.min(axis=1), t_all.max(axis=1)
        x0a = np.clip(np.ceil(lo[:, 0] - 0.5), 0, width).astype(np.int64)
        x1a = np.clip(np.floor(hi[:, 0] - 0.5), -1, width - 1).astype(np.int64)
        y0a = np.clip(np.ceil(lo[:, 1] - 0.5), 0, height).astype(np.int64)
        y1a = np.clip(np.floor(hi[:, 1] - 0.5), -1, height - 1).astype(np.int64)
        wa, ha = x1a - x0a + 1, y1a - y0a + 1
        cnt_a = np.where((wa > 0) & (ha > 0), wa * ha, 0)
        cnt_a[cnt_a > max_px] = 0
        cuts = np.searchsorted(np.cumsum(cnt_a), np.arange(budget, int(cnt_a.sum()) + budget, budget), side="right")
        lo_i = 0
        for hi_i in list(dict.fromkeys(int(c) for c in cuts)) + [len(t_all)]:
            hi_i = max(hi_i, lo_i + 1)
            if lo_i >= len(t_all): break
            sl = slice(lo_i, hi_i); s = s0 + lo_i; lo_i = hi_i
            t, x0, y0, w, cnt = t_all[sl], x0a[sl], y0a[sl], wa[sl], cnt_a[sl]
            total = int(cnt.sum())
            if total == 0:
                continue
            ti = np.repeat(np.arange(len(t)), cnt)
            start = np.repeat(np.cumsum(cnt) - cnt, cnt)
            local = np.arange(total) - start
            px = x0[ti] + local % w[ti]
            py = y0[ti] + local // w[ti]
            cx, cy = px + 0.5, py + 0.5
            a, b, c = t[ti, 0], t[ti, 1], t[ti, 2]
            den = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1.0)
            l0 = ((b[:, 1] - c[:, 1]) * (cx - c[:, 0]) + (c[:, 0] - b[:, 0]) * (cy - c[:, 1])) / den
            l1 = ((c[:, 1] - a[:, 1]) * (cx - c[:, 0]) + (a[:, 0] - c[:, 0]) * (cy - c[:, 1])) / den
            l2 = 1.0 - l0 - l1
            inside = ok & (l0 >= -1e-7) & (l1 >= -1e-7) & (l2 >= -1e-7)
            if inside.any():
                yield s + ti[inside], px[inside], py[inside], np.stack([l0, l1, l2], axis=1)[inside]


def depth_buffer(tri_screen: np.ndarray, mapping, width: int, height: int) -> np.ndarray:
    """Max-depth (nearest) buffer over (n, 3, 3) triangles in screen (right, up, depth) metres."""
    zbuf = np.full(height * width, -np.inf)
    rx, ry = to_ref_px(tri_screen[..., 0], tri_screen[..., 1], mapping)
    xy = np.stack([rx, ry], axis=-1)
    for ti, px, py, bary in raster(xy, width, height):
        z = (bary * tri_screen[ti, :, 2]).sum(axis=1)
        np.maximum.at(zbuf, py * width + px, z)
    return zbuf.reshape(height, width)


def label_buffer(tri_screen: np.ndarray, tri_label: np.ndarray, mapping, width: int, height: int) -> np.ndarray:
    """(height, width) int32: the label of the nearest triangle at every pixel, -1 where none covers it."""
    zbuf = depth_buffer(tri_screen, mapping, width, height).ravel()
    out = np.full(height * width, -1, np.int32)
    rx, ry = to_ref_px(tri_screen[..., 0], tri_screen[..., 1], mapping)
    xy = np.stack([rx, ry], axis=-1)
    for ti, px, py, bary in raster(xy, width, height):
        z = (bary * tri_screen[ti, :, 2]).sum(axis=1)
        at = py * width + px
        top = z >= zbuf[at] - 1e-9
        out[at[top]] = tri_label[ti[top]]
    return out.reshape(height, width)


def sample_bilinear(img: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """img (H, W, C) float; continuous pixel coords (pixel centres at i + 0.5), clamped at the border."""
    h, w = img.shape[:2]
    fx = np.clip(x - 0.5, 0, w - 1)
    fy = np.clip(y - 0.5, 0, h - 1)
    x0 = np.floor(fx).astype(np.int64); y0 = np.floor(fy).astype(np.int64)
    x1 = np.minimum(x0 + 1, w - 1); y1 = np.minimum(y0 + 1, h - 1)
    ax = (fx - x0)[:, None]; ay = (fy - y0)[:, None]
    top = img[y0, x0] * (1 - ax) + img[y0, x1] * ax
    bot = img[y1, x0] * (1 - ax) + img[y1, x1] * ax
    return top * (1 - ay) + bot * ay


def bleed(rgb: np.ndarray, mask: np.ndarray, iterations: int = 24, return_mask: bool = False):
    """Copy foreground colour outward across the background so edge samples never pick up the backdrop (and UV
    islands get their own edge colour in their gutter). With return_mask, also the grown mask."""
    out = rgb.astype(np.float64).copy()
    have = mask.astype(bool).copy()
    for _ in range(iterations):
        if have.all():
            break
        acc = np.zeros_like(out); cnt = np.zeros(have.shape)
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            sh = np.roll(np.roll(have, dy, 0), dx, 1)
            acc += np.roll(np.roll(out, dy, 0), dx, 1) * sh[..., None]
            cnt += sh
        grow = (~have) & (cnt > 0)
        out[grow] = acc[grow] / cnt[grow, None]
        have |= grow
    return (out, have) if return_mask else out


def push_pull(rgb: np.ndarray, weight: np.ndarray) -> np.ndarray:
    """Fill texels with weight 0 from a weighted mip pyramid (push-pull). rgb (H, W, 3), weight (H, W) >= 0."""
    w = weight.astype(np.float64)
    levels = [(rgb.astype(np.float64) * w[..., None], w)]
    while min(levels[-1][1].shape) > 1:
        c, ww = levels[-1]
        h, wd = ww.shape
        h2, w2 = h // 2 * 2, wd // 2 * 2
        if h2 == 0 or w2 == 0:
            break
        c = c[:h2, :w2]; ww = ww[:h2, :w2]
        c = c.reshape(h2 // 2, 2, w2 // 2, 2, 3).sum(axis=(1, 3))
        ww = ww.reshape(h2 // 2, 2, w2 // 2, 2).sum(axis=(1, 3))
        levels.append((c, ww))
    col = levels[-1][0] / np.maximum(levels[-1][1], 1e-12)[..., None]
    for c, ww in reversed(levels[:-1]):
        h, wd = ww.shape
        up = np.repeat(np.repeat(col, 2, axis=0), 2, axis=1)
        up = np.pad(up, ((0, max(0, h - up.shape[0])), (0, max(0, wd - up.shape[1])), (0, 0)), mode="edge")[:h, :wd]
        have = ww > 1e-12
        col = np.where(have[..., None], c / np.maximum(ww, 1e-12)[..., None], up)
    return col


def distance_field(mask: np.ndarray) -> np.ndarray:
    """Signed Euclidean distance in pixels to the mask's boundary pixels (positive outside, negative inside).
    Exact and separable: per column the distance to the nearest boundary pixel, then per row the minimum of
    dx^2 + that^2 over columns, in row blocks of bounded memory. O(H * W^2), a second or two for outline masks."""
    m = mask.astype(bool)
    h, w = m.shape
    p = np.pad(m, 1, mode="constant")
    edge = m & ~(p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
    if not edge.any():
        return np.full((h, w), float(h + w)) * np.where(m, -1.0, 1.0)
    g = np.where(edge, 0.0, float(h + w))
    for y in range(1, h):
        np.minimum(g[y], g[y - 1] + 1.0, out=g[y])
    for y in range(h - 2, -1, -1):
        np.minimum(g[y], g[y + 1] + 1.0, out=g[y])
    g2 = g * g
    dx2 = (np.arange(w)[:, None] - np.arange(w)[None, :]).astype(np.float64) ** 2
    d2 = np.empty((h, w))
    rows = max(1, (8 << 20) // max(w * w, 1))              # ~64 MB per block
    for y in range(0, h, rows):
        d2[y:y + rows] = (dx2[None] + g2[y:y + rows, None, :]).min(axis=2)
    d = np.sqrt(d2)
    return np.where(m, -d, d)


def refit_mapping(mapping, model_mask: np.ndarray, ref_box):
    """Re-centre and re-scale a mapping on the model's drawn coverage instead of its vertex bounds, as outline_match
    fits the captured silhouette: a hair tip or ribbon corner thinner than a pixel stretches the vertex box but not
    the picture of the model, and would leave every outline a fraction of a pixel too fat or thin."""
    ys, xs = np.nonzero(model_mask)
    if not len(ys):
        return mapping
    scale, (mcx, mcy), (rcx, rcy) = mapping
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    sx = mcx + ((x0 + x1) / 2 - rcx) / scale
    sy = mcy - ((y0 + y1) / 2 - rcy) / scale
    side_m = max(x1 - x0, y1 - y0) / scale
    bx0, by0, bx1, by1 = (float(v) for v in ref_box)
    return max(bx1 - bx0, by1 - by0) / side_m, (sx, sy), ((bx0 + bx1) / 2, (by0 + by1) / 2)


def register_mapping(mapping, ref_mask: np.ndarray, model_mask: np.ndarray, shift: int = 4,
                     scales=tuple(round(1.0 + 0.0025 * k, 4) for k in range(-6, 7))):
    """Refine a fit_map mapping by the small shift/scale (about the picture centre) that best overlays model_mask
    (the model's coverage drawn with `mapping`) on ref_mask: the same registration outline_match reports, so moves
    and paint land where the measurement looks. Large masks search at half size first, then refine around the
    best. Returns (mapping, {"dx", "dy", "scale", "iou"})."""
    steps = register_mapping_steps(mapping, ref_mask, model_mask, shift, scales)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def register_mapping_steps(mapping, ref_mask: np.ndarray, model_mask: np.ndarray, shift: int = 4,
                           scales=tuple(round(1.0 + 0.0025 * k, 4) for k in range(-6, 7))):
    """register_mapping as a generator that yields after each trial scale (a long search on a big picture stays
    responsive when a caller runs it in slices); its return value is register_mapping's result."""
    scales = sorted(scales, key=lambda s: abs(s - 1.0))      # ties keep the smallest change

    def search(ref, mod, shifts, scl, unit=1.0):
        h, w = ref.shape
        cy, cx = h / 2.0, w / 2.0
        yy, xx = np.mgrid[:h, :w]
        best = (-1.0, 0, 0, 1.0)
        for s in scl:
            for dx, dy in sorted(shifts, key=lambda d: abs(d[0]) + abs(d[1])):
                sy = np.clip(np.round((yy + 0.5 - cy - dy / unit) / s + cy - 0.5).astype(np.int64), 0, h - 1)
                sx = np.clip(np.round((xx + 0.5 - cx - dx / unit) / s + cx - 0.5).astype(np.int64), 0, w - 1)
                m = mod[sy, sx]
                u = int((m | ref).sum())
                iou = float((m & ref).sum()) / u if u else 0.0
                if iou > best[0] + 1e-9:
                    best = (iou, dx, dy, s)
            yield
        return best

    grid = [(dx, dy) for dy in range(-shift, shift + 1) for dx in range(-shift, shift + 1)]
    if ref_mask.size > 200_000:
        _, cdx, cdy, cs = yield from search(ref_mask[::2, ::2], model_mask[::2, ::2],
                                            [d for d in grid if d[0] % 2 == 0 and d[1] % 2 == 0], scales, unit=2.0)
        near_s = sorted({s for s in scales if abs(s - cs) <= 0.0026}, key=lambda s: abs(s - 1.0))
        near = [(dx, dy) for dx, dy in grid if abs(dx - cdx) <= 1 and abs(dy - cdy) <= 1]
        best = yield from search(ref_mask, model_mask, near, near_s)
    else:
        best = yield from search(ref_mask, model_mask, grid, scales)
    iou, dx, dy, s = best
    h, w = ref_mask.shape
    cy, cx = h / 2.0, w / 2.0
    scale, (mcx, mcy), (rcx, rcy) = mapping
    return (scale * s, (mcx, mcy), (cx + s * (rcx - cx) + dx, cy + s * (rcy - cy) + dy)), \
        {"dx": dx, "dy": dy, "scale": s, "iou": round(iou, 4)}


def _blur(z: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur over the first two axes (edge-padded)."""
    r = max(1, int(round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    pad = [(r, r), (0, 0)] + [(0, 0)] * (z.ndim - 2)
    zp = np.pad(z, pad, mode="edge")
    z = sum(k[i] * zp[i:i + z.shape[0]] for i in range(2 * r + 1))
    pad = [(0, 0), (r, r)] + [(0, 0)] * (z.ndim - 2)
    zp = np.pad(z, pad, mode="edge")
    return sum(k[i] * zp[:, i:i + z.shape[1]] for i in range(2 * r + 1))


def smooth_field(acc: np.ndarray, cnt: np.ndarray, sigma: float) -> np.ndarray:
    """Normalised convolution of sparse 2D moves: acc (H, W, 2) summed moves, cnt (H, W) how many. Near samples the
    field is their local average; it fades to zero within about two sigma of the nearest sample."""
    a = _blur(acc, sigma); c = _blur(cnt, sigma)
    near = _blur((cnt > 0).astype(np.float64), sigma)
    fade = np.clip(near / max(near.max(), 1e-12) * 8.0, 0, 1)
    return a / np.maximum(c, 1e-9)[..., None] * fade[..., None]


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """uint8 sRGB (..., 3) -> CIELAB (D65)."""
    c = rgb.astype(np.float64) / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                        [0.0193339, 0.1191920, 0.9503041]]).T
    xyz /= np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e00(lab1: np.ndarray, lab2: np.ndarray) -> np.ndarray:
    """CIEDE2000 colour difference, the print-proofing standard: ~1 is a just-noticeable difference."""
    L1, a1, b1 = lab1[..., 0], lab1[..., 1], lab1[..., 2]
    L2, a2, b2 = lab2[..., 0], lab2[..., 1], lab2[..., 2]
    cbar = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(cbar ** 7 / (cbar ** 7 + 25.0 ** 7)))
    a1p, a2p = a1 * (1 + g), a2 * (1 + g)
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    dLp, dCp = L2 - L1, c2p - c1p
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(c1p * c2p == 0, 0, dh)
    dHp = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh) / 2)
    Lbp, Cbp = (L1 + L2) / 2, (c1p + c2p) / 2
    hsum = h1p + h2p
    hbp = np.where(c1p * c2p == 0, hsum,
                   np.where(np.abs(h1p - h2p) <= 180, hsum / 2, np.where(hsum < 360, (hsum + 360) / 2, (hsum - 360) / 2)))
    t = (1 - 0.17 * np.cos(np.radians(hbp - 30)) + 0.24 * np.cos(np.radians(2 * hbp))
         + 0.32 * np.cos(np.radians(3 * hbp + 6)) - 0.20 * np.cos(np.radians(4 * hbp - 63)))
    sl = 1 + 0.015 * (Lbp - 50) ** 2 / np.sqrt(20 + (Lbp - 50) ** 2)
    sc, sh = 1 + 0.045 * Cbp, 1 + 0.015 * Cbp * t
    rt = (-2 * np.sqrt(Cbp ** 7 / (Cbp ** 7 + 25.0 ** 7))
          * np.sin(np.radians(60 * np.exp(-(((hbp - 275) / 25) ** 2)))))
    return np.sqrt((dLp / sl) ** 2 + (dCp / sc) ** 2 + (dHp / sh) ** 2 + rt * (dCp / sc) * (dHp / sh))


def de_hist_stats(hist: np.ndarray) -> dict:
    """Summary of a 0..100 (1-wide bins, last = 100+) histogram of CIEDE2000 values between the two strongest views
    at each texel: how well the reference pictures and the model agree in 3D. Two pictures that disagree about one
    surface point are plates out of register: wrong geometry, wrong registration, or pictures that do not agree."""
    n = float(hist.sum())
    if n == 0:
        return {"texels": 0, "delta_e_mean": None, "delta_e_p90": None, "conflict_pct": None}
    centres = np.arange(len(hist)) + 0.5
    cdf = np.cumsum(hist) / n
    return {"texels": int(n), "delta_e_mean": round(float((hist * centres).sum() / n), 2),
            "delta_e_p90": float(np.searchsorted(cdf, 0.9)),
            "conflict_pct": round(100.0 * float(hist[15:].sum()) / n, 2)}


def warp_field(ref_mask: np.ndarray, model_mask: np.ndarray, sigma: float = 8.0, max_px: float = 30.0,
               rim_px: float = 1.5) -> np.ndarray:
    """Per picture pixel, how far (dx, dy) to look in the picture so its outline lands on the model's outline.
    Pixels on the model's outline point at the nearest picture outline; the moves spread smoothly inward (sigma)
    and fade away from the outline, so a picture whose arms or skirt are drawn a little wider or narrower than the
    model still paints arm on arm and skirt on skirt. (H, W, 2) float."""
    sdf = distance_field(ref_mask)
    gy, gx = np.gradient(sdf)
    n = np.maximum(np.hypot(gx, gy), 1e-9)
    msdf = distance_field(model_mask)
    rim = np.abs(msdf) <= rim_px
    d = np.clip(sdf - msdf, -max_px, max_px)     # picture edge minus model edge, seen from this pixel
    acc = np.zeros(ref_mask.shape + (2,)); cnt = rim.astype(np.float64)
    acc[..., 0] = np.where(rim, -d * gx / n, 0.0); acc[..., 1] = np.where(rim, -d * gy / n, 0.0)
    return smooth_field(acc, cnt, sigma)


def palette(lab: np.ndarray, k: int = 6, iterations: int = 8, seed: int = 0) -> np.ndarray:
    """k-means colour centres (CIELAB) of a mesh's trusted samples; fewer when there are few distinct colours."""
    lab = np.asarray(lab, np.float64)
    if len(lab) > 20000:
        lab = lab[np.random.default_rng(seed).choice(len(lab), 20000, replace=False)]
    order = np.argsort(lab[:, 0])
    centres = lab[order[np.linspace(0, len(lab) - 1, min(k, len(lab))).astype(int)]].copy()
    for _ in range(iterations):
        lab_idx = np.argmin(((lab[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
        for j in range(len(centres)):
            sel = lab_idx == j
            if sel.any(): centres[j] = lab[sel].mean(axis=0)
    return centres


def foreign(lab: np.ndarray, centres: np.ndarray, max_de: float) -> np.ndarray:
    """True where a colour is further than max_de (CIE76) from every palette centre: paint that belongs to another
    part (an arm drawn over a skirt in one picture but not on the model)."""
    if len(lab) == 0 or len(centres) == 0:
        return np.zeros(len(lab), bool)
    d = np.sqrt(((np.asarray(lab)[:, None, :] - centres[None]) ** 2).sum(axis=2)).min(axis=1)
    return d > max_de


def fill_3d(src_p: np.ndarray, src_rgb: np.ndarray, dst_p: np.ndarray, cell: float = 0.004) -> np.ndarray:
    """Colour for points dst_p from nearby coloured points src_p in 3D: average per cell of a voxel grid, then
    push-pull across the grid so empty cells take the colour of the closest filled region. Vectorized; replaces a
    per-point KD-tree lookup that took minutes for a body with a million hidden texels."""
    if len(dst_p) == 0:
        return np.zeros((0, 3))
    lo = np.minimum(src_p.min(axis=0), dst_p.min(axis=0))
    hi = np.maximum(src_p.max(axis=0), dst_p.max(axis=0))
    dims = np.maximum(np.ceil((hi - lo) / cell).astype(np.int64) + 1, 1)
    while int(np.prod(dims)) > 16_000_000:                  # keep the grid under ~0.5 GB
        cell *= 1.25
        dims = np.maximum(np.ceil((hi - lo) / cell).astype(np.int64) + 1, 1)

    def flat(p):
        ijk = np.clip(((p - lo) / cell).astype(np.int64), 0, dims - 1)
        return (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]

    n = int(np.prod(dims)); si = flat(src_p)
    w = np.bincount(si, minlength=n).astype(np.float32).reshape(dims)
    c = np.stack([np.bincount(si, weights=src_rgb[:, k], minlength=n) for k in range(3)], -1).astype(np.float32)
    levels = [(c.reshape(*dims, 3), w)]
    while max(levels[-1][1].shape) > 1:
        cc, ww = levels[-1]
        pad = [(0, s % 2) for s in ww.shape]
        ww = np.pad(ww, pad); cc = np.pad(cc, pad + [(0, 0)])
        a, b, d = (s // 2 for s in ww.shape)
        ww = ww.reshape(a, 2, b, 2, d, 2).sum(axis=(1, 3, 5))
        cc = cc.reshape(a, 2, b, 2, d, 2, 3).sum(axis=(1, 3, 5))
        levels.append((cc, ww))
    col = levels[-1][0] / np.maximum(levels[-1][1], 1e-12)[..., None]
    for cc, ww in reversed(levels[:-1]):
        up = _smooth3(col.repeat(2, 0).repeat(2, 1).repeat(2, 2))[:ww.shape[0], :ww.shape[1], :ww.shape[2]]
        col = np.where((ww > 0)[..., None], cc / np.maximum(ww, 1e-12)[..., None], up)
    # read back trilinearly between cell centres, so far-from-paint regions get gradients, not 4 mm blocks
    f = (dst_p - lo) / cell - 0.5
    i0 = np.clip(np.floor(f).astype(np.int64), 0, dims - 1); i1 = np.minimum(i0 + 1, dims - 1)
    t = np.clip(f - i0, 0.0, 1.0)
    out = np.zeros((len(dst_p), 3))
    for cx in (0, 1):
        for cy in (0, 1):
            for cz in (0, 1):
                wgt = ((t[:, 0] if cx else 1 - t[:, 0]) * (t[:, 1] if cy else 1 - t[:, 1]) * (t[:, 2] if cz else 1 - t[:, 2]))
                ix = i1[:, 0] if cx else i0[:, 0]; iy = i1[:, 1] if cy else i0[:, 1]; iz = i1[:, 2] if cz else i0[:, 2]
                out += col[ix, iy, iz] * wgt[:, None]
    return out


def _smooth3(a: np.ndarray) -> np.ndarray:
    """1-2-1 blur along the three grid axes (edge-padded), for pulling coarse levels up without blocks."""
    for ax in range(3):
        p = np.pad(a, [(1, 1) if k == ax else (0, 0) for k in range(a.ndim)], mode="edge")
        sl = lambda s, e: tuple(slice(s, e) if k == ax else slice(None) for k in range(a.ndim))
        n = a.shape[ax]
        a = 0.25 * p[sl(0, n)] + 0.5 * p[sl(1, n + 1)] + 0.25 * p[sl(2, n + 2)]
    return a
