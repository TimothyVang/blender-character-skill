# blender-mcp-plus

[MCP for Blender](https://github.com/ahujasid/mcp-for-blender) (MIT, by Siddharth Ahuja; see `NOTICE.md`,
`UPSTREAM_README.md`) with this repository's relay and character tools added. Everything upstream does still works:
`execute_blender_code`, `get_scene_info`, `look`, Poly Haven / Sketchfab / Poly Pizza assets, AI model generation.

What it adds:

| | Upstream | blender-mcp-plus |
|---|---|---|
| Long commands | block Blender's main thread until they finish | run in slices: Blender keeps redrawing, progress shows in the status bar, other tools keep answering |
| Verified scene edits | none | `scene_observe` / `scene_act`: the app-automation-relay's select, move, frame and save, each checked against the observed revision and read back |
| Watching the work | screenshots | `watch`: points the person's own viewport at the part being changed, with the reference picture beside it, and returns that view |
| Likeness against reference pictures | none | `outline_match`, `visual_match`, `orbit_check`, `three_quarter_check` |
| Painting pictures onto a model, scripted sculpting | none | `project_paint`, `fit_outline`, `sculpt_*`, `mesh_report`, `reference_setup`, `turnaround_sheet`, `compare_images` |
| Telemetry | opt-in events and screenshots to a hosted backend | never sent |
| Port | 9876 | 9879, so it runs beside upstream and `blender-live` |

The character tools are the same code as `../blender-live` (`live_core.py`, `sculpt_cmds.py`, `projection.py`,
`outline.py`, `server.py`), loaded from there, not copied.

## Run

```
uv run --project mcp/blender-mcp-plus blender-mcp-plus
```

In Blender, load `addon.py` (with `addon_plus.py` beside it) as an addon; it serves on port 9879. Paths:
`BLENDER_LIVE_DIR` (default `../blender-live`), `DMB_SCENE_ASSETS` (default the installed app-automation-relay
assets), `BLENDER_HOST` / `BLENDER_PORT` for the server.

Live check against a running Blender with the addon loaded: `uv run --project mcp/blender-mcp-plus python
mcp/blender-mcp-plus/plus_smoke.py`.
