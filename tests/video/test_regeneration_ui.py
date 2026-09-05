import threading
import time
from unittest.mock import patch

from PyQt6.QtCore import QPointF

from labelImgPlusPlus import get_main_app
from libs.core.video_types import ObservationRecord, PropagationResult


def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _close_window(app, window):
    window.dirty = False
    window.close()
    app.processEvents()
    app.processEvents()


def _generated_correction_fixture(window):
    model = window.video_model
    first_pts = window.current_video_frame_ref.pts
    snapshot = window.video_snapshot
    step = int(round(
        snapshot.average_rate_den / snapshot.average_rate_num /
        (snapshot.time_base_num / snapshot.time_base_den)))
    correction_pts = first_pts + 8 * step
    track = model.create_track(
        'object', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    model.upsert_manual(track.track_id, first_pts, [16, 14, 52, 50])
    model.upsert_tracker(ObservationRecord(
        track.track_id, correction_pts - step, [23, 14, 59, 50],
        source='tracker', review_state='accepted', anchor=False))
    model.upsert_tracker(ObservationRecord(
        track.track_id, correction_pts, [24, 14, 60, 50],
        source='tracker', review_state='accepted', anchor=False))
    model.upsert_tracker(ObservationRecord(
        track.track_id, correction_pts + step, [25, 14, 61, 50],
        source='tracker', review_state='accepted', anchor=False))
    model.upsert_manual(
        track.track_id, first_pts + 16 * step, [32, 14, 68, 50])
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window.request_video_frame(window.video_timeline._normalized_to_ref(
        window.video_timeline._pts_to_normalized(correction_pts)))
    return track, correction_pts, step


def _edit_current_generated_shape(app, window, correction_pts):
    assert _wait(
        app, lambda: window.current_video_frame_ref.pts == correction_pts)
    shape = window.canvas.shapes[0]
    old_points = [QPointF(point) for point in shape.points]
    shape.points = [QPointF(point.x() + 4, point.y())
                    for point in shape.points]
    window._on_shape_move_finished(shape, old_points)


def test_generated_correction_and_regeneration_are_two_undo_entries(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'regenerate.mp4', frames=20, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def staged(_backend, request, direction, cancelled, _emit):
        started.set()
        while not gate.wait(.002) and not cancelled():
            pass
        frame_step = int(round(
            request.average_rate_den / request.average_rate_num /
            (request.time_base_num / request.time_base_den)))
        pts = request.current_pts + direction * frame_step
        item = ObservationRecord(
            request.seeds[0].track_id, pts,
            [80 + direction, 14, 116 + direction, 50],
            source='tracker', review_state='accepted', anchor=False)
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(item,))

    try:
        assert window.open_video(video)
        track, correction_pts, step = _generated_correction_fixture(window)
        baseline_undo = len(window.undo_stack)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                staged):
            _edit_current_generated_shape(app, window, correction_pts)
            assert window.video_model.observations[
                (track.track_id, correction_pts)].source == 'manual'
            assert len(window.undo_stack) == baseline_undo + 1
            assert track.track_id in window._regeneration_runs
            assert started.wait(1)
            gate.set()
            assert _wait(
                app, lambda: track.track_id not in window._regeneration_runs)

        assert len(window.undo_stack) == baseline_undo + 2
        assert window.video_model.observations[
            (track.track_id, correction_pts - step)].geometry[0] == 79
        assert window.video_model.observations[
            (track.track_id, correction_pts + step)].geometry[0] == 81

        window.undo_action()
        assert window.video_model.observations[
            (track.track_id, correction_pts)].source == 'manual'
        assert window.video_model.observations[
            (track.track_id, correction_pts - step)].geometry[0] == 23
        window.undo_action()
        assert window.video_model.observations[
            (track.track_id, correction_pts)].source == 'tracker'
    finally:
        gate.set()
        _close_window(app, window)


def test_regeneration_failure_preserves_correction_and_prior_generated_data(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'failure.mp4', frames=20, width=128, height=96,
        tracking_stress=True)

    def fail(_backend, _request, _direction, _cancelled, _emit):
        raise RuntimeError('decoder failed')

    try:
        assert window.open_video(video)
        track, correction_pts, step = _generated_correction_fixture(window)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate', fail):
            _edit_current_generated_shape(app, window, correction_pts)
            assert _wait(
                app, lambda: track.track_id not in window._regeneration_runs)
        assert window.video_model.observations[
            (track.track_id, correction_pts)].source == 'manual'
        assert window.video_model.observations[
            (track.track_id, correction_pts - step)].geometry[0] == 23
        assert window.video_model.observations[
            (track.track_id, correction_pts + step)].geometry[0] == 25
    finally:
        _close_window(app, window)


def test_undoing_correction_cancels_and_discards_regeneration(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'undo.mp4', frames=20, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def delayed(_backend, request, direction, cancelled, _emit):
        started.set()
        while not gate.wait(.002) and not cancelled():
            pass
        frame_step = int(round(
            request.average_rate_den / request.average_rate_num /
            (request.time_base_num / request.time_base_den)))
        item = ObservationRecord(
            request.seeds[0].track_id,
            request.current_pts + direction * frame_step,
            [90, 14, 126, 50], source='tracker',
            review_state='accepted', anchor=False)
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(item,))

    try:
        assert window.open_video(video)
        track, correction_pts, step = _generated_correction_fixture(window)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed):
            _edit_current_generated_shape(app, window, correction_pts)
            assert started.wait(1)
            window.undo_action()
            assert track.track_id not in window._regeneration_runs
            gate.set()
            assert _wait(app, lambda: not window._regeneration_runs)
        assert window.video_model.observations[
            (track.track_id, correction_pts)].source == 'tracker'
        assert window.video_model.observations[
            (track.track_id, correction_pts - step)].geometry[0] == 23
        assert not any(
            item.geometry[0] == 90
            for item in window.video_model.observations.values()
            if item.track_id == track.track_id)
    finally:
        gate.set()
        _close_window(app, window)
