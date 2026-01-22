"""Tests for YOLO format I/O."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..'))

from libs.yolo_io import YOLOWriter, YoloReader


class MockQImage:
    """Mock QImage for testing YoloReader without Qt dependency."""

    def __init__(self, width, height, grayscale=False):
        self._width = width
        self._height = height
        self._grayscale = grayscale

    def width(self):
        return self._width

    def height(self):
        return self._height

    def isGrayscale(self):
        return self._grayscale


class TestYOLOWriter(unittest.TestCase):
    """Test cases for YOLO format writer."""

    def setUp(self):
        """Create a temp directory for test outputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_single_box(self):
        """Test writing a single bounding box."""
        txt_path = os.path.join(self.temp_dir, 'test.txt')

        writer = YOLOWriter(self.temp_dir, 'test', (100, 200, 3))  # height=100, width=200
        writer.add_bnd_box(50, 25, 150, 75, 'person', difficult=0)
        writer.save(class_list=['person'], target_file=txt_path)

        with open(txt_path, 'r') as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 1)
        parts = lines[0].strip().split()
        self.assertEqual(len(parts), 5)

        class_idx = int(parts[0])
        x_center = float(parts[1])
        y_center = float(parts[2])
        w = float(parts[3])
        h = float(parts[4])

        self.assertEqual(class_idx, 0)
        # x_center = (50 + 150) / 2 / 200 = 100 / 200 = 0.5
        self.assertAlmostEqual(x_center, 0.5, places=4)
        # y_center = (25 + 75) / 2 / 100 = 50 / 100 = 0.5
        self.assertAlmostEqual(y_center, 0.5, places=4)
        # w = (150 - 50) / 200 = 100 / 200 = 0.5
        self.assertAlmostEqual(w, 0.5, places=4)
        # h = (75 - 25) / 100 = 50 / 100 = 0.5
        self.assertAlmostEqual(h, 0.5, places=4)

    def test_write_multiple_boxes(self):
        """Test writing multiple bounding boxes."""
        txt_path = os.path.join(self.temp_dir, 'multi.txt')

        writer = YOLOWriter(self.temp_dir, 'multi', (100, 100, 3))
        writer.add_bnd_box(0, 0, 50, 50, 'cat', difficult=0)
        writer.add_bnd_box(50, 50, 100, 100, 'dog', difficult=0)
        writer.save(class_list=['cat', 'dog'], target_file=txt_path)

        with open(txt_path, 'r') as f:
            lines = f.readlines()

        self.assertEqual(len(lines), 2)

        # First box: cat
        parts1 = lines[0].strip().split()
        self.assertEqual(int(parts1[0]), 0)  # class index for 'cat'

        # Second box: dog
        parts2 = lines[1].strip().split()
        self.assertEqual(int(parts2[0]), 1)  # class index for 'dog'

    def test_classes_file_created(self):
        """Test that classes.txt is created with correct content."""
        txt_path = os.path.join(self.temp_dir, 'test.txt')

        writer = YOLOWriter(self.temp_dir, 'test', (100, 100, 3))
        writer.add_bnd_box(10, 10, 50, 50, 'apple', difficult=0)
        writer.add_bnd_box(60, 60, 90, 90, 'banana', difficult=0)
        writer.save(class_list=['apple', 'banana'], target_file=txt_path)

        classes_path = os.path.join(self.temp_dir, 'classes.txt')
        self.assertTrue(os.path.exists(classes_path))

        with open(classes_path, 'r') as f:
            classes = [line.strip() for line in f.readlines()]

        self.assertEqual(classes, ['apple', 'banana'])

    def test_new_class_appended_to_list(self):
        """Test that new classes are appended to the class list."""
        txt_path = os.path.join(self.temp_dir, 'append.txt')

        writer = YOLOWriter(self.temp_dir, 'append', (100, 100, 3))
        writer.add_bnd_box(10, 10, 50, 50, 'existing', difficult=0)
        writer.add_bnd_box(60, 60, 90, 90, 'new_class', difficult=0)

        class_list = ['existing']
        writer.save(class_list=class_list, target_file=txt_path)

        # new_class should have been appended
        self.assertIn('new_class', class_list)

    def test_coordinate_normalization(self):
        """Test that coordinates are properly normalized to [0, 1]."""
        txt_path = os.path.join(self.temp_dir, 'norm.txt')

        # Image: 640x480 (width x height, but img_size is [height, width, depth])
        writer = YOLOWriter(self.temp_dir, 'norm', (480, 640, 3))
        # Box: x=64, y=48, width=320, height=240 -> center at (224, 168)
        writer.add_bnd_box(64, 48, 384, 288, 'obj', difficult=0)
        writer.save(class_list=['obj'], target_file=txt_path)

        with open(txt_path, 'r') as f:
            line = f.readline().strip()

        parts = line.split()
        x_center = float(parts[1])
        y_center = float(parts[2])
        w = float(parts[3])
        h = float(parts[4])

        # x_center = (64 + 384) / 2 / 640 = 224 / 640 = 0.35
        self.assertAlmostEqual(x_center, 0.35, places=4)
        # y_center = (48 + 288) / 2 / 480 = 168 / 480 = 0.35
        self.assertAlmostEqual(y_center, 0.35, places=4)
        # w = (384 - 64) / 640 = 320 / 640 = 0.5
        self.assertAlmostEqual(w, 0.5, places=4)
        # h = (288 - 48) / 480 = 240 / 480 = 0.5
        self.assertAlmostEqual(h, 0.5, places=4)


class TestYoloReader(unittest.TestCase):
    """Test cases for YOLO format reader."""

    def setUp(self):
        """Create a temp directory for test inputs."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_yolo_files(self, annotations, classes, filename='test'):
        """Helper to create YOLO annotation and classes files."""
        txt_path = os.path.join(self.temp_dir, f'{filename}.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            for ann in annotations:
                f.write(f"{ann['class_idx']} {ann['x_center']} {ann['y_center']} {ann['w']} {ann['h']}\n")

        with open(classes_path, 'w') as f:
            for cls in classes:
                f.write(f"{cls}\n")

        return txt_path, classes_path

    def test_read_single_box(self):
        """Test reading a single bounding box."""
        annotations = [{'class_idx': 0, 'x_center': 0.5, 'y_center': 0.5, 'w': 0.5, 'h': 0.5}]
        txt_path, classes_path = self._create_yolo_files(annotations, ['person'])

        mock_image = MockQImage(200, 100)  # width=200, height=100
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        self.assertEqual(len(shapes), 1)
        label, points, _, _, difficult = shapes[0]

        self.assertEqual(label, 'person')
        self.assertFalse(difficult)

        # Convert normalized to pixel: center=(0.5*200, 0.5*100)=(100, 50), size=(0.5*200, 0.5*100)=(100, 50)
        # So box is from (50, 25) to (150, 75)
        x_min, y_min = points[0]
        x_max, y_max = points[2]

        self.assertEqual(x_min, 50)
        self.assertEqual(y_min, 25)
        self.assertEqual(x_max, 150)
        self.assertEqual(y_max, 75)

    def test_read_multiple_boxes(self):
        """Test reading multiple bounding boxes."""
        annotations = [
            {'class_idx': 0, 'x_center': 0.25, 'y_center': 0.25, 'w': 0.5, 'h': 0.5},
            {'class_idx': 1, 'x_center': 0.75, 'y_center': 0.75, 'w': 0.5, 'h': 0.5},
        ]
        txt_path, classes_path = self._create_yolo_files(annotations, ['cat', 'dog'])

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        self.assertEqual(len(shapes), 2)
        self.assertEqual(shapes[0][0], 'cat')
        self.assertEqual(shapes[1][0], 'dog')

    def test_coordinate_clamping(self):
        """Test that coordinates outside [0, 1] are clamped."""
        # Annotation with center that would place edges outside image
        annotations = [{'class_idx': 0, 'x_center': 0.1, 'y_center': 0.1, 'w': 0.5, 'h': 0.5}]
        txt_path, classes_path = self._create_yolo_files(annotations, ['obj'])

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        # x_min would be 0.1 - 0.25 = -0.15, should be clamped to 0
        x_min = shapes[0][1][0][0]
        y_min = shapes[0][1][0][1]

        self.assertGreaterEqual(x_min, 0)
        self.assertGreaterEqual(y_min, 0)

    def test_class_index_fallback(self):
        """Test fallback label when class index not in classes file."""
        # Only one class in file, but annotation references index 5
        annotations = [{'class_idx': 5, 'x_center': 0.5, 'y_center': 0.5, 'w': 0.2, 'h': 0.2}]
        txt_path, _ = self._create_yolo_files(annotations, ['only_one'])

        mock_image = MockQImage(100, 100)

        # This should raise an IndexError since class_idx 5 doesn't exist
        with self.assertRaises(IndexError):
            reader = YoloReader(txt_path, mock_image)

    def test_roundtrip_write_read(self):
        """Test that write/read roundtrip preserves data."""
        txt_path = os.path.join(self.temp_dir, 'roundtrip.txt')

        # Write
        writer = YOLOWriter(self.temp_dir, 'roundtrip', (100, 100, 3))
        writer.add_bnd_box(10, 20, 60, 80, 'test_class', difficult=0)
        writer.save(class_list=['test_class'], target_file=txt_path)

        # Read
        mock_image = MockQImage(100, 100)
        classes_path = os.path.join(self.temp_dir, 'classes.txt')
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        self.assertEqual(len(shapes), 1)
        self.assertEqual(shapes[0][0], 'test_class')

        # Check coordinates are close to original (may have small rounding differences)
        points = shapes[0][1]
        x_min, y_min = points[0]
        x_max, y_max = points[2]

        self.assertAlmostEqual(x_min, 10, delta=1)
        self.assertAlmostEqual(y_min, 20, delta=1)
        self.assertAlmostEqual(x_max, 60, delta=1)
        self.assertAlmostEqual(y_max, 80, delta=1)


if __name__ == '__main__':
    unittest.main()
