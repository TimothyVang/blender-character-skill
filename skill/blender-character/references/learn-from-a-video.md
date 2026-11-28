# Learn a method from a video

How the routes in this skill were extracted from YouTube videos, as steps you can repeat on a new video. The scripts
are in `scripts/`. They need Python 3.11+, `yt-dlp`, `ffmpeg` (on PATH or `--ffmpeg DIR`) and Pillow. Speech-to-text
needs `faster-whisper`.

The output is study material for private use. Keep it out of version control (the scripts write a `.gitignore` of
`*` into every output folder) and never republish frames, clips or captions. What goes into the skill is your own
description of the method, with timestamps pointing back to the video and the artist credited.

## 1. Look at the video first

```
yt-dlp --skip-download --print "%(title)s | %(duration)s s | %(upload_date)s | chapters=%(chapters|)j" URL
```

- **Chapters** become the units of work; each chapter title maps to a stage (`make_clips.stage_for`). No chapters:
  the whole video is one chapter.
- **Does anyone speak?** List captions with `--list-subs`. An `en-orig` auto-caption track that reads "Heat. Heat."
  or song lyrics means music only: the video is **silent**. Run `scripts/transcribe.py` on it if unsure: a silent
  video comes out with one stray line.
- **A whole channel:** `yt-dlp --flat-playlist --print "%(id)s\t%(duration)s\t%(title)s" URL/videos` (also
  `/shorts`, `/streams`). Get upload dates per video (`--print "%(upload_date)s"`). Agree the scope before
  downloading: a channel can be tens of hours.

## 2. Download, frames, transcript

```
python scripts/course_grab.py URL [--silent] [--floor 30] [--scene 0.08] [--out references/video-courses]
```

- **What it writes:** `<out>/<id>/` with `<id>.mp4`, `<id>.info.json` and captions; `chapters/NN-<slug>.md` (timed
  transcript, frames linked); `frames/NN-<slug>/HHMMSS.jpg` (scene changes, "right here" moments, at least one per
  `--floor` s); `index.json`.
- **`--silent`** for music-only videos: chapters and frames are kept and transcripts left empty, instead of exiting 2.
- **For a 1-minute Short:** `--floor 2 --scene 0.05` gives a frame every 2 s.
- **"Sign in to confirm you're not a bot" or HTTP 429:** `python -m pip install -U "yt-dlp[default]"` first. If only
  the captions fail (429), download video and info without subtitles, then make the captions yourself:
  `python scripts/transcribe.py <out>/<id>` (Whisper, GPU if present) writes `<id>.en.vtt`. Run `course_grab.py`
  again; it skips what is already there.

## 3. Clips and study sheets

```
python scripts/make_clips.py <out>/<id> [--silent] [--min 8 --max 30]     # 8-30 s clips + clips/manifest.jsonl
python scripts/clip_sheets.py <out>/<id> [--silent]                       # 2x2 full-resolution frames per clip
```

- **Narrated:** each clip starts where a spoken line starts and never crosses a chapter.
- **`--silent`:** each chapter is cut into equal clips of at most `--max` s.
- **A sheet** is four 960x540 frames from the 1080p source, each stamped with its time, with the clip's narration
  underneath. You read sheets, not video.
- **For a Short:** clips of `--min 4 --max 10`. Tiling the 2 s frames into grids of 15 to 25 is quicker to read than
  sheets.

## 4. Read every sheet

Read sheets in time order. With narration, match each spoken step to the frames. Without narration, everything
comes from the screen:

- **the key-cast overlay** (bottom-left of the viewport: "E", "Ctrl R", "G x3", "S Z 0") says which operation ran;
- **the redo panel** (bottom-left: Extrude, Loop Cut and Slide, Bevel, Move, with values) gives the numbers;
- **the header** gives mode, workspace, active brush, Radius px, Strength, Blend, Dyntopo/Remesh and symmetry;
- **the Properties editor** shows modifiers and their settings, materials and node set-ups;
- **the outliner** names objects and counts them (a new `Sphere.0xx` is a new part; a count that drops means a join);
- **the status bar** gives Verts / Faces / Tris (a falling face count means faces were deleted);
- **the viewport label** ("Right Orthographic") gives the view.

Never write a value you cannot read; say it was not visible. Mark what you deduce from before-and-after frames as
inferred.

For a long video, split the sheets between several readers (agents), about 20 to 35 sheets each, by chapter. Each
writes its own files, and you merge them.

## 5. Write labels

One JSON object per line, one to three per sheet, in `annotations/<id>/<stage>.jsonl`:

```json
{"clip_id": "<id>-NN-HHMMSS", "start": 1299.0, "end": 1307.8, "stage": "02-blockout", "step": 1,
 "action": "one concrete sentence", "tool": "mode / brush / operator", "settings": {"only": "values read"},
 "view": "Front Orthographic", "why": "the purpose", "reader_equivalent": "the MCP tool or bpy call",
 "confidence": "seen"}
```

Check before merging:
- every row has exactly these keys;
- every `clip_id` is in the video's clip manifest;
- `start` is inside that clip;
- `confidence` is `seen` or `inferred`;
- every sheet has at least one row.

## 6. Turn it into the skill

- **Choose where it goes.**
  - A different *method*: a new route. Give it a section per stage file, or one reference file when it is short,
    plus a line under "Two routes" in `SKILL.md`.
  - The same method with new detail: add it to the stage file it belongs to.
- **Tag timestamps per source** (`[NQ 00:42:03]`, `[YS 00:13]`) so they cannot be mixed up with the main course's.
- **Write it for an agent with no mouse.** Each step says what was done, the settings read, and the `blender-live`
  call or `bpy` that does the same.
  - Python blocks that were not run say `# not run in Blender`. Parse them at least (`ast.parse`); run them in
    Blender before calling them verified.
- **Code that replays a whole method** (like `scripts/speed_sculpt.py`) emits data: an ordered list of tool calls.
  That way it can be tested without Blender against the server's real tool names, arguments and stroke rules.
- **Add the screen habits** (modes, keys, brushes, settings) to `references/how-they-use-blender.md`.
- **Credit the artist and link the video** in the reference file and the repository README.
