# Public Plugin API Instructions

## Scope

This file governs the shipped public package under `labelimgplusplus/`. It extends the repository-wide instructions in the root `AGENTS.md`.

## Contracts

- Treat `labelimgplusplus/plugins.py` as a third-party compatibility boundary; `libs/**` remains internal and is not a plugin contract.
- Keep this package standard-library-only. Do not import PyQt, `libs`, or optional runtime dependencies here.
- Preserve compatibility within the current `PLUGIN_API_MAJOR` through additive changes. Do not remove, rename, or change existing public fields, protocols, or semantics without an explicitly approved `PLUGIN_API_MAJOR` bump.
- Keep the entry-point name equal to `PluginMetadata.id`.
- Preserve command identities as `plugin.<plugin-id>.<command-id>` because they are persisted in shortcut settings.
- Keep exposed document records immutable and host services narrow; do not expose `MainWindow`, widgets, `QAction`, `Shape`, or internal job handles.
- Before changing the contract, read `docs/reference/plugin-api-v1.md` and `docs/guides/plugin-authoring.md`.

## Validation

Run the explicit plugin CI gate from the repository root:

```bash
pip install wheel
QT_QPA_PLATFORM=offscreen python3 -m pytest \
  tests/core/test_plugin_discovery.py \
  tests/core/test_plugin_manager.py \
  tests/core/test_shortcut_config.py \
  tests/integration/test_plugins.py \
  tests/integration/test_plugin_packaging.py \
  tests/integration/test_plugin_performance.py \
  -v
```

Also run the base-startup optional-import check from the root `AGENTS.md`.
