#!/usr/bin/env python3
"""Generate deterministic local performance corpora without extra packages."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction

from PyQt5.QtCore import QByteArray, QBuffer, QIODevice
from PyQt5.QtGui import QImage

REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

from libs.core.dataset import AnnotationResolver  # noqa: E402
from libs.core.video_decoder import (  # noqa: E402
    _rotation_for_frame, _rotation_for_stream,
)


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


def _write_video(path, width, height, frames, rate=30, gop=12,
                 rotation=0, variable_rate=False, tracking=False):
    """Write deterministic optional media without importing video at boot."""
    try:
        import av
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            'video workload generation requires labelimgplusplus[video]: %s'
            % exc)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    output = av.open(path, mode='w')
    stream = output.add_stream('mpeg4', rate=rate)
    stream.width = width
    stream.height = height
    stream.pix_fmt = 'yuv420p'
    stream.gop_size = gop
    if rotation:
        stream.metadata['rotate'] = str(rotation)
    pts = 0
    for index in range(frames):
        array = np.zeros((height, width, 3), dtype=np.uint8)
        array[:, :, 0] = 28
        array[:, :, 2] = 52
        box_size = max(24, min(width, height) // 8)
        x0 = 16 + (index * max(1, width // 500)) % max(
            1, width - box_size - 16)
        y0 = max(8, height // 3)
        array[y0:y0 + box_size, x0:x0 + box_size] = (35, 35, 35)
        if tracking:
            spacing = max(4, box_size // 10)
            for y in range(y0 + spacing, y0 + box_size - 2, spacing):
                for x in range(x0 + spacing, x0 + box_size - 2, spacing):
                    array[y - 1:y + 2, x - 1:x + 2] = (240, 240, 240)
        frame = av.VideoFrame.from_ndarray(array, format='rgb24')
        frame.pts = pts
        frame.time_base = Fraction(1, rate)
        pts += (2 if variable_rate and index % 5 == 0 else 1)
        for packet in stream.encode(frame):
            output.mux(packet)
    for packet in stream.encode():
        output.mux(packet)
    output.close()
    if rotation:
        _apply_rotation_metadata(path, rotation)


def _apply_rotation_metadata(path, rotation):
    """Attach a real display matrix after PyAV creates deterministic media."""
    executable = shutil.which('ffmpeg')
    if executable is None:
        # Older FFmpeg/PyAV combinations preserve this stream metadata during
        # encode. Newer MOV muxers require a display matrix, so the smoke test
        # covers the decoder adapter independently when the CLI is absent.
        return
    file_descriptor, staged = tempfile.mkstemp(
        prefix='.labelimgpp-rotated-', suffix=os.path.splitext(path)[1],
        dir=os.path.dirname(path))
    os.close(file_descriptor)
    try:
        commands = (
            # FFmpeg before 6 converts the legacy rotate key to a display
            # matrix. Newer versions removed that compatibility path.
            [executable, '-hide_banner', '-loglevel', 'error', '-y',
             '-i', path, '-map', '0', '-c', 'copy',
             '-metadata:s:v:0', 'rotate=%s' % int(rotation), staged],
            # Current FFmpeg exposes rotation as a per-stream input override
            # and writes its display matrix through stream copy.
            [executable, '-hide_banner', '-loglevel', 'error', '-y',
             '-display_rotation:v:0', str(int(rotation)),
             '-i', path, '-map', '0', '-c', 'copy', staged],
        )
        for command in commands:
            try:
                subprocess.run(
                    command, check=True, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                continue
            if _read_video_rotation(staged) == int(rotation) % 360:
                os.replace(staged, path)
                staged = None
                return
    finally:
        if staged is not None:
            try:
                os.unlink(staged)
            except OSError:
                pass


def _read_video_rotation(path):
    try:
        import av
        container = av.open(path, mode='r')
        try:
            stream = container.streams.video[0]
            frame = next(container.decode(stream), None)
            stream_rotation = _rotation_for_stream(stream)
            if frame is None:
                return stream_rotation
            return _rotation_for_frame(frame, stream_rotation)
        finally:
            container.close()
    except (ImportError, IndexError, OSError, TypeError, ValueError):
        return 0


def generate_video_workload(root, profile='full'):
    """Generate CFR/VFR/GOP/rotation/resolution/tracking acceptance media."""
    video_root = os.path.join(root, 'video')
    if profile == 'smoke':
        specs = (
            ('cfr.mp4', 160, 90, 16, 8, 0, False, False),
            ('cfr.avi', 160, 90, 12, 6, 0, False, False),
            ('vfr.mkv', 160, 90, 16, 8, 0, True, False),
            ('long-gop.mp4', 160, 90, 16, 16, 0, False, False),
            ('rotated.mov', 90, 160, 12, 8, 90, False, False),
            ('navigation-4k.mp4', 384, 216, 6, 6, 0, False, False),
            ('navigation-8k.mkv', 768, 432, 3, 3, 0, False, False),
            ('tracking-stress.mp4', 192, 108, 24, 12, 0, False, True),
        )
    else:
        specs = (
            ('cfr.mp4', 1280, 720, 180, 12, 0, False, False),
            ('cfr.avi', 640, 360, 90, 12, 0, False, False),
            ('vfr.mkv', 960, 540, 120, 12, 0, True, False),
            ('long-gop.mp4', 1920, 1080, 180, 120, 0, False, False),
            ('rotated.mov', 720, 1280, 90, 30, 90, False, False),
            ('navigation-4k.mp4', 3840, 2160, 30, 30, 0, False, False),
            ('navigation-8k.mkv', 7680, 4320, 6, 6, 0, False, False),
            ('tracking-stress.mp4', 1280, 720, 180, 60, 0, False, True),
        )
    records = []
    for name, width, height, frames, gop, rotation, vfr, tracking in specs:
        path = os.path.join(video_root, name)
        _write_video(
            path, width, height, frames, gop=gop, rotation=rotation,
            variable_rate=vfr, tracking=tracking)
        records.append({
            'name': name, 'width': width, 'height': height,
            'frames': frames, 'gop': gop, 'rotation': rotation,
            'vfr': vfr, 'tracking': tracking,
        })
    switch_width, switch_height = (
        (384, 216) if profile == 'smoke' else (3840, 2160))
    switch_image = os.path.join(video_root, 'switch-image.jpg')
    image = QImage(switch_width, switch_height, QImage.Format_RGB32)
    image.fill(0xFF334455)
    if not image.save(switch_image, 'JPEG', 85):
        raise RuntimeError('failed to write %s' % switch_image)
    _write(os.path.join(video_root, 'manifest.json'), json.dumps({
        'seed': 0, 'profile': profile, 'media': records,
        'switch_image': 'switch-image.jpg',
    }, indent=2))
    return tuple(os.path.join(video_root, item['name']) for item in records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output')
    parser.add_argument('--count', type=int, default=10_000)
    parser.add_argument(
        '--video', action='store_true',
        help='also generate the optional smart-video media corpus')
    parser.add_argument(
        '--video-only', action='store_true',
        help='generate only the optional smart-video media corpus')
    parser.add_argument(
        '--video-profile', choices=('full', 'smoke'), default='full')
    args = parser.parse_args()
    if not args.video_only:
        generate(os.path.abspath(args.output), args.count)
    if args.video or args.video_only:
        generate_video_workload(
            os.path.abspath(args.output), profile=args.video_profile)


if __name__ == '__main__':
    main()
