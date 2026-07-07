"""Tests for the nozzle-matched fabric presets."""
import pytest

from textures.presets import fabric_preset
from textures.zigzag_fabric import fabric_solid


@pytest.mark.parametrize("nozzle", [0.2, 0.4, 0.6, 0.8])
@pytest.mark.parametrize("stitch", ["zigzag", "domes", "wave"])
def test_preset_builds_watertight_fabric(nozzle, stitch):
    p = fabric_preset(nozzle, diameter=40, stitch=stitch)
    # small squat test part keeps every combination fast
    kwargs = dict(p["fabric"])
    kwargs["floor_t"] = min(kwargs["floor_t"], 1.6)
    kwargs["solid_base_z"] = min(kwargs["solid_base_z"], 3.0)
    tm = fabric_solid(lambda z: 20.0, 14.0, **kwargs)
    assert tm.is_watertight
    assert len(tm.split(only_watertight=False)) == 1


def test_preset_matches_known_bowls():
    # the 0.4 zigzag preset reproduces the original 200mm bowl fabric
    p4 = fabric_preset(0.4, diameter=200, stitch="zigzag")["fabric"]
    assert p4["layer_h"] == 0.2 and p4["shell_t"] == 1.0
    assert p4["zigzags_around"] == 90
    assert p4["zigzag_layers"] == 3 and p4["straight_layers"] == 2
    # the 0.2 zigzag preset reproduces the 160mm lace bowl fabric
    p2 = fabric_preset(0.2, diameter=160, stitch="zigzag")["fabric"]
    assert p2["layer_h"] == 0.1 and p2["zigzags_around"] == 140
    assert p2["band_quantize"] is True


def test_preset_rejects_unknown_nozzle():
    with pytest.raises(ValueError, match="no preset"):
        fabric_preset(0.1, diameter=100)


def test_print_card_bottom_layers_cover_floor():
    p = fabric_preset(0.4, diameter=100)
    assert p["print"]["bottom_layers"] == 15   # 3.0mm / 0.2mm
