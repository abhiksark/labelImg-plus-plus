"""One progressive annotation catalog shared by every UI consumer."""

from dataclasses import dataclass
import os
import time

from PyQt5.QtCore import QObject, pyqtSignal

from libs.core.profiling import recorder as trace_recorder
from libs.core.task_coordinator import JobPriority
from libs.formats.annotation_probe import probe, shared_json_cache


NO_LABELS = 0
HAS_LABELS = 1
VERIFIED = 2


@dataclass(frozen=True)
class CatalogEntry:
    image_path: str
    annotation_path: object
    annotation_format: object
    status: int
    labels: tuple
    labels_complete: bool
    fingerprint: object


def _fingerprint(path):
    if not path:
        return None
    try:
        stat = os.stat(path)
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _catalog_entry(snapshot, image_path, include_labels, json_cache,
                   extensions=None):
    info = probe(
        image_path,
        snapshot.save_dir,
        want_labels=include_labels,
        image_list=snapshot.image_paths,
        resolver=snapshot.resolver,
        json_cache=json_cache,
        extensions=extensions,
    )
    if info.verified:
        status = VERIFIED
    elif info.has_labels:
        status = HAS_LABELS
    else:
        status = NO_LABELS
    labels_complete = not (
        info.fmt == 'yolo' and info.has_labels and not include_labels)
    return CatalogEntry(
        image_path=image_path,
        annotation_path=info.path,
        annotation_format=info.fmt,
        status=status,
        labels=tuple(info.labels),
        labels_complete=labels_complete,
        fingerprint=_fingerprint(info.path),
    )


class AnnotationCatalog(QObject):
    """Generation-safe catalog service using the coordinator background lane."""

    batch_ready = pyqtSignal(dict)
    statistics_ready = pyqtSignal(int, int, int, dict)
    progress = pyqtSignal(int, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, coordinator, parent=None, batch_size=100):
        super().__init__(parent)
        self.coordinator = coordinator
        self.batch_size = max(1, int(batch_size))
        self.entries = {}
        self.snapshot = None
        self._handle = None
        self._stats_handle = None
        self._want_statistics = False
        self._json_cache = shared_json_cache
        # Sidecar search order; MainWindow keeps this in step with the active
        # format so the catalog resolves the same file the canvas loads.
        self.extensions = None

    def start(self, snapshot):
        self.cancel()
        self.snapshot = snapshot
        self.entries = {}
        # _want_statistics describes what the UI is showing, not what this
        # scan holds, so it stays armed across restarts. Clearing it here
        # meant Batch Verify / Change Save Dir / Open Dir silently switched
        # statistics off until the user pressed Refresh.
        self._handle = self._submit(
            snapshot.image_paths, include_labels=False,
            priority=JobPriority.CATALOG, key='annotation-catalog')
        return self._handle

    def cancel(self):
        for handle in (self._handle, self._stats_handle):
            if handle is not None:
                handle.cancel()
        self._handle = None
        self._stats_handle = None

    def invalidate(self, image_path, snapshot=None):
        if snapshot is not None:
            self.snapshot = snapshot
        self.entries.pop(image_path, None)
        if self.snapshot is None or image_path not in \
                self.snapshot.path_to_index:
            return None
        return self._submit(
            (image_path,), include_labels=self._want_statistics,
            priority=JobPriority.CATALOG,
            key='annotation-catalog:' + image_path)

    def request_statistics(self):
        self._want_statistics = True
        if self.snapshot is None:
            return
        if self._handle is not None:
            # Initial scan completion will continue with the missing labels.
            return
        self._complete_statistics()

    def _complete_statistics(self):
        unresolved = [
            path for path in self.snapshot.image_paths
            if path not in self.entries
            or not self.entries[path].labels_complete
        ]
        if unresolved:
            self._stats_handle = self._submit(
                unresolved, include_labels=True,
                priority=JobPriority.STATISTICS,
                key='annotation-statistics')
            return
        total = len(self.snapshot.image_paths)
        annotated = 0
        verified = 0
        label_counts = {}
        for entry in self.entries.values():
            if entry.status != NO_LABELS:
                annotated += 1
            if entry.status == VERIFIED:
                verified += 1
            for label in entry.labels:
                label_counts[label] = label_counts.get(label, 0) + 1
        self.statistics_ready.emit(
            total, annotated, verified, label_counts)

    def _submit(self, paths, include_labels, priority, key):
        snapshot = self.snapshot
        generation = snapshot.generation
        paths = tuple(paths)
        json_cache = self._json_cache
        extensions = self.extensions
        batch_size = self.batch_size

        def run(handle):
            trace_started = (
                time.perf_counter_ns() if trace_recorder is not None else None)
            batch = {}
            all_entries = {}
            last_progress = time.monotonic()
            for index, image_path in enumerate(paths, 1):
                handle.check_cancelled()
                entry = _catalog_entry(
                    snapshot, image_path, include_labels, json_cache,
                    extensions)
                batch[image_path] = entry
                all_entries[image_path] = entry
                now = time.monotonic()
                if (len(batch) >= batch_size
                        or now - last_progress >= 0.20):
                    handle.report_progress(
                        (generation, 'batch', dict(batch)))
                    batch.clear()
                    handle.report_progress(
                        (generation, 'progress', (index, len(paths))))
                    last_progress = now
            if batch:
                handle.report_progress(
                    (generation, 'batch', dict(batch)))
            handle.report_progress(
                (generation, 'progress', (len(paths), len(paths))))
            if trace_recorder is not None:
                trace_recorder.complete(
                    'annotation.catalog', trace_started,
                    args={'images': len(paths), 'labels': include_labels})
            return generation, include_labels, all_entries

        handle = self.coordinator.submit(
            'background', run, priority=priority, key=key, latest=True,
            generation=generation)
        handle.progress.connect(self._on_progress)
        # Carry the handle into the slot: a single-image invalidate() result
        # must not clear the full scan's handle, which would defeat the
        # request_statistics guard and start a duplicate dataset-wide pass.
        handle.result.connect(
            lambda payload, owner=handle: self._on_result(payload, owner))
        handle.error.connect(self._on_error)
        return handle

    def _is_current(self, generation):
        return (self.snapshot is not None
                and generation == self.snapshot.generation)

    def _on_progress(self, payload):
        generation, kind, value = payload
        if not self._is_current(generation):
            return
        if kind == 'batch':
            self.entries.update(value)
            self.batch_ready.emit({
                path: entry.status for path, entry in value.items()
            })
        else:
            self.progress.emit(*value)

    def _on_result(self, payload, owner=None):
        generation, include_labels, entries = payload
        if not self._is_current(generation):
            return
        # Completion and progress use different Qt signal senders; applying
        # the final immutable result here makes event ordering irrelevant.
        changed = {
            path: entry for path, entry in entries.items()
            if self.entries.get(path) != entry
        }
        self.entries.update(entries)
        if changed:
            self.batch_ready.emit({
                path: entry.status for path, entry in changed.items()
            })
        if include_labels:
            if owner is None or owner is self._stats_handle:
                self._stats_handle = None
        elif owner is None or owner is self._handle:
            self._handle = None
            self.finished.emit()
        if self._want_statistics:
            self._complete_statistics()

    def _on_error(self, message):
        self._handle = None
        self._stats_handle = None
        self.error.emit(message)
