import os
import sqlite3

import pytest

from libs.core.video_project import (
    APPLICATION_ID, ProjectRevisionConflict, UnknownProjectError,
    default_project_path, fingerprint_video, initialize_project, load_project,
    read_project_source, save_project_as, save_project_delta,
    validate_project_source,
)
from libs.core.video_types import (
    ObservationRecord, TrackRecord, VideoSaveRequest,
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


def test_project_schema_has_fixed_identity_and_safe_pragmas(tmp_path):
    _source, project, _fingerprint = _project(tmp_path)
    connection = sqlite3.connect(project)
    try:
        assert connection.execute('PRAGMA application_id').fetchone()[0] == \
            APPLICATION_ID
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 1
        assert connection.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            'project_meta', 'video_source', 'classes', 'tracks',
            'observations', 'interpolation_segments', 'frame_state',
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
