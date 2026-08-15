# Widget Instructions

## Scope

This file governs canvas widgets, workspace chrome, galleries, dialogs, and video views under `libs/widgets/`. It extends the repository-wide instructions in the root `AGENTS.md`.

## Workspace contracts

- For persistent workspace chrome, extend `WorkspaceSplitterShell`, `WorkspacePages`, or `WorkspaceInspector`; do not introduce a `QDockWidget` or a second toolbar.
- Bind command controls to the existing MainWindow-owned `QAction` with `setDefaultAction()`. Do not copy enabled, checked, text, icon, or shortcut state into widget-owned state.

## Theme and DPI

- Add semantic colors to both `LIGHT_COLORS` and `DARK_COLORS` in `libs/utils/styles.py`; do not add color literals to widgets.
- For self-styled widgets, set an object name, enable `WA_StyledBackground`, implement `apply_theme()`, and ensure the active theme reaches it through its owner or `MainWindow._apply_theme()`.
- Theme lazily created dialogs from their caller before showing them.
- Define dimensions in logical pixels and call `scale_px()` at construction or use time. Do not freeze scaled values at module import.

## Canvas changes

- Keep unclassified geometry in `canvas.provisional_shape`; do not append it to `canvas.shapes` before class confirmation.
- Geometry mutations must emit the appropriate pre-mutation undo signal and update the spatial index with `reindex_shape()` or `rebuild_spatial_index()`.
- New canvas modes must perform the cleanup and conditional `modeChanged` emission used by `set_sam_mode()`.

## Validation

- Run the closest file under `tests/widgets/` and any affected test under `tests/integration/`.
- For theme changes, run `python3 -m pytest tests/ -k theme -v` and inspect the affected flow in light and dark themes at 1x and 2x scaling.
- Before theme testing, read `docs/testing/theme-testing.md`.
