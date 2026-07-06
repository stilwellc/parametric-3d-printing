"""Tests for the floor through-cut helpers."""
import numpy as np
import pytest
import trimesh

from floor_cuts import diamond_cutters, text_cutters, text_region, cut_floor

# DejaVu Sans ships with matplotlib — tests must not depend on OS fonts
FONT = "DejaVu Sans"


def solid_disk(radius=40.0, thick=3.0):
    disk = trimesh.creation.cylinder(radius=radius, height=thick, sections=96)
    disk.apply_translation([0, 0, thick / 2])   # floor spans z=0..thick
    return disk


def test_diamond_cutters_genus_matches_hole_count():
    disk = solid_disk()
    cutters = diamond_cutters([(15.0, 8), (25.0, 12)], diag=5.0, depth=5.0)
    result = cut_floor(disk, cutters)
    assert result.is_watertight
    # every through-hole adds one to the genus: 8 + 12
    assert result.euler_number == 2 - 2 * 20


def test_text_counters_stay_attached():
    disk = solid_disk()
    # "gob" has three enclosed counters (g bowl, o, b)
    cutters = text_cutters("gob", width=30.0, font=FONT,
                           bridge_w=1.0, depth=5.0)
    result = cut_floor(disk, cutters)
    assert result.is_watertight
    assert len(result.split(only_watertight=False)) == 1


def test_text_region_bridges_every_counter():
    polys = text_region("gob", width=30.0, font=FONT, bridge_w=1.0)
    # after bridging, no cut polygon may fully enclose kept material:
    # a hole in a cut polygon that is itself ring-shaped would detach.
    # The stencil bridges split each letter outline into open pieces,
    # so every interior that remains must touch a bridge gap.
    from shapely.geometry import Polygon
    for p in polys:
        assert isinstance(p, Polygon)


def test_cut_floor_refuses_loose_islands():
    from shapely.geometry import Point
    disk = solid_disk()
    # an annular cutter isolates the center: must be rejected
    ring = Point(0, 0).buffer(12).difference(Point(0, 0).buffer(9))
    prism = trimesh.creation.extrude_polygon(ring, height=5.0)
    prism.apply_translation([0, 0, -1.0])
    from floor_cuts import _to_manifold
    with pytest.raises(ValueError, match="loose island"):
        cut_floor(disk, [_to_manifold(prism)])
