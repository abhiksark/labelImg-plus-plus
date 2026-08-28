"""Controller, selection, visibility, and undo coverage for one object list."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import MainWindow
from libs.core.shape import Shape, ShapeType
from libs.widgets.annotationInspector import AnnotationRoles


def _shape(label, shape_type=ShapeType.RECTANGLE):
    shape = Shape(label, shape_type=shape_type)
    shape.add_point(QPointF(10, 10))
    shape.add_point(QPointF(40, 40))
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


def test_image_selection_is_guarded_and_identity_based(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    first = _shape('car')
    second = _shape('road', ShapeType.POLYGON)
    try:
        window.canvas.shapes.extend((first, second))
        window.add_label(first)
        window.add_label(second)
        first_id = window.annotation_model.identity_for_shape(first)
        second_id = window.annotation_model.identity_for_shape(second)

        window._select_annotation_identity(first_id)
        QApplication.processEvents()
        assert window.canvas.selected_shape is first

        window.canvas.select_shape(second)
        QApplication.processEvents()
        assert window.current_annotation_identity() == second_id
        assert window.annotation_model.data(
            window.annotation_model.index_for_identity(second_id),
            AnnotationRoles.Selected) is True
    finally:
        _close(window)


def test_image_edits_visibility_and_undo_use_canonical_shape(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    shape = _shape('car')
    try:
        window.canvas.shapes.append(shape)
        window.add_label(shape)
        identity = window.annotation_model.identity_for_shape(shape)
        index = window.annotation_model.index_for_identity(identity)
        window._select_annotation_identity(identity)

        assert window.annotation_model.setData(index, 'vehicle', Qt.EditRole)
        assert shape.label == 'vehicle'
        window.undo_action()
        assert shape.label == 'car'

        window.diffc_button.setChecked(True)
        assert shape.difficult is True
        window.undo_action()
        assert shape.difficult is False

        assert window.annotation_model.setData(
            index, Qt.Unchecked, Qt.CheckStateRole)
        assert window.canvas.isVisible(shape) is False

        old_color = shape.line_color
        window.color_dialog.getColor = lambda *_args, **_kwargs: QColor(1, 2, 3)
        window.choose_shape_line_color()
        assert shape.line_color == QColor(1, 2, 3)
        window.undo_action()
        assert shape.line_color == old_color
    finally:
        _close(window)


def test_difficult_is_enabled_only_for_an_editable_selection(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert not window.diffc_button.isEnabled()
        window.diffc_button.setChecked(True)
        window.shape_selection_changed(False)
        assert not window.diffc_button.isEnabled()
        assert not window.diffc_button.isChecked()

        shape = _shape('crate')
        window.canvas.shapes.append(shape)
        window.add_label(shape)
        window.canvas.select_shape(shape)
        window.shape_selection_changed(True)
        assert window.diffc_button.isEnabled()
    finally:
        _close(window)
