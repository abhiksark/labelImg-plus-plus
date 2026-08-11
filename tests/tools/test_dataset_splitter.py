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

from libs.formats.annotation_paths import annotation_output_base
from libs.tools.dataset_splitter import (
    SplitCancelled,
    _place_file,
    execute_split,
    execute_split_transactional,
    split_dataset,
)


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

    def _annotated_image(self, directory, filename, annotation_extension,
                         image_content, annotation_content):
        source_dir = os.path.join(self.src, directory)
        os.makedirs(source_dir, exist_ok=True)
        image_path = os.path.join(source_dir, filename)
        image_stem = os.path.splitext(filename)[0]
        _touch(image_path, image_content)
        _touch(os.path.join(
            source_dir, image_stem + annotation_extension),
            annotation_content)
        return image_path

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

    def test_same_filename_in_subdirs_keeps_both_annotation_pairs(self):
        """Colliding basenames and their annotations get distinct flat names."""
        first = self._annotated_image(
            'camera-a', 'frame.jpg', '.xml', 'IMAGE-A', 'ANNOTATION-A')
        second = self._annotated_image(
            'camera-b', 'frame.jpg', '.xml', 'IMAGE-B', 'ANNOTATION-B')

        manifest_path = execute_split(
            {'train': [first, second], 'val': [], 'test': []},
            self.out, copy=True)

        train_dir = os.path.join(self.out, 'train')
        image_names = sorted(
            name for name in os.listdir(train_dir) if name.endswith('.jpg'))
        self.assertEqual(len(image_names), 2)
        self.assertTrue(all(name.startswith('frame__') for name in image_names))
        self.assertEqual(
            {os.path.splitext(name)[0] for name in image_names},
            {os.path.splitext(name)[0] for name in os.listdir(train_dir)
             if name.endswith('.xml')})

        expected_annotations = {
            'IMAGE-A': 'ANNOTATION-A',
            'IMAGE-B': 'ANNOTATION-B',
        }
        for image_name in image_names:
            image_path = os.path.join(train_dir, image_name)
            with open(image_path) as f:
                image_content = f.read()
            annotation_name = os.path.splitext(image_name)[0] + '.xml'
            with open(os.path.join(train_dir, annotation_name)) as f:
                self.assertEqual(
                    f.read(), expected_annotations[image_content])

        with open(manifest_path) as f:
            manifest = json.load(f)
        self.assertCountEqual(manifest['files']['train'], image_names)
        self.assertEqual(manifest['skipped'], [])
        self.assertEqual(manifest['errors'], [])

    def test_same_stem_different_extensions_and_annotations_in_symlink_mode(self):
        """Image and annotation extensions do not break pair disambiguation."""
        jpeg = self._annotated_image(
            'jpeg-source', 'sample.jpg', '.xml', 'JPEG', 'VOC')
        png = self._annotated_image(
            'png-source', 'sample.png', '.txt', 'PNG', 'YOLO')
        _touch(os.path.join(self.src, 'png-source', 'classes.txt'), 'object\n')

        manifest_path = execute_split(
            {'train': [jpeg, png], 'val': [], 'test': []},
            self.out, copy=False)

        train_dir = os.path.join(self.out, 'train')
        with open(manifest_path) as f:
            output_names = json.load(f)['files']['train']
        self.assertEqual(len(output_names), 2)

        expected_annotations = {
            'JPEG': ('.xml', 'VOC'),
            'PNG': ('.txt', 'YOLO'),
        }
        for image_name in output_names:
            image_path = os.path.join(train_dir, image_name)
            self.assertTrue(os.path.islink(image_path))
            with open(image_path) as f:
                image_content = f.read()
            annotation_extension, annotation_content = (
                expected_annotations[image_content])
            annotation_path = os.path.join(
                train_dir,
                os.path.splitext(image_name)[0] + annotation_extension)
            self.assertTrue(os.path.islink(annotation_path))
            with open(annotation_path) as f:
                self.assertEqual(f.read(), annotation_content)

        self.assertTrue(os.path.isfile(
            os.path.join(train_dir, 'classes.txt')))
        self.assertFalse(os.path.islink(
            os.path.join(train_dir, 'classes.txt')))

    def test_collision_names_are_deterministic_and_rerun_safe(self):
        """Reruns target the same names and never create suffix variants."""
        first = self._annotated_image(
            'one', 'frame.jpg', '.xml', 'IMAGE-ONE', 'ANNOTATION-ONE')
        second = self._annotated_image(
            'two', 'frame.jpg', '.xml', 'IMAGE-TWO', 'ANNOTATION-TWO')
        splits = {'train': [first, second], 'val': [], 'test': []}

        first_manifest_path = execute_split(splits, self.out, copy=True)
        with open(first_manifest_path) as f:
            first_names = json.load(f)['files']['train']

        train_dir = os.path.join(self.out, 'train')
        first_names_by_content = {}
        for name in first_names:
            with open(os.path.join(train_dir, name)) as f:
                first_names_by_content[f.read()] = name
        preserved_path = os.path.join(train_dir, first_names[0])
        _touch(preserved_path, 'PRESERVE-EXISTING')

        second_manifest_path = execute_split(splits, self.out, copy=True)
        with open(second_manifest_path) as f:
            second_manifest = json.load(f)

        with open(preserved_path) as f:
            self.assertEqual(f.read(), 'PRESERVE-EXISTING')
        self.assertEqual(second_manifest['files']['train'], [])
        self.assertCountEqual(
            [os.path.basename(path) for path in second_manifest['skipped']],
            first_names)
        self.assertCountEqual(
            [name for name in os.listdir(train_dir) if name.endswith('.jpg')],
            first_names)

        # Input ordering changes manifest ordering, but not the name selected
        # for each source identity.
        second_out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, second_out, True)
        reversed_manifest_path = execute_split(
            {'train': [second, first], 'val': [], 'test': []},
            second_out, copy=True)
        with open(reversed_manifest_path) as f:
            reversed_names = json.load(f)['files']['train']

        def names_by_content(output_dir, names):
            result = {}
            for name in names:
                with open(os.path.join(output_dir, 'train', name)) as f:
                    result[f.read()] = name
            return result

        self.assertEqual(
            first_names_by_content,
            names_by_content(second_out, reversed_names))

    def test_collision_safe_source_annotations_override_legacy_decoy(self):
        """The splitter copies each hashed source sidecar, never the decoy."""
        first_dir = os.path.join(self.src, 'camera-a')
        second_dir = os.path.join(self.src, 'camera-b')
        os.makedirs(first_dir)
        os.makedirs(second_dir)
        images = [
            os.path.join(first_dir, 'frame.jpg'),
            os.path.join(second_dir, 'frame.jpg'),
        ]
        _touch(images[0], 'IMAGE-A')
        _touch(images[1], 'IMAGE-B')
        first_xml = annotation_output_base(
            images[0], self.src, images) + '.xml'
        second_xml = annotation_output_base(
            images[1], self.src, images) + '.xml'
        _touch(first_xml, 'ANNOTATION-A')
        _touch(second_xml, 'ANNOTATION-B')
        _touch(os.path.join(self.src, 'frame.xml'), 'STALE')

        execute_split(
            {'train': [images[0]], 'val': [images[1]], 'test': []},
            self.out, save_dir=self.src, copy=True)

        for split_name, expected_image, expected_annotation in (
            ('train', 'IMAGE-A', 'ANNOTATION-A'),
            ('val', 'IMAGE-B', 'ANNOTATION-B'),
        ):
            split_dir = os.path.join(self.out, split_name)
            with open(os.path.join(split_dir, 'frame.jpg')) as f:
                self.assertEqual(f.read(), expected_image)
            with open(os.path.join(split_dir, 'frame.xml')) as f:
                self.assertEqual(f.read(), expected_annotation)

    def test_cancelled_copy_removes_partial_destination(self):
        source = os.path.join(self.src, 'large.jpg')
        with open(source, 'wb') as stream:
            stream.write(b'x' * (2 * 1024 * 1024))
        destination = os.path.join(self.out, 'large.jpg')
        calls = []

        def cancelled():
            calls.append(True)
            return len(calls) >= 2

        with self.assertRaises(SplitCancelled):
            _place_file(source, destination, copy=True, cancelled=cancelled)
        self.assertFalse(os.path.exists(destination))

    def test_transactional_cancel_does_not_publish_staging_files(self):
        image = self._yolo_image('cancelled')
        output = os.path.join(self.out, 'published')

        class Handle:
            def is_cancelled(self):
                return True

            def report_progress(self, _value):
                pass

            def begin_non_cancellable(self):
                raise AssertionError('cancelled job cannot enter commit')

        result = execute_split_transactional(
            {'train': [image], 'val': [], 'test': []},
            output, self.src, True, Handle())

        self.assertIsNone(result)
        self.assertFalse(os.path.exists(output))


class TestSplitRatios(unittest.TestCase):

    def setUp(self):
        self.src = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)

    def test_stratification_uses_collision_safe_annotations(self):
        """Same-stem images are grouped by their image-specific VOC labels."""
        from libs.formats.pascal_voc_io import PascalVocWriter

        save_dir = os.path.join(self.src, 'labels')
        os.makedirs(save_dir)
        images = []
        for directory in ('camera-a', 'camera-b'):
            image_dir = os.path.join(self.src, directory)
            os.makedirs(image_dir)
            image_path = os.path.join(image_dir, 'frame.jpg')
            _touch(image_path)
            images.append(image_path)

        def write_voc(path, label):
            writer = PascalVocWriter('f', 'frame.jpg', (50, 50, 3))
            writer.add_bnd_box(1, 1, 9, 9, label, difficult=0)
            writer.save(path)

        write_voc(
            annotation_output_base(images[0], save_dir, images) + '.xml',
            'cat')
        write_voc(
            annotation_output_base(images[1], save_dir, images) + '.xml',
            'dog')
        write_voc(os.path.join(save_dir, 'frame.xml'), 'stale')

        result = split_dataset(
            images,
            {'train': 0.5, 'val': 0.5, 'test': 0.0},
            stratified=True,
            save_dir=save_dir,
        )

        # Each image is the sole member of a distinct class group, so the
        # stratifier's minimum-one policy puts both into train. Resolving the
        # stale legacy decoy for both would instead split one into val.
        self.assertCountEqual(result['train'], images)
        self.assertEqual(result['val'], [])
        self.assertEqual(result['test'], [])

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
