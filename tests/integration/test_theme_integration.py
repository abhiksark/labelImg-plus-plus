# tests/integration/test_theme_integration.py
"""Theme propagation integration test.

Uses real assertions (not a try/except that returns True/False) so a
regression actually fails the suite.
"""
import sys
import os

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication, QMessageBox
import labelImgPlusPlus as application_module
from labelImgPlusPlus import MainWindow
from libs.core.settings import Settings
from libs.utils.styles import Theme

app = QApplication.instance() or QApplication(sys.argv)


def _window(monkeypatch, tmp_path):
    settings = Settings()
    settings.path = str(tmp_path / 'settings.json')
    monkeypatch.setattr(application_module, 'Settings', lambda: settings)
    default_file = os.path.join(
        os.path.dirname(__file__), '../../data/predefined_classes.txt')
    return MainWindow(default_prefdef_class_file=default_file)


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()


def test_theme_integration(monkeypatch, tmp_path):
    """Toggling the theme must propagate to the canvas and gallery."""
    win = _window(monkeypatch, tmp_path)
    try:
        initial_theme = win._current_theme
        initial_checked = win.dark_mode_action.isChecked()

        # Toggle via the action, the way the UI does.
        win.dark_mode_action.setChecked(not initial_checked)
        win._toggle_dark_mode()
        toggled_theme = win._current_theme
        assert toggled_theme != initial_theme

        # Theme must have reached the canvas and the gallery.
        assert win.canvas._theme == toggled_theme
        assert win.gallery_widget._current_theme == toggled_theme
        assert win.command_bar._current_theme == toggled_theme

        # Toggle back.
        win.dark_mode_action.setChecked(initial_checked)
        win._toggle_dark_mode()
        assert win._current_theme == initial_theme
    finally:
        _close(win)


def test_dark_popup_surfaces_are_owned_by_the_themed_workspace(
        monkeypatch, tmp_path):
    win = _window(monkeypatch, tmp_path)
    try:
        win._apply_theme(Theme.DARK)
        assert win.menus.labelList.parent() is win
        assert win.menus.recentFiles.parent() is win
        assert all(menu.parent() is win.canvas for menu in win.canvas.menus)
    finally:
        _close(win)


def test_format_warning_is_owned_by_the_themed_workspace(
        monkeypatch, tmp_path):
    win = _window(monkeypatch, tmp_path)
    parents = []

    def reject_dialog():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            parents.append(dialog.parent())
            dialog.reject()

    try:
        win._apply_theme(Theme.DARK)
        QTimer.singleShot(0, reject_dialog)
        win.change_format()
        assert parents == [win]
    finally:
        _close(win)
