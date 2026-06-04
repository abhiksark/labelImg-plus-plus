# tests/widgets/test_stats_controller.py
"""Tests for StatsController — the background statistics orchestrator.

Exercises the worker lifecycle, the generation counter that invalidates
in-flight results, and result dispatch to the stats widget, all without real
threads: the worker, thread pool, and stats widget are injected as fakes.
"""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from libs.widgets.stats_controller import StatsController


class FakeStatsWidget:
    def __init__(self):
        self.dataset = None
        self.label_dist = None
        self.current = None

    def update_dataset_stats(self, total, annotated, verified):
        self.dataset = (total, annotated, verified)

    def update_label_distribution(self, counts):
        self.label_dist = counts

    def update_current_image_stats(self, count, labels):
        self.current = (count, labels)


class FakeSignals(QObject):
    progress = pyqtSignal(int, int, int, dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)


class FakeWorker:
    def __init__(self, image_list, save_dir):
        self.image_list = list(image_list)
        self.save_dir = save_dir
        self.signals = FakeSignals()
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeThreadPool:
    def __init__(self):
        self.started = []

    def start(self, worker):
        self.started.append(worker)


class StatsControllerTestBase(unittest.TestCase):
    def setUp(self):
        self.widget = FakeStatsWidget()
        self.pool = FakeThreadPool()
        self.controller = StatsController(
            stats_widget_getter=lambda: self.widget,
            worker_factory=FakeWorker,
            thread_pool=self.pool)


class TestRefreshAll(StatsControllerTestBase):

    def test_starts_worker_with_snapshot_and_bumps_generation(self):
        self.controller.refresh_all(['a.jpg', 'b.jpg'], '/save')
        self.assertEqual(len(self.pool.started), 1)
        worker = self.pool.started[0]
        self.assertEqual(worker.image_list, ['a.jpg', 'b.jpg'])
        self.assertEqual(worker.save_dir, '/save')
        self.assertEqual(self.controller._worker_gen, 1)

    def test_noop_when_no_widget(self):
        controller = StatsController(
            stats_widget_getter=lambda: None,
            worker_factory=FakeWorker,
            thread_pool=self.pool)
        controller.refresh_all(['a.jpg'], '/save')
        self.assertEqual(self.pool.started, [])
        self.assertEqual(controller._worker_gen, 0)

    def test_second_refresh_cancels_first_worker(self):
        self.controller.refresh_all(['a.jpg'], '/save')
        first = self.pool.started[0]
        self.controller.refresh_all(['b.jpg'], '/save')
        self.assertTrue(first.cancelled)
        self.assertEqual(self.controller._worker_gen, 2)


class TestSignalDispatch(StatsControllerTestBase):

    def test_progress_updates_widget(self):
        self.controller.refresh_all(['a.jpg'], '/save')
        worker = self.pool.started[0]
        worker.signals.progress.emit(10, 6, 2, {'cat': 4})
        self.assertEqual(self.widget.dataset, (10, 6, 2))
        self.assertEqual(self.widget.label_dist, {'cat': 4})

    def test_finished_requests_current_image_refresh_and_clears_worker(self):
        seen = []
        self.controller.current_image_refresh_requested.connect(
            lambda: seen.append(True))
        self.controller.refresh_all(['a.jpg'], '/save')
        worker = self.pool.started[0]
        worker.signals.finished.emit()
        self.assertEqual(seen, [True])
        self.assertIsNone(self.controller._worker)

    def test_error_clears_worker(self):
        self.controller.refresh_all(['a.jpg'], '/save')
        worker = self.pool.started[0]
        worker.signals.error.emit('boom')
        self.assertIsNone(self.controller._worker)


class TestStaleGenerationGuard(StatsControllerTestBase):

    def test_stale_progress_ignored(self):
        self.controller._worker_gen = 5
        self.controller._on_progress(10, 6, 2, {'cat': 4}, gen=4)
        self.assertIsNone(self.widget.dataset)

    def test_stale_finished_does_not_request_refresh(self):
        seen = []
        self.controller.current_image_refresh_requested.connect(
            lambda: seen.append(True))
        self.controller._worker_gen = 5
        self.controller._on_finished(gen=4)
        self.assertEqual(seen, [])

    def test_stale_error_ignored(self):
        self.controller._worker_gen = 5
        self.controller._worker = object()  # sentinel; must survive stale error
        self.controller._on_error('old', gen=4)
        self.assertIsNotNone(self.controller._worker)


class TestUpdateCurrentImage(StatsControllerTestBase):

    def test_forwards_count_and_labels_to_widget(self):
        self.controller.update_current_image(3, ['cat', 'dog'])
        self.assertEqual(self.widget.current, (3, ['cat', 'dog']))

    def test_noop_when_no_widget(self):
        controller = StatsController(
            stats_widget_getter=lambda: None,
            worker_factory=FakeWorker,
            thread_pool=self.pool)
        controller.update_current_image(3, ['cat'])  # must not raise


class TestCleanup(StatsControllerTestBase):

    def test_cancels_and_clears_worker(self):
        self.controller.refresh_all(['a.jpg'], '/save')
        worker = self.pool.started[0]
        self.controller.cleanup()
        self.assertTrue(worker.cancelled)
        self.assertIsNone(self.controller._worker)

    def test_cleanup_is_safe_with_no_worker(self):
        self.controller.cleanup()  # must not raise
        self.assertIsNone(self.controller._worker)


if __name__ == '__main__':
    unittest.main()
