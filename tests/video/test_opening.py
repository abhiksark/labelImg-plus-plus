import os
import sqlite3
import time
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QThread, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QPushButton, QToolButton

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_decoder import PreparedVideoOpen, VideoDependencyError
from libs.core.video_model import VideoProjectModel
from libs.core.video_project import (
    default_project_path, initialize_project, load_project,
    read_project_source, save_project_delta,
)
from libs.core.video_types import (
    ObservationRecord, VideoFingerprint, VideoFrameRef,
    VideoFrameResult, VideoSessionSnapshot,
)


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _image(path):
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


def _missing_runtime_status():
    from libs.core.video_runtime import VideoRuntimeStatus
    return VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av')


def _install_writable_video_document(window, tmp_path):
    source = tmp_path / 'current.mp4'
    source.write_bytes(b'failed-replacement-current-video')
    stat = source.stat()
    fingerprint = VideoFingerprint(
        stat.st_size, stat.st_mtime_ns, 'current-fingerprint')
    project = tmp_path / 'current.labelimgpp.sqlite'
    initialize_project(str(project), SimpleNamespace(
        source_path=str(source), fingerprint=fingerprint, stream_index=0,
        time_base_num=1, time_base_den=12, duration_pts=2, width=64,
        height=48, rotation=0, codec='fixture'))
    snapshot = VideoSessionSnapshot(
        source_path=str(source), project_path=str(project),
        fingerprint=fingerprint, stream_index=0, time_base_num=1,
        time_base_den=12, width=64, height=48, rotation=0,
        codec='fixture', duration_pts=2, start_pts=0,
        average_rate_num=12, average_rate_den=1, revision=0,
        initial_frame=None, read_only=False)
    window._dataset_generation = window.task_coordinator.next_generation()
    window.document_kind = DocumentKind.VIDEO
    window.file_path = str(source)
    window.video_snapshot = snapshot
    window.video_model = VideoProjectModel()
    window.current_video_frame_ref = VideoFrameRef(
        fingerprint, 0, 0, 1, 12)
    window.continuous_save.reset(
        window._continuous_document_key(), window._dataset_generation, 0)
    return str(source), str(project)


class _RecordingDecoder:
    def __init__(self, on_close=None):
        self.close_count = 0
        self.on_close = on_close

    def close(self):
        self.close_count += 1
        if self.on_close is not None:
            self.on_close()


def _prepared_video(tmp_path, name, decoder=None, color=0xFF336699):
    source = tmp_path / ('%s.mp4' % name)
    source.write_bytes(('fixture-%s' % name).encode('ascii'))
    stat = source.stat()
    fingerprint = VideoFingerprint(
        stat.st_size, stat.st_mtime_ns, '%s-fingerprint' % name)
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(color)
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    frame_ref = VideoFrameRef(fingerprint, 0, 0, 1, 12)
    first = VideoFrameResult(
        frame_ref, image, 64, 48, 64, 48, 0, byte_size,
        '%s:0' % name)
    project = tmp_path / ('%s.labelimgpp.sqlite' % name)
    snapshot = VideoSessionSnapshot(
        source_path=str(source), project_path=str(project),
        fingerprint=fingerprint, stream_index=0, time_base_num=1,
        time_base_den=12, width=64, height=48, rotation=0,
        codec='fixture', duration_pts=2, start_pts=0,
        average_rate_num=12, average_rate_den=1, revision=0,
        initial_frame=first, read_only=False)
    initialize_project(str(project), snapshot)
    return PreparedVideoOpen(
        snapshot=snapshot, decoder=decoder or _RecordingDecoder(),
        tracks=(), observations=(), frame_states=(), classes=(), gaps=(),
        warning=None)


def _install_prepared_video(window, prepared):
    window._dataset_generation = window.task_coordinator.next_generation()
    window._commit_video_open(prepared)


def _add_and_save_video_observation(app, window, project, pts):
    track = window.video_model.tracks.get('track-1')
    if track is None:
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    window.video_model.upsert_manual(
        track.track_id, pts, [2 + pts, 3, 22 + pts, 23])
    window._on_video_model_mutation()
    window.continuous_save.flush()
    revision = window.video_model.revision
    assert _wait(app, lambda: (
        load_project(project).revision == revision
        and not window.video_model.dirty))
    return revision


def _add_video_observation(window, pts):
    track = window.video_model.tracks.get('track-1')
    if track is None:
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    window.video_model.upsert_manual(
        track.track_id, pts, [2 + pts, 3, 22 + pts, 23])
    window._on_video_model_mutation()
    return window.video_model.revision


def _block_background_lane(window):
    release = Event()
    started = []
    handles = []

    for _index in range(
            window.task_coordinator.pool('background').maxThreadCount()):
        worker_started = Event()
        started.append(worker_started)

        def block(_handle, signal=worker_started):
            signal.set()
            release.wait(5)

        handles.append(window.task_coordinator.submit(
            'background', block, priority=0))
    assert all(signal.wait(1) for signal in started)
    return release, handles


def test_synchronous_open_creates_sidecar_after_first_frame(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    project = default_project_path(video)
    try:
        assert not os.path.exists(project)
        assert window.open_video(video)
        assert os.path.isfile(project)
        assert window.document_kind == DocumentKind.VIDEO
        assert window.video_snapshot.project_path == project
        assert window.file_path == video
        assert not window.image.isNull()
        assert window.workspace_inspector.tabs.indexOf(
            window.file_controls) == 1
        assert window.frame_cache.max_images == 12
    finally:
        window.dirty = False
        window.close()


def test_async_failed_open_keeps_previous_image_document(
        tmp_path, make_video):
    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    try:
        window.request_open_video(str(tmp_path / 'missing.mp4'),
                                  skip_prompt=True)
        assert _wait(
            app, lambda: not window.task_coordinator.queue_depths()['video'])
        app.processEvents()
        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == str(image)
        assert not window.image.isNull()
    finally:
        window.dirty = False
        window.close()


def test_failed_video_replacement_keeps_save_identity_for_current_document(
        tmp_path):
    from libs.core.video_runtime import VideoRuntimeStatus

    app, window = get_main_app()
    current_source, project = _install_writable_video_document(
        window, tmp_path)
    committed_generation = window._dataset_generation
    replacement = tmp_path / 'replacement.mp4'
    replacement.write_bytes(b'failed replacement')
    ready = VideoRuntimeStatus(
        True, (), 'pip install "labelimgplusplus[video]"', 'Ready')
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=ready), patch(
                'libs.core.video_decoder.load_video_dependencies'), patch(
                'labelImgPlusPlus.prepare_video_open',
                side_effect=RuntimeError('replacement preparation failed')):
            window.request_open_video(str(replacement), skip_prompt=True)
            assert _wait(
                app, lambda: 'replacement preparation failed' in
                window.statusBar().currentMessage())

        assert window.file_path == current_source
        assert window._dataset_generation == committed_generation

        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_manual(track.track_id, 0, [2, 3, 22, 23])
        window._on_video_model_mutation()
        window.continuous_save.flush()
        first_revision = window.video_model.revision
        assert _wait(
            app, lambda: (
                load_project(project).revision == first_revision
                and not window.video_model.dirty))
        assert not window.video_model.dirty

        window.video_model.upsert_manual(
            track.track_id, 1, [3, 4, 23, 24])
        window._on_video_model_mutation()
        assert window.save_video_project()
        assert len(load_project(project).observations) == 2
    finally:
        window.dirty = False
        window.close()


def test_async_open_decodes_qimage_off_thread_and_builds_qpixmap_on_gui(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    decode_threads = []
    pixmap_threads = []
    from libs.core.video_decoder import VideoDecoderSession
    original_decode = VideoDecoderSession.decode_first
    original_from_image = QPixmap.fromImage

    def observed_decode(self, *args, **kwargs):
        decode_threads.append(QThread.currentThread() != app.thread())
        return original_decode(self, *args, **kwargs)

    def observed_pixmap(*args, **kwargs):
        pixmap_threads.append(QThread.currentThread() == app.thread())
        return original_from_image(*args, **kwargs)

    try:
        with patch.object(VideoDecoderSession, 'decode_first', observed_decode), \
                patch('labelImgPlusPlus.QPixmap.fromImage', observed_pixmap):
            window.request_open_video(video, skip_prompt=True)
            assert _wait(app, lambda: window.document_kind == DocumentKind.VIDEO)
        assert decode_threads == [True]
        assert pixmap_threads == [True]
    finally:
        window.dirty = False
        window.close()


def _assert_prior_video_restored(
        window, prepared, snapshot, timeline_snapshot, generation,
        revision, save_identity, model, pixmap_key):
    assert window.document_kind == DocumentKind.VIDEO
    assert window.file_path == prepared.snapshot.source_path
    assert window.video_decoder is prepared.decoder
    assert window.video_snapshot is snapshot
    assert window.video_model is model
    assert window.current_video_frame_ref == \
        snapshot.initial_frame.frame_ref
    assert window._dataset_generation == generation
    assert window._document_revision == revision
    assert window._save_document_identity() == save_identity
    assert window.canvas.pixmap.cacheKey() == pixmap_key
    assert window.canvas.isEnabled()
    assert window.video_timeline._snapshot is timeline_snapshot
    assert window.actions.videoPlayPause.isEnabled()
    assert window.actions.saveAs.isEnabled()
    assert window._plugin_document_ready


def test_async_publication_failure_rolls_back_prior_video_and_save_owner(
        tmp_path):
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    candidate_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'prior-async', old_decoder)
    candidate = _prepared_video(
        tmp_path, 'candidate-async', candidate_decoder, color=0xFF993322)
    try:
        _install_prepared_video(window, prior)
        prior_revision = _add_and_save_video_observation(
            app, window, prior.snapshot.project_path, 0)
        window._refresh_video_timeline_markers()
        window.canvas.setFocus(Qt.OtherFocusReason)
        app.processEvents()
        prior_generation = window._dataset_generation
        prior_snapshot = window.video_snapshot
        prior_timeline_snapshot = window.video_timeline._snapshot
        prior_save_identity = window._save_document_identity()
        prior_model = window.video_model
        prior_pixmap_key = window.canvas.pixmap.cacheKey()
        prior_plugin_generation = window._plugin_document_generation
        assert window._plugin_document_ready
        prior_marker_groups = window.video_timeline.slider.marker_groups()
        owner = ('video', window._video_open_request_id)
        window._show_replacement_loading(owner, 'Opening candidate…')
        original_materialize = window._materialize_video_frame

        def fail_after_reset(pts):
            if window.file_path == candidate.snapshot.source_path:
                raise RuntimeError('fail after destructive publication')
            return original_materialize(pts)

        with patch.object(
                window, '_materialize_video_frame',
                side_effect=fail_after_reset):
            window._on_video_open_result(
                candidate, window._video_open_request_id,
                prior_generation, requested_path=candidate.snapshot.source_path)

        _assert_prior_video_restored(
            window, prior, prior_snapshot, prior_timeline_snapshot,
            prior_generation, prior_revision,
            prior_save_identity, prior_model, prior_pixmap_key)
        assert window._plugin_document_generation == prior_plugin_generation
        assert window.video_timeline.slider.marker_groups() == \
            prior_marker_groups
        assert candidate_decoder.close_count == 1
        assert old_decoder.close_count == 0
        assert window._loading_veil.isHidden()
        assert window._replacement_loading_owner is None
        assert 'fail after destructive publication' in \
            window.statusBar().currentMessage()
        assert window.canvas.hasFocus()

        second_revision = _add_and_save_video_observation(
            app, window, prior.snapshot.project_path, 1)
        assert second_revision > prior_revision
        assert len(load_project(
            prior.snapshot.project_path).observations) == 2
        assert old_decoder.close_count == 0
    finally:
        window.dirty = False
        window.close()


def test_async_publication_failure_preserves_pending_save_and_drains_newest(
        tmp_path):
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    candidate_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'pending-prior', old_decoder)
    candidate = _prepared_video(
        tmp_path, 'pending-candidate', candidate_decoder, color=0xFF663399)
    release, blockers = _block_background_lane(window)
    try:
        _install_prepared_video(window, prior)
        first_revision = _add_video_observation(window, 0)
        window.continuous_save.flush()
        prior_handle = window._video_save_handle
        prior_ticket = window.continuous_save._in_flight
        prior_generation = window._dataset_generation
        prior_snapshot = window.video_snapshot
        prior_timeline_snapshot = window.video_timeline._snapshot
        prior_save_identity = window._save_document_identity()
        prior_model = window.video_model
        prior_pixmap_key = window.canvas.pixmap.cacheKey()
        prior_plugin_generation = window._plugin_document_generation
        owner = ('video', window._video_open_request_id)
        window._show_replacement_loading(owner, 'Opening candidate…')
        original_materialize = window._materialize_video_frame

        assert prior_handle is not None
        assert prior_ticket.revision == first_revision
        assert window.task_coordinator.has_active_handle(prior_handle)

        def fail_after_reset(pts):
            if window.file_path == candidate.snapshot.source_path:
                raise RuntimeError('pending save publication failure')
            return original_materialize(pts)

        with patch.object(
                window, '_materialize_video_frame',
                side_effect=fail_after_reset):
            window._on_video_open_result(
                candidate, window._video_open_request_id,
                prior_generation, requested_path=candidate.snapshot.source_path)

        _assert_prior_video_restored(
            window, prior, prior_snapshot, prior_timeline_snapshot,
            prior_generation, first_revision,
            prior_save_identity, prior_model, prior_pixmap_key)
        assert window._plugin_document_generation == prior_plugin_generation
        assert window.continuous_save._in_flight == prior_ticket
        assert window._video_save_handle is prior_handle
        assert not prior_handle.is_cancelled()
        assert window.task_coordinator.has_active_handle(prior_handle)
        assert candidate_decoder.close_count == 1
        assert old_decoder.close_count == 0
        assert window._loading_veil.isHidden()
        assert window._replacement_loading_owner is None

        second_revision = _add_video_observation(window, 1)
        assert second_revision > first_revision
        release.set()
        assert _wait(app, lambda: (
            load_project(prior.snapshot.project_path).revision
            == second_revision
            and window.continuous_save.is_drained))
        durable = load_project(prior.snapshot.project_path)
        assert durable.revision == second_revision
        assert len(durable.observations) == 2
        assert not window.video_model.dirty
    finally:
        release.set()
        for handle in blockers:
            handle.cancel()
        window.dirty = False
        window.close()


def test_synchronous_publication_failure_rolls_back_prior_video_and_saves(
        tmp_path):
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    candidate_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'prior-sync', old_decoder)
    candidate = _prepared_video(
        tmp_path, 'candidate-sync', candidate_decoder, color=0xFF225588)
    try:
        _install_prepared_video(window, prior)
        prior_revision = _add_and_save_video_observation(
            app, window, prior.snapshot.project_path, 0)
        prior_generation = window._dataset_generation
        prior_snapshot = window.video_snapshot
        prior_timeline_snapshot = window.video_timeline._snapshot
        prior_save_identity = window._save_document_identity()
        prior_model = window.video_model
        prior_pixmap_key = window.canvas.pixmap.cacheKey()
        assert window._plugin_document_ready
        original_materialize = window._materialize_video_frame

        def fail_after_reset(pts):
            if window.file_path == candidate.snapshot.source_path:
                raise RuntimeError('sync failure after reset')
            return original_materialize(pts)

        with patch(
                'labelImgPlusPlus.prepare_video_open',
                return_value=candidate), patch.object(
                window, '_video_project_target',
                return_value=(candidate.snapshot.project_path, False)), \
                patch.object(
                    window, '_materialize_video_frame',
                    side_effect=fail_after_reset):
            assert window.open_video(candidate.snapshot.source_path) is False

        _assert_prior_video_restored(
            window, prior, prior_snapshot, prior_timeline_snapshot,
            prior_generation, prior_revision,
            prior_save_identity, prior_model, prior_pixmap_key)
        assert candidate_decoder.close_count == 1
        assert old_decoder.close_count == 0
        assert window._loading_veil is None or window._loading_veil.isHidden()
        assert 'sync failure after reset' in window.statusBar().currentMessage()

        _add_and_save_video_observation(
            app, window, prior.snapshot.project_path, 1)
        assert len(load_project(
            prior.snapshot.project_path).observations) == 2
    finally:
        window.dirty = False
        window.close()


def test_sync_publication_failure_preserves_running_save_and_drains_newest(
        tmp_path):
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    candidate_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'running-prior', old_decoder)
    candidate = _prepared_video(
        tmp_path, 'running-candidate', candidate_decoder, color=0xFF224466)
    started = Event()
    release = Event()

    def blocked_save(*args, **kwargs):
        started.set()
        release.wait(5)
        return save_project_delta(*args, **kwargs)

    try:
        _install_prepared_video(window, prior)
        with patch('labelImgPlusPlus.save_project_delta', blocked_save):
            first_revision = _add_video_observation(window, 0)
            window.continuous_save.flush()
            assert started.wait(1)
            prior_handle = window._video_save_handle
            prior_ticket = window.continuous_save._in_flight
            prior_generation = window._dataset_generation
            prior_snapshot = window.video_snapshot
            prior_timeline_snapshot = window.video_timeline._snapshot
            prior_save_identity = window._save_document_identity()
            prior_model = window.video_model
            prior_pixmap_key = window.canvas.pixmap.cacheKey()
            original_materialize = window._materialize_video_frame

            def fail_after_reset(pts):
                if window.file_path == candidate.snapshot.source_path:
                    raise RuntimeError('running save publication failure')
                return original_materialize(pts)

            with patch(
                    'labelImgPlusPlus.prepare_video_open',
                    return_value=candidate), patch.object(
                    window, '_video_project_target',
                    return_value=(candidate.snapshot.project_path, False)), \
                    patch.object(window, 'may_continue', return_value=True), \
                    patch.object(
                        window, '_materialize_video_frame',
                        side_effect=fail_after_reset):
                assert window.open_video(
                    candidate.snapshot.source_path) is False

            _assert_prior_video_restored(
                window, prior, prior_snapshot, prior_timeline_snapshot,
                prior_generation, first_revision,
                prior_save_identity, prior_model, prior_pixmap_key)
            assert window.continuous_save._in_flight == prior_ticket
            assert window._video_save_handle is prior_handle
            assert not prior_handle.is_cancelled()
            assert window.task_coordinator.has_active_handle(prior_handle)
            assert candidate_decoder.close_count == 1
            assert old_decoder.close_count == 0
            assert window._loading_veil is None or \
                window._loading_veil.isHidden()

            second_revision = _add_video_observation(window, 1)
            release.set()
            assert _wait(app, lambda: (
                load_project(prior.snapshot.project_path).revision
                == second_revision
                and window.continuous_save.is_drained))
            durable = load_project(prior.snapshot.project_path)
            assert durable.revision == second_revision
            assert len(durable.observations) == 2
            assert not window.video_model.dirty
    finally:
        release.set()
        window.dirty = False
        window.close()


def test_failed_video_publication_restores_existing_image_workspace(
        tmp_path):
    _app, window = get_main_app()
    image = tmp_path / 'prior-image.png'
    _image(image)
    candidate_decoder = _RecordingDecoder()
    candidate = _prepared_video(
        tmp_path, 'candidate-over-image', candidate_decoder)
    try:
        assert window.load_file(str(image))
        prior_generation = window._dataset_generation
        prior_pixmap_key = window.canvas.pixmap.cacheKey()
        original_materialize = window._materialize_video_frame

        def fail_after_reset(pts):
            if window.file_path == candidate.snapshot.source_path:
                raise RuntimeError('image rollback')
            return original_materialize(pts)

        with patch(
                'labelImgPlusPlus.prepare_video_open',
                return_value=candidate), patch.object(
                window, '_video_project_target',
                return_value=(candidate.snapshot.project_path, False)), \
                patch.object(
                    window, '_materialize_video_frame',
                    side_effect=fail_after_reset):
            assert window.open_video(candidate.snapshot.source_path) is False

        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == str(image)
        assert window._dataset_generation == prior_generation
        assert window.canvas.pixmap.cacheKey() == prior_pixmap_key
        assert window.canvas.isEnabled()
        assert window.actions.create.isEnabled()
        assert window._plugin_document_ready
        assert candidate_decoder.close_count == 1
    finally:
        window.dirty = False
        window.close()


def test_failed_image_publication_does_not_close_restored_video_decoder(
        tmp_path):
    """A post-reset image failure must leave the live video decoder usable."""
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'image-rollback-prior', old_decoder)
    candidate = tmp_path / 'image-rollback-candidate.png'
    _image(candidate)
    try:
        _install_prepared_video(window, prior)
        prior_generation = window._dataset_generation
        prior_snapshot = window.video_snapshot
        prior_timeline_snapshot = window.video_timeline._snapshot
        prior_save_identity = window._save_document_identity()
        prior_model = window.video_model
        prior_pixmap_key = window.canvas.pixmap.cacheKey()
        prior_identity = window.document_identity
        original_publish = window._publish_plugin_document

        def fail_after_reset(*args, **kwargs):
            if (window.document_kind == DocumentKind.IMAGE
                    and window.file_path == str(candidate)):
                raise RuntimeError('image publication failed after reset')
            return original_publish(*args, **kwargs)

        with patch.object(
                window, '_publish_plugin_document',
                side_effect=fail_after_reset):
            assert window.load_file(str(candidate)) is False

        assert _wait(
            app,
            lambda: not window.task_coordinator.queue_depths()['video'])
        _assert_prior_video_restored(
            window, prior, prior_snapshot, prior_timeline_snapshot,
            prior_generation, 0, prior_save_identity, prior_model,
            prior_pixmap_key)
        assert window.document_identity == prior_identity
        assert old_decoder.close_count == 0
        assert window.inline_open_error.isVisible()
    finally:
        window.dirty = False
        window.close()


def test_successful_publication_closes_old_decoder_after_candidate_commit(
        tmp_path):
    app, window = get_main_app()
    candidate_decoder = _RecordingDecoder()
    candidate = _prepared_video(tmp_path, 'successful-candidate',
                                candidate_decoder)
    close_observations = []

    def observe_close():
        close_observations.append((
            window.video_decoder is candidate_decoder,
            window.video_snapshot is candidate.snapshot,
            window.video_timeline._snapshot is candidate.snapshot,
            window.file_path == candidate.snapshot.source_path,
            window._plugin_document_ready,
        ))

    old_decoder = _RecordingDecoder(on_close=observe_close)
    prior = _prepared_video(tmp_path, 'successful-prior', old_decoder)
    try:
        _install_prepared_video(window, prior)
        prior_generation = window._dataset_generation

        with patch(
                'labelImgPlusPlus.prepare_video_open',
                return_value=candidate), patch.object(
                window, '_video_project_target',
                return_value=(candidate.snapshot.project_path, False)):
            assert window.open_video(candidate.snapshot.source_path) is True

        assert _wait(app, lambda: old_decoder.close_count == 1)
        assert close_observations == [(True, True, True, True, True)]
        assert candidate_decoder.close_count == 0
        assert window._dataset_generation != prior_generation
    finally:
        window.dirty = False
        window.close()


def test_successful_publication_identity_gates_preserved_old_save_callback(
        tmp_path):
    app, window = get_main_app()
    old_decoder = _RecordingDecoder()
    candidate_decoder = _RecordingDecoder()
    prior = _prepared_video(tmp_path, 'successful-save-prior', old_decoder)
    candidate = _prepared_video(
        tmp_path, 'successful-save-candidate', candidate_decoder)
    started = Event()
    release = Event()

    def blocked_save(*args, **kwargs):
        started.set()
        release.wait(5)
        return save_project_delta(*args, **kwargs)

    try:
        _install_prepared_video(window, prior)
        with patch('labelImgPlusPlus.save_project_delta', blocked_save):
            old_revision = _add_video_observation(window, 0)
            window.continuous_save.flush()
            assert started.wait(1)
            old_handle = window._video_save_handle

            with patch(
                    'labelImgPlusPlus.prepare_video_open',
                    return_value=candidate), patch.object(
                    window, '_video_project_target',
                    return_value=(candidate.snapshot.project_path, False)), \
                    patch.object(window, 'may_continue', return_value=True):
                assert window.open_video(
                    candidate.snapshot.source_path) is True

            assert not old_handle.is_cancelled()
            assert window.task_coordinator.has_active_handle(old_handle)
            candidate_generation = window._dataset_generation
            candidate_snapshot = window.video_snapshot
            candidate_model = window.video_model
            window.continuous_save.set_enabled(False)
            candidate_revision = _add_video_observation(window, 0)
            assert candidate_model.dirty

            release.set()
            assert _wait(app, lambda: (
                load_project(prior.snapshot.project_path).revision
                == old_revision
                and not window.task_coordinator.has_active_handle(old_handle)))
            assert window.document_kind == DocumentKind.VIDEO
            assert window.file_path == candidate.snapshot.source_path
            assert window.video_decoder is candidate_decoder
            assert window.video_snapshot is candidate_snapshot
            assert window.video_model is candidate_model
            assert window._dataset_generation == candidate_generation
            assert window.video_model.dirty
            assert window.continuous_save.state == 'pending'
            assert window.continuous_save._durable_revision == 0

            window.continuous_save.set_enabled(True)
            assert _wait(app, lambda: (
                load_project(candidate.snapshot.project_path).revision
                == candidate_revision
                and window.continuous_save.is_drained))
            durable_candidate = load_project(candidate.snapshot.project_path)
            assert durable_candidate.revision == candidate_revision
            assert len(durable_candidate.observations) == 1
            assert not window.video_model.dirty
    finally:
        release.set()
        window.dirty = False
        window.close()


def test_missing_optional_dependencies_leave_current_document_untouched(
        tmp_path, make_video):
    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    video = make_video(tmp_path / 'clip.mp4')
    assert window.load_file(str(image))
    try:
        with patch(
                'libs.core.video_decoder.load_video_dependencies',
                side_effect=VideoDependencyError('install [video]')):
            window.request_open_video(video, skip_prompt=True)
            assert _wait(
                app, lambda: not window.task_coordinator.queue_depths()['video'])
        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == str(image)
        assert 'install [video]' in window.statusBar().currentMessage()
    finally:
        window.dirty = False
        window.close()


def test_cli_positional_argument_accepts_video_project(tmp_path, make_video):
    app, first = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    assert first.open_video(video)
    project = first.video_snapshot.project_path
    first.dirty = False
    first.close()

    _same_app, window = get_main_app(['labelimgpp', project])
    source_problems = []
    try:
        assert _same_app is app
        with patch.object(
                window, '_video_source_changed_choice',
                side_effect=lambda message: source_problems.append(message)
                or 'cancel'):
            assert _wait(
                app, lambda: window.document_kind == DocumentKind.VIDEO
                or bool(source_problems))
        assert not source_problems, source_problems
        assert window.video_snapshot.project_path == project
        assert window.file_path == video
    finally:
        window.dirty = False
        window.close()


def test_missing_project_source_can_be_located_and_relinked(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    assert window.open_video(video)
    project = window.video_snapshot.project_path
    # Windows does not permit replacing a media file while the decoder owns
    # its file handle. A moved-source project is reopened after the original
    # document has been closed, which is also the real user workflow.
    window.reset_state()
    assert _wait(
        app, lambda: not window.task_coordinator.queue_depths()['video'])
    moved = tmp_path / 'moved.mp4'
    os.replace(video, moved)
    try:
        with patch(
                'labelImgPlusPlus.QFileDialog.getOpenFileName',
                return_value=(str(moved), 'Video files')):
            window.request_open_video(project, skip_prompt=True)
            assert _wait(app, window.inline_open_error.isVisible)
            window.inline_open_error.choose_button.click()
            assert _wait(
                app, lambda: window.video_snapshot is not None
                and window.video_snapshot.source_path == str(moved))
        assert read_project_source(project).absolute_path == str(moved)
    finally:
        window.dirty = False
        window.close()


def test_changed_source_can_create_a_separate_project(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    assert window.open_video(video)
    old_project = window.video_snapshot.project_path
    make_video(tmp_path / 'clip.mp4', width=80, height=64)
    new_project = str(tmp_path / 'changed.labelimgpp.sqlite')
    try:
        with patch(
                'labelImgPlusPlus.QFileDialog.getSaveFileName',
                return_value=(new_project, 'LabelImg++ video project')):
            window.request_open_video(video, skip_prompt=True)
            assert _wait(app, window.inline_open_error.isVisible)
            window.inline_open_error.choose_button.click()
            assert _wait(
                app, lambda: window.video_snapshot is not None
                and window.video_snapshot.project_path == new_project)
        assert os.path.isfile(old_project)
        assert os.path.isfile(new_project)
        assert window.video_snapshot.width == 80
    finally:
        window.dirty = False
        window.close()


def test_read_only_video_blocks_controller_mutations_and_keeps_clean(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'read-only.mp4')
    try:
        assert window.open_video(video)
        pts = window.current_video_frame_ref.pts
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_manual(
            track.track_id, pts, [2, 3, 22, 23])
        window._on_video_model_mutation()
        assert window.save_video_project()
        project = window.video_snapshot.project_path

        with patch.object(
                window, '_video_project_target', return_value=(project, True)):
            assert window.open_video(video)
        before = window.video_model.snapshot_state()
        shape = window.canvas.shapes[0]
        index = window.annotation_model.index_for_identity('track-1')
        window.canvas.select_shape(shape)

        assert window.video_snapshot.read_only is True
        assert window.canvas.locked is True
        assert window.label_save_status.text() == '● Read-only'
        assert window.label_save_status.toolTip() == 'Read-only'
        assert not window.actions.verify.isEnabled()
        assert not window.actions.delete.isEnabled()
        assert not window.actions.videoAddKeyframe.isEnabled()
        assert window.request_verify_image() is None
        window.delete_selected_shape()
        window.add_track_keyframe()
        window.annotation_model.setData(index, 'changed', Qt.EditRole)
        window.copy_to_clipboard()
        window.set_dirty()
        assert window.label_save_status.text() == '● Read-only'

        assert window.video_model.snapshot_state() == before
        index = window.annotation_model.index_for_identity('track-1')
        assert window.annotation_model.data(index, Qt.EditRole) == 'car'
        assert not window.actions.pasteFromClipboard.isEnabled()
        assert window.dirty is False
        assert window.request_save_video_project() is None
        assert window.label_save_status.text() == '● Read-only'
        assert window.label_save_status.toolTip() == 'Read-only'
    finally:
        window.dirty = False
        window.close()


def test_failed_v1_migration_surfaces_warning_and_preserves_pending_rows(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'legacy.mp4')
    try:
        assert window.open_video(video)
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        pending = ObservationRecord(
            track.track_id, window.current_video_frame_ref.pts,
            [2, 3, 22, 23], source='tracker', review_state='pending',
            anchor=False, quality=.75)
        window.video_model.upsert_tracker(pending)
        window._on_video_model_mutation()
        assert window.save_video_project()
        project = window.video_snapshot.project_path
        window.reset_state()

        connection = sqlite3.connect(project)
        try:
            connection.execute('DROP TABLE track_gaps')
            connection.execute(
                'UPDATE project_meta SET schema_version=1 WHERE singleton=1')
            connection.execute('PRAGMA user_version=1')
            connection.commit()
        finally:
            connection.close()

        from libs.core import video_project
        create_schema = video_project._create_track_gaps_schema

        def fail_after_schema(connection):
            create_schema(connection)
            raise sqlite3.OperationalError('simulated full disk')

        with patch.object(
                video_project, '_create_track_gaps_schema',
                fail_after_schema):
            assert window.open_video(project)

        loaded = window.video_model.observations[
            ('track-1', pending.pts)]
        assert window.video_snapshot.read_only is True
        assert loaded.review_state == 'pending'
        assert loaded.quality == .75
        assert 'reopened read-only' in window.statusBar().currentMessage()
        assert not window.actions.save.isEnabled()
    finally:
        window.dirty = False
        window.close()


def test_opening_a_video_leaves_gallery_mode(tmp_path, make_video):
    """A video has no gallery representation.

    Regression: with gallery mode persisted on, _set_document_kind skipped the
    page switch entirely, so the clip loaded behind an empty gallery page and
    the user saw a blank workspace with no frame and no timeline.
    """
    _app, window = get_main_app()
    try:
        window.toggle_gallery_mode(True)
        assert window.gallery_mode_enabled
        assert window.workspace_pages.current_page() == 'gallery'

        assert window.open_video(make_video(tmp_path / 'clip.mp4'))

        assert window.document_kind == DocumentKind.VIDEO
        assert not window.gallery_mode_enabled
        assert window.workspace_pages.current_page() == 'canvas'
        assert not window.actions.galleryMode.isChecked()
        assert window.workspace_pages.timeline.isVisible()

        # The gallery must also be unreachable while the video is open,
        # otherwise re-entering it strands the user on an empty page.
        assert not window.actions.galleryMode.isEnabled()
        window.toggle_gallery_mode(True)
        assert not window.gallery_mode_enabled
        assert window.workspace_pages.current_page() == 'canvas'
        assert window.workspace_pages.timeline.isVisible()
    finally:
        window.dirty = False
        window.close()


def test_gallery_becomes_available_again_after_the_video_closes(
        tmp_path, make_video):
    """Disabling the gallery for video must not be a one-way trip."""
    _app, window = get_main_app()
    try:
        assert window.open_video(make_video(tmp_path / 'clip.mp4'))
        assert not window.actions.galleryMode.isEnabled()

        window.reset_state()
        assert window.document_kind == DocumentKind.NONE
        assert window.actions.galleryMode.isEnabled()
    finally:
        window.dirty = False
        window.close()


def test_missing_runtime_short_circuits_before_touching_current_document(
        tmp_path):
    from libs.core.video_runtime import VideoRuntimeStatus

    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    committed_generation = window._dataset_generation
    window.dirty = True
    missing = VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av')
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=missing), patch.object(
                window, 'discard_changes_dialog') as save_prompt, patch.object(
                window, '_video_project_target') as project_target, patch(
                'libs.core.video_decoder.load_video_dependencies') \
                as load_dependencies, patch(
                'labelImgPlusPlus.prepare_video_open') as prepare:
            assert window.request_open_video(
                str(tmp_path / 'clip.mp4')) is None

        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == str(image)
        assert window.dirty is True
        assert window._dataset_generation == committed_generation
        assert window.workspace_pages.current_page() == 'canvas'
        assert not window.workspace_pages.video_setup_overlay.isHidden()
        assert window.workspace_pages.video_setup_card.detail.text() == \
            'Missing optional component: av'
        assert not window.task_coordinator.queue_depths()['video']
        save_prompt.assert_not_called()
        project_target.assert_not_called()
        load_dependencies.assert_not_called()
        prepare.assert_not_called()
        app.processEvents()
    finally:
        window.dirty = False
        window.close()


def test_missing_runtime_supersedes_delayed_image_result(tmp_path):
    from libs.core.image_pipeline import load_image_result

    app, window = get_main_app()
    current = tmp_path / 'current.png'
    delayed = tmp_path / 'delayed.png'
    _image(current)
    _image(delayed)
    assert window.load_file(str(current))
    result = load_image_result(str(delayed))
    request_id = window._load_request_id
    committed_generation = window._dataset_generation
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=_missing_runtime_status()):
            window.request_open_video(
                str(tmp_path / 'missing-runtime.mp4'), skip_prompt=True)

        window._on_image_result(
            result, request_id, committed_generation)
        app.processEvents()

        assert window.file_path == str(current)
        assert window._dataset_generation == committed_generation
        assert not window.workspace_pages.video_setup_overlay.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_missing_runtime_supersedes_delayed_video_and_closes_decoder(
        tmp_path):
    class Decoder:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    _app, window = get_main_app()
    current = tmp_path / 'current.png'
    _image(current)
    assert window.load_file(str(current))
    decoder = Decoder()
    prepared = SimpleNamespace(decoder=decoder)
    request_id = window._video_open_request_id
    committed_generation = window._dataset_generation
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=_missing_runtime_status()):
            window.request_open_video(
                str(tmp_path / 'missing-runtime.mp4'), skip_prompt=True)

        with patch.object(window, '_commit_video_open') as commit:
            window._on_video_open_result(
                prepared, request_id, committed_generation,
                requested_path=str(tmp_path / 'old.mp4'))

        commit.assert_not_called()
        assert decoder.closed
        assert window.file_path == str(current)
        assert window._dataset_generation == committed_generation
        assert not window.workspace_pages.video_setup_overlay.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_missing_runtime_supersedes_blocked_video_before_gui_delivery(
        tmp_path):
    from threading import Event

    from libs.core.video_runtime import VideoRuntimeStatus

    class Decoder:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    app, window = get_main_app()
    current = tmp_path / 'current.png'
    _image(current)
    assert window.load_file(str(current))
    window.show()
    app.processEvents()
    committed_generation = window._dataset_generation
    started = Event()
    release = Event()
    decoder = Decoder()
    prepared = SimpleNamespace(decoder=decoder)
    ready = VideoRuntimeStatus(
        True, (), 'pip install "labelimgplusplus[video]"', 'Ready')

    def blocked_prepare(*_args, **_kwargs):
        started.set()
        assert release.wait(1)
        return prepared

    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                side_effect=(ready, _missing_runtime_status())), patch(
                'libs.core.video_decoder.load_video_dependencies',
                return_value=(object(), object())), patch(
                'labelImgPlusPlus.prepare_video_open',
                side_effect=blocked_prepare):
            window.request_open_video(
                str(tmp_path / 'blocked.mp4'), skip_prompt=True)
            assert started.wait(1)
            assert not window._loading_veil.isHidden()
            release.set()
            assert window.task_coordinator.pool('video').waitForDone(1000)
            assert not decoder.closed

            window.request_open_video(
                str(tmp_path / 'missing-runtime.mp4'), skip_prompt=True)
            app.processEvents()

        assert decoder.closed
        assert window.file_path == str(current)
        assert window._dataset_generation == committed_generation
        assert window.workspace_pages.video_setup_overlay.isVisible()
        assert window.workspace_pages.video_setup_card.isEnabled()
        assert window._loading_veil.isHidden()
        assert window.canvas.isEnabled()
    finally:
        release.set()
        _wait(
            app, lambda: not window.task_coordinator.queue_depths()['video'])
        window.dirty = False
        window.close()


def test_missing_runtime_supersedes_blocked_image_and_restores_canvas(
        tmp_path):
    from threading import Event

    from libs.core.image_pipeline import load_image_result

    app, window = get_main_app()
    current = tmp_path / 'current.png'
    replacement = tmp_path / 'replacement.png'
    _image(current)
    _image(replacement)
    assert window.load_file(str(current))
    window.show()
    app.processEvents()
    committed_generation = window._dataset_generation
    delayed_result = load_image_result(str(replacement))
    started = Event()
    release = Event()

    def blocked_load(*_args, **_kwargs):
        started.set()
        assert release.wait(1)
        return delayed_result

    try:
        with patch(
                'labelImgPlusPlus.load_image_result',
                side_effect=blocked_load):
            window.request_load_file(str(replacement), skip_prompt=True)
            assert started.wait(1)
            assert window.canvas.isEnabled()
            assert not window._loading_veil.isHidden()

            with patch(
                    'labelImgPlusPlus.probe_video_runtime',
                    return_value=_missing_runtime_status()):
                window.request_open_video(
                    str(tmp_path / 'missing-runtime.mp4'), skip_prompt=True)

            assert window.workspace_pages.video_setup_overlay.isVisible()
            assert window.workspace_pages.video_setup_card.isEnabled()
            assert window._loading_veil.isHidden()
            assert window.canvas.isEnabled()
            assert window.file_path == str(current)
            assert window._dataset_generation == committed_generation
    finally:
        release.set()
        _wait(
            app, lambda: not
            window.task_coordinator.queue_depths()['interactive'])
        window.dirty = False
        window.close()


def test_video_setup_choose_another_reopens_file_chooser(tmp_path):
    from libs.core.video_runtime import VideoRuntimeStatus

    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    missing = VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av')
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=missing):
            window.request_open_video(
                str(tmp_path / 'clip.mp4'), skip_prompt=True)

        with patch.object(window, 'open_video_dialog') as open_dialog:
            window.workspace_pages.video_setup_card \
                .choose_another_button.click()

        assert window.workspace_pages.video_setup_overlay.isHidden()
        open_dialog.assert_called_once_with()
        app.processEvents()
    finally:
        window.dirty = False
        window.close()


def test_closing_video_setup_returns_focus_to_current_canvas(tmp_path):
    from libs.core.video_runtime import VideoRuntimeStatus

    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    window.show()
    app.processEvents()
    missing = VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av')
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=missing):
            window.request_open_video(
                str(tmp_path / 'clip.mp4'), skip_prompt=True)
        window.workspace_pages.video_setup_card.close_button.click()
        app.processEvents()

        assert window.workspace_pages.video_setup_overlay.isHidden()
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_closing_video_setup_restores_prior_focus_on_every_workspace_page(
        tmp_path):
    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    window.show()
    app.processEvents()
    empty_action = next(
        button for button in
        window.workspace_pages.empty_page.findChildren(QPushButton)
        if button.text() == 'Open Image')
    canvas_action = window.workspace_pages.canvas_chrome \
        .findChildren(QToolButton)[0]
    cases = (
        ('canvas', canvas_action),
        ('empty', empty_action),
        ('gallery', window.full_gallery.list_widget),
    )
    try:
        for page, target in cases:
            window.workspace_pages.set_page(page)
            target.setFocus(Qt.OtherFocusReason)
            app.processEvents()
            assert QApplication.focusWidget() is target

            window._show_video_runtime_setup(
                str(tmp_path / 'clip.mp4'), _missing_runtime_status())
            window.workspace_pages.video_setup_card.close_button.click()
            app.processEvents()

            assert window.workspace_pages.video_setup_overlay.isHidden()
            assert QApplication.focusWidget() is target
    finally:
        window.dirty = False
        window.close()


def test_canceling_choose_another_restores_prior_empty_page_focus(tmp_path):
    app, window = get_main_app()
    window.show()
    window.workspace_pages.set_page('empty')
    target = next(
        button for button in
        window.workspace_pages.empty_page.findChildren(QPushButton)
        if button.text() == 'Open Folder')
    target.setFocus(Qt.OtherFocusReason)
    app.processEvents()
    assert QApplication.focusWidget() is target
    try:
        window._show_video_runtime_setup(
            str(tmp_path / 'clip.mp4'), _missing_runtime_status())
        with patch(
                'labelImgPlusPlus.QFileDialog.getOpenFileName',
                return_value=('', '')):
            window.workspace_pages.video_setup_card \
                .choose_another_button.click()
        app.processEvents()

        assert window.workspace_pages.video_setup_overlay.isHidden()
        assert QApplication.focusWidget() is target
    finally:
        window.dirty = False
        window.close()


def test_opening_image_hides_visible_video_setup(tmp_path):
    app, window = get_main_app()
    current = tmp_path / 'current.png'
    replacement = tmp_path / 'replacement.png'
    _image(current)
    _image(replacement)
    assert window.load_file(str(current))
    try:
        window._show_video_runtime_setup(
            str(tmp_path / 'clip.mp4'), _missing_runtime_status())
        assert not window.workspace_pages.video_setup_overlay.isHidden()

        window.request_open_file(str(replacement), skip_prompt=True)

        assert window.workspace_pages.video_setup_overlay.isHidden()
        assert _wait(app, lambda: window.file_path == str(replacement))
        assert window.workspace_pages.video_setup_overlay.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_reset_dataset_close_and_window_close_hide_video_setup(tmp_path):
    app, window = get_main_app()
    try:
        window._show_video_runtime_setup(
            str(tmp_path / 'reset.mp4'), _missing_runtime_status())
        window.reset_state()
        assert window.workspace_pages.video_setup_overlay.isHidden()

        window._show_video_runtime_setup(
            str(tmp_path / 'dataset.mp4'), _missing_runtime_status())
        window.close_file()
        assert window.workspace_pages.video_setup_overlay.isHidden()

        window._show_video_runtime_setup(
            str(tmp_path / 'window.mp4'), _missing_runtime_status())
        window.close()
        app.processEvents()
        assert window.workspace_pages.video_setup_overlay.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_dependency_import_race_shows_setup_without_submitting_work(tmp_path):
    from libs.core.video_runtime import VideoRuntimeStatus

    _app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    assert window.load_file(str(image))
    committed_generation = window._dataset_generation
    ready = VideoRuntimeStatus(
        True, (), 'pip install "labelimgplusplus[video]"', 'Ready')
    try:
        with patch(
                'labelImgPlusPlus.probe_video_runtime',
                return_value=ready), patch(
                'libs.core.video_decoder.load_video_dependencies',
                side_effect=VideoDependencyError('av disappeared')):
            assert window.request_open_video(
                str(tmp_path / 'clip.mp4'), skip_prompt=True) is None

        assert window.file_path == str(image)
        assert window._dataset_generation == committed_generation
        assert not window.workspace_pages.video_setup_overlay.isHidden()
        assert 'av disappeared' in \
            window.workspace_pages.video_setup_card.detail.text()
        assert not window.task_coordinator.queue_depths()['video']
    finally:
        window.dirty = False
        window.close()
