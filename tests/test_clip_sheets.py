import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "blender-character" / "scripts"))
import course_grab as cg  # noqa: E402
import clip_sheets as cs  # noqa: E402

FFMPEG = os.environ.get("FFMPEG_DIR") or cg.find_ffmpeg_dir()


def test_sample_times_spread_inside_the_clip():
    t = cs.sample_times(10.0, 30.0, 4)
    assert len(t) == 4 and t == sorted(t) and 10.0 < t[0] and t[-1] < 30.0
    assert t[1] - t[0] == pytest.approx(t[2] - t[1])


@pytest.fixture
def course(tmp_path):
    if not FFMPEG:
        pytest.skip("ffmpeg not found; set FFMPEG_DIR")
    d = tmp_path / "clip"; (d / "clips").mkdir(parents=True)
    subprocess.run([str(Path(FFMPEG) / "ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=30:size=1920x1080:rate=10",
                    "-pix_fmt", "yuv420p", str(d / "clip.mp4")], check=True)
    rows = [{"id": "clip-01-000000", "video_id": "clip", "chapter_n": 1, "chapter": "Blocking Out", "stage": "02-blockout",
             "start": 0.0, "end": 12.0, "duration": 12.0, "text": "we start with a sphere.", "file": "clips/01-a/000000-000012.mp4"},
            {"id": "clip-01-000012", "video_id": "clip", "chapter_n": 1, "chapter": "Blocking Out", "stage": "02-blockout",
             "start": 12.0, "end": 30.0, "duration": 18.0, "text": "pull out this area right here.", "file": "clips/01-a/000012-000030.mp4"}]
    (d / "clips" / "manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return d


def test_planned_rows_match_make_clips(tmp_path):
    d = tmp_path / "v"; d.mkdir()
    (d / "v.info.json").write_text(json.dumps({"id": "v", "duration": 60, "chapters": [
        {"start_time": 0, "end_time": 60, "title": "Sculpting the Face of Your Character"}]}))
    (d / "v.en.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nfirst.\n\n00:00:20.000 --> 00:00:24.000\nsecond.\n")
    rows = cs.planned_rows(d, "v")
    assert rows[0]["file"] == "clips/01-sculpting-the-face-of-your-character/000001-000020.mp4"
    assert rows[0]["stage"] == "03-sculpt-face" and rows[0]["text"] == "first."


def test_sheets_written_once_with_index(course):
    assert cs.make_sheets(course, "clip", ffmpeg_dir=FFMPEG, workers=2) == 0
    idx = [json.loads(l) for l in (course / "sheets" / "index.jsonl").read_text().splitlines()]
    assert len(idx) == 2 and all((course / r["sheet"]).exists() for r in idx)
    im = Image.open(course / idx[0]["sheet"])
    assert im.size[0] == 1920 and im.size[1] > 1080            # 2x2 of 960x540 plus a caption band
    assert idx[1]["text"] == "pull out this area right here." and idx[1]["stage"] == "02-blockout"
    m = (course / idx[0]["sheet"]).stat().st_mtime
    assert cs.make_sheets(course, "clip", ffmpeg_dir=FFMPEG, workers=2) == 0
    assert (course / idx[0]["sheet"]).stat().st_mtime == m
    assert (course / "sheets" / ".gitignore").read_text().strip() == "*"


def test_frame_pipes_png_without_tempdir(course, monkeypatch):
    def forbid_tempdir(*args, **kwargs):
        raise AssertionError("_frame must not create temporary directories")

    import tempfile
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbid_tempdir)
    im = cs._frame(course / "clip.mp4", 5.0, FFMPEG)
    assert im is not None and im.mode == "RGB" and im.size == (1920, 1080)

    def bad_ffmpeg(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(cs.subprocess, "run", bad_ffmpeg)
    assert cs._frame(course / "clip.mp4", 5.0, FFMPEG) is None


def test_planned_rows_for_a_silent_video(tmp_path):
    d = tmp_path / "q"; d.mkdir()
    (d / "q.info.json").write_text('{"id": "q", "duration": 60, "chapters": [{"start_time": 0, "end_time": 60, "title": "Head Modeling"}]}')
    rows = cs.planned_rows(d, "q", silent=True)
    assert len(rows) == 2 and rows[0]["stage"] == "03-sculpt-face" and rows[-1]["end"] == 60
