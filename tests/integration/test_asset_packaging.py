"""Verify runtime assets survive wheel build and installation."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def _run(command, **kwargs):
    return subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        **kwargs
    )


def test_installed_wheel_resolves_assets_outside_checkout(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    wheelhouse = tmp_path / "wheelhouse"
    target = tmp_path / "installed"
    workdir = tmp_path / "outside-checkout"
    wheelhouse.mkdir()
    workdir.mkdir()
    source.mkdir()
    for name in (
            "pyproject.toml", "setup.cfg", "MANIFEST.in", "README.rst",
            "LICENSE", "labelImgPlusPlus.py"):
        shutil.copy2(root / name, source / name)
    for name in ("libs", "labelimgplusplus", "data"):
        shutil.copytree(
            root / name, source / name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


    _run([
        sys.executable, "-m", "pip", "wheel", "--no-deps",
        "--no-build-isolation", "--wheel-dir", str(wheelhouse), str(source),
    ])
    wheel, = wheelhouse.glob("labelimgplusplus-*.whl")

    with zipfile.ZipFile(wheel) as archive:
        members = set(archive.namelist())
    assert "libs/assets/icons/app.png" in members
    assert "libs/assets/icons/feather/help-circle.svg" in members
    assert "libs/assets/strings/strings.properties" in members
    assert "libs/assets/licenses/feather.txt" in members

    _run([
        sys.executable, "-m", "pip", "install", "--no-deps",
        "--target", str(target), str(wheel),
    ])
    environment = dict(os.environ)
    environment.update({
        "PYTHONPATH": str(target),
        "QT_QPA_PLATFORM": "offscreen",
    })
    process = _run([
        sys.executable, "-c",
        "import labelImgPlusPlus; "
        "raise SystemExit(labelImgPlusPlus.verify_assets([]))",
    ], cwd=workdir, env=environment)
    assert "Verified 44 icons, 4 string bundles, and 1 license." in process.stdout
