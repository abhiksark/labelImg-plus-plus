# tests/integration/test_class_colors.py
"""A colour chosen for a class must outlive reload, relabel and restart."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from labelImgPlusPlus import MainWindow
from libs.core.shape import Shape
from libs.utils.utils import generate_color_by_text, set_class_colors

RED = QColor(255, 0, 0, 200)


@pytest.fixture(autouse=True)
def _forget_class_colors():
    """Class colours are process-wide; do not leak them into other tests."""
    yield
    set_class_colors(None)


def _shape(label, x=10):
    shape = Shape(label)
    for point in ((x, 10), (x + 30, 10), (x + 30, 40), (x, 40)):
        shape.add_point(QPointF(*point))
    shape.close()
    return shape


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()
    QApplication.processEvents()


def _image(tmp_path):
    image_path = str(tmp_path / 'colors.png')
    image = QImage(200, 100, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    assert image.save(image_path)
    return image_path


def _line_colors(window, label):
    return [shape.line_color for shape in window.canvas.shapes
            if shape.label == label]


def test_class_color_survives_reload_relabel_new_shape_and_restart(
        monkeypatch, tmp_path):
    image_path = _image(tmp_path)
    window = _window(monkeypatch, tmp_path)
    try:
        window.load_file(image_path)
        cars = (_shape('car', 10), _shape('car', 60))
        person = _shape('person', 110)
        for shape in cars + (person,):
            window.canvas.shapes.append(shape)
            window.add_label(shape)
        window.canvas.select_shape(cars[0])

        window.color_dialog.getColor = lambda *_args, **_kwargs: QColor(RED)
        window.choose_shape_line_color()

        # The colour belongs to the class, not to the one selected shape.
        assert _line_colors(window, 'car') == [RED, RED]
        assert person.line_color != RED

        window.set_dirty()
        assert window.save_file()
        window.load_file(image_path)
        assert _line_colors(window, 'car') == [RED, RED]
        assert _line_colors(window, 'person') == [
            generate_color_by_text('person')]

        # Relabelling a shape to the class adopts the class colour.
        relabelled = next(shape for shape in window.canvas.shapes
                          if shape.label == 'person')
        window._annotation_class_edit_requested(
            window.annotation_model.identity_for_shape(relabelled), 'car')
        assert relabelled.line_color == RED

        # So does a newly drawn shape.
        window.canvas.provisional_shape = _shape(None, 150)
        window._pending_provisional_shape = window.canvas.provisional_shape
        window._commit_provisional_shape('car')
        assert _line_colors(window, 'car') == [RED] * 4

        assert window.save_file()
    finally:
        _close(window)

    restarted = _window(monkeypatch, tmp_path)
    try:
        restarted.load_file(image_path)
        assert _line_colors(restarted, 'car') == [RED] * 4
    finally:
        _close(restarted)


def test_restoring_the_generated_color_and_undo_clear_the_override(
        monkeypatch, tmp_path):
    image_path = _image(tmp_path)
    window = _window(monkeypatch, tmp_path)
    generated = generate_color_by_text('car')
    try:
        window.load_file(image_path)
        car = _shape('car')
        window.canvas.shapes.append(car)
        window.add_label(car)
        window.canvas.select_shape(car)
        window.set_dirty()
        assert window.save_file()

        window.color_dialog.getColor = lambda *_args, **_kwargs: QColor(RED)
        window.choose_shape_line_color()
        window.undo_action()
        assert window.save_file()
        window.load_file(image_path)
        assert _line_colors(window, 'car') == [generated]

        # Restore Defaults in the dialog hands back the generated colour.
        window.canvas.select_shape(window.canvas.shapes[0])
        window.choose_shape_line_color()
        assert _line_colors(window, 'car') == [RED]
        window.color_dialog.getColor = (
            lambda *_args, default=None, **_kwargs: QColor(default))
        window.choose_shape_line_color()
        assert window.save_file()
    finally:
        _close(window)

    restarted = _window(monkeypatch, tmp_path)
    try:
        restarted.load_file(image_path)
        assert _line_colors(restarted, 'car') == [generated]
    finally:
        _close(restarted)
