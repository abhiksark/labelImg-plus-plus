import os
import time


if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'


from PyQt5.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PyQt5.QtGui import QImage, QMouseEvent  # noqa: E402
from PyQt5.QtTest import QSignalSpy, QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from labelImgPlusPlus import get_main_app  # noqa: E402


def _wait(app, predicate, timeout_ms=3000):
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def commit_rectangle(window, label):
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


def test_mid_drag_does_not_schedule_a_save(tmp_path):
    app, window = get_main_app()
    try:
        requested = QSignalSpy(window.continuous_save.saveRequested)
        event = QMouseEvent(
            QEvent.MouseMove, QPointF(20, 20), Qt.NoButton, Qt.LeftButton,
            Qt.NoModifier)
        window.canvas.mouseMoveEvent(event)
        app.processEvents()
        assert len(requested) == 0
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
