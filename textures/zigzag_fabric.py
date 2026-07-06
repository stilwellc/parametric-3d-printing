"""zigzag_fabric.py — printed-fabric (zigzag textile) wall generator.

Builds a closed solid of revolution whose wall is a thin shell with a
per-print-layer alternating contour: M zigzag layers whose triangle
wave swings outward, then N straight (circular) layers, repeating, with
each successive zigzag band phase-shifted half a period so the bands
crisscross into diamonds. Printed with 1-2 perimeters and no infill,
the zigzag layers bridge in mid-air and leave open diamond windows —
a light, airy fabric-like wall (not a solid wall with surface texture).

Geometry is quantized to the print layer height (staircase rings), so
the slicer reproduces the exact zigzag/straight alternation. The
slicer layer height MUST match `layer_h` or the pattern smears.

Print settings for parts built with this module:
  2 perimeters, 0% infill, 0 top layers, ~4 bottom layers,
  vase/spiral mode OFF, fan 100%, outer wall <=60mm/s, no supports.

Reference example: zigzag_bowl.py (200mm catch-all bowl).
"""
import numpy as np
import trimesh


def tri01(x):
    """Triangle wave, period 1, range 0..1, peak at x=0.5."""
    x = np.asarray(x)
    return 1.0 - 2.0 * np.abs(x - np.floor(x) - 0.5)


def fabric_solid(profile_r, height, *,
                 shell_t=1.0,
                 floor_t=3.0,
                 solid_base_z=6.0,
                 layer_h=0.2,
                 zigzags_around=90,
                 zigzag_depth=2.0,
                 zigzag_layers=3,
                 straight_layers=2,
                 samples_per_zigzag=6):
    """Closed, watertight fabric-walled solid of revolution.

    profile_r      callable z (scalar mm) -> outer wall radius (mm);
                   the smooth silhouette the fabric pattern rides on.
    height         total height, mm. Flat bottom lands at z=0.
    shell_t        wall shell thickness, mm (2 perimeters at ~0.5mm).
    floor_t        solid floor slab thickness, mm.
    solid_base_z   smooth solid wall band before the pattern starts, mm.
    layer_h        print layer height, mm — MUST match the slicer.
    zigzags_around zigzag periods around the circumference. Keep the
                   half-period (pi*D/zigzags/2) under the material's
                   bridge limit; ~3-4mm is comfortable for PLA.
    zigzag_depth   outward swing of zigzag layers, mm (opening size).
    zigzag_layers  print layers per zigzag band.
    straight_layers print layers per straight band.

    Returns a trimesh.Trimesh. Callers should verify `is_watertight`
    and, after any boolean floor cuts, `len(tm.split()) == 1`.
    """
    n_theta = zigzags_around * samples_per_zigzag
    theta = np.linspace(0, 2 * np.pi, n_theta, endpoint=False)
    n_layers = int(round(height / layer_h))
    cycle = zigzag_layers + straight_layers

    def layer_contour(k):
        """Outer-wall radius array (n_theta,) for print layer k."""
        z_mid = (k + 0.5) * layer_h
        base_r = float(profile_r(min(z_mid, height)))
        if z_mid < solid_base_z:
            return np.full(n_theta, base_r)
        pk = k - int(solid_base_z / layer_h)   # layers since pattern start
        if pk % cycle >= zigzag_layers:        # straight band
            return np.full(n_theta, base_r)
        band = pk // cycle
        phase = 0.5 * (band % 2)               # crisscross: half-period shift
        u = zigzags_around * theta / (2 * np.pi) + phase
        # 0.02mm standoff keeps zigzag valleys from exactly coinciding
        # with straight rings — merged duplicate vertices would pinch
        # the mesh non-manifold. Invisible to the slicer.
        return base_r + 0.02 + zigzag_depth * tri01(u)

    # staircase rings: outer up, rim, inner down, floor. Coincident
    # consecutive rings (constant-radius profiles) are skipped — their
    # zero-area quads would break manifoldness after vertex merging.
    rings = []   # list of (z, r_array)

    def add_ring(z, r):
        if rings and abs(rings[-1][0] - z) < 1e-9 \
                and np.allclose(rings[-1][1], r):
            return
        rings.append((z, r))

    for k in range(n_layers):
        r = layer_contour(k)
        add_ring(k * layer_h, r)
        add_ring((k + 1) * layer_h, r)
    for k in range(n_layers - 1, -1, -1):
        z_mid = (k + 0.5) * layer_h
        if z_mid < floor_t:
            break
        r = layer_contour(k) - shell_t
        add_ring((k + 1) * layer_h, r)
        add_ring(k * layer_h, r)
    # land inner wall on the floor (skip if the staircase already ends there)
    if abs(rings[-1][0] - floor_t) > 1e-9:
        add_ring(floor_t, rings[-1][1])

    n_rings = len(rings)
    prof_z = np.array([z for z, _ in rings])
    R = np.stack([r for _, r in rings])            # (n_rings, n_theta)
    X = R * np.cos(theta)[None, :]
    Y = R * np.sin(theta)[None, :]
    Z = np.broadcast_to(prof_z[:, None], R.shape)

    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    c_bot = len(verts)
    c_top = len(verts) + 1
    verts = np.vstack([verts, [[0, 0, 0], [0, 0, floor_t]]])

    faces = []
    idx = lambda i, j: i * n_theta + (j % n_theta)
    for i in range(n_rings - 1):
        for j in range(n_theta):
            a, b = idx(i, j), idx(i, j + 1)
            c, d = idx(i + 1, j), idx(i + 1, j + 1)
            faces.append([a, b, c])
            faces.append([b, d, c])
    for j in range(n_theta):
        faces.append([idx(0, j + 1), idx(0, j), c_bot])                     # bottom cap
        faces.append([idx(n_rings - 1, j), idx(n_rings - 1, j + 1), c_top])  # floor

    tm = trimesh.Trimesh(vertices=verts, faces=np.array(faces), process=True)
    trimesh.repair.fix_normals(tm)
    if tm.volume < 0:
        tm.invert()
    return tm
