#!/usr/bin/env python3
"""Build PyQt resources without embedding source-file mtimes."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import List, Tuple
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
FIXED_MTIME = 946684800  # 2000-01-01T00:00:00Z


def build_resources(
        qrc_path: Path,
        output_path: Path,
        compiler: str = "pyrcc5") -> None:
    qrc_path = Path(qrc_path).resolve()
    output_path = Path(output_path).resolve()
    qrc_root = qrc_path.parent
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        raise RuntimeError("{} was not found on PATH".format(compiler))

    tree = ElementTree.parse(str(qrc_path))
    source_paths: List[Tuple[Path, Path]] = []
    for file_element in tree.getroot().iter("file"):
        source_name = (file_element.text or "").strip()
        if not source_name:
            raise ValueError("resources.qrc contains an empty <file> entry")
        source_path = (qrc_root / source_name).resolve()
        try:
            relative_path = source_path.relative_to(qrc_root)
        except ValueError:
            raise ValueError(
                "resource source is outside the qrc directory: {}".format(
                    source_name
                )
            )
        if not source_path.is_file():
            raise FileNotFoundError(str(source_path))
        source_paths.append((source_path, relative_path))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
            prefix=".qt-resources-", dir=str(output_path.parent)) as temporary:
        stage = Path(temporary)
        staged_qrc = stage / qrc_path.name
        _ = shutil.copyfile(str(qrc_path), str(staged_qrc))
        os.utime(str(staged_qrc), (FIXED_MTIME, FIXED_MTIME))

        for source_path, relative_path in source_paths:
            staged_source = stage / relative_path
            staged_source.parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copyfile(str(source_path), str(staged_source))
            os.utime(str(staged_source), (FIXED_MTIME, FIXED_MTIME))

        staged_output = stage / output_path.name
        _ = subprocess.run(
            [compiler_path, "-o", str(staged_output), staged_qrc.name],
            cwd=str(stage),
            check=True,
        )
        os.replace(str(staged_output), str(output_path))


def main() -> int:
    try:
        build_resources(
            ROOT / "resources.qrc",
            ROOT / "libs" / "resources.py",
        )
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print("failed to build Qt resources: {}".format(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
