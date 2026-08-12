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
from libs.core.video_types import (
    ObservationRecord, TrackGapRecord, TrackRecord)
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


def _one_track_state(observations, gaps=()):
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),)
    return VideoModelState(tracks, observations, (), ('car',), gaps)


def _relative_luminance(hex_color):
    channels = []
    for offset in (1, 3, 5):
        value = int(hex_color[offset:offset + 2], 16) / 255.0
        channels.append(
            value / 12.92 if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground, background):
    lighter = _relative_luminance(foreground)
    darker = _relative_luminance(background)
    if lighter < darker:
        lighter, darker = darker, lighter
    return (lighter + 0.05) / (darker + 0.05)


def _spans(view, track_id='t1'):
    """The segments as bare tuples, so boundaries can be asserted exactly."""
    return [(seg.start_pts, seg.end_pts, seg.kind)
            for seg in view.segments_for(track_id)]


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

    def test_the_selected_lane_label_stays_readable_in_both_themes(self):
        """The label is drawn over the selection fill, so it must clear AA.

        Computed, not pinned to a hex: filling with ``accent`` and lettering
        in ``text`` measured 3.1:1 light and 1.94:1 dark, and a later palette
        change must be caught the same way rather than by a stale literal.
        """
        for theme in (Theme.LIGHT, Theme.DARK):
            self.view.apply_theme(theme)
            fill, label = self.view.selection_colors()
            ratio = _contrast_ratio(label, fill)
            self.assertGreaterEqual(
                ratio, 4.5,
                '%s selected label %s on %s is %.2f:1' % (
                    theme, label, fill, ratio))

    def test_the_selected_lane_paints_the_colours_it_reports(self):
        """Keeps ``selection_colors`` honest about what reaches the screen."""
        self.view.resize(400, 200)
        self.view.select_track('t1')
        painted = self.view.grab().toImage().pixelColor(1, 1).name()
        self.assertEqual(painted, self.view.selection_colors()[0])

    def test_empty_state_renders_no_lanes(self):
        self.view.set_state(VideoModelState((), (), (), ()), duration_pts=100)
        self.assertEqual(self.view.lane_count(), 0)

    def test_pending_outranks_a_manual_anchor(self):
        """Rule 1 beats rule 2: awaiting review is what the lane must show."""
        self.view.set_state(_one_track_state((
            ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 10, 10],
                              source='manual', review_state='pending',
                              anchor=True),
        )), duration_pts=100)
        self.assertEqual(_spans(self.view),
                         [(0, 0, 'pending'), (0, 100, 'absent')])

    def test_runs_merge_by_kind_and_tile_the_whole_duration(self):
        """Boundaries, not just kinds: merging and gap-free tiling are fixed."""
        self.view.set_state(_one_track_state((
            ObservationRecord(track_id='t1', pts=10, geometry=[0, 0, 1, 1]),
            ObservationRecord(track_id='t1', pts=20, geometry=[0, 0, 1, 1]),
            ObservationRecord(track_id='t1', pts=30, geometry=[0, 0, 1, 1],
                              source='tracker', anchor=False),
            ObservationRecord(track_id='t1', pts=40, geometry=[0, 0, 1, 1],
                              source='tracker', anchor=False),
        )), duration_pts=100)
        self.assertEqual(_spans(self.view), [
            (0, 10, 'absent'),
            (10, 20, 'anchor'),     # the two manual anchors merge
            (20, 30, 'absent'),     # no interpolation crosses a kind boundary
            (30, 40, 'tracker'),    # the two tracker frames merge
            (40, 100, 'absent'),
        ])

    def test_a_gap_splits_the_run_it_overlaps(self):
        """A declared gap is absent even where interpolation would cover."""
        self.view.set_state(_one_track_state(
            (ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 1, 1]),
             ObservationRecord(track_id='t1', pts=100, geometry=[0, 0, 1, 1])),
            gaps=(TrackGapRecord(track_id='t1', start_pts=40, end_pts=60,
                                 reason='occluded', backend='manual'),),
        ), duration_pts=100)
        self.assertEqual(_spans(self.view), [
            (0, 40, 'anchor'),
            (40, 60, 'absent'),
            (60, 100, 'anchor'),
        ])

    def test_rejected_observations_are_not_coverage(self):
        """Rejected data breaks the run rather than filling it."""
        self.view.set_state(_one_track_state((
            ObservationRecord(track_id='t1', pts=0, geometry=[0, 0, 1, 1]),
            ObservationRecord(track_id='t1', pts=50, geometry=[0, 0, 1, 1],
                              review_state='rejected'),
            ObservationRecord(track_id='t1', pts=100, geometry=[0, 0, 1, 1]),
        )), duration_pts=200)
        self.assertEqual(_spans(self.view), [
            (0, 0, 'anchor'),
            (0, 100, 'absent'),
            (100, 100, 'anchor'),
            (100, 200, 'absent'),
        ])

    def test_not_present_observations_are_not_coverage(self):
        """present=False says the object is gone; the lane must agree."""
        self.view.set_state(_one_track_state((
            ObservationRecord(track_id='t1', pts=0, geometry=None,
                              present=False),
        )), duration_pts=100)
        self.assertEqual(_spans(self.view), [(0, 100, 'absent')])


if __name__ == '__main__':
    unittest.main()
