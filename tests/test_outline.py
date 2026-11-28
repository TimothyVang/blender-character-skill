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


def _character_ref_and_captures(tmp_path, *, banded_clay: bool = False, blank_material: bool = False):
    """Build a synthetic 512x512 character reference with crisp interior features (hairline, belt, skirt)
    plus matching/defective model captures to test visual_score and banding_ratio."""
    h, w = 512, 512
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    yy, xx = np.mgrid[:h, :w]
    mask = ((xx - 256) / 96.0) ** 2 + ((yy - 256) / 210.0) ** 2 <= 1.0
    rgba[mask, 3] = 255
    # Distinct Ghibli-like bands: dark brown hair top, warm peach face, cream shirt, navy skirt
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[mask & (yy < 130)] = (55, 35, 25)
    rgb[mask & (yy >= 130) & (yy < 200)] = (235, 195, 170)
    rgb[mask & (yy >= 200) & (yy < 295)] = (235, 228, 205)
    rgb[mask & (yy >= 295) & (yy < 318)] = (120, 65, 35)
    rgb[mask & (yy >= 318)] = (30, 60, 105)
    rgba[:, :, :3] = rgb
    ref_path = tmp_path / "char_ref.png"
    Image.fromarray(rgba).save(ref_path)

    mat_rgb = np.full((h, w, 3), 185, dtype=np.uint8) if blank_material else rgb.copy()
    mat_rgb[~mask] = 0

    # Smooth hemisphere clay vs horizontal lathe-ring banded clay
    nx = (xx - 256) / 100.0
    ny = (yy - 256) / 215.0
    nz = np.sqrt(np.clip(1.0 - nx * nx - ny * ny, 0.0, 1.0))
    clay = np.clip(45.0 + 185.0 * nz, 0, 255)
    if banded_clay:
        clay = np.clip(clay + 28.0 * np.sin(yy * np.pi / 2.0), 0, 255)
    clay_u8 = clay.astype(np.uint8)
    clay_u8[~mask] = 0
    return str(ref_path), mask, mat_rgb, clay_u8


def test_visual_score_passes_smooth_textured_match_and_rejects_banded_or_blank(tmp_path):
    ref_p, mod_mask, mat_ok, clay_ok = _character_ref_and_captures(tmp_path)
    rm = {"FRONT": ol.reference_mask(ref_p)}
    rc = {"FRONT": ol.reference_rgb(ref_p)}

    good = ol.visual_score(rc, rm, {"FRONT": mat_ok}, {"FRONT": clay_ok}, {"FRONT": mod_mask}, ["FRONT", "LEFT"])
    assert good["views"]["FRONT"]["status"] == "passed"
    assert good["views"]["FRONT"]["failed_checks"] == []
    assert good["views"]["FRONT"]["iou"] >= 0.99
    assert good["views"]["FRONT"]["ssim"] >= 0.95
    assert good["views"]["FRONT"]["interior_edge_f1"] >= 0.90
    assert good["views"]["FRONT"]["clay_banding_ratio"] < 1.0
    assert good["views"]["LEFT"]["status"] == "not_run"
    assert good["all_measured_passed"] is True
    assert good["all_views_passed"] is False

    # Projected texture on horizontally banded clay geometry MUST fail clay_banding_ratio despite 0.99 IoU & 0.99 SSIM!
    _, _, mat_b, clay_banded = _character_ref_and_captures(tmp_path, banded_clay=True)
    banded = ol.visual_score(rc, rm, {"FRONT": mat_b}, {"FRONT": clay_banded}, {"FRONT": mod_mask}, ["FRONT"])
    assert banded["views"]["FRONT"]["status"] == "failed"
    assert banded["views"]["FRONT"]["iou"] >= 0.99
    assert "clay_banding_ratio" in banded["views"]["FRONT"]["failed_checks"]

    # Smooth clay geometry with blank/untextured interior MUST fail interior_edge_f1 and the colour proof despite 0.99 IoU!
    _, _, mat_blank, clay_smooth = _character_ref_and_captures(tmp_path, blank_material=True)
    blank = ol.visual_score(rc, rm, {"FRONT": mat_blank}, {"FRONT": clay_smooth}, {"FRONT": mod_mask}, ["FRONT"])
    assert blank["views"]["FRONT"]["status"] == "failed"
    assert blank["views"]["FRONT"]["iou"] >= 0.99
    assert "interior_edge_f1" in blank["views"]["FRONT"]["failed_checks"]
    assert "delta_e" in blank["views"]["FRONT"]["failed_checks"]


def test_delta_e00_matches_published_cie_test_pairs():
    # Sharma, Wu & Dalal (2005) CIEDE2000 test data, pairs 1, 7 and 17.
    lab1 = np.array([[50.0, 2.6772, -79.7751], [50.0, 0.0, 0.0], [50.0, 2.5, 0.0]])
    lab2 = np.array([[50.0, 0.0, -82.7485], [50.0, -1.0, 2.0], [73.0, 25.0, -18.0]])
    np.testing.assert_allclose(ol.delta_e00(lab1, lab2), [2.0425, 2.3669, 27.1492], atol=1e-3)


def test_colour_proof_reports_inks_and_flags_a_wrong_colour():
    ref = np.zeros((64, 64, 3), np.uint8); ref[:, :32] = (200, 40, 40); ref[:, 32:] = (40, 60, 160)
    region = np.ones((64, 64), bool)
    same = ol.colour_proof(ref, ref.copy(), region)
    assert same["delta_e_mean"] < 0.5 and same["within_de5_pct"] > 99
    assert {r["ref_hex"] for r in same["inks"]} >= {"#c82828", "#283ca0"}
    wrong = ref.copy(); wrong[:, 32:] = (40, 160, 60)
    off = ol.colour_proof(ref, wrong, region)
    blue = next(r for r in off["inks"] if r["ref_hex"] == "#283ca0")
    assert blue["model_hex"] == "#28a03c" and blue["delta_e"] > 30 and off["delta_e_mean"] > 10


def test_banding_ignores_single_hems_but_catches_repeated_rings():
    yy, xx = np.mgrid[:512, :512]
    mask = ((xx - 256) / 100.0) ** 2 + ((yy - 256) / 215.0) ** 2 <= 1.0
    nz = np.sqrt(np.clip(1 - ((xx - 256) / 100.0) ** 2 - ((yy - 256) / 215.0) ** 2, 0, 1))
    smooth = 45 + 185 * nz
    hems = smooth + 25 * (((yy > 200) & (yy < 203)) | ((yy > 330) & (yy < 333)))
    rings = smooth + 20 * np.sin(yy * 2 * np.pi / 10)
    score = lambda lum: ol.banding_ratio((np.clip(lum, 0, 255) * mask).astype(np.uint8), mask)
    assert score(smooth) < 1.0 and score(hems) < 1.6 < score(rings)


def test_registration_recovers_a_shifted_outline_and_reports_it():
    ref = np.zeros((512, 512), bool); ref[100:400, 150:350] = True
    moved = np.roll(np.roll(ref, 3, axis=0), -2, axis=1)
    reg = ol.register(ref, moved)
    assert (reg["dx"], reg["dy"], reg["scale"]) == (2, -3, 1.0) and reg["iou"] == 1.0
    assert ol.transform(moved, reg).tolist() == ref.tolist()


def test_reference_pairs_reports_pictures_that_disagree():
    a = np.zeros((300, 200), bool); a[50:250, 60:140] = True
    b_ok = a[:, ::-1].copy()
    b_wide = np.zeros_like(a); b_wide[50:250, 40:160] = True
    assert ol.reference_pairs({"FRONT": a, "BACK": b_ok})["FRONT/BACK"] > 0.99
    assert ol.reference_pairs({"FRONT": a, "BACK": b_wide})["FRONT/BACK"] < 0.9
    assert ol.reference_pairs({"FRONT": a}) == {}


def test_model_coverage_cuts_at_half_coverage_in_standard_srgb():
    grey = np.zeros((40, 40), np.uint8); grey[10:30, 10:30] = 255
    grey[10:30, 9] = 188; grey[10:30, 30] = 128         # ~50% and ~22% covered edge columns
    m = ol.model_mask(grey, "FRONT")
    assert m[15, 9] and not m[15, 30]
    assert abs(ol.model_coverage(grey, "FRONT")[15, 9] - 0.5) < 0.02


def test_orbit_score_flags_banding_and_missing_texture():
    yy, xx = np.mgrid[:400, :400]
    disk = ((xx - 200) / 80.0) ** 2 + ((yy - 200) / 160.0) ** 2 <= 1
    sil = (disk * 255).astype(np.uint8)
    nz = np.sqrt(np.clip(1 - ((xx - 200) / 80.0) ** 2 - ((yy - 200) / 160.0) ** 2, 0, 1))
    clay = ((45 + 185 * nz) * disk).astype(np.uint8)
    ringed = (np.clip(45 + 185 * nz + 25 * np.sin(yy * np.pi / 2), 0, 255) * disk).astype(np.uint8)
    mat = np.zeros((400, 400, 3), np.uint8); mat[disk] = (120, 90, 60)
    pink = mat.copy(); pink[disk] = (255, 0, 255)
    res = ol.orbit_score([{"azimuth": 0.0, "elevation": 0.0, "sil": sil, "clay": clay, "mat": mat},
                          {"azimuth": 90.0, "elevation": 0.0, "sil": sil, "clay": ringed, "mat": pink}])
    a, b = res["angles"]
    assert a["status"] == "passed" and res["passed"] == 1 and res["failed"] == 1
    assert b["failed_checks"] == ["clay_banding_ratio", "missing_texture"]


def _figure(size=600):
    """A standing figure 400 px tall: silhouette and a skin-coloured render painted everywhere."""
    sil = np.zeros((size, size), np.uint8); sil[100:500, 225:375] = 255
    mat = np.full((size, size, 3), 60, np.uint8); mat[sil > 0] = (235, 205, 180)
    return sil, mat


def test_three_quarter_consistency_fails_only_where_two_pictures_put_a_feature_on_different_surfaces():
    sil, a = _figure()
    b = a.copy()
    assert ol.consistency_score(a, b, sil, "same")["status"] == "passed"
    a[120:160, 240:280] = (20, 20, 30)            # the eye where picture A puts it
    b[120:160, 320:360] = (20, 20, 30)            # picture B puts it on the cheek
    res = ol.consistency_score(a, b, sil, "moved eye")
    assert res["failed_gates"] == ["head.delta_e"]
    assert res["regions"]["body"]["status"] == "passed" and res["regions"]["legs"]["status"] == "passed"
    assert res["regions"]["head"]["conflict_pct"] > 20


def test_three_quarter_region_only_one_picture_paints_is_not_covered_not_passed():
    sil, a = _figure()
    b = a.copy(); b[380:500] = (255, 0, 255)       # picture B paints nothing on the legs
    res = ol.consistency_score(a, b, sil, "legs unpainted")
    assert res["regions"]["legs"]["status"] == "not covered"
    assert res["status"] == "passed"
