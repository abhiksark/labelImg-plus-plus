from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QTest

from labelImgPlusPlus import get_main_app
from libs.core.annotation_workflow import AnnotationTool, PromptPolicy
from libs.core.assist_state import AssistPhase
from libs.core.sam_types import SamResult
from libs.core.shape import Shape, ShapeType


def _finalise_rectangle(window):
    shape = Shape(shape_type=ShapeType.RECTANGLE)
    for point in ((10, 10), (40, 10), (40, 30), (10, 30)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()


def test_video_confirmation_keeps_rectangle_armed_and_reuses_class(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'picker.mp4')
    try:
        assert window.open_video(video)
        window.active_class_control.confirm_each.setChecked(False)
        assert window.workflow.snapshot.prompt_policy is \
            PromptPolicy.REUSE_ACTIVE
        window.activate_box_tool()
        _finalise_rectangle(window)
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
        assert not window.video_model.dirty

        window.class_picker.edit.setText('car')
        QTest.keyClick(window.class_picker.edit, Qt.Key_Return)
        app.processEvents()
        assert len(window.video_model.tracks) == 1
        observation = next(iter(window.video_model.observations.values()))
        assert observation.source == 'manual'
        assert observation.review_state == 'accepted'
        assert window.workflow.snapshot.active_class == 'car'
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert window.actions.create.isChecked()
        assert window.canvas.mode == window.canvas.CREATE
        assert window.class_picker.isHidden()

        _finalise_rectangle(window)
        app.processEvents()
        assert window.class_picker.isHidden()
        assert len(window.video_model.tracks) == 2
        assert {track.label for track in window.video_model.tracks.values()} \
            == {'car'}
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert window.canvas.mode == window.canvas.CREATE

        window.undo_action()
        window.undo_action()
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
    finally:
        window.active_class_control.confirm_each.setChecked(False)
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()


def test_video_assist_box_is_preview_then_commits_as_manual_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'sam-box.mp4')
    try:
        assert window.open_video(video)
        window.sam_output_mode = 'box'
        result = SamResult(
            polygon=((10.0, 10.0), (40.0, 10.0), (40.0, 30.0)),
            bounds=(10.0, 10.0, 41.0, 31.0))
        window.assist_state.ready('test-assist')
        window._assist_document_identity = window.document_identity
        window.assist_state.start_run(window._dataset_generation)
        window._on_assist_preview(window._dataset_generation, result)
        preview = window.canvas.assist_preview_shape
        assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
        assert preview is not None
        assert preview.shape_type == ShapeType.RECTANGLE
        assert window.canvas.provisional_shape is None
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}

        assert window.accept_assist_preview() is False
        assert window.class_picker.isVisible()

        window.class_picker.edit.setText('vehicle')
        QTest.keyClick(window.class_picker.edit, Qt.Key_Return)
        app.processEvents()
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        track = next(iter(window.video_model.tracks.values()))
        observation = next(iter(window.video_model.observations.values()))
        assert track.shape_type == 'rectangle'
        assert observation.source == 'manual'
        assert observation.review_state == 'accepted'
        assert observation.anchor is True
        assert window._propagation_handle is None
        assert window._assist_track_forward_available()
        assert window.workspace_pages.assist_panel \
            .track_forward_button.isEnabled()

        window.undo_action()
        assert window.video_model.tracks == {}
        assert window.video_model.observations == {}
    finally:
        window.dirty = False
        window.close()
        app.processEvents()
        app.processEvents()
