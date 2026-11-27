# 08 Hair, eyebrows and eyelashes

Course source: chapter 11 "Grooming the Hair for your Character", 12:05:29 to 14:24:52. The video uses Blender 5.0.1;
the snippets here were run in Blender 4.5.16, where one input of `Interpolate Hair Curves` is shown differently
(see Settings).

## Goal

The character has eyebrows, upper and lower eyelashes and head hair made of real strands: Curves objects ("new
hair"), each attached to a small scalp mesh, each holding a few hand-shaped guide curves that Blender's bundled hair
node groups multiply, clump and roughen. The hair has volume (it stands off the skull), follows the flow seen in the
references, and no strand passes through the head.

## Starting state

- `body_retopo` exists with UVs from stage 07 and **no pinned UVs** (scalps are cut from it and unwrapped again).
- The high-poly sculpt is available to look at for brow and hairline placement [12:30:25].
- Hair references, ideally from every side [12:07:00]. A view you have no picture of cannot be measured later.
- Before making anything, answer the course's two questions for the hairstyle [12:07:24]:
  1. Can it be split into parts or volumes that are easier to groom one at a time? The course's own answer for its
     character: a swept-back main mass, a loose strand at each side of the face, and a ponytail [13:41:51].
  2. What is the flow and direction of each part: where it starts, which way it runs, where it turns or gathers?

## How the system works

- A **scalp** is a mesh the hair grows from. It needs a UV map. One scalp per region, kept in a collection the
  course names `hair_scalp` [12:31:43]. Do not grow hair straight from the body mesh [12:15:18].
- `Add > Curve > Empty Hair` with the scalp active makes a Curves object parented to the scalp, with the scalp set
  as its surface and a `Surface Deform` geometry-nodes modifier already on it. Leave that modifier alone [13:30:03].
- You shape a few **guide** curves; modifiers make the many **children**. The narrator's comparison: like a
  Subdivision Surface modifier, a few control the many [12:14:16]. Too many guides cannot be combed; too few give
  no control.
- The four steps, used for every part [12:27:07]: **1** create guides, **2** interpolate, **3** clump, **4** add
  noise or frizz.
- The node groups are Blender's bundled assets (Asset Browser, `Essentials > Hair`) [12:23:17]. Brows and lashes
  use them as modifiers in a stack; head hair uses the same groups as nodes inside one geometry-nodes modifier,
  which allows branching [12:24:50, 13:29:49].

The asset file and the exact group names (all present in 4.5.16):

`<blender>/4.5/datafiles/assets/geometry_nodes/procedural_hair_node_assets.blend` holds `Interpolate Hair Curves`,
`Clump Hair Curves`, `Frizz Hair Curves`, `Hair Curves Noise`, `Set Hair Curve Profile`, `Blend Hair Curves`,
`Trim Hair Curves`, `Create Guide Index Map`, `Curve Info` (used by the course) and `Attach Hair Curves to Surface`,
`Braid Hair Curves`, `Curl Hair Curves`, `Curve Root`, `Curve Segment`, `Curve Tip`, `Displace Hair Curves`,
`Duplicate Hair Curves`, `Generate Hair Curves`, `Hair Attachment Info`, `Redistribute Curve Points`,
`Restore Curve Segment Length`, `Roll Hair Curves`, `Rotate Hair Curves`, `Shrinkwrap Hair Curves`,
`Smooth Hair Curves`, `Straighten Hair Curves` (not used).

```python
# verified in 4.5.16 background
import bpy, bmesh, os, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HAIR_LIB = os.path.join(bpy.utils.system_resource('DATAFILES'), "assets", "geometry_nodes",
                        "procedural_hair_node_assets.blend")

def hair_group(name):
    """Append one bundled hair node group by exact name (reused if already in the file)."""
    if name not in bpy.data.node_groups:
        with bpy.data.libraries.load(HAIR_LIB, link=False) as (src, dst):
            if name not in src.node_groups: raise KeyError(f"{name!r} not in {HAIR_LIB}")
            dst.node_groups = [name]
    return bpy.data.node_groups[name]

def add_hair_modifier(obj, group_name, **values):
    """Add a bundled group as a modifier; set inputs by UI name with _ for spaces, e.g. Guide_Distance=0.004.
    A str given to a number or vector input is read as an attribute name (UV map, vertex group)."""
    ng = hair_group(group_name)
    m = obj.modifiers.new(group_name, 'NODES'); m.node_group = ng
    socks = {it.name: it for it in ng.interface.items_tree if it.item_type == 'SOCKET'
             and it.in_out == 'INPUT' and it.socket_type != 'NodeSocketGeometry'}
    for k, v in values.items():
        it = socks[k.replace("_", " ")]
        if isinstance(v, str) and it.socket_type != 'NodeSocketString':
            m[it.identifier + "_use_attribute"] = True; m[it.identifier + "_attribute_name"] = v
        else:
            m[it.identifier] = v
    obj.update_tag()
    return m

def scalp_from_faces(body, name, face_test, subdivide=0, collection="hair_scalp"):
    """New scalp object from the body faces where face_test(world_centre, world_normal) is True, with fresh UVs."""
    bm = bmesh.new(); bm.from_mesh(body.data); mw = body.matrix_world; nm = mw.to_3x3().inverted().transposed()
    bmesh.ops.delete(bm, context='FACES', geom=[f for f in bm.faces if not face_test(
        mw @ f.calc_center_median(), (nm @ f.normal).normalized())])
    if subdivide: bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=subdivide, use_grid_fill=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.matrix_world = mw
    root = bpy.data.objects.get("CHARACTER")
    if root is not None: ob.parent = root; ob.matrix_world = mw     # under CHARACTER, so its hair is in the checks
    col = bpy.data.collections.get(collection)
    if col is None:
        col = bpy.data.collections.new(collection); bpy.context.scene.collection.children.link(col)
    col.objects.link(ob)
    if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT'); ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.mark_seam(clear=True); bpy.ops.uv.select_all(action='SELECT'); bpy.ops.uv.pin(clear=True)
    bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.02)
    bpy.ops.object.mode_set(mode='OBJECT')
    return ob

def new_hair(scalp, name):
    """Empty hair Curves object on the scalp (parent, surface, surface UV map and Surface Deform are set for you)."""
    if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT'); scalp.select_set(True); bpy.context.view_layer.objects.active = scalp
    bpy.ops.object.curves_empty_hair_add()
    bpy.context.object.name = name
    return bpy.context.object
```

## Shaping guides without brushes

The course shapes guides in Sculpt Mode with the curve brushes. Blender's brush stroke operators cannot be driven
from Python here, so you write guide positions directly. What each brush does, so you know what to reproduce:

| Brush | Effect | Your route |
|---|---|---|
| Add | one new guide where you click; `Curve Shape` popover sets Length and Points; Interpolate Length/Shape copies neighbours [13:48:15] | `add_guides` |
| Density | fills an area with guides no closer than Distance Min [12:18:11] | `scalp_points(spacing)` then `add_guides` |
| Delete | removes guides | `hair.data.remove_curves(indices=[...])` |
| Comb | drags the curve along the stroke, root stays [12:19:28] | `flow_guides` with a new flow, or `reshape_guides` |
| Grow/Shrink | lengthens or shortens (set Minimum Length 0 to shrink short hairs) [12:43:19] | `reshape_guides` scaling about the root |
| Pinch, Puff, Pull Tips, Slide, Smooth | gather; stand hair up off the scalp; drag tips; move roots along the scalp; straighten kinks | `reshape_guides`; `lift` in `flow_guides` for Puff |

The course also switches every brush between **Projected** (affects all hair under the cursor, used first for the
overall shape) and **Sphere** (affects only hair near the surface under the cursor, used to refine without wrecking
the rest) [12:22:03]. For you: shape everything with one flow first, then correct chosen curves only.

```python
# verified in 4.5.16 background
def scalp_points(scalp, spacing, face_test=None, seed=0):
    """Evenly spread (world_point, world_normal) pairs on the scalp, about `spacing` apart."""
    rng = np.random.default_rng(seed); mw = scalp.matrix_world; out = []
    for f in scalp.data.polygons:
        c, n = mw @ f.center, (mw.to_3x3() @ f.normal).normalized()
        if face_test and not face_test(c, n): continue
        k = f.area / spacing ** 2
        vs = [mw @ scalp.data.vertices[i].co for i in f.vertices]
        for _ in range(int(k) + (rng.random() < k - int(k))):
            w = rng.dirichlet(np.ones(len(vs)))
            out.append((sum((v * float(x) for v, x in zip(vs, w)), Vector()), n))
    return out

def flow_guides(collide, roots, flow, length, points=8, lift=0.003):
    """One polyline per root (world points). flow(point, t) -> world direction, t = 0 at the root, 1 at the tip.
    length: metres, or a function of the root. Every step is pushed out to at least `lift` above `collide`."""
    dg = bpy.context.evaluated_depsgraph_get(); bvh = BVHTree.FromObject(collide, dg)
    mw = collide.matrix_world; inv = mw.inverted(); lines = []
    for r in roots:
        p = Vector(r); line = [p.copy()]; step = (length(p) if callable(length) else length) / (points - 1)
        for i in range(1, points):
            p = p + Vector(flow(p, i / (points - 1))).normalized() * step
            co, no, _, _ = bvh.find_nearest(inv @ p)
            if co is not None:
                co, no = mw @ co, (mw.to_3x3() @ no).normalized()
                if (p - co).dot(no) < lift: p = p + no * (lift - (p - co).dot(no))
            line.append(p.copy())
        lines.append(line)
    return lines

def add_guides(hair, polylines, points=8, mirror_x=False):
    """Append guide curves from world-space polylines (root first), each resampled to `points` points."""
    inv = hair.matrix_world.inverted(); lines = []
    for pl in polylines:
        p = np.array([inv @ Vector(c) for c in pl], dtype=np.float32)
        t = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
        lines.append(np.stack([np.interp(np.linspace(0, t[-1], points), t, p[:, k]) for k in range(3)], axis=1))
        if mirror_x: lines.append(lines[-1] * np.array([-1, 1, 1], dtype=np.float32))
    cu = hair.data; old = len(cu.points)
    cu.add_curves([points] * len(lines))
    pos = np.empty(len(cu.points) * 3, dtype=np.float32); cu.attributes["position"].data.foreach_get("vector", pos)
    pos = pos.reshape(-1, 3); pos[old:] = np.concatenate(lines)
    cu.attributes["position"].data.foreach_set("vector", pos.ravel()); cu.update_tag()
    bpy.ops.object.select_all(action='DESELECT'); hair.select_set(True); bpy.context.view_layer.objects.active = hair
    bpy.ops.curves.snap_curves_to_surface(attach_mode='NEAREST')      # writes surface_uv_coordinate per curve
    return len(cu.curves)

def reshape_guides(hair, fn):
    """Rewrite guides in place. fn(index, world_points (n, 3) array) -> new (n, 3) array; keep row 0 (the root)."""
    cu = hair.data; mw = np.array(hair.matrix_world); inv = np.linalg.inv(mw)
    pos = np.empty(len(cu.points) * 3, dtype=np.float32); cu.attributes["position"].data.foreach_get("vector", pos)
    pos = pos.reshape(-1, 3)
    for i, c in enumerate(cu.curves):
        a, b = c.first_point_index, c.first_point_index + c.points_length
        w = np.asarray(fn(i, pos[a:b] @ mw[:3, :3].T + mw[:3, 3]), dtype=np.float32)
        pos[a:b] = w @ inv[:3, :3].T + inv[:3, 3]
    cu.attributes["position"].data.foreach_set("vector", pos.ravel()); cu.update_tag()
```

## Order of work

The course goes easiest first: eyebrows, eyelashes, a short haircut as practice, then the character's real hair
[12:29:30]. Set `bpy.context.scene.render.hair_type = 'STRAND'` while placing guides (thin lines) and `'STRIP'`
when judging thickness: only Strip shows the radius profile [12:52:00, 13:02:28].

### 1. Eyebrows [12:29:45 to 12:58:25]

1. **Scalp** `brow_scalp`: duplicate the body faces under and around the brow, separate, remove its Subdivision
   modifier, add a Shrinkwrap to the body so it sits on the surface, Mirror, then apply everything (`Object >
   Apply > Visual Geometry to Mesh`). Clear pins and unwrap; orientation of the UVs does not matter [12:30:00 to
   12:33:10]. `scalp_from_faces` does all of this in one call.
2. **Mark the brow** on the sculpt first (the course draws it with the Annotate tool set to Surface) [12:33:40].
   You: decide the brow's centre line as three or four world points read from the sculpt and the reference.
3. **Guides** `eyebrows`: Add brush, X symmetry on, Length 0.01 m then shortened (the narration suggests about
   0.007 m), 8 points [12:34:40]. About 30 guides per brow, combed flat to the skin, never through it. Direction
   from the reference: hairs at the inner end point up and slightly outward; along the upper edge they lean down
   and outward; along the lower edge up and outward, so both rows close onto the centre line; all sweep toward the
   temple and get shorter at the tail (Grow/Shrink with Minimum Length 0) [12:43:12].
4. **Interpolate**: drag `Interpolate Hair Curves` onto the object; everything vanishes until Surface is set to the
   scalp [12:46:55]. Density is raised in steps (50 000, 800 000, then 1 500 000 and 3 000 000 once masked).
5. **Mask**: unmasked, children cover the whole scalp. The course paints a 2K black image `brow density` white
   where the brow is (Texture Paint, mode Single Image, saved into a `textures` folder; images must be saved by
   hand, `Alt S`) and picks it as Mask Texture [12:47:50 to 12:51:50].
6. **Profile**: Render Properties, `Curves > Shape: Strip`; add `Set Hair Curve Profile`, Radius 0.0001 m ("the
   average human hair is about 0.1 mm"), Shape about 0.6; Interpolation Guides tried at 6, left at 3 [12:52:00].
7. **Clump** twice: primary `Clump Hair Curves` with Existing Guide Map off (otherwise Guide Distance does
   nothing), Guide Distance 0.004 m, Factor lowered; secondary with Guide Distance 0.002 m [12:55:16 to 12:57:10].
8. **Frizz**: `Frizz Hair Curves`, Cumulative Offset off (with it on "everything goes crazy"), Factor 0.272,
   Distance 0.001 m, Shape 0.5 [12:57:20]. Viewport Display colour of the Curves object set to black [12:53:10].

```python
# verified in 4.5.16 background
body = bpy.data.objects["body_retopo"]
bpy.context.scene.render.hair_type = 'STRIP'
# example region and centre line for a head centred at (0, 0, 1.6), facing -Y: replace with your measurements
in_brow = lambda c, n: c.y < -0.07 and 1.615 < c.z < 1.66 and 0.005 < abs(c.x) < 0.07
brow_scalp = scalp_from_faces(body, "brow_scalp", in_brow, subdivide=2)
mid_z = lambda x: 1.640 - 0.25 * (abs(x) - 0.035) ** 2 / 0.035        # height of the brow centre line at x
vg = brow_scalp.vertex_groups.new(name="density")                     # stands in for the painted mask image
vg.add([v.index for v in brow_scalp.data.vertices
        if abs((brow_scalp.matrix_world @ v.co).z - mid_z(v.co.x)) < 0.004 and 0.012 < abs(v.co.x) < 0.06], 1.0, 'REPLACE')
brows = new_hair(brow_scalp, "eyebrows"); brows.color = (0, 0, 0, 1)
roots = [p for p, n in scalp_points(brow_scalp, 0.004, lambda c, n: c.x > 0.012 and c.x < 0.06
                                    and abs(c.z - mid_z(c.x)) < 0.004)]
def brow_flow(p, t):                      # outward along the brow, closing onto the centre line, up at the inner end
    inner = max(0.0, 1 - (p.x - 0.012) / 0.012)
    return Vector((1 - 0.7 * inner, 0, 0.9 * inner + 2.0 * (mid_z(p.x) - p.z) / 0.004 * 0.15))
tail = lambda r: 0.007 * (1.0 - 0.5 * max(0.0, (r.x - 0.045) / 0.015))    # shorter toward the tail
add_guides(brows, flow_guides(body, roots, brow_flow, tail, points=8, lift=0.0005), points=8, mirror_x=True)
add_hair_modifier(brows, "Interpolate Hair Curves", Surface=brow_scalp, Surface_UV_Map="UVMap",
                  Poisson_Disk_Distribution=False, Density=3000000.0, Density_Mask="density", Interpolation_Guides=3)
add_hair_modifier(brows, "Set Hair Curve Profile", Radius=0.0001, Shape=0.6)
add_hair_modifier(brows, "Clump Hair Curves", Existing_Guide_Map=False, Guide_Distance=0.004, Factor=0.7)
add_hair_modifier(brows, "Clump Hair Curves", Existing_Guide_Map=False, Guide_Distance=0.002)
add_hair_modifier(brows, "Frizz Hair Curves", Cumulative_Offset=False, Factor=0.272, Distance=0.001, Shape=0.5)
result = {"guides": len(brows.data.curves)}
```

`Factor=0.7` for the primary clump is my value; the course only says it was toned down. The vertex group replaces
the painted image because you cannot paint: `Density Mask` reads it from the scalp, and `subdivide=2` gives the
scalp enough vertices to draw the brow shape. To follow the course literally, build a `bpy.types.Image`, fill its
pixels from numpy, save it, and pass it as `Mask_Texture=image` (that input was tested and does cut the hair).

### 2. Eyelashes [12:58:30 to 13:16:20]

- **Scalp** `lashes_scalp`: the ring of faces round the eye opening, narrowed (edge slide) so it is a thin band on
  the lid edge; faces at the inner corner removed because the reference has no lashes there; Shrinkwrap, Mirror,
  apply; unwrap. Duplicate or overlapping faces made the unwrap fail and had to be rebuilt [13:01:00].
- **Guides** `eyelashes`: Add brush, Length 0.01 m, evenly spaced along the upper lid, "not too many"; combed
  outward then curved up; shorter toward both corners. Not done with X symmetry: the finished side was duplicated in
  Edit Mode and mirrored about the world origin [13:04:20]. `add_guides(..., mirror_x=True)` covers it. Lower
  lashes the same way, fewer, pointing out and down [13:05:45].
- **Stack** for the upper lashes: `Set Hair Curve Profile` Radius 0.0002 m, Shape 0.5 (the narrator says "2 mm";
  the panel reads 0.0002 m) [13:10:00]; `Interpolate Hair Curves` Surface `lashes_scalp`, Density 2 500 000;
  `Clump Hair Curves` Existing Guide Map off, Guide Distance 0.001 m, a very small Tip Spread [13:11:20];
  `Hair Curves Noise` Cumulative Offset off, Factor about 0.04, Shape 0.5, Scale about 9, Scale along Curve 15
  [13:12:10].
- **Lower lashes** want far fewer, clumpier hairs, so they are separated into their own Curves object
  (`eyelashes.001`), and the scalp ring is split between upper and lower lid (rip, `V`) so the two are separate
  mesh islands [13:13:05]. Its clump keeps Existing Guide Map **on**, so children gather onto the hand-placed
  guides, and neighbouring guides are combed together in twos and threes. Its Density is lowered a lot (the value
  spoken is unclear).

### 3. Head hair as a node tree [13:16:40 to 14:23:00]

**Scalp** `hair_scalp`: the skull faces inside the hairline (drawn first with Annotate), one half selected,
duplicated, separated, mirrored, edges pulled to the hairline with snapping and the mesh Grab brush, holes filled,
Shrinkwrap applied, pins and seams cleared, unwrapped [13:16:50 to 13:22:20]. It need not be exact; the mask trims
it.

**Practice cut, `short`** [13:22:30 to 13:41:40]: Density brush with Distance Min 0.013 m (0.02 tried first),
Length 0.04 m, covering the whole scalp; combed down at the sides and back, forward and slightly up at the front;
sides shortened with Grow/Shrink; no hair lying over the ear. Tree `short hair`: profile 0.0001 m, interpolate at
Density 800 000 (Viewport Amount 0.5 while combing, to stop lag), clump with Existing Guide Map off and Guide
Distance 0.015 m, Factor 0.743, then a second clump inside the first and noise on a quarter of the strands.

**The character's hair** is three Curves objects [13:41:51]:

- `main hair`: 30-point guides placed **only round the perimeter of the hairline**, each running back over the
  skull to one gather point where the hair band is, **held off the scalp** so the mass has volume [13:44:20]. The
  band itself is a small separate mesh; name it `Hair.Band` (ours), for example
  `bpy.ops.mesh.primitive_torus_add(location=gather, major_radius=0.02, minor_radius=0.006)` turned to sit round
  the gathered hair, and parent it to `CHARACTER`. Stages 09 and 10 look for it by that name. Near
  the centre line shrink the brush so the mirrored twin is not caught [13:46:10]. Because the guides sit only at
  the rim, the density mask `main hair density` is painted only along that rim band [13:53:35]; children are still
  interpolated across the gap. Final Density 2 000 000.
- **Parting**: `Part by Mesh Islands` only works if the scalp is in separate islands, so the scalp edges along the
  parting are ripped (`V`), giving left, right and the rest [13:57:10]. `Blend Hair Curves` (Blend Radius 0.01 m)
  fills gaps between clumps but smears the parting shut, so its Factor is fed from a vertex group named `parting`
  on the scalp: weight 1 everywhere except the faces along the parting [13:58:25].
- `left side hair`: a few long guides from the front hairline falling past the eye and curving in, its own mask
  image; the right side is the same tree with a mask for the other side [14:06:20 to 14:15:20].
- `ponytail`: its own scalp `ponytail scalp`, a small disc (a plane subdivided twice, made round, parked at the
  gather point); guides fan out, drop and curl at the tips as planned on screen first [14:15:30 to 14:19:40]. When
  adding hair to a new scalp raised a missing-attachment error, the fix was select curves then scalp,
  `Ctrl P > Object (Attach Curves to Surface)` [14:20:25]; `new_hair` avoids it.

The node chain, in order (`hair_tree` builds it; pieces not wanted for a part are switched off by argument):

1. `Set Hair Curve Profile` (Radius 0.0001 m).
2. `Interpolate Hair Curves`: Surface object, Surface UV Map from a Named Attribute node holding the scalp's UV
   map name, Density, mask, Part by Mesh Islands on [13:31:05].
3. `Clump Hair Curves`. Either by distance (Existing Guide Map off, Guide Distance set) as in `short`, or onto the
   real guides by linking Interpolate's `Guide Index` output with Existing Guide Map on, Shape 0.8, as in
   `main hair`, `left side hair` and `ponytail` [13:56:05].
4. `Blend Hair Curves` with the `parting` attribute as Factor (main hair only).
5. Secondary clumps [13:34:20, 14:12:15]: Random Value (Boolean, Probability 0.95) into Delete Geometry (Spline)
   leaves about 5 % of the strands; `Create Guide Index Map` takes all strands as Geometry and the survivors as
   Guides; a second `Clump Hair Curves` gets its Geometry and Guide Index from it, Existing Guide Map off.
6. Noise on a share only [13:39:10]: Random Value (Boolean) into Separate Geometry (Spline); `Hair Curves Noise`
   on the Selection output; Join Geometry with the Inverted output. Share 0.25 for `short`, about 0.1 for the rest.
7. Flyaways (main hair only) [14:02:35]: a second Separate Geometry with another seed and a small share;
   `Trim Hair Curves` with Replace Length off and Length Factor from a Random Value (0 to about 0.2) keyed on
   `Curve Info > Random`; heavy `Hair Curves Noise` with Preserve Length on; joined back.

```python
# verified in 4.5.16 background
def hair_tree(hair, scalp, name, density, mask="", clump="INDEX", guide_distance=0.015, blend_attr="",
              second_clump=False, noise_share=0.1, noise=None, flyaway_share=0.0):
    """Build the course's node chain as one modifier on `hair`. Returns the group nodes by name for tuning."""
    nt = bpy.data.node_groups.new(name, 'GeometryNodeTree'); N, L = nt.nodes, nt.links; made = {}
    nt.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    nt.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    def grp(key, group, src, **vals):
        n = N.new("GeometryNodeGroup"); n.node_tree = hair_group(group); n.label = key; made[key] = n
        n.location = (220 * len(made), 0)
        if src is not None: L.new(src, n.inputs["Geometry"])
        for k, v in vals.items(): n.inputs[k.replace("_", " ")].default_value = v
        return n
    def attr(attr_name, data_type):
        n = N.new("GeometryNodeInputNamedAttribute"); n.data_type = data_type; n.inputs["Name"].default_value = attr_name
        return n.outputs["Attribute"]
    def share(src, probability, seed, node_type, domain='CURVE'):
        r = N.new("FunctionNodeRandomValue"); r.data_type = 'BOOLEAN'
        r.inputs["Probability"].default_value = probability; r.inputs["Seed"].default_value = seed
        n = N.new(node_type); n.domain = domain; L.new(src, n.inputs["Geometry"]); L.new(r.outputs["Value"], n.inputs["Selection"])
        return n
    gin, gout = N.new("NodeGroupInput"), N.new("NodeGroupOutput")
    prof = grp("profile", "Set Hair Curve Profile", gin.outputs[0], Radius=0.0001)
    interp = grp("interpolate", "Interpolate Hair Curves", prof.outputs["Geometry"], Density=density,
                 Poisson_Disk_Distribution=False, Part_by_Mesh_Islands=True)
    next(s for s in interp.inputs if s.name == "Surface" and s.type == 'OBJECT').default_value = scalp
    L.new(attr(scalp.data.uv_layers.active.name, 'FLOAT_VECTOR'), interp.inputs["Surface UV Map"])
    if mask: L.new(attr(mask, 'FLOAT'), interp.inputs["Density Mask"])
    c1 = grp("clump", "Clump Hair Curves", interp.outputs["Geometry"], Existing_Guide_Map=(clump == "INDEX"),
             Guide_Distance=guide_distance, Shape=0.8 if clump == "INDEX" else 0.5)
    if clump == "INDEX": L.new(interp.outputs["Guide Index"], c1.inputs["Guide Index"])
    out = c1.outputs["Geometry"]
    if blend_attr:
        b = grp("blend", "Blend Hair Curves", out, Blend_Radius=0.01); L.new(attr(blend_attr, 'FLOAT'), b.inputs["Factor"])
        out = b.outputs["Geometry"]
    if second_clump:
        keep = share(out, 0.95, 0, "GeometryNodeDeleteGeometry")
        gmap = grp("guide_map", "Create Guide Index Map", out); L.new(keep.outputs["Geometry"], gmap.inputs["Guides"])
        c2 = grp("clump2", "Clump Hair Curves", gmap.outputs["Geometry"], Existing_Guide_Map=False)
        L.new(gmap.outputs["Guide Index"], c2.inputs["Guide Index"]); out = c2.outputs["Geometry"]
    def noisy(src, key, probability, seed, trim, **vals):
        sep = share(src, probability, seed, "GeometryNodeSeparateGeometry"); sel = sep.outputs["Selection"]
        if trim:
            t = grp(key + "_trim", "Trim Hair Curves", sel, Replace_Length=False)
            rl = N.new("FunctionNodeRandomValue"); rl.data_type = 'FLOAT'
            next(s for s in rl.inputs if s.name == "Max" and s.type == 'VALUE').default_value = 0.2
            L.new(grp(key + "_info", "Curve Info", None).outputs["Random"], rl.inputs["ID"])
            L.new(next(s for s in rl.outputs if s.type == 'VALUE'), t.inputs["Length Factor"]); sel = t.outputs["Geometry"]
        nz = grp(key, "Hair Curves Noise", sel, **vals); j = N.new("GeometryNodeJoinGeometry")
        L.new(nz.outputs["Geometry"], j.inputs[0]); L.new(sep.outputs["Inverted"], j.inputs[0])
        return j.outputs[0]
    if noise_share:
        out = noisy(out, "noise", noise_share, 0, False, **(noise or dict(Distance=0.02, Shape=0.2, Scale=10.0)))
    if flyaway_share:
        out = noisy(out, "flyaway", flyaway_share, 1, True, Distance=0.02, Shape=0.1, Preserve_Length=True)
    L.new(out, gout.inputs[0])
    m = hair.modifiers.new(name, 'NODES'); m.node_group = nt
    return made

# example on a head centred at (0, 0, 1.6): replace the tests, the gather point and the lengths with your own
hair_scalp = scalp_from_faces(body, "hair_scalp", lambda c, n: c.z > 1.63 and not (c.y < -0.06 and c.z < 1.67))
rim = hair_scalp.vertex_groups.new(name="main hair density")
rim.add([v.index for v in hair_scalp.data.vertices if (hair_scalp.matrix_world @ v.co).z < 1.66], 1.0, 'REPLACE')
part = hair_scalp.vertex_groups.new(name="parting")
part.add([v.index for v in hair_scalp.data.vertices if abs(v.co.x) > 0.008], 1.0, 'REPLACE')
main = new_hair(hair_scalp, "main hair"); main.color = (0, 0, 0, 1)
gather = Vector((0, 0.11, 1.62))                                       # where the hair band sits
roots = [p for p, n in scalp_points(hair_scalp, 0.02, lambda c, n: c.z < 1.66 and c.x > 0.004)]
lines = flow_guides(body, roots, lambda p, t: gather - p, lambda r: (gather - r).length * 1.3, points=30, lift=0.012)
add_guides(main, lines, points=30, mirror_x=True)
nodes = hair_tree(main, hair_scalp, "main hair", density=2000000.0, mask="main hair density", clump="INDEX",
                  blend_attr="parting", noise_share=0.1, flyaway_share=0.01)
nodes["interpolate"].inputs["Viewport Amount"].default_value = 0.25    # lighter viewport while shaping
result = {"guides": len(main.data.curves), "nodes": sorted(nodes)}
```

The parting rip is not in the snippet: split the scalp along the parting edges with
`bmesh.ops.split_edges(bm, edges=[...])` (tested) before adding hair. `lift=0.012` and the 1.3 length factor are
mine; the course only says to leave space under the guides and grows each one until it reaches the band.

## Settings the course uses

| Setting | Value | Where | Time |
|---|---|---|---|
| Curves render shape | Strand while placing guides, Strip to see thickness | Render Properties > Curves > Shape | 12:52:21 |
| Viewport | Matcap, outline off, focal length 150 mm; high-poly collection disabled in viewport | Layout workspace | 12:28:30 |
| Add brush, brows | Length 0.01 m then shorter, Points 8, Count 1, X symmetry | Curve Shape popover | 12:34:55 |
| Interpolate, brows | Density 50 000 up to 3 000 000; Interpolation Guides 4, 6, then 3; Mask Texture `brow density` (2K) | modifier | 12:47:10 |
| Profile, brows | Radius 0.0001 m, Shape 0.6 | `Set Hair Curve Profile` | 12:52:57 |
| Clump, brows | Guide Distance 0.004 m then 0.002 m; Existing Guide Map off | two `Clump Hair Curves` | 12:55:44 |
| Frizz, brows | Factor 0.272, Distance 0.001 m, Shape 0.5, Cumulative Offset off | `Frizz Hair Curves` | 12:57:37 |
| Lashes | Length 0.01 m; Radius 0.0002 m; Density 2 500 000; clump 0.001 m; noise Scale 8.98, Scale along Curve 15 | modifiers | 13:02:18 |
| Density brush, `short` | Distance Min 0.013 m, Count Max 100, Length 0.04 m | tool header | 13:24:39 |
| `short hair` tree | Density 800 000; clump Factor 0.743, Guide Distance 0.015 m; secondary guides Probability 0.95 deleted | node editor | 13:33:40 |
| Noise, `short` | share 0.25; Factor 1, Distance 0.015 m, Shape 0.1, Scale 10, Scale along Curve 40.9, Offset per Curve 0.1 | `Hair Curves Noise` | 13:39:50 |
| Add brush, main hair | Points 30; Interpolate Length and Shape on after the first guides | Curve Shape popover | 13:43:50 |
| `main hair` tree | Density 2 000 000; clump Shape 0.8, Existing Guide Map on; Blend Radius 0.01 m, Blend Neighbors 10 | node editor | 13:56:25 |
| Noise, main hair | share about 0.1; Distance 0.02 m, Shape 0.2, Cumulative Offset on | `Hair Curves Noise` | 14:01:10 |
| Flyaways | share 0.05 falling to 0.01; Length Factor random 0 to 0.2 (0.1 and 0.3 tried); Preserve Length on | Trim + Noise | 14:03:10 |
| Noise, ponytail | Factor 1, Distance 0.01 m, Shape 0.1, Scale 50, Scale along Curve 50, Cumulative Offset off | `Hair Curves Noise` | 14:22:10 |
| Mask images | 2048 x 2048, black, painted white, saved in `textures` | Texture Paint | 12:48:30 |

In 5.0 the Interpolate panel has a Method switch (Random / Poisson Disk) and the course leaves it on Random. In 4.5
the same input is the checkbox `Poisson Disk Distribution`, default on, so set it to `False`. The 4.5 default
Density is 10, which looks like "nothing happened".

## Mistakes the course warns about

- No UV map on the scalp, or pinned UVs inherited from the body: interpolation fails or the unwrap is wrong
  [12:32:40, 13:21:40]. A new plane already has UVs, which hides the problem for the ponytail scalp [14:20:05].
- Forgetting to set Surface on `Interpolate Hair Curves`: all hair disappears [12:23:45].
- Not saving a painted mask image: Blender does not save it with the file and it can be lost [12:50:11].
- Guides lying on the skull for long hair: the result is flat. Leave a gap [13:44:20].
- Guides or children through the head or over the ear; check with overlays off [12:38:16, 13:26:10].
- Judging thickness in Strand display: root and tip look equally thick there [12:52:00].
- Leaving Cumulative Offset on by habit; decide it per part by looking [14:01:21, 14:14:55].
- Uniform perfection. Noise goes on a share of the strands, not all of them [13:39:10].

## What changes for a different character

General: one scalp per region; guides only where they add control; the four steps; masks to keep children where
the guides are; clump then roughen; split the scalp for a parting; answer the two questions first.

Specific here: the parts (swept-back mass, side strands, ponytail), every density and distance (they suit a head
about 0.2 m wide), and black viewport colour. Scale distances with the head size.

- Curly or coiled hair: the course names the look ("a lot of noise", curls) but builds none; the bundled
  `Curl Hair Curves` and `Braid Hair Curves` are the groups to try after clumping (untested here).
- Long loose hair: more points per guide (the course uses 30 for shoulder-length), guides over the whole scalp, not
  only the rim, and a collision check against shoulders and clothes as well as the head.
- Beards, body hair, fur: the brow recipe at a larger scale; for fur use many short guides from `scalp_points` and
  a flow that follows the body.
- Bald or helmeted characters: skip the head hair; brows and lashes still apply.
- Very stylised chunky hair is better modelled as mesh in the sculpt stages; the narrator notes that thick Strip
  curves with no interpolation already give a stylised look [13:30:40].

## Exit check

```python
# verified in 4.5.16 background
def hair_report(hair, collide, tolerance=0.0005):
    """Evaluated strand count and how many sampled strand points (roots excluded) lie under the collide surface."""
    dg = bpy.context.evaluated_depsgraph_get(); dg.update(); ev = hair.evaluated_get(dg).data; n = len(ev.points)
    pos = np.empty(n * 3, dtype=np.float32); ev.attributes["position"].data.foreach_get("vector", pos)
    pos = pos.reshape(-1, 3); roots = {c.first_point_index for c in ev.curves}
    bvh = BVHTree.FromObject(collide, dg); to_c = collide.matrix_world.inverted() @ hair.matrix_world
    step = max(1, n // 20000); inside = checked = 0
    for i in range(0, n, step):
        if i in roots: continue
        p = to_c @ Vector(pos[i]); co, no, _, _ = bvh.find_nearest(p); checked += 1
        inside += co is not None and (p - co).dot(no) < -tolerance
    w = np.array(hair.matrix_world); world = pos @ w[:3, :3].T + w[:3, 3]
    return {"guides": len(hair.data.curves), "strands": len(ev.curves), "points_checked": checked,
            "points_inside": int(inside), "world_min": world.min(axis=0).round(3).tolist(),
            "world_max": world.max(axis=0).round(3).tolist()}

def outline_proxy(mesh_objs, hair_objs, name="HAIR_OUTLINE_PROXY", radius=0.0015):
    """One temporary mesh of body + hair (strands as thin tubes) so outline_match can measure the head with hair."""
    dg = bpy.context.evaluated_depsgraph_get(); dg.update(); parts = []
    for o in mesh_objs:
        me = bpy.data.meshes.new_from_object(o.evaluated_get(dg)); me.transform(o.matrix_world); parts.append(me)
    nt = bpy.data.node_groups.new("hair_proxy_tubes", 'GeometryNodeTree'); N, L = nt.nodes, nt.links
    nt.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    nt.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    gin, gout, c2m, circ = (N.new(t) for t in ("NodeGroupInput", "NodeGroupOutput", "GeometryNodeCurveToMesh",
                                               "GeometryNodeCurvePrimitiveCircle"))
    circ.inputs["Resolution"].default_value = 3; circ.inputs["Radius"].default_value = radius
    L.new(gin.outputs[0], c2m.inputs["Curve"]); L.new(circ.outputs["Curve"], c2m.inputs["Profile Curve"])
    L.new(c2m.outputs["Mesh"], gout.inputs[0])
    for h in hair_objs:
        m = h.modifiers.new("hair_proxy_tubes", 'NODES'); m.node_group = nt; dg.update()
        me = bpy.data.meshes.new_from_object(h.evaluated_get(dg)); me.transform(h.matrix_world); parts.append(me)
        h.modifiers.remove(m)
    bm = bmesh.new()
    for me in parts: bm.from_mesh(me); bpy.data.meshes.remove(me)
    out = bpy.data.meshes.new(name); bm.to_mesh(out); bm.free(); bpy.data.node_groups.remove(nt)
    ob = bpy.data.objects.new(name, out); bpy.context.scene.collection.objects.link(ob)
    return ob

nodes["interpolate"].inputs["Viewport Amount"].default_value = 1.0
result = {"brows": hair_report(brows, body), "main": hair_report(main, body)}
```

For every Curves object, failed if any of these is true:

- `strands` equals `guides` (nothing is interpolating: Surface, UV map name or Density is wrong) or is 0.
- `points_inside` is more than 1 % of `points_checked`. The limit is mine; the course checks by eye that nothing
  goes through the head. Roots are skipped because they sit on the surface. Also run it against the ears and, for
  long hair, the shirt.
- A scalp has no UV map, or a hair object's `data.surface` is not its scalp.
- Brows or lashes are not mirrored: `world_min[0]` and `world_max[0]` should be equal and opposite within 2 mm.
- A Curves object still has `Viewport Amount` below 1 on its Interpolate node or modifier.

Look, with `render_image` or `viewport_capture(shading="RENDERED")` and `render.hair_type = 'STRIP'`: close-ups of
each brow and eye from FRONT and three-quarter, and the head from FRONT, BACK, LEFT, RIGHT and TOP, each next to its
reference. Check flow direction per part, the parting, clump size against the reference, and bald patches.
`turnaround_sheet(object="CHARACTER")` shows every child, but thin strands may barely show in its clay shading; look
at the proxy too (`turnaround_sheet(object="HAIR_OUTLINE_PROXY")`).

Measure: hair strands are too thin to register in a silhouette, so measure a stand-in for the whole character. Build
`outline_proxy([every mesh under CHARACTER], [main, side, ponytail, ...])` (body, garments, eyes and all), run
`outline_match("HAIR_OUTLINE_PROXY", references, threshold=0.98)` on the views that have a real reference picture
of the character with this hairstyle, then delete the proxy object. Any view below 0.98 is failed. A view with no
reference picture is `not_run`: report it as "looked at, not measured", never as passed. The proxy tubes are 1.5 mm
thick (my choice) so strands register in a silhouette; with millions of strands lower `Viewport Amount` to about
0.1 first, because `outline_proxy` turns every evaluated strand into mesh.

## Gaps

- **Add-ons.** LoopTools (free; a Blender extension since 4.2) is used once, `LoopTools > Circle`, to make the
  ponytail scalp round [14:16:05]. Built-in route: `bpy.ops.mesh.primitive_circle_add(fill_type='NGON')` or
  `bpy.ops.mesh.looptools_circle()` is not needed at all. Everything else is built in.
- **Curve sculpt brushes** (Comb, Pinch, Slide and the rest) are not available to you. Flow functions plus
  `reshape_guides` reach the same shapes but without the look-and-nudge loop the course relies on; expect several
  capture-and-correct rounds per part. This is the weakest point of the stage.
- **Texture painting the masks** is replaced by vertex groups read through `Density Mask`. A mask is then only as
  sharp as the scalp's vertex spacing; subdivide the scalp where a crisp edge matters.
- **Hair material: the chapter has none.** It sets only the viewport colour (black) on each Curves object. The
  hair shader belongs to the next stage (course chapter 12, shading); add its material to each Curves object there.
- **Not shown in the video**: most of the main-hair, side-strand and ponytail guide placement is a time-lapse with
  music [13:47:20 to 13:52:00, 14:08:10, 14:17:55], so guide counts and exact paths for those parts are not
  recorded; the right-side strand is described, not made; the lower-lash Density is inaudible.
- **Unsettled in the course**: for secondary clumps the narrator unticks Existing Guide Map while also linking
  Guide Index. `hair_tree` copies that. If secondary clumps do not appear, tick it on node `clump2` and compare.
- `Curl Hair Curves`, `Braid Hair Curves` and the other unused groups are named from the asset file but untested.
