import pytest

from libs.core.video_model import VideoProjectModel
from libs.core.video_types import (
    ObservationRecord, PropagationResult, TrackGapRecord,
)


def _track(model, shape_type='rectangle'):
    return model.create_track(
        'car', shape_type, (0, 255, 0, 255), track_id='track-1')


def test_rectangle_interpolates_by_pts_and_keypoint_visibility_is_nearest():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(
        track.track_id, 100, [0, 0, 10, 10],
        keypoints=[[1, 2, 1], [3, 4, 2]])
    model.upsert_manual(
        track.track_id, 300, [10, 20, 30, 40],
        keypoints=[[11, 12, 2], [13, 14, 0]])
    materialized = model.materialize_one(track.track_id, 150)
    assert materialized.render_state == 'interpolation'
    assert materialized.observation.geometry == [2.5, 5.0, 15.0, 17.5]
    assert materialized.observation.keypoints == [
        [3.5, 4.5, 1], [5.5, 6.5, 2]]


def test_polygon_is_never_interpolated():
    model = VideoProjectModel()
    track = _track(model, shape_type='polygon')
    model.upsert_manual(track.track_id, 0, [[0, 0], [1, 0], [1, 1]])
    model.upsert_manual(track.track_id, 10, [[2, 2], [3, 2], [3, 3]])
    assert model.materialize_one(track.track_id, 5) is None


def test_presence_anchor_terminates_interpolation_until_new_present_anchor():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    model.upsert_manual(track.track_id, 5, None, present=False)
    model.upsert_manual(track.track_id, 10, [10, 10, 20, 20])
    assert model.materialize_one(track.track_id, 3) is None
    assert model.materialize_one(track.track_id, 5) is None
    assert model.materialize_one(track.track_id, 7) is None


def test_manual_and_review_precedence_over_generated_state():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    model.upsert_manual(track.track_id, 20, [20, 20, 30, 30])
    pending = ObservationRecord(
        track.track_id, 10, [9, 9, 19, 19], source='tracker',
        review_state='pending', anchor=False)
    model.upsert_tracker(pending)
    assert model.materialize_one(track.track_id, 10).render_state == 'pending'
    model.upsert_manual(track.track_id, 10, [8, 8, 18, 18])
    exact = model.materialize_one(track.track_id, 10)
    assert exact.render_state == 'exact'
    assert exact.observation.source == 'manual'
    assert exact.observation.geometry == [8, 8, 18, 18]


def test_accepted_tracker_is_exact_but_not_interpolation_anchor():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    model.upsert_tracker(ObservationRecord(
        track.track_id, 10, [10, 10, 20, 20], source='tracker',
        review_state='accepted', anchor=False))
    assert model.materialize_one(track.track_id, 10).render_state == 'exact'
    assert model.materialize_one(track.track_id, 5) is None


def test_deleting_interpolation_writes_absence_but_exact_delete_removes():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    model.upsert_manual(track.track_id, 10, [10, 10, 20, 20])
    model.delete_occurrence(track.track_id, 5)
    absence = model.observations[(track.track_id, 5)]
    assert absence.present is False
    model.delete_occurrence(track.track_id, 5)
    assert (track.track_id, 5) not in model.observations


def test_save_delta_coalesces_only_mutations_newer_than_completed_revision():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    first = model.build_save_request('/tmp/project.sqlite')
    model.upsert_manual(track.track_id, 10, [1, 1, 11, 11])
    model.mark_saved(first.target_revision)
    assert model.dirty
    second = model.build_save_request('/tmp/project.sqlite')
    assert second.expected_durable_revision == first.target_revision
    assert [item.pts for item in second.observations] == [10]
    model.mark_saved(second.target_revision)
    assert not model.dirty


def test_rerun_replaces_pending_and_rejected_but_never_accepted_or_manual():
    model = VideoProjectModel()
    track = _track(model)
    pending = ObservationRecord(
        track.track_id, 10, [1, 1, 11, 11], source='tracker',
        review_state='pending', anchor=False)
    model.upsert_tracker(pending)
    replacement = ObservationRecord(
        track.track_id, 10, [2, 2, 12, 12], source='tracker',
        review_state='pending', anchor=False)
    assert model.upsert_tracker(replacement).geometry == [2, 2, 12, 12]
    model.review(track.track_id, 10, 'rejected')
    assert model.upsert_tracker(replacement).review_state == 'pending'
    model.review(track.track_id, 10, 'accepted')
    accepted = model.observations[(track.track_id, 10)]
    assert model.upsert_tracker(pending) == accepted
    model.upsert_manual(track.track_id, 10, [3, 3, 13, 13])
    manual = model.observations[(track.track_id, 10)]
    assert model.upsert_tracker(pending) == manual


def test_gaps_round_trip_through_snapshot_restore_and_save_delta():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 0, [0, 0, 10, 10])
    model.upsert_manual(track.track_id, 20, [20, 20, 30, 30])
    baseline = model.snapshot_state()

    first = model.upsert_gap(TrackGapRecord(
        track.track_id, 5, 10, 'occluded', 'opencv'))
    assert model.materialize_one(track.track_id, 7) is None
    request = model.build_save_request('/tmp/project.sqlite')
    assert request.gaps == (first,)
    assert request.deleted_gaps == ()

    model.restore_state(baseline)
    assert model.gaps == {}
    restored = model.build_save_request('/tmp/project.sqlite')
    assert restored.deleted_gaps == ((track.track_id, 5, 10),)


def test_gap_replacement_deletion_and_track_cascade_are_revisioned():
    model = VideoProjectModel()
    track = _track(model)
    first = model.upsert_gap(TrackGapRecord(
        track.track_id, 5, 10, 'occluded', 'opencv'))
    replacement = model.upsert_gap(TrackGapRecord(
        track.track_id, 5, 10, 'scene_cut', 'opencv'))
    assert replacement.revision > first.revision
    assert tuple(model.gaps.values()) == (replacement,)
    assert model.delete_gap(track.track_id, 5, 10) is True
    assert model.delete_gap(track.track_id, 5, 10) is False
    assert model.build_save_request(
        '/tmp/project.sqlite').deleted_gaps == ((track.track_id, 5, 10),)

    model.upsert_gap(TrackGapRecord(
        track.track_id, 20, 30, 'out_of_frame', 'opencv'))
    model.delete_track(track.track_id)
    assert model.gaps == {}


def test_propagation_result_is_one_revision_and_protects_manual_anchors():
    model = VideoProjectModel()
    track = _track(model)
    manual = model.upsert_manual(track.track_id, 10, [10, 0, 20, 10])
    previous_revision = model.revision
    applied = model.apply_propagation_result(PropagationResult(
        1, 2, previous_revision,
        observations=(
            ObservationRecord(
                track.track_id, 5, [5, 0, 15, 10], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 10, [99, 99, 100, 100], source='tracker',
                review_state='accepted', anchor=False),
        ),
        gaps=(TrackGapRecord(
            track.track_id, 15, 20, 'occluded', 'opencv'),)))
    assert model.revision == previous_revision + 1
    assert model.observations[(track.track_id, 10)] == manual
    assert model.observations[(track.track_id, 5)].revision == model.revision
    assert model.gaps[(track.track_id, 15, 20)].revision == model.revision
    assert model.tracks[track.track_id].revision == model.revision
    assert [item.pts for item in applied.observations] == [5]


def test_completed_propagation_is_pending_until_review_in_one_revision():
    model = VideoProjectModel()
    track = _track(model)
    baseline_revision = model.revision

    staged = model.stage_propagation_result(PropagationResult(
        1, 2, baseline_revision,
        observations=(
            ObservationRecord(
                track.track_id, 10, [2, 2, 12, 12], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 20, [3, 3, 13, 13], source='tracker',
                review_state='accepted', anchor=False),
        )))

    assert model.revision == baseline_revision + 1
    assert staged.observations
    assert all(item.review_state == 'pending'
               for item in staged.observations)
    assert model.dirty

    review_revision = model.revision
    reviewed = model.review_many(
        ((item.track_id, item.pts) for item in staged.observations),
        'accepted')
    assert model.revision == review_revision + 1
    assert len(reviewed) == 2
    assert all(model.observations[(item.track_id, item.pts)].review_state
               == 'accepted' for item in staged.observations)


def test_staging_preserves_manual_and_accepted_barriers_while_storing_gaps():
    model = VideoProjectModel()
    track = _track(model)
    manual = model.upsert_manual(
        track.track_id, 10, [1, 1, 11, 11])
    accepted = model.upsert_tracker(ObservationRecord(
        track.track_id, 20, [2, 2, 12, 12], source='tracker',
        review_state='accepted', anchor=False))
    baseline_revision = model.revision

    staged = model.stage_propagation_result(PropagationResult(
        2, 3, baseline_revision,
        observations=(
            ObservationRecord(
                track.track_id, 10, [90, 90, 99, 99], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 20, [80, 80, 89, 89], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 30, [3, 3, 13, 13], source='tracker',
                review_state='accepted', anchor=False),
        ),
        gaps=(
            TrackGapRecord(track.track_id, 5, 25, 'occluded', 'opencv'),
            TrackGapRecord(track.track_id, 40, 45, 'cancelled', 'opencv'),
        )))

    assert model.revision == baseline_revision + 1
    assert model.observations[(track.track_id, 10)] == manual
    assert model.observations[(track.track_id, 20)] == accepted
    assert model.observations[(track.track_id, 30)].review_state == 'pending'
    assert [item.pts for item in staged.observations] == [30]
    assert set(model.gaps) == {
        (track.track_id, 5, 25),
        (track.track_id, 40, 45),
    }


def test_staging_and_many_review_validate_before_any_revision_advances():
    model = VideoProjectModel()
    track = _track(model)
    baseline = model.snapshot_state()
    revision = model.revision
    with pytest.raises(ValueError, match='model revision'):
        model.stage_propagation_result(PropagationResult(
            1, 1, revision - 1,
            observations=(ObservationRecord(
                track.track_id, 5, [0, 0, 10, 10], source='tracker',
                review_state='accepted', anchor=False),)))
    assert model.revision == revision
    assert model.snapshot_state() == baseline

    with pytest.raises(KeyError):
        model.stage_propagation_result(PropagationResult(
            1, 1, revision,
            observations=(ObservationRecord(
                track.track_id, 5, [0, 0, 10, 10], source='tracker',
                review_state='accepted', anchor=False),),
            gaps=(TrackGapRecord(
                'missing', 6, 7, 'occluded', 'opencv'),)))
    assert model.revision == revision
    assert model.snapshot_state() == baseline

    pending = model.upsert_tracker(ObservationRecord(
        track.track_id, 5, [0, 0, 10, 10], source='tracker',
        review_state='pending', anchor=False))
    review_revision = model.revision
    with pytest.raises(KeyError):
        model.review_many(
            ((pending.track_id, pending.pts), ('missing', 99)), 'accepted')
    assert model.revision == review_revision
    assert model.observations[(pending.track_id, pending.pts)] == pending


def test_propagation_gap_removes_stale_tracker_but_not_manual_data():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_tracker(ObservationRecord(
        track.track_id, 5, [5, 0, 15, 10], source='tracker',
        review_state='accepted', anchor=False))
    manual = model.upsert_manual(track.track_id, 7, [7, 0, 17, 10])
    model.apply_propagation_result(PropagationResult(
        1, 1, model.revision,
        gaps=(TrackGapRecord(
            track.track_id, 4, 8, 'scene_cut', 'opencv'),)))
    assert (track.track_id, 5) not in model.observations
    assert model.observations[(track.track_id, 7)] == manual
    assert model.materialize_one(track.track_id, 6) is None


def test_invalid_propagation_result_cannot_partially_mutate_model():
    model = VideoProjectModel()
    track = _track(model)
    baseline = model.snapshot_state()
    revision = model.revision
    with pytest.raises(KeyError):
        model.apply_propagation_result(PropagationResult(
            1, 1, revision,
            observations=(ObservationRecord(
                track.track_id, 5, [0, 0, 10, 10], source='tracker',
                review_state='accepted', anchor=False),),
            gaps=(TrackGapRecord(
                'missing', 6, 7, 'occluded', 'opencv'),)))
    assert model.revision == revision
    assert model.snapshot_state() == baseline


def test_regeneration_replaces_only_generated_data_inside_open_segments():
    model = VideoProjectModel()
    track = _track(model)
    for pts in (0, 10, 20):
        model.upsert_manual(track.track_id, pts, [pts, 0, pts + 10, 10])
    for pts in (3, 7, 13, 17, 25):
        model.upsert_tracker(ObservationRecord(
            track.track_id, pts, [pts, 0, pts + 10, 10],
            source='tracker', review_state='accepted', anchor=False))
    model.upsert_gap(TrackGapRecord(
        track.track_id, 4, 6, 'occluded', 'opencv'))
    other = model.create_track(
        'person', 'rectangle', (255, 0, 0, 255), track_id='track-2')
    other_value = model.upsert_tracker(ObservationRecord(
        other.track_id, 7, [0, 0, 5, 5], source='tracker',
        review_state='accepted', anchor=False))
    before_revision = model.revision

    applied = model.apply_regeneration_result(PropagationResult(
        2, 3, before_revision,
        observations=(ObservationRecord(
            track.track_id, 5, [50, 0, 60, 10], source='tracker',
            review_state='accepted', anchor=False),),
        gaps=(TrackGapRecord(
            track.track_id, 14, 18, 'scene_cut', 'opencv'),)),
        track.track_id, ((0, 10), (10, 20)))

    assert model.revision == before_revision + 1
    assert set(pts for tid, pts in model.observations if tid == track.track_id) \
        == {0, 5, 10, 20, 25}
    assert model.observations[(track.track_id, 5)].geometry[0] == 50
    assert model.observations[(other.track_id, 7)] == other_value
    assert set(model.gaps) == {(track.track_id, 14, 18)}
    assert applied.observations[0].revision == model.revision


def test_regeneration_filters_segment_boundaries_and_rejects_other_tracks():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_manual(track.track_id, 10, [0, 0, 10, 10])
    result = model.apply_regeneration_result(PropagationResult(
        1, 1, model.revision,
        observations=(
            ObservationRecord(
                track.track_id, 0, [0, 0, 10, 10], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 5, [5, 0, 15, 10], source='tracker',
                review_state='accepted', anchor=False),
            ObservationRecord(
                track.track_id, 10, [10, 0, 20, 10], source='tracker',
                review_state='accepted', anchor=False),
        )), track.track_id, ((0, 10),))
    assert [item.pts for item in result.observations] == [5]
    assert (track.track_id, 0) not in model.observations
    assert model.observations[(track.track_id, 10)].source == 'manual'

    baseline = model.snapshot_state()
    with pytest.raises(ValueError, match='another track'):
        model.apply_regeneration_result(PropagationResult(
            2, 1, model.revision,
            observations=(ObservationRecord(
                'other', 6, [0, 0, 1, 1], source='tracker',
                review_state='accepted', anchor=False),)),
            track.track_id, ((0, 10),))
    assert model.snapshot_state() == baseline


def test_regeneration_preserves_gap_portions_outside_segments():
    model = VideoProjectModel()
    track = _track(model)
    model.upsert_gap(TrackGapRecord(
        track.track_id, 0, 20, 'occluded', 'opencv'))
    model.apply_regeneration_result(
        PropagationResult(1, 1, model.revision),
        track.track_id, ((5, 15),))
    assert set(model.gaps) == {
        (track.track_id, 0, 5),
        (track.track_id, 15, 20),
    }
