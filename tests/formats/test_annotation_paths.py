"""Tests for deterministic annotation sidecar path resolution."""
import os
import shutil
import tempfile
import unittest

from libs.formats.annotation_paths import (
    annotation_output_stem,
    annotation_stem_candidates,
    image_specific_annotation_stem,
    legacy_annotation_stem,
    normalized_image_identity,
)


class TestAnnotationPaths(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.save_dir = os.path.join(self.root, 'labels')
        os.makedirs(self.save_dir)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _image_path(self, directory, filename='frame.jpg'):
        path = os.path.join(self.root, directory, filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as image_file:
            image_file.write(b'image')
        return path

    def test_normalized_identity_and_specific_stem_are_deterministic(self):
        image = self._image_path('a')
        alternate_spelling = os.path.join(
            self.root, 'a', '..', 'a', '.', 'frame.jpg')

        self.assertEqual(
            normalized_image_identity(image),
            normalized_image_identity(alternate_spelling),
        )
        self.assertEqual(
            image_specific_annotation_stem(image, [image]),
            image_specific_annotation_stem(alternate_spelling, [image]),
        )

    def test_all_same_stem_images_receive_distinct_specific_stems(self):
        first = self._image_path('a', 'frame.jpg')
        second = self._image_path('b', 'FRAME.png')
        images = [first, second]

        first_stem = annotation_output_stem(first, self.save_dir, images)
        second_stem = annotation_output_stem(second, self.save_dir, images)

        self.assertNotEqual(first_stem.casefold(), 'frame')
        self.assertNotEqual(second_stem.casefold(), 'frame')
        self.assertNotEqual(first_stem.casefold(), second_stem.casefold())

    def test_specific_stem_is_sticky_after_active_collision_disappears(self):
        first = self._image_path('a')
        second = self._image_path('b')
        collision_stem = annotation_output_stem(
            first, self.save_dir, [first, second])
        with open(os.path.join(self.save_dir, collision_stem + '.xml'), 'w'):
            pass

        self.assertEqual(
            annotation_output_stem(first, self.save_dir, [first]),
            collision_stem,
        )

    def test_noncolliding_image_retains_legacy_stem(self):
        image = self._image_path('unique', 'photo.jpg')

        self.assertEqual(legacy_annotation_stem(image), 'photo')
        self.assertEqual(
            annotation_output_stem(image, self.save_dir, [image]),
            'photo',
        )

    def test_specific_candidates_precede_legacy_fallback(self):
        first = self._image_path('a')
        second = self._image_path('b')
        candidates = annotation_stem_candidates(first, [first, second])

        self.assertEqual(candidates[-1], 'frame')
        self.assertNotEqual(candidates[0].casefold(), 'frame')

    def test_specific_stem_extends_digest_when_active_stem_would_collide(self):
        first = self._image_path('a')
        second = self._image_path('b')
        short_specific = image_specific_annotation_stem(first, [first])
        blocker = self._image_path('blocker', short_specific + '.png')

        guarded = image_specific_annotation_stem(
            first, [first, second, blocker])

        self.assertNotEqual(guarded.casefold(), short_specific.casefold())
        self.assertTrue(guarded.startswith('frame__'))


if __name__ == '__main__':
    unittest.main()
