# UX Remediation Verification — 2026-08-23

## Build and environment

| Item | Value |
|---|---|
| Branch | `feat/ux-flow-remediation` |
| Base revision | `a49788e` |
| Working state | Clean local feature branch prepared for review |
| Application | labelImg++ `4.0.0rc0` |
| Host | macOS 26.5.2 (25F84), Asia/Kolkata |
| Runtime | Python 3.9.21, PyQt 5.15.11, Qt 5.15.14 |

## Automated verification

| Scope | Result |
|---|---|
| Focused final regression suites | **PASS — 374 passed** in 1011.55s |
| Complete final audit suite | **PASS — 1446 passed, 3 skipped** in 3:05:28 |
| Polygon capture harness | **PASS** at 1366x768 and 1440x900 |
| Capture dimensions | **PASS** — all 16 PNG files match their named dimensions |

The focused suites covered geometry and file-format integrity, picker focus,
tool-state projection, workspace reset, accessibility and tab order, native
shortcut presentation, gallery semantics, verification persistence, theme
contrast, responsive status layout, and inspector selection state.

The complete final run reported three legitimate optional cases and no test
failures. The focused rerun exercised the final workspace, gallery, canvas,
accessibility, polygon-integrity, and video-opening remediation on the exact
file state committed to the feature branch.

## macOS interaction audit

The live application audit used the macOS accessibility tree and keyboard
events against an isolated temporary application bundle. Geometry export was
also exercised with Qt's synthesized mouse events at both release sizes.

| Check | Result | Evidence |
|---|---|---|
| Four-point polygon and saved XML | **PASS — synthesized** | 4 canvas points, 4 Pascal VOC `<pt>` elements, no consecutive duplicates at both sizes |
| Immediate class typing and Return | **PASS** | Picker owned focus and committed the typed class at both sizes |
| Canvas and gallery Tab / Shift+Tab | **PASS** | Traversal reached visible primary controls and returned in reverse; hidden-page controls were skipped |
| Native macOS shortcut presentation | **PASS** | Live controls exposed Command-based labels, including `Select (⌘J)` |
| Verify, save, navigate, and return | **PASS** | The Verified action/chip persisted after save and reload, disappeared on the next unverified image, and returned on navigation back |
| Gallery meaning and scale | **PASS** | `Dataset gallery`, 150px scale, interaction hint, named Unannotated/Annotated/Verified legend, and per-item accessible status words were present |
| Gallery close to empty workspace | **PASS** | Document, dataset, statistics, rail, verification state, and previous status message cleared in one transition |
| Dark theme and polygon visibility | **PASS — visual/synthesized** | Dark rail palette applied, no startup picker ghost appeared, and the contrast halo remained visible in both capture sizes |

### Remaining hardware gate

A physical hardware-mouse polygon pass at 1366x768 and 1440x900 was **not
run** because this automated environment cannot emit physical hardware events.
Coordinate-based Computer Use clicks against the temporary Qt bundle were also
unavailable (`noWindowsAvailable`), although accessibility inspection and
keyboard control worked. The synthesized-event matrix and automated format
tests pass, but a human hardware-mouse pass remains the final release-gate
check for input-path classification.

## Screenshot matrix

Each link represents both release sizes (`1366x768`, `1440x900`); matching dark
or light variants are stored beside it.

| State | Light | Dark |
|---|---|---|
| Unselected polygon | [1366x768](../screenshots/ux-remediation-2026-08-23/canvas-unselected-polygon-light-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/canvas-unselected-polygon-light-1440x900.png) | [1366x768](../screenshots/ux-remediation-2026-08-23/canvas-unselected-polygon-dark-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/canvas-unselected-polygon-dark-1440x900.png) |
| Verified image | [1366x768](../screenshots/ux-remediation-2026-08-23/verified-image-light-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/verified-image-light-1440x900.png) | [1366x768](../screenshots/ux-remediation-2026-08-23/verified-image-dark-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/verified-image-dark-1440x900.png) |
| Full gallery | [1366x768](../screenshots/ux-remediation-2026-08-23/full-gallery-light-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/full-gallery-light-1440x900.png) | [1366x768](../screenshots/ux-remediation-2026-08-23/full-gallery-dark-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/full-gallery-dark-1440x900.png) |
| Empty after close | [1366x768](../screenshots/ux-remediation-2026-08-23/empty-after-close-light-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/empty-after-close-light-1440x900.png) | [1366x768](../screenshots/ux-remediation-2026-08-23/empty-after-close-dark-1366x768.png) · [1440x900](../screenshots/ux-remediation-2026-08-23/empty-after-close-dark-1440x900.png) |

## Continuous image workflow acceptance — 2026-08-24

The image slice now has one real-window acceptance flow covering a single
class choice, two committed rectangles, continuous Pascal VOC persistence,
next-image navigation, retained Rectangle/class state, retained Fit Window
view mode, navigation back, and exact sidecar reload. The screenshot API tests
also construct fresh real windows for annotated, saving, saved, and failed
states so advertised scenarios do not depend on matrix order.

### Test-first evidence

- The flow test was first run against the completed Tasks 1–6 implementation
  and passed. Sensitivity was then proven with a temporary mutation replacing
  image-navigation `workflow.navigate()` with `workflow.start_session()`; the
  test failed at the retained-class assertion (`None != 'vehicle'`). The
  mutation was restored exactly and the test returned green.
- The screenshot contract test was added before its implementation and failed
  during collection with `ModuleNotFoundError` for the absent capture harness.
  After implementing `capture_scenario()`, both Task 7 tests passed.
- A combined-suite run exposed inherited annotation-format/autosave state in
  the first test. The test now explicitly selects Pascal VOC, enables
  continuous save, and waits for both `Saved` and the concrete XML sidecar.
  It passes alone and after the autosave integration module.
- Review sensitivity runs then exposed three gaps before the fix: a saved
  `confirm_each` prompt policy prevented choose-once/draw-twice, `saving`
  produced `pending` instead of a real in-flight save, and the source-image
  neutrality assertion found the baked-in rectangle colors `#536878` and
  `#8aa1b2`. The fixed acceptance and harness explicitly establish
  `reuse_active`, restore the original prompt policy, hold a real coordinator
  ticket in the `saving` state, and use a uniform `#dce6ee` source image.
- Navigation back now reparses the Pascal VOC sidecar and requires exactly
  `['vehicle', 'vehicle']`, plus two reloaded canvas shapes.
- The first verbose aggregate run named three stale expectations from earlier
  tasks: the removed default-class combo, a docked-only inspector assertion at
  narrow width, and legacy `Unsaved` copy. Their approved Active class,
  responsive drawer, and `Saving…` contracts failed together in 0.22s before
  the expectation update and passed together in 0.26s afterward.

### Screenshot matrix

`tools/ux/capture_workspace_matrix.py` captured these eight states in light and
dark at 800x600, 960x640, 1366x768, and 1440x900:

1. `empty-workspace`
2. `first-image-fit`
3. `two-rectangles`
4. `inspector-open`
5. `inspector-closed`
6. `saving`
7. `saved`
8. `save-failed`

All 64 exact filenames are listed in the
[screenshot README](../screenshots/README.md#continuous-image-workflow-2026-08-24).
The harness reopened every PNG, checked its named dimensions, and rejected
empty files. A filesystem check also found 64 PNGs and zero zero-byte files.
Two complete consecutive captures produced the same aggregate SHA-1:
`d9dc6e0d0525f74d5cdbd14fc1274b3ffc47be85`.

### Verification results

| Scope | Result |
|---|---|
| Task 7 acceptance and capture API | **PASS — 7 passed** in 3.45s |
| Scoped stale-expectation nodes | **PASS — 3 passed** in 0.26s |
| Screenshot harness | **PASS — 64 deterministic PNGs** in about 11.0s per run |
| Exact image-focused aggregate command | **PASS — 733 passed, 47 deselected** in 200.51s |
| Complete suite | **PASS — 1074 passed, 72 skipped** in 299.89s |

The final required image-focused command ran serially with current-test
visibility and completed normally:

```bash
QT_QPA_PLATFORM=offscreen pytest -vv tests/core tests/widgets \
  tests/integration -k 'not video and not sam'
```

The previously suspected CPU-bound path was a slow but progressing UI sequence.
In particular,
`tests/integration/test_autosave.py::test_disabled_automatic_save_uses_navigation_safeguard`
took roughly 30 seconds and passed. No test stalled, so no process sampling or
termination was needed.

The exact full suite then ran serially with the same verbose diagnostics:

```bash
QT_QPA_PLATFORM=offscreen pytest -vv
```

It completed with 1,074 passes and 72 optional-dependency/platform skips. Both
passing aggregate runs emitted the repository's existing teardown tracebacks
from deliberately incomplete `MainWindow` test objects after test execution;
those tracebacks did not change either process exit status.
