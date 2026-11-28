import importlib.util
import json
import sys
import types
from pathlib import Path

import numpy as np
import pytest
from mcp.types import CallToolResult

MCP_DIR = Path(__file__).resolve().parents[1] / "mcp" / "blender-live"
sys.path.insert(0, str(MCP_DIR))      # outline.py and sculpt_cmds.py import projection.py from beside them


def _load_mcp_module(name: str):
    spec = importlib.util.spec_from_file_location(name, MCP_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ol = _load_mcp_module("outline")
srv = _load_mcp_module("server")

def _load_sculpt_cmds_without_blender():
    """Import sculpt_cmds.py with lightweight stubs for bpy/mathutils so pure-numpy helpers can be unit-tested."""
    saved = {}
    stub_names = ("bpy", "mathutils", "mathutils.bvhtree", "mathutils.kdtree")
    for name in stub_names:
        if name in sys.modules:
            saved[name] = sys.modules[name]
    bpy_mod = types.ModuleType("bpy")
    mathutils_mod = types.ModuleType("mathutils")
    mathutils_mod.Euler = object
    mathutils_mod.Vector = object
    bvh_mod = types.ModuleType("mathutils.bvhtree")
    bvh_mod.BVHTree = object
    kd_mod = types.ModuleType("mathutils.kdtree")
    kd_mod.KDTree = object
    sys.modules["bpy"] = bpy_mod
    sys.modules["mathutils"] = mathutils_mod
    sys.modules["mathutils.bvhtree"] = bvh_mod
    sys.modules["mathutils.kdtree"] = kd_mod
    try:
        spec = importlib.util.spec_from_file_location("_sculpt_cmds_unit", MCP_DIR / "sculpt_cmds.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod, bpy_mod
    finally:
        for name in stub_names:
            if name in saved:
                sys.modules[name] = saved[name]
            else:
                sys.modules.pop(name, None)


def test_bridge_returns_call_tool_result_with_is_error_flags(monkeypatch):
    monkeypatch.setattr(srv, "call", lambda cmd, timeout=300, **args: {"ok": True, "cmd": cmd, "echo": args})
    for fn, kwargs in (
        (srv.reference_setup, {"images": {"FRONT": "a.png"}}),
        (srv.sculpt_begin, {"object": "Head"}),
        (srv.sculpt_remesh, {"object": "Head", "voxel_size": 0.05}),
        (srv.sculpt_mask, {"object": "Head", "op": "clear"}),
        (srv.mesh_report, {"object": "Head"}),
    ):
        res = fn(**kwargs)
        assert isinstance(res, CallToolResult)
        assert res.isError is False
        payload = json.loads(res.content[0].text)
        assert "ok" not in payload
        assert payload["echo"]

    def explode(cmd, timeout=300, **args):
        raise RuntimeError(f"boom on {cmd}")

    monkeypatch.setattr(srv, "call", explode)
    for fn, kwargs in (
        (srv.reference_setup, {"images": {"FRONT": "a.png"}}),
        (srv.sculpt_begin, {"object": "Missing"}),
        (srv.sculpt_remesh, {"object": "Head", "voxel_size": 0.0001}),
        (srv.sculpt_mask, {"object": "Head", "op": "box"}),
        (srv.mesh_report, {"object": "Missing"}),
    ):
        res = fn(**kwargs)
        assert isinstance(res, CallToolResult)
        assert res.isError is True
        payload = json.loads(res.content[0].text)
        assert payload["status"] == "error"
        assert "boom on" in payload["detail"]


def test_nearest_matches_reference_across_chunks_ties_and_empty():
    sc, _ = _load_sculpt_cmds_without_blender()

    best, idx = sc._nearest(np.zeros((0, 3)), np.zeros((3, 3)))
    assert len(best) == 0 and len(idx) == 0
    best, idx = sc._nearest(np.zeros((4, 3)), np.zeros((0, 3)))
    assert np.all(np.isinf(best)) and np.all(idx == 0)

    c = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    samples = np.array([[1.0, 0.0, 0.0], [-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    best, idx = sc._nearest(c, samples, v_chunk=1, s_chunk=2)
    assert np.allclose(best, [1.0, 0.0])
    assert idx.tolist() == [0, 0]

    rng = np.random.default_rng(7)
    pts = rng.normal(size=(513, 3))
    samp = rng.normal(size=(137, 3))
    got_best, got_idx = sc._nearest(pts, samp, v_chunk=64, s_chunk=16)

    ref_best = np.full(len(pts), np.inf)
    ref_idx = np.zeros(len(pts), dtype=np.int64)
    for i, s in enumerate(samp):
        d = np.linalg.norm(pts - s, axis=1)
        m = d < ref_best
        ref_best[m] = d[m]
        ref_idx[m] = i

    assert np.allclose(got_best, ref_best, rtol=1e-12, atol=1e-12)
    assert np.array_equal(got_idx, ref_idx)


def test_undo_push_catches_only_expected_errors():
    sc, bpy_mod = _load_sculpt_cmds_without_blender()

    class _Ctx:
        def temp_override(self, **kwargs):
            class _CM:
                def __enter__(self): return None
                def __exit__(self, *a): return False
            return _CM()

    pushed = []
    bpy_mod.context = _Ctx()
    bpy_mod.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=lambda message: pushed.append(message)))
    sc.view3d = lambda: ("win", "area", "region")
    assert sc._undo_push("ok") is True
    assert pushed == ["ok"]

    def fail_runtime(message):
        raise RuntimeError("no undo context")

    bpy_mod.ops = types.SimpleNamespace(ed=types.SimpleNamespace(undo_push=fail_runtime))
    assert sc._undo_push("rt") is False

    sc.view3d = lambda: (_ for _ in ()).throw(AttributeError("no screen"))
    assert sc._undo_push("attr") is False

    sc.view3d = lambda: (_ for _ in ()).throw(ValueError("unexpected bug"))
    with pytest.raises(ValueError, match="unexpected bug"):
        sc._undo_push("val")


def test_components_handles_non_bool_and_preserves_zero_background():
    arr = np.array([[0, 2, 0], [5, 3, 0], [0, 0, 9]], dtype=np.uint8)
    lab, n = ol._components(arr)
    assert n == 2
    assert lab[0, 0] == 0 and lab[2, 0] == 0
    assert lab[0, 1] == lab[1, 0] == lab[1, 1] > 0
    assert lab[2, 2] > 0 and lab[2, 2] != lab[0, 1]


def test_visual_match_mcp_contract_handles_pass_fail_and_errors(monkeypatch, tmp_path):
    import base64, io
    from PIL import Image

    # Create a clean RGBA reference with two distinct interior colour bands
    h, w = 256, 256
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    yy, xx = np.mgrid[:h, :w]
    mask = ((xx - 128) / 55.0) ** 2 + ((yy - 128) / 95.0) ** 2 <= 1.0
    rgba[mask, 3] = 255
    rgba[mask & (yy < 128), :3] = (230, 210, 185)
    rgba[mask & (yy >= 128), :3] = (35, 70, 125)
    ref_file = tmp_path / "front.png"
    Image.fromarray(rgba).save(ref_file)

    def _to_b64(arr, mode):
        buf = io.BytesIO()
        Image.fromarray(arr, mode=mode).save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()

    sil_b64 = _to_b64((mask.astype(np.uint8) * 255), "L")
    nz = np.sqrt(np.clip(1.0 - ((xx - 128) / 60.0) ** 2 - ((yy - 128) / 100.0) ** 2, 0.0, 1.0))
    clay_smooth = (np.clip(50.0 + 170.0 * nz, 0, 255) * mask).astype(np.uint8)
    clay_banded = (np.clip(50.0 + 170.0 * nz + 35.0 * np.sin(yy * np.pi / 2.0), 0, 255) * mask).astype(np.uint8)
    mat_good = rgba[:, :, :3].copy()

    monkeypatch.setenv("BLENDER_LIVE_TMP", str(tmp_path))
    monkeypatch.setattr(srv, "call", lambda cmd, timeout=900, **kw: {
        "ok": True,
        "shots": [{
            "view": "FRONT",
            "perspective": "ORTHO",
            "silhouette_b64": sil_b64,
            "clay_b64": _to_b64(clay_smooth, "L"),
            "material_b64": _to_b64(mat_good, "RGB"),
        }],
    })
    ok_res = srv.visual_match(object="CHARACTER", references={"FRONT": str(ref_file)})
    assert isinstance(ok_res, CallToolResult) and ok_res.isError is False
    payload = json.loads(ok_res.content[0].text)
    assert payload["views"]["FRONT"]["status"] == "passed"
    assert Path(payload["visual_sheet_path"]).is_file()

    monkeypatch.setattr(srv, "call", lambda cmd, timeout=900, **kw: {
        "ok": True,
        "shots": [{
            "view": "FRONT",
            "perspective": "ORTHO",
            "silhouette_b64": sil_b64,
            "clay_b64": _to_b64(clay_banded, "L"),
            "material_b64": _to_b64(mat_good, "RGB"),
        }],
    })
    fail_res = srv.visual_match(object="CHARACTER", references={"FRONT": str(ref_file)})
    assert fail_res.isError is False
    fail_payload = json.loads(fail_res.content[0].text)
    assert fail_payload["views"]["FRONT"]["status"] == "failed"
    assert "clay_banding_ratio" in fail_payload["views"]["FRONT"]["failed_checks"]

    bad_res = srv.visual_match(object="CHARACTER", references={"BADVIEW": str(ref_file)})
    assert bad_res.isError is True
