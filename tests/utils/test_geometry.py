import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPointF
from libs.utils.utils import douglas_peucker


def test_collinear_points_collapse_to_endpoints():
    pts = [QPointF(0, 0), QPointF(5, 0), QPointF(10, 0)]
    out = douglas_peucker(pts, epsilon=1.0)
    assert len(out) == 2
    assert (out[0].x(), out[0].y()) == (0, 0)
    assert (out[-1].x(), out[-1].y()) == (10, 0)


def test_corner_is_preserved():
    pts = [QPointF(0, 0), QPointF(5, 5), QPointF(10, 0)]
    out = douglas_peucker(pts, epsilon=1.0)
    assert len(out) == 3
    assert (out[1].x(), out[1].y()) == (5, 5)   # the corner survives simplification
