import os
import sqlite3
import time
from unittest.mock import patch

from PyQt5.QtCore import QThread, Qt
from PyQt5.QtGui import QImage, QPixmap

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.video_decoder import VideoDependencyError
from libs.core.video_project import default_project_path
from libs.core.video_project import read_project_source
from libs.core.video_types import ObservationRecord


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
        assert 'Read-only' in window.label_save_status.text()
        assert not window.actions.verify.isEnabled()
        assert not window.actions.delete.isEnabled()
        assert not window.actions.videoAddKeyframe.isEnabled()
        assert window.request_verify_image() is None
        window.delete_selected_shape()
        window.add_track_keyframe()
        window.annotation_model.setData(index, 'changed', Qt.EditRole)
        window.copy_to_clipboard()
        window.set_dirty()

        assert window.video_model.snapshot_state() == before
        index = window.annotation_model.index_for_identity('track-1')
        assert window.annotation_model.data(index, Qt.EditRole) == 'car'
        assert not window.actions.pasteFromClipboard.isEnabled()
        assert window.dirty is False
        assert window.request_save_video_project() is None
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


def test_opening_a_video_keeps_browsing_and_shows_the_overview(
        tmp_path, make_video):
    """The browse slot follows the document instead of closing for video.

    4.0.0rc0 forced browse mode off and disabled its action here, because the
    image gallery had no entries for a clip. The slot was never wrong -- its
    content was -- so browsing now stays on and shows the video overview.
    """
    _app, window = get_main_app()
    try:
        window.toggle_gallery_mode(True)
        assert window.gallery_mode_enabled
        assert window.workspace_pages.current_page() == 'gallery'

        assert window.open_video(make_video(tmp_path / 'clip.mp4'))

        assert window.document_kind == DocumentKind.VIDEO
        assert window.gallery_mode_enabled
        assert window.workspace_pages.current_page() == 'overview'
        assert window.actions.galleryMode.isEnabled()

        # Leaving the slot lands on the clip, timeline and all.
        window.toggle_gallery_mode(False)
        assert window.workspace_pages.current_page() == 'canvas'
        assert window.workspace_pages.timeline.isVisible()

        # And re-entering it returns to the overview, not the image gallery.
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'overview'
    finally:
        window.dirty = False
        window.close()


def test_opening_a_second_clip_while_browsing_replaces_the_overview(
        tmp_path, make_video):
    """The routed page must carry the clip that is open, not the last one.

    _set_document_kind runs before the new VideoProjectModel is assigned, so
    refreshing the overview from there alone leaves the previous clip's tracks
    on screen under the new clip's name -- the same "the slot's content was
    wrong" failure this whole change exists to retire.
    """
    _app, window = get_main_app()
    try:
        assert window.open_video(make_video(tmp_path / 'first.mp4'))
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_manual(
            track.track_id, window.current_video_frame_ref.pts,
            [2, 3, 22, 23])
        window._on_video_model_mutation()
        assert window.save_video_project()

        window.toggle_gallery_mode(True)
        overview = window.workspace_pages.video_overview
        assert list(overview.lanes.lane_track_ids()) == ['track-1']

        assert window.open_video(make_video(tmp_path / 'second.mp4'))
        assert window.workspace_pages.current_page() == 'overview'
        assert list(overview.lanes.lane_track_ids()) == []
        assert overview.distinct_pts() == ()
    finally:
        window.dirty = False
        window.close()


def test_the_browse_slot_returns_to_the_gallery_after_the_video_closes(
        tmp_path, make_video):
    """Routing to the overview must not be a one-way trip.

    The old test asserted the browse action became enabled again; that can no
    longer fail, because the action is never disabled now. What can still
    regress is the routing: with no video open, browsing is the gallery.
    """
    _app, window = get_main_app()
    try:
        assert window.open_video(make_video(tmp_path / 'clip.mp4'))
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'overview'

        window.reset_state()
        assert window.document_kind == DocumentKind.NONE
        assert window.actions.galleryMode.isEnabled()
        assert window.workspace_pages.current_page() == 'gallery'
    finally:
        window.dirty = False
        window.close()


def test_the_overview_shows_the_open_clip_and_seeks_back_to_the_canvas(
        tmp_path, make_video):
    """The routed page carries the video's own state, not an empty shell.

    Routing to a blank overview would reproduce the very dead end the disable
    patch worked around, so this asserts content: the track that was just
    created reaches the lanes, the count reads over real frames, and picking a
    frame leaves the slot for the canvas at that pts.
    """
    _app, window = get_main_app()
    try:
        assert window.open_video(make_video(tmp_path / 'clip.mp4'))
        pts = window.current_video_frame_ref.pts
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_manual(track.track_id, pts, [2, 3, 22, 23])
        window._on_video_model_mutation()

        window.toggle_gallery_mode(True)
        overview = window.workspace_pages.video_overview
        assert window.workspace_pages.current_page() == 'overview'
        assert list(overview.lanes.lane_track_ids()) == ['track-1']
        assert pts in overview.distinct_pts()
        assert list(overview.frames.visible_pts()) == [pts]
        assert overview.count_text() == overview.COUNT_FORMAT % (1, 1)

        # A second keyframe while the overview is on screen keeps it live.
        window.video_model.upsert_manual(
            track.track_id, pts + 1000, [40, 41, 60, 61])
        window._on_video_model_mutation()
        assert overview.count_text() == overview.COUNT_FORMAT % (2, 2)

        overview.seekRequested.emit(pts)
        assert window.workspace_pages.current_page() == 'canvas'
        assert not window.gallery_mode_enabled
        assert not window.actions.galleryMode.isChecked()
    finally:
        window.dirty = False
        window.close()
