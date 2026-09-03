# tests/video/test_navigation.py
import threading
import time
from unittest.mock import patch

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtTest import QTest

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.shape import Shape, ShapeType
from libs.core.video_types import VideoFrameRef


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


def _stage_provisional_box(window):
    window.activate_box_tool()
    shape = Shape(shape_type=ShapeType.RECTANGLE)
    for point in ((2, 3), (22, 3), (22, 23), (2, 23)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()
    return shape


def test_provisional_box_blocks_video_seek_step_and_playback(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'provisional-navigation.mp4', frames=12)
    try:
        assert window.open_video(video)
        shape = _stage_provisional_box(window)
        app.processEvents()
        original = window.current_video_frame_ref

        assert window.request_video_frame(
            _ref(window, original.pts + window._video_step_pts())) is None
        assert window.request_next_video_frame() is None
        assert window.request_previous_video_frame() is None
        assert window.play_pause_video() is None
        app.processEvents()

        assert window.current_video_frame_ref == original
        assert not window._video_playback_timer.isActive()
        assert window.canvas.provisional_shape is shape
        assert window.class_picker.edit.hasFocus()
    finally:
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()


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


def test_frame_navigation_preserves_manual_zoom_and_pan(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(
        tmp_path / 'manual-pan.mp4', width=320, height=240)
    window.resize(720, 520)
    try:
        assert window.open_video(video)
        app.processEvents()
        window.set_zoom(400)
        app.processEvents()
        expected = {}
        for orientation in (Qt.Horizontal, Qt.Vertical):
            bar = window.scroll_bars[orientation]
            bar.setRange(0, 200)
            bar.setValue(100)
            expected[orientation] = bar.value()

        first_pts = window.current_video_frame_ref.pts
        window.request_next_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > first_pts)
        app.processEvents()

        assert window.zoom_mode == window.MANUAL_ZOOM
        assert window.zoom_widget.value() == 400
        for orientation, value in expected.items():
            assert window.scroll_bars[orientation].value() == value
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


def test_ctrl_space_shortcut_toggles_playback(tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'playback-shortcut.mp4', frames=30)
    try:
        assert window.open_video(video)
        window.activateWindow()
        app.processEvents()
        window.canvas.setFocus()
        QTest.keyClick(window.canvas, Qt.Key_Space, Qt.ControlModifier)
        assert window._video_playback_timer.isActive()
        assert window.video_timeline._playing

        QTest.keyClick(window.canvas, Qt.Key_Space, Qt.ControlModifier)
        assert not window._video_playback_timer.isActive()
        assert not window.video_timeline._playing
    finally:
        window.pause_video()
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
        assert not window.workspace_inspector.tabs.isTabVisible(1)
        assert window.frame_cache.max_images == 12
        window.request_open_file(image_path, skip_prompt=True)
        assert _wait(app, lambda: window.document_kind == DocumentKind.IMAGE)
        assert window.video_timeline.isHidden()
        assert window.workspace_inspector.tabs.indexOf(
            window.file_controls) == 1
        assert window.workspace_inspector.tabs.isTabVisible(1)
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
