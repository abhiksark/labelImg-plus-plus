"""Transactional registries and restricted services for plugin activation."""

from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass
from copy import deepcopy
import math
import re
import threading
import traceback
from types import MappingProxyType
from typing import Optional
import weakref

from PyQt6.QtCore import QObject, Qt, pyqtSlot

from labelimgplusplus.plugins import CommandSpec
from libs.core.task_coordinator import JobCancelled, JobPriority


_VALID_COMMAND_ID = re.compile(r"^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$")
_RESERVED_SETTINGS_KEY = "__type__"


def validate_json_value(value, path="value", seen=None):
    """Raise ``ValueError`` unless *value* is strict, untagged JSON data."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("%s must not contain NaN or infinity" % path)
        return
    if seen is None:
        seen = set()
    if isinstance(value, list):
        identity = id(value)
        if identity in seen:
            raise ValueError("%s must not contain cycles" % path)
        seen.add(identity)
        try:
            for index, item in enumerate(value):
                validate_json_value(item, "%s[%d]" % (path, index), seen)
        finally:
            seen.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in seen:
            raise ValueError("%s must not contain cycles" % path)
        seen.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError("%s keys must be strings" % path)
                if key == _RESERVED_SETTINGS_KEY:
                    raise ValueError(
                        "%s contains reserved key %r" % (path, key))
                validate_json_value(item, "%s.%s" % (path, key), seen)
        finally:
            seen.remove(identity)
        return
    raise ValueError(
        "%s is not JSON-compatible: %s" % (path, type(value).__name__))


class StagedCommandRegistry:
    """Collect commands without exposing the host's live registry."""

    def __init__(self, plugin_id):
        self._plugin_id = plugin_id
        self._commands = {}
        self._closed = False

    @property
    def commands(self):
        return dict(self._commands)

    def register(self, command):
        if self._closed:
            raise RuntimeError("command registry is closed")
        if not isinstance(command, CommandSpec):
            raise TypeError("commands must be CommandSpec instances")
        if not _VALID_COMMAND_ID.fullmatch(command.id or ""):
            raise ValueError("invalid command ID: %r" % command.id)
        if command.id in self._commands:
            raise ValueError("duplicate command ID: %s" % command.id)
        if not isinstance(command.title, str) or not command.title.strip():
            raise ValueError("command title must be a non-empty string")
        if not callable(command.callback):
            raise TypeError("command callback must be callable")
        if not isinstance(command.description, str):
            raise TypeError("command description must be a string")
        if not isinstance(command.default_shortcut, str):
            raise TypeError("command default shortcut must be a string")
        if command.enabled is not None and not callable(command.enabled):
            raise TypeError("command enablement predicate must be callable")
        namespaced = "plugin.%s.%s" % (self._plugin_id, command.id)
        self._commands[command.id] = command
        return namespaced

    def close(self):
        self._closed = True


class StagedPluginSettings:
    """Plugin-isolated settings with activation-time write staging."""

    def __init__(self, manager, plugin_id, initial):
        self._manager = manager
        self._plugin_id = plugin_id
        self._data = deepcopy(initial) if isinstance(initial, dict) else {}
        try:
            validate_json_value(self._data, "plugin settings")
        except ValueError:
            self._data = {}
        self._active = False
        self._closed = False

    def get(self, key, default=None):
        self._validate_key(key)
        return deepcopy(self._data.get(key, default))

    def set(self, key, value):
        self._ensure_open()
        self._validate_key(key)
        validate_json_value(value, "settings.%s" % key)
        updated = deepcopy(self._data)
        updated[key] = deepcopy(value)
        if self._active:
            self._manager._persist_plugin_config(self._plugin_id, updated)
        self._data = updated

    def delete(self, key):
        self._ensure_open()
        self._validate_key(key)
        if key not in self._data:
            return
        updated = deepcopy(self._data)
        del updated[key]
        if self._active:
            self._manager._persist_plugin_config(self._plugin_id, updated)
        self._data = updated

    def as_dict(self):
        return MappingProxyType(deepcopy(self._data))

    def commit(self):
        self._ensure_open()
        self._manager._persist_plugin_config(self._plugin_id, self._data)
        self._active = True

    def close(self):
        self._closed = True

    def _ensure_open(self):
        if self._closed:
            raise RuntimeError("plugin settings are closed")

    @staticmethod
    def _validate_key(key):
        if not isinstance(key, str) or not key or key == _RESERVED_SETTINGS_KEY:
            raise ValueError("plugin setting keys must be non-empty strings")


class StagedDocumentService:
    """Read-only document state with subscriptions staged until commit."""

    def __init__(self, manager, record):
        self._manager = manager
        self._record = record
        self._staged = []
        self._committed = []
        self._closed = False

    @property
    def current(self):
        return self._manager.document

    def subscribe(self, callback):
        if self._closed:
            raise RuntimeError("document service is closed")
        if not callable(callback):
            raise TypeError("document callback must be callable")
        target = self._committed if self._record.is_active else self._staged
        target.append(callback)
        if self._record.is_active:
            self._manager._add_document_subscription(self._record, callback)
        active = True

        def unsubscribe():
            nonlocal active
            if not active:
                return
            active = False
            for callbacks in (self._staged, self._committed):
                if callback in callbacks:
                    callbacks.remove(callback)
            self._manager._remove_document_subscription(self._record, callback)

        return unsubscribe

    def commit(self):
        for callback in self._staged:
            self._manager._add_document_subscription(self._record, callback)
            self._committed.append(callback)
        self._staged = []

    def close(self):
        for callback in list(self._committed):
            self._manager._remove_document_subscription(self._record, callback)
        self._committed = []
        self._staged = []
        self._closed = True


class PluginDiagnosticService:
    def __init__(self, manager, record):
        self._manager = manager
        self._record = record

    def report(self, code, message, details="", severity="error"):
        self._manager._record_diagnostic(
            self._record, "plugin", code, message, details, severity)


class _PluginTaskHandle:
    """Plain plugin task facade with no Qt or coordinator surface."""

    __slots__ = ("_cancelled", "_handle_ref")

    def __init__(self, handle):
        self._cancelled = threading.Event()
        self._handle_ref = weakref.ref(handle)

    def cancel(self):
        self._cancelled.set()
        handle = self._handle_ref() if self._handle_ref is not None else None
        if handle is not None:
            handle.cancel()

    def is_cancelled(self):
        if self._cancelled.is_set():
            return True
        handle = self._handle_ref() if self._handle_ref is not None else None
        if handle is not None and handle.is_cancelled():
            self._cancelled.set()
            return True
        return False

    def check_cancelled(self):
        if self.is_cancelled():
            raise CancelledError()

    def report_progress(self, value):
        handle = self._handle_ref() if self._handle_ref is not None else None
        if handle is not None and not self._cancelled.is_set():
            handle.report_progress(value)


def _detach_task_handle(handle):
    coordinator_handle = (
        handle._handle_ref() if handle._handle_ref is not None else None)
    if coordinator_handle is not None and coordinator_handle.is_cancelled():
        handle._cancelled.set()
    handle._handle_ref = None


@dataclass(frozen=True)
class _TaskOutcome:
    result: object = None
    message: Optional[str] = None
    details: str = ""

    @property
    def failed(self):
        return self.message is not None

    @classmethod
    def from_exception(cls, exc):
        details = "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__))
        return cls(message=str(exc), details=details)


class _TaskBridge(QObject):
    """QObject receiver that fences callbacks to the application thread."""

    def __init__(self, service, handle, generation):
        super().__init__(service._manager)
        self._service = service
        self._handle = handle
        self._generation = generation
        self._result_callback = None
        self._error_callback = None
        self._progress_callback = None

    def configure(self, on_result, on_error, on_progress):
        self._result_callback = on_result
        self._error_callback = on_error
        self._progress_callback = on_progress

    def _deliverable(self):
        if self._service is None or self._handle is None:
            return False
        return (
            self._service.accepting
            and self._service._record.is_active
            and self._service._manager.document.generation == self._generation
            and not self._handle.is_cancelled()
        )

    @pyqtSlot(object)
    def result(self, outcome):
        if not self._deliverable():
            return
        if outcome.failed:
            self._service._manager._record_diagnostic(
                self._service._record,
                "task",
                "task_failed",
                outcome.message,
                outcome.details,
            )
            if self._error_callback is not None:
                self._service._invoke_callback(
                    "error", self._error_callback, outcome.message)
        elif self._result_callback is not None:
            self._service._invoke_callback(
                "result", self._result_callback, outcome.result)

    @pyqtSlot(str)
    def error(self, message):
        if not self._deliverable():
            return
        self._service._manager._record_diagnostic(
            self._service._record,
            "task",
            "task_failed",
            message,
        )
        if self._error_callback is not None:
            self._service._invoke_callback("error", self._error_callback, message)

    @pyqtSlot(object)
    def progress(self, value):
        if self._deliverable() and self._progress_callback is not None:
            self._service._invoke_callback(
                "progress", self._progress_callback, value)

    @pyqtSlot()
    def finished(self):
        if self._service is None:
            return
        self._service._finished(self._handle)

    def detach(self):
        self._result_callback = None
        self._error_callback = None
        self._progress_callback = None
        self._service = None
        self._handle = None


class PluginTaskServiceImpl:
    """Plugin-scoped adapter over the coordinator background lane."""

    def __init__(self, manager, record):
        self._manager = manager
        self._record = record
        self._accepting = False
        self._bridges = {}
        self._latest_by_key = {}

    @property
    def accepting(self):
        return self._accepting and not self._manager.is_shutting_down

    @property
    def handles(self):
        return tuple(self._bridges)

    def commit(self):
        self._accepting = True

    def submit(self, work, key=None, latest=False, on_result=None,
               on_error=None, on_progress=None):
        if not self.accepting:
            raise RuntimeError("plugin tasks cannot start during activation or shutdown")
        if not callable(work):
            raise TypeError("task work must be callable")
        for name, callback in (
                ("result", on_result), ("error", on_error),
                ("progress", on_progress)):
            if callback is not None and not callable(callback):
                raise TypeError("%s callback must be callable" % name)
        if key is not None and (not isinstance(key, str) or not key):
            raise ValueError("task key must be a non-empty string")
        generation = self._manager.document.generation
        namespaced_key = (
            "plugin.%s.%s" % (self._record.id, key)
            if key is not None else None)
        ready = threading.Event()

        facade = None

        def connected_work(_coordinator_handle):
            ready.wait()
            try:
                facade.check_cancelled()
                return _TaskOutcome(result=work(facade))
            except CancelledError as exc:
                raise JobCancelled() from exc
            except Exception as exc:
                return _TaskOutcome.from_exception(exc)

        coordinator_handle = self._manager.coordinator.submit(
            "background",
            connected_work,
            priority=JobPriority.BULK,
            key=namespaced_key,
            latest=latest,
            generation=generation,
        )
        facade = _PluginTaskHandle(coordinator_handle)
        bridge = _TaskBridge(self, facade, generation)
        try:
            bridge.configure(on_result, on_error, on_progress)
            if latest and namespaced_key is not None:
                previous = self._latest_by_key.get(namespaced_key)
                if previous is not None:
                    previous.cancel()
                    self._release(previous)
                self._latest_by_key[namespaced_key] = facade
            self._bridges[facade] = bridge
            coordinator_handle.result.connect(bridge.result, Qt.ConnectionType.QueuedConnection)
            coordinator_handle.error.connect(bridge.error, Qt.ConnectionType.QueuedConnection)
            coordinator_handle.progress.connect(
                bridge.progress, Qt.ConnectionType.QueuedConnection)
            coordinator_handle.finished.connect(
                bridge.finished, Qt.ConnectionType.QueuedConnection)
        except Exception:
            facade.cancel()
            self._release(facade, bridge)
            raise
        finally:
            ready.set()
        return facade

    def cancel_all(self):
        for handle in tuple(self._bridges):
            handle.cancel()
            self._release(handle)

    def shutdown(self):
        self._accepting = False
        for handle in tuple(self._bridges):
            handle.cancel()
            self._release(handle)
        self._latest_by_key.clear()

    def _finished(self, handle):
        self._release(handle)

    def _release(self, handle, bridge=None):
        bridge = bridge or self._bridges.pop(handle, None)
        self._bridges.pop(handle, None)
        for key, latest_handle in tuple(self._latest_by_key.items()):
            if latest_handle is handle:
                self._latest_by_key.pop(key, None)
        _detach_task_handle(handle)
        if bridge is not None:
            bridge.detach()
            bridge.deleteLater()

    def _invoke_callback(self, kind, callback, value):
        try:
            callback(value)
        except Exception as exc:
            self._manager._record_exception(
                self._record,
                "callback",
                "%s_callback_failed" % kind,
                exc,
            )


class ActivationContext:
    """Concrete context whose registrations can be committed or discarded."""

    def __init__(self, manager, record, initial_settings):
        self.commands = StagedCommandRegistry(record.id)
        self.tasks = PluginTaskServiceImpl(manager, record)
        self.settings = StagedPluginSettings(
            manager, record.id, initial_settings)
        self.documents = StagedDocumentService(manager, record)
        self.diagnostics = PluginDiagnosticService(manager, record)
        self._closed = False

    def commit(self):
        if self._closed:
            raise RuntimeError("activation context is closed")
        self.commands.close()
        self.settings.commit()
        self.documents.commit()
        self.tasks.commit()

    def close(self):
        if self._closed:
            return
        self.tasks.shutdown()
        self.documents.close()
        self.settings.close()
        self.commands.close()
        self._closed = True


__all__ = [
    "ActivationContext",
    "PluginTaskServiceImpl",
    "StagedCommandRegistry",
    "StagedDocumentService",
    "StagedPluginSettings",
    "validate_json_value",
]
