# tests/video/test_inline_class_picker.py
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QPushButton

from labelImgPlusPlus import get_main_app
from libs.core.sam_types import SamResult
from libs.core.shape import Shape, ShapeType


def _finalise_rectangle(window):
    shape = Shape(shape_type=ShapeType.RECTANGLE)
    for point in ((10, 10), (40, 10), (40, 30), (10, 30)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()


def test_video_confirmation_creates_manual_anchor_and_undo_removes_track(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'picker.mp4')
    try:
        assert window.open_video(video)
        window.activate_box_tool()
        _finalise_rectangle(window)
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
        assert not window.video_model.dirty

        window.class_picker.edit.setText('car')
        QTest.keyClick(window.class_picker.edit, Qt.Key.Key_Return)
        app.processEvents()
        assert len(window.video_model.tracks) == 1
        observation = next(iter(window.video_model.observations.values()))
        assert observation.source == 'manual'
        assert observation.review_state == 'accepted'
        # Video anchors use the same sustained annotation session as images.
        assert window.actions.create.isChecked()
        assert window.canvas.mode == window.canvas.CREATE
        card = window.inspector_context_card
        assert card.eyebrow.text() == 'SELECTED TRACK'
        assert card.title.text() == 'car'
        assert window.actions.videoPropagateSelected in \
            card.visible_actions()
        more = set(card.more_menu.actions())
        assert {window.actions.videoEditSpan,
                window.actions.videoTrackForward,
                window.actions.videoTrackBackward,
                window.actions.videoDeleteTrack} <= more
        assert not window.workspace_inspector.tabs.isTabVisible(1)

        window.undo_action()
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_video_sam_box_is_provisional_then_commits_as_manual_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'sam-box.mp4')
    try:
        assert window.open_video(video)
        window.canvas.set_sam_mode(True)
        window.sam_output_mode = 'box'
        result = SamResult(
            polygon=((10.0, 10.0), (40.0, 10.0), (40.0, 30.0)),
            bounds=(10.0, 10.0, 41.0, 31.0))
        window.sam_controller._on_finished(
            window.sam_controller._gen, result, None)
        provisional = window.canvas.provisional_shape
        assert provisional is not None
        assert provisional.shape_type == ShapeType.RECTANGLE
        assert window.video_model.tracks == {}
        assert window.class_picker.prompt.text() == 'Use this outline?'

        use_outline = window.class_picker.findChild(
            QPushButton, 'useOutlineButton')
        QTest.keyClick(use_outline, Qt.Key.Key_Return)
        app.processEvents()
        assert window.class_picker.prompt.text() == 'Choose a class'

        window.class_picker.edit.setText('vehicle')
        QTest.keyClick(window.class_picker.edit, Qt.Key.Key_Return)
        app.processEvents()
        track = next(iter(window.video_model.tracks.values()))
        observation = next(iter(window.video_model.observations.values()))
        assert track.shape_type == 'rectangle'
        assert observation.source == 'manual'
        assert observation.review_state == 'accepted'
        assert observation.anchor is True

        window.undo_action()
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_video_smart_select_rejection_leaves_project_and_undo_unchanged(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'sam-reject.mp4')
    try:
        assert window.open_video(video)
        window.canvas.set_sam_mode(True)
        window.sam_output_mode = 'box'
        result = SamResult(
            polygon=((10.0, 10.0), (40.0, 10.0), (40.0, 30.0)),
            bounds=(10.0, 10.0, 41.0, 31.0))
        window.sam_controller._on_finished(
            window.sam_controller._gen, result, None)
        assert window.canvas.provisional_shape is not None
        assert window.class_picker.prompt.text() == 'Use this outline?'

        QTest.keyClick(window.class_picker, Qt.Key.Key_Escape)
        app.processEvents()
        assert window.canvas.provisional_shape is None
        assert window.canvas.shapes == []
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
        assert not window.video_model.dirty
        assert not window.undo_stack.can_undo()
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()
