"""Draft-and-carve the face from the drawing (run inside Blender through the bridge).

Every number below was read off the 2K FRONT / LEFT drawings on a millimetre grid, registered on the head
silhouette, in world metres on a 1.7 m character.  The face is kept symmetric about x = 0.
"""
import bpy, bmesh, math, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
C, D = bpy.context, bpy.data

P = dict(
    # eye: the drawn opening relative to the eye centre (u = |x| - EYE_X); the eye is carved into the face
    # surface (anime method: no marble eyeball), with a thin lens 1.2 mm behind the face inside the opening
    EYE_X=0.047, EYE_Z=1.479,
    U_IN=-0.017, Z_IN=1.480, U_OUT=0.019, Z_OUT=1.478, H_UP=0.0105, H_LO=0.0132,
    LASH_MID=0.0036, LASH_END=0.0012,
    IRIS_W=0.022, IRIS_H=0.026, IRIS_DZ=0.0,
    # brow arch (|x|, z) and thickness
    BROW=[(0.016, 1.5010), (0.025, 1.5055), (0.035, 1.5090), (0.044, 1.5100), (0.053, 1.5085), (0.062, 1.5055), (0.068, 1.5030)],
    BROW_T=[0.0020, 0.0026, 0.0030, 0.0030, 0.0028, 0.0022, 0.0014],
    # centre-line profile (z, y) from LEFT, chin to brow
    PROFILE=[(1.380, -0.1080), (1.390, -0.1130), (1.400, -0.1200), (1.410, -0.1235),
             (1.418, -0.1255), (1.423, -0.1285), (1.428, -0.1310), (1.435, -0.1340), (1.440, -0.1400),
             (1.444, -0.1380), (1.449, -0.1350), (1.458, -0.1290), (1.470, -0.1255), (1.482, -0.1255),
             (1.494, -0.1280), (1.500, -0.1290)],
    NOSE_BAND=(1.428, 1.458),
    # face half-width (front half) from the FRONT jaw line, and the chin bottom (FRONT 1.377, LEFT 1.368)
    JAW=[(1.382, 0.031), (1.390, 0.053), (1.403, 0.068), (1.415, 0.072), (1.432, 0.0755)],
    CHIN_Z=1.372,
    NOSTRIL_X=0.005, NOSTRIL_Z=1.438, MOUTH_Z=1.409, MOUTH_HW=0.021, LOWLIP_Z=1.399, LOWLIP_HW=0.008,
    EAR_DZ=-0.008, EAR_DX=-0.008,
    # LEFT: front edge of the side hair (temple diagonal down to just in front of the ear)
    SIDE_HAIR=[(1.43, -0.030), (1.44, -0.030), (1.458, -0.047), (1.47, -0.062), (1.48, -0.073),
               (1.494, -0.088), (1.505, -0.095), (1.512, -0.110), (1.520, -0.400)],
)

def world_co(o):
    me = o.data; co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get("co", co)
    mw = np.array(o.matrix_world); return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3], mw

def set_world_co(o, w, mw):
    inv = np.linalg.inv(mw); co = w @ inv[:3, :3].T + inv[:3, 3]
    o.data.vertices.foreach_set("co", co.astype(np.float32).ravel()); o.data.update()

def apply_subsurf(o, levels):
    s = o.modifiers.new("Sub", "SUBSURF"); s.levels = levels; s.render_levels = levels
    with C.temp_override(object=o, active_object=o, selected_objects=[o]):
        bpy.ops.object.modifier_apply(modifier=s.name)
    for p in o.data.polygons: p.use_smooth = True

def neighbours(me):
    e = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get("vertices", e); return e.reshape(-1, 2)

def diffuse(field, edges, n, iters):
    """Smooth a per-vertex scalar field over the mesh (mean of neighbours), so moves never leave steps."""
    f = field.astype(np.float64).copy(); deg = np.maximum(np.bincount(edges.ravel(), minlength=n), 1).astype(float)
    for _ in range(iters):
        acc = np.bincount(edges[:, 0], weights=f[edges[:, 1]], minlength=n) + np.bincount(edges[:, 1], weights=f[edges[:, 0]], minlength=n)
        f = 0.5 * f + 0.5 * acc / deg
    return f

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0); return t * t * (3 - 2 * t)

def profile_at(o, zs):
    dg = C.evaluated_depsgraph_get(); bvh = BVHTree.FromObject(o, dg); inv = o.matrix_world.inverted(); out = []
    for zz in zs:
        loc = bvh.ray_cast(inv @ Vector((0, -1, zz)), (inv.to_3x3() @ Vector((0, 1, 0))).normalized())[0]
        out.append((o.matrix_world @ loc).y if loc else np.nan)
    return np.array(out)

def fit_profile(W, E, n, target_y, sig_nose, sig_wide, iters, clip):
    """centre-line depth -> drawn profile, spread sideways with a gaussian (narrow at the nose), smoothed over the mesh"""
    cur = profile_at(hd, pz)
    delta = np.where(np.isnan(cur), 0.0, np.clip(target_y - cur, -clip, clip))
    z = W[:, 2]
    dz = np.interp(z, pz, delta, left=0.0, right=0.0) * smoothstep(pz[0] - 0.012, pz[0], z) * (1 - smoothstep(pz[-1], pz[-1] + 0.012, z))
    nb0, nb1 = P["NOSE_BAND"]
    sig = np.where((z > nb0) & (z < nb1), sig_nose, sig_wide)
    sig = diffuse(sig, E, n, iters // 2 + 2)
    W[:, 1] += diffuse(dz * np.exp(-(W[:, 0] / sig) ** 2) * smoothstep(-0.03, -0.07, W[:, 1]), E, n, iters)
    return cur

def fit_jaw(W, E, n, iters):
    """front-half face width per height -> drawn jaw line"""
    jz = np.array([j[0] for j in P["JAW"]]); jt = np.array([j[1] for j in P["JAW"]]); cw = []
    for zz in jz:
        m = (np.abs(W[:, 2] - zz) < 0.003) & (W[:, 1] < -0.02); cw.append(np.abs(W[m, 0]).max())
    s = np.clip(jt / np.array(cw), 0.8, 1.5)
    sz = np.interp(W[:, 2], np.r_[jz[0] - 0.012, jz, jz[-1] + 0.02], np.r_[s[0], s, 1.0])
    W[:, 0] += diffuse(W[:, 0] * (sz - 1) * smoothstep(0.02, -0.04, W[:, 1]), E, n, iters)
    return dict(zip(jz.tolist(), np.round(s, 3).tolist()))

def fit_chin(W, E, n, iters):
    m = (np.abs(W[:, 0]) < 0.012) & (W[:, 1] < -0.04); zc = W[m, 2].min()
    k = (1.41 - P["CHIN_Z"]) / (1.41 - zc)
    dz = np.where(W[:, 2] < 1.41, (1.41 - (1.41 - W[:, 2]) * k) - W[:, 2], 0.0) * smoothstep(0.0, -0.05, W[:, 1])
    W[:, 2] += diffuse(dz, E, n, iters); return round(float(zc), 4)

hd = D.objects["BLK_head"]
pz = np.array([p[0] for p in P["PROFILE"]]); py = np.array([p[1] for p in P["PROFILE"]])
nb0, nb1 = P["NOSE_BAND"]; nose = (pz > nb0) & (pz < nb1)
py_wide = py.copy(); py_wide[nose] = np.interp(pz[nose], pz[~nose], py[~nose])   # coarse: no nose yet
report = {}

# ---- 1. coarse mesh: proportions first (profile without the nose, chin, jaw), smooth by construction ----
assert len(hd.data.vertices) < 10000, "start from the coarse blockout head (before any face sculpt)"
W, MW = world_co(hd); n = len(W); E = neighbours(hd.data)
report["chin_before"] = fit_chin(W, E, n, 3); set_world_co(hd, W, MW)
report["profile_before"] = dict(zip(pz.round(3).tolist(), np.round(fit_profile(W, E, n, py_wide, 0.03, 0.032, 3, 0.03), 4).tolist()))
set_world_co(hd, W, MW)
report["jaw_coarse"] = [fit_jaw(W, E, n, 3) for _ in range(2)]; set_world_co(hd, W, MW)

# ---- 2. subdivide, then fine residual passes (nose included), heavily smoothed ----
apply_subsurf(hd, 3)
W, MW = world_co(hd); n = len(W); E = neighbours(hd.data)
report["head_verts"] = n
for _ in range(2):
    fit_profile(W, E, n, py, 0.011, 0.03, 60, 0.025); set_world_co(hd, W, MW)
    report.setdefault("jaw_fine", []).append(fit_jaw(W, E, n, 60)); set_world_co(hd, W, MW)
report["profile_after"] = dict(zip(pz.round(3).tolist(), np.round(profile_at(hd, pz), 4).tolist()))

# ---- 3. eye zone: relax the blockout socket into a smooth membrane (positions, so no folded socket walls) ----
deg = np.maximum(np.bincount(E.ravel(), minlength=n), 1).astype(float)
ax = np.abs(W[:, 0])
zone = ((ax - P["EYE_X"]) / 0.034) ** 2 + ((W[:, 2] - (P["EYE_Z"] + 0.002)) / 0.028) ** 2
wz = (1 - smoothstep(0.8, 1.3, zone)) * smoothstep(-0.05, -0.08, W[:, 1])
for _ in range(150):
    avg = np.stack([np.bincount(E[:, 0], weights=W[E[:, 1], k], minlength=n) + np.bincount(E[:, 1], weights=W[E[:, 0], k], minlength=n) for k in range(3)], 1) / deg[:, None]
    W += 0.5 * wz[:, None] * (avg - W)

# ---- 4. the drawn opening as a 2D outline in (|x|, z) and a continuous signed distance to it ----
uc = 0.5 * (P["U_IN"] + P["U_OUT"]); uh = 0.5 * (P["U_OUT"] - P["U_IN"])
def curves(tt):
    zc = P["Z_IN"] + (P["Z_OUT"] - P["Z_IN"]) * (tt + 1) / 2
    return zc, zc + P["H_UP"] * (1 - tt ** 2) ** 0.55 * (1 - 0.15 * tt), zc - P["H_LO"] * (1 - tt ** 2) ** 0.75
ts = np.linspace(-1, 1, 301); zc_s, zU_s, zL_s = curves(ts); us = P["EYE_X"] + uc + uh * ts
kd2 = KDTree(2 * len(ts))
for i, (uu, zz) in enumerate(list(zip(us, zU_s)) + list(zip(us, zL_s))): kd2.insert((uu, 0.0, zz), i)
kd2.balance()
ax = np.abs(W[:, 0]); z = W[:, 2]
t = (ax - P["EYE_X"] - uc) / uh; tc = np.clip(t, -1, 1)
zc, zU, zL = curves(tc)
act = np.nonzero(wz > 0)[0]
sd = np.full(n, 1.0)
for i in act: sd[i] = kd2.find((ax[i], 0.0, z[i]))[2]
inside = (np.abs(t) <= 1) & (z > zL) & (z < zU); sd = np.where(inside, -sd, sd)
lash = P["LASH_END"] + (P["LASH_MID"] - P["LASH_END"]) * (1 - tc ** 2) ** 0.4 + 0.0010 * smoothstep(0.5, 1.0, tc)
m_up = smoothstep(-0.0015, 0.0015, z - zc)
# push back (+y) inside the opening; thick lash rim proud above it with a crisp lower edge; crease groove; soft lower lid
h_in = 0.0028 * smoothstep(0.0, 0.0008, -sd)
rim = -0.0024 * smoothstep(0.0, 0.0008, sd) * (1 - smoothstep(lash * 0.6, lash + 0.0014, sd))
crease = 0.0005 * np.exp(-((sd - (lash + 0.0022)) / 0.0006) ** 2) * smoothstep(-0.8, -0.6, tc) * (1 - smoothstep(0.85, 1.0, tc))
h_lo = -0.0007 * smoothstep(0.0, 0.0006, sd) * (1 - smoothstep(0.0015, 0.0045, sd))
h = np.where(sd < 0, h_in, m_up * (rim + crease) + (1 - m_up) * h_lo)
# outer lash flick: a raised stroke continuing past the outer corner, drooping 4 mm
f0 = np.array([P["EYE_X"] + P["U_OUT"] - 0.001, P["Z_OUT"] + 0.001]); f1 = np.array([P["EYE_X"] + P["U_OUT"] + 0.005, P["Z_OUT"] - 0.004])
seg = f1 - f0; s_ = np.clip(((ax - f0[0]) * seg[0] + (z - f0[1]) * seg[1]) / (seg @ seg), 0, 1)
df = np.hypot(ax - (f0[0] + s_ * seg[0]), z - (f0[1] + s_ * seg[1]))
h += -0.0018 * np.exp(-(df / 0.0008) ** 2) * (1 - 0.6 * s_) * smoothstep(0.0, 0.0005, sd)
h *= (wz > 0)
# lens: the membrane inside the opening (+2.5 mm margin), 1.2 mm back, is the eye surface the iris sits on
lens_sel = (sd < 0.0025) & (wz > 0.5)
eye = D.objects["BLK_eye"]; mats = list(eye.data.materials)
set_world_co(hd, W, MW)
bm = bmesh.new(); bm.from_mesh(hd.data); bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[f for f in bm.faces if not all(lens_sel[v.index] for v in f.verts)], context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
hmw = hd.matrix_world; emw_inv = eye.matrix_world.inverted()
for v in bm.verts: v.co = emw_inv @ ((hmw @ v.co) + Vector((0, 0.0012, 0)))
bm.to_mesh(eye.data); bm.free()
eye.data.materials.clear(); [eye.data.materials.append(m) for m in mats]
for p in eye.data.polygons: p.use_smooth = True
s = eye.modifiers.new("Sol", "SOLIDIFY"); s.thickness = 0.0008; s.offset = -1.0
with C.temp_override(object=eye, active_object=eye, selected_objects=[eye]):
    bpy.ops.object.modifier_apply(modifier=s.name)
W[:, 1] += h
report["eye_carved_verts"] = int((np.abs(h) > 1e-5).sum()); report["lens_faces"] = len(eye.data.polygons)

# ---- 5. nostrils and the mouth line (Ghibli: a line, not lips) ----
x = W[:, 0]; z = W[:, 2]; fr = smoothstep(-0.09, -0.11, W[:, 1])
nost = np.exp(-((np.abs(x) - P["NOSTRIL_X"]) / 0.0018) ** 2) * np.exp(-((z - P["NOSTRIL_Z"]) / 0.0016) ** 2) * fr
W[:, 1] += 0.0011 * nost; W[:, 2] += 0.0007 * nost
xm = np.clip(np.abs(x) / P["MOUTH_HW"], 0, 2)
mz = P["MOUTH_Z"] + 0.0008 * xm ** 2
mouth = np.exp(-((z - mz) / 0.0007) ** 2) * (1 - smoothstep(0.85, 1.05, xm)) * fr
W[:, 1] += 0.0009 * mouth
low_lip = np.exp(-((z - P["LOWLIP_Z"]) / 0.0006) ** 2) * (1 - smoothstep(0.8, 1.1, np.abs(x) / P["LOWLIP_HW"])) * fr
W[:, 1] += 0.0005 * low_lip
upper = np.exp(-((z - (P["MOUTH_Z"] + 0.004)) / 0.003) ** 2) * (1 - smoothstep(0.6, 1.1, xm)) * fr   # soft upper-lip plane
W[:, 1] -= 0.0006 * upper
set_world_co(hd, W, MW)

# ---- 6. brows: ridges along the drawn arch, projected onto the head ----
old = D.objects.get("BLK_brows"); bmats = list(old.data.materials) if old else []
if old: D.objects.remove(old, do_unlink=True)
dg = C.evaluated_depsgraph_get(); bvh = BVHTree.FromObject(hd, dg); inv = hd.matrix_world.inverted(); hmw = hd.matrix_world
bx_ = np.array([b[0] for b in P["BROW"]]); bz_ = np.array([b[1] for b in P["BROW"]]); bt_ = np.array(P["BROW_T"])
xs = np.linspace(bx_[0], bx_[-1], 40)
verts, faces = [], []
for sx in (1.0, -1.0):
    base = len(verts)
    for xi in xs:
        zi = np.interp(xi, bx_, bz_); ti = np.interp(xi, bx_, bt_)
        for k, (dzk, hk) in enumerate(((-0.5, 0.0001), (-0.25, 0.0009), (0.0, 0.0013), (0.25, 0.0009), (0.5, 0.0001))):
            o_ = inv @ Vector((sx * xi, -1.0, zi + dzk * ti)); hit = bvh.ray_cast(o_, (inv.to_3x3() @ Vector((0, 1, 0))).normalized())
            p = hmw @ (hit[0] + hit[1] * hk) if hit[0] else Vector((sx * xi, -0.12, zi))
            verts.append(tuple(p))
    for i in range(len(xs) - 1):
        for k in range(4):
            a = base + i * 5 + k; b = a + 5
            faces.append((a, b, b + 1, a + 1) if sx > 0 else (a, a + 1, b + 1, b))
me_b = D.meshes.new("BLK_brows"); me_b.from_pydata(verts, [], faces)
ob_b = D.objects.new("BLK_brows", me_b); C.scene.collection.objects.link(ob_b); ob_b.parent = D.objects.get("CHARACTER")
ob_b.matrix_parent_inverse = ob_b.parent.matrix_world.inverted() if ob_b.parent else ob_b.matrix_parent_inverse
s = ob_b.modifiers.new("Sol", "SOLIDIFY"); s.thickness = 0.0006; s.offset = -1.0
with C.temp_override(object=ob_b, active_object=ob_b, selected_objects=[ob_b]):
    bpy.ops.object.modifier_apply(modifier=s.name)
for p in me_b.polygons: p.use_smooth = True
for m in bmats: me_b.materials.append(m)

# ---- 7. iris discs on the lens (slightly raised rim, recessed pupil) ----
old = D.objects.get("BLK_iris")
if old: D.objects.remove(old, do_unlink=True)
dg = C.evaluated_depsgraph_get(); bvh_e = BVHTree.FromObject(eye, dg); einv = eye.matrix_world.inverted(); emw = eye.matrix_world
def lens_y(xw, zw):
    hit = bvh_e.ray_cast(einv @ Vector((xw, -1.0, zw)), (einv.to_3x3() @ Vector((0, 1, 0))).normalized())[0]
    return (emw @ hit).y if hit else None
verts, faces = [], []
R_, A_ = 14, 48
for sx in (1.0, -1.0):
    base = len(verts)
    for i in range(R_ + 1):
        rr = i / R_
        lift = 0.0002 + 0.00045 * smoothstep(0.55, 0.9, rr) * (1 - smoothstep(0.93, 1.0, rr)) - 0.0003 * (1 - smoothstep(0.0, 0.35, rr))
        for j in range(A_):
            a = 2 * math.pi * j / A_
            xa = P["EYE_X"] + rr * 0.5 * P["IRIS_W"] * math.cos(a); za = P["EYE_Z"] + P["IRIS_DZ"] + rr * 0.5 * P["IRIS_H"] * math.sin(a)
            yb = lens_y(sx * xa, za)
            if yb is None: yb = lens_y(sx * P["EYE_X"], P["EYE_Z"])   # under the lid rim: follow the lens centre depth
            verts.append((sx * xa, yb - lift, za))
    for i in range(R_):
        for j in range(A_):
            a = base + i * A_ + j; b = base + i * A_ + (j + 1) % A_; c = b + A_; d = a + A_
            faces.append((a, b, c, d) if sx < 0 else (a, d, c, b))
me_i = D.meshes.new("BLK_iris"); me_i.from_pydata(verts, [], faces)
ob_i = D.objects.new("BLK_iris", me_i); C.scene.collection.objects.link(ob_i); ob_i.parent = D.objects.get("CHARACTER")
ob_i.matrix_parent_inverse = ob_i.parent.matrix_world.inverted() if ob_i.parent else ob_i.matrix_parent_inverse
s = ob_i.modifiers.new("Sol", "SOLIDIFY"); s.thickness = 0.0003; s.offset = 1.0
with C.temp_override(object=ob_i, active_object=ob_i, selected_objects=[ob_i]):
    bpy.ops.object.modifier_apply(modifier=s.name)
for p in me_i.polygons: p.use_smooth = True

# ---- 8. lashes are the lid rim now; ears tucked down and in ----
old = D.objects.get("BLK_lashes")
if old: D.objects.remove(old, do_unlink=True)
ear = D.objects["BLK_ears"]; Wl, MWl = world_co(ear)
Wl[:, 2] += P["EAR_DZ"]; Wl[:, 0] += np.sign(Wl[:, 0]) * P["EAR_DX"]; set_world_co(ear, Wl, MWl)

# ---- 9. side hair: pack the front edge of the side locks back behind the drawn diagonal (back of hair untouched) ----
hz = np.array([h[0] for h in P["SIDE_HAIR"]]); hy = np.array([h[1] for h in P["SIDE_HAIR"]]); BAND = 0.02
zg = np.arange(1.30, 1.53, 0.002)
for name in ("Hair.Cap", "Hair.Fringe"):
    o = D.objects.get(name)
    if o is None: continue
    W, MW = world_co(o); y0 = W[:, 1].copy(); side = smoothstep(0.045, 0.065, np.abs(W[:, 0]))
    newy = y0.copy()
    for sgn in (1, -1):
        mine = (np.sign(W[:, 0]) == sgn) & (side > 0)
        yf = np.full(len(zg), np.nan)
        for i, zz in enumerate(zg):
            m = mine & (np.abs(W[:, 2] - zz) < 0.003)
            if m.any(): yf[i] = y0[m].min()
        ok = ~np.isnan(yf)
        if ok.sum() < 3: continue
        yf = np.interp(zg, zg[ok], yf[ok]); yf = np.convolve(np.pad(yf, 4, mode="edge"), np.ones(9) / 9, mode="valid")
        f = np.interp(W[mine, 2], zg, yf); L = np.interp(W[mine, 2], hz, hy, left=hy[0], right=-1.0)
        ys = y0[mine]; sq = (f < L) & (ys < L + BAND)
        ys2 = ys.copy(); ys2[sq] = L[sq] + (ys[sq] - f[sq]) / (L[sq] + BAND - f[sq]) * BAND
        newy[mine] = ys2
    E_h = neighbours(o.data); dy = diffuse((newy - y0) * side, E_h, len(y0), 20)
    W[:, 1] = y0 + dy; set_world_co(o, W, MW)
    report[name] = {"moved": int((np.abs(dy) > 1e-4).sum()), "max_move": round(float(np.abs(dy).max()), 4)}

report["eye"] = [P["EYE_X"], P["EYE_Z"]]
result = report
