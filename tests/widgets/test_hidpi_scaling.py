# tests/widgets/test_hidpi_scaling.py
"""HiDPI scaling of fixed widget sizes (issue #66).

Each test pins the DPI factor to 2x and asserts that the widget's fixed or
minimum dimensions double. At the default 1x factor these wraps are no-ops,
so the production change is invisible on standard displays.
"""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from libs.utils import dpi
from libs.core.shortcut_config import ShortcutConfig
from libs.widgets.batchVerifyDialog import BatchVerifyDialog
from libs.widgets.shortcutsDialog import ShortcutsDialog
from libs.widgets.splitDialog import SplitDialog
from libs.widgets.keypointPanel import KeypointPanel
from libs.widgets.galleryWidget import GalleryWidget
from libs.widgets.toolBar import ToolBar


def _at_2x():
    """Patch the DPI factor to 2.0 for the duration of a with-block."""
    return patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0)


class TestDialogMinimumsScale(unittest.TestCase):
    def test_split_dialog_minimum_width_doubles(self):
        with _at_2x():
            dialog = SplitDialog(parent=None, image_count=10, default_dir='/tmp')
        self.assertEqual(dialog.minimumWidth(), 900)

    def test_batch_verify_dialog_minimum_width_doubles(self):
        with _at_2x():
            dialog = BatchVerifyDialog(parent=None, image_count=10,
                                       annotated_count=5)
        self.assertEqual(dialog.minimumWidth(), 700)

    def test_shortcuts_dialog_minimum_size_doubles(self):
        with _at_2x():
            dialog = ShortcutsDialog(ShortcutConfig(), {})
        self.assertEqual(dialog.minimumWidth(), 1100)
        self.assertEqual(dialog.minimumHeight(), 1000)


class TestToolBarWidthsScale(unittest.TestCase):
    def test_collapsed_and_expanded_widths_double(self):
        with _at_2x():
            toolbar = ToolBar('test')
        self.assertEqual(toolbar._collapsed_width, 170)
        self.assertEqual(toolbar._expanded_width, 280)


class TestGalleryControlsScale(unittest.TestCase):
    def test_preset_buttons_fixed_size_doubles(self):
        with _at_2x():
            gallery = GalleryWidget(show_size_slider=True)
        self.assertTrue(gallery._preset_buttons)
        btn = gallery._preset_buttons[0]
        self.assertEqual(btn.minimumWidth(), 64)
        self.assertEqual(btn.minimumHeight(), 52)

    def test_size_value_label_minimum_width_doubles(self):
        with _at_2x():
            gallery = GalleryWidget(show_size_slider=True)
        self.assertEqual(gallery.size_value_label.minimumWidth(), 100)


class TestKeypointPanelIndicatorsScale(unittest.TestCase):
    def test_status_label_fixed_width_doubles(self):
        with _at_2x():
            panel = KeypointPanel()
            panel.load_template('person')
        self.assertTrue(panel._rows)
        status = panel._rows[0]['status']
        self.assertEqual(status.minimumWidth(), 32)
        self.assertEqual(status.maximumWidth(), 32)


if __name__ == '__main__':
    unittest.main()
