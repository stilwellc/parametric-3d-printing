# Parametric 3D Printing Skill for Claude Code

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill for generating production-ready 3D-printable models using [CadQuery](https://cadquery.readthedocs.io/). Describe a part, and Claude designs it parametrically, verifies it structurally, slices it headlessly, and delivers a print-ready STL with settings — in one shot.

<p align="center">
  <img src="docs/magsafe_stand_preview.png" alt="MagSafe stand preview, 4 views" width="480">
  <img src="docs/iphone13_pro_case_preview.png" alt="iPhone 13 Pro case preview, 4 views" width="480">
</p>

<p align="center">
  <img src="docs/gridfinity_d110_bin_preview.png" alt="Gridfinity 3x2 bin for Orico D110 label printer" width="640">
</p>

<p align="center">
  <img src="docs/magnet_catch_preview.png" alt="Magnetic door catch (frame side)" width="480">
  <img src="docs/magnet_strike_preview.png" alt="Magnetic door catch (door side)" width="480">
</p>

More examples on [MakerWorld](https://makerworld.com/en/@sercanto).

---

## What it does

The skill handles four modes, selected automatically based on what you ask:

| Mode | Trigger | What happens |
|------|---------|--------------|
| **A — New Design** | "Design me a…" | Full pipeline: requirements → repo search → design brief → phased build → structural check → slicer verification → delivery |
| **B — STL Reference** | Provide an existing STL | Analyzes the file, recovers dimensions, then modifies or uses it as inspiration |
| **C — Overhang Fix** | "This keeps failing at the overhang" | Ray-cast ceiling map + manifold3d boolean fill to eliminate overhangs without supports |
| **D — Printability Audit** | "Will this print?" | Full mesh audit: watertight check, overhang detection, wall analysis, orientation recommendation, auto-repair |

### What "one shot" means in practice

The skill looks up tolerances, hardware dimensions, and structural rules from built-in reference tables before writing any geometry — no guessing. Before delivery, it:

1. Runs a **structural reinforcement pass** — checks fill ratio, steep overhangs, wall thickness, and cantilever lengths against per-material rules
2. Searches **MakerWorld, Printables, Thingiverse, Cults3D, and MyMiniFactory** before building from scratch
3. Writes a **design brief** for you to confirm before any code is written
4. Slices the finished model with **PrusaSlicer CLI** and reports estimated time, filament weight, and support volume — if supports exceed 25%, it redesigns instead of delivering

---

## Installation

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/stilwellc/parametric-3d-printing ~/.claude/skills/parametric-3d-printing
```

### Python dependencies

Requires **Python 3.10–3.12** (CadQuery's OCC kernel has no 3.13+ wheels):

```bash
cd ~/.claude/skills/parametric-3d-printing
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### PrusaSlicer (optional, for slicer verification)

Download from [prusaslicer.com](https://www.prusa3d.com/page/prusaslicer_424/). On macOS the CLI is at:

```bash
/Applications/PrusaSlicer.app/Contents/MacOS/prusa-slicer --version
```

If PrusaSlicer is not installed, the skill skips slicer verification and notes it in the delivery message.

---

## Usage

Once installed, the skill activates in two ways inside Claude Code:

- **Auto-trigger** — describe what you want ("design a wall mount for a Raspberry Pi 4", "I need a snap-fit lid", "this STL has terrible overhangs") and Claude picks up the skill from its trigger keywords.
- **Explicit slash command** — type `/parametric-3d-printing` to invoke it directly.

### Example interactions

```
"Design a parametric enclosure for an Arduino Uno with a snap-fit lid, PETG, Bambu X1C"
→ Design brief + 3-phase build + structural check + slicer report + STL

"Here's my STL — can you make the top 10mm taller and add a cable slot on the left side?"
→ Analyzes geometry, recovers parameters, rebuilds in CadQuery with changes

"This overhang keeps failing at 15mm height even with supports"
→ Ray-cast overhang map + filled geometry + before/after preview

"Will this print? [attaches STL]"
→ Mesh audit report + auto-repair + orientation recommendation
```

---

## Design Constants Built In

The skill ships with reference tables Claude uses automatically — no need to look these up yourself.

### Material profiles

Covers PLA, PETG, ABS, ASA, TPU 95A, and PA-CF with:
- Minimum wall thickness (structural and decorative)
- Maximum unsupported bridge span
- Shrinkage compensation percentage
- Sliding, rotating, and press-fit clearances by material
- Horizontal hole sag correction
- UV resistance and enclosure requirements

### Hardware database

Exact dimensions for:
- **Heat inserts** (Ruthex M2–M5): hole diameter, OD, depth, minimum surrounding wall
- **Screw clearance holes** (M2–M5): through-hole, self-tapping, counterbore
- **SBC mounting patterns**: Raspberry Pi 4/5, Pi Zero 2W, Arduino Uno/Nano, ESP32 DevKit
- **Standard magnets**: N35 disc pocket clearances for 6mm, 8mm, 10mm

### Mechanical fit tables

- Clearance fits: sliding, rotating, print-in-place hinge, loose/rattle-free — per material
- Snap-fit arm geometry: strain-limit formula + quick-reference proportions for PLA/PETG/TPU/Nylon
- Living hinge dimensions (TPU): thickness and bend radius by span
- Print-in-place joint clearances: pin hinges, ball sockets, captive nuts, gears

---

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Complete skill definition: 4-mode workflow, design constants, all reference tables |
| `preview.py` | Headless STL → 4-view PNG renderer (trimesh + pyrender). `--strict` fails on non-watertight. |
| `run_cadquery_model.py` | Runs a CadQuery script, renders preview, emits JSON result for Claude's self-correct loop |
| `mesh_io.py` | STL loading with validation (no pyrender dependency) |
| `stl_to_3mf.py` | STL → 3MF converter for Bambu Studio / PrusaSlicer |
| `design-review.md` | Visual inspection checklist and printability analysis helpers |
| `requirements.txt` | Pinned Python dependency versions |

---

## Delivery format

At the end of a new design session, Claude delivers:

```
Print settings: PETG, 0.2mm layer, 3 walls, 20% gyroid infill, no supports.
Orientation: flat base on bed (open top faces up).
Why: no overhangs above 45°; 3 walls gives adequate snap-fit arm backing.
Slicer report (PETG, 0.2mm, 3 walls, 20% infill): ~3h 40m · 31g · no supports · 184 layers.
```

Plus a parameter summary table and offer to tweak any dimension.

---

## License

Licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). Free to use, modify, and distribute for noncommercial purposes.

---

Originally created by [Nicolas Chourrout](https://github.com/nchourrout) / [Flowful.ai](https://flowlow.ai). Extended with STL analysis modes, overhang fix pipeline, slicer verification, material profiles, hardware database, structural reinforcement pass, and model repository search.
