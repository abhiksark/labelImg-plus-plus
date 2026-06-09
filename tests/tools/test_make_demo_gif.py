# tests/tools/test_make_demo_gif.py
"""Tests for the pure helpers in the demo-GIF generator.

The choreography itself drives Qt and produces a media artifact, so it is not
unit-tested (validated by eyeballing the GIF). These tests cover the two
deterministic helpers: QPixmap->PIL conversion and GIF assembly.
"""

import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, 'scripts'))

import pytest

# Pillow is a maintainer-only dependency for the demo-GIF tooling, not a
# labelImg++ runtime dependency, so it is absent from CI. Skip rather than fail.
pytest.importorskip("PIL")
from PIL import Image

import make_demo_gif


def test_assemble_gif_writes_animated_file(tmp_path):
    frames = [
        Image.new('RGB', (200, 120), (220, 30, 30)),
        Image.new('RGB', (200, 120), (30, 220, 30)),
        Image.new('RGB', (200, 120), (30, 30, 220)),
    ]
    out = str(tmp_path / 'out.gif')
    make_demo_gif.assemble_gif(frames, out, fps=10, width=100)

    assert os.path.isfile(out)
    with Image.open(out) as gif:
        assert gif.format == 'GIF'
        assert gif.width == 100          # scaled to requested width
        assert gif.height == 60          # aspect preserved (120 * 100/200)
        assert getattr(gif, 'is_animated', False)
        assert gif.n_frames == 3


def test_assemble_gif_rejects_empty():
    try:
        make_demo_gif.assemble_gif([], 'unused.gif')
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty frame list")


def test_qpixmap_to_pil_preserves_size_and_color():
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QImage, QPixmap, QColor

    app = QApplication.instance() or QApplication([])
    img = QImage(8, 5, QImage.Format_RGB32)
    img.fill(QColor(200, 40, 60))
    pil = make_demo_gif.qpixmap_to_pil(QPixmap.fromImage(img))

    assert pil.size == (8, 5)
    assert pil.mode == 'RGB'
    assert pil.getpixel((0, 0)) == (200, 40, 60)
