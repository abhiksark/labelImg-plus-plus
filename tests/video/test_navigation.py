import threading
import time
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy, QTest

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_types import (
    VideoFingerprint, VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
)


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _ref(window, pts):
    snapshot = window.video_snapshot
    return VideoFrameRef(
        snapshot.fingerprint, snapshot.stream_index, pts,
        snapshot.time_base_num, snapshot.time_base_den)


def _timeline_snapshot():
    fingerprint = VideoFingerprint(1024, 123, 'navigation-timeline')
    frame_ref = VideoFrameRef(fingerprint, 0, 3400, 1, 1000)
    image = QImage(96, 64, QImage.Format_RGB32)
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    first = VideoFrameResult(
        frame_ref, image, 96, 64, 96, 64, 0,
        byte_size, 'navigation-timeline:0:3400')
    return VideoSessionSnapshot(
        'navigation-timeline.mp4', None, fingerprint, 0, 1, 1000,
        96, 64, 0, 'fixture', 10_000, 900, 12, 1, 0, first)


def test_frame_step_and_previous_use_pts_not_frame_index(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        first_pts = window.current_video_frame_ref.pts
        window.request_next_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > first_pts)
        next_pts = window.current_video_frame_ref.pts
        assert next_pts - first_pts != 1
        window.request_previous_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == first_pts)
    finally:
        window.dirty = False
        window.close()


def test_rapid_seek_commits_only_latest_request(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = int(window.video_snapshot.start_pts or 0)
        window.request_video_frame(_ref(window, start + 3 * step))
        window.request_video_frame(_ref(window, start + 12 * step))
        assert _wait(
            app, lambda: not window.task_coordinator.queue_depths()['video'])
        app.processEvents()
        assert abs(window.current_video_frame_ref.pts -
                   (start + 12 * step)) <= step
    finally:
        window.dirty = False
        window.close()


def test_escape_from_exact_time_restores_display_and_canvas_focus():
    app, window = get_main_app()
    try:
        window.workspace_pages.set_page('canvas')
        timeline = window.video_timeline
        timeline.show()
        displayed = timeline.time_edit.text()
        focus_returns = QSignalSpy(timeline.focusReturnRequested)
        timeline.time_edit.setFocus(Qt.OtherFocusReason)
        timeline.time_edit.setText('invalid')

        QTest.keyClick(timeline.time_edit, Qt.Key_Escape)

        assert _wait(app, window.canvas.hasFocus)
        assert timeline.time_edit.text() == displayed
        assert len(focus_returns) == 1
    finally:
        window.dirty = False
        window.close()


def test_valid_exact_time_seeks_then_restores_canvas_focus():
    app, window = get_main_app()
    try:
        window.workspace_pages.set_page('canvas')
        timeline = window.video_timeline
        timeline.set_session(_timeline_snapshot())
        timeline.show()
        events = []
        timeline.seekRequested.connect(
            lambda _frame_ref: events.append('seek'))
        timeline.focusReturnRequested.connect(
            lambda: events.append('focus'))
        seeks = QSignalSpy(timeline.seekRequested)
        timeline.time_edit.setText('00:00:02.345')
        timeline.time_edit.setFocus(Qt.OtherFocusReason)

        QTest.keyClick(timeline.time_edit, Qt.Key_Return)

        assert _wait(app, window.canvas.hasFocus)
        assert events == ['seek', 'focus']
        assert len(seeks) == 1
        assert seeks[0][0].pts == 3245
    finally:
        window.dirty = False
        window.close()


def test_playback_has_one_decode_request_in_flight_and_drops_debt(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=30)
    try:
        assert window.open_video(video)
        window.play_pause_video()
        window._video_play_started_wall -= .3
        window._video_playback_tick()
        request_id = window._video_frame_request_id
        window._video_playback_tick()
        assert window._video_frame_request_id == request_id
        assert window.task_coordinator.queue_depths()['video'] <= 1
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > 0)
        window.pause_video()
        assert not window._video_playback_timer.isActive()
    finally:
        window.dirty = False
        window.close()


def test_image_video_mode_transitions_reconfigure_timeline_and_cache(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    from PyQt5.QtGui import QImage
    image_path = str(tmp_path / 'image.png')
    image = QImage(32, 24, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(image_path)
    try:
        assert window.open_video(video)
        assert window.document_kind == DocumentKind.VIDEO
        # Check the timeline's own visibility contract independently of the
        # currently selected central page (which may be restored as Gallery).
        assert not window.video_timeline.isHidden()
        assert window.video_timeline.parent() is \
            window.workspace_pages.canvas_page
        assert window.workspace_inspector.tabs.indexOf(
            window.file_controls) == 1
        assert window.frame_cache.max_images == 12
        window.request_open_file(image_path, skip_prompt=True)
        assert _wait(app, lambda: window.document_kind == DocumentKind.IMAGE)
        assert window.video_timeline.isHidden()
        assert window.workspace_inspector.tabs.indexOf(
            window.file_controls) == 1
        assert window.frame_cache.max_images == 5
    finally:
        window.dirty = False
        window.close()


def test_shutdown_waits_for_video_lane_before_closing_session_decoder(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'shutdown.mp4')
    started = threading.Event()
    finished = threading.Event()
    closed = []
    try:
        assert window.open_video(video)
        decoder = window.video_decoder
        original_close = decoder.close

        def cancellable_decode(cancelled=None):
            started.set()
            while cancelled is None or not cancelled():
                time.sleep(.001)
            finished.set()
            return None

        def observed_close():
            closed.append(finished.is_set())
            return original_close()

        with patch.object(decoder, 'next_frame', cancellable_decode), \
                patch.object(decoder, 'close', observed_close):
            window.request_next_video_frame()
            assert started.wait(1)
            window._shutdown_workers()
        assert finished.is_set()
        assert closed == [True]
    finally:
        window.dirty = False
        window.close()
