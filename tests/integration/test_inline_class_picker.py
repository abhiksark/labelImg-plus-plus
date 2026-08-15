from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtTest import QTest

from labelImgPlusPlus import get_main_app
from libs.core.sam_types import SamResult
from libs.core.shape import Shape, ShapeType
from libs.core.video_types import DocumentKind


def _prepare_image(window, tmp_path):
    window.reset_state()
    window.single_class_mode.setChecked(False)
    window.use_default_label_checkbox.setChecked(False)
    image_path = str(tmp_path / 'picker.png')
    image = QImage(160, 120, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(image_path)
    window.file_path = image_path
    window.image = image
    window._set_document_kind(DocumentKind.IMAGE)
    window.canvas.load_pixmap(QPixmap.fromImage(image))
    window.canvas.setEnabled(True)
    window.toggle_actions(True)
    window.set_clean()
    window.activate_box_tool()


def _finalise_rectangle(window, x=10, y=10):
    shape = Shape(shape_type=ShapeType.RECTANGLE)
    for point in ((x, y), (x + 30, y),
                  (x + 30, y + 20), (x, y + 20)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()
    return shape


def _enter_class(window, text):
    window.class_picker.edit.setText(text)
    QTest.keyClick(window.class_picker.edit, Qt.Key_Return)


def test_image_geometry_is_provisional_until_enter_and_undo_is_single_step(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        shape = _finalise_rectangle(window)
        app.processEvents()

        assert window.canvas.provisional_shape is shape
        assert window.canvas.shapes == []
        assert window.annotation_model.rowCount() == 0
        assert not window.dirty
        assert not window.undo_stack.can_undo()
        assert window.class_picker.isVisible()
        hint = window.workspace_pages.canvas_chrome.annotation_session_hint
        assert hint.text() == 'Name this box'
        assert 'Enter confirms' in hint.toolTip()
        assert window.actions.primary.text() == 'Name object first'
        assert not window.actions.primary.isEnabled()
        assert window.inspector_context_card.eyebrow.text() == \
            'CLASSIFY OBJECT'
        assert window.inspector_context_card.title.text() == 'Name this box'

        _enter_class(window, 'delivery van')
        app.processEvents()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == [shape]
        assert shape.label == 'delivery van'
        assert window.annotation_model.rowCount() == 1
        assert window.dirty
        assert window.undo_stack.can_undo()
        # Annotation is a sustained session: confirming one box keeps Box
        # armed so the next gesture can create another object immediately.
        assert window.actions.create.isChecked()
        assert window.canvas.mode == window.canvas.CREATE
        assert window.canvas.selected_shape is shape
        assert window.canvas.hasFocus()
        assert hint.text() == 'Box stays active'
        assert window.actions.primary.isEnabled()
        assert window.inspector_context_card.eyebrow.text() == \
            'ANNOTATION SESSION'
        assert window.inspector_context_card.title.text() == \
            'Continuous boxes'
        assert not window.use_default_label_container.isHidden()

        second = _finalise_rectangle(window, 55, 10)
        app.processEvents()
        assert window.canvas.provisional_shape is second
        assert window.class_picker.isVisible()
        _enter_class(window, 'forklift')
        app.processEvents()
        assert [item.label for item in window.canvas.shapes] == [
            'delivery van', 'forklift']
        assert window.actions.create.isChecked()

        window.undo_action()
        assert window.canvas.shapes == [shape]
        assert window.annotation_model.rowCount() == 1
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_escape_discards_provisional_shape_without_document_mutation(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        _finalise_rectangle(window)
        QTest.keyClick(window.class_picker.edit, Qt.Key_Escape)
        app.processEvents()

        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert window.annotation_model.rowCount() == 0
        assert not window.dirty
        assert not window.undo_stack.can_undo()
        assert window.actions.create.isChecked()
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_default_and_single_class_modes_bypass_after_required_confirmation(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.use_default_label_checkbox.setChecked(True)
        window.default_label = 'dog'
        _finalise_rectangle(window)
        assert [shape.label for shape in window.canvas.shapes] == ['dog']
        assert not window.class_picker.isVisible()

        window.use_default_label_checkbox.setChecked(False)
        window.single_class_mode.setChecked(True)
        window._session_last_class = None
        _finalise_rectangle(window, 50, 10)
        assert window.class_picker.isVisible()
        _enter_class(window, 'car')
        app.processEvents()
        _finalise_rectangle(window, 90, 10)
        app.processEvents()
        assert [shape.label for shape in window.canvas.shapes] == [
            'dog', 'car', 'car']
        assert not window.class_picker.isVisible()
        assert window.actions.create.isChecked()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_document_reset_cancels_picker_and_drops_only_provisional_geometry(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        _finalise_rectangle(window)
        assert window.class_picker.isVisible()
        assert window.canvas.provisional_shape is not None

        window.reset_state()
        app.processEvents()
        assert not window.class_picker.isVisible()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert not window.dirty
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_sam_picker_escape_discards_result_without_mutation(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.sam_output_mode = 'polygon'
        result = SamResult(
            polygon=((10.0, 10.0), (80.0, 10.0), (80.0, 60.0)),
            bounds=(10.0, 10.0, 81.0, 61.0))
        window.sam_controller._on_finished(
            window.sam_controller._gen, result, None)
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.isVisible()

        QTest.keyClick(window.class_picker.edit, Qt.Key_Escape)
        app.processEvents()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert window.annotation_model.rowCount() == 0
        assert not window.dirty
        assert not window.undo_stack.can_undo()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()
