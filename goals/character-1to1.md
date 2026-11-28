Make the character in <START_FILE> (or a new one built from scratch) match its concept pictures 1:1, using the
blender-character skill and the blender-live MCP tools. Read skill://blender-character, then its
references/likeness-1to1.md, before the first change.

Pictures (Blender view names): FRONT <path>, LEFT <path>, RIGHT <path>, BACK <path>[, TOP <path>].
Gated views (the two the person cares about; a pair whose `reference_pairs` is below 0.98 cannot both pass):
<FRONT and LEFT>. Paint settings to keep for every paint and check: priority_views=[<...>], palette_view="<FRONT>".

Done when all of this holds on a saved file that was reopened, at the rig's rest frame:
1. `visual_match` passes every gate on each gated view: iou >= 0.98, ssim >= 0.78, interior_edge_f1 >= 0.60,
   delta_e_mean <= 10, clay_banding_ratio <= 1.60.
2. `orbit_check(object="CHARACTER", elevations=[-30, 0, 30])` (45 degree steps) reports failed: 0, and close `watch`
   views of the head at every 45 degrees from elevation -35 (looking up under the hair and chin) show nothing on
   the eye review's FROM BELOW line.
3. `three_quarter_check` passes every pair of neighbouring pictures (delta E <= 12 in head, body and legs).
4. The eye review checklist in likeness-1to1.md has no open finding on the visual, orbit and three-quarter sheets.
5. Every ungated view is reported with its numbers and the reason it cannot pass (its reference_pairs value).
Or stop when a criterion has stalled for two rounds and you can name the cause with a measurement.

Rules:
- Never lower a threshold or narrow a check to pass. Report a failing number as failed.
- Follow the likeness loop in order. Before changing geometry for an in-between angle, measure the landmarks
  (skin width, side hair line, iris) in the pictures, one side at a time with that side's own picture.
- Move vertices only along the axis the gated views do not see; re-check outline_match after every move; revert a
  change that does not move the failing number the right way.
- One long call per message (project_paint and three_quarter_check take 1-2 minutes); report numbers after each.
- Save each passing state under a new numbered name; write only inside the project folder.

Final report: a table of every gate per view and pair with its number, the saved file, the sheet paths, and what
is still visible by eye.
