"""Cut a grabbed course into short captioned clips for training: each clip is the video while the narrator says one
stretch of the transcript, with that text in a manifest.

  python tools/make_clips.py references/video-courses/<video-id> [--min 8] [--max 30] [--height 720]
                             [--chapters 3-6] [--workers 4] [--encoder h264_nvenc] [--ffmpeg DIR]

Needs what course_grab.py downloads (<id>.mp4, <id>.info.json, <id>.en*.vtt). Writes, in <dir>/clips/:
  NN-<slug>/<HHMMSS>-<HHMMSS>.mp4     one clip per segment, H.264 + AAC
  manifest.jsonl                      one line per clip: id, video_id, chapter_n, chapter, stage, start, end,
                                      duration, text, file (relative to <dir>)
Segments never cross a chapter boundary, start where a transcript line starts, and run from min to max seconds.
--silent (a video with no narration): every chapter is cut into equal clips of at most --max seconds, with no text.
Running it again only cuts what is missing. The clips are someone else's course: keep them for private use.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_grab as cg  # noqa: E402

STAGES = [   # chapter-title words -> the skill's stage file
    ("concept", "01-concept-and-references"), ("blocking", "02-blockout"), ("face", "03-sculpt-face"),
    ("sculpting the body", "04-sculpt-body"), ("clothes", "05-clothes-accessories"), ("retopolog", "06-retopology"),
    ("uv", "07-uv"), ("hair", "08-hair"), ("shading", "09-shading-texturing"), ("texturing", "09-shading-texturing"),
    ("rigging", "10-rigging-posing"), ("posing", "10-rigging-posing"), ("lighting", "11-lighting-presenting"),
    ("render", "11-lighting-presenting"),
    # chapter titles of a box-modelling speed-model (low-poly game character); checked after the words above
    ("reference", "01-concept-and-references"), ("base shape", "02-blockout"), ("texture", "09-shading-texturing"),
    ("head", "03-sculpt-face"), ("chest", "04-sculpt-body"), ("hand", "04-sculpt-body"), ("shoe", "05-clothes-accessories"),
    ("short", "05-clothes-accessories"), ("cloth", "05-clothes-accessories"), ("godot", "11-lighting-presenting"),
    ("export", "11-lighting-presenting"),
]


def stage_for(title: str) -> str | None:
    t = title.lower()
    if "sculpting the clothes" in t: return "05-clothes-accessories"
    if "retopolog" in t: return "06-retopology"
    for word, stage in STAGES:
        if word in t: return stage
    return None


def segments(by_chapter: dict, chapters: list[dict], min_s: float = 8.0, max_s: float = 30.0,
             cover_silent: bool = False) -> list[dict]:
    """Consecutive transcript lines merged into segments of min_s..max_s seconds. A segment ends where the next one
    starts (or at the chapter end); a stretch longer than max_s is split into equal parts, the text going with the
    first part only. A chapter with no lines is skipped, or with cover_silent=True cut into equal silent parts."""
    out = []
    for c in chapters:
        lines = sorted(by_chapter.get(c["n"], []))
        if not lines:
            if cover_silent and c["end"] > c["start"]:
                out += _split({"start": c["start"], "end": c["end"], "texts": []}, c, max_s)
            continue
        starts = [max(c["start"], t) for t, _ in lines] + [c["end"]]
        groups, cur = [], None
        for i, (_, text) in enumerate(lines):
            if cur is None: cur = {"start": starts[i], "texts": []}
            cur["texts"].append(text)
            if starts[i + 1] - cur["start"] >= min_s:
                cur["end"] = starts[i + 1]; groups.append(cur); cur = None
        if cur is not None:                                   # a short tail joins the previous segment if it can
            cur["end"] = c["end"]
            if groups and cur["end"] - groups[-1]["start"] <= max_s:
                groups[-1]["texts"] += cur["texts"]; groups[-1]["end"] = cur["end"]
            else:
                groups.append(cur)
        for g in groups:
            out += _split(g, c, max_s)
    return out


def _split(g: dict, c: dict, max_s: float) -> list[dict]:
    """One group as equal parts of at most max_s seconds; its text goes with the first part only."""
    out = []
    span = g["end"] - g["start"]
    n = max(1, math.ceil(span / max_s - 1e-9))
    for k in range(n):
        a = g["start"] + span * k / n; b = g["start"] + span * (k + 1) / n
        if b - a < 0.5: continue
        out.append({"chapter_n": c["n"], "chapter": c["title"], "slug": c["slug"], "stage": stage_for(c["title"]),
                    "start": round(a, 3), "end": round(b, 3), "text": " ".join(g["texts"]) if k == 0 else ""})
    return out


ENCODERS = {
    "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "26"],
    "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"],
}


def _cut(video: Path, seg: dict, dest: Path, ffmpeg_dir: str, height: int, encoder: str) -> bool:
    tmp = dest.with_suffix(".part.mp4")
    cmd = [str(Path(ffmpeg_dir) / "ffmpeg"), "-v", "error", "-y", "-ss", f"{seg['start']:.3f}", "-i", str(video),
           "-t", f"{seg['end'] - seg['start']:.3f}", "-vf", f"scale=-2:{height}", *ENCODERS[encoder],
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(tmp)]
    ok = subprocess.run(cmd, capture_output=True).returncode == 0 and tmp.exists() and tmp.stat().st_size > 0
    if ok: tmp.replace(dest)
    elif tmp.exists(): tmp.unlink()
    return ok


def make_clips(dir: Path, video_id: str, ffmpeg_dir: str | None, min_s: float = 8.0, max_s: float = 30.0,
               height: int = 720, chapters: str | None = None, workers: int = 4, encoder: str = "h264_nvenc",
               silent: bool = False) -> int:
    dir = Path(dir)
    if not ffmpeg_dir: raise RuntimeError("ffmpeg not found: pass --ffmpeg DIR or put ffmpeg on PATH")
    if encoder not in ENCODERS: raise ValueError(f"encoder must be one of {', '.join(ENCODERS)}")
    info = json.loads((dir / f"{video_id}.info.json").read_text(encoding="utf-8"))
    try:
        lines = cg.read_lines(dir, video_id, silent)
    except FileNotFoundError:
        print(f"{video_id}: no English captions; nothing cut (pass --silent if it has no narration)", file=sys.stderr)
        return 2
    video = dir / f"{video_id}.mp4"
    chaps = cg.chapters_from_info(info)
    selected = cg._parse_chapter_selection(chapters, chaps)
    segs = [s for s in segments(cg.split_by_chapter(lines, chaps), chaps, min_s, max_s, cover_silent=silent)
            if s["chapter_n"] in selected]
    out = dir / "clips"; out.mkdir(exist_ok=True)
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    jobs = []
    for s in segs:
        rel = f"clips/{s['chapter_n']:02d}-{s['slug']}/{cg.hhmmss(s['start'])}-{cg.hhmmss(s['end'])}.mp4"
        s["file"] = rel
        dest = dir / rel; dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists(): jobs.append((s, dest))
    print(f"{video_id}: {len(segs)} segments, {len(jobs)} to cut", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, ((s, dest), ok) in enumerate(zip(jobs, pool.map(lambda j: _cut(video, j[0], j[1], ffmpeg_dir, height, encoder), jobs)), 1):
            if not ok: failed.append(s["file"])
            if i % 200 == 0: print(f"  {i}/{len(jobs)} cut", flush=True)
    rows = []
    for s in segs:
        if not (dir / s["file"]).exists(): continue
        rows.append({"id": f"{video_id}-{s['chapter_n']:02d}-{cg.hhmmss(s['start'])}", "video_id": video_id,
                     "chapter_n": s["chapter_n"], "chapter": s["chapter"], "stage": s["stage"], "start": s["start"],
                     "end": s["end"], "duration": round(s["end"] - s["start"], 3), "text": s["text"], "file": s["file"]})
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{video_id}: {len(rows)} clips in manifest, {len(failed)} failed", flush=True)
    for f in failed[:10]: print("  failed:", f, file=sys.stderr)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir", help="a video's folder made by course_grab.py")
    ap.add_argument("--min", type=float, default=8.0); ap.add_argument("--max", type=float, default=30.0)
    ap.add_argument("--height", type=int, default=720); ap.add_argument("--chapters", default=None)
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--encoder", default="h264_nvenc", choices=list(ENCODERS))
    ap.add_argument("--ffmpeg", default=None)
    ap.add_argument("--silent", action="store_true", help="no narration: cut every chapter into equal clips")
    a = ap.parse_args(argv)
    d = Path(a.dir)
    return make_clips(d, d.name, a.ffmpeg or cg.find_ffmpeg_dir(), a.min, a.max, a.height, a.chapters, a.workers, a.encoder,
                      a.silent)


if __name__ == "__main__":
    sys.exit(main())
