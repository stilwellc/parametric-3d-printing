---
name: parametric-3d-printing
description: "Use this skill when the user wants to design a 3D-printable physical object they intend to manufacture. Triggers: any mention of '3D print', 'STL', 'parametric model', 'enclosure', 'bracket', 'mount', 'case', 'housing', 'CadQuery', 'OpenSCAD', or a specific FDM printer (Bambu Lab, Prusa, Ender); questions about print-friendly design, snap-fits, tolerances, or wall thickness; requests for functional parts like Arduino enclosures, cable organizers, wall mounts, adapters, or mechanical components; providing an existing STL file as a reference, for modification, or for inspiration. Also fires when the user describes a real physical object to make, provided the goal is to manufacture it. Do NOT use for: 3D rendering, animation, game assets, digital-only art, photogrammetry, sculpting, or any 3D work that is not heading toward a printer."
---

# Parametric 3D Printing with CadQuery

## Mode Select

Read the user's request and pick one mode. Follow that mode linearly from start to finish.

| If the user… | Use |
|---|---|
| Wants a new part designed from scratch | **Mode A: New Design** |
| Provides an existing STL to modify or use as inspiration | **Mode B: STL Reference** |
| Has an STL that fails to print due to overhangs | **Mode C: Overhang Fix** |
| Wants an STL checked or repaired for printability | **Mode D: Printability Audit** |

---

## Setup

```bash
# CadQuery requires Python 3.10-3.12 (OCC kernel lacks 3.13+ wheels)
python3.12 -m venv .venv && source .venv/bin/activate

# Install CadQuery and preview dependencies
pip install cadquery trimesh pyrender Pillow manifold3d rtree
```

CadQuery uses the OpenCASCADE kernel under the hood. trimesh, pyrender, and Pillow are used for the preview-analyze-iterate loop. manifold3d and rtree are required for overhang fix and mesh repair. No display server is needed; everything renders headlessly via pyrender's offscreen backend.

**If CadQuery fails to install** (OCC kernel build errors), try:
```bash
# Option 1: Use conda (CadQuery's officially recommended method)
conda install -c cadquery -c conda-forge cadquery

# Option 2: Use the pre-built wheels
pip install cadquery --find-links https://github.com/CadQuery/CadQuery/releases
```

**PrusaSlicer CLI check** (needed for Slicer Verification in Phase 3):
```bash
PSLICER="/Applications/PrusaSlicer.app/Contents/MacOS/prusa-slicer"
$PSLICER --version   # confirm it's found
# On Linux: prusa-slicer (package manager or AppImage)
# If not installed, skip slicer verification and note "slicer not available" in delivery.
```

### Live Design UI

A companion browser UI shows the model building in real time. Start it once per session before Phase 1:

```bash
python3 ui_server.py   # opens http://localhost:7384 automatically
```

The UI shows: live 3D model (Three.js STL viewer), multi-view preview images, phase progress, parameter table, and slicer report. It updates automatically whenever you export a new STL or PNG.

**Write `ui_state.json` at every phase transition** so the UI stays in sync. Use this schema:

```python
import json, pathlib

def update_ui(phase_id, phase_label, message, parameters=None,
              object_name="", material="", printer="", slicer_report=None):
    state = {
        "phase":         phase_label,
        "phase_id":      phase_id,       # see phase IDs below
        "object":        object_name,
        "material":      material,
        "printer":       printer,
        "message":       message,
        "parameters":    parameters or {},
        "slicer_report": slicer_report,  # dict or None
    }
    pathlib.Path("ui_state.json").write_text(json.dumps(state, indent=2))
```

**Phase IDs** (use exactly these strings):
`requirements` · `search` · `dimensions` · `brief` · `phase1` · `phase2` · `structural` · `phase3` · `slicer` · `delivered`

**Slicer report dict** (fill from gcode parse):
```python
slicer_report = {"time": "2h 15m", "filament_g": "18", "support_pct": 0.0, "layers": 112}
```

If the user hasn't started `ui_server.py`, skip the `update_ui` calls silently — they are optional and must never block the design workflow.

---

## Design Constants Reference

All lookup tables live here. When writing code, come back to this section rather than guessing values.

### Material Profiles

| Property | PLA | PETG | ABS | ASA | TPU 95A | PA-CF |
|---|---|---|---|---|---|---|
| Min wall structural | 1.2mm | 1.2mm | 1.5mm | 1.5mm | 1.0mm | 1.2mm |
| Min wall decorative | 0.8mm | 0.8mm | 1.0mm | 1.0mm | 0.6mm | 0.8mm |
| Max bridge unsupported | 20mm | 15mm | 18mm | 18mm | 10mm | 22mm |
| Shrinkage compensation % | 0.2% | 0.3% | 0.7% | 0.6% | 0.5% | 1.2% |
| Sliding fit clearance/side | 0.2mm | 0.3mm | 0.25mm | 0.25mm | 0.15mm | 0.2mm |
| Press fit interference (neg = tighter) | -0.2mm | -0.25mm | -0.3mm | -0.3mm | -0.1mm | -0.2mm |
| Horizontal hole sag correction | +0.1mm | +0.15mm | +0.1mm | +0.1mm | +0.05mm | +0.1mm |
| Outdoor UV resistance | Poor | Fair | Fair | Excellent | Good | Good |
| Enclosure required | No | No | Yes | No | No | No |
| Layer adhesion strength | Good | Very good | Good | Good | Excellent | Good |

**PA-CF shrinkage note:** PA-CF shrinks 1.2%. If a dimension must be exactly 50.0mm, model it at 50.6mm (50.0 / (1 - 0.012) ≈ 50.6mm).

### Clearance Fits (sliding or rotating)

| Fit type | PLA | PETG | ABS/ASA | TPU 95A |
|---|---|---|---|---|
| Sliding (drawer, rail) | 0.2mm/side | 0.3mm/side | 0.25mm/side | 0.15mm/side |
| Rotating (pin in hole) | 0.25mm/side | 0.35mm/side | 0.3mm/side | 0.2mm/side |
| Print-in-place hinge | 0.3mm/side | 0.4mm/side | 0.35mm/side | 0.25mm/side |
| Loose / rattle-free | 0.15mm/side | 0.2mm/side | 0.2mm/side | 0.1mm/side |

Clearance is **per side**. A 5mm PLA sliding pin goes in a `5.0 + 2×0.2 = 5.4mm` hole.

### Press and Interference Fits

| Fit type | PLA | PETG |
|---|---|---|
| Light press (removable by hand) | -0.1mm | -0.15mm |
| Firm press (stays permanently) | -0.2mm | -0.25mm |
| Interference (structural) | -0.3mm | -0.4mm |

Negative = hole smaller than shaft. Interference fits in thin walls crack — wall must be ≥ 2× the interference value.

### Snap-Fit Arm Geometry

Three variables drive a safe snap: arm length, root thickness, and material strain limit.

```
Max safe deflection y = (strain_limit × L²) / (1.5 × t)
  L = arm length (mm), t = root thickness (mm)

FDM strain limits (conservative — layer adhesion is the weak axis):
  PLA     0.015   PETG    0.020   ABS/ASA  0.018
  TPU 95A 0.150   Nylon   0.040
```

**Quick-reference arm proportions:**

| Material | Arm length | Root thickness | Max deflection | Return angle |
|---|---|---|---|---|
| PLA | 15mm | 1.5mm | 1.5mm | 30° |
| PLA | 20mm | 1.5mm | 2.5mm | 35° |
| PETG | 15mm | 1.5mm | 2.0mm | 25° |
| PETG | 20mm | 2.0mm | 2.5mm | 30° |
| TPU 95A | 10mm | 0.8mm | 3.0mm | 45° |
| Nylon | 15mm | 1.2mm | 3.5mm | 40° |

**Rules that must not be skipped:**
- Orient snap arms so they deflect **perpendicular to layer lines** (sideways, not up/down) — layer-direction deflection delaminates.
- Add 0.3mm clearance on the deflection side so the arm can actually move before engaging.
- Taper root→tip (e.g. 1.5mm → 0.8mm) to distribute stress and soften the snap force.
- Return angle > 45° on PLA = permanent lock. Use 25–35° for user-removable snaps.

**CadQuery snippet — cantilever snap arm deflecting in Y:**
```python
arm_length  = 20.0   # mm
root_thick  = 1.5    # mm
tip_thick   = 0.8    # mm
arm_width   = 4.0    # mm
hook_height = 1.5    # mm — must match deflection clearance in mating part
return_ang  = 30     # degrees

arm = (
    cq.Workplane("XZ")
    .polyline([
        (0, 0), (arm_length, 0),
        (arm_length, hook_height),
        (arm_length - hook_height / math.tan(math.radians(return_ang)), 0),
    ])
    .close()
    .extrude(arm_width)
    .faces("<Z").shell(-root_thick)  # taper via loft in practice
)
```

### Living Hinges (TPU only)

| Hinge span | Thickness | Min bend radius |
|---|---|---|
| < 20mm | 0.6mm | 2mm |
| 20–50mm | 0.8mm | 3mm |
| > 50mm | 1.0mm | 5mm |

Layer lines must run **across** the hinge (perpendicular to flex direction). Parallel layer lines delaminate immediately. Print flat.

### Print-in-Place Joints

| Joint type | Clearance | Key rule |
|---|---|---|
| Pin hinge PLA | 0.3mm/side | Print with pin axis parallel to bed |
| Pin hinge PETG | 0.4mm/side | Same orientation |
| Ball socket PLA | 0.4mm radial | Print socket open-side-up |
| Captive M3 nut | 0.2mm/side hex | Pause print at nut layer, drop nut in |
| Gear mesh | 0.15–0.2mm backlash | Print both gears in same plane |

### Minimum Feature Sizes (0.4mm nozzle, 0.2mm layers)

| Feature | Minimum | Notes |
|---|---|---|
| Structural wall | 1.2mm | = 3 perimeters |
| Decorative wall | 0.8mm | = 2 perimeters; no load |
| Boss / pin diameter | 1.0mm | Smaller doesn't adhere reliably |
| Slot / gap width | 0.5mm | Narrower fills with stringing |
| Embossed text stroke | 0.5mm, 1.5mm deep | Shallower disappears |
| Debossed text stroke | 0.6mm, 0.8mm deep | |
| Vertical hole | 1.0mm diameter | |
| Horizontal hole | nominal + 0.1–0.15mm | Gravity sags the top; D-shape top helps |

### Hardware Database

**Heat inserts — Ruthex brand defaults:**

| Size | Hole dia | OD | Depth | Wall around |
|---|---|---|---|---|
| M2 | 3.2mm | 3.5mm | 3.2mm | 1.5mm |
| M3 | 4.4mm | 4.6mm | 4.0mm | 1.8mm |
| M4 | 5.7mm | 6.0mm | 6.0mm | 2.0mm |
| M5 | 6.6mm | 7.0mm | 7.0mm | 2.2mm |

Insert with soldering iron at ~200°C, flush with surface.

**Screw clearance holes:**

| Size | Through hole | Self-tap | Counterbore dia × depth |
|---|---|---|---|
| M2 | 2.4mm | 1.6mm | 4.4mm × 2mm |
| M3 | 3.4mm | 2.5mm | 5.5mm × 3mm |
| M4 | 4.5mm | 3.3mm | 7.0mm × 4mm |
| M5 | 5.5mm | 4.2mm | 8.5mm × 5mm |

**Common SBC mounting patterns:**

| Board | Hole pattern | Screw | Notes |
|---|---|---|---|
| Raspberry Pi 4/5 | 58.0 × 49.0mm | M2.5 | 3.5mm from edges |
| Raspberry Pi Zero 2W | 58.0 × 23.0mm | M2.5 | 3.5mm from edges |
| Arduino Uno R3 | 68.6 × 53.3mm | M3 | Standard UNO footprint |
| Arduino Nano | 43.2 × 17.8mm | M3 | 1.5mm from edge |
| ESP32 DevKit | 50.8 × 25.4mm | M3 | 2mm from edge |

**Always web-search SBC dimensions to confirm — board revisions change hole positions.**

**Standard magnets (N35 disc, press-fit pockets):**

| Magnet | Pocket dia | Pocket depth adjustment |
|---|---|---|
| 6mm disc N35 | nominal +0.2mm | nominal +0.1mm |
| 8mm disc N35 | nominal +0.2mm | nominal +0.1mm |
| 10mm disc N35 | nominal +0.2mm | nominal +0.1mm |

### Seam Placement Strategy

PrusaSlicer/BambuStudio default: aligned seam at the sharpest concave corner (vertical edges).

1. **Rectilinear objects:** add a 0.5mm V-groove on the least-visible rear edge to pin the seam there.
2. **Cylindrical/organic objects:** add a 0.3mm-wide × 0.3mm-deep channel to pin seam; or use "random" seam in slicer.
3. Keep seams away from mating surfaces, bearing seats, sliding rails, and snap-fit arms — the seam adds 0.1–0.2mm of material.
4. Choose print orientation so the seam-attracting edge faces back or bottom.
5. Comment in code: `# seam pins to rear-left vertical edge — intentional`

### Structural Rules

| Situation | Rule |
|---|---|
| Cantilever > 25mm | Add triangular gusset at root; min gusset base = 1/3 arm length |
| Cantilever > 40mm with load | Redesign as supported bracket or split into two parts |
| Interior sharp corner under load | Fillet r ≥ 0.5mm |
| Horizontal span > bridge limit (per material) | Add mid-span rib or support column |
| Thin wall < 1.5mm carrying load | Bump to 2.0mm or add perpendicular rib |
| Load perpendicular to layer lines | Reorient part or add ribs to align load with layers |
| Tall narrow part H > 5× base | 5mm brim + consider internal cross-bracing |
| Snap arm root | Wall behind arm must be ≥ 2× arm root thickness |

---

## Mode A: New Design

Follow these steps in order. Do not skip phases or combine them unless the model is very simple (a flat bracket with two holes). Show the user progress at each phase and wait for feedback before continuing.

**UI:** Start `python3 ui_server.py` now if not already running. Call `update_ui()` at every step below.

### Step 1: Requirements Gathering

Walk through these topics conversationally. Ask the most important ones first, follow up based on answers. Use reasonable defaults when the user doesn't specify.

**Reference STL? (ask first)** — Does the user have an existing STL they want to modify or use as inspiration? If yes, switch to **Mode B** before continuing here.

**What is it?** — Object type, purpose, what it holds/protects/attaches to. Get a clear mental model before anything else.

**Critical dimensions** — Must-fit measurements: PCB size, phone width, screw spacing, diameter of what it wraps around. These are non-negotiable and drive everything else.

**Mounting & attachment** — How does it connect? Screws (what size?), snap-fit, adhesive tape, magnets, freestanding? Affects wall thickness, boss placement, and overall structure.

**Printer & material** — What printer (Bambu, Prusa, Ender)? Nozzle size? Material (PLA, PETG, TPU)? Defaults: 0.4mm nozzle, PLA, 0.2mm layer height.

**Functional needs** — Ventilation, water resistance, cable routing, access panels, visibility windows, stacking, weight limits. Ask only what's relevant.

**Aesthetic preferences** — Rounded vs sharp edges, minimal vs industrial. Ask briefly. Most users care more about function.

Start with what + dimensions, then ask about mounting and material. Only ask about aesthetics if the user seems to care or if it affects structural choices.

```python
update_ui("requirements", "Requirements", "Gathering requirements...", object_name=OBJECT, material=MATERIAL, printer=PRINTER)
```

### Step 2: Search Model Repositories

Before writing any code, search the major repositories. A high-quality existing model saves time and may be better-tested. This step runs after requirements gathering (so you know what to search for) but before any design work.

**Sites to search:**

| Site | URL | Notes |
|---|---|---|
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

**A result is worth presenting if it:**
- Matches the core function the user described
- Is compatible with their printer/material
- Has a recent upload or proven remix count
- Fits the critical dimensions, OR is parametric so dimensions can be adjusted

**Report format:**
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
- **"Modify it"** → switch to **Mode B** with the downloaded file
- **"Build custom"** → proceed

**When to skip the search:**
- User explicitly says "build me a custom" or "I want it parametric from scratch"
- User already has a reference STL they're working from
- The object is highly specific to their exact hardware where a generic match is unlikely

Even then, a 30-second search costs nothing — if you skip it, say why.

```python
update_ui("search", "Repo Search", "Searching MakerWorld, Printables, Thingiverse...", object_name=OBJECT, material=MATERIAL, printer=PRINTER)
```

### Step 3: Research Real-World Dimensions

When designing objects that interface with real products (phones, chargers, PCBs, connectors), **use web search to find accurate dimensions before writing any geometry code**. Don't guess. Even 1–2mm off can make a part unusable.

**What to research:**
- Connector/port dimensions (USB-C: 8.4 × 2.6mm opening, Lightning, barrel jacks)
- Device dimensions (phone width/thickness, PCB footprints, charger puck diameters)
- Mounting hole patterns and screw sizes (M2.5, M3, etc.) — check Hardware Database first
- Standard component specs (MagSafe puck: 56mm diameter, 5.6mm thick)
- Cable bend radii and strain relief requirements

Cross-reference at least 2 sources when precision matters. Add sourced dimensions as comments in the PARAMETERS section:
```python
# MagSafe puck dimensions (source: Apple spec + iFixit teardown)
puck_diameter = 56.0    # mm
puck_thickness = 5.6    # mm
```

When in doubt, add 0.3–0.5mm clearance to external dimensions.

```python
update_ui("dimensions", "Dimensions", "Researching real-world dimensions...", object_name=OBJECT, material=MATERIAL, printer=PRINTER)
```

### Step 4: Design Brief

After requirements, repository search, and dimension research — and before writing any code — synthesize a design brief:

```
Design brief:
Object: [what it is and does]
Critical constraints: [must-hit dimensions]
Material: [material — note which profile constants apply]
Fit tolerance: [which type, specific values from tables]
Printer: [printer + nozzle + layer height]
Seam: [which edge, why]
Print orientation: [which face on bed, why no supports]
Hardware: [heat inserts / screws / boards with exact hole sizes from Hardware Database]
```

Then ask: "Here's my design plan — does this match what you're after before I start modeling?"

**Wait for confirmation before proceeding.**

```python
update_ui("brief", "Design Brief", "Waiting for brief confirmation...", object_name=OBJECT, material=MATERIAL, printer=PRINTER, parameters=PARAMS)
```

### Step 5: Phase 1 — Base Shape

Build the basic outer form: overall dimensions, shell/walls, bottom plate. No cutouts, no fillets, no details yet. All parameters defined at the top of the script using the Script Template below.

**Design principles for this phase:**
- All dimensions go in the PARAMETERS section at the top. Use descriptive names: `screw_hole_d`, not `d1`. Add units in comments (always mm).
- Use `centered=(True, True, False)` on `.box()` to place the bottom at Z=0.
- Design with print orientation in mind. Flat bottom surfaces print best. Add chamfers to bottom edges instead of fillets (fillets need supports). Comment the intended print orientation in the script.
- Apply shrinkage compensation from the Material Profiles table if the material is ABS, ASA, or PA-CF.

**Steps:**
1. Write the script with parameters and basic geometry
2. `update_ui("phase1", "Phase 1 — Base Shape", "Building base shell...", parameters=PARAMS, ...)`
3. Export STL and render preview: `python3 run_cadquery_model.py model.py --preview --strict`
4. Self-review: Does the shape and size look right? Is the bottom flat for printing?
5. `update_ui("phase1", "Phase 1 — Base Shape", "Base shape complete — waiting for feedback", parameters=PARAMS, ...)`
6. **Show the preview to the user:** "Here's the basic shape. Does this look right before I add details?" Include key dimensions.
7. Wait for feedback. Iterate here before moving on.

### Step 6: Phase 2 — Features

Add functional details: holes, cutouts, mounting bosses, cable slots, ventilation, snap-fits, internal structures.

Look up all fit values from the Design Constants Reference:
- Clearance fits from the Clearance Fits table
- Heat insert hole diameters from the Hardware Database
- SBC hole patterns from the Hardware Database
- Snap-fit arm proportions from the Snap-Fit Arm Geometry table
- Seam placement per the Seam Placement Strategy

**Steps:**
1. `update_ui("phase2", "Phase 2 — Features", "Adding functional features...", parameters=PARAMS, ...)`
2. Add features to the script
3. Export STL and render preview
4. Self-review: Are all features visible? Do booleans look clean? Are holes in the right positions?
5. `update_ui("phase2", "Phase 2 — Features", "Features complete — waiting for feedback", parameters=PARAMS, ...)`
6. **Show the preview to the user:** "I've added [list features]. Anything to change before I finalize?"
7. Wait for feedback. Iterate if needed.

### Step 7: Structural Reinforcement Pass

After Phase 2 features are done, before Phase 3 finishing, run a structural analysis and reason through the Structural Rules table.

```python
update_ui("structural", "Structural Check", "Running structural reinforcement analysis...", parameters=PARAMS, ...)
```

```python
import trimesh, numpy as np
tm = trimesh.load("model.stl", force="mesh")
hull_vol = tm.convex_hull.volume
fill_ratio = abs(tm.volume) / hull_vol if hull_vol > 0 else 0
dot_z = np.dot(tm.face_normals, [0, 0, 1])
steep = (dot_z < -np.sin(np.radians(45))).sum()
print(f"Fill ratio: {fill_ratio:.2f} ({'thin-walled' if fill_ratio < 0.25 else 'adequate'})")
print(f"Steep overhangs >45°: {steep} faces")
print(f"Bounding box: {tm.extents[0]:.1f}×{tm.extents[1]:.1f}×{tm.extents[2]:.1f}mm")
```

Then reason through the Structural Rules:
- Any cantilever > 25mm? Add gusset.
- Any sharp interior corners under load? Add fillet r ≥ 0.5mm.
- Any wall < 1.5mm carrying load? Bump to 2.0mm or add rib.
- Load perpendicular to layer lines? Reorient or add ribs.
- Tall narrow part (H > 5× base)? Plan for 5mm brim.
- Snap arm root: wall behind arm ≥ 2× arm root thickness?

Fix issues, re-export, re-run the check. Only proceed to Phase 3 when the analysis is clean.

```python
update_ui("phase3", "Phase 3 — Finish", "Structural check passed — applying final finish...", parameters=PARAMS, ...)
```

### Step 8: Phase 3 — Final Delivery

Apply finishing touches, run slicer verification, and deliver.

1. Add fillets/chamfers (largest radius first, apply after shell, before cuts into the body)
2. Export final STL and render preview
3. Run the full self-review checklist (see Output Checklist at the bottom)
4. Fix any issues found, re-export if needed

```python
update_ui("slicer", "Slicer Verification", "Slicing model headlessly...", parameters=PARAMS, ...)
```

**Run Slicer Verification:**

Generate a slice profile:
```python
# write_profile.py
import configparser

def write_slice_profile(path, material="PLA", layer_h=0.2, nozzle=0.4,
                        walls=2, infill=15, supports=False):
    c = configparser.ConfigParser()
    c["print"] = {
        "layer_height":          str(layer_h),
        "perimeters":            str(walls),
        "fill_density":          f"{infill}%",
        "fill_pattern":          "gyroid",
        "support_material":      "1" if supports else "0",
        "support_material_auto": "1" if supports else "0",
    }
    c["filament"] = {
        "filament_type":  material,
        "nozzle_diameter": str(nozzle),
    }
    with open(path, "w") as f:
        c.write(f)

write_slice_profile("slice_profile.ini",
    material=MATERIAL, layer_h=LAYER_H,
    walls=WALLS, infill=INFILL, supports=SUPPORTS)
```

Slice and parse:
```bash
PSLICER="/Applications/PrusaSlicer.app/Contents/MacOS/prusa-slicer"
$PSLICER \
  --load slice_profile.ini \
  --export-gcode \
  --output model_sliced.gcode \
  model.stl 2>&1
```

```python
import re, pathlib

gcode = pathlib.Path("model_sliced.gcode").read_text(errors="ignore")

def extract(pattern, text, default="unknown"):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else default

time_str    = extract(r"; estimated printing time \(normal mode\) = (.+)", gcode)
filament_g  = extract(r"; total filament used \[g\] = ([\d.]+)", gcode)
filament_mm = extract(r"; total filament used \[mm\] = ([\d.]+)", gcode)
support_g   = extract(r"; total support material used \[g\] = ([\d.]+)", gcode, "0")
layers      = len(re.findall(r"^;LAYER_CHANGE", gcode, re.MULTILINE))

try:
    support_pct = float(support_g) / float(filament_g) * 100
except (ValueError, ZeroDivisionError):
    support_pct = 0.0

print(f"Print time:     {time_str}")
print(f"Filament:       {filament_g}g  ({float(filament_mm)/1000:.1f}m)")
print(f"Support:        {support_pct:.1f}% of total filament")
print(f"Layer count:    {layers}")
```

**Interpret and act:**

| Finding | Threshold | Action |
|---|---|---|
| Support volume | > 25% | Redesign orientation or add chamfers to eliminate |
| Support volume | > 50% | Hard stop — do not deliver; redesign first |
| Print time | > 8 hours | Flag to user; offer to split model or reduce infill |
| Filament weight | > 200g | Note material cost; consider hollowing if appropriate |
| Layer count | < 10 | Model may be wrong scale or too flat — verify |

After fixing anything flagged, re-slice and re-parse. Only deliver once the numbers are clean.

```python
# Update UI with slicer results — the UI will show these in the Slicer Report panel
update_ui("delivered", "Delivered", "Print-ready STL delivered.",
          object_name=OBJECT, material=MATERIAL, printer=PRINTER, parameters=PARAMS,
          slicer_report={"time": time_str, "filament_g": filament_g,
                         "support_pct": support_pct, "layers": layers})
```

**Deliver the Complete Package:**

1. **STL file** — named `<descriptive_name>.stl`
2. **Preview image** — 4-view, already generated
3. **Print settings card** — material, layer height, walls, infill, supports, brim

   When to deviate from the baseline (PLA, 0.2mm, 2 walls, 15% gyroid, no supports):
   - Load-bearing brackets/hooks/hinges: bump to 25–40% infill, 3–4 walls; consider PETG over PLA
   - Thin decorative walls or vases: 0 infill, vase mode or 1 wall
   - Tall narrow parts: add a brim for bed adhesion
   - Flexible parts (gaskets, grips): TPU 95A, 0.2mm layer, slower speed, no supports
   - Outdoor/hot environments: PETG or ASA, not PLA
   - Food/skin contact: call out that FDM parts are not food-safe; recommend food-safe coating

4. **Slicer report** — `~[time] · [weight]g · [support]% · [n] layers`
5. **Orientation** — state explicitly which face goes on the bed and why
6. **Assembly note** if hardware is involved (insert order, screw sizes)
7. **Tweak note** — "Change `wall` on line N to adjust thickness"

**Format:**
```
Print settings: PLA, 0.2mm layer, 2 walls, 15% gyroid infill, no supports.
Orientation: place flat back side on the bed (front face up).
Why: no overhangs above 45°; 15% infill is adequate for a protective shell.
Slicer report (PLA, 0.2mm, 2 walls, 15% infill): ~2h 15m · 18g · no supports · 112 layers.
```

**Always present the key parameters as a summary table after delivery and offer to tweak:**
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

Only include parameters the user would plausibly want to change. Skip internal constants. Group logically: dimensions first, then structural, then tolerances.

---

## Mode B: STL Reference

When the user provides an existing STL to **modify** or use as **inspiration**, follow this workflow before writing any new geometry.

### Step 1: Identify the Mode

Ask the user (or infer from context) which mode they're in:

- **Modify** — "make this taller", "add a hole here", "change the wall thickness": goal is a new part that is functionally the same shape with targeted changes.
- **Inspire** — "I like the general shape but want my own version", "use this as a reference for dimensions": extract what's useful, then design fresh.

When the user provides a reference STL, also add these questions to the normal requirements flow:
- **What do you want to change?** (specific features, dimensions, functionality) — get a clear diff from the reference
- **Is the reference the right size, or do you want to rescale?**
- **Should the output be compatible/mate with the original, or is it a standalone redesign?**

### Step 2: Analyze the Reference STL

Run both the renderer and the geometry extractor:

```bash
# Render a multi-view preview so you can visually inspect the shape
python3 preview.py reference.stl reference_preview.png --views multi
```

```python
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
```

**View the preview image** to understand the shape. Note:
- Overall form (box, cylinder, curved shell, assembly)
- Visible features (holes, slots, bosses, snap tabs, ribs)
- Which face is the print bed (usually the largest flat face at Z=0)
- Any asymmetry or chirality

### Step 3: Recover Parameters from Geometry

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

### Step 4: Branch by Mode

**Modify mode:**
1. Recover all key parameters from the reference (Step 3 above)
2. Ask the user to confirm the recovered dimensions before writing code
3. Rebuild the part in CadQuery using those parameters — do NOT try to import the STL directly; rebuild from scratch as a parametric model
4. Apply the requested changes on top of the rebuilt baseline
5. Show a side-by-side comparison: reference_preview.png + new model preview

**Inspire mode:**
1. Extract only the dimensions and proportions relevant to the user's stated goal
2. Describe what you're borrowing ("I'll use the ~62mm width and the 4-hole mounting pattern from the reference")
3. Design the new part freely, referencing those values in PARAMETERS with attribution comments
4. You are not obligated to replicate features the user didn't ask for

### Step 5: Note What Was NOT Recovered

STL is a surface mesh — it contains no feature history, parametric intent, internal structure, or material. Warn the user if:
- The reference has complex organic/sculpted surfaces that are hard to reconstruct exactly
- Wall thickness is ambiguous (open mesh, non-watertight)
- The reference is very high-poly (>100k faces) — recovery will be approximate

---

## Mode C: Overhang Fix

When the user has an existing STL that **fails to print due to overhangs** and wants the geometry fixed (not replaced with slicer supports), use this workflow to surgically fill the gap between overhanging surfaces and the bed.

**Triggers:** "keeps failing at the same spot", "PETG/ASA won't bridge this", "overhang keeps drooping", "can you fill the gap under the overhang", or any request to make an existing STL print without supports.

**Do NOT remove any original geometry.** Only add fill material below overhanging faces.

### Step 1: Identify Print Orientation and Bed Axis

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

### Step 2: Map the Full Overhang Surface with a 2D Ray-Cast Ceiling Grid

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

### Step 3: Build the Fill and Boolean-Union It into the Model

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

### Step 4: Preview and Iterate

Render a 3-view preview with original geometry faint (blue, alpha=0.06) and fill highlighted (orange, alpha=0.9). Show the user and ask:
- Does the fill reach the full overhang area?
- Does it follow the curve correctly at the sides?
- Are there any areas still uncovered?

Iterate on the `x_cap`, grid density, or which overhangs to include based on user feedback.

### Key Rules for Overhang Fix

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

## Mode D: Printability Audit

When the user uploads an STL and asks to check or improve its printability — or as a final gate on any STL you design before delivery — run this audit pipeline.

**Triggers:** "will this print?", "is this printable?", "fix this STL", "check my file", "clean up this mesh", any STL provided without a specific design request, or automatically at Phase 3 of your own designs.

### Step 1: Full Printability Audit

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

### Step 2: Report Findings to the User

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

### Step 3: Auto-Fix Pipeline

Fix issues in this order:

| Issue | Severity | Auto-fix? |
|---|---|---|
| Non-manifold / open mesh | High | Yes — manifold3d repair |
| Steep overhangs > 45° | High | Yes — ray-cast fill + manifold union (see Mode C) |
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
# Then write via binary STL (same pattern as Mode C Step 3)
```

**Overhang fix:** run the full Mode C workflow — ray-cast ceiling grid → manifold3d batch union → union with original mesh → binary STL export.

### Step 4: Orientation Recommendation

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

### Step 5: Deliver the Enhanced STL

- Name it `<original_name>_printable.stl`
- Render a before/after preview (original + fixed side by side if possible)
- State exactly what changed ("filled 38 overhang faces, repaired 3 non-manifold edges")
- Include print settings (see Mode A Complete Delivery Package)

---

## Code Reference

### Script Template

ALWAYS structure scripts like this:

```python
import cadquery as cq

# ============================================================
# PARAMETERS - Edit these to customize the model
# All dimensions in mm. Put ALL values here — no magic numbers
# in geometry code below.
# ============================================================
# Overall dimensions
width = 60.0        # mm - outer width
depth = 40.0        # mm - outer depth
height = 25.0       # mm - outer height

# Wall and structural
wall = 2.0          # mm - wall thickness (min 1.2 for FDM)
floor_t = 1.6       # mm - floor thickness
corner_r = 2.0      # mm - corner fillet radius

# Tolerances (see Design Constants Reference for values by material)
fit_clearance = 0.3 # mm - clearance per side for sliding fit

# Print orientation: flat bottom (Z=0) on bed, open top faces up
# Seam pins to rear-left vertical edge — intentional

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
# tolerance=0.01, angularTolerance=0.1 gives consistent tessellation.
# Defaults produce coarser, wildly variable STL sizes.
cq.exporters.export(result, "output.stl",
                    tolerance=0.01, angularTolerance=0.1)
print(f"Exported: {width}x{depth}x{height}mm")
```

### Preview Recipe

**One-shot (run script + render + parse result as JSON):**
```bash
python3 run_cadquery_model.py model.py --preview --strict
```
This executes `model.py`, finds the STL it wrote, renders the multi-view preview, and emits a JSON result with `success`, `stdout`, `stderr`, `stl`, `preview`, and `watertight`. With `--strict`, a non-watertight mesh is a hard failure. Use this as the default loop: if `success` is false, read the `stderr` field to fix the CadQuery script, then re-run.

**Rendering only (when the STL already exists):**
```bash
python3 preview.py model.stl preview.png --views multi
```

### CadQuery Patterns

**Hollow enclosure (boolean subtraction — preferred over `.shell()`):**
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

**Multi-part models:**
```python
# Export each part separately
cq.exporters.export(body, "enclosure_body.stl")
cq.exporters.export(lid, "enclosure_lid.stl")
```

Name files descriptively so the user knows which part is which.

### Common Pitfalls

- **Hollowing: prefer boolean subtraction over `.shell()`**. `.shell()` is fragile. It fails on tapered bodies, lofted shapes, unions of multiple primitives, and anything with many fillets. Only reach for `.shell()` when the body is a single simple primitive (one `.box()` or `.cylinder()`) with a uniform wall thickness on all sides. If in doubt, use boolean subtraction.
- **Build order: fillet → cut, not cut → fillet**. Apply fillets while the geometry is still a clean primitive. Once you have cut holes/slots/pockets into a body, filleting the resulting edges often fails or produces bad geometry. Same rule for chamfers.
- **Fillet failures**: Apply fillets from largest to smallest radius. **Do not wrap fillets in `try/except` to silently shrink the radius.** A fillet failure means the geometry or the radius is wrong; find the root cause and fix that.
- **Zero-thickness geometry**: Ensure boolean operations don't create infinitely thin walls. Add a small epsilon (0.01mm) when cutting bodies that are meant to pass just through a surface.
- **Coordinate system**: CadQuery centers geometry at origin by default. Use `centered=(True, True, False)` on `.box()` to place the bottom at Z=0 so `.faces("<Z")` is always the print bed.
- **Hole direction**: `.hole()` cuts through the entire part by default. Use `.cboreHole()` or `.cskHole()` for counterbore/countersink.
- **Taper direction**: In `.extrude(taper=angle)`, a **positive** taper angle narrows the shape (draft inward), **negative** flares it outward. This is opposite to what many people expect.
- **Loft is fragile**: `.loft()` fails on many cross-section combinations. Prefer `.extrude(taper=angle)` when transitioning between a shape and a scaled version of itself. Only use `.loft()` when you need to transition between genuinely different profiles (e.g., circle to rectangle).
- **Export errors / non-watertight STL**: If export fails or the preview reports a non-watertight mesh, the geometry is invalid (usually self-intersecting booleans or zero-thickness faces). Fix the cause, don't paper over it. Run `python3 preview.py model.stl --strict` to fail loudly on non-watertight output.

### Export

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

---

## Output Checklist

Before delivering any model, verify:
- [ ] All dimensions are parameterized (no magic numbers in geometry code)
- [ ] Wall thickness >= 1.2mm (structural), >= 0.8mm (decorative)
- [ ] Clearances looked up from Design Constants Reference — not guessed
- [ ] Hardware hole sizes taken from Hardware Database
- [ ] Shrinkage compensation applied if ABS, ASA, or PA-CF
- [ ] Seam placement commented in code
- [ ] Designed for printability (minimal overhangs/supports)
- [ ] Print orientation noted in comments and stated in delivery
- [ ] STL exported and file size is reasonable (not 0 bytes)
- [ ] Script runs without errors
- [ ] Multi-view preview generated and visually inspected
- [ ] Preview shows correct shape, features, and proportions
- [ ] Bounding box dimensions match requirements
- [ ] Structural reinforcement pass completed (fill ratio, steep overhangs checked)
- [ ] Slicer verification run (or noted as unavailable)
- [ ] Both STL and preview PNG delivered to user
