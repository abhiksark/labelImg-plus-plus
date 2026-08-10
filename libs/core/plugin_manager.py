"""Deterministic, failure-contained lifecycle for installed plugins."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import os
import traceback

from PyQt5.QtCore import QObject

from labelimgplusplus.plugins import (
    PLUGIN_API_MAJOR,
    DocumentDescriptor,
    PluginCapability,
    PluginDiagnostic,
    PluginMetadata,
)
from libs.core.plugin_discovery import (
    discover_plugins,
    is_valid_plugin_id,
    normalized_plugin_id,
)
from libs.core.plugin_registry import ActivationContext, validate_json_value


class PluginState(str, Enum):
    DISCOVERED = "discovered"
    DISABLED = "disabled"
    INCOMPATIBLE = "incompatible"
    CONFLICTING = "conflicting"
    LOADING = "loading"
    ACTIVE = "active"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    SHUTTING_DOWN = "shutting_down"


@dataclass
class PluginRecord:
    id: str
    state: PluginState
    enabled: bool
    candidate: object = None
    metadata: object = None
    diagnostics: list = field(default_factory=list)
    plugin: object = field(default=None, repr=False)
    context: object = field(default=None, repr=False)
    command_cleanup: object = field(default=None, repr=False)

    @property
    def is_active(self):
        return self.state == PluginState.ACTIVE

    @property
    def provider(self):
        return self.candidate.distribution if self.candidate else None

    @property
    def provider_version(self):
        return self.candidate.distribution_version if self.candidate else None

    @property
    def reference(self):
        return self.candidate.reference if self.candidate else None


class _NullCommandHost:
    def commit(self, plugin_id, commands, invoke):
        del plugin_id, commands, invoke
        return lambda: None


class _ValidationFailure(Exception):
    def __init__(self, code, message, state=PluginState.FAILED):
        super().__init__(message)
        self.code = code
        self.state = state


class PluginManager(QObject):
    """Own plugin discovery, activation, services, and teardown."""

    def __init__(self, settings, coordinator, candidates=None,
                 discovery=discover_plugins, command_host=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.coordinator = coordinator
        self.command_host = command_host or _NullCommandHost()
        self.safe_mode = os.environ.get("LABELIMGPP_DISABLE_PLUGINS") == "1"
        self._shutting_down = False
        self._activation_order = []
        self._commands = {}
        self._command_owners = {}
        self._document_subscriptions = []
        self._document = DocumentDescriptor()
        self._records = []
        if not self.safe_mode:
            discovered = tuple(candidates) if candidates is not None else discovery()
            discovered = tuple(sorted(
                discovered,
                key=lambda item: (
                    normalized_plugin_id(item.id), item.id,
                    item.distribution or "", item.reference),
            ))
            self._build_records(discovered)

    @property
    def records(self):
        return tuple(self._records)

    @property
    def document(self):
        return self._document

    @property
    def is_shutting_down(self):
        return self._shutting_down

    @property
    def active_commands(self):
        return dict(self._commands)

    def record_for(self, plugin_id):
        for record in self._records:
            if record.id == plugin_id:
                return record
        return None

    def activate_enabled(self):
        if self.safe_mode or self._shutting_down:
            return
        for record in self._records:
            if (record.enabled
                    and record.state == PluginState.DISCOVERED
                    and record.candidate is not None):
                self._activate(record)

    def invoke_command(self, command_id):
        record = self._command_owners.get(command_id)
        command = self._commands.get(command_id)
        if record is None or command is None or not record.is_active:
            return False
        try:
            command.callback()
            return True
        except Exception as exc:
            self._record_exception(
                record, "callback", "command_callback_failed", exc)
            return False

    def command_enabled(self, command_id):
        record = self._command_owners.get(command_id)
        command = self._commands.get(command_id)
        if record is None or command is None or not record.is_active:
            return False
        if command.enabled is None:
            return True
        try:
            return bool(command.enabled(self._document))
        except Exception as exc:
            self._record_exception(
                record, "callback", "enablement_callback_failed", exc)
            return False

    def publish_document(self, descriptor):
        if not isinstance(descriptor, DocumentDescriptor):
            raise TypeError("document updates must be DocumentDescriptor instances")
        generation_changed = descriptor.generation != self._document.generation
        self._document = descriptor
        if generation_changed:
            for record in self._activation_order:
                if record.context is not None:
                    record.context.tasks.cancel_all()
        for record, callback in tuple(self._document_subscriptions):
            if not record.is_active:
                continue
            try:
                callback(descriptor)
            except Exception as exc:
                self._record_exception(
                    record, "callback", "document_callback_failed", exc)

    def set_enabled(self, plugin_id, enabled):
        enabled_ids = set(self._enabled_ids())
        if enabled:
            enabled_ids.add(plugin_id)
        else:
            enabled_ids.discard(plugin_id)
        plugins = self._plugins_settings_copy()
        plugins["enabled"] = sorted(enabled_ids)
        self._replace_plugins_settings(plugins)
        for record in self._records:
            if record.id == plugin_id:
                record.enabled = bool(enabled)

    def forget(self, plugin_id):
        if any(record.id == plugin_id and record.is_active
               for record in self._records):
            raise RuntimeError("active plugins can only be forgotten after restart")
        plugins = self._plugins_settings_copy()
        plugins["enabled"] = [
            item for item in plugins.get("enabled", ()) if item != plugin_id]
        for section in ("config", "metadata"):
            values = plugins.get(section)
            if isinstance(values, dict):
                values.pop(plugin_id, None)
        self._replace_plugins_settings(plugins)
        self._records = [record for record in self._records
                         if record.id != plugin_id or record.candidate is not None]

    def shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        for record in reversed(self._activation_order):
            record.state = PluginState.SHUTTING_DOWN
            if record.context is not None:
                record.context.tasks.shutdown()
            try:
                record.plugin.deactivate()
            except Exception as exc:
                self._record_exception(
                    record, "deactivation", "deactivation_failed", exc)
            try:
                if record.command_cleanup is not None:
                    record.command_cleanup()
            except Exception as exc:
                self._record_exception(
                    record, "deactivation", "command_cleanup_failed", exc)
            self._remove_record_registrations(record)
            if record.context is not None:
                record.context.close()
            record.plugin = None
            record.context = None
            record.command_cleanup = None
        self._activation_order = []

    def _build_records(self, candidates):
        enabled = set(self._enabled_ids())
        available_ids = set()
        for candidate in candidates:
            available_ids.add(candidate.id)
            codes = {item.code for item in candidate.diagnostics}
            if "duplicate_plugin_id" in codes:
                state = PluginState.CONFLICTING
            elif "missing_provider_metadata" in codes:
                state = PluginState.UNAVAILABLE
            elif candidate.diagnostics:
                state = PluginState.FAILED
            elif candidate.id in enabled:
                state = PluginState.DISCOVERED
            else:
                state = PluginState.DISABLED
            self._records.append(PluginRecord(
                id=candidate.id,
                state=state,
                enabled=candidate.id in enabled,
                candidate=candidate,
                diagnostics=list(candidate.diagnostics),
            ))
        configured = set(enabled)
        config = self._plugins_settings_copy().get("config", {})
        if isinstance(config, dict):
            configured.update(key for key in config if isinstance(key, str))
        for plugin_id in sorted(configured - available_ids):
            self._records.append(PluginRecord(
                id=plugin_id,
                state=PluginState.UNAVAILABLE,
                enabled=plugin_id in enabled,
            ))

    def _activate(self, record):
        record.state = PluginState.LOADING
        plugin = None
        context = None
        host_cleanup = None
        activation_started = False
        settings_before = deepcopy(self.settings.data)
        try:
            try:
                factory = record.candidate.entry_point.load()
            except ModuleNotFoundError as exc:
                raise _ValidationFailure(
                    "missing_dependency", str(exc)) from exc
            if not callable(factory):
                raise _ValidationFailure(
                    "invalid_factory", "The entry point must resolve to a callable factory.")
            try:
                plugin = factory()
            except ModuleNotFoundError as exc:
                raise _ValidationFailure(
                    "missing_dependency", str(exc)) from exc
            metadata_value = getattr(plugin, "metadata", None)
            self._validate_plugin(record, plugin, metadata_value)
            record.metadata = metadata_value
            context = ActivationContext(
                self, record, self._plugin_config(record.id))
            activation_started = True
            try:
                plugin.activate(context)
            except ModuleNotFoundError as exc:
                raise _ValidationFailure(
                    "missing_dependency", str(exc)) from exc
            if (context.commands.commands
                    and PluginCapability.COMMANDS
                    not in metadata_value.capabilities):
                raise _ValidationFailure(
                    "capability_not_declared",
                    "Plugin registered commands without declaring the commands capability.",
                )
            staged = {}
            for local_id, command in context.commands.commands.items():
                command_id = "plugin.%s.%s" % (record.id, local_id)
                if command_id in self._commands:
                    raise _ValidationFailure(
                        "command_collision",
                        "Command ID already registered: %s" % command_id)
                staged[command_id] = command
            host_cleanup = self.command_host.commit(
                record.id, dict(staged), self.invoke_command)
            if not callable(host_cleanup):
                raise _ValidationFailure(
                    "invalid_command_host", "Command host did not return cleanup.")
            context.commit()
            self._commands.update(staged)
            self._command_owners.update(
                (command_id, record) for command_id in staged)
            record.plugin = plugin
            record.context = context
            record.command_cleanup = host_cleanup
            record.state = PluginState.ACTIVE
            self._activation_order.append(record)
        except _ValidationFailure as exc:
            self.settings.data = settings_before
            if host_cleanup is not None:
                self._safe_cleanup(record, host_cleanup)
            if context is not None:
                context.close()
            if activation_started:
                self._safe_failed_deactivation(record, plugin)
            record.state = exc.state
            self._record_diagnostic(
                record, "validation", exc.code, str(exc))
        except Exception as exc:
            self.settings.data = settings_before
            if host_cleanup is not None:
                self._safe_cleanup(record, host_cleanup)
            if context is not None:
                context.close()
            if activation_started:
                self._safe_failed_deactivation(record, plugin)
            record.state = PluginState.FAILED
            phase = "activation" if plugin is not None else "factory"
            self._record_exception(record, phase, "%s_failed" % phase, exc)

    def _validate_plugin(self, record, plugin, metadata_value):
        if not callable(getattr(plugin, "activate", None)):
            raise _ValidationFailure(
                "invalid_plugin", "Plugin has no callable activate() method.")
        if not callable(getattr(plugin, "deactivate", None)):
            raise _ValidationFailure(
                "invalid_plugin", "Plugin has no callable deactivate() method.")
        if not isinstance(metadata_value, PluginMetadata):
            raise _ValidationFailure(
                "invalid_metadata", "Plugin metadata must be PluginMetadata.")
        if metadata_value.id != record.id:
            raise _ValidationFailure(
                "metadata_id_mismatch",
                "Entry-point ID %r does not match metadata ID %r."
                % (record.id, metadata_value.id))
        if not is_valid_plugin_id(metadata_value.id):
            raise _ValidationFailure(
                "invalid_plugin_id", "Plugin metadata contains an invalid ID.")
        if type(metadata_value.api_major) is not int:
            raise _ValidationFailure(
                "invalid_metadata", "API major must be an integer.")
        if metadata_value.api_major != PLUGIN_API_MAJOR:
            raise _ValidationFailure(
                "api_major_mismatch",
                "Plugin requires API major %s; host provides %s."
                % (metadata_value.api_major, PLUGIN_API_MAJOR),
                PluginState.INCOMPATIBLE,
            )
        if (not isinstance(metadata_value.display_name, str)
                or not metadata_value.display_name.strip()
                or not isinstance(metadata_value.version, str)
                or not metadata_value.version.strip()
                or not isinstance(metadata_value.description, str)
                or not isinstance(metadata_value.homepage, str)):
            raise _ValidationFailure(
                "invalid_metadata",
                "Metadata text fields are invalid or required fields are empty.")
        if not isinstance(metadata_value.capabilities, tuple):
            raise _ValidationFailure(
                "invalid_metadata", "Capabilities must be a tuple.")
        if any(not isinstance(capability, PluginCapability)
               for capability in metadata_value.capabilities):
            raise _ValidationFailure(
                "invalid_metadata",
                "Capabilities must contain PluginCapability values.")
        supported = {PluginCapability.COMMANDS}
        unknown = [capability for capability in metadata_value.capabilities
                   if capability not in supported]
        if unknown:
            raise _ValidationFailure(
                "unsupported_capability",
                "Unsupported plugin capabilities: %s" % ", ".join(map(str, unknown)),
                PluginState.INCOMPATIBLE,
            )

    def _safe_failed_deactivation(self, record, plugin):
        if plugin is None or not callable(getattr(plugin, "deactivate", None)):
            return
        try:
            plugin.deactivate()
        except Exception as exc:
            self._record_exception(
                record, "deactivation", "rollback_deactivation_failed", exc)

    def _safe_cleanup(self, record, cleanup):
        try:
            rollback = getattr(cleanup, "rollback", cleanup)
            rollback()
        except Exception as exc:
            self._record_exception(
                record, "activation", "rollback_cleanup_failed", exc)

    def _remove_record_registrations(self, record):
        for command_id, owner in tuple(self._command_owners.items()):
            if owner is record:
                self._command_owners.pop(command_id, None)
                self._commands.pop(command_id, None)
        self._document_subscriptions = [
            item for item in self._document_subscriptions if item[0] is not record]

    def _add_document_subscription(self, record, callback):
        self._document_subscriptions.append((record, callback))

    def _remove_document_subscription(self, record, callback):
        item = (record, callback)
        if item in self._document_subscriptions:
            self._document_subscriptions.remove(item)

    def _record_diagnostic(self, record, phase, code, message, details="",
                           severity="error"):
        record.diagnostics.append(PluginDiagnostic(
            plugin_id=record.id,
            phase=phase,
            code=code,
            message=str(message),
            details=str(details),
            severity=severity,
        ))

    def _record_exception(self, record, phase, code, exc):
        details = "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__))
        self._record_diagnostic(record, phase, code, str(exc), details)

    def _enabled_ids(self):
        values = self._plugins_settings_copy().get("enabled", ())
        if not isinstance(values, list):
            return ()
        return tuple(item for item in values if isinstance(item, str))

    def _plugin_config(self, plugin_id):
        configs = self._plugins_settings_copy().get("config", {})
        value = configs.get(plugin_id, {}) if isinstance(configs, dict) else {}
        try:
            validate_json_value(value, "plugins.config.%s" % plugin_id)
        except ValueError:
            return {}
        return deepcopy(value) if isinstance(value, dict) else {}

    def _persist_plugin_config(self, plugin_id, value):
        validate_json_value(value, "plugins.config.%s" % plugin_id)
        plugins = self._plugins_settings_copy()
        configs = plugins.setdefault("config", {})
        if not isinstance(configs, dict):
            configs = {}
            plugins["config"] = configs
        configs[plugin_id] = deepcopy(value)
        self._replace_plugins_settings(plugins)

    def _plugins_settings_copy(self):
        plugins = self.settings.get("plugins", {})
        return deepcopy(plugins) if isinstance(plugins, dict) else {}

    def _replace_plugins_settings(self, plugins):
        before = deepcopy(self.settings.data)
        self.settings["plugins"] = plugins
        try:
            saved = self.settings.save()
        except Exception:
            self.settings.data = before
            raise
        if not saved:
            self.settings.data = before
            raise OSError("could not persist plugin settings")


__all__ = ["PluginManager", "PluginRecord", "PluginState"]
