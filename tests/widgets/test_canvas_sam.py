import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPointF, QEvent, Qt
from PyQt5.QtGui import QPixmap, QMouseEvent
from PyQt5.QtWidgets import QApplication

from libs.widgets.canvas import Canvas
from libs.core.shape import ShapeType

app = QApplication.instance() or QApplication([])


def _canvas():
    c = Canvas()
    c.load_pixmap(QPixmap(200, 200))
    c.resize(200, 200)
    return c


def test_commit_polygon_creates_polygon_and_emits_new_shape():
    c = _canvas()
    fired = []
    c.newShape.connect(lambda: fired.append(True))
    c.commit_polygon([(10, 10), (100, 10), (100, 100), (10, 100)])
    assert len(c.shapes) == 1
    assert c.shapes[0].shape_type == ShapeType.POLYGON
    assert fired == [True]


def test_commit_polygon_ignores_degenerate_input():
    c = _canvas()
    c.commit_polygon([(10, 10), (20, 20)])     # < 3 points
    assert c.shapes == []


def test_left_click_in_sam_mode_emits_samclicked_in_image_coords():
    c = _canvas()
    c.scale = 1.0
    got = []
    c.samClicked.connect(lambda p: got.append((p.x(), p.y())))
    c.set_sam_mode(True)
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(30, 40),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    c.mousePressEvent(ev)
    assert len(got) == 1
    # The signal must carry image-space coords (transform_pos), not widget coords.
    assert got[0] == (30.0, 40.0)
