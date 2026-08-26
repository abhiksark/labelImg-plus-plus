import os
import json
import threading
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QThread, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QMessageBox

from labelImgPlusPlus import get_main_app
from libs.core.image_pipeline import load_image_result
from libs.formats.labelFile import LabelFileFormat


def _wait(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _image(path, color):
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(path)


def test_rapid_load_requests_commit_only_latest(tmp_path):
    app, window = get_main_app()
    first = str(tmp_path / 'first.png')
    second = str(tmp_path / 'second.png')
    third = str(tmp_path / 'third.png')
    for index, path in enumerate((first, second, third)):
        _image(path, 0xFF000000 + index)
    window.import_dir_images(str(tmp_path))
    gate = threading.Event()
    original = load_image_result

    def delayed(path, *args, **kwargs):
        if path == second:
            gate.wait(1)
        return original(path, *args, **kwargs)

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=delayed):
            window.request_load_file(second, skip_prompt=True)
            window.request_load_file(third, skip_prompt=True)
            assert _wait(app, lambda: window.file_path == third)
            gate.set()
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()['interactive'])
        assert window.file_path == third
    finally:
        window.dirty = False
        window.close()


def test_failed_async_load_keeps_current_document(tmp_path):
    app, window = get_main_app()
    valid = str(tmp_path / 'valid.png')
    _image(valid, 0xFFFFFFFF)
    window.load_file(valid)
    try:
        window.request_load_file(str(tmp_path / 'missing.png'), skip_prompt=True)
        assert _wait(
            app, lambda: not window.task_coordinator.queue_depths()['interactive'])
        app.processEvents()
        assert window.file_path == valid
        assert not window.image.isNull()
    finally:
        window.dirty = False
        window.close()


def test_standalone_open_replaces_dataset_only_after_success(tmp_path):
    app, window = get_main_app()
    dataset_dir = tmp_path / 'dataset'
    other_dir = tmp_path / 'other'
    dataset_dir.mkdir()
    other_dir.mkdir()
    first = str(dataset_dir / 'first.png')
    standalone = str(other_dir / 'standalone.png')
    _image(first, 0xFFFFFFFF)
    _image(standalone, 0xFF000000)
    window.import_dir_images(str(dataset_dir))

    try:
        window.request_open_file(standalone, skip_prompt=True)
        assert _wait(app, lambda: window.file_path == standalone)
        assert window.dataset_snapshot.image_paths == (standalone,)
        assert window.m_img_list == [standalone]
        assert window.img_count == 1
        assert len(window.frame_cache) == 1
    finally:
        window.dirty = False
        window.close()


def test_failed_standalone_open_restores_snapshot_generation(tmp_path):
    app, window = get_main_app()
    first = str(tmp_path / 'first.png')
    _image(first, 0xFFFFFFFF)
    window.import_dir_images(str(tmp_path))
    old_paths = window.dataset_snapshot.image_paths

    try:
        window.request_open_file(
            str(tmp_path / 'missing.png'), skip_prompt=True)
        assert _wait(
            app,
            lambda: not window.task_coordinator.queue_depths()['interactive'])
        app.processEvents()
        assert window.file_path == first
        assert window.dataset_snapshot.image_paths == old_paths
        assert window.dataset_snapshot.generation == \
            window._dataset_generation
    finally:
        window.dirty = False
        window.close()


def test_queued_statistics_refresh_is_inert_after_window_shutdown(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'image.png')
    _image(image_path, 0xFFFFFFFF)
    window.import_dir_images(str(tmp_path))
    window.dirty = False
    window.close()

    # Reproduce the delayed Gallery refresh that can outlive closeEvent. An
    # exception escaping this PyQt slot aborts the interpreter instead of
    # becoming an ordinary assertion failure.
    QTimer.singleShot(0, window._refresh_all_statistics)
    app.processEvents()
    app.processEvents()
    assert window.task_coordinator.is_shutting_down


def test_cancelled_standalone_open_does_not_advance_generation(tmp_path):
    _app, window = get_main_app()
    first = str(tmp_path / 'first.png')
    second = str(tmp_path / 'second.png')
    _image(first, 0xFFFFFFFF)
    _image(second, 0xFF000000)
    window.load_file(first)
    window.set_dirty()
    old_generation = window._dataset_generation

    try:
        with patch.object(
                window, 'discard_changes_dialog',
                return_value=QMessageBox.Cancel):
            assert window.request_open_file(second) is None
        assert window.file_path == first
        assert window._dataset_generation == old_generation
    finally:
        window.dirty = False
        window.close()


def test_save_completion_does_not_clean_newer_revision(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'image.png')
    _image(image_path, 0xFFFFFFFF)
    window.default_save_dir = str(tmp_path)
    window.label_file_format = LabelFileFormat.PASCAL_VOC
    window.load_file(image_path)
    window.set_dirty()
    gate = threading.Event()

    def delayed(request, cancelled=None, begin_commit=None):
        gate.wait(1)
        from libs.core.save_pipeline import write_save_request
        return write_save_request(
            request, cancelled=cancelled, begin_commit=begin_commit)

    try:
        with patch('labelImgPlusPlus.write_save_request', side_effect=delayed):
            window.request_save_file()
            window.set_dirty()
            gate.set()
            assert _wait(app, lambda: os.path.exists(tmp_path / 'image.xml'))
            app.processEvents()
        assert window.dirty is True
    finally:
        window.dirty = False
        window.close()


def test_save_as_uses_async_save_pipeline(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'image.png')
    annotation_base = str(tmp_path / 'renamed')
    _image(image_path, 0xFFFFFFFF)
    window.label_file_format = LabelFileFormat.PASCAL_VOC
    window.load_file(image_path)
    window.set_dirty()

    try:
        with patch.object(
                window, 'save_file_dialog',
                return_value=annotation_base):
            handle = window.request_save_file_as()
        assert handle is not None
        assert _wait(
            app, lambda: os.path.isfile(annotation_base + '.xml')
            and window.dirty is False)
        assert window.dirty is False
    finally:
        window.dirty = False
        window.close()


def test_main_window_cache_budgets_fit_combined_limit():
    _app, window = get_main_app()
    try:
        thumbnail_budget = window.gallery_widget.thumbnail_cache.max_bytes
        assert window.frame_cache.max_bytes + 2 * thumbnail_budget <= \
            128 * 1024 * 1024
    finally:
        window.dirty = False
        window.close()


def test_ultralytics_export_runs_on_background_lane(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'image.png')
    _image(image_path, 0xFFFFFFFF)
    annotation_path = str(tmp_path / 'image.xml')
    from libs.formats.pascal_voc_io import PascalVocWriter
    writer = PascalVocWriter(
        tmp_path.name, 'image.png', (48, 64, 3),
        local_img_path=image_path)
    writer.add_bnd_box(8, 6, 40, 30, 'object', False)
    writer.save(target_file=annotation_path)
    window.import_dir_images(str(tmp_path))
    destination = str(tmp_path / 'ultralytics')

    class _Dialog:
        output_dir = destination
        ratios = {'train': 1.0, 'val': 0.0, 'test': 0.0}
        seed = 42
        copy_mode = True

        def apply_theme(self, _theme):
            pass

        def exec_(self):
            from PyQt5.QtWidgets import QDialog
            return QDialog.Accepted

    try:
        with patch(
                'libs.widgets.ultralyticsExportDialog.'
                'UltralyticsExportDialog', return_value=_Dialog()), \
                patch.object(QMessageBox, 'information') as information, \
                patch.object(window, 'error_message') as error_message:
            handle = window.export_ultralytics_dataset()
            assert handle is not None
            assert _wait(
                app, lambda: os.path.isfile(
                    os.path.join(destination, 'data.yaml')))
            assert _wait(app, lambda: information.called)
        assert not error_message.called
        assert os.path.isfile(os.path.join(
            destination, 'labels', 'train', 'image.txt'))
        assert any(
            action.text() == 'Export Ultralytics Dataset...'
            for action in window.menus.tools.actions())
    finally:
        window.dirty = False
        window.close()


def test_worker_decodes_qimage_and_gui_thread_creates_qpixmap(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'thread-boundary.png')
    _image(image_path, 0xFFFFFFFF)
    decoded_off_thread = []
    pixmap_on_thread = []
    original_load = load_image_result
    original_from_image = QPixmap.fromImage

    def observed_load(*args, **kwargs):
        decoded_off_thread.append(
            QThread.currentThread() != app.thread())
        return original_load(*args, **kwargs)

    def observed_pixmap(image, *args, **kwargs):
        pixmap_on_thread.append(QThread.currentThread() == app.thread())
        return original_from_image(image, *args, **kwargs)

    try:
        with patch('labelImgPlusPlus.load_image_result', observed_load), \
                patch('labelImgPlusPlus.QPixmap.fromImage', observed_pixmap):
            window.request_load_file(image_path, skip_prompt=True)
            assert _wait(app, lambda: window.file_path == image_path)
        assert decoded_off_thread == [True]
        assert pixmap_on_thread == [True]
    finally:
        window.dirty = False
        window.close()


def test_directory_scan_is_transactional_and_latest_request_wins(tmp_path):
    app, window = get_main_app()
    first_dir = tmp_path / 'first'
    slow_dir = tmp_path / 'slow'
    latest_dir = tmp_path / 'latest'
    for directory, name in (
            (first_dir, 'first.png'),
            (slow_dir, 'slow.png'),
            (latest_dir, 'latest.png')):
        directory.mkdir()
        _image(str(directory / name), 0xFFFFFFFF)
    window.import_dir_images(str(first_dir))
    original_path = window.file_path
    original_scan = window.dataset_snapshot.scan
    gate = threading.Event()
    slow_started = threading.Event()

    def delayed_scan(root, *args, **kwargs):
        if os.path.abspath(root) == os.path.abspath(str(slow_dir)):
            slow_started.set()
            gate.wait(1)
        return original_scan(root, *args, **kwargs)

    try:
        with patch('labelImgPlusPlus.DatasetSnapshot.scan', delayed_scan):
            window.request_import_dir_images(str(slow_dir))
            assert slow_started.wait(1)
            app.processEvents()
            assert window.file_path == original_path
            window.request_import_dir_images(str(latest_dir))
            assert _wait(
                app,
                lambda: window.dataset_snapshot.root_dir
                == os.path.abspath(str(latest_dir)))
            gate.set()
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()['background'])
        assert window.dataset_snapshot.root_dir == os.path.abspath(
            str(latest_dir))
    finally:
        gate.set()
        window.dirty = False
        window.close()


def test_failed_directory_scan_keeps_committed_generation_and_identity(tmp_path):
    """A failed scan is only a candidate and cannot rebase live work."""
    app, window = get_main_app()
    first = str(tmp_path / 'first.png')
    _image(first, 0xFFFFFFFF)
    window.import_dir_images(str(tmp_path))
    old_paths = window.dataset_snapshot.image_paths
    old_snapshot = window.dataset_snapshot
    old_identity = window.document_identity
    old_generation = window._dataset_generation

    try:
        with patch(
                'labelImgPlusPlus.DatasetSnapshot.scan',
                side_effect=OSError('scan failed')):
            window.request_import_dir_images(str(tmp_path / 'missing'))
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()[
                    'background'])
            app.processEvents()
        assert window.file_path == first
        assert window.dataset_snapshot.image_paths == old_paths
        assert window.dataset_snapshot is old_snapshot
        assert window.document_identity == old_identity
        assert window._dataset_generation == old_generation
        assert window.canvas.isEnabled()
        assert window.inline_open_error.isVisible()
    finally:
        window.dirty = False
        window.close()


def test_unreadable_first_directory_candidate_keeps_live_workspace(tmp_path):
    """Directory publication waits for the first image to be fully staged."""
    app, window = get_main_app()
    current_dir = tmp_path / 'current'
    bad_dir = tmp_path / 'bad'
    current_dir.mkdir()
    bad_dir.mkdir()
    current = str(current_dir / 'current.png')
    _image(current, 0xFFFFFFFF)
    (bad_dir / 'bad.png').write_bytes(b'not an image')
    window.import_dir_images(str(current_dir))
    try:
        before_identity = window.document_identity
        before_pixmap = window.canvas.pixmap.cacheKey()
        before_snapshot = window.dataset_snapshot

        window.request_import_dir_images(str(bad_dir), skip_prompt=True)
        assert _wait(
            app,
            lambda: not window.task_coordinator.queue_depths()['background']
            and not window.task_coordinator.queue_depths()['interactive'])

        assert window.document_identity == before_identity
        assert window.dataset_snapshot is before_snapshot
        assert window.canvas.pixmap.cacheKey() == before_pixmap
        assert window.canvas.isEnabled()
        assert window.inline_open_error.isVisible()
    finally:
        window.dirty = False
        window.close()


def test_superseded_running_image_and_directory_keep_live_workspace(tmp_path):
    """Cancellation reconciles a live candidate without disabling the old image."""
    app, window = get_main_app()
    current_dir = tmp_path / 'current'
    candidate_dir = tmp_path / 'candidate'
    current_dir.mkdir()
    candidate_dir.mkdir()
    current = str(current_dir / 'current.png')
    candidate = str(candidate_dir / 'candidate.png')
    _image(current, 0xFFFFFFFF)
    _image(candidate, 0xFF000000)
    window.import_dir_images(str(current_dir))
    started = threading.Event()
    release = threading.Event()
    original_load = load_image_result

    def blocked_load(path, *args, **kwargs):
        if os.path.abspath(path) == os.path.abspath(candidate):
            started.set()
            release.wait(1)
        return original_load(path, *args, **kwargs)

    try:
        window.show()
        app.processEvents()
        window.canvas.setFocus()
        app.processEvents()
        assert window.canvas.hasFocus()
        before_identity = window.document_identity
        before_pixmap = window.canvas.pixmap.cacheKey()
        with patch('labelImgPlusPlus.load_image_result', side_effect=blocked_load), \
                patch('labelImgPlusPlus.DatasetSnapshot.scan',
                      side_effect=OSError('directory unavailable')):
            window.request_open_file(candidate, skip_prompt=True)
            assert started.wait(1)
            window.request_import_dir_images(str(tmp_path / 'missing'),
                                               skip_prompt=True)
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()['background'])
            release.set()
            assert _wait(
                app,
                lambda: not window.task_coordinator.queue_depths()['interactive'])

        assert window.document_identity == before_identity
        assert window.canvas.pixmap.cacheKey() == before_pixmap
        assert window.canvas.isEnabled()
        assert window.canvas.hasFocus()
        assert window.inline_open_error.isVisible()
    finally:
        release.set()
        window.dirty = False
        window.close()


def test_dirty_autosave_chains_navigation_after_durable_save(tmp_path):
    app, window = get_main_app()
    first = str(tmp_path / 'first.png')
    second = str(tmp_path / 'second.png')
    _image(first, 0xFFFFFFFF)
    _image(second, 0xFF000000)
    window.default_save_dir = str(tmp_path)
    window.import_dir_images(str(tmp_path))
    window.auto_saving.setChecked(True)
    window.set_dirty()

    try:
        window.request_next_image()
        assert _wait(app, lambda: window.file_path == second)
        assert os.path.isfile(os.path.splitext(first)[0] + '.xml')
        assert window.dirty is False
    finally:
        window.dirty = False
        window.close()


def test_dirty_directory_replacement_chains_after_durable_save(tmp_path):
    app, window = get_main_app()
    first_dir = tmp_path / 'first'
    second_dir = tmp_path / 'second'
    first_dir.mkdir()
    second_dir.mkdir()
    first = str(first_dir / 'first.png')
    second = str(second_dir / 'second.png')
    _image(first, 0xFFFFFFFF)
    _image(second, 0xFF000000)
    window.default_save_dir = str(first_dir)
    window.import_dir_images(str(first_dir))
    window.auto_saving.setChecked(True)
    window.set_dirty()

    try:
        window.request_import_dir_images(str(second_dir))
        assert _wait(
            app,
            lambda: window.dataset_snapshot.root_dir
            == os.path.abspath(str(second_dir))
            and window.file_path == second)
        assert os.path.isfile(first_dir / 'first.xml')
        assert window.dirty is False
    finally:
        window.dirty = False
        window.close()


def test_synchronous_load_compatibility_reads_shared_coco(tmp_path):
    _app, window = get_main_app()
    image_path = str(tmp_path / 'image.png')
    _image(image_path, 0xFFFFFFFF)
    (tmp_path / 'annotations.json').write_text(json.dumps({
        'images': [{
            'id': 1, 'file_name': 'image.png',
            'width': 64, 'height': 48,
        }],
        'annotations': [{
            'id': 1, 'image_id': 1, 'category_id': 1,
            'bbox': [1, 2, 10, 12],
        }],
        'categories': [{'id': 1, 'name': 'cat'}],
    }))
    window.default_save_dir = str(tmp_path)
    window.label_file_format = LabelFileFormat.COCO

    try:
        assert window.load_file(image_path)
        assert len(window.canvas.shapes) == 1
        assert window.canvas.shapes[0].label == 'cat'
    finally:
        window.dirty = False
        window.close()


def test_save_directory_change_rebuilds_generation_and_reloads(tmp_path):
    app, window = get_main_app()
    image_dir = tmp_path / 'images'
    label_dir = tmp_path / 'labels'
    image_dir.mkdir()
    label_dir.mkdir()
    image_path = str(image_dir / 'image.png')
    _image(image_path, 0xFFFFFFFF)
    (label_dir / 'image.xml').write_text(
        '<annotation><filename>image.png</filename>'
        '<size><width>64</width><height>48</height><depth>3</depth></size>'
        '<object><name>cat</name><difficult>0</difficult><bndbox>'
        '<xmin>1</xmin><ymin>2</ymin><xmax>10</xmax><ymax>12</ymax>'
        '</bndbox></object></annotation>')
    window.default_save_dir = str(image_dir)
    window.import_dir_images(str(image_dir))
    old_generation = window._dataset_generation

    try:
        with patch.object(
                window, 'pick_directory', return_value=str(label_dir)):
            window.change_save_dir_dialog()
        assert _wait(
            app, lambda: window.file_path == image_path
            and len(window.canvas.shapes) == 1)
        assert window._dataset_generation > old_generation
        assert window.dataset_snapshot.generation == \
            window._dataset_generation
        assert window.default_save_dir == str(label_dir)
        assert window.canvas.shapes[0].label == 'cat'
    finally:
        window.dirty = False
        window.close()
