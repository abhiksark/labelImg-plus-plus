# libs/core/video_distinctness_worker.py
"""Seek a bounded frame plan and refine geometry distinctness with pixels.

The worker owns an independent decoder.  It never walks the active session and
never calls ``next_frame``: the planner has already limited ``sample_pts`` to
events plus at most one ordinary frame per half-second window.  Any failure or
cancellation returns the immediate geometry answer unchanged.
"""

from dataclasses import dataclass

from libs.core.video_distinctness import (
    DISTINCTNESS_POLICY, DistinctnessPlan, dhash, hamming, pts_window,
)
from libs.core.video_project import fingerprint_video


DEFAULT_DISTANCE_THRESHOLD = 12


@dataclass(frozen=True)
class DistinctnessRefinementRequest:
    """Everything needed to decode and fence one refinement request."""

    request_id: int
    generation: int
    model_revision: int
    source_path: str
    fingerprint: object
    stream_index: int
    time_base_num: int
    time_base_den: int
    start_pts: int
    plan: DistinctnessPlan
    policy: str = DISTINCTNESS_POLICY
    distance_threshold: int = DEFAULT_DISTANCE_THRESHOLD


@dataclass(frozen=True)
class DistinctnessRefinementResult:
    """A fenced additive answer; incomplete work must not be cached."""

    request_id: int
    generation: int
    model_revision: int
    source_path: str
    fingerprint: object
    stream_index: int
    time_base_num: int
    time_base_den: int
    start_pts: int
    policy: str
    refined_pts: tuple
    completed: bool


def stride_for(fps, max_per_second):
    """Legacy arithmetic helper retained for internal compatibility tests."""
    if not fps or fps <= 0 or max_per_second <= 0:
        return 1
    return max(1, int(round(fps / max_per_second)))


def _matches_fingerprint(expected, current):
    if expected is None:
        return True
    matcher = getattr(expected, 'content_matches', None)
    if matcher is not None:
        return bool(matcher(current))
    return expected == current


def _decode_samples(source_path, stream_index, selected_pts, sample_pts,
                    forced_pts, start_pts, time_base_num, time_base_den,
                    distance_threshold, expected_fingerprint=None,
                    cancelled=None):
    """Return ``(pts, completed)`` after exact bounded seeks."""
    seeded = tuple(sorted(set(int(pts) for pts in selected_pts)))
    samples = tuple(sorted(set(int(pts) for pts in sample_pts)))
    forced = {int(pts) for pts in forced_pts}
    if cancelled is not None and cancelled():
        return seeded, False

    from libs.core.video_decoder import VideoDecoderSession
    from libs.integrations.image_convert import qimage_to_rgb

    session = None
    try:
        session = VideoDecoderSession(
            source_path, stream_index=stream_index, cancelled=cancelled)
        if (not _matches_fingerprint(expected_fingerprint,
                                     session.fingerprint)
                or session.stream_index != int(stream_index)
                or session.time_base_num != int(time_base_num)
                or session.time_base_den != int(time_base_den)):
            return seeded, False

        added = set()
        occupied_windows = {
            pts_window(
                pts, start_pts, time_base_num, time_base_den)
            for pts in seeded if pts not in forced}
        last_hash = None
        for pts in samples:
            if cancelled is not None and cancelled():
                return seeded, False
            result = session.seek_pts(
                pts, mode='nearest', cancelled=cancelled)
            if result is None or (cancelled is not None and cancelled()):
                return seeded, False
            current_hash = dhash(qimage_to_rgb(result.image))
            if (last_hash is not None
                    and hamming(current_hash, last_hash)
                    > int(distance_threshold)):
                window = pts_window(
                    pts, start_pts, time_base_num, time_base_den)
                if pts in forced or window not in occupied_windows:
                    added.add(pts)
                    if pts not in forced:
                        occupied_windows.add(window)
            last_hash = current_hash
        final_fingerprint = fingerprint_video(
            source_path, cancelled=cancelled)
        if (final_fingerprint is None
                or not _matches_fingerprint(
                    expected_fingerprint, final_fingerprint)):
            return seeded, False
        return tuple(sorted(set(seeded) | added)), True
    except Exception:
        # Pixel refinement is optional evidence.  The synchronous plan is the
        # complete fallback for dependency, decode, seek, and conversion errors.
        return seeded, False
    finally:
        if session is not None:
            session.close()


def refine_distinctness(request, cancelled=None):
    """Execute one immutable request and echo every result fence."""
    refined, completed = _decode_samples(
        request.source_path, request.stream_index,
        request.plan.selected_pts, request.plan.sample_pts,
        request.plan.forced_pts, request.start_pts,
        request.time_base_num, request.time_base_den,
        request.distance_threshold,
        expected_fingerprint=request.fingerprint, cancelled=cancelled)
    return DistinctnessRefinementResult(
        request.request_id, request.generation, request.model_revision,
        request.source_path, request.fingerprint, request.stream_index,
        request.time_base_num, request.time_base_den, request.start_pts,
        request.policy,
        refined, completed)


def refine_distinct_pts(source_path, stream_index, geometry_pts,
                        fps=None, max_per_second=2.0,
                        distance_threshold=DEFAULT_DISTANCE_THRESHOLD,
                        cancelled=None, sample_pts=None, forced_pts=(),
                        start_pts=0, time_base_num=1, time_base_den=1,
                        fingerprint=None):
    """Compatibility seam returning the additive PTS tuple directly.

    ``fps`` and ``max_per_second`` are accepted for callers of the previous
    internal helper but no longer drive decoding.  Only explicit
    ``sample_pts`` are sought; omitting them samples the seeded geometry PTS.
    """
    del fps, max_per_second
    samples = geometry_pts if sample_pts is None else sample_pts
    refined, _completed = _decode_samples(
        source_path, stream_index, geometry_pts, samples, forced_pts,
        start_pts, time_base_num, time_base_den, distance_threshold,
        expected_fingerprint=fingerprint, cancelled=cancelled)
    return refined
