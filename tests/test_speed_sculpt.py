import ast
import json
import re
import sys
from pathlib import Path

import pytest

LIVE = Path(__file__).resolve().parents[1] / "mcp" / "blender-live"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "blender-character" / "scripts"))
import speed_sculpt as ss  # noqa: E402


def _server_tools() -> set[str]:
    src = (LIVE / "server.py").read_text(encoding="utf-8")
    return set(re.findall(r"@mcp\.tool\(\)\s*\ndef (\w+)\(", src))


def _server_params(tool: str) -> set[str]:
    tree = ast.parse((LIVE / "server.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == tool)
    return {a.arg for a in fn.args.args}


@pytest.fixture(scope="module")
def steps():
    return ss.plan(1.6)


def test_brushes_match_the_sculpt_commands():
    src = (LIVE / "sculpt_cmds.py").read_text(encoding="utf-8")
    m = re.search(r"^BRUSHES = (\(.*?\))", src, re.M)
    assert tuple(ast.literal_eval(m.group(1))) == ss.BRUSHES


def test_every_step_is_a_real_tool_with_real_arguments(steps):
    tools = _server_tools()
    for s in steps:
        assert s["tool"] in tools, s["tool"]
        assert set(s["args"]) <= _server_params(s["tool"]), (s["tool"], set(s["args"]))
        assert s["why"] and s["source"].startswith("[YS")


def test_generated_code_parses_and_sets_result(steps):
    code = [s["args"]["code"] for s in steps if s["tool"] == "exec_python"]
    assert len(code) > 30
    for c in code:
        tree = ast.parse(c)
        assert "result" in {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign) for t in n.targets
                            if isinstance(t, ast.Name)}


def test_strokes_pass_the_server_checks_and_land_near_their_part(steps):
    parts = ss.proportions(1.6)
    n = 0
    for s in steps:
        if s["tool"] != "sculpt_strokes":
            continue
        obj = s["args"]["object"].removeprefix(ss.PREFIX)
        c = parts[obj]["center"] if obj in parts else None
        for st in s["args"]["strokes"]:
            ss.check_stroke(st); n += 1
            assert 0 < st["strength"] <= 1
            if c is None:
                continue
            reach = max(parts[obj]["radii"]) * 1.6 + st["radius"]
            for p in st["points"][:1]:
                assert sum((p[i] - c[i]) ** 2 for i in range(3)) ** 0.5 <= reach, (obj, p)
    assert n >= 20


def test_his_order(steps):
    def first(pred):
        return next(i for i, s in enumerate(steps) if pred(s))
    code = lambda s: s["args"].get("code", "")
    head = first(lambda s: "'YS_head'" in code(s) and "create_uvsphere" in code(s))
    remesh = first(lambda s: s["tool"] == "sculpt_remesh")
    face = first(lambda s: s["tool"] == "sculpt_strokes" and s["args"]["object"] == "YS_head")
    eye = first(lambda s: "'YS_eye'" in code(s) and "create_uvsphere" in code(s))
    lids = [i for i, s in enumerate(steps) if s["tool"] == "sculpt_strokes" and s["args"]["object"] == "YS_head"][1]
    torso = first(lambda s: "'YS_torso'" in code(s) and "create_uvsphere" in code(s))
    mask = first(lambda s: s["tool"] == "sculpt_mask")
    extract = first(lambda s: "geometry_extract_solidify" in code(s))
    paint = first(lambda s: "color_attributes" in code(s))
    last_sculpt = max(i for i, s in enumerate(steps) if s["tool"] in ("sculpt_strokes", "sculpt_remesh"))
    lights = first(lambda s: "LIGHTS" in code(s))
    assert head < remesh < face < eye < lids < torso < mask < extract < paint
    assert last_sculpt < paint < lights == len(steps) - 1


def test_one_sided_parts_mirror_across_the_head():
    for name, p in ss.proportions(1.7).items():
        code = ss.code_add_part(name, p["center"], p["radii"], p["side"])
        assert ("mirror_object = bpy.data.objects.get('YS_head')" in code) == (p["side"] == "L")
        if p["side"] == "L":
            assert p["center"][0] > 0


def test_proportions_stand_on_the_floor_and_reach_the_height():
    for height in (1.2, 1.6, 1.9):
        parts = ss.proportions(height)
        top = max(p["center"][2] + p["radii"][2] for p in parts.values())
        bottom = min(p["center"][2] - p["radii"][2] for p in parts.values())
        assert abs(bottom) < 0.02 * height and abs(top - height) < 0.03 * height
    with pytest.raises(ValueError):
        ss.proportions(0)


def test_colours_are_linear_and_overridable():
    assert ss._hex("#ffffff") == (1.0, 1.0, 1.0, 1.0) and ss._hex("#000000")[:3] == (0, 0, 0)
    assert abs(ss._hex("#808080")[0] - 0.2159) < 1e-3
    with pytest.raises(ValueError):
        ss._hex("#fff")
    steps = ss.plan(1.6, {"hair": "#ff0000"})
    assert any("(1.0, 0.0, 0.0, 1.0)" in s["args"].get("code", "") for s in steps)


def test_bad_strokes_are_refused():
    for bad in ({"brush": "pinch", "points": [[0, 0, 0]]}, {"brush": "grab", "points": [[0, 0, 0]]},
                {"brush": "draw", "points": [[0, 0]]}, {"brush": "draw", "points": [[0, 0, 0]], "radius": 0}):
        with pytest.raises(ValueError):
            ss.check_stroke(bad)


def test_cli_writes_json(capsys):
    assert ss.main(["--height", "1.5", "--hair-locks", "2", "--colors", "skin=#e0c0b0"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out[0]["tool"] == "exec_python" and sum("hair_lock_" in json.dumps(s) for s in out) >= 2
