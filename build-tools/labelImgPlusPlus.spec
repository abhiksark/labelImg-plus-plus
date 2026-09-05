# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys


ROOT = Path(SPECPATH).resolve().parent
MACOS_ICON = ROOT / "libs" / "assets" / "icons" / "app.icns"

analysis = Analysis(
    [str(ROOT / "labelImgPlusPlus.py")],
    pathex=[str(ROOT), str(ROOT / "libs")],
    binaries=[],
    datas=[
        (str(ROOT / "libs" / "assets"), "libs/assets"),
        (str(ROOT / "libs" / "data"), "libs/data"),
    ],
    hiddenimports=[
        "xml",
        "xml.etree",
        "xml.etree.ElementTree",
        "lxml.etree",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "PyQt4", "PyQt5", "PySide2", "PySide6",
        "av", "cv2", "numpy", "onnxruntime",
        "torch", "torchvision", "sam2", "psutil",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="labelImgPlusPlus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(MACOS_ICON) if sys.platform == "darwin" else None,
)
