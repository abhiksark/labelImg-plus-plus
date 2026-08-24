import os
import sqlite3
import time
from types import SimpleNamespace
from unittest.mock import patch

from PyQt5.QtCore import QThread, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QPushButton, QToolButton

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_decoder import VideoDependencyError
from libs.core.video_model import VideoProjectModel
from libs.core.video_project import (
    default_project_path, initialize_project, load_project,
    read_project_source,
)
from libs.core.video_types import (
    ObservationRecord, VideoFingerprint, VideoFrameRef,
    VideoSessionSnapshot,
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
            assert not window.canvas.isEnabled()
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
