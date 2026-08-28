#!/usr/bin/env python3
"""Five-run Linux workstation profiler for smart video annotation."""

import argparse
import cProfile
import csv
import gc
import json
import os
import platform
import pstats
import statistics
import subprocess
import sys
import tempfile
import threading
import time


REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)
if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QEventLoop, QPointF, QTimer  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from libs.core.image_pipeline import (  # noqa: E402
    FrameCache, load_image_result,
)
from libs.core.task_coordinator import JobCancelled, TaskCoordinator  # noqa: E402
from libs.core.video_decoder import VideoDecoderSession  # noqa: E402
from libs.core.video_export import export_video_frames  # noqa: E402
from libs.core.video_tracking import track_optical_flow  # noqa: E402
from libs.core.video_types import (  # noqa: E402
    ObservationRecord, TrackingRequest, TrackRecord, VideoExportRequest,
    VideoFrameRef,
)
from libs.formats.labelFile import LabelFileFormat  # noqa: E402


MIB = 1024 * 1024
TARGETS = {
    'first_frame_ms': 1000.0,
    'cold_seek_p95_ms': 500.0,
    'prefetched_seek_p95_ms': 100.0,
    'event_loop_latency_p95_ms': 50.0,
    'event_loop_latency_max_ms': 100.0,
    'progress_gap_max_ms': 250.0,
    'cancellation_ack_ms': 500.0,
    'combined_cache_bytes': 128 * MIB,
    'rss_growth_percent': 10.0,
}


def percentile(values, fraction):
    values = sorted(values)
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1,
                       int(len(values) * fraction) - 1))
    return values[index]


def distribution(values):
    values = list(values)
    return {
        'median': statistics.median(values) if values else 0.0,
        'p95': percentile(values, .95),
        'max': max(values) if values else 0.0,
    }


def _rss_bytes():
    try:
        import psutil
        return psutil.Process().memory_info().rss
    except ImportError:
        try:
            import resource
            multiplier = 1024 if sys.platform.startswith('linux') else 1
            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * \
                multiplier
        except (AttributeError, ImportError):
            return 0


def _metadata(workload):
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=REPOSITORY_ROOT,
            text=True).strip()
        dirty = bool(subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=REPOSITORY_ROOT))
    except (OSError, subprocess.CalledProcessError):
        commit = None
        dirty = None
    return {
        'commit': commit,
        'dirty': dirty,
        'python': sys.version.split()[0],
        'platform': platform.platform(),
        'logical_cpus': os.cpu_count(),
        'workload': os.path.abspath(workload),
    }


def _wait_for(application, predicate, timeout=60.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        application.processEvents(QEventLoop.AllEvents, 10)
        if time.monotonic() >= deadline:
            raise RuntimeError('timed out waiting for video worker')


def _duration_targets(decoder):
    start = decoder.start_pts or 0
    duration = decoder.duration_pts or max(1, decoder.time_base_den * 5)
    return tuple(start + int(duration * fraction)
                 for fraction in (.15, .35, .55, .75, .9))


def _timed_decode(path):
    started = time.perf_counter()
    decoder = VideoDecoderSession(path)
    try:
        result = decoder.decode_first()
        elapsed = (time.perf_counter() - started) * 1000
        return elapsed, result
    finally:
        decoder.close()


def _seek_metrics(path):
    decoder = VideoDecoderSession(path)
    cache = FrameCache(max_images=12, max_bytes=96 * MIB)
    cold = []
    cached = []
    try:
        decoder.decode_first()
        for target in _duration_targets(decoder):
            started = time.perf_counter()
            result = decoder.seek_pts(target)
            cold.append((time.perf_counter() - started) * 1000)
            if result is not None:
                cache.put(result)
        for result in tuple(cache._entries.values()):
            started = time.perf_counter()
            assert cache.get(result.frame_ref) is result
            cached.append((time.perf_counter() - started) * 1000)
        return (percentile(cold, .95), percentile(cached, .95),
                cache.byte_size, cache.max_bytes + 32 * MIB)
    finally:
        cache.clear()
        decoder.close()


def _event_loop_latency(application, path):
    decoder = VideoDecoderSession(path)
    coordinator = TaskCoordinator()
    completed = []
    errors = []
    latencies = []
    interval = .010
    last_tick = [time.perf_counter()]
    timer = QTimer()
    timer.setInterval(int(interval * 1000))

    def tick():
        now = time.perf_counter()
        latencies.append(max(0.0, now - last_tick[0] - interval) * 1000)
        last_tick[0] = now

    targets = _duration_targets(decoder)

    def seek_all(handle):
        results = []
        for target in targets:
            handle.check_cancelled()
            results.append(decoder.seek_pts(
                target, cancelled=handle.is_cancelled))
        return tuple(results)

    try:
        handle = coordinator.submit(
            'video', seek_all, key='profile-video-seek', latest=True)
        handle.result.connect(completed.append)
        handle.error.connect(errors.append)
        timer.timeout.connect(tick)
        last_tick[0] = time.perf_counter()
        timer.start()
        _wait_for(application, lambda: bool(completed or errors))
        timer.stop()
        if errors:
            raise RuntimeError(errors[0])
        return percentile(latencies, .95), max(latencies or (0.0,))
    finally:
        timer.stop()
        coordinator.shutdown(5000)
        decoder.close()


def run_video_soak(window, path, cycles=10, timeout=8.0):
    """Exercise real video ownership through bounded open/play/seek/close cycles.

    The summary is intentionally stateful rather than a pass/fail boolean so
    release tooling can retain the final owner state when a cycle fails.
    """
    from labelImgPlusPlus import DocumentKind

    application = QApplication.instance()
    if application is None:
        raise RuntimeError('run_video_soak requires a QApplication')
    cycles = int(cycles)
    if cycles < 1:
        raise ValueError('cycles must be positive')
    timeout = float(timeout)
    if timeout <= 0:
        raise ValueError('timeout must be positive')

    started = time.monotonic()
    completed = 0
    failures = []
    for cycle in range(1, cycles + 1):
        try:
            if not window.open_video(path):
                raise RuntimeError('open_video returned False')
            if (window.document_kind != DocumentKind.VIDEO
                    or window.current_video_frame_ref is None
                    or window.video_snapshot is None):
                raise RuntimeError('video did not publish a first frame')

            first_pts = window.current_video_frame_ref.pts
            window.play_pause_video()
            _wait_for(
                application,
                lambda: (window.current_video_frame_ref is not None
                         and window.current_video_frame_ref.pts > first_pts),
                timeout=timeout)
            window.pause_video()

            snapshot = window.video_snapshot
            midpoint = (int(snapshot.start_pts or 0)
                        + int(snapshot.duration_pts or 0) // 2)
            frame_ref = VideoFrameRef(
                snapshot.fingerprint, snapshot.stream_index, midpoint,
                snapshot.time_base_num, snapshot.time_base_den)
            window.request_video_frame(frame_ref)
            _wait_for(
                application,
                lambda: (not window._video_decode_in_flight
                         and not window.task_coordinator
                         .queue_depths()['video']),
                timeout=timeout)

            window.dirty = False
            window.close_file()
            _wait_for(application, window.task_coordinator.is_idle,
                      timeout=timeout)
            if (window.video_decoder is not None
                    or window.video_snapshot is not None
                    or window._video_decode_in_flight
                    or window.continuous_save._in_flight is not None):
                raise RuntimeError('close left video or save ownership active')
            completed += 1
        except Exception as exc:
            failures.append('cycle %d: %s' % (cycle, exc))
            try:
                window.pause_video()
                window.dirty = False
                window.close_file()
                _wait_for(application, window.task_coordinator.is_idle,
                          timeout=timeout)
            except Exception as cleanup_error:
                failures.append(
                    'cycle %d cleanup: %s' % (cycle, cleanup_error))
            break

    coordinator = window.task_coordinator
    return {
        'cycles': cycles,
        'completed_cycles': completed,
        'failures': tuple(failures),
        'remaining_jobs': coordinator.active_jobs(),
        'queue_depths': coordinator.queue_depths(),
        'elapsed_seconds': time.monotonic() - started,
        'decoder_active': window.video_decoder is not None,
        'session_active': window.video_snapshot is not None,
        'save_state': window.continuous_save.state,
        'save_in_flight': window.continuous_save._in_flight is not None,
        'video_decode_in_flight': bool(window._video_decode_in_flight),
        'document_kind': window.document_kind.value,
        'document_identity': window.document_identity,
    }


def _gui_workflow_metrics(application, path):
    """Exercise open, scrub, playback, timeline, canvas, and drawing in Qt."""
    from labelImgPlusPlus import DocumentKind, MainWindow
    from libs.core.shape import Shape, ShapeType

    latencies = []
    interval = .010
    last_tick = [time.perf_counter()]
    timer = QTimer()
    timer.setInterval(int(interval * 1000))

    def tick():
        now = time.perf_counter()
        latencies.append(max(0.0, now - last_tick[0] - interval) * 1000)
        last_tick[0] = now

    timer.timeout.connect(tick)
    window = MainWindow()
    window.show()
    application.processEvents()
    try:
        with tempfile.TemporaryDirectory(
                prefix='labelimgpp-video-gui-profile-') as root:
            project = os.path.join(root, 'profile.labelimgpp.sqlite')
            last_tick[0] = time.perf_counter()
            timer.start()
            started = time.perf_counter()
            window.request_open_video(
                path, project_path=project, skip_prompt=True)
            _wait_for(
                application,
                lambda: window.document_kind == DocumentKind.VIDEO)
            first_frame_ms = (time.perf_counter() - started) * 1000

            scrub_started = time.perf_counter()
            window.video_timeline._slider_pressed()
            window.video_timeline.slider.setValue(600_000)
            window.video_timeline._slider_released()
            _wait_for(
                application,
                lambda: not window.task_coordinator.queue_depths()['video'])
            application.processEvents()
            scrub_seek_ms = (time.perf_counter() - scrub_started) * 1000

            playback_start = window.current_video_frame_ref.pts
            playback_started = time.perf_counter()
            window.play_pause_video()
            _wait_for(
                application,
                lambda: (window.current_video_frame_ref is not None
                         and window.current_video_frame_ref.pts
                         > playback_start),
                timeout=5.0)
            playback_advance_ms = (
                time.perf_counter() - playback_started) * 1000
            window.pause_video()

            timeline_started = time.perf_counter()
            window.video_timeline.repaint()
            application.processEvents()
            timeline_paint_ms = (
                time.perf_counter() - timeline_started) * 1000

            width = max(8, window.video_snapshot.width)
            height = max(8, window.video_snapshot.height)
            shape = Shape(label='profile-object',
                          shape_type=ShapeType.RECTANGLE)
            left, top = width * .1, height * .1
            right, bottom = width * .3, height * .3
            for x, y in ((left, top), (right, top),
                         (right, bottom), (left, bottom)):
                shape.add_point(QPointF(x, y))
            shape.close()
            drawing_started = time.perf_counter()
            window._store_video_shape_as_manual(shape)
            window._on_video_model_mutation()
            window._materialize_video_frame(
                window.current_video_frame_ref.pts)
            application.processEvents()
            drawing_commit_ms = (
                time.perf_counter() - drawing_started) * 1000

            canvas_started = time.perf_counter()
            window.canvas.repaint()
            application.processEvents()
            canvas_paint_ms = (time.perf_counter() - canvas_started) * 1000
            timer.stop()
            return {
                'first_frame_ms': first_frame_ms,
                'event_loop_latency_p95_ms': percentile(latencies, .95),
                'event_loop_latency_max_ms': max(latencies or (0.0,)),
                'scrub_seek_ms': scrub_seek_ms,
                'playback_advance_ms': playback_advance_ms,
                'timeline_paint_ms': timeline_paint_ms,
                'drawing_commit_ms': drawing_commit_ms,
                'canvas_paint_ms': canvas_paint_ms,
            }
    finally:
        timer.stop()
        window.dirty = False
        window.close()
        application.processEvents()


class _TrackingHandle:
    def __init__(self):
        self.cancelled = threading.Event()
        self.progress_times = []

    def check_cancelled(self):
        if self.cancelled.is_set():
            raise JobCancelled()

    def is_cancelled(self):
        return self.cancelled.is_set()

    def report_progress(self, _value):
        self.progress_times.append(time.perf_counter())

    def begin_non_cancellable(self):
        self.check_cancelled()


def _tracking_request(path):
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        box_size = max(24, min(
            first.display_width, first.display_height) // 8)
        y0 = max(8, first.display_height // 3)
        track = TrackRecord(
            'profile-track', 'object', 'rectangle', (0, 255, 0, 255),
            revision=1)
        seed = ObservationRecord(
            track.track_id, first.frame_ref.pts,
            [16, y0, 16 + box_size, y0 + box_size],
            source='manual', review_state='accepted', anchor=True,
            revision=1)
        duration = decoder.duration_pts or int(5 / float(decoder.time_base))
        end_pts = min(
            first.frame_ref.pts + int(5 / float(decoder.time_base)),
            (decoder.start_pts or 0) + duration - 1)
        return TrackingRequest(
            1, 1, path, decoder.stream_index, first.frame_ref, end_pts, 1,
            track, seed, track.revision, 1)
    finally:
        decoder.close()


def _tracking_metrics(path):
    request = _tracking_request(path)
    handle = _TrackingHandle()
    started = time.perf_counter()
    track_optical_flow(request, handle)
    ended = time.perf_counter()
    points = [started] + handle.progress_times + [ended]
    progress_gap = max(
        ((right - left) * 1000
         for left, right in zip(points, points[1:])), default=0.0)

    cancel_handle = _TrackingHandle()
    finished = threading.Event()

    def cancellable():
        try:
            track_optical_flow(request, cancel_handle)
        except JobCancelled:
            pass
        finally:
            finished.set()

    worker = threading.Thread(target=cancellable, daemon=True)
    worker.start()
    time.sleep(.02)
    cancel_started = time.perf_counter()
    cancel_handle.cancelled.set()
    if not finished.wait(5.0):
        raise RuntimeError('tracking cancellation timed out')
    worker.join()
    cancellation_ms = (time.perf_counter() - cancel_started) * 1000
    return progress_gap, cancellation_ms


def _image_switch_metric(path):
    started = time.perf_counter()
    result = load_image_result(path)
    if result is None or result.image.isNull():
        raise RuntimeError('failed to decode switch image')
    return (time.perf_counter() - started) * 1000


def _export_metric(path):
    decoder = VideoDecoderSession(path)
    try:
        first = decoder.decode_first()
        second = decoder.next_frame()
        refs = (first.frame_ref,) + (
            (second.frame_ref,) if second is not None else ())
    finally:
        decoder.close()
    with tempfile.TemporaryDirectory(prefix='labelimgpp-video-profile-') as root:
        destination = os.path.join(root, 'export')
        request = VideoExportRequest(
            source_path=path, project_path='', destination=destination,
            stream_index=first.frame_ref.stream_index, frame_refs=refs,
            observations=(), tracks=(), frame_states=(),
            annotation_format=LabelFileFormat.PASCAL_VOC)
        started = time.perf_counter()
        export_video_frames(request, _TrackingHandle())
        elapsed = (time.perf_counter() - started) * 1000
        if not os.path.isfile(os.path.join(
                destination, 'video_export_manifest.json')):
            raise RuntimeError('video export did not publish its manifest')
        return elapsed


def measured_run(video_root, application, iteration):
    cfr = os.path.join(video_root, 'cfr.mp4')
    long_gop = os.path.join(video_root, 'long-gop.mp4')
    tracking = os.path.join(video_root, 'tracking-stress.mp4')
    navigation_4k = os.path.join(video_root, 'navigation-4k.mp4')
    navigation_8k = os.path.join(video_root, 'navigation-8k.mkv')
    switch_image = os.path.join(video_root, 'switch-image.jpg')
    required = (cfr, long_gop, tracking, navigation_4k, navigation_8k,
                switch_image)
    missing = [path for path in required if not os.path.isfile(path)]
    if missing:
        raise RuntimeError('missing video workload: %s' % missing[0])

    gc.collect()
    rss_before = _rss_bytes()
    gui = _gui_workflow_metrics(application, cfr)
    cold, prefetched, cache_bytes, combined = _seek_metrics(long_gop)
    progress_gap, cancellation = _tracking_metrics(tracking)
    image_switch_ms = _image_switch_metric(switch_image)
    export_ms = _export_metric(cfr)
    high_4k_ms, _frame_4k = _timed_decode(navigation_4k)
    high_8k_ms, _frame_8k = _timed_decode(navigation_8k)
    gc.collect()
    return {
        'iteration': iteration,
        'first_frame_ms': gui['first_frame_ms'],
        'cold_seek_p95_ms': cold,
        'prefetched_seek_p95_ms': prefetched,
        'event_loop_latency_p95_ms': gui['event_loop_latency_p95_ms'],
        'event_loop_latency_max_ms': gui['event_loop_latency_max_ms'],
        'scrub_seek_ms': gui['scrub_seek_ms'],
        'playback_advance_ms': gui['playback_advance_ms'],
        'timeline_paint_ms': gui['timeline_paint_ms'],
        'drawing_commit_ms': gui['drawing_commit_ms'],
        'canvas_paint_ms': gui['canvas_paint_ms'],
        'progress_gap_max_ms': progress_gap,
        'cancellation_ack_ms': cancellation,
        'video_cache_occupancy_bytes': cache_bytes,
        'combined_cache_bytes': combined,
        'navigation_4k_first_frame_ms': high_4k_ms,
        'navigation_8k_first_frame_ms': high_8k_ms,
        'image_switch_ms': image_switch_ms,
        'atomic_export_ms': export_ms,
        'rss_before_bytes': rss_before,
        'rss_after_bytes': _rss_bytes(),
    }


def _acceptance(summary):
    checks = {}
    for key, limit in TARGETS.items():
        if key == 'rss_growth_percent':
            value = summary[key]
        else:
            values = summary['operations'][key]
            value = values['max'] if key.endswith(
                ('_max_ms', '_bytes')) else values['p95']
        checks[key] = {
            'value': value, 'limit': limit, 'passed': value <= limit,
        }
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workload')
    parser.add_argument('--output', default='profile-results/video')
    args = parser.parse_args()
    video_root = os.path.join(os.path.abspath(args.workload), 'video')
    output = os.path.abspath(args.output)
    os.makedirs(output, exist_ok=True)
    application = QApplication.instance() or QApplication([])

    profiler = cProfile.Profile()
    profiler.enable()
    measured_run(video_root, application, 0)
    profiler.disable()
    profiler.dump_stats(os.path.join(output, 'profile.prof'))
    with open(os.path.join(output, 'profile.txt'), 'w') as stream:
        pstats.Stats(profiler, stream=stream).sort_stats(
            'cumulative').print_stats(80)

    runs = [measured_run(video_root, application, iteration)
            for iteration in range(1, 6)]
    summary = _metadata(video_root)
    summary['runs'] = runs
    summary['operations'] = {}
    keys = sorted({
        key for run in runs for key, value in run.items()
        if key != 'iteration' and isinstance(value, (int, float))
    })
    for key in keys:
        summary['operations'][key] = distribution(
            run[key] for run in runs)
    first_rss = runs[0]['rss_after_bytes']
    last_rss = runs[-1]['rss_after_bytes']
    summary['rss_growth_percent'] = (
        max(0.0, (last_rss - first_rss) / first_rss * 100)
        if first_rss else 0.0)
    summary['acceptance'] = _acceptance(summary)
    summary['passed'] = all(
        check['passed'] for check in summary['acceptance'].values())

    with open(os.path.join(output, 'summary.json'), 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
    with open(os.path.join(output, 'resources.csv'), 'w', newline='') as stream:
        writer = csv.DictWriter(
            stream, fieldnames=sorted({key for run in runs for key in run}))
        writer.writeheader()
        writer.writerows(runs)
    with open(os.path.join(output, 'comparison.md'), 'w') as stream:
        stream.write('# LabelImg++ smart-video performance run\n\n')
        stream.write('- Commit: `%s`\n' % summary['commit'])
        stream.write('- Dirty tree: `%s`\n' % summary['dirty'])
        stream.write('- Overall: **%s**\n\n' % (
            'PASS' if summary['passed'] else 'FAIL'))
        stream.write('| Target | Observed | Limit | Result |\n')
        stream.write('|---|---:|---:|---|\n')
        for key, check in summary['acceptance'].items():
            stream.write('| %s | %.3f | %.3f | %s |\n' % (
                key, check['value'], check['limit'],
                'PASS' if check['passed'] else 'FAIL'))
    print(os.path.join(output, 'summary.json'))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
