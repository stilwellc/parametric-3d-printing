"""Zigzag fabric bowl — procedural parametric mesh.

Bulged-barrel bowl whose wall is a thin shell with a per-layer
alternating contour: N straight (circular) layers, then M zigzag layers
whose triangle wave swings outward off the layers below. Printed with
1-2 perimeters and no infill, the zigzag layers bridge in mid-air and
leave open diamond windows — a light, airy "printed fabric" wall.

Geometry is quantized to the print layer height (staircase rings) so
the slicer reproduces the exact zigzag/straight alternation.

Print orientation: flat base on bed, no supports.
Print settings: 2 perimeters, 0% infill, no top layers, 4 bottom layers.
Seam: Bambu scarf/random — hidden in the zigzag.
"""
import numpy as np
import trimesh

from zigzag_fabric import fabric_solid

# ============================================================
# PARAMETERS - Edit these to customize the model
# All dimensions in mm.
# ============================================================
# Overall dimensions
max_diameter   = 200.0   # mm - widest point of the bulge
height         = 60.0    # mm - total height
base_diameter  = 156.0   # mm - flat bottom (keeps bulge <45deg overhang)
rim_diameter   = 186.0   # mm - outer diameter at the top rim
bulge_z_frac   = 0.52    # 0-1 - where the widest point sits

# Wall and structural
shell_t        = 1.0     # mm - wall shell thickness (2 perimeters @ 0.5mm)
floor_t        = 3.0     # mm - solid floor slab
solid_base_z   = 6.0     # mm - smooth solid wall band before pattern starts

# Fabric pattern
layer_h        = 0.2     # mm - MUST match slicer layer height
zigzags_around = 90      # zigzag periods around the circumference
zigzag_depth   = 2.0     # mm - outward swing of zigzag layers
zigzag_layers  = 3       # layers per zigzag band
straight_layers = 2      # layers per straight band
# each successive zigzag band shifts half a period -> crisscross diamonds

# Floor pattern — concentric rings of diamond cutouts, alternate rings
# rotated half a step so they crisscross like the wall bands.
# (radius mm, hole count) per ring; keep outermost radius + diag/2 well
# inside the inner wall (~80mm at floor level) for a solid margin.
floor_diamond_rings = [(20.0, 15), (27.0, 20), (34.0, 26), (42.0, 32),
                       (50.0, 38), (58.0, 44), (66.0, 50)]
diamond_diag        = 5.0     # mm - point-to-point size of each cutout

# Floor text — the word cut clean through the center of the floor, read
# from inside the bowl. Letters with enclosed counters (e, p) get thin
# vertical stencil bridges so no piece falls out.
floor_text        = "empty"
floor_text_width  = 27.0    # mm - overall width of the word
floor_text_font   = "Arial Rounded MT Bold"
stencil_bridge_w  = 0.8     # mm - width of the stencil bridge tabs

# Mesh resolution
samples_per_zigzag = 6   # angular samples per zigzag period

R_max  = max_diameter / 2
R_base = base_diameter / 2
R_rim  = rim_diameter / 2
z_peak = bulge_z_frac * height

# ============================================================
# PROFILE  r(z) — smooth silhouette the pattern rides on
# ============================================================
def r_outer(z):
    z = np.asarray(z, dtype=float)
    r = np.empty_like(z)
    lo = z <= z_peak
    t = np.clip(z[lo] / z_peak, 0, 1)
    h00 = 2*t**3 - 3*t**2 + 1
    h10 = t**3 - 2*t**2 + t
    h01 = -2*t**3 + 3*t**2
    r[lo] = h00 * R_base + h10 * z_peak * 1.0 + h01 * R_max
    t = np.clip((z[~lo] - z_peak) / (height - z_peak), 0, 1)
    r[~lo] = R_rim + (R_max - R_rim) * np.cos(t * np.pi / 2)
    return float(r) if r.shape == () else r  # scalar in, scalar out

# ============================================================
# MODEL — fabric wall via the reusable zigzag_fabric module
# ============================================================
tm = fabric_solid(
    r_outer, height,
    shell_t=shell_t, floor_t=floor_t, solid_base_z=solid_base_z,
    layer_h=layer_h, zigzags_around=zigzags_around,
    zigzag_depth=zigzag_depth, zigzag_layers=zigzag_layers,
    straight_layers=straight_layers,
    samples_per_zigzag=samples_per_zigzag)
n_layers = int(round(height / layer_h))

# ============================================================
# FLOOR PATTERN — diamond ring cutouts + stencil text cut
# ============================================================
def text_cut_region():
    """The floor word as 2D cut polygons with stencil bridges."""
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    from shapely import affinity

    path = TextPath((0, 0), floor_text, size=20,
                    prop=FontProperties(family=floor_text_font))
    rings = [r for r in path.to_polygons() if len(r) > 2]
    # even-odd containment: a ring inside an odd number of rings is a hole
    polys = [Polygon(r) for r in rings]
    letters = []
    for i, p in enumerate(polys):
        depth = sum(1 for j, q in enumerate(polys)
                    if i != j and q.contains(p))
        if depth % 2 == 0:
            holes = [r for j, r in enumerate(rings) if j != i
                     and polys[j].within(p)]
            letters.append(Polygon(rings[i], holes))

    word = unary_union(letters)
    # scale to target width, center on origin
    minx, miny, maxx, maxy = word.bounds
    s = floor_text_width / (maxx - minx)
    word = affinity.scale(word, xfact=s, yfact=s, origin=(0, 0))
    word = affinity.translate(word,
        xoff=-(word.bounds[0] + word.bounds[2]) / 2,
        yoff=-(word.bounds[1] + word.bounds[3]) / 2)

    # stencil bridges: vertical tab through each enclosed counter
    bridges = []
    for letter in getattr(word, "geoms", [word]):
        for hole in letter.interiors:
            hx = hole.centroid.x
            b = letter.bounds
            bridges.append(box(hx - stencil_bridge_w / 2, b[1] - 1,
                               hx + stencil_bridge_w / 2, b[3] + 1))
    cut = word.difference(unary_union(bridges)) if bridges else word
    n_holes = sum(len(l.interiors) for l in getattr(word, "geoms", [word]))
    print(f"Floor text '{floor_text}': {n_holes} counters bridged")
    return list(cut.geoms) if isinstance(cut, MultiPolygon) else [cut]

if floor_diamond_rings or floor_text:
    import manifold3d as m3d

    def to_manifold(t):
        return m3d.Manifold(m3d.Mesh(
            vert_properties=np.array(t.vertices, dtype=np.float32),
            tri_verts=np.array(t.faces, dtype=np.int32)))

    def diamond_cutter(cx, cy, angle):
        """Vertical diamond prism through the floor at (cx, cy)."""
        side = diamond_diag / np.sqrt(2)
        cut = m3d.Manifold.cube([side, side, floor_t + 2], center=True)
        cut = cut.rotate([0, 0, 45 + np.degrees(angle)])
        return cut.translate([cx, cy, (floor_t + 2) / 2 - 1])

    cutters = []
    for ring_i, (ring_r, count) in enumerate(floor_diamond_rings):
        offset = (np.pi / count) * (ring_i % 2)   # crisscross alternate rings
        for h in range(count):
            a = 2 * np.pi * h / count + offset
            cutters.append(diamond_cutter(ring_r * np.cos(a),
                                          ring_r * np.sin(a), a))
    n_diamonds = len(cutters)

    if floor_text:
        for poly in text_cut_region():
            prism = trimesh.creation.extrude_polygon(poly, height=floor_t + 2)
            prism.apply_translation([0, 0, -1])
            cutters.append(to_manifold(prism))

    cutter_m = m3d.Manifold.batch_boolean(cutters, m3d.OpType.Add)
    result_m = to_manifold(tm) - cutter_m
    out = result_m.to_mesh()
    tm = trimesh.Trimesh(
        vertices=np.array(out.vert_properties, dtype=np.float64),
        faces=np.array(out.tri_verts, dtype=np.int64), process=True)
    print(f"Floor pattern: {n_diamonds} diamonds + text, "
          f"genus={result_m.genus()}, status={result_m.status()}")
    n_bodies = len(tm.split(only_watertight=False))
    print(f"Bodies after cut: {n_bodies} (must be 1 — no loose islands)")

# ============================================================
# CHECKS + EXPORT
# ============================================================
print(f"Watertight: {tm.is_watertight}")
print(f"Bounding box: {tm.extents[0]:.1f} x {tm.extents[1]:.1f} x {tm.extents[2]:.1f} mm")
print(f"Volume: {tm.volume/1000:.0f} cm^3, faces: {len(tm.faces)}")
print(f"Layers: {n_layers}, pattern cycle: {zigzag_layers}zz + {straight_layers}st")
half_period_mm = np.pi * max_diameter / zigzags_around / 2
print(f"Unsupported zigzag half-period: ~{half_period_mm:.1f}mm (PLA bridges fine <20mm)")

tm.export("zigzag_bowl.stl")
print("Exported: zigzag_bowl.stl")
