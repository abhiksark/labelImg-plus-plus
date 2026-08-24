from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from libs.core.continuous_save import ContinuousSaveCoordinator


_APP = QApplication.instance() or QApplication([])


def test_mutations_coalesce_and_late_completion_cannot_clean_newer_revision():
    coordinator = ContinuousSaveCoordinator(delay_ms=20)
    coordinator.reset('image:/a.png', generation=4, durable_revision=0)
    requested = QSignalSpy(coordinator.saveRequested)

    coordinator.mark_dirty(1)
    coordinator.mark_dirty(2)
    assert requested.wait(1000)
    first = requested[0][0]
    assert first.revision == 2

    coordinator.mark_dirty(3)
    coordinator.complete(first)
    if len(requested) < 2:
        assert requested.wait(1000)
    assert requested[1][0].revision == 3
    assert coordinator.state == 'saving'


def test_failed_save_stays_dirty_until_explicit_retry():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    coordinator.mark_dirty(1)
    assert requested.wait(1000)
    coordinator.fail(requested[0][0], 'disk full')
    assert coordinator.state == 'failed'
    coordinator.retry()
    if len(requested) < 2:
        assert requested.wait(1000)


def test_newer_mutation_after_failure_waits_for_retry_and_saves_newest():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    coordinator.mark_dirty(1)
    assert requested.wait(1000)
    coordinator.fail(requested[0][0], 'disk full')

    coordinator.mark_dirty(2)
    QSignalSpy(coordinator.saveRequested).wait(20)
    assert coordinator.state == 'failed'
    assert len(requested) == 1

    coordinator.retry()
    if len(requested) < 2:
        assert requested.wait(1000)
    assert requested[1][0].revision == 2


def test_reset_rejects_late_completion_from_replaced_document_generation():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    coordinator.mark_dirty(1)
    assert requested.wait(1000)
    replaced = requested[0][0]

    coordinator.reset('image:/b.png', 2, 7)
    coordinator.complete(replaced)
    coordinator.fail(replaced, 'late failure')
    assert coordinator.state == 'saved'
    assert coordinator.error is None

    coordinator.mark_dirty(8)
    if len(requested) < 2:
        assert requested.wait(1000)
    current = requested[1][0]
    assert current.document_key == 'image:/b.png'
    assert current.generation == 2
    assert current.revision == 8


def test_disabled_coordinator_keeps_dirty_work_pending_until_reenabled():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)

    coordinator.set_enabled(False)
    coordinator.mark_dirty(1)
    coordinator.flush()
    QSignalSpy(coordinator.saveRequested).wait(20)

    assert coordinator.state == 'pending'
    assert len(requested) == 0

    coordinator.set_enabled(True)
    if not requested:
        assert requested.wait(1000)
    assert requested[0][0].revision == 1
    assert coordinator.state == 'saving'


def test_disable_during_save_requeues_newer_revision_without_dispatching():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    coordinator.mark_dirty(1)
    assert requested.wait(1000)
    first = requested[0][0]

    coordinator.set_enabled(False)
    coordinator.mark_dirty(2)
    coordinator.complete(first)
    QSignalSpy(coordinator.saveRequested).wait(20)

    assert coordinator.state == 'pending'
    assert len(requested) == 1

    coordinator.set_enabled(True)
    if len(requested) < 2:
        assert requested.wait(1000)
    assert requested[1][0].revision == 2


def test_explicit_drain_serializes_newest_revision_while_automatic_is_off():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    drained = QSignalSpy(coordinator.drained)
    coordinator.set_enabled(False)
    coordinator.mark_dirty(1)

    coordinator.drain()

    assert len(requested) == 1
    first = requested[0][0]
    assert first.revision == 1
    coordinator.mark_dirty(2)
    coordinator.complete(first)
    assert len(requested) == 2
    newest = requested[1][0]
    assert newest.revision == 2
    coordinator.complete(newest)
    assert len(drained) == 1
    assert coordinator.state == 'saved'
