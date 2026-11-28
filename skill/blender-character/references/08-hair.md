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
5. **Mask**: unmasked, children cover the whole scalp. The course paints a black image `brow density` white
   where the brow is (Texture Paint, brush Paint Soft, Size 44 px, Strength 1.000, mode Single Image; the new-image
   dialog's size is not legible, see Settings; `Image > Save` straight after, `Alt S`) and picks it as Mask Texture
   [12:47:50 to 12:51:50].
6. **Profile**: Render Properties, `Curves > Shape: Strip`; add `Set Hair Curve Profile`, Radius 0.0001 m ("the
   average human hair is about 0.1 mm"), Shape 0.500 on the panel (the example below uses 0.6, my choice for a slightly
   stronger taper); Interpolation Guides reads 4 in every frame seen here, the narration mentions trying 6 and
   settling on 3 [12:52:00].
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
  `Hair Curves Noise` Cumulative Offset off, Factor about 0.13 (0.172 mid-drag, then reads 0.132; the sheets
  show no further drop), Shape 0.5, Scale 8.98, Scale along Curve 15 [13:12:10, 13:12:59].
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
  adding hair to a new scalp raised an error (the Surface Deform panel reads "Invalid surface UVs on 2 curves" after
  the fresh unwrap [14:20:24]), the fix was select curves then scalp,
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

## How the artist works on screen

Read from 120 course sheets (Blender 5.0.1, the version label is bottom right). Clip ids are `qy-wwP-b9HY-11-` plus
six digits; times are the on-screen clock. Brush sizes below are screen pixels at the artist's zoom and do not carry
over to you: use the world-unit equivalents given with each step. These are observations; "reader" lines are mine.

### Layout and habits (all steps)

- Brows, lashes and the short cut are done in the **Layout** workspace: 3D viewport on the left, an area that is
  switched between Asset Browser (`Essentials > Hair`), Image Editor, UV Editor and Geometry Node Editor, and the
  Properties editor on the right. A small Text editor lists the four steps: create guides, interpolate, clump, add
  noise and frizz, with the current line highlighted [qy-wwP-b9HY-11-124648, 12:46:50; qy-wwP-b9HY-11-125508, 12:55:09].
- Viewport: MatCap lighting, focal length 150 mm set in the `N` panel `View` tab, Outline left ticked
  [qy-wwP-b9HY-11-122827, 12:28:32 to 12:28:39]. The hair reference floats over the viewport as a separate small
  window, so the picture and the head are always in view together [qy-wwP-b9HY-11-123013].
- Curves Sculpt Mode shows a brush shelf under the viewport: Comb, Grow/Shrink, Pinch, Puff, Pull Tips, Slide, Smooth,
  Add, Delete, Density, Select. The header holds Size, Strength, a Sphere / Projected pair, Brush Falloff, Curve Falloff
  and the X Y Z mirror toggles [qy-wwP-b9HY-11-122158]. `Q` opens a Quick Favorites list (Add, Delete, Comb, Grow/Shrink,
  Pull Tips, Smooth, Slide, Puff, Pinch); `F` resizes the brush; `Ctrl+Tab` flips between Object Mode and Curves Sculpt
  Mode [qy-wwP-b9HY-11-123756, 12:37:58; qy-wwP-b9HY-11-135144, 13:51:51].
- **Strength reads 1.000 in every header that is legible.** The artist changes the radius instead: about 40 to 100 px
  for Add, 100 to 470 px for Comb, 164 px for Grow/Shrink, 44 px for Paint Soft.
- Rhythm: a few strokes, then orbit to a second view (side after front, top after side) to check nothing passes through
  the skin; he zooms in far for the brow and lash work, out to the full head for the main hair. He judges finished work
  against the floating reference, in a clean grey matcap, in the viewport colour he set (black for brows and main hair).
- Do not copy: the ponytail Curves object stays at the default light viewport colour in the video, so it renders pale
  while the rest is black [qy-wwP-b9HY-11-142258, 14:23:00]. Set it black yourself to match.

### Reading the system (before step 1)

- Scalp, guides and children: the artist shows a plane with a few dark guides and many pale children, then the
  subdivision-surface comparison [qy-wwP-b9HY-11-121402, 12:14:04 to 12:14:14].
- Brush demonstrations on a bald head: Delete removes one whole guide when hovered, Select picks whole curves (Sphere
  mode, Strength 1.000), and a very large Comb (about 312 to 404 px) drags the whole fan [qy-wwP-b9HY-11-121757,
  qy-wwP-b9HY-11-121914, qy-wwP-b9HY-11-122158]. Sphere only touches hairs near the surface under the cursor; Projected
  carries through everything under the circle.
- Modifiers or nodes: dragging `Interpolate Hair Curves` from the Asset Browser onto the object makes everything vanish
  until Surface is chosen (panel: Surface empty, Surface UV Map `UVMap`, Interpolation Guides 4, Part by Mesh Islands
  ticked, Method Random, Density 10) [qy-wwP-b9HY-11-122343, 12:23:45 to 12:23:56]. `Clump Hair Curves` opens with
  Factor 1.000, Shape 0.500, Tip Spread 0, Guide Distance 0.1 m, Existing Guide Map ticked [qy-wwP-b9HY-11-122442].

### Step 1. Eyebrows

- **1.1 Scalp.** On `body_retopo` in Edit Mode he selects the quads under one brow, enables the high-poly collection to
  see the sculpted ridge, duplicates and separates them; the new `brow_scalp` has a Shrinkwrap (Nearest Surface Point,
  On Surface, offset 0 m, target `body_retopo`) and a Mirror (merge 0.001 m); `Ctrl+A` opens Apply and he picks Visual
  Geometry to Mesh [qy-wwP-b9HY-11-123013; qy-wwP-b9HY-11-123129, 12:31:31]. The scalp goes into a new collection. He
  selects all, `U`, Unwrap Angle Based, and scales the two UV islands into the square; the UV layout is irrelevant
  [qy-wwP-b9HY-11-123221; qy-wwP-b9HY-11-123253]. Reader: `scalp_from_faces(body, "brow_scalp", test, subdivide=2)`.
- **1.2 Mark the brow.** Annotate tool, Placement set to Surface (the header lists 3D Cursor, View, Surface), a blue
  line drawn over the sculpt [qy-wwP-b9HY-11-123333, 12:33:46]. Reader: choose three or four world points on the brow
  centre line from the sculpt and reference.
- **1.3 Guides.** `Add > Curve > Empty Hair` (object `eyebrows`, a Surface Deform modifier is already there). In Curves
  Sculpt Mode he picks Add, ticks X mirror, and drops the first strand with the Curve Shape popover open: `Interpolate`
  shows Length / Radius / Shape / Point Count tick boxes with only Radius ticked, Length typed as 0.01 m, Points 8
  [qy-wwP-b9HY-11-123428; qy-wwP-b9HY-11-123447, 12:34:50 to 12:34:55]. He adds a few strands, then combs each along the
  blue line with Comb (Projected, Strength 1.000, radius about 410 to 470 px zoomed to the brow). Guides that dive
  through the skin are selected with Select, then Comb pushes them out, checked edge-on [qy-wwP-b9HY-11-123813]. Toward
  the tail he uses Grow/Shrink with `Ctrl`; its Scaling popover shows Scale Uniform off and Minimum Length 0 m, which is
  what lets it shorten [qy-wwP-b9HY-11-124312, 12:43:25 to 12:43:31]. Reader: `add_guides(brows, flow_guides(...),
  points=8, mirror_x=True)`; shorten the tail guides by scaling about the root, e.g. 0.007 m falling to 0.0035 m.
- **1.4 Interpolate.** Dragged in; Surface chosen with the eyedropper from the scalp; Density typed (about 50 000, later
  up to 800 000 and 3 000 000); with no mask the whole scalp outline fills with hair [qy-wwP-b9HY-11-124702;
  qy-wwP-b9HY-11-124743, 12:47:44 to 12:47:54]. Reader: `add_hair_modifier(brows, "Interpolate Hair Curves", Surface=...,
  Poisson_Disk_Distribution=False, Density=...)`.
- **1.5 Mask.** In Texture Paint he opens the Texture Slots popover, sets Single Image, and clicks `New` to open
  the create-image dialog (name `brow density`, a Width/Height pair whose default shows 1024 px, Blank, alpha ticked;
  Paint Hard is active in the header) [qy-wwP-b9HY-11-124823, 12:48:24 to 12:48:35]. Strokes follow the brow outline
  on the scalp with Paint Soft, white, Mix, Size 44 px, Strength 1.000; the Image Editor below shows two white arcs
  on black, and `Image > Save` is used at once [qy-wwP-b9HY-11-125009, 12:50:10 to 12:50:16]. After painting the brows
  shrink to a thin line [qy-wwP-b9HY-11-125146].
  Reader: `Density_Mask="density"`, a vertex group weighted 1 on the brow band (see snippet).
- **1.6 Profile.** Render Properties, `Curves` panel, Shape Strand / Strip / Cylinder; Strip makes the brow flat and
  wide [qy-wwP-b9HY-11-125208, 12:52:16; qy-wwP-b9HY-11-125244]. `Set Hair Curve Profile` panel: Replace Radius ticked,
  Radius (0.0001 m typed), Shape 0.500, Factor Min 0.000, Factor Max 1.000. The Curves object's Color (Object properties
  > Viewport Display) is changed from white to black [qy-wwP-b9HY-11-125305, 12:53:14].
- **1.7 Clump.** `Clump Hair Curves` with Existing Guide Map unticked, then Guide Distance 0.002 m on a second clump; a
  clump inside a clump is the look [qy-wwP-b9HY-11-125531; qy-wwP-b9HY-11-125658, 12:56:59 to 12:57:09].
- **1.8 Frizz.** On first drop it is wild (Cumulative ticked, Factor 1.000, Distance 0.01 m, Shape 0.500); he unticks
  Cumulative, lowers Distance to 0.001 m, then drags Factor down to 0.272 [qy-wwP-b9HY-11-125728, 12:57:36;
  qy-wwP-b9HY-11-125749; qy-wwP-b9HY-11-125817, 12:58:18]. Done when a front view of the whole head shows brows that
  look soft, not wiry.

### Step 2. Eyelashes

- **2.1 Scalp.** On `body_retopo` he selects the lid ring in a side view, duplicates it to `lashes_scalp` (a thin band
  that appears as an orange ring on each eye) and unwraps: the UV editor shows four long curved strips, and he checks
  that none overlap [qy-wwP-b9HY-11-125829; qy-wwP-b9HY-11-130051, 13:00:53 to 13:01:03].
- **2.2 Guides.** New Curves object `eyelashes`. Add brush, Curve Shape popover, Length about 0.01 m, Points 8; he
  keeps the display on Strand while placing (the Render Properties tab shows Shape Strand), because in Strip the guide
  is a fat flat patch [qy-wwP-b9HY-11-130206; qy-wwP-b9HY-11-130221, 13:02:33]. Lashes are placed evenly along the upper
  lid in a close three-quarter view, with `lashes_scalp` selected so the roots can be seen [qy-wwP-b9HY-11-130246].
  Grow/Shrink with `Ctrl` (radius about 164 px) shortens the corners; plain Grow lengthens the middle
  [qy-wwP-b9HY-11-130402]. X mirror is on in the header when he combs the outward-then-up curve
  [qy-wwP-b9HY-11-130457; qy-wwP-b9HY-11-130537]. Reader: `add_guides(lashes, ..., points=8, mirror_x=True)`.
- **2.3 Stack.** Strip display on, `Set Hair Curve Profile` put above `Interpolate` (stack: Surface Deform, Set Hair
  Curve Profile, Interpolate, Clump, Noise); order does not matter, he says [qy-wwP-b9HY-11-130958; qy-wwP-b9HY-11-131103].
  Clump: Factor 1.000, Shape 0.500, Tip Spread 0.001, Guide Distance 0.001 m, Existing Guide Map off
  [qy-wwP-b9HY-11-131201, 13:12:02]. `Hair Curves Noise`: Cumulative Offset off, Factor about 0.13 after dragging
  (0.17 mid-drag), Distance 0.01 m, Shape 0.500, Scale 8.980, Scale along Curve 15.000, Offset per Curve 0
  [qy-wwP-b9HY-11-131248, 13:12:50 to 13:12:59].
- **2.4 Lower lashes.** A second object `eyelashes.001` with the same stack (profile, Interpolate on `lashes_scalp` with
  Density about 2 500 000, Clump, Noise) [qy-wwP-b9HY-11-131611, 13:16:12]. The lowered Density is not legible.

### Step 3. Head hair

- **3.1 Scalp.** In Edit Mode on `body_retopo` he selects the cranium faces in side, back and rear-three-quarter views,
  adds missing faces with `Shift`, duplicates (`Shift+D`) and separates (`P`) [qy-wwP-b9HY-11-131750]. Shrinkwrap and
  Mirror are applied with `Ctrl+A > Visual Geometry to Mesh`, then `U` > Unwrap, and he renames it `hair_scalp`
  [qy-wwP-b9HY-11-132132; qy-wwP-b9HY-11-132218].
- **3.2 Short cut.** Object `short`. Density brush (shelf shows Smooth, Add, Delete, Density, Select here): header Distance
  Min about 0.01 m and Count Max 100, strokes over the cranium from side and top views; it fills the head with upright
  guides like a mohawk, and he types a larger Distance Min (0.02) to thin it [qy-wwP-b9HY-11-132420, 13:24:22 to
  13:24:37]. From the side Comb (Projected) lays the guides down; hairs are kept in front of the ear; the front hairs
  are angled up and forward [qy-wwP-b9HY-11-132607; qy-wwP-b9HY-11-132756]. Reader: `scalp_points(scalp, 0.013..0.02)`
  and `flow_guides(..., length=0.04, points=8)`.
- **3.3 Node tree `short hair`.** The bottom area is switched to Geometry Node Editor (editor-type menu), a new group
  `short hair` appears beside the Surface Deform one, and nodes are dragged in from the Asset Browser
  [qy-wwP-b9HY-11-132949, 13:29:54 to 13:30:01]. `Set Hair Curve Profile` first: Strip on, Radius typed as 0.1 mm
  [qy-wwP-b9HY-11-133038, 13:30:51]. `Interpolate Hair Curves`: Part by Mesh Islands ticked, Interpolation Guides 4,
  Distance to Guides 0 m, Method Random, Density 800 000, Viewport Amount 1.000; a Named Attribute node holds the UV map
  name [qy-wwP-b9HY-11-133258, 13:33:00 to 13:33:09]. `Clump Hair Curves`: Guide Distance 0.05 m, edited to 0.01 m
  (final value 0.015 m), Existing Guide Map unticked; Factor dragged from 0.994 to 0.765
  [qy-wwP-b9HY-11-133336; qy-wwP-b9HY-11-133403]. Reader: `hair_tree(short, hair_scalp, "short hair", density=800000.0,
  clump="DISTANCE", guide_distance=0.015)`.
- **3.4 Share-based noise.** `Hair Curves Noise` first on everything (Factor 1.000, Distance 0.015 m, Shape 0.500, Scale
  31.500, Scale along Curve 15.400). He then adds Separate Geometry (the narration and an on-screen note say change Point
  to Spline), a Random Value (Boolean) feeding its Selection with Probability typed as 0.25, and joins the Inverted
  output back [qy-wwP-b9HY-11-133908; qy-wwP-b9HY-11-133939]. Done when the top looks mostly smooth with a few rough
  strands. Reader: `noise_share=0.25`.
- **3.5 Ponytail-style plan.** He draws the parts and flow on the reference (red outlines and orange arrows: guides pack to
  one point at the band, the lower tail runs a different way and is shorter) [qy-wwP-b9HY-11-120935, 12:09:38 to 12:09:53].
- **3.6 Main hair guides.** Annotate with Placement Surface marks the hair pattern (blue lines over the bald head); Add
  brush, Curve Shape popover: Interpolate Radius ticked, Length 0.3 m, Points typed 30, X mirror on; the first strand
  stands straight up from the hairline [qy-wwP-b9HY-11-134302; qy-wwP-b9HY-11-134348, 13:43:50 to 13:43:58]. Comb
  (Projected, radius 162 to 314 px) arches each guide over the head; `Shift` smooths; near the middle line the Comb
  radius is cut from about 454 px to 180 px so the mirrored twin is not caught [qy-wwP-b9HY-11-134418;
  qy-wwP-b9HY-11-134608]. The time-lapse (5X speed badge) shows the sequence only in outline: arcs of white guides from
  the hairline rim, over the crown, to one point behind the head [qy-wwP-b9HY-11-134714; qy-wwP-b9HY-11-135144, 13:51:46
  to 13:52:01]. Reader: `flow_guides(body, roots, lambda p,t: gather - p, ..., points=30, lift=0.012)`, mirrored.
- **3.7 Main hair tree.** New group `main hair`: Set Hair Curve Profile (Radius 0.0001 m, Shape 0.500), a Named Attribute
  for the UV map, `Interpolate` (children appear over the whole scalp, with a ring of guides only at the rim)
  [qy-wwP-b9HY-11-135253; qy-wwP-b9HY-11-135332]. The mask is a painted image `main hair density`, saved
  [qy-wwP-b9HY-11-135554]. Clump takes Interpolate's Guide Index; Shape dragged from 0.500 to 0.800, Factor 1.000
  [qy-wwP-b9HY-11-135619]. Density reads 1 500 000 at 13:58:14 and 2 000 000 at 14:06:21, so it was raised late
  [qy-wwP-b9HY-11-135812; qy-wwP-b9HY-11-140619].
- **3.8 Parting.** Part by Mesh Islands is ticked but does nothing on one island; he selects half the scalp (Select Linked
  is the last operator shown) and separates it so the mesh has left, right and rest islands; the parting then shows on
  the forehead; `Blend Hair Curves` (Factor 1.000, Blend Radius 0.01 m, Blend Neighbors 10) closes it again until its
  Factor is fed from an attribute [qy-wwP-b9HY-11-135704; qy-wwP-b9HY-11-135756; qy-wwP-b9HY-11-135812]. Reader: split
  scalp edges along the parting; `blend_attr="parting"`.
- **3.9 Noise and flyaways.** Random Value probability about 0.066 into Separate Geometry (Spline) then Noise: Cumulative
  Offset off, Distance 0.01 then 0.02 m, Shape 0.500, Scale 47.2, Scale along Curve 44.6, Factor 1.000
  [qy-wwP-b9HY-11-140051; qy-wwP-b9HY-11-140110]. The Separate Geometry plus Random Value pair is duplicated for the
  short, noisy flyaways [qy-wwP-b9HY-11-140258, 14:02:59 to 14:03:08].
- **3.10 Side strand.** New object `left side hair` with its own tree; Q-menu to Add, Slide, Comb; a few long guides hang
  from the front hairline past the eye and cheek, curved from the side view [qy-wwP-b9HY-11-140754;
  qy-wwP-b9HY-11-140806 at 5X speed]. Its tree: Clump with Guide Distance 0.1 m and Existing Guide Map ticked, Create
  Guide Index Map after Delete Geometry for secondary clumps, Noise with Cumulative off, Scale 100, Scale along Curve 100
  [qy-wwP-b9HY-11-141206; qy-wwP-b9HY-11-141258; qy-wwP-b9HY-11-141444]. The right side repeats it with another mask
  [qy-wwP-b9HY-11-141508].
- **3.11 Ponytail.** A plane is scaled down and placed at the back, subdivided twice, made round with LoopTools Circle (the
  operator panel is labelled Circle); `U` > Unwrap Angle Based because no UV map was made; the Surface Deform modifier
  then warns "Invalid surface UVs on 2 curves" [qy-wwP-b9HY-11-141600, 14:16:11; qy-wwP-b9HY-11-142002;
  qy-wwP-b9HY-11-142016, 14:20:24]. Guides: Add brush, then Grow/Shrink and Comb (radius about 190 to 440 px), a fan of
  about a dozen long guides drooping from the disc [qy-wwP-b9HY-11-141750; qy-wwP-b9HY-11-141935]. Tree: profile 0.0001 m,
  Interpolate Density 8 000 000 then 10 000 000, Clump Guide Distance 0.1 m, Existing Guide Map ticked, Separate Geometry
  (Spline) with Random Value about 0.074 [qy-wwP-b9HY-11-142154]. Final Noise: Cumulative off, Factor 1.000, Distance
  0.01 m, Shape 0.100, Scale and Scale along Curve first 50 then 20 [qy-wwP-b9HY-11-142258, 14:23:10 to 14:23:16]. Done when
  the tail from the back reads as curling tufts at the band, not a smear.

## Settings the course uses

| Setting | Value | Where | Time |
|---|---|---|---|
| Curves render shape | Strand while placing guides, Strip to see thickness | Render Properties > Curves > Shape | 12:52:21 |
| Viewport | Matcap, Outline ticked, focal length 150 mm; high-poly collection disabled in viewport | Layout workspace | 12:28:30 |
| Add brush, brows | Length 0.01 m then shorter, Points 8, Count 1, X symmetry | Curve Shape popover | 12:34:55 |
| Interpolate, brows | Density 50 000 up to 3 000 000; Interpolation Guides 4, 6, then 3; Mask Texture `brow density` | modifier | 12:47:10 |
| Profile, brows | Radius 0.0001 m, Shape 0.6 | `Set Hair Curve Profile` | 12:52:57 |
| Clump, brows | Guide Distance 0.004 m then 0.002 m; Existing Guide Map off | two `Clump Hair Curves` | 12:55:44 |
| Frizz, brows | Factor 0.272, Distance 0.001 m, Shape 0.5, Cumulative Offset off | `Frizz Hair Curves` | 12:57:37 |
| Lashes | Length 0.01 m; Radius 0.0002 m; Density 2 500 000; clump 0.001 m; noise Factor about 0.13, Scale 8.98, Scale along Curve 15 | modifiers | 13:02:18 |
| Density brush, `short` | Distance Min about 0.01 m on first stroke, 0.02 tried; final 0.013 m; Count Max 100 (legible); Length 0.04 m | tool header | 13:24:39 |
| `short hair` tree | Density 800 000; clump Factor 0.743 final (0.994 to 0.765 seen while dragging), Guide Distance 0.015 m (0.05 default, 0.01 tried); secondary guides Probability 0.95 deleted | node editor | 13:33:40 |
| Noise, `short` | share 0.25; Factor 1, Distance 0.015 m, Shape 0.1, Scale 10, Scale along Curve 40.9, Offset per Curve 0.1 | `Hair Curves Noise` | 13:39:50 |
| Add brush, main hair | Length 0.3 m before growing, Points 30 (typed); Interpolate Radius ticked | Curve Shape popover | 13:43:50 |
| `main hair` tree | Density 2 000 000; clump Shape 0.8, Existing Guide Map on; Blend Radius 0.01 m, Blend Neighbors 10 | node editor | 13:56:25 |
| Noise, main hair | share about 0.1; Distance 0.02 m, Shape 0.500, Cumulative Offset unticked | `Hair Curves Noise` | 14:00:51 to 14:01:10 |
| Flyaways | share 0.05 falling to 0.01; Length Factor random 0 to 0.2 (0.1 and 0.3 tried); Preserve Length on | Trim + Noise | 14:03:10 |
| Noise, ponytail | Factor 1, Distance 0.01 m, Shape 0.1, Scale and Scale along Curve 50 first, then 20 and 20, Cumulative Offset off | `Hair Curves Noise` | 14:23:10 to 14:23:16 |
| Mask images | Name `brow density` / `main hair density`; create dialog defaults to 1024 px (typed final resolution not legible); black, painted white, saved | Texture Paint | 12:48:30 |

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

Anime sculpted hair (clay, not strands): follow `anime-clay-planes.md`, "Hair".
- Tight or slicked hair is one grooved mass with one graphic bang.
- Everything else is separate `hair_lock` objects over a smooth cap: thick at the root, needle-sharp at the tip,
  grooved, front bangs first.
- Sink each root by its thickness plus 5 mm.

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

## Low-poly game route (second course: Nhij Quang, Girl#01)

Second source: Nhij Quang, [Blender 3D Quick Modeling Character For Game - Girl#01](https://www.youtube.com/watch?v=mlnR-Eyazh0), Blender 4.2.1 LTS, 1 h 15 min, no narration (music only). Everything here was read off the screen: the key-cast overlay, redo panels, modifier panels and status-bar counts, from 157 study sheets; labels are in `annotations/mlnR-Eyazh0/`. Times marked `NQ` point into that video, not the main course. Use this route instead of the sculpt route when the job is a low-poly game character (box/poly modelled, hand-painted, Mixamo-rigged); see "Two routes" in `SKILL.md`. Values that could not be read are listed as not visible, never guessed. Python blocks marked `# not run in Blender` were not executed.

Source: chapter 10 "Hair Modeling", 00:42:03 to 00:51:20 (19 clips). The hair is built from extruded polygon strips: single-sided, one face wide, no thickness, no Solidify modifier, no curves and no particle hair. It is split into a fringe object, a mirrored cap-plus-back-hair object, and a bun made of duplicated rotated petals.

### Order of work

1. [NQ 00:42:03 to 00:42:13] Snap the 3D cursor to the world origin (Shift+S pie). Make a new empty mesh object (named Cube.007 again, because the old head Cube.007 was joined into the body). It has no modifiers and Verts 0/0. Object count 1/10.
2. [NQ 00:42:13 to 00:42:57] In see-through Front Orthographic, extrude a vertex chain from the crown along the hairline and rotate it (Move X 0.055742, Z 0.090581 m; header Rotation 19.82). Adjust it in side view, with undo and Ctrl-click extrude to cursor. With see-through off, push the strip off the scalp (Move X 0.029015, Z -0.012194 m). Result: a one-row band of quads over the top of the head from the centre to the temple. 26 verts, 12 faces.
3. [NQ 00:42:57 to 00:43:56] Bang strands: extrude band edges straight down into strips one face wide, beside and in front of the face. Taper the tips with Scale and add a loop cut along each strand (1 cut, Falloff Inverse Square, Factor about 0.088, Clamp, Mirror Editing, Correct UVs on). One long lock is pulled down past the jaw in side view (Move Y about 0.148 m). The left image editor is switched to a close front portrait. Result: 62 verts, 27 faces.
4. [NQ 00:43:56 to 00:44:47] More fringe strands with Extrude x4 (Move X -0.034516, Z -0.11468 m). Bend them with Proportional Editing (header Proportional Size 0.3505 m). Rip (V) to split neighbouring strands; one attempt shows "Rip failed". Result: Cube.007 fringe, 87 verts, 41 faces, 82 tris. The fringe is asymmetric and has no Mirror modifier.
5. [NQ 00:44:47 to 00:44:55] Select a side strand with Select Linked and open Add Modifier. The next frame shows a new object Cube.008 with a Mirror modifier (X, Clipping, Merge 0.001 m). Inferred: the strand was separated (P) into Cube.008, which got a Mirror. Object count 0/11.
6. [NQ 00:44:55 to 00:45:31] Add a UV Sphere (146 verts, 304 edges, 160 faces; that matches 16 segments x 10 rings). Move it up to head height (Move Z 1.8573 m) and fit it over the skull in side view (Move Y -0.022645, Z 0.051388 m). Delete part of it (X). It then shows as part of Cube.008 and is shaped with Proportional Editing (size 0.2176 m). Result: Cube.008 = mirrored half cap plus side lock, 69 verts / 46 faces.
7. [NQ 00:45:31 to 00:46:01] Return to Cube.007 and adjust the fringe from Front, Top and Left Orthographic so it hugs the cap (87 verts / 42 faces).
8. [NQ 00:46:01 to 00:46:59] Bun on top, in Cube.007: model one small petal piece at the crown. Duplicate it and rotate the copy around Z in top view (Angle 82.6, then -75.5, Orientation View). Add a loop cut to bend the petals (header "Cuts: 1, Smoothness: 0.00") and move vertices (X 0.015567, Y 0.007938, X -0.010569 m). Result: a closed ring of petals forming the bun. Cube.007 is about 189 verts / 99 faces.
9. [NQ 00:46:59 to 00:47:58] In Cube.008, duplicate (Shift+D) and extrude a strip from the cap down behind the ear (Extrude Move X -0.031752, Z 0.050802 m). Bend it with Proportional Editing (Falloff Root, Size 0.180, Connected on; Move Y -0.059278 m). Add a loop cut along it (1 cut, Factor 0). Fit the tip in see-through front view. Result: 97 verts / 64 faces.
10. [NQ 00:47:58 to 00:49:11] Back hair: duplicate one back strand and rotate the copy around Z in top view (Angle -31.3, Orientation View). Scale the tips to a point and repeat around the back of the head. Mirror Clipping on Cube.008 is now off, so strands can cross the centre line. Circle Select (C) in see-through front view to refine. Extrude tips and rotate them outward (Angle -19.5) for flicks. Result: a bob made of vertical strips. Cube.008 is about 208 verts / 130 faces / 255 tris on the half.
11. [NQ 00:49:11 to 00:49:55] Select one strip with Select Linked and duplicate it. A new object Cube.009 appears (18 verts, 10 faces, no modifier); it is scaled and loop-cut. Then Tab, Ctrl+Z x4, Tab, and the object count drops back to 11. Whether Cube.009 was kept, joined or undone cannot be read.
12. [NQ 00:49:55 to 00:50:54] Add layered strands by the ear: duplicate (Add Duplicate Move X -0.044, Z -0.004552 m, Mirror Editing off) and rotate (Angle -14.2). Grow the selection with Select More (Face Step on). Extrude the strand end edge and scale it to a point for spiky tips (Move Y 0.085238, Z -0.019493 m). Fix tips from back and 3/4 views. Result: Cube.008 about 277 verts / 166 faces / 327 tris.
13. [NQ 00:50:54 to 00:51:20] Knife cuts on the body torso (not hair). Final outliner: Model collection = Body (Mirror X, Clipping, Merge 0.001 m), Hair1, Hair2. Scene 4,405 verts / 3,889 faces / 7,520 tris. Mapping Hair1 = fringe+bun (Cube.007) and Hair2 = cap+back (Cube.008) is inferred.

Piece count seen: 2 hair objects at the end (Hair1, Hair2), plus a temporary Cube.009. Strand count by eye: about 4 to 5 fringe strands, about 6 to 8 bun petals, and about 10 to 12 back/side strips on the mirrored half. These are estimates from the frames, not exact counts.

### How it looks on screen

- The reference panel on the left changes from the turnaround to a large front portrait and later a back view, while the viewport keeps the sheet behind the model.
- See-through/X-ray in Front Orthographic is used to trace hair outlines. Solid view is used to check that strips sit above the head.
- Top Orthographic is used for every duplicate-and-rotate around the head (Rotate, Axis Z, Orientation View).
- The fringe object has no Mirror. The cap/back object uses Mirror X, with Clipping turned off later.
- Proportional Editing (Root falloff, Connected) is used to bend long strands.
- Strips are flat polygon cards: no Solidify, no Subdivision, no curve objects seen in the modifier stack or outliner.

### Python route

```python
# not run in Blender
import bpy, bmesh, math
from mathutils import Vector, Matrix

# Step 1: cursor to origin, empty hair object
bpy.context.scene.cursor.location = (0, 0, 0)
me = bpy.data.meshes.new("Hair1"); fringe = bpy.data.objects.new("Hair1", me)
bpy.context.collection.objects.link(fringe)
```

```python
# not run in Blender
# Step 2-3: one strand = a strip of quads from a root edge along a list of centre points
def strand(bm, pts, width_root=0.03, width_tip=0.002, side=Vector((1, 0, 0))):
    rows = []
    n = len(pts)
    for i, p in enumerate(pts):
        w = width_root + (width_tip - width_root) * i / (n - 1)
        rows.append((bm.verts.new(p - side * w / 2), bm.verts.new(p + side * w / 2)))
    for (a, b), (c, d) in zip(rows, rows[1:]):
        bm.faces.new((a, b, d, c))

bm = bmesh.new()
strand(bm, [Vector((0.03, -0.10, 1.90)), Vector((0.05, -0.11, 1.84)), Vector((0.06, -0.10, 1.78)), Vector((0.065, -0.08, 1.72))])  # placeholder points
bm.to_mesh(fringe.data); bm.free()
```

```python
# not run in Blender
# Step 6: skull cap from a UV sphere, keep upper half and +X side, mirrored
bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=10, radius=0.11, location=(0, -0.02, 1.86))
cap = bpy.context.active_object; cap.name = "Hair2"
bm = bmesh.new(); bm.from_mesh(cap.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x < -1e-5 or v.co.z < -0.03], context='VERTS')
bm.to_mesh(cap.data); bm.free()
mm = cap.modifiers.new("Mirror", 'MIRROR'); mm.use_axis[0] = True; mm.use_clip = True; mm.merge_threshold = 0.001
```

```python
# not run in Blender
# Step 8/10: duplicate a strand/petal and rotate the copy about the head's Z axis (Top view)
def dup_rotate(obj, deg, pivot):
    bm = bmesh.new(); bm.from_mesh(obj.data)
    src = [f for f in bm.faces if f.select]          # the strand faces
    ret = bmesh.ops.duplicate(bm, geom=src)
    verts = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.rotate(bm, verts=verts, cent=pivot, matrix=Matrix.Rotation(math.radians(deg), 3, 'Z'))
    bm.to_mesh(obj.data); bm.free()

for a in (-31.3, -62.6, -93.9):   # angle seen: -31.3 per copy (spacing of later copies not readable)
    dup_rotate(cap, a, Vector((0, -0.02, 1.86)))
```

```python
# not run in Blender
# Step 9: bend a long strand with proportional editing (edit mode, tip verts selected)
bpy.ops.transform.translate(value=(0, -0.059278, 0), use_proportional_edit=True,
                            proportional_edit_falloff='ROOT', proportional_size=0.18,
                            use_proportional_connected=True)
# Step 10: allow strands to cross the centre line
cap.modifiers["Mirror"].use_clip = False
```

```python
# not run in Blender
# Step 12: spiky tip = extrude end edge, move, scale to a point
bm = bmesh.from_edit_mesh(cap.data)
tip = [e for e in bm.edges if e.select]
ret = bmesh.ops.extrude_edge_only(bm, edges=tip)
nv = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
bmesh.ops.translate(bm, verts=nv, vec=Vector((0, 0.085238, -0.019493)))
c = sum((v.co for v in nv), Vector()) / len(nv)
bmesh.ops.scale(bm, vec=Vector((0.05, 0.05, 0.05)), space=Matrix.Translation(-c), verts=nv)
bmesh.update_edit_mesh(cap.data)
```

### Settings read on screen

- Hair fringe object (Cube.007 to Hair1): no modifiers.
- Cap/back object (Cube.008 to Hair2): Mirror Axis X, Merge 0.001 m. Clipping on at first, off from about 00:48:35.
- Body at the end: Mirror X, Clipping on, Merge 0.001 m.
- UV Sphere: 146 verts, 304 edges, 160 faces, 288 tris. Moved to Z 1.8573 m, then Y -0.022645 / Z 0.051388 m.
- Extrude Region and Move: X 0.055742 / Z 0.090581; X -0.034516 / Z -0.11468; X -0.031752 / Z 0.050802; Y 0.085238 / Z -0.019493 (m). Flip Normals off, Dissolve Orthogonal Edges off.
- Header Rotation 19.82 (first hairline extrude).
- Rotate (Axis Z, Orientation View): 82.6, -75.5, -31.3, -19.5, -14.2 degrees.
- Proportional Editing: size 0.3505 m (fringe), 0.2176 m (cap), Falloff Root, Size 0.180, Connected on (side lock).
- Loop Cut and Slide: Number of Cuts 1, Smoothness 0, Falloff Inverse Square, Factor 0.088 (fringe, as read) and 0.000 (side lock), Clamp on, Correct UVs on.
- Add Duplicate: Move X -0.044, Z -0.004552 m, Mirror Editing off.
- Select More: Face Step on.
- Scale redo values seen but hard to read: -0.156 (sign unclear), 0.053 (digit unclear), -0.688 (sign unclear).
- Counts: fringe 87 verts / 41 faces before the bun. Cap/back half 277 verts / 166 faces / 327 tris near the end. Final scene 4,405 verts / 3,889 faces / 7,520 tris, objects Body, Hair1, Hair2.

### Not visible in the frames

- How each empty hair object was created (Cube.007 at 00:42:13 shows Verts 0/0).
- Whether the strand at 00:44:47 was separated with P, or the Mirror was added some other way. Only the result (Cube.008 with Mirror) is seen.
- Whether the sphere was joined into Cube.008 with Ctrl+J, or its geometry copied in.
- What happened to Cube.009: it was undone or joined, but the frames do not say which.
- When Hair1/Hair2 were renamed and when the body parts Cube.001 to Cube.006 were joined into Body. This happens between 00:51:09 and 00:51:16.
- Normals direction, backface culling and double-sided settings for the single-sided strips.
- Any UV, material or texture work on the hair. None is shown in this chapter.
- Exact number of strands and petals. The counts above are estimates.

## Gaps

- **Add-ons.** LoopTools (free; a Blender extension since 4.2) is used once, `LoopTools > Circle` (the operator panel
  reads Circle), to make the ponytail scalp round [14:16:05, 14:16:11]. Built-in route:
  `bpy.ops.mesh.primitive_circle_add(fill_type='NGON')`. Everything else is built in.
- **Curve sculpt brushes** (Comb, Pinch, Slide and the rest) are not available to you. Flow functions plus
  `reshape_guides` reach the same shapes but without the look-and-nudge loop the course relies on; expect several
  capture-and-correct rounds per part. This is the weakest point of the stage.
- **Texture painting the masks** is replaced by vertex groups read through `Density Mask`. A mask is then only as
  sharp as the scalp's vertex spacing; subdivide the scalp where a crisp edge matters.
- **Hair material: the chapter has none.** It sets only the viewport colour (black on the brows and main hair; the
  ponytail object is left light). The hair shader belongs to the next stage (course chapter 12, shading); add its
  material to each Curves object there.
- **Not shown in the video**: most of the main-hair, side-strand and ponytail guide placement is a time-lapse with
  music marked with a 5X speed badge [13:47:20 to 13:52:00, 14:08:10, 14:17:55]. The sheets show the result of that
  time-lapse (arcs of guides from the hairline rim to one point behind the head; about a dozen long guides on the
  ponytail disc) but guide counts and exact paths are not recorded; the right-side strand is described, not made;
  the lower-lash Density after thinning is not legible (2 500 000 is the copied value).
- **Ponytail viewport colour**: the video leaves the ponytail Curves object at the default light colour (white),
  unlike the black brows and main hair [14:23:00]; make it black for a consistent review capture.
- **Unsettled in the course**: for secondary clumps the narrator unticks Existing Guide Map while also linking
  Guide Index. `hair_tree` copies that. If secondary clumps do not appear, tick it on node `clump2` and compare.
- `Curl Hair Curves`, `Braid Hair Curves` and the other unused groups are named from the asset file but untested.
