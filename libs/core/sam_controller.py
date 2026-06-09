# libs/core/sam_controller.py
"""Orchestrates SAM-assisted polygon creation.

Bridges canvas clicks to worker-thread inference and routes results back to the
canvas on the main thread. Top-level imports are Qt + stdlib only; numpy and the
libs.integrations heavy modules are imported lazily inside methods so MainWindow
can import this controller unconditionally.

The first segmentation also loads the model (download + torch) inside the worker,
so the UI never blocks: a click on an unloaded backend shows "Loading SAM…" and
the model is built off the main thread.
"""

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QMessageBox


class _SamSignals(QObject):
    # (generation, points or None, backend created this run or None)
    finished = pyqtSignal(int, object, object)
    failed = pyqtSignal(int, str)         # (generation, message)


class _SamTask(QRunnable):
    """Loads the model if needed, embeds if needed, and predicts — all off the
    main thread. Returns plain data; the controller mutates Qt state on the main
    thread in the connected slots."""

    def __init__(self, generation, backend, settings, rgb, point, signals):
        super().__init__()
        self.setAutoDelete(True)
        self._generation = generation
        self._backend = backend           # existing backend, or None to load
        self._settings = settings
        self._rgb = rgb                   # numpy array if embedding needed, else None
        self._point = point
        self._signals = signals

    def run(self):
        try:
            from libs.integrations.mask_to_polygon import mask_to_polygon
            backend = self._backend
            created = None
            if backend is None:
                from libs.integrations.segmentation import load_backend
                backend, error = load_backend(self._settings)
                if backend is None:
                    self._signals.failed.emit(self._generation, error)
                    return
                created = backend
            if self._rgb is not None:
                backend.set_image(self._rgb)
            mask = backend.predict(
                [(self._point.x(), self._point.y())], [1])
            self._signals.finished.emit(
                self._generation, mask_to_polygon(mask), created)
        except Exception as exc:
            self._signals.failed.emit(self._generation, str(exc))


class SamController:
    def __init__(self, main_window):
        self.mw = main_window
        self.backend = None
        self._busy = False
        self._gen = 0
        self._embedded_key = None        # file_path the current embedding belongs to
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

    def cancel(self):
        # A running QThreadPool task cannot be stopped, so we only invalidate its
        # result (bump the generation). _busy stays set until that task finishes
        # and its handler clears it; this preserves the single-in-flight invariant
        # that serialises access to the non-thread-safe predictor.
        self._gen += 1

    def segment_at(self, point):
        if self._busy:
            self.mw.status("SAM working…")
            return
        from libs.integrations.image_convert import qimage_to_rgb
        # A not-yet-loaded backend has no embedding, so the first click must embed.
        need_embed = self.backend is None or self._embedded_key != self.mw.file_path
        rgb = qimage_to_rgb(self.mw.image) if need_embed else None
        self._busy = True
        self._gen += 1
        if need_embed:
            self._embedded_key = self.mw.file_path
        self.mw.status("Loading SAM…" if self.backend is None else "Segmenting…")
        QThreadPool.globalInstance().start(
            _SamTask(self._gen, self.backend, self.mw.settings, rgb, point,
                     self.signals))

    def _on_finished(self, generation, points, created):
        # Only one task is ever in flight (segment_at's _busy guard, and neither
        # cancel nor on_image_changed releases _busy), so the task completing here
        # is always the sole in-flight one: clearing _busy is unconditional/safe.
        self._busy = False
        if created is not None:
            # The model is image-independent, so keep it even if this result is
            # stale (e.g. the user switched images mid-load) to avoid reloading.
            self.backend = created
            if getattr(created, "device_warning", None):
                self.mw.status(created.device_warning)
        if generation != self._gen:
            return
        if not points:
            self.mw.status("No object found, try another point")
            return
        self.mw.canvas.commit_polygon(points)

    def _on_failed(self, generation, message):
        # A failed run may not have embedded the image, so always force a fresh
        # embed on the next click (cheap, and robust even if cancel() is later
        # wired to a UI action). Only the error dialog is gated on staleness.
        self._busy = False
        self._embedded_key = None
        if generation != self._gen:
            return
        QMessageBox.warning(self.mw, "SAM", message)
