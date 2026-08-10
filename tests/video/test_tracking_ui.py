import threading
import time
from unittest.mock import patch

from labelImgPlusPlus import get_main_app
from libs.core.video_types import VideoFrameRef


def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _seed(window):
    model = window.video_model
    track = model.create_track(
        'object', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    model.upsert_manual(
        track.track_id, window.current_video_frame_ref.pts,
        [16, 14, 52, 50])
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window._materialize_video_frame(window.current_video_frame_ref.pts)
    return track


def _ref(window, pts):
    snapshot = window.video_snapshot
    return VideoFrameRef(
        snapshot.fingerprint, snapshot.stream_index, pts,
        snapshot.time_base_num, snapshot.time_base_den)


def test_tracking_batches_render_pending_and_review_is_undoable(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'tracking.mp4', frames=24, width=128, height=96,
        tracking_stress=True)
    try:
        assert window.open_video(video)
        _seed(window)
        handle = window.track_selected_forward()
        assert handle is not None
        assert _wait(app, lambda: window._tracking_handle is None)
        pending = [item for item in window.video_model.observations.values()
                   if item.review_state == 'pending']
        assert len(pending) >= 8
        target = pending[0]
        window.request_video_frame(_ref(window, target.pts))
        assert _wait(app, lambda: window.current_video_frame_ref.pts
                     == target.pts)
        assert window.canvas.shapes[0].video_render_state == 'pending'
        assert window.actions.videoAcceptVisible.isEnabled()
        assert window.actions.videoRejectVisible.isEnabled()
        assert window.actions.videoAcceptRun.isEnabled()
        assert window.actions.videoRejectRun.isEnabled()
        assert window.accept_current_suggestion()
        accepted = window.video_model.observations[
            (target.track_id, target.pts)]
        assert accepted.review_state == 'accepted'
        assert accepted.anchor is False
        assert window.canvas.shapes[0].video_render_state == 'exact'
        window.undo_action()
        assert window.video_model.observations[
            (target.track_id, target.pts)].review_state == 'pending'
        assert window.review_full_propagation('rejected')
        assert not any(
            item.review_state == 'pending'
            for item in window.video_model.observations.values())
    finally:
        window.dirty = False
        window.close()


def test_tracking_action_accepts_exact_user_endpoint(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'endpoint.mp4', frames=24, width=128, height=96,
        tracking_stress=True)
    try:
        assert window.open_video(video)
        _seed(window)
        with patch(
                'labelImgPlusPlus.QInputDialog.getText',
                return_value=('00:00:00.500', True)):
            handle = window.track_selected_forward(choose_endpoint=True)
        assert handle is not None
        expected = int(round(
            .5 * window.video_snapshot.time_base_den /
            window.video_snapshot.time_base_num))
        assert window._active_tracking_request.end_pts == expected
        window.cancel_video_tracking()
        assert _wait(app, lambda: window._tracking_handle is None)
    finally:
        window.dirty = False
        window.close()


def test_external_seed_edit_cancels_and_discards_stale_tracking_result(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'stale.mp4', frames=20, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()
    from libs.core.video_tracking import track_optical_flow

    def delayed(request, handle):
        started.set()
        gate.wait(2)
        return track_optical_flow(request, handle)

    try:
        assert window.open_video(video)
        track = _seed(window)
        with patch('labelImgPlusPlus.track_optical_flow', delayed):
            window.track_selected_forward()
            assert started.wait(1)
            window.video_model.rename_track(track.track_id, 'changed')
            window._on_video_model_mutation()
            gate.set()
            assert _wait(app, lambda: window._tracking_handle is None)
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
    finally:
        gate.set()
        window.dirty = False
        window.close()
