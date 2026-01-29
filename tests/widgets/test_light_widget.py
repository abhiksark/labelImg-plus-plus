#!/usr/bin/env python
# tests/widgets/test_light_widget.py
"""Tests for LightWidget."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication

from libs.widgets.lightWidget import LightWidget


class TestLightWidget(unittest.TestCase):
    """Tests for LightWidget functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init_with_title(self):
        """Test LightWidget initializes with title."""
        widget = LightWidget('Brightness')
        self.assertIsNotNone(widget)

    def test_default_value(self):
        """Test default brightness value."""
        widget = LightWidget('Brightness')
        # Should have some default value
        self.assertIsNotNone(widget.value())

    def test_set_value(self):
        """Test setting brightness value."""
        widget = LightWidget('Brightness')
        widget.setValue(50)
        self.assertEqual(widget.value(), 50)

    def test_value_changed_signal(self):
        """Test valueChanged signal is emitted."""
        widget = LightWidget('Brightness')
        signal_received = []

        def slot(value):
            signal_received.append(value)

        widget.valueChanged.connect(slot)
        widget.setValue(75)

        self.assertEqual(len(signal_received), 1)
        self.assertEqual(signal_received[0], 75)


if __name__ == '__main__':
    unittest.main()
