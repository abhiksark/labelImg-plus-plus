# tests/widgets/test_gallery_status_controller.py
"""Tests for GalleryStatusController — async annotation-status refresh.

Covers the cached-immediate / uncached-async split, the generation counter
that drops stale results, the shared status cache, and worker cleanup — all
without real threads (worker, thread pool, and gallery widget are fakes).
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

from libs.widgets.gallery_status_controller import GalleryStatusController


class FakeGallery:
    def __init__(self):
        self.all_status_calls = []

    def update_all_statuses(self, statuses):
        self.all_status_calls.append(dict(statuses))


class FakeSignals(QObject):
    batch_ready = pyqtSignal(dict)
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


def make_controller(widget, cache, pool):
    return GalleryStatusController(
        widget_getter=lambda: widget,
        cache=cache,
        worker_factory=FakeWorker,
        thread_pool=pool,
        label='Status refresh')


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.widget = FakeGallery()
        self.cache = {}
        self.pool = FakeThreadPool()
        self.controller = make_controller(self.widget, self.cache, self.pool)

    def test_applies_cached_immediately_and_starts_worker_for_uncached(self):
        self.cache['a.jpg'] = 'HAS_LABELS'
        self.controller.refresh(['a.jpg', 'b.jpg'], '/save')

        # Cached status pushed to the widget right away.
        self.assertEqual(self.widget.all_status_calls, [{'a.jpg': 'HAS_LABELS'}])
        # Only the uncached image goes to the worker.
        self.assertEqual(len(self.pool.started), 1)
        self.assertEqual(self.pool.started[0].image_list, ['b.jpg'])
        self.assertEqual(self.pool.started[0].save_dir, '/save')
        self.assertEqual(self.controller._worker_gen, 1)

    def test_all_cached_applies_but_starts_no_worker(self):
        self.cache.update({'a.jpg': 'VERIFIED', 'b.jpg': 'NO_LABELS'})
        self.controller.refresh(['a.jpg', 'b.jpg'], '/save')

        self.assertEqual(len(self.widget.all_status_calls), 1)
        self.assertEqual(self.pool.started, [])
        self.assertEqual(self.controller._worker_gen, 0)

    def test_noop_without_widget(self):
        controller = make_controller(None, self.cache, self.pool)
        controller.refresh(['a.jpg'], '/save')
        self.assertEqual(self.pool.started, [])
        self.assertEqual(controller._worker_gen, 0)

    def test_second_refresh_cancels_first_worker(self):
        self.controller.refresh(['a.jpg'], '/save')
        first = self.pool.started[0]
        self.controller.refresh(['b.jpg'], '/save')
        self.assertTrue(first.cancelled)
        self.assertEqual(self.controller._worker_gen, 2)


class TestSignalDispatch(unittest.TestCase):
    def setUp(self):
        self.widget = FakeGallery()
        self.cache = {}
        self.pool = FakeThreadPool()
        self.controller = make_controller(self.widget, self.cache, self.pool)

    def test_batch_ready_updates_cache_and_widget(self):
        self.controller.refresh(['a.jpg'], '/save')
        worker = self.pool.started[0]
        worker.signals.batch_ready.emit({'a.jpg': 'HAS_LABELS'})

        self.assertEqual(self.cache['a.jpg'], 'HAS_LABELS')
        self.assertIn({'a.jpg': 'HAS_LABELS'}, self.widget.all_status_calls)

    def test_stale_batch_ignored(self):
        self.controller._worker_gen = 5
        self.controller._on_batch_ready({'a.jpg': 'HAS_LABELS'}, gen=4)
        self.assertNotIn('a.jpg', self.cache)
        self.assertEqual(self.widget.all_status_calls, [])

    def test_batch_ignored_when_widget_gone(self):
        controller = make_controller(None, self.cache, self.pool)
        controller._worker_gen = 1
        controller._on_batch_ready({'a.jpg': 'X'}, gen=1)
        # Cache must not be updated if there is no widget to show it.
        self.assertNotIn('a.jpg', self.cache)

    def test_finished_clears_worker(self):
        self.controller.refresh(['a.jpg'], '/save')
        self.pool.started[0].signals.finished.emit()
        self.assertIsNone(self.controller._worker)

    def test_error_clears_worker(self):
        self.controller.refresh(['a.jpg'], '/save')
        self.pool.started[0].signals.error.emit('boom')
        self.assertIsNone(self.controller._worker)

    def test_stale_finished_ignored(self):
        self.controller._worker_gen = 5
        self.controller._worker = object()  # sentinel must survive
        self.controller._on_finished(gen=4)
        self.assertIsNotNone(self.controller._worker)


class TestCleanup(unittest.TestCase):
    def test_cancels_and_clears(self):
        widget, cache, pool = FakeGallery(), {}, FakeThreadPool()
        controller = make_controller(widget, cache, pool)
        controller.refresh(['a.jpg'], '/save')
        worker = pool.started[0]
        controller.cleanup()
        self.assertTrue(worker.cancelled)
        self.assertIsNone(controller._worker)

    def test_cleanup_safe_with_no_worker(self):
        controller = make_controller(FakeGallery(), {}, FakeThreadPool())
        controller.cleanup()
        self.assertIsNone(controller._worker)


class TestSharedCache(unittest.TestCase):
    def test_two_controllers_share_cache(self):
        """The full-gallery and dock controllers share one cache dict, so a
        status computed by one is seen by the other."""
        cache = {}
        pool = FakeThreadPool()
        full = make_controller(FakeGallery(), cache, pool)
        dock = make_controller(FakeGallery(), cache, pool)

        full.refresh(['a.jpg'], '/save')
        full._on_batch_ready({'a.jpg': 'VERIFIED'}, gen=full._worker_gen)

        # dock sees the cached status and applies it without a worker.
        pool.started.clear()
        dock.refresh(['a.jpg'], '/save')
        self.assertEqual(pool.started, [])  # nothing uncached for dock


if __name__ == '__main__':
    unittest.main()
