import threading
import time
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QMessageBox

from labelImgPlusPlus import get_main_app
from libs.core.video_project import load_project
from libs.core.video_types import VideoFrameRef


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _seed_track(window, end_pts=None):
    model = window.video_model
    start = window.current_video_frame_ref.pts
    track = model.create_track(
        'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    model.upsert_manual(track.track_id, start, [2, 3, 22, 23])
    if end_pts is not None:
        model.upsert_manual(track.track_id, end_pts, [12, 13, 32, 33])
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window._materialize_video_frame(start)
    return track


def _ref(window, pts):
    snapshot = window.video_snapshot
    return VideoFrameRef(
        snapshot.fingerprint, snapshot.stream_index, pts,
        snapshot.time_base_num, snapshot.time_base_den)


def test_tracks_tab_materializes_manual_shape_and_renames_globally(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        assert window.track_list_widget.count() == 1
        assert len(window.canvas.shapes) == 1
        shape = window.canvas.shapes[0]
        assert shape.video_track_id == 'track-1'
        item = window.shapes_to_items[shape]
        item.setText('vehicle')
        assert window.video_model.tracks['track-1'].label == 'vehicle'
        assert window.canvas.shapes[0].label == 'vehicle'
    finally:
        window.dirty = False
        window.close()


def test_editing_interpolation_creates_manual_anchor_and_undo_restores_it(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts >=
            start + 4 * step)
        shape = window.canvas.shapes[0]
        assert shape.video_render_state == 'interpolation'
        old_points = list(shape.points)
        shape.points = [QPointF(point.x() + 3, point.y() + 2)
                        for point in shape.points]
        window._on_shape_move_finished(shape, old_points)
        pts = window.current_video_frame_ref.pts
        exact = window.video_model.observations[('track-1', pts)]
        assert exact.source == 'manual'
        assert exact.anchor is True
        window.undo_action()
        assert ('track-1', pts) not in window.video_model.observations
        assert window.canvas.shapes[0].video_render_state == 'interpolation'
    finally:
        window.dirty = False
        window.close()


def test_deleting_interpolated_occurrence_writes_absence_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(app, lambda: bool(window.canvas.shapes)
                     and window.canvas.shapes[0].video_render_state
                     == 'interpolation')
        pts = window.current_video_frame_ref.pts
        window.canvas.select_shape(window.canvas.shapes[0])
        window.delete_selected_shape()
        assert window.video_model.observations[('track-1', pts)].present is False
        assert window.canvas.shapes == []
    finally:
        window.dirty = False
        window.close()


def test_add_keyframe_promotes_interpolation_to_manual_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(app, lambda: bool(window.canvas.shapes)
                     and window.canvas.shapes[0].video_render_state
                     == 'interpolation')
        window._selected_video_track_id = 'track-1'
        window.add_track_keyframe()
        observation = window.video_model.observations[
            ('track-1', window.current_video_frame_ref.pts)]
        assert observation.source == 'manual'
        assert observation.anchor is True
        assert window.canvas.shapes[0].video_render_state == 'exact'
    finally:
        window.dirty = False
        window.close()


def test_verify_and_explicit_save_are_durable(tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        pts = window.current_video_frame_ref.pts
        window.video_model.set_frame_verified(pts, True)
        window._on_video_model_mutation()
        assert window.save_video_project()
        contents = load_project(window.video_snapshot.project_path)
        assert contents.tracks[0].track_id == 'track-1'
        assert contents.observations[0].pts == pts
        assert contents.frame_states[0].verified is True
        assert window.dirty is False
    finally:
        window.dirty = False
        window.close()


def test_mutation_during_async_save_is_chained_into_next_delta(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    gate = threading.Event()
    started = threading.Event()
    from libs.core.video_project import save_project_delta

    def delayed(request, cancelled=None, begin_commit=None):
        started.set()
        gate.wait(2)
        return save_project_delta(
            request, cancelled=cancelled, begin_commit=begin_commit)

    try:
        assert window.open_video(video)
        track = _seed_track(window)
        with patch('labelImgPlusPlus.save_project_delta', delayed):
            window.request_save_video_project()
            assert started.wait(1)
            step = window._video_step_pts()
            window.video_model.upsert_manual(
                track.track_id,
                window.current_video_frame_ref.pts + step,
                [3, 4, 23, 24])
            window._on_video_model_mutation()
            window.request_save_video_project()
            gate.set()
            assert _wait(app, lambda: not window.video_model.dirty)
        contents = load_project(window.video_snapshot.project_path)
        assert len(contents.observations) == 2
        assert window.dirty is False
    finally:
        gate.set()
        window.dirty = False
        window.close()


def test_async_save_failure_retains_overlay_and_dirty_state(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        with patch(
                'labelImgPlusPlus.save_project_delta',
                side_effect=RuntimeError('disk unavailable')):
            window.request_save_video_project()
            assert _wait(app, lambda: not window._video_save_active)
        assert window.video_model.dirty is True
        assert window.dirty is True
        assert window.actions.save.isEnabled()
        assert 'disk unavailable' in window.statusBar().currentMessage()
    finally:
        window.dirty = False
        window.close()


def test_close_with_save_ignores_first_event_until_async_commit_finishes(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'close-save.mp4')
    gate = threading.Event()
    started = threading.Event()
    from libs.core.video_project import save_project_delta

    def delayed(request, cancelled=None, begin_commit=None):
        started.set()
        gate.wait(2)
        return save_project_delta(
            request, cancelled=cancelled, begin_commit=begin_commit)

    event = MagicMock()
    try:
        assert window.open_video(video)
        _seed_track(window)
        with patch.object(
                window, 'discard_changes_dialog',
                return_value=QMessageBox.Yes), patch(
                'labelImgPlusPlus.save_project_delta', delayed), patch.object(
                window, 'close', return_value=True) as close:
            window.closeEvent(event)
            assert started.wait(1)
            event.ignore.assert_called_once_with()
            event.accept.assert_not_called()
            assert window._video_close_save_pending is True
            assert window.task_coordinator.is_shutting_down is False

            gate.set()
            assert _wait(app, lambda: close.called)
            assert window._video_close_save_pending is False
            assert window.dirty is False
    finally:
        gate.set()
        window.dirty = False
        window.close()
