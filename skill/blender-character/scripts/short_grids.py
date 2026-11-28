"""Tile each grabbed Short's frames into numbered grids, the quickest way for an agent to read a 1-minute video.

  python scripts/short_grids.py references/video-courses/<channel> [--per 10] [--cols 5] [--cell 360]

For every video folder under the root that course_grab.py filled (frames/*/HHMMSS.jpg), writes grids/gridNN.jpg:
`--per` frames in `--cols` columns, each cell `--cell` px wide (height kept to the frame's aspect, so a vertical Short
gets tall cells) and stamped with its time. Also writes <root>/grids_index.json: id, title, duration, frame count and
grid paths per video. Private study material: keep it out of version control.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try: return ImageFont.truetype(name, size)
        except OSError: pass
    return ImageFont.load_default()


def stamp(stem: str) -> str:
    return f"{stem[0:2]}:{stem[2:4]}:{stem[4:6]}" if len(stem) == 6 and stem.isdigit() else stem


def grids_for(video_dir: Path, per: int = 10, cols: int = 5, cell: int = 360) -> list[Path]:
    frames = sorted(video_dir.glob("frames/*/*.jpg"))
    if not frames: return []
    with Image.open(frames[0]) as im: w, h = im.size
    cw, ch = cell, round(cell * h / w)
    out = video_dir / "grids"; out.mkdir(exist_ok=True)
    font = _font(max(14, cell // 14)); paths = []
    for gi in range(0, len(frames), per):
        chunk = frames[gi:gi + per]
        rows = -(-len(chunk) // cols)
        sheet = Image.new("RGB", (cw * cols, ch * rows), "black"); dr = ImageDraw.Draw(sheet)
        for k, f in enumerate(chunk):
            with Image.open(f) as im: sheet.paste(im.convert("RGB").resize((cw, ch)), (x := k % cols * cw, y := k // cols * ch))
            dr.rectangle([x, y, x + cell * 0.36, y + cell * 0.09], fill="black")
            dr.text((x + 4, y + 2), stamp(f.stem), fill="yellow", font=font)
        p = out / f"grid{gi // per + 1:02d}.jpg"; sheet.save(p, quality=88); paths.append(p)
    return paths


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", help="folder holding one course_grab.py folder per video")
    ap.add_argument("--per", type=int, default=10, help="frames per grid")
    ap.add_argument("--cols", type=int, default=5)
    ap.add_argument("--cell", type=int, default=360, help="cell width in px")
    a = ap.parse_args(argv)
    root = Path(a.root); index = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        grids = grids_for(d, a.per, a.cols, a.cell)
        if not grids: continue
        info = next(d.glob("*.info.json"), None)
        meta = json.loads(info.read_text(encoding="utf-8")) if info else {}
        index.append({"id": d.name, "title": meta.get("title"), "duration": meta.get("duration"),
                      "frames": len(list(d.glob("frames/*/*.jpg"))), "grids": [str(g) for g in grids]})
    (root / "grids_index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(f"{len(index)} videos, {sum(len(i['grids']) for i in index)} grids")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
