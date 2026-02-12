# Testing Plan

## Current State

### Existing tests

- `tests/test_commands.py`: unit tests for undo/redo command system (`libs/commands.py`)
- `tests/test_io.py`: Pascal VOC + CreateML I/O smoke tests (`libs/pascal_voc_io.py`, `libs/create_ml_io.py`)
- `tests/test_settings.py`: basic settings persistence (`libs/settings.py`)
- `tests/test_utils.py`: basic utilities (`libs/utils.py`)
- `tests/test_stringBundle.py`: i18n bundle loading (`libs/stringBundle.py`)
- `tests/test_qt.py`: Qt app boot (currently a no-op test)

### CI behavior

- GitHub Actions workflow: `.github/workflows/ci.yaml`
- Installs `pytest` and runs `pytest tests/ -v`, but currently uses `|| true` which means CI passes even when tests fail.

### Stability / isolation risks

- `tests/test_settings.py` writes to `~/.labelImgSettings.pkl` (can pollute machines and create flaky tests)
- `tests/test_stringBundle.py` assumes `LC_ALL` and `LANG` exist in the environment
- `tests/test_io.py` writes into the repository under `tests/` instead of a temporary directory

## Coverage Gaps

### High-value untested logic

- YOLO format I/O: `libs/yolo_io.py` (writer/reader, class list handling, coordinate conversion)
- Label format orchestration and bounding box conversion: `libs/labelFile.py`
- Gallery mode / thumbnail annotation parsing and lookup: `libs/galleryWidget.py`
- Canvas interaction logic: `libs/canvas.py` (mouse events, selection, moving, draw-square, panning)
- Toolbar / DPI scaling and expand/collapse state: `libs/toolBar.py`

## Roadmap

### Phase 0: Make tests enforceable and stable

- Update CI to fail on test failures (remove `|| true`)
- Install package-under-test for CI and local testing (avoid `sys.path` hacks)
- Run Qt tests headlessly in CI (e.g. `QT_QPA_PLATFORM=offscreen` or `xvfb-run`)
- Refactor existing tests to use temp dirs / temp files:
  - `Settings.path` should be redirected to a temp file during tests
  - environment variables in `test_stringBundle.py` should be set/restored safely
  - IO tests should write outputs to temp dirs

### Phase 1: Unit tests for core format logic

- `libs/yolo_io.py`
  - Writer math: center/width/height normalization correctness
  - `classes.txt` generation and stable ordering
  - Reader conversion: normalized -> pixel coordinates, clamping, missing classes file behavior
- `libs/labelFile.py`
  - `convert_points_to_bnd_box()` edge cases (floats, point ordering, clamp to 1)
  - End-to-end save flows (Pascal/YOLO/CreateML) using temp filesystem artifacts

### Phase 2: Gallery mode logic tests (non-UI focused)

- `libs/galleryWidget.py`
  - `find_annotation_file()` search order and return values
  - `parse_voc_annotations()` normalization correctness
  - `parse_yolo_annotations()` class mapping and parsing robustness
  - `ThumbnailCache` eviction and access-order correctness

### Phase 3: Qt integration / smoke tests (selective)

- Use a Qt-aware test runner (recommended: `pytest-qt`) for reliable widget lifecycle handling
- Smoke tests:
  - `get_main_app()` boots and shuts down cleanly
  - Minimal flows that should not crash:
    - load image
    - toggle gallery mode
    - create a box
    - move a box
    - undo/redo integration around create/move/delete

## Tooling Recommendations

- Standardize on `pytest` (it can run existing `unittest` tests)
- Add coverage reporting (`pytest-cov`) and start tracking module coverage for `libs/` and `labelImgPlusPlus.py`
- Introduce a small number of higher-level integration tests, but keep most tests at the unit level for speed and determinism
