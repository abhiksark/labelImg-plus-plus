# tests/widgets/test_view_scaling.py
"""Tests for the pure fit-to-viewport scale helpers.

Extracted from MainWindow.scale_fit_window / scale_fit_width so the
aspect-ratio math can be exercised without a Qt main window.
"""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.widgets.view_scaling import fit_window_scale, fit_width_scale

# scale_fit_window subtracts a 2px epsilon from the viewport so fitting
# doesn't itself spawn scrollbars; the tests account for it.
EPS = 2.0


class TestFitWindowScale(unittest.TestCase):

    def test_pixmap_wider_than_viewport_is_width_bound(self):
        """When the pixmap is relatively wider (a2 >= a1), width is the
        limiting dimension: scale = (viewport_w - eps) / pixmap_w."""
        scale = fit_window_scale(802, 602, 400, 100)  # pixmap aspect 4.0
        self.assertAlmostEqual(scale, (802 - EPS) / 400)

    def test_pixmap_taller_than_viewport_is_height_bound(self):
        """When the pixmap is relatively taller (a2 < a1), height is the
        limiting dimension: scale = (viewport_h - eps) / pixmap_h."""
        scale = fit_window_scale(802, 602, 100, 400)  # pixmap aspect 0.25
        self.assertAlmostEqual(scale, (602 - EPS) / 400)

    def test_matches_legacy_formula_on_square(self):
        scale = fit_window_scale(402, 402, 200, 200)
        # Square pixmap in square viewport: a2 == a1 -> width-bound branch.
        self.assertAlmostEqual(scale, (402 - EPS) / 200)

    def test_degenerate_pixmap_returns_unit_scale(self):
        """Zero-sized pixmap must not raise ZeroDivisionError."""
        self.assertEqual(fit_window_scale(800, 600, 0, 0), 1.0)
        self.assertEqual(fit_window_scale(800, 600, 100, 0), 1.0)

    def test_degenerate_viewport_returns_unit_scale(self):
        """Viewport collapsed to the epsilon must not raise."""
        self.assertEqual(fit_window_scale(800, 2, 100, 100), 1.0)


class TestFitWidthScale(unittest.TestCase):

    def test_fits_pixmap_width_to_viewport(self):
        scale = fit_width_scale(802, 400)
        self.assertAlmostEqual(scale, (802 - EPS) / 400)

    def test_degenerate_pixmap_returns_unit_scale(self):
        self.assertEqual(fit_width_scale(800, 0), 1.0)


if __name__ == '__main__':
    unittest.main()
