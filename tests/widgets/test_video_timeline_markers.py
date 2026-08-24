from dataclasses import FrozenInstanceError, replace

import pytest
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QSignalSpy, QTest
from PyQt5.QtWidgets import QApplication

from libs.core.video_types import (
    VideoFingerprint, VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
)
from libs.widgets import videoTimelineWidget as timeline


_APP = QApplication.instance() or QApplication([])


@pytest.fixture
def video_snapshot():
    fingerprint = VideoFingerprint(1024, 123, 'marker-fixture')
    frame_ref = VideoFrameRef(fingerprint, 0, 3400, 1, 1000)
    image = QImage(96, 64, QImage.Format_RGB32)
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    first = VideoFrameResult(
        frame_ref, image, 96, 64, 96, 64, 0,
        byte_size, 'marker-fixture:0:3400')
    return VideoSessionSnapshot(
        'timeline.mp4', None, fingerprint, 0, 1, 1000,
        96, 64, 0, 'fixture', 10_000, 900, 12, 1, 0, first)


def test_marker_groups_normalize_every_kind_and_are_immutable():
    assert hasattr(timeline, 'TimelineMarkerGroup')
    slider = timeline._MarkerSlider()
    slider.setRange(0, timeline.TIMELINE_MAX)
    slider.set_markers(
        accepted=(10,),
        pending=(20, 30),
        verified=(40,),
        propagation=((80, 70),),
        gaps=((-4, timeline.TIMELINE_MAX + 20),))

    groups = slider.marker_groups()
    assert groups == (
        timeline.TimelineMarkerGroup(
            'accepted', 'Accepted', 'solid-tick', ((10, 10),)),
        timeline.TimelineMarkerGroup(
            'pending', 'Pending', 'hollow-diamond',
            ((20, 20), (30, 30))),
        timeline.TimelineMarkerGroup(
            'verified', 'Verified', 'bottom-triangle', ((40, 40),)),
        timeline.TimelineMarkerGroup(
            'propagation', 'Propagation', 'hatched-span', ((70, 80),)),
        timeline.TimelineMarkerGroup(
            'gap', 'Gaps', 'crossed-span',
            ((0, timeline.TIMELINE_MAX),)),
    )
    assert len({group.pattern for group in groups}) == 5
    with pytest.raises(FrozenInstanceError):
        groups[0].kind = 'pending'


def test_marker_summary_is_the_slider_accessible_description():
    slider = timeline._MarkerSlider()
    assert hasattr(slider, 'accessible_marker_summary')
    slider.setRange(0, timeline.TIMELINE_MAX)
    slider.set_markers(
        accepted=(10,), pending=(20, 30), verified=(40,),
        propagation=((45, 48),), gaps=((50, 60),))

    summary = slider.accessible_marker_summary()
    assert slider.accessibleName() == 'Video timeline'
    assert slider.accessibleDescription() == summary
    assert '1 accepted, range 10' in summary
    assert '2 pending, range 20–30' in summary
    assert '1 verified, range 40' in summary
    assert '1 propagation, range 45–48' in summary
    assert '1 gap, range 50–60' in summary


def test_legend_has_one_keyboard_action_per_kind_and_uses_seek_intent(
        video_snapshot):
    widget = timeline.VideoTimelineWidget()
    assert hasattr(widget, 'legend_button')
    try:
        widget.set_session(video_snapshot)
        widget.set_markers(
            accepted=(1900, 2900), pending=(2100,), verified=(2300,),
            propagation=((2500, 2700),), gaps=((3100, 3300),))
        widget.resize(748, 96)
        widget.show()
        QApplication.processEvents()

        assert widget.legend_button.isVisible()
        assert widget.legend_button.focusPolicy() == Qt.StrongFocus
        assert widget.legend_button.accessibleName() == 'Timeline legend'
        assert widget.legend_menu.title() == 'Timeline legend'
        actions = widget.legend_menu.actions()
        assert len(actions) == 5
        assert [action.data() for action in actions] == [
            'accepted', 'pending', 'verified', 'propagation', 'gap']
        assert all('range' in action.text() for action in actions)
        assert sum('accepted' in action.text().lower()
                   for action in actions) == 1

        widget.legend_button.setFocus(Qt.TabFocusReason)
        assert widget.legend_button.hasFocus()
        opened = QSignalSpy(widget.legend_menu.aboutToShow)
        QTimer.singleShot(0, widget.legend_menu.close)
        QTest.keyClick(widget.legend_button, Qt.Key_Space)
        QApplication.processEvents()
        assert len(opened) == 1

        current = replace(video_snapshot.initial_frame.frame_ref, pts=1400)
        expected_pts = {
            'accepted': 1900,
            'pending': 2100,
            'verified': 2300,
            'propagation': 2500,
            'gap': 3100,
        }
        seeks = QSignalSpy(widget.seekRequested)
        for index, action in enumerate(actions, 1):
            widget.set_current_frame(current)
            displayed_value = widget.slider.value()
            projected_changes = QSignalSpy(widget.slider.valueChanged)
            action.trigger()
            assert len(seeks) == index
            frame_ref = seeks[-1][0]
            assert frame_ref == VideoFrameRef(
                video_snapshot.fingerprint, video_snapshot.stream_index,
                expected_pts[action.data()], video_snapshot.time_base_num,
                video_snapshot.time_base_den)
            with pytest.raises(FrozenInstanceError):
                frame_ref.pts = 0
            assert widget.slider.value() == displayed_value
            assert len(projected_changes) == 0
    finally:
        widget.close()


def test_legend_wraps_to_the_first_marker_without_queued_slider_feedback(
        video_snapshot):
    widget = timeline.VideoTimelineWidget()
    assert hasattr(widget, 'legend_button')
    try:
        widget.set_session(video_snapshot)
        widget.set_markers(accepted=(1900, 2900))
        widget.set_current_frame(
            replace(video_snapshot.initial_frame.frame_ref, pts=3900))
        widget.slider.setValue(widget._pts_to_normalized(3500))
        seeks = QSignalSpy(widget.seekRequested)

        widget.legend_menu.actions()[0].trigger()
        QTest.qWait(75)

        assert len(seeks) == 1
        assert seeks[0][0].pts == 1900
    finally:
        widget.close()
