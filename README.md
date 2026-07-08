<h1 align="center">text2print</h1>

<p align="center"><em>Describe a thing. Get a print-ready STL.</em></p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm%20Noncommercial-8a7248" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10–3.12-e8a33d" alt="Python 3.10–3.12">
  <img src="https://img.shields.io/badge/Claude%20Code-skill-d9a05b" alt="Claude Code skill">
</p>

<p align="center">
  <img src="docs/live_ui.png" alt="The text2print live studio: model on a print plate, phase pipeline, and an approval gate awaiting your decision" width="920">
</p>

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skill that turns a sentence into a manufacturable object. Claude researches real-world dimensions, builds the part parametrically in [CadQuery](https://cadquery.readthedocs.io/) — or procedural mesh code when the geometry demands it — verifies it structurally, slices it headlessly, and delivers an STL with exact print settings. You watch the whole thing take shape in a live browser studio, and nothing moves past a design checkpoint until you approve it.

---

## How it works

text2print picks one of four modes from what you ask:

| Mode | You say… | What happens |
|------|----------|--------------|
| **New Design** | "Design me a…" | Requirements → repo search → design brief → phased build → structural check → slicer verification → delivery |
| **STL Reference** | *attach an STL* | Analyzes the mesh, recovers dimensions, then modifies it or designs from its DNA |
| **Overhang Fix** | "It keeps failing at the overhang" | Ray-cast ceiling map + manifold boolean fill — overhangs removed without slicer supports |
| **Printability Audit** | "Will this print?" | Watertight check, overhang detection, wall analysis, auto-repair, orientation recommendation |

Nothing is guessed along the way:

- **Reference tables built in** — material profiles (PLA / PETG / ABS / ASA / TPU / PA-CF), clearance and press fits, snap-fit arm geometry, living hinges, heat-insert and screw dimensions, SBC mounting patterns, magnet pockets
- **Repo search first** — MakerWorld, Printables, Thingiverse, Cults3D, and MyMiniFactory are checked before designing from scratch
- **Structural pass before delivery** — fill ratio, steep overhangs, wall thickness, and cantilever rules per material
- **Slicer verification** — headless PrusaSlicer reports time, filament, and support volume; more than 25% support means redesign, not delivery

Every delivery ends with settings you can drop straight into your slicer:

```
Print settings: PLA, 0.4mm layer, 2 walls, 0% infill, vase mode off, no supports.
Orientation: flat base on bed. Outer wall ≤30mm/s, fan 100%.
Slicer report: ~2h 20m · 165g · no supports · 150 layers.
```

---

## You approve every phase

The differentiator: **four verification gates**. At the design brief, the base shape, the features pass, and the final review, Claude stops, raises an **Approve / Request changes** banner in the live studio, and waits. Type a note like *"make it feel more textured for the fat lines"* and the design iterates before a single layer is wasted. A background watcher delivers your click the moment you make it — no typing required.

| Gate | You're approving |
|------|------------------|
| `design-brief` | The plan, before any geometry exists |
| `phase-1-base` | Proportions of the raw body |
| `phase-2-features` | Textures, cutouts, mounts — the design itself |
| `final-review` | Structural + slicer results, before the STL ships |

---

## The live studio

```bash
source .venv/bin/activate
python3 tools/ui_server.py     # serves + auto-opens http://localhost:7384
```

A single-file Flask + Three.js app that watches the working directory and streams every change to the browser:

- **The model, live** — each exported STL appears on a 256mm print plate under studio lighting, with real dimensions and triangle count; orbit, auto-rotate, wireframe
- **Approval banner** — the verification gates, answerable in one click, with a note box for change requests
- **Pipeline rail** — the ten design phases with live progress
- **Renders gallery** — every preview image, in a lightbox
- **Parameters, slicer report, activity log** — the numbers behind the shape
- **File history** — every STL iteration with size and age; click any to reload it, or download directly

---

## The texture library

Reusable, tested fabric generators live in `textures/` — this is where text2print goes beyond boxes and brackets.

**Printed fabric walls** (`textures/zigzag_fabric.py`) — walls that are light, airy, and open: a thin shell whose contour changes *per print layer*, quantized exactly to layer height, so the slicer itself weaves the pattern. Three stitches ship, plus an escape hatch:

- `zigzag` — crisscross triangle fins, open diamond windows
- `domes` — stockinette-style rounded stitch bumps in offset rows
- `wave` — mirrored sine strands that cross into eye-shaped windows
- …or pass a **callable** and compose your own — two-scale gradients, morphs, panel mixes

```python
from textures.presets import fabric_preset
from textures.zigzag_fabric import fabric_solid

p = fabric_preset(0.4, diameter=200, stitch="wave", rim_loops=True)
tm = fabric_solid(profile_fn, height=60.0, **p["fabric"])
print(p["print"])   # the exact slicer settings card
```

**Nozzle presets** (`textures/presets.py`) — every number that must scale together, in one call:

| Nozzle | Layer | Zigzag diamonds | Wave length | Character |
|--------|-------|-----------------|-------------|-----------|
| 0.2mm | 0.1mm | 3.6mm | 3.6mm | Lace |
| 0.4mm | 0.2mm | 7.0mm | 6.0mm | Classic |
| 0.6mm | 0.3mm | 9.5mm | 8.0mm | Bold |
| 0.8mm | 0.4mm | 12mm | 10mm | Chunky basket |

**Floor cutouts** (`textures/floor_cuts.py`) — perforate the solid floor to match the walls: crisscross **diamond** rings, **eye-lens** rings (the wave-window shape), and stencil-bridged **through-cut text** — with a hard guard that refuses any cut leaving a loose island to fall off the print bed.

<p align="center">
  <img src="docs/tide_lens_floor.png" alt="Lens-perforated floor — eye-shaped cutouts in concentric crisscross rings" width="460">
  <img src="docs/zigzag_fabric_closeup.png" alt="Printed zigzag fabric wall, macro" width="460">
</p>

<p align="center">
  <img src="docs/tide_bowl_elevation.png" alt="Tide bowl: fine ripple below a separator ring, deep waves above" width="920">
</p>

---

## Quick start

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/stilwellc/text2print ~/.claude/skills/parametric-3d-printing

# Python 3.10–3.12 (CadQuery's OCC kernel has no 3.13+ wheels)
cd ~/.claude/skills/parametric-3d-printing
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Optional: install [PrusaSlicer](https://www.prusa3d.com/page/prusaslicer_424/) for slicer verification (macOS CLI: `/Applications/PrusaSlicer.app/Contents/MacOS/prusa-slicer`). Without it the skill says so and skips that check.

Then just ask, in Claude Code:

```
"Design a parametric enclosure for an Arduino Uno with a snap-fit lid, PETG, Bambu X1C"
"Make me a catch-all bowl with the wave pattern, 0.8mm nozzle, full size"
"Here's my STL — make the top 10mm taller and add a cable slot"
"Will this print?"
```

The skill auto-triggers on requests like these, or invoke it with `/parametric-3d-printing`.

---

## Under the hood

| Path | Purpose |
|------|---------|
| `SKILL.md` | The skill itself: 4-mode workflow, verification gates, design constants, reference tables |
| `tools/ui_server.py` | The live studio (Flask + Three.js), including the approval-gate API |
| `tools/run_cadquery_model.py` | Runs a CadQuery script, renders previews, emits JSON for the self-correct loop |
| `tools/preview.py` | Headless STL → multi-view PNG renderer; `--strict` fails on non-watertight meshes |
| `tools/stl_to_3mf.py` · `tools/mesh_io.py` | 3MF conversion · validated STL loading (pyrender-free) |
| `textures/` | Fabric generators, nozzle presets, floor cutouts — all tested |
| `tests/` | 40-test pytest suite: watertightness, genus accounting, island guards, preset matrix |
| `docs/` | Renders and the design-review checklist |

Everything geometric ships watertight and single-body, or it doesn't ship: the generators verify `is_watertight`, floor cuts refuse loose islands, and the test suite locks known-good bowls to their exact preset numbers.

---

## License

[PolyForm Noncommercial 1.0.0](LICENSE) — free to use, modify, and distribute for noncommercial purposes.

Built on [cad-skill](https://github.com/flowful-ai/cad-skill) by [Nicolas Chourrout](https://github.com/nchourrout).
