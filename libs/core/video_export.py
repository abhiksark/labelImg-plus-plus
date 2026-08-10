"""Atomic tracked-frame export through existing annotation contracts."""

import json
import os
import tempfile

from libs.core.save_pipeline import (
    SaveRequest, target_path, write_save_request,
)
from libs.core.video_decoder import VideoDecoderSession
from libs.core.video_model import VideoProjectModel
from libs.formats.labelFile import LabelFileFormat


class VideoExportError(RuntimeError):
    pass


def frame_export_name(video_stem, stream_index, pts, extension):
    return '%s__s%s__p%s.%s' % (
        video_stem, int(stream_index), int(pts), extension.lower())


def _shape_dict(track, observation):
    if track.shape_type == 'rectangle':
        xmin, ymin, xmax, ymax = observation.geometry
        points = ((xmin, ymin), (xmax, ymin),
                  (xmax, ymax), (xmin, ymax))
    else:
        points = tuple(tuple(point) for point in observation.geometry)
    values = {
        'label': track.label,
        'points': points,
        'difficult': track.difficult,
        'shape_type': track.shape_type,
        'line_color': track.color,
        'fill_color': track.color,
    }
    if observation.keypoints is not None:
        values['keypoints'] = tuple(
            tuple(item) if item is not None else None
            for item in observation.keypoints)
    return values


def _serialize_shape(track, observation):
    return tuple(_shape_dict(track, observation).items())


def _coco_document(frames, classes):
    category_ids = {name: index + 1 for index, name in enumerate(classes)}
    images = []
    annotations = []
    annotation_id = 1
    for image_id, frame in enumerate(frames, 1):
        images.append({
            'id': image_id, 'file_name': frame['name'],
            'width': frame['width'], 'height': frame['height'],
        })
        for track, observation in frame['accepted']:
            shape = _shape_dict(track, observation)
            category_id = category_ids[track.label]
            points = shape['points']
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            annotation = {
                'id': annotation_id, 'image_id': image_id,
                'category_id': category_id,
                'bbox': [min(xs), min(ys),
                         max(xs) - min(xs), max(ys) - min(ys)],
                'iscrowd': 0, 'difficult': int(track.difficult),
            }
            annotation_id += 1
            if track.shape_type == 'polygon':
                annotation['segmentation'] = [[
                    value for point in points for value in point]]
            if observation.keypoints is not None:
                flat = []
                count = 0
                for item in observation.keypoints:
                    if item is not None and item[2] > 0:
                        flat.extend(item)
                        count += 1
                    else:
                        flat.extend((0, 0, 0))
                annotation['keypoints'] = flat
                annotation['num_keypoints'] = count
            annotations.append(annotation)
    return {
        'images': images,
        'annotations': annotations,
        'categories': [
            {'id': category_ids[name], 'name': name} for name in classes],
    }


def _create_ml_document(frames):
    document = []
    for frame in frames:
        annotations = []
        for track, observation in frame['accepted']:
            shape = _shape_dict(track, observation)
            xs = [point[0] for point in shape['points']]
            ys = [point[1] for point in shape['points']]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            annotations.append({
                'label': track.label,
                'coordinates': {
                    'x': min(xs) + width / 2,
                    'y': min(ys) + height / 2,
                    'width': width, 'height': height,
                },
            })
        document.append({
            'image': frame['name'],
            'verified': frame['verified'],
            'annotations': annotations,
        })
    return document


def _validate_destination(destination):
    if os.path.exists(destination):
        if not os.path.isdir(destination):
            raise VideoExportError('export destination is not a directory')
        if os.listdir(destination):
            raise VideoExportError(
                'export destination must be new or empty')


def export_video_frames(request, handle):
    """Stage all output and publish only after every frame succeeds."""
    destination = os.path.abspath(request.destination)
    _validate_destination(destination)
    parent = os.path.dirname(destination) or '.'
    if not os.path.isdir(parent):
        raise VideoExportError('export destination parent does not exist')
    staging = tempfile.mkdtemp(prefix='.labelimgpp-export-', dir=parent)
    decoder = None
    try:
        model = VideoProjectModel(
            tracks=request.tracks,
            observations=tuple(
                item for item in request.observations
                if item.review_state == 'accepted'),
            frame_states=request.frame_states, classes=request.class_order)
        class_order = list(request.class_order)
        for track in request.tracks:
            if track.label not in class_order:
                class_order.append(track.label)
        verified_pts = {
            item.pts for item in request.frame_states if item.verified}
        decoder = VideoDecoderSession(
            request.source_path, stream_index=request.stream_index,
            cancelled=handle.is_cancelled)
        video_stem = os.path.splitext(
            os.path.basename(request.source_path))[0]
        extension = ('png' if request.image_format.lower() == 'png'
                     else 'jpg')
        staged_frames = []
        seen_pts = set()
        total = len(request.frame_refs)
        for index, frame_ref in enumerate(request.frame_refs, 1):
            handle.check_cancelled()
            result = decoder.seek_pts(
                frame_ref.pts, mode='nearest',
                cancelled=handle.is_cancelled)
            if result is None or result.frame_ref.pts in seen_pts:
                continue
            seen_pts.add(result.frame_ref.pts)
            name = frame_export_name(
                video_stem, result.frame_ref.stream_index,
                result.frame_ref.pts, extension)
            image_path = os.path.join(staging, name)
            if extension == 'png':
                saved = result.image.save(image_path, 'PNG')
            else:
                saved = result.image.save(
                    image_path, 'JPEG', int(request.jpeg_quality))
            if not saved:
                raise VideoExportError('failed to encode frame %s' % name)
            materialized = model.materialize(result.frame_ref.pts)
            accepted = tuple(
                (item.track, item.observation) for item in materialized
                if item.render_state != 'pending'
                and item.observation.review_state == 'accepted')
            verified = result.frame_ref.pts in verified_pts
            staged_frames.append({
                'name': name, 'path': image_path,
                'width': result.display_width,
                'height': result.display_height,
                'ref': result.frame_ref,
                'accepted': accepted,
                'verified': verified,
            })
            if request.annotation_format not in (
                    LabelFileFormat.COCO, LabelFileFormat.CREATE_ML):
                serialized = tuple(
                    _serialize_shape(track, observation)
                    for track, observation in accepted)
                write_save_request(SaveRequest(
                    image_path=image_path,
                    annotation_path=target_path(
                        os.path.splitext(image_path)[0],
                        request.annotation_format),
                    label_file_format=request.annotation_format,
                    shapes=serialized, class_list=tuple(class_order),
                    verified=verified, revision=0),
                    cancelled=handle.is_cancelled)
            handle.report_progress((index, total, name))

        handle.check_cancelled()
        if request.annotation_format == LabelFileFormat.COCO:
            shared = _coco_document(staged_frames, class_order)
            with open(os.path.join(staging, 'annotations.json'), 'w',
                      encoding='utf-8') as output:
                json.dump(shared, output, indent=2)
        elif request.annotation_format == LabelFileFormat.CREATE_ML:
            shared = _create_ml_document(staged_frames)
            with open(os.path.join(staging, 'annotations.json'), 'w',
                      encoding='utf-8') as output:
                json.dump(shared, output, indent=2)

        manifest = {
            'schema_version': 1,
            'source': {
                'path': os.path.basename(request.source_path),
                'size': request.frame_refs[0].fingerprint.size
                if request.frame_refs else 0,
                'sampled_sha256': (
                    request.frame_refs[0].fingerprint.sampled_sha256
                    if request.frame_refs else None),
                'stream_index': request.stream_index,
            },
            'frames': [{
                'file': frame['name'],
                'pts': frame['ref'].pts,
                'time_base': [frame['ref'].time_base_num,
                              frame['ref'].time_base_den],
                'verified': frame['verified'],
                'track_ids': [track.track_id
                              for track, _observation in frame['accepted']],
            } for frame in staged_frames],
        }
        with open(os.path.join(staging, 'video_export_manifest.json'), 'w',
                  encoding='utf-8') as output:
            json.dump(manifest, output, indent=2)
        handle.check_cancelled()
        handle.begin_non_cancellable()
        if os.path.isdir(destination):
            os.rmdir(destination)  # It was verified empty; races fail safely.
        os.replace(staging, destination)
        staging = None
        return destination
    finally:
        if decoder is not None:
            decoder.close()
        if staging is not None and os.path.basename(staging).startswith(
                '.labelimgpp-export-'):
            import shutil
            shutil.rmtree(staging, ignore_errors=True)
