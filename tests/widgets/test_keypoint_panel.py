"""Tests for the keypoint checklist panel theming."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication

from libs.widgets.keypointPanel import KeypointPanel
from libs.utils.styles import Theme, get_theme_colors

app = QApplication.instance() or QApplication(sys.argv)


def _visible_first(n=17):
    return [(10, 10, 2)] + [None] * (n - 1)


class TestKeypointPanelTheme(unittest.TestCase):

    def test_status_color_follows_active_theme(self):
        panel = KeypointPanel()
        panel.load_template('person')
        panel.apply_theme(Theme.LIGHT)
        panel.set_keypoints(_visible_first())

        style = panel._rows[0]['status'].styleSheet()
        self.assertIn(get_theme_colors(Theme.LIGHT)['success'], style)

    def test_apply_theme_repaints_existing_keypoints(self):
        panel = KeypointPanel()
        panel.load_template('person')
        panel.set_keypoints(_visible_first())   # painted with default theme
        panel.apply_theme(Theme.LIGHT)          # theme switch must repaint

        style = panel._rows[0]['status'].styleSheet()
        self.assertIn(get_theme_colors(Theme.LIGHT)['success'], style)


if __name__ == '__main__':
    unittest.main()
