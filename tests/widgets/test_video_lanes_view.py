"""Lanes turn observations into per-track segment runs."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication

from libs.core.video_model import VideoModelState
from libs.core.video_types import ObservationRecord, TrackRecord
from libs.widgets.videoLanesView import VideoLanesView
from libs.utils.styles import Theme

app = QApplication.instance() or QApplication(sys.argv)


def _state():
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),
              TrackRecord(track_id='t2', label='person',
                          shape_type='rectangle', color=(0, 255, 0)))
    observations = (
        ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 10, 10]),
        ObservationRecord(track_id='t1', pts=50, geometry=[0, 0, 10, 10],
                          source='tracker', anchor=False),
        ObservationRecord(track_id='t2', pts=60, geometry=[5, 5, 15, 15],
                          source='tracker', review_state='pending',
                          anchor=False),
    )
    return VideoModelState(tracks, observations, (), ('car', 'person'))


class TestVideoLanesView(unittest.TestCase):

    def setUp(self):
        self.view = VideoLanesView()
        self.view.set_state(_state(), duration_pts=100)

    def test_one_lane_per_track(self):
        self.assertEqual(self.view.lane_count(), 2)

    def test_lanes_carry_their_track_id(self):
        self.assertEqual(self.view.lane_track_ids(), ['t1', 't2'])

    def test_segments_classify_observation_state(self):
        kinds = {seg.kind for seg in self.view.segments_for('t1')}
        self.assertIn('anchor', kinds)
        self.assertIn('tracker', kinds)

    def test_pending_is_distinguished(self):
        kinds = {seg.kind for seg in self.view.segments_for('t2')}
        self.assertIn('pending', kinds)

    def test_selecting_a_lane_emits_the_track_id(self):
        received = []
        self.view.trackSelected.connect(received.append)
        self.view.select_track('t2')
        self.assertEqual(received, ['t2'])

    def test_apply_theme_does_not_raise(self):
        self.view.apply_theme(Theme.DARK)
        self.view.apply_theme(Theme.LIGHT)

    def test_empty_state_renders_no_lanes(self):
        self.view.set_state(VideoModelState((), (), (), ()), duration_pts=100)
        self.assertEqual(self.view.lane_count(), 0)


if __name__ == '__main__':
    unittest.main()
