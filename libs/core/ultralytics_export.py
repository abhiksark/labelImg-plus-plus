"""Transactional Ultralytics YOLO detection dataset export."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
import shutil
import tempfile
import time

from libs.core.image_pipeline import load_image_result
from libs.core.task_coordinator import JobCancelled
from libs.formats.labelFile import LabelFile
from libs.formats.yolo_io import YOLOWriter
from libs.tools.dataset_splitter import (
    SplitCancelled, _build_output_names, _place_file, _source_key,
    split_dataset,
)


class UltralyticsExportError(RuntimeError):
    """Raised when a requested dataset cannot be exported safely."""


@dataclass(frozen=True)
class UltralyticsExportRequest:
    destination: str
    image_paths: tuple
    save_dir: object
    resolver: object
    source_format: object
    class_order: tuple
    ratios: tuple
    seed: int = 42
    copy_images: bool = True


@dataclass(frozen=True)
class UltralyticsExportResult:
    destination: str
    manifest_path: str
    counts: tuple
    class_order: tuple
    annotated_images: int
    unannotated_images: int
    polygon_boxes: int

    @property
    def counts_by_split(self):
        return dict(self.counts)


def _ratios(request):
    try:
        values = dict(request.ratios)
        result = {
            name: float(values.get(name, 0.0))
            for name in ('train', 'val', 'test')
        }
    except (TypeError, ValueError) as exc:
        raise UltralyticsExportError('invalid train/val/test ratios') from exc
    if any(not math.isfinite(value) or value < 0 for value in result.values()):
        raise UltralyticsExportError(
            'train/val/test ratios must be finite and non-negative')
    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise UltralyticsExportError(
            'train/val/test ratios must sum to 1.0')
    return result


def _validate_destination(destination):
    if os.path.lexists(destination):
        if os.path.islink(destination) or not os.path.isdir(destination):
            raise UltralyticsExportError(
                'export destination must be a new or empty directory')
        if os.listdir(destination):
            raise UltralyticsExportError(
                'export destination must be a new or empty directory')


def _stable_classes(values):
    result = []
    for value in values:
        label = str(value)
        if not label:
            continue
        if label not in result:
            result.append(label)
    return result


def _shape_values(shape, image_path):
    if len(shape) == 7:
        label, points, _line, _fill, difficult, shape_type, _keypoints = shape
    elif len(shape) == 6:
        label, points, _line, _fill, difficult, shape_type = shape
    elif len(shape) == 5:
        label, points, _line, _fill, difficult = shape
        shape_type = 'rectangle'
    else:
        raise UltralyticsExportError(
            'unsupported shape payload in %s' % image_path)

    label = str(label)
    if not label:
        raise UltralyticsExportError(
            'annotation with an empty class name in %s' % image_path)
    try:
        normalized_points = tuple(
            (float(point[0]), float(point[1])) for point in points)
    except (IndexError, TypeError, ValueError) as exc:
        raise UltralyticsExportError(
            'invalid annotation geometry in %s' % image_path) from exc
    if not normalized_points or any(
            not math.isfinite(value)
            for point in normalized_points for value in point):
        raise UltralyticsExportError(
            'invalid annotation geometry in %s' % image_path)
    return label, normalized_points, bool(difficult), str(shape_type)


def _write_yolo_label(path, image_path, width, height, shapes, classes):
    writer = YOLOWriter(
        os.path.basename(os.path.dirname(image_path)),
        os.path.basename(image_path),
        [height, width, 3], local_img_path=image_path)
    polygon_boxes = 0
    for shape in shapes:
        label, points, difficult, shape_type = _shape_values(
            shape, image_path)
        if label not in classes:
            classes.append(label)
        x_min, y_min, x_max, y_max = LabelFile.convert_points_to_bnd_box(
            points)
        if x_max <= x_min or y_max <= y_min:
            raise UltralyticsExportError(
                'zero-area annotation for class %s in %s'
                % (label, image_path))
        writer.add_bnd_box(
            x_min, y_min, x_max, y_max, label, int(difficult))
        if shape_type == 'polygon':
            polygon_boxes += 1
    writer.save(
        target_file=path, class_list=classes, write_classes_file=False)
    return polygon_boxes


def _write_data_yaml(path, classes):
    lines = [
        'path: .',
        'train: images/train',
        'val: images/val',
        'test: images/test',
        'names:',
    ]
    if classes:
        lines.extend(
            '  %d: %s' % (index, json.dumps(label, ensure_ascii=False))
            for index, label in enumerate(classes))
    else:
        lines[-1] = 'names: {}'
    with open(path, 'w', encoding='utf-8', newline='\n') as output:
        output.write('\n'.join(lines) + '\n')


def export_ultralytics_dataset(request, handle):
    """Build and atomically publish one Ultralytics detection dataset."""
    destination = os.path.abspath(os.fspath(request.destination))
    if not request.image_paths:
        raise UltralyticsExportError('no images were selected for export')
    _validate_destination(destination)
    ratios = _ratios(request)
    parent = os.path.dirname(destination) or os.curdir
    os.makedirs(parent, exist_ok=True)
    staging = tempfile.mkdtemp(
        prefix='.labelimgpp-ultralytics-', dir=parent)
    published = False
    try:
        splits = split_dataset(
            request.image_paths, ratios, seed=int(request.seed),
            stratified=False, save_dir=request.save_dir,
            resolver=request.resolver)
        for split_name in ('train', 'val', 'test'):
            os.makedirs(os.path.join(staging, 'images', split_name))
            os.makedirs(os.path.join(staging, 'labels', split_name))

        classes = _stable_classes(request.class_order)
        manifest = {
            'schema_version': 1,
            'format': 'ultralytics-yolo-detect',
            'created_utc': datetime.now(timezone.utc).isoformat(),
            'image_mode': 'copy' if request.copy_images else 'symlink',
            'seed': int(request.seed),
            'ratios': ratios,
            'splits': {
                name: [] for name in ('train', 'val', 'test')
            },
        }
        split_by_source = {}
        output_names = {}
        for split_name in ('train', 'val', 'test'):
            split_names = _build_output_names(splits[split_name])
            for image_path in splits[split_name]:
                source_key = _source_key(image_path)
                split_by_source[source_key] = split_name
                output_names[source_key] = split_names[source_key]
        total = len(request.image_paths)
        processed = 0
        annotated = 0
        unannotated = 0
        polygon_boxes = 0
        last_progress = 0.0

        def report_progress(force=False):
            nonlocal last_progress
            now = time.monotonic()
            if force or now - last_progress >= 0.20:
                handle.report_progress((processed, total))
                last_progress = now

        report_progress(force=True)
        # Walk the immutable dataset order, rather than shuffled split order,
        # so newly discovered labels always receive stable indices regardless
        # of the selected random seed.
        for image_path in request.image_paths:
            handle.check_cancelled()
            loaded = load_image_result(
                image_path, resolver=request.resolver,
                image_list=request.image_paths,
                save_dir=request.save_dir,
                label_file_format=request.source_format,
                cancelled=handle.is_cancelled)
            if loaded is None:
                raise JobCancelled()
            if loaded.annotation_error:
                raise UltralyticsExportError(
                    'could not read annotation for %s: %s'
                    % (image_path, loaded.annotation_error))

            source_key = _source_key(image_path)
            split_name = split_by_source[source_key]
            output_name = output_names[source_key]
            output_stem = os.path.splitext(output_name)[0]
            image_relative = os.path.join(
                'images', split_name, output_name)
            label_relative = None
            if loaded.annotation_path is not None:
                label_relative = os.path.join(
                    'labels', split_name, output_stem + '.txt')
                polygon_boxes += _write_yolo_label(
                    os.path.join(staging, label_relative), image_path,
                    loaded.original_width, loaded.original_height,
                    loaded.shapes, classes)
                annotated += 1
            else:
                unannotated += 1

            try:
                _place_file(
                    image_path, os.path.join(staging, image_relative),
                    bool(request.copy_images),
                    cancelled=handle.is_cancelled,
                    heartbeat=report_progress)
            except SplitCancelled as exc:
                raise JobCancelled() from exc
            manifest['splits'][split_name].append({
                'source': os.path.abspath(os.fspath(image_path)),
                'image': image_relative.replace(os.sep, '/'),
                'label': (label_relative.replace(os.sep, '/')
                          if label_relative else None),
                'objects': len(loaded.shapes),
            })
            processed += 1
            report_progress(processed == total)

        manifest['classes'] = classes
        manifest['summary'] = {
            'annotated_images': annotated,
            'unannotated_images': unannotated,
            'polygon_boxes': polygon_boxes,
        }
        _write_data_yaml(os.path.join(staging, 'data.yaml'), classes)
        manifest_name = 'labelimgpp_export_manifest.json'
        with open(os.path.join(staging, manifest_name), 'w',
                  encoding='utf-8', newline='\n') as output:
            json.dump(manifest, output, ensure_ascii=False, indent=2)
            output.write('\n')

        handle.begin_non_cancellable()
        _validate_destination(destination)
        if os.path.isdir(destination):
            os.rmdir(destination)
        os.replace(staging, destination)
        published = True
        staging = None
        return UltralyticsExportResult(
            destination=destination,
            manifest_path=os.path.join(destination, manifest_name),
            counts=tuple(
                (name, len(splits[name]))
                for name in ('train', 'val', 'test')),
            class_order=tuple(classes),
            annotated_images=annotated,
            unannotated_images=unannotated,
            polygon_boxes=polygon_boxes,
        )
    finally:
        if not published and staging is not None:
            shutil.rmtree(staging, ignore_errors=True)
