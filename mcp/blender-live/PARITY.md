# blender-live ↔ unreal-live parity

`unreal-live` drives a running Unreal editor: edit with fresh visual feedback, find and act on Slate UI widgets, and sample a window as a live image stream. `blender-live` gives the same loop for a running Blender.

| unreal-live tool | blender-live equivalent | Notes |
|---|---|---|
| `edit_and_see` (dispatch an edit, return fresh visual or camera state) | `exec_python(code, capture=True)` | Runs bpy in the live session, returns `result` and stdout, then a viewport image taken right after the edit. |
| `motion_preview` (ordered JPEGs of a live window, including motion, in one turn) | `motion_preview(frames \| start/end/count, camera, shading)` | Steps the scene's frames and captures the viewport at each, returning ordered images in one call. Blender motion is frame-driven, so stepping frames is deterministic where screen sampling is not. |
| `slate_find` (find rendered UI widgets by label/role) | `scene_tree`, `object_info` | Blender agents act on data (`bpy`), not on UI widgets, so the data model replaces widget lookup. |
| `slate_act` (click or hover one widget) | `exec_python` (`bpy.ops.*` with a context override) | Any UI action has an operator; calling it directly is reproducible, while clicking pixels is not. No synthetic mouse input, so other windows and sessions are never touched. |
| `vision_start` (sample a widget or window) | `viewport_capture` / `motion_preview` | Captures are on demand: the viewport renders off-screen (`render.opengl`), so there is no stream to start. |
| `vision_latest` (latest frame, never a backlog) | `viewport_capture` | Each call returns the current state. |
| `vision_stop` (stop sampling, release pixels) | not needed | Nothing is retained between calls; capture files go to `.scratch/tmp/blender-live/<pid>/`. |
| (unreal-mcp `list_toolsets` / `call_tool`) | the MCP tool list | blender-live exposes its tools directly. |

Blender-only extras: `render_image` (a full render with settings restored), `headless_run` (background Blender jobs with marker lines), `compare_images` (pixel/SSIM against a reference), `open_file`/`save_file`/`set_frame`, and `blender_launch`/`blender_status`.
