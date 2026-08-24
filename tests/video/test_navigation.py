import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QMainWindow, QMessageBox

from labelImgPlusPlus import DocumentKind, MainWindow, get_main_app
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


def test_close_is_nonblocking_and_waits_for_video_lane_before_decoder_close():
    app, window = get_main_app()
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    closed = []
    event = MagicMock()
    try:
        def cancellable_decode(handle):
            started.set()
            while not handle.is_cancelled() and not release.is_set():
                time.sleep(.001)
            finished.set()
        decoder = SimpleNamespace(
            close=lambda: closed.append(finished.is_set()))
        window.video_decoder = decoder
        window.task_coordinator.submit(
            'video', cancellable_decode, key='video decode')
        assert started.wait(1)

        before = time.monotonic()
        with patch.object(window, 'close', return_value=True) as close:
            window.closeEvent(event)
            elapsed = time.monotonic() - before

            assert elapsed < .1
            event.ignore.assert_called_once_with()
            event.accept.assert_not_called()
            assert _wait(app, lambda: close.called)

        assert finished.is_set()
        assert closed == [True]
        assert window._shutdown_ready is True
        assert window._shutdown_save_authority is None
    finally:
        release.set()
        window.dirty = False
        window.close()


def test_close_during_shallow_partial_initialization_uses_minimal_teardown():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._initialization_complete = False
    decoder = SimpleNamespace(close=MagicMock())
    window.video_decoder = decoder
    event = MagicMock()
    try:
        window.closeEvent(event)

        event.accept.assert_called_once_with()
        event.ignore.assert_not_called()
        decoder.close.assert_called_once_with()
    finally:
        window.deleteLater()


def test_close_after_task_owner_partial_initialization_skips_full_cleanup():
    window = MainWindow.__new__(MainWindow)
    QMainWindow.__init__(window)
    window._initialization_complete = False
    task_coordinator = SimpleNamespace(
        shutdown=MagicMock(return_value=True))
    decoder = SimpleNamespace(close=MagicMock())
    window.task_coordinator = task_coordinator
    window.video_decoder = decoder
    event = MagicMock()
    try:
        window.closeEvent(event)

        event.accept.assert_called_once_with()
        event.ignore.assert_not_called()
        task_coordinator.shutdown.assert_called_once_with(wait_ms=0)
        decoder.close.assert_called_once_with()
        assert not hasattr(window, 'settings')
    finally:
        window.deleteLater()


def test_shutdown_timeout_surface_is_named_reused_and_keyboard_reachable():
    app, window = get_main_app()
    release = threading.Event()
    started = threading.Event()
    first_event = MagicMock()
    later_event = MagicMock()

    def stuck(_handle):
        started.set()
        release.wait(2)

    try:
        window.task_coordinator.submit('video', stuck, key='video decode')
        assert started.wait(1)
        with patch.object(window, 'close', return_value=True) as close:
            window.closeEvent(first_event)
            coordinator = window._shutdown_coordinator
            authority = window._shutdown_save_authority
            assert authority is not None
            coordinator._deadline_expired()
            app.processEvents()
            surface = window._shutdown_surface

            assert coordinator.state == 'timed_out'
            assert surface.isVisible()
            assert surface.accessibleName() == 'Shutdown waiting'
            assert 'video decode' in window._shutdown_remaining_label.text()
            assert window._shutdown_wait_button.focusPolicy() == Qt.StrongFocus
            assert window._shutdown_force_button.focusPolicy() == Qt.StrongFocus

            window.closeEvent(later_event)
            assert window._shutdown_coordinator is coordinator
            assert window._shutdown_surface is surface
            later_event.ignore.assert_called_once_with()

            QTest.mouseClick(window._shutdown_wait_button, Qt.LeftButton)
            assert coordinator.state == 'waiting'
            coordinator._deadline_expired()
            QTest.mouseClick(window._shutdown_force_button, Qt.LeftButton)
            assert coordinator.state == 'force_requested'
            assert window._shutdown_save_authority is None
            assert close.called
    finally:
        release.set()
        window.dirty = False
        window.close()


def test_force_quit_requires_second_confirmation_for_unsaved_work():
    app, window = get_main_app()
    release = threading.Event()
    started = threading.Event()
    event = MagicMock()

    def stuck(_handle):
        started.set()
        release.wait(2)

    try:
        window.task_coordinator.submit('video', stuck, key='video decode')
        assert started.wait(1)
        window.dirty = True
        with patch.object(
                window, 'discard_changes_dialog',
                return_value=QMessageBox.Yes), patch.object(
                window, 'close', return_value=True) as close, patch(
                'labelImgPlusPlus.QMessageBox.warning',
                side_effect=(QMessageBox.Cancel, QMessageBox.Yes)) as warning:
            window.closeEvent(event)
            window._shutdown_coordinator._deadline_expired()
            app.processEvents()

            QTest.mouseClick(window._shutdown_force_button, Qt.LeftButton)
            assert window._shutdown_coordinator.state == 'timed_out'
            assert not close.called

            QTest.mouseClick(window._shutdown_force_button, Qt.LeftButton)
            assert window._shutdown_coordinator.state == 'force_requested'
            assert close.called
            assert warning.call_count == 2
    finally:
        release.set()
        window.dirty = False
        window.close()
