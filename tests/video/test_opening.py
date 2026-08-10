import os
import time
from unittest.mock import patch

from PyQt5.QtCore import QThread
from PyQt5.QtGui import QImage, QPixmap

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_decoder import VideoDependencyError
from libs.core.video_project import default_project_path
from libs.core.video_project import read_project_source


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
        assert window.file_dock.isVisible() is False
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
    try:
        assert _same_app is app
        assert _wait(
            app, lambda: window.document_kind == DocumentKind.VIDEO)
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
    moved = tmp_path / 'moved.mp4'
    os.replace(video, moved)
    try:
        with patch(
                'labelImgPlusPlus.QFileDialog.getOpenFileName',
                return_value=(str(moved), 'Video files')):
            window.request_open_video(project, skip_prompt=True)
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
        with patch.object(
                window, '_video_source_changed_choice',
                return_value='create'), patch(
                'labelImgPlusPlus.QFileDialog.getSaveFileName',
                return_value=(new_project, 'LabelImg++ video project')):
            window.request_open_video(video, skip_prompt=True)
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
        item = window.shapes_to_items[shape]
        window.canvas.select_shape(shape)

        assert window.video_snapshot.read_only is True
        assert window.canvas.locked is True
        assert not window.actions.verify.isEnabled()
        assert not window.actions.delete.isEnabled()
        assert not window.actions.videoAddKeyframe.isEnabled()
        assert window.request_verify_image() is None
        window.delete_selected_shape()
        window.add_track_keyframe()
        item.setText('changed')
        window.copy_to_clipboard()
        window.set_dirty()

        assert window.video_model.snapshot_state() == before
        assert item.text() == 'car'
        assert not window.actions.pasteFromClipboard.isEnabled()
        assert window.dirty is False
        assert window.request_save_video_project() is None
    finally:
        window.dirty = False
        window.close()
