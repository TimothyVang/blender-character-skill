import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp" / "blender-live"))
import projection as pj  # noqa: E402


def _rasterized(tri, w, h):
    hit = np.zeros((h, w), int)
    for _, px, py, bary in pj.raster(np.asarray([tri], float), w, h):
        np.add.at(hit, (py, px), 1)
        assert np.allclose(bary.sum(axis=1), 1.0) and (bary >= -1e-6).all()
    return hit


def test_raster_covers_triangle_area_once_and_shared_edges_without_gaps():
    a = _rasterized([[0, 0], [64, 0], [0, 64]], 64, 64)
    b = _rasterized([[64, 0], [64, 64], [0, 64]], 64, 64)
    assert abs(a.sum() - 64 * 64 / 2) < 64            # area within one edge row
    assert ((a + b) >= 1).all()                       # two halves of a square leave no hole


def test_depth_buffer_keeps_the_nearest_surface():
    mapping = pj.fit_map((-1, -1, 1, 1), (0, 0, 32, 32))
    near = [[-1, -1, 0.5], [1, -1, 0.5], [0, 1, 0.5]]
    far = [[-1, -1, -0.5], [1, -1, -0.5], [0, 1, -0.5]]
    z = pj.depth_buffer(np.asarray([far, near]), mapping, 32, 32)
    assert np.nanmax(z[np.isfinite(z)]) == 0.5 and np.isfinite(z).sum() > 200
    assert np.isinf(z[0, 0])                           # outside both triangles


def test_view_axes_put_the_character_facing_the_camera_in_front():
    p = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 2.0]])     # a point in front (-Y) and one to the character's left (+X)
    f = pj.view_coords(p, "FRONT")
    assert f[0, 2] > 0 and f[1, 0] > 0 and f[1, 1] == 2.0
    r = pj.view_coords(p, "RIGHT")                         # RIGHT looks from +X: the +X point is nearest
    assert r[1, 2] > r[0, 2]


def test_fit_map_centres_boxes_with_one_scale():
    m = pj.fit_map((0.0, 0.0, 0.5, 2.0), (100, 50, 200, 450))
    x, y = pj.to_ref_px(np.array([0.25, 0.0, 0.25]), np.array([1.0, 1.0, 2.0]), m)
    assert np.allclose([x[0], y[0]], [150, 250]) and np.isclose(m[0], 200.0)
    assert np.isclose(y[2], 50) and np.isclose(x[1], 100)


def test_push_pull_fills_holes_from_neighbours_and_keeps_known_texels():
    rgb = np.zeros((16, 16, 3)); w = np.zeros((16, 16))
    rgb[:, :8] = (255, 0, 0); w[:, :8] = 1
    out = pj.push_pull(rgb, w)
    assert np.allclose(out[:, :8], (255, 0, 0)) and np.allclose(out[:, 8:, 0], 255)


def test_bleed_carries_edge_colour_outward():
    rgb = np.zeros((8, 8, 3)); rgb[2:6, 2:6] = (10, 200, 30)
    mask = np.zeros((8, 8), bool); mask[2:6, 2:6] = True
    out = pj.bleed(rgb, mask, iterations=4)
    assert np.allclose(out[0, 0], (10, 200, 30))


def test_distance_field_is_signed_euclidean():
    m = np.zeros((40, 40), bool); m[10:30, 10:30] = True
    d = pj.distance_field(m)
    assert d[20, 20] < -8 and abs(d[20, 35] - 6.0) < 1e-6 and d[20, 10] <= 0 and d[20, 9] > 0


def test_register_mapping_recovers_a_pixel_shift():
    ref = np.zeros((60, 60), bool); ref[10:50, 20:40] = True
    model = np.roll(ref, 2, axis=1)
    mapping = (100.0, (0.0, 0.0), (30.0, 30.0))
    new, reg = pj.register_mapping(mapping, ref, model)
    assert reg["dx"] == -2 and reg["dy"] == 0 and reg["iou"] == 1.0
    assert np.isclose(new[2][0], 28.0) and new[0] == 100.0


def test_smooth_field_averages_moves_and_fades_far_away():
    acc = np.zeros((50, 50, 2)); cnt = np.zeros((50, 50))
    acc[25, 10] = (4.0, 0.0); cnt[25, 10] = 1
    acc[25, 11] = (2.0, 0.0); cnt[25, 11] = 1
    f = pj.smooth_field(acc, cnt, 2.0)
    assert 2.5 < f[25, 10, 0] < 3.5 and abs(f[25, 45, 0]) < 1e-3


def test_de_hist_stats_summarises_cross_view_agreement():
    h = np.zeros(101); h[1] = 80; h[30] = 20
    s = pj.de_hist_stats(h)
    assert s["texels"] == 100 and s["conflict_pct"] == 20.0 and s["delta_e_p90"] == 30.0
    assert pj.de_hist_stats(np.zeros(101))["delta_e_mean"] is None


def test_fill_3d_takes_the_colour_of_the_nearest_painted_region():
    rng = np.random.default_rng(1)
    src = rng.random((5000, 3)) * [0.4, 0.2, 1.0]
    col = np.where(src[:, 2:3] > 0.5, [[200.0, 40.0, 40.0]], [[30.0, 60.0, 150.0]])
    dst = np.array([[0.2, 0.1, 0.95], [0.2, 0.1, 0.05], [0.2, 0.1, 1.2]])   # top, bottom, above everything
    out = pj.fill_3d(src, col, dst, cell=0.02)
    assert np.allclose(out[0], (200, 40, 40), atol=1) and np.allclose(out[1], (30, 60, 150), atol=1)
    assert out[2][0] > 150                                                    # outside the samples: nearest is red


def test_palette_flags_colours_that_belong_to_another_part():
    navy = np.tile([[40.0, 60.0, 100.0]], (300, 1)); dark = np.tile([[15.0, 20.0, 35.0]], (100, 1))
    centres = pj.palette(pj.srgb_to_lab(np.concatenate([navy, dark])))
    skin, navy_fold = np.array([[245.0, 205.0, 180.0]]), np.array([[30.0, 45.0, 80.0]])
    flags = pj.foreign(pj.srgb_to_lab(np.concatenate([skin, navy_fold])), centres, 28.0)
    assert flags.tolist() == [True, False]


def test_warp_field_points_from_model_outline_to_picture_outline():
    ref = np.zeros((80, 80), bool); ref[20:60, 20:64] = True                 # picture drawn 4 px wider on the right
    model = np.zeros((80, 80), bool); model[20:60, 20:60] = True
    f = pj.warp_field(ref, model, sigma=2.0)
    assert f[40, 59, 0] > 1.5 and abs(f[40, 59, 1]) < 0.5 and abs(f[40, 40, 0]) < 0.5
