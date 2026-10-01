"""Runs tests/blender/run_in_blender.py inside a real Blender, if one is available.

Set NODEBRIDGE_BLENDER to a Blender executable (4.2+) to enable. These
tests drive the add-on's real operators; the rest of the suite is pure
Python and does not need Blender.
"""

import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _blenders():
    found = []
    if os.environ.get("NODEBRIDGE_BLENDER"):
        found.extend(os.environ["NODEBRIDGE_BLENDER"].split(os.pathsep))
    elif shutil.which("blender"):
        found.append(shutil.which("blender"))
    return [path for path in found if path and pathlib.Path(path).exists()]


@pytest.mark.parametrize("blender", _blenders() or [pytest.param(None, marks=pytest.mark.skip(reason="set NODEBRIDGE_BLENDER to run Blender integration tests"))])
def test_addon_operators_inside_blender(blender, tmp_path):
    env = dict(os.environ, BLENDER_USER_RESOURCES=str(tmp_path / "user"))
    zip_path = subprocess.run(["python3", str(ROOT / "tools" / "build_addon.py"), str(tmp_path / "dist")], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run([blender, "--command", "extension", "install-file", "--repo", "user_default", "--enable", zip_path], check=True, capture_output=True, env=env)
    run = subprocess.run(
        [blender, "--background", "--python-exit-code", "1", "--python", str(ROOT / "tests" / "blender" / "run_in_blender.py")],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    assert "loaded from bl_ext.user_default.nodebridge" in run.stdout, run.stdout[-3000:]
    assert run.returncode == 0 and "ALL BLENDER CHECKS PASSED" in run.stdout, run.stdout[-3000:] + run.stderr[-2000:]
