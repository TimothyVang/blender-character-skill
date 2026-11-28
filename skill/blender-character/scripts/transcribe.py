"""Transcribe a downloaded video's speech into <id>.en.vtt, for when YouTube's captions are missing or rate-limited
(HTTP 429). Needs faster-whisper (pip install faster-whisper); uses the GPU when there is one.

  python transcribe.py references/video-courses/<video-id> [more dirs...] [--model small.en] [--force]

Writes <dir>/<id>.en.vtt next to <id>.mp4, which course_grab.py, make_clips.py and clip_sheets.py then read as the
narration. A music-only video comes out with one or two stray lines ("Thanks for watching!"): treat it as silent
(--silent in the other scripts). Skips a dir that already has <id>.en.vtt unless --force. Exit 2 when faster-whisper
is not installed.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def stamp(t: float) -> str:
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h:02d}:{m:02d}:{t % 60:06.3f}"


def to_vtt(segments) -> str:
    """segments: objects or tuples with start, end, text."""
    lines = ["WEBVTT", ""]
    for s in segments:
        start, end, text = (s.start, s.end, s.text) if hasattr(s, "start") else s
        text = " ".join(str(text).split())
        if text:
            lines += [f"{stamp(start)} --> {stamp(end)}", text, ""]
    return "\n".join(lines) + "\n"


def _model(name: str):
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(name, device="cuda", compute_type="float16")
    except Exception:                                   # no CUDA: fall back to CPU
        return WhisperModel(name, device="cpu", compute_type="int8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dirs", nargs="+", help="video folders made by course_grab.py (or holding <id>.mp4)")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--force", action="store_true", help="overwrite an existing <id>.en.vtt")
    a = ap.parse_args(argv)
    try:
        model = _model(a.model)
    except ImportError:
        print("faster-whisper is not installed: pip install faster-whisper", file=sys.stderr)
        return 2
    worst = 0
    for d in map(Path, a.dirs):
        vid = d.name
        video, out = d / f"{vid}.mp4", d / f"{vid}.en.vtt"
        if not video.is_file():
            print(f"{vid}: no {video.name}", file=sys.stderr); worst = 1; continue
        if out.exists() and not a.force:
            print(f"{vid}: {out.name} already there"); continue
        segs, _ = model.transcribe(str(video), language="en", vad_filter=True)
        text = to_vtt(segs)
        out.write_text(text, encoding="utf-8")
        print(f"{vid}: {text.count(' --> ')} lines")
    return worst


if __name__ == "__main__":
    sys.exit(main())
