# Repository Agent Instructions

## Scope

This file governs the entire repository. Nested `AGENTS.md` files add rules for the public plugin API, annotation formats, widgets, and tests.

- Treat this `AGENTS.md` hierarchy as local workspace policy. Do not stage or commit these files unless the user explicitly requests it.
- Run repository commands from the repository root. Some tests open `pyproject.toml` relative to the current directory.
- Keep production code compatible with Python 3.8 through 3.13.

## Core commands

- Install base and test dependencies with `pip install -r requirements/requirements-linux-python3.txt pytest`.
- Run the application with `python3 labelImgPlusPlus.py`.
- During iteration, run the closest test with `QT_QPA_PLATFORM=offscreen python3 -m pytest path/to/test_file.py -v`.
- Before finishing a base change, run `make test`.
- There is no repository lint, formatter, or type-check command. Do not invent or report one as a required gate.
- Do not run `make clean` for routine cleanup; it deletes `~/.labelImgSettings.json` as well as build outputs.

## Runtime and data-safety contracts

- Keep base startup free of optional feature imports. Load PyAV, NumPy, OpenCV, ONNX Runtime, Torch, torchvision, and SAM 2 only inside operations that require them. The only current module-level heavy adapters are `libs/integrations/image_convert.py` and `libs/integrations/mask_to_polygon.py`, and their callers import them lazily.
- Route new production background work through the MainWindow-owned `TaskCoordinator` using the existing `interactive`, `background`, `sam`, or serialized `video` lane. Existing standalone pools in compatibility/test fallbacks are not patterns to copy.
- Submit and cancel coordinator work on the GUI thread. Use `latest=True` with a stable namespaced key when only the newest request is valid.
- Workers may return immutable/plain records and detached `QImage` values. Create `QPixmap` and `Shape` objects and mutate widgets or models only on the GUI thread.
- Reject stale asynchronous results before mutation. Recheck every applicable request ID, generation, document/media fingerprint, stream/time base, and model or document revision.
- Shut down plugins and plugin-owned tasks before shutting down the shared coordinator.
- Push annotation mutations through the existing `Command`/`UndoStack` path, then mark the document dirty. Push video mutations through `VideoModelCommand` and `_on_video_model_mutation()`.
- Route new production asynchronous image-annotation writes through immutable `SaveRequest` plus `write_save_request()`. Do not copy the synchronous compatibility save path or weaken the temp-file, fsync, commit-fence, and `os.replace` publication path.
- Mark an image clean or navigate after save only when that exact image and document revision are still current.
- Canvas geometry is display-space. Convert through `_image_scale_factor` before persistence or export; do not write `canvas.shapes` coordinates directly.

## Compatibility boundaries

- Treat `labelimgplusplus/` as the shipped public plugin API and `libs/` as internal. Read `labelimgplusplus/AGENTS.md` before changing the public package.
- Do not import `MainWindow` from `libs/core` or construct or mutate widgets there off the GUI thread.
- Preserve existing QAction and shortcut identities. UI wrappers must reuse host-owned actions rather than create parallel state.
- Keep plugin activation transactional. On failure, restore staged settings, run host cleanup rollback, close the activation context, and call `deactivate()`.
- Keep plugin settings strict untagged JSON and reject the reserved `__type__` key at any depth.
- Address video frames by stream PTS plus time base, never by inferred frame index. Preserve source fingerprint, stream, and time-base fences through requests, caches, seeks, and manifests.
- New tracking or SAM 2 worker output must use `source='tracker'`, `review_state='pending'`, and `anchor=False`. Human acceptance does not promote it to an interpolation anchor, and export continues to exclude pending and rejected suggestions.
- Treat `*.labelimgpp.sqlite` as a versioned transactional format. Any schema change requires a `SCHEMA_VERSION` bump and a transactional migration; preserve read-only fallback on migration failure.
- Keep optional dependency markers in `pyproject.toml` aligned with `tests/video/test_compatibility.py`; that test intentionally asserts exact PyAV markers, two OpenCV entries, and no packaged Torch or SAM 2 dependency.

## Generated files and release metadata

- Do not edit `libs/resources.py` directly. Edit `resources.qrc` or its source asset, run `make qt5py3`, then run `python3 scripts/verify_qt_resources.py`; keep source and generated output together.
- Add every new `get_str()` key to `resources/strings/strings.properties` before rebuilding resources.
- Keep release versions synchronized in `pyproject.toml`, `libs/__init__.py`, `setup.cfg`, and `labelimgplusplus.egg-info/PKG-INFO`.
- Treat `build-tools/build-for-pypi.sh` as a destructive manual-release script: it removes tracked egg metadata before rebuilding and can upload interactively.

## Validation

- For plugin API or host changes, run the explicit gate in `labelimgplusplus/AGENTS.md`; for SAM, video, or combined-feature changes, run the corresponding suite in `tests/AGENTS.md`. Also run `make test`.
- Check the base import boundary with `QT_QPA_PLATFORM=offscreen python3 -c "import sys, labelImgPlusPlus; assert not {'av', 'cv2', 'numpy', 'onnxruntime', 'torch', 'torchvision', 'sam2'} & sys.modules.keys()"`.
- After resource changes, regenerate and run `python3 scripts/verify_qt_resources.py`.
- After version or packaging changes, run `python3 -m pytest tests/test_release_consistency.py tests/video/test_compatibility.py -v`. For a distribution build, install `build` and `twine`, then run `python3 -m build` and `twine check dist/*`.
- For UI changes, run affected widget and integration tests and inspect the real flow in light and dark themes at 1x and 2x scaling.
- Leave the full supported-Python matrix and Windows/macOS video smoke to CI unless those environments are available locally.

## Git and delivery

- Branch `feature/*`, `fix/*`, and `chore/*` work from `dev` and target pull requests to `dev`. Do not follow the obsolete `develop` references in `CONTRIBUTING.rst`.
- Use Conventional Commit subjects in the form `type(scope): lowercase imperative`.
- Do not add AI-tool attribution, `Co-Authored-By` trailers, or tool branding to commits or pull-request text.
- Squash-merge feature, fix, and chore pull requests into `dev` after required checks and review approval; refresh `dev` before starting dependent work.
- Preserve unrelated working-tree changes and stage only the intended implementation files.
- For releases, read `build-tools/README.md` and `.github/workflows/ci.yaml`; a release tag must match the package version and point to a commit already on `origin/master`.

## Read before changing

- Before changing async runtime, plugin hosting, or video pipelines, read the runtime sections at the start of `docs/architecture.md`; verify later legacy diagrams against current code.
- Before changing Smart Video behavior, read `docs/features/smart-video-annotation.md` for workflow context and use current code and tests as the behavioral authority.
- Before changing SAM behavior or dependencies, read `docs/features/sam-assisted-polygon.md` and `docs/guides/optional-dependencies.md`.
