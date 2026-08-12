# libs/core/video_distinctness_worker.py
"""Refine the geometry distinctness answer using decoded pixels.

Geometry cannot see a parked car under changing light, or a moving background
behind a static object. This pass walks the clip on a time stride, hashes what
it decodes, and adds frames whose appearance changed.

It is bounded by stride rather than clip length: a ten-minute 30fps clip costs
about 1,200 decodes instead of 18,000. It only ever *adds* frames, so a
cancelled or failed pass degrades to the geometry answer, which is always
correct and merely less thorough.
"""

from libs.core.video_distinctness import dhash, hamming


def stride_for(fps, max_per_second):
    """How many frames to skip between pixel samples."""
    if not fps or fps <= 0 or max_per_second <= 0:
        return 1
    return max(1, int(round(fps / max_per_second)))


def refine_distinct_pts(source_path, stream_index, state, geometry_pts,
                        fps=None, max_per_second=2.0, distance_threshold=12,
                        cancelled=None):
    """Return geometry_pts plus frames whose appearance changed materially."""
    seeded = tuple(sorted(set(int(pts) for pts in geometry_pts)))
    if cancelled is not None and cancelled():
        return seeded

    from libs.core.video_decoder import VideoDecoderSession
    from libs.integrations.image_convert import qimage_to_rgb

    stride = stride_for(fps, max_per_second)
    added = set()
    session = None
    try:
        session = VideoDecoderSession(
            source_path, stream_index=stream_index, cancelled=cancelled)
        result = session.seek_pts(0, mode='at_or_after', cancelled=cancelled)
        index = 0
        last_hash = None
        while result is not None:
            if cancelled is not None and cancelled():
                break
            if index % stride == 0:
                current = dhash(qimage_to_rgb(result.image))
                if (last_hash is not None
                        and hamming(current, last_hash) > distance_threshold):
                    added.add(int(result.frame_ref.pts))
                last_hash = current
            index += 1
            result = session.next_frame(cancelled=cancelled)
    except Exception:
        # A refinement failure must never break the overview; the geometry
        # answer stands on its own.
        return seeded
    finally:
        if session is not None:
            session.close()
    return tuple(sorted(set(seeded) | added))
