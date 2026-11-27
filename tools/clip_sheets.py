"""Study sheets for clips: four full-resolution frames from each clip in a 2x2 grid with its time and transcript
underneath, so someone who cannot play video (an agent) can see what the artist did on screen.

  python tools/clip_sheets.py references/video-courses/<video-id> [--chapters 3-6] [--workers 6] [--ffmpeg DIR]

Reads clips/manifest.jsonl (from make_clips.py) and samples frames from the 1080p source video, not from the smaller
clips, so panels and menus stay readable. Writes sheets/NN-<slug>/<clip>.jpg and sheets/index.jsonl (the manifest row
plus `sheet`). Running it again only makes what is missing. Private study material: keep it out of version control.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import course_grab as cg  # noqa: E402

CELL = (960, 540)
BAND = 150


def sample_times(start: float, end: float, n: int = 4) -> list[float]:
    span = end - start
    return [round(start + span * (i + 0.5) / n, 3) for i in range(n)]


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try: return ImageFont.truetype(name, size)
        except OSError: pass
    return ImageFont.load_default()


def _frame(video: Path, t: float, ffmpeg_dir: str) -> Image.Image | None:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "f.png"
        subprocess.run([str(Path(ffmpeg_dir) / "ffmpeg"), "-v", "error", "-ss", f"{t:.3f}", "-i", str(video),
                        "-frames:v", "1", "-y", str(out)], capture_output=True)
        if not out.exists(): return None
        return Image.open(out).convert("RGB").copy()


def _sheet(video: Path, row: dict, dest: Path, ffmpeg_dir: str) -> bool:
    times = sample_times(row["start"], row["end"])
    sheet = Image.new("RGB", (CELL[0] * 2, CELL[1] * 2 + BAND), (20, 20, 20))
    d = ImageDraw.Draw(sheet); small, big = _font(22), _font(24)
    got = 0
    for i, t in enumerate(times):
        f = _frame(video, t, ffmpeg_dir)
        x, y = (i % 2) * CELL[0], (i // 2) * CELL[1]
        if f is not None:
            sheet.paste(f.resize(CELL, Image.LANCZOS), (x, y)); got += 1
        clock = f"{int(t) // 3600:02d}:{int(t) % 3600 // 60:02d}:{int(t) % 60:02d}"
        d.rectangle((x, y, x + 130, y + 30), fill=(0, 0, 0)); d.text((x + 8, y + 3), clock, fill=(255, 220, 80), font=small)
    head = f"{row['id']}  {row['chapter']}  stage {row['stage'] or '-'}  {row['start']:.1f}s to {row['end']:.1f}s"
    d.text((12, CELL[1] * 2 + 8), head, fill=(255, 220, 80), font=small)
    for k, line in enumerate(textwrap.wrap(row["text"] or "(no speech)", 150)[:4]):
        d.text((12, CELL[1] * 2 + 38 + k * 27), line, fill=(235, 235, 235), font=big)
    if not got: return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part.jpg"); sheet.save(tmp, "JPEG", quality=85); tmp.replace(dest)
    return True


def planned_rows(dir: Path, video_id: str, min_s: float = 8.0, max_s: float = 30.0) -> list[dict]:
    import make_clips as mc
    info = json.loads((dir / f"{video_id}.info.json").read_text(encoding="utf-8"))
    vtts = sorted(dir.glob(f"{video_id}.en*.vtt"))
    if not vtts: raise FileNotFoundError(f"{video_id}: no English captions")
    preferred = dir / f"{video_id}.en.vtt"
    lines = cg.parse_vtt((preferred if preferred.exists() else vtts[0]).read_text(encoding="utf-8", errors="replace"))
    chaps = cg.chapters_from_info(info)
    rows = []
    for s in mc.segments(cg.split_by_chapter(lines, chaps), chaps, min_s, max_s):
        rows.append({"id": f"{video_id}-{s['chapter_n']:02d}-{cg.hhmmss(s['start'])}", "video_id": video_id,
                     "chapter_n": s["chapter_n"], "chapter": s["chapter"], "stage": s["stage"], "start": s["start"],
                     "end": s["end"], "duration": round(s["end"] - s["start"], 3), "text": s["text"],
                     "file": f"clips/{s['chapter_n']:02d}-{s['slug']}/{cg.hhmmss(s['start'])}-{cg.hhmmss(s['end'])}.mp4"})
    return rows


def make_sheets(dir: Path, video_id: str, ffmpeg_dir: str | None, chapters: str | None = None, workers: int = 6) -> int:
    dir = Path(dir)
    if not ffmpeg_dir: raise RuntimeError("ffmpeg not found: pass --ffmpeg DIR or put ffmpeg on PATH")
    manifest = dir / "clips" / "manifest.jsonl"
    if manifest.exists():
        rows = [json.loads(l) for l in manifest.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:                      # clips not cut yet: work out the same segments make_clips.py will use
        rows = planned_rows(dir, video_id)
    if chapters:
        keep = cg._parse_chapter_selection(chapters, [{"n": r["chapter_n"]} for r in rows])
        rows = [r for r in rows if r["chapter_n"] in keep]
    video = dir / f"{video_id}.mp4"
    out = dir / "sheets"; out.mkdir(exist_ok=True)
    (out / ".gitignore").write_text("*\n", encoding="utf-8")
    for r in rows: r["sheet"] = "sheets/" + r["file"].split("/", 1)[1].replace(".mp4", ".jpg")
    todo = [r for r in rows if not (dir / r["sheet"]).exists()]
    print(f"{video_id}: {len(rows)} clips, {len(todo)} sheets to make", flush=True)
    failed = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for i, (r, ok) in enumerate(zip(todo, pool.map(lambda r: _sheet(video, r, dir / r["sheet"], ffmpeg_dir), todo)), 1):
            if not ok: failed.append(r["id"])
            if i % 200 == 0: print(f"  {i}/{len(todo)} sheets", flush=True)
    done = [r for r in rows if (dir / r["sheet"]).exists()]
    old = {}
    if (out / "index.jsonl").exists():
        old = {json.loads(l)["id"]: l for l in (out / "index.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    for r in done: old[r["id"]] = json.dumps(r, ensure_ascii=False)
    (out / "index.jsonl").write_text("".join(v + "\n" for _, v in sorted(old.items())), encoding="utf-8")
    print(f"{video_id}: {len(done)} sheets, {len(failed)} failed", flush=True)
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dir"); ap.add_argument("--chapters", default=None)
    ap.add_argument("--workers", type=int, default=6); ap.add_argument("--ffmpeg", default=None)
    a = ap.parse_args(argv)
    d = Path(a.dir)
    return make_sheets(d, d.name, a.ffmpeg or cg.find_ffmpeg_dir(), a.chapters, a.workers)


if __name__ == "__main__":
    sys.exit(main())
