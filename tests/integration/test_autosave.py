import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import xml.etree.ElementTree as ET


if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'


from PyQt5.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QImage, QMouseEvent  # noqa: E402
from PyQt5.QtTest import QSignalSpy, QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

import labelImgPlusPlus as app_module  # noqa: E402
from labelImgPlusPlus import get_main_app  # noqa: E402
from libs.core.shape import Shape, ShapeType  # noqa: E402
from libs.formats.annotation_paths import find_existing_annotation  # noqa: E402
from libs.formats.labelFile import LabelFileFormat  # noqa: E402
from libs.core.video_model import VideoProjectModel  # noqa: E402
from libs.core.video_project import initialize_project, load_project  # noqa: E402
from libs.core.video_types import (  # noqa: E402
    DocumentKind, VideoFingerprint, VideoFrameRef, VideoSessionSnapshot,
)


def _wait(app, predicate, timeout_ms=3000):
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def commit_rectangle(window, label):
    window.active_class_control.confirm_each.setChecked(False)
    window._active_class_selected(label)
    window.activate_box_tool()
    window.canvas.commit_rectangle((2, 2, 20, 20))


def test_shape_commit_creates_sidecar_without_navigation(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'frame.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        commit_rectangle(window, 'vehicle')
        sidecar = image_path.with_suffix('.xml')
        assert _wait(app, sidecar.exists)
        assert window.continuous_save.state == 'saved'
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_image_save_without_a_durable_path_remains_dirty(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'missing-path.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))

        with patch('labelImgPlusPlus.write_save_request', return_value=None):
            commit_rectangle(window, 'vehicle')
            window.continuous_save.flush()
            assert _wait(app, lambda: window._save_handle is None)

        assert window.continuous_save.state == 'failed'
        assert window.dirty is True
        assert not image_path.with_suffix('.xml').exists()
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def _image_to_widget(canvas, x, y):
    offset = canvas.offset_to_center()
    return QPointF((x + offset.x()) * canvas.scale,
                   (y + offset.y()) * canvas.scale)


def _mouse(canvas, kind, x, y, button, buttons):
    return QMouseEvent(kind, _image_to_widget(canvas, x, y), button,
                       buttons, Qt.NoModifier)


def test_provisional_geometry_and_existing_shape_drag_save_only_on_completion(
        tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'geometry.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        window.active_class_control.confirm_each.setChecked(False)
        window._active_class_selected('vehicle')
        requested = QSignalSpy(window.continuous_save.saveRequested)

        rectangle = Shape(shape_type=ShapeType.RECTANGLE)
        rectangle.add_point(QPointF(2, 2))
        rectangle.add_point(QPointF(20, 20))
        window.canvas.current = rectangle
        QTest.qWait(300)
        assert len(requested) == 0
        window.canvas.finalise()
        assert requested.wait(1000)
        assert _wait(app, lambda: window.continuous_save.state == 'saved')

        requested = QSignalSpy(window.continuous_save.saveRequested)
        polygon = Shape(shape_type=ShapeType.POLYGON)
        polygon.add_point(QPointF(2, 2))
        polygon.add_point(QPointF(20, 2))
        polygon.add_point(QPointF(20, 20))
        window.canvas.current = polygon
        QTest.qWait(300)
        assert len(requested) == 0
        window.canvas.finalise()
        assert requested.wait(1000)
        assert _wait(app, lambda: window.continuous_save.state == 'saved')

        requested = QSignalSpy(window.continuous_save.saveRequested)
        shape = window.canvas.shapes[0]
        window.canvas.set_editing(True)
        window.canvas.selected_shape = shape
        window.canvas.mousePressEvent(_mouse(
            window.canvas, QEvent.MouseButtonPress, 10, 10,
            Qt.LeftButton, Qt.LeftButton))
        window.canvas.mouseMoveEvent(_mouse(
            window.canvas, QEvent.MouseMove, 14, 14,
            Qt.NoButton, Qt.LeftButton))
        QTest.qWait(300)
        assert len(requested) == 0
        window.canvas.mouseReleaseEvent(_mouse(
            window.canvas, QEvent.MouseButtonRelease, 14, 14,
            Qt.LeftButton, Qt.NoButton))
        assert requested.wait(1000)
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_duplicate_shape_creates_a_new_durable_revision(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'duplicate.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        commit_rectangle(window, 'vehicle')
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
        revision = window._document_revision
        window.canvas.selected_shape = window.canvas.shapes[0]
        requested = QSignalSpy(window.continuous_save.saveRequested)

        window.copy_selected_shape()

        assert window._document_revision == revision + 1
        assert requested.wait(1000)
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
        assert len(window.canvas.shapes) == 2
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_verification_waits_while_disabled_and_saves_after_reenable(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'verify.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        window.save_changes_automatically.setChecked(False)
        requested = QSignalSpy(window.continuous_save.saveRequested)

        window.request_verify_image()
        QTest.qWait(300)

        assert window.canvas.verified
        assert window.continuous_save.state == 'pending'
        assert len(requested) == 0
        assert not image_path.with_suffix('.xml').exists()

        window.save_changes_automatically.setChecked(True)
        if not requested:
            assert requested.wait(1000)
        assert _wait(app, image_path.with_suffix('.xml').exists)
        assert window.continuous_save.state == 'saved'
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_late_image_save_updates_original_image_without_invalidating_current(
        monkeypatch, tmp_path):
    app, window = get_main_app()
    first = tmp_path / 'a.png'
    second = tmp_path / 'b.png'
    for path in (first, second):
        image = QImage(80, 60, QImage.Format_RGB32)
        image.fill(Qt.white)
        assert image.save(str(path))
    started = threading.Event()
    release = threading.Event()
    original_write = app_module.write_save_request

    def delayed_write(request, **kwargs):
        started.set()
        assert release.wait(3)
        return original_write(request, **kwargs)

    monkeypatch.setattr(app_module, 'write_save_request', delayed_write)
    try:
        assert window.import_dir_images(str(tmp_path))
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(first), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(first))
        commit_rectangle(window, 'vehicle')
        window.continuous_save.flush()
        assert _wait(app, started.is_set, timeout_ms=2000)

        window.request_open_file(str(second), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(second))
        assert window.frame_cache.get(str(second)) is not None
        removed = []
        remove = window.frame_cache.remove

        def record_remove(path):
            removed.append(path)
            remove(path)

        monkeypatch.setattr(window.frame_cache, 'remove', record_remove)
        release.set()
        assert _wait(app, first.with_suffix('.xml').exists)
        assert _wait(app, lambda: find_existing_annotation(
            str(first), resolver=window.dataset_snapshot.resolver) is not None)

        assert str(second) not in removed
        resolver = window.dataset_snapshot.resolver
        assert find_existing_annotation(
            str(first), resolver=resolver) == str(first.with_suffix('.xml'))
        assert find_existing_annotation(str(second), resolver=resolver) is None
    finally:
        release.set()
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_close_save_drains_newest_image_revision_after_blocked_write(
        monkeypatch, tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'close-race.png'
    image = QImage(120, 80, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    started = threading.Event()
    release = threading.Event()
    first_published = threading.Event()
    writes = []
    original_write = app_module.write_save_request

    def block_first_publication(request, cancelled=None, begin_commit=None):
        writes.append(request)
        if len(writes) == 1:
            if begin_commit is not None:
                begin_commit()
            started.set()
            assert release.wait(5)
            result = original_write(request)
            first_published.set()
            return result
        return original_write(
            request, cancelled=cancelled, begin_commit=begin_commit)

    monkeypatch.setattr(
        app_module, 'write_save_request', block_first_publication)
    event = MagicMock()
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.active_class_control.confirm_each.setChecked(False)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))

        commit_rectangle(window, 'vehicle')
        window.continuous_save.flush()
        assert started.wait(2)
        window.canvas.commit_rectangle((30, 5, 55, 35))
        assert len(window.canvas.shapes) == 2

        with patch.object(
                window, 'discard_changes_dialog',
                return_value=QMessageBox.Yes), patch.object(
                window, 'close', return_value=True) as close:
            window.closeEvent(event)
            release.set()
            assert _wait(app, lambda: close.called, timeout_ms=5000)

        assert first_published.is_set()
        assert _wait(
            app, lambda: window.continuous_save.state == 'saved',
            timeout_ms=5000)
        assert len(ET.parse(str(image_path.with_suffix('.xml'))).findall(
            'object')) == 2
    finally:
        release.set()
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_disable_during_in_flight_save_requeues_until_reenabled(
        monkeypatch, tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'paused.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    started = threading.Event()
    release = threading.Event()
    writes = []
    original_write = app_module.write_save_request

    def delayed_first_write(request, **kwargs):
        writes.append(request)
        if len(writes) == 1:
            started.set()
            assert release.wait(3)
        return original_write(request, **kwargs)

    monkeypatch.setattr(app_module, 'write_save_request', delayed_first_write)
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        commit_rectangle(window, 'vehicle')
        window.continuous_save.flush()
        assert _wait(app, started.is_set)

        window.save_changes_automatically.setChecked(False)
        window.set_dirty()
        release.set()
        assert _wait(app, image_path.with_suffix('.xml').exists)
        assert _wait(app, lambda: window.continuous_save.state == 'pending')
        assert len(writes) == 1

        window.save_changes_automatically.setChecked(True)
        assert _wait(app, lambda: len(writes) == 2)
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
        assert writes[1].revision > writes[0].revision
    finally:
        release.set()
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_completed_video_mutation_saves_continuously(tmp_path):
    app, window = get_main_app()
    source = tmp_path / 'clip.mp4'
    source.write_bytes(b'video-save-boundary')
    stat = source.stat()
    fingerprint = VideoFingerprint(
        stat.st_size, stat.st_mtime_ns, 'fixture-fingerprint')
    project_path = tmp_path / 'clip.labelimgpp.sqlite'
    session = SimpleNamespace(
        source_path=str(source), fingerprint=fingerprint, stream_index=0,
        time_base_num=1, time_base_den=12, duration_pts=1, width=64,
        height=48, rotation=0, codec='fixture')
    initialize_project(str(project_path), session)
    snapshot = VideoSessionSnapshot(
        source_path=str(source), project_path=str(project_path),
        fingerprint=fingerprint, stream_index=0, time_base_num=1,
        time_base_den=12, width=64, height=48, rotation=0,
        codec='fixture', duration_pts=1, start_pts=0,
        average_rate_num=12, average_rate_den=1, revision=0,
        initial_frame=None, read_only=False)
    try:
        window.save_changes_automatically.setChecked(True)
        window._dataset_generation = window.task_coordinator.next_generation()
        window.document_kind = DocumentKind.VIDEO
        window.video_snapshot = snapshot
        window.video_model = VideoProjectModel()
        window.current_video_frame_ref = VideoFrameRef(
            fingerprint, 0, 0, 1, 12)
        window.continuous_save.reset(
            window._continuous_document_key(), window._dataset_generation, 0)
        model = window.video_model
        track = model.create_track(
            'vehicle', 'rectangle', (0, 255, 0, 255), track_id='track-1')
        model.upsert_manual(
            track.track_id, window.current_video_frame_ref.pts,
            [2, 2, 20, 20])
        target_revision = model.revision

        window._on_video_model_mutation()

        def durable():
            try:
                return load_project(str(project_path)).revision >= \
                    target_revision
            except Exception:
                return False

        assert _wait(app, durable, timeout_ms=5000)
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
        assert not window.video_model.dirty
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_disabled_automatic_save_uses_navigation_safeguard(monkeypatch,
                                                           tmp_path):
    app, window = get_main_app()
    for name in ('a.png', 'b.png'):
        image = QImage(40, 30, QImage.Format_RGB32)
        image.fill(Qt.white)
        assert image.save(str(tmp_path / name))
    try:
        assert window.import_dir_images(str(tmp_path))
        window.save_changes_automatically.setChecked(False)
        window.dirty = True
        window.continuous_save.mark_dirty(1)
        QApplication.processEvents()
        assert window.continuous_save.state == 'pending'
        with monkeypatch.context() as patcher:
            patcher.setattr(
                window, 'discard_changes_dialog',
                lambda: QMessageBox.Cancel)
            current = window.file_path
            window.request_next_image()
            app.processEvents()
            assert window.file_path == current
    finally:
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()
