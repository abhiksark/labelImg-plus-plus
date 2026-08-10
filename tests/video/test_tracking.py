import threading

import pytest

from libs.core.task_coordinator import JobCancelled
from libs.core.video_decoder import VideoDecoderSession
from libs.core.video_tracking import _propagate_pair, track_optical_flow
from libs.core.video_types import (
    ObservationRecord, TrackRecord, TrackingRequest,
)


class _Handle:
    def __init__(self):
        self.cancelled = threading.Event()
        self.progress = []

    def check_cancelled(self):
        if self.cancelled.is_set():
            raise JobCancelled()

    def is_cancelled(self):
        return self.cancelled.is_set()

    def report_progress(self, value):
        self.progress.append(value)


def test_affine_flow_tracks_textured_translation():
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    previous = np.zeros((96, 128), dtype=np.uint8)
    current = np.zeros_like(previous)
    for y in range(23, 55, 6):
        for x in range(23, 55, 6):
            previous[y - 1:y + 2, x - 1:x + 2] = 255
            current[y + 1:y + 4, x + 2:x + 5] = 255
    rectangle = [18, 18, 60, 60]
    points = cv2.goodFeaturesToTrack(
        previous, maxCorners=100, qualityLevel=.01, minDistance=3)
    propagated, reason = _propagate_pair(
        previous, current, rectangle, points, cv2, np)
    assert reason is None
    transformed, _matrix, _points, quality = propagated
    assert transformed == pytest.approx([21, 20, 63, 62], abs=.8)
    assert quality > .5


def test_affine_flow_rejects_insufficient_features():
    cv2 = pytest.importorskip('cv2')
    np = pytest.importorskip('numpy')
    gray = np.zeros((64, 64), dtype=np.uint8)
    propagated, reason = _propagate_pair(
        gray, gray, [1, 1, 20, 20], None, cv2, np)
    assert propagated is None
    assert reason == 'insufficient features'


def _request(path, decoder, first, end_pts):
    track = TrackRecord(
        'track-1', 'object', 'rectangle', (0, 255, 0, 255),
        revision=2)
    seed = ObservationRecord(
        track.track_id, first.frame_ref.pts, [16, 14, 52, 50],
        source='manual', review_state='accepted', anchor=True,
        revision=2)
    return TrackingRequest(
        request_id=7, generation=3, source_path=path,
        stream_index=decoder.stream_index, start_ref=first.frame_ref,
        end_pts=end_pts, direction=1, track=track, seed=seed,
        seed_track_revision=track.revision, document_revision=2)


def test_worker_emits_pending_observations_with_quality(
        tmp_path, make_video):
    path = make_video(
        tmp_path / 'tracking.mp4', frames=18, width=128, height=96,
        tracking_stress=True)
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        step = int(round(
            decoder.average_rate_den / decoder.average_rate_num /
            float(decoder.time_base)))
        request = _request(path, decoder, first, first.frame_ref.pts + 12 * step)
        result = track_optical_flow(request, _Handle())
        assert result.finished is True
        assert len(result.observations) >= 8
        assert all(item.source == 'tracker' for item in result.observations)
        assert all(item.review_state == 'pending'
                   for item in result.observations)
        assert result.observations[-1].geometry[0] > \
            result.observations[0].geometry[0]
        assert all(0 <= item.quality <= 1 for item in result.observations)
    finally:
        decoder.close()


def test_worker_stops_at_scene_cut(tmp_path, make_video):
    path = make_video(
        tmp_path / 'cut.mp4', frames=18, width=128, height=96,
        tracking_stress=True, scene_cut_at=7)
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        step = int(round(
            decoder.average_rate_den / decoder.average_rate_num /
            float(decoder.time_base)))
        result = track_optical_flow(
            _request(path, decoder, first, first.frame_ref.pts + 14 * step),
            _Handle())
        assert result.stop_reason in (
            'scene cut', 'insufficient forward/backward matches',
            'insufficient features')
        assert result.end_pts < first.frame_ref.pts + 14 * step
    finally:
        decoder.close()


def test_backward_worker_processes_bounded_chunks_in_reverse(
        tmp_path, make_video):
    path = make_video(
        tmp_path / 'backward.mp4', frames=30, width=128, height=96,
        tracking_stress=True)
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        step = int(round(
            decoder.average_rate_den / decoder.average_rate_num /
            float(decoder.time_base)))
        seed_frame = decoder.seek_pts(first.frame_ref.pts + 20 * step)
        request = _request(path, decoder, seed_frame,
                           first.frame_ref.pts + 8 * step)
        request = request.__class__(
            request.request_id, request.generation, request.source_path,
            request.stream_index, request.start_ref, request.end_pts, -1,
            request.track,
            ObservationRecord(
                request.track.track_id, seed_frame.frame_ref.pts,
                [36, 14, 72, 50], source='manual',
                review_state='accepted', anchor=True, revision=2),
            request.seed_track_revision, request.document_revision)
        result = track_optical_flow(request, _Handle())
        assert len(result.observations) >= 8
        assert result.observations[0].pts < seed_frame.frame_ref.pts
        assert result.observations[-1].pts <= result.observations[0].pts
        assert result.observations[-1].geometry[0] < \
            result.observations[0].geometry[0]
    finally:
        decoder.close()


def test_worker_honors_cancellation_before_decode(tmp_path, make_video):
    path = make_video(
        tmp_path / 'cancel.mp4', tracking_stress=True,
        width=128, height=96)
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        handle = _Handle()
        handle.cancelled.set()
        request = _request(path, decoder, first, first.frame_ref.pts + 1000)
        with pytest.raises(JobCancelled):
            track_optical_flow(request, handle)
    finally:
        decoder.close()
