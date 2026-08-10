"""Transactional video/project opening orchestration."""

import os

from libs.core.video_decoder import PreparedVideoOpen, VideoDecoderSession
from libs.core.video_project import (
    PROJECT_SUFFIX, VideoSourceMissing, default_project_path,
    initialize_project, load_project, read_project_source,
    validate_project_source,
)


def is_video_project(path):
    return os.fspath(path).lower().endswith(PROJECT_SUFFIX)


def prepare_video_open(path, project_path=None, read_only=False,
                       cancelled=None):
    """Fully prepare a new session without mutating application state."""
    requested = os.path.abspath(os.fspath(path))
    if is_video_project(requested):
        project_path = requested
        source = read_project_source(project_path)
        source_path = source.absolute_path
        if not os.path.isfile(source_path):
            raise VideoSourceMissing(
                'video source is missing: %s' % source_path)
        stream_index = source.stream_index
    else:
        source_path = requested
        stream_index = None
        if project_path is None and not read_only:
            project_path = default_project_path(source_path)
    decoder = VideoDecoderSession(
        source_path, stream_index=stream_index, cancelled=cancelled)
    try:
        initial = decoder.decode_first(cancelled=cancelled)
        if cancelled is not None and cancelled():
            raise RuntimeError('video opening was cancelled')
        if project_path is None:
            contents = None
            revision = 0
        elif os.path.exists(project_path):
            validate_project_source(
                project_path, source_path, decoder.fingerprint,
                update_path=not read_only)
            contents = load_project(project_path)
            revision = contents.revision
        else:
            draft = decoder.snapshot(project_path, initial, read_only=read_only)
            contents = initialize_project(project_path, draft)
            revision = contents.revision
        snapshot = decoder.snapshot(
            project_path, initial, revision=revision, read_only=read_only)
        return PreparedVideoOpen(
            snapshot=snapshot, decoder=decoder,
            tracks=contents.tracks if contents else (),
            observations=contents.observations if contents else (),
            frame_states=contents.frame_states if contents else (),
            classes=contents.classes if contents else ())
    except Exception:
        decoder.close()
        raise
