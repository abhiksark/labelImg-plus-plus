"""Immutable contracts shared by smart-video workers and the Qt UI.

This module intentionally imports no optional video dependency.  Base installs
can import the application, inspect projects, and show a useful installation
hint without importing PyAV, NumPy, or OpenCV.
"""

from dataclasses import dataclass
from enum import Enum


class DocumentKind(Enum):
    NONE = 'none'
    IMAGE = 'image'
    VIDEO = 'video'


@dataclass(frozen=True)
class VideoFingerprint:
    size: int
    mtime_ns: int
    sampled_sha256: str

    def content_matches(self, other):
        """Return whether *other* is the same sampled media content."""
        return (
            isinstance(other, VideoFingerprint)
            and self.size == other.size
            and self.sampled_sha256 == other.sampled_sha256
        )


@dataclass(frozen=True)
class VideoFrameRef:
    fingerprint: VideoFingerprint
    stream_index: int
    pts: int
    time_base_num: int
    time_base_den: int

    @property
    def seconds(self):
        return self.pts * self.time_base_num / self.time_base_den

    @property
    def cache_key(self):
        return (
            'video', self.fingerprint.size,
            self.fingerprint.sampled_sha256, self.stream_index,
            self.pts, self.time_base_num, self.time_base_den,
        )


@dataclass(frozen=True)
class VideoFrameResult:
    frame_ref: VideoFrameRef
    image: object
    display_width: int
    display_height: int
    original_width: int
    original_height: int
    rotation: int
    byte_size: int
    decode_fingerprint: str

    @property
    def cache_key(self):
        return self.frame_ref.cache_key


@dataclass(frozen=True)
class VideoSessionSnapshot:
    source_path: str
    project_path: object
    fingerprint: VideoFingerprint
    stream_index: int
    time_base_num: int
    time_base_den: int
    width: int
    height: int
    rotation: int
    codec: str
    duration_pts: object
    start_pts: object
    average_rate_num: object
    average_rate_den: object
    revision: int
    initial_frame: VideoFrameResult
    read_only: bool = False


@dataclass(frozen=True)
class TrackRecord:
    track_id: str
    label: str
    shape_type: str
    color: tuple
    difficult: bool = False
    revision: int = 0


@dataclass(frozen=True)
class ObservationRecord:
    track_id: str
    pts: int
    geometry: object
    keypoints: object = None
    present: bool = True
    source: str = 'manual'
    review_state: str = 'accepted'
    anchor: bool = True
    quality: object = None
    revision: int = 0


@dataclass(frozen=True)
class FrameStateRecord:
    pts: int
    verified: bool
    revision: int = 0


@dataclass(frozen=True)
class VideoSaveRequest:
    project_path: str
    expected_durable_revision: int
    target_revision: int
    tracks: tuple = ()
    observations: tuple = ()
    deleted_observations: tuple = ()
    deleted_tracks: tuple = ()
    frame_states: tuple = ()
    classes: tuple = ()
    touched_tracks: tuple = ()


@dataclass(frozen=True)
class TrackingRequest:
    request_id: int
    generation: int
    source_path: str
    stream_index: int
    start_ref: VideoFrameRef
    end_pts: int
    direction: int
    track: TrackRecord
    seed: ObservationRecord
    seed_track_revision: int
    document_revision: int


@dataclass(frozen=True)
class TrackingBatch:
    request_id: int
    generation: int
    track_id: str
    seed_track_revision: int
    document_revision: int
    start_pts: int
    end_pts: int
    observations: tuple
    finished: bool = False
    stop_reason: object = None


@dataclass(frozen=True)
class VideoExportRequest:
    source_path: str
    project_path: str
    destination: str
    stream_index: int
    frame_refs: tuple
    observations: tuple
    tracks: tuple
    frame_states: tuple
    annotation_format: object
    image_format: str = 'jpg'
    jpeg_quality: int = 95
    class_order: tuple = ()
    range_start_pts: object = None
    range_end_pts: object = None
    sample_every_frames: object = None
