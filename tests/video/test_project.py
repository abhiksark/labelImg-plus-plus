import os
import sqlite3

import pytest

from libs.core import video_project
from libs.core.video_project import (
    APPLICATION_ID, SCHEMA_VERSION, ProjectRevisionConflict,
    UnknownProjectError, default_project_path, fingerprint_video,
    initialize_project, load_project, read_project_source, save_project_as,
    save_project_delta, validate_project_source,
)
from libs.core.video_types import (
    FrameStateRecord, ObservationRecord, TrackGapRecord, TrackRecord,
    VideoSaveRequest,
)


class _Session:
    def __init__(self, source_path, fingerprint):
        self.source_path = source_path
        self.fingerprint = fingerprint
        self.stream_index = 0
        self.time_base_num = 1
        self.time_base_den = 30
        self.duration_pts = 10
        self.width = 64
        self.height = 48
        self.rotation = 0
        self.codec = 'test'


def _project(tmp_path):
    source = tmp_path / 'clip.mp4'
    source.write_bytes(b'a' * (2 * 1024 * 1024 + 31))
    fingerprint = fingerprint_video(source)
    project = default_project_path(source)
    initialize_project(project, _Session(str(source), fingerprint))
    return source, project, fingerprint


def _downgrade_to_v1(project):
    connection = sqlite3.connect(project)
    try:
        connection.execute('DROP TABLE track_gaps')
        connection.execute(
            'UPDATE project_meta SET schema_version=1 WHERE singleton=1')
        connection.execute('PRAGMA user_version=1')
        connection.commit()
    finally:
        connection.close()


def _raw_observation_rows(project):
    connection = sqlite3.connect(project)
    try:
        return connection.execute(
            'SELECT track_id, pts, geometry_json, keypoints_json, present, '
            'source, review_state, anchor, quality, revision '
            'FROM observations ORDER BY pts').fetchall()
    finally:
        connection.close()


def test_project_schema_has_fixed_identity_and_safe_pragmas(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    connection = sqlite3.connect(project)
    try:
        assert connection.execute('PRAGMA application_id').fetchone()[0] == \
            APPLICATION_ID
        assert connection.execute('PRAGMA user_version').fetchone()[0] == \
            SCHEMA_VERSION
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            'project_meta', 'video_source', 'classes', 'tracks',
            'observations', 'interpolation_segments', 'frame_state',
            'track_gaps',
        } <= tables
    finally:
        connection.close()


def test_revision_guard_rolls_back_conflicting_delta(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord('track-1', 'car', 'rectangle', (1, 2, 3, 255))
    observation = ObservationRecord(
        'track-1', 0, [1, 2, 10, 20], revision=1)
    request = VideoSaveRequest(
        project, 0, 1, tracks=(track,), observations=(observation,),
        touched_tracks=('track-1',), classes=('car',))
    assert save_project_delta(request) == 1
    with pytest.raises(ProjectRevisionConflict):
        save_project_delta(VideoSaveRequest(
            project, 0, 2,
            tracks=(TrackRecord('track-2', 'person', 'rectangle',
                                (2, 3, 4, 255)),)))
    contents = load_project(project)
    assert contents.revision == 1
    assert [track.track_id for track in contents.tracks] == ['track-1']
    assert contents.observations == (observation,)
    assert contents.classes == ('car',)


def test_continuous_save_roundtrip_preserves_video_project_semantics(tmp_path):
    """A second project save preserves prior geometry, class, and verification."""
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord('track-1', 'car', 'rectangle', (1, 2, 3, 255))
    first = ObservationRecord(
        'track-1', 0, [1, 2, 10, 20], source='manual',
        review_state='accepted', anchor=True, revision=1)
    verified = FrameStateRecord(0, True, revision=1)
    assert save_project_delta(VideoSaveRequest(
        project, 0, 1, tracks=(track,), observations=(first,),
        frame_states=(verified,), touched_tracks=('track-1',),
        classes=('car',))) == 1

    loaded = load_project(project)
    second = ObservationRecord(
        'track-1', 5, [2, 3, 12, 24], source='manual',
        review_state='accepted', anchor=True, revision=2)
    assert save_project_delta(VideoSaveRequest(
        project, loaded.revision, 2, observations=(second,),
        touched_tracks=('track-1',))) == 2

    reopened = load_project(project)
    assert reopened.revision == 2
    assert reopened.tracks == (track,)
    assert reopened.observations == (first, second)
    assert reopened.frame_states == (verified,)
    assert reopened.classes == ('car',)


def test_gap_delta_insert_replace_delete_and_revision_conflict(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord(
        'track-1', 'car', 'rectangle', (1, 2, 3, 255), revision=1)
    first = VideoSaveRequest(project, 0, 1, tracks=(track,))
    assert save_project_delta(first) == 1
    gap = TrackGapRecord(
        'track-1', 10, 20, 'occluded', 'opencv', revision=2)
    assert save_project_delta(VideoSaveRequest(
        project, 1, 2, gaps=(gap,), touched_tracks=('track-1',))) == 2
    assert load_project(project).gaps == (gap,)

    replacement = TrackGapRecord(
        'track-1', 10, 20, 'scene_cut', 'opencv', revision=3)
    assert save_project_delta(VideoSaveRequest(
        project, 2, 3, gaps=(replacement,),
        touched_tracks=('track-1',))) == 3
    assert load_project(project).gaps == (replacement,)

    with pytest.raises(ProjectRevisionConflict):
        save_project_delta(VideoSaveRequest(
            project, 2, 4,
            deleted_gaps=(('track-1', 10, 20),)))
    contents = load_project(project)
    assert contents.revision == 3
    assert contents.gaps == (replacement,)

    assert save_project_delta(VideoSaveRequest(
        project, 3, 4,
        deleted_gaps=(('track-1', 10, 20),),
        touched_tracks=('track-1',))) == 4
    assert load_project(project).gaps == ()


def test_gap_schema_uses_inclusive_validated_pts_bounds(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord('track-1', 'car', 'rectangle', (1, 2, 3, 255))
    save_project_delta(VideoSaveRequest(project, 0, 1, tracks=(track,)))
    connection = sqlite3.connect(project)
    try:
        connection.execute(
            "INSERT INTO track_gaps VALUES "
            "('track-1', 10, 10, 'occluded', 'opencv', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO track_gaps VALUES "
                "('track-1', 30, 20, 'occluded', 'opencv', 1)")
    finally:
        connection.rollback()
        connection.close()


def test_writable_v1_migrates_transactionally_without_changing_observations(
        tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord('track-1', 'car', 'rectangle', (1, 2, 3, 255))
    observations = (
        ObservationRecord(
            'track-1', 1, [1, 2, 3, 4], source='manual',
            review_state='accepted', anchor=True, revision=1),
        ObservationRecord(
            'track-1', 2, [2, 3, 4, 5], source='tracker',
            review_state='pending', anchor=False, quality=.8, revision=1),
        ObservationRecord(
            'track-1', 3, [3, 4, 5, 6], source='tracker',
            review_state='rejected', anchor=False, quality=.2, revision=1),
    )
    save_project_delta(VideoSaveRequest(
        project, 0, 1, tracks=(track,), observations=observations,
        touched_tracks=('track-1',)))
    _downgrade_to_v1(project)
    before = _raw_observation_rows(project)

    contents = load_project(project)

    assert contents.observations == observations
    assert contents.gaps == ()
    assert contents.read_only is False
    assert contents.warning is None
    assert _raw_observation_rows(project) == before
    connection = sqlite3.connect(project)
    try:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='track_gaps'"
        ).fetchone() == ('track_gaps',)
        assert connection.execute(
            'SELECT schema_version FROM project_meta').fetchone()[0] == 2
    finally:
        connection.close()


def test_read_only_v1_loads_with_empty_gap_projection(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    _downgrade_to_v1(project)

    contents = load_project(project, read_only=True)

    assert contents.gaps == ()
    assert contents.read_only is True
    assert contents.warning is None
    connection = sqlite3.connect(project)
    try:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
    finally:
        connection.close()


def test_failed_v1_migration_rolls_back_and_reopens_read_only(
        tmp_path, monkeypatch):
    _source, project, _fingerprint = _project(tmp_path)
    track = TrackRecord('track-1', 'car', 'rectangle', (1, 2, 3, 255))
    observation = ObservationRecord(
        'track-1', 1, [1, 2, 3, 4], source='tracker',
        review_state='pending', anchor=False, quality=.75, revision=1)
    save_project_delta(VideoSaveRequest(
        project, 0, 1, tracks=(track,), observations=(observation,),
        touched_tracks=('track-1',)))
    _downgrade_to_v1(project)
    before = _raw_observation_rows(project)
    create_schema = video_project._create_track_gaps_schema

    def fail_after_schema(connection):
        create_schema(connection)
        raise sqlite3.OperationalError('simulated full disk')

    monkeypatch.setattr(
        video_project, '_create_track_gaps_schema', fail_after_schema)
    contents = load_project(project)

    assert contents.read_only is True
    assert 'reopened read-only' in contents.warning
    assert 'free disk space' in contents.warning
    assert contents.observations == (observation,)
    assert _raw_observation_rows(project) == before
    connection = sqlite3.connect(project)
    try:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='track_gaps'"
        ).fetchone() is None
        assert connection.execute(
            'SELECT schema_version FROM project_meta').fetchone()[0] == 1
    finally:
        connection.close()


def test_moved_source_is_repaired_when_sampled_content_matches(tmp_path):
    source, project, fingerprint = _project(tmp_path)
    moved_dir = tmp_path / 'moved'
    moved_dir.mkdir()
    moved = moved_dir / source.name
    source.rename(moved)
    stat = moved.stat()
    os.utime(moved, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1000))
    moved_fingerprint = fingerprint_video(moved)
    assert fingerprint.content_matches(moved_fingerprint)
    validate_project_source(project, moved, moved_fingerprint)
    assert read_project_source(project).absolute_path == str(moved)


def test_unknown_application_id_is_rejected_without_modification(tmp_path):
    path = tmp_path / 'unknown.sqlite'
    connection = sqlite3.connect(str(path))
    connection.execute('CREATE TABLE sentinel (value TEXT)')
    connection.execute("INSERT INTO sentinel VALUES ('unchanged')")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    with pytest.raises(UnknownProjectError):
        load_project(str(path))
    assert path.read_bytes() == before


def test_save_as_uses_consistent_sqlite_backup(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    target = str(tmp_path / 'copy.labelimgpp.sqlite')
    assert save_project_as(project, target) == target
    assert load_project(target) == load_project(project)
