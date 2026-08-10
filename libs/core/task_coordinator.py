"""Bounded Qt worker lanes with cancellable, generation-scoped jobs.

Qt's global thread pool is process-wide.  Changing its size in the gallery
used to affect SAM, statistics, and any extension using the same pool.  The
coordinator owns independent pools and keeps pending work in Python heaps so
superseded jobs can be removed before Qt starts them.
"""

from dataclasses import dataclass, field
import heapq
import itertools
import os
import threading

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal


class JobPriority:
    IMAGE_LOAD = 0
    VISIBLE_THUMBNAIL = 10
    CATALOG = 20
    STATISTICS = 30
    BULK = 40


class JobCancelled(Exception):
    """Raised cooperatively by a worker that notices cancellation."""


class JobHandle(QObject):
    """Signals and cooperative cancellation state for one submitted job."""

    progress = pyqtSignal(object)
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, job_id, generation, key=None, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.generation = generation
        self.key = key
        self._cancel_event = threading.Event()
        self._non_cancellable = False

    def cancel(self):
        if not self._non_cancellable:
            self._cancel_event.set()

    def is_cancelled(self):
        return self._cancel_event.is_set()

    def check_cancelled(self):
        if self.is_cancelled():
            raise JobCancelled()

    def report_progress(self, value):
        if not self.is_cancelled():
            self.progress.emit(value)

    def begin_non_cancellable(self):
        """Fence a short atomic commit phase after all preparation succeeds."""
        self.check_cancelled()
        self._non_cancellable = True


class _CompletionSignals(QObject):
    done = pyqtSignal(object, object, object)


class _Worker(QRunnable):
    def __init__(self, record, completion):
        super().__init__()
        self.setAutoDelete(True)
        self._record = record
        self._completion = completion

    def run(self):
        result = None
        error = None
        try:
            self._record.handle.check_cancelled()
            result = self._record.function(self._record.handle)
            self._record.handle.check_cancelled()
        except JobCancelled:
            pass
        except Exception as exc:  # Errors cross the thread boundary as text.
            error = str(exc)
        self._completion.done.emit(self._record, result, error)


@dataclass(order=True)
class _JobRecord:
    priority: int
    sequence: int
    lane: object = field(compare=False)
    function: object = field(compare=False)
    handle: JobHandle = field(compare=False)


class _Lane:
    def __init__(self, name, threads):
        self.name = name
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(1, int(threads)))
        self.pending = []
        self.running = {}


class TaskCoordinator(QObject):
    """Own application worker capacity and apply latest-request-wins policy."""

    def __init__(self, logical_cpus=None, parent=None):
        super().__init__(parent)
        cpus = max(1, int(logical_cpus or os.cpu_count() or 1))
        interactive = 2 if cpus >= 4 else 1
        background = min(4, max(1, cpus - interactive))
        self._lanes = {
            'interactive': _Lane('interactive', interactive),
            'background': _Lane('background', background),
            'sam': _Lane('sam', 1),
        }
        self._sequence = itertools.count()
        self._generation = 0
        self._latest_by_key = {}
        self._shutting_down = False
        self._completion = _CompletionSignals(self)
        self._completion.done.connect(self._on_done)

    @property
    def generation(self):
        return self._generation

    @property
    def is_shutting_down(self):
        return self._shutting_down

    def next_generation(self):
        self._generation += 1
        self.cancel_all()
        return self._generation

    def pool(self, lane):
        return self._lanes[lane].pool

    def queue_depths(self):
        return {
            name: len(lane.pending) + len(lane.running)
            for name, lane in self._lanes.items()
        }

    def submit(self, lane, function, priority=JobPriority.BULK, key=None,
               latest=False, generation=None):
        if self._shutting_down:
            raise RuntimeError('task coordinator is shutting down')
        if lane not in self._lanes:
            raise ValueError('unknown worker lane: %s' % lane)
        if generation is None:
            generation = self._generation
        sequence = next(self._sequence)
        handle = JobHandle(sequence, generation, key, self)
        if latest and key is not None:
            previous = self._latest_by_key.get(key)
            if previous is not None:
                previous.cancel()
            self._latest_by_key[key] = handle
        record = _JobRecord(
            int(priority), sequence, lane, function, handle)
        target = self._lanes[lane]
        heapq.heappush(target.pending, record)
        self._dispatch(target)
        return handle

    def cancel_key(self, key):
        handle = self._latest_by_key.pop(key, None)
        if handle is not None:
            handle.cancel()

    def cancel_generation(self, generation):
        for lane in self._lanes.values():
            for record in lane.pending:
                if record.handle.generation == generation:
                    record.handle.cancel()
            for record in lane.running.values():
                if record.handle.generation == generation:
                    record.handle.cancel()
            self._drop_cancelled(lane)

    def cancel_all(self):
        for lane in self._lanes.values():
            for record in lane.pending:
                record.handle.cancel()
            for record in lane.running.values():
                record.handle.cancel()
            self._drop_cancelled(lane)
        self._latest_by_key.clear()

    def shutdown(self, wait_ms=500):
        self._shutting_down = True
        self.cancel_all()
        for lane in self._lanes.values():
            lane.pool.clear()
            lane.pool.waitForDone(wait_ms)

    def _drop_cancelled(self, lane):
        if not lane.pending:
            return
        lane.pending = [
            record for record in lane.pending
            if not record.handle.is_cancelled()
        ]
        heapq.heapify(lane.pending)

    def _dispatch(self, lane):
        self._drop_cancelled(lane)
        capacity = lane.pool.maxThreadCount() - len(lane.running)
        while capacity > 0 and lane.pending:
            record = heapq.heappop(lane.pending)
            if record.handle.is_cancelled():
                continue
            lane.running[record.sequence] = record
            lane.pool.start(_Worker(record, self._completion))
            capacity -= 1

    def _on_done(self, record, result, error):
        lane = self._lanes[record.lane]
        lane.running.pop(record.sequence, None)
        handle = record.handle
        if (handle.key is not None
                and self._latest_by_key.get(handle.key) is handle):
            self._latest_by_key.pop(handle.key, None)
        if not handle.is_cancelled():
            if error is None:
                handle.result.emit(result)
            else:
                handle.error.emit(error)
        handle.finished.emit()
        self._dispatch(lane)
