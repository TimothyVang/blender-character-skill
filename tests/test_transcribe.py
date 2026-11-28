import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skill" / "blender-character" / "scripts"))
import course_grab as cg  # noqa: E402
import transcribe as tr  # noqa: E402


def test_vtt_round_trips_through_the_course_parser():
    vtt = tr.to_vtt([(0.5, 2.0, " start with a sphere. "), (3.25, 5.0, ""), (3725.1, 3727.0, "pull down his face.")])
    assert "01:02:05.100 --> 01:02:07.000" in vtt and vtt.count(" --> ") == 2
    lines = cg.parse_vtt(vtt)
    assert [s for _, s in lines] == ["start with a sphere.", "pull down his face."]
    assert lines[0][0] == 0.5 and abs(lines[1][0] - 3725.1) < 1e-6


def test_missing_video_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "_model", lambda name: object())
    (tmp_path / "abc").mkdir()
    assert tr.main([str(tmp_path / "abc")]) == 1
