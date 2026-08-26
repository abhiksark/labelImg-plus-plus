"""Bounded ownership checks for repeated image, video, and Assist work."""

import fractions
import threading
import time
from unittest.mock import patch

import pytest
from PyQt5.QtCore import QEventLoop
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QTest

import labelImgPlusPlus as app_mod
from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.assist_state import AssistPhase, AssistPrompt
from libs.core.video_types import PropagationResult, VideoFrameRef
from libs.integrations.model_cache import ModelDownloadCancelled
from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST
from tools.performance.profile_video import run_video_soak


def _wait(application, predicate, timeout=5.0):
    """Drive only Qt events until one observable lifecycle condition settles."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents(QEventLoop.AllEvents, 10)
        if predicate():
            return True
        QTest.qWait(1)
    return False


def _write_image(path, color):
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(str(path), 'PNG')


def _make_vfr_video(path, frames=24, width=96, height=64, rate=12):
    av = pytest.importorskip('av')
    numpy = pytest.importorskip('numpy')
    output = av.open(str(path), mode='w')
    stream = output.add_stream('mpeg4', rate=rate)
    stream.width = width
    stream.height = height
    stream.pix_fmt = 'yuv420p'
    stream.gop_size = 6
    for index in range(frames):
        pixels = numpy.zeros((height, width, 3), dtype=numpy.uint8)
        pixels[:, :, 0] = (index * 19) % 255
        pixels[12:36, 8 + index:32 + index, 1] = 255
        frame = av.VideoFrame.from_ndarray(pixels, format='rgb24')
        frame.pts = index + index // 4
        frame.time_base = fractions.Fraction(1, rate)
        for packet in stream.encode(frame):
            output.mux(packet)
    for packet in stream.encode():
        output.mux(packet)
    output.close()
    return str(path)


@pytest.fixture
def application_window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    application, window = get_main_app()
    window.show()
    application.processEvents()
    yield application, window
    window.dirty = False
    window._shutdown_force = True
    window.close()
    application.processEvents()
    application.processEvents()


def _assert_quiescent(window):
    """Assert all resource owners instead of merely observing a closed window."""
    assert window.task_coordinator.active_jobs() == ()
    assert all(depth == 0 for depth in window.task_coordinator.queue_depths().values())
    assert window._assist_download_handle is None
    assert window._propagation_handle is None
    assert window._video_decode_in_flight is False
    assert window.sam_controller._active_handle is None


def test_ten_generated_vfr_cycles_leave_no_worker_or_session(
        application_window, tmp_path):
    """A cycle leak would retain a job, decoder, save ticket, or stale identity."""
    _application, window = application_window
    video = _make_vfr_video(tmp_path / 'soak-vfr.mp4')

    summary = run_video_soak(window, video, cycles=10, timeout=5.0)

    assert summary['cycles'] == 10
    assert summary['completed_cycles'] == 10
    assert summary['failures'] == ()
    assert summary['remaining_jobs'] == ()
    assert all(depth == 0 for depth in summary['queue_depths'].values())
    assert summary['elapsed_seconds'] >= 0.0
    assert summary['decoder_active'] is False
    assert summary['session_active'] is False
    assert summary['save_state'] == 'saved'
    assert summary['save_in_flight'] is False
    assert summary['video_decode_in_flight'] is False
    assert summary['document_kind'] == DocumentKind.NONE.value
    assert summary['document_identity'] == window.document_identity
    _assert_quiescent(window)


def test_repeated_image_navigation_does_not_accept_an_old_save(
        application_window, tmp_path):
    """An old save completion must not clean or repaint the newest image."""
    application, window = application_window
    first = tmp_path / 'first.png'
    second = tmp_path / 'second.png'
    third = tmp_path / 'third.png'
    for index, path in enumerate((first, second, third)):
        _write_image(path, 0xFF101010 + index)
    window.default_save_dir = str(tmp_path)
    assert window.import_dir_images(str(tmp_path))
    assert window.file_path == str(first)
    old_identity = window.document_identity
    started = threading.Event()
    release = threading.Event()
    original_write = app_mod.write_save_request

    def delayed_save(*args, **kwargs):
        started.set()
        assert release.wait(3.0)
        return original_write(*args, **kwargs)

    try:
        with patch('labelImgPlusPlus.write_save_request', delayed_save):
            window.set_dirty()
            window.request_save_file()
            assert started.wait(1.0)
            # The save is now owned by the old document.  Do not exercise a
            # modal prompt; navigation must remain safe while it is in flight.
            window.dirty = False
            window.request_next_image()
            assert _wait(application, lambda: window.file_path == str(second))
            window.request_next_image()
            assert _wait(application, lambda: window.file_path == str(third))
            newest_identity = window.document_identity
            release.set()
            assert _wait(application, window.task_coordinator.is_idle)

        assert newest_identity != old_identity
        assert window.document_identity == newest_identity
        assert window.file_path == str(third)
        assert window.continuous_save._document_key == \
            window._continuous_document_key()
        _assert_quiescent(window)
    finally:
        release.set()


def test_cancelled_model_download_clears_sam_lane_without_network(
        application_window, tmp_path, monkeypatch):
    """Cancelling the explicit download must not retain its handle or cache part."""
    application, window = application_window
    started = threading.Event()
    cancellation_seen = threading.Event()
    cache_dir = tmp_path / 'model-cache'

    def controlled_download(_manifest, requested_cache, cancelled, progress):
        assert requested_cache == str(cache_dir)
        started.set()
        while not cancelled():
            cancellation_seen.wait(.01)
        cancellation_seen.set()
        raise ModelDownloadCancelled()

    monkeypatch.setattr(window, '_assist_cache_dir', lambda: str(cache_dir))
    monkeypatch.setattr(
        app_mod.model_cache, 'download_manifest', controlled_download)
    monkeypatch.setattr(
        app_mod.model_cache, 'cached_model_paths', lambda _manifest: None)
    window.assist_state.ready_to_download(MOBILE_SAM_MANIFEST.model_id)
    window._download_assist_model()
    assert started.wait(1.0)

    window.cancel_assist_download()

    assert _wait(
        application,
        lambda: (window._assist_download_handle is None
                 and not window.task_coordinator.queue_depths()['sam']))
    assert cancellation_seen.is_set()
    assert window.assist_state.snapshot.phase is AssistPhase.READY_TO_DOWNLOAD
    assert not cache_dir.exists() or not tuple(cache_dir.glob('*.part'))
    _assert_quiescent(window)


def test_cancelled_propagation_clears_preview_and_background_owner(
        application_window, tmp_path):
    """A cancelled external propagator must not leave preview or lane ownership."""
    application, window = application_window
    video = _make_vfr_video(tmp_path / 'propagation-vfr.mp4')
    started = threading.Event()
    cancellation_seen = threading.Event()

    def controlled_propagate(_backend, request, _direction, cancelled, _emit):
        started.set()
        while not cancelled():
            cancellation_seen.wait(.01)
        cancellation_seen.set()
        return PropagationResult(
            request.request_id, request.generation, request.document_revision)

    try:
        assert window.open_video(video)
        identity = window.document_identity
        window.active_class_control.confirm_each.setChecked(False)
        window._active_class_selected('vehicle')
        window.activate_box_tool()
        window.canvas.commit_rectangle((8, 8, 40, 32))
        track_id = next(iter(window.video_model.tracks))
        window._selected_video_track_id = track_id
        with patch(
                'labelImgPlusPlus.ConfiguredPropagationBackend.propagate',
                controlled_propagate):
            handle = window.track_selected_forward()
            assert handle is not None
            assert started.wait(1.0)
            assert window.cancel_video_propagation()
            assert _wait(
                application,
                lambda: (window._propagation_handle is None
                         and window.task_coordinator.is_idle()))

        assert window.document_identity == identity
        assert cancellation_seen.is_set()
        assert not window._propagation_preview
        assert not window._propagation_preview_gaps
        assert window.video_timeline._propagation_running is False
        _assert_quiescent(window)
    finally:
        window.dirty = False


def test_close_file_discards_late_decode_and_assist_inference(
        application_window, tmp_path):
    """Close must invalidate delayed decode/inference before either can paint."""
    application, window = application_window
    image_path = tmp_path / 'assist.png'
    _write_image(image_path, 0xFFDDDDDD)
    assert window.load_file(str(image_path))
    inference_started = threading.Event()
    release_inference = threading.Event()

    class BlockingInference(object):
        def predict(self, _prompt):
            inference_started.set()
            assert release_inference.wait(3.0)
            import numpy
            return numpy.zeros((48, 64), dtype=bool)

    try:
        controller = window.sam_controller
        controller.backend = BlockingInference()
        controller._embedded_key = controller._content_key
        controller.run_prompt(AssistPrompt(
            mode='points', positive_points=((20.0, 20.0),)))
        assert inference_started.wait(1.0)
        identity = window.document_identity
        window.close_file()
        release_inference.set()
        assert _wait(application, window.task_coordinator.is_idle)

        assert window.document_kind is DocumentKind.NONE
        assert window.document_identity != identity
        assert window.file_path is None
        assert window.canvas.assist_preview_shape is None
        _assert_quiescent(window)

        video = _make_vfr_video(tmp_path / 'late-decode-vfr.mp4')
        assert window.open_video(video)
        decode_started = threading.Event()
        decoder_closed = threading.Event()
        decoder = window.video_decoder
        original_close = decoder.close

        def blocked_seek(_pts, mode='nearest', cancelled=None):
            decode_started.set()
            cancellation_seen = threading.Event()
            while not cancelled():
                cancellation_seen.wait(.01)
            return None

        def recorded_close():
            original_close()
            decoder_closed.set()

        decoder.seek_pts = blocked_seek
        decoder.close = recorded_close
        snapshot = window.video_snapshot
        target = int(snapshot.start_pts or 0) + \
            int(snapshot.duration_pts or 0) // 2
        frame_ref = VideoFrameRef(
            snapshot.fingerprint, snapshot.stream_index, target,
            snapshot.time_base_num, snapshot.time_base_den)
        video_identity = window.document_identity
        assert window.request_video_frame(frame_ref) is not None
        assert decode_started.wait(1.0)
        window.dirty = False
        window.close_file()
        settled = _wait(
            application,
            lambda: window.task_coordinator.is_idle() and decoder_closed.is_set())
        assert settled, (
            window.document_kind, window.video_decoder is decoder,
            window.task_coordinator.active_jobs(),
            window.task_coordinator.queue_depths(), decoder_closed.is_set())

        assert window.document_kind is DocumentKind.NONE
        assert window.document_identity != video_identity
        assert window.file_path is None
        assert window.video_snapshot is None
        _assert_quiescent(window)
    finally:
        release_inference.set()
