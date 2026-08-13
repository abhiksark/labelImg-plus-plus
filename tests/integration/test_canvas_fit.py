import os
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage

from labelImgPlusPlus import get_main_app


def _wait(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _image(path, width=1600, height=1200, color=0xFFFFFFFF):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(color)
    assert image.save(path)


def test_fit_scale_uses_scroll_viewport_contents_rect(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'viewport.png')
    _image(image_path)
    window.resize(900, 700)
    window.load_file(image_path)
    app.processEvents()

    try:
        viewport = window.scroll_area.viewport().contentsRect()
        pixmap = window.canvas.pixmap
        with patch(
                'labelImgPlusPlus.view_scaling.fit_window_scale',
                return_value=1.0) as fit_window:
            window.scale_fit_window()
        fit_window.assert_called_once_with(
            viewport.width(), viewport.height(),
            pixmap.width(), pixmap.height())

        with patch(
                'labelImgPlusPlus.view_scaling.fit_width_scale',
                return_value=1.0) as fit_width:
            window.scale_fit_width()
        fit_width.assert_called_once_with(viewport.width(), pixmap.width())
        assert viewport.size() != window.centralWidget().contentsRect().size()
    finally:
        window.dirty = False
        window.close()


def test_loaded_images_enter_fit_mode_with_zero_scroll_ranges(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'fit.png')
    _image(image_path)
    window.resize(800, 600)

    try:
        assert window.load_file(image_path)
        assert _wait(app, lambda: window.actions.fitWindow.isChecked())
        assert window.zoom_mode == window.FIT_WINDOW
        for orientation in (Qt.Horizontal, Qt.Vertical):
            bar = window.scroll_bars[orientation]
            assert bar.minimum() == 0
            assert bar.maximum() == 0
            assert bar.value() == bar.minimum()
    finally:
        window.dirty = False
        window.close()


def test_fit_width_resets_pan_and_eliminates_horizontal_scroll(tmp_path):
    app, window = get_main_app()
    image_path = str(tmp_path / 'fit-width.png')
    _image(image_path, width=1000, height=1800)
    window.resize(800, 600)

    try:
        assert window.load_file(image_path)
        window.set_zoom(300)
        app.processEvents()
        for bar in window.scroll_bars.values():
            bar.setValue(bar.maximum())

        window.set_fit_width(True)
        app.processEvents()

        horizontal = window.scroll_bars[Qt.Horizontal]
        vertical = window.scroll_bars[Qt.Vertical]
        assert window.zoom_mode == window.FIT_WIDTH
        assert window.actions.fitWidth.isChecked()
        assert horizontal.maximum() == horizontal.minimum()
        assert horizontal.value() == horizontal.minimum()
        assert vertical.maximum() > vertical.minimum()
        assert vertical.value() == vertical.minimum()
    finally:
        window.dirty = False
        window.close()


def test_image_navigation_discards_manual_pan_and_refits(tmp_path):
    app, window = get_main_app()
    first = str(tmp_path / '001.png')
    second = str(tmp_path / '002.png')
    _image(first, color=0xFFFFFFFF)
    _image(second, color=0xFF000000)
    window.resize(800, 600)
    window.import_dir_images(str(tmp_path))

    try:
        window.set_zoom(300)
        app.processEvents()
        for bar in window.scroll_bars.values():
            assert bar.maximum() > bar.minimum()
            bar.setValue(bar.maximum())

        window.request_next_image()
        assert _wait(app, lambda: window.file_path == second)
        app.processEvents()

        assert window.zoom_mode == window.FIT_WINDOW
        assert window.actions.fitWindow.isChecked()
        for bar in window.scroll_bars.values():
            assert bar.maximum() == bar.minimum()
            assert bar.value() == bar.minimum()
    finally:
        window.dirty = False
        window.close()
