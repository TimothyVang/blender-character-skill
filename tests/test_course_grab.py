import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import course_grab as cg  # noqa: E402

FFMPEG = os.environ.get("FFMPEG_DIR") or cg.find_ffmpeg_dir()

VTT = """WEBVTT
Kind: captions
Language: en

00:44:12.390 --> 00:44:12.400 align:start position:0%
chest of the character. And I'm also


00:44:12.400 --> 00:44:14.870 align:start position:0%
chest of the character. And I'm also
going<00:44:12.560><c> to</c><00:44:12.720><c> pull</c><00:44:12.960><c> out</c><00:44:13.280><c> this</c><00:44:13.599><c> area</c><00:44:14.079><c> right</c><00:44:14.319><c> here.</c>

00:44:14.870 --> 00:44:14.880 align:start position:0%
going to pull out this area right here.

"""


def test_parse_vtt_removes_rolling_duplicates_and_tags():
    lines = cg.parse_vtt(VTT)
    text = " ".join(t for _, t in lines)
    assert text.count("chest of the character") == 1
    assert text.count("pull out this area right here") == 1
    assert "<" not in text
    assert lines[0][0] == pytest.approx(2652.39, abs=0.5)


def test_chapters_from_info_and_no_chapters():
    info = {"duration": 100, "chapters": [{"start_time": 0, "title": "Introduction", "end_time": 40},
                                          {"start_time": 40, "title": "Blocking Out Your Character", "end_time": 100}]}
    ch = cg.chapters_from_info(info)
    assert [c["slug"] for c in ch] == ["introduction", "blocking-out-your-character"]
    assert ch[1]["n"] == 2 and ch[1]["start"] == 40
    assert cg.chapters_from_info({"duration": 100, "chapters": None}) == [
        {"n": 1, "slug": "full", "title": "Full video", "start": 0.0, "end": 100.0}]


def test_split_by_chapter_and_pointing_times():
    ch = cg.chapters_from_info({"duration": 100, "chapters": [{"start_time": 0, "title": "A", "end_time": 40},
                                                              {"start_time": 40, "title": "B", "end_time": 100}]})
    lines = [(5.0, "we start with a sphere"), (41.0, "pull out this area right here"), (60.0, "nice")]
    by = cg.split_by_chapter(lines, ch)
    assert [t for t, _ in by[1]] == [5.0] and [t for t, _ in by[2]] == [41.0, 60.0]
    assert cg.pointing_times(lines) == [41.0]


def test_hhmmss():
    assert cg.hhmmss(2652.4) == "004412"


def test_frame_times_floor_gap_and_bounds():
    ch = {"n": 1, "slug": "a", "title": "A", "start": 0.0, "end": 100.0}
    t = cg.frame_times(ch, scene_times=[10.0, 10.5, 150.0], pointing=[55.0], floor_s=30.0, min_gap_s=2.0)
    assert t == sorted(t) and all(0 <= x < 100 for x in t)
    assert 10.0 in t and 10.5 not in t and 55.0 in t
    assert all(b - a >= 2.0 for a, b in zip(t, t[1:]))
    assert max(b - a for a, b in zip([0.0] + t, t + [100.0])) <= 30.0


def test_build_index_links_frame_to_line():
    ch = [{"n": 1, "slug": "a", "title": "A", "start": 0.0, "end": 100.0}]
    idx = cg.build_index("vid", ch, {1: [(5.0, "x"), (41.0, "y")]}, {1: [45.0]})
    f = idx["chapters"][0]["frames"][0]
    assert f == {"t": 45.0, "file": "frames/01-a/000045.jpg", "line_t": 41.0}
    assert idx["chapters"][0]["transcript"] == "chapters/01-a.md"


def test_missing_captions_exits_2(tmp_path):
    (tmp_path / "vid").mkdir()
    (tmp_path / "vid" / "vid.info.json").write_text('{"id": "vid", "duration": 10, "chapters": null}')
    (tmp_path / "vid" / "vid.mp4").write_bytes(b"")
    assert cg.process_video_dir(tmp_path / "vid", "vid", ffmpeg_dir=None) == 2
    assert not (tmp_path / "vid" / "chapters").exists()


@pytest.fixture
def short_clip(tmp_path):
    """A 20 s test video (two different pictures, so there is one scene change) with captions and metadata."""
    if not FFMPEG:
        pytest.skip("ffmpeg not found; set FFMPEG_DIR")
    d = tmp_path / "clip"
    d.mkdir()
    exe = str(Path(FFMPEG) / "ffmpeg")
    subprocess.run([exe, "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=10:size=320x240:rate=10",
                    "-f", "lavfi", "-i", "smptebars=duration=10:size=320x240:rate=10",
                    "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]", "-pix_fmt", "yuv420p",
                    str(d / "clip.mp4")], check=True)
    (d / "clip.info.json").write_text('{"id": "clip", "duration": 20, "chapters": null}')
    (d / "clip.en.vtt").write_text(
        "WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nwe start with a sphere.\n\n"
        "00:00:12.000 --> 00:00:15.000\npull out this area right here.\n")
    return d


def test_output_folder_is_kept_out_of_git(tmp_path):
    out = tmp_path / "anything"
    cg.protect_output(out)
    assert (out / ".gitignore").read_text().strip() == "*"


def test_english_caption_variants_are_found(tmp_path):
    d = tmp_path / "v"; d.mkdir()
    (d / "v.info.json").write_text('{"id": "v", "duration": 10, "chapters": null}')
    (d / "v.en-US.vtt").write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nhello there.\n")
    assert cg.process_video_dir(d, "v", ffmpeg_dir=None, chapters="2") == 0
    assert "hello there." in (d / "chapters" / "01-full.md").read_text()
    assert "en.*" in cg.SUB_LANGS


def test_rerun_is_idempotent(short_clip):
    assert cg.process_video_dir(short_clip, "clip", ffmpeg_dir=FFMPEG) == 0
    first = (short_clip / "index.json").read_text()
    n = len(list((short_clip / "frames").rglob("*.jpg")))
    assert cg.process_video_dir(short_clip, "clip", ffmpeg_dir=FFMPEG) == 0
    assert (short_clip / "index.json").read_text() == first
    assert len(list((short_clip / "frames").rglob("*.jpg"))) == n and n > 0
    assert (short_clip / "chapters" / "01-full.md").read_text().count("pull out this area right here") == 1
