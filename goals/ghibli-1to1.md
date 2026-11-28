Finish the 1:1 match of the Ghibli-style girl in
.scratch/ghibli-character/ghibli_27f_holes.blend with her Midjourney pictures, using the blender-character
skill and the blender-mcp-plus MCP tools (watch, scene_observe/scene_act, project_paint, visual_match, ...). Read
skill://blender-character, then its references/likeness-1to1.md, before the first change. Blender: the installed
blender_mcp_plus addon serves port 9879 and arms the scene relay itself; open the file, go to frame 1 (the rig's
action poses an arm on other frames), set undo_steps 8 and undo_memory_limit 2048.

Pictures: .scratch/ghibli-character/refs/{front,left,right,back}_clean.png as FRONT, LEFT, RIGHT, BACK. Gated
views: FRONT and LEFT. BACK and RIGHT disagree with them (reference_pairs 0.893 and 0.880) and are reported, not
gated. TOP is a T-pose: report only. Paint and check with priority_views=["LEFT","FRONT"], palette_view="FRONT",
power=14, priority_cos=0.15, warp=False, tex_size=2048, fill_colours={"body_retopo": "#fdddc7", "hair_scalp":
"#453026", "Hair.Band": "#453026", "Hair.Cap": "#453026", "Hair.Lock": "#453026"} (sampled from FRONT).

Starting point (measured): FRONT passes every visual_match gate (iou 0.982, ssim 0.842, delta E 1.13), LEFT too
(iou 0.984, ssim 0.823, delta E 1.53). The fringe over the eyes was cut back to where FRONT draws it ends
(z 1.53-1.57) and its edge curled onto the forehead; the hair now meets the face down to the jaw. three_quarter_check
and orbit_check have not been re-run since. Still wrong, seen from below (elevation -35): the hair is three nested
shells (Hair.Cap, hair_scalp, Hair.Band) standing off the head, and from below you look between them: dark bands
under the face, skin patches over the brows, blotches on the hair undersides. That needs the hair rebuilt as one
layer lying on the head where the side pictures draw it, then a repaint; deleting hair_scalp faces in front of the
face cost LEFT iou (0.977), so the scalp's forehead part forms the side outline and must be replaced, not removed.

Done when all of this holds on a saved file that was reopened, at frame 1:
0. **Clay gate (passed BEFORE paint):** untextured studio+cavity 360-degree up-and-down clay pan (8 azimuths ×
   elevations -35, 0, +35 = 24 head + 24 body views) has zero clay defects (round crown from above, buried fringe
   roots, continuous flowing bob, smooth face/nose/chin, plump 5-finger hands, smooth bodice/sleeves/skirt hem),
   and clay outline_match passes FRONT and LEFT (>= 0.98) without cardboard-box deformation.
1. visual_match passes every gate on FRONT and LEFT (iou >= 0.98, ssim >= 0.78, interior_edge_f1 >= 0.60,
   delta_e_mean <= 10, clay_banding_ratio <= 1.60).
2. orbit_check (45 degree steps, elevations -30, 0 and 30) reports failed: 0, and close watch views of the head at
   every 45 degrees from elevation -35 show nothing on the eye review's FROM BELOW line (no shell under the hair,
   no gap between fringe and forehead, no holes beside the face, no smears under the chin).
3. three_quarter_check passes all four pairs (delta E <= 12 in head, body and legs).
4. The eye review checklist has no open finding, including the two above.
Or stop when a criterion has stalled for two rounds and you can name the cause with a measurement.

Rules: never lower a threshold or narrow a check; follow the likeness loop's Landmarks step for the 45 degree head,
on the +X side with the RIGHT picture only; move vertices only along x for face changes and y for hair; re-check
outline_match after every move and revert what does not lower the failing number; one long call per message with
numbers after each; save passing states as ghibli_27_*.blend and up; write only inside
C:\Users\newbi\Desktop\blender-character-skill.

Final report: a table of every gate per view and pair with its number, the saved file, the sheet paths, and what
is still visible by eye.
