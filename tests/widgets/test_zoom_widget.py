#!/usr/bin/env python
# tests/widgets/test_zoom_widget.py
"""Tests for ZoomWidget."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication

from libs.widgets.zoomWidget import ZoomWidget


class TestZoomWidget(unittest.TestCase):
    """Tests for ZoomWidget functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init_default_value(self):
        """Test ZoomWidget initializes with correct default."""
        widget = ZoomWidget(value=100)
        self.assertEqual(widget.value(), 100)

    def test_set_value(self):
        """Test setting zoom value."""
        widget = ZoomWidget(value=100)
        widget.setValue(150)
        self.assertEqual(widget.value(), 150)

    def test_value_range(self):
        """Test zoom value stays within range."""
        widget = ZoomWidget(value=100)
        # Check minimum/maximum are set
        self.assertIsNotNone(widget.minimum())
        self.assertIsNotNone(widget.maximum())

    def test_value_changed_signal(self):
        """Test valueChanged signal is emitted."""
        widget = ZoomWidget(value=100)
        signal_received = []

        def slot(value):
            signal_received.append(value)

        widget.valueChanged.connect(slot)
        widget.setValue(120)

        self.assertEqual(len(signal_received), 1)
        self.assertEqual(signal_received[0], 120)


if __name__ == '__main__':
    unittest.main()
