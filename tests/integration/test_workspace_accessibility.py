"""Drawer focus and assistive-technology contracts."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

from labelImgPlusPlus import MainWindow


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()
    QApplication.processEvents()


def test_drawer_scrim_dismisses_and_restores_reopen_focus(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()
        assert window.workspace_inspector.collapse_button.accessibleName() == \
            'Close inspector'

        QTest.mouseClick(window.workspace_shell.scrim, Qt.LeftButton)
        QApplication.processEvents()
        assert window.workspace_inspector.isHidden()
        assert window.workspace_shell.reopen_button.hasFocus()
    finally:
        _close(window)


def test_tab_focus_stays_inside_visible_drawer(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()

        for _index in range(32):
            QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
            QApplication.processEvents()
            focused = QApplication.focusWidget()
            assert focused is window.workspace_inspector or \
                window.workspace_inspector.isAncestorOf(focused)
    finally:
        _close(window)


def test_reopen_accessible_name_includes_current_object_count(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 0 objects'
        window.canvas.shapes = [object(), object(), object()]
        window.update_box_count()
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 3 objects'

        window.reset_state()
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 0 objects'
    finally:
        _close(window)
