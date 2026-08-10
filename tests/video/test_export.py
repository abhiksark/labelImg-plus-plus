import json
import os
import threading

import pytest

from libs.core.task_coordinator import JobCancelled
from libs.core.video_decoder import VideoDecoderSession
from libs.core.video_export import (
    VideoExportError, export_video_frames, frame_export_name,
)
from libs.core.video_types import (
    FrameStateRecord, ObservationRecord, TrackRecord, VideoExportRequest,
)
from libs.formats.labelFile import LabelFileFormat


class _Handle:
    def __init__(self, cancel_after=None):
        self.cancelled = threading.Event()
        self.cancel_after = cancel_after
        self.progress = []
        self.committing = False

    def check_cancelled(self):
        if self.cancelled.is_set() and not self.committing:
            raise JobCancelled()

    def is_cancelled(self):
        return self.cancelled.is_set() and not self.committing

    def report_progress(self, value):
        self.progress.append(value)
        if self.cancel_after is not None \
                and len(self.progress) >= self.cancel_after:
            self.cancelled.set()

    def begin_non_cancellable(self):
        self.check_cancelled()
        self.committing = True


def _request(tmp_path, make_video, annotation_format, destination='export'):
    source = make_video(tmp_path / 'clip.mp4', frames=12)
    decoder = VideoDecoderSession(source)
    try:
        first = decoder.decode_first()
        second = decoder.next_frame()
        third = decoder.next_frame()
    finally:
        decoder.close()
    track = TrackRecord(
        'track-1', 'car', 'rectangle', (0, 255, 0, 255), revision=1)
    observations = (
        ObservationRecord(
            track.track_id, first.frame_ref.pts, [1, 2, 20, 22],
            source='manual', review_state='accepted', anchor=True,
            revision=1),
        ObservationRecord(
            track.track_id, second.frame_ref.pts, [2, 2, 21, 22],
            source='tracker', review_state='pending', anchor=False,
            revision=2),
        ObservationRecord(
            track.track_id, third.frame_ref.pts, [3, 2, 22, 22],
            source='manual', review_state='accepted', anchor=True,
            revision=3),
    )
    return VideoExportRequest(
        source_path=source, project_path=source + '.labelimgpp.sqlite',
        destination=str(tmp_path / destination), stream_index=0,
        frame_refs=(first.frame_ref, second.frame_ref, third.frame_ref),
        observations=observations, tracks=(track,),
        frame_states=(FrameStateRecord(second.frame_ref.pts, True, 1),),
        annotation_format=annotation_format,
        class_order=('car',))


def test_stable_export_name_uses_stream_and_integer_pts():
    assert frame_export_name('drive', 2, -17, 'jpg') == \
        'drive__s2__p-17.jpg'


@pytest.mark.parametrize('annotation_format, annotation_name', [
    (LabelFileFormat.PASCAL_VOC, 'clip__s0__p0.xml'),
    (LabelFileFormat.YOLO, 'clip__s0__p0.txt'),
    (LabelFileFormat.YOLO_SEG, 'clip__s0__p0.txt'),
    (LabelFileFormat.COCO, 'annotations.json'),
    (LabelFileFormat.CREATE_ML, 'annotations.json'),
])
def test_export_uses_existing_formats_and_writes_manifest(
        tmp_path, make_video, annotation_format, annotation_name):
    request = _request(tmp_path, make_video, annotation_format)
    destination = export_video_frames(request, _Handle())
    assert os.path.isdir(destination)
    names = sorted(os.listdir(destination))
    assert annotation_name in names
    manifest = json.loads((tmp_path / 'export' /
                           'video_export_manifest.json').read_text())
    assert manifest['source']['sampled_sha256'] == \
        request.frame_refs[0].fingerprint.sampled_sha256
    assert [item['pts'] for item in manifest['frames']] == \
        [item.pts for item in request.frame_refs]
    # The pending tracker suggestion is excluded; interpolation between the
    # two accepted manual anchors is exported on the middle frame instead.
    assert manifest['frames'][1]['track_ids'] == ['track-1']
    if annotation_format == LabelFileFormat.COCO:
        document = json.loads((tmp_path / 'export' /
                               'annotations.json').read_text())
        assert len(document['images']) == 3
        assert len(document['annotations']) == 3
        assert document['categories'] == [{'id': 1, 'name': 'car'}]
    elif annotation_format == LabelFileFormat.CREATE_ML:
        document = json.loads((tmp_path / 'export' /
                               'annotations.json').read_text())
        assert len(document) == 3
        assert all(len(item['annotations']) == 1 for item in document)


def test_export_rejects_nonempty_destination_without_touching_it(
        tmp_path, make_video):
    request = _request(
        tmp_path, make_video, LabelFileFormat.PASCAL_VOC)
    destination = tmp_path / 'export'
    destination.mkdir()
    sentinel = destination / 'owned.txt'
    sentinel.write_text('keep')
    with pytest.raises(VideoExportError):
        export_video_frames(request, _Handle())
    assert sentinel.read_text() == 'keep'


def test_cancel_removes_only_owned_staging_tree(tmp_path, make_video):
    request = _request(
        tmp_path, make_video, LabelFileFormat.PASCAL_VOC)
    unrelated = tmp_path / '.labelimgpp-export-unrelated'
    unrelated.mkdir()
    (unrelated / 'keep').write_text('keep')
    with pytest.raises(JobCancelled):
        export_video_frames(request, _Handle(cancel_after=1))
    assert not os.path.exists(request.destination)
    assert (unrelated / 'keep').read_text() == 'keep'
    owned = [path for path in tmp_path.iterdir()
             if path.name.startswith('.labelimgpp-export-')
             and path != unrelated]
    assert owned == []
