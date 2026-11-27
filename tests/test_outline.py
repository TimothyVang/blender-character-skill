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
