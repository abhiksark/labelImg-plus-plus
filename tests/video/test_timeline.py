from dataclasses import replace

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from libs.core.video_decoder import VideoDecoderSession
from libs.widgets.videoTimelineWidget import (
    TIMELINE_MAX, VideoTimelineWidget, format_timecode, parse_timecode,
)


_APP = QApplication.instance() or QApplication([])


@pytest.mark.parametrize('seconds, expected', [
    (0, '00:00:00.000'),
    (1.234, '00:00:01.234'),
    (3661.999, '01:01:01.999'),
])
def test_timecode_round_trip(seconds, expected):
    assert format_timecode(seconds) == expected
    assert parse_timecode(expected) == pytest.approx(seconds)


def test_normalized_slider_handles_long_duration_without_overflow(
        tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mp4')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        snapshot = decoder.snapshot(None, first)
        snapshot = replace(snapshot, duration_pts=10 ** 15)
        widget = VideoTimelineWidget()
        widget.set_session(snapshot)
        ref = replace(first.frame_ref, pts=5 * 10 ** 14)
        widget.set_current_frame(ref)
        assert 0 <= widget.slider.value() <= TIMELINE_MAX
        assert abs(widget.slider.value() - TIMELINE_MAX // 2) <= 1
        widget.close()
    finally:
        decoder.close()


def test_release_emits_exact_frame_reference(tmp_path, make_video):
    path = make_video(tmp_path / 'clip.mp4')
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        snapshot = decoder.snapshot(None, first)
        widget = VideoTimelineWidget()
        widget.set_session(snapshot)
        spy = QSignalSpy(widget.seekRequested)
        widget.slider.setValue(TIMELINE_MAX // 2)
        widget._slider_released()
        assert len(spy) == 1
        ref = spy[0][0]
        assert ref.stream_index == snapshot.stream_index
        assert ref.time_base_den == snapshot.time_base_den
        widget.close()
    finally:
        decoder.close()


def test_invalid_timecode_does_not_emit():
    widget = VideoTimelineWidget()
    spy = QSignalSpy(widget.seekRequested)
    widget.time_edit.setText('not-a-time')
    widget._emit_time_seek()
    assert len(spy) == 0
    widget.close()
