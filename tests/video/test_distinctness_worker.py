# tests/video/test_distinctness_worker.py
"""Pixel refinement seeks only the bounded plan and remains additive."""

from types import SimpleNamespace
from time import perf_counter
from unittest.mock import patch

import pytest

np = pytest.importorskip('numpy')

from libs.core.video_distinctness import DistinctnessPlan  # noqa: E402
from libs.core.video_decoder import VideoDecoderSession  # noqa: E402
from libs.core.video_distinctness_worker import (  # noqa: E402
    DistinctnessRefinementRequest, refine_distinct_pts,
    refine_distinctness, stride_for,
)
from libs.core.video_types import VideoFingerprint  # noqa: E402


FINGERPRINT = VideoFingerprint(10, 20, 'abc')


def _flat():
    return np.zeros((8, 9), dtype=np.uint8)


def _gradient():
    return np.tile(np.arange(9, dtype=np.uint8), (8, 1))


class _Decoder:
    images = {}
    seeks = []
    fail_at = None
    fingerprint = FINGERPRINT
    stream_index = 0
    time_base_num = 1
    time_base_den = 30

    def __init__(self, _path, stream_index=None, cancelled=None):
        del cancelled
        self.stream_index = int(stream_index)
        self.closed = False

    def seek_pts(self, pts, mode='nearest', cancelled=None):
        assert mode == 'nearest'
        if cancelled is not None and cancelled():
            return None
        self.__class__.seeks.append(int(pts))
        if self.fail_at == pts:
            raise RuntimeError('decode failed')
        return SimpleNamespace(image=self.images[int(pts)])

    def next_frame(self, **_kwargs):
        raise AssertionError('refinement must never decode sequentially')

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def _reset_decoder():
    _Decoder.images = {}
    _Decoder.seeks = []
    _Decoder.fail_at = None
    _Decoder.fingerprint = FINGERPRINT


def _run(selected=(0, 30), samples=(0, 15, 30), forced=(0, 30),
         cancelled=None):
    with patch(
            'libs.core.video_decoder.VideoDecoderSession', _Decoder), patch(
            'libs.integrations.image_convert.qimage_to_rgb',
            side_effect=lambda image: image), patch(
            'libs.core.video_distinctness_worker.fingerprint_video',
            return_value=FINGERPRINT):
        return refine_distinct_pts(
            '/tmp/clip.mp4', 0, selected, sample_pts=samples,
            forced_pts=forced, start_pts=0, time_base_num=1,
            time_base_den=30, fingerprint=FINGERPRINT,
            cancelled=cancelled)


def test_stride_helper_remains_compatible_but_does_not_drive_decoding():
    assert stride_for(30.0, 2.0) == 15
    assert stride_for(60.0, 2.0) == 30
    assert stride_for(None, 2.0) == 1


def test_unchanged_pixels_add_nothing_and_seek_only_sample_pts():
    _Decoder.images = {0: _flat(), 15: _flat(), 30: _flat()}
    result = _run()
    assert result == (0, 30)
    assert _Decoder.seeks == [0, 15, 30]


def test_material_visual_change_promotes_the_sampled_frame():
    _Decoder.images = {0: _flat(), 15: _gradient(), 30: _gradient()}
    result = _run()
    assert result == (0, 15, 30)


def test_refinement_cannot_add_a_second_ordinary_frame_in_a_window():
    _Decoder.images = {
        0: _flat(), 13: _flat(), 14: _gradient(), 30: _gradient(),
    }
    result = _run(
        selected=(0, 13, 30), samples=(0, 13, 14, 30),
        forced=(0, 30))
    assert result == (0, 13, 30)


def test_decode_failure_returns_the_complete_geometry_answer():
    _Decoder.images = {0: _flat(), 15: _gradient(), 30: _gradient()}
    _Decoder.fail_at = 15
    assert _run() == (0, 30)


def test_cancellation_is_observed_between_seeks():
    _Decoder.images = {0: _flat(), 15: _gradient(), 30: _gradient()}
    started = perf_counter()
    assert _run(cancelled=lambda: bool(_Decoder.seeks)) == (0, 30)
    elapsed = perf_counter() - started
    assert _Decoder.seeks == [0]
    assert elapsed < .5


def test_source_mismatch_leaves_geometry_and_marks_request_incomplete():
    _Decoder.images = {0: _flat(), 15: _gradient(), 30: _gradient()}
    _Decoder.fingerprint = VideoFingerprint(11, 20, 'changed')
    request = DistinctnessRefinementRequest(
        7, 3, 11, '/tmp/clip.mp4', FINGERPRINT, 0, 1, 30, 0,
        DistinctnessPlan((0, 30), (0, 30), (0, 15, 30)))
    with patch(
            'libs.core.video_decoder.VideoDecoderSession', _Decoder), patch(
            'libs.integrations.image_convert.qimage_to_rgb',
            side_effect=lambda image: image), patch(
            'libs.core.video_distinctness_worker.fingerprint_video',
            return_value=FINGERPRINT):
        result = refine_distinctness(request)
    assert result.refined_pts == (0, 30)
    assert result.completed is False
    assert _Decoder.seeks == []


def test_result_echoes_every_fence_and_is_cacheable_after_success():
    _Decoder.images = {0: _flat(), 15: _gradient(), 30: _gradient()}
    request = DistinctnessRefinementRequest(
        7, 3, 11, '/tmp/clip.mp4', FINGERPRINT, 0, 1, 30, 0,
        DistinctnessPlan((0, 30), (0, 30), (0, 15, 30)))
    with patch(
            'libs.core.video_decoder.VideoDecoderSession', _Decoder), patch(
            'libs.integrations.image_convert.qimage_to_rgb',
            side_effect=lambda image: image), patch(
            'libs.core.video_distinctness_worker.fingerprint_video',
            return_value=FINGERPRINT):
        result = refine_distinctness(request)
    assert result.completed is True
    assert result.refined_pts == (0, 15, 30)
    assert (result.request_id, result.generation, result.model_revision) == (
        7, 3, 11)
    assert result.fingerprint == FINGERPRINT
    assert (result.stream_index, result.time_base_num,
            result.time_base_den) == (0, 1, 30)
    assert result.start_pts == 0


def test_real_decoder_seeks_only_the_planned_pts(make_video, tmp_path):
    path = make_video(tmp_path / 'bounded.mp4', frames=24, rate=12)
    decoder = VideoDecoderSession(path)
    decoded_pts = []
    try:
        frame = decoder.decode_first()
        while frame is not None:
            decoded_pts.append(frame.frame_ref.pts)
            frame = decoder.next_frame()
        metadata = (
            decoder.stream_index, decoder.time_base_num,
            decoder.time_base_den, decoder.fingerprint)
    finally:
        decoder.close()

    samples = (
        decoded_pts[0], decoded_pts[len(decoded_pts) // 2], decoded_pts[-1])
    seeded = (samples[0], samples[-1])
    seeks = []
    original_seek = VideoDecoderSession.seek_pts

    def observed_seek(self, pts, *args, **kwargs):
        seeks.append(int(pts))
        return original_seek(self, pts, *args, **kwargs)

    with patch.object(
            VideoDecoderSession, 'seek_pts', observed_seek), patch.object(
            VideoDecoderSession, 'next_frame',
            side_effect=AssertionError('sequential decode is forbidden')):
        result = refine_distinct_pts(
            path, metadata[0], seeded, sample_pts=samples,
            forced_pts=seeded, start_pts=decoded_pts[0],
            time_base_num=metadata[1], time_base_den=metadata[2],
            fingerprint=metadata[3])

    assert seeks == list(samples)
    assert set(seeded).issubset(result)
    assert set(result).issubset(samples)
