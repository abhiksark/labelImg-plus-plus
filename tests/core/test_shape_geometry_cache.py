import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication

from libs.core.shape import Shape
from libs.widgets.canvas import _ShapeSpatialGrid


_APP = QApplication.instance() or QApplication([])


def _shape(x, y):
    shape = Shape('object')
    shape.add_point(QPointF(x, y))
    shape.add_point(QPointF(x + 20, y + 20))
    shape.close()
    return shape


def test_geometry_cache_is_reused_then_invalidated_by_movement():
    shape = _shape(10, 20)
    first_path = shape.make_path()
    first_rect = shape.bounding_rect()

    assert shape.make_path() is first_path
    assert shape.bounding_rect() is first_rect

    shape.move_by(QPointF(5, 7))

    assert shape.make_path() is not first_path
    assert shape.bounding_rect().left() == 15
    assert shape.bounding_rect().top() == 27


def test_spatial_grid_updates_hover_and_axis_alignment_buckets():
    near = _shape(10, 20)
    far = _shape(800, 900)
    grid = _ShapeSpatialGrid(cell_size=256)
    grid.rebuild([near, far])

    assert grid.query(QPointF(15, 25)) == [near]
    assert grid.alignment_candidates(QPointF(11, 700), 5) == [near]

    near.move_by(QPointF(600, 0))
    grid.update(near)

    assert grid.query(QPointF(15, 25)) == []
    assert grid.alignment_candidates(QPointF(11, 700), 5) == []
