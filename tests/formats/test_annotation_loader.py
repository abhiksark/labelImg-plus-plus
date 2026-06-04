# tests/formats/test_annotation_loader.py
"""Tests for the format-agnostic annotation loader.

The loader pulls the per-format reader glue out of MainWindow so it can be
exercised without a Qt main window. Each loader returns a
``LoadedAnnotation(shapes, verified)``; the YOLO loaders additionally honor an
``original_image_size`` so normalized coordinates convert against the source
image dimensions rather than a scaled display image.
"""
import json
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from libs.formats import annotation_loader
from libs.formats.pascal_voc_io import PascalVocWriter


class TestImageSizeAdapter(unittest.TestCase):
    """The size adapter replaces the MockImage duplicated in MainWindow."""

    def test_exposes_width_height_grayscale(self):
        adapter = annotation_loader._ImageSizeAdapter(QSize(400, 200),
                                                      grayscale=True)
        self.assertEqual(adapter.width(), 400)
        self.assertEqual(adapter.height(), 200)
        self.assertTrue(adapter.isGrayscale())

    def test_defaults_to_color(self):
        adapter = annotation_loader._ImageSizeAdapter(QSize(10, 10))
        self.assertFalse(adapter.isGrayscale())


class TestLoadPascalVoc(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def _write_voc(self, verified):
        writer = PascalVocWriter('folder', 'img.jpg', (200, 300, 3))
        writer.verified = verified
        writer.add_bnd_box(10, 20, 110, 120, 'cat', False)
        path = os.path.join(self.tmp_dir, 'img.xml')
        writer.save(target_file=path)
        return path

    def test_returns_shapes_and_unverified(self):
        loaded = annotation_loader.load_pascal_voc(self._write_voc(False))
        self.assertEqual(len(loaded.shapes), 1)
        self.assertEqual(loaded.shapes[0][0], 'cat')
        self.assertFalse(loaded.verified)

    def test_propagates_verified_flag(self):
        loaded = annotation_loader.load_pascal_voc(self._write_voc(True))
        self.assertTrue(loaded.verified)


class TestLoadYolo(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.txt_path = os.path.join(self.tmp_dir, 'img.txt')
        with open(os.path.join(self.tmp_dir, 'classes.txt'), 'w') as f:
            f.write('cat\n')
        # center (0.5, 0.5), size (0.5, 0.5) -> box spans [0.25, 0.75] in both axes.
        with open(self.txt_path, 'w') as f:
            f.write('0 0.5 0.5 0.5 0.5\n')

    def test_uses_original_image_size_over_display_image(self):
        """Normalized coords must convert against original_image_size, not the
        (possibly downscaled) display image — the dedup'd MockImage behavior."""
        tiny_display = QImage(10, 10, QImage.Format_RGB32)
        loaded = annotation_loader.load_yolo(
            self.txt_path, tiny_display,
            original_image_size=QSize(400, 200))  # width=400, height=200

        self.assertEqual(len(loaded.shapes), 1)
        label, points = loaded.shapes[0][0], loaded.shapes[0][1]
        self.assertEqual(label, 'cat')
        # x: round(400 * 0.25)=100 .. round(400 * 0.75)=300
        # y: round(200 * 0.25)=50  .. round(200 * 0.75)=150
        self.assertEqual(points[0], (100, 50))
        self.assertEqual(points[2], (300, 150))

    def test_falls_back_to_display_image_when_no_original_size(self):
        img = QImage(200, 100, QImage.Format_RGB32)  # width=200, height=100
        loaded = annotation_loader.load_yolo(self.txt_path, img,
                                             original_image_size=None)
        points = loaded.shapes[0][1]
        # x: round(200*0.25)=50 .. round(200*0.75)=150
        self.assertEqual(points[0], (50, 25))
        self.assertEqual(points[2], (150, 75))


class TestLoadYoloSeg(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.txt_path = os.path.join(self.tmp_dir, 'img.txt')
        with open(os.path.join(self.tmp_dir, 'classes.txt'), 'w') as f:
            f.write('cat\n')
        # axis-aligned rectangle in normalized coords -> read back as rectangle
        with open(self.txt_path, 'w') as f:
            f.write('0 0.25 0.25 0.75 0.25 0.75 0.75 0.25 0.75\n')

    def test_uses_original_image_size(self):
        tiny_display = QImage(10, 10, QImage.Format_RGB32)
        loaded = annotation_loader.load_yolo_seg(
            self.txt_path, tiny_display,
            original_image_size=QSize(400, 200))
        self.assertEqual(len(loaded.shapes), 1)
        self.assertEqual(loaded.shapes[0][0], 'cat')
        # First vertex (0.25, 0.25) -> (100, 50) against 400x200
        self.assertEqual(loaded.shapes[0][1][0], (100, 50))


class TestLoadCreateML(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.image_path = os.path.join(self.tmp_dir, 'img.jpg')
        self.json_path = os.path.join(self.tmp_dir, 'img.json')
        payload = [{
            'image': 'img.jpg',
            'annotations': [{
                'label': 'cat',
                'coordinates': {'x': 60, 'y': 70, 'width': 100, 'height': 100},
            }],
        }]
        with open(self.json_path, 'w') as f:
            json.dump(payload, f)

    def test_returns_shapes(self):
        loaded = annotation_loader.load_create_ml(self.json_path,
                                                  self.image_path)
        self.assertEqual(len(loaded.shapes), 1)
        self.assertEqual(loaded.shapes[0][0], 'cat')


class TestLoadCoco(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.image_path = os.path.join(self.tmp_dir, 'img.jpg')
        self.json_path = os.path.join(self.tmp_dir, 'annotations.json')
        payload = {
            'images': [{'id': 1, 'file_name': 'img.jpg',
                        'width': 200, 'height': 200}],
            'categories': [{'id': 1, 'name': 'cat'}],
            'annotations': [{
                'id': 1, 'image_id': 1, 'category_id': 1,
                'bbox': [10, 20, 100, 100], 'iscrowd': 0,
            }],
        }
        with open(self.json_path, 'w') as f:
            json.dump(payload, f)

    def test_returns_shapes_matched_by_image_basename(self):
        loaded = annotation_loader.load_coco(self.json_path, self.image_path)
        self.assertEqual(len(loaded.shapes), 1)
        self.assertEqual(loaded.shapes[0][0], 'cat')


if __name__ == '__main__':
    unittest.main()
