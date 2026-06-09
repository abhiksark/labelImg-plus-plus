# libs/core/sam_controller.py
"""Orchestrates SAM-assisted polygon creation.

Bridges canvas clicks to worker-thread inference and routes results back to the
canvas on the main thread. Top-level imports are Qt + stdlib only; numpy and the
libs.integrations heavy modules are imported lazily inside methods so MainWindow
can import this controller unconditionally.
"""

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt5.QtWidgets import QMessageBox


class _SamSignals(QObject):
    finished = pyqtSignal(int, object)    # (generation, points or None)
    failed = pyqtSignal(int, str)         # (generation, message)


class _SamTask(QRunnable):
    def __init__(self, generation, backend, rgb, point, signals):
        super().__init__()
        self.setAutoDelete(True)
        self._generation = generation
        self._backend = backend
        self._rgb = rgb               # numpy array if embedding needed, else None
        self._point = point
        self._signals = signals

    def run(self):
        try:
            from libs.integrations.mask_to_polygon import mask_to_polygon
            if self._rgb is not None:
                self._backend.set_image(self._rgb)
            mask = self._backend.predict(
                [(self._point.x(), self._point.y())], [1])
            self._signals.finished.emit(self._generation, mask_to_polygon(mask))
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

    def ensure_model(self):
        if self.backend is not None:
            return True
        from libs.integrations.segmentation import load_backend
        backend, error = load_backend(self.mw.settings)
        if backend is None:
            QMessageBox.warning(self.mw, "SAM", error)
            return False
        self.backend = backend
        if getattr(backend, "device_warning", None):
            self.mw.status(backend.device_warning)
        return True

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
        if not self.ensure_model():
            return
        from libs.integrations.image_convert import qimage_to_rgb
        need_embed = self._embedded_key != self.mw.file_path
        rgb = qimage_to_rgb(self.mw.image) if need_embed else None
        self._busy = True
        self._gen += 1
        if need_embed:
            self._embedded_key = self.mw.file_path
        self.mw.status("Segmenting…")
        QThreadPool.globalInstance().start(
            _SamTask(self._gen, self.backend, rgb, point, self.signals))

    def _on_finished(self, generation, points):
        # Only one task is ever in flight (segment_at's _busy guard, and neither
        # cancel nor on_image_changed releases _busy), so the task completing here
        # is always the sole in-flight one: clearing _busy is unconditional/safe.
        self._busy = False
        if generation != self._gen:
            return
        if not points:
            self.mw.status("No object found, try another point")
            return
        self.mw.canvas.commit_polygon(points)

    def _on_failed(self, generation, message):
        self._busy = False
        self._embedded_key = None        # embedding may not have been set
        if generation != self._gen:
            return
        QMessageBox.warning(self.mw, "SAM", message)
