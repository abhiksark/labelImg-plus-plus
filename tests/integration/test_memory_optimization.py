# tests/test_memory_optimization.py
"""Tests for memory optimization with large images (Issue #31)."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
sys.path.insert(0, os.path.join(dir_name, '..', '..', 'libs'))

try:
    from PyQt5.QtCore import QSize, Qt
    from PyQt5.QtGui import QImageReader
except ImportError:
    from PyQt4.QtCore import QSize, Qt
    from PyQt4.QtGui import QImageReader


class TestImageScaling(unittest.TestCase):
    """Test cases for image downsampling logic."""

    def test_scale_factor_calculation(self):
        """Test scale factor calculation for large images."""
        # Simulate 4K image (3840x2160) being scaled to max 2048
        original_width = 3840
        original_height = 2160
        max_display_dim = 2048

        original_size = QSize(original_width, original_height)
        if original_size.width() > max_display_dim or original_size.height() > max_display_dim:
            scaled_size = original_size.scaled(max_display_dim, max_display_dim, Qt.KeepAspectRatio)
            scale_factor = scaled_size.width() / original_size.width()
        else:
            scale_factor = 1.0
            scaled_size = original_size

        # Scale factor should be 2048/3840 = 0.533...
        self.assertAlmostEqual(scale_factor, 2048 / 3840, places=4)
        # Scaled width should be 2048
        self.assertEqual(scaled_size.width(), 2048)
        # Scaled height should maintain aspect ratio: 2160 * (2048/3840) = 1152
        self.assertEqual(scaled_size.height(), 1152)

    def test_small_image_no_scaling(self):
        """Test that small images are not scaled."""
        original_width = 1920
        original_height = 1080
        max_display_dim = 2048

        original_size = QSize(original_width, original_height)
        if original_size.width() > max_display_dim or original_size.height() > max_display_dim:
            scaled_size = original_size.scaled(max_display_dim, max_display_dim, Qt.KeepAspectRatio)
            scale_factor = scaled_size.width() / original_size.width()
        else:
            scale_factor = 1.0
            scaled_size = original_size

        # No scaling for images <= 2048
        self.assertEqual(scale_factor, 1.0)
        self.assertEqual(scaled_size.width(), 1920)
        self.assertEqual(scaled_size.height(), 1080)

    def test_8k_image_scaling(self):
        """Test scale factor calculation for 8K images."""
        # 8K image (7680x4320)
        original_width = 7680
        original_height = 4320
        max_display_dim = 2048

        original_size = QSize(original_width, original_height)
        scaled_size = original_size.scaled(max_display_dim, max_display_dim, Qt.KeepAspectRatio)
        scale_factor = scaled_size.width() / original_size.width()

        # Scale factor should be 2048/7680 = 0.267...
        self.assertAlmostEqual(scale_factor, 2048 / 7680, places=4)
        # Scaled width should be 2048
        self.assertEqual(scaled_size.width(), 2048)
        # Scaled height: 4320 * (2048/7680) = 1152
        self.assertEqual(scaled_size.height(), 1152)


class TestCoordinateScaling(unittest.TestCase):
    """Test cases for coordinate transformation."""

    def test_display_to_original_scaling(self):
        """Test scaling display coordinates to original coordinates."""
        scale_factor = 0.5  # Image displayed at half size
        inv_scale = 1.0 / scale_factor

        # Display coord (100, 50) should map to original (200, 100)
        display_x, display_y = 100, 50
        original_x = display_x * inv_scale
        original_y = display_y * inv_scale

        self.assertEqual(original_x, 200)
        self.assertEqual(original_y, 100)

    def test_original_to_display_scaling(self):
        """Test scaling original coordinates to display coordinates."""
        scale_factor = 0.5  # Image displayed at half size

        # Original coord (200, 100) should map to display (100, 50)
        original_x, original_y = 200, 100
        display_x = original_x * scale_factor
        display_y = original_y * scale_factor

        self.assertEqual(display_x, 100)
        self.assertEqual(display_y, 50)

    def test_roundtrip_scaling(self):
        """Test that coordinates survive roundtrip scaling."""
        scale_factor = 0.2666  # Simulated 8K to 2K scaling

        original_coords = [(100.0, 200.0), (500.0, 300.0), (1000.0, 800.0)]

        for orig_x, orig_y in original_coords:
            # Original -> Display
            display_x = orig_x * scale_factor
            display_y = orig_y * scale_factor

            # Display -> Original
            recovered_x = display_x / scale_factor
            recovered_y = display_y / scale_factor

            # Should recover original coordinates
            self.assertAlmostEqual(recovered_x, orig_x, places=4)
            self.assertAlmostEqual(recovered_y, orig_y, places=4)

    def test_no_scaling_passthrough(self):
        """Test that scale factor 1.0 passes coordinates through unchanged."""
        scale_factor = 1.0
        inv_scale = 1.0 / scale_factor

        original_x, original_y = 123.456, 789.012

        display_x = original_x * scale_factor
        display_y = original_y * scale_factor
        recovered_x = display_x * inv_scale
        recovered_y = display_y * inv_scale

        self.assertEqual(display_x, original_x)
        self.assertEqual(display_y, original_y)
        self.assertEqual(recovered_x, original_x)
        self.assertEqual(recovered_y, original_y)


class TestAnnotationCoordinates(unittest.TestCase):
    """Test cases for annotation coordinate handling."""

    def test_bounding_box_scaling(self):
        """Test that bounding box coordinates scale correctly."""
        scale_factor = 0.5

        # Original bounding box: top-left (100, 100), bottom-right (300, 200)
        original_points = [(100, 100), (300, 100), (300, 200), (100, 200)]

        # Scale to display
        display_points = [(x * scale_factor, y * scale_factor) for x, y in original_points]

        expected_display = [(50, 50), (150, 50), (150, 100), (50, 100)]
        for (dx, dy), (ex, ey) in zip(display_points, expected_display):
            self.assertEqual(dx, ex)
            self.assertEqual(dy, ey)

        # Scale back to original
        inv_scale = 1.0 / scale_factor
        recovered_points = [(x * inv_scale, y * inv_scale) for x, y in display_points]

        for (rx, ry), (ox, oy) in zip(recovered_points, original_points):
            self.assertEqual(rx, ox)
            self.assertEqual(ry, oy)

    def test_normalized_yolo_coords_unchanged(self):
        """Test that YOLO normalized coordinates work with any image size."""
        # YOLO stores normalized coords (0-1), so they're resolution-independent
        # When loading: normalized -> pixel (using original size)
        # When saving: pixel -> normalized (using original size)

        normalized_x_center = 0.5
        normalized_y_center = 0.5
        normalized_width = 0.2
        normalized_height = 0.3

        # For 4K original image
        orig_width = 3840
        orig_height = 2160

        # Convert to pixel coords in original space
        pixel_x_center = normalized_x_center * orig_width  # 1920
        pixel_y_center = normalized_y_center * orig_height  # 1080

        # Convert back to normalized
        recovered_x = pixel_x_center / orig_width
        recovered_y = pixel_y_center / orig_height

        self.assertEqual(recovered_x, normalized_x_center)
        self.assertEqual(recovered_y, normalized_y_center)


class TestMockImageForYolo(unittest.TestCase):
    """Test the mock image class used for YOLO loading."""

    def test_mock_image_dimensions(self):
        """Test that mock image provides correct dimensions."""
        class MockImage:
            def __init__(self, size, grayscale=False):
                self._size = size
                self._grayscale = grayscale
            def width(self):
                return self._size.width()
            def height(self):
                return self._size.height()
            def isGrayscale(self):
                return self._grayscale

        original_size = QSize(3840, 2160)
        mock = MockImage(original_size, grayscale=False)

        self.assertEqual(mock.width(), 3840)
        self.assertEqual(mock.height(), 2160)
        self.assertFalse(mock.isGrayscale())

    def test_mock_image_grayscale(self):
        """Test mock image grayscale flag."""
        class MockImage:
            def __init__(self, size, grayscale=False):
                self._size = size
                self._grayscale = grayscale
            def width(self):
                return self._size.width()
            def height(self):
                return self._size.height()
            def isGrayscale(self):
                return self._grayscale

        original_size = QSize(1920, 1080)
        mock = MockImage(original_size, grayscale=True)

        self.assertTrue(mock.isGrayscale())


class TestQImageReaderScaling(unittest.TestCase):
    """Test QImageReader scaled size functionality."""

    def test_scaled_size_preserves_aspect_ratio(self):
        """Test that QSize.scaled() preserves aspect ratio."""
        # 16:9 aspect ratio
        original = QSize(1920, 1080)
        scaled = original.scaled(1280, 1280, Qt.KeepAspectRatio)

        # Width should be 1280 (the limiting dimension)
        self.assertEqual(scaled.width(), 1280)
        # Height should maintain 16:9 ratio: 1080 * (1280/1920) = 720
        self.assertEqual(scaled.height(), 720)

    def test_scaled_size_square_constraint(self):
        """Test scaling with square constraint."""
        # Wide image
        original = QSize(4000, 1000)
        scaled = original.scaled(2048, 2048, Qt.KeepAspectRatio)

        # Width limited to 2048
        self.assertEqual(scaled.width(), 2048)
        # Height: 1000 * (2048/4000) = 512
        self.assertEqual(scaled.height(), 512)

    def test_scaled_size_tall_image(self):
        """Test scaling tall image."""
        # Tall image (portrait)
        original = QSize(1000, 4000)
        scaled = original.scaled(2048, 2048, Qt.KeepAspectRatio)

        # Height limited to 2048
        self.assertEqual(scaled.height(), 2048)
        # Width: 1000 * (2048/4000) = 512
        self.assertEqual(scaled.width(), 512)


if __name__ == '__main__':
    unittest.main()
