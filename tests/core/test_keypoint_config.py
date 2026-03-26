# tests/core/test_keypoint_config.py
"""Tests for COCO keypoint skeleton template constants."""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.core.keypoint_config import (
    COCO_KEYPOINT_NAMES, COCO_SKELETON, COCO_KEYPOINT_COLORS,
    get_keypoint_color,
)


class TestCOCOKeypointConfig(unittest.TestCase):
    """Test COCO keypoint skeleton template constants."""

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


if __name__ == '__main__':
    unittest.main()
