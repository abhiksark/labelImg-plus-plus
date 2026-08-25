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
    on_discard: object = field(compare=False, default=None)


class _Lane:
    def __init__(self, name, threads):
        self.name = name
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(1, int(threads)))
        self.pending = []
        self.running = {}


class _ShutdownSubmissionPermit(object):
    """Opaque capability for one exact save stream during shutdown."""

    __slots__ = ()


class _ShutdownSaveAuthority(object):
    """Opaque authority held by the active application shutdown owner."""

    __slots__ = ()


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
            # The active PyAV container is session-owned and never touched by
            # two workers concurrently. Tracking/export open independent
            # containers on the background lane.
            'video': _Lane('video', 1),
        }
        self._sequence = itertools.count()
        self._generation = 0
        self._latest_by_key = {}
        self._shutting_down = False
        self._shutdown_lock = threading.Lock()
        self._shutdown_authority = None
        self._shutdown_submission = None
        self._shutdown_used_intents = []
        self._completion = _CompletionSignals(self)
        self._completion.done.connect(self._on_done)

    @property
    def generation(self):
        return self._generation

    @property
    def is_shutting_down(self):
        return self._shutting_down

    def next_generation(self, exclude_handles=()):
        self._generation += 1
        self.cancel_all(exclude_handles=exclude_handles)
        return self._generation

    def pool(self, lane):
        return self._lanes[lane].pool

    def queue_depths(self):
        return {
            name: len(lane.pending) + len(lane.running)
            for name, lane in self._lanes.items()
        }

    def active_jobs(self, exclude_handles=()):
        """Return stable, human-readable identities for every active job."""
        excluded = set(id(handle) for handle in exclude_handles
                       if handle is not None)
        values = []
        for lane in self._lanes.values():
            records = list(lane.pending) + list(lane.running.values())
            for record in records:
                if id(record.handle) in excluded:
                    continue
                values.append(str(
                    record.handle.key or '%s job' % lane.name))
        return tuple(sorted(set(values)))

    def has_active_handle(self, handle):
        if handle is None:
            return False
        return any(
            any(record.handle is handle for record in lane.pending)
            or any(record.handle is handle
                   for record in lane.running.values())
            for lane in self._lanes.values())

    def is_idle(self):
        return all(
            not lane.pending and not lane.running
            for lane in self._lanes.values())

    def submit(self, lane, function, priority=JobPriority.BULK, key=None,
               latest=False, generation=None, on_discard=None,
               shutdown_permit=None, shutdown_owner=None,
               shutdown_intent=None):
        if lane not in self._lanes:
            raise ValueError('unknown worker lane: %s' % lane)
        if generation is None:
            generation = self._generation
        supplied_shutdown_capability = bool(
            shutdown_permit is not None or shutdown_owner is not None
            or shutdown_intent is not None)
        with self._shutdown_lock:
            if self._shutting_down:
                authorization = self._shutdown_submission
                allowed_during_shutdown = bool(
                    authorization is not None
                    and shutdown_permit is authorization[0]
                    and shutdown_owner is authorization[1]
                    and lane == 'background'
                    and key == authorization[2]
                    and generation == authorization[3]
                    and shutdown_intent is authorization[4])
                if not allowed_during_shutdown:
                    raise RuntimeError('task coordinator is shutting down')
                self._shutdown_submission = None
                self._shutdown_used_intents.append(shutdown_intent)
            elif supplied_shutdown_capability:
                raise RuntimeError(
                    'shutdown submission permit is not active')
        sequence = next(self._sequence)
        handle = JobHandle(sequence, generation, key, self)
        if latest and key is not None:
            previous = self._latest_by_key.get(key)
            if previous is not None:
                previous.cancel()
            self._latest_by_key[key] = handle
        record = _JobRecord(
            int(priority), sequence, lane, function, handle, on_discard)
        target = self._lanes[lane]
        heapq.heappush(target.pending, record)
        self._dispatch(target)
        return handle

    def cancel_key(self, key):
        handle = self._latest_by_key.pop(key, None)
        if handle is not None:
            handle.cancel()

    def cancel_handle(self, handle):
        """Cancel one handle and report whether it was pending or running.

        A pending record is removed synchronously, so its owner can reconcile
        a never-started operation without waiting for a worker completion that
        cannot arrive. Running work remains cooperatively cancelled and keeps
        its normal completion/cleanup boundary.
        """
        if handle is None:
            return 'inactive'
        for lane in self._lanes.values():
            for index, record in enumerate(lane.pending):
                if record.handle is not handle:
                    continue
                handle.cancel()
                del lane.pending[index]
                heapq.heapify(lane.pending)
                if (handle.key is not None
                        and self._latest_by_key.get(handle.key) is handle):
                    self._latest_by_key.pop(handle.key, None)
                self._dispatch(lane)
                return 'pending'
            if any(record.handle is handle
                   for record in lane.running.values()):
                handle.cancel()
                return 'running'
        handle.cancel()
        return 'inactive'

    def cancel_generation(self, generation):
        for lane in self._lanes.values():
            for record in lane.pending:
                if record.handle.generation == generation:
                    record.handle.cancel()
            for record in lane.running.values():
                if record.handle.generation == generation:
                    record.handle.cancel()
            self._drop_cancelled(lane)

    def cancel_all(self, exclude_handles=()):
        excluded = set(id(handle) for handle in exclude_handles
                       if handle is not None)
        for lane in self._lanes.values():
            for record in lane.pending:
                if id(record.handle) not in excluded:
                    record.handle.cancel()
            for record in lane.running.values():
                if id(record.handle) not in excluded:
                    record.handle.cancel()
            self._drop_cancelled(lane)
        self._latest_by_key = {
            key: handle for key, handle in self._latest_by_key.items()
            if id(handle) in excluded
        }

    def begin_shutdown(self, exclude_handles=()):
        """Stop new work and return authority for exact save admission."""
        with self._shutdown_lock:
            if self._shutting_down:
                raise RuntimeError('task coordinator shutdown already began')
            self._shutting_down = True
            authority = _ShutdownSaveAuthority()
            self._shutdown_authority = authority
            self._shutdown_submission = None
            self._shutdown_used_intents = []
        self.cancel_all(exclude_handles=exclude_handles)
        return authority

    def authorize_shutdown_save(self, authority, key, generation, owner,
                                intent):
        """Issue one exact, one-shot permit for the active save owner."""
        if key is None or owner is None or intent is None:
            raise ValueError('shutdown save identity is incomplete')
        with self._shutdown_lock:
            if (not self._shutting_down
                    or authority is not self._shutdown_authority):
                raise RuntimeError('shutdown save authority is not active')
            if self._shutdown_submission is not None:
                raise RuntimeError('a shutdown save permit is already active')
            if any(value is intent for value in self._shutdown_used_intents):
                raise RuntimeError('shutdown save intent was already used')
            permit = _ShutdownSubmissionPermit()
            self._shutdown_submission = (
                permit, owner, str(key), int(generation), intent)
            return permit

    def revoke_shutdown_save_authority(self, authority):
        """Seal save admission while leaving the general shutdown gate on."""
        with self._shutdown_lock:
            if authority is not self._shutdown_authority:
                raise RuntimeError('shutdown save authority is not active')
            self._shutdown_authority = None
            self._shutdown_submission = None
            self._shutdown_used_intents = []

    def abort_shutdown(self):
        """Reopen submissions after the user cancels application shutdown."""
        with self._shutdown_lock:
            self._shutting_down = False
            self._shutdown_authority = None
            self._shutdown_submission = None
            self._shutdown_used_intents = []

    def shutdown(self, wait_ms=500):
        with self._shutdown_lock:
            self._shutting_down = True
            self._shutdown_authority = None
            self._shutdown_submission = None
            self._shutdown_used_intents = []
        self.cancel_all()
        all_done = True
        for lane in self._lanes.values():
            lane.pool.clear()
            all_done = lane.pool.waitForDone(wait_ms) and all_done
        return all_done

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
        if handle.is_cancelled():
            if result is not None and record.on_discard is not None:
                try:
                    record.on_discard(result)
                except Exception:
                    pass
        else:
            if error is None:
                handle.result.emit(result)
            else:
                handle.error.emit(error)
        handle.finished.emit()
        self._dispatch(lane)
