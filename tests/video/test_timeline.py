# tests/video/test_timeline.py
from dataclasses import replace

import pytest
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QAction, QApplication

from libs.core.video_decoder import VideoDecoderSession
from libs.widgets.videoTimelineWidget import (
    TIMELINE_MAX, VideoTimelineWidget, format_timecode, parse_timecode,
)
from libs.utils.styles import Theme, get_theme_colors


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
        assert 'PTS' not in widget.position_label.text()
        assert 'Exact PTS' in widget.position_label.toolTip()
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


def test_timeline_controls_have_names_and_semantic_focus_style():
    widget = VideoTimelineWidget()
    try:
        widget.apply_theme(Theme.DARK)
        assert widget.play_button.accessibleName() == 'Play or pause video'
        assert widget.previous_button.accessibleName() == 'Previous frame'
        assert widget.next_button.accessibleName() == 'Next frame'
        assert widget.time_edit.accessibleName() == 'Presentation time'
        assert widget.slider.accessibleName() == 'Video timeline'
        assert 'QSlider:focus' in widget.styleSheet()
        assert get_theme_colors(Theme.DARK)['focus'] in widget.styleSheet()
    finally:
        widget.close()


def test_propagation_actions_and_progress_replace_each_other():
    widget = VideoTimelineWidget()
    propagate_all = QAction('Propagate across video', widget)
    propagate_selected = QAction('Propagate selected object', widget)
    cancel = QAction('Cancel', widget)
    widget.set_propagation_actions(
        propagate_all, propagate_selected, cancel)
    assert widget.propagate_all_button.defaultAction() is propagate_all
    assert widget.propagate_selected_button.defaultAction() is \
        propagate_selected

    widget.set_propagation_progress(
        12, 40, 2, 1, 3.25, 4, running=True)
    assert widget.progress_label.isHidden() is False
    assert widget.cancel_propagation_button.isHidden() is False
    assert widget.propagate_all_button.isHidden() is True
    assert '12/40 frames' in widget.progress_label.text()
    assert '4 gaps/failures' in widget.progress_label.text()

    widget.set_propagation_progress(
        0, 0, 0, 0, None, 0, running=False)
    assert widget.progress_label.isHidden() is True
    assert widget.cancel_propagation_button.isHidden() is True
    assert widget.propagate_all_button.isHidden() is True
    widget.close()


def test_workflow_stage_follows_canonical_markers():
    widget = VideoTimelineWidget()
    assert widget.workflow_stage() == 'anchor'

    widget.set_markers(accepted=(10,))
    assert widget.workflow_stage() == 'propagate'

    widget.set_markers(spans=((10, 30),), accepted=(10,), pending=(20,))
    assert widget.workflow_stage() == 'review'

    widget.set_markers(spans=((10, 30),), accepted=(10,))
    assert widget.workflow_stage() == 'export'

    widget.set_propagation_progress(
        1, 10, 1, 0, 2.0, 0, running=True)
    assert widget.workflow_stage() == 'propagate'

    widget._update_responsive_chrome(640)
    assert widget.position_label.isHidden()
    assert [label.text() for label in widget.workflow_stages
            if not label.isHidden()] == ['● Propagate']
    assert all(arrow.isHidden() for arrow in widget.workflow_arrows)
    widget.close()
