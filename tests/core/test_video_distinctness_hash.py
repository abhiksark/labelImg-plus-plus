# tests/core/test_video_distinctness_hash.py
"""Tests for the perceptual hash half of the distinctness pass.

Split out from test_video_distinctness.py: a module-level
``pytest.importorskip('numpy')`` skips the *entire* module on collection, so
keeping these in the same file as the stdlib-only geometry tests would skip
those 8 tests too whenever numpy is absent (e.g. the base ``test`` CI job).
"""
import unittest

import pytest

np = pytest.importorskip('numpy')

from libs.core.video_distinctness import dhash, hamming  # noqa: E402


class TestPerceptualHash(unittest.TestCase):

    @staticmethod
    def _gradient(offset=0):
        rows = np.arange(64, dtype=np.int64).reshape(64, 1)
        cols = np.arange(64, dtype=np.int64).reshape(1, 64)
        return ((rows + cols + offset) % 256).astype(np.uint8)

    def test_identical_images_hash_identically(self):
        image = self._gradient()
        self.assertEqual(hamming(dhash(image), dhash(image.copy())), 0)

    def test_hash_is_64_bit(self):
        self.assertLess(dhash(self._gradient()), 1 << 64)

    def test_unrelated_images_differ(self):
        left = np.zeros((64, 64), dtype=np.uint8)
        right = self._gradient()
        self.assertGreater(hamming(dhash(left), dhash(right)), 4)

    def test_colour_images_are_accepted(self):
        colour = np.dstack([self._gradient()] * 3)
        self.assertEqual(hamming(dhash(colour), dhash(self._gradient())), 0)

    def test_hamming_counts_differing_bits(self):
        self.assertEqual(hamming(0b1011, 0b1000), 2)
        self.assertEqual(hamming(0, 0), 0)


if __name__ == '__main__':
    unittest.main()
