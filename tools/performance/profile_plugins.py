"""Five-run qualification for the plugin architecture performance budgets."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import weakref


REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if REPOSITORY_ROOT not in sys.path:
    sys.path.insert(0, REPOSITORY_ROOT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QMainWindow,
    QMenu,
)

from labelimgplusplus.plugins import (  # noqa: E402
    CommandSpec,
    DocumentDescriptor,
    PluginCapability,
    PluginMetadata,
)
from libs.core.plugin_discovery import (  # noqa: E402
    ENTRY_POINT_GROUP,
    PluginCandidate,
    discover_plugins,
)
from libs.core.plugin_manager import PluginManager  # noqa: E402
from libs.core.settings import Settings  # noqa: E402
from libs.core.shortcut_config import ShortcutConfig  # noqa: E402
from libs.core.task_coordinator import TaskCoordinator  # noqa: E402
from libs.widgets.pluginManagerDialog import (  # noqa: E402
    PluginManagerDialog,
    QtPluginCommandHost,
)


BUDGETS_MS = {
    "no_plugin_startup_p95_ms": 50.0,
    "disabled_100_discovery_p95_ms": 100.0,
    "manager_100_open_p95_ms": 100.0,
    "cancellation_ack_p95_ms": 500.0,
}
_PROFILE_APPLICATION = None


class _EntryPoint:
    group = ENTRY_POINT_GROUP

    def __init__(self, plugin_id, factory=None):
        self.name = plugin_id
        self.value = "benchmark_plugin:create_plugin"
        self.dist = SimpleNamespace(
            metadata={"Name": "benchmark-distribution"}, version="1.0.0")
        self._factory = factory

    def load(self):
        return self._factory


def _candidate(plugin_id, factory=None):
    entry = _EntryPoint(plugin_id, factory)
    return PluginCandidate(
        id=plugin_id,
        reference=entry.value,
        distribution="benchmark-distribution",
        distribution_version="1.0.0",
        entry_point=entry,
    )


def _settings(path, enabled=()):
    settings = Settings()
    settings.path = str(path)
    settings.data = {"plugins": {"enabled": list(enabled), "config": {}}}
    return settings


def _p95(values):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _measure(function, runs):
    function()
    values = []
    for _index in range(runs):
        started = time.perf_counter()
        function()
        values.append((time.perf_counter() - started) * 1000.0)
    return _p95(values), values


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.001)
    return False


class _BenchmarkPlugin:
    metadata = PluginMetadata(
        id="benchmark.plugin",
        display_name="Benchmark Plugin",
        version="1.0.0",
        api_major=1,
        capabilities=(PluginCapability.COMMANDS,),
    )

    def activate(self, context):
        self.context = context
        context.commands.register(CommandSpec(
            id="run", title="Run", callback=self.run))

    def deactivate(self):
        pass

    def run(self):
        pass


def _profile_no_plugins(settings_path):
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(
        _settings(settings_path), coordinator, discovery=discover_plugins)
    manager.shutdown()
    coordinator.shutdown()


def _profile_disabled_discovery(entries):
    candidates = discover_plugins(lambda: entries)
    if len(candidates) != len(entries) or not all(item.loadable for item in candidates):
        raise AssertionError("disabled discovery fixture was not fully discovered")


def _profile_manager_open(candidates, settings_path):
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(
        _settings(settings_path), coordinator, candidates=candidates)
    dialog = PluginManagerDialog(manager)
    if dialog.table.rowCount() != 100:
        raise AssertionError("plugin manager did not render all candidates")
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    manager.shutdown()
    coordinator.shutdown()


def _profile_cancellation(settings_path):
    coordinator = TaskCoordinator(logical_cpus=1)
    settings = _settings(settings_path, ("benchmark.plugin",))
    manager = PluginManager(
        settings, coordinator,
        candidates=[_candidate("benchmark.plugin", _BenchmarkPlugin)])
    manager.activate_enabled()
    record = manager.record_for("benchmark.plugin")
    started = threading.Event()

    def work(handle):
        started.set()
        while True:
            handle.check_cancelled()
            time.sleep(0.001)

    record.context.tasks.submit(work)
    if not started.wait(1):
        raise AssertionError("plugin cancellation benchmark did not start")
    before = time.perf_counter()
    manager.publish_document(DocumentDescriptor(generation=1))
    if not _wait_until(lambda: coordinator.queue_depths()["background"] == 0):
        raise AssertionError("plugin task did not acknowledge cancellation")
    elapsed_ms = (time.perf_counter() - before) * 1000.0
    manager.shutdown()
    coordinator.shutdown()
    return elapsed_ms


def _verify_teardown(settings_path):
    owner = QMainWindow()
    menu = QMenu("Plugins", owner)
    shortcuts = ShortcutConfig()
    action_map = {}
    settings = _settings(settings_path, ("benchmark.plugin",))
    coordinator = TaskCoordinator(logical_cpus=1, parent=owner)
    host = QtPluginCommandHost(owner, menu, shortcuts, action_map, settings)
    manager = PluginManager(
        settings, coordinator,
        candidates=[_candidate("benchmark.plugin", _BenchmarkPlugin)],
        command_host=host,
        parent=owner,
    )
    manager.activate_enabled()
    record = manager.record_for("benchmark.plugin")
    plugin = record.plugin
    context = record.context
    action = host.actions["plugin.benchmark.plugin.run"]
    references = {
        "plugin": weakref.ref(plugin),
        "context": weakref.ref(context),
        "action": weakref.ref(action),
    }
    manager.shutdown()
    coordinator.shutdown()
    if manager.active_commands or host.actions or record.plugin or record.context:
        raise AssertionError("plugin registrations survived teardown")
    del plugin, context, action
    owner.close()
    owner.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    gc.collect()
    retained = [name for name, reference in references.items()
                if reference() is not None]
    if retained:
        raise AssertionError("plugin teardown retained: %s" % ", ".join(retained))
    return True


def profile_plugins(runs=5):
    global _PROFILE_APPLICATION
    _PROFILE_APPLICATION = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory(prefix="labelimgpp-plugin-profile-") as temp:
        root = Path(temp)
        no_plugin_p95, no_plugin_runs = _measure(
            lambda: _profile_no_plugins(root / "no-plugin.json"), runs)
        entries = tuple(
            _EntryPoint("benchmark.disabled-%03d" % index)
            for index in range(100))
        discovery_p95, discovery_runs = _measure(
            lambda: _profile_disabled_discovery(entries), runs)
        candidates = tuple(
            _candidate("benchmark.manager-%03d" % index)
            for index in range(100))
        manager_p95, manager_runs = _measure(
            lambda: _profile_manager_open(
                candidates, root / "manager.json"), runs)
        _profile_cancellation(root / "cancel-warmup.json")
        cancellation_runs = [
            _profile_cancellation(root / ("cancel-%d.json" % index))
            for index in range(runs)]
        cancellation_p95 = _p95(cancellation_runs)
        teardown_clean = _verify_teardown(root / "teardown.json")
    return {
        "runs": runs,
        "no_plugin_startup_p95_ms": no_plugin_p95,
        "disabled_100_discovery_p95_ms": discovery_p95,
        "manager_100_open_p95_ms": manager_p95,
        "cancellation_ack_p95_ms": cancellation_p95,
        "teardown_clean": teardown_clean,
        "samples_ms": {
            "no_plugin_startup": no_plugin_runs,
            "disabled_100_discovery": discovery_runs,
            "manager_100_open": manager_runs,
            "cancellation_ack": cancellation_runs,
        },
    }


def assert_budgets(result):
    failures = []
    for name, budget in BUDGETS_MS.items():
        if result[name] >= budget:
            failures.append("%s %.3f >= %.3f" % (name, result[name], budget))
    if not result["teardown_clean"]:
        failures.append("plugin teardown retained registrations")
    if failures:
        raise AssertionError("; ".join(failures))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--assert-budgets", action="store_true")
    args = parser.parse_args(argv)
    result = profile_plugins(max(1, args.runs))
    if args.assert_budgets:
        assert_budgets(result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
