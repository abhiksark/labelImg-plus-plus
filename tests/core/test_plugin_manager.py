from concurrent.futures import CancelledError
import gc
import sys
import threading
import time
import weakref

from PyQt5.QtCore import QCoreApplication, QEvent, QObject, QThread
from PyQt5.QtWidgets import QApplication

from labelimgplusplus.plugins import (
    CommandSpec,
    DocumentDescriptor,
    PluginCapability,
    PluginMetadata,
)
from libs.core.plugin_discovery import PluginCandidate
from libs.core.plugin_manager import PluginManager, PluginState
from libs.core.plugin_registry import validate_json_value
from libs.core.settings import Settings
from libs.core.task_coordinator import JobHandle, TaskCoordinator


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return False


class _EntryPoint:
    def __init__(self, plugin_id, factory=None, error=None):
        self.name = plugin_id
        self.value = "fixture:create_plugin"
        self.group = "labelimgplusplus.plugins"
        self._factory = factory
        self._error = error

    def load(self):
        if self._error is not None:
            raise self._error
        return self._factory


def _metadata(plugin_id, api_major=1, capabilities=None):
    if capabilities is None:
        capabilities = (PluginCapability.COMMANDS,)
    return PluginMetadata(
        id=plugin_id,
        display_name="Fixture Plugin",
        version="1.0.0",
        api_major=api_major,
        capabilities=capabilities,
    )


def _candidate(plugin_id, factory=None, error=None):
    entry = _EntryPoint(plugin_id, factory, error)
    return PluginCandidate(
        id=plugin_id,
        reference=entry.value,
        distribution="fixture-distribution",
        distribution_version="1.0.0",
        entry_point=entry,
    )


class _Plugin:
    def __init__(self, plugin_id, activate=None, deactivate=None,
                 api_major=1, capabilities=None):
        self.metadata = _metadata(plugin_id, api_major, capabilities)
        self._activate = activate
        self._deactivate = deactivate
        self.context = None

    def activate(self, context):
        self.context = context
        if self._activate is not None:
            self._activate(context)

    def deactivate(self):
        if self._deactivate is not None:
            self._deactivate()


def _host(tmp_path, plugin_ids, candidates):
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {"enabled": list(plugin_ids), "config": {}}}
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(settings, coordinator, candidates=candidates)
    return settings, coordinator, manager


def _shutdown(manager, coordinator):
    manager.shutdown()
    coordinator.shutdown()
    QCoreApplication.processEvents()


def test_valid_plugin_activation_commits_command_and_settings(tmp_path):
    calls = []

    def activate(context):
        context.commands.register(CommandSpec(
            id="review", title="Review", callback=lambda: calls.append("ran")))
        context.settings.set("color", {"rgb": [1, 2, 3]})

    plugin = _Plugin("com.example.review", activate)
    settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.ACTIVE
        command_id = "plugin.com.example.review.review"
        assert command_id in manager.active_commands
        assert manager.invoke_command(command_id)
        assert calls == ["ran"]
        assert settings.get("plugins")["config"][plugin.metadata.id] == {
            "color": {"rgb": [1, 2, 3]}}
    finally:
        _shutdown(manager, coordinator)


def test_activation_rollback_discards_all_staged_state(tmp_path):
    events = []

    def activate(context):
        context.commands.register(CommandSpec(
            id="partial", title="Partial", callback=lambda: None))
        context.settings.set("partial", True)
        context.documents.subscribe(lambda document: events.append(document))
        try:
            context.tasks.submit(lambda handle: None)
        except RuntimeError:
            pass
        raise RuntimeError("activation exploded")

    plugin = _Plugin(
        "com.example.rollback", activate,
        deactivate=lambda: events.append("deactivated"))
    settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.FAILED
        assert manager.active_commands == {}
        assert settings.get("plugins")["config"] == {}
        manager.publish_document(DocumentDescriptor(generation=1))
        assert events == ["deactivated"]
        assert "activation_failed" in {item.code for item in record.diagnostics}
    finally:
        _shutdown(manager, coordinator)


def test_task_submission_during_activation_rejects_plugin(tmp_path):
    plugin = _Plugin(
        "com.example.eager",
        lambda context: context.tasks.submit(lambda handle: None))
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        assert manager.record_for(plugin.metadata.id).state == PluginState.FAILED
        assert coordinator.queue_depths()["background"] == 0
    finally:
        _shutdown(manager, coordinator)


def test_command_registration_requires_declared_capability(tmp_path):
    plugin = _Plugin(
        "com.example.undeclared",
        lambda context: context.commands.register(CommandSpec(
            id="run", title="Run", callback=lambda: None)),
        capabilities=(),
    )
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.FAILED
        assert record.diagnostics[-1].code == "capability_not_declared"
        assert manager.active_commands == {}
    finally:
        _shutdown(manager, coordinator)


def test_api_mismatch_is_incompatible(tmp_path):
    plugin = _Plugin("com.example.future", api_major=99)
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.INCOMPATIBLE
        assert record.diagnostics[-1].code == "api_major_mismatch"
    finally:
        _shutdown(manager, coordinator)


def test_invalid_metadata_field_types_are_rejected(tmp_path):
    capability_plugin = _Plugin("com.example.bad-capability")
    capability_plugin.metadata = PluginMetadata(
        id=capability_plugin.metadata.id,
        display_name="Bad Capability",
        version="1.0.0",
        api_major=1,
        capabilities=("commands",),
    )
    text_plugin = _Plugin("com.example.bad-text")
    text_plugin.metadata = PluginMetadata(
        id=text_plugin.metadata.id,
        display_name=42,
        version="1.0.0",
        api_major=1,
        capabilities=(PluginCapability.COMMANDS,),
    )
    plugins = (capability_plugin, text_plugin)
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id for plugin in plugins], [
            _candidate(plugin.metadata.id, lambda plugin=plugin: plugin)
            for plugin in plugins
        ])
    try:
        manager.activate_enabled()
        for plugin in plugins:
            record = manager.record_for(plugin.metadata.id)
            assert record.state == PluginState.FAILED
            assert record.diagnostics[-1].code == "invalid_metadata"
    finally:
        _shutdown(manager, coordinator)


def test_missing_dependency_and_malformed_factory_are_contained(tmp_path):
    missing_id = "com.example.missing"
    malformed_id = "com.example.malformed"
    _settings, coordinator, manager = _host(
        tmp_path, [missing_id, malformed_id], [
            _candidate(missing_id, error=ModuleNotFoundError("missing_lib")),
            _candidate(malformed_id, factory=object()),
        ])
    try:
        manager.activate_enabled()
        assert manager.record_for(missing_id).diagnostics[-1].code == "missing_dependency"
        assert manager.record_for(malformed_id).diagnostics[-1].code == "invalid_factory"
    finally:
        _shutdown(manager, coordinator)


def test_missing_dependency_from_factory_is_identified(tmp_path):
    plugin_id = "com.example.factory-dependency"

    def factory():
        raise ModuleNotFoundError("factory_dependency")

    _settings, coordinator, manager = _host(
        tmp_path, [plugin_id], [_candidate(plugin_id, factory=factory)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin_id)
        assert record.state == PluginState.FAILED
        assert record.diagnostics[-1].code == "missing_dependency"
    finally:
        _shutdown(manager, coordinator)


def test_json_settings_are_isolated_and_reject_reserved_tags(tmp_path):
    plugins = []
    candidates = []
    for plugin_id in ("a.plugin", "b.plugin"):
        plugin = _Plugin(
            plugin_id, lambda context, value=plugin_id: context.settings.set(
                "shared", value))
        plugins.append(plugin)
        candidates.append(_candidate(plugin_id, lambda plugin=plugin: plugin))
    settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id for plugin in plugins], candidates)
    try:
        manager.activate_enabled()
        configs = settings.get("plugins")["config"]
        assert configs["a.plugin"]["shared"] == "a.plugin"
        assert configs["b.plugin"]["shared"] == "b.plugin"
        for bad in (
            {"nested": {"__type__": "QColor"}},
            {"tuple": (1, 2)},
            {"nan": float("nan")},
        ):
            try:
                validate_json_value(bad)
            except ValueError:
                pass
            else:
                raise AssertionError("invalid plugin JSON was accepted")
    finally:
        _shutdown(manager, coordinator)


def test_document_generation_cancels_and_discards_stale_task(tmp_path):
    gate = threading.Event()
    delivered = []
    plugin = _Plugin("com.example.tasks")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()

        def work(handle):
            gate.wait(1)
            return "stale"

        handle = plugin.context.tasks.submit(work, on_result=delivered.append)
        manager.publish_document(DocumentDescriptor(generation=1))
        assert handle.is_cancelled()
        try:
            handle.check_cancelled()
        except CancelledError:
            pass
        else:
            raise AssertionError("plugin cancellation did not use CancelledError")
        gate.set()
        assert _wait_until(lambda: coordinator.queue_depths()["background"] == 0)
        assert delivered == []
    finally:
        gate.set()
        _shutdown(manager, coordinator)


def test_duplicate_document_subscriptions_unsubscribe_independently(tmp_path):
    delivered = []
    unsubscribers = []

    def activate(context):
        def callback(document):
            delivered.append(document.revision)

        unsubscribers.append(context.documents.subscribe(callback))
        unsubscribers.append(context.documents.subscribe(callback))

    plugin = _Plugin("com.example.subscriptions", activate)
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        manager.publish_document(DocumentDescriptor(generation=1, revision=1))
        assert delivered == [1, 1]
        unsubscribers[0]()
        manager.publish_document(DocumentDescriptor(generation=1, revision=2))
        assert delivered == [1, 1, 2]
        unsubscribers[1]()
        manager.publish_document(DocumentDescriptor(generation=1, revision=3))
        assert delivered == [1, 1, 2]
    finally:
        _shutdown(manager, coordinator)


def test_immediate_task_progress_is_delivered(tmp_path):
    progress = []
    results = []
    plugin = _Plugin("com.example.progress")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()

        def work(handle):
            handle.report_progress("connected")
            return "done"

        plugin.context.tasks.submit(
            work, on_progress=progress.append, on_result=results.append)
        assert _wait_until(lambda: results == ["done"])
        assert progress == ["connected"]
    finally:
        _shutdown(manager, coordinator)


def test_plugin_task_uses_same_plain_restricted_facade_in_worker(tmp_path):
    worker_handles = []
    results = []
    plugin = _Plugin("com.example.facade")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()

        def work(handle):
            worker_handles.append(handle)
            return "done"

        caller_handle = plugin.context.tasks.submit(
            work, on_result=results.append)
        assert _wait_until(lambda: results == ["done"])
        assert worker_handles == [caller_handle]
        assert not isinstance(caller_handle, (QObject, JobHandle))
        for name in (
            "parent",
            "thread",
            "job_id",
            "generation",
            "key",
            "result",
            "error",
            "progress",
            "finished",
            "begin_non_cancellable",
        ):
            assert not hasattr(caller_handle, name)
        assert {
            name for name in dir(type(caller_handle)) if not name.startswith("_")
        } == {
            "cancel", "check_cancelled", "is_cancelled", "report_progress"}
    finally:
        _shutdown(manager, coordinator)


def test_latest_plugin_task_cancels_and_releases_previous_facade(tmp_path):
    first_started = threading.Event()
    first_cancelled = threading.Event()
    results = []
    plugin = _Plugin("com.example.latest")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()

        def first_work(handle):
            first_started.set()
            try:
                while True:
                    handle.check_cancelled()
                    time.sleep(0.001)
            except CancelledError:
                first_cancelled.set()
                raise

        first = plugin.context.tasks.submit(
            first_work, key="scan", latest=True, on_result=results.append)
        assert first_started.wait(1)
        second = plugin.context.tasks.submit(
            lambda handle: "current",
            key="scan",
            latest=True,
            on_result=results.append,
        )
        assert first is not second
        assert _wait_until(lambda: results == ["current"])
        assert first.is_cancelled()
        assert first_cancelled.wait(1)
        assert plugin.context.tasks.handles == ()
    finally:
        _shutdown(manager, coordinator)


def test_task_failure_preserves_traceback_and_reports_on_gui_thread(tmp_path):
    errors = []
    results = []
    plugin = _Plugin("com.example.task-failure")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()

        def worker_frame(_handle):
            raise LookupError("worker exploded")

        plugin.context.tasks.submit(
            worker_frame,
            on_result=results.append,
            on_error=lambda message: errors.append(
                (message, QThread.currentThread())),
        )
        assert _wait_until(lambda: bool(errors))
        diagnostic = manager.record_for(plugin.metadata.id).diagnostics[-1]
        assert diagnostic.code == "task_failed"
        assert diagnostic.message == "worker exploded"
        assert "LookupError: worker exploded" in diagnostic.details
        assert "in worker_frame" in diagnostic.details
        assert errors == [("worker exploded", QApplication.instance().thread())]
        assert results == []
    finally:
        _shutdown(manager, coordinator)


def test_shutdown_cancels_live_work_and_releases_task_handles(tmp_path):
    progress_queued = threading.Event()
    unexpected = []
    previous_excepthook = sys.excepthook
    plugin = _Plugin("com.example.close-work")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    sys.excepthook = lambda *args: unexpected.append(args)
    try:
        manager.activate_enabled()

        def work(handle):
            handle.report_progress("queued-before-shutdown")
            progress_queued.set()
            while True:
                handle.check_cancelled()
                time.sleep(0.001)

        handle = plugin.context.tasks.submit(work, on_progress=lambda _value: None)
        assert progress_queued.wait(1)
        task_service = plugin.context.tasks
        manager.shutdown()
        assert handle.is_cancelled()
        assert task_service.handles == ()
        assert _wait_until(
            lambda: coordinator.queue_depths()["background"] == 0)
        QCoreApplication.processEvents()
        assert unexpected == []
    finally:
        manager.shutdown()
        coordinator.shutdown()
        QCoreApplication.processEvents()
        sys.excepthook = previous_excepthook


def test_retained_plugin_facade_detaches_after_host_shutdown(tmp_path):
    started = threading.Event()
    stopped = threading.Event()

    def work(handle):
        started.set()
        try:
            while True:
                handle.check_cancelled()
                time.sleep(0.001)
        except CancelledError:
            stopped.set()
            raise

    def run_host():
        plugin = _Plugin("com.example.retained-facade")
        _settings, coordinator, manager = _host(
            tmp_path, [plugin.metadata.id],
            [_candidate(plugin.metadata.id, lambda: plugin)])
        manager.activate_enabled()
        retained = plugin.context.tasks.submit(work)
        assert started.wait(1)
        coordinator_handle_ref = weakref.ref(retained._handle_ref())
        manager.shutdown()
        coordinator.shutdown()
        assert stopped.wait(1)
        assert _wait_until(
            lambda: coordinator.queue_depths()["background"] == 0)
        assert retained.is_cancelled()
        assert retained._handle_ref is None
        plugin.context = None
        manager.deleteLater()
        coordinator.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        return retained, coordinator_handle_ref

    retained, coordinator_handle_ref = run_host()
    gc.collect()
    assert retained.is_cancelled()
    assert coordinator_handle_ref() is None


def test_invalid_activation_diagnostic_rolls_back_transaction(tmp_path):
    def activate(context):
        context.settings.set("partial", True)
        context.diagnostics.report("bad", "invalid", severity=None)

    plugin = _Plugin("com.example.invalid-activation-diagnostic", activate)
    settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.FAILED
        assert settings.get("plugins")["config"] == {}
        assert record.diagnostics[-1].code == "activation_failed"
        assert "diagnostic severity must be a string" in (
            record.diagnostics[-1].details)
    finally:
        _shutdown(manager, coordinator)


def test_invalid_runtime_diagnostic_becomes_callback_failure(tmp_path):
    def activate(context):
        context.commands.register(CommandSpec(
            id="report",
            title="Report",
            callback=lambda: context.diagnostics.report(
                "runtime", "invalid", severity=None),
        ))

    plugin = _Plugin("com.example.invalid-runtime-diagnostic", activate)
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        assert not manager.invoke_command(
            "plugin.com.example.invalid-runtime-diagnostic.report")
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.ACTIVE
        assert record.diagnostics[-1].code == "command_callback_failed"
        assert "diagnostic severity must be a string" in (
            record.diagnostics[-1].details)
    finally:
        _shutdown(manager, coordinator)


def test_plugin_diagnostic_report_requires_valid_string_fields(tmp_path):
    plugin = _Plugin("com.example.diagnostic-fields")
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        diagnostics = plugin.context.diagnostics
        invalid = (
            ((None, "message", "", "error"), TypeError),
            (("code", None, "", "error"), TypeError),
            (("code", "message", None, "error"), TypeError),
            (("code", "message", "", None), TypeError),
            (("", "message", "", "error"), ValueError),
            (("code", "message", "", ""), ValueError),
        )
        for arguments, exception_type in invalid:
            try:
                diagnostics.report(*arguments)
            except exception_type:
                pass
            else:
                raise AssertionError(
                    "invalid diagnostic fields were accepted: %r" % (
                        arguments,))
        diagnostics.report("valid", "message", "details", "warning")
        recorded = manager.record_for(plugin.metadata.id).diagnostics
        assert len(recorded) == 1
        assert recorded[0].code == "valid"
        assert recorded[0].severity == "warning"
    finally:
        _shutdown(manager, coordinator)


def test_callback_failures_become_diagnostics(tmp_path):
    def activate(context):
        context.commands.register(CommandSpec(
            id="fail", title="Fail",
            callback=lambda: (_ for _ in ()).throw(RuntimeError("callback bad"))))
        context.documents.subscribe(
            lambda document: (_ for _ in ()).throw(RuntimeError("document bad")))

    plugin = _Plugin("com.example.callbacks", activate)
    _settings, coordinator, manager = _host(
        tmp_path, [plugin.metadata.id],
        [_candidate(plugin.metadata.id, lambda: plugin)])
    try:
        manager.activate_enabled()
        assert not manager.invoke_command("plugin.com.example.callbacks.fail")
        manager.publish_document(DocumentDescriptor(generation=1))
        codes = {item.code for item in manager.record_for(plugin.metadata.id).diagnostics}
        assert "command_callback_failed" in codes
        assert "document_callback_failed" in codes
    finally:
        _shutdown(manager, coordinator)


def test_shutdown_deactivates_in_reverse_and_continues_after_failure(tmp_path):
    order = []
    first = _Plugin(
        "a.plugin",
        deactivate=lambda: (
            order.append("a"),
            (_ for _ in ()).throw(RuntimeError("a failed")),
        ))
    second = _Plugin("b.plugin", deactivate=lambda: order.append("b"))
    _settings, coordinator, manager = _host(
        tmp_path, [first.metadata.id, second.metadata.id], [
            _candidate(second.metadata.id, lambda: second),
            _candidate(first.metadata.id, lambda: first),
        ])
    try:
        manager.activate_enabled()
        manager.shutdown()
        manager.shutdown()
        assert order == ["b", "a"]
        assert "deactivation_failed" in {
            item.code for item in manager.record_for("a.plugin").diagnostics}
    finally:
        coordinator.shutdown()


def test_safe_mode_bypasses_discovery(monkeypatch, tmp_path):
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    coordinator = TaskCoordinator(logical_cpus=1)
    called = []
    monkeypatch.setenv("LABELIMGPP_DISABLE_PLUGINS", "1")
    manager = PluginManager(
        settings, coordinator, discovery=lambda: called.append(True))
    try:
        assert manager.safe_mode
        assert manager.records == ()
        assert called == []
    finally:
        _shutdown(manager, coordinator)


def test_unavailable_config_is_retained_until_forget(tmp_path):
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {
        "enabled": ["gone.plugin"],
        "config": {"gone.plugin": {"keep": True}},
    }}
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(settings, coordinator, candidates=[])
    try:
        assert manager.record_for("gone.plugin").state == PluginState.UNAVAILABLE
        assert settings.get("plugins")["config"]["gone.plugin"] == {"keep": True}
        manager.forget("gone.plugin")
        assert "gone.plugin" not in settings.get("plugins")["config"]
    finally:
        _shutdown(manager, coordinator)


def test_validated_metadata_is_cached_without_reloading_disabled_plugin(tmp_path):
    plugin_id = "com.example.cached"
    plugin = _Plugin(plugin_id)
    settings, coordinator, manager = _host(
        tmp_path, [plugin_id], [_candidate(plugin_id, lambda: plugin)])
    try:
        manager.activate_enabled()
        cached = settings.get("plugins")["metadata"][plugin_id]
        assert cached["api_major"] == 1
        assert cached["capabilities"] == ["commands"]
        manager.set_enabled(plugin_id, False)
    finally:
        _shutdown(manager, coordinator)

    second_coordinator = TaskCoordinator(logical_cpus=1)
    loads = []
    second = PluginManager(
        settings, second_coordinator,
        candidates=[_candidate(plugin_id, lambda: loads.append(True))])
    try:
        record = second.record_for(plugin_id)
        assert record.state == PluginState.DISABLED
        assert record.metadata == plugin.metadata
        assert loads == []
    finally:
        _shutdown(second, second_coordinator)
