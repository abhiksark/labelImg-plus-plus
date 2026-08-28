import threading
import time

import pytest
from PyQt5.QtCore import QCoreApplication
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication

from libs.core.shutdown_coordinator import ShutdownCoordinator
from libs.core.task_coordinator import JobPriority, TaskCoordinator


_APP = QApplication.instance() or QApplication([])


class FakeActivity(object):
    def __init__(self, jobs):
        self.jobs = tuple(jobs)
        self.cancelled = 0

    def cancel_all(self):
        self.cancelled += 1

    def active_jobs(self):
        return self.jobs

    def is_idle(self):
        return not self.jobs


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return False


def test_shutdown_waits_five_seconds_then_reports_remaining():
    source = FakeActivity(('video decode', 'Saving newest revision'))
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)
    timed_out = QSignalSpy(shutdown.timedOut)

    shutdown.begin()
    shutdown._deadline_expired()

    assert source.cancelled == 1
    assert timed_out[0][0] == (
        'video decode', 'Saving newest revision')
    assert shutdown.state == 'timed_out'


def test_shutdown_finishes_only_when_workers_and_save_are_drained():
    source = FakeActivity(('Saving newest revision',))
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)
    ready = QSignalSpy(shutdown.ready)

    shutdown.begin()
    shutdown.poll()
    assert len(ready) == 0

    source.jobs = ()
    shutdown.poll()

    assert len(ready) == 1
    assert shutdown.state == 'ready'


def test_wait_again_restarts_one_bounded_interval_and_force_stops_it():
    source = FakeActivity(('video decode',))
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)

    shutdown.begin()
    shutdown._deadline_expired()
    shutdown.wait_again()

    assert shutdown.state == 'waiting'
    assert source.cancelled == 1
    assert shutdown._deadline.isActive()

    shutdown.force_requested()

    assert shutdown.state == 'force_requested'
    assert not shutdown._poll_timer.isActive()
    assert not shutdown._deadline.isActive()


def test_cancel_stops_a_timed_out_coordinator_without_restarting_it():
    source = FakeActivity(('Saving newest revision',))
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)

    shutdown.begin()
    shutdown._deadline_expired()
    shutdown.cancel()
    shutdown.wait_again()

    assert shutdown.state == 'cancelled'
    assert not shutdown._poll_timer.isActive()
    assert not shutdown._deadline.isActive()


def test_task_coordinator_reports_stable_pending_and_running_job_names():
    coordinator = TaskCoordinator(logical_cpus=1)
    gates = {
        'interactive': threading.Event(),
        'background': threading.Event(),
        'sam': threading.Event(),
        'video': threading.Event(),
    }
    started = dict((lane, threading.Event()) for lane in gates)

    def blocking(lane):
        def run(_handle):
            started[lane].set()
            gates[lane].wait(2)
        return run

    try:
        for lane in ('interactive', 'background', 'sam', 'video'):
            coordinator.submit(
                lane, blocking(lane), priority=JobPriority.IMAGE_LOAD,
                key='%s running' % lane)
            assert started[lane].wait(1)
        coordinator.submit(
            'video', lambda _handle: None, key='video pending')

        assert coordinator.active_jobs() == (
            'background running', 'interactive running', 'sam running',
            'video pending', 'video running')
        assert coordinator.is_idle() is False

        coordinator.cancel_all()
        for gate in gates.values():
            gate.set()
        assert _wait_until(coordinator.is_idle)
        assert coordinator.active_jobs() == ()
    finally:
        for gate in gates.values():
            gate.set()
        coordinator.shutdown()


def test_task_cancellation_can_preserve_the_sole_active_save_owner():
    coordinator = TaskCoordinator(logical_cpus=1)
    save_gate = threading.Event()
    decode_gate = threading.Event()
    save_started = threading.Event()
    decode_started = threading.Event()

    def save(_handle):
        save_started.set()
        save_gate.wait(2)

    def decode(_handle):
        decode_started.set()
        decode_gate.wait(2)

    try:
        save_handle = coordinator.submit(
            'background', save, key='continuous-save:project.sqlite')
        decode_handle = coordinator.submit(
            'video', decode, key='video decode')
        assert save_started.wait(1)
        assert decode_started.wait(1)

        coordinator.cancel_all(exclude_handles=(save_handle,))

        assert save_handle.is_cancelled() is False
        assert decode_handle.is_cancelled() is True
        assert coordinator.active_jobs() == (
            'continuous-save:project.sqlite', 'video decode')
    finally:
        save_gate.set()
        decode_gate.set()
        coordinator.shutdown()


def test_shutdown_save_permit_is_exact_and_consumed_by_one_submit():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    intent = object()

    try:
        authority = coordinator.begin_shutdown()
        permit = coordinator.authorize_shutdown_save(
            authority, 'save:image.png', coordinator.generation,
            owner, intent)

        assert coordinator.is_shutting_down is True
        with pytest.raises(RuntimeError):
            coordinator.submit(
                'interactive', lambda _handle: None, key='image load')
        rejected = (
            ('background', 'save:other.png', coordinator.generation,
             permit, owner),
            ('background', 'continuous-save:project.sqlite',
             coordinator.generation, permit, owner),
            ('interactive', 'save:image.png', coordinator.generation,
             permit, owner),
            ('background', 'save:image.png', coordinator.generation + 1,
             permit, owner),
            ('background', 'save:image.png', coordinator.generation,
             permit, object(), intent),
            ('background', 'save:image.png', coordinator.generation,
             object(), owner, intent),
            ('background', 'save:image.png', coordinator.generation,
             None, owner, intent),
            ('background', 'save:image.png', coordinator.generation,
             permit, owner, object()),
        )
        for candidate in rejected:
            if len(candidate) == 5:
                lane, key, generation, candidate_permit, candidate_owner = candidate
                candidate_intent = intent
            else:
                (lane, key, generation, candidate_permit,
                 candidate_owner, candidate_intent) = candidate
            with pytest.raises(RuntimeError):
                coordinator.submit(
                    lane, lambda _handle: None, key=key,
                    generation=generation,
                    shutdown_permit=candidate_permit,
                    shutdown_owner=candidate_owner,
                    shutdown_intent=candidate_intent)
        chained = coordinator.submit(
            'background', lambda _handle: None,
            key='save:image.png', latest=True,
            generation=coordinator.generation,
            shutdown_permit=permit, shutdown_owner=owner,
            shutdown_intent=intent)
        assert chained.is_cancelled() is False
        with pytest.raises(RuntimeError):
            coordinator.submit(
                'background', lambda _handle: None,
                key='save:image.png', latest=True,
                generation=coordinator.generation,
                shutdown_permit=permit, shutdown_owner=owner,
                shutdown_intent=intent)
    finally:
        coordinator.shutdown()


def test_abort_shutdown_revokes_the_save_permit_and_reopens_normal_work():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    intent = object()
    authority = coordinator.begin_shutdown()
    permit = coordinator.authorize_shutdown_save(
        authority, 'save:image.png', coordinator.generation, owner, intent)

    coordinator.abort_shutdown()

    assert coordinator.is_shutting_down is False
    normal = coordinator.submit(
        'interactive', lambda _handle: None, key='image load')
    with pytest.raises(RuntimeError):
        coordinator.submit(
            'background', lambda _handle: None, key='save:image.png',
            generation=coordinator.generation,
            shutdown_permit=permit, shutdown_owner=owner,
            shutdown_intent=intent)
    assert normal.is_cancelled() is False

    next_authority = coordinator.begin_shutdown()
    with pytest.raises(RuntimeError):
        coordinator.authorize_shutdown_save(
            authority, 'save:image.png', coordinator.generation,
            owner, object())
    with pytest.raises(RuntimeError):
        coordinator.submit(
            'background', lambda _handle: None, key='save:image.png',
            generation=coordinator.generation,
            shutdown_permit=permit, shutdown_owner=owner,
            shutdown_intent=intent)
    next_intent = object()
    next_permit = coordinator.authorize_shutdown_save(
        next_authority, 'save:image.png', coordinator.generation,
        owner, next_intent)
    coordinator.submit(
        'background', lambda _handle: None, key='save:image.png',
        generation=coordinator.generation,
        shutdown_permit=next_permit, shutdown_owner=owner,
        shutdown_intent=next_intent)
    coordinator.shutdown()


def test_reentrant_begin_shutdown_cannot_replace_the_active_authority():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    intent = object()
    authority = coordinator.begin_shutdown()

    with pytest.raises(RuntimeError):
        coordinator.begin_shutdown()
    with pytest.raises(RuntimeError):
        coordinator.authorize_shutdown_save(
            object(), 'save:other.png', coordinator.generation,
            object(), object())

    permit = coordinator.authorize_shutdown_save(
        authority, 'save:image.png', coordinator.generation, owner, intent)
    accepted = coordinator.submit(
        'background', lambda _handle: None, key='save:image.png',
        generation=coordinator.generation,
        shutdown_permit=permit, shutdown_owner=owner,
        shutdown_intent=intent)
    assert accepted.is_cancelled() is False
    coordinator.shutdown()


def test_each_save_intent_requires_a_fresh_shutdown_permit():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    first_intent = object()
    second_intent = object()
    authority = coordinator.begin_shutdown()

    first = coordinator.authorize_shutdown_save(
        authority, 'save:image.png', coordinator.generation,
        owner, first_intent)
    coordinator.submit(
        'background', lambda _handle: None, key='save:image.png',
        generation=coordinator.generation,
        shutdown_permit=first, shutdown_owner=owner,
        shutdown_intent=first_intent)
    with pytest.raises(RuntimeError):
        coordinator.authorize_shutdown_save(
            authority, 'save:image.png', coordinator.generation,
            owner, first_intent)

    second = coordinator.authorize_shutdown_save(
        authority, 'save:image.png', coordinator.generation,
        owner, second_intent)
    assert second is not first
    coordinator.submit(
        'background', lambda _handle: None, key='save:image.png',
        generation=coordinator.generation,
        shutdown_permit=second, shutdown_owner=owner,
        shutdown_intent=second_intent)
    coordinator.shutdown()


def test_concurrent_authorization_for_one_save_intent_issues_once():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    intent = object()
    authority = coordinator.begin_shutdown()
    barrier = threading.Barrier(3)
    permits = []
    rejected = []

    def issue():
        barrier.wait()
        try:
            permits.append(coordinator.authorize_shutdown_save(
                authority, 'save:image.png', coordinator.generation,
                owner, intent))
        except RuntimeError:
            rejected.append(True)

    threads = [threading.Thread(target=issue) for _index in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)

    assert len(permits) == 1
    assert rejected == [True]
    coordinator.shutdown()


def test_concurrent_submission_consumes_one_shutdown_permit_once():
    coordinator = TaskCoordinator(logical_cpus=1)
    owner = object()
    intent = object()
    authority = coordinator.begin_shutdown()
    permit = coordinator.authorize_shutdown_save(
        authority, 'save:image.png', coordinator.generation, owner, intent)
    barrier = threading.Barrier(3)
    accepted = []
    rejected = []

    def submit():
        barrier.wait()
        try:
            accepted.append(coordinator.submit(
                'background', lambda _handle: None, key='save:image.png',
                generation=coordinator.generation,
                shutdown_permit=permit, shutdown_owner=owner,
                shutdown_intent=intent))
        except RuntimeError:
            rejected.append(True)

    threads = [threading.Thread(target=submit) for _index in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(1)

    assert len(accepted) == 1
    assert rejected == [True]
    coordinator.shutdown()
