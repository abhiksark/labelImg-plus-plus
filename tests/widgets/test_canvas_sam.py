import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPointF, QEvent, Qt
from PyQt5.QtGui import QColor, QPixmap, QMouseEvent
from PyQt5.QtWidgets import QApplication

from libs.core.assist_state import AssistPrompt
from libs.core.shape import Shape
from libs.widgets.canvas import Canvas
from libs.core.shape import ShapeType

app = QApplication.instance() or QApplication([])


def _canvas():
    c = Canvas()
    c.load_pixmap(QPixmap(200, 200))
    c.resize(200, 200)
    return c


def test_canvas_names_the_annotation_surface_for_accessibility():
    """Removing the name makes the main editing surface anonymous to AX."""
    c = _canvas()
    assert c.accessibleName() == 'Annotation canvas'


def test_commit_polygon_stages_provisional_polygon_and_emits_new_shape():
    c = _canvas()
    fired = []
    c.newShape.connect(lambda: fired.append(True))
    c.commit_polygon([(10, 10), (100, 10), (100, 100), (10, 100)])
    assert c.shapes == []
    assert c.provisional_shape.shape_type == ShapeType.POLYGON
    assert fired == [True]


def test_commit_polygon_ignores_degenerate_input():
    c = _canvas()
    c.commit_polygon([(10, 10), (20, 20)])     # < 3 points
    assert c.shapes == []


def test_commit_rectangle_stages_tight_provisional_box():
    c = _canvas()
    fired = []
    c.newShape.connect(lambda: fired.append(True))
    c.commit_rectangle((10, 20, 41, 61))
    shape = c.provisional_shape
    assert c.shapes == []
    assert shape.shape_type == ShapeType.RECTANGLE
    assert [(point.x(), point.y()) for point in shape.points] == [
        (10.0, 20.0), (41.0, 20.0), (41.0, 61.0), (10.0, 61.0)]
    assert fired == [True]


def test_commit_rectangle_rejects_zero_area_bounds():
    c = _canvas()
    c.commit_rectangle((10, 10, 10, 20))
    assert c.provisional_shape is None


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


def test_smart_points_refines_positive_and_negative_prompt():
    """Catches point refinement replacing history or losing negative intent."""
    c = _canvas()
    c.scale = 1.0
    prompts = []
    c.assistPrompted.connect(prompts.append)
    c.set_assist_prompt_mode('points')
    c.set_sam_mode(True)

    c.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(20, 30),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    c.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(40, 50),
        Qt.LeftButton, Qt.LeftButton, Qt.AltModifier))
    c.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(60, 70),
        Qt.RightButton, Qt.RightButton, Qt.NoModifier))

    assert prompts == [
        AssistPrompt(mode='points', positive_points=((20.0, 30.0),)),
        AssistPrompt(
            mode='points', positive_points=((20.0, 30.0),),
            negative_points=((40.0, 50.0),)),
        AssistPrompt(
            mode='points', positive_points=((20.0, 30.0),),
            negative_points=((40.0, 50.0), (60.0, 70.0))),
    ]


def test_smart_points_right_release_never_opens_annotation_menu():
    """Catches negative-point release falling into the edit context menu."""
    c = _canvas()
    opened = []

    class RecordingMenu:
        def exec_(self, _position):
            opened.append(True)

    c.menus = (RecordingMenu(), RecordingMenu())
    c.set_assist_prompt_mode('points')
    c.set_sam_mode(True)
    c.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(60, 70),
        Qt.RightButton, Qt.RightButton, Qt.NoModifier))
    c.mouseReleaseEvent(QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(60, 70),
        Qt.RightButton, Qt.NoButton, Qt.NoModifier))

    assert opened == []


def test_smart_box_drag_emits_normalized_image_space_prompt():
    """Catches a Smart Box being submitted as a click or reversed bounds."""
    c = _canvas()
    c.scale = 1.0
    prompts = []
    c.assistPrompted.connect(prompts.append)
    c.set_assist_prompt_mode('box')
    c.set_sam_mode(True)

    c.mousePressEvent(QMouseEvent(
        QEvent.MouseButtonPress, QPointF(90, 80),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
    c.mouseMoveEvent(QMouseEvent(
        QEvent.MouseMove, QPointF(20, 30),
        Qt.NoButton, Qt.LeftButton, Qt.NoModifier))
    c.mouseReleaseEvent(QMouseEvent(
        QEvent.MouseButtonRelease, QPointF(20, 30),
        Qt.LeftButton, Qt.NoButton, Qt.NoModifier))

    assert prompts == [AssistPrompt(
        mode='box', box=(20.0, 30.0, 90.0, 80.0))]
    assert c.assist_box_bounds == (20.0, 30.0, 90.0, 80.0)


def test_assist_preview_is_paint_only_and_clearable():
    """Catches preview publication entering committed or class-pending state."""
    c = _canvas()
    preview = Shape(
        line_color=QColor(20, 160, 240), shape_type=ShapeType.POLYGON)
    for point in ((2, 2), (30, 2), (30, 30)):
        preview.add_point(QPointF(*point))
    preview.close()
    existing_shapes = list(c.shapes)

    c.set_assist_preview(preview)

    assert c.assist_preview_shape is preview
    assert c.shapes == existing_shapes
    assert c.provisional_shape is None
    assert c.current is None
    assert c.clear_assist_preview() is preview
    assert c.assist_preview_shape is None
