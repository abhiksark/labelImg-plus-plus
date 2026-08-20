# tests/core/test_video_distinctness.py
"""Tests for the adaptive geometry distinctness planner."""

import unittest

from libs.core.video_distinctness import (
    DistinctnessPlan, build_distinctness_plan, geometry_distinct_pts,
    pts_window,
)
from libs.core.video_model import VideoModelState
from libs.core.video_types import (
    FrameStateRecord, ObservationRecord, TrackGapRecord, TrackRecord,
)


def _track(track_id, label='car', shape_type='rectangle'):
    return TrackRecord(track_id=track_id, label=label,
                       shape_type=shape_type, color=(255, 0, 0))


def _obs(track_id, pts, geometry, **changes):
    values = {
        'source': 'tracker', 'review_state': 'accepted', 'anchor': False,
    }
    values.update(changes)
    return ObservationRecord(
        track_id=track_id, pts=pts, geometry=geometry, **values)


def _state(tracks, observations, frame_states=(), gaps=()):
    return VideoModelState(
        tuple(tracks), tuple(observations), tuple(frame_states),
        tuple(track.label for track in tracks), tuple(gaps))


class TestGeometryDistinctness(unittest.TestCase):

    def test_plan_is_frozen_and_empty_state_is_empty(self):
        plan = build_distinctness_plan(_state([], []))
        self.assertEqual(plan, DistinctnessPlan((), (), ()))
        with self.assertRaises(AttributeError):
            plan.selected_pts = (1,)

    def test_reproduction_is_limited_to_four_frames(self):
        """59 tiny moving boxes used to make all 59 frames distinct."""
        observations = [
            _obs('t1', pts, [pts * 3, 0, pts * 3 + 36, 36],
                 review_state='pending')
            for pts in range(59)]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            start_pts=0, time_base_num=1, time_base_den=30)
        self.assertEqual(plan.forced_pts, (0, 58))
        self.assertEqual(plan.selected_pts, (0, 29, 44, 58))
        self.assertEqual(len(plan.selected_pts), 4)

    def test_static_propagation_collapses_to_first_and_last(self):
        box = (10, 10, 50, 50)
        observations = [_obs('t1', pts, box) for pts in range(59)]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            start_pts=0, time_base_num=1, time_base_den=30)
        self.assertEqual(plan.selected_pts, (0, 58))
        self.assertEqual(plan.sample_pts, (0, 29, 44, 58))

    def test_manual_anchors_closer_than_a_window_are_all_forced(self):
        observations = [
            _obs('t1', 0, [0, 0, 20, 20]),
            _obs('t1', 3, [1, 0, 21, 20], source='manual', anchor=True),
            _obs('t1', 7, [2, 0, 22, 20], source='manual', anchor=True),
            _obs('t1', 14, [3, 0, 23, 20]),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertTrue({3, 7}.issubset(plan.forced_pts))
        self.assertTrue({3, 7}.issubset(plan.selected_pts))

    def test_annotated_verified_frame_is_forced(self):
        observations = [_obs('t1', pts, [0, 0, 20, 20])
                        for pts in (0, 5, 10)]
        plan = build_distinctness_plan(
            _state(
                [_track('t1')], observations,
                frame_states=(FrameStateRecord(5, True),)),
            time_base_num=1, time_base_den=30)
        self.assertIn(5, plan.forced_pts)

    def test_track_appearance_and_disappearance_force_both_sides(self):
        observations = [
            _obs('t1', pts, [0, 0, 20, 20]) for pts in (0, 5, 10, 15)
        ] + [
            _obs('t2', pts, [30, 0, 50, 20]) for pts in (5, 10)
        ]
        plan = build_distinctness_plan(
            _state([_track('t1'), _track('t2')], observations),
            time_base_num=1, time_base_den=30)
        self.assertTrue({0, 5, 10, 15}.issubset(plan.forced_pts))

    def test_source_and_review_transitions_force_both_sides(self):
        observations = [
            _obs('t1', 0, [0, 0, 20, 20]),
            _obs('t1', 5, [0, 0, 20, 20], review_state='pending'),
            _obs('t1', 10, [0, 0, 20, 20], review_state='pending'),
            _obs('t1', 15, [0, 0, 20, 20], source='manual', anchor=True),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertTrue({0, 5, 10, 15}.issubset(plan.forced_pts))

    def test_only_pending_run_boundaries_are_events(self):
        observations = [
            _obs('t1', pts, [0, 0, 20, 20], review_state='pending')
            for pts in range(20)]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertEqual(plan.forced_pts, (0, 19))
        self.assertNotIn(10, plan.forced_pts)

    def test_absence_transition_forces_usable_sides_not_absent_frame(self):
        observations = [
            _obs('t1', 0, [0, 0, 20, 20]),
            _obs('t1', 5, None, present=False, source='manual', anchor=True),
            _obs('t1', 10, [0, 0, 20, 20]),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertEqual(plan.selected_pts, (0, 10))
        self.assertNotIn(5, plan.sample_pts)

    def test_gap_forces_nearest_observation_on_each_side(self):
        observations = [_obs('t1', pts, [0, 0, 20, 20])
                        for pts in (0, 5, 10, 20, 25, 30)]
        gap = TrackGapRecord('t1', 11, 19, 'occluded', 'opencv')
        plan = build_distinctness_plan(
            _state([_track('t1')], observations, gaps=(gap,)),
            time_base_num=1, time_base_den=30)
        self.assertTrue({10, 20}.issubset(plan.forced_pts))

    def test_observations_on_gap_boundaries_are_forced(self):
        observations = [_obs('t1', pts, [0, 0, 20, 20])
                        for pts in (0, 10, 20, 30)]
        gap = TrackGapRecord('t1', 10, 20, 'occluded', 'opencv')
        plan = build_distinctness_plan(
            _state([_track('t1')], observations, gaps=(gap,)),
            time_base_num=1, time_base_den=30)
        self.assertTrue({10, 20}.issubset(plan.forced_pts))

    def test_rejected_and_absent_observations_are_not_candidates(self):
        observations = [
            _obs('t1', 0, [0, 0, 20, 20]),
            _obs('t1', 5, [50, 0, 70, 20], review_state='rejected'),
            _obs('t1', 10, [100, 0, 120, 20], present=False),
            _obs('t1', 15, [0, 0, 20, 20]),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertNotIn(5, plan.sample_pts)
        self.assertNotIn(10, plan.sample_pts)

    def test_polygon_bounds_participate_in_novelty(self):
        observations = [
            _obs('t1', 0, [[0, 0], [20, 0], [10, 20]]),
            _obs('t1', 15, [[30, 0], [50, 0], [40, 20]]),
            _obs('t1', 30, [[30, 0], [50, 0], [40, 20]]),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1', shape_type='polygon')], observations),
            time_base_num=1, time_base_den=30)
        self.assertIn(15, plan.selected_pts)

    def test_least_stable_track_controls_multiple_track_novelty(self):
        observations = []
        for pts in (0, 15, 30):
            observations.append(_obs('static', pts, [0, 0, 100, 100]))
            x = 0 if pts == 0 else 30
            observations.append(_obs('moving', pts, [x, 0, x + 20, 20]))
        plan = build_distinctness_plan(
            _state(
                [_track('static'), _track('moving')], observations),
            time_base_num=1, time_base_den=30)
        self.assertIn(15, plan.selected_pts)

    def test_vfr_pts_use_presentation_time_buckets(self):
        pts_values = (100, 103, 109, 116, 124, 131)
        observations = [
            _obs('t1', pts, [pts, 0, pts + 10, 10])
            for pts in pts_values]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations), start_pts=100,
            time_base_num=1, time_base_den=30)
        ordinary = set(plan.sample_pts).difference(plan.forced_pts)
        buckets = [pts_window(pts, 100, 1, 30) for pts in ordinary]
        self.assertEqual(len(buckets), len(set(buckets)))
        self.assertLessEqual(len(ordinary), 2)

    def test_threshold_controls_only_ordinary_selection(self):
        observations = [
            _obs('t1', 0, [0, 0, 100, 100]),
            _obs('t1', 5, [5, 0, 105, 100]),
            _obs('t1', 10, [5, 0, 105, 100]),
        ]
        state = _state([_track('t1')], observations)
        strict = geometry_distinct_pts(
            state, iou_threshold=.99, time_base_num=1, time_base_den=10)
        loose = geometry_distinct_pts(
            state, iou_threshold=.5, time_base_num=1, time_base_den=10)
        self.assertEqual(strict, (0, 5, 10))
        self.assertEqual(loose, (0, 10))

    def test_equal_novelty_uses_latest_frame_in_window(self):
        observations = [
            _obs('t1', 0, [0, 0, 20, 20]),
            _obs('t1', 15, [0, 0, 20, 20]),
            _obs('t1', 16, [0, 0, 20, 20]),
            _obs('t1', 30, [0, 0, 20, 20]),
        ]
        plan = build_distinctness_plan(
            _state([_track('t1')], observations),
            time_base_num=1, time_base_den=30)
        self.assertIn(16, plan.sample_pts)
        self.assertNotIn(15, plan.sample_pts)


if __name__ == '__main__':
    unittest.main()
