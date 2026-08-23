# tests/integration/test_inline_class_picker.py
import os
from unittest.mock import MagicMock, patch

import pytest
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QMessageBox, QPushButton

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
    window.actions.galleryMode.setChecked(False)
    window.toggle_gallery_mode(False)
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


def _stage_smart_select(window, result=None):
    window.canvas.set_sam_mode(True)
    result = result or SamResult(
        polygon=((10.0, 10.0), (80.0, 10.0), (80.0, 60.0)),
        bounds=(10.0, 10.0, 81.0, 61.0))
    window.sam_controller._on_finished(
        window.sam_controller._gen, result, None)


def _approve_outline(window):
    button = window.class_picker.findChild(
        QPushButton, 'useOutlineButton')
    QTest.keyClick(button, Qt.Key_Return)


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
        assert window.use_default_label_container.isHidden()
        assert not window.inspector_context_card.class_strategy_combo \
            .isHidden()

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


def test_annotation_session_is_the_only_visible_class_strategy_surface(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.default_label = 'dog'
        window._session_last_class = 'person'
        window._sync_inspector_context()
        card = window.inspector_context_card

        assert window.use_default_label_container.isHidden()
        assert [card.class_strategy_combo.itemText(index)
                for index in range(card.class_strategy_combo.count())] == [
                    'Confirm each', 'Repeat last', 'Fixed class']
        assert card.fixed_class_combo.isHidden()

        card.class_strategy_combo.setCurrentIndex(
            card.class_strategy_combo.findData('repeat'))
        app.processEvents()
        assert window.single_class_mode.isChecked()
        assert not window.use_default_label_checkbox.isChecked()
        assert 'Repeat last · person' in card.detail.text()

        card.class_strategy_combo.setCurrentIndex(
            card.class_strategy_combo.findData('fixed'))
        card.fixed_class_combo.setCurrentIndex(
            card.fixed_class_combo.findText('car'))
        app.processEvents()
        assert window.use_default_label_checkbox.isChecked()
        assert not window.single_class_mode.isChecked()
        assert window.default_label == 'car'
        assert window.default_label_combo_box.cb.currentText() == 'car'
        assert not card.fixed_class_combo.isHidden()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_changing_fixed_class_preserves_dirty_annotation_and_labels_next(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        existing = _finalise_rectangle(window)
        _enter_class(window, 'dog')
        app.processEvents()

        assert window.canvas.shapes == [existing]
        assert existing.label == 'dog'
        assert window.dirty

        card = window.inspector_context_card
        card.class_strategy_combo.setCurrentIndex(
            card.class_strategy_combo.findData('fixed'))
        card.fixed_class_combo.setCurrentIndex(
            card.fixed_class_combo.findText('car'))
        app.processEvents()

        assert window.canvas.shapes == [existing]
        assert window.dirty
        assert card.fixed_class_combo.currentText() == 'car'
        assert window.default_label_combo_box.cb.currentText() == 'car'

        created = _finalise_rectangle(window, 55, 10)
        app.processEvents()
        assert window.canvas.shapes == [existing, created]
        assert [shape.label for shape in window.canvas.shapes] == [
            'dog', 'car']
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_fixed_class_selects_label_created_after_window_construction(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        _finalise_rectangle(window)
        _enter_class(window, 'delivery robot')
        app.processEvents()

        card = window.inspector_context_card
        card.class_strategy_combo.setCurrentIndex(
            card.class_strategy_combo.findData('fixed'))
        card.fixed_class_combo.setCurrentIndex(
            card.fixed_class_combo.findText('delivery robot'))
        app.processEvents()

        assert card.fixed_class_combo.currentText() == 'delivery robot'
        assert window.default_label_combo_box.cb.currentText() == \
            'delivery robot'
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


@pytest.mark.parametrize('transition', (
    'next_image', 'open_source', 'browse', 'reset', 'delete_image',
))
def test_provisional_object_blocks_destructive_image_transitions(
        tmp_path, transition):
    """Removing the shared guard must let one named transition lose work."""
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        current_path = window.file_path
        next_path = str(tmp_path / 'next.png')
        next_image = QImage(160, 120, QImage.Format_RGB32)
        next_image.fill(Qt.black)
        assert next_image.save(next_path)
        window.m_img_list = [current_path, next_path]
        window._path_to_idx = {current_path: 0, next_path: 1}
        window.cur_img_idx = 0
        shape = _finalise_rectangle(window)
        app.processEvents()

        if transition == 'next_image':
            result = window.request_next_image()
        elif transition == 'open_source':
            result = window.request_open_file(next_path)
        elif transition == 'browse':
            result = window.toggle_gallery_mode(True)
        elif transition == 'reset':
            result = window.reset_state()
        else:
            with patch(
                    'labelImgPlusPlus.QMessageBox.warning') as confirm:
                result = window.delete_image()
            confirm.assert_not_called()
        app.processEvents()

        assert result in (None, False)
        assert window.file_path == current_path
        assert window.canvas.provisional_shape is shape
        assert window.class_picker.isVisible()
        assert window.class_picker.edit.hasFocus()
        assert window.workspace_pages.current_page() == 'canvas'
        assert window.statusBar().currentMessage() == \
            window.string_bundle.get_string('provisionalPending')
        assert os.path.exists(current_path)
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_provisional_object_projects_truthful_clean_and_dirty_save_state(
        tmp_path):
    """Dropping the provisional projection must make the bar claim Saved."""
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        _finalise_rectangle(window)
        app.processEvents()
        assert window.command_bar.save_state_label.text() == \
            'Provisional object · not saved'
        assert window.label_save_status.text() == \
            '● Provisional object · not saved'

        window.set_dirty()
        assert window.command_bar.save_state_label.text() == \
            'Unsaved changes · provisional object'
        assert window.label_save_status.text() == \
            '● Unsaved changes · provisional object'
        assert window.canvas.provisional_shape is not None
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_delete_rechecks_provisional_state_after_confirmation(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        image_path = window.file_path

        def confirm(*_args, **_kwargs):
            _stage_smart_select(window)
            return QMessageBox.Yes

        with patch(
                'labelImgPlusPlus.QMessageBox.warning', side_effect=confirm), \
                patch('labelImgPlusPlus.os.remove') as remove:
            assert not window.delete_image()

        remove.assert_not_called()
        assert os.path.exists(image_path)
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.isVisible()
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_classification_hides_controls_for_the_previous_selection(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        first = _finalise_rectangle(window)
        _enter_class(window, 'car')
        app.processEvents()
        assert window.canvas.selected_shape is first
        assert not window.diffc_button.isHidden()

        _finalise_rectangle(window, 60, 10)
        app.processEvents()
        assert window.inspector_context_card.eyebrow.text() == \
            'CLASSIFY OBJECT'
        assert window.diffc_button.isHidden()
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_close_is_ignored_while_provisional_object_needs_resolution(
        tmp_path):
    """Removing the close guard must start shutdown with geometry pending."""
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        shape = _finalise_rectangle(window)
        app.processEvents()
        event = MagicMock()
        with patch.object(window, '_shutdown_workers') as shutdown:
            window.closeEvent(event)

        event.ignore.assert_called_once_with()
        shutdown.assert_not_called()
        assert window.canvas.provisional_shape is shape
        assert window.class_picker.edit.hasFocus()
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_sam_try_again_discards_result_without_mutation(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.sam_output_mode = 'polygon'
        _stage_smart_select(window)
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.isVisible()
        assert window.class_picker.prompt.text() == 'Use this outline?'
        assert window.workspace_pages.canvas_chrome.annotation_session_hint \
            .text() == 'Review this outline'
        assert window.actions.primary.text() == 'Review outline first'
        assert window.inspector_context_card.eyebrow.text() == \
            'REVIEW OUTLINE'
        assert window.inspector_context_card.detail.text() == \
            'Geometry is provisional and not saved yet'
        window._on_provisional_click_blocked()
        app.processEvents()
        assert window.statusBar().currentMessage() == \
            'Use this outline or press Escape to try again'
        use_outline = window.class_picker.findChild(
            QPushButton, 'useOutlineButton')
        assert use_outline.hasFocus()

        try_again = window.class_picker.findChild(
            QPushButton, 'tryAgainButton')
        QTest.mouseClick(try_again, Qt.LeftButton)
        app.processEvents()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert window.annotation_model.rowCount() == 0
        assert not window.dirty
        assert not window.undo_stack.can_undo()
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.actions.sam_mode.isChecked()
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_smart_select_approval_enters_class_stage_and_escape_discards(
        tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        _stage_smart_select(window)

        _approve_outline(window)
        app.processEvents()
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.prompt.text() == 'Choose a class'
        assert window.class_picker.edit.hasFocus()
        assert window.workspace_pages.canvas_chrome.annotation_session_hint \
            .text() == 'Name this polygon'
        assert window.actions.primary.text() == 'Name object first'
        assert window.inspector_context_card.eyebrow.text() == \
            'CLASSIFY OBJECT'
        window._on_provisional_click_blocked()
        assert window.statusBar().currentMessage() == \
            window.string_bundle.get_string('provisionalPending')
        assert window.class_picker.edit.hasFocus()

        QTest.keyClick(window.class_picker.edit, Qt.Key_Escape)
        app.processEvents()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert not window.dirty
        assert not window.undo_stack.can_undo()
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_smart_select_class_click_commits_and_rearms_next_point(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.label_hist = ['vehicle']
        _stage_smart_select(window)
        first = window.canvas.provisional_shape
        _approve_outline(window)
        app.processEvents()

        item = window.class_picker.list_widget.item(0)
        QTest.mouseClick(
            window.class_picker.list_widget.viewport(), Qt.LeftButton,
            pos=window.class_picker.list_widget.visualItemRect(item).center())
        app.processEvents()
        assert window.canvas.shapes == [first]
        assert first.label == 'vehicle'
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.canvas.hasFocus()

        _stage_smart_select(window, SamResult(
            polygon=((20.0, 20.0), (90.0, 20.0), (90.0, 70.0)),
            bounds=(20.0, 20.0, 91.0, 71.0)))
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.prompt.text() == 'Use this outline?'
        assert window.canvas.shapes == [first]
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_smart_select_default_and_repeat_classes_wait_for_review(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.use_default_label_checkbox.setChecked(True)
        window.default_label = 'dog'
        _stage_smart_select(window)
        assert window.canvas.shapes == []
        assert window.class_picker.prompt.text() == 'Use this outline?'
        assert window.class_picker.use_outline_button.text() == \
            'Use outline as dog (Enter)'

        _approve_outline(window)
        app.processEvents()
        assert [shape.label for shape in window.canvas.shapes] == ['dog']
        assert not window.class_picker.isVisible()

        window.use_default_label_checkbox.setChecked(False)
        window.single_class_mode.setChecked(True)
        window._session_last_class = 'car'
        _stage_smart_select(window)
        assert [shape.label for shape in window.canvas.shapes] == ['dog']
        assert window.class_picker.use_outline_button.text() == \
            'Use outline as car (Enter)'
        _approve_outline(window)
        app.processEvents()
        assert [shape.label for shape in window.canvas.shapes] == [
            'dog', 'car']
        assert window.canvas.mode == window.canvas.CREATE_SAM
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_manual_polygon_opens_class_selection_without_outline_review(tmp_path):
    app, window = get_main_app()
    try:
        _prepare_image(window, tmp_path)
        window.activate_polygon_tool()
        shape = Shape(shape_type=ShapeType.POLYGON)
        for point in ((10, 10), (50, 10), (30, 40)):
            shape.add_point(QPointF(*point))
        window.canvas.current = shape
        window.canvas.finalise()
        app.processEvents()

        assert window.canvas.provisional_shape is shape
        assert window.class_picker.prompt.text() == 'Choose a class'
        assert window.class_picker.edit.hasFocus()
        assert window.inspector_context_card.eyebrow.text() == \
            'CLASSIFY OBJECT'
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()
