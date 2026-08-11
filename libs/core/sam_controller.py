# libs/core/sam_controller.py
"""Orchestrates SAM-assisted polygon or rectangle creation.

Bridges canvas clicks to worker-thread inference and routes results back to the
canvas on the main thread. Top-level imports are Qt + stdlib only; numpy and the
libs.integrations heavy modules are imported lazily inside methods so MainWindow
can import this controller unconditionally.

The first segmentation also loads the model (download + session build) inside
the worker,
so the UI never blocks: a click on an unloaded backend shows "Loading SAM…" and
the model is built off the main thread.
"""

from PyQt5.QtCore import QObject, QPointF, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from libs.core.profiling import recorder as trace_recorder


class _SamSignals(QObject):
    # (generation, SamResult or None, backend created this run or None)
    finished = pyqtSignal(int, object, object)
    failed = pyqtSignal(int, str)         # (generation, message)


class _SamTask(QRunnable):
    """Loads the model if needed, embeds if needed, and predicts — all off the
    main thread. Returns plain data; the controller mutates Qt state on the main
    thread in the connected slots."""

    def __init__(self, generation, backend, settings, qimage, point, signals):
        super().__init__()
        self.setAutoDelete(True)
        self._generation = generation
        self._backend = backend           # existing backend, or None to load
        self._settings = settings
        self._qimage = qimage             # converted inside this worker
        self._point = point
        self._signals = signals

    def run(self):
        try:
            generation, result, created = self.execute()
            if self._signals is not None:
                self._signals.finished.emit(generation, result, created)
        except Exception as exc:
            if self._signals is not None:
                self._signals.failed.emit(self._generation, str(exc))

    def execute(self):
        from libs.integrations.mask_to_polygon import mask_to_sam_result
        backend = self._backend
        created = None
        if backend is None:
            from libs.integrations.segmentation import load_backend
            if trace_recorder is not None:
                import time
                started = time.perf_counter_ns()
            backend, error = load_backend(self._settings)
            if trace_recorder is not None:
                trace_recorder.complete('sam.backend.load', started)
            if backend is None:
                raise RuntimeError(error)
            created = backend
        if self._qimage is not None:
            from libs.integrations.image_convert import qimage_to_rgb
            if trace_recorder is not None:
                import time
                started = time.perf_counter_ns()
            backend.set_image(qimage_to_rgb(self._qimage))
            if trace_recorder is not None:
                trace_recorder.complete('sam.image.embed', started)
        if self._point is None:
            return self._generation, None, created
        if trace_recorder is not None:
            import time
            started = time.perf_counter_ns()
        mask = backend.predict(
            [(self._point.x(), self._point.y())], [1])
        result = mask_to_sam_result(mask)
        if trace_recorder is not None:
            trace_recorder.complete('sam.inference', started)
        return self._generation, result, created


class SamController:
    def __init__(self, main_window):
        self.mw = main_window
        self.backend = None
        self._busy = False
        self._gen = 0
        self._embedded_key = None        # file_path the current embedding belongs to
        self._enabled = False
        self._pending_click = None
        self._pending_prepare = False
        self._active_point = None
        self._active_handle = None
        self._standalone_pool = QThreadPool()
        self._standalone_pool.setMaxThreadCount(1)
        self.signals = _SamSignals()
        self.signals.finished.connect(self._on_finished)
        self.signals.failed.connect(self._on_failed)

    def reset_backend(self):
        """Drop the loaded model and cached embedding so the next click reloads.

        Both must be cleared together: a fresh backend has no embedding, so
        leaving a stale _embedded_key would skip set_image and crash predict.
        """
        self.backend = None
        self._embedded_key = None

    def on_image_changed(self):
        # Invalidate the cached embedding AND discard any in-flight result, so a
        # segmentation started on the previous image can never commit onto the
        # new one (the stale generation is dropped in _on_finished).
        self._embedded_key = None
        self._gen += 1
        if self._enabled:
            if self._busy:
                self._pending_prepare = True
            else:
                self._start(None)

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if not self._enabled:
            self._pending_click = None
            self._pending_prepare = False
            self.cancel()
            return
        if getattr(self.mw, 'file_path', None):
            if self._busy:
                self._pending_prepare = True
            else:
                self._start(None)

    def cancel(self):
        # A running QThreadPool task cannot be stopped, so we only invalidate its
        # result (bump the generation). _busy stays set until that task finishes
        # and its handler clears it; this preserves the single-in-flight invariant
        # that serialises access to the non-thread-safe predictor.
        self._gen += 1

    def segment_at(self, point):
        if self._busy:
            self._pending_click = QPointF(point)
            self.mw.status("SAM working…")
            return
        self._start(point)

    def _start(self, point):
        # A not-yet-loaded backend has no embedding, so the first click must embed.
        need_embed = self.backend is None or self._embedded_key != self.mw.file_path
        qimage = self.mw.image.copy() if need_embed else None
        self._busy = True
        self._gen += 1
        self._active_point = point
        if need_embed:
            self._embedded_key = self.mw.file_path
        if point is None:
            message = "Preparing SAM…"
        else:
            message = "Loading SAM…" if self.backend is None else "Segmenting…"
        self.mw.status(message)
        coordinator = getattr(self.mw, 'task_coordinator', None)
        if coordinator is not None:
            task = _SamTask(
                self._gen, self.backend, self.mw.settings, qimage, point,
                None)
            from libs.core.task_coordinator import JobPriority
            handle = coordinator.submit(
                'sam', lambda job: task.execute(),
                priority=JobPriority.IMAGE_LOAD, key='sam-active',
                generation=coordinator.generation)
            self._active_handle = handle
            handle.result.connect(
                lambda value: self._on_finished(*value))
            handle.error.connect(
                lambda message, generation=self._gen:
                self._on_failed(generation, message))
            handle.finished.connect(
                lambda active=handle: self._on_task_finished(active))
        else:  # Compatibility for extensions constructing the controller alone.
            task = _SamTask(
                self._gen, self.backend, self.mw.settings, qimage, point,
                self.signals)
            self._standalone_pool.start(task)

    def _on_task_finished(self, handle):
        if self._active_handle is not handle:
            return
        self._active_handle = None
        if handle.is_cancelled() and self._busy:
            self._busy = False
            self._embedded_key = None
            self._start_pending()

    def _on_finished(self, generation, result, created):
        # Only one task is ever in flight (segment_at's _busy guard, and neither
        # cancel nor on_image_changed releases _busy), so the task completing here
        # is always the sole in-flight one: clearing _busy is unconditional/safe.
        self._busy = False
        if created is not None:
            # The model is image-independent, so keep it even if this result is
            # stale (e.g. the user switched images mid-load) to avoid reloading.
            self.backend = created
        if generation != self._gen:
            self._start_pending()
            return
        if result is None:
            if self._active_point is not None:
                self.mw.status("No object found, try another point")
            self._start_pending()
            return
        output_mode = getattr(self.mw, 'sam_output_mode', 'polygon')
        if output_mode == 'box':
            self.mw.canvas.commit_rectangle(result.bounds)
        else:
            self.mw.canvas.commit_polygon(result.polygon)
        self._start_pending()

    def _on_failed(self, generation, message):
        # A failed run may not have embedded the image, so always force a fresh
        # embed on the next click (cheap, and robust even if cancel() is later
        # wired to a UI action). Only the error dialog is gated on staleness.
        self._busy = False
        self._embedded_key = None
        if generation != self._gen:
            self._start_pending()
            return
        QMessageBox.warning(self.mw, "SAM", message)
        self._start_pending()

    def _start_pending(self):
        if self._busy:
            return
        if self._pending_prepare:
            self._pending_prepare = False
            self._start(None)
            return
        if self._pending_click is not None:
            point = self._pending_click
            self._pending_click = None
            self._start(point)
