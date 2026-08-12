# libs/core/video_distinctness.py
"""Decide which video frames carry new information.

Propagation writes an observation on every frame, so "annotated" silently
becomes "all of them" as soon as tracking succeeds. This module is the single
answer to "which of those frames actually differ", and it feeds the overview's
frame grid, its count, and later the export default.

The geometry pass here is pure arithmetic over records already in memory: no
decoding, no optional dependency, fast enough to run on the GUI thread.
"""


def _bounds(geometry):
    """Axis-aligned bounds for a flat rectangle or a polygon point list."""
    if geometry is None:
        return None
    if len(geometry) == 4 and not isinstance(geometry[0], (list, tuple)):
        return tuple(float(value) for value in geometry)
    if len(geometry) < 3:
        return None
    xs = [float(point[0]) for point in geometry]
    ys = [float(point[1]) for point in geometry]
    return (min(xs), min(ys), max(xs), max(ys))


def iou(first, second):
    """Intersection over union of two bounds tuples, 0.0 when disjoint."""
    if first is None or second is None:
        return 0.0
    ax1, ay1, ax2, ay2 = first
    bx1, by1, bx2, by2 = second
    inter_w = min(ax2, bx2) - max(ax1, bx1)
    inter_h = min(ay2, by2) - max(ay1, by1)
    if inter_w <= 0 or inter_h <= 0:
        return 0.0
    intersection = inter_w * inter_h
    union = ((ax2 - ax1) * (ay2 - ay1)
             + (bx2 - bx1) * (by2 - by1) - intersection)
    return intersection / union if union > 0 else 0.0


def _frames_by_pts(state):
    """Group present observations into {pts: {track_id: bounds}}."""
    frames = {}
    for item in state.observations:
        if not item.present or item.geometry is None:
            continue
        bounds = _bounds(item.geometry)
        if bounds is None:
            continue
        frames.setdefault(int(item.pts), {})[item.track_id] = bounds
    return frames


def geometry_distinct_pts(state, iou_threshold=0.85):
    """Sorted PTS values whose annotated geometry differs from the last kept.

    A frame is kept when the set of present tracks changes, or when any track
    has moved far enough that its IoU against its own last kept position falls
    below ``iou_threshold``. The first annotated frame is always kept.
    """
    frames = _frames_by_pts(state)
    kept = []
    last = None
    for pts in sorted(frames):
        current = frames[pts]
        if last is None or set(current) != set(last):
            kept.append(pts)
            last = current
            continue
        if any(iou(current[track_id], last[track_id]) < iou_threshold
               for track_id in current):
            kept.append(pts)
            last = current
    return tuple(kept)
