# tests/formats/test_yolo_seg_io.py
"""Tests for YOLO segmentation format I/O."""
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from libs.formats.yolo_seg_io import YOLOSegWriter, YOLOSegReader


class TestYOLOSegWriter(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.out_path = os.path.join(self.tmp_dir, 'test.txt')

    def test_write_polygon(self):
        writer = YOLOSegWriter('folder', 'test.jpg', [100, 200, 3])
        points = [(20, 10), (180, 10), (180, 90), (20, 90)]
        writer.add_polygon(points, 'cat', False)
        writer.save(target_file=self.out_path, class_list=['cat'])

        with open(self.out_path) as f:
            line = f.readline().strip()

        parts = line.split()
        self.assertEqual(parts[0], '0')
        self.assertEqual(len(parts), 9)  # class + 4 points * 2 coords
        self.assertAlmostEqual(float(parts[1]), 0.1, places=4)
        self.assertAlmostEqual(float(parts[2]), 0.1, places=4)

    def test_write_rectangle_as_polygon(self):
        writer = YOLOSegWriter('folder', 'test.jpg', [100, 200, 3])
        writer.add_bnd_box(0, 0, 200, 100, 'dog', False)
        writer.save(target_file=self.out_path, class_list=['dog'])

        with open(self.out_path) as f:
            line = f.readline().strip()

        parts = line.split()
        self.assertEqual(len(parts), 9)  # class + 4 points * 2 coords

    def test_existing_class_map_is_preserved_for_old_annotations(self):
        """An existing classes.txt is authoritative for the whole dataset."""
        classes_path = os.path.join(self.tmp_dir, 'classes.txt')
        old_txt_path = os.path.join(self.tmp_dir, 'old.txt')

        with open(classes_path, 'w') as f:
            f.write('zebra\ncat\n')
        with open(old_txt_path, 'w') as f:
            f.write('0 0.100000 0.100000 0.900000 0.100000 '
                    '0.500000 0.900000\n')

        writer = YOLOSegWriter('folder', 'new.jpg', [100, 100, 3])
        writer.add_polygon([(10, 10), (20, 10), (15, 20)], 'dog', False)
        writer.add_polygon([(20, 20), (30, 20), (25, 30)], 'zebra', False)
        writer.add_polygon([(30, 30), (40, 30), (35, 40)], 'dog', False)
        writer.add_polygon([(40, 40), (50, 40), (45, 50)], 'ant', False)

        # This models MainWindow's label history: it is not the dataset map and
        # may contain unused labels in a different order.
        writer.save(
            target_file=self.out_path,
            class_list=['dog', 'zebra', 'unused'],
        )

        with open(classes_path) as f:
            self.assertEqual(f.read(), 'zebra\ncat\ndog\nant\n')
        with open(self.out_path) as f:
            indices = [int(line.split()[0]) for line in f]
        self.assertEqual(indices, [2, 0, 2, 3])

        image = QImage(100, 100, QImage.Format_RGB32)
        old_reader = YOLOSegReader(old_txt_path, image, classes_path)
        new_reader = YOLOSegReader(self.out_path, image, classes_path)
        self.assertEqual([shape[0] for shape in old_reader.get_shapes()],
                         ['zebra'])
        self.assertEqual([shape[0] for shape in new_reader.get_shapes()],
                         ['dog', 'zebra', 'dog', 'ant'])


class TestYOLOSegReader(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.image = QImage(200, 100, QImage.Format_RGB32)

    def test_read_axis_aligned_rectangle(self):
        """4-point axis-aligned shapes should be detected as rectangles."""
        txt_path = os.path.join(self.tmp_dir, 'test.txt')
        classes_path = os.path.join(self.tmp_dir, 'classes.txt')
        with open(classes_path, 'w') as f:
            f.write('cat\n')
        with open(txt_path, 'w') as f:
            f.write('0 0.100000 0.100000 0.900000 0.100000 0.900000 0.900000 0.100000 0.900000\n')

        reader = YOLOSegReader(txt_path, self.image, classes_path)
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        label, points, _, _, difficult, shape_type = shapes[0]
        self.assertEqual(label, 'cat')
        self.assertEqual(shape_type, 'rectangle')
        self.assertEqual(len(points), 4)

    def test_missing_classes_file_raises_friendly_error(self):
        """A missing classes.txt must raise FileNotFoundError mentioning it,
        mirroring the plain YOLO reader (recoverable, not an opaque crash)."""
        txt_path = os.path.join(self.tmp_dir, 'noclasses.txt')
        with open(txt_path, 'w') as f:
            f.write('0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n')
        missing = os.path.join(self.tmp_dir, 'classes.txt')  # not created

        with self.assertRaises(FileNotFoundError) as ctx:
            YOLOSegReader(txt_path, self.image, missing)
        self.assertIn('classes.txt', str(ctx.exception))

    def test_malformed_tokens_are_skipped(self):
        """Non-numeric class index or coordinates must skip the line, not crash."""
        txt_path = os.path.join(self.tmp_dir, 'test.txt')
        classes_path = os.path.join(self.tmp_dir, 'classes.txt')
        with open(classes_path, 'w') as f:
            f.write('cat\n')
        with open(txt_path, 'w') as f:
            f.write('x 0.1 0.1 0.9 0.1 0.9 0.9\n')          # bad class index
            f.write('0 0.1 zz 0.9 0.1 0.9 0.9\n')           # bad coordinate
            f.write('0 0.100 0.100 0.900 0.100 0.900 0.900 0.100 0.900\n')  # valid

        reader = YOLOSegReader(txt_path, self.image, classes_path)  # must not raise
        self.assertEqual(len(reader.get_shapes()), 1)

    def test_read_non_axis_aligned_quadrilateral(self):
        """4-point non-axis-aligned shapes remain polygons."""
        txt_path = os.path.join(self.tmp_dir, 'test.txt')
        classes_path = os.path.join(self.tmp_dir, 'classes.txt')
        with open(classes_path, 'w') as f:
            f.write('cat\n')
        with open(txt_path, 'w') as f:
            # A rotated quadrilateral (not axis-aligned)
            f.write('0 0.250000 0.100000 0.900000 0.250000 0.750000 0.900000 0.100000 0.750000\n')

        reader = YOLOSegReader(txt_path, self.image, classes_path)
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        label, points, _, _, difficult, shape_type = shapes[0]
        self.assertEqual(label, 'cat')
        self.assertEqual(shape_type, 'polygon')
        self.assertEqual(len(points), 4)

    def test_read_triangle(self):
        txt_path = os.path.join(self.tmp_dir, 'test.txt')
        classes_path = os.path.join(self.tmp_dir, 'classes.txt')
        with open(classes_path, 'w') as f:
            f.write('tri\n')
        with open(txt_path, 'w') as f:
            f.write('0 0.5 0.0 1.0 1.0 0.0 1.0\n')

        reader = YOLOSegReader(txt_path, self.image, classes_path)
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        label, points, _, _, _, shape_type = shapes[0]
        self.assertEqual(shape_type, 'polygon')
        self.assertEqual(len(points), 3)


def test_writer_clamps_coords_to_unit_interval(tmp_path):
    """Vertices outside the image bounds must clamp to [0.0, 1.0]."""
    writer = YOLOSegWriter('folder', 'img.jpg', (100, 100, 3))
    # x=-5 must clamp to 0.0; x=120 must clamp to 1.0; y=200 must clamp to 1.0
    writer.add_polygon([(-5.0, 50.0), (120.0, 50.0), (50.0, 200.0)],
                       'thing',
                       difficult=False)
    out = tmp_path / 'img.txt'
    writer.save(target_file=str(out), class_list=['thing'])
    line = out.read_text().strip().split()
    coords = [float(x) for x in line[1:]]
    assert all(0.0 <= c <= 1.0 for c in coords), \
        'coords escaped [0,1]: %s' % coords
    # Sanity: first vertex (-5, 50) -> (0.0, 0.5)
    assert coords[0] == 0.0
    assert coords[1] == 0.5
    # Third vertex (50, 200) -> (0.5, 1.0)
    assert coords[4] == 0.5
    assert coords[5] == 1.0


if __name__ == '__main__':
    unittest.main()
