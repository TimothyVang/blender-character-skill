import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "blender-character" / "scripts"))
import course_grab as cg  # noqa: E402
import make_clips as mc  # noqa: E402

FFMPEG = os.environ.get("FFMPEG_DIR") or cg.find_ffmpeg_dir()
CH = [{"n": 1, "slug": "a", "title": "A", "start": 0.0, "end": 100.0},
      {"n": 2, "slug": "b", "title": "B", "start": 100.0, "end": 160.0}]


def test_segments_merge_short_lines_and_stay_inside_chapters():
    lines = {1: [(0.0, "one."), (3.0, "two."), (6.0, "three."), (12.0, "four."), (60.0, "five."), (95.0, "six.")],
             2: [(101.0, "seven."), (130.0, "eight.")]}
    segs = mc.segments(lines, CH, min_s=8, max_s=30)
    for s in segs:
        ch = next(c for c in CH if c["n"] == s["chapter_n"])
        assert ch["start"] <= s["start"] < s["end"] <= ch["end"]
        assert s["end"] - s["start"] <= 30 + 1e-6
    first = segs[0]
    assert first["start"] == 0.0 and first["text"].startswith("one. two. three.")
    assert first["end"] - first["start"] >= 8
    assert not any(s["start"] < 100 < s["end"] for s in segs)          # never crosses a chapter boundary
    assert all(segs[i]["end"] <= segs[i + 1]["start"] + 1e-6 for i in range(len(segs) - 1))


def test_long_silence_is_split_and_text_is_not_repeated():
    lines = {1: [(0.0, "start."), (70.0, "late.")], 2: []}
    segs = mc.segments(lines, CH, min_s=8, max_s=30)
    text = " ".join(s["text"] for s in segs)
    assert text.count("start.") == 1 and text.count("late.") == 1
    assert all(s["end"] - s["start"] <= 30 + 1e-6 for s in segs)


def test_stage_tags():
    assert mc.stage_for("Sculpting the Face of Your Character") == "03-sculpt-face"
    assert mc.stage_for("Retopologizing the Body") == "06-retopology"
    assert mc.stage_for("Rigging & Posing Your Character") == "10-rigging-posing"
    assert mc.stage_for("Introduction") is None


@pytest.fixture
def clip_dir(tmp_path):
    if not FFMPEG:
        pytest.skip("ffmpeg not found; set FFMPEG_DIR")
    d = tmp_path / "clip"; d.mkdir()
    subprocess.run([str(Path(FFMPEG) / "ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=40:size=640x360:rate=10",
                    "-f", "lavfi", "-i", "sine=duration=40", "-shortest", "-pix_fmt", "yuv420p", str(d / "clip.mp4")], check=True)
    (d / "clip.info.json").write_text(json.dumps({"id": "clip", "title": "T", "duration": 40, "chapters": [
        {"start_time": 0, "end_time": 25, "title": "Blocking Out Your Character"},
        {"start_time": 25, "end_time": 40, "title": "Sculpting the Face of Your Character"}]}))
    (d / "clip.en.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nwe start with a sphere.\n\n"
                                   "00:00:12.000 --> 00:00:15.000\npull out this area right here.\n\n"
                                   "00:00:27.000 --> 00:00:30.000\nnow the eyes.\n")
    return d


def test_clips_and_manifest(clip_dir):
    assert mc.make_clips(clip_dir, "clip", ffmpeg_dir=FFMPEG, height=240, workers=2, encoder="libx264") == 0
    rows = [json.loads(l) for l in (clip_dir / "clips" / "manifest.jsonl").read_text().splitlines()]
    assert rows and all((clip_dir / r["file"]).stat().st_size > 1000 for r in rows)
    assert {r["stage"] for r in rows} == {"02-blockout", "03-sculpt-face"}
    assert any("pull out this area" in r["text"] for r in rows)
    assert set(rows[0]) >= {"id", "video_id", "chapter_n", "chapter", "stage", "start", "end", "duration", "text", "file"}
    probe = subprocess.run([str(Path(FFMPEG) / "ffprobe"), "-v", "error", "-show_entries", "stream=codec_type,height",
                            "-of", "csv=p=0", str(clip_dir / rows[0]["file"])], capture_output=True, text=True).stdout
    assert "video,240" in probe.replace("\r", "") and "audio" in probe
    first_mtime = (clip_dir / rows[0]["file"]).stat().st_mtime
    assert mc.make_clips(clip_dir, "clip", ffmpeg_dir=FFMPEG, height=240, workers=2, encoder="libx264") == 0
    assert (clip_dir / rows[0]["file"]).stat().st_mtime == first_mtime          # not cut again
    assert (clip_dir / "clips" / ".gitignore").read_text().strip() == "*"


def test_silent_chapters_are_covered_by_equal_windows():
    segs = mc.segments({1: [], 2: []}, CH, min_s=8, max_s=30, cover_silent=True)
    for c in CH:
        mine = [s for s in segs if s["chapter_n"] == c["n"]]
        assert mine[0]["start"] == c["start"] and mine[-1]["end"] == c["end"]
        assert all(s["end"] - s["start"] <= 30 + 1e-6 and s["text"] == "" for s in mine)
    assert len([s for s in segs if s["chapter_n"] == 1]) == 4          # 100 s -> 4 x 25 s
    assert mc.segments({1: [], 2: []}, CH) == []                       # default: narrated courses unchanged


def test_stage_tags_for_a_box_modelling_speed_model():
    expect = {"Image Reference": "01-concept-and-references", "Base Shape": "02-blockout",
              "Shoe Modeling": "05-clothes-accessories", "Shorts Modeling": "05-clothes-accessories",
              "Chest Modeling": "04-sculpt-body", "Cloth Modeling": "05-clothes-accessories",
              "Hand Modeling": "04-sculpt-body", "Head Modeling": "03-sculpt-face", "Hair Modeling": "08-hair",
              "UV Unwrap": "07-uv", "Hand Texture Painting": "09-shading-texturing",
              "Mixamo Rigging": "10-rigging-posing", "Import to Godot": "11-lighting-presenting"}
    assert {t: mc.stage_for(t) for t in expect} == expect
    assert mc.stage_for("<Untitled Chapter 1>") is None
