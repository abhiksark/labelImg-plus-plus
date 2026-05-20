"""Tests for YOLO format I/O."""
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', '..', 'libs')
sys.path.insert(0, libs_path)
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.formats.yolo_io import YOLOWriter, YoloReader


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

    def test_save_default_class_list_does_not_leak_between_writers(self):
        """save() with no class_list must not share state across instances.

        Regression: a mutable default argument (class_list=[]) is shared at
        function-definition time, so classes from one save() would bleed into
        the next, corrupting class indices in the second file's classes.txt.
        """
        first_txt = os.path.join(self.temp_dir, 'first.txt')
        first = YOLOWriter(self.temp_dir, 'first', (100, 100, 3))
        first.add_bnd_box(10, 10, 50, 50, 'cat', difficult=0)
        first.save(target_file=first_txt)  # no class_list -> default arg

        second_dir = tempfile.mkdtemp()
        try:
            second_txt = os.path.join(second_dir, 'second.txt')
            second = YOLOWriter(second_dir, 'second', (100, 100, 3))
            second.add_bnd_box(10, 10, 50, 50, 'dog', difficult=0)
            second.save(target_file=second_txt)  # no class_list -> default arg

            with open(os.path.join(second_dir, 'classes.txt')) as f:
                classes = f.read().strip().split('\n')
            # Second writer only saw 'dog'; 'cat' must not leak in.
            self.assertEqual(classes, ['dog'])
        finally:
            shutil.rmtree(second_dir, ignore_errors=True)

    def test_bnd_box_to_yolo_line_default_class_list_isolated(self):
        """bnd_box_to_yolo_line() called without class_list stays isolated."""
        writer_a = YOLOWriter(self.temp_dir, 'a', (100, 100, 3))
        idx_a, *_ = writer_a.bnd_box_to_yolo_line(
            {'xmin': 0, 'ymin': 0, 'xmax': 10, 'ymax': 10, 'name': 'cat'})
        self.assertEqual(idx_a, 0)

        writer_b = YOLOWriter(self.temp_dir, 'b', (100, 100, 3))
        idx_b, *_ = writer_b.bnd_box_to_yolo_line(
            {'xmin': 0, 'ymin': 0, 'xmax': 10, 'ymax': 10, 'name': 'dog'})
        # 'dog' is the first class this writer saw -> index 0, not 1.
        self.assertEqual(idx_b, 0)

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

    def test_class_index_out_of_range_skipped(self):
        """Test that invalid class index is skipped with warning (not crash)."""
        # Only one class in file, but annotation references index 5
        annotations = [{'class_idx': 5, 'x_center': 0.5, 'y_center': 0.5, 'w': 0.2, 'h': 0.2}]
        txt_path, _ = self._create_yolo_files(annotations, ['only_one'])

        mock_image = MockQImage(100, 100)

        # Should not raise - invalid lines are skipped gracefully
        reader = YoloReader(txt_path, mock_image)
        shapes = reader.get_shapes()
        # No valid shapes should be loaded since the only annotation was invalid
        self.assertEqual(len(shapes), 0)

    def test_malformed_line_skipped(self):
        """Test that malformed lines (wrong number of values) are skipped."""
        txt_path = os.path.join(self.temp_dir, 'malformed.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        # Write malformed annotation (only 3 values instead of 5)
        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5\n")  # Missing w and h

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        # Malformed line should be skipped
        self.assertEqual(len(shapes), 0)

    def test_mixed_valid_invalid_lines(self):
        """Test that valid lines are loaded even when some are invalid."""
        txt_path = os.path.join(self.temp_dir, 'mixed.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5 0.2 0.2\n")  # Valid
            f.write("5 0.5 0.5 0.2 0.2\n")  # Invalid class index
            f.write("0 0.3 0.3\n")           # Malformed
            f.write("0 0.7 0.7 0.2 0.2\n")  # Valid

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        # Only 2 valid lines should be loaded
        self.assertEqual(len(shapes), 2)

    def test_empty_lines_skipped(self):
        """Test that empty lines are skipped gracefully."""
        txt_path = os.path.join(self.temp_dir, 'empty_lines.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("\n")                    # Empty line
            f.write("0 0.5 0.5 0.2 0.2\n")  # Valid
            f.write("   \n")                 # Whitespace only
            f.write("0 0.7 0.7 0.2 0.2\n")  # Valid

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        # Both valid lines should be loaded
        self.assertEqual(len(shapes), 2)

    def test_negative_class_index_skipped(self):
        """Test that negative class indices are skipped."""
        txt_path = os.path.join(self.temp_dir, 'negative.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("-1 0.5 0.5 0.2 0.2\n")  # Negative index

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        shapes = reader.get_shapes()

        # Negative index should be skipped
        self.assertEqual(len(shapes), 0)

    def test_non_numeric_class_skipped(self):
        """A 5-token line whose class index is not an integer is skipped."""
        txt_path = os.path.join(self.temp_dir, 'non_numeric_class.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("foo 0.5 0.5 0.2 0.2\n")  # class token is not an int

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        # Must not raise ValueError - non-numeric lines are skipped.
        reader = YoloReader(txt_path, mock_image, classes_path)
        self.assertEqual(len(reader.get_shapes()), 0)

    def test_non_numeric_coordinate_skipped(self):
        """A 5-token line with a non-numeric coordinate is skipped."""
        txt_path = os.path.join(self.temp_dir, 'non_numeric_coord.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("0 abc 0.5 0.2 0.2\n")  # x_center is not a float

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        # Must not raise ValueError - non-numeric lines are skipped.
        reader = YoloReader(txt_path, mock_image, classes_path)
        self.assertEqual(len(reader.get_shapes()), 0)

    def test_valid_lines_loaded_despite_non_numeric_line(self):
        """Valid lines still load when another line has non-numeric tokens."""
        txt_path = os.path.join(self.temp_dir, 'mixed_non_numeric.txt')
        classes_path = os.path.join(self.temp_dir, 'classes.txt')

        with open(txt_path, 'w') as f:
            f.write("0 0.5 0.5 0.2 0.2\n")    # Valid
            f.write("foo 0.5 0.5 0.2 0.2\n")  # Non-numeric class
            f.write("0 abc 0.5 0.2 0.2\n")    # Non-numeric coordinate
            f.write("0 0.7 0.7 0.2 0.2\n")    # Valid

        with open(classes_path, 'w') as f:
            f.write("person\n")

        mock_image = MockQImage(100, 100)
        reader = YoloReader(txt_path, mock_image, classes_path)
        self.assertEqual(len(reader.get_shapes()), 2)

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
