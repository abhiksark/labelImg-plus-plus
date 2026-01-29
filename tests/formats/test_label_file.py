"""Tests for LabelFile class and utility functions."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.labelFile import LabelFile, LabelFileFormat


class TestConvertPointsToBndBox(unittest.TestCase):
    """Test cases for convert_points_to_bnd_box static method."""

    def test_standard_rectangle(self):
        """Test conversion of standard rectangle points."""
        # Points in order: top-left, top-right, bottom-right, bottom-left
        points = [(10, 20), (100, 20), (100, 80), (10, 80)]
        result = LabelFile.convert_points_to_bnd_box(points)

        self.assertEqual(result, (10, 20, 100, 80))

    def test_unordered_points(self):
        """Test that unordered points still produce correct bounding box."""
        # Points in random order
        points = [(100, 80), (10, 20), (100, 20), (10, 80)]
        result = LabelFile.convert_points_to_bnd_box(points)

        self.assertEqual(result, (10, 20, 100, 80))

    def test_float_points(self):
        """Test that float coordinates are converted to int."""
        points = [(10.5, 20.7), (100.9, 20.3), (100.1, 80.8), (10.2, 80.4)]
        result = LabelFile.convert_points_to_bnd_box(points)

        # Should return integers
        self.assertIsInstance(result[0], int)
        self.assertIsInstance(result[1], int)
        self.assertIsInstance(result[2], int)
        self.assertIsInstance(result[3], int)

    def test_zero_coordinate_clamped_to_one(self):
        """Test that coordinates < 1 are clamped to 1."""
        points = [(0, 0), (50, 0), (50, 50), (0, 50)]
        result = LabelFile.convert_points_to_bnd_box(points)

        # x_min and y_min should be clamped to 1
        self.assertEqual(result[0], 1)  # x_min
        self.assertEqual(result[1], 1)  # y_min

    def test_negative_coordinate_clamped_to_one(self):
        """Test that negative coordinates are clamped to 1."""
        points = [(-5, -10), (50, -10), (50, 50), (-5, 50)]
        result = LabelFile.convert_points_to_bnd_box(points)

        self.assertEqual(result[0], 1)  # x_min clamped from -5
        self.assertEqual(result[1], 1)  # y_min clamped from -10

    def test_single_point_box(self):
        """Test degenerate case of single point repeated."""
        points = [(50, 50), (50, 50), (50, 50), (50, 50)]
        result = LabelFile.convert_points_to_bnd_box(points)

        self.assertEqual(result, (50, 50, 50, 50))

    def test_two_point_diagonal(self):
        """Test with only two points (diagonal corners)."""
        points = [(10, 20), (100, 80)]
        result = LabelFile.convert_points_to_bnd_box(points)

        self.assertEqual(result, (10, 20, 100, 80))


class TestLabelFileFormat(unittest.TestCase):
    """Test cases for LabelFileFormat enum."""

    def test_format_values(self):
        """Test that format enum has expected values."""
        self.assertEqual(LabelFileFormat.PASCAL_VOC.value, 1)
        self.assertEqual(LabelFileFormat.YOLO.value, 2)
        self.assertEqual(LabelFileFormat.CREATE_ML.value, 3)


class TestIsLabelFile(unittest.TestCase):
    """Test cases for is_label_file static method."""

    def test_xml_file_is_label_file(self):
        """Test that .xml files are recognized as label files."""
        self.assertTrue(LabelFile.is_label_file('annotation.xml'))
        self.assertTrue(LabelFile.is_label_file('/path/to/file.xml'))
        self.assertTrue(LabelFile.is_label_file('FILE.XML'))  # case insensitive

    def test_non_xml_not_label_file(self):
        """Test that non-.xml files are not recognized as label files."""
        self.assertFalse(LabelFile.is_label_file('image.jpg'))
        self.assertFalse(LabelFile.is_label_file('data.json'))
        self.assertFalse(LabelFile.is_label_file('labels.txt'))


class TestLabelFileInit(unittest.TestCase):
    """Test cases for LabelFile initialization."""

    def test_default_init(self):
        """Test default initialization."""
        lf = LabelFile()

        self.assertEqual(lf.shapes, ())
        self.assertIsNone(lf.image_path)
        self.assertIsNone(lf.image_data)
        self.assertFalse(lf.verified)

    def test_toggle_verify(self):
        """Test toggle_verify method."""
        lf = LabelFile()

        self.assertFalse(lf.verified)
        lf.toggle_verify()
        self.assertTrue(lf.verified)
        lf.toggle_verify()
        self.assertFalse(lf.verified)


if __name__ == '__main__':
    unittest.main()
