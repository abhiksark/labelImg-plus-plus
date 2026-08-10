import os
import json

from PyQt5.QtGui import QImage

from libs.core.dataset import DatasetSnapshot
from libs.core.image_pipeline import FrameCache, load_image_result
from libs.formats.labelFile import LabelFileFormat


def _image(path, width=32, height=24):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(path)


def test_load_result_contains_worker_safe_data_and_raw_annotations(tmp_path):
    image_path = str(tmp_path / 'image.png')
    _image(image_path)
    (tmp_path / 'image.xml').write_text(
        '<annotation verified="yes"><filename>image.png</filename>'
        '<size><width>32</width><height>24</height><depth>3</depth></size>'
        '<object><name>cat</name><difficult>0</difficult><bndbox>'
        '<xmin>1</xmin><ymin>2</ymin><xmax>10</xmax><ymax>12</ymax>'
        '</bndbox></object></annotation>')
    snapshot = DatasetSnapshot.from_images(
        [image_path], root_dir=str(tmp_path), save_dir=str(tmp_path))

    result = load_image_result(
        image_path, resolver=snapshot.resolver,
        image_list=snapshot.image_paths, save_dir=str(tmp_path),
        label_file_format=LabelFileFormat.PASCAL_VOC)

    assert not result.image.isNull()
    assert (result.original_width, result.original_height) == (32, 24)
    assert result.verified is True
    assert result.shapes[0][0] == 'cat'


def test_frame_cache_obeys_count_and_byte_caps(tmp_path):
    paths = []
    results = []
    for index in range(7):
        path = str(tmp_path / ('image-%d.png' % index))
        _image(path, width=128, height=128)
        paths.append(path)
        results.append(load_image_result(path))
    one_size = results[0].byte_size
    cache = FrameCache(max_images=5, max_bytes=one_size * 3)

    for result in results:
        cache.put(result)

    assert len(cache) == 3
    assert cache.byte_size <= one_size * 3
    assert cache.get(paths[-1]) is not None
    assert cache.get(paths[0]) is None


def test_frame_cache_invalidates_image_and_annotation_fingerprints(tmp_path):
    image_path = str(tmp_path / 'image.png')
    annotation_path = tmp_path / 'image.xml'
    _image(image_path)
    annotation_path.write_text(
        '<annotation><filename>image.png</filename><size><width>32</width>'
        '<height>24</height><depth>3</depth></size></annotation>')
    result = load_image_result(image_path, save_dir=str(tmp_path))
    cache = FrameCache()
    cache.put(result)
    assert cache.get(image_path) is result

    annotation_path.write_text(annotation_path.read_text() + ' ')
    stat = annotation_path.stat()
    os.utime(annotation_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))
    assert cache.get(image_path) is None


def test_frame_cache_invalidates_when_missing_annotation_appears(tmp_path):
    image_path = str(tmp_path / 'image.png')
    _image(image_path)
    result = load_image_result(image_path, save_dir=str(tmp_path))
    cache = FrameCache()
    cache.put(result)
    assert cache.get(image_path) is result

    (tmp_path / 'image.xml').write_text('<annotation/>')
    stat = tmp_path.stat()
    os.utime(tmp_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1))

    assert cache.get(image_path) is None


def test_load_result_reads_shared_coco_document(tmp_path):
    image_path = str(tmp_path / 'image.png')
    _image(image_path)
    (tmp_path / 'annotations.json').write_text(json.dumps({
        'images': [{
            'id': 1, 'file_name': 'image.png',
            'width': 32, 'height': 24,
        }],
        'annotations': [{
            'id': 1, 'image_id': 1, 'category_id': 1,
            'bbox': [1, 2, 9, 10],
        }],
        'categories': [{'id': 1, 'name': 'cat'}],
    }))
    snapshot = DatasetSnapshot.from_images(
        [image_path], root_dir=str(tmp_path), save_dir=str(tmp_path))

    result = load_image_result(
        image_path, resolver=snapshot.resolver,
        image_list=snapshot.image_paths, save_dir=str(tmp_path),
        label_file_format=LabelFileFormat.COCO)

    assert result.annotation_path.endswith('annotations.json')
    assert result.annotation_format == LabelFileFormat.COCO
    assert result.shapes[0][0] == 'cat'
