import json
import threading
import time

from PyQt5.QtCore import QCoreApplication, QThread, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QMainWindow, QMenu

import labelImgPlusPlus as application_module
from labelimgplusplus.plugins import (
    CommandSpec,
    PluginCapability,
    PluginDiagnostic,
    PluginMetadata,
)
from libs.core.plugin_discovery import PluginCandidate
from libs.core.plugin_manager import PluginManager, PluginState
from libs.core.settings import Settings
from libs.core.shortcut_config import ShortcutConfig
from libs.core.task_coordinator import TaskCoordinator
from libs.widgets.pluginManagerDialog import (
    PluginManagerDialog,
    QtPluginCommandHost,
)


def _wait_until(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.002)
    return False


class _EntryPoint:
    name = "com.example.qt"
    value = "qt_fixture:create_plugin"
    group = "labelimgplusplus.plugins"

    def __init__(self, factory):
        self._factory = factory

    def load(self):
        return self._factory


def _candidate(factory):
    entry = _EntryPoint(factory)
    return PluginCandidate(
        id=entry.name,
        reference=entry.value,
        distribution="qt-fixture",
        distribution_version="1.0.0",
        entry_point=entry,
    )


class _QtPlugin:
    metadata = PluginMetadata(
        id="com.example.qt",
        display_name="Qt Fixture",
        version="1.0.0",
        api_major=1,
        capabilities=(PluginCapability.COMMANDS,),
        homepage="https://example.invalid/plugin",
    )

    def __init__(self, events):
        self.events = events
        self.context = None

    def activate(self, context):
        self.context = context
        context.documents.subscribe(self._document_changed)
        context.commands.register(CommandSpec(
            id="inspect",
            title="Inspect Document",
            description="Exercise the host-owned command path",
            default_shortcut="Ctrl+Alt+I",
            callback=self._run,
            enabled=lambda document: document.kind == "image",
        ))

    def deactivate(self):
        self.events.append(("deactivate", QThread.currentThread()))

    def _document_changed(self, document):
        self.events.append(
            ("document", document, QThread.currentThread()))

    def _run(self):
        self.events.append(("command", QThread.currentThread()))

        def work(handle):
            handle.check_cancelled()
            self.events.append(("worker", threading.get_ident()))
            return "complete"

        self.context.tasks.submit(
            work,
            on_result=lambda value: self.events.append(
                ("result", value, QThread.currentThread())),
        )


def _isolated_window(monkeypatch, tmp_path, enabled, plugin):
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {
        "enabled": [plugin.metadata.id] if enabled else [],
        "config": {},
    }}
    settings.save()
    monkeypatch.setattr(application_module, "Settings", lambda: settings)

    def create_manager(host_settings, coordinator, parent=None):
        return PluginManager(
            host_settings, coordinator,
            candidates=[_candidate(lambda: plugin)], parent=parent)

    monkeypatch.setattr(application_module, "PluginManager", create_manager)
    return application_module.MainWindow(), settings


def _close_window(window):
    window.dirty = False
    window.close()
    QCoreApplication.processEvents()


def test_mainwindow_owns_actions_and_publishes_documents_on_gui_thread(
        monkeypatch, tmp_path):
    events = []
    plugin = _QtPlugin(events)
    window, _settings = _isolated_window(
        monkeypatch, tmp_path, enabled=True, plugin=plugin)
    app = QApplication.instance()
    command_id = "plugin.com.example.qt.inspect"
    try:
        record = window.plugin_manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.ACTIVE
        action = window._action_map[command_id]
        assert action.parent() is window
        assert action.thread() == app.thread()
        assert window.menus.plugins.thread() == app.thread()
        assert window.menus.plugins.menuAction().isVisible()
        assert not action.isEnabled()
        assert window.shortcut_config.get(command_id) == "Ctrl+Alt+I"

        image_path = str(tmp_path / "document.png")
        image = QImage(32, 24, QImage.Format_RGB32)
        image.fill(0xFFFFFFFF)
        assert image.save(image_path)
        assert window.load_file(image_path)
        assert action.isEnabled()
        descriptor = window.plugin_manager.document
        assert descriptor.kind == "image"
        assert descriptor.source_path == image_path
        assert descriptor.read_only is False

        action.trigger()
        assert _wait_until(
            lambda: any(event[0] == "result" for event in events))
        command = next(event for event in events if event[0] == "command")
        result = next(event for event in events if event[0] == "result")
        assert command[1] == app.thread()
        assert result[1:] == ("complete", app.thread())
        assert any(event[0] == "worker" for event in events)
        assert all(
            event[-1] == app.thread()
            for event in events if event[0] == "document")

        previous_generation = descriptor.generation
        window.reset_state()
        assert window.plugin_manager.document.kind == "none"
        assert window.plugin_manager.document.generation > previous_generation
        assert not action.isEnabled()
    finally:
        _close_window(window)

    assert events[-1] == ("deactivate", app.thread())
    assert command_id not in window._action_map


def test_manager_enablement_is_saved_but_does_not_hot_load(
        monkeypatch, tmp_path):
    events = []
    plugin = _QtPlugin(events)
    loaded = []
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {"enabled": [], "config": {}}}
    settings.save()
    monkeypatch.setattr(application_module, "Settings", lambda: settings)

    def create_manager(host_settings, coordinator, parent=None):
        candidate = _candidate(lambda: (loaded.append(True), plugin)[1])
        return PluginManager(
            host_settings, coordinator, candidates=[candidate], parent=parent)

    monkeypatch.setattr(application_module, "PluginManager", create_manager)
    window = application_module.MainWindow()
    dialog = PluginManagerDialog(window.plugin_manager, window)
    try:
        record = window.plugin_manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.DISABLED
        assert loaded == []
        assert not window.menus.plugins.menuAction().isVisible()
        assert dialog.table.item(0, 4).text() == "Unknown until enabled"

        enabled_item = dialog.table.item(0, 6)
        enabled_item.setCheckState(Qt.Checked)
        QCoreApplication.processEvents()
        assert record.enabled is True
        assert record.state == PluginState.DISABLED
        assert loaded == []
        assert "restart" in dialog.restart_notice.text().lower()
        with open(settings.path, "r", encoding="utf-8") as settings_file:
            persisted = json.load(settings_file)
        assert persisted["plugins"]["enabled"] == [plugin.metadata.id]
    finally:
        dialog.close()
        _close_window(window)


def test_failed_host_commit_removes_actions_and_new_shortcut_defaults(tmp_path):
    class FailingSettings(Settings):
        def save(self):
            return False

    events = []
    plugin = _QtPlugin(events)
    owner = QMainWindow()
    menu = QMenu("Plugins", owner)
    shortcuts = ShortcutConfig()
    action_map = {}
    settings = FailingSettings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {
        "enabled": [plugin.metadata.id], "config": {}}}
    coordinator = TaskCoordinator(logical_cpus=1, parent=owner)
    host = QtPluginCommandHost(
        owner, menu, shortcuts, action_map, settings)
    manager = PluginManager(
        settings, coordinator,
        candidates=[_candidate(lambda: plugin)],
        command_host=host,
        parent=owner,
    )
    command_id = "plugin.com.example.qt.inspect"
    try:
        manager.activate_enabled()
        record = manager.record_for(plugin.metadata.id)
        assert record.state == PluginState.FAILED
        assert manager.active_commands == {}
        assert host.actions == {}
        assert action_map == {}
        assert command_id not in shortcuts.to_dict()
        assert not menu.menuAction().isVisible()
    finally:
        manager.shutdown()
        coordinator.shutdown()
        owner.close()


def test_command_host_keeps_dispatchers_isolated_per_plugin(tmp_path):
    owner = QMainWindow()
    menu = QMenu("Plugins", owner)
    shortcuts = ShortcutConfig()
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {"enabled": [], "config": {}}}
    host = QtPluginCommandHost(owner, menu, shortcuts, {}, settings)
    calls = []
    first_id = "plugin.a.run"
    second_id = "plugin.a.b.run"
    first_cleanup = host.commit(
        "a",
        {first_id: CommandSpec(
            id="run", title="First", callback=lambda: None)},
        lambda command_id: calls.append(("a", command_id)),
        lambda _command_id: True,
    )
    second_cleanup = host.commit(
        "a.b",
        {second_id: CommandSpec(
            id="run", title="Second", callback=lambda: None)},
        lambda command_id: calls.append(("a.b", command_id)),
        lambda _command_id: True,
    )
    try:
        host.refresh_enablement()
        host.actions[first_id].trigger()
        host.actions[second_id].trigger()
        assert calls == [("a", first_id), ("a.b", second_id)]
        first_cleanup()
        host.actions[second_id].trigger()
        assert calls[-1] == ("a.b", second_id)
    finally:
        first_cleanup()
        second_cleanup()
        owner.close()


def test_manager_homepage_allows_only_escaped_web_links(tmp_path):
    plugin = _QtPlugin([])
    plugin.metadata = PluginMetadata(
        id=plugin.metadata.id,
        display_name=plugin.metadata.display_name,
        version=plugin.metadata.version,
        api_major=plugin.metadata.api_major,
        capabilities=plugin.metadata.capabilities,
        homepage='javascript:alert("plugin")',
    )
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {
        "enabled": [plugin.metadata.id], "config": {}}}
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(
        settings, coordinator, candidates=[_candidate(lambda: plugin)])
    manager.activate_enabled()
    dialog = PluginManagerDialog(manager)
    try:
        assert dialog.homepage.text() == ""
        record = manager.record_for(plugin.metadata.id)
        record.metadata = PluginMetadata(
            id=plugin.metadata.id,
            display_name=plugin.metadata.display_name,
            version=plugin.metadata.version,
            api_major=plugin.metadata.api_major,
            capabilities=plugin.metadata.capabilities,
            homepage='https://example.invalid/?q="><script>',
        )
        dialog._selection_changed(0, 0, -1, -1)
        rendered = dialog.homepage.text()
        assert rendered.startswith('<a href="https://')
        assert "&quot;&gt;&lt;script&gt;" in rendered
        assert "<script>" not in rendered
    finally:
        dialog.close()
        manager.shutdown()
        coordinator.shutdown()


def test_manager_renders_malformed_diagnostics_defensively(tmp_path):
    plugin = _QtPlugin([])
    settings = Settings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {"plugins": {
        "enabled": [plugin.metadata.id], "config": {}}}
    coordinator = TaskCoordinator(logical_cpus=1)
    manager = PluginManager(
        settings, coordinator, candidates=[_candidate(lambda: plugin)])
    manager.activate_enabled()
    record = manager.record_for(plugin.metadata.id)
    record.diagnostics.extend([
        PluginDiagnostic(
            plugin_id=plugin.metadata.id,
            phase="runtime",
            code="missing-severity",
            message="severity was None",
            severity=None,
        ),
        {
            "phase": None,
            "code": "",
            "message": None,
            "details": None,
            "severity": None,
        },
        object(),
    ])
    dialog = PluginManagerDialog(manager)
    try:
        dialog._selection_changed(0, 0, -1, -1)
        rendered = dialog.diagnostics.toPlainText()
        assert "[ERROR] runtime/missing-severity: severity was None" in rendered
        assert "unknown/invalid_diagnostic" in rendered
        assert "Malformed plugin diagnostic." in rendered
    finally:
        dialog.close()
        manager.shutdown()
        coordinator.shutdown()


def test_failed_forget_keeps_record_settings_and_exact_shortcuts(tmp_path):
    class FailingSettings(Settings):
        def save(self):
            return False

    plugin_id = "a"
    command_id = "plugin.a.run"
    settings = FailingSettings()
    settings.path = str(tmp_path / "settings.json")
    settings.data = {
        "plugins": {
            "enabled": [],
            "config": {plugin_id: {"retained": True}},
            "shortcut_owners": {command_id: plugin_id},
        },
        "shortcuts": {command_id: "Ctrl+1"},
    }
    shortcuts = ShortcutConfig()
    shortcuts.from_dict(settings.data["shortcuts"])
    owner = QMainWindow()
    host = QtPluginCommandHost(
        owner, QMenu("Plugins", owner), shortcuts, {}, settings)
    coordinator = TaskCoordinator(logical_cpus=1, parent=owner)
    manager = PluginManager(
        settings, coordinator, candidates=[], command_host=host, parent=owner)
    try:
        assert manager.record_for(plugin_id).state == PluginState.UNAVAILABLE
        assert manager.forget(plugin_id) is False
        assert manager.record_for(plugin_id) is not None
        assert settings.data["plugins"]["config"][plugin_id] == {
            "retained": True}
        assert shortcuts.to_dict()[command_id] == "Ctrl+1"
        assert shortcuts.owner_for(command_id) == plugin_id
    finally:
        manager.shutdown()
        coordinator.shutdown()
        owner.close()
