# tests/integrations/test_image_convert.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
pytest.importorskip("numpy")

from PyQt5.QtGui import QImage, qRgb
from libs.integrations.image_convert import qimage_to_rgb


def _solid(width, height, r, g, b):
    img = QImage(width, height, QImage.Format_RGB32)
    img.fill(qRgb(r, g, b))
    return img


def test_shape_and_channel_order_is_rgb():
    arr = qimage_to_rgb(_solid(4, 3, 10, 20, 30))
    assert arr.shape == (3, 4, 3)
    assert tuple(arr[0, 0]) == (10, 20, 30)  # R, G, B


def test_non_multiple_of_four_width_handles_stride():
    # width 5 -> 15 bytes/row, padded to a 16-byte stride in RGB888
    arr = qimage_to_rgb(_solid(5, 2, 1, 2, 3))
    assert arr.shape == (2, 5, 3)
    assert tuple(arr[1, 4]) == (1, 2, 3)
