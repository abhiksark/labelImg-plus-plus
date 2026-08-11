# Testing Plan

## Current State

The ordinary suite covers the format readers/writers, collision-safe dataset
resolver, task coordinator priority/cancellation/generation behavior, shared
JSON indexing, frame-cache invalidation, gallery scheduling, canvas geometry,
SAM orchestration, bulk tools, and asynchronous MainWindow flows. Timing is
deliberately excluded from hosted CI; `docs/performance.md` defines the fixed
Linux workstation gate and its deterministic 10k corpora.

### Existing tests

- `tests/test_commands.py`: unit tests for undo/redo command system (`libs/commands.py`)
- `tests/test_io.py`: Pascal VOC + CreateML I/O smoke tests (`libs/pascal_voc_io.py`, `libs/create_ml_io.py`)
- `tests/core/test_settings.py`: isolated JSON settings persistence (`libs/core/settings.py`)
- `tests/test_utils.py`: basic utilities (`libs/utils.py`)
- `tests/test_stringBundle.py`: i18n bundle loading (`libs/stringBundle.py`)
- `tests/test_qt.py`: Qt app boot (currently a no-op test)

### CI behavior

- GitHub Actions workflow: `.github/workflows/ci.yaml`
- Installs `pytest` and runs `pytest tests/ -v` across Python 3.8–3.13.
- Runs focused `[video]` jobs across Python 3.8–3.13, combined `[sam,video]`
  jobs on Python 3.8 and 3.13, and decoder/persistence smoke tests on Windows
  and macOS.
- Base jobs import the application without PyAV, NumPy, or OpenCV to preserve
  the optional-dependency boundary.

### Smart-video coverage

`tests/video/` covers PyAV dependency markers, PTS and VFR seeking, rotation,
MP4/MOV/MKV/AVI decoding, corrupt media, source fingerprints, SQLite schema and
revision behavior, track precedence/interpolation, frame-aware editing,
tracking and review, cache/navigation behavior, export formats and atomic
staging, CLI/project opening, and Qt GUI-thread boundaries.

Temporary smoke workloads cover CFR, VFR, short/long GOP, rotation, reduced
4K/8K navigation analogues, and optical-flow stress. Timing remains excluded
from hosted CI; the full-resolution, five-run acceptance gate is local and is
documented in `docs/performance.md`.

### Stability / isolation risks

- Settings tests replace the default path with isolated temporary JSON files.
- `tests/test_stringBundle.py` assumes `LC_ALL` and `LANG` exist in the environment
- `tests/test_io.py` writes into the repository under `tests/` instead of a temporary directory

## Performance correctness gates

- Resolver tests use call counts and collision corpora instead of wall-clock
  thresholds to enforce linear work in hosted CI.
- Qt integration tests cover latest-request-wins navigation, failed loads,
  revision-aware saves, delete/reset/shutdown, both gallery surfaces, and SAM
  image changes.
- `QImage` may be produced by workers, while `QPixmap`, `Shape`, and all widget
  mutation are asserted at the application-thread boundary.
- The workstation profiler performs one warm-up and five measured runs and
  emits `summary.json`, `trace.json`, `resources.csv`, cProfile output, a
  comparison report, and optionally a py-spy flamegraph.
- The plugin qualification profiler can be executed directly by file path
  from any working directory. From the repository root, run:

  ```bash
  repository_root=$(pwd)
  (cd /tmp && python "$repository_root/tools/performance/profile_plugins.py" \
    --runs 5 --assert-budgets)
  ```

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
