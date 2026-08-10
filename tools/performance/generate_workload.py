#!/usr/bin/env python3
"""Generate deterministic local performance corpora without extra packages."""

import argparse
import json
import os
import sys

from PyQt5.QtCore import QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QImage

REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from libs.core.dataset import AnnotationResolver  # noqa: E402


def _jpeg_bytes(width=64, height=64):
    image = QImage(width, height, QImage.Format_RGB32)
    image.fill(0xFF557799)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, 'JPEG', 85):
        raise RuntimeError('Qt JPEG encoder is unavailable')
    buffer.close()
    return bytes(data)


JPEG = _jpeg_bytes()


def _write(path, data, binary=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = 'wb' if binary else 'w'
    with open(path, mode) as output:
        output.write(data)


def _voc(name, verified, populated):
    objects = ''
    if populated:
        objects = (
            '<object><name>object</name><difficult>0</difficult>'
            '<bndbox><xmin>0</xmin><ymin>0</ymin>'
            '<xmax>1</xmax><ymax>1</ymax></bndbox></object>')
    verified_attr = ' verified="yes"' if verified else ''
    return (
        f'<annotation{verified_attr}><filename>{name}</filename>'
        '<size><width>1</width><height>1</height><depth>3</depth></size>'
        f'{objects}</annotation>')


def generate(root, count):
    yolo_root = os.path.join(root, 'yolo')
    yolo_labels = os.path.join(yolo_root, 'labels')
    _write(os.path.join(yolo_labels, 'classes.txt'), 'object\n')
    image_records = []
    for index in range(count):
        # Every 20-image block contains a same-stem pair in separate dirs.
        if index % 20 in (0, 10):
            relative = os.path.join(
                'images', 'camera-%s' % ('a' if index % 20 == 0 else 'b'),
                'shared-%04d.jpg' % (index // 20))
        else:
            relative = os.path.join('images', 'image-%05d.jpg' % index)
        image_path = os.path.join(yolo_root, relative)
        _write(image_path, JPEG, binary=True)
        image_records.append((index, image_path))

    resolver = AnnotationResolver(
        [path for _index, path in image_records], yolo_labels)
    for index, image_path in image_records:
        label_path = resolver.output_base(image_path) + '.txt'
        if index % 3 == 1:
            _write(label_path, '')
        elif index % 3 == 2:
            _write(label_path, '0 0.5 0.5 0.5 0.5\n')

    voc_root = os.path.join(root, 'voc')
    for index in range(count):
        name = 'image-%05d.jpg' % index
        _write(os.path.join(voc_root, name), JPEG, binary=True)
        if index % 3:
            _write(
                os.path.join(voc_root, 'image-%05d.xml' % index),
                _voc(name, verified=bool(index % 2), populated=True))

    coco_root = os.path.join(root, 'coco')
    coco_images = []
    coco_annotations = []
    for index in range(count):
        name = 'image-%05d.jpg' % index
        _write(os.path.join(coco_root, name), JPEG, binary=True)
        coco_images.append({
            'id': index + 1, 'file_name': name, 'width': 1, 'height': 1})
        if index % 3:
            coco_annotations.append({
                'id': index + 1, 'image_id': index + 1,
                'category_id': 1, 'bbox': [0, 0, 1, 1]})
    _write(os.path.join(coco_root, 'annotations.json'), json.dumps({
        'images': coco_images,
        'annotations': coco_annotations,
        'categories': [{'id': 1, 'name': 'object'}],
    }, separators=(',', ':')))

    compatibility = os.path.join(root, 'compatibility')
    create_ml = []
    for index in range(min(count, 500)):
        name = 'compat-%04d.jpg' % index
        _write(os.path.join(compatibility, name), JPEG, binary=True)
        create_ml.append({
            'image': name,
            'verified': bool(index % 2),
            'annotations': [{
                'label': 'object',
                'coordinates': {'x': .5, 'y': .5,
                                'width': 1, 'height': 1},
            }],
        })
        _write(
            os.path.join(compatibility, 'compat-%04d.txt' % index),
            '0 0 0 1 0 1 1 0 1\n')
    _write(os.path.join(compatibility, 'annotations.json'),
           json.dumps(create_ml, separators=(',', ':')))

    navigation = os.path.join(root, 'navigation')
    navigation_sizes = ((3840, 2160), (7680, 4320))
    for width, height in navigation_sizes:
        path = os.path.join(navigation, '%dx%d.jpg' % (width, height))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(0xFF334455)
        if not image.save(path, 'JPEG', 85):
            raise RuntimeError('failed to write %s' % path)

    canvas_root = os.path.join(root, 'canvas-stress')
    canvas_image = os.path.join(canvas_root, 'stress.jpg')
    _write(canvas_image, _jpeg_bytes(2048, 2048), binary=True)
    canvas_annotations = []
    for index in range(200):
        x = (index * 37) % 1900
        y = (index * 53) % 1900
        annotation = {
            'id': index + 1,
            'image_id': 1,
            'category_id': 1,
            'bbox': [x, y, 96, 72],
        }
        if index < 50:
            annotation['keypoints'] = [x + 20, y + 20, 2,
                                       x + 60, y + 45, 2]
            annotation['num_keypoints'] = 2
        canvas_annotations.append(annotation)
    for index in range(50):
        x = (index * 71) % 1850
        y = (index * 89) % 1850
        canvas_annotations.append({
            'id': 201 + index,
            'image_id': 1,
            'category_id': 1,
            'bbox': [x, y, 120, 100],
            'segmentation': [[x, y, x + 120, y + 10,
                              x + 95, y + 100, x + 15, y + 85]],
        })
    _write(os.path.join(canvas_root, 'annotations.json'), json.dumps({
        'images': [{
            'id': 1, 'file_name': 'stress.jpg',
            'width': 2048, 'height': 2048,
        }],
        'annotations': canvas_annotations,
        'categories': [{
            'id': 1, 'name': 'object',
            'keypoints': ['left', 'right'], 'skeleton': [[1, 2]],
        }],
    }, separators=(',', ':')))

    _write(os.path.join(root, 'manifest.json'), json.dumps({
        'count_per_primary_format': count,
        'seed': 0,
        'corpora': [
            'yolo', 'voc', 'coco', 'compatibility',
            'navigation', 'canvas-stress',
        ],
    }, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--count', type=int, default=10_000)
    args = parser.parse_args()
    generate(os.path.abspath(args.output), args.count)


if __name__ == '__main__':
    main()
