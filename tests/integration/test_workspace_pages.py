# tests/integration/test_workspace_pages.py
"""Structural and routing coverage for Empty, Canvas, and Gallery pages."""

import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QMimeData, QSize, QUrl
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QDockWidget, QPushButton, QToolButton

from labelImgPlusPlus import MainWindow
from libs.core.video_types import DocumentKind
from libs.utils.styles import Theme


class _DropEvent(object):
    def __init__(self, urls):
        self._mime = QMimeData()
        self._mime.setUrls(urls)
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()
    QApplication.processEvents()


def test_empty_page_actions_and_recent_projection(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.workspace_pages.current_page() == 'empty'
        labels = {button.text() for button in
                  window.workspace_pages.empty_page.findChildren(QPushButton)
                  if not button.isHidden()}
        assert {'Open Image', 'Open Folder', 'Open Video'} <= labels

        paths = [str(tmp_path / ('recent-%s.png' % index))
                 for index in range(7)]
        window.workspace_pages.empty_page.set_recent_paths(paths)
        visible = [button for button in
                   window.workspace_pages.empty_page.recent_buttons
                   if not button.isHidden()]
        assert [button.property('path') for button in visible] == paths[:5]
        activated = []
        window.workspace_pages.empty_page.recentActivated.connect(
            activated.append)
        visible[0].click()
        assert activated == [paths[0]]
    finally:
        _close(window)


def test_gallery_is_embedded_and_keeps_workspace_chrome(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(1100, 700)
        window.show()
        QApplication.processEvents()
        original_central = window.centralWidget()
        window.toggle_gallery_mode(True)
        QApplication.processEvents()
        assert window.workspace_pages.current_page() == 'gallery'
        assert window.centralWidget() is original_central
        assert window.full_gallery.parent() is \
            window.workspace_pages.gallery_page
        assert window.full_gallery.window() is window
        assert not hasattr(window, 'gallery_window')
        assert window.tool_rail.isVisibleTo(window)
        assert window.workspace_inspector.isVisibleTo(window)
        assert window.workspace_pages.status_strip.isVisibleTo(window)

        window.toggle_gallery_mode(False)
        assert window.workspace_pages.current_page() == 'empty'
    finally:
        _close(window)


def test_drop_routing_accepts_exactly_one_supported_local_path(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    image_path = tmp_path / 'image.png'
    image = QImage(20, 10, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(image_path))
    unsupported = tmp_path / 'notes.bin'
    unsupported.write_bytes(b'not an image')
    directory = tmp_path / 'dataset'
    directory.mkdir()
    try:
        local_image = QUrl.fromLocalFile(str(image_path))
        local_dir = QUrl.fromLocalFile(str(directory))
        assert window._workspace_drop_path(_DropEvent([local_image])) == \
            str(image_path)
        assert window._workspace_drop_path(_DropEvent([local_dir])) == \
            str(directory)
        assert window._workspace_drop_path(_DropEvent([
            local_image, local_dir])) is None
        assert window._workspace_drop_path(_DropEvent([
            QUrl('https://example.com/image.png')])) is None
        assert window._workspace_drop_path(_DropEvent([
            QUrl.fromLocalFile(str(unsupported))])) is None

        accepted = _DropEvent([local_image])
        with patch.object(window, 'request_open_file') as open_file:
            window.dropEvent(accepted)
        assert accepted.accepted
        open_file.assert_called_once_with(str(image_path))

        rejected = _DropEvent([local_image, local_dir])
        with patch.object(window, 'request_open_file') as open_file, \
                patch.object(window, 'request_import_dir_images') as open_dir:
            window.dropEvent(rejected)
        assert not rejected.accepted
        open_file.assert_not_called()
        open_dir.assert_not_called()
        assert window.document_kind == DocumentKind.NONE
    finally:
        _close(window)


def test_canvas_chrome_reuses_actions_and_status_bar_is_hidden_bus(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        chrome = window.workspace_pages.canvas_chrome
        defaults = {button.defaultAction() for button in
                    chrome.findChildren(QToolButton)
                    if button.defaultAction() is not None}
        assert {window.actions.zoomOut, window.actions.zoomIn,
                window.actions.fitWindow, window.actions.fitWidth,
                window.actions.zoomOrg} <= defaults
        assert window.findChildren(QDockWidget) == []
        assert not window.statusBar().isVisible()

        window.status('Decoder warning', delay=0)
        QApplication.processEvents()
        assert window.statusBar().currentMessage() == 'Decoder warning'
        assert window.label_status_message.text() == 'Decoder warning'
        window.set_dirty()
        assert 'Unsaved' in window.label_save_status.text()
        window._apply_theme(Theme.DARK)
        assert 'Unsaved' in window.label_save_status.text()
        window.update_save_status(True)
        window._apply_theme(Theme.LIGHT)
        assert 'Saved' in window.label_save_status.text()
        assert window.label_active_tool.text()

        assert chrome.annotation_session_hint.isHidden()
        window.activate_box_tool()
        QApplication.processEvents()
        assert not chrome.annotation_session_hint.isHidden()
        assert 'Box stays active' in chrome.annotation_session_hint.text()

        window.activate_select_tool()
        QApplication.processEvents()
        assert chrome.annotation_session_hint.isHidden()

        window._original_image_size = QSize(1920, 1080)
        window.update_status_bar()
        assert window.label_dimensions.text() == '1920 x 1080'

        old_shortcut = window.actions.editMode.shortcut()
        window.actions.editMode.setShortcut('Alt+1')
        window.activate_select_tool()
        assert window.label_active_tool.text() == 'Select (Alt+1)'
        window.actions.editMode.setShortcut(old_shortcut)

        window.workspace_pages._update_status_visibility(320)
        assert window.label_status_message.isVisibleTo(
            window.workspace_pages.status_strip)
        assert window.label_save_status.isVisibleTo(
            window.workspace_pages.status_strip)
        assert window.label_zoom.isVisibleTo(
            window.workspace_pages.status_strip)
        assert not window.label_dimensions.isVisibleTo(
            window.workspace_pages.status_strip)
    finally:
        _close(window)
