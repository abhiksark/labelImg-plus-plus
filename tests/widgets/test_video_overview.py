"""The overview keeps both views agreeing on one answer."""
import os
import sys
import unittest
from unittest.mock import patch

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication

from libs.core.video_distinctness import geometry_distinct_pts
from libs.core.video_model import VideoModelState
from libs.core.video_types import ObservationRecord, TrackRecord
from libs.utils import dpi
from libs.utils.styles import Theme, get_theme_colors
from libs.widgets.videoOverview import VideoOverview

app = QApplication.instance() or QApplication(sys.argv)


def _state():
    """Two tracks moving together; every annotated frame is distinct."""
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),
              TrackRecord(track_id='t2', label='person',
                          shape_type='rectangle', color=(0, 255, 0)))
    observations = tuple(
        ObservationRecord(track_id=track, pts=pts,
                          geometry=[pts, 0, pts + 10, 10])
        for track in ('t1', 't2') for pts in (0, 10, 20))
    return VideoModelState(tracks, observations, (), ('car', 'person'))


def _redundant_state(moved_at=30):
    """One track annotated on 0, 10, 20, 30 but parked until *moved_at*.

    Geometry distinctness therefore keeps the first frame and *moved_at* only,
    so the rest are the frames a pixel refinement pass is allowed to add back.
    Moving the jump gives a second state with a different answer over the same
    annotated frames.
    """
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),)
    observations = tuple(
        ObservationRecord(track_id='t1', pts=pts,
                          geometry=[0, 0, 10, 10] if pts < moved_at
                          else [100, 0, 110, 10])
        for pts in (0, 10, 20, 30))
    return VideoModelState(tracks, observations, (), ('car',))


def _split_state():
    """Two tracks on different frames, so a track filter actually narrows."""
    tracks = (TrackRecord(track_id='t1', label='car',
                          shape_type='rectangle', color=(255, 0, 0)),
              TrackRecord(track_id='t2', label='person',
                          shape_type='rectangle', color=(0, 255, 0)))
    observations = tuple(
        ObservationRecord(track_id='t1', pts=pts,
                          geometry=[pts, 0, pts + 10, 10])
        for pts in (0, 10, 20)) + tuple(
        ObservationRecord(track_id='t2', pts=pts,
                          geometry=[pts, 20, pts + 10, 30])
        for pts in (20, 30))
    return VideoModelState(tracks, observations, (), ('car', 'person'))


class TestVideoOverview(unittest.TestCase):

    def setUp(self):
        self.overview = VideoOverview()
        self.overview.set_state(_state(), duration_pts=100)

    # -- the view toggle -------------------------------------------------

    def test_defaults_to_lanes(self):
        self.assertEqual(self.overview.current_view(), 'lanes')

    def test_the_default_page_on_screen_is_the_lanes(self):
        self.assertIs(self.overview.stack.currentWidget(), self.overview.lanes)

    def test_view_toggle_switches(self):
        self.overview.set_view('frames')
        self.assertEqual(self.overview.current_view(), 'frames')

    def test_switching_view_changes_the_page_on_screen(self):
        self.overview.set_view('frames')
        self.assertIs(self.overview.stack.currentWidget(),
                      self.overview.frames)

    def test_switching_back_to_lanes_restores_that_page(self):
        self.overview.set_view('frames')
        self.overview.set_view('lanes')
        self.assertIs(self.overview.stack.currentWidget(), self.overview.lanes)

    def test_an_unknown_view_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.overview.set_view('timeline')

    def test_clicking_the_toggle_button_switches_the_view(self):
        self.overview.view_button('frames').click()
        self.assertEqual(self.overview.current_view(), 'frames')

    def test_the_toggle_buttons_follow_set_view(self):
        self.overview.set_view('frames')
        self.assertTrue(self.overview.view_button('frames').isChecked())
        self.assertFalse(self.overview.view_button('lanes').isChecked())

    # -- the two children stay in step -----------------------------------

    def test_the_lanes_receive_the_state_and_the_duration(self):
        self.assertEqual(self.overview.lanes.lane_track_ids(), ['t1', 't2'])
        self.assertEqual(
            self.overview.lanes.segments_for('t1')[-1].end_pts, 100)

    def test_the_grid_starts_from_the_geometry_answer(self):
        state = _redundant_state()
        self.overview.set_state(state, duration_pts=100)
        self.assertEqual(self.overview.frames.visible_pts(),
                         list(geometry_distinct_pts(state)))
        self.assertEqual(self.overview.frames.visible_pts(), [0, 30])

    def test_selecting_a_lane_filters_the_frames_view(self):
        self.overview.lanes.select_track('t2')
        self.overview.set_view('frames')
        self.assertEqual(self.overview.frames.track_filter(), 't2')

    def test_selecting_a_lane_narrows_the_frames_on_screen(self):
        self.overview.set_state(_split_state(), duration_pts=100)
        self.assertEqual(self.overview.frames.visible_pts(), [0, 10, 20, 30])
        self.overview.lanes.select_track('t2')
        self.assertEqual(self.overview.frames.visible_pts(), [20, 30])

    def test_selecting_a_lane_does_not_switch_the_view(self):
        self.overview.lanes.select_track('t2')
        self.assertEqual(self.overview.current_view(), 'lanes')

    def test_seek_from_either_view_is_forwarded(self):
        received = []
        self.overview.seekRequested.connect(received.append)
        self.overview.frames.activate_pts(10)
        self.overview.lanes.seekRequested.emit(20)
        self.assertEqual(received, [10, 20])

    # -- refinement ------------------------------------------------------

    def test_refinement_only_adds_frames(self):
        self.overview.set_view('frames')
        before = set(self.overview.frames.visible_pts())
        self.overview.set_refined_pts(tuple(sorted(before | {15})))
        after = set(self.overview.frames.visible_pts())
        self.assertTrue(before.issubset(after))

    def test_refinement_adds_a_frame_geometry_skipped(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.overview.set_refined_pts((0, 10, 30))
        self.assertEqual(self.overview.frames.visible_pts(), [0, 10, 30])

    def test_refinement_never_drops_the_geometry_answer(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.overview.set_refined_pts((10,))
        self.assertEqual(self.overview.frames.visible_pts(), [0, 10, 30])

    def test_a_new_state_discards_the_previous_refinement(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.overview.set_refined_pts((0, 10, 20, 30))
        state = _redundant_state(moved_at=20)
        self.overview.set_state(state, duration_pts=100)
        self.assertEqual(self.overview.frames.visible_pts(), [0, 20])
        self.assertEqual(self.overview.frames.visible_pts(),
                         list(geometry_distinct_pts(state)))

    def test_refinement_before_any_state_is_harmless(self):
        overview = VideoOverview()
        overview.set_refined_pts((5,))
        self.assertEqual(overview.frames.visible_pts(), [])

    # -- the live count --------------------------------------------------

    def test_the_count_reports_shown_and_total(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.assertEqual(self.overview.count_text(), '2 of 4 frames')

    def test_the_count_follows_the_frames_filter(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.overview.frames.set_filter('annotated')
        self.assertEqual(self.overview.count_text(), '4 of 4 frames')

    def test_the_count_follows_a_refinement(self):
        self.overview.set_state(_redundant_state(), duration_pts=100)
        self.overview.set_refined_pts((0, 10, 30))
        self.assertEqual(self.overview.count_text(), '3 of 4 frames')

    # -- theming ---------------------------------------------------------

    def test_the_theme_reaches_both_children(self):
        self.overview.apply_theme(Theme.DARK)
        surface = get_theme_colors(Theme.DARK)['surface']
        self.assertIn(surface, self.overview.lanes.styleSheet())
        self.assertIn(surface, self.overview.frames.styleSheet())

    def test_the_toggle_metrics_follow_the_display_scale(self):
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.0):
            self.overview.apply_theme(Theme.LIGHT)
            single = self.overview.styleSheet()
        with patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0):
            self.overview.apply_theme(Theme.LIGHT)
            double = self.overview.styleSheet()
        self.assertIn('border-radius: 10px', single)
        self.assertIn('border-radius: 20px', double)


if __name__ == '__main__':
    unittest.main()
