import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy, QTest

from labelImgPlusPlus import get_main_app
from libs.core.assist_state import AssistPhase
from libs.core.sam_types import SamResult
from libs.core.video_model import VideoProjectModel
from libs.core.video_project import load_project
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


def _arm_propagation(window, track, seed, directions=(-1, 1), request_id=17):
    request = PropagationRequest(
        request_id=request_id, generation=window._dataset_generation,
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


def _show_assist_preview(window):
    window.assist_state.ready('test-assist')
    window.assist_state.start_run(window._dataset_generation)
    window._on_assist_preview(
        window._dataset_generation,
        SamResult(
            polygon=((10.0, 10.0), (40.0, 10.0), (40.0, 30.0)),
            bounds=(10.0, 10.0, 41.0, 31.0)))
    assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW


def test_assist_video_accepts_one_manual_anchor_then_tracks_only_on_request(
        tmp_path, make_video):
    """Catches video acceptance auto-starting or bypassing the anchor lane."""
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'assist-track-forward.mp4', frames=18,
        width=128, height=96, tracking_stress=True)
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
        window.save_changes_automatically.setChecked(True)
        window.sam_output_mode = 'box'
        window.workspace_pages.show_assist()
        _show_assist_preview(window)
        window.workflow.set_active_class('vehicle')
        baseline_revision = window._document_revision
        baseline_undo = len(window.undo_stack._undo_stack)
        requested = QSignalSpy(window.continuous_save.saveRequested)

        assert window.accept_assist_preview() is True

        manual = [
            item for item in window.video_model.observations.values()
            if item.source == 'manual' and item.review_state == 'accepted'
            and item.anchor]
        assert len(window.video_model.tracks) == 1
        assert len(manual) == 1
        assert manual[0].track_id == window._selected_video_track_id
        assert len(window.undo_stack._undo_stack) == baseline_undo + 1
        assert window._document_revision > baseline_revision
        assert _wait(app, lambda: len(requested) == 1)
        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert not window.workspace_pages.assist_panel \
            .track_forward_button.isHidden()
        assert window.workspace_pages.assist_panel \
            .track_forward_button.isEnabled()

        with patch(
                'labelImgPlusPlus.OpenCVPropagationBackend.propagate',
                delayed):
            window.workspace_pages.assist_panel.track_forward_button.click()
            assert _wait(app, started.is_set)
            assert window._propagation_handle is not None
            assert window._active_propagation_request.direction == 1
            assert tuple(
                item.track_id
                for item in window._active_propagation_request.seeds) == (
                    manual[0].track_id,)
            window.cancel_video_propagation()
            gate.set()
            assert _wait(app, lambda: window._propagation_handle is None)
    finally:
        gate.set()
        _close_window(app, window)


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

        window._on_propagation_result(
            PropagationResult(
                request.request_id, request.generation,
                request.document_revision, observations=(final_generated,),
                gaps=(gap,)),
            window._propagation_handle, request)

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


@pytest.mark.parametrize('activation', ('wide-button', 'compact-menu'))
def test_user_cancel_action_always_stages_partial_run_without_av(
        tmp_path, activation):
    app, window = get_main_app()
    try:
        track, seed = _install_video_seam(window, tmp_path)
        request = _arm_propagation(window, track, seed, directions=(1,))
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
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)
        save_states = QSignalSpy(window.continuous_save.stateChanged)
        window.workspace_pages.set_page('canvas')
        window.workspace_pages.set_video_visible(True)

        if activation == 'wide-button':
            window.video_timeline._update_layout_mode(2000)
            app.processEvents()
            assert window.video_timeline.layout_mode == 'wide'
            assert window.video_timeline.cancel_propagation_button.isVisible()
            QTest.mouseClick(
                window.video_timeline.cancel_propagation_button,
                Qt.LeftButton)
        else:
            window.video_timeline._update_layout_mode(420)
            app.processEvents()
            assert window.video_timeline.layout_mode == 'compact'
            assert window.video_timeline.track_button.isVisible()
            assert window.actions.videoCancelPropagation \
                in window.video_timeline.track_menu.actions()
            window.actions.videoCancelPropagation.trigger()

        assert window._propagation_handle is None
        assert window._active_propagation_request is None
        assert not window._propagation_preview
        assert not window.canvas.propagation_preview_shapes
        assert window.video_model.observations[
            (track.track_id, 60)].review_state == 'pending'
        assert set(window.video_model.gaps) == {
            (track.track_id, 61, 62),
            (track.track_id, 63, 100),
        }
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert window.continuous_save.state == 'pending'
        assert [values[0] for values in save_states] == ['pending']
        assert window.video_timeline.slider.pending
        assert window.video_timeline.slider.gaps
        assert window._video_editable()
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

        window._on_propagation_result(
            PropagationResult(
                request.request_id, request.generation,
                request.document_revision, observations=(invalid,)),
            window._propagation_handle, request)

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

        window._on_propagation_error(
            'decoder failed after progress',
            window._propagation_handle, request)

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
        assert window._pending_propagation_failures == 1
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)


@pytest.mark.parametrize('outcome', ('result', 'error'))
def test_stale_worker_terminal_callback_is_noop_for_new_run_without_av(
        tmp_path, outcome):
    app, window = get_main_app()
    started = threading.Event()
    release = threading.Event()

    def delayed(_backend, request, _direction, _cancelled, _emit_batch):
        started.set()
        release.wait(8)
        if outcome == 'error':
            raise RuntimeError('stale worker A failed')
        stale = ObservationRecord(
            request.seeds[0].track_id, 55, [17, 14, 53, 50],
            source='tracker', review_state='accepted', anchor=False,
            revision=request.document_revision)
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision, observations=(stale,))

    try:
        track, seed = _install_video_seam(window, tmp_path)
        with patch(
                'labelImgPlusPlus.ConfiguredPropagationBackend.propagate',
                delayed):
            a_handle = window._start_video_propagation(
                (seed,), (1,))
            assert a_handle is not None
            assert _wait(app, started.is_set)
            a_request = window._active_propagation_request

            b_request = _arm_propagation(
                window, track, seed, directions=(1,),
                request_id=a_request.request_id + 1000)
            b_handle = window._propagation_handle
            b_observation = ObservationRecord(
                track.track_id, 65, [18, 14, 54, 50], source='tracker',
                review_state='accepted', anchor=False,
                revision=b_request.document_revision)
            b_gap = TrackGapRecord(
                track.track_id, 66, 67, 'occluded', 'opencv',
                b_request.document_revision)
            window._on_propagation_batch(PropagationBatch(
                b_request.request_id, b_request.generation, 1,
                observations=(b_observation,), gaps=(b_gap,),
                processed_frames=1, total_frames=5, active_tracks=1))

            baseline_model = window.video_model.snapshot_state()
            baseline_revision = window.video_model.revision
            baseline_undo = len(window.undo_stack)
            baseline_save_state = window.continuous_save.state
            baseline_preview = dict(window._propagation_preview)
            baseline_preview_gaps = dict(window._propagation_preview_gaps)
            baseline_markers = tuple(
                window.video_timeline.slider.marker_groups())
            save_states = QSignalSpy(window.continuous_save.stateChanged)
            delivered = threading.Event()
            a_handle.finished.connect(delivered.set)

            release.set()
            assert _wait(app, delivered.is_set)

        assert window._propagation_handle is b_handle
        assert window._active_propagation_request is b_request
        assert window._propagation_preview == baseline_preview
        assert window._propagation_preview_gaps == baseline_preview_gaps
        assert window.video_model.snapshot_state() == baseline_model
        assert window.video_model.revision == baseline_revision
        assert len(window.undo_stack) == baseline_undo
        assert window.continuous_save.state == baseline_save_state
        assert not save_states
        assert tuple(window.video_timeline.slider.marker_groups()) \
            == baseline_markers
        assert window.video_timeline._propagation_running
    finally:
        release.set()
        window._close_video_decoder(close_decoder=False)
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


def test_explicit_unavailable_sam2_stages_failed_span_for_review(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'sam2-unavailable.mp4', frames=12,
        width=128, height=96, tracking_stress=True)
    try:
        assert window.open_video(video)
        _seed(window)
        baseline = window.video_model.snapshot_state()
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)
        project = window.video_snapshot.project_path
        window.video_propagation_backend = 'sam2'
        window.video_sam2_checkpoint = '/missing/model.pt'
        window.video_sam2_config = '/missing/model.yaml'
        with patch(
                'libs.core.video_sam2.inspect_sam2_environment',
                return_value=Sam2Availability(
                    False, ('a working CUDA runtime is required',))):
            assert window.track_selected_forward() is not None
            assert _wait(app, lambda: window._propagation_handle is None)
        assert window.video_model.observations == {
            (item.track_id, item.pts): item for item in baseline.observations}
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert set(window.video_model.gaps) == {('track-1', 1, 12288)}
        gap = window.video_model.gaps[('track-1', 1, 12288)]
        assert gap.reason == 'failed'
        assert gap.backend == 'sam2'
        assert window._pending_propagation_failures == 1
        assert '1 failures' in window.video_timeline.progress_label.text()
        assert not window._propagation_preview
        assert 'SAM 2 propagation is unavailable' \
            in window.statusBar().currentMessage()
        assert 'Select OpenCV or Auto' \
            in window.statusBar().currentMessage()
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
        durable = load_project(project)
        assert durable.revision == baseline_revision + 1
        assert durable.gaps == (gap,)
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


def test_worker_error_before_first_batch_stages_entire_failed_request_without_av(
        tmp_path):
    app, window = get_main_app()
    def fail(_backend, _request, _direction, _cancelled, _emit_batch):
        raise RuntimeError('decoder infrastructure failed')

    try:
        track, seed = _install_video_seam(window, tmp_path)
        baseline_revision = window.video_model.revision
        baseline_undo = len(window.undo_stack)
        save_states = QSignalSpy(window.continuous_save.stateChanged)
        with patch.object(
                window.video_model, 'stage_propagation_result',
                wraps=window.video_model.stage_propagation_result) as stage:
            with patch(
                    'labelImgPlusPlus.ConfiguredPropagationBackend.propagate',
                    fail):
                assert window._start_video_propagation(
                    (seed,), (1,)) is not None
                assert _wait(app, lambda: window._propagation_handle is None)
        assert window._active_propagation_request is None
        assert not window._propagation_preview
        assert window.video_model.revision == baseline_revision + 1
        assert len(window.undo_stack) == baseline_undo + 1
        assert not any(
            item.source == 'tracker'
            for item in window.video_model.observations.values())
        assert set(window.video_model.gaps) == {
            (track.track_id, 51, 100),
        }
        gap = window.video_model.gaps[(track.track_id, 51, 100)]
        assert gap.reason == 'failed'
        assert gap.track_id == track.track_id
        assert stage.call_count == 1
        assert stage.call_args.args[0].failures == (
            (track.track_id, 'decoder infrastructure failed'),)
        assert window._pending_propagation_failures == 1
        assert '1 failures' in window.video_timeline.progress_label.text()
        assert window.continuous_save.state == 'pending'
        assert [values[0] for values in save_states] == ['pending']
        assert window._video_editable()
    finally:
        window.save_changes_automatically.setChecked(True)
        _close_window(app, window)
