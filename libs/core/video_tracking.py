"""Cancellable rectangle propagation using standard OpenCV optical flow."""

import math
import time

from libs.core.video_propagation import PropagationBackend
from libs.core.video_project import fingerprint_video
from libs.core.video_decoder import (
    _oriented_array, _rotation_for_frame, _rotation_for_stream,
    load_video_dependencies,
)
from libs.core.video_types import (
    geometry_bounds,
    ObservationRecord, PropagationBatch, PropagationResult, TrackGapRecord,
    TrackingBatch,
)


MAX_WORKING_EDGE = 1280
MAX_FEATURES = 100
MAX_FB_ERROR = 2.0
MIN_INLIERS = 8
MIN_INLIER_RATIO = .5
MIN_HISTOGRAM_CORRELATION = .5
BACKWARD_CHUNK_SECONDS = 2.0


def _working_frame(frame, rotation, cv2, np):
    array = _oriented_array(frame, rotation, np)
    height, width = array.shape[:2]
    scale = min(1.0, MAX_WORKING_EDGE / max(width, height))
    if scale < 1.0:
        array = cv2.resize(
            array, (max(1, int(round(width * scale))),
                    max(1, int(round(height * scale)))),
            interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    return gray, scale, width, height


def _histogram(gray, cv2):
    histogram = cv2.calcHist([gray], [0], None, [64], [0, 256])
    return cv2.normalize(histogram, histogram).flatten()


def _feature_points(gray, rectangle, cv2, np):
    xmin, ymin, xmax, ymax = rectangle
    height, width = gray.shape[:2]
    x0 = max(0, min(width, int(math.floor(xmin))))
    y0 = max(0, min(height, int(math.floor(ymin))))
    x1 = max(0, min(width, int(math.ceil(xmax))))
    y1 = max(0, min(height, int(math.ceil(ymax))))
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    mask = np.zeros_like(gray, dtype=np.uint8)
    mask[y0:y1, x0:x1] = 255
    return cv2.goodFeaturesToTrack(
        gray, mask=mask, maxCorners=MAX_FEATURES,
        qualityLevel=.01, minDistance=3, blockSize=3)


def _transform_rectangle(rectangle, matrix, cv2, np):
    xmin, ymin, xmax, ymax = rectangle
    corners = np.asarray([[
        [xmin, ymin], [xmax, ymin], [xmax, ymax], [xmin, ymax],
    ]], dtype=np.float32)
    transformed = cv2.transform(corners, matrix)[0]
    return [
        float(transformed[:, 0].min()),
        float(transformed[:, 1].min()),
        float(transformed[:, 0].max()),
        float(transformed[:, 1].max()),
    ]


def _inside_ratio(rectangle, width, height):
    xmin, ymin, xmax, ymax = rectangle
    area = max(0.0, xmax - xmin) * max(0.0, ymax - ymin)
    if area <= 0:
        return 0.0
    inside = max(0.0, min(width, xmax) - max(0.0, xmin)) * \
        max(0.0, min(height, ymax) - max(0.0, ymin))
    return inside / area


def _warp_keypoints_by_affine(keypoints, matrix, scale, cv2, np):
    if keypoints is None:
        return None
    result = list(keypoints)
    valid = [(index, item) for index, item in enumerate(keypoints)
             if item is not None]
    if not valid:
        return result
    points = np.asarray([[[item[0] * scale, item[1] * scale]
                          for _index, item in valid]], dtype=np.float32)
    transformed = cv2.transform(points, matrix)[0]
    for output, (index, item) in zip(transformed, valid):
        result[index] = [float(output[0] / scale),
                         float(output[1] / scale), item[2]]
    return result


def _propagate_pair(previous_gray, current_gray, rectangle, points,
                    cv2, np):
    if points is None or len(points) < MIN_INLIERS:
        return None, 'insufficient features'
    forward, status_forward, _error = cv2.calcOpticalFlowPyrLK(
        previous_gray, current_gray, points, None,
        winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                  30, .01))
    if forward is None:
        return None, 'optical flow failed'
    backward, status_backward, _error = cv2.calcOpticalFlowPyrLK(
        current_gray, previous_gray, forward, None,
        winSize=(21, 21), maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,
                  30, .01))
    if backward is None:
        return None, 'backward optical flow failed'
    fb_error = np.linalg.norm(points - backward, axis=2).reshape(-1)
    valid = ((status_forward.reshape(-1) == 1)
             & (status_backward.reshape(-1) == 1)
             & (fb_error <= MAX_FB_ERROR))
    source = points.reshape(-1, 2)[valid]
    target = forward.reshape(-1, 2)[valid]
    if len(source) < MIN_INLIERS:
        return None, 'insufficient forward/backward matches'
    matrix, inlier_mask = cv2.estimateAffinePartial2D(
        source, target, method=cv2.RANSAC,
        ransacReprojThreshold=2.0, maxIters=2000,
        confidence=.99, refineIters=10)
    if matrix is None or inlier_mask is None:
        return None, 'affine estimation failed'
    inliers = int(inlier_mask.sum())
    ratio = inliers / len(source)
    if inliers < MIN_INLIERS or ratio < MIN_INLIER_RATIO:
        return None, 'insufficient affine inliers'
    median_error = float(np.median(fb_error[valid]))
    if median_error > MAX_FB_ERROR:
        return None, 'median flow error exceeded 2 pixels'
    scale = math.sqrt(matrix[0, 0] ** 2 + matrix[0, 1] ** 2)
    if not .7 <= scale <= 1.4:
        return None, 'per-step scale left 0.7-1.4'
    transformed = _transform_rectangle(rectangle, matrix, cv2, np)
    quality = max(0.0, min(1.0, ratio *
                           (1.0 - median_error / (MAX_FB_ERROR + 1e-9))))
    return (transformed, matrix, target.reshape(-1, 1, 2), quality), None


def _decoded_frames(container, stream, start_pts, end_pts, rotation,
                    cv2, np, handle):
    container.seek(
        int(start_pts), stream=stream, backward=True, any_frame=False)
    for frame in container.decode(stream):
        handle.check_cancelled()
        if frame.pts is None or frame.pts < start_pts:
            continue
        if frame.pts > end_pts:
            break
        frame_rotation = _rotation_for_frame(frame, rotation)
        gray, scale, width, height = _working_frame(
            frame, frame_rotation, cv2, np)
        yield int(frame.pts), gray, scale, width, height


def _ordered_frames(container, stream, request, rotation, cv2, np, handle):
    if request.direction > 0:
        yield from _decoded_frames(
            container, stream, request.start_ref.pts, request.end_pts,
            rotation, cv2, np, handle)
        return
    time_base = float(stream.time_base)
    chunk_pts = max(1, int(round(BACKWARD_CHUNK_SECONDS / time_base)))
    cursor = request.start_ref.pts
    first_chunk = True
    while cursor > request.end_pts:
        handle.check_cancelled()
        chunk_start = max(request.end_pts, cursor - chunk_pts)
        frames = list(_decoded_frames(
            container, stream, chunk_start, cursor, rotation,
            cv2, np, handle))
        for value in reversed(frames):
            if value[0] < cursor or (first_chunk and value[0] == cursor):
                yield value
        first_chunk = False
        cursor = chunk_start


def track_optical_flow(request, handle):
    """Run one propagation and return/emit non-overlapping pending batches."""
    av, np = load_video_dependencies()
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            'Optical-flow tracking requires labelimgplusplus[video]: %s' %
            exc)
    if request.track.shape_type != 'rectangle' \
            or not request.seed.present \
            or request.seed.geometry is None \
            or len(request.seed.geometry) != 4:
        raise ValueError('tracking requires an accepted rectangle seed')
    cv2.setRNGSeed(0)
    container = av.open(request.source_path, mode='r')
    try:
        stream = next((item for item in container.streams.video
                       if item.index == request.stream_index), None)
        if stream is None:
            raise ValueError('video stream is no longer available')
        rotation = _rotation_for_stream(stream)
        frames = _ordered_frames(
            container, stream, request, rotation, cv2, np, handle)
        first = next(frames, None)
        if first is None:
            return TrackingBatch(
                request.request_id, request.generation,
                request.track.track_id, request.seed_track_revision,
                request.document_revision, request.start_ref.pts,
                request.start_ref.pts, (), finished=True,
                stop_reason='no frames in range')
        _first_pts, previous_gray, working_scale, width, height = first
        rectangle = [float(value) * working_scale
                     for value in request.seed.geometry]
        keypoints = request.seed.keypoints
        points = _feature_points(previous_gray, rectangle, cv2, np)
        previous_histogram = _histogram(previous_gray, cv2)
        pending = []
        batch_start = request.start_ref.pts
        last_emit = time.monotonic()
        stop_reason = 'end of range'
        step_index = 0
        last_pts = request.start_ref.pts
        for pts, current_gray, scale, width, height in frames:
            handle.check_cancelled()
            if pts == request.start_ref.pts:
                continue
            if abs(scale - working_scale) > 1e-9:
                stop_reason = 'working scale changed'
                break
            correlation = cv2.compareHist(
                previous_histogram, _histogram(current_gray, cv2),
                cv2.HISTCMP_CORREL)
            if correlation < MIN_HISTOGRAM_CORRELATION:
                stop_reason = 'scene cut'
                break
            propagated, reason = _propagate_pair(
                previous_gray, current_gray, rectangle, points, cv2, np)
            if propagated is None:
                stop_reason = reason
                break
            rectangle, matrix, points, quality = propagated
            if rectangle[2] - rectangle[0] < 4 \
                    or rectangle[3] - rectangle[1] < 4:
                stop_reason = 'rectangle became smaller than 4 pixels'
                break
            if _inside_ratio(rectangle, current_gray.shape[1],
                             current_gray.shape[0]) < .5:
                stop_reason = 'less than half the rectangle remains in frame'
                break
            keypoints = _warp_keypoints_by_affine(
                keypoints, matrix, working_scale, cv2, np)
            observation = ObservationRecord(
                request.track.track_id, pts,
                [value / working_scale for value in rectangle],
                keypoints=keypoints, present=True, source='tracker',
                review_state='pending', anchor=False, quality=quality,
                revision=request.document_revision)
            pending.append(observation)
            last_pts = pts
            step_index += 1
            previous_gray = current_gray
            previous_histogram = _histogram(current_gray, cv2)
            if step_index % 5 == 0:
                points = _feature_points(
                    current_gray, rectangle, cv2, np)
            # Leave scheduling headroom so observers receive progress at
            # least once per 250 ms rather than just after that boundary.
            if time.monotonic() - last_emit >= .20:
                handle.report_progress(TrackingBatch(
                    request.request_id, request.generation,
                    request.track.track_id, request.seed_track_revision,
                    request.document_revision, batch_start, last_pts,
                    tuple(pending)))
                pending = []
                batch_start = last_pts
                last_emit = time.monotonic()
        return TrackingBatch(
            request.request_id, request.generation,
            request.track.track_id, request.seed_track_revision,
            request.document_revision, batch_start, last_pts,
            tuple(pending), finished=True, stop_reason=stop_reason)
    finally:
        container.close()


class PropagationCancelled(RuntimeError):
    """Internal cooperative-cancellation sentinel."""


class _CancellationHandle:
    def __init__(self, cancelled):
        self._cancelled = cancelled

    def check_cancelled(self):
        if self._cancelled():
            raise PropagationCancelled('propagation cancelled')


def _propagation_frames(container, stream, request, direction, rotation,
                        cv2, np, cancelled):
    handle = _CancellationHandle(cancelled)
    if direction > 0:
        yield from _decoded_frames(
            container, stream, request.current_pts, request.end_pts,
            rotation, cv2, np, handle)
        return
    time_base = float(stream.time_base)
    chunk_pts = max(1, int(round(BACKWARD_CHUNK_SECONDS / time_base)))
    cursor = request.current_pts
    first_chunk = True
    while cursor > request.start_pts:
        handle.check_cancelled()
        chunk_start = max(request.start_pts, cursor - chunk_pts)
        frames = list(_decoded_frames(
            container, stream, chunk_start, cursor, rotation,
            cv2, np, handle))
        for value in reversed(frames):
            if value[0] < cursor or (first_chunk and value[0] == cursor):
                yield value
        first_chunk = False
        cursor = chunk_start


def _scaled_geometry(geometry, scale):
    if len(geometry) == 4 and not isinstance(geometry[0], (list, tuple)):
        return [float(value) * scale for value in geometry]
    return [[float(point[0]) * scale, float(point[1]) * scale]
            for point in geometry]


def _transform_geometry(geometry, matrix, cv2, np):
    if len(geometry) == 4 and not isinstance(geometry[0], (list, tuple)):
        return _transform_rectangle(geometry, matrix, cv2, np)
    points = np.asarray([geometry], dtype=np.float32)
    transformed = cv2.transform(points, matrix)[0]
    return [[float(point[0]), float(point[1])] for point in transformed]


def _unscaled_geometry(geometry, scale):
    if len(geometry) == 4 and not isinstance(geometry[0], (list, tuple)):
        return [float(value) / scale for value in geometry]
    return [[float(point[0]) / scale, float(point[1]) / scale]
            for point in geometry]


def _stable_gap_reason(reason):
    reason = str(reason or '').lower()
    if 'scene cut' in reason:
        return 'scene_cut'
    if 'flow failed' in reason:
        return 'occluded'
    if 'frame' in reason or 'rectangle became' in reason:
        return 'out_of_frame'
    return 'low_confidence'


def _estimated_frames(request, direction):
    if not request.average_rate_num or not request.average_rate_den:
        return 0
    endpoint = request.end_pts if direction > 0 else request.start_pts
    seconds = abs(endpoint - request.current_pts) * \
        request.time_base_num / request.time_base_den
    return max(0, int(round(
        seconds * request.average_rate_num / request.average_rate_den)))


class OpenCVPropagationBackend(PropagationBackend):
    """Portable multi-track Lucas-Kanade and affine propagation."""

    name = 'opencv'

    def propagate(self, request, direction, cancelled, emit_batch):
        if direction not in (-1, 1):
            raise ValueError('propagation direction must be -1 or 1')
        if not request.seeds:
            raise ValueError('propagation requires at least one seed')
        current_fingerprint = fingerprint_video(request.source_path)
        if (current_fingerprint is None
                or not request.fingerprint.content_matches(
                    current_fingerprint)):
            raise RuntimeError(
                'video media changed after propagation was requested')
        av, np = load_video_dependencies()
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                'Video propagation requires labelimgplusplus[video]: %s' %
                exc)
        cv2.setRNGSeed(0)
        container = av.open(request.source_path, mode='r')
        try:
            stream = next((item for item in container.streams.video
                           if item.index == request.stream_index), None)
            if stream is None:
                raise RuntimeError('video stream is no longer available')
            if (int(stream.time_base.numerator) != request.time_base_num
                    or int(stream.time_base.denominator)
                    != request.time_base_den):
                raise RuntimeError(
                    'video time base changed after propagation was requested')
            rotation = _rotation_for_stream(stream)
            frames = _propagation_frames(
                container, stream, request, direction, rotation,
                cv2, np, cancelled)
            first = next(frames, None)
            if first is None:
                return PropagationResult(
                    request.request_id, request.generation,
                    request.document_revision)

            first_pts, previous_gray, working_scale, width, height = first
            if first_pts != request.current_pts:
                raise RuntimeError(
                    'current propagation frame is no longer decodable')
            anchors = {}
            for anchor in request.manual_anchors:
                anchors[(anchor.track_id, int(anchor.pts))] = anchor
            states = {}
            for seed in request.seeds:
                bounds = geometry_bounds(seed.geometry)
                if (not seed.present or seed.geometry is None
                        or bounds is None):
                    raise ValueError(
                        'propagation seeds must be present accepted geometry')
                geometry = _scaled_geometry(seed.geometry, working_scale)
                scaled_bounds = geometry_bounds(geometry)
                states[seed.track_id] = {
                    'active': True,
                    'geometry': geometry,
                    'keypoints': seed.keypoints,
                    'points': _feature_points(
                        previous_gray, scaled_bounds, cv2, np),
                    'gap_start': None,
                    'gap_end': None,
                    'gap_reason': None,
                    'steps': 0,
                }

            observations = []
            gaps = []
            failures = {}
            pending_observations = []
            pending_gaps = []
            processed = 0
            total = _estimated_frames(request, direction)
            started = time.monotonic()
            last_emit = started
            previous_histogram = _histogram(previous_gray, cv2)

            def close_gap(track_id, state):
                if state['gap_start'] is None:
                    return
                start_pts = min(state['gap_start'], state['gap_end'])
                end_pts = max(state['gap_start'], state['gap_end'])
                gap = TrackGapRecord(
                    track_id, start_pts, end_pts, state['gap_reason'],
                    self.name, request.document_revision)
                gaps.append(gap)
                pending_gaps.append(gap)
                failures[track_id] = state['gap_reason']
                state['gap_start'] = None
                state['gap_end'] = None
                state['gap_reason'] = None

            def deactivate(track_id, state, pts, reason):
                if state['gap_start'] is None:
                    state['gap_start'] = int(pts)
                    state['gap_reason'] = reason
                state['gap_end'] = int(pts)
                state['active'] = False
                failures[track_id] = reason

            for pts, current_gray, scale, width, height in frames:
                if cancelled():
                    raise PropagationCancelled('propagation cancelled')
                if pts == request.current_pts:
                    continue
                if abs(scale - working_scale) > 1e-9:
                    raise RuntimeError(
                        'decoded working scale changed during propagation')
                processed += 1
                current_histogram = _histogram(current_gray, cv2)
                scene_cut = cv2.compareHist(
                    previous_histogram, current_histogram,
                    cv2.HISTCMP_CORREL) < MIN_HISTOGRAM_CORRELATION

                for track_id, state in states.items():
                    anchor = anchors.get((track_id, int(pts)))
                    if anchor is not None:
                        close_gap(track_id, state)
                        if not anchor.present or anchor.geometry is None:
                            deactivate(
                                track_id, state, pts, 'occluded')
                            continue
                        state['geometry'] = _scaled_geometry(
                            anchor.geometry, working_scale)
                        state['keypoints'] = anchor.keypoints
                        state['points'] = _feature_points(
                            current_gray,
                            geometry_bounds(state['geometry']), cv2, np)
                        state['active'] = True
                        state['steps'] = 0
                        continue
                    if not state['active']:
                        state['gap_end'] = int(pts)
                        continue
                    if scene_cut:
                        deactivate(
                            track_id, state, pts, 'scene_cut')
                        continue
                    bounds = geometry_bounds(state['geometry'])
                    propagated, reason = _propagate_pair(
                        previous_gray, current_gray, bounds,
                        state['points'], cv2, np)
                    if propagated is None:
                        deactivate(
                            track_id, state, pts,
                            _stable_gap_reason(reason))
                        continue
                    _bounds, matrix, points, quality = propagated
                    geometry = _transform_geometry(
                        state['geometry'], matrix, cv2, np)
                    transformed_bounds = geometry_bounds(geometry)
                    if (transformed_bounds[2] - transformed_bounds[0] < 4
                            or transformed_bounds[3]
                            - transformed_bounds[1] < 4
                            or _inside_ratio(
                                transformed_bounds,
                                current_gray.shape[1],
                                current_gray.shape[0]) < .5):
                        deactivate(
                            track_id, state, pts, 'out_of_frame')
                        continue
                    state['geometry'] = geometry
                    state['points'] = points
                    state['keypoints'] = _warp_keypoints_by_affine(
                        state['keypoints'], matrix, working_scale,
                        cv2, np)
                    state['steps'] += 1
                    if state['steps'] % 5 == 0:
                        state['points'] = _feature_points(
                            current_gray, transformed_bounds, cv2, np)
                    observation = ObservationRecord(
                        track_id, int(pts),
                        _unscaled_geometry(geometry, working_scale),
                        keypoints=state['keypoints'], present=True,
                        # Provisional until a human reviews it. Machine output
                        # must never be indistinguishable from hand-drawn work.
                        source='tracker', review_state='pending',
                        anchor=False, quality=quality,
                        revision=request.document_revision)
                    observations.append(observation)
                    pending_observations.append(observation)

                previous_gray = current_gray
                previous_histogram = current_histogram
                now = time.monotonic()
                if (len(pending_observations) >= 16
                        or now - last_emit >= .20):
                    active = sum(
                        1 for state in states.values() if state['active'])
                    elapsed = max(1e-9, now - started)
                    eta = (elapsed / processed * max(0, total - processed)
                           if total else None)
                    emit_batch(PropagationBatch(
                        request.request_id, request.generation, direction,
                        observations=tuple(pending_observations),
                        gaps=tuple(pending_gaps),
                        processed_frames=processed, total_frames=total,
                        active_tracks=active,
                        completed_tracks=len(states) - active,
                        eta_seconds=eta))
                    pending_observations = []
                    pending_gaps = []
                    last_emit = now

            boundary_pts = (
                request.end_pts if direction > 0 else request.start_pts)
            for track_id, state in states.items():
                if state['gap_start'] is not None:
                    if state['gap_end'] is None:
                        state['gap_end'] = boundary_pts
                    close_gap(track_id, state)
            active = sum(1 for state in states.values() if state['active'])
            elapsed = max(1e-9, time.monotonic() - started)
            eta = (elapsed / processed * max(0, total - processed)
                   if total and processed else None)
            emit_batch(PropagationBatch(
                request.request_id, request.generation, direction,
                observations=tuple(pending_observations),
                gaps=tuple(pending_gaps), processed_frames=processed,
                total_frames=total, active_tracks=active,
                completed_tracks=len(states) - active,
                eta_seconds=eta, finished=True))
            final_fingerprint = fingerprint_video(request.source_path)
            if (final_fingerprint is None
                    or not request.fingerprint.content_matches(
                        final_fingerprint)):
                raise RuntimeError(
                    'video media changed during propagation')
            return PropagationResult(
                request.request_id, request.generation,
                request.document_revision,
                observations=tuple(observations), gaps=tuple(gaps),
                failures=tuple(sorted(failures.items())))
        finally:
            container.close()
