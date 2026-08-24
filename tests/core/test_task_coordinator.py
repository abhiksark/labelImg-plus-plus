import threading
import time

from PyQt5.QtCore import QCoreApplication
from PyQt5.QtWidgets import QApplication

from libs.core.task_coordinator import JobPriority, TaskCoordinator


_APP = QApplication.instance() or QApplication([])


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return False


def test_latest_request_cancels_pending_job():
    coordinator = TaskCoordinator(logical_cpus=1)
    gate = threading.Event()
    started = threading.Event()
    ran = []

    def blocker(handle):
        started.set()
        gate.wait(1)

    coordinator.submit(
        'interactive', blocker, priority=JobPriority.IMAGE_LOAD)
    assert started.wait(1)
    old = coordinator.submit(
        'interactive', lambda handle: ran.append('old'),
        key='load', latest=True)
    coordinator.submit(
        'interactive', lambda handle: ran.append('new'),
        key='load', latest=True)
    assert old.is_cancelled()
    gate.set()
    assert _wait_until(lambda: ran == ['new'])
    coordinator.shutdown()


def test_pending_jobs_run_in_priority_order():
    coordinator = TaskCoordinator(logical_cpus=1)
    gate = threading.Event()
    started = threading.Event()
    order = []

    def blocker(handle):
        started.set()
        gate.wait(1)

    coordinator.submit('background', blocker, priority=0)
    assert started.wait(1)
    coordinator.submit(
        'background', lambda handle: order.append('bulk'),
        priority=JobPriority.BULK)
    coordinator.submit(
        'background', lambda handle: order.append('visible'),
        priority=JobPriority.VISIBLE_THUMBNAIL)
    gate.set()
    assert _wait_until(lambda: len(order) == 2)
    assert order == ['visible', 'bulk']
    coordinator.shutdown()


def test_generation_cancellation_discards_result():
    coordinator = TaskCoordinator(logical_cpus=1)
    gate = threading.Event()
    delivered = []

    def work(handle):
        gate.wait(1)
        return 'stale'

    handle = coordinator.submit('interactive', work, generation=3)
    handle.result.connect(delivered.append)
    coordinator.cancel_generation(3)
    gate.set()
    assert _wait_until(lambda: not coordinator.queue_depths()['interactive'])
    assert delivered == []
    coordinator.shutdown()


def test_video_lane_is_single_threaded_and_independent():
    coordinator = TaskCoordinator(logical_cpus=8)
    assert coordinator.pool('video').maxThreadCount() == 1
    assert coordinator.pool('video') is not coordinator.pool('interactive')
    assert coordinator.pool('video') is not coordinator.pool('background')
    assert 'video' in coordinator.queue_depths()
    coordinator.shutdown()


def test_cancel_after_worker_result_disposes_suppressed_result():
    coordinator = TaskCoordinator(logical_cpus=1)
    produced = threading.Event()
    release = threading.Event()
    delivered = []
    finished = []

    class Resource:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    resource = Resource()

    def work(_handle):
        produced.set()
        assert release.wait(1)
        return resource

    try:
        handle = coordinator.submit(
            'video', work, key='prepared-video', latest=True,
            on_discard=lambda result: result.close())
        handle.result.connect(delivered.append)
        handle.finished.connect(lambda: finished.append(True))
        assert produced.wait(1)
        release.set()
        assert coordinator.pool('video').waitForDone(1000)

        handle.cancel()
        assert _wait_until(lambda: finished)

        assert delivered == []
        assert resource.closed
    finally:
        release.set()
        coordinator.shutdown()
