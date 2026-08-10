from types import SimpleNamespace
import struct

import pytest

from libs.core.video_decoder import (
    VIDEO_EXTENSIONS, VideoDecoderSession, _rotation_for_frame,
    _rotation_for_stream, pyav_major,
)
from libs.core.video_project import default_project_path


def test_pyav_adapter_reports_supported_major():
    pytest.importorskip('av')
    assert pyav_major() in (12, 13, 14, 15, 16, 17, 18)


def test_decoder_uses_pts_and_returns_detached_qimages(tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mp4')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        assert first.frame_ref.stream_index == decoder.stream_index
        assert first.frame_ref.time_base_den > 0
        assert not first.image.isNull()
        assert (first.display_width, first.display_height) == (96, 64)

        step = int(round(
            decoder.average_rate_den / decoder.average_rate_num /
            float(decoder.time_base)))
        target_pts = first.frame_ref.pts + 5 * step
        sought = decoder.seek_pts(target_pts)
        assert abs(sought.frame_ref.pts - target_pts) <= step
        assert sought.decode_fingerprint != first.decode_fingerprint
    finally:
        decoder.close()


def test_snapshot_keeps_original_source_contract(tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mkv', container_format='matroska')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        snapshot = decoder.snapshot(default_project_path(path), first)
        assert snapshot.source_path == path
        assert snapshot.initial_frame.frame_ref.fingerprint == \
            snapshot.fingerprint
        assert snapshot.codec
    finally:
        decoder.close()


@pytest.mark.parametrize('suffix,container_format', (
    ('.mp4', 'mp4'),
    ('.mov', 'mov'),
    ('.mkv', 'matroska'),
    ('.avi', 'avi'),
))
def test_guaranteed_local_containers_decode(
        tmp_path, make_video, suffix, container_format):
    path = make_video(
        tmp_path / ('acceptance' + suffix),
        container_format=container_format)
    decoder = VideoDecoderSession(path)
    try:
        assert decoder.decode_first().display_width == 96
        assert suffix in VIDEO_EXTENSIONS
    finally:
        decoder.close()


def test_vfr_seek_selects_nearest_presentation_timestamp(
        tmp_path, make_video):
    path = make_video(
        tmp_path / 'vfr.mkv', container_format='matroska',
        variable_rate=True)
    decoder = VideoDecoderSession(path)
    try:
        decoded = [decoder.decode_first().frame_ref.pts]
        while True:
            result = decoder.next_frame()
            if result is None:
                break
            decoded.append(result.frame_ref.pts)
        assert len(set(
            right - left for left, right in zip(decoded, decoded[1:]))) > 1
        target = (decoded[5] + decoded[6]) // 2
        result = decoder.seek_pts(target)
        expected = min(decoded, key=lambda pts: abs(pts - target))
        assert result.frame_ref.pts == expected
    finally:
        decoder.close()


def test_next_frame_after_nearest_seek_returns_unconsumed_successor(
        tmp_path, make_video):
    path = make_video(
        tmp_path / 'vfr-next.mkv', container_format='matroska',
        variable_rate=True)
    decoder = VideoDecoderSession(path)
    try:
        decoded = [decoder.decode_first().frame_ref.pts]
        while True:
            result = decoder.next_frame()
            if result is None:
                break
            decoded.append(result.frame_ref.pts)

        target = (decoded[6] + decoded[7]) // 2
        sought = decoder.seek_pts(target)
        expected_index = decoded.index(sought.frame_ref.pts) + 1
        assert decoder.next_frame().frame_ref.pts == decoded[expected_index]
    finally:
        decoder.close()


def test_display_matrix_rotation_overrides_stream_metadata():
    stream = SimpleNamespace(
        metadata={'rotate': '180'}, side_data={'DISPLAYMATRIX': 90.0})
    assert _rotation_for_stream(stream) == 90
    assert _rotation_for_frame(SimpleNamespace(rotation=90), 0) == 90
    assert _rotation_for_frame(SimpleNamespace(rotation=-90), 0) == 270
    assert _rotation_for_frame(SimpleNamespace(), 180) == 180


def test_raw_display_matrix_supports_intermediate_pyav_versions():
    class DisplayMatrix:
        type = SimpleNamespace(name='DISPLAYMATRIX')

        def __bytes__(self):
            return struct.pack(
                '=9i', 0, -65536, 0, 65536, 0, 0, 0, 0, 1073741824)

    frame = SimpleNamespace(side_data=(DisplayMatrix(),), rotation=0)
    assert _rotation_for_frame(frame, 0) == 90


def test_corrupted_container_is_rejected_without_side_effects(tmp_path):
    path = tmp_path / 'corrupted.mp4'
    path.write_bytes(b'not a media container')
    with pytest.raises(Exception):
        VideoDecoderSession(str(path))
