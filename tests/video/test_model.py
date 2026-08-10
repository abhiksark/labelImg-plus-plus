from libs.core.video_model import VideoProjectModel
from libs.core.video_types import ObservationRecord


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
