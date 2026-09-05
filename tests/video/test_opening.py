# tests/video/test_opening.py
import os
import sqlite3
import threading
import time
from unittest.mock import patch

from PyQt6.QtCore import QPointF, QThread, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtTest import QTest

from labelImgPlusPlus import DocumentKind, get_main_app
from libs.core.shape import Shape
from libs.core.video_decoder import VideoDependencyError
from libs.core.video_session import prepare_video_open
from libs.core.video_project import default_project_path
from libs.core.video_project import read_project_source
from libs.core.video_types import (
    ObservationRecord, VideoThumbnailRequest, VideoThumbnailResult,
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
    image = QImage(64, 48, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(path))


def _stage_provisional_box(window):
    window.activate_box_tool()
    shape = Shape()
    for point in ((2, 3), (22, 3), (22, 23), (2, 23)):
        shape.add_point(QPointF(*point))
    window.canvas.current = shape
    window.canvas.finalise()
    return shape


def test_synchronous_open_creates_sidecar_after_first_frame(
        tmp_path, make_video):
    app, window = get_main_app()
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
        assert not window.workspace_inspector.tabs.isTabVisible(1)
        assert window.frame_cache.max_images == 12
        app.processEvents()
        assert window.zoom_mode == window.FIT_WINDOW
        assert window.actions.fitWindow.isChecked()
        assert all(
            bar.maximum() == bar.minimum()
            and bar.value() == bar.minimum()
            for bar in window.scroll_bars.values())
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


def test_delayed_video_commit_keeps_provisional_object_and_closes_decoder(
        tmp_path, make_video):
    app, window = get_main_app()
    image = tmp_path / 'image.png'
    _image(image)
    video = make_video(tmp_path / 'clip.mp4')
    assert window.load_file(str(image))
    gate = threading.Event()
    started = threading.Event()
    prepared_values = []

    def delayed(*args, **kwargs):
        started.set()
        gate.wait(1)
        prepared = prepare_video_open(*args, **kwargs)
        prepared_values.append(prepared)
        return prepared

    try:
        with patch('labelImgPlusPlus.prepare_video_open', delayed):
            window.request_open_video(video, skip_prompt=True)
            assert started.wait(1)
            shape = _stage_provisional_box(window)
            gate.set()
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()['video'])
            app.processEvents()

        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == str(image)
        assert window.canvas.provisional_shape is shape
        assert prepared_values[0].decoder._closed
    finally:
        gate.set()
        window._cancel_provisional_shape()
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
        window.annotation_model.setData(index, 'changed', Qt.ItemDataRole.EditRole)
        window.copy_to_clipboard()
        window.set_dirty()

        assert window.video_model.snapshot_state() == before
        index = window.annotation_model.index_for_identity('track-1')
        assert window.annotation_model.data(index, Qt.ItemDataRole.EditRole) == 'car'
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


def test_video_primary_action_accepts_current_pending_then_routes_remote_work(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'primary.mp4')
    try:
        assert window.open_video(video)
        assert window.actions.primary.text() == 'Browse video'

        window.trigger_primary_action()
        assert window.workspace_pages.current_page() == 'overview'

        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        pending = ObservationRecord(
            track.track_id, window.current_video_frame_ref.pts,
            [2, 3, 22, 23], source='tracker', review_state='pending',
            anchor=False, quality=.75)
        window.video_model.upsert_tracker(pending)
        window._selected_video_track_id = track.track_id
        window._on_video_model_mutation()
        window._materialize_video_frame(pending.pts)

        assert window.actions.primary.text() == 'Accept & Next'
        card = window.inspector_context_card
        assert card.eyebrow.text() == 'REVIEW SUGGESTION'
        assert card.title.text() == 'car'
        assert '1 suggestion remaining' in card.detail.text()
        assert card.visible_actions() == (
            window.actions.videoAcceptSuggestion,
            window.actions.videoRejectSuggestion,
        )
        window.trigger_primary_action()
        assert window.video_model.observations[
            (track.track_id, pending.pts)].review_state == 'accepted'
        assert window.actions.primary.text() == 'Browse video'

        remote = ObservationRecord(
            track.track_id, pending.pts + window._video_step_pts(),
            [3, 4, 23, 24], source='tracker', review_state='pending',
            anchor=False, quality=.75)
        window.video_model.upsert_tracker(remote)
        window._on_video_model_mutation()
        assert window.actions.primary.text() == 'Review queue'

        window.trigger_primary_action()
        assert window.workspace_pages.current_page() == 'canvas'
        assert not window.gallery_mode_enabled
        assert window._selected_video_track_id == track.track_id
        assert window.canvas.mode == window.canvas.EDIT
        assert window.actions.editMode.isChecked()
        assert window.canvas.hasFocus()
        assert '1 suggestion remaining' in window.statusBar().currentMessage()
    finally:
        window.dirty = False
        window.close()


def test_review_entry_neutralizes_drawing_and_canvas_click_is_safe(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'review-click.mp4')
    try:
        assert window.open_video(video)
        pts = window.current_video_frame_ref.pts
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_tracker(ObservationRecord(
            track.track_id, pts, [2, 3, 22, 23], source='tracker',
            review_state='pending', anchor=False, quality=.75))
        window._on_video_model_mutation()
        window.activate_box_tool()
        assert window.canvas.mode == window.canvas.CREATE

        window._activate_pending_review((track.track_id, pts))
        app.processEvents()
        assert window.canvas.mode == window.canvas.EDIT
        assert window.actions.editMode.isChecked()
        assert window.canvas.hasFocus()
        shape_count = len(window.canvas.shapes)

        QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton,
                         pos=window.canvas.rect().center())
        app.processEvents()
        assert len(window.canvas.shapes) == shape_count
        assert window.canvas.current is None
        assert window.canvas.provisional_shape is None

        # A deliberate tool choice remains authoritative, while entering the
        # review item again restores the safe neutral default.
        window.activate_box_tool()
        assert window.canvas.mode == window.canvas.CREATE
        window._activate_pending_review((track.track_id, pts))
        assert window.canvas.mode == window.canvas.EDIT

        assert window.accept_current_suggestion()
        assert window.canvas.mode == window.canvas.EDIT
        assert window.actions.editMode.isChecked()
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_single_item_review_decisions_advance_through_pending_queue(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'review-queue.mp4', frames=12)
    try:
        assert window.open_video(video)
        first_pts = window.current_video_frame_ref.pts
        next_pts = first_pts + window._video_step_pts()
        first_track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        next_track = window.video_model.create_track(
            'person', 'rectangle', (255, 150, 0, 255),
            track_id='track-2')
        for track, pts in ((first_track, first_pts),
                           (next_track, next_pts)):
            window.video_model.upsert_tracker(ObservationRecord(
                track.track_id, pts, [2, 3, 22, 23], source='tracker',
                review_state='pending', anchor=False, quality=.75))
        window._selected_video_track_id = first_track.track_id
        window._on_video_model_mutation()
        window._materialize_video_frame(first_pts)

        assert '2 suggestions remaining' in \
            window.inspector_context_card.detail.text()
        assert window.inspector_context_card.visible_actions() == (
            window.actions.videoAcceptSuggestion,
            window.actions.videoRejectSuggestion,
            window.actions.videoPreviousIssue,
        )
        assert window.accept_current_suggestion()
        assert window.video_model.observations[
            (first_track.track_id, first_pts)].review_state == 'accepted'
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == next_pts)
        app.processEvents()
        assert window._selected_video_track_id == next_track.track_id
        assert window.canvas.selected_shape.video_track_id == \
            next_track.track_id
        assert '1 suggestion remaining' in \
            window.inspector_context_card.detail.text()

        assert window.reject_current_suggestion()
        assert window.video_model.observations[
            (next_track.track_id, next_pts)].review_state == 'rejected'
        assert window._pending_video_observation_count() == 0
        assert window.actions.primary.text() == 'Browse video'
        assert 'Review complete' in window.statusBar().currentMessage()
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_review_shortcuts_wait_for_the_exact_target_frame(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'review-fence.mp4', frames=12)
    try:
        assert window.open_video(video)
        first_pts = window.current_video_frame_ref.pts
        next_pts = first_pts + window._video_step_pts()
        first_track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        next_track = window.video_model.create_track(
            'person', 'rectangle', (255, 150, 0, 255),
            track_id='track-2')
        keys = ((first_track.track_id, first_pts),
                (next_track.track_id, next_pts))
        for track_id, pts in keys:
            window.video_model.upsert_tracker(ObservationRecord(
                track_id, pts, [2, 3, 22, 23], source='tracker',
                review_state='pending', anchor=False, quality=.75))
        window._selected_video_track_id = first_track.track_id
        window._on_video_model_mutation()
        window._materialize_video_frame(first_pts)
        window.frame_cache.clear()

        handle = window._activate_pending_review(keys[1])
        assert handle is not None
        assert window.current_video_frame_ref.pts == first_pts
        assert window.actions.primary.text() == 'Opening suggestion…'
        assert not window.actions.primary.isEnabled()
        assert not window.accept_current_suggestion()
        assert not window.reject_current_suggestion()
        assert all(
            window.video_model.observations[key].review_state == 'pending'
            for key in keys)

        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == next_pts)
        assert window._review_navigation_key is None
        assert window._selected_video_track_id == next_track.track_id
        assert window.accept_current_suggestion()
        assert window.video_model.observations[keys[1]].review_state == \
            'accepted'
        assert window.video_model.observations[keys[0]].review_state == \
            'pending'
    finally:
        window.dirty = False
        window.close()


def test_previous_issue_wraps_over_the_live_pending_queue(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'previous-issue.mp4', frames=12)
    try:
        assert window.open_video(video)
        first_pts = window.current_video_frame_ref.pts
        step = window._video_step_pts()
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        keys = []
        for offset in range(3):
            pts = first_pts + offset * step
            key = (track.track_id, pts)
            keys.append(key)
            window.video_model.upsert_tracker(ObservationRecord(
                track.track_id, pts, [2 + offset, 3, 22 + offset, 23],
                source='tracker', review_state='pending', anchor=False,
                quality=.75))
        window._on_video_model_mutation()

        window._activate_pending_review(keys[1])
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == keys[1][1])
        window.previous_review_issue()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == keys[0][1])
        window.previous_review_issue()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts == keys[2][1])
        assert window.actions.videoPreviousIssue.isEnabled()
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


def test_overview_thumbnails_decode_exact_pts_and_reject_stale_revision(
        tmp_path, make_video):
    app, window = get_main_app()
    try:
        assert window.open_video(make_video(tmp_path / 'thumbnails.mp4'))
        pts = window.current_video_frame_ref.pts
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_tracker(ObservationRecord(
            track.track_id, pts, [8, 12, 32, 36], source='tracker',
            review_state='pending', anchor=False))
        window._on_video_model_mutation()
        window.toggle_gallery_mode(True)
        overview = window.workspace_pages.video_overview
        overview.set_view('frames')
        overview.frames.resize(320, 220)
        overview.frames.request_visible_thumbnails()

        assert _wait(app, lambda: pts in overview.frames._thumbnail_cache)
        assert 'Exact PTS %d' % pts in \
            overview.frames.list_widget.item(0).toolTip()

        snapshot = window.video_snapshot
        request = VideoThumbnailRequest(
            request_id=window._video_overview_thumbnail_request_id,
            generation=window._dataset_generation,
            model_revision=window.video_model.revision - 1,
            source_path=snapshot.source_path,
            fingerprint=snapshot.fingerprint,
            stream_index=snapshot.stream_index,
            time_base_num=snapshot.time_base_num,
            time_base_den=snapshot.time_base_den,
            pts=(pts,), max_size=96)
        overview.frames._thumbnail_cache.clear()
        window._on_video_overview_thumbnails(VideoThumbnailResult(
            request, ((window.current_video_frame_ref, window.image),)))
        assert overview.frames.thumbnail_cache_size() == 0
    finally:
        window.dirty = False
        window.close()


def test_new_overview_thumbnail_request_cancels_the_previous_one(
        tmp_path, make_video):
    app, window = get_main_app()
    started = threading.Event()

    def slow_decode(request, cancelled):
        if not started.is_set():
            started.set()
            while not cancelled():
                time.sleep(.001)
        return VideoThumbnailResult(request, ())

    try:
        assert window.open_video(make_video(tmp_path / 'cancel-thumbs.mp4'))
        pts = window.current_video_frame_ref.pts
        with patch('labelImgPlusPlus.decode_video_thumbnails', slow_decode):
            first = window._request_video_overview_thumbnails((pts,), 96)
            assert _wait(app, started.is_set)
            second = window._request_video_overview_thumbnails((pts,), 96)
            assert first.is_cancelled()
            assert not second.is_cancelled()
    finally:
        window.task_coordinator.cancel_key('video-overview-thumbnails')
        window.dirty = False
        window.close()
