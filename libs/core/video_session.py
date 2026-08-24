"""Transactional video/project opening orchestration."""

from dataclasses import dataclass
import os

from libs.core.video_decoder import PreparedVideoOpen, VideoDecoderSession
from libs.core.video_project import (
    PROJECT_SUFFIX, VideoSourceMissing, default_project_path,
    initialize_project, load_project, read_project_source,
    validate_project_source,
)


@dataclass(frozen=True)
class VideoOpenProblem:
    kind: str
    message: str


def is_video_project(path):
    return os.fspath(path).lower().endswith(PROJECT_SUFFIX)


def prepare_video_open(path, project_path=None, read_only=False,
                       cancelled=None, source_override=None,
                       dependencies=None):
    """Fully prepare a new session without mutating application state."""
    requested = os.path.abspath(os.fspath(path))
    if is_video_project(requested):
        project_path = requested
        source = read_project_source(project_path)
        source_path = (os.path.abspath(os.fspath(source_override))
                       if source_override else source.absolute_path)
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
        source_path, stream_index=stream_index, cancelled=cancelled,
        dependencies=dependencies)
    try:
        initial = decoder.decode_first(cancelled=cancelled)
        if cancelled is not None and cancelled():
            raise RuntimeError('video opening was cancelled')
        if project_path is None:
            contents = None
            revision = 0
            effective_read_only = bool(read_only)
        elif os.path.exists(project_path):
            validate_project_source(
                project_path, source_path, decoder.fingerprint,
                update_path=False)
            contents = load_project(project_path, read_only=read_only)
            revision = contents.revision
            effective_read_only = bool(read_only or contents.read_only)
            if not effective_read_only:
                validate_project_source(
                    project_path, source_path, decoder.fingerprint,
                    update_path=True)
        else:
            draft = decoder.snapshot(project_path, initial, read_only=read_only)
            contents = initialize_project(project_path, draft)
            revision = contents.revision
            effective_read_only = bool(read_only or contents.read_only)
        snapshot = decoder.snapshot(
            project_path, initial, revision=revision,
            read_only=effective_read_only)
        return PreparedVideoOpen(
            snapshot=snapshot, decoder=decoder,
            tracks=contents.tracks if contents else (),
            observations=contents.observations if contents else (),
            frame_states=contents.frame_states if contents else (),
            classes=contents.classes if contents else (),
            gaps=contents.gaps if contents else (),
            warning=contents.warning if contents else None)
    except Exception:
        decoder.close()
        raise
