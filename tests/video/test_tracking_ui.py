import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtGui import QImage

from labelImgPlusPlus import get_main_app
from libs.core.video_model import VideoProjectModel
from libs.core.video_types import (
    DocumentKind, FrameStateRecord, ObservationRecord, PropagationBatch,
    PropagationRequest, PropagationResult, TrackGapRecord, TrackRecord,
    VideoFingerprint, VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
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


def _install_video_seam(window, tmp_path, duration_pts=100):
    source = tmp_path / 'propagation-seam.mp4'
    source.write_bytes(b'deterministic-propagation-seam')
    stat = source.stat()
    fingerprint = VideoFingerprint(
        stat.st_size, stat.st_mtime_ns, 'propagation-seam')
    frame_ref = VideoFrameRef(fingerprint, 0, 50, 1, 10)
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    first = VideoFrameResult(
        frame_ref, image, 64, 48, 64, 48, 0, image.sizeInBytes(), 'fixture')
    snapshot = VideoSessionSnapshot(
        source_path=str(source), project_path=str(tmp_path / 'seam.sqlite'),
        fingerprint=fingerprint, stream_index=0, time_base_num=1,
        time_base_den=10, width=64, height=48, rotation=0,
        codec='fixture', duration_pts=duration_pts, start_pts=0,
        average_rate_num=10, average_rate_den=1, revision=5,
        initial_frame=first, read_only=False)
    track = TrackRecord(
        'track-1', 'object', 'rectangle', (0, 255, 0, 255), revision=5)
    seed = ObservationRecord(
        track.track_id, 50, [16, 14, 52, 50], source='manual',
        review_state='accepted', anchor=True, revision=5)
    window.save_changes_automatically.setChecked(False)
    window._dataset_generation = window.task_coordinator.next_generation()
    window.document_kind = DocumentKind.VIDEO
    window.file_path = str(source)
    window.video_snapshot = snapshot
    window.video_model = VideoProjectModel(
        revision=5, tracks=(track,), observations=(seed,),
        frame_states=(FrameStateRecord(seed.pts, True, 5),))
    window.current_video_frame_ref = frame_ref
    window._selected_video_track_id = track.track_id
    window.continuous_save.reset(
        window._continuous_document_key(), window._dataset_generation, 5)
    window.video_timeline.set_session(snapshot)
    window._sync_video_model_views()
    window._refresh_video_timeline_markers()
    window._materialize_video_frame(seed.pts)
    return track, seed


def _arm_propagation(window, track, seed, directions=(-1, 1)):
    request = PropagationRequest(
        request_id=17, generation=window._dataset_generation,
        document_revision=window.video_model.revision,
        source_path=window.video_snapshot.source_path,
        fingerprint=window.video_snapshot.fingerprint,
        stream_index=window.video_snapshot.stream_index,
        time_base_num=window.video_snapshot.time_base_num,
        time_base_den=window.video_snapshot.time_base_den,
        start_pts=0, end_pts=100, current_pts=seed.pts,
        direction=(directions[0] if len(directions) == 1 else 0),
        seeds=(seed,), manual_anchors=(seed,),
        track_revisions=((track.track_id, track.revision),),
        average_rate_num=10, average_rate_den=1)
    window._active_propagation_request = request
    window._propagation_before_state = window.video_model.snapshot_state()
    window._propagation_handle = SimpleNamespace(cancel=lambda: None)
    window._propagation_preview = {}
    window._propagation_preview_gaps = {}
    window._set_propagation_running(True)
    return request


def test_final_propagation_is_pending_with_explicit_atomic_review_without_av(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
        baseline_undo = len(window.undo_stack)
        generated = ObservationRecord(
            track.track_id, 60, [17, 14, 53, 50], source='tracker',
            review_state='accepted', anchor=False,
            revision=request.document_revision)
        final_generated = ObservationRecord(
            track.track_id, 65, [18, 14, 54, 50], source='tracker',
            review_state='accepted', anchor=False,
            revision=request.document_revision)
        gap = TrackGapRecord(
            track.track_id, 70, 80, 'occluded', 'opencv',
            request.document_revision)
        window._on_propagation_batch(PropagationBatch(
            request.request_id, request.generation, 1,
            observations=(generated,), processed_frames=1,
            total_frames=5, active_tracks=1))

        window._on_propagation_result(PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(final_generated,),
            gaps=(gap,)))

        staged = window.video_model.observations[(track.track_id, 60)]
        assert staged.review_state == 'pending'
        assert window.video_model.observations[
            (track.track_id, 65)].review_state == 'pending'
        assert window.video_model.revision == request.document_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert window._propagation_handle is None
        assert window._video_editable()
        assert window.continuous_save.state == 'pending'
        assert window.actions.videoAcceptRun.isEnabled()
        assert window.actions.videoRejectRun.isEnabled()
        assert '2 pending' in window.video_timeline.progress_label.text()
        assert window.video_timeline.accept_propagation_button.defaultAction() \
            is window.actions.videoAcceptRun
        assert window.video_timeline.reject_propagation_button.defaultAction() \
            is window.actions.videoRejectRun
        assert window.actions.videoAcceptRun \
            in window.video_timeline.track_menu.actions()
        assert window.actions.videoRejectRun \
            in window.video_timeline.track_menu.actions()
        assert window.video_timeline.slider.pending
        assert window.video_timeline.slider.gaps
        assert {group.kind for group in
                window.video_timeline.slider.marker_groups()} == {
                    'accepted', 'pending', 'verified', 'propagation', 'gap'}

        review_revision = window.video_model.revision
        assert window.accept_pending_propagation()
        assert window.video_model.revision == review_revision + 1
        assert len(window.undo_stack) == baseline_undo + 2
        assert window.video_model.observations[
            (track.track_id, 60)].review_state == 'accepted'

        window.undo_stack.undo()
        assert window.video_model.observations[
            (track.track_id, 60)].review_state == 'pending'
        assert window.actions.videoAcceptRun.isEnabled()
        assert '2 pending' in window.video_timeline.progress_label.text()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_cancel_stages_preview_pending_and_marks_only_unresolved_tail_without_av(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)
        generated = ObservationRecord(
            track.track_id, 60, [17, 14, 53, 50], source='tracker',
            review_state='accepted', anchor=False,
            revision=request.document_revision)
        known_gap = TrackGapRecord(
            track.track_id, 61, 62, 'occluded', 'opencv',
            request.document_revision)
        window._on_propagation_batch(PropagationBatch(
            request.request_id, request.generation, 1,
            observations=(generated,), gaps=(known_gap,),
            processed_frames=1, total_frames=5, active_tracks=1))

        assert window.cancel_video_propagation()

        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert not window._propagation_preview
        assert not window.canvas.propagation_preview_shapes
        staged = window.video_model.observations[(track.track_id, 60)]
        assert staged.review_state == 'pending'
        assert set(window.video_model.gaps) == {
            (track.track_id, 61, 62),
            (track.track_id, 63, 100),
        }
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert window._video_editable()
        assert window.continuous_save.state == 'pending'
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_cancel_without_batch_records_only_unresolved_gaps_without_av(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        _arm_propagation(window, track, seed)
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)

        assert window.cancel_video_propagation()

        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
        assert set(window.video_model.gaps) == {
            (track.track_id, 0, 49),
            (track.track_id, 51, 100),
        }
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert window._propagation_handle is None
        assert window._video_editable()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_worker_finish_without_result_stages_unresolved_gaps_without_av(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        _arm_propagation(window, track, seed, directions=(1,))
        handle = window._propagation_handle
        baseline_revision = window.video_model.revision

        window._on_propagation_finished(handle)

        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert window.video_model.revision == baseline_revision + 1
        assert set(window.video_model.gaps) == {
            (track.track_id, 51, 100),
        }
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
        assert window._video_editable()
        assert window.continuous_save.state == 'pending'
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_track_selected_requires_manual_anchor_and_track_all_stays_in_menu(
        tmp_path):
    app, window = get_main_app()
    try:
        track, _seed_value = _install_video_seam(window, tmp_path)
        window._sync_video_track_actions(track.track_id)
        assert window.actions.videoPropagateSelected.isEnabled()
        assert window.actions.videoTrackForward.isEnabled()
        assert window.actions.videoTrackBackward.isEnabled()
        assert window.video_timeline.track_menu.actions()[0] \
            is window.actions.videoPropagateAll
        assert window.actions.videoPropagateAll.text() == 'Track all anchors'

        generated_track = window.video_model.create_track(
            'generated', 'rectangle', (255, 0, 0, 255),
            track_id='generated-track')
        window.video_model.upsert_tracker(ObservationRecord(
            generated_track.track_id, window.current_video_frame_ref.pts,
            [5, 5, 15, 15], source='tracker',
            review_state='accepted', anchor=False))
        window._selected_video_track_id = generated_track.track_id
        window._sync_video_track_actions(generated_track.track_id)

        assert not window.actions.videoPropagateSelected.isEnabled()
        assert not window.actions.videoTrackForward.isEnabled()
        assert not window.actions.videoTrackBackward.isEnabled()
        assert window.actions.videoPropagateAll.isEnabled()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_invalid_final_payload_clears_lifecycle_without_partial_staging(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
        baseline = window.video_model.snapshot_state()
        invalid = ObservationRecord(
            track.track_id, 60, [17, 14, 53, 50], source='manual',
            review_state='accepted', anchor=True,
            revision=request.document_revision)

        window._on_propagation_result(PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(invalid,)))

        assert window.video_model.snapshot_state() == baseline
        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert not window.video_timeline._propagation_running
        assert window._video_editable()
        assert 'could not be staged' in window.statusBar().currentMessage()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_worker_error_after_gap_batch_stages_truthful_failure_ranges_without_av(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
        baseline_revision = window.video_model.revision
        known_gap = TrackGapRecord(
            track.track_id, 60, 65, 'scene_cut', 'opencv',
            request.document_revision)
        window._on_propagation_batch(PropagationBatch(
            request.request_id, request.generation, 1, gaps=(known_gap,),
            processed_frames=1, total_frames=5, active_tracks=1))

        window._on_propagation_error('decoder failed after progress')

        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert window.video_model.revision == baseline_revision + 1
        assert set(window.video_model.gaps) == {
            (track.track_id, 60, 65),
            (track.track_id, 66, 100),
        }
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
        assert window._video_editable()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_forced_document_teardown_clears_active_run_without_stranding_save(
        tmp_path):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
        generated = ObservationRecord(
            track.track_id, 60, [17, 14, 53, 50], source='tracker',
            review_state='accepted', anchor=False,
            revision=request.document_revision)
        window._on_propagation_batch(PropagationBatch(
            request.request_id, request.generation, 1,
            observations=(generated,), processed_frames=1,
            total_frames=5, active_tracks=1))
        baseline_undo = len(window.undo_stack)

        window._close_video_decoder(close_decoder=False)

        assert window.video_model is None
        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert not window._propagation_preview
        assert len(window.undo_stack) == baseline_undo
        assert window.continuous_save.state == 'saved'
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


def test_batches_are_preview_only_then_cancel_stages_pending_in_one_undo_step(
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
            source='tracker', review_state='accepted', anchor=False)
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
            window.cancel_video_propagation()
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
                capture):
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
