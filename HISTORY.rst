History
=======

3.2.0 (2026-08-11)
------------------

Workspace release replacing the legacy toolbar-and-dock layout with the
Balanced modern annotation workspace. Existing annotation formats, filenames,
command-line entry points, plugin APIs, document methods, shortcut identifiers,
and Python 3.8 through 3.13 support remain compatible.

Balanced Workspace
~~~~~~~~~~~~~~~~~~

* Replace the legacy toolbar with a fixed 52-logical-pixel tool rail for
  Select, Bounding Box, Polygon, Smart Select, and Keypoints. The rail binds
  directly to the existing authoritative actions, reflects their live enabled
  and checked states, and always shows configured shortcuts in its tooltips.
* Add a responsive 44-logical-pixel command bar and compact action-backed
  canvas controls for zoom, fit modes, 100 percent scale, and annotation
  visibility.
* Replace the floating right docks with a fixed, collapsible Objects/Files
  inspector. Its validated width, selected tab, and collapsed state persist
  independently while obsolete dock and toolbar settings remain serialized for
  downgrade compatibility.
* Embed Empty, Canvas, and Gallery pages in the central workspace. Gallery Mode
  no longer opens a detached maximized window, and the video timeline now sits
  directly beneath the canvas instead of in a dock.
* Add an Empty page with existing recent paths and direct image, folder, and
  video entry points. Exactly one supported local file or directory can also be
  opened by drag and drop; rejected drops leave the current document unchanged.
* Keep the native status bar alive as a hidden compatibility message bus while
  mirroring saved, dirty, read-only, dimensions, object count, progress,
  warning, active-tool, shortcut, and zoom state into a slim visible strip.

Unified Annotation Inspector
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Replace the nested Rectangle, Polygon, and Track tabs with one model-backed,
  searchable object list. Image rows represent canonical canvas shapes; video
  rows represent stable track identifiers, including tracks absent from the
  current frame.
* Synchronize canvas and inspector selection with guarded identity updates and
  route contextual class, difficult, color, keypoint, span, keyframe, and
  pending-review edits through undoable model mutations.
* Keep annotation geometry owned exclusively by the canvas and video model,
  preserve ``label_list`` as a compatibility alias, and retain legacy pending
  video observations and their accept/reject workflow.

Visual and Compatibility Qualification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Vendor only the five required official Feather SVGs and their MIT license in
  Qt resources; Smart Select now defaults to ``S`` under the existing
  ``sam_mode`` shortcut identifier.
* Preserve the hidden legacy status-bar API, settings round-tripping, plugin
  snapshots, and GUI-thread boundaries while removing all runtime floating
  docks, detached Gallery windows, nested annotation tabs, and text-under-icon
  toolbar presentation.
* Qualify Empty, Image, Gallery, Video, collapsed-inspector, read-only, dark,
  and true 2x-DPI states at 1366x768 and 1440x900, alongside structural Qt,
  settings, selection, undo, plugin, SAM, and video coverage.

3.1.0 (2026-08-11)
------------------

Feature release adding smart video annotation, direct Ultralytics dataset
export, a versioned installed-plugin platform, and a bounded asynchronous
runtime for responsive work on large datasets. Python 3.8 through 3.13 remain
supported, and existing image formats, annotation naming, command entry points,
and synchronous extension-facing methods remain compatible.

Highlights
~~~~~~~~~~

* Add optional smart video annotation for MP4, MOV, MKV, and AVI sources with
  exact presentation-timestamp navigation, rectangle keyframes and
  interpolation, reviewable optical-flow propagation, project persistence,
  verified-frame tracking, and export to all five annotation formats.
* Export image datasets directly to an Ultralytics-ready YOLO detection layout
  with deterministic train/validation/test splits, copy or absolute-symlink
  modes, validated class mappings, and transactional publication.
* Add API-major-1 installed Python plugins with PyPA entry-point discovery,
  transactional activation, host-owned commands and shortcuts, JSON-only
  settings, bounded generation-scoped tasks, read-only document descriptors,
  structured diagnostics, a restart-oriented manager, and safe-mode recovery.

Runtime and Performance
~~~~~~~~~~~~~~~~~~~~~~~

* Add bounded interactive, background, and dedicated SAM task lanes plus a
  dataset index, progressive annotation catalog, fingerprinted image-load
  cache, and cached shared annotation documents.
* Route navigation, prefetch, gallery loading, annotation status, durable
  saves, bulk dataset operations, and SAM work through generation-aware or
  revision-aware asynchronous paths while preserving synchronous compatibility
  methods.
* Cache canvas geometry, bound frame and gallery memory, add opt-in local trace
  recording, and publish reproducible five-run profiling and teardown gates for
  real 4K/8K images and 10,000-image datasets.

Plugin Hardening
~~~~~~~~~~~~~~~~

* Keep new and disabled plugins import-free, preserve unavailable
  configuration until explicitly forgotten, and document that enabled plugins
  are trusted in-process code rather than sandboxed extensions.
* Qualify a separately installed fixture wheel on Python 3.8 through 3.13 and
  add five-run startup, 100-entry discovery/manager, cancellation, and teardown
  gates.
* Restrict plugin tasks to a plain cancellation/progress facade, preserve
  worker tracebacks through GUI-thread error delivery, validate diagnostic
  fields transactionally, and render malformed diagnostics defensively.
* Apply empty shortcut values to active plugin actions after reset/import and
  make the plugin qualification profiler runnable directly from outside the
  repository.

Compatibility and Release Engineering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* Keep the base installation free of video and plugin-only dependencies.
  ``[video]`` is an optional, Python-version-pinned PyAV/OpenCV extra, while
  ``[sam]`` remains independently installable and both extras can be combined.
* Package the stable ``labelimgplusplus`` public namespace alongside ``libs``
  and test a separately built fixture distribution so entry-point discovery is
  qualified from installed metadata rather than the source tree.
* Exercise ordinary, plugin, and video behavior across Python 3.8 through 3.13,
  SAM and combined SAM/video paths on the oldest and newest supported Python,
  safe-mode import isolation, PyInstaller base-only boot, wheel/sdist contents,
  and five-run performance, cancellation, and teardown budgets.

3.0.0 (2026-08-09)
------------------

Stable release of the 3.0 line. It carries the SAM-assisted annotation work
introduced in the alpha and RC0 format fixes into a production release, while
hardening annotation paths, save operations, gallery refreshes, dataset tools,
and packaging. Python 3.8 through 3.13 are supported.

Highlights
~~~~~~~~~~

* **SAM-assisted polygons** — click an object to trace a polygon with
  MobileSAM on ONNX Runtime. The optional ``[sam]`` extra remains isolated
  from core installs, downloads a checksum-verified model pair on first use,
  and requires neither PyTorch nor Git dependencies.
* **Five annotation formats** — PASCAL VOC, YOLO bounding boxes, CreateML,
  COCO, and YOLO-seg are available in one workflow, including polygon
  previews in both gallery surfaces and COCO keypoint preservation.
* **Dataset utilities** — the train/validation/test splitter now keeps image
  and annotation pairs collision-safe and deterministic, and the Vertex AI
  CSV exporter validates malformed input and reports actionable failures.

Fixes Since RC0
~~~~~~~~~~~~~~~

* Fix the Gallery Mode status filter (#97). **Annotated** includes verified
  images, **Verified** includes only verified images, and **Unannotated**
  includes only images without labels. The filter now applies to the dock and
  full-screen galleries, survives reloads, waits for asynchronous status
  results, and re-evaluates thumbnails after save and verification changes.
* Prevent recursively discovered same-stem images from overwriting one
  another in a flat annotation directory. Every member of a real collision
  receives a deterministic image-specific sidecar name; non-colliding images
  keep the historical basename.
* Prefer collision-specific annotations over stale legacy sidecars throughout
  loading, status probing, gallery previews, batch verification, autosave,
  label checking, and dataset splitting.
* Render bounding boxes and polygons correctly in gallery thumbnails for all
  supported formats, select the intended image in shared COCO/CreateML JSON,
  and prevent stale thumbnail workers from replacing refreshed overlays.
* Preserve an existing YOLO ``classes.txt`` index map, reject malformed
  coordinates safely, retain COCO keys and keypoints correctly, and convert
  polygons to enclosing boxes consistently when a target format requires it.
* Propagate cancelled or failed saves instead of reporting success, delete the
  intended image only after explicit confirmation, avoid changing state on a
  failed delete, and guard Reset All against recursive settings callbacks.
* Refresh docked and full-screen gallery status and overlays only after a
  successful persistence operation.
* Make dataset-split output names deterministic and collision-safe across
  image and annotation extensions without overwriting existing output.
* Replace the CSV exporter's implicit pandas behavior with a dependency-free,
  validated 11-column Vertex AI exporter and honor its requested output path.
* Package the generated Qt resource module so installed wheels can start and
  load icons and translated strings without a source checkout.
* Make the project test commands and CI preserve pytest's real exit status.

Compatibility Notes
~~~~~~~~~~~~~~~~~~~

* Existing legacy ``<image-stem>.xml``, ``.txt``, and ``.json`` sidecars
  remain readable. Collision-specific names are created only when recursive
  same-stem images need distinct files, and remain stable once created.
* Core installation remains ``pip install labelimgplusplus``. SAM stays
  opt-in with ``pip install labelimgplusplus[sam]``.
* The **Label Checker** is intentionally read-only in 3.0.0: it scans,
  suggests, and exports reports, but its automatic repair action remains
  disabled because annotation rewriting is not implemented safely yet.

Release Engineering
~~~~~~~~~~~~~~~~~~~

* Test core behavior on Python 3.8 through 3.13 and the focused ``[sam]``
  dependency path on Python 3.8 and 3.13.
* Validate that release tags match the package version and point to a commit on
  ``master``; build and Twine-check the wheel and sdist once, wait for Linux,
  macOS, and Windows packaging, then publish those exact artifacts through
  PyPI Trusted Publishing.

3.0.0rc0 (2026-06-18)
---------------------

Release candidate for the 3.0 line. Annotation-format I/O bug fixes ahead of
the stable 3.0.0; the ``[sam]`` feature from 3.0.0a0 is unchanged.

Bug Fixes
~~~~~~~~~

* **COCO** — read crowd/RLE annotations without crashing (they now fall back
  to the bounding box) and keep keypoints on polygon annotations through a
  full read/write round-trip.
* **Label colors** — fix the color hash, which collapsed the 256-bit SHA-256
  to a lossy float and clustered label colors; the channels are well
  distributed again.
* **YOLO** — parse annotation lines separated by tabs or multiple spaces
  instead of discarding them as malformed.

3.0.0a0 (2026-06-11)
--------------------

First alpha of the 3.0 line, introducing the project's first AI-assisted
labeling feature. This is a pre-release for testing the new ``[sam]`` extra
across platforms — install it with ``pip install --pre labelimgplusplus``.
The core tool is unchanged for existing users.

New Features
~~~~~~~~~~~~

* **SAM-assisted polygons** — toggle **SAM Segment**, click an object, and a
  polygon annotation is traced from a Segment-Anything mask. Runs MobileSAM on
  ONNX Runtime (CPU-friendly, ~70 MB optional extra, no PyTorch). The model
  pair is auto-downloaded on first use and verified against pinned SHA256
  checksums. Point **Tools → SAM Settings…** at your own exported
  encoder/decoder ``.onnx`` pair to use a different SAM variant. Without the
  extra installed, the action stays disabled with an install hint and nothing
  else changes.

Notes
~~~~~

* The ``[sam]`` extra pulls ``onnxruntime``, ``numpy``, and
  ``opencv-python-headless`` from PyPI — no PyTorch, no Git dependencies.
* ONNX models are protobuf data, not pickled code, so loading one cannot
  execute arbitrary code on load.

2.4.1 (2026-06-09)
------------------

Documentation and discoverability release. Adds an animated demo to the README
and improves how the project is found and presented. No functional changes —
the application behaves identically to 2.4.0.

Documentation
~~~~~~~~~~~~~

* Add an animated demo GIF to the README showcasing the core workflow —
  gallery mode, bounding boxes, dark theme, polygons, face keypoints, and save
* Refresh project metadata for discoverability (description, topics, homepage)

2.4.0 (2026-06-09)
------------------

HiDPI scaling release. The interface now scales consistently on high-density
and fractionally-scaled displays: chrome, dialogs, stylesheets, and the canvas
grab tolerance all grow by the same factor that already drove icon sizing.
Backward compatible — every change is a no-op at the standard 96 DPI baseline,
so non-HiDPI displays are unchanged.

New features
~~~~~~~~~~~~

* Scale the full UI for HiDPI displays from a single DPI factor (#66) —
  dialog and dock minimum sizes, status-bar labels, keypoint-panel
  indicators, gallery preset controls, the collapsible toolbar, every
  stylesheet padding/margin/border/font-size value, and the canvas
  hit-test radius

Bug fixes
~~~~~~~~~

* Fix a ``ModuleNotFoundError`` crash when selecting the "Auto" toolbar icon
  size — the handler imported from a stale ``libs.toolBar`` path (#93)

Internal
~~~~~~~~

* Add ``libs/utils/dpi.py`` as the single source of truth for screen scaling
  (``get_dpi_scale_factor`` + ``scale_px``); chrome and stylesheets now scale
  through it instead of recomputing DPI per site

2.3.3 (2026-06-09)
------------------

Security, correctness, and reliability release. Hardens settings storage and
annotation parsing against untrusted input, closes several undo/redo gaps, and
decomposes the monolithic main window into focused, unit-tested modules. No new
features and no breaking changes.

Security
~~~~~~~~

* Store user settings as JSON instead of a Python pickle, removing an
  arbitrary-code-execution vector (the old ``~/.labelImgSettings.pkl`` is no
  longer read; settings start fresh on upgrade)
* Harden the PASCAL VOC XML reader against entity-expansion (billion-laughs)
  and external-entity / network (XXE) attacks

Bug fixes
~~~~~~~~~

* Make whole-shape moves, rectangle resizes, arrow-key nudges, the
  context-menu "Move here", and in-mode keypoint Ctrl-Z all undoable — these
  mutations previously bypassed the undo stack (#68)
* Defer the annotation-format switch until the reader succeeds for the YOLO and
  PASCAL VOC loaders, so a malformed file no longer flips the saved format;
  PASCAL VOC now reports parse errors gracefully instead of crashing (#69)
* Stop PASCAL VOC bounding-box coordinate data loss on save (round rather than
  truncate), and round polygon coordinates likewise
* Harden the COCO, YOLO-seg, and CreateML readers against malformed input
* Report a clear error instead of crashing when an annotation file is opened
  as an image
* Restore label-list ordering on delete and refresh the label combo on edit so
  undo/redo stays consistent
* Surface batch-verify failures instead of silently swallowing them
* Validate imported shortcut configurations instead of crashing on bad input
* Deep-copy points in ``Shape.copy()`` and preserve a ``None`` label
* Correct the label-fix status message and make "Reset All" relaunch through
  the Python interpreter so installed entry points restart correctly
* Theme the gallery regardless of the thumbnail-size slider, and source the
  keypoint-panel and shortcuts-dialog colors from the active palette
* Zoom-scale the keypoint hit-test and cache the canvas overlay composite

Packaging
~~~~~~~~~

* Ship the default class list inside the installed wheel
* Require Python >= 3.8 and drop dead Py2 / Qt4 shims

Internal
~~~~~~~~

* Decompose the ~3,700-line ``MainWindow``: extract annotation loading,
  fit-to-window scaling, the statistics controller, the gallery
  status-refresh controller, and the format-metadata registry into focused,
  unit-tested modules
* Unify annotation status / label probing across the gallery and stats views
* Run the CI test matrix on the ``dev`` branch and cache pip
* Add a real mouse-event polygon insert/drag/undo integration test (#70);
  the full suite now runs 592 tests (up from 471)

2.3.2 (2026-05-20)
------------------

Patch release hardening the annotation format loaders against malformed
input. Slightly corrupt or hand-edited label files previously crashed the
load or silently dropped valid annotations.

* Skip individual malformed YOLO lines instead of discarding the whole
  file — a line with non-numeric values no longer raises an error that
  drops every annotation in that file
* Report corrupt CreateML JSON through an error dialog instead of
  silently loading zero annotations, and defer the format switch until
  the reader succeeds so a bad file no longer flips the saved format
* Fix the CreateML branch of label extraction, which passed the wrong
  number of constructor arguments and could never return labels
* Replace a mutable default argument in the YOLO writer that could leak
  class names across files and corrupt class indices in ``classes.txt``
* Guard ``load_predefined_classes`` against a missing class-file path

Internal: tolerate a PyQt5/coverage shutdown segfault in CI, ignore
coverage and local working-directory artifacts, and add 8 regression
tests (full suite now 471 passing).


2.3.1 (2026-05-14)
------------------

Patch release fixing five blocker-tier issues identified in the v2.3.0 review.

* Restore Ctrl-Z for polygon vertex insert, vertex delete, vertex drag-move, and
  keypoint placement — these previously silently undid the prior rectangle action
* Clear polygon/keypoint mode state when loading a new file, preventing
  stale-reference crashes after switching images mid-annotation
* Exit keypoint mode safely when the active keypoint shape is deleted
* Defer format switch in COCO and YOLO-seg loaders until the reader succeeds,
  so a malformed annotation file no longer silently flips the saved format
* Clamp YOLO-seg normalized coordinates to ``[0.0, 1.0]`` to prevent
  out-of-range values when a vertex is dragged past the image edge


2.3.0 (2026-03-27)
------------------

* Add polygon annotation support with dual-mode tool system (#2)
* Add click-to-place polygon drawing with vertex-by-vertex placement (#2)
* Add freehand polygon drawing with Douglas-Peucker simplification (Shift+drag) (#2)
* Add full polygon vertex editing: move, insert via midpoints, right-click delete (#2)
* Add COCO JSON format reader/writer with polygon segmentation support (#2)
* Add YOLO-seg format reader/writer for normalized polygon coordinates (#2)
* Extend Pascal VOC XML format with polygon element support (#2)
* Add tabbed label list separating Rectangles and Polygons (#2)
* Add polygon degradation warning when saving to bbox-only formats (#2)
* Add configurable polygon tool shortcut (default: P) (#2)
* Add COCO 17-point human pose keypoint annotation (#15)
* Add hybrid sequential/free keypoint placement workflow (#15)
* Add skeleton visualization with colored bones on canvas (#15)
* Add inline keypoint checklist panel in sidebar (#15)
* Add COCO JSON keypoint export with skeleton definition (#15)
* Add 5-point face landmark annotation template (#15)
* Add keypoint template registry for extensible annotation types (#15)


2.2.0 (2026-03-05)
------------------

* Add Clear Recent Files option to File > Open Recent menu (#14)
* Add Review Lock: prevent editing verified images via View > Lock on Verify (#22)
* Add Batch Verify/Unverify dialog under Tools menu (#22)
* Add status filter (All/Annotated/Verified/Unannotated) to file list (#22)
* Add Snap to Grid overlay with configurable grid size (8/16/32/64px) (#18)
* Add Edge Alignment mode with visual guide lines (#18)
* Add customizable keyboard shortcuts with full editor dialog (#8)
* Add shortcut export/import as JSON files (#8)
* Add Dataset Splitting tool with train/val/test ratios (#21)
* Add stratified split option for balanced class distribution (#21)
* Add split manifest JSON generation for reproducibility (#21)


2.1.1 (2026-02-05)
------------------

* Rename command from ``labelImgPlusPlus`` to ``labelimgpp`` and ``labelimgplusplus``
* Add deprecation warning for old ``labelImgPlusPlus`` command (still works for backwards compatibility)
* Update all documentation to reference new command names


2.1.0b (2026-02-05)
-------------------

* Add Dark Mode theme support with Ctrl+Shift+T toggle (Beta Release)
* Add 13 new theme-aware color keys to Settings
* Fix hardcoded colors in canvas, gallery widget, and dialogs
* Add hex_to_qcolor() utility function for color handling
* Add comprehensive theme documentation (docs/features/dark-mode.md)
* Add theme integration tests (tests/test_theme.py)
* Fix keyboard shortcut conflicts
* Improve gallery widget styling for both light and dark themes


2.0.1 (2025-01-22)
------------------

* Update all references to labelImgPlusPlus
* Add PyPI and CI badges to README
* Update build-tools for labelImgPlusPlus
* Update Chinese and Japanese translations
* Add comprehensive developer documentation


2.0.0 (2025-01-22)
------------------

* Rebrand to labelImg++
* Add Gallery Mode - full-screen thumbnail browser with Ctrl+G
* Thumbnails show annotation status (gray/blue/green borders)
* Adjustable thumbnail size slider (40px - 300px)
* Modernize packaging with pyproject.toml
* Add GitHub Actions CI/CD with PyPI trusted publishing
* Update dependencies to latest versions


1.8.6 (2021-10-10)
------------------

* Display box width and height


1.8.5 (2021-04-11)
------------------

* Merged a couple of PRs
* Fixed issues
* Support CreateML format


1.8.4 (2020-11-04)
------------------

* Merged a couple of PRs
* Fixed issues

1.8.2 (2018-12-02)
------------------

* Fix pip depolyment issue


1.8.1 (2018-12-02)
------------------

* Fix issues
* Support zh-Tw strings


1.8.0 (2018-10-21)
------------------

* Support drawing sqaure rect
* Add item single click slot
* Fix issues

1.7.0 (2018-05-18)
------------------

* Support YOLO
* Fix minor issues


1.6.1 (2018-04-17)
------------------

* Fix issue

1.6.0 (2018-01-29)
------------------

* Add more pre-defined labels
* Show cursor pose in status bar
* Fix minor issues

1.5.2 (2017-10-24)
------------------

* Assign different colors to different lablels

1.5.1 (2017-9-27)
------------------

* Show a autosaving dialog

1.5.0 (2017-9-14)
------------------

* Fix the issues
* Add feature: Draw a box easier


1.4.3 (2017-08-09)
------------------

* Refactor setting
* Fix the issues


1.4.0 (2017-07-07)
------------------

* Add feature: auto saving
* Add feature: single class mode
* Fix the issues

1.3.4 (2017-07-07)
------------------

* Fix issues and improve zoom-in

1.3.3 (2017-05-31)
------------------

* Fix issues

1.3.2 (2017-05-18)
------------------

* Fix issues


1.3.1 (2017-05-11)
------------------

* Fix issues

1.3.0 (2017-04-22)
------------------

* Fix issues
* Add difficult tag
* Create new files for pypi

1.2.3 (2017-04-22)
------------------

* Fix issues

1.2.2 (2017-01-09)
------------------

* Fix issues
