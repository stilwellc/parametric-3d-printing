---
name: parametric-3d-printing
description: "Use this skill when the user wants to design a 3D-printable physical object they intend to manufacture. Triggers: any mention of '3D print', 'STL', 'parametric model', 'enclosure', 'bracket', 'mount', 'case', 'housing', 'CadQuery', 'OpenSCAD', or a specific FDM printer (Bambu Lab, Prusa, Ender); questions about print-friendly design, snap-fits, tolerances, or wall thickness; requests for functional parts like Arduino enclosures, cable organizers, wall mounts, adapters, or mechanical components; providing an existing STL file as a reference, for modification, or for inspiration. Also fires when the user describes a real physical object to make, provided the goal is to manufacture it. Do NOT use for: 3D rendering, animation, game assets, digital-only art, photogrammetry, sculpting, or any 3D work that is not heading toward a printer."
---

# Parametric 3D Printing with CadQuery

## Overview

This skill generates parametric 3D models using **CadQuery** (Python) and exports them as STL files ready for slicing. CadQuery is preferred because it installs via pip, has a Pythonic API, and handles complex geometry (fillets, chamfers, booleans, assemblies) better than alternatives.

## Setup

```bash
# CadQuery requires Python 3.10-3.12 (OCC kernel lacks 3.13+ wheels)
python3.12 -m venv .venv && source .venv/bin/activate

# Install CadQuery and preview dependencies
pip install cadquery trimesh pyrender Pillow
```

CadQuery uses the OpenCASCADE kernel under the hood. trimesh, pyrender, and Pillow are used for the preview-analyze-iterate loop. No display server is needed; everything renders headlessly via pyrender's offscreen backend.

**If CadQuery fails to install** (OCC kernel build errors), try:
```bash
# Option 1: Use conda (CadQuery's officially recommended method)
conda install -c cadquery -c conda-forge cadquery

# Option 2: Use the pre-built wheels
pip install cadquery --find-links https://github.com/CadQuery/CadQuery/releases
```

## Real-World Dimension Research

When designing objects that interface with real products (phones, chargers, PCBs, connectors, etc.), **use web search to find accurate dimensions** before writing any geometry code. Don't guess or use approximate values. Even 1-2mm off can make a part unusable.

**What to research:**
- Connector/port dimensions (USB-C: 8.4 x 2.6mm opening, Lightning, barrel jacks)
- Device dimensions (phone width/thickness, PCB footprints, charger puck diameters)
- Mounting hole patterns and screw sizes (M2.5, M3, etc.)
- Standard component specs (MagSafe puck: 56mm diameter, 5.6mm thick)
- Cable bend radii and strain relief requirements

**How to use it:**
1. Search for "[product] dimensions mm" or "[component] datasheet"
2. Cross-reference at least 2 sources when precision matters
3. Add the sourced dimensions as comments in the PARAMETERS section:
   ```python
   # MagSafe puck dimensions (source: Apple spec + iFixit teardown)
   puck_diameter = 56.0    # mm
   puck_thickness = 5.6    # mm
   ```
4. When in doubt, add 0.3-0.5mm clearance to external dimensions

This is especially important for: phone cases/stands, charger mounts, PCB enclosures, cable management, adapter fittings, and anything that clips onto or wraps around an existing product.

## STL Reference Mode

When the user provides an existing STL file — either to **modify** it or use it as **inspiration** — follow this workflow before writing any new geometry.

### Step 1: Identify the mode

Ask the user (or infer from context) which mode they're in:

- **Modify** — "make this taller", "add a hole here", "change the wall thickness": the goal is a new part that is functionally the same shape with targeted changes.
- **Inspire** — "I like the general shape but want my own version", "use this as a reference for dimensions": extract what's useful, then design fresh.

### Step 2: Analyze the reference STL

Run both the renderer and the geometry extractor:

```bash
# Render a multi-view preview so you can visually inspect the shape
python3 preview.py reference.stl reference_preview.png --views multi

# Extract geometry stats for dimension recovery
python3 - <<'EOF'
import trimesh, numpy as np

tm = trimesh.load("reference.stl", force="mesh")
bb = tm.bounding_box.bounds          # [[xmin,ymin,zmin],[xmax,ymax,zmax]]
ext = tm.extents                     # [xlen, ylen, zlen]
vol = tm.volume
centroid = tm.centroid

print(f"Bounding box (mm): {ext[0]:.2f} W  x  {ext[1]:.2f} D  x  {ext[2]:.2f} H")
print(f"Volume: {vol:.0f} mm³")
print(f"Centroid: {centroid}")
print(f"Watertight: {tm.is_watertight}")
print(f"Faces: {len(tm.faces)},  Vertices: {len(tm.vertices)}")

# Estimate wall thickness via convex hull fill ratio
hull_vol = tm.convex_hull.volume
fill_ratio = vol / hull_vol
print(f"Fill ratio (vol/hull): {fill_ratio:.2f}  ({'thin-walled' if fill_ratio < 0.4 else 'solid'})")
EOF
```

**View the preview image** to understand the shape. Make note of:
- Overall form (box, cylinder, curved shell, assembly…)
- Visible features (holes, slots, bosses, snap tabs, ribs)
- Which face is the print bed (usually the largest flat face at Z=0)
- Any asymmetry or chirality

### Step 3: Recover parameters from geometry

Use trimesh to probe specific features — don't guess:

```python
import trimesh, numpy as np

tm = trimesh.load("reference.stl", force="mesh")

# Find all unique Z heights (good for detecting floors, ledges, snap features)
unique_z = np.unique(np.round(tm.vertices[:,2], 1))
print("Z heights:", unique_z[:20])   # cap at 20 to avoid noise

# Find approximate hole centers by clustering vertices near a given Z plane
z_plane = 2.0   # e.g. floor level
near = tm.vertices[np.abs(tm.vertices[:,2] - z_plane) < 0.3]
# Then use scipy or simple min/max to identify hole positions

# Face normal histogram — reveals dominant flat faces
normals = tm.face_normals
for axis, label in [([0,0,1],"top"), ([0,0,-1],"bottom"), ([1,0,0],"+X"), ([0,1,0],"+Y")]:
    pct = np.mean(np.dot(normals, axis) > 0.95) * 100
    print(f"{label}: {pct:.1f}% of faces")
```

Add recovered values as comments in the PARAMETERS block:
```python
# Recovered from reference STL (reference.stl)
width  = 62.4   # mm — bounding box X
depth  = 38.0   # mm — bounding box Y
height = 22.5   # mm — bounding box Z
wall   = 2.1    # mm — estimated from fill ratio
```

### Step 4: Branch by mode

**Modify mode:**
1. Recover all key parameters from the reference (Step 3 above)
2. Ask the user to confirm the recovered dimensions before writing code
3. Rebuild the part in CadQuery using those parameters — do NOT try to import the STL directly; rebuild it from scratch as a parametric model
4. Apply the requested changes on top of the rebuilt baseline
5. Show a side-by-side comparison: reference_preview.png + new model preview

**Inspire mode:**
1. Extract only the dimensions and proportions that are relevant to the user's stated goal
2. Describe what you're borrowing ("I'll use the ~62mm width and the 4-hole mounting pattern from the reference")
3. Design the new part freely, referencing those values in PARAMETERS with attribution comments
4. You are not obligated to replicate features the user didn't ask for

### Step 5: Note what was NOT recovered

STL is a surface mesh — it contains no feature history, parametric intent, internal structure, or material. Warn the user if:
- The reference has complex organic/sculpted surfaces that are hard to reconstruct exactly
- Wall thickness is ambiguous (open mesh, non-watertight)
- The reference is very high-poly (>100k faces) — recovery will be approximate

### Reference STL in Requirements Gathering

When the user provides a reference STL, add these questions to the normal requirements flow:

- **What do you want to change?** (specific features, dimensions, functionality) — get a clear diff from the reference
- **Is the reference the right size, or do you want to rescale?**
- **Should the output be compatible/mate with the original, or is it a standalone redesign?**

---

## STL Overhang Fix Mode

When the user has an existing STL that **fails to print due to overhangs** and wants the geometry fixed (not replaced with slicer supports), use this workflow to surgically fill the gap between overhanging surfaces and the bed.

### When to use this mode

Triggers: "keeps failing at the same spot", "PETG/ASA won't bridge this", "overhang keeps drooping", "can you fill the gap under the overhang", or any request to make an existing STL print without supports.

**Do NOT remove any original geometry.** Only add fill material below overhanging faces.

### Step 1: Identify print orientation and bed axis

```python
import trimesh, numpy as np

tm = trimesh.load("model.stl", force="mesh")
normals = tm.face_normals

# Find the largest flat face — that's the print bed face
for axis, label in [([1,0,0],"+X"), ([-1,0,0],"-X"), ([0,1,0],"+Y"),
                    ([0,-1,0],"-Y"), ([0,0,1],"+Z"), ([0,0,-1],"-Z")]:
    pct = np.mean(np.dot(normals, axis) > 0.95) * 100
    print(f"{label}: {pct:.1f}% of faces")
# The dominant axis = bed face. x_min/y_min/z_min along that axis = bed level.
```

Confirm with the user which face goes on the bed. The **print height axis** is perpendicular to the bed face (e.g., if mounting plate is -X face, print height = +X direction, bed = x_min).

### Step 2: Map the full overhang surface with a 2D ray-cast ceiling grid

Cast rays upward (in the print height direction) at a dense 2D grid across the other two axes. For each grid point, record the lowest downward-facing surface hit — this is the "ceiling" the fill must reach.

```python
# Example: print height = +X, bed at x_min, scanning Y/Z plane
y_steps = np.linspace(y_min + 2, y_max - 2, 50)
z_steps = np.linspace(z_min - 5, z_max + 5, 60)

ray_origins, ray_yz = [], []
for y in y_steps:
    for z in z_steps:
        ray_origins.append([x_min + 0.5, y, z])
ray_origins = np.array(ray_origins)
ray_dirs = np.array([[1, 0, 0]] * len(ray_origins))

# Install rtree first: pip install rtree
locs, ray_idx, face_idx = tm.ray.intersects_location(
    ray_origins, ray_dirs, multiple_hits=True)

dot_up = tm.face_normals[:, 0]  # component along print-height axis
x_cap = x_min + 35.0  # cap: don't go higher than 35mm above bed

NY, NZ = len(y_steps), len(z_steps)
grid_h = np.full((NY, NZ), np.nan)

for loc, ri, fi in zip(locs, ray_idx, face_idx):
    x = loc[0]
    if dot_up[fi] < -0.05 and x > x_min + 1.0 and x <= x_cap:
        iy, iz = ri // NZ, ri % NZ
        if np.isnan(grid_h[iy, iz]) or x < grid_h[iy, iz]:
            grid_h[iy, iz] = x
```

**Visualize the ceiling map** before building fill — it reveals the full crescent/arc shape of the overhang:

```python
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(12, 8))
im = ax.pcolormesh(z_steps, y_steps, grid_h - x_min, cmap='hot', vmin=0, vmax=35)
plt.colorbar(im, ax=ax, label='Height above bed (mm)')
ax.set_xlabel('Z'); ax.set_ylabel('Y')
ax.set_title('Ceiling map — colored = fill needed, white = no overhang')
plt.savefig('ceiling_map.png', dpi=120, bbox_inches='tight')
```

Show this map to the user and confirm the overhang region looks right before building fill.

### Step 3: Build the fill and boolean-union it into the model

Use **manifold3d** to create per-cell watertight boxes (one per valid grid cell, with exact ceiling height), batch-union them into a single fill solid, then boolean-union the fill with the original mesh. This produces one merged body that every slicer unambiguously treats as solid.

**Why not a terrain mesh or concatenated boxes?** Terrain meshes have open topology at the crescent boundary — slicers can't determine inside/outside. Concatenated separate boxes trigger even-odd winding rules in some slicers, marking the fill as void. The manifold3d union avoids both issues.

```python
import manifold3d as m3d
import struct

# pip install manifold3d rtree

NY, NZ = len(y_steps), len(z_steps)
dy = y_steps[1] - y_steps[0]
dz = z_steps[1] - z_steps[0]

# One watertight box per valid cell — exact ceiling height, 2% Y/Z overlap
# so adjacent boxes definitely intersect (avoids touch-face precision errors)
boxes = []
for iy in range(NY):
    for iz in range(NZ):
        h = grid_h[iy, iz]
        if np.isnan(h):
            continue
        x_size = h - x_min
        if x_size < 0.3:
            continue
        box = m3d.Manifold.cube([x_size, dy * 1.02, dz * 1.02], center=False)
        box = box.translate([x_min,
                             y_steps[iy] - (dy * 1.02) / 2,
                             z_steps[iz] - (dz * 1.02) / 2])
        boxes.append(box)

# Batch union all fill boxes → single fill solid
fill_m = m3d.Manifold.batch_boolean(boxes, m3d.OpType.Add)
print(f"Fill: genus={fill_m.genus()}, tris={fill_m.num_tri()}")

# Convert original mesh to manifold (repairs non-manifold edges automatically)
verts_orig = np.array(tm.vertices, dtype=np.float32)
faces_orig = np.array(tm.faces, dtype=np.int32)
original_m = m3d.Manifold(m3d.Mesh(vert_properties=verts_orig, tri_verts=faces_orig))
print(f"Original: genus={original_m.genus()}, tris={original_m.num_tri()}")

# Boolean union → one merged body
result_m = original_m + fill_m
print(f"Result: genus={result_m.genus()}, tris={result_m.num_tri()}, vol={result_m.volume():.0f} mm³")

# Write binary STL directly from manifold3d data
mesh_out = result_m.to_mesh()
out_verts = np.array(mesh_out.vert_properties, dtype=np.float32)
out_tris  = np.array(mesh_out.tri_verts, dtype=np.int32)

path = "model_fixed.stl"
with open(path, 'wb') as f:
    f.write(b'\x00' * 80)
    f.write(struct.pack('<I', len(out_tris)))
    for tri in out_tris:
        v0, v1, v2 = out_verts[tri[0]], out_verts[tri[1]], out_verts[tri[2]]
        n = np.cross(v1 - v0, v2 - v0)
        nl = np.linalg.norm(n)
        if nl > 0: n /= nl
        f.write(struct.pack('<3f', *n))
        f.write(struct.pack('<3f', *v0))
        f.write(struct.pack('<3f', *v1))
        f.write(struct.pack('<3f', *v2))
        f.write(b'\x00\x00')
print(f"Saved {len(out_tris)} triangles → {path}")
```

### Step 4: Preview and iterate

Render a 3-view preview with original geometry faint (blue, alpha=0.06) and fill highlighted (orange, alpha=0.9). Show the user and ask:
- Does the fill reach the full overhang area?
- Does it follow the curve correctly at the sides?
- Are there any areas still uncovered?

Iterate on the `x_cap`, grid density, or which overhangs to include based on user feedback.

### Key rules for overhang fix

- **Always verify the output before calling it done.** After every export, run:
  ```python
  bodies = result_tm.split(only_watertight=False)
  _, ec = np.unique(np.sort(result_tm.edges, axis=1), axis=0, return_counts=True)
  print(f"Bodies: {len(bodies)}, NM edges: {(ec>2).sum()}, boundary: {(ec==1).sum()}")
  ```
  If bodies >> original + expected fill components, something went wrong. Fix before reporting success. Never call a file "print ready" without passing this check.
- **Never remove original faces.** Only add geometry below overhanging surfaces.
- **Don't use boundary-loop fills alone** for complex curved overhangs — they miss the 3D shape. The ray-cast grid is the reliable method.
- **Install rtree** (`pip install rtree`) before ray casting — trimesh requires it for the spatial index.
- **Multiple Z samples** (e.g., z_steps starting 5mm before the model's z_min) catch overhangs at the very edges.
- **x_cap** prevents fill from tunneling into the upper housing body. Start at 35mm and adjust based on the ceiling map.
- **Use per-cell exact heights**, not max-per-strip. Using the max ceiling height for an entire strip overfills the middle — cells that need 8mm of fill get 35mm, poking through the model above.
- **manifold3d batch_boolean is the correct union method** — do NOT use incremental `fill_m = fill_m + box` (accumulates precision errors, produces genus=-1). Use `m3d.Manifold.batch_boolean(boxes, m3d.OpType.Add)` in one shot.
- **The valid cell region is often 2 disconnected components** (outer ring + inner bowl). The sconce body bridges them when you do `original_m + fill_m`. Don't try to fix the topology of the fill alone — the union handles it.
- **Write STL directly from manifold3d** via the binary writer shown above. Converting through trimesh can produce false non-watertight readings due to original mesh artifacts; trust manifold3d's `status()` and `volume()` instead.
- **Don't mix methods** — if you use the ray-cast manifold fill, don't also add separate boundary-loop fills on top. They clash.

---

## STL Printability Enhancement Mode

When the user uploads an STL and asks to check or improve its printability — or as a final gate on any STL you design before delivery — run this audit pipeline.

**Triggers:** "will this print?", "is this printable?", "fix this STL", "check my file", "clean up this mesh", any STL provided without a specific design request, or automatically at Phase 3 of your own designs.

### Step 1: Full printability audit

Run this immediately on any provided STL, before asking the user anything:

```python
import trimesh, numpy as np

tm = trimesh.load("model.stl", force="mesh")
normals = tm.face_normals
ext = tm.extents

# Mesh integrity
edges_sorted = np.sort(tm.edges, axis=1)
unique_edges, edge_counts = np.unique(edges_sorted, axis=0, return_counts=True)
boundary_edges = (edge_counts == 1).sum()
nm_edges = (edge_counts > 2).sum()
bodies = tm.split(only_watertight=False)

# Overhangs — assuming Z-up print orientation (most common default)
dot_z = np.dot(normals, [0, 0, 1])
n_downward = (dot_z < -0.1).sum()
n_steep    = (dot_z < -np.sin(np.radians(45))).sum()  # > 45° overhang

# Wall estimate via fill ratio
hull_vol   = tm.convex_hull.volume
fill_ratio = abs(tm.volume) / hull_vol if hull_vol > 0 else 0

print("=== MESH ===")
print(f"Watertight: {tm.is_watertight}")
print(f"Boundary edges (holes): {boundary_edges}")
print(f"Non-manifold edges: {nm_edges}")
print(f"Bodies: {len(bodies)}")
print(f"\n=== SIZE ===")
print(f"Bounding box: {ext[0]:.1f} x {ext[1]:.1f} x {ext[2]:.1f} mm")
print(f"Volume: {abs(tm.volume):.0f} mm³")
print(f"\n=== OVERHANGS (Z-up) ===")
print(f"Downward-facing faces: {n_downward}  Steep >45°: {n_steep}")
print(f"\n=== WALLS ===")
print(f"Fill ratio: {fill_ratio:.2f}  ({'thin-walled' if fill_ratio < 0.25 else 'solid-ish'})")
```

Then render a preview:
```bash
python3 preview.py model.stl audit_preview.png --views multi
```

### Step 2: Report findings to the user

One line per check, with severity and proposed action:

```
Printability audit — model.stl (45 x 30 x 23mm):

✅ Size: fits standard 256mm build volume
⚠️ Mesh: 3 non-manifold edges — will repair with manifold3d
❌ Overhangs: 38 steep faces (>45°) at Z=8–14mm — will fill from bed (no slicer supports needed)
✅ Walls: fill ratio 0.31 — adequate for FDM
✅ Bodies: 1 connected mesh

I can automatically fix: mesh repair + overhang fill.
Shall I proceed, or is there anything you want to keep as-is?
```

Always show the preview image alongside the report so the user can see which region the overhangs are in.

### Step 3: Auto-fix pipeline

Fix issues in this order:

| Issue | Severity | Auto-fix? |
|-------|----------|-----------|
| Non-manifold / open mesh | High | Yes — manifold3d repair |
| Steep overhangs > 45° | High | Yes — ray-cast fill + manifold union (see Overhang Fix Mode) |
| Exceeds printer build volume | High | Flag — ask user about scaling or part splitting |
| Floating bodies at Z > 0 | Medium | Flag — likely needs support or repositioning |
| Multiple disconnected bodies | Medium | Flag — may be intentional (assembly parts) |
| Thin features < 0.8mm | Medium | Flag with location — can't auto-fix without full reconstruction |
| Min wall < 1.2mm | Medium | Flag — needs redesign |

**Mesh repair** (non-manifold edges, open boundaries):
```python
import manifold3d as m3d, numpy as np, trimesh, struct

tm = trimesh.load("model.stl", force="mesh")
repaired_m = m3d.Manifold(m3d.Mesh(
    vert_properties=np.array(tm.vertices, dtype=np.float32),
    tri_verts=np.array(tm.faces, dtype=np.int32)
))
print(f"Repaired: genus={repaired_m.genus()}, status={repaired_m.status()}, vol={repaired_m.volume():.0f} mm³")
# Then write via binary STL (same pattern as Overhang Fix Step 3)
```

**Overhang fix:** run the full Overhang Fix Mode workflow — ray-cast ceiling grid → manifold3d batch union → union with original mesh → binary STL export.

### Step 4: Orientation recommendation

After fixing, always suggest the optimal print orientation:

```python
# Find the flat face with the largest area — best bed candidate
areas = tm.area_faces
for axis, label in [([0,0,-1],"-Z (bottom)"), ([0,0,1],"+Z (top)"),
                    ([1,0,0],"+X"), ([-1,0,0],"-X"),
                    ([0,1,0],"+Y"), ([0,-1,0],"-Y")]:
    matching = np.dot(normals, axis) > 0.95
    flat_area = areas[matching].sum()
    oh_count  = (np.dot(normals[~matching], [0,0,1]) < -np.sin(np.radians(45))).sum()
    print(f"{label}: {flat_area:.0f} mm² bed area, {oh_count} remaining overhangs")
# Pick the orientation with most bed area and fewest overhangs
```

State the recommendation clearly:
```
Best orientation: flat bottom face on bed (already correct).
Remaining overhangs after fill: none. No slicer supports needed.
```

### Step 5: Deliver the enhanced STL

- Name it `<original_name>_printable.stl`
- Render a before/after preview (original + fixed side by side if possible)
- State exactly what changed ("filled 38 overhang faces, repaired 3 non-manifold edges")
- Include print settings (see Print Recommendations section)

---

## Model Repository Search

Before writing any CadQuery code, search the major model repositories. A high-quality existing model saves the user time and may be better-tested than a fresh design. This step runs **after** requirements gathering (so you know what to search for) but **before** any design work.

### Sites to search

| Site | URL | Notes |
|------|-----|-------|
| MakerWorld | makerworld.com | Bambu Lab's community — highest quality filter, good parametric models |
| Printables | printables.com | Prusa's community — large library, strong tagging |
| Thingiverse | thingiverse.com | Largest archive — older models, variable quality |
| Cults3D | cults3d.com | Curated, paid and free — good for functional parts |
| MyMiniFactory | myminifactory.com | Community + creator marketplace |

Search all five. Use `WebSearch` with targeted queries like:
```
site:makerworld.com <object name> <key constraint>
site:printables.com <object name> parametric
<object name> 3d print filetype:stl
```

### What to look for

A result is worth presenting to the user if it meets **all** of these:
- Matches the core function the user described
- Is compatible with their printer/material (check the listing's print settings if shown)
- Has a recent upload or a proven remix count (indicates it actually prints)
- Fits the critical dimensions, OR is parametric so dimensions can be adjusted

### How to report findings

Present results **before** starting design. Be specific — include the model name, site, URL, and what makes it relevant or insufficient:

```
Before designing, I searched the major repositories. Here's what I found:

✅ Strong match — MakerWorld: "Parametric Wall Hook" by user X
   Fits your ~50mm mounting slot, PETG-compatible, 4.8★ with 200+ makes.
   URL: [link]
   → Worth downloading first. Want me to use this, modify it, or design a custom version?

⚠️ Partial match — Printables: "Cable Tray v2"
   Right function but fixed 80mm width; you need 120mm. Not parametric.

❌ Nothing suitable on Thingiverse or Cults3D for this combination.
```

Then wait for the user's decision:
- **"Use it"** → provide the download link, done
- **"Modify it"** → switch to **STL Reference Mode** (above) with the downloaded file
- **"Build custom"** → proceed with the normal design workflow

### When to skip the search

- User explicitly says "build me a custom" or "I want it parametric from scratch"
- User already has a reference STL they're working from
- The object is highly specific to their exact hardware (custom PCB, one-off enclosure dimensions) where a generic match is unlikely

Even then, a 30-second search costs nothing — if you skip it, say why.

---

## Core Workflow

1. **Gather requirements** (see Requirements Gathering below)
2. **Search model repositories** (see Model Repository Search below) — find existing designs before building from scratch
3. **Research dimensions** of any real-world products involved (see above)
4. **Phase 1, Base shape**: Build outer shell, preview, get user feedback
5. **Phase 2, Features**: Add functional details, preview, get user feedback
6. **Phase 3, Final delivery**: Fillets, cleanup, final preview + STL + print recommendations
7. **Offer parameter tweaks** after delivery

This is a **collaborative, show-as-you-go** process. Do NOT disappear and come back with a finished model. Show the user your progress at each phase and incorporate their feedback before moving on.

## Requirements Gathering

Before writing any code, walk through these topics with the user **conversationally**. Don't dump all questions at once. Ask the most important ones first, then follow up based on answers. Use reasonable defaults when the user doesn't specify.

**Reference STL? (ask first)**
Does the user have an existing STL they want to modify or use as inspiration? If yes, switch to the **STL Reference Mode** workflow above before continuing here.

**What is it?**
Object type, purpose, what it holds/protects/attaches to. Get a clear mental model of the object before anything else.

**Critical dimensions**
Must-fit measurements, like PCB size, phone width, screw spacing, diameter of the thing it wraps around, etc. These are non-negotiable and drive everything else.

**Mounting & attachment**
How does it connect to things? Screws (what size?), snap-fit, adhesive tape, magnets, freestanding on a desk? This affects wall thickness, boss placement, and overall structure.

**Printer & material**
What printer do they have? (Bambu, Prusa, Ender, etc.) Nozzle size? Material (PLA, PETG, TPU)? This directly affects tolerances, minimum feature sizes, and design constraints. Defaults: 0.4mm nozzle, PLA, 0.2mm layer height.

**Functional needs**
Ventilation/airflow, water resistance, cable routing, access panels, visibility windows, stacking, weight limits. Ask only what's relevant to the object.

**Aesthetic preferences**
Rounded vs sharp edges, minimal vs industrial look, color considerations (affects visibility of layer lines). Ask briefly. Most users care more about function than form.

Start with the first two (what + dimensions), then ask about mounting and material if relevant. Only ask about aesthetics if the user seems to care or if it affects structural choices.

## Progressive Preview Workflow

Build the model in phases. At each phase, export an STL, render a preview, self-review it, then **show it to the user and ask for feedback** before proceeding. This catches problems early and keeps the user involved.

### Preview recipe (use at every phase)

**One-shot (run script + render + parse result as JSON):**
```bash
python3 run_cadquery_model.py model.py --preview --strict
```
This executes `model.py`, finds the STL it wrote, renders the multi-view preview, and emits a JSON result with `success`, `stdout`, `stderr`, `stl`, `preview`, and `watertight`. With `--strict`, a non-watertight mesh is a hard failure. Use this as the default loop: if `success` is false, read the `stderr` field to fix the CadQuery script, then re-run.

**Rendering only (when the STL already exists):**
```bash
python3 preview.py model.stl preview.png --views multi
```

Then view the preview image, self-review it against the checklist in `design-review.md`, and fix any issues you spot **before** showing it to the user.

---

### Phase 1: Base Shape

Build the basic outer form: overall dimensions, shell/walls, bottom plate. No cutouts, no fillets, no details yet.

1. Write the script with parameters and basic geometry
2. Export STL and render preview
3. Self-review: Does the shape and size look right? Is the bottom flat for printing?
4. **Show the preview to the user**: "Here's the basic shape. Does this look right before I add details?" Include key dimensions.
5. Wait for feedback. If the user wants changes, iterate here before moving on.

### Phase 2: Features

Add functional details: holes, cutouts, mounting bosses, cable slots, ventilation, snap-fits, internal structures.

1. Add features to the script
2. Export STL and render preview
3. Self-review: Are all features visible? Do booleans look clean? Are holes in the right positions?
4. **Show the preview to the user**: "I've added [list features]. Anything to change before I finalize?"
5. Wait for feedback. Iterate if needed.

### Phase 3: Final Delivery

Apply finishing touches: fillets, chamfers, edge cleanup. Do a full printability review.

1. Add fillets/chamfers (largest radius first, apply after shell)
2. Export final STL and render preview
3. **Full self-review** using the complete checklist from `design-review.md`: visual inspection, dimensional verification, printability analysis
4. Fix any issues found, re-export if needed
5. **Deliver to the user**: final STL + preview image + print recommendations (orientation, supports, infill, material notes)

---

**Important:** Do NOT skip phases or combine them unless the model is very simple (e.g., a flat bracket with two holes). For anything with enclosed geometry, multiple features, or tight tolerances, follow all three phases.

Read `design-review.md` for the full visual inspection checklist, dimensional verification code, and printability analysis helpers.

### Print Recommendations (final delivery)

When you deliver the final STL, always include a one-line slicer recipe plus a short rationale. Bambu Studio, PrusaSlicer, and OrcaSlicer already set sensible defaults from their filament + process presets, so **do not restate every slicer option**. Only tell the user what matters for *this* model: material, layer height, walls, infill, supports, and orientation. Tweak from the baseline below only when the model needs it.

**Baseline recipe (0.4mm nozzle, typical FDM):**
> PLA, 0.2mm layer, 2 walls, 15% gyroid infill, no supports, orientation: flat side on bed.

**When to deviate from the baseline:**
- **Load-bearing brackets / hooks / hinges**: bump infill to 25-40%, 3-4 walls, consider PETG over PLA for toughness.
- **Thin decorative walls or vases**: 0 infill, vase mode or 1 wall.
- **Tall narrow parts**: add a brim for bed adhesion.
- **Flexible parts (gaskets, grips)**: TPU 95A, 0.2mm layer, slower speed, no supports.
- **Functional overhangs the geometry can't avoid**: tree supports, or call them out so the user knows.
- **Outdoor / hot environments**: PETG or ASA, not PLA.
- **Food / skin contact**: call out that FDM parts are not food-safe and recommend a food-safe coating.

**Format at delivery time:**
```
Print settings: PLA, 0.2mm layer, 2 walls, 15% gyroid infill, no supports.
Orientation: place flat back side on the bed (front face up).
Why: the case has no overhangs above 45°, and 15% infill is plenty for a
TPU-adjacent protective shell.
```

Keep it to ~3 lines. Never dump every slicer setting; the slicer already knows.

## Script Template

ALWAYS structure scripts like this:

```python
import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# ============================================================
# Overall dimensions
width = 60.0        # mm - outer width
depth = 40.0        # mm - outer depth  
height = 25.0       # mm - outer height

# Wall and structural
wall = 2.0          # mm - wall thickness (min 1.2 for FDM)
corner_r = 2.0      # mm - corner fillet radius

# Tolerances
fit_clearance = 0.3 # mm - clearance for press-fit (adjust per printer)

# ============================================================
# MODEL
# ============================================================
result = (
    cq.Workplane("XY")
    .box(width, depth, height, centered=(True, True, False))
    # ... build geometry using parameters above (bottom at Z=0)
)

# ============================================================
# EXPORT
# ============================================================
# Use tolerance=0.01, angularTolerance=0.1 for consistent tessellation
# across models. Defaults give coarser, wildly variable STL sizes.
cq.exporters.export(result, "output.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(f"Exported: {width}x{depth}x{height}mm")
```

## Key Rules

### Parameters First
- ALL dimensions go in the PARAMETERS section at the top
- Use descriptive names: `screw_hole_d`, not `d1`
- Add units in comments (always mm)
- Group related parameters with blank lines and section comments

### Print-Friendly Defaults
Key FDM design defaults:

| Property | Minimum | Recommended |
|----------|---------|-------------|
| Wall thickness | 1.2mm | 2.0mm |
| Layer height | 0.08mm | 0.2mm |
| Hole clearance | 0.2mm | 0.3mm |
| Press-fit interference | 0.1mm | 0.15mm |
| Min feature size | 0.4mm (nozzle) | 0.8mm |
| Fillet radius (bottom) | 0.5mm | 1.0mm |
| Bridge span | - | < 20mm unsupported |
| Overhang angle | - | < 45 degrees from vertical |

**Material-specific adjustments:** TPU needs larger clearances (~0.5mm) due to flex. PETG is stickier, so add +0.1mm to fit clearances. ABS shrinks ~0.5-0.7%, so scale critical dimensions up slightly. When in doubt, print a small test piece first.

### Orientation Awareness
- Design with print orientation in mind
- Flat bottom surfaces print best
- Avoid supports when possible by designing around overhangs
- Add chamfers to bottom edges instead of fillets (fillets need supports)
- Comment the intended print orientation in the script

### CadQuery Patterns

Common patterns to know:

**Hollow enclosure (boolean subtraction, preferred):**
```python
outer = (
    cq.Workplane("XY")
    .box(width, depth, height, centered=(True, True, False))
    .edges("|Z").fillet(corner_r)
)
inner = (
    cq.Workplane("XY")
    .workplane(offset=floor_t)
    .box(width - 2*wall, depth - 2*wall, height, centered=(True, True, False))
    .edges("|Z").fillet(max(0.1, corner_r - wall))
)
result = outer.cut(inner)
```

**Screw boss:**
```python
.pushPoints([(x, y)])
.circle(boss_od / 2).extrude(boss_h)
.pushPoints([(x, y)])
.hole(screw_d + fit_clearance)
```

**Snap-fit clip:**
```python
# Cantilever beam with overhang hook
.workplane(offset=wall)
.moveTo(x, y).rect(clip_w, clip_l).extrude(clip_h)
# Add hook at tip with a small overhang (< 45 deg)
```

**Ventilation grid:**
```python
.pushPoints(vent_positions)
.slot2D(slot_l, slot_w).cutThruAll()
```

Other patterns: mounting brackets, cable routing channels, text/labels (`.text()`), multi-part assemblies with alignment pins.

### Common Pitfalls

- **Hollowing: prefer boolean subtraction over `.shell()`**. `.shell()` is fragile. It fails on tapered bodies, lofted shapes, unions of multiple primitives, and anything with many fillets. The reliable pattern is:
  ```python
  outer = cq.Workplane("XY").box(w, d, h, centered=(True, True, False)).edges("|Z").fillet(corner_r)
  inner = (
      cq.Workplane("XY")
      .workplane(offset=floor_t)
      .box(w - 2*wall, d - 2*wall, h, centered=(True, True, False))
      .edges("|Z").fillet(max(0.1, corner_r - wall))
  )
  result = outer.cut(inner)
  ```
  Only reach for `.shell()` when the body is a single simple primitive (one `.box()` or `.cylinder()`) with a uniform wall thickness on all sides. If in doubt, use boolean subtraction.
- **Build order: fillet → cut, not cut → fillet**. Apply fillets while the geometry is still a clean primitive. Once you have cut holes/slots/pockets into a body, filleting the resulting edges often fails or produces bad geometry. Same rule for chamfers.
- **Fillet failures**: Apply fillets from largest to smallest radius. **Do not wrap fillets in `try/except` to silently shrink the radius.** A fillet failure means the geometry or the radius is wrong; find the root cause (too-large radius, wall thinner than radius, adjacent faces that the fillet would degenerate) and fix that.
- **Zero-thickness geometry**: Ensure boolean operations don't create infinitely thin walls. Add a small epsilon (0.01mm) when cutting bodies that are meant to pass just through a surface.
- **Coordinate system**: CadQuery centers geometry at origin by default. Use `centered=(True, True, False)` on `.box()` to place the bottom at Z=0 so `.faces("<Z")` is always the print bed.
- **Hole direction**: `.hole()` cuts through the entire part by default. Use `.cboreHole()` or `.cskHole()` for counterbore/countersink.
- **Taper direction**: In `.extrude(taper=angle)`, a **positive** taper angle narrows the shape (draft inward), **negative** flares it outward. This is opposite to what many people expect.
- **Loft is fragile**: `.loft()` fails on many cross-section combinations. Prefer `.extrude(taper=angle)` when transitioning between a shape and a scaled version of itself. Only use `.loft()` when you need to transition between genuinely different profiles (e.g., circle to rectangle).
- **Export errors / non-watertight STL**: If export fails or the preview reports a non-watertight mesh, the geometry is invalid (usually self-intersecting booleans or zero-thickness faces). Fix the cause, don't paper over it. Run `python3 preview.py model.stl --strict` to fail loudly on non-watertight output.

## Export

```python
# STL (for slicing) - always set tolerance + angularTolerance for
# consistent tessellation. Defaults produce variable file sizes and
# over-tessellated glyphs on text features.
cq.exporters.export(result, "model.stl",
                    tolerance=0.01, angularTolerance=0.1)

# STEP (for further CAD editing)
cq.exporters.export(result, "model.step")
```

Always export STL for printing. Optionally export STEP if the user might want to edit in Fusion 360 or similar.

## Multi-Part Models

For models with multiple parts (e.g., enclosure + lid):

```python
# Export each part separately
cq.exporters.export(body, "enclosure_body.stl")
cq.exporters.export(lid, "enclosure_lid.stl")
```

Name files descriptively so the user knows which part is which.

## Parameter Adjustment Offer

After delivering the final model, **always present the key parameters as a summary table** and offer to tweak them. This lets the user fine-tune without re-explaining the whole design.

Example:
```
Here's your final model! Current parameters:

| Parameter       | Value  |
|----------------|--------|
| Width          | 90 mm  |
| Depth          | 65 mm  |
| Height         | 30 mm  |
| Wall thickness | 4 mm   |
| Cable slot     | 18 mm  |
| Corner radius  | 3 mm   |
| Fit clearance  | 0.3 mm |

Want me to adjust anything? Just say e.g. "make it 5mm taller" or "wider cable slot."
```

Only include parameters the user would plausibly want to change. Skip internal constants like `eps` or `nozzle_d`. Group them logically (dimensions first, then structural, then tolerances).

## Output Checklist

Before delivering a model, verify:
- [ ] All dimensions are parameterized (no magic numbers in geometry code)
- [ ] Wall thickness >= 1.2mm
- [ ] Designed for printability (minimal overhangs/supports)
- [ ] Print orientation noted in comments
- [ ] STL exported and file size is reasonable (not 0 bytes)
- [ ] Clear parameter names with units
- [ ] Script runs without errors
- [ ] **Multi-view preview generated and visually inspected**
- [ ] **Preview shows correct shape, features, and proportions**
- [ ] **Bounding box dimensions match requirements**
- [ ] Both STL and preview PNG delivered to user
