# tests/formats/test_coco_io.py
"""Tests for COCO JSON format I/O."""
import json
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.formats.coco_io import COCOWriter, COCOReader


class TestCOCOWriter(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.out_path = os.path.join(self.tmp_dir, 'annotations.json')

    def test_write_rectangle(self):
        writer = COCOWriter('test_folder', 'test.jpg', [480, 640, 3])
        writer.add_bnd_box(10, 20, 100, 200, 'cat', False)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        self.assertEqual(len(data['annotations']), 1)
        ann = data['annotations'][0]
        self.assertEqual(ann['bbox'], [10, 20, 90, 180])
        self.assertNotIn('segmentation', ann)

    def test_write_polygon(self):
        writer = COCOWriter('test_folder', 'test.jpg', [480, 640, 3])
        points = [(10, 20), (50, 20), (50, 80), (30, 90), (10, 60)]
        writer.add_polygon(points, 'dog', False)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        ann = data['annotations'][0]
        self.assertEqual(ann['segmentation'], [[10, 20, 50, 20, 50, 80, 30, 90, 10, 60]])
        self.assertEqual(ann['bbox'], [10, 20, 40, 70])

    def test_write_mixed_shapes(self):
        writer = COCOWriter('test_folder', 'test.jpg', [480, 640, 3])
        writer.add_bnd_box(0, 0, 50, 50, 'cat', False)
        writer.add_polygon([(10, 10), (40, 10), (25, 40)], 'dog', False)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        self.assertEqual(len(data['annotations']), 2)
        self.assertEqual(len(data['categories']), 2)

    def test_categories_unique(self):
        writer = COCOWriter('test_folder', 'test.jpg', [480, 640, 3])
        writer.add_bnd_box(0, 0, 50, 50, 'cat', False)
        writer.add_bnd_box(10, 10, 60, 60, 'cat', False)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        self.assertEqual(len(data['categories']), 1)


class TestCOCOReader(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def test_read_rectangle(self):
        data = {
            'images': [{'id': 1, 'file_name': 'test.jpg', 'width': 640, 'height': 480}],
            'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1,
                             'bbox': [10, 20, 90, 180], 'iscrowd': 0}],
            'categories': [{'id': 1, 'name': 'cat'}]
        }
        path = os.path.join(self.tmp_dir, 'annotations.json')
        with open(path, 'w') as f:
            json.dump(data, f)

        reader = COCOReader(path, 'test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        label, points, _, _, difficult, shape_type, _ = shapes[0]
        self.assertEqual(label, 'cat')
        self.assertEqual(shape_type, 'rectangle')

    def test_read_polygon(self):
        data = {
            'images': [{'id': 1, 'file_name': 'test.jpg', 'width': 640, 'height': 480}],
            'annotations': [{'id': 1, 'image_id': 1, 'category_id': 1,
                             'segmentation': [[10, 20, 50, 20, 50, 80]],
                             'bbox': [10, 20, 40, 60], 'iscrowd': 0}],
            'categories': [{'id': 1, 'name': 'dog'}]
        }
        path = os.path.join(self.tmp_dir, 'annotations.json')
        with open(path, 'w') as f:
            json.dump(data, f)

        reader = COCOReader(path, 'test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        label, points, _, _, difficult, shape_type, _ = shapes[0]
        self.assertEqual(label, 'dog')
        self.assertEqual(shape_type, 'polygon')
        self.assertEqual(points, [(10, 20), (50, 20), (50, 80)])


class TestCOCOKeypoints(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.out_path = os.path.join(self.tmp_dir, 'annotations.json')

    def test_write_bbox_with_keypoints(self):
        writer = COCOWriter('folder', 'test.jpg', [480, 640, 3])
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)  # nose, visible
        kps[5] = (30.0, 60.0, 1)  # left shoulder, occluded
        writer.add_bnd_box(10, 20, 100, 200, 'person', False, keypoints=kps)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        ann = data['annotations'][0]
        self.assertIn('keypoints', ann)
        self.assertEqual(len(ann['keypoints']), 51)
        self.assertEqual(ann['keypoints'][0], 50.0)
        self.assertEqual(ann['keypoints'][1], 20.0)
        self.assertEqual(ann['keypoints'][2], 2)
        self.assertEqual(ann['keypoints'][3], 0)
        self.assertEqual(ann['keypoints'][4], 0)
        self.assertEqual(ann['keypoints'][5], 0)
        self.assertEqual(ann['num_keypoints'], 2)

    def test_write_bbox_without_keypoints(self):
        writer = COCOWriter('folder', 'test.jpg', [480, 640, 3])
        writer.add_bnd_box(10, 20, 100, 200, 'cat', False)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        ann = data['annotations'][0]
        self.assertNotIn('keypoints', ann)

    def test_write_person_category_with_skeleton(self):
        writer = COCOWriter('folder', 'test.jpg', [480, 640, 3])
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)
        writer.add_bnd_box(10, 20, 100, 200, 'person', False, keypoints=kps)
        writer.save(self.out_path)

        with open(self.out_path) as f:
            data = json.load(f)

        cat = data['categories'][0]
        self.assertEqual(cat['name'], 'person')
        self.assertIn('keypoints', cat)
        self.assertEqual(len(cat['keypoints']), 17)
        self.assertIn('skeleton', cat)

    def test_read_keypoints(self):
        flat_kps = [0] * 51
        flat_kps[0], flat_kps[1], flat_kps[2] = 50, 20, 2   # nose
        flat_kps[15], flat_kps[16], flat_kps[17] = 30, 60, 1  # left shoulder
        data = {
            'images': [{'id': 1, 'file_name': 'test.jpg', 'width': 640, 'height': 480}],
            'annotations': [{
                'id': 1, 'image_id': 1, 'category_id': 1,
                'bbox': [10, 20, 90, 180],
                'keypoints': flat_kps,
                'num_keypoints': 2, 'iscrowd': 0
            }],
            'categories': [{'id': 1, 'name': 'person'}]
        }
        path = os.path.join(self.tmp_dir, 'annotations.json')
        with open(path, 'w') as f:
            json.dump(data, f)

        reader = COCOReader(path, 'test.jpg')
        shapes = reader.get_shapes()
        self.assertEqual(len(shapes), 1)
        shape = shapes[0]
        self.assertEqual(len(shape), 7)
        keypoints = shape[6]
        self.assertIsNotNone(keypoints)
        self.assertEqual(keypoints[0], (50, 20, 2))
        self.assertEqual(keypoints[5], (30, 60, 1))
        self.assertIsNone(keypoints[1])

    def test_read_no_keypoints_returns_none(self):
        data = {
            'images': [{'id': 1, 'file_name': 'test.jpg', 'width': 640, 'height': 480}],
            'annotations': [{
                'id': 1, 'image_id': 1, 'category_id': 1,
                'bbox': [10, 20, 90, 180], 'iscrowd': 0
            }],
            'categories': [{'id': 1, 'name': 'cat'}]
        }
        path = os.path.join(self.tmp_dir, 'annotations.json')
        with open(path, 'w') as f:
            json.dump(data, f)

        reader = COCOReader(path, 'test.jpg')
        shapes = reader.get_shapes()
        shape = shapes[0]
        self.assertEqual(len(shape), 7)
        self.assertIsNone(shape[6])


if __name__ == '__main__':
    unittest.main()
