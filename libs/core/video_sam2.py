"""Lazy optional SAM 2 backend for whole-video propagation.

This module deliberately imports neither Torch nor SAM 2 at module import
time. The base application and every published extra remain free of those
dependencies; users provide an official source installation and local model
files when they choose this backend.
"""

from dataclasses import dataclass
import gc
import importlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import tempfile
import time

from libs.core.video_propagation import PropagationBackend
from libs.core.video_project import fingerprint_video
from libs.core.video_types import (
    geometry_bounds,
    ObservationRecord, PropagationBatch, PropagationResult, TrackGapRecord,
)


PROPAGATION_BACKENDS = ('auto', 'opencv', 'sam2')
MIN_TORCH_VERSION = (2, 5, 1)


@dataclass(frozen=True)
class Sam2Availability:
    available: bool
    reasons: tuple = ()

    @property
    def message(self):
        return '; '.join(self.reasons)


def normalize_propagation_backend(value):
    """Return a supported persisted backend name."""
    value = str(value or 'auto').strip().lower()
    return value if value in PROPAGATION_BACKENDS else 'auto'


def _version_tuple(value):
    parts = re.findall(r'\d+', str(value or ''))
    return tuple(int(part) for part in parts[:3])


def _source_install(metadata_lookup=importlib.metadata.distribution):
    """Recognize pip installs that retain their source/VCS provenance."""
    for name in ('SAM-2', 'sam2'):
        try:
            distribution = metadata_lookup(name)
        except importlib.metadata.PackageNotFoundError:
            continue
        direct_url = distribution.read_text('direct_url.json')
        if not direct_url:
            return False
        try:
            provenance = json.loads(direct_url)
        except (TypeError, ValueError):
            return False
        return bool(
            provenance.get('vcs_info')
            or provenance.get('dir_info')
            or str(provenance.get('url', '')).startswith('file:'))
    return False


def inspect_sam2_environment(
        checkpoint_path, config_path, module_loader=importlib.import_module,
        metadata_lookup=importlib.metadata.distribution,
        system=None, version_info=None):
    """Inspect the optional runtime only when propagation is invoked."""
    reasons = []
    system = platform.system() if system is None else system
    version_info = sys.version_info if version_info is None else version_info
    if system != 'Linux':
        reasons.append('SAM 2 video propagation requires Linux')
    if tuple(version_info[:2]) < (3, 10):
        reasons.append('SAM 2 video propagation requires Python 3.10 or newer')
    if not checkpoint_path or not os.path.isfile(checkpoint_path):
        reasons.append('configure an existing SAM 2 checkpoint file')
    if not config_path or not os.path.isfile(config_path):
        reasons.append('configure an existing SAM 2 model-config file')
    if reasons:
        return Sam2Availability(False, tuple(reasons))

    try:
        torch = module_loader('torch')
    except (ImportError, OSError, RuntimeError) as exc:
        reasons.append('install compatible PyTorch 2.5.1 or newer (%s)' % exc)
    else:
        if _version_tuple(getattr(torch, '__version__', '')) \
                < MIN_TORCH_VERSION:
            reasons.append('PyTorch 2.5.1 or newer is required')
        try:
            cuda_available = bool(torch.cuda.is_available())
        except (AttributeError, OSError, RuntimeError) as exc:
            reasons.append('PyTorch CUDA probing failed (%s)' % exc)
        else:
            if not cuda_available:
                reasons.append('a working CUDA-enabled PyTorch runtime is required')

    sam2_module = None
    try:
        sam2_module = module_loader('sam2')
        build_module = module_loader('sam2.build_sam')
        if not callable(getattr(
                build_module, 'build_sam2_video_predictor', None)):
            reasons.append('the installed SAM 2 build API is incompatible')
    except (ImportError, OSError, RuntimeError) as exc:
        reasons.append('install official SAM 2 from source (%s)' % exc)
    else:
        try:
            _config_name(config_path, sam2_module)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            reasons.append(str(exc))
        try:
            source_install = _source_install(metadata_lookup)
        except (OSError, ValueError):
            source_install = False
        if not source_install:
            reasons.append('install official SAM 2 from a source checkout')
    try:
        torchvision = module_loader('torchvision')
    except (ImportError, OSError, RuntimeError) as exc:
        reasons.append('install compatible torchvision 0.20.1 or newer (%s)'
                       % exc)
    else:
        if _version_tuple(getattr(torchvision, '__version__', '')) \
                < (0, 20, 1):
            reasons.append('torchvision 0.20.1 or newer is required')
    return Sam2Availability(not reasons, tuple(reasons))


class ConfiguredPropagationBackend(PropagationBackend):
    """Choose the configured backend lazily in the worker thread."""

    name = 'configured'

    def __init__(self, choice='auto', checkpoint_path='', config_path=''):
        self.choice = normalize_propagation_backend(choice)
        self.checkpoint_path = str(checkpoint_path or '')
        self.config_path = str(config_path or '')

    def propagate(self, request, direction, cancelled, emit_batch):
        if self.choice == 'opencv':
            return self._opencv().propagate(
                request, direction, cancelled, emit_batch)
        availability = inspect_sam2_environment(
            self.checkpoint_path, self.config_path)
        if availability.available:
            return Sam2PropagationBackend(
                self.checkpoint_path, self.config_path).propagate(
                    request, direction, cancelled, emit_batch)
        if self.choice == 'sam2':
            raise RuntimeError(
                'SAM 2 propagation is unavailable: %s. '
                'Select OpenCV or Auto to use the portable backend.' %
                availability.message)
        return self._opencv().propagate(
            request, direction, cancelled, emit_batch)

    @staticmethod
    def _opencv():
        from libs.core.video_tracking import OpenCVPropagationBackend
        return OpenCVPropagationBackend()


def _load_sam2_runtime():
    """Load heavyweight optional modules only inside an active SAM 2 run."""
    from libs.core.video_decoder import load_video_dependencies

    _av, np = load_video_dependencies()
    try:
        cv2 = importlib.import_module('cv2')
        torch = importlib.import_module('torch')
        sam2 = importlib.import_module('sam2')
        build_module = importlib.import_module('sam2.build_sam')
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            'SAM 2 propagation requires a source-installed SAM 2 and '
            'CUDA-enabled PyTorch runtime: %s' % exc)
    return (
        torch, np, cv2, sam2,
        build_module.build_sam2_video_predictor,
    )


def _config_name(config_path, sam2_module):
    """Translate a selected package config file to Hydra's package name."""
    package_dir = os.path.dirname(os.path.realpath(sam2_module.__file__))
    config_path = os.path.realpath(config_path)
    relative = os.path.relpath(config_path, package_dir)
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        raise RuntimeError(
            'SAM 2 config must be selected from the source-installed sam2 '
            'package directory')
    return relative.replace(os.sep, '/')


def _is_rectangle(geometry):
    return (
        geometry is not None and len(geometry) == 4
        and not isinstance(geometry[0], (list, tuple)))


def _seed_mask(geometry, width, height, cv2, np):
    mask = np.zeros((height, width), dtype=np.uint8)
    if geometry is None:
        return mask.astype(bool)
    if _is_rectangle(geometry):
        xmin, ymin, xmax, ymax = geometry_bounds(geometry)
        x0 = max(0, min(width - 1, int(math.floor(xmin))))
        y0 = max(0, min(height - 1, int(math.floor(ymin))))
        x1 = max(0, min(width, int(math.ceil(xmax))))
        y1 = max(0, min(height, int(math.ceil(ymax))))
        if x1 > x0 and y1 > y0:
            cv2.rectangle(
                mask, (x0, y0), (x1 - 1, y1 - 1), 1, thickness=-1)
        return mask.astype(bool)
    points = np.asarray(
        [[int(round(point[0])), int(round(point[1]))]
         for point in geometry], dtype=np.int32)
    points[:, 0] = np.clip(points[:, 0], 0, width - 1)
    points[:, 1] = np.clip(points[:, 1], 0, height - 1)
    if len(points) >= 3:
        cv2.fillPoly(mask, [points], 1)
    return mask.astype(bool)


def _mask_data(mask_logits, np):
    value = mask_logits
    for method in ('detach', 'cpu'):
        callback = getattr(value, method, None)
        if callback is not None:
            value = callback()
    callback = getattr(value, 'numpy', None)
    if callback is not None:
        value = callback()
    logits = np.asarray(value).squeeze()
    if logits.ndim != 2:
        raise RuntimeError('SAM 2 returned a mask with an unexpected shape')
    maximum = float(logits.max()) if logits.size else float('-inf')
    quality = (
        1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, maximum))))
        if math.isfinite(maximum) else 0.0)
    return logits > 0.0, quality


def _mask_geometry(mask, rectangle, cv2, np):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None
    if rectangle:
        xmin = int(xs.min())
        ymin = int(ys.min())
        xmax = int(xs.max()) + 1
        ymax = int(ys.max()) + 1
        return [float(xmin), float(ymin), float(xmax), float(ymax)]
    contours, _hierarchy = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    if cv2.contourArea(contour) <= 0:
        return None
    epsilon = max(1.0, .01 * cv2.arcLength(contour, True))
    simplified = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
    if len(simplified) < 3:
        return None
    return [[float(point[0]), float(point[1])] for point in simplified]


def _rescale_keypoints_to_bounds(keypoints, old_geometry, new_geometry):
    if keypoints is None:
        return None
    old = geometry_bounds(old_geometry)
    new = geometry_bounds(new_geometry)
    if old is None or new is None:
        return keypoints
    old_width = max(1e-9, old[2] - old[0])
    old_height = max(1e-9, old[3] - old[1])
    output = []
    for item in keypoints:
        if item is None:
            output.append(None)
            continue
        x_ratio = (float(item[0]) - old[0]) / old_width
        y_ratio = (float(item[1]) - old[1]) / old_height
        output.append([
            new[0] + x_ratio * (new[2] - new[0]),
            new[1] + y_ratio * (new[3] - new[1]), item[2],
        ])
    return output


def _extract_frames(request, directory, cancelled, cv2, np):
    """Decode exact display-oriented PTS frames to a temporary JPEG sequence."""
    from libs.core.video_decoder import (
        _oriented_array, _rotation_for_frame, _rotation_for_stream,
        load_video_dependencies,
    )
    from libs.core.video_tracking import PropagationCancelled

    av, _loaded_np = load_video_dependencies()
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
        container.seek(
            int(request.start_pts), stream=stream,
            backward=True, any_frame=False)
        points = []
        width = height = None
        for frame in container.decode(stream):
            if cancelled():
                raise PropagationCancelled('propagation cancelled')
            if frame.pts is None or frame.pts < request.start_pts:
                continue
            if frame.pts > request.end_pts:
                break
            if (request.direction > 0 and frame.pts < request.current_pts) \
                    or (request.direction < 0
                        and frame.pts > request.current_pts):
                continue
            array = _oriented_array(
                frame, _rotation_for_frame(frame, rotation), np)
            height, width = array.shape[:2]
            path = os.path.join(directory, '%08d.jpg' % len(points))
            if not cv2.imwrite(path, cv2.cvtColor(
                    array, cv2.COLOR_RGB2BGR),
                    [int(cv2.IMWRITE_JPEG_QUALITY), 95]):
                raise RuntimeError('failed to stage a video frame for SAM 2')
            points.append(int(frame.pts))
        if not points or request.current_pts not in points:
            raise RuntimeError(
                'current propagation frame is no longer decodable')
        return tuple(points), int(width), int(height)
    finally:
        container.close()


def _release_sam2_state(predictor, state):
    """Release inference tensors plus SAM 2's unregistered module caches."""
    reset = getattr(predictor, 'reset_state', None)
    if reset is not None:
        reset(state)
    clear_state = getattr(state, 'clear', None)
    if clear_state is not None:
        clear_state()
    modules = getattr(predictor, 'modules', None)
    if modules is None:
        return
    for module in modules():
        cache = getattr(module, 'cache', None)
        if isinstance(cache, dict):
            cache.clear()


def _release_cuda_memory(torch):
    """Release PyTorch caches initialized by an otherwise completed run."""
    torch.cuda.empty_cache()
    clear_workspaces = getattr(
        getattr(torch, '_C', None), '_cuda_clearCublasWorkspaces', None)
    if clear_workspaces is not None:
        clear_workspaces()
        torch.cuda.empty_cache()


class Sam2PropagationBackend(PropagationBackend):
    """Official source-installed SAM 2 adapter with local-only model files."""

    name = 'sam2'

    def __init__(self, checkpoint_path, config_path):
        self.checkpoint_path = str(checkpoint_path)
        self.config_path = str(config_path)

    def propagate(self, request, direction, cancelled, emit_batch):
        if direction not in (-1, 1):
            raise ValueError('propagation direction must be -1 or 1')
        if not request.seeds:
            raise ValueError('propagation requires at least one seed')
        availability = inspect_sam2_environment(
            self.checkpoint_path, self.config_path)
        if not availability.available:
            raise RuntimeError(
                'SAM 2 propagation is unavailable: %s' %
                availability.message)
        current_fingerprint = fingerprint_video(request.source_path)
        if (current_fingerprint is None
                or not request.fingerprint.content_matches(
                    current_fingerprint)):
            raise RuntimeError(
                'video media changed after propagation was requested')

        torch, np, cv2, sam2, builder = _load_sam2_runtime()
        predictor = state = None
        results = mask_logits = masks = raw_mask = None
        with tempfile.TemporaryDirectory(prefix='labelimgpp-sam2-') as frames:
            points, width, height = _extract_frames(
                request, frames, cancelled, cv2, np)
            pts_to_index = {pts: index for index, pts in enumerate(points)}
            current_index = pts_to_index[request.current_pts]
            endpoint = request.end_pts if direction > 0 else request.start_pts
            endpoint_index = min(
                range(len(points)), key=lambda index: abs(points[index] - endpoint))
            max_frames = abs(endpoint_index - current_index)
            config_name = _config_name(self.config_path, sam2)
            predictor = builder(
                config_name, self.checkpoint_path, device='cuda',
                apply_postprocessing=False)
            observations = []
            gaps = []
            failures = {}
            pending_observations = []
            pending_gaps = []
            seeds = {item.track_id: item for item in request.seeds}
            anchors = {
                (item.track_id, int(item.pts)): item
                for item in request.manual_anchors
                if item.track_id in seeds and int(item.pts) in pts_to_index
            }
            anchors.update(
                ((item.track_id, int(item.pts)), item)
                for item in request.seeds)
            track_states = {
                track_id: {
                    'geometry': seed.geometry,
                    'keypoints': seed.keypoints,
                    'rectangle': _is_rectangle(seed.geometry),
                    'gap_start': None,
                    'gap_end': None,
                    'active': True,
                }
                for track_id, seed in seeds.items()
            }

            def close_gap(track_id, track_state, resumed=False):
                if track_state['gap_start'] is None:
                    return
                gap = TrackGapRecord(
                    track_id,
                    min(track_state['gap_start'], track_state['gap_end']),
                    max(track_state['gap_start'], track_state['gap_end']),
                    'occluded', self.name, request.document_revision)
                gaps.append(gap)
                pending_gaps.append(gap)
                failures[track_id] = 'occluded'
                track_state['gap_start'] = None
                track_state['gap_end'] = None
                if resumed:
                    track_state['active'] = True

            def mark_gap(track_id, track_state, pts):
                if track_state['gap_start'] is None:
                    track_state['gap_start'] = int(pts)
                track_state['gap_end'] = int(pts)
                track_state['active'] = False
                failures[track_id] = 'occluded'

            started = time.monotonic()
            processed = 0
            last_pts = request.current_pts
            try:
                with torch.inference_mode():
                    state = predictor.init_state(
                        video_path=frames, offload_video_to_cpu=True,
                        offload_state_to_cpu=False,
                        async_loading_frames=False)
                    for (track_id, pts), anchor in sorted(
                            anchors.items(), key=lambda item: item[0][1]):
                        if not anchor.present or anchor.geometry is None:
                            continue
                        predictor.add_new_mask(
                            inference_state=state,
                            frame_idx=pts_to_index[pts], obj_id=track_id,
                            mask=_seed_mask(
                                anchor.geometry, width, height, cv2, np))
                    results = predictor.propagate_in_video(
                        state, start_frame_idx=current_index,
                        max_frame_num_to_track=max_frames,
                        reverse=direction < 0)
                    for frame_index, object_ids, mask_logits in results:
                        if cancelled():
                            from libs.core.video_tracking import \
                                PropagationCancelled
                            raise PropagationCancelled(
                                'propagation cancelled')
                        pts = points[int(frame_index)]
                        if pts == request.current_pts:
                            continue
                        processed += 1
                        last_pts = pts
                        masks = {
                            str(object_id): mask_logits[index]
                            for index, object_id in enumerate(object_ids)
                        }
                        for track_id, track_state in track_states.items():
                            anchor = anchors.get((track_id, pts))
                            if anchor is not None:
                                if anchor.present and anchor.geometry is not None:
                                    close_gap(
                                        track_id, track_state, resumed=True)
                                    track_state['geometry'] = anchor.geometry
                                    track_state['keypoints'] = anchor.keypoints
                                else:
                                    mark_gap(track_id, track_state, pts)
                                continue
                            if not track_state['active']:
                                mark_gap(track_id, track_state, pts)
                                continue
                            raw_mask = masks.get(str(track_id))
                            if raw_mask is None:
                                mark_gap(track_id, track_state, pts)
                                continue
                            mask, quality = _mask_data(raw_mask, np)
                            geometry = _mask_geometry(
                                mask, track_state['rectangle'], cv2, np)
                            if geometry is None:
                                mark_gap(track_id, track_state, pts)
                                continue
                            close_gap(track_id, track_state, resumed=True)
                            keypoints = _rescale_keypoints_to_bounds(
                                track_state['keypoints'],
                                track_state['geometry'], geometry)
                            observation = ObservationRecord(
                                track_id, int(pts), geometry,
                                keypoints=keypoints, present=True,
                                # Provisional until reviewed, same contract as
                                # the portable OpenCV backend.
                                source='tracker', review_state='pending',
                                anchor=False, quality=quality,
                                revision=request.document_revision)
                            observations.append(observation)
                            pending_observations.append(observation)
                            track_state['geometry'] = geometry
                            track_state['keypoints'] = keypoints
                        elapsed = max(1e-9, time.monotonic() - started)
                        eta = elapsed / processed * max(
                            0, max_frames - processed)
                        emit_batch(PropagationBatch(
                            request.request_id, request.generation,
                            direction,
                            observations=tuple(pending_observations),
                            gaps=tuple(pending_gaps),
                            processed_frames=processed,
                            total_frames=max_frames,
                            active_tracks=sum(
                                1 for item in track_states.values()
                                if item['active']),
                            completed_tracks=sum(
                                1 for item in track_states.values()
                                if not item['active']),
                            eta_seconds=eta))
                        pending_observations = []
                        pending_gaps = []
                for track_id, track_state in track_states.items():
                    if track_state['gap_start'] is not None:
                        track_state['gap_end'] = last_pts
                        close_gap(track_id, track_state)
                emit_batch(PropagationBatch(
                    request.request_id, request.generation, direction,
                    observations=tuple(pending_observations),
                    gaps=tuple(pending_gaps),
                    processed_frames=processed, total_frames=max_frames,
                    active_tracks=sum(
                        1 for item in track_states.values()
                        if item['active']),
                    completed_tracks=sum(
                        1 for item in track_states.values()
                        if not item['active']),
                    eta_seconds=0.0, finished=True))
            finally:
                try:
                    if predictor is not None and state is not None:
                        _release_sam2_state(predictor, state)
                except (AttributeError, KeyError, RuntimeError, TypeError):
                    pass
                finally:
                    state = None
                    predictor = None
                    results = None
                    mask_logits = None
                    masks = None
                    raw_mask = None
                    gc.collect()
                    try:
                        _release_cuda_memory(torch)
                    except (AttributeError, RuntimeError):
                        pass

        final_fingerprint = fingerprint_video(request.source_path)
        if (final_fingerprint is None
                or not request.fingerprint.content_matches(
                    final_fingerprint)):
            raise RuntimeError('video media changed during propagation')
        return PropagationResult(
            request.request_id, request.generation,
            request.document_revision,
            observations=tuple(observations), gaps=tuple(gaps),
            failures=tuple(sorted(failures.items())))
