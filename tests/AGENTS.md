# Test Instructions

## Scope

This file governs tests and fixtures under `tests/`. It extends the repository-wide instructions in the root `AGENTS.md`.

## Commands

- Run all commands from the repository root.
- While iterating, run `python3 -m pytest path/to/test_file.py -v`.
- For video coverage, install `pip install '.[video]' pytest`, then run `python3 -m pytest tests/video -v`.
- For SAM coverage, install `pip install '.[sam]' pytest`, then run:

```bash
python3 -m pytest \
  tests/integrations \
  tests/integration/test_sam_controller.py \
  tests/integration/test_sam_mainwindow.py \
  tests/widgets/test_canvas_sam.py \
  tests/widgets/test_sam_settings_dialog.py \
  tests/utils/test_sam_constants.py \
  -v
```

- For changes crossing SAM and video, install `pip install '.[sam,video]' pytest`, then run:

```bash
python3 -m pytest \
  tests/video \
  tests/integrations \
  tests/integration/test_sam_controller.py \
  tests/integration/test_sam_mainwindow.py \
  tests/widgets/test_canvas_sam.py \
  tests/widgets/test_sam_settings_dialog.py \
  tests/utils/test_sam_constants.py \
  -v
```

## Placement and dependencies

- Put base-installed MainWindow and workflow tests in `tests/integration/`.
- Put tests for optional modules under `libs/integrations/` in `tests/integrations/`.
- Put video-extra tests in `tests/video/`.
- Call `pytest.importorskip()` before importing a module that pulls an optional dependency.
- Separate optional-dependency tests from stdlib-only tests; a module-level skip discards the entire test file.
- Add new plugin compatibility tests to the explicit `plugin-test` file list in `.github/workflows/ci.yaml`.
- Reuse `tests/video/conftest.py::make_video`; do not commit video clips as fixtures.

## Completion

- Run the closest affected file while iterating, then the owning optional-feature suite when applicable. The root completion gates still apply.
