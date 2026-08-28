# Screenshots

## Assist lifecycle acceptance 2026-08-25

`assist-lifecycle-2026-08-25/` contains the controlled production-Qt matrix
for setup, explicit download/cancel, typed failures, ready/running/preview,
post-accept Track Forward, and closed-Assist states. Every required state is a
full-window PNG at exact 800x600 and 1366x768 dimensions. The post-accept state
is produced through a real task-local video model with one accepted manual
anchor and timeline marker; it does not inject Track Forward availability. The
directory also retains four native computer-use JPEGs from the supplied-video
pass: preview, accepted manual anchor, explicit propagation running, and
pending review.

The matching acceptance record distinguishes controlled exact-size captures
from native live evidence and records the real provider manifest, source-file
integrity, accessibility names, focus behavior, and test gates:
[`docs/testing/assist-lifecycle-acceptance.md`](../testing/assist-lifecycle-acceptance.md).
The raw timestamped native provider cancel/no-retry/retry record is retained in
[`provider-cancel-retry-transcript.md`](assist-lifecycle-2026-08-25/provider-cancel-retry-transcript.md).

## Video workspace supplied-file acceptance 2026-08-24

`video-workspace-2026-08-24/` contains the 32-state video acceptance matrix at
800x600, 960x640, 1366x768, and 1440x900. The eight states are paused,
playing, invalid time, compact Track menu, propagation progress, pending
review, missing-runtime setup, and shutdown timeout.

The matching acceptance record identifies the computer-use captures and the
deterministic real-Qt surrogates, with source-video metadata, accessibility
observations, exact dimensions, and SHA-256 hashes:
[`docs/testing/video-workspace-acceptance.md`](../testing/video-workspace-acceptance.md).

## Continuous image workflow 2026-08-24

`continuous-workflow-2026-08-24/` is the deterministic offscreen Qt
acceptance matrix for the choose-once, draw-twice, continuously saved image
workflow. Regenerate it with:

```bash
QT_QPA_PLATFORM=offscreen QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 \
  python tools/ux/capture_workspace_matrix.py
```

Every scenario is captured in light and dark themes at 800x600, 960x640,
1366x768, and 1440x900. The exact artifacts are:

- Empty workspace:
  `empty-workspace-light-800x600.png`,
  `empty-workspace-dark-800x600.png`,
  `empty-workspace-light-960x640.png`,
  `empty-workspace-dark-960x640.png`,
  `empty-workspace-light-1366x768.png`,
  `empty-workspace-dark-1366x768.png`,
  `empty-workspace-light-1440x900.png`, and
  `empty-workspace-dark-1440x900.png`.
- First image fitted to the canvas:
  `first-image-fit-light-800x600.png`,
  `first-image-fit-dark-800x600.png`,
  `first-image-fit-light-960x640.png`,
  `first-image-fit-dark-960x640.png`,
  `first-image-fit-light-1366x768.png`,
  `first-image-fit-dark-1366x768.png`,
  `first-image-fit-light-1440x900.png`, and
  `first-image-fit-dark-1440x900.png`.
- Two committed rectangles with Rectangle still active:
  `two-rectangles-light-800x600.png`,
  `two-rectangles-dark-800x600.png`,
  `two-rectangles-light-960x640.png`,
  `two-rectangles-dark-960x640.png`,
  `two-rectangles-light-1366x768.png`,
  `two-rectangles-dark-1366x768.png`,
  `two-rectangles-light-1440x900.png`, and
  `two-rectangles-dark-1440x900.png`.
- Inspector open:
  `inspector-open-light-800x600.png`,
  `inspector-open-dark-800x600.png`,
  `inspector-open-light-960x640.png`,
  `inspector-open-dark-960x640.png`,
  `inspector-open-light-1366x768.png`,
  `inspector-open-dark-1366x768.png`,
  `inspector-open-light-1440x900.png`, and
  `inspector-open-dark-1440x900.png`.
- Inspector closed:
  `inspector-closed-light-800x600.png`,
  `inspector-closed-dark-800x600.png`,
  `inspector-closed-light-960x640.png`,
  `inspector-closed-dark-960x640.png`,
  `inspector-closed-light-1366x768.png`,
  `inspector-closed-dark-1366x768.png`,
  `inspector-closed-light-1440x900.png`, and
  `inspector-closed-dark-1440x900.png`.
- Saving:
  `saving-light-800x600.png`, `saving-dark-800x600.png`,
  `saving-light-960x640.png`, `saving-dark-960x640.png`,
  `saving-light-1366x768.png`, `saving-dark-1366x768.png`,
  `saving-light-1440x900.png`, and `saving-dark-1440x900.png`.
- Saved:
  `saved-light-800x600.png`, `saved-dark-800x600.png`,
  `saved-light-960x640.png`, `saved-dark-960x640.png`,
  `saved-light-1366x768.png`, `saved-dark-1366x768.png`,
  `saved-light-1440x900.png`, and `saved-dark-1440x900.png`.
- Save failed:
  `save-failed-light-800x600.png`,
  `save-failed-dark-800x600.png`,
  `save-failed-light-960x640.png`,
  `save-failed-dark-960x640.png`,
  `save-failed-light-1366x768.png`,
  `save-failed-dark-1366x768.png`,
  `save-failed-light-1440x900.png`, and
  `save-failed-dark-1440x900.png`.

The harness verifies all 64 PNGs are non-empty and match the dimensions in
their filenames. The matching acceptance record is
[`docs/testing/ux-remediation-2026-08-23.md`](../testing/ux-remediation-2026-08-23.md#continuous-image-workflow-acceptance--2026-08-24).

## UX remediation 2026-08-23

`ux-remediation-2026-08-23/` is the macOS release-review matrix for the
annotation UX remediation. It contains four full-window states in light and
dark themes at 1366x768 and 1440x900:

- `canvas-unselected-polygon-*` shows a fitted image and a readable unselected
  polygon edge.
- `verified-image-*` shows the persistent Verified command and status chip.
- `full-gallery-*` shows 150px thumbnails, the interaction hint, the status
  legend, and dataset statistics.
- `empty-after-close-*` shows the atomic close reset with no stale document,
  gallery, tool rail, verification chip, or status message.

The matching verification record is
[`docs/testing/ux-remediation-2026-08-23.md`](../testing/ux-remediation-2026-08-23.md).
The capture harness also exercised a four-point polygon and inline keyboard
class confirmation at both target sizes; the saved Pascal VOC XML contained
four points with no consecutive duplicates.

## Deterministic workspace matrix harness

`tools/ux/capture_workspace_matrix.py` is the single 1x offscreen-Qt harness
for the workspace review matrix. It writes files as
`<scenario>-<theme>-<width>x<height>.png` and rejects unknown scenarios,
themes, and sizes rather than silently producing mislabeled evidence.

Run it with:

```bash
QT_QPA_PLATFORM=offscreen QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 \
  python tools/ux/capture_workspace_matrix.py
```

The registry has 18 states: the existing empty, fit, rectangle, inspector,
Saving, Saved, and save-failed image states; video paused, playing, invalid
time, Track menu, and pending propagation; Assist setup, download, failure,
and preview; plus shutdown timeout. Each is captured at 800x600, 960x640,
1366x768, and 1440x900 in light and dark themes, for **144 PNGs**.

The harness projects real MainWindow, timeline, AssistState/AssistPanel,
canvas-preview, continuous-save, and shutdown-surface owners. It uses only
small in-memory video frames and explicit lifecycle values where a network
provider, downloaded model, decoder, or long worker would otherwise be
nondeterministic; it neither opens nor changes supplied source media.

Each capture applies its requested theme only while it creates the PNG, then
restores the window's prior theme. A setup or PNG-write failure releases the
harness-owned save, menu, Assist, shutdown, and loading projections without
cancelling application workers.

## Workspace 3.2

`workspace-3.2-balanced/` contains the accepted browser-lab contract for the
Balanced workspace at 1366x768 and 1440x900. Dense and Canvas-first remain
archived comparison studies in the interactive prototype and are not runtime
themes.

`workspace-3.2-tool-rail/` contains fixed Linux/offscreen Qt captures of the
first runtime slice in light and dark mode at both approval sizes. The legacy
docks are intentionally still present in this slice; the fixed-inspector PR
replaces them next.

`workspace-3.2-fixed-inspector/` contains fixed Linux/offscreen Qt captures of
the Objects/Files inspector in light, dark, and collapsed states at 1366x768
and 1440x900. The existing annotation and file projections are reparented into
the fixed panel; the collapsed captures retain the accessible reopen control
at the right edge of the canvas.

`workspace-3.2-unified-inspector/` contains fixed Linux/offscreen Qt captures
of the unified searchable object projection in light and dark mode at both
approval sizes. Rectangle and polygon rows share one list, with no nested
annotation tabs; video tests separately cover track rows that are absent from
the current frame.

`workspace-3.2-final/` is the final Balanced workspace acceptance matrix. It
contains Empty, Image, embedded Gallery, Video, collapsed-inspector,
read-only/disabled, dark-mode, and true 2x-DPI image states at 1366x768 and
1440x900. The matrix verifies that the rail, command bar, inspector, compact
canvas controls, integrated timeline, and slim status strip remain in the
single main window with no docks or detached gallery.

## Workspace 3.3

`workspace-3.3-inline-picker/` contains fixed Linux Qt captures of the
provisional geometry and non-modal class picker in light and dark mode. The
1x captures use the 1366x768 and 1440x900 approval sizes; the matching HiDPI
captures retain those logical sizes and are stored at 2732x1536 and 2880x1800
physical pixels. The empty Objects projection demonstrates that provisional
geometry is not canonical until class confirmation.

`workspace-3.3-sam-output-mode/` contains the matching light/dark and 1x/2x
matrix for Smart Select's contextual Box/Polygon selector. The control appears
only while Smart Select is active, retains the fixed canvas chrome height, and
leaves all primary workspace controls unclipped at both approval sizes.

## Workspace 3.4

`workspace-3.4-propagation/` contains fixed Linux Qt captures of the portable
whole-video propagation preview at 1366x768 and 1440x900. Rectangle, polygon,
and associated keypoint previews are painted separately from canonical model
geometry while the integrated timeline reports processed frames, active and
completed objects, ETA, gap/failure count, and the accessible Cancel action.

## Workspace 3.5

`workspace-3.5-sam2-settings/` contains the fixed Linux light/dark and 1x/2x
matrix for the combined Smart Select and whole-video propagation settings.
The captures verify that backend choice, local checkpoint/config paths, the
no-bundle explanation, and all dialog actions remain readable and unclipped at
1366x768 and 1440x900 logical sizes.

This directory contains screenshots demonstrating various features of labelImg++.

## Required Screenshots

### Dark Mode Feature

#### `light-mode.png`
**Description:** Main application window in light theme showing:
- Main toolbar with icons on the left
- Image canvas in the center with sample annotations
- Label list panel on the right
- Gallery thumbnails at the bottom (if visible)
- Status bar at the bottom
- At least 2-3 bounding boxes with labels visible

**How to capture:**
1. Launch labelImgPlusPlus
2. Open a sample image with annotations
3. Ensure View > Dark Mode is unchecked (light theme active)
4. Take a full window screenshot
5. Save as `light-mode.png` (PNG format, recommended size: 1920x1080 or similar)

#### `dark-mode.png`
**Description:** Main application window in dark theme showing:
- Same view as light-mode.png but with dark theme active
- Main toolbar with dark background
- Dark gray canvas background
- Dark-themed panels and controls
- Same annotations visible for comparison
- Status bar in dark theme

**How to capture:**
1. With the same image and annotations as light-mode screenshot
2. Press Ctrl+Shift+T or select View > Dark Mode to enable dark theme
3. Take a full window screenshot
4. Save as `dark-mode.png` (PNG format, recommended size: 1920x1080 or similar)

## Screenshot Guidelines

- **Resolution:** Use the feature's fixed review matrix when specified;
  otherwise prefer 1920x1080 or higher for documentation
- **Format:** PNG (lossless) preferred
- **Content:** Show meaningful sample images with multiple bounding boxes
- **Annotations:** Use diverse labels (e.g., "person", "car", "dog") to demonstrate the feature
- **Window State:** Full window capture, not cropped
- **Clean State:** No error messages or temporary UI elements
- **Consistency:** Use the same sample image for light/dark comparison

## Adding More Screenshots

When adding new feature screenshots:
1. Create descriptive filename (e.g., `gallery-mode.png`, `label-dialog.png`)
2. Add entry to this README with description and capture instructions
3. Reference in relevant documentation markdown files
4. Use consistent resolution and quality

## Workspace 3.2 command-bar review

The `workspace-3.2-command-bar/` directory contains the fixed Linux visual
review set for the first modern-workspace slice. Each empty, image, gallery,
video, and disabled-action state is captured at both 1366×768 and 1440×900 at
96 DPI. Review the set for:

- a single 44 px application row below the native OS title bar;
- no native File/Edit/View menu row;
- visible application, Open, document, navigation, Save, Verify, format, and
  overflow controls without clipping;
- consistent document names, positions, and disabled action styling; and
- unchanged canvas, annotation, gallery, and video behavior below the row.

High-DPI full-window review joins the next 3.2 slice: the legacy text-under-icon
toolbar still sets a window minimum taller than 768 px at 2× scaling and is the
component that slice replaces. Collapsed-inspector review begins with the fixed
inspector slice.

## Alternative: Placeholder Images

Until actual screenshots are captured, the documentation uses placeholder references. The application is fully functional, and users can see the actual themes by using the feature.

## Continuous annotation release evidence — 2026-08-27

[`continuous-annotation-release-2026-08-24/`](continuous-annotation-release-2026-08-24/)
is the final deterministic full-window matrix: 18 named states at 800×600,
960×640, 1366×768, and 1440×900 in light and dark themes, for exactly 144
PNGs. The real capture CLI completed twice in isolated settings environments
(19s and 18s); the sorted per-file manifests were byte-identical. Every image
is nonempty and matches its 1× named dimensions.

[`SHA256SUMS`](continuous-annotation-release-2026-08-24/SHA256SUMS) lists the
144 sorted PNG basenames and SHA-256 digests. Its own SHA-256 is
`0c2a2ba62822711628694334bdad44940fd3886e2592b9b18c0f9ed36b5aea9d`.
Visual review confirmed all five actual Track-menu actions in light/dark
800×600 and 1440×900 captures, plus an elided pending-propagation summary
with transport, Legend, and Track still visible at 800×600.

The matching release record, including automated results, source-media
fingerprints, prepared task-local copies, and the explicitly pending
Mac-locked native rows, is
[`docs/testing/continuous-annotation-release-matrix.md`](../testing/continuous-annotation-release-matrix.md).
