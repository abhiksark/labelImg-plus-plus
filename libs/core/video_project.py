"""Versioned SQLite project storage for smart-video annotations."""

from dataclasses import dataclass
import hashlib
import json
import os
import shutil
import sqlite3

from libs.core.video_types import (
    FrameStateRecord, ObservationRecord, TrackRecord, VideoFingerprint,
)


PROJECT_SUFFIX = '.labelimgpp.sqlite'
APPLICATION_ID = 0x4C495050  # ASCII-ish "LIPP", stored in SQLite's header.
SCHEMA_VERSION = 1
SAMPLE_BYTES = 1024 * 1024


class VideoProjectError(Exception):
    pass


class UnknownProjectError(VideoProjectError):
    pass


class NewerSchemaError(VideoProjectError):
    pass


class ProjectRevisionConflict(VideoProjectError):
    pass


class VideoSourceMissing(VideoProjectError):
    pass


class VideoSourceChanged(VideoProjectError):
    pass


@dataclass(frozen=True)
class ProjectContents:
    revision: int
    tracks: tuple
    observations: tuple
    frame_states: tuple
    classes: tuple


@dataclass(frozen=True)
class ProjectSource:
    relative_path: object
    absolute_path: str
    fingerprint: VideoFingerprint
    stream_index: int
    time_base_num: int
    time_base_den: int


def default_project_path(source_path):
    return os.path.abspath(os.fspath(source_path)) + PROJECT_SUFFIX


def fingerprint_video(path, cancelled=None):
    """Hash bounded samples while retaining cheap source stat metadata."""
    path = os.path.abspath(os.fspath(path))
    stat = os.stat(path)
    size = int(stat.st_size)
    offsets = (0, max(0, (size - SAMPLE_BYTES) // 2),
               max(0, size - SAMPLE_BYTES))
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for offset in offsets:
            if cancelled is not None and cancelled():
                return None
            stream.seek(offset)
            digest.update(stream.read(SAMPLE_BYTES))
    return VideoFingerprint(size, int(stat.st_mtime_ns), digest.hexdigest())


def _connect(path):
    connection = sqlite3.connect(path, timeout=5.0)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=5000')
    connection.execute('PRAGMA synchronous=FULL')
    return connection


def _validate_existing(path):
    uri = 'file:%s?mode=ro' % os.path.abspath(path)
    connection = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        application_id = connection.execute(
            'PRAGMA application_id').fetchone()[0]
        version = connection.execute('PRAGMA user_version').fetchone()[0]
    finally:
        connection.close()
    if application_id != APPLICATION_ID:
        raise UnknownProjectError(
            'not a LabelImg++ video project (application id %s)' %
            application_id)
    if version > SCHEMA_VERSION:
        raise NewerSchemaError(
            'project schema %s is newer than supported schema %s' %
            (version, SCHEMA_VERSION))
    if version != SCHEMA_VERSION:
        raise UnknownProjectError(
            'unsupported LabelImg++ video project schema %s' % version)


def _schema_sql():
    return """
    CREATE TABLE project_meta (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL,
        durable_revision INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE video_source (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        relative_path TEXT,
        absolute_path TEXT NOT NULL,
        fingerprint_size INTEGER NOT NULL,
        fingerprint_mtime_ns INTEGER NOT NULL,
        fingerprint_sha256 TEXT NOT NULL,
        stream_index INTEGER NOT NULL,
        time_base_num INTEGER NOT NULL,
        time_base_den INTEGER NOT NULL,
        duration_pts INTEGER,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        rotation INTEGER NOT NULL,
        codec TEXT NOT NULL
    );
    CREATE TABLE classes (
        class_index INTEGER PRIMARY KEY,
        label TEXT NOT NULL UNIQUE
    );
    CREATE TABLE tracks (
        track_id TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        shape_type TEXT NOT NULL CHECK (shape_type IN ('rectangle', 'polygon')),
        color_json TEXT NOT NULL,
        difficult INTEGER NOT NULL DEFAULT 0 CHECK (difficult IN (0, 1)),
        revision INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE observations (
        track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
        pts INTEGER NOT NULL,
        geometry_json TEXT,
        keypoints_json TEXT,
        present INTEGER NOT NULL DEFAULT 1 CHECK (present IN (0, 1)),
        source TEXT NOT NULL CHECK (source IN ('manual', 'tracker')),
        review_state TEXT NOT NULL CHECK (
            review_state IN ('accepted', 'pending', 'rejected')),
        anchor INTEGER NOT NULL DEFAULT 0 CHECK (anchor IN (0, 1)),
        quality REAL,
        revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (track_id, pts)
    );
    CREATE TABLE interpolation_segments (
        track_id TEXT NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
        start_pts INTEGER NOT NULL,
        end_pts INTEGER NOT NULL,
        PRIMARY KEY (track_id, start_pts, end_pts)
    );
    CREATE TABLE frame_state (
        pts INTEGER PRIMARY KEY,
        verified INTEGER NOT NULL DEFAULT 0 CHECK (verified IN (0, 1)),
        revision INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX observations_pts_idx ON observations(pts);
    CREATE INDEX observations_review_idx
        ON observations(review_state, pts);
    """


def initialize_project(path, session):
    """Create schema v1 after a source and its first frame were decoded."""
    path = os.path.abspath(os.fspath(path))
    if os.path.exists(path):
        _validate_existing(path)
        return load_project(path)
    parent = os.path.dirname(path) or '.'
    os.makedirs(parent, exist_ok=True)
    connection = _connect(path)
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('BEGIN IMMEDIATE')
        connection.executescript(_schema_sql())
        connection.execute('PRAGMA application_id=%d' % APPLICATION_ID)
        connection.execute('PRAGMA user_version=%d' % SCHEMA_VERSION)
        connection.execute(
            'INSERT INTO project_meta '
            '(singleton, schema_version, durable_revision) VALUES (1, ?, 0)',
            (SCHEMA_VERSION,))
        source = os.path.abspath(session.source_path)
        try:
            relative = os.path.relpath(source, os.path.dirname(path))
        except ValueError:
            relative = None
        connection.execute(
            'INSERT INTO video_source ('
            'singleton, relative_path, absolute_path, fingerprint_size, '
            'fingerprint_mtime_ns, fingerprint_sha256, stream_index, '
            'time_base_num, time_base_den, duration_pts, width, height, '
            'rotation, codec) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (relative, source, session.fingerprint.size,
             session.fingerprint.mtime_ns,
             session.fingerprint.sampled_sha256, session.stream_index,
             session.time_base_num, session.time_base_den,
             session.duration_pts, session.width, session.height,
             session.rotation, session.codec))
        connection.commit()
    except Exception:
        connection.rollback()
        connection.close()
        try:
            os.remove(path)
        except OSError:
            pass
        raise
    finally:
        if connection:
            connection.close()
    return load_project(path)


def validate_project_source(path, source_path, fingerprint, update_path=True):
    """Validate content and optionally repair a moved source path."""
    _validate_existing(path)
    connection = _connect(path)
    try:
        row = connection.execute(
            'SELECT fingerprint_size, fingerprint_mtime_ns, '
            'fingerprint_sha256, absolute_path FROM video_source '
            'WHERE singleton=1').fetchone()
        stored = VideoFingerprint(int(row[0]), int(row[1]), row[2])
        if not stored.content_matches(fingerprint):
            raise VideoSourceChanged(
                'video content does not match the project fingerprint')
        source_path = os.path.abspath(source_path)
        if update_path and source_path != os.path.abspath(row[3]):
            relative = os.path.relpath(source_path, os.path.dirname(path))
            with connection:
                connection.execute(
                    'UPDATE video_source SET relative_path=?, '
                    'absolute_path=?, fingerprint_mtime_ns=? '
                    'WHERE singleton=1',
                    (relative, source_path, fingerprint.mtime_ns))
    finally:
        connection.close()


def read_project_source(path):
    _validate_existing(path)
    connection = _connect(path)
    try:
        row = connection.execute(
            'SELECT relative_path, absolute_path, fingerprint_size, '
            'fingerprint_mtime_ns, fingerprint_sha256, stream_index, '
            'time_base_num, time_base_den FROM video_source '
            'WHERE singleton=1').fetchone()
    finally:
        connection.close()
    if row is None:
        raise UnknownProjectError('project has no video source')
    relative_path, absolute_path = row[0], row[1]
    candidates = []
    if relative_path:
        candidates.append(os.path.abspath(os.path.join(
            os.path.dirname(path), relative_path)))
    candidates.append(os.path.abspath(absolute_path))
    source_path = next((item for item in candidates if os.path.isfile(item)),
                       candidates[0])
    return ProjectSource(
        relative_path, source_path,
        VideoFingerprint(int(row[2]), int(row[3]), row[4]),
        int(row[5]), int(row[6]), int(row[7]))


def _track_from_row(row):
    return TrackRecord(
        track_id=row[0], label=row[1], shape_type=row[2],
        color=tuple(json.loads(row[3])), difficult=bool(row[4]),
        revision=int(row[5]))


def _observation_from_row(row):
    return ObservationRecord(
        track_id=row[0], pts=int(row[1]),
        geometry=(json.loads(row[2]) if row[2] is not None else None),
        keypoints=(json.loads(row[3]) if row[3] is not None else None),
        present=bool(row[4]), source=row[5], review_state=row[6],
        anchor=bool(row[7]), quality=row[8], revision=int(row[9]))


def load_project(path):
    _validate_existing(path)
    connection = _connect(path)
    try:
        revision = int(connection.execute(
            'SELECT durable_revision FROM project_meta WHERE singleton=1'
        ).fetchone()[0])
        tracks = tuple(_track_from_row(row) for row in connection.execute(
            'SELECT track_id, label, shape_type, color_json, difficult, '
            'revision FROM tracks ORDER BY rowid'))
        observations = tuple(_observation_from_row(row) for row in
                             connection.execute(
            'SELECT track_id, pts, geometry_json, keypoints_json, present, '
            'source, review_state, anchor, quality, revision '
            'FROM observations ORDER BY pts, track_id'))
        frame_states = tuple(FrameStateRecord(int(row[0]), bool(row[1]),
                                              int(row[2])) for row in
                             connection.execute(
            'SELECT pts, verified, revision FROM frame_state ORDER BY pts'))
        classes = tuple(row[0] for row in connection.execute(
            'SELECT label FROM classes ORDER BY class_index'))
        return ProjectContents(
            revision, tracks, observations, frame_states, classes)
    finally:
        connection.close()


def _rebuild_segments(connection, track_id):
    connection.execute(
        'DELETE FROM interpolation_segments WHERE track_id=?', (track_id,))
    rows = connection.execute(
        "SELECT pts, present FROM observations WHERE track_id=? "
        "AND source='manual' AND review_state='accepted' AND anchor=1 "
        'ORDER BY pts', (track_id,)).fetchall()
    for previous, current in zip(rows, rows[1:]):
        if bool(previous[1]) and bool(current[1]):
            connection.execute(
                'INSERT INTO interpolation_segments '
                '(track_id, start_pts, end_pts) VALUES (?, ?, ?)',
                (track_id, int(previous[0]), int(current[0])))


def save_project_delta(request, cancelled=None, begin_commit=None):
    """Apply one immutable revision delta in a guarded transaction."""
    _validate_existing(request.project_path)
    if cancelled is not None and cancelled():
        return None
    connection = _connect(request.project_path)
    try:
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('BEGIN IMMEDIATE')
        revision = int(connection.execute(
            'SELECT durable_revision FROM project_meta WHERE singleton=1'
        ).fetchone()[0])
        if revision != request.expected_durable_revision:
            raise ProjectRevisionConflict(
                'expected durable revision %s, found %s' %
                (request.expected_durable_revision, revision))
        for track_id, pts in request.deleted_observations:
            connection.execute(
                'DELETE FROM observations WHERE track_id=? AND pts=?',
                (track_id, int(pts)))
        for track_id in request.deleted_tracks:
            connection.execute(
                'DELETE FROM tracks WHERE track_id=?', (track_id,))
        for track in request.tracks:
            connection.execute(
                'INSERT INTO tracks (track_id, label, shape_type, '
                'color_json, difficult, revision) VALUES (?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(track_id) DO UPDATE SET label=excluded.label, '
                'shape_type=excluded.shape_type, color_json=excluded.color_json, '
                'difficult=excluded.difficult, revision=excluded.revision',
                (track.track_id, track.label, track.shape_type,
                 json.dumps(list(track.color), separators=(',', ':')),
                 int(track.difficult), int(track.revision)))
        for observation in request.observations:
            connection.execute(
                'INSERT INTO observations (track_id, pts, geometry_json, '
                'keypoints_json, present, source, review_state, anchor, '
                'quality, revision) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(track_id, pts) DO UPDATE SET '
                'geometry_json=excluded.geometry_json, '
                'keypoints_json=excluded.keypoints_json, '
                'present=excluded.present, source=excluded.source, '
                'review_state=excluded.review_state, anchor=excluded.anchor, '
                'quality=excluded.quality, revision=excluded.revision',
                (observation.track_id, int(observation.pts),
                 (json.dumps(observation.geometry, separators=(',', ':'))
                  if observation.geometry is not None else None),
                 (json.dumps(observation.keypoints, separators=(',', ':'))
                  if observation.keypoints is not None else None),
                 int(observation.present), observation.source,
                 observation.review_state, int(observation.anchor),
                 observation.quality, int(observation.revision)))
        for state in request.frame_states:
            connection.execute(
                'INSERT INTO frame_state (pts, verified, revision) '
                'VALUES (?, ?, ?) ON CONFLICT(pts) DO UPDATE SET '
                'verified=excluded.verified, revision=excluded.revision',
                (int(state.pts), int(state.verified), int(state.revision)))
        if request.classes:
            connection.execute('DELETE FROM classes')
            connection.executemany(
                'INSERT INTO classes (class_index, label) VALUES (?, ?)',
                tuple(enumerate(request.classes)))
        touched = set(request.touched_tracks)
        touched.update(item.track_id for item in request.observations)
        touched.update(item.track_id for item in request.tracks)
        for track_id in sorted(touched):
            if connection.execute(
                    'SELECT 1 FROM tracks WHERE track_id=?',
                    (track_id,)).fetchone():
                _rebuild_segments(connection, track_id)
        connection.execute(
            'UPDATE project_meta SET durable_revision=? WHERE singleton=1',
            (int(request.target_revision),))
        if cancelled is not None and cancelled():
            connection.rollback()
            return None
        if begin_commit is not None:
            begin_commit()
        connection.commit()
        return request.target_revision
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def checkpoint_project(path):
    _validate_existing(path)
    connection = _connect(path)
    try:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchall()
    finally:
        connection.close()


def save_project_as(source, destination):
    """Use SQLite backup so a live WAL project is copied consistently."""
    _validate_existing(source)
    destination = os.path.abspath(destination)
    if os.path.exists(destination):
        raise VideoProjectError('destination project already exists')
    os.makedirs(os.path.dirname(destination) or '.', exist_ok=True)
    source_connection = _connect(source)
    destination_connection = _connect(destination)
    try:
        source_connection.backup(destination_connection)
    except Exception:
        destination_connection.close()
        try:
            os.remove(destination)
        except OSError:
            pass
        raise
    finally:
        source_connection.close()
        try:
            destination_connection.close()
        except Exception:
            pass
    _validate_existing(destination)
    return destination


def remove_owned_staging_tree(path):
    """Small shared helper; only explicitly owned staging trees are removed."""
    if os.path.basename(path).startswith('.labelimgpp-export-'):
        shutil.rmtree(path, ignore_errors=True)
