"""Tests for transactional Ultralytics detection dataset export."""

import json
import os

import pytest
from PyQt6.QtGui import QImage

from libs.core.dataset import DatasetSnapshot
from libs.core.task_coordinator import JobCancelled
from libs.core.ultralytics_export import (
    UltralyticsExportError, UltralyticsExportRequest,
    export_ultralytics_dataset,
)
from libs.formats.labelFile import LabelFileFormat
from libs.formats.pascal_voc_io import PascalVocWriter


class _Handle:
    def __init__(self, cancel_on_progress=False):
        self.cancelled = False
        self.cancel_on_progress = cancel_on_progress
        self.progress = []
        self.commit_started = False

    def is_cancelled(self):
        return self.cancelled

    def check_cancelled(self):
        if self.cancelled:
            raise JobCancelled()

    def report_progress(self, value):
        self.progress.append(value)
        if self.cancel_on_progress:
            self.cancelled = True

    def begin_non_cancellable(self):
        self.check_cancelled()
        self.commit_started = True


def _image(path, color=0xFFFFFFFF):
    image = QImage(100, 50, QImage.Format.Format_RGB32)
    image.fill(color)
    assert image.save(str(path))


def _voc(path, image_path, objects):
    writer = PascalVocWriter(
        os.path.basename(os.path.dirname(str(image_path))),
        os.path.basename(str(image_path)), (50, 100, 3),
        local_img_path=str(image_path))
    for shape_type, label, points in objects:
        if shape_type == 'polygon':
            writer.add_polygon(points, label, False)
        else:
            writer.add_bnd_box(*points, label, False)
    writer.save(target_file=str(path))


def _request(snapshot, destination, **overrides):
    values = {
        'destination': str(destination),
        'image_paths': snapshot.image_paths,
        'save_dir': snapshot.save_dir,
        'resolver': snapshot.resolver,
        'source_format': LabelFileFormat.PASCAL_VOC,
        'class_order': ('dog',),
        'ratios': (('train', 1.0), ('val', 0.0), ('test', 0.0)),
        'seed': 42,
        'copy_images': True,
    }
    values.update(overrides)
    return UltralyticsExportRequest(**values)


def test_exports_standard_layout_yaml_labels_and_manifest(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    first = source / 'first.png'
    second = source / 'second.png'
    third = source / 'third.png'
    for image_path in (first, second, third):
        _image(image_path)
    _voc(source / 'first.xml', first, [
        ('rectangle', 'cat', (10, 5, 50, 25)),
    ])
    _voc(source / 'second.xml', second, [
        ('polygon', 'bird', ((20, 10), (60, 10), (40, 30))),
    ])
    snapshot = DatasetSnapshot.from_images(
        (first, second, third), root_dir=source, save_dir=source)
    destination = tmp_path / 'ultralytics'
    handle = _Handle()

    result = export_ultralytics_dataset(
        _request(snapshot, destination), handle)

    assert result.destination == str(destination)
    assert result.counts_by_split == {'train': 3, 'val': 0, 'test': 0}
    assert result.class_order == ('dog', 'cat', 'bird')
    assert result.annotated_images == 2
    assert result.unannotated_images == 1
    assert result.polygon_boxes == 1
    assert handle.commit_started
    assert handle.progress[0] == (0, 3)
    assert handle.progress[-1] == (3, 3)

    for kind in ('images', 'labels'):
        for split_name in ('train', 'val', 'test'):
            assert (destination / kind / split_name).is_dir()
    assert sorted(path.name for path in (
        destination / 'images' / 'train').iterdir()) == [
            'first.png', 'second.png', 'third.png']
    assert not list(destination.rglob('classes.txt'))

    yaml_text = (destination / 'data.yaml').read_text(encoding='utf-8')
    assert 'path: .' in yaml_text
    assert 'train: images/train' in yaml_text
    assert 'val: images/val' in yaml_text
    assert 'test: images/test' in yaml_text
    assert '0: "dog"' in yaml_text
    assert '1: "cat"' in yaml_text
    assert '2: "bird"' in yaml_text
    assert (destination / 'labels' / 'train' / 'first.txt').read_text() == \
        '1 0.300000 0.300000 0.400000 0.400000\n'
    assert (destination / 'labels' / 'train' / 'second.txt').read_text() == \
        '2 0.400000 0.400000 0.400000 0.400000\n'
    assert not (destination / 'labels' / 'train' / 'third.txt').exists()

    manifest = json.loads(
        (destination / 'labelimgpp_export_manifest.json').read_text())
    assert manifest['format'] == 'ultralytics-yolo-detect'
    assert manifest['classes'] == ['dog', 'cat', 'bird']
    assert manifest['summary'] == {
        'annotated_images': 2,
        'unannotated_images': 1,
        'polygon_boxes': 1,
    }


def test_symlink_mode_and_collision_safe_names(tmp_path):
    images = []
    for directory_name, label in (('camera-a', 'cat'), ('camera-b', 'dog')):
        directory = tmp_path / directory_name
        directory.mkdir()
        image_path = directory / 'frame.png'
        _image(image_path)
        _voc(directory / 'frame.xml', image_path, [
            ('rectangle', label, (10, 5, 50, 25)),
        ])
        images.append(image_path)
    snapshot = DatasetSnapshot.from_images(images, root_dir=tmp_path)
    destination = tmp_path / 'export'

    export_ultralytics_dataset(
        _request(
            snapshot, destination, class_order=(), copy_images=False),
        _Handle())

    exported = sorted((destination / 'images' / 'train').iterdir())
    assert len(exported) == 2
    assert all(path.is_symlink() for path in exported)
    assert all(path.name.startswith('frame__') for path in exported)
    assert {path.stem for path in exported} == {
        path.stem for path in (destination / 'labels' / 'train').iterdir()
    }


@pytest.mark.parametrize('source_format', (
    LabelFileFormat.YOLO,
    LabelFileFormat.YOLO_SEG,
    LabelFileFormat.CREATE_ML,
    LabelFileFormat.COCO,
))
def test_converts_every_non_voc_source_format(tmp_path, source_format):
    source = tmp_path / 'source'
    source.mkdir()
    image_path = source / 'image.png'
    _image(image_path)
    if source_format == LabelFileFormat.YOLO:
        (source / 'classes.txt').write_text('object\n')
        (source / 'image.txt').write_text(
            '0 0.500000 0.500000 0.400000 0.400000\n')
    elif source_format == LabelFileFormat.YOLO_SEG:
        (source / 'classes.txt').write_text('object\n')
        (source / 'image.txt').write_text(
            '0 0.300000 0.300000 0.700000 0.300000 '
            '0.700000 0.700000 0.300000 0.700000\n')
    elif source_format == LabelFileFormat.CREATE_ML:
        (source / 'image.json').write_text(json.dumps([{
            'image': 'image.png',
            'annotations': [{
                'label': 'object',
                'coordinates': {
                    'x': 50, 'y': 25, 'width': 40, 'height': 20,
                },
            }],
        }]))
    else:
        (source / 'annotations.json').write_text(json.dumps({
            'images': [{
                'id': 1, 'file_name': 'image.png',
                'width': 100, 'height': 50,
            }],
            'categories': [{'id': 1, 'name': 'object'}],
            'annotations': [{
                'id': 1, 'image_id': 1, 'category_id': 1,
                'bbox': [30, 15, 40, 20], 'iscrowd': 0,
            }],
        }))
    snapshot = DatasetSnapshot.from_images((image_path,), root_dir=source)
    destination = tmp_path / 'export'

    result = export_ultralytics_dataset(
        _request(
            snapshot, destination, source_format=source_format,
            class_order=()), _Handle())

    assert result.class_order == ('object',)
    assert (destination / 'labels' / 'train' / 'image.txt').read_text() == \
        '0 0.500000 0.500000 0.400000 0.400000\n'


def test_class_order_is_independent_of_split_seed(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    images = []
    for index, label in enumerate(('zebra', 'cat', 'bird', 'dog')):
        image_path = source / ('%d.png' % index)
        _image(image_path)
        _voc(source / ('%d.xml' % index), image_path, [
            ('rectangle', label, (10, 5, 50, 25)),
        ])
        images.append(image_path)
    snapshot = DatasetSnapshot.from_images(images, root_dir=source)
    ratios = (('train', .5), ('val', .5), ('test', 0.0))

    first = export_ultralytics_dataset(
        _request(
            snapshot, tmp_path / 'one', class_order=(), ratios=ratios,
            seed=1), _Handle())
    second = export_ultralytics_dataset(
        _request(
            snapshot, tmp_path / 'two', class_order=(), ratios=ratios,
            seed=999), _Handle())

    assert first.class_order == ('zebra', 'cat', 'bird', 'dog')
    assert second.class_order == first.class_order


def test_cancel_cleans_owned_staging_and_keeps_empty_destination(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    image_path = source / 'image.png'
    _image(image_path)
    snapshot = DatasetSnapshot.from_images((image_path,), root_dir=source)
    destination = tmp_path / 'export'
    destination.mkdir()

    with pytest.raises(JobCancelled):
        export_ultralytics_dataset(
            _request(snapshot, destination),
            _Handle(cancel_on_progress=True))

    assert destination.is_dir()
    assert list(destination.iterdir()) == []
    assert not list(tmp_path.glob('.labelimgpp-ultralytics-*'))


def test_failure_is_transactional_and_nonempty_destination_is_preserved(
        tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    image_path = source / 'image.png'
    _image(image_path)
    (source / 'image.xml').write_text('<invalid>')
    snapshot = DatasetSnapshot.from_images((image_path,), root_dir=source)
    destination = tmp_path / 'export'

    with pytest.raises(UltralyticsExportError, match='could not read'):
        export_ultralytics_dataset(
            _request(snapshot, destination), _Handle())
    assert not destination.exists()
    assert not list(tmp_path.glob('.labelimgpp-ultralytics-*'))

    destination.mkdir()
    sentinel = destination / 'keep.txt'
    sentinel.write_text('preserve')
    with pytest.raises(UltralyticsExportError, match='new or empty'):
        export_ultralytics_dataset(
            _request(snapshot, destination), _Handle())
    assert sentinel.read_text() == 'preserve'
