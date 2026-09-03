import os
import shutil

import pytest

from scripts.build_qt_resources import build_resources


@pytest.mark.skipif(shutil.which("pyrcc5") is None, reason="pyrcc5 is unavailable")
def test_resource_build_ignores_source_mtime(tmp_path):
    qrc_path = tmp_path / "resources.qrc"
    source_path = tmp_path / "payload.txt"
    output_path = tmp_path / "resources.py"
    qrc_path.write_text(
        '<RCC version="1.0"><qresource>'
        '<file alias="payload">payload.txt</file>'
        '</qresource></RCC>',
        encoding="utf-8",
    )
    source_path.write_text("stable payload", encoding="utf-8")

    os.utime(str(source_path), (1_000_000_000, 1_000_000_000))
    build_resources(qrc_path, output_path)
    first_build = output_path.read_bytes()

    os.utime(str(source_path), (1_500_000_000, 1_500_000_000))
    build_resources(qrc_path, output_path)

    assert output_path.read_bytes() == first_build
