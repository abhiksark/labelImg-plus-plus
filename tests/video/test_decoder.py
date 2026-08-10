from libs.core.video_decoder import VideoDecoderSession, pyav_major
from libs.core.video_project import default_project_path


def test_pyav_adapter_reports_supported_major():
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
