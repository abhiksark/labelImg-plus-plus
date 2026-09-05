#!/usr/bin/env python3
"""Five-run Linux workstation profiler for generated LabelImg++ corpora."""

import argparse
import cProfile
import csv
import gc
import hashlib
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
import tracemalloc


REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)
if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import (  # noqa: E402
    PYQT_VERSION_STR, QT_VERSION_STR, QCoreApplication, QEvent, QEventLoop,
    QPointF, QTimer,
)
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication, QListWidget  # noqa: E402

from libs.core.dataset import DatasetSnapshot  # noqa: E402
from libs.core.image_pipeline import FrameCache, load_image_result  # noqa: E402
from libs.core.save_pipeline import SaveRequest, write_save_request  # noqa: E402
from libs.core.shape import Shape, ShapeType  # noqa: E402
from libs.core.task_coordinator import (  # noqa: E402
    JobPriority, TaskCoordinator,
)
from libs.formats.annotation_probe import (  # noqa: E402
    probe, shared_json_cache,
)
from libs.formats.labelFile import LabelFileFormat  # noqa: E402
from libs.widgets.canvas import Canvas  # noqa: E402
from libs.widgets.galleryWidget import (  # noqa: E402
    AnnotationStatus, GalleryWidget, ThumbnailLoaderWorker,
)


TARGETS = {
    'event_loop_latency_p95_ms': 50.0,
    'event_loop_latency_max_ms': 100.0,
    'navigation_cold_p95_ms': 500.0,
    'navigation_prefetched_p95_ms': 100.0,
    'first_image_ms': 1000.0,
    'list_complete_ms': 2000.0,
    'gallery_filter_p95_ms': 50.0,
    'gallery_scroll_p95_ms': 50.0,
    'canvas_hover_p95_ms': 50.0,
    'canvas_move_p95_ms': 50.0,
    'canvas_paint_p95_ms': 50.0,
    'progress_gap_max_ms': 250.0,
    'cancellation_ack_ms': 500.0,
    'cache_bytes': 128 * 1024 * 1024,
    'rss_growth_percent': 10.0,
}


class ProfileWidgets:
    """Persistent widgets matching repeated cycles in one application."""

    def __init__(self):
        self.file_list = QListWidget()
        self.gallery = GalleryWidget(show_size_slider=False)
        self.gallery.resize(1000, 700)
        self.gallery.show()
        self.canvas = Canvas()
        self.canvas.resize(800, 600)
        self.canvas.show()

    def close(self, application):
        self.gallery.clear()
        self.gallery.thread_pool.clear()
        self.gallery.thread_pool.waitForDone(5000)
        for widget in (self.file_list, self.gallery, self.canvas):
            widget.close()
            widget.deleteLater()
        _release_qt_objects(application)


def percentile(values, fraction):
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(
        len(ordered) - 1, int(len(ordered) * fraction) - 1))
    return ordered[index]


def distribution(values):
    values = list(values)
    return {
        'median': statistics.median(values) if values else 0.0,
        'p95': percentile(values, .95),
        'max': max(values) if values else 0.0,
    }


def _process_sample():
    result = {}
    try:
        import psutil
        process = psutil.Process()
        io_counters = process.io_counters()
        result.update({
            'rss_bytes': process.memory_info().rss,
            'threads': process.num_threads(),
            'read_bytes': io_counters.read_bytes,
            'write_bytes': io_counters.write_bytes,
            'cpu_user_seconds': process.cpu_times().user,
            'cpu_system_seconds': process.cpu_times().system,
        })
    except ImportError:
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            multiplier = 1024 if sys.platform.startswith('linux') else 1
            result['rss_bytes'] = usage.ru_maxrss * multiplier
        except (ImportError, AttributeError):
            pass
    return result


def _cpu_name():
    try:
        with open('/proc/cpuinfo', 'r') as stream:
            for line in stream:
                if line.lower().startswith('model name'):
                    return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def metadata(workload):
    dirty = None
    source_fingerprint = None
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], text=True,
            cwd=REPOSITORY_ROOT).strip()
        tracked_diff = subprocess.check_output(
            ['git', 'diff', '--binary', 'HEAD', '--'],
            cwd=REPOSITORY_ROOT)
        untracked_output = subprocess.check_output(
            ['git', 'ls-files', '--others', '--exclude-standard', '-z'],
            cwd=REPOSITORY_ROOT)
        untracked = sorted(
            path for path in untracked_output.split(b'\0') if path)
        digest = hashlib.sha256()
        digest.update(commit.encode('ascii'))
        digest.update(tracked_diff)
        for relative_path in untracked:
            digest.update(b'\0' + relative_path + b'\0')
            try:
                with open(os.path.join(
                        REPOSITORY_ROOT,
                        os.fsdecode(relative_path)), 'rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
            except OSError:
                digest.update(b'<unreadable>')
        dirty = bool(tracked_diff or untracked)
        source_fingerprint = digest.hexdigest()
    except Exception:
        commit = None
    try:
        filesystem = subprocess.check_output(
            ['stat', '-f', '-c', '%T', workload], text=True).strip()
    except Exception:
        filesystem = None
    result = {
        'commit': commit,
        'dirty': dirty,
        'source_fingerprint': source_fingerprint,
        'python': sys.version.split()[0],
        'pyqt': PYQT_VERSION_STR,
        'qt': QT_VERSION_STR,
        'platform': platform.platform(),
        'cpu': _cpu_name(),
        'logical_cpus': os.cpu_count(),
        'filesystem': filesystem,
        'display_backend': (
            os.environ.get('XDG_SESSION_TYPE')
            or os.environ.get('QT_QPA_PLATFORM')),
    }
    try:
        import psutil
        result['ram_bytes'] = psutil.virtual_memory().total
    except ImportError:
        pass
    result.update(_process_sample())
    return result


def _record(trace_events, iteration, name, started, ended, category='profile'):
    trace_events.append({
        'name': name,
        'cat': category,
        'ph': 'X',
        'ts': started * 1_000_000,
        'dur': (ended - started) * 1_000_000,
        'pid': os.getpid(),
        'tid': threading.get_ident(),
        'args': {'iteration': iteration},
    })
    return (ended - started) * 1000


def _wait_for(application, predicate, timeout=60.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        if time.monotonic() >= deadline:
            raise RuntimeError('timed out waiting for Qt worker completion')


def _release_qt_objects(application):
    application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    gc.collect()


def _format_for_corpus(corpus):
    return {
        'yolo': LabelFileFormat.YOLO,
        'voc': LabelFileFormat.PASCAL_VOC,
        'coco': LabelFileFormat.COCO,
        'compatibility': LabelFileFormat.CREATE_ML,
    }.get(corpus, LabelFileFormat.PASCAL_VOC)


def _catalog_with_latency(application, snapshot, iteration, trace_events):
    coordinator = TaskCoordinator()
    completed = []
    errors = []
    statuses = {}
    latencies = []
    progress_times = []
    interval = 0.010
    last_tick = [time.perf_counter()]

    timer = QTimer()
    timer.setInterval(int(interval * 1000))

    def tick():
        now = time.perf_counter()
        latencies.append(max(0.0, now - last_tick[0] - interval) * 1000)
        last_tick[0] = now

    def catalog(handle):
        last_progress = time.monotonic()
        for index, path in enumerate(snapshot.image_paths, 1):
            handle.check_cancelled()
            info = probe(
                path, snapshot.save_dir, resolver=snapshot.resolver,
                json_cache=shared_json_cache)
            statuses[path] = (
                AnnotationStatus.VERIFIED if info.verified
                else AnnotationStatus.HAS_LABELS if info.has_labels
                else AnnotationStatus.NO_LABELS)
            now = time.monotonic()
            if now - last_progress >= .20 or index == len(snapshot.image_paths):
                handle.report_progress(index)
                last_progress = now
        return len(statuses)

    handle = coordinator.submit(
        'background', catalog, priority=JobPriority.CATALOG,
        key='profile-catalog', latest=True)
    handle.progress.connect(
        lambda _value: progress_times.append(time.perf_counter()))
    handle.result.connect(completed.append)
    handle.error.connect(errors.append)
    timer.timeout.connect(tick)
    timer.start()
    started = time.perf_counter()
    last_tick[0] = started
    _wait_for(application, lambda: bool(completed or errors))
    ended = time.perf_counter()
    timer.stop()
    coordinator.shutdown()
    if errors:
        raise RuntimeError(errors[0])
    catalog_ms = _record(
        trace_events, iteration, 'annotation.catalog', started, ended)
    progress_points = [started] + progress_times + [ended]
    progress_gaps = [
        (right - left) * 1000
        for left, right in zip(progress_points, progress_points[1:])
    ]
    return statuses, catalog_ms, latencies, progress_gaps


def _navigation_metrics(snapshot, label_format, iteration, trace_events):
    count = len(snapshot.image_paths)
    indexes = sorted({0, count // 4, count // 2, 3 * count // 4, count - 1})
    paths = [snapshot.image_paths[index] for index in indexes if count]
    cache = FrameCache(max_images=5, max_bytes=96 * 1024 * 1024)
    cold = []
    for path in paths:
        started = time.perf_counter()
        result = load_image_result(
            path, resolver=snapshot.resolver,
            image_list=snapshot.image_paths, save_dir=snapshot.save_dir,
            label_file_format=label_format)
        ended = time.perf_counter()
        cold.append(_record(
            trace_events, iteration, 'image.decode', started, ended))
        cache.put(result)
    prefetched = []
    for _cycle in range(20):
        for path in paths:
            started = time.perf_counter()
            if cache.get(path) is None:
                raise RuntimeError('fingerprinted frame cache missed')
            ended = time.perf_counter()
            prefetched.append((ended - started) * 1000)
    return cold, prefetched, cache.byte_size


def _gallery_metrics(application, gallery, snapshot, statuses, iteration,
                     trace_events):
    started = time.perf_counter()
    gallery.set_dataset_snapshot(snapshot)
    _wait_for(
        application,
        lambda: gallery.list_widget.count() == len(snapshot.image_paths))
    ended = time.perf_counter()
    complete_ms = _record(
        trace_events, iteration, 'gallery.populate', started, ended)

    gallery.update_all_statuses(statuses)
    filter_times = []
    for filter_index in (1, 2, 3, 0):
        started = time.perf_counter()
        gallery.set_status_filter(filter_index)
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        filter_times.append((time.perf_counter() - started) * 1000)

    scroll_times = []
    scrollbar = gallery.list_widget.verticalScrollBar()
    maximum = max(1, scrollbar.maximum())
    for step in range(20):
        started = time.perf_counter()
        scrollbar.setValue(int(maximum * step / 19))
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        scroll_times.append((time.perf_counter() - started) * 1000)

    thumbnail_ms = 0.0
    if snapshot.image_paths:
        worker = ThumbnailLoaderWorker(
            snapshot.image_paths[0], 100, snapshot.save_dir,
            snapshot.image_paths, resolver=snapshot.resolver)
        started = time.perf_counter()
        worker.load()
        thumbnail_ms = (time.perf_counter() - started) * 1000
    gallery.thread_pool.clear()
    gallery.thread_pool.waitForDone(5000)
    return complete_ms, filter_times, scroll_times, thumbnail_ms


def _shape_from_tuple(values):
    label, points = values[:2]
    shape_type = values[5] if len(values) > 5 else 'rectangle'
    if isinstance(shape_type, ShapeType):
        enum_type = shape_type
    else:
        enum_type = (ShapeType.POLYGON if shape_type == 'polygon'
                     else ShapeType.RECTANGLE)
    shape = Shape(label=label, shape_type=enum_type)
    shape.points = [QPointF(float(x), float(y)) for x, y in points]
    shape.close()
    if len(values) > 6:
        shape.keypoints = values[6]
    return shape


def _canvas_metrics(application, canvas, workload_root, iteration,
                    trace_events):
    root = os.path.join(workload_root, 'canvas-stress')
    image_path = os.path.join(root, 'stress.jpg')
    if not os.path.isfile(image_path):
        return [], [], []
    snapshot = DatasetSnapshot.from_images(
        [image_path], root_dir=root, save_dir=root)
    result = load_image_result(
        image_path, resolver=snapshot.resolver,
        image_list=snapshot.image_paths, save_dir=root,
        label_file_format=LabelFileFormat.COCO)
    canvas.load_pixmap(QPixmap.fromImage(result.image))
    canvas.load_shapes([_shape_from_tuple(values) for values in result.shapes])
    canvas.show()
    application.processEvents()

    hover = []
    for index in range(500):
        point = QPointF((index * 37) % 2048, (index * 53) % 2048)
        started = time.perf_counter()
        canvas._spatial_index.query(point, margin=canvas.epsilon)
        hover.append((time.perf_counter() - started) * 1000)

    moves = []
    for index in range(min(100, len(canvas.shapes))):
        shape = canvas.shapes[index]
        started = time.perf_counter()
        shape.move_by(QPointF(1, 0))
        canvas.reindex_shape(shape)
        moves.append((time.perf_counter() - started) * 1000)

    paints = []
    target = QPixmap(canvas.size())
    for _index in range(5):
        started = time.perf_counter()
        canvas.render(target)
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        ended = time.perf_counter()
        paints.append(_record(
            trace_events, iteration, 'canvas.paint', started, ended))
    return hover, moves, paints


def _save_metric(snapshot, label_format, iteration, trace_events):
    if not snapshot.image_paths:
        return 0.0
    with tempfile.TemporaryDirectory(prefix='labelimgpp-save-profile-') as root:
        extension = '.xml' if label_format == LabelFileFormat.PASCAL_VOC \
            else '.txt'
        if label_format in (LabelFileFormat.COCO, LabelFileFormat.CREATE_ML):
            extension = '.json'
        request = SaveRequest(
            image_path=snapshot.image_paths[0],
            annotation_path=os.path.join(root, 'annotation' + extension),
            label_file_format=label_format,
            shapes=(), class_list=('object',), verified=False, revision=0)
        started = time.perf_counter()
        write_save_request(request)
        ended = time.perf_counter()
        return _record(
            trace_events, iteration, 'annotation.save', started, ended)


def _cancellation_metric(application):
    coordinator = TaskCoordinator(logical_cpus=2)
    started_running = threading.Event()
    finished = []

    def run(handle):
        started_running.set()
        while True:
            handle.check_cancelled()

    handle = coordinator.submit(
        'background', run, priority=JobPriority.BULK,
        key='cancellation-probe', latest=True)
    handle.finished.connect(lambda: finished.append(True))
    _wait_for(application, started_running.is_set)
    started = time.perf_counter()
    handle.cancel()
    _wait_for(application, lambda: bool(finished), timeout=5.0)
    elapsed = (time.perf_counter() - started) * 1000
    coordinator.shutdown()
    return elapsed


def _memory_cycle_metric(application, widgets):
    """Measure repeated navigation/gallery-style use without rebuilding UI."""
    gallery = widgets.gallery
    canvas = widgets.canvas
    target = QPixmap(canvas.size())
    before = _process_sample().get('rss_bytes')
    scrollbar = gallery.list_widget.verticalScrollBar()
    maximum = max(1, scrollbar.maximum())
    for cycle in range(5):
        for filter_index in (1, 2, 3, 0):
            gallery.set_status_filter(filter_index)
        scrollbar.setValue(maximum if cycle % 2 else 0)
        for index in range(100):
            point = QPointF((index * 37) % 2048, (index * 53) % 2048)
            canvas._spatial_index.query(point, margin=canvas.epsilon)
        canvas.render(target)
        application.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
    gallery.thread_pool.waitForDone(5000)
    _release_qt_objects(application)
    after = _process_sample().get('rss_bytes')
    if before is None or after is None or not before:
        return 0.0
    return max(0.0, (after - before) / before * 100)


def measured_run(workload_root, corpus, application, widgets, iteration,
                 trace_events):
    root = os.path.join(workload_root, corpus)
    resources_before = _process_sample()
    started = time.perf_counter()
    snapshot = DatasetSnapshot.scan(root, save_dir=root)
    ended = time.perf_counter()
    scan_ms = _record(
        trace_events, iteration, 'directory.scan', started, ended)

    list_widget = widgets.file_list
    list_widget.clear()
    started = time.perf_counter()
    list_widget.addItems(snapshot.image_paths)
    ended = time.perf_counter()
    list_apply_ms = _record(
        trace_events, iteration, 'file-list.apply', started, ended)

    statuses, catalog_ms, latencies, progress_gaps = _catalog_with_latency(
        application, snapshot, iteration, trace_events)
    label_format = _format_for_corpus(corpus)
    navigation_root = os.path.join(workload_root, 'navigation')
    navigation_snapshot = DatasetSnapshot.scan(
        navigation_root, save_dir=navigation_root)
    cold, prefetched, cache_bytes = _navigation_metrics(
        navigation_snapshot, LabelFileFormat.PASCAL_VOC,
        iteration, trace_events)
    gallery_complete, filters, scrolls, thumbnail_ms = _gallery_metrics(
        application, widgets.gallery, snapshot, statuses,
        iteration, trace_events)
    cache_bytes += widgets.gallery.thumbnail_cache.bytes_used
    hover, moves, paints = _canvas_metrics(
        application, widgets.canvas, workload_root, iteration, trace_events)
    save_ms = _save_metric(
        snapshot, label_format, iteration, trace_events)
    cancellation_ms = _cancellation_metric(application)
    cycle_rss_growth = _memory_cycle_metric(application, widgets)
    _release_qt_objects(application)
    resources_after = _process_sample()

    result = {
        'iteration': iteration,
        'images': len(snapshot.image_paths),
        'scan_ms': scan_ms,
        'file_list_apply_ms': list_apply_ms,
        'catalog_ms': catalog_ms,
        'catalog_images_per_second': (
            len(snapshot.image_paths) / max(catalog_ms / 1000, 1e-9)),
        'event_loop_latency_p95_ms': percentile(latencies, .95),
        'event_loop_latency_max_ms': max(latencies or [0.0]),
        'progress_gap_max_ms': max(progress_gaps or [0.0]),
        'navigation_cold_p95_ms': percentile(cold, .95),
        'navigation_prefetched_p95_ms': percentile(prefetched, .95),
        'first_image_ms': scan_ms + list_apply_ms + (cold[0] if cold else 0),
        'list_complete_ms': scan_ms + list_apply_ms,
        'gallery_complete_ms': gallery_complete,
        'gallery_filter_p95_ms': percentile(filters, .95),
        'gallery_scroll_p95_ms': percentile(scrolls, .95),
        'thumbnail_ms': thumbnail_ms,
        'canvas_hover_p95_ms': percentile(hover, .95),
        'canvas_move_p95_ms': percentile(moves, .95),
        'canvas_paint_p95_ms': percentile(paints, .95),
        'save_ms': save_ms,
        'cancellation_ack_ms': cancellation_ms,
        'cache_bytes': cache_bytes,
        'cycle_rss_growth_percent': cycle_rss_growth,
    }
    for key, value in resources_after.items():
        result['end_' + key] = value
        before = resources_before.get(key)
        if before is not None and isinstance(value, (int, float)):
            result['delta_' + key] = value - before
    return result


def _acceptance(summary):
    operations = summary['operations']
    checks = {}
    for key, limit in TARGETS.items():
        if key == 'rss_growth_percent':
            value = summary.get(key, 0.0)
        else:
            values = operations.get(key, {})
            value = values.get('p95', values.get('max', 0.0))
            if key.endswith('_max_ms') or key in (
                    'progress_gap_max_ms', 'cache_bytes'):
                value = values.get('max', value)
        checks[key] = {
            'value': value,
            'limit': limit,
            'passed': value <= limit,
        }
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workload')
    parser.add_argument('--corpus', default='yolo')
    parser.add_argument('--output', default='profile-results')
    args = parser.parse_args()
    workload_root = os.path.abspath(args.workload)
    corpus_root = os.path.join(workload_root, args.corpus)
    if not os.path.isdir(corpus_root):
        raise SystemExit('corpus does not exist: %s' % corpus_root)
    output = os.path.abspath(args.output)
    os.makedirs(output, exist_ok=True)
    application = QApplication.instance() or QApplication([])
    widgets = ProfileWidgets()

    warmup_trace = []
    tracemalloc.start()
    profiler = cProfile.Profile()
    profiler.enable()
    measured_run(
        workload_root, args.corpus, application, widgets, 0, warmup_trace)
    profiler.disable()
    profiler.dump_stats(os.path.join(output, 'profile.prof'))
    with open(os.path.join(output, 'profile.txt'), 'w') as stream:
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats('cumulative').print_stats(80)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    _release_qt_objects(application)

    trace_events = []
    runs = []
    for iteration in range(1, 6):
        runs.append(measured_run(
            workload_root, args.corpus, application, widgets,
            iteration, trace_events))
    summary = metadata(corpus_root)
    summary['corpus'] = args.corpus
    summary['peak_tracemalloc_bytes'] = peak
    summary['runs'] = runs
    summary['operations'] = {}
    numeric_keys = sorted({
        key for run in runs for key, value in run.items()
        if key not in ('iteration', 'images')
        and isinstance(value, (int, float))
    })
    for key in numeric_keys:
        summary['operations'][key] = distribution(
            run[key] for run in runs if key in run)
    rss_values = [run.get('end_rss_bytes') for run in runs]
    rss_values = [value for value in rss_values if value is not None]
    if len(rss_values) >= 2 and rss_values[0]:
        summary['benchmark_process_rss_growth_percent'] = max(
            0.0, (rss_values[-1] - rss_values[0]) / rss_values[0] * 100)
    else:
        summary['benchmark_process_rss_growth_percent'] = 0.0
    summary['rss_growth_percent'] = max(
        run['cycle_rss_growth_percent'] for run in runs)
    summary['acceptance'] = _acceptance(summary)
    summary['passed'] = all(
        check['passed'] for check in summary['acceptance'].values())

    with open(os.path.join(output, 'summary.json'), 'w') as stream:
        json.dump(summary, stream, indent=2, sort_keys=True)
    with open(os.path.join(output, 'trace.json'), 'w') as stream:
        json.dump({'traceEvents': trace_events}, stream, separators=(',', ':'))
    fieldnames = sorted({key for run in runs for key in run})
    with open(os.path.join(output, 'resources.csv'), 'w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(runs)
    with open(os.path.join(output, 'comparison.md'), 'w') as stream:
        stream.write('# LabelImg++ performance run\n\n')
        stream.write('- Commit: `%s`\n' % summary['commit'])
        stream.write('- Dirty tree: `%s`\n' % summary['dirty'])
        stream.write('- Source fingerprint: `%s`\n'
                     % summary['source_fingerprint'])
        stream.write('- Corpus: `%s`\n' % args.corpus)
        stream.write('- Images: %d\n' % runs[0]['images'])
        stream.write('- Overall: **%s**\n\n' % (
            'PASS' if summary['passed'] else 'FAIL'))
        stream.write('| Target | Observed | Limit | Result |\n')
        stream.write('|---|---:|---:|---|\n')
        for key, check in summary['acceptance'].items():
            stream.write('| %s | %.3f | %.3f | %s |\n' % (
                key, check['value'], check['limit'],
                'PASS' if check['passed'] else 'FAIL'))
        stream.write('\n## All measurements\n\n')
        for key, values in summary['operations'].items():
            stream.write(
                '- %s: median %.3f, p95 %.3f, max %.3f\n' % (
                    key, values['median'], values['p95'], values['max']))
    widgets.close(application)
    print(os.path.join(output, 'summary.json'))
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
