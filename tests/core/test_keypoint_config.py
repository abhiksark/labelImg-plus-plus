# tests/core/test_keypoint_config.py
"""Tests for keypoint skeleton template registry."""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.core.keypoint_config import (
    COCO_KEYPOINT_NAMES, COCO_SKELETON, COCO_KEYPOINT_COLORS,
    KEYPOINT_TEMPLATES, get_keypoint_color, get_template,
)


class TestCOCOKeypointConfig(unittest.TestCase):
    """Test COCO keypoint skeleton template constants (backward compat)."""

    def test_17_keypoint_names(self):
        self.assertEqual(len(COCO_KEYPOINT_NAMES), 17)

    def test_keypoint_names_are_strings(self):
        for name in COCO_KEYPOINT_NAMES:
            self.assertIsInstance(name, str)
            self.assertTrue(len(name) > 0)

    def test_skeleton_indices_valid(self):
        for i, j in COCO_SKELETON:
            self.assertGreaterEqual(i, 0)
            self.assertLessEqual(i, 16)
            self.assertGreaterEqual(j, 0)
            self.assertLessEqual(j, 16)

    def test_skeleton_has_connections(self):
        self.assertGreaterEqual(len(COCO_SKELETON), 16)

    def test_colors_cover_all_regions(self):
        expected = {'head', 'shoulder', 'arm', 'wrist', 'hip', 'leg', 'ankle'}
        self.assertEqual(set(COCO_KEYPOINT_COLORS.keys()), expected)

    def test_get_keypoint_color_head(self):
        self.assertEqual(get_keypoint_color(0), COCO_KEYPOINT_COLORS['head'])

    def test_get_keypoint_color_ankle(self):
        self.assertEqual(get_keypoint_color(15), COCO_KEYPOINT_COLORS['ankle'])

    def test_get_keypoint_color_all_indices(self):
        for i in range(17):
            color = get_keypoint_color(i)
            self.assertTrue(color.startswith('#'))


class TestTemplateRegistry(unittest.TestCase):
    """Test the keypoint template registry."""

    def test_person_template_exists(self):
        self.assertIn('person', KEYPOINT_TEMPLATES)

    def test_face_template_exists(self):
        self.assertIn('face', KEYPOINT_TEMPLATES)

    def test_face_has_5_keypoints(self):
        face = KEYPOINT_TEMPLATES['face']
        self.assertEqual(len(face['names']), 5)

    def test_face_skeleton_indices_valid(self):
        face = KEYPOINT_TEMPLATES['face']
        for i, j in face['skeleton']:
            self.assertGreaterEqual(i, 0)
            self.assertLess(i, 5)
            self.assertGreaterEqual(j, 0)
            self.assertLess(j, 5)

    def test_face_colors_cover_all_regions(self):
        face = KEYPOINT_TEMPLATES['face']
        expected = {'eye', 'nose', 'mouth'}
        self.assertEqual(set(face['colors'].keys()), expected)

    def test_get_template_person(self):
        t = get_template('person')
        self.assertIsNotNone(t)
        self.assertEqual(len(t['names']), 17)

    def test_get_template_face(self):
        t = get_template('face')
        self.assertIsNotNone(t)
        self.assertEqual(len(t['names']), 5)

    def test_get_template_case_insensitive(self):
        self.assertIsNotNone(get_template('Person'))
        self.assertIsNotNone(get_template('FACE'))

    def test_get_template_unknown_returns_none(self):
        self.assertIsNone(get_template('car'))

    def test_get_keypoint_color_face(self):
        color = get_keypoint_color(0, 'face')
        face = KEYPOINT_TEMPLATES['face']
        self.assertEqual(color, face['colors']['eye'])

    def test_get_keypoint_color_face_nose(self):
        color = get_keypoint_color(2, 'face')
        face = KEYPOINT_TEMPLATES['face']
        self.assertEqual(color, face['colors']['nose'])

    def test_each_template_has_required_keys(self):
        for name, t in KEYPOINT_TEMPLATES.items():
            self.assertIn('names', t, f'{name} missing names')
            self.assertIn('skeleton', t, f'{name} missing skeleton')
            self.assertIn('colors', t, f'{name} missing colors')
            self.assertIn('index_to_region', t, f'{name} missing index_to_region')


if __name__ == '__main__':
    unittest.main()
