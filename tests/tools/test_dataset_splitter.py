# tests/tools/test_dataset_splitter.py
"""Tests for dataset splitting and its data-safety guarantees."""

import json
import os
import sys
import tempfile
import shutil
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.tools.dataset_splitter import execute_split, split_dataset


def _touch(path, content='x'):
    with open(path, 'w') as f:
        f.write(content)


class TestExecuteSplitDataSafety(unittest.TestCase):

    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.out = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)
        shutil.rmtree(self.out, ignore_errors=True)

    def _yolo_image(self, name):
        img = os.path.join(self.src, name + '.jpg')
        _touch(img)
        _touch(os.path.join(self.src, name + '.txt'), '0 0.5 0.5 0.2 0.2\n')
        return img

    def test_classes_txt_copied_for_yolo_splits(self):
        """classes.txt must be copied into each split dir so YOLO labels decode."""
        imgs = [self._yolo_image('a'), self._yolo_image('b')]
        _touch(os.path.join(self.src, 'classes.txt'), 'cat\ndog\n')
        splits = {'train': [imgs[0]], 'val': [imgs[1]], 'test': []}

        execute_split(splits, self.out, save_dir=self.src, copy=True)

        self.assertTrue(os.path.isfile(os.path.join(self.out, 'train', 'classes.txt')))
        self.assertTrue(os.path.isfile(os.path.join(self.out, 'val', 'classes.txt')))

    def test_existing_destination_not_overwritten(self):
        """A pre-existing destination file must not be clobbered."""
        img = self._yolo_image('a')
        os.makedirs(os.path.join(self.out, 'train'))
        existing = os.path.join(self.out, 'train', 'a.jpg')
        _touch(existing, 'ORIGINAL')

        execute_split({'train': [img], 'val': [], 'test': []},
                      self.out, save_dir=self.src, copy=True)

        with open(existing) as f:
            self.assertEqual(f.read(), 'ORIGINAL')  # untouched

    def test_symlink_to_existing_destination_does_not_crash(self):
        """Symlink mode with an existing destination must not raise FileExistsError."""
        img = self._yolo_image('a')
        os.makedirs(os.path.join(self.out, 'train'))
        _touch(os.path.join(self.out, 'train', 'a.jpg'), 'ORIGINAL')

        # Must not raise.
        execute_split({'train': [img], 'val': [], 'test': []},
                      self.out, save_dir=self.src, copy=False)

    def test_partial_failure_is_recorded_not_raised(self):
        """A missing source file must be recorded, not crash the whole split."""
        good = self._yolo_image('good')
        missing = os.path.join(self.src, 'gone.jpg')  # never created

        manifest_path = execute_split(
            {'train': [missing, good], 'val': [], 'test': []},
            self.out, save_dir=self.src, copy=True)

        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path) as f:
            manifest = json.load(f)
        self.assertTrue(manifest.get('errors'))  # the missing file is recorded
        # The good file still made it through.
        self.assertTrue(os.path.isfile(os.path.join(self.out, 'train', 'good.jpg')))


class TestSplitRatios(unittest.TestCase):

    def test_rejects_ratios_that_do_not_sum_to_one(self):
        """split_dataset must reject ratios that don't sum to 1.0."""
        with self.assertRaises(ValueError):
            split_dataset(['a.jpg', 'b.jpg'],
                          {'train': 0.8, 'val': 0.8, 'test': 0.0})

    def test_accepts_valid_ratios(self):
        out = split_dataset(['a', 'b', 'c', 'd'],
                            {'train': 0.5, 'val': 0.25, 'test': 0.25})
        self.assertEqual(sum(len(v) for v in out.values()), 4)


if __name__ == '__main__':
    unittest.main()
