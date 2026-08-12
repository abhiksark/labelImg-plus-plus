import threading
import time
from unittest.mock import patch

from labelImgPlusPlus import get_main_app
from libs.core.video_types import (
    ObservationRecord, PropagationBatch, PropagationResult, TrackGapRecord,
    VideoFrameRef,
)
from libs.core.video_sam2 import Sam2Availability


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


def _seed(window, track_id='track-1', shape_type='rectangle'):
    model = window.video_model
    track = model.create_track(
        'object', shape_type, (0, 255, 0, 255), track_id=track_id)
    geometry = ([16, 14, 52, 50] if shape_type == 'rectangle' else
                [[16, 14], [52, 14], [52, 50], [16, 50]])
    model.upsert_manual(
        track.track_id, window.current_video_frame_ref.pts, geometry)
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window._materialize_video_frame(window.current_video_frame_ref.pts)
    return track


def _ref(window, pts):
    snapshot = window.video_snapshot
    return VideoFrameRef(
        snapshot.fingerprint, snapshot.stream_index, pts,
        snapshot.time_base_num, snapshot.time_base_den)


def test_batches_are_preview_only_then_commit_pending_in_one_undo_step(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'preview.mp4', frames=24, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def delayed(_backend, request, direction, cancelled, emit):
        pts = request.current_pts + direction
        observation = ObservationRecord(
            request.seeds[0].track_id, pts, [17, 14, 53, 50],
            source='tracker', review_state='pending', anchor=False)
        gap = TrackGapRecord(
            request.seeds[0].track_id, pts + 1, pts + 2,
            'occluded', 'opencv')
        emit(PropagationBatch(
            request.request_id, request.generation, direction,
            observations=(observation,), gaps=(gap,),
            processed_frames=1, total_frames=2, active_tracks=1))
        started.set()
        while not gate.wait(.002):
            if cancelled():
                return PropagationResult(
                    request.request_id, request.generation,
                    request.document_revision)
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(observation,),
            gaps=(gap,))

    try:
        assert window.open_video(video)
        track = _seed(window)
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed):
            handle = window.track_selected_forward()
            assert handle is not None
            assert _wait(app, started.is_set)
            assert _wait(app, lambda: bool(window._propagation_preview))
            assert window.video_model.revision == baseline_revision
            assert not any(
                item.source == 'tracker'
                for item in window.video_model.observations.values())
            assert not window.actions.save.isEnabled()
            assert not window.actions.videoExport.isEnabled()
            assert not window.actions.undo.isEnabled()
            assert window.video_timeline.next_button.isEnabled()
            gate.set()
            assert _wait(app, lambda: window._propagation_handle is None)
        generated = [
            item for item in window.video_model.observations.values()
            if item.source == 'tracker']
        assert len(generated) == 1
        assert generated[0].review_state == 'pending'
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert window.video_model.gaps
        window.undo_action()
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
        assert track.track_id in window.video_model.tracks
    finally:
        gate.set()
        _close_window(app, window)


def test_directional_alias_accepts_exact_user_endpoint(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'endpoint.mp4', frames=24, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def delayed(_backend, request, _direction, cancelled, _emit):
        started.set()
        while not gate.wait(.002) and not cancelled():
            pass
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision)

    try:
        assert window.open_video(video)
        _seed(window)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed), patch(
                    'labelImgPlusPlus.QInputDialog.getText',
                    return_value=('00:00:00.500', True)):
            handle = window.track_selected_forward(choose_endpoint=True)
            assert handle is not None
            assert _wait(app, started.is_set)
            expected = int(round(
                .5 * window.video_snapshot.time_base_den /
                window.video_snapshot.time_base_num))
            assert window._active_propagation_request.end_pts == expected
            window.cancel_video_propagation()
            gate.set()
            assert _wait(app, lambda: window._propagation_handle is None)
    finally:
        gate.set()
        _close_window(app, window)


def test_intervening_track_revision_discards_stale_result(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'stale.mp4', frames=20, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def delayed(_backend, request, direction, cancelled, emit):
        observation = ObservationRecord(
            request.seeds[0].track_id, request.current_pts + direction,
            [17, 14, 53, 50], source='tracker',
            review_state='accepted', anchor=False)
        started.set()
        while not gate.wait(.002) and not cancelled():
            pass
        emit(PropagationBatch(
            request.request_id, request.generation, direction,
            observations=(observation,)))
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(observation,))

    try:
        assert window.open_video(video)
        track = _seed(window)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed):
            handle = window.track_selected_forward()
            assert handle is not None
            assert _wait(app, started.is_set)
            window.video_model.rename_track(track.track_id, 'changed')
            gate.set()
            assert _wait(app, lambda: window._propagation_handle is None)
        assert not window._propagation_preview
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
    finally:
        gate.set()
        _close_window(app, window)


def test_propagate_all_includes_rectangle_and_polygon_current_anchors(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'all.mp4', frames=18, width=128, height=96,
        tracking_stress=True)
    captured = []

    def capture(_backend, request, _direction, _cancelled, _emit):
        captured.append(tuple(item.track_id for item in request.seeds))
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision)

    try:
        assert window.open_video(video)
        _seed(window, 'rectangle')
        _seed(window, 'polygon', shape_type='polygon')
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                capture), patch.object(
                    window, '_confirm_propagation_scope', return_value=True):
            assert window.propagate_across_video() is not None
            assert _wait(app, lambda: window._propagation_handle is None)
        assert captured
        assert all(set(values) == {'rectangle', 'polygon'}
                   for values in captured)
    finally:
        _close_window(app, window)


def test_explicit_unavailable_sam2_keeps_canonical_model_unchanged(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'sam2-unavailable.mp4', frames=12,
        width=128, height=96, tracking_stress=True)
    try:
        assert window.open_video(video)
        _seed(window)
        baseline = window.video_model.snapshot_state()
        baseline_undo = len(window.undo_stack)
        window.video_propagation_backend = 'sam2'
        window.video_sam2_checkpoint = '/missing/model.pt'
        window.video_sam2_config = '/missing/model.yaml'
        with patch(
                'libs.core.video_sam2.inspect_sam2_environment',
                return_value=Sam2Availability(
                    False, ('a working CUDA runtime is required',))):
            assert window.track_selected_forward() is not None
            assert _wait(app, lambda: window._propagation_handle is None)
        assert window.video_model.snapshot_state() == baseline
        assert len(window.undo_stack) == baseline_undo
        assert not window._propagation_preview
        assert 'SAM 2 propagation is unavailable' \
            in window.statusBar().currentMessage()
        assert 'Select OpenCV or Auto' \
            in window.statusBar().currentMessage()
    finally:
        _close_window(app, window)


def test_document_close_cancels_and_clears_preview(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'close.mp4', frames=18, width=128, height=96,
        tracking_stress=True)
    gate = threading.Event()
    started = threading.Event()

    def delayed(_backend, request, direction, cancelled, emit):
        item = ObservationRecord(
            request.seeds[0].track_id, request.current_pts + direction,
            [17, 14, 53, 50], source='tracker',
            review_state='accepted', anchor=False)
        emit(PropagationBatch(
            request.request_id, request.generation, direction,
            observations=(item,)))
        started.set()
        while not gate.wait(.002) and not cancelled():
            pass
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(item,))

    try:
        assert window.open_video(video)
        _seed(window)
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed):
            assert window.track_selected_forward() is not None
            assert _wait(app, started.is_set)
            window._close_video_decoder(close_decoder=False)
            gate.set()
            assert _wait(app, lambda: window._propagation_handle is None)
        assert not window._propagation_preview
        assert not window.canvas.propagation_preview_shapes
    finally:
        gate.set()
        _close_window(app, window)


def test_backend_infrastructure_failure_leaves_model_and_gaps_unchanged(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'broken.mp4', frames=18, width=128, height=96,
        tracking_stress=True)

    def fail(_backend, _request, _direction, _cancelled, _emit):
        raise RuntimeError('decoder infrastructure failed')

    try:
        assert window.open_video(video)
        _seed(window)
        baseline = window.video_model.snapshot_state()
        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate', fail):
            assert window.track_selected_forward() is not None
            assert _wait(app, lambda: window._propagation_handle is None)
        assert window.video_model.snapshot_state() == baseline
        assert not window._propagation_preview
        assert not window.video_model.gaps
    finally:
        _close_window(app, window)
