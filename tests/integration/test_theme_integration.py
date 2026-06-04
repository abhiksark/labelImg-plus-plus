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

from PyQt5.QtWidgets import QApplication
from labelImgPlusPlus import MainWindow

app = QApplication.instance() or QApplication(sys.argv)


def test_theme_integration():
    """Toggling the theme must propagate to the canvas and gallery."""
    default_file = os.path.join(
        os.path.dirname(__file__), '../../data/predefined_classes.txt')
    win = MainWindow(default_prefdef_class_file=default_file)

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

    # Toggle back.
    win.dark_mode_action.setChecked(initial_checked)
    win._toggle_dark_mode()
    assert win._current_theme == initial_theme


if __name__ == '__main__':
    test_theme_integration()
