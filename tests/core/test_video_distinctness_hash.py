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

    def test_colour_channels_are_averaged_not_picked(self):
        """Would pass with a correct mean(axis=2); would fail if _greyscale
        took a single channel instead.

        ``_gradient`` is unsuitable here: it is monotonic along both axes,
        so any per-channel shift of it (as in a prior, weaker version of this
        test) still hashes to the degenerate all-ones value, and so does
        their mean -- the assertion would pass even for a "pick channel 0"
        bug. These three rows are built so no pair of channels cancels in
        the mean and every channel's own left/right comparison pattern
        differs from the mean's in at least one column, by construction
        rather than by chance: verified against a deliberately buggy
        "always take channel 0" greyscale, which this test does catch.
        """
        row_r = [0, 100, 0, 100, 0, 100, 0, 100, 0]
        row_g = [255, 255, 0, 0, 255, 255, 0, 0, 255]
        row_b = [130, 30, 230, 130, 30, 230, 130, 30, 230]
        r = np.array([row_r] * 8, dtype=np.uint8)
        g = np.array([row_g] * 8, dtype=np.uint8)
        b = np.array([row_b] * 8, dtype=np.uint8)
        colour = np.dstack([r, g, b])
        expected = dhash(colour.astype(np.float64).mean(axis=2))
        self.assertEqual(dhash(colour), expected)
        for channel in (r, g, b):
            self.assertNotEqual(dhash(colour), dhash(channel))

    def test_hash_bit_pattern_matches_hand_computed_value(self):
        """Pins one exact 64-bit value, derived independently of dhash, so
        the packing order (first comparison -> most significant bit) is
        checked directly rather than only through self-consistency.

        An 8x9 image resizes to itself (no interpolation), so every pixel is
        known. Each row is the same alternating [50, 150, 50, 150, ...]:
        that gives the 8 within-row comparisons True,False,True,False,...
        (150 > 50, 50 > 150, ...), i.e. bits "1,0,1,0,1,0,1,0". Repeated
        identically for all 8 rows and packed MSB-first, per row, gives the
        64-bit string "10101010" x 8, independent of calling dhash's own
        packing loop to produce it.
        """
        row = [50, 150, 50, 150, 50, 150, 50, 150, 50]
        image = np.array([row] * 8, dtype=np.uint8)
        expected = int('10101010' * 8, 2)
        self.assertEqual(dhash(image), expected)

    def test_hamming_counts_differing_bits(self):
        self.assertEqual(hamming(0b1011, 0b1000), 2)
        self.assertEqual(hamming(0, 0), 0)


if __name__ == '__main__':
    unittest.main()
