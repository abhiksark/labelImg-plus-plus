"""Public, Qt-free plugin API for labelImg++.

Plugins are trusted, installed Python packages.  These interfaces deliberately
expose descriptors and host-owned services instead of application internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Optional, Protocol, Tuple


PLUGIN_API_MAJOR = 1


class PluginCapability(str, Enum):
    """Capabilities understood by the current plugin host."""

    COMMANDS = "commands"


@dataclass(frozen=True)
class PluginMetadata:
    """Identity and compatibility information declared by a plugin."""

    id: str
    display_name: str
    version: str
    api_major: int
    capabilities: Tuple[PluginCapability, ...]
    description: str = ""
    homepage: str = ""


@dataclass(frozen=True)
class PluginDiagnostic:
    """A structured plugin failure or warning suitable for display."""

    plugin_id: str
    phase: str
    code: str
    message: str
    details: str = ""
    severity: str = "error"


@dataclass(frozen=True)
class DocumentDescriptor:
    """Immutable summary of the active document."""

    kind: str = "none"
    source_path: Optional[str] = None
    project_path: Optional[str] = None
    generation: int = 0
    revision: int = 0
    dirty: bool = False
    read_only: bool = True


@dataclass(frozen=True)
class CommandSpec:
    """A plugin-local command registered as a host-owned action."""

    id: str
    title: str
    callback: Callable[[], None]
    description: str = ""
    default_shortcut: str = ""
    enabled: Optional[Callable[[DocumentDescriptor], bool]] = None


class CommandRegistry(Protocol):
    """Transactional registry for commands declared during activation."""

    def register(self, command: CommandSpec) -> str:
        """Stage *command* and return its host namespaced identifier."""


class PluginTaskHandle(Protocol):
    """Cooperative cancellation and progress surface passed to task work."""

    def cancel(self) -> None: ...

    def is_cancelled(self) -> bool: ...

    def check_cancelled(self) -> None: ...

    def report_progress(self, value: Any) -> None: ...


class PluginTaskService(Protocol):
    """Restricted access to the host's background worker lane."""

    def submit(
        self,
        work: Callable[[PluginTaskHandle], Any],
        key: Optional[str] = None,
        latest: bool = False,
        on_result: Optional[Callable[[Any], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_progress: Optional[Callable[[Any], None]] = None,
    ) -> PluginTaskHandle: ...


class PluginSettings(Protocol):
    """JSON-only settings isolated to one plugin ID."""

    def get(self, key: str, default: Any = None) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...

    def as_dict(self) -> Mapping[str, Any]: ...


class ReadOnlyDocumentService(Protocol):
    """Read and subscribe to immutable active-document descriptors."""

    @property
    def current(self) -> DocumentDescriptor: ...

    def subscribe(
        self, callback: Callable[[DocumentDescriptor], None]
    ) -> Callable[[], None]: ...


class PluginDiagnostics(Protocol):
    """Plugin-scoped diagnostic reporting service."""

    def report(
        self,
        code: str,
        message: str,
        details: str = "",
        severity: str = "error",
    ) -> None: ...


class PluginContext(Protocol):
    """Services available while a plugin is active."""

    commands: CommandRegistry
    tasks: PluginTaskService
    settings: PluginSettings
    documents: ReadOnlyDocumentService
    diagnostics: PluginDiagnostics


class Plugin(Protocol):
    """Object returned by a plugin's zero-argument factory."""

    metadata: PluginMetadata

    def activate(self, context: PluginContext) -> None: ...

    def deactivate(self) -> None: ...


__all__ = [
    "PLUGIN_API_MAJOR",
    "CommandRegistry",
    "CommandSpec",
    "DocumentDescriptor",
    "Plugin",
    "PluginCapability",
    "PluginContext",
    "PluginDiagnostic",
    "PluginDiagnostics",
    "PluginMetadata",
    "PluginSettings",
    "PluginTaskHandle",
    "PluginTaskService",
    "ReadOnlyDocumentService",
]
