# tests/integration/test_sam_mainwindow.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json
import time

import pytest
from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QImage, QMouseEvent
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication
import labelImgPlusPlus as app_mod
from libs.core.annotation_workflow import AnnotationTool, PromptPolicy
from libs.core.assist_state import AssistPhase, AssistPrompt
from libs.core.sam_types import SamResult
from libs.core.shape import Shape, ShapeType

app = QApplication.instance() or QApplication([])


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _assist_window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(app_mod.segmentation, 'sam_available', lambda: True)
    monkeypatch.setattr(
        app_mod.model_cache, 'resolve_models',
        lambda *_args, **_kwargs: ('encoder', 'decoder'))
    return app_mod.MainWindow(default_save_dir=str(tmp_path))


def _prepare_image_document(window, path):
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(path))
    assert window.load_file(str(path))
    window.save_changes_automatically.setChecked(True)


def _show_preview(window):
    window.assist_state.ready('test-assist')
    window._assist_document_identity = window.document_identity
    window.assist_state.start_run(window._dataset_generation)
    window._on_assist_preview(
        window._dataset_generation,
        SamResult(
            polygon=((2.0, 2.0), (20.0, 2.0), (20.0, 18.0)),
            bounds=(2.0, 2.0, 20.0, 18.0)))
    assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
    return window.canvas.assist_preview_shape


def _continuous_state(window):
    return (
        window.continuous_save.state,
        window.continuous_save._newest_revision,
        window.continuous_save._durable_revision,
        window.continuous_save._in_flight,
    )


class _FakeInferenceBackend:
    """External deterministic boundary; controller/coordinator stay real."""

    def __init__(self):
        self._image_shape = None

    @property
    def image_is_set(self):
        return self._image_shape is not None

    def set_image(self, rgb):
        self._image_shape = rgb.shape[:2]

    def predict(self, _prompt):
        import numpy as np
        height, width = self._image_shape
        mask = np.zeros((height, width), dtype=bool)
        mask[8:32, 10:40] = True
        return mask


def _accepted_rectangle():
    shape = Shape(label='accepted', shape_type=ShapeType.RECTANGLE)
    for point in ((1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)):
        shape.add_point(QPointF(*point))
    shape.close()
    return shape


def _canvas_mouse_event(canvas, kind, x, y, button, buttons):
    offset = canvas.offset_to_center()
    position = QPointF(
        (float(x) + offset.x()) * canvas.scale,
        (float(y) + offset.y()) * canvas.scale)
    return QMouseEvent(
        kind, position, button, buttons, Qt.NoModifier)


@pytest.mark.parametrize(
    ('manual_tool', 'assist_tool'),
    (('rectangle', 'points'), ('polygon', 'box')),
)
def test_smart_tool_activation_releases_manual_picker_and_draft_ownership(
        monkeypatch, tmp_path, manual_tool, assist_tool):
    """A manual picker/draft cannot coexist with Assist prompt ownership."""
    pytest.importorskip('numpy')
    pytest.importorskip('cv2')
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(
            window, tmp_path / ('manual-to-%s.png' % assist_tool))
        window.show()
        app.processEvents()
        window.sam_controller.backend = _FakeInferenceBackend()

        accepted = _accepted_rectangle()
        window.canvas.shapes.append(accepted)
        window.canvas.rebuild_spatial_index()
        window.workflow.set_active_class('vehicle')
        window.workflow.set_prompt_policy(PromptPolicy.CONFIRM_EACH)
        window._apply_workflow_state()

        if manual_tool == 'rectangle':
            window.activate_box_tool()
            window.canvas.commit_rectangle((8.0, 8.0, 28.0, 24.0))
        else:
            window.activate_polygon_tool()
            window.canvas.commit_polygon(
                ((8.0, 8.0), (28.0, 8.0), (24.0, 24.0)))
        app.processEvents()

        manual_draft = window.canvas.provisional_shape
        assert manual_draft is not None
        assert window._pending_provisional_shape is manual_draft
        assert window.workflow.snapshot.provisional is True
        assert window.class_picker.isVisible()
        window.class_picker.edit.setText('stale manual class')
        picker_accepts = QSignalSpy(window.class_picker.accepted)
        save_requests = QSignalSpy(window.continuous_save.saveRequested)
        protected_document = (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        )

        if assist_tool == 'points':
            window.activate_smart_points_tool()
            expected_tool = AnnotationTool.SMART_POINTS
            expected_mode = 'points'
            expected_geometry = (18.0, 16.0)
        else:
            window.activate_smart_box_tool()
            expected_tool = AnnotationTool.SMART_BOX
            expected_mode = 'box'
            expected_geometry = (10.0, 10.0, 36.0, 30.0)
        assert _wait(lambda: not window.sam_controller._busy)

        assert window.class_picker.isHidden()
        assert window._pending_provisional_shape is None
        assert window.canvas.provisional_shape is None
        assert window.canvas.current is None
        assert window.workflow.snapshot.provisional is False
        assert window.workflow.snapshot.active_tool is expected_tool
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.canvas.hasFocus()
        assert (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        ) == protected_document
        assert len(save_requests) == 0

        QTest.keyClick(window.canvas, Qt.Key_Return)
        app.processEvents()
        assert len(picker_accepts) == 0
        assert tuple(window.canvas.shapes) == (accepted,)

        prompts = []
        manual_shapes = QSignalSpy(window.canvas.newShape)
        window.canvas.assistPrompted.connect(prompts.append)
        if assist_tool == 'points':
            window.canvas.mousePressEvent(_canvas_mouse_event(
                window.canvas, QEvent.MouseButtonPress, 18, 16,
                Qt.LeftButton, Qt.LeftButton))
        else:
            window.canvas.mousePressEvent(_canvas_mouse_event(
                window.canvas, QEvent.MouseButtonPress, 10, 10,
                Qt.LeftButton, Qt.LeftButton))
            window.canvas.mouseMoveEvent(_canvas_mouse_event(
                window.canvas, QEvent.MouseMove, 36, 30,
                Qt.NoButton, Qt.LeftButton))
            window.canvas.mouseReleaseEvent(_canvas_mouse_event(
                window.canvas, QEvent.MouseButtonRelease, 36, 30,
                Qt.LeftButton, Qt.NoButton))

        assert len(prompts) == 1
        prompt = prompts[0]
        assert isinstance(prompt, AssistPrompt)
        assert prompt.mode == expected_mode
        if assist_tool == 'points':
            assert prompt.positive_points[0] == pytest.approx(
                expected_geometry, abs=.5)
            assert prompt.negative_points == ()
            assert prompt.box is None
        else:
            assert prompt.box == pytest.approx(expected_geometry, abs=.5)
            assert prompt.positive_points == ()
            assert prompt.negative_points == ()
        assert len(manual_shapes) == 0
        assert _wait(
            lambda: window.assist_state.snapshot.phase is AssistPhase.PREVIEW)
        assert window._assist_prompt == prompt
        assert window.canvas.assist_preview_shape is not None
        assert window.canvas.provisional_shape is None
        assert window.canvas.current is None
        assert window.workflow.snapshot.provisional is False
        assert window.class_picker.isHidden()
        assert tuple(window.canvas.shapes) == (accepted,)
        assert (
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        ) == protected_document[1:]
        assert len(save_requests) == 0
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


@pytest.mark.parametrize(
    ('manual_tool', 'assist_tool', 'expected_tool'),
    (
        ('rectangle', 'box', AnnotationTool.SMART_BOX),
        ('polygon', 'points', AnnotationTool.SMART_POINTS),
    ),
)
def test_smart_tool_activation_finishes_in_progress_manual_gesture_ownership(
        monkeypatch, tmp_path, manual_tool, assist_tool, expected_tool):
    """Switching tools balances the unfinished manual drawing lifecycle."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(
            window, tmp_path / ('in-progress-to-%s.png' % assist_tool))
        window.show()
        app.processEvents()
        window.sam_controller.backend = _FakeInferenceBackend()
        if manual_tool == 'rectangle':
            window.activate_box_tool()
        else:
            window.activate_polygon_tool()
        window.canvas.handle_drawing(QPointF(10.0, 10.0))
        assert window.canvas.current is not None
        assert window.class_picker.isHidden()
        assert window.workflow.snapshot.provisional is False

        drawing_finished = QSignalSpy(window.canvas.drawingPolygon)
        save_requests = QSignalSpy(window.continuous_save.saveRequested)
        protected_document = (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        )

        if assist_tool == 'box':
            window.activate_smart_box_tool()
        else:
            window.activate_smart_points_tool()
        assert _wait(lambda: not window.sam_controller._busy)

        assert len(drawing_finished) == 1
        assert drawing_finished[0][0] is False
        assert window.canvas.current is None
        assert window.canvas.provisional_shape is None
        assert window._pending_provisional_shape is None
        assert window.class_picker.isHidden()
        assert window.workflow.snapshot.provisional is False
        assert window.workflow.snapshot.active_tool is expected_tool
        assert window.canvas.mode == window.canvas.CREATE_SAM
        assert window.canvas.hasFocus()
        assert (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        ) == protected_document
        assert len(save_requests) == 0
    finally:
        window.dirty = False
        window.close()


def test_enter_accepts_assist_preview_through_one_image_mutation_and_save(
        monkeypatch, tmp_path):
    """Catches Assist acceptance bypassing class, undo, revision, or save."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(window, tmp_path / 'assist-enter.png')
        _show_preview(window)
        window.workflow.set_active_class('vehicle')
        revision = window._document_revision
        undo_depth = len(window.undo_stack._undo_stack)
        requested = QSignalSpy(window.continuous_save.saveRequested)

        QTest.keyClick(window.canvas, Qt.Key_Return)
        app.processEvents()

        assert [shape.label for shape in window.canvas.shapes] == ['vehicle']
        assert window.canvas.assist_preview_shape is None
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert window._document_revision == revision + 1
        assert len(window.undo_stack._undo_stack) == undo_depth + 1
        assert _wait(lambda: len(requested) == 1)
        assert _wait(lambda: window.continuous_save.state == 'saved')
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_escape_rejects_assist_preview_without_document_mutation(
        monkeypatch, tmp_path):
    """Catches rejection changing document, undo, revision, or save state."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(window, tmp_path / 'assist-escape.png')
        _show_preview(window)
        protected = (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        )

        QTest.keyClick(window.canvas, Qt.Key_Escape)
        app.processEvents()

        assert window.canvas.assist_preview_shape is None
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert (
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack),
            window._document_revision,
            window.dirty,
            _continuous_state(window),
        ) == protected
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_assist_picker_return_commits_and_escape_retains_same_preview(
        monkeypatch, tmp_path):
    """Catches missing-class review discarding or replacing the preview."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(window, tmp_path / 'assist-picker.png')
        window.show()
        app.processEvents()
        preview = _show_preview(window)
        revision = window._document_revision

        assert window.accept_assist_preview() is False
        app.processEvents()
        assert window.class_picker.isVisible()
        assert window.canvas.assist_preview_shape is preview

        QTest.keyClick(window.class_picker.edit, Qt.Key_Escape)
        app.processEvents()
        app.processEvents()
        assert window.class_picker.isHidden()
        assert window.canvas.assist_preview_shape is preview
        assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
        assert window._document_revision == revision
        assert not window.undo_stack.can_undo()

        assert window.accept_assist_preview() is False
        app.processEvents()
        window.class_picker.edit.setText('pedestrian')
        QTest.keyClick(window.class_picker.edit, Qt.Key_Return)
        app.processEvents()
        app.processEvents()

        assert [shape.label for shape in window.canvas.shapes] == [
            'pedestrian']
        assert window.canvas.assist_preview_shape is None
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert window._document_revision == revision + 1
        assert len(window.undo_stack._undo_stack) == 1
    finally:
        window.dirty = False
        window.close()


def test_switching_from_assist_picker_does_not_claim_manual_picker_return(
        monkeypatch, tmp_path):
    """Catches stale Assist picker ownership swallowing a manual commit."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(window, tmp_path / 'assist-tool-exit.png')
        window.show()
        app.processEvents()
        _show_preview(window)
        window.workflow.set_active_class('')
        assert window.accept_assist_preview() is False
        app.processEvents()
        assert window.class_picker.isVisible()

        window.activate_box_tool()
        window.canvas.commit_rectangle((4.0, 4.0, 24.0, 20.0))
        app.processEvents()
        assert window.class_picker.isVisible()
        window.class_picker.edit.setText('manual vehicle')
        QTest.keyClick(window.class_picker.edit, Qt.Key_Return)
        app.processEvents()
        app.processEvents()

        assert [shape.label for shape in window.canvas.shapes] == [
            'manual vehicle']
        assert window.canvas.provisional_shape is None
        assert window.canvas.assist_preview_shape is None
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert len(window.undo_stack._undo_stack) == 1
    finally:
        window.dirty = False
        window.close()


def test_assist_review_keys_are_inert_outside_preview(monkeypatch, tmp_path):
    """Catches global Enter/Escape handlers reviewing a non-preview state."""
    window = _assist_window(monkeypatch, tmp_path)
    try:
        _prepare_image_document(window, tmp_path / 'assist-key-scope.png')
        window.assist_state.ready('test-assist')
        protected = (
            window.assist_state.snapshot,
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            window._document_revision,
            _continuous_state(window),
        )

        QTest.keyClick(window.canvas, Qt.Key_Return)
        QTest.keyClick(window.canvas, Qt.Key_Escape)
        app.processEvents()

        assert (
            window.assist_state.snapshot,
            tuple(window.canvas.shapes),
            tuple(window.undo_stack._undo_stack),
            window._document_revision,
            _continuous_state(window),
        ) == protected
    finally:
        window.dirty = False
        window.close()


def test_closing_assist_keeps_accepted_shape_and_completed_cache(
        monkeypatch, tmp_path):
    """Catches Assist close deleting durable user or model data."""
    window = _assist_window(monkeypatch, tmp_path)
    cache = tmp_path / 'models' / 'completed.onnx'
    cache.parent.mkdir()
    cache.write_bytes(b'validated-model')
    try:
        _prepare_image_document(window, tmp_path / 'assist-close.png')
        _show_preview(window)
        window.workflow.set_active_class('parcel')
        assert window.accept_assist_preview() is True
        accepted = tuple(window.canvas.shapes)

        window._close_assist()

        assert tuple(window.canvas.shapes) == accepted
        assert [shape.label for shape in accepted] == ['parcel']
        assert cache.read_bytes() == b'validated-model'
    finally:
        window.dirty = False
        window.close()


def test_sam_action_disabled_when_extra_missing(monkeypatch, tmp_path):
    # Force "extra not installed" regardless of the dev machine.
    from libs.integrations import segmentation
    monkeypatch.setattr(segmentation, "sam_available", lambda: False)

    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        assert hasattr(win.actions, "sam_mode")
        assert hasattr(win, "sam_controller")
        # Even once editing actions are enabled, the gate keeps SAM disabled
        # because the [sam] extra is absent.
        win.toggle_actions(True)
        assert win.actions.sam_mode.isEnabled() is False
    finally:
        win.close()


def test_sam_mode_sticks_in_beginner_mode(monkeypatch, tmp_path):
    # Regression: entering SAM mode must NOT be reverted to EDIT by the
    # drawingPolygon -> toggle_drawing_sensitive path in beginner mode.
    from libs.integrations import segmentation
    monkeypatch.setattr(segmentation, "sam_available", lambda: True)

    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        assert win.beginner()                       # default population
        win.toggle_sam_mode()
        assert win.canvas.mode == win.canvas.CREATE_SAM
        win.toggle_sam_mode()                        # toggle off
        assert win.canvas.mode != win.canvas.CREATE_SAM
    finally:
        win.close()


def test_sam_output_toggle_is_contextual_and_persists(monkeypatch, tmp_path):
    from libs.integrations import segmentation
    from libs.utils.constants import SETTING_SAM_OUTPUT_MODE

    settings_path = tmp_path / 'settings.json'

    def load_isolated(settings):
        settings.path = str(settings_path)
        settings.data = {}
        return False

    monkeypatch.setattr(app_mod.Settings, 'load', load_isolated)
    monkeypatch.setattr(segmentation, 'sam_available', lambda: True)
    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        toggle = win.workspace_pages.sam_output_toggle
        assert win.sam_output_mode == 'polygon'
        assert toggle.mode() == 'polygon'
        assert toggle.isHidden()

        win.activate_smart_select_tool()
        assert not toggle.isHidden()
        toggle.buttons['box'].click()
        app.processEvents()
        assert win.sam_output_mode == 'box'
        assert win.settings.get(SETTING_SAM_OUTPUT_MODE) == 'box'
        assert json.loads(settings_path.read_text())[SETTING_SAM_OUTPUT_MODE] \
            == 'box'
        assert win.canvas.hasFocus()

        win.activate_select_tool()
        assert toggle.isHidden()
    finally:
        win.close()
        app.processEvents()
        app.processEvents()


def test_video_propagation_settings_are_normalized_and_persisted(
        monkeypatch, tmp_path):
    from libs.utils.constants import (
        SETTING_VIDEO_PROPAGATION_BACKEND, SETTING_VIDEO_SAM2_CHECKPOINT,
        SETTING_VIDEO_SAM2_CONFIG,
    )
    from libs.widgets import sam_settings_dialog

    settings_path = tmp_path / 'settings.json'

    def load_isolated(settings):
        settings.path = str(settings_path)
        settings.data = {
            SETTING_VIDEO_PROPAGATION_BACKEND: 'obsolete',
            SETTING_VIDEO_SAM2_CHECKPOINT: '/old.pt',
            SETTING_VIDEO_SAM2_CONFIG: '/old.yaml',
        }
        return True

    captured = {}

    class FakeDialog:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def apply_theme(self, _theme):
            pass

        def exec_(self):
            return True

        def values(self):
            return {'encoder': '', 'decoder': ''}

        def propagation_values(self):
            return {
                'backend': 'sam2', 'checkpoint': '/new.pt',
                'config': '/new.yaml'}

    monkeypatch.setattr(app_mod.Settings, 'load', load_isolated)
    monkeypatch.setattr(sam_settings_dialog, 'SamSettingsDialog', FakeDialog)
    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        assert win.video_propagation_backend == 'auto'
        win.open_sam_settings()
        assert captured['propagation_backend'] == 'auto'
        assert captured['sam2_checkpoint'] == '/old.pt'
        assert captured['sam2_config'] == '/old.yaml'
        assert win.video_propagation_backend == 'sam2'
        saved = json.loads(settings_path.read_text())
        assert saved[SETTING_VIDEO_PROPAGATION_BACKEND] == 'sam2'
        assert saved[SETTING_VIDEO_SAM2_CHECKPOINT] == '/new.pt'
        assert saved[SETTING_VIDEO_SAM2_CONFIG] == '/new.yaml'
    finally:
        win.close()
        app.processEvents()
        app.processEvents()
