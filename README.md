# blender-character-skill

Teach an AI agent to build a character in Blender from concept pictures, by hand: blockout, sculpt, clothes,
retopology, UVs, hair, shading, rig, lighting.

Five parts:

| Part | Where | What it does |
|------|-------|--------------|
| The skill | `skill/blender-character/` | A Claude skill: one entry file and one reference file per stage of the character pipeline. |
| The MCP server | `mcp/blender-live/` | Drives a running Blender: run Python, capture the viewport, sculpt, remesh, mask, place references, and measure the model's outline against reference pictures. |
| The course grabber | `skill/blender-character/scripts/course_grab.py` | Turns a video course into a transcript per chapter plus the frames that go with it, for writing skills like this one. |
| Visual study annotations | `annotations/qy-wwP-b9HY/` | 1,253 structured visual study labels across 11 stage JSONL files (`53` in stage 01 + `120` each in stages 02–11) backing the stage notes. |
| Low-poly route annotations | `annotations/mlnR-Eyazh0/` | 366 labels read off the screen of a silent speed-model (157 study sheets, every one labelled), in 11 JSONL files (stages 01–05 and 07–11, plus `00-intro`), backing each stage file's "Low-poly game route" section. |
| Speed-sculpt annotations | `annotations/FGU0ZwYub-0/`, `umF8UhsczO4/`, `huJs2R7JckM/`, `Yq9Dzaw2f1k/`, `ainRAUwXMO4/` | 252 labels from five YanSculpts videos: the D.Va Short (30), two 22-minute timelapses (89 + 73, from 91 study sheets) and the Venom and Spider-Man Shorts (28 + 32, narration transcribed with Whisper), backing `references/speed-sculpt.md`. |
| Speed-sculpt recipe | `skill/blender-character/scripts/speed_sculpt.py` | That method as Python: an ordered plan of `blender-live` tool calls (spheres per part, face strokes, eyes before lids, brow/lash strips, hair locks, mask-extract clothes, vertex paint, toon material, rim lights). Tested without Blender in `tests/test_speed_sculpt.py`. |

## Status

- **Speed-sculpt plan** (`skill/blender-character/scripts/speed_sculpt.py`): all 79 steps replayed in live Blender
  4.5.16 over real MCP stdio (`uv run --script mcp/blender-live/speed_sculpt_smoke.py OUT_DIR` with `BLENDER_EXE`
  set), 12 of 12 checks passing:
  - every stroke moved vertices;
  - every part exists, and the one-sided parts are mirrored;
  - the brow and lash strips have their modifier stack;
  - the top was extracted from the mask;
  - paint reached vertices;
  - the toon material and the 4 rim lights are in place;
  - the figure stands at the requested height.

  The result is a posed, painted mannequin, not a likeness: the face and front hair locks are crude until shaped
  against reference pictures. The smoke uses its own bridge port (9891) and never touches an open Blender.
- **MCP sculpt, 1:1 and review tools:** tested against live Blender 4.5.16 over real MCP stdio
  (`mcp/blender-live/sculpt_smoke.py`, 60 checks passing, including `sculpt_relax`, `fit_outline`, `project_paint`,
  `visual_match`, `orbit_check` and `three_quarter_check`).
- **Outline and pixel measuring, projection helpers, MCP contracts, and course/sheet tools:** tested without Blender
  (`tests/`, 62 tests passing).
- **Skill stage files (Stages 01–11 E2E proof):** executed end to end in live Blender 4.5.16 through the `blender-live` MCP server from a real front concept image (`character_01_refs.blend` through `character_11_final.blend`): 13 blockout parts, sculpted face/body (`BLK_head` `symmetry_error=0.000385`, `symmetry_p95_error=0.001598`, `symmetry_max_error=0.004978`), clothes/cloak/hair/goggles, manifold retopo (`body_retopo` 6,060 faces, `non_manifold_edges=0`), 13 UV-unwrapped meshes, `hair_scalp` + 710 hair curves, 15 shaded renderables, Rigify 918-bone rig (`0` unweighted body vertices, `0.4618 m` verified pose deformation), and Cycles studio renders.
  - **Likeness measurement (`outline_match`, `threshold=0.98`):** `FRONT` measured `0.9055` IoU (`failed` at the strict `0.98` target; remaining gap comes from the reference's studio floor cast shadow, inter-boot shadow, and fine hair/cuff differences). `BACK`, `LEFT`, `RIGHT`, and `TOP` were `not_run` ("looked at, not measured", no reference pictures for those views).
  - **Limitations:** retopology in the scripted E2E run used voxel/clean-mesh lowpoly proxies rather than hand-placed edge-loop patches; hitting `>= 0.98` across multiple views still requires multi-view clean-cutout references and iterative sculpting/fitting. Bpy snippets in stage files carry explicit verification markers for Blender 4.5.16.
- **1:1 run (Ghibli-style girl, Midjourney FRONT/BACK/LEFT/RIGHT/TOP pictures):** the slice-lofted model from the
  earlier run (FRONT `iou 0.972`, clay banding `14.3`, delta E `13.8`) was remeshed, relaxed, outline-fitted,
  sculpted (nose, brow, collar, pleats, hair clumps, boot folds), the face cut out of the hair helmet, the forearms
  moved onto the drawn arm, and painted with `project_paint`. FRONT and LEFT pass every `visual_match` gate
  (FRONT `iou 0.984`, SSIM `0.820`, edge F1 `0.965`, delta E `1.6`; LEFT `iou 0.981`, SSIM `0.786`, edge F1
  `0.978`, delta E `1.6`), reproduced after saving and reopening; `orbit_check` passes all 16 angles. BACK and RIGHT
  stop near `0.89` outline because their pictures disagree with FRONT and LEFT (`reference_pairs` `0.893` and
  `0.880`); TOP is drawn in a T-pose. `three_quarter_check` (neighbouring pictures painted on their own, compared at
  45/135/225/315 degrees, CIEDE2000 `<= 12` per region) passes 135, 225 and 315 degrees; at 45 degrees the head
  measures `12.97`: the right picture's eye sits about 1 cm off the front picture's eye on the surface. The double
  face it caught measured `17` to `24`, the hair flap `17`.

## Set up

Needs [uv](https://docs.astral.sh/uv/), Blender 4.5, and for the grabber `yt-dlp` and `ffmpeg`.

1. Register the MCP server with your client (see `mcp/mcp-client.example.json`), pointing `BLENDER_EXE` at your
   Blender. The server starts Blender with its bridge when you call `blender_launch`.
2. Copy `skill/blender-character/` into your skills folder (for Claude Code: `~/.claude/skills/`).
3. Ask for a character and give it reference pictures. For a 1:1 match, run it as an omp goal (needs the
   `goal.enabled` setting): fill in `goals/character-1to1.md`, then
   `omp --goal (Get-Content -Raw goals/character-1to1.md)` in PowerShell, or `/goal` with the text in a session.
   `goals/ghibli-1to1.md` is the filled-in goal that continues the Ghibli run from its current state.

Run the tool checks yourself:

```
uv run --script mcp/blender-live/sculpt_smoke.py .scratch/sculpt-smoke
python -m pytest tests
```

## Security

The bridge listens on 127.0.0.1 only, and its `exec` command runs any Python it is sent. Any program on the same
computer can send it. Set `BLENDER_LIVE_TOKEN` (the same value for Blender and the MCP server) to require a token.

## How likeness is measured

`outline_match` captures the model as a flat orthographic silhouette from each view that has a reference picture
(Standard view transform, so an edge pixel is cut at half coverage), registers it onto the picture with a small
reported shift and scale (at most 4 px and 1.5 %), and reports their overlap (intersection over union, target `0.98`
per view). A view with no reference picture is reported `not_run`: it was not checked, and the skill never counts it
as a pass. `reference_pairs` reports how well opposite pictures agree (BACK is the FRONT outline mirrored): below
0.98 no single model can pass both.

Inside the outline, `visual_match` proves pixels per referenced view with five gates — outline IoU (`>= 0.98`),
masked SSIM (`>= 0.78`), interior edge F1 (`>= 0.60`), a CIEDE2000 colour proof like a printer's (mean delta E
`<= 10`, with the reference's dominant inks as hex beside the model's) and untextured clay banding (`<= 1.60`, so
ring-stacked geometry cannot hide behind a projected texture). `orbit_check` scores the surface from every angle
and returns a sheet for review by eye. `skill/blender-character/references/likeness-1to1.md` is the loop that uses
them, with `fit_outline` (warp the outline onto the pictures), `sculpt_relax` (iron terraces) and `project_paint`
(paint the pictures onto the UVs with depth-buffer occlusion, reporting where pictures disagree in 3D).

The same Blender can also be reached through the `blender_scene` relay of the app-automation-relay skill
(document identity, verified moves and saves); the skill's "Two connections to Blender" says which to use.

## How the sculpt tools work

Blender's own brush operator cannot be scripted reliably (it crashed Blender 4.5.16 when driven from a timer), so
`sculpt_strokes` moves vertices directly with numpy. The brushes share Blender's names (`grab`, `snake_hook`,
`draw`, `clay_strips`, `inflate`, `crease`, `smooth`) but are simpler; `sculpt_cmds.py` says exactly what each does.
Strokes do not depend on the viewport, repeat exactly, and each one reports how many vertices it moved.

## Grab a course

```
python skill/blender-character/scripts/course_grab.py "https://www.youtube.com/watch?v=VIDEO_ID" --out references/video-courses
python skill/blender-character/scripts/course_grab.py urls.txt --chapters 3-6
```

Per video it writes `chapters/NN-<slug>.md` (timed transcript), `frames/NN-<slug>/HHMMSS.jpg` (where the picture
changes, where the speaker points at the screen, and at least one per 30 seconds) and `index.json`. Running it again
skips what is already there. It needs English captions and exits with code 2 without them, unless the video has
no narration (a speed-model set to music): then pass `--silent` to all three tools. The grabber keeps the chapters and
frames with empty transcripts, and `make_clips.py` / `clip_sheets.py` cut every chapter into equal clips of at most
`--max` seconds. The study labels then come from what is on screen: the key-cast overlay, redo panels and modifier
panels.

```
python skill/blender-character/scripts/course_grab.py "https://www.youtube.com/watch?v=mlnR-Eyazh0" --silent
python skill/blender-character/scripts/make_clips.py references/video-courses/mlnR-Eyazh0 --silent
python skill/blender-character/scripts/clip_sheets.py references/video-courses/mlnR-Eyazh0 --silent
```

If YouTube answers "Sign in to confirm you're not a bot" or HTTP 429, update yt-dlp first
(`python -m pip install -U "yt-dlp[default]"`); that was enough here.

Then cut it into short captioned clips and make study sheets an agent can read:

```
python skill/blender-character/scripts/make_clips.py references/video-courses/VIDEO_ID           # 8-30 s clips + clips/manifest.jsonl
python skill/blender-character/scripts/clip_sheets.py references/video-courses/VIDEO_ID          # 2x2 full-resolution frames + transcript per clip
```

Each clip starts where the narrator starts a line, never crosses a chapter, and its manifest row carries the spoken
text and the skill stage it belongs to. Sheets let an agent that cannot play video see what the artist did on screen.

The output is study material for your own use. It is git-ignored here; do not republish someone else's course.

## Credit

The stage files are our own notes on the method taught in Kenny Praise's free masterclass
[How to Create Stylized 3D Characters](https://www.youtube.com/watch?v=qy-wwP-b9HY), with timestamps pointing back
at it. No part of the video, its captions or its frames is included in this repository. Watch the course: it shows
what these notes can only describe.

The "Low-poly game route" sections are our own notes on Nhij Quang's
[Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), read from
the screen (the video has no narration); their timestamps are marked `NQ`. The same applies: nothing from the video
is included here.

`references/rig-for-animation.md` takes its rigging steps and its list of pose fixes from YanSculpts'
[3D Character Creation Walkthrough - Part 2 - Rigging and Posing Tifa](https://www.youtube.com/watch?v=vPFRxvsOBb4)
(timestamps marked `YT`). The video rigs for a still pose only; the animation steps in that file (snapping, driven
correctives, cycle check, actions, bake) are our own, checked in Blender 4.5.16.

`references/speed-sculpt.md` is our own notes on YanSculpts'
[How to Sculpt D.Va in 1 Minute](https://youtube.com/shorts/FGU0ZwYub-0),
[Sculpting a Girl (Summer)](https://www.youtube.com/watch?v=umF8UhsczO4),
[Sculpting a Girl (Black and White)](https://www.youtube.com/watch?v=huJs2R7JckM),
[Venom in 1 minute](https://youtube.com/shorts/Yq9Dzaw2f1k) and
[Spider-Man in 1 minute](https://youtube.com/shorts/ainRAUwXMO4) (his channel: https://www.youtube.com/@yansculpts);
its timestamps are marked `YS`. Only the method is described; the characters and the videos are theirs.
