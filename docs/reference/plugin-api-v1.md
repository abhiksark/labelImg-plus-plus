# Plugin API major 1 reference

Import the stable API from `labelimgplusplus.plugins`. Importing this module is
standard-library-only and does not import Qt, NumPy, OpenCV, PyAV, SAM, Canvas,
Shape, or MainWindow.

```python
from labelimgplusplus.plugins import PLUGIN_API_MAJOR

assert PLUGIN_API_MAJOR == 1
```

## Discovery and identity

- Entry-point group: `labelimgplusplus.plugins`
- Entry-point value: a zero-argument `create_plugin()` factory
- Canonical ID: the entry-point name, exactly equal to `PluginMetadata.id`
- Allowed ID characters: lowercase letters, digits, dots, underscores, hyphens
- Activation order: deterministic normalized-ID order
- Duplicate IDs: every conflicting candidate is disabled
- Disabled plugins: distribution metadata is read, target modules are not
  imported
- Safe mode: `LABELIMGPP_DISABLE_PLUGINS=1` skips discovery and loading

Production discovery uses `importlib.metadata` and supports both the legacy
Python 3.8/3.9 collection shapes and selectable Python 3.10–3.13 collections.

## Frozen descriptors

### `PluginMetadata`

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Canonical globally unique ID |
| `display_name` | `str` | User-facing name |
| `version` | `str` | Plugin API/content version |
| `api_major` | `int` | Exactly one required plugin API major |
| `capabilities` | `tuple[PluginCapability, ...]` | Declared host capabilities |
| `description` | `str` | Optional summary |
| `homepage` | `str` | Optional publisher/source page |

### `PluginDiagnostic`

Structured diagnostics contain `plugin_id`, `phase`, `code`, `message`,
`details`, and `severity`. The manager preserves tracebacks in `details` for
load, lifecycle, task, and callback failures.

### `DocumentDescriptor`

| Field | Meaning |
|---|---|
| `kind` | `none`, `image`, or `video` |
| `source_path` | Active image/video path, if any |
| `project_path` | Video project path, if any |
| `generation` | Changes when the published document identity changes |
| `revision` | Current document content revision |
| `dirty` | Whether the active document has unsaved changes |
| `read_only` | Whether host mutation is unavailable |

### `CommandSpec`

`CommandSpec(id, title, callback, description="", default_shortcut="",
enabled=None)` declares a plugin-local command. The optional `enabled`
predicate receives the current frozen `DocumentDescriptor`. The host-visible
ID and shortcut key are `plugin.<plugin-id>.<command-id>`.

## Capabilities

`PluginCapability.COMMANDS` is the only initial capability. Unknown or
unsupported required capabilities make the plugin incompatible. Issue #27 may
add annotation-tool descriptors and issue #28 may add format/import/export
descriptors only through backward-compatible additions or a later API major.

## Lifecycle protocols

The entry-point factory returns a `Plugin` with `metadata`,
`activate(context)`, and `deactivate()`. The host calls activation on the GUI
thread after core widgets, actions, menus, Settings, and TaskCoordinator exist,
but before a queued startup document opens.

Activation may register commands, settings changes, and document
subscriptions. Those changes commit atomically after `activate()` returns.
Tasks cannot start during activation. An import, factory, metadata,
registration, or activation failure discards the staged transaction and does
not stop base startup.

Shutdown stops new task submissions, cancels plugin handles, deactivates active
plugins in reverse order, removes subscriptions and host-owned actions, then
continues TaskCoordinator shutdown. One deactivation failure does not block the
remaining plugins. Repeated shutdown is safe.

## `PluginContext` services

### `commands`

`register(CommandSpec) -> str` stages one command and returns its namespaced
host ID. Duplicate local or host IDs reject the complete activation.

### `tasks`

```python
submit(
    work,
    key=None,
    latest=False,
    on_result=None,
    on_error=None,
    on_progress=None,
) -> PluginTaskHandle
```

Work runs on the existing bounded background lane and receives a handle with
`cancel()`, `is_cancelled()`, `check_cancelled()`, and
`report_progress(value)`. Callbacks return to the GUI thread. Keys are
plugin-namespaced; results from an old generation or shutting-down plugin are
discarded.

### `settings`

`get(key, default=None)`, `set(key, value)`, `delete(key)`, and `as_dict()`
operate only on the active plugin's JSON object. Values are copied, validated
recursively, and may not contain `__type__` keys. Configuration remains after
the distribution disappears until explicitly forgotten.

### `documents`

`current` returns the latest `DocumentDescriptor`.
`subscribe(callback) -> unsubscribe` stages a descriptor subscription.
Document publications occur at successful image/video commits, dirty/revision
changes, resets, and close transitions.

### `diagnostics`

`report(code, message, details="", severity="error")` adds a plugin-scoped
diagnostic visible in **Tools → Plugins…**.

## Thread and trust contract

Plugin code is trusted and executes in-process. The API reduces accidental
coupling; it does not restrict Python or operating-system access and is not a
sandbox.

The host owns all widgets, `QAction`, `QPixmap`, Canvas, Shape, selection,
timeline, track state, undo/dirty state, and document mutation. Worker inputs
and outputs must be detached plain/immutable data or detached `QImage` values.
Plugin callbacks and every host UI mutation run on `QApplication.thread()`.

## Compatibility and deprecation policy

- Additive fields, protocols, methods, or capabilities may be introduced
  within API major 1 when existing plugins continue to work.
- Breaking signature, lifecycle, identity, or semantic changes require a new
  API major.
- A future major will be documented with a migration guide and a deprecation
  period before support for the previous major is removed.
- The application version and plugin API major are independent.
- Nothing under `libs.*`, nor any MainWindow/Canvas/Shape attribute, becomes
  public through plugin availability.
