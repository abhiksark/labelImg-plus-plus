# Plugin authoring guide

labelImg++ API-major-1 plugins are normal Python distributions installed into
the same environment as the application. The host discovers them through
Python package entry points, keeps new plugins disabled, and loads code only
after the user enables the plugin and restarts labelImg++.

> Plugins are trusted in-process code, not sandboxed extensions. Enabling one
> grants it the same filesystem, network, process, and Python access as
> labelImg++. Review its publisher, source, version, homepage, and entry-point
> reference, and install plugins in a dedicated virtual environment.

## Create the distribution

Use a separate project; do not place plugin source inside the labelImg++
checkout:

```text
review-plugin/
├── pyproject.toml
└── src/
    └── labelimgpp_review/
        └── __init__.py
```

`pyproject.toml` declares one zero-argument factory in the canonical entry-point
group:

```toml
[build-system]
requires = ["setuptools>=61", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "labelimgpp-review-plugin"
version = "0.1.0"
requires-python = ">=3.8"
dependencies = ["labelimgplusplus>=4,<6"]

[project.entry-points."labelimgplusplus.plugins"]
"com.example.review" = "labelimgpp_review:create_plugin"

[tool.setuptools.packages.find]
where = ["src"]
```

A plugin that uses only `labelimgplusplus.plugins` may keep a Python 3.8 floor
and run on both the PyQt5-based 4.0.0rc0 host and PyQt6-based 4.0.0rc1 or later
hosts. Stable labelImg++ 4 requires Python 3.10. Cross-host plugins must not
import PyQt5, PyQt6, or internal `libs.*` modules. If a plugin intentionally
uses Qt UI internals, it is not covered by API major 1 and cannot be
cross-host compatible.

The entry-point name is the canonical plugin ID. It must exactly match
`PluginMetadata.id`, be globally unique, and contain only lowercase letters,
digits, dots, underscores, and hyphens. Reverse-domain IDs are recommended.

## Register a command

The public API is `labelimgplusplus.plugins`; modules under `libs.*` are
internal and are not a compatibility contract.

```python
from labelimgplusplus.plugins import (
    CommandSpec,
    PluginCapability,
    PluginMetadata,
)


class ReviewPlugin:
    metadata = PluginMetadata(
        id="com.example.review",
        display_name="Example Review",
        version="0.1.0",
        api_major=1,
        capabilities=(PluginCapability.COMMANDS,),
        description="Run a read-only review of the active document.",
        homepage="https://example.com/labelimgpp-review",
    )

    def activate(self, context):
        self.context = context
        context.commands.register(CommandSpec(
            id="run",
            title="Run Example Review",
            description="Analyze the active image or video project",
            default_shortcut="Ctrl+Alt+R",
            callback=self.run,
            enabled=lambda document: document.kind in ("image", "video"),
        ))

    def deactivate(self):
        pass

    def run(self):
        document = self.context.documents.current
        self.context.diagnostics.report(
            "review_started",
            "Review started for %s" % document.source_path,
            severity="info",
        )


def create_plugin():
    return ReviewPlugin()
```

The host creates the `QAction`, owns its lifetime, places it in the Plugins
menu, invokes the callback on `QApplication.thread()`, and exposes it to the
shortcut editor as `plugin.com.example.review.run`. Plugins never receive the
action, menu, MainWindow, Canvas, Shape, or another mutable application object.

Activation and deactivation are synchronous and must be lightweight.
Activation is registration-only: attempting to start a task from `activate()`
rejects the activation. If any registration or activation step fails, all
staged commands, settings writes, and document subscriptions are discarded.

## Store settings

Settings are isolated automatically by plugin ID:

```python
threshold = self.context.settings.get("threshold", 0.8)
self.context.settings.set("threshold", 0.9)
self.context.settings.delete("obsolete")
```

Values must be strict JSON: `None`, booleans, finite numbers, strings, lists,
and dictionaries with string keys. Tuples, arbitrary Python objects, cycles,
NaN/infinity, and a `__type__` key at any nesting level are rejected. Reads
return copies and `as_dict()` returns a read-only snapshot.

Writes made during activation are staged. Once active, successful writes are
persisted immediately under `plugins.config.<plugin-id>` in the existing
settings file. Configuration for an uninstalled plugin is retained until the
user chooses **Forget Unavailable Plugin**.

## Run background work

Capture immutable/plain inputs on the GUI thread and submit heavy work after
activation, normally from a command callback:

```python
def run(self):
    document = self.context.documents.current
    source_path = document.source_path

    def work(handle):
        handle.check_cancelled()
        result = analyze_file(source_path)
        handle.report_progress(100)
        handle.check_cancelled()
        return result

    self.context.tasks.submit(
        work,
        key="review",
        latest=True,
        on_progress=self.show_progress,
        on_result=self.show_result,
        on_error=self.show_error,
    )
```

Plugin task keys are host-namespaced. `latest=True` cooperatively cancels the
previous task with the same local key. The host also cancels plugin work on a
document-generation change and plugin shutdown, and discards stale results.
The submitter and worker receive the same plain `PluginTaskHandle` facade; it
does not expose Qt signals, a `QObject` parent, coordinator metadata, or an
atomic non-cancellable phase. The host detaches it from internal work after
completion or shutdown.

Worker functions must call `check_cancelled()` around expensive steps. It
raises `concurrent.futures.CancelledError`, so use that standard exception if
worker-local cleanup is needed:

```python
from concurrent.futures import CancelledError

try:
    handle.check_cancelled()
    result = analyze_file(source_path)
except CancelledError:
    release_worker_resources()
    raise
```

Result, error, and progress callbacks run on the GUI thread and are converted
to diagnostics if they raise. A worker exception skips `on_result`, passes its
message to `on_error`, and records a `task_failed` diagnostic with the complete
formatted worker traceback in `details`.

Workers may return immutable/plain values or detached `QImage` values. They
must not create `QPixmap`, widgets, `QAction`, or mutable Shape/Canvas/video
objects, and must not use unmanaged global thread pools for host-integrated
work.

Diagnostic `code`, `message`, `details`, and `severity` values must all be
strings, and `code` and `severity` must be non-empty. Invalid diagnostic
reporting during activation rolls back the complete activation transaction;
invalid reporting from a command, document, or task callback is contained as a
normal callback diagnostic.

## Observe documents

`context.documents.current` is a frozen `DocumentDescriptor`. Subscribe when
the plugin needs updates:

```python
self.unsubscribe = context.documents.subscribe(self.document_changed)
```

The descriptor contains `kind`, `source_path`, `project_path`, `generation`,
`revision`, `dirty`, and `read_only`. A subscription receives descriptors, not
live models or widgets. Subscriptions are staged during activation and removed
automatically at shutdown; the returned callable can remove one earlier.

## Install and test locally

Use the same virtual environment for the host and plugin:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install labelimgplusplus
python -m pip install -e ./review-plugin
labelimgpp
```

On Windows, activate with `.venv\Scripts\activate`. Open **Tools → Plugins…**,
review the provider and entry-point reference, enable the plugin, close the
application cleanly, and restart it. Enable/disable changes never hot-load or
hot-unload code in API major 1.

For automated tests, build a wheel and install it into a clean environment.
Test disabled discovery without importing the plugin module, enabled
activation, command execution, callback failures, generation changes,
cooperative cancellation, and repeated shutdown.

## Recover from a broken plugin

Start without discovery or loading:

```bash
LABELIMGPP_DISABLE_PLUGINS=1 labelimgpp
```

On Windows PowerShell:

```powershell
$env:LABELIMGPP_DISABLE_PLUGINS = "1"
labelimgpp
```

Then uninstall or repair the distribution. Safe mode does not reset plugin
configuration, shortcuts, application settings, or image/video project data.
See [Troubleshooting](../reference/troubleshooting.md#plugins).

## Scope of API major 1

API major 1 initially supports commands, JSON settings, restricted background
tasks, read-only document descriptors, and diagnostics. It does not provide a
marketplace, automatic installation, signing, permissions, sandboxing, hot
reload, plugin dependency resolution, or native-crash containment.

The PyQt5-to-PyQt6 host migration does not change API major 1 because every
public descriptor and protocol remains standard-library-only. A plugin loaded
into labelImg++ 5 must not import PyQt5 into the PyQt6 process.

Custom annotation tools belong to issue #27 and format/import/export adapters
belong to issue #28. Until those APIs land, such changes remain source
contributions rather than external plugins.
