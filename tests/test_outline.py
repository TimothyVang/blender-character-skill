import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp" / "blender-live"))
import outline as ol  # noqa: E402


def circle_png(path, size=600, bg=(30, 30, 30), fg=(220, 200, 180), border=None, patch=False, mark=False, alpha=False):
    im = Image.new("RGBA" if alpha else "RGB", (size, size), (0, 0, 0, 0) if alpha else bg)
    d = ImageDraw.Draw(im)
    d.ellipse((100, 100, 500, 500), fill=fg + ((255,) if alpha else ()))
    if patch: d.ellipse((250, 250, 330, 330), fill=bg)            # background-coloured spot inside the subject
    if mark: d.rectangle((540, 560, 580, 575), fill=(250, 250, 250))  # a signature in the corner area
    if border: d.rectangle((0, 0, size - 1, size - 1), outline=border, width=6)
    im.save(path); return str(path)


def model_circle(size=1024):
    yy, xx = np.mgrid[:size, :size]
    return ((xx - size / 2) ** 2 + (yy - size / 2) ** 2 < (size * 0.3) ** 2)


def test_views_outside_the_five_are_refused(tmp_path):
    ref = circle_png(tmp_path / "c.png")
    with pytest.raises(ValueError, match="SIDE"):
        ol.check_request({"FRONT": ref, "SIDE": ref}, None, 0.98)
    with pytest.raises(ValueError, match="FRONTT"):
        ol.check_request({"FRONT": ref}, ["FRONTT"], 0.98)


def test_threshold_outside_range_is_refused(tmp_path):
    ref = circle_png(tmp_path / "c.png")
    for bad in (0.0, 0.5, 0.89, 1.01):
        with pytest.raises(ValueError, match="threshold"):
            ol.check_request({"FRONT": ref}, None, bad)


def test_all_views_passed_counts_all_five_even_when_fewer_requested(tmp_path):
    ref = circle_png(tmp_path / "c.png")
    res = ol.score({"FRONT": ol.reference_mask(ref)}, {"FRONT": model_circle()}, ["FRONT"], 0.98)
    assert res["views"]["FRONT"]["status"] == "passed"
    assert res["all_measured_passed"] is True
    assert res["all_views_passed"] is False
    assert res["views_requested"] == ["FRONT"]
    assert sorted(res["unmeasured_of_five"]) == ["BACK", "LEFT", "RIGHT", "TOP"]


def test_reference_that_fills_its_canvas_is_refused(tmp_path):
    full = tmp_path / "full.png"
    im = Image.new("RGBA", (400, 400), (200, 100, 50, 255)); im.putpixel((0, 0), (0, 0, 0, 0)); im.save(full)
    with pytest.raises(ValueError, match="fills"):
        ol.reference_mask(str(full))
    framed = circle_png(tmp_path / "framed.png", border=(0, 0, 0))
    m = ol.reference_mask(framed)                  # a thin frame is background-ish noise, not the subject
    assert 0.3 < m.mean() < 0.6


def test_model_capture_touching_the_edge_is_refused():
    edge = np.zeros((1024, 1024), bool); edge[:, :600] = True
    with pytest.raises(ValueError, match="edge"):
        ol.check_model_mask(edge, "FRONT")


def test_patch_and_signature_do_not_spoil_a_correct_match(tmp_path):
    for kw in ({"patch": True}, {"mark": True}, {"alpha": True}, {}):
        ref = circle_png(tmp_path / f"c{len(kw)}{list(kw)}.png", **kw)
        res = ol.score({"FRONT": ol.reference_mask(ref)}, {"FRONT": model_circle()}, ["FRONT"], 0.98)
        assert res["views"]["FRONT"]["iou"] >= 0.98, kw


def test_separate_parts_are_all_kept(tmp_path):
    grey = np.zeros((1024, 1024), np.uint8)
    yy, xx = np.mgrid[:1024, :1024]
    grey[((xx - 300) ** 2 + (yy - 512) ** 2) < 150 ** 2] = 255
    grey[((xx - 750) ** 2 + (yy - 512) ** 2) < 120 ** 2] = 255      # a second part that does not touch the first
    m = ol.model_mask(grey, "FRONT")
    assert m[512, 300] and m[512, 750]
    p = tmp_path / "two.png"
    im = Image.new("RGB", (900, 500), (30, 30, 30)); d = ImageDraw.Draw(im)
    d.ellipse((50, 100, 350, 400), fill=(220, 200, 180)); d.ellipse((550, 130, 790, 370), fill=(220, 200, 180)); im.save(p)
    r = ol.reference_mask(str(p))
    h, w = r.shape
    assert r[h // 2, int(w * 200 / 900)] and r[h // 2, int(w * 670 / 900)]


def test_square_does_not_match_circle(tmp_path):
    sq = tmp_path / "sq.png"
    im = Image.new("RGB", (600, 600), (30, 30, 30)); ImageDraw.Draw(im).rectangle((100, 100, 500, 500), fill=(220, 200, 180)); im.save(sq)
    res = ol.score({"FRONT": ol.reference_mask(str(sq))}, {"FRONT": model_circle()}, ["FRONT"], 0.98)
    assert res["views"]["FRONT"]["status"] == "failed" and res["views"]["FRONT"]["iou"] < 0.9


def test_busy_background_is_refused(tmp_path):
    p = tmp_path / "busy.png"
    im = Image.new("RGB", (600, 600), (30, 30, 30)); ImageDraw.Draw(im).rectangle((0, 0, 300, 300), fill=(250, 250, 250)); im.save(p)
    with pytest.raises(ValueError, match="not plain"):
        ol.reference_mask(str(p))


def _bfs_components_ref(mask: np.ndarray) -> tuple[np.ndarray, int]:
    from collections import deque
    mask_b = np.asarray(mask, dtype=bool)
    h, w = mask_b.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(mask_b)):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and mask_b[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
    return lab, n


def _assert_same_components(mask: np.ndarray) -> None:
    got_lab, got_n = ol._components(mask)
    ref_lab, ref_n = _bfs_components_ref(mask)
    assert got_n == ref_n
    assert got_lab.shape == ref_lab.shape and got_lab.dtype == np.int32
    assert np.array_equal(got_lab > 0, ref_lab > 0)
    for a, b in ((got_lab, ref_lab), (ref_lab, got_lab)):
        mapping = {}
        for ga, gb in zip(a[a > 0].tolist(), b[a > 0].tolist()):
            if ga in mapping:
                assert mapping[ga] == gb
            else:
                mapping[ga] = gb


def test_components_scanline_matches_bfs_on_edges_and_shapes():
    for mask in (
        np.zeros((0, 0), bool),
        np.zeros((5, 7), bool),
        np.ones((5, 7), bool),
        np.array([[True]]),
        np.array([[True, False, True, True, False, True]]),
        np.array([[True], [False], [True], [True], [False]]),
        (np.indices((8, 8)).sum(axis=0) % 2) == 0,
    ):
        _assert_same_components(mask)

    u = np.zeros((10, 12), bool)
    u[1:8, 1:3] = True
    u[1:8, 5:7] = True
    u[1:8, 9:11] = True
    u[7:9, 1:11] = True
    lab, n = ol._components(u)
    assert n == 1
    _assert_same_components(u)

    rng = np.random.default_rng(42)
    for density in (0.1, 0.35, 0.55, 0.8):
        for _ in range(5):
            _assert_same_components(rng.random((40, 40)) < density)


def test_studio_vertical_gradient_and_tight_crop_are_accepted(tmp_path):
    h, w = 600, 600
    t = np.linspace(0.0, 1.0, h)[:, None, None]
    bg = (np.array([[[172.0, 167.0, 160.0]]]) * (1.0 - t) + np.array([[[195.0, 190.0, 184.0]]]) * t).astype(np.uint8)
    arr = np.broadcast_to(bg, (h, w, 3)).copy()
    im = Image.fromarray(arr)
    ImageDraw.Draw(im).ellipse((120, 40, 480, 592), fill=(80, 110, 60))
    grad = tmp_path / "studio_grad.png"
    im.save(grad)
    m = ol.reference_mask(str(grad))
    assert 0.3 < m.mean() < 0.75

    split = np.zeros((400, 400, 3), dtype=np.uint8)
    split[:200] = (230, 230, 230)
    split[200:] = (40, 40, 40)
    split_im = Image.fromarray(split)
    ImageDraw.Draw(split_im).ellipse((120, 120, 280, 280), fill=(180, 50, 50))
    sp = tmp_path / "split_bg.png"
    split_im.save(sp)
    with pytest.raises(ValueError, match="not plain"):
        ol.reference_mask(str(sp))
