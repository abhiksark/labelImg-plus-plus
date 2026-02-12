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

    def test_range_bounds(self):
        """Test LightWidget range is 0-100."""
        widget = LightWidget('Brightness')
        self.assertEqual(widget.minimum(), 0)
        self.assertEqual(widget.maximum(), 100)

    def test_suffix(self):
        """Test LightWidget shows percentage suffix."""
        widget = LightWidget('Brightness')
        self.assertEqual(widget.suffix(), ' %')

    def test_tooltip(self):
        """Test LightWidget has tooltip."""
        widget = LightWidget('Brightness')
        self.assertEqual(widget.toolTip(), 'Brightness')

    def test_minimumSizeHint(self):
        """Test minimumSizeHint returns valid QSize."""
        widget = LightWidget('Brightness')
        size_hint = widget.minimumSizeHint()
        self.assertIsNotNone(size_hint)
        self.assertGreater(size_hint.width(), 0)
        self.assertGreater(size_hint.height(), 0)

    def test_color_at_50_returns_none(self):
        """Test color() returns None at default value (50)."""
        widget = LightWidget('Brightness', value=50)
        self.assertIsNone(widget.color())

    def test_color_at_0_returns_dark(self):
        """Test color() at 0 returns near-black QColor."""
        widget = LightWidget('Brightness')
        widget.setValue(0)
        color = widget.color()
        self.assertIsNotNone(color)
        # At 0%, strength = 0, so RGB should be (0, 0, 0)
        self.assertEqual(color.red(), 0)
        self.assertEqual(color.green(), 0)
        self.assertEqual(color.blue(), 0)

    def test_color_at_100_returns_bright(self):
        """Test color() at 100 returns near-white QColor."""
        widget = LightWidget('Brightness')
        widget.setValue(100)
        color = widget.color()
        self.assertIsNotNone(color)
        # At 100%, strength = 255, so RGB should be (255, 255, 255)
        self.assertEqual(color.red(), 255)
        self.assertEqual(color.green(), 255)
        self.assertEqual(color.blue(), 255)


if __name__ == '__main__':
    unittest.main()
