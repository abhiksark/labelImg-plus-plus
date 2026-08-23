# UX Remediation Verification — 2026-08-23

## Build and environment

| Item | Value |
|---|---|
| Branch | `codex/ux-audit-remediation` |
| Base revision | `a49788e` |
| Working state | Remediation changes are uncommitted; nothing was pushed |
| Application | labelImg++ `4.0.0rc0` |
| Host | macOS 26.5.2 (25F84), Asia/Kolkata |
| Runtime | Python 3.9.21, PyQt 5.15.11, Qt 5.15.14 |

## Automated verification

| Scope | Result |
|---|---|
| Focused remediation suites | **PASS — 179 passed** in 9.16s |
| Complete test suite | **PASS — 1014 passed, 72 skipped** in 139.18s |
| Polygon capture harness | **PASS** at 1366x768 and 1440x900 |
| Capture dimensions | **PASS** — all 16 PNG files match their named dimensions |

The focused suites covered geometry and file-format integrity, picker focus,
tool-state projection, workspace reset, accessibility and tab order, native
shortcut presentation, gallery semantics, verification persistence, theme
contrast, responsive status layout, and inspector selection state.

The 72 skips are existing optional platform/video-dependency cases. The suite
also emits known teardown tracebacks from tests that intentionally construct an
incomplete `MainWindow`; they were present before this work and did not produce
test failures.

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
next-image navigation, retained Rectangle/class state, and retained Fit Window
view mode. A second real-window test protects the stable screenshot API's
scenario dispatch, filename, dimensions, and non-empty PNG output.

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
`4777dc2cfa95058de10c7840191b99bf08ceeaec`.

### Verification results

| Scope | Result |
|---|---|
| Task 7 acceptance and capture API | **PASS — 2 passed** in 0.66s |
| Acceptance after autosave integration tests | **PASS — 10 passed** in 7.95s |
| Image core shard | **PASS — 254 passed, 13 deselected** in 0.65s |
| Image widget shard | **PASS — 275 passed, 15 deselected** in 0.28s |
| Screenshot harness | **PASS — 64 deterministic PNGs** in 10.8s per run |
| Exact image-focused aggregate command | **CPU-bound path recurred after 69%** |
| Complete `pytest -q` attempt | **CPU-bound path recurred after 37%** |

The required image-focused command was attempted after the test isolation fix:

```bash
pytest -q tests/core tests/widgets tests/integration -k 'not video and not sam'
```

It advanced past 69% and another 60 tests, then remained at 100% CPU (PID
54743, 1:00 elapsed) in the known UI-heavy path. Only that pytest process was
terminated. Running the core and widget portions in fresh processes produced
the passing shard results above. An integration-only confirmation reproduced
the same path at 100% CPU (PID 55067, 0:39 elapsed) after 28 tests and was also
terminated without affecting other processes.

The required final `pytest -q` attempt reached 37% before the same behavior:
PID 54854 remained at 100% CPU at 1:10 elapsed and only that pytest process was
terminated. No test failure was printed in either post-fix aggregate attempt;
the limitation is the pre-existing CPU-bound combined UI execution path, not a
Task 7 assertion failure.
