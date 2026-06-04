# libs/widgets/stats_controller.py
"""Background statistics orchestration for the gallery stats panel.

Owns the statistics worker lifecycle, the generation counter that invalidates
in-flight results when a newer refresh starts, and the dispatch of results to
the stats widget. Extracted from ``MainWindow`` so the (error-prone)
stale-signal guarding is unit testable without a Qt main window.

The worker class and the live stats widget are injected so this controller has
no dependency on the ``MainWindow`` module. The widget is read lazily through a
getter because the gallery — and its stats panel — is created and destroyed on
demand.
"""
from PyQt5.QtCore import QObject, QThreadPool, pyqtSignal


class StatsController(QObject):
    """Drives async dataset-statistics computation for the stats widget."""

    # Emitted when a full dataset refresh finishes, so the owner can refresh
    # the current-image panel (which depends on live canvas state the
    # controller deliberately does not reach into).
    current_image_refresh_requested = pyqtSignal()

    def __init__(self, stats_widget_getter, worker_factory,
                 thread_pool=None, parent=None):
        super().__init__(parent)
        self._get_widget = stats_widget_getter
        self._worker_factory = worker_factory
        self._thread_pool = thread_pool or QThreadPool.globalInstance()
        self._worker = None
        self._worker_gen = 0  # Bumped per refresh; guards against stale signals.

    def refresh_all(self, image_list, save_dir):
        """Start an async refresh of dataset-wide statistics."""
        if self._get_widget() is None:
            return

        self.cleanup()
        self._worker_gen += 1
        gen = self._worker_gen

        worker = self._worker_factory(image_list, save_dir)
        worker.signals.progress.connect(
            lambda t, a, v, l, g=gen: self._on_progress(t, a, v, l, g))
        worker.signals.finished.connect(lambda g=gen: self._on_finished(g))
        worker.signals.error.connect(lambda e, g=gen: self._on_error(e, g))

        self._worker = worker
        self._thread_pool.start(worker)

    def cleanup(self):
        """Cancel the in-flight worker and disconnect its signals."""
        if self._worker:
            self._worker.cancel()
            try:
                self._worker.signals.progress.disconnect()
                self._worker.signals.finished.disconnect()
                self._worker.signals.error.disconnect()
            except (TypeError, RuntimeError):
                pass  # Already disconnected.
            self._worker = None

    def update_current_image(self, annotations_count, labels):
        """Push the current image's annotation count and labels to the widget."""
        widget = self._get_widget()
        if widget is None:
            return
        widget.update_current_image_stats(annotations_count, labels)

    def _on_progress(self, total, annotated, verified, label_counts, gen):
        if gen != self._worker_gen:
            return  # Stale signal from a superseded worker.
        widget = self._get_widget()
        if widget is not None:
            widget.update_dataset_stats(total, annotated, verified)
            widget.update_label_distribution(label_counts)

    def _on_finished(self, gen):
        if gen != self._worker_gen:
            return
        self._worker = None
        self.current_image_refresh_requested.emit()

    def _on_error(self, error_msg, gen):
        if gen != self._worker_gen:
            return
        print(f"Statistics worker error: {error_msg}")
        self._worker = None
