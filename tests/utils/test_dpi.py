# tests/utils/test_dpi.py
"""Tests for the central DPI scaling utilities."""

import os
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from libs.utils import dpi


class TestScalePx(unittest.TestCase):
    """scale_px multiplies a base pixel value by the current DPI factor."""

    def test_at_1x_returns_input_unchanged(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.0):
            self.assertEqual(dpi.scale_px(450), 450)

    def test_at_2x_doubles_value(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0):
            self.assertEqual(dpi.scale_px(450), 900)

    def test_fractional_factor_rounds_to_nearest_int(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.25):
            self.assertEqual(dpi.scale_px(80), 100)

    def test_returns_int_type(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.5):
            result = dpi.scale_px(24)
            self.assertIsInstance(result, int)
            self.assertEqual(result, 36)

    def test_zero_stays_zero(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0):
            self.assertEqual(dpi.scale_px(0), 0)


class TestGetDpiScaleFactor(unittest.TestCase):
    """get_dpi_scale_factor reads the primary screen's logical DPI."""

    def test_returns_one_when_no_application(self):
        with patch.object(dpi, 'QApplication') as mock_app:
            mock_app.instance.return_value = None
            self.assertEqual(dpi.get_dpi_scale_factor(), 1.0)

    def test_returns_positive_float(self):
        factor = dpi.get_dpi_scale_factor()
        self.assertIsInstance(factor, float)
        self.assertGreater(factor, 0.0)


if __name__ == '__main__':
    unittest.main()
