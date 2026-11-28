# blender-mcp-plus

A fork of [MCP for Blender](https://github.com/ahujasid/mcp-for-blender) by Siddharth Ahuja, MIT licensed
(`LICENSE`, copyright notice kept). Upstream commit: `UPSTREAM_COMMIT`. Upstream's own README:
`UPSTREAM_README.md`.

What this fork changes in upstream files:

- Telemetry and trajectory rows are never sent (`telemetry.py`, `trajectory.py`).
- Default port 9879, so it runs beside upstream's addon (9876) and the `blender-live` bridge (9876).
- The addon's command loop runs long commands in slices so Blender keeps redrawing (`addon.py`).
- Extra handlers and tools from this repository: the scene relay's verified actions, the watch view, and
  `blender-live`'s likeness, paint and sculpt tools.
