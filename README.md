# blender-character-skill

Teach an AI agent to build a character in Blender from concept pictures, by hand: blockout, sculpt, clothes,
retopology, UVs, hair, shading, rig, lighting.

Three parts:

| Part | Where | What it does |
|------|-------|--------------|
| The skill | `skill/blender-character/` | A Claude skill: one entry file and one reference file per stage of the character pipeline. |
| The MCP server | `mcp/blender-live/` | Drives a running Blender: run Python, capture the viewport, sculpt, remesh, mask, place references, and measure the model's outline against reference pictures. |
| The course grabber | `tools/course_grab.py` | Turns a video course into a transcript per chapter plus the frames that go with it, for writing skills like this one. |

## Status

- **MCP sculpt and review tools:** tested against a live Blender 4.5.16 (`mcp/blender-live/sculpt_smoke.py`, 45 checks).
- **Outline measuring and course grabber:** tested without Blender (`tests/`, 19 tests).
- **Skill stage files:** written from the course. They have **not yet been proven** by an agent building a full
  character with them. Bpy snippets are marked in each file as verified in background Blender or not verified.

## Set up

Needs [uv](https://docs.astral.sh/uv/), Blender 4.5, and for the grabber `yt-dlp` and `ffmpeg`.

1. Register the MCP server with your client (see `mcp/mcp-client.example.json`), pointing `BLENDER_EXE` at your
   Blender. The server starts Blender with its bridge when you call `blender_launch`.
2. Copy `skill/blender-character/` into your skills folder (for Claude Code: `~/.claude/skills/`).
3. Ask for a character and give it reference pictures.

Run the tool checks yourself:

```
uv run --script mcp/blender-live/sculpt_smoke.py .scratch/sculpt-smoke
python -m pytest tests
```

## Security

The bridge listens on 127.0.0.1 only, and its `exec` command runs any Python it is sent. Any program on the same
computer can send it. Set `BLENDER_LIVE_TOKEN` (the same value for Blender and the MCP server) to require a token.

## How likeness is measured

`outline_match` captures the model as a flat orthographic silhouette from each view that has a reference picture,
scales both outlines the same way, and reports their overlap (intersection over union). The skill's target is 0.98
per view. A view with no reference picture is reported `not_run`: it was not checked, and the skill never counts it
as a pass. One picture fixes the shape from one direction only, so claiming a match in 3D takes real pictures from
at least the front and a side.

It measures outline only. Depth inside the outline, surface detail and colour are judged by eye.

## How the sculpt tools work

Blender's own brush operator cannot be scripted reliably (it crashed Blender 4.5.16 when driven from a timer), so
`sculpt_strokes` moves vertices directly with numpy. The brushes share Blender's names (`grab`, `snake_hook`,
`draw`, `clay_strips`, `inflate`, `crease`, `smooth`) but are simpler; `sculpt_cmds.py` says exactly what each does.
Strokes do not depend on the viewport, repeat exactly, and each one reports how many vertices it moved.

## Grab a course

```
python tools/course_grab.py "https://www.youtube.com/watch?v=VIDEO_ID" --out references/video-courses
python tools/course_grab.py urls.txt --chapters 3-6
```

Per video it writes `chapters/NN-<slug>.md` (timed transcript), `frames/NN-<slug>/HHMMSS.jpg` (where the picture
changes, where the speaker points at the screen, and at least one per 30 seconds) and `index.json`. Running it again
skips what is already there. It needs English captions and exits with code 2 without them.

Then cut it into short captioned clips and make study sheets an agent can read:

```
python tools/make_clips.py references/video-courses/VIDEO_ID           # 8-30 s clips + clips/manifest.jsonl
python tools/clip_sheets.py references/video-courses/VIDEO_ID          # 2x2 full-resolution frames + transcript per clip
```

Each clip starts where the narrator starts a line, never crosses a chapter, and its manifest row carries the spoken
text and the skill stage it belongs to. Sheets let an agent that cannot play video see what the artist did on screen.

The output is study material for your own use. It is git-ignored here; do not republish someone else's course.

## Credit

The stage files are our own notes on the method taught in Kenny Praise's free masterclass
[How to Create Stylized 3D Characters](https://www.youtube.com/watch?v=qy-wwP-b9HY), with timestamps pointing back
at it. No part of the video, its captions or its frames is included in this repository. Watch the course: it shows
what these notes can only describe.
