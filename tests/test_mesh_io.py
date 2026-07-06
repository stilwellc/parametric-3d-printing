import subprocess
import sys

import pytest
import mesh_io

from conftest import REPO_ROOT


def test_load_mesh_valid(tmp_stl):
    tm = mesh_io.load_mesh(str(tmp_stl))
    assert len(tm.vertices) > 0
    assert len(tm.faces) > 0
    assert tm.is_watertight


def test_load_mesh_missing_file(tmp_path):
    with pytest.raises(ValueError, match="Failed to load STL"):
        mesh_io.load_mesh(str(tmp_path / "nope.stl"))


def test_load_mesh_empty_file(tmp_path):
    empty = tmp_path / "empty.stl"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        mesh_io.load_mesh(str(empty))


def test_load_mesh_no_pyrender_import():
    """mesh_io must not pull in pyrender (it's the whole point of the split).

    Checked in a subprocess: this process has already imported pyrender
    via other tests, so sys.modules here proves nothing.
    """
    code = ("import sys, mesh_io; "
            "sys.exit(1 if 'pyrender' in sys.modules else 0)")
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT)
    assert proc.returncode == 0, "importing mesh_io pulled in pyrender"
