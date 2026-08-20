# libs/core/video_distinctness.py
"""Plan the annotated frames that carry new video information.

Whole-video propagation deliberately writes dense observations.  The overview
must therefore preserve review and tracking events without allowing object size
or frame rate to turn a small, steady movement back into every decoded frame.

The planner is dependency-free and runs over an immutable ``VideoModelState``.
It keeps explicit events, then considers at most one ordinary observation per
half-second presentation-time window.  ``sample_pts`` is the bounded input to
the optional pixel pass; it contains the events and the same single ordinary
representative, never the whole clip.
"""

from bisect import bisect_left, bisect_right
from dataclasses import dataclass


WINDOW_SECONDS = 0.5
DEFAULT_IOU_THRESHOLD = 0.85
DISTINCTNESS_POLICY = 'adaptive-global-v1'


@dataclass(frozen=True)
class DistinctnessPlan:
    """Immutable immediate answer and bounded work for pixel refinement."""

    forced_pts: tuple
    selected_pts: tuple
    sample_pts: tuple


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


def pts_window(pts, start_pts, time_base_num, time_base_den):
    """Return the exact half-second bucket for one presentation timestamp."""
    numerator = 2 * (int(pts) - int(start_pts)) * int(time_base_num)
    denominator = int(time_base_den)
    if int(time_base_num) <= 0 or denominator <= 0:
        raise ValueError('video time base must be positive')
    return numerator // denominator


def _eligible_bounds(observation):
    """Bounds contributed by a usable distinctness observation, if any."""
    if observation.review_state == 'rejected' or not observation.present:
        return None
    return _bounds(observation.geometry)


def _indexed_observations(state):
    """Return frame geometry plus full and eligible per-track histories."""
    frames = {}
    all_by_track = {}
    valid_by_track = {}
    for item in getattr(state, 'observations', ()) or ():
        all_by_track.setdefault(item.track_id, []).append(item)
        bounds = _eligible_bounds(item)
        if bounds is None:
            continue
        pts = int(item.pts)
        frames.setdefault(pts, {})[item.track_id] = bounds
        valid_by_track.setdefault(item.track_id, []).append(item)
    for values in all_by_track.values():
        values.sort(key=lambda item: int(item.pts))
    for values in valid_by_track.values():
        values.sort(key=lambda item: int(item.pts))
    return frames, all_by_track, valid_by_track


def _forced_event_pts(state, frames, all_by_track, valid_by_track):
    """Find important event frames without admitting rejected/absent data."""
    forced = set()

    # A track must remain findable even when its geometry never changes.
    for values in valid_by_track.values():
        if values:
            forced.add(int(values[0].pts))
            forced.add(int(values[-1].pts))

    # Manual decisions and verified annotated frames are explicit user intent.
    for values in valid_by_track.values():
        for item in values:
            if (item.source == 'manual'
                    and item.review_state == 'accepted' and item.anchor):
                forced.add(int(item.pts))
    for frame_state in getattr(state, 'frame_states', ()) or ():
        pts = int(frame_state.pts)
        if frame_state.verified and pts in frames:
            forced.add(pts)

    # Appearance/disappearance is a frame-wide transition.  Both neighboring
    # annotated frames matter: one says what was there and one what changed.
    previous_pts = None
    previous_membership = None
    for pts in sorted(frames):
        membership = frozenset(frames[pts])
        if (previous_membership is not None
                and membership != previous_membership):
            forced.add(previous_pts)
            forced.add(pts)
        previous_pts = pts
        previous_membership = membership

    # Per-track provenance/review/presence changes are likewise two-sided.
    # An excluded side is deliberately not added; the nearest later/earlier
    # valid observation is forced by the next transition or run boundary.
    for values in all_by_track.values():
        previous = None
        previous_valid = False
        pending_start = None
        pending_last = None
        for item in values:
            valid = _eligible_bounds(item) is not None
            if previous is not None and (
                    item.source != previous.source
                    or item.review_state != previous.review_state
                    or bool(item.present) != bool(previous.present)):
                if previous_valid:
                    forced.add(int(previous.pts))
                if valid:
                    forced.add(int(item.pts))

            is_pending = valid and item.review_state == 'pending'
            if is_pending:
                if pending_start is None:
                    pending_start = int(item.pts)
                pending_last = int(item.pts)
            elif pending_start is not None:
                forced.add(pending_start)
                forced.add(pending_last)
                pending_start = pending_last = None

            previous = item
            previous_valid = valid
        if pending_start is not None:
            forced.add(pending_start)
            forced.add(pending_last)

    # Gaps usually contain no observations.  Preserve the nearest usable
    # observation on each side rather than inventing a tile at a bare gap PTS.
    for gap in getattr(state, 'gaps', ()) or ():
        values = valid_by_track.get(gap.track_id, ())
        if not values:
            continue
        pts_values = [int(item.pts) for item in values]
        left = bisect_right(pts_values, int(gap.start_pts)) - 1
        right = bisect_left(pts_values, int(gap.end_pts))
        if left >= 0:
            forced.add(pts_values[left])
        if right < len(pts_values):
            forced.add(pts_values[right])

    # Every distinct tile must still name a frame with a usable observation.
    return forced.intersection(frames)


def _minimum_track_iou(current, previous):
    """Return the least per-track IoU, with membership changes maximally new."""
    if previous is None or set(current) != set(previous):
        return 0.0
    if not current:
        return 1.0
    return min(iou(current[track_id], previous[track_id])
               for track_id in current)


def build_distinctness_plan(state, start_pts=0, time_base_num=1,
                            time_base_den=1,
                            iou_threshold=DEFAULT_IOU_THRESHOLD):
    """Build the adaptive global distinctness plan for immutable video state.

    Event-containing windows keep all of their events and need no additional
    ordinary representative.  Every other populated window contributes its
    most geometrically novel frame to ``sample_pts``; that frame joins the
    immediate answer only when its minimum track IoU is below the threshold.
    Equal novelty is resolved toward the latest PTS.
    """
    if not 0.0 <= float(iou_threshold) <= 1.0:
        raise ValueError('IoU threshold must be between zero and one')
    # Validate even an empty state so callers never cache a plan under a bogus
    # time base that a later populated state would reject.
    pts_window(start_pts, start_pts, time_base_num, time_base_den)

    frames, all_by_track, valid_by_track = _indexed_observations(state)
    if not frames:
        return DistinctnessPlan((), (), ())
    forced = _forced_event_pts(
        state, frames, all_by_track, valid_by_track)
    buckets = {}
    for pts in frames:
        bucket = pts_window(
            pts, start_pts, time_base_num, time_base_den)
        buckets.setdefault(bucket, []).append(pts)

    selected = set(forced)
    samples = set(forced)
    last_retained = None
    for bucket in sorted(buckets):
        values = sorted(buckets[bucket])
        events = [pts for pts in values if pts in forced]
        if events:
            # Explicit events may exceed the ordinary density cap.  The last
            # one is the state subsequent ordinary windows compare against.
            last_retained = frames[events[-1]]
            continue

        candidate = min(
            values,
            key=lambda pts: (
                _minimum_track_iou(frames[pts], last_retained), -pts))
        samples.add(candidate)
        novelty_iou = _minimum_track_iou(
            frames[candidate], last_retained)
        if last_retained is None or novelty_iou < float(iou_threshold):
            selected.add(candidate)
            last_retained = frames[candidate]

    return DistinctnessPlan(
        tuple(sorted(forced)), tuple(sorted(selected)),
        tuple(sorted(samples)))


def geometry_distinct_pts(state, iou_threshold=DEFAULT_IOU_THRESHOLD,
                          start_pts=0, time_base_num=1, time_base_den=1):
    """Compatibility seam returning the immediate geometry selection."""
    return build_distinctness_plan(
        state, start_pts=start_pts, time_base_num=time_base_num,
        time_base_den=time_base_den,
        iou_threshold=iou_threshold).selected_pts


# dHash: downscale to 9x8 greyscale, compare each pixel with its right
# neighbour, pack the 64 comparisons into an integer. Robust to brightness and
# scale, sensitive to structure. Implemented here rather than pulled from
# imagehash because tests/video/test_compatibility.py asserts the extras
# verbatim and this is ten lines.
_HASH_WIDTH = 9
_HASH_HEIGHT = 8


def _greyscale(image):
    numpy = __import__('numpy')
    array = numpy.asarray(image)
    if array.ndim == 3:
        array = array[..., :3].mean(axis=2)
    return array.astype(numpy.float64)


def _resize_nearest(array, width, height):
    numpy = __import__('numpy')
    rows = (numpy.linspace(0, array.shape[0] - 1, height)
            .round().astype(numpy.int64))
    cols = (numpy.linspace(0, array.shape[1] - 1, width)
            .round().astype(numpy.int64))
    return array[rows][:, cols]


def dhash(image):
    """64-bit difference hash of a greyscale or colour image array."""
    small = _resize_nearest(_greyscale(image), _HASH_WIDTH, _HASH_HEIGHT)
    bits = small[:, 1:] > small[:, :-1]
    value = 0
    for bit in bits.flatten():
        value = (value << 1) | int(bit)
    return value


def hamming(first, second):
    """Number of differing bits between two hashes."""
    return bin(int(first) ^ int(second)).count('1')
