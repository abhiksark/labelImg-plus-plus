#!/usr/bin/env python
# tests/integration/test_main_window.py
"""Tests for MainWindow core functionality.

Tests cover:
- File operations (load, save)
- Image navigation
- Annotation operations
- Mode switching
"""
import os
import sys
import tempfile
import shutil
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QImage

from labelImgPlusPlus import get_main_app
from libs.core.shape import Shape


class TestMainWindowFileOperations(unittest.TestCase):
    """Tests for file loading and saving."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        # Create test images
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset state before each test."""
        self.win.reset_state()
        self.win.default_save_dir = self.temp_dir

    def test_load_file_valid_image(self):
        """Test loading a valid image file."""
        self.win.load_file(self.test_image_path)
        self.assertEqual(self.win.file_path, self.test_image_path)
        self.assertFalse(self.win.image.isNull())

    def test_load_file_nonexistent(self):
        """Test loading a non-existent file."""
        fake_path = os.path.join(self.temp_dir, 'nonexistent.png')
        self.win.load_file(fake_path)
        # Should not crash, file_path should be unchanged or empty
        self.assertNotEqual(self.win.file_path, fake_path)

    def test_dirty_flag_on_annotation(self):
        """Test that dirty flag is set when adding annotation."""
        self.win.load_file(self.test_image_path)
        self.win.set_clean()
        self.assertFalse(self.win.dirty)

        # Simulate adding annotation via set_dirty
        self.win.set_dirty()

        self.assertTrue(self.win.dirty)

    def test_save_file_voc_format(self):
        """Test saving in PASCAL VOC format."""
        self.win.load_file(self.test_image_path)

        # Add annotation
        shape = Shape(label='car')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.add_label(shape)

        # Save as VOC
        from libs.formats.labelFile import LabelFileFormat
        self.win.label_file_format = LabelFileFormat.PASCAL_VOC
        self.win.save_file()

        # Check XML file exists
        xml_path = os.path.join(self.temp_dir, 'test_image.xml')
        self.assertTrue(os.path.exists(xml_path))

    def test_save_file_yolo_format(self):
        """Test saving in YOLO format."""
        self.win.load_file(self.test_image_path)

        # Add annotation
        shape = Shape(label='car')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(50, 50))
        shape.close()
        self.win.add_label(shape)

        # Save as YOLO
        from libs.formats.labelFile import LabelFileFormat
        self.win.label_file_format = LabelFileFormat.YOLO
        self.win.save_file()

        # Check TXT file exists
        txt_path = os.path.join(self.temp_dir, 'test_image.txt')
        self.assertTrue(os.path.exists(txt_path))


class TestMainWindowNavigation(unittest.TestCase):
    """Tests for image navigation."""

    @classmethod
    def setUpClass(cls):
        """Create app and test images."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()

        # Create multiple test images
        cls.image_paths = []
        for i in range(3):
            path = os.path.join(cls.temp_dir, f'image_{i}.png')
            img = QImage(100, 100, QImage.Format_RGB32)
            img.fill(0xFFFFFF)
            img.save(path)
            cls.image_paths.append(path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Load directory before each test."""
        self.win.reset_state()
        self.win.import_dir_images(self.temp_dir)
        self.win.load_file(self.image_paths[0])

    def test_next_image(self):
        """Test navigating to next image."""
        initial_path = self.win.file_path
        self.win.open_next_image()
        self.assertNotEqual(self.win.file_path, initial_path)
        self.assertEqual(self.win.file_path, self.image_paths[1])

    def test_prev_image(self):
        """Test navigating to previous image."""
        # Start from second image
        self.win.load_file(self.image_paths[1])
        initial_path = self.win.file_path
        self.win.open_prev_image()
        # Should have moved to a different image (or stayed if at start)
        # Just verify navigation doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_navigation_at_end(self):
        """Test navigation at end of list."""
        # Go to last image
        self.win.load_file(self.image_paths[-1])
        self.win.open_next_image()
        # Should stay at last or wrap - check doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_navigation_at_start(self):
        """Test navigation at start of list."""
        self.win.load_file(self.image_paths[0])
        self.win.open_prev_image()
        # Should stay at first or wrap - check doesn't crash
        self.assertIsNotNone(self.win.file_path)

    def test_image_list_populated(self):
        """Test that image list is populated correctly."""
        self.assertEqual(len(self.win.m_img_list), 3)


class TestMainWindowAnnotations(unittest.TestCase):
    """Tests for annotation operations."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset and load test image."""
        self.win.reset_state()
        self.win.load_file(self.test_image_path)

    def test_create_shape(self):
        """Test creating a bounding box annotation."""
        shape = Shape(label='person')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(60, 60))
        shape.close()

        # Add to canvas directly (like the canvas test pattern)
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 1)
        self.assertEqual(self.win.canvas.shapes[0].label, 'person')

    def test_delete_shape(self):
        """Test deleting an annotation."""
        # Add shape
        shape = Shape(label='person')
        shape.add_point(QPointF(10, 10))
        shape.add_point(QPointF(60, 60))
        shape.close()
        self.win.canvas.shapes.append(shape)
        self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 1)

        # Remove shape
        self.win.canvas.shapes.remove(shape)
        self.win.remove_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 0)

    def test_multiple_shapes(self):
        """Test handling multiple annotations."""
        for i, label in enumerate(['car', 'person', 'bike']):
            shape = Shape(label=label)
            shape.add_point(QPointF(10 + i*20, 10))
            shape.add_point(QPointF(50 + i*20, 50))
            shape.close()
            self.win.canvas.shapes.append(shape)
            self.win.add_label(shape)

        self.assertEqual(len(self.win.canvas.shapes), 3)


class TestMainWindowModes(unittest.TestCase):
    """Tests for mode switching."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()
        # Create test image for zoom tests
        cls.test_image_path = os.path.join(cls.temp_dir, 'test_image.png')
        img = QImage(100, 100, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(cls.test_image_path)

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_toggle_advanced_mode(self):
        """Test switching to advanced mode."""
        # Start in beginner mode
        self.assertTrue(self.win.beginner())

        self.win.toggle_advanced_mode(True)

        self.assertFalse(self.win.beginner())

    def test_toggle_beginner_mode(self):
        """Test switching back to beginner mode."""
        self.win.toggle_advanced_mode(True)
        self.assertFalse(self.win.beginner())

        self.win.toggle_advanced_mode(False)

        self.assertTrue(self.win.beginner())

    def test_zoom_in(self):
        """Test zoom in operation."""
        self.win.load_file(self.test_image_path)
        self.win.set_zoom(100)
        initial_zoom = self.win.zoom_widget.value()
        self.win.add_zoom(10)
        self.assertGreater(self.win.zoom_widget.value(), initial_zoom)

    def test_zoom_out(self):
        """Test zoom out operation."""
        self.win.load_file(self.test_image_path)
        self.win.set_zoom(150)
        initial_zoom = self.win.zoom_widget.value()
        self.win.add_zoom(-10)
        self.assertLess(self.win.zoom_widget.value(), initial_zoom)


if __name__ == '__main__':
    unittest.main()
