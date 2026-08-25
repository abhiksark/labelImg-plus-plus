# libs/core/sam_controller.py
"""Orchestrates SAM-assisted polygon or rectangle creation.

Bridges canvas clicks to worker-thread inference and routes results back to the
canvas on the main thread. Top-level imports are Qt + stdlib only; numpy and the
libs.integrations heavy modules are imported lazily inside methods so MainWindow
can import this controller unconditionally.

After explicit Assist setup, the first segmentation loads the cached model and
builds its session inside the worker, so the UI never blocks: a click on an
unloaded backend shows "Loading SAM…" and the model is built off the main
thread. Model acquisition is owned by the Assist download action.
"""

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from libs.core.assist_state import AssistFailureKind, AssistPrompt
from libs.core.profiling import recorder as trace_recorder


class _SamSignals(QObject):
    # (generation, SamResult or None, backend created this run or None)
    finished = pyqtSignal(int, object, object)
    failed = pyqtSignal(int, object, str)  # (generation, kind, message)


class _SamTaskFailure(RuntimeError):
    """Typed worker failure safe to project across the Qt boundary."""

    def __init__(self, kind, message):
        super().__init__(str(message))
        self.kind = kind


class _SamTask(QRunnable):
    """Loads the model if needed, embeds if needed, and predicts — all off the
    main thread. Returns plain data; the controller mutates Qt state on the main
    thread in the connected slots."""

    def __init__(self, generation, backend, settings, qimage, prompt, signals):
        super().__init__()
        self.setAutoDelete(True)
        self._generation = generation
        self._backend = backend           # existing backend, or None to load
        self._settings = settings
        self._qimage = qimage             # converted inside this worker
        self._prompt = prompt
        self._signals = signals

    def run(self):
        try:
            generation, result, created = self.execute()
            if self._signals is not None:
                self._signals.finished.emit(generation, result, created)
        except _SamTaskFailure as exc:
            if self._signals is not None:
                self._signals.failed.emit(
                    self._generation, exc.kind, str(exc))
        except Exception as exc:
            if self._signals is not None:
                self._signals.failed.emit(
                    self._generation, AssistFailureKind.INFERENCE, str(exc))

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
                from libs.integrations.model_cache import ModelSetupRequiredError
                kind = ('setup_required'
                        if isinstance(error, ModelSetupRequiredError)
                        else AssistFailureKind.RUNTIME)
                raise _SamTaskFailure(kind, error)
            created = backend
        if self._qimage is not None:
            from libs.integrations.image_convert import qimage_to_rgb
            if trace_recorder is not None:
                import time
                started = time.perf_counter_ns()
            backend.set_image(qimage_to_rgb(self._qimage))
            if trace_recorder is not None:
                trace_recorder.complete('sam.image.embed', started)
        if self._prompt is None:
            return self._generation, None, created
        if trace_recorder is not None:
            import time
            started = time.perf_counter_ns()
        try:
            mask = backend.predict(self._prompt)
        except _SamTaskFailure:
            raise
        except Exception as exc:
            raise _SamTaskFailure(AssistFailureKind.INFERENCE, exc)
        result = mask_to_sam_result(mask)
        if trace_recorder is not None:
            trace_recorder.complete('sam.inference', started)
        return self._generation, result, created


class SamController(QObject):
    previewReady = pyqtSignal(int, object)  # document generation, SamResult
    previewFailed = pyqtSignal(int, object, str)

    def __init__(self, main_window):
        super().__init__()
        self.mw = main_window
        self.backend = None
        self._busy = False
        self._gen = 0
        self._content_key = None         # identity of the published image/frame
        self._embedded_key = None        # content identity the embedding belongs to
        self._enabled = False
        self._pending_prompt = None
        self._pending_prepare = False
        self._active_prompt = None
        self._active_document_generation = int(
            getattr(main_window, '_dataset_generation', 0))
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
        self._on_content_changed(self.mw.file_path)

    def on_video_frame_changed(self, session_generation, frame_ref):
        """Invalidate Assist for one successfully published video frame."""
        frame_key = getattr(frame_ref, 'cache_key', None)
        if frame_key is None:  # Compatibility for lightweight frame adapters.
            frame_key = ('pts', int(frame_ref.pts))
        self._on_content_changed((
            'video', int(session_generation), frame_key))

    def _on_content_changed(self, content_key):
        # Invalidate the cached embedding AND discard any in-flight result, so a
        # segmentation started on the previous image can never commit onto the
        # new one (the stale generation is dropped in _on_finished).
        self._content_key = content_key
        self._embedded_key = None
        self._gen += 1
        self._pending_prompt = None
        changed = getattr(self.mw, '_on_assist_document_changed', None)
        if changed is not None:
            changed()
        if self._enabled:
            if self._busy:
                self._pending_prepare = True
            else:
                self._start(None)

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if not self._enabled:
            self._pending_prompt = None
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
        coordinator = getattr(self.mw, 'task_coordinator', None)
        if coordinator is not None and self._active_handle is not None:
            coordinator.cancel_handle(self._active_handle)

    def segment_at(self, point):
        """Compatibility entry point for one positive Smart Point."""
        self.run_prompt(AssistPrompt(
            mode='points',
            positive_points=((float(point.x()), float(point.y())),)))

    def run_prompt(self, prompt):
        """Run the latest immutable prompt; newer input invalidates old output."""
        if not isinstance(prompt, AssistPrompt):
            raise TypeError('prompt must be an AssistPrompt')
        if self._busy:
            self._pending_prompt = prompt
            self._gen += 1
            coordinator = getattr(self.mw, 'task_coordinator', None)
            if coordinator is not None and self._active_handle is not None:
                coordinator.cancel_handle(self._active_handle)
            self.mw.status("SAM working…")
            return
        self._start(prompt)

    def _start(self, prompt):
        # A not-yet-loaded backend has no embedding, so the first click must embed.
        content_key = (
            self._content_key
            if self._content_key is not None else self.mw.file_path)
        need_embed = self.backend is None or self._embedded_key != content_key
        qimage = self.mw.image.copy() if need_embed else None
        self._busy = True
        self._gen += 1
        self._active_prompt = prompt
        self._active_document_generation = int(
            getattr(self.mw, '_dataset_generation', 0))
        if need_embed:
            self._embedded_key = content_key
        if prompt is None:
            message = "Preparing SAM…"
        else:
            message = "Loading SAM…" if self.backend is None else "Segmenting…"
        self.mw.status(message)
        coordinator = getattr(self.mw, 'task_coordinator', None)
        if coordinator is not None:
            task = _SamTask(
                self._gen, self.backend, self.mw.settings, qimage, prompt,
                None)
            from libs.core.task_coordinator import JobPriority
            handle = coordinator.submit(
                'sam', lambda job: self._execute_task(task),
                priority=JobPriority.IMAGE_LOAD, key='sam-active',
                generation=coordinator.generation)
            self._active_handle = handle
            handle.result.connect(self._on_task_result)
            handle.error.connect(lambda message, generation=self._gen:
                                 self._on_failed(
                                     generation,
                                     AssistFailureKind.INFERENCE, message))
            handle.finished.connect(
                lambda active=handle: self._on_task_finished(active))
        else:  # Compatibility for extensions constructing the controller alone.
            task = _SamTask(
                self._gen, self.backend, self.mw.settings, qimage, prompt,
                self.signals)
            self._standalone_pool.start(task)

    @staticmethod
    def _execute_task(task):
        """Return typed failures as data because JobHandle errors are text-only."""
        try:
            return 'finished', task.execute()
        except _SamTaskFailure as exc:
            return 'failed', task._generation, exc.kind, str(exc)
        except Exception as exc:
            return ('failed', task._generation,
                    AssistFailureKind.INFERENCE, str(exc))

    def _on_task_result(self, value):
        if not value:
            return
        if value[0] == 'failed':
            self._on_failed(*value[1:])
        else:
            self._on_finished(*value[1])

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
            if self._active_prompt is not None:
                self.mw.status("No object found, try another point")
            self._start_pending()
            return
        self.previewReady.emit(self._document_generation(generation), result)
        self._start_pending()

    def _on_failed(self, generation, kind, message=None):
        # A failed run may not have embedded the image, so always force a fresh
        # embed on the next click (cheap, and robust even if cancel() is later
        # wired to a UI action). Only failure publication is gated on staleness.
        self._busy = False
        self._embedded_key = None
        if message is None:  # compatibility with old two-argument callbacks
            message = str(kind)
            kind = AssistFailureKind.INFERENCE
        if generation != self._gen:
            self._start_pending()
            return
        self.previewFailed.emit(
            self._document_generation(generation), kind, str(message))
        self._start_pending()

    def _document_generation(self, fallback):
        return int(getattr(self, '_active_document_generation', fallback))

    def _start_pending(self):
        if self._busy:
            return
        if self._pending_prepare:
            self._pending_prepare = False
            self._start(None)
            return
        if self._pending_prompt is not None:
            prompt = self._pending_prompt
            self._pending_prompt = None
            self._start(prompt)
