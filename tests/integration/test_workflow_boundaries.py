import os
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QTest

from labelImgPlusPlus import get_main_app
from libs.core.annotation_workflow import AnnotationTool
from libs.core.shape import Shape, ShapeType


def _wait(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def _write_image(path):
    image = QImage(120, 80, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(path))


@pytest.mark.parametrize('shape_type', [
    ShapeType.RECTANGLE,
    ShapeType.POLYGON,
])
def test_navigation_discards_in_progress_geometry_with_status(
        tmp_path, shape_type):
    first, second = tmp_path / 'a.png', tmp_path / 'b.png'
    _write_image(first)
    _write_image(second)
    app, window = get_main_app()
    try:
        assert window.import_dir_images(str(tmp_path))
        if shape_type is ShapeType.POLYGON:
            window.activate_polygon_tool()
        else:
            window.activate_box_tool()
        draft = Shape(shape_type=shape_type)
        draft.add_point(QPointF(5, 5))
        draft.add_point(QPointF(30, 20))
        window.canvas.current = draft

        window.request_next_image()

        assert _wait(app, lambda: window.file_path == str(second))
        assert window.canvas.current is None
        assert window.statusBar().currentMessage() == 'Draft discarded'
        assert window.workflow.snapshot.active_tool is (
            AnnotationTool.POLYGON
            if shape_type is ShapeType.POLYGON
            else AnnotationTool.RECTANGLE)
    finally:
        window.dirty = False
        window.close()


def test_navigation_discards_visible_picker_and_finishes_provisional_state(
        tmp_path):
    first, second = tmp_path / 'a.png', tmp_path / 'b.png'
    _write_image(first)
    _write_image(second)
    app, window = get_main_app()
    try:
        assert window.import_dir_images(str(tmp_path))
        window.activate_box_tool()
        window.canvas.commit_rectangle((5, 5, 30, 25))
        assert window.class_picker.isVisible()
        assert window.workflow.snapshot.provisional

        window.request_next_image()

        assert _wait(app, lambda: window.file_path == str(second))
        assert not window.class_picker.isVisible()
        assert window.canvas.provisional_shape is None
        assert not window.workflow.snapshot.provisional
        assert window.statusBar().currentMessage() == 'Draft discarded'
    finally:
        window.dirty = False
        window.close()


def test_close_file_resets_the_authoritative_workflow_session(tmp_path):
    image_path = tmp_path / 'frame.png'
    _write_image(image_path)
    app, window = get_main_app()
    try:
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        window._active_class_selected('vehicle')
        window.active_class_control.confirm_each.setChecked(True)
        window.activate_polygon_tool()
        window.canvas.commit_polygon(((5, 5), (35, 5), (20, 30)))
        assert window.workflow.snapshot.provisional
        assert window.class_picker.isVisible()

        window.close_file()

        assert window.file_path is None
        assert not window.class_picker.isVisible()
        assert window.canvas.current is None
        assert window.canvas.provisional_shape is None
        assert window.workflow.snapshot.active_class is None
        assert window.workflow.snapshot.active_tool is AnnotationTool.SELECT
        assert not window.workflow.snapshot.provisional
    finally:
        window.dirty = False
        window.close()
