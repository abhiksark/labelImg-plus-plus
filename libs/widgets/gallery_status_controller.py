# libs/widgets/gallery_status_controller.py
"""Async annotation-status refresh for a gallery widget.

Owns the status-refresh worker lifecycle, the generation counter that drops
results from a superseded worker, and the split between applying already-cached
statuses immediately and computing the rest in the background. Extracted from
``MainWindow``, where the full-screen-gallery and dock-gallery flows were two
verbatim copies of this logic.

The gallery widget is read lazily through a getter (galleries are created and
destroyed on demand) and the status cache is shared by reference, so the
full-gallery and dock controllers — and the synchronous cache helpers that
remain on ``MainWindow`` — all see the same computed statuses. The worker class
and thread pool are injected, keeping this controller free of any dependency on
the ``MainWindow`` module and unit testable without real threads.
"""
from PyQt5.QtCore import QObject, QThreadPool


class GalleryStatusController(QObject):
    """Drives async annotation-status computation for one gallery widget."""

    def __init__(self, widget_getter, cache, worker_factory,
                 thread_pool=None, label='Status', parent=None):
        super().__init__(parent)
        self._get_widget = widget_getter
        self._cache = cache  # Shared {path: AnnotationStatus} dict (by reference).
        self._worker_factory = worker_factory
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._worker = None
        self._worker_gen = 0  # Bumped per refresh; guards against stale signals.
        self._label = label

    def refresh(self, image_list, save_dir):
        """Apply cached statuses immediately, then compute the rest async."""
        widget = self._get_widget()
        if widget is None:
            return

        cached = {p: self._cache[p] for p in image_list if p in self._cache}
        if cached:
            widget.update_all_statuses(cached)

        uncached = [p for p in image_list if p not in self._cache]
        if not uncached:
            return

        self.cleanup()
        self._worker_gen += 1
        gen = self._worker_gen

        worker = self._worker_factory(uncached, save_dir)
        worker.signals.batch_ready.connect(
            lambda s, g=gen: self._on_batch_ready(s, g))
        worker.signals.finished.connect(lambda g=gen: self._on_finished(g))
        worker.signals.error.connect(lambda e, g=gen: self._on_error(e, g))

        self._worker = worker
        self._thread_pool.start(worker)

    def cleanup(self):
        """Cancel the in-flight worker and disconnect its signals."""
        if self._worker:
            self._worker.cancel()
            try:
                self._worker.signals.batch_ready.disconnect()
                self._worker.signals.finished.disconnect()
                self._worker.signals.error.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected.
            self._worker = None

    def _on_batch_ready(self, statuses, gen):
        if gen != self._worker_gen:
            return  # Stale signal from a superseded worker.
        widget = self._get_widget()
        if widget is None:
            return
        self._cache.update(statuses)
        widget.update_all_statuses(statuses)

    def _on_finished(self, gen):
        if gen != self._worker_gen:
            return
        self._worker = None

    def _on_error(self, error_msg, gen):
        if gen != self._worker_gen:
            return
        print(f"{self._label} worker error: {error_msg}")
        self._worker = None
