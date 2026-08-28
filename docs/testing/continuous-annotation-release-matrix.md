# Continuous annotation release matrix — 2026-08-27

## Evidence status

This is the completed Task 6 release record for the reviewed source and test
implementation through `68bdb97` (`fix: elide compact video progress`). The
complete final gate and focused automated evidence were recorded in `5aae186`;
the native computer-use matrix was completed on 2026-08-27 against real UI
flows and task-local copies of the supplied media.

The reviewed change sequence begins at `86c82e9` (settings compatibility) and
includes the accessibility, recovery, matrix, soak, collection, Track-menu,
and compact-progress commits through `68bdb97`. Nothing in this record changes
source media, normal user settings, or the application.

## Runtime provenance

| Item | Observed value |
| --- | --- |
| Host | macOS 26.5.2 (25F84), arm64 |
| Python | 3.9.21 |
| Qt binding/runtime | PyQt 5.15.11 / Qt 5.15.14 |
| Video runtime | PyAV 15.1.0 |
| Base ONNX Runtime | Not installed. Native Assist validation used ONNX Runtime 1.19.2 installed only in `/tmp/labelimgpp-native-release.r5PJWB/assist-runtime`; the normal Python environment was not changed. |
| Final automated collection | 1,449 nodes; node-only LF SHA-256 `fc2d162e1a14fade632255f66014e4f06d87046b288e83cdcece8c1acd19ab7f` |

## Automated release evidence

The subsystem counts below are the recorded fresh-process Task 6 evidence.
The video command used the stable exhaustive per-file partition rather than
the known pathological monolithic aggregate.

| Scope | Result | Duration / evidence boundary |
| --- | --- | --- |
| Annotation workflow, continuous save, and view transform | **14 passed** | 0.13s |
| Video suite, exhaustive stable partition | **208 passed** | Recorded as the 208-node Task 6 partition; no aggregate wall-clock value was retained in the final summary. |
| Assist state/cache/panel/flow | **55 passed** | 8.72s |
| Responsive workspace, recovery, and worker soak | **35 passed** | 36.12s |
| Complete base gate at reviewed `9832250` | **1,440 passed, 3 skipped** | 3,970.89s (1:06:10) |
| Complete final gate at reviewed `68bdb97` | **1,446 passed, 3 skipped** | 4,138.25s (1:08:58) |
| Optional video + SAM gate | **215 passed, 1 legitimate optional skip** | Fresh bounded partitions. |
| Final-delta Track-menu harness | **28 passed** | Covers real popup-menu capture after the complete gate. |
| Final-delta timeline suite | **40 passed** | Covers compact progress elision after the complete gate. |
| Final-delta timeline/tracking/responsive/accessibility/theme selection | **95 passed** | 28.19s |

The earlier complete gate is deliberately attributed to `9832250` for
chronology. The complete final gate directly covers the later `520d71d` and
`68bdb97` deltas; the focused gates remain as targeted diagnostic evidence.

## Deterministic screenshot evidence

[`docs/screenshots/continuous-annotation-release-2026-08-24/`](../screenshots/continuous-annotation-release-2026-08-24/)
contains exactly 144 full-window PNGs: 18 named scenarios × four logical
sizes (800×600, 960×640, 1366×768, 1440×900) × light/dark themes. Filenames
are stable as `<scenario>-<theme>-<width>x<height>.png`; every image was
verified non-empty and at its named 1× logical size.

The real CLI (`tools/ux/capture_workspace_matrix.py`) completed with exit 0 in
19 seconds. A second isolated run completed with exit 0 in 18 seconds at
`/tmp/labelimgpp-evidence-repeat-DE7Ynj`; its sorted per-file SHA-256 manifest
was byte-identical to the release directory. The release manifest is
[`SHA256SUMS`](../screenshots/continuous-annotation-release-2026-08-24/SHA256SUMS)
(144 sorted `SHA-256  basename` lines), whose SHA-256 is
`0c2a2ba62822711628694334bdad44940fd3886e2592b9b18c0f9ed36b5aea9d`.

Visual review confirmed the five real Track-menu actions — **Track all
anchors**, **Track selected object**, **Accept propagated results**, **Reject
propagated results**, and **Cancel** — in each light/dark 800×600 and
1440×900 artifact. The light/dark 800×600 pending-propagation artifacts show
a typographic right ellipsis while Previous, Play/Pause, Next, exact time,
speed, Legend, and Track remain visible.

Representative artifacts:

- [light Track menu, 800×600](../screenshots/continuous-annotation-release-2026-08-24/video-track-menu-light-800x600.png)
- [dark Track menu, 1440×900](../screenshots/continuous-annotation-release-2026-08-24/video-track-menu-dark-1440x900.png)
- [light pending propagation, 800×600](../screenshots/continuous-annotation-release-2026-08-24/video-propagation-pending-light-800x600.png)
- [dark pending propagation, 800×600](../screenshots/continuous-annotation-release-2026-08-24/video-propagation-pending-dark-800x600.png)

The deterministic harness uses real MainWindow, timeline, Assist-state,
canvas-preview, save, and shutdown projections. It substitutes only
deterministic in-memory/external boundaries for network, model download,
decoder, and long-running worker operations; it does not modify supplied
media.

## Supplied-video fingerprints and prepared copies

Each supplied source was read-only hashed and probed again for this record.

| ID | Original path | Bytes | SHA-256 | Metadata |
| --- | --- | ---: | --- | --- |
| V1 | `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-49-10_w.mp4` | 10,351,896 | `04e6148c003d7e29a8dd7900af988855eb9e50d46bbe3424c37d6e0f756941a5` | H.264, 1920×1080, 288 frames, time base 1/90000, rate 5184000/172789, 9.599389s |
| V2 | `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-06-31_w.mp4` | 14,272,282 | `2147612e79463a6d61949cb2ac80dfa11c046b2eb52ff85060b4ee83dc781eee` | H.264, 1920×1080, 288 frames, time base 1/90000, rate 160000/5333, 9.599400s |
| V3 | `/Users/abhiksarkar/Downloads/Videos/000414_000558_2025_10_13_08-15-48_w.mp4` | 1,402,211 | `329477efbde5cec6294e3a0886929a80b5348ddbd3c65bdbd71bd999e3931125` | H.264, 1920×1080, 192 frames, time base 1/90000, rate 5760000/287483, 9.582767s |

The current native-review fixture contains byte-identical video copies at:

- `/tmp/labelimgpp-native-release.r5PJWB/videos/000414_000480_2025_09_04_17-49-10_w.mp4`
- `/tmp/labelimgpp-native-release.r5PJWB/videos/000414_000480_2025_09_04_17-06-31_w.mp4`
- `/tmp/labelimgpp-native-release.r5PJWB/videos/000414_000558_2025_10_13_08-15-48_w.mp4`

Its `images/` directory contains the four prepared PNG frames used by the
native image-flow row.

Their MP4 byte counts and SHA-256 values match the corresponding source rows.
The adjacent SQLite sidecars belong only to those task-local copies.

## Comparison acceptance scorecard

Competitor observations informed these acceptance criteria only; they are not
runtime dependencies. LabelImg++ passes every automated criterion below.

| Acceptance criterion | LabelImg++ automated evidence | Status |
| --- | --- | --- |
| Choose one class for repeated objects | Active-class workflow and continuous image/video flow tests | **PASS** |
| Keep one tool until explicitly changed | Workflow state plus compact/responsive matrix | **PASS** |
| Use one-key next/previous navigation | Image navigation and A/D video controls | **PASS** |
| Save completed mutations without navigating away | Continuous-save, recovery, and soak gates | **PASS** |
| Show a complete frame on first paint | Image-fit/video workspace projections and recovery gates | **PASS** |
| Keep essential video controls usable at 800 pixels | Responsive matrix, timeline, and 800×600 evidence | **PASS** |

## Native computer-use matrix

All native rows were completed on 2026-08-27 with the real macOS application
and task-local fixture. The supplied videos were accessed through the
byte-identical copies listed above; the source files were never modified.

| Native check | Status | Direct observation |
| --- | --- | --- |
| Four-frame image flow, including 800-pixel-width repeat | **PASS** | Chose `vehicle`, drew repeatedly, and confirmed **W** kept the rectangle tool armed. **A/D**, Saved, undo/redo, verification, quit/reopen, and annotation persistence all worked. At approximately 802 pixels wide the inspector collapsed, the whole image remained fitted, and another box could be drawn and saved without clipping, focus loss, or a modal interruption. |
| V1, V2, V3 ten-cycle open/play/PTS-seek/close soak | **PASS — 30/30 cycles** | Each prepared video completed ten launch/open, play/pause, **D/A** PTS step, and quit cycles. Every cycle closed the application with no abandoned application or worker process. |
| 800-pixel video controls | **PASS** | At approximately 802 pixels wide, Previous, Play/Pause, Next, exact time, speed, PTS/frame, Legend, Track, and the seek control remained available. A real slider seek reached value 500870 and displayed `00:00:04.800`, `PTS 431975`, and approximately frame 96. |
| Real Assist lifecycle | **PASS** | The panel exposed model purpose, provider, 42.6 MB size, and storage path. Explicit download/cancel returned to Ready without automatic retry; manual retry promoted files matching the manifest hashes with no `.part` files. A task-local runtime then completed real image inference: reject preserved five objects, accept autosaved a `plant` polygon, and quit/reopen restored all six objects. On V3, a manual anchor tracked forward across 100 frames with 0 gaps and 0 failures; accepting propagation produced 101 accepted annotations. |
| Crash/process report inspection | **PASS** | After the final clean quit, no application or Python worker remained and no new macOS diagnostic report existed for the audit window. The audit log contained no Python exception or fatal crash; only non-fatal ONNX Runtime/CoreML capability warnings were observed. |

## Short user workflow and optional setup

1. **Open** an image or directory.
2. Choose an **Active class**, then select a drawing tool.
3. Draw as many annotations as needed; the selected class and tool continue
   until you explicitly change them.
4. Use **A** and **D** to move through images. Wait for the **Saved** indicator
   after each completed mutation.

Video features are optional: open a video when the video runtime is available,
then use the timeline to play, seek, and manage tracks. Assist is also
optional: its panel describes the required setup and presents an explicit
download action when a model is absent. Neither feature promises or performs
an automatic installation or download.

## Reproduction notes

Use an isolated settings path for tests and screenshot generation. The matrix
command is:

```bash
matrix_settings_dir="$(mktemp -d /tmp/labelimgpp-workspace-matrix.XXXXXX)"
LABELIMGPP_SETTINGS_PATH="$matrix_settings_dir/settings.json" \
  QT_QPA_PLATFORM=offscreen QT_AUTO_SCREEN_SCALE_FACTOR=0 QT_SCALE_FACTOR=1 \
  python tools/ux/capture_workspace_matrix.py \
  --output-dir docs/screenshots/continuous-annotation-release-2026-08-24
```

The native observations above were completed with an isolated settings file,
cache, and optional Assist runtime under the task-local `/tmp` fixture. The
base Python environment and the supplied source media remain unchanged.
