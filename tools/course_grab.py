"""Turn a video course into study material: a transcript per chapter and the frames that go with it.

  python tools/course_grab.py URL_OR_LIST_FILE [--out DIR] [--chapters 3-6] [--ffmpeg DIR]

Per video, in OUT/<video-id>/:
  <id>.mp4, <id>.info.json, <id>.en.vtt     downloaded with yt-dlp (skipped when already there)
  chapters/NN-<slug>.md                     transcript, one timed line per sentence group
  frames/NN-<slug>/HHMMSS.jpg               frames where the picture changes, where the speaker points at
                                            the screen ("right here"), and at least one per --floor seconds
  index.json                                chapters, frames, and the transcript line each frame belongs to

Exit code 0 on success, 2 when a video has no English captions. The material is for private study: keep it
out of version control and do not republish it.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

POINTING_WORDS: tuple[str, ...] = ("right here", "this area", "like this", "like so", "over here", "this part")
YT_FORMAT = "137+140/bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b"
SUB_LANGS = "en,en.*"
SCENE_THRESHOLD = 0.08
GROUP_MAX_S = 12.0

_CUE = re.compile(r"^(\d+):(\d\d):(\d\d)[.,](\d{3})\s+-->")
_TAG = re.compile(r"<[^>]*>")


# ------------------------------------------------------------------ transcript
def parse_vtt(text: str) -> list[tuple[float, str]]:
    """(start seconds, text) per sentence group. Auto-captions repeat each line across cues; repeats are dropped."""
    raw: list[tuple[float, str]] = []
    t = None
    for line in text.splitlines():
        m = _CUE.match(line.strip())
        if m:
            h, mi, s, ms = (int(g) for g in m.groups())
            t = h * 3600 + mi * 60 + s + ms / 1000
            continue
        if t is None:
            continue
        clean = " ".join(html.unescape(_TAG.sub("", line)).split())
        if clean and (not raw or raw[-1][1] != clean):
            raw.append((t, clean))
    groups: list[tuple[float, str]] = []
    start, parts = None, []
    for t, s in raw:
        if start is not None and t - start > GROUP_MAX_S:
            groups.append((start, " ".join(parts)))
            start, parts = None, []
        if start is None:
            start = t
        parts.append(s)
        if s[-1] in ".?!":
            groups.append((start, " ".join(parts)))
            start, parts = None, []
    if parts:
        groups.append((start, " ".join(parts)))
    return groups


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower().encode("ascii", "ignore").decode()).strip("-") or "chapter"


def chapters_from_info(info: dict) -> list[dict]:
    chapters = info.get("chapters") or []
    if not chapters:
        return [{"n": 1, "slug": "full", "title": "Full video", "start": 0.0, "end": float(info.get("duration") or 0)}]
    return [{"n": i, "slug": _slug(c.get("title") or f"chapter-{i}"), "title": c.get("title") or f"Chapter {i}",
             "start": float(c["start_time"]), "end": float(c["end_time"])} for i, c in enumerate(chapters, 1)]


def split_by_chapter(lines: list[tuple[float, str]], chapters: list[dict]) -> dict[int, list[tuple[float, str]]]:
    out: dict[int, list[tuple[float, str]]] = {c["n"]: [] for c in chapters}
    for t, s in lines:
        owner = chapters[-1]
        for c in chapters:
            if c["start"] <= t < c["end"]:
                owner = c
                break
        if t < chapters[0]["start"]:
            owner = chapters[0]
        out[owner["n"]].append((t, s))
    return out


def pointing_times(lines: list[tuple[float, str]]) -> list[float]:
    return [t for t, s in lines if any(w in s.lower() for w in POINTING_WORDS)]


def hhmmss(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}{s % 3600 // 60:02d}{s % 60:02d}"


# ------------------------------------------------------------------ frames
def frame_times(chapter: dict, scene_times: list[float], pointing: list[float], floor_s: float = 30.0,
                min_gap_s: float = 2.0) -> list[float]:
    """Sorted times inside the chapter: pointing moments first, then scene changes, then a floor of one per floor_s.
    No two are closer than min_gap_s."""
    a, b = chapter["start"], chapter["end"]
    kept: list[float] = []
    for group in (sorted(pointing), sorted(scene_times)):
        for t in group:
            if a <= t < b and all(abs(t - k) >= min_gap_s for k in kept):
                kept.append(round(t, 2))
    kept.sort()
    filled: list[float] = []
    prev = a
    for t in kept + [b]:
        gap = t - prev
        if gap > floor_s:
            n = math.ceil(gap / floor_s)
            filled += [round(prev + gap * i / n, 2) for i in range(1, n)]
        if t < b:
            filled.append(t)
        prev = t
    return filled


def build_index(video_id: str, chapters: list[dict], by_chapter: dict, frames: dict[int, list[float]]) -> dict:
    out = []
    for c in chapters:
        name = f"{c['n']:02d}-{c['slug']}"
        lines = by_chapter.get(c["n"], [])
        entries = []
        for t in frames.get(c["n"], []):
            before = [lt for lt, _ in lines if lt <= t]
            entries.append({"t": t, "file": f"frames/{name}/{hhmmss(t)}.jpg",
                            "line_t": before[-1] if before else (lines[0][0] if lines else None)})
        out.append({"n": c["n"], "slug": c["slug"], "title": c["title"], "start": c["start"], "end": c["end"],
                    "transcript": f"chapters/{name}.md", "frames": entries})
    return {"video_id": video_id, "chapters": out}


def find_ffmpeg_dir() -> str | None:
    exe = shutil.which("ffmpeg")
    return str(Path(exe).parent) if exe else None


def _scene_times(video: Path, chapter: dict, ffmpeg_dir: str, threshold: float) -> list[float]:
    """Times where the picture changes, read from keyframes only at a small size (fast on long videos)."""
    cmd = [str(Path(ffmpeg_dir) / "ffmpeg"), "-hide_banner", "-nostats", "-skip_frame", "nokey",
           "-ss", f"{chapter['start']:.3f}", "-t", f"{chapter['end'] - chapter['start']:.3f}", "-i", str(video), "-an",
           "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-vsync", "vfr", "-f", "null", "-"]
    err = subprocess.run(cmd, capture_output=True, text=True, errors="replace").stderr
    return [round(chapter["start"] + float(m), 2) for m in re.findall(r"pts_time:([0-9.]+)", err)]


def _grab_frame(video: Path, t: float, dest: Path, ffmpeg_dir: str) -> None:
    subprocess.run([str(Path(ffmpeg_dir) / "ffmpeg"), "-v", "error", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                    "-q:v", "3", "-y", str(dest)], check=False)


def _parse_chapter_selection(spec: str | None, chapters: list[dict]) -> set[int]:
    if not spec:
        return {c["n"] for c in chapters}
    chosen: set[int] = set()
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        chosen.update(range(int(lo), int(hi or lo) + 1))
    return chosen & {c["n"] for c in chapters}


def _fmt_clock(t: float) -> str:
    s = int(t)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def process_video_dir(dir: Path, video_id: str, ffmpeg_dir: str | None, chapters: str | None = None,
                      floor_s: float = 30.0, threshold: float = SCENE_THRESHOLD) -> int:
    """Build chapters/, frames/ and index.json from the downloaded files in `dir`. Safe to run again."""
    dir = Path(dir)
    info = json.loads((dir / f"{video_id}.info.json").read_text(encoding="utf-8"))
    vtts = sorted(dir.glob(f"{video_id}.en*.vtt"))
    if not vtts:
        print(f"{video_id}: no English captions (expected {video_id}.en.vtt); nothing written", file=sys.stderr)
        return 2
    preferred = dir / f"{video_id}.en.vtt"
    lines = parse_vtt((preferred if preferred.exists() else vtts[0]).read_text(encoding="utf-8", errors="replace"))
    chaps = chapters_from_info(info)
    by = split_by_chapter(lines, chaps)
    video = dir / f"{video_id}.mp4"
    selected = _parse_chapter_selection(chapters, chaps)

    old = {}
    if (dir / "index.json").exists():
        old = {c["n"]: [f["t"] for f in c["frames"]] for c in json.loads((dir / "index.json").read_text())["chapters"]}
    frames: dict[int, list[float]] = {}
    for c in chaps:
        name = f"{c['n']:02d}-{c['slug']}"
        if c["n"] not in selected:
            frames[c["n"]] = old.get(c["n"], [])
            continue
        if not ffmpeg_dir:
            raise RuntimeError("ffmpeg not found: pass --ffmpeg DIR or put ffmpeg on PATH")
        fdir = dir / "frames" / name
        fdir.mkdir(parents=True, exist_ok=True)
        cache = fdir / "_scenes.json"
        if cache.exists():
            scenes = json.loads(cache.read_text())
        else:
            scenes = _scene_times(video, c, ffmpeg_dir, threshold)
            cache.write_text(json.dumps(scenes))
        times = frame_times(c, scenes, pointing_times(by[c["n"]]), floor_s=floor_s)
        got = []
        for t in times:
            dest = fdir / f"{hhmmss(t)}.jpg"
            if not dest.exists():
                _grab_frame(video, t, dest, ffmpeg_dir)
            if dest.exists():
                got.append(t)
        frames[c["n"]] = got
        print(f"{video_id} {name}: {len(by[c['n']])} lines, {len(got)} frames", flush=True)

    index = build_index(video_id, chaps, by, frames)
    (dir / "chapters").mkdir(exist_ok=True)
    url = info.get("webpage_url") or ""
    for c, entry in zip(chaps, index["chapters"]):
        by_line: dict[float, list[str]] = {}
        for f in entry["frames"]:
            by_line.setdefault(f["line_t"], []).append(f["file"])
        body = [f"# {c['n']:02d} {c['title']}", "",
                f"Source: {info.get('title', video_id)} {url} ({_fmt_clock(c['start'])} to {_fmt_clock(c['end'])})",
                "Private study notes. Do not republish.", ""]
        for t, s in by[c["n"]]:
            body.append(f"[{_fmt_clock(t)}] {s}")
            body += [f"    frame: {p}" for p in by_line.get(t, [])]
        (dir / entry["transcript"]).write_text("\n".join(body) + "\n", encoding="utf-8")
    (dir / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return 0


# ------------------------------------------------------------------ download + CLI
def _video_id(url: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", url)
    if m:
        return m.group(1)
    out = subprocess.run(["yt-dlp", "--no-playlist", "--skip-download", "--print", "id", url], capture_output=True, text=True)
    return out.stdout.strip().splitlines()[-1]


def protect_output(out_root: Path) -> None:
    """Course material is someone else's work: keep the whole output folder out of git, wherever it is."""
    out_root = Path(out_root); out_root.mkdir(parents=True, exist_ok=True)
    (out_root / ".gitignore").write_text("*\n", encoding="utf-8")


def download(url: str, out_root: Path, ffmpeg_dir: str | None) -> tuple[Path, str]:
    vid = _video_id(url)
    d = out_root / vid
    d.mkdir(parents=True, exist_ok=True)
    have = (d / f"{vid}.mp4").exists() and (d / f"{vid}.info.json").exists() and any(d.glob(f"{vid}.en*.vtt"))
    if have:
        print(f"{vid}: already downloaded", flush=True)
        return d, vid
    cmd = ["yt-dlp", "--no-playlist", "-f", YT_FORMAT, "--merge-output-format", "mp4", "--write-auto-subs", "--write-subs",
           "--sub-langs", SUB_LANGS, "--sub-format", "vtt", "--write-info-json", "--no-progress", "--no-overwrites",
           "-o", str(d / "%(id)s.%(ext)s"), url]
    if ffmpeg_dir:
        cmd[1:1] = ["--ffmpeg-location", ffmpeg_dir]
    subprocess.run(cmd, check=False)
    return d, vid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target", help="a video URL, or a text file with one URL per line")
    ap.add_argument("--out", default="references/video-courses")
    ap.add_argument("--chapters", default=None, help="chapters to pull frames for, e.g. 3-6 or 2,5 (default: all)")
    ap.add_argument("--ffmpeg", default=None, help="folder holding ffmpeg (default: the one on PATH)")
    ap.add_argument("--floor", type=float, default=30.0, help="at least one frame per this many seconds")
    ap.add_argument("--scene", type=float, default=SCENE_THRESHOLD, help="scene-change sensitivity (lower = more frames)")
    a = ap.parse_args(argv)
    ffmpeg_dir = a.ffmpeg or find_ffmpeg_dir()
    urls = [a.target]
    if Path(a.target).is_file():
        urls = [u.strip() for u in Path(a.target).read_text().splitlines() if u.strip() and not u.startswith("#")]
    protect_output(Path(a.out))
    worst = 0
    for url in urls:
        d, vid = download(url, Path(a.out), ffmpeg_dir)
        if not (d / f"{vid}.info.json").exists() or not (d / f"{vid}.mp4").exists():
            print(f"{vid}: download failed", file=sys.stderr)
            worst = max(worst, 1)
            continue
        worst = max(worst, process_video_dir(d, vid, ffmpeg_dir, a.chapters, a.floor, a.scene))
    return worst


if __name__ == "__main__":
    sys.exit(main())
