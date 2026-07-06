"""Tests for the printed-fabric wall generator."""
import numpy as np

from textures.zigzag_fabric import fabric_solid, tri01


def small_fabric(**overrides):
    """Coarse, fast fabric cylinder for tests."""
    kwargs = dict(
        shell_t=1.0, floor_t=1.6, solid_base_z=2.4, layer_h=0.4,
        zigzags_around=24, zigzag_depth=1.5,
        zigzag_layers=2, straight_layers=2, samples_per_zigzag=4,
    )
    kwargs.update(overrides)
    return fabric_solid(lambda z: 30.0, 12.0, **kwargs)


def test_tri01_range_and_peaks():
    x = np.linspace(-2, 2, 401)
    y = tri01(x)
    assert y.min() >= 0.0 and y.max() <= 1.0
    assert tri01(0.5) == 1.0
    assert tri01(0.0) == 0.0
    assert tri01(1.0) == 0.0


def test_fabric_solid_watertight_single_body():
    tm = small_fabric()
    assert tm.is_watertight
    assert len(tm.split(only_watertight=False)) == 1
    assert tm.volume > 0


def test_fabric_solid_dimensions():
    tm = small_fabric()
    # width = 2 * (radius + zigzag_depth), flat bottom at z=0
    assert abs(tm.extents[0] - 63.0) < 0.1
    assert abs(tm.extents[2] - 12.0) < 1e-6
    assert abs(tm.bounds[0][2]) < 1e-9


def test_solid_base_band_stays_smooth():
    tm = small_fabric()
    # below solid_base_z no vertex may swing past the profile radius
    v = tm.vertices
    low = v[v[:, 2] < 2.3]
    r = np.linalg.norm(low[:, :2], axis=1)
    assert r.max() < 30.0 + 1e-6
