import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QInputDialog, QMessageBox

from labelImgPlusPlus import get_main_app
from libs.core.video_model import VideoProjectModel
from libs.core.video_project import initialize_project, load_project
from libs.core.video_types import (
    DocumentKind, VideoFingerprint, VideoFrameRef, VideoSessionSnapshot,
)


def _wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _seed_track(window, end_pts=None):
    model = window.video_model
    start = window.current_video_frame_ref.pts
    track = model.create_track(
        'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
    model.upsert_manual(track.track_id, start, [2, 3, 22, 23])
    if end_pts is not None:
        model.upsert_manual(track.track_id, end_pts, [12, 13, 32, 33])
    window._selected_video_track_id = track.track_id
    window._on_video_model_mutation()
    window._materialize_video_frame(start)
    return track


def _ref(window, pts):
    snapshot = window.video_snapshot
    return VideoFrameRef(
        snapshot.fingerprint, snapshot.stream_index, pts,
        snapshot.time_base_num, snapshot.time_base_den)


class _BlockingFirstSave(object):
    def __init__(self, writer):
        self.writer = writer
        self.started = threading.Event()
        self.release = threading.Event()
        self.requests = []
        self.max_active = 0
        self._active = 0
        self._lock = threading.Lock()

    def __call__(self, request, cancelled=None, begin_commit=None):
        with self._lock:
            self.requests.append(request)
            self._active += 1
            self.max_active = max(self.max_active, self._active)
            first = len(self.requests) == 1
        try:
            if first:
                self.started.set()
                assert self.release.wait(5)
            return self.writer(
                request, cancelled=cancelled, begin_commit=begin_commit)
        finally:
            with self._lock:
                self._active -= 1


def _install_writable_video_document(window, tmp_path, name):
    source = tmp_path / (name + '.mp4')
    source.write_bytes(b'video-save-owner-fixture')
    stat = source.stat()
    fingerprint = VideoFingerprint(
        stat.st_size, stat.st_mtime_ns, name + '-fingerprint')
    project = tmp_path / (name + '.labelimgpp.sqlite')
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
    return str(project)


def test_unified_inspector_materializes_shape_and_renames_globally(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        assert window.track_list_widget.count() == 1
        assert len(window.canvas.shapes) == 1
        shape = window.canvas.shapes[0]
        assert shape.video_track_id == 'track-1'
        index = window.annotation_model.index_for_identity('track-1')
        window.annotation_model.setData(index, 'vehicle', Qt.EditRole)
        assert window.video_model.tracks['track-1'].label == 'vehicle'
        assert window.canvas.shapes[0].label == 'vehicle'
    finally:
        window.dirty = False
        window.close()


def test_unified_rows_include_tracks_absent_from_current_frame(
        tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'absent.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        window.video_model.create_track(
            'person', 'polygon', (255, 0, 0, 255), track_id='track-absent')
        window._on_video_model_mutation()
        window._materialize_video_frame(window.current_video_frame_ref.pts)

        assert window.annotation_model.rowCount() == 2
        assert len(window.canvas.shapes) == 1
        index = window.annotation_model.index_for_identity('track-absent')
        assert window.annotation_model.data(index, Qt.DisplayRole).startswith(
            'person')
        window._select_annotation_identity('track-absent')
        assert window.current_shape() is None
        assert window.actions.edit.isEnabled()
        assert window.annotation_model.setData(
            index, 'pedestrian', Qt.EditRole)
        assert window.video_model.tracks['track-absent'].label == 'pedestrian'
    finally:
        window.dirty = False
        window.close()


def test_track_span_trim_is_undoable(tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'span.mp4', frames=10)
    try:
        assert window.open_video(video)
        start = window.current_video_frame_ref.pts
        end = start + 5 * window._video_step_pts()
        _seed_track(window, end)
        with patch.object(
                QInputDialog, 'getText', return_value=(f'{start},{start}', True)):
            window.edit_selected_track_span()
        assert ('track-1', start) in window.video_model.observations
        assert ('track-1', end) not in window.video_model.observations
        window.undo_action()
        assert ('track-1', end) in window.video_model.observations
    finally:
        window.dirty = False
        window.close()


def test_editing_interpolation_creates_manual_anchor_and_undo_restores_it(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts >=
            start + 4 * step)
        shape = window.canvas.shapes[0]
        assert shape.video_render_state == 'interpolation'
        old_points = list(shape.points)
        shape.points = [QPointF(point.x() + 3, point.y() + 2)
                        for point in shape.points]
        window._on_shape_move_finished(shape, old_points)
        pts = window.current_video_frame_ref.pts
        exact = window.video_model.observations[('track-1', pts)]
        assert exact.source == 'manual'
        assert exact.anchor is True
        window.undo_action()
        assert ('track-1', pts) not in window.video_model.observations
        assert window.canvas.shapes[0].video_render_state == 'interpolation'
    finally:
        window.dirty = False
        window.close()


def test_deleting_interpolated_occurrence_writes_absence_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(app, lambda: bool(window.canvas.shapes)
                     and window.canvas.shapes[0].video_render_state
                     == 'interpolation')
        pts = window.current_video_frame_ref.pts
        window.canvas.select_shape(window.canvas.shapes[0])
        window.delete_selected_shape()
        assert window.video_model.observations[('track-1', pts)].present is False
        assert window.canvas.shapes == []
    finally:
        window.dirty = False
        window.close()


def test_add_keyframe_promotes_interpolation_to_manual_anchor(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4', frames=20)
    try:
        assert window.open_video(video)
        step = window._video_step_pts()
        start = window.current_video_frame_ref.pts
        _seed_track(window, start + 10 * step)
        window.request_video_frame(_ref(window, start + 5 * step))
        assert _wait(app, lambda: bool(window.canvas.shapes)
                     and window.canvas.shapes[0].video_render_state
                     == 'interpolation')
        window._selected_video_track_id = 'track-1'
        window.add_track_keyframe()
        observation = window.video_model.observations[
            ('track-1', window.current_video_frame_ref.pts)]
        assert observation.source == 'manual'
        assert observation.anchor is True
        assert window.canvas.shapes[0].video_render_state == 'exact'
    finally:
        window.dirty = False
        window.close()


def test_verify_and_explicit_save_are_durable(tmp_path, make_video):
    _app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        pts = window.current_video_frame_ref.pts
        window.video_model.set_frame_verified(pts, True)
        window._on_video_model_mutation()
        assert window.save_video_project()
        contents = load_project(window.video_snapshot.project_path)
        assert contents.tracks[0].track_id == 'track-1'
        assert contents.observations[0].pts == pts
        assert contents.frame_states[0].verified is True
        assert window.dirty is False
    finally:
        window.dirty = False
        window.close()


def test_mutation_during_async_save_is_chained_into_next_delta(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    gate = threading.Event()
    started = threading.Event()
    from libs.core.video_project import save_project_delta

    def delayed(request, cancelled=None, begin_commit=None):
        started.set()
        gate.wait(2)
        return save_project_delta(
            request, cancelled=cancelled, begin_commit=begin_commit)

    try:
        assert window.open_video(video)
        track = _seed_track(window)
        with patch('labelImgPlusPlus.save_project_delta', delayed):
            window.request_save_video_project()
            assert started.wait(1)
            step = window._video_step_pts()
            window.video_model.upsert_manual(
                track.track_id,
                window.current_video_frame_ref.pts + step,
                [3, 4, 23, 24])
            window._on_video_model_mutation()
            window.request_save_video_project()
            gate.set()
            assert _wait(app, lambda: not window.video_model.dirty)
        contents = load_project(window.video_snapshot.project_path)
        assert len(contents.observations) == 2
        assert window.dirty is False
    finally:
        gate.set()
        window.dirty = False
        window.close()


def test_manual_save_joins_the_active_continuous_video_writer(tmp_path):
    app, window = get_main_app()
    from libs.core.video_project import save_project_delta
    blocked = _BlockingFirstSave(save_project_delta)
    try:
        project = _install_writable_video_document(
            window, tmp_path, 'manual-join')
        window.save_changes_automatically.setChecked(True)
        with patch('labelImgPlusPlus.save_project_delta', blocked):
            track = window.video_model.create_track(
                'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
            window.video_model.upsert_manual(
                track.track_id, 0, [2, 3, 22, 23])
            window._on_video_model_mutation()
            window.continuous_save.flush()
            assert blocked.started.wait(2)
            window.video_model.upsert_manual(
                track.track_id,
                window.current_video_frame_ref.pts
                + window._video_step_pts(),
                [3, 4, 23, 24])
            window._on_video_model_mutation()
            target_revision = window.video_model.revision

            window._request_save_or_retry()
            blocked.release.set()
            assert _wait(
                app, lambda: (window.continuous_save.state == 'saved'
                              and not window.video_model.dirty))

        contents = load_project(project)
        assert contents.revision == target_revision
        assert len(contents.observations) == 2
        assert blocked.max_active == 1
    finally:
        blocked.release.set()
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_async_save_failure_retains_overlay_and_dirty_state(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'clip.mp4')
    try:
        assert window.open_video(video)
        _seed_track(window)
        with patch(
                'labelImgPlusPlus.save_project_delta',
                side_effect=RuntimeError('disk unavailable')):
            window.request_save_video_project()
            assert _wait(app, lambda: not window._video_save_active)
        assert window.video_model.dirty is True
        assert window.dirty is True
        assert window.actions.save.isEnabled()
        assert 'disk unavailable' in window.statusBar().currentMessage()
    finally:
        window.dirty = False
        window.close()


def test_video_save_without_a_durable_revision_remains_dirty(tmp_path):
    app, window = get_main_app()
    try:
        _install_writable_video_document(window, tmp_path, 'missing-revision')
        track = window.video_model.create_track(
            'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        window.video_model.upsert_manual(
            track.track_id, 0, [2, 3, 22, 23])
        window._on_video_model_mutation()

        with patch('labelImgPlusPlus.save_project_delta', return_value=None):
            window.request_save_video_project()
            assert _wait(
                app, lambda: window.continuous_save.state in (
                    'saved', 'failed'))

        assert window.continuous_save.state == 'failed'
        assert window.video_model.dirty is True
        assert window.dirty is True
    finally:
        window.dirty = False
        window.close()


def test_close_with_save_ignores_first_event_until_async_commit_finishes(
        tmp_path, make_video):
    app, window = get_main_app()
    video = make_video(tmp_path / 'close-save.mp4')
    gate = threading.Event()
    started = threading.Event()
    from libs.core.video_project import save_project_delta

    def delayed(request, cancelled=None, begin_commit=None):
        started.set()
        gate.wait(2)
        return save_project_delta(
            request, cancelled=cancelled, begin_commit=begin_commit)

    event = MagicMock()
    try:
        assert window.open_video(video)
        _seed_track(window)
        with patch.object(
                window, 'discard_changes_dialog',
                return_value=QMessageBox.Yes), patch(
                'labelImgPlusPlus.save_project_delta', delayed), patch.object(
                window, 'close', return_value=True) as close:
            window.closeEvent(event)
            assert started.wait(1)
            event.ignore.assert_called_once_with()
            event.accept.assert_not_called()
            assert window._video_close_save_pending is True
            assert window.task_coordinator.is_shutting_down is False

            gate.set()
            assert _wait(app, lambda: close.called)
            assert window._video_close_save_pending is False
            assert window.dirty is False
    finally:
        gate.set()
        window.dirty = False
        window.close()


def test_quit_save_waits_for_the_continuous_video_writer_to_drain(tmp_path):
    app, window = get_main_app()
    from libs.core.video_project import save_project_delta
    blocked = _BlockingFirstSave(save_project_delta)
    event = MagicMock()
    close_observations = []
    try:
        project = _install_writable_video_document(
            window, tmp_path, 'quit-join')
        window.save_changes_automatically.setChecked(True)
        with patch('labelImgPlusPlus.save_project_delta', blocked):
            track = window.video_model.create_track(
                'car', 'rectangle', (0, 255, 0, 255), track_id='track-1')
            window.video_model.upsert_manual(
                track.track_id, 0, [2, 3, 22, 23])
            window._on_video_model_mutation()
            window.continuous_save.flush()
            assert blocked.started.wait(2)
            window.video_model.upsert_manual(
                track.track_id,
                window.current_video_frame_ref.pts
                + window._video_step_pts(),
                [3, 4, 23, 24])
            window._on_video_model_mutation()
            target_revision = window.video_model.revision

            def observe_close():
                close_observations.append((
                    window.continuous_save.state,
                    window.video_model.durable_revision))
                return True

            with patch.object(
                    window, 'discard_changes_dialog',
                    return_value=QMessageBox.Yes), patch.object(
                    window, 'close', side_effect=observe_close):
                window.closeEvent(event)
                event.ignore.assert_called_once_with()
                blocked.release.set()
                assert _wait(app, lambda: bool(close_observations))

        assert close_observations == [('saved', target_revision)]
        assert load_project(project).revision == target_revision
        assert blocked.max_active == 1
    finally:
        blocked.release.set()
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()
