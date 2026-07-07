"""presets.py — nozzle-matched settings for the fabric textures.

One call maps a nozzle size (0.2 / 0.4 / 0.6 / 0.8mm — the Bambu
lineup) to everything that must scale together: layer height (the
geometry is quantized to it), line width, shell thickness, band
rhythm, stitch size, and the print-settings card.

    from textures.presets import fabric_preset
    from textures.zigzag_fabric import fabric_solid

    p = fabric_preset(0.4, diameter=160, stitch="zigzag")
    tm = fabric_solid(profile_r, height, **p["fabric"])
    print(p["print"])   # settings card for the delivery message

Values are tuned, not formulaic — the 0.4 zigzag preset reproduces the
original 200mm bowl fabric; the 0.2 presets reproduce the lace/wave
test cups. The 0.6 presets sit between classic and chunky; 0.8 is a
full basket weave.
"""
import numpy as np

# nozzle -> shared machine numbers
_MACHINE = {
    #        layer_h line_w shell  floor  base_z outer-wall speed
    0.2: dict(layer_h=0.10, line_w=0.25, shell_t=0.50, floor_t=2.4,
              solid_base_z=4.0, speed=40),
    0.4: dict(layer_h=0.20, line_w=0.50, shell_t=1.00, floor_t=3.0,
              solid_base_z=6.0, speed=60),
    0.6: dict(layer_h=0.30, line_w=0.75, shell_t=1.50, floor_t=3.6,
              solid_base_z=7.0, speed=45),
    0.8: dict(layer_h=0.40, line_w=1.00, shell_t=2.00, floor_t=4.0,
              solid_base_z=8.0, speed=35),
}

# nozzle -> zigzag stitch geometry (diamond width mm, swing mm, bands)
_ZIGZAG = {
    0.2: dict(width=3.6,  depth=1.2, zigzag_layers=4, straight_layers=2),
    0.4: dict(width=7.0,  depth=2.0, zigzag_layers=3, straight_layers=2),
    0.6: dict(width=9.5,  depth=2.8, zigzag_layers=3, straight_layers=1),
    0.8: dict(width=12.0, depth=3.5, zigzag_layers=3, straight_layers=1),
}

# nozzle -> domes stitch geometry (stitch width mm, dome mm; band
# height is ~0.8x the stitch width so domes come out roughly round)
_DOMES = {
    0.2: dict(width=2.0, depth=1.0),
    0.4: dict(width=3.5, depth=1.6),
    0.6: dict(width=4.8, depth=2.1),
    0.8: dict(width=6.0, depth=2.6),
}

# nozzle -> wave stitch geometry (wavelength mm, peak-to-peak swing mm;
# each print layer mirrors the sine of the one below)
_WAVE = {
    0.2: dict(width=3.6,  depth=1.4),
    0.4: dict(width=6.0,  depth=2.4),
    0.6: dict(width=8.0,  depth=3.2),
    0.8: dict(width=10.0, depth=4.0),
}


def fabric_preset(nozzle, *, diameter, stitch="zigzag", rim_loops=False):
    """Nozzle-matched kwargs for fabric_solid + a print-settings card.

    nozzle    0.2, 0.4, 0.6, or 0.8 (mm)
    diameter  the part's max diameter (mm) — sets the stitch count
    stitch    "zigzag", "domes", or "wave"
    rim_loops add a crochet cast-off loop band at the rim

    Returns {"fabric": kwargs for fabric_solid, "print": settings card}.
    """
    if nozzle not in _MACHINE:
        raise ValueError(f"no preset for {nozzle}mm nozzle "
                         f"(have {sorted(_MACHINE)})")
    if stitch not in ("zigzag", "domes", "wave"):
        raise ValueError('stitch must be "zigzag", "domes", or "wave"')

    m = _MACHINE[nozzle]
    g = {"zigzag": _ZIGZAG, "domes": _DOMES, "wave": _WAVE}[stitch][nozzle]
    stitches = max(8, round(np.pi * diameter / g["width"]))

    fabric = dict(
        shell_t=m["shell_t"], floor_t=m["floor_t"],
        solid_base_z=m["solid_base_z"], layer_h=m["layer_h"],
        zigzags_around=stitches, zigzag_depth=g["depth"],
        stitch=stitch,
        band_quantize=(stitch == "zigzag" and m["layer_h"] <= 0.1),
        samples_per_zigzag={"zigzag": 4, "domes": 6, "wave": 8}[stitch],
    )
    if stitch == "zigzag":
        fabric["zigzag_layers"] = g["zigzag_layers"]
        fabric["straight_layers"] = g["straight_layers"]
    elif stitch == "domes":
        fabric["zigzag_layers"] = max(4, round(0.8 * g["width"] / m["layer_h"]))
        fabric["straight_layers"] = 0
    else:
        # wave: hold each sine direction for a short band (~0.15x the
        # wavelength, ~4 layers), then mirror. Per-layer flipping
        # collapses into vertical ribs; tall bands read as stacked
        # slabs — the strand look lives in between
        fabric["zigzag_layers"] = max(2, round(0.15 * g["width"] / m["layer_h"]))
        fabric["straight_layers"] = 0
    if rim_loops:
        fabric["rim_loop_h"] = round(0.6 * g["width"], 1)
        fabric["rim_loop_depth"] = g["depth"]
        fabric["rim_loop_period"] = 2.0

    half_period = np.pi * diameter / stitches / 2
    card = dict(
        nozzle=f"{nozzle}mm",
        layer_height=f"{m['layer_h']}mm (MUST match — geometry is "
                     "quantized to it)",
        line_width=f"~{m['line_w']}mm, 2 perimeters",
        infill="0%, no top layers, vase mode OFF",
        bottom_layers=int(round(m["floor_t"] / m["layer_h"])),
        outer_wall_speed=f"<={m['speed']}mm/s, fan 100%",
        supports="none",
        bridge_span=f"{half_period:.1f}mm half-period"
                    if stitch in ("zigzag", "wave") else "n/a (domes ramp)",
    )
    return {"fabric": fabric, "print": card}
