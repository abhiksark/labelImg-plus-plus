# tests/core/test_video_distinctness.py
"""Tests for the geometry distinctness pass."""
import unittest

from libs.core.video_distinctness import geometry_distinct_pts
from libs.core.video_model import VideoModelState
from libs.core.video_types import ObservationRecord, TrackRecord


def _track(track_id, label='car'):
    return TrackRecord(track_id=track_id, label=label,
                       shape_type='rectangle', color=(255, 0, 0))


def _obs(track_id, pts, box):
    return ObservationRecord(track_id=track_id, pts=pts, geometry=list(box))


def _state(tracks, observations):
    return VideoModelState(tuple(tracks), tuple(observations), (), ('car',))


class TestGeometryDistinctness(unittest.TestCase):

    def test_static_object_collapses_to_one_frame(self):
        """A parked object over many frames is one distinct frame."""
        box = (10, 10, 50, 50)
        obs = [_obs('t1', pts, box) for pts in range(0, 100, 10)]
        result = geometry_distinct_pts(_state([_track('t1')], obs))
        self.assertEqual(result, (0,))

    def test_moving_object_yields_multiple_frames(self):
        obs = [_obs('t1', pts, (pts, 0, pts + 40, 40))
               for pts in range(0, 100, 10)]
        result = geometry_distinct_pts(_state([_track('t1')], obs))
        self.assertGreater(len(result), 3)
        self.assertEqual(result[0], 0)

    def test_new_track_forces_a_frame(self):
        """An object appearing is always worth a frame, however static."""
        box = (10, 10, 50, 50)
        obs = [_obs('t1', 0, box), _obs('t1', 10, box),
               _obs('t1', 20, box), _obs('t2', 20, (60, 60, 90, 90))]
        result = geometry_distinct_pts(_state([_track('t1'), _track('t2')], obs))
        self.assertIn(20, result)

    def test_disappearing_track_forces_a_frame(self):
        box = (10, 10, 50, 50)
        obs = [_obs('t1', 0, box), _obs('t2', 0, (60, 60, 90, 90)),
               _obs('t1', 10, box), _obs('t1', 20, box)]
        result = geometry_distinct_pts(_state([_track('t1'), _track('t2')], obs))
        self.assertIn(10, result)

    def test_first_frame_is_always_kept(self):
        result = geometry_distinct_pts(
            _state([_track('t1')], [_obs('t1', 7, (0, 0, 10, 10))]))
        self.assertEqual(result, (7,))

    def test_empty_state_returns_empty(self):
        self.assertEqual(geometry_distinct_pts(_state([], [])), ())

    def test_absent_observations_are_ignored(self):
        box = (10, 10, 50, 50)
        obs = [_obs('t1', 0, box),
               ObservationRecord(track_id='t1', pts=10, geometry=list(box),
                                 present=False)]
        result = geometry_distinct_pts(_state([_track('t1')], obs))
        self.assertEqual(result, (0,))

    def test_threshold_controls_sensitivity(self):
        """A small shift is distinct at a strict threshold, not at a loose one."""
        obs = [_obs('t1', 0, (0, 0, 100, 100)),
               _obs('t1', 10, (5, 0, 105, 100))]
        strict = geometry_distinct_pts(_state([_track('t1')], obs),
                                       iou_threshold=0.99)
        loose = geometry_distinct_pts(_state([_track('t1')], obs),
                                      iou_threshold=0.5)
        self.assertEqual(len(strict), 2)
        self.assertEqual(len(loose), 1)


if __name__ == '__main__':
    unittest.main()
