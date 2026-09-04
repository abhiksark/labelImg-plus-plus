"""Host-owned plugin actions and the restart-oriented plugin manager UI."""

from functools import partial
from html import escape
from urllib.parse import urlparse

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from libs.core.plugin_manager import PluginState, normalize_plugin_diagnostic
from libs.utils.constants import SETTING_SHORTCUTS
from libs.utils.dpi import scale_px


class QtPluginCommandHost:
    """Create and own every QAction declared by an active plugin."""

    def __init__(self, owner, menu, shortcut_config, action_map, settings):
        self._owner = owner
        self._menu = menu
        self._shortcut_config = shortcut_config
        self._action_map = action_map
        self._settings = settings
        self._actions = {}
        self._plugin_actions = {}
        self._plugin_shortcut_preexisting = {}
        self._plugin_callbacks = {}
        plugins = settings.get("plugins", {})
        owners = (
            plugins.get("shortcut_owners", {})
            if isinstance(plugins, dict) else {})
        self._shortcut_config.restore_plugin_owners(owners)
        self._update_visibility()

    @property
    def actions(self):
        return dict(self._actions)

    def commit(self, plugin_id, commands, invoke, enabled):
        self._assert_gui_thread()
        if plugin_id in self._plugin_actions:
            raise ValueError("plugin actions are already committed: %s" % plugin_id)
        collisions = set(commands).intersection(self._action_map)
        collisions.update(set(commands).intersection(self._actions))
        if collisions:
            raise ValueError(
                "action IDs already exist: %s" % ", ".join(sorted(collisions)))
        created = {}
        registered = []
        try:
            for command_id, spec in commands.items():
                preexisting = command_id in self._shortcut_config.to_dict()
                previous_owner = self._shortcut_config.owner_for(command_id)
                shortcut = self._shortcut_config.register_plugin(
                    command_id, spec.default_shortcut, plugin_id)
                registered.append(
                    (command_id, preexisting, previous_owner))
                action = QAction(spec.title, self._owner)
                action.setObjectName(command_id)
                action.setProperty("pluginCommandId", command_id)
                action.setToolTip(spec.description)
                action.setStatusTip(spec.description)
                action.setShortcut(shortcut)
                action.triggered.connect(partial(
                    self._trigger, plugin_id, command_id))
                action.setEnabled(False)
                created[command_id] = action
            for command_id, action in created.items():
                self._menu.addAction(action)
                self._action_map[command_id] = action
                self._actions[command_id] = action
            self._plugin_actions[plugin_id] = tuple(created)
            self._plugin_shortcut_preexisting[plugin_id] = {
                command_id: (preexisting, previous_owner)
                for command_id, preexisting, previous_owner in registered
            }
            self._plugin_callbacks[plugin_id] = (invoke, enabled)
            self._stage_shortcut_owners()
            self._update_visibility()
        except Exception:
            for command_id, action in created.items():
                self._menu.removeAction(action)
                self._action_map.pop(command_id, None)
                self._actions.pop(command_id, None)
                action.deleteLater()
            for command_id, preexisting, previous_owner in registered:
                self._shortcut_config.unregister_plugin(
                    command_id, retain=preexisting)
                self._shortcut_config.set_plugin_owner(
                    command_id, previous_owner)
            self._stage_shortcut_owners()
            self._update_visibility()
            raise

        cleaned = False

        def cleanup():
            nonlocal cleaned
            if cleaned:
                return
            cleaned = True
            self._remove_plugin(plugin_id)

        def rollback():
            nonlocal cleaned
            if cleaned:
                return
            cleaned = True
            self._remove_plugin(plugin_id, rollback=True)

        cleanup.rollback = rollback

        return cleanup

    def refresh_enablement(self):
        self._assert_gui_thread()
        for plugin_id, command_ids in tuple(self._plugin_actions.items()):
            callbacks = self._plugin_callbacks.get(plugin_id)
            if callbacks is None:
                continue
            enabled = callbacks[1]
            for command_id in command_ids:
                action = self._actions.get(command_id)
                if action is not None:
                    action.setEnabled(bool(enabled(command_id)))

    def forget(self, plugin_id):
        snapshot = self._shortcut_config._snapshot()
        try:
            self._shortcut_config.forget_plugin(plugin_id)
            self._settings[SETTING_SHORTCUTS] = self._shortcut_config.to_dict()
            self._stage_shortcut_owners()
            saved = self._settings.save()
        except Exception:
            self._shortcut_config._restore(snapshot)
            raise
        if not saved:
            self._shortcut_config._restore(snapshot)
        return saved

    def _remove_plugin(self, plugin_id, rollback=False):
        self._assert_gui_thread()
        preexisting = self._plugin_shortcut_preexisting.pop(plugin_id, {})
        for command_id in self._plugin_actions.pop(plugin_id, ()):
            action = self._actions.pop(command_id, None)
            self._action_map.pop(command_id, None)
            existed, previous_owner = preexisting.get(
                command_id, (False, None))
            self._shortcut_config.unregister_plugin(
                command_id,
                retain=(not rollback or existed),
            )
            if rollback:
                self._shortcut_config.set_plugin_owner(
                    command_id, previous_owner)
            if action is not None:
                self._menu.removeAction(action)
                action.deleteLater()
        self._plugin_callbacks.pop(plugin_id, None)
        self._stage_shortcut_owners()
        self._update_visibility()

    def _trigger(self, plugin_id, command_id, _checked=False):
        self._assert_gui_thread()
        callbacks = self._plugin_callbacks.get(plugin_id)
        if callbacks is not None:
            callbacks[0](command_id)

    def _stage_shortcut_owners(self):
        plugins = self._settings.get("plugins", {})
        plugins = dict(plugins) if isinstance(plugins, dict) else {}
        plugins["shortcut_owners"] = self._shortcut_config.plugin_owners()
        self._settings["plugins"] = plugins

    def _update_visibility(self):
        self._menu.menuAction().setVisible(bool(self._actions))

    @staticmethod
    def _assert_gui_thread():
        application = QApplication.instance()
        if application is None or QThread.currentThread() != application.thread():
            raise RuntimeError("plugin UI operations must run on QApplication.thread()")


class PluginManagerDialog(QDialog):
    """Inspect plugins and persist enablement for the next application start."""

    _COLUMNS = (
        "Plugin", "Provider", "Entry point", "Status",
        "API major", "Capabilities", "Enabled", "Homepage",
    )

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Plugins")
        self.setMinimumSize(scale_px(980), scale_px(600))

        layout = QVBoxLayout(self)
        warning = QLabel(
            "Plugins are trusted in-process Python code with the same access "
            "as labelImg++. Enable only packages whose publisher and source "
            "you trust; a virtual environment is recommended.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        if manager.safe_mode:
            safe_mode = QLabel(
                "Safe mode is active (LABELIMGPP_DISABLE_PLUGINS=1). "
                "Discovery and loading were skipped.")
            safe_mode.setWordWrap(True)
            layout.addWidget(safe_mode)

        self.table = QTableWidget(0, len(self._COLUMNS), self)
        self.table.setHorizontalHeaderLabels(self._COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.restart_notice = QLabel("")
        self.restart_notice.setWordWrap(True)
        layout.addWidget(self.restart_notice)

        details_label = QLabel("Diagnostics")
        layout.addWidget(details_label)
        self.diagnostics = QPlainTextEdit(self)
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setPlaceholderText("No diagnostics for this plugin.")
        layout.addWidget(self.diagnostics)

        self.homepage = QLabel("")
        self.homepage.setOpenExternalLinks(True)
        layout.addWidget(self.homepage)

        buttons = QHBoxLayout()
        self.copy_button = QPushButton("Copy Diagnostics", self)
        self.copy_button.clicked.connect(self._copy_diagnostics)
        self.forget_button = QPushButton("Forget Unavailable Plugin", self)
        self.forget_button.clicked.connect(self._forget_selected)
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.forget_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._populate()
        self.table.itemChanged.connect(self._enabled_changed)
        self.table.currentCellChanged.connect(self._selection_changed)
        if self.table.rowCount():
            self.table.selectRow(0)
            self._selection_changed(0, 0, -1, -1)
        else:
            self.forget_button.setEnabled(False)
            self.copy_button.setEnabled(False)

    def _populate(self):
        self.table.blockSignals(True)
        records = self.manager.records
        self.table.setRowCount(len(records))
        for row, record in enumerate(records):
            metadata = record.metadata
            display = metadata.display_name if metadata else record.id
            plugin_item = QTableWidgetItem(display)
            plugin_item.setData(Qt.ItemDataRole.UserRole, record)
            plugin_item.setToolTip(record.id)
            self.table.setItem(row, 0, plugin_item)
            provider = record.provider or "Unavailable"
            if record.provider_version:
                provider += " " + record.provider_version
            self.table.setItem(row, 1, QTableWidgetItem(provider))
            self.table.setItem(
                row, 2, QTableWidgetItem(record.reference or "Unavailable"))
            self.table.setItem(row, 3, QTableWidgetItem(
                self._status_text(record)))
            api = str(metadata.api_major) if metadata else "Unknown until enabled"
            capabilities = (
                ", ".join(item.value for item in metadata.capabilities)
                if metadata else "Unknown until enabled")
            self.table.setItem(row, 4, QTableWidgetItem(api))
            self.table.setItem(row, 5, QTableWidgetItem(capabilities))
            enabled = QTableWidgetItem("")
            enabled.setData(Qt.ItemDataRole.UserRole, record)
            enabled.setFlags(
                enabled.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            enabled.setCheckState(Qt.CheckState.Checked if record.enabled else Qt.CheckState.Unchecked)
            self.table.setItem(row, 6, enabled)
            self.table.setItem(
                row, 7, QTableWidgetItem(
                    metadata.homepage if metadata and metadata.homepage else ""))
        self.table.blockSignals(False)

    @staticmethod
    def _status_text(record):
        status = record.state.value.replace("_", " ").title()
        if record.state == PluginState.ACTIVE and not record.enabled:
            return status + " (disable after restart)"
        if record.state == PluginState.DISABLED and record.enabled:
            return status + " (enable after restart)"
        return status

    def _enabled_changed(self, item):
        if item.column() != 6:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        enabled = item.checkState() == Qt.CheckState.Checked
        try:
            self.manager.set_enabled(record.id, enabled)
        except Exception as exc:
            self.table.blockSignals(True)
            item.setCheckState(Qt.CheckState.Checked if record.enabled else Qt.CheckState.Unchecked)
            self.table.blockSignals(False)
            QMessageBox.warning(self, "Plugin settings", str(exc))
            return
        self.table.item(item.row(), 3).setText(self._status_text(record))
        self.restart_notice.setText(
            "The change was saved and will take effect after labelImg++ restarts.")

    def _selection_changed(self, current_row, _current_column,
                           _previous_row, _previous_column):
        record = self._record_at(current_row)
        if record is None:
            self.diagnostics.clear()
            self.homepage.clear()
            self.forget_button.setEnabled(False)
            return
        lines = []
        for diagnostic in record.diagnostics:
            diagnostic = normalize_plugin_diagnostic(record.id, diagnostic)
            lines.append(
                "[%s] %s/%s: %s" % (
                    diagnostic.severity.upper(), diagnostic.phase,
                    diagnostic.code, diagnostic.message))
            if diagnostic.details:
                lines.append(diagnostic.details.rstrip())
        self.diagnostics.setPlainText("\n\n".join(lines))
        metadata = record.metadata
        homepage = metadata.homepage if metadata else ""
        try:
            parsed = urlparse(homepage)
            valid_homepage = (
                parsed.scheme in ("http", "https") and bool(parsed.netloc))
        except ValueError:
            valid_homepage = False
        if valid_homepage:
            escaped = escape(homepage, quote=True)
            self.homepage.setText(
                '<a href="%s">%s</a>' % (escaped, escaped))
        else:
            self.homepage.clear()
        self.copy_button.setEnabled(bool(lines))
        self.forget_button.setEnabled(
            record.state == PluginState.UNAVAILABLE and not record.is_active)

    def _copy_diagnostics(self):
        QApplication.clipboard().setText(self.diagnostics.toPlainText())

    def _forget_selected(self):
        record = self._record_at(self.table.currentRow())
        if record is None:
            return
        try:
            saved = self.manager.forget(record.id)
        except Exception as exc:
            QMessageBox.warning(self, "Forget plugin", str(exc))
            return
        if not saved:
            QMessageBox.warning(
                self, "Forget plugin",
                "The plugin settings file could not be saved.")
            return
        self._populate()
        self.restart_notice.setText(
            "Unavailable plugin configuration and shortcuts were removed.")

    def _record_at(self, row):
        if row < 0 or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None


__all__ = ["PluginManagerDialog", "QtPluginCommandHost"]
