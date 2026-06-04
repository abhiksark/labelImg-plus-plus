# tests/formats/test_annotation_probe.py
"""Tests for the unified annotation probe (status + label resolution)."""
import json
import os
import sys
import tempfile
import shutil
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

from libs.formats.annotation_probe import probe
from libs.formats.pascal_voc_io import PascalVocWriter

app = QApplication.instance() or QApplication(sys.argv)


class TestAnnotationProbe(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _image(self, name='img.png', w=100, h=80, where=None):
        path = os.path.join(where or self.d, name)
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(0xFFFFFF)
        img.save(path)
        return path

    # ---- VOC ----
    def test_voc_status_and_labels(self):
        img = self._image('a.png')
        w = PascalVocWriter('f', 'a.png', (80, 100, 3))
        w.add_bnd_box(10, 10, 50, 50, 'cat', difficult=0)
        w.save(os.path.join(self.d, 'a.xml'))

        info = probe(img, save_dir=self.d, want_labels=True)
        self.assertEqual(info.fmt, 'voc')
        self.assertTrue(info.has_labels)
        self.assertIn('cat', info.labels)

    def test_voc_verified_flag(self):
        img = self._image('v.png')
        w = PascalVocWriter('f', 'v.png', (80, 100, 3))
        w.verified = True
        w.add_bnd_box(1, 1, 9, 9, 'dog', difficult=0)
        w.save(os.path.join(self.d, 'v.xml'))

        self.assertTrue(probe(img, save_dir=self.d).verified)

    # ---- YOLO ----
    def test_yolo_status_and_labels(self):
        img = self._image('y.png')
        with open(os.path.join(self.d, 'y.txt'), 'w') as f:
            f.write('0 0.5 0.5 0.2 0.2\n')
        with open(os.path.join(self.d, 'classes.txt'), 'w') as f:
            f.write('person\ncar\n')

        info = probe(img, save_dir=self.d, want_labels=True)
        self.assertEqual(info.fmt, 'yolo')
        self.assertTrue(info.has_labels)
        self.assertIn('person', info.labels)

    def test_yolo_labels_sibling_folder(self):
        # images/ and labels/ sibling structure
        images_dir = os.path.join(self.d, 'images')
        labels_dir = os.path.join(self.d, 'labels')
        os.makedirs(images_dir)
        os.makedirs(labels_dir)
        img = self._image('s.png', where=images_dir)
        with open(os.path.join(labels_dir, 's.txt'), 'w') as f:
            f.write('1 0.5 0.5 0.2 0.2\n')
        with open(os.path.join(self.d, 'classes.txt'), 'w') as f:
            f.write('person\ncar\n')

        info = probe(img, want_labels=True)  # no save_dir
        self.assertEqual(info.fmt, 'yolo')
        self.assertIn('car', info.labels)

    # ---- CreateML per-image <base>.json ----
    def test_createml_base_json_status_and_labels(self):
        """Cross-view fix: a CreateML <base>.json must report HAS_LABELS for
        the status probe AND surface its labels (previously they disagreed)."""
        img = self._image('c.png')
        with open(os.path.join(self.d, 'c.json'), 'w') as f:
            json.dump([{'image': 'c.png', 'verified': False, 'annotations': [
                {'label': 'cat',
                 'coordinates': {'x': 40, 'y': 30, 'width': 20, 'height': 20}}]}], f)

        info = probe(img, save_dir=self.d, want_labels=True)
        self.assertTrue(info.has_labels)        # status agrees ...
        self.assertIn('cat', info.labels)       # ... and labels are read

    # ---- COCO shared annotations.json ----
    def test_coco_annotations_json(self):
        img = self._image('k.png')
        coco = {
            'images': [{'id': 1, 'file_name': 'k.png', 'width': 100, 'height': 80}],
            'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1,
                             'bbox': [10, 10, 30, 30]}],
            'categories': [{'id': 1, 'name': 'boat'}],
        }
        with open(os.path.join(self.d, 'annotations.json'), 'w') as f:
            json.dump(coco, f)

        info = probe(img, save_dir=self.d, want_labels=True)
        self.assertTrue(info.has_labels)
        self.assertIn('boat', info.labels)

    # ---- resolution / precedence ----
    def test_no_annotation(self):
        img = self._image('none.png')
        info = probe(img, save_dir=self.d, want_labels=True)
        self.assertFalse(info.has_labels)
        self.assertEqual(info.labels, [])
        self.assertIsNone(info.fmt)

    def test_searches_image_dir_when_not_in_save_dir(self):
        # annotation lives next to the image, save_dir points elsewhere
        other = tempfile.mkdtemp()
        try:
            img = self._image('x.png')
            w = PascalVocWriter('f', 'x.png', (80, 100, 3))
            w.add_bnd_box(1, 1, 9, 9, 'cat', difficult=0)
            w.save(os.path.join(self.d, 'x.xml'))
            info = probe(img, save_dir=other, want_labels=True)  # not in `other`
            self.assertIn('cat', info.labels)
        finally:
            shutil.rmtree(other, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
