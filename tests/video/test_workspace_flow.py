"""End-to-end contracts for the supported video annotation workspace."""

import time
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QSignalSpy, QTest

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_project import load_project
from libs.core.video_types import (
    ObservationRecord, PropagationBatch, PropagationResult,
)
from libs.widgets.videoTimelineWidget import TIMELINE_MAX


def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _close(app, window):
    window.dirty = False
    window._shutdown_force = True
    window.close()
    app.processEvents()
    app.processEvents()


def _draw_rectangle(window, bounds):
    window.activate_box_tool()
    window.canvas.commit_rectangle(bounds)


def test_open_fit_step_seek_annotate_verify_save_and_reopen(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'workspace-vfr.mp4', frames=24, variable_rate=True,
        width=128, height=96)
    try:
        window.show()
        window.workspace_pages.set_page('canvas')
        assert window.open_video(video)
        assert window.document_kind == DocumentKind.VIDEO
        assert window.view_transform.mode.value == 'fit_window'
        assert not window.canvas.pixmap.isNull()
        assert window.canvas.pixmap.width() == 128
        assert window.canvas.pixmap.height() == 96
        assert window.canvas.scale <= window.scale_fit_window() + .01

        # A failed replacement is transactional: the current video remains.
        current_path = window.file_path
        with patch('labelImgPlusPlus.QMessageBox.warning'):
            window.request_open_video(
                str(tmp_path / 'missing-replacement.mp4'), skip_prompt=True)
            assert _wait(
                app, lambda: getattr(window, '_video_open_handle', None)
                is None)
        assert window.file_path == current_path
        assert window.document_kind == DocumentKind.VIDEO

        first = window.current_video_frame_ref
        window.request_next_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > first.pts)
        second = window.current_video_frame_ref
        window.request_previous_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == first.pts)

        window.canvas.setFocus(Qt.OtherFocusReason)
        QTest.keyClick(window.canvas, Qt.Key_D)
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == second.pts)
        QTest.keyClick(window.canvas, Qt.Key_A)
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == first.pts)

        window.actions.videoPlayPause.trigger()
        assert window.video_timeline.play_button.accessibleName() == \
            'Pause video'
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > first.pts)
        window.actions.videoPlayPause.trigger()
        assert window.video_timeline.play_button.accessibleName() == \
            'Play video'

        timeline = window.video_timeline
        seeks = QSignalSpy(timeline.seekRequested)
        QTest.mouseClick(
            timeline.slider, Qt.LeftButton,
            pos=timeline.slider.rect().center())
        assert _wait(app, lambda: len(seeks) >= 1)
        mouse_pts = window.current_video_frame_ref.pts

        timeline.slider.setFocus(Qt.OtherFocusReason)
        timeline.slider.setPageStep(TIMELINE_MAX // 8)
        keyboard_seek_count = len(seeks)
        QTest.keyClick(timeline.slider, Qt.Key_PageDown)
        assert _wait(app, lambda: len(seeks) > keyboard_seek_count)
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts != mouse_pts)
        keyboard_pts = window.current_video_frame_ref.pts

        timeline.slider.setValue(TIMELINE_MAX // 4)
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts != keyboard_pts)
        assert len(seeks) >= 3

        errors = QSignalSpy(timeline.timeInputError)
        timeline.time_edit.setText('00:00:00.500')
        QTest.keyClick(timeline.time_edit, Qt.Key_Return)
        assert _wait(app, window.canvas.hasFocus)
        assert timeline.time_edit.text() == '00:00:00.500'

        timeline.time_edit.setText('not-a-time')
        timeline.time_edit.setFocus(Qt.OtherFocusReason)
        QTest.keyClick(timeline.time_edit, Qt.Key_Return)
        assert _wait(app, lambda: len(errors) == 1)
        assert timeline.time_edit.text() == 'not-a-time'
        assert timeline.time_edit.hasFocus()

        timeline.time_edit.setText('99:00:00.000')
        timeline.time_edit.setFocus(Qt.OtherFocusReason)
        QTest.keyClick(timeline.time_edit, Qt.Key_Return)
        assert _wait(app, lambda: len(errors) == 2)
        assert timeline.time_edit.text() == '99:00:00.000'
        QTest.keyClick(timeline.time_edit, Qt.Key_Escape)
        assert _wait(app, window.canvas.hasFocus)

        window.active_class_control.confirm_each.setChecked(False)
        window._active_class_selected('vehicle')
        _draw_rectangle(window, (8, 8, 40, 32))
        _draw_rectangle(window, (48, 16, 84, 52))
        assert len(window.video_model.tracks) == 2
        assert {track.label for track in window.video_model.tracks.values()} \
            == {'vehicle'}
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert _wait(
            app, lambda: window.continuous_save.state == 'saved')
        assert 'Saved' in window.label_save_status.text()

        pts = window.current_video_frame_ref.pts
        window.verify_image()
        assert window.video_model.frame_states[pts].verified is True
        assert _wait(
            app, lambda: window.continuous_save.state == 'saved')
        project = window.video_snapshot.project_path
        assert project
        durable = load_project(project)
        assert any(
            item.pts == pts and item.verified
            for item in durable.frame_states)

        window.dirty = False
        window.close_file()
        assert window.open_video(project)
        assert len(window.video_model.tracks) == 2
        assert window.video_model.frame_states[pts].verified is True
    finally:
        _close(app, window)


def test_cancelled_propagation_is_pending_then_accepts_and_rejects(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'propagation-review.mp4', frames=24,
        tracking_stress=True, width=128, height=96)

    def preview_then_wait(_backend, request, direction, cancelled, emit):
        delta = 1
        observation = ObservationRecord(
            request.seeds[0].track_id,
            request.current_pts + direction * delta,
            [17 + delta, 14, 53 + delta, 50], source='tracker',
            review_state='accepted', anchor=False,
            revision=request.document_revision)
        emit(PropagationBatch(
            request.request_id, request.generation, direction,
            observations=(observation,), processed_frames=1,
            total_frames=3, active_tracks=1))
        deadline = time.monotonic() + 2
        while not cancelled() and time.monotonic() < deadline:
            time.sleep(.002)
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision)

    try:
        assert window.open_video(video)
        window.active_class_control.confirm_each.setChecked(False)
        window._active_class_selected('vehicle')
        _draw_rectangle(window, (16, 14, 52, 50))
        track_id = next(iter(window.video_model.tracks))
        window._selected_video_track_id = track_id
        window._materialize_video_frame(window.current_video_frame_ref.pts)

        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                preview_then_wait):
            assert window.track_selected_forward() is not None
            assert _wait(app, lambda: bool(window._propagation_preview))
            assert window.cancel_video_propagation()
            assert _wait(app, lambda: window._propagation_handle is None)

            first_pending = tuple(window._pending_propagation_keys)
            assert first_pending
            assert window.video_model.gaps
            assert all(
                window.video_model.observations[key].review_state == 'pending'
                for key in first_pending)
            assert window.accept_pending_propagation()
            assert all(
                window.video_model.observations[key].review_state ==
                'accepted' for key in first_pending)
            window.undo_action()

        second_pending = tuple(first_pending)
        assert all(
            window.video_model.observations[key].review_state == 'pending'
            for key in second_pending)
        assert window.reject_pending_propagation()
        assert all(
            window.video_model.observations[key].review_state == 'rejected'
            for key in second_pending)
        assert _wait(
            app, lambda: window.continuous_save.state == 'saved')
    finally:
        _close(app, window)


def test_ten_cycle_open_play_seek_close_soak_leaves_no_video_work(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'ten-cycle-soak.mp4', frames=12, variable_rate=True)
    try:
        for cycle in range(10):
            assert window.open_video(video), cycle
            start = window.current_video_frame_ref
            window.play_pause_video()
            assert _wait(
                app, lambda: window.current_video_frame_ref != start)
            window.pause_video()
            window.video_timeline.slider.setValue(
                TIMELINE_MAX * (cycle + 1) // 11)
            assert _wait(
                app, lambda: not window.task_coordinator.queue_depths()[
                    'video'])
            window.dirty = False
            before = time.monotonic()
            window.close_file()
            assert time.monotonic() - before < 5
            assert window.document_kind == DocumentKind.NONE
            assert window.video_decoder is None
            assert _wait(app, window.task_coordinator.is_idle)

        assert window.open_video(video)
        assert window.document_kind == DocumentKind.VIDEO
    finally:
        _close(app, window)
