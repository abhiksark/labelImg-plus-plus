# Continuous Image Workflow final-review fix report

Date: 2026-08-24

Reviewed fix base: `9ac872a10328015dd592321b0c4d49a27a95078f`

Implementation commit: `bc63a83` (`fix: close continuous workflow review gaps`)

Report commit: the report-only commit immediately following `bc63a83` in the
final reported range.

## Outcome

All eight final-review findings were fixed with real-behavior regressions and
fresh focused and aggregate verification. Image and video documents now each
have one GUI serialization owner: the continuous-save coordinator. Manual
Save, navigation, close-file, delete, and quit join the coordinator's forced
drain instead of constructing a competing mutable write.

No push was performed.

## Test-driven development record

Every finding was driven through RED, GREEN, and a cleanup/self-review pass.
The test commands below were run with `QT_QPA_PLATFORM=offscreen` unless the
test itself initialized that environment.

### Finding 1: close-time image r1/r2 overwrite

Regression:
`test_close_save_drains_newest_image_revision_after_blocked_write`

- RED: the blocked r1 write completed, but close's independent save path did
  not wait for the coordinator's newer r2 ticket. Targeted result: `1 failed,
  8 deselected`.
- GREEN: the test passed after Save/close were routed through `drain()` and the
  immutable image ticket became the sole request builder/writer. Targeted
  result: `1 passed, 8 deselected`.
- The test blocks the actual first `write_save_request` publication with
  events, commits a second rectangle while r1 is blocked, requests close with
  Save, releases r1, and parses the final XML to assert two objects. It uses no
  timing sleep to manufacture the race.
- An additional publication-safety regression,
  `test_image_save_without_a_durable_path_remains_dirty`, was RED with the
  coordinator stuck in `saving`; after the fix it joined the paired image and
  video check at `2 passed, 21 deselected`.

Production result:

- `_dispatch_image_save()` is the only GUI image `SaveRequest` builder and
  worker submitter.
- Save As stores an exact `(document key, generation, revision)` target
  override consumed by that ticket.
- Explicit Save and synchronous compatibility callers force and join the
  ticket stream; they do not call the legacy mutable writer.
- Close callbacks run only after `drained`, when the newest revision is
  durable.
- Same-path replacement identities include a monotonically changing epoch,
  preventing a late old ticket from matching a reopened document with the
  same generation/revision values.

### Finding 2: three competing video save owners

Regressions:

- `test_manual_save_joins_the_active_continuous_video_writer`
- `test_quit_save_waits_for_the_continuous_video_writer_to_drain`
- `test_video_save_without_a_durable_revision_remains_dirty`

RED/GREEN evidence:

- The manual-Save and quit-Save pair was RED at `2 failed, 10 deselected`:
  the old manual/synchronous paths could construct competing requests.
- Both ownership tests passed after routing callers through the continuous
  drain. The complete video editing/opening focus later passed at `5 passed,
  21 skipped` in the environment's optional-media configuration.
- A worker returning no durable revision was separately RED because the
  coordinator reported `saved`; the paired missing-publication GREEN result
  was `2 passed, 21 deselected`.

Production result:

- `_dispatch_continuous_video_save()` is the sole GUI video request builder
  and `save_project_delta` submitter.
- Manual Save, close Save, and the synchronous compatibility API join the
  coordinator instead of writing independently.
- `video_model.mark_saved(revision)` runs before
  `continuous_save.complete(ticket)`, so any chained newer request is built
  only after the earlier delta has updated the durable model baseline.
- A missing durable revision fails the current ticket and preserves dirty
  state. A late error for an obsolete ticket cannot clear drain callbacks for
  the replacement document.
- Obsolete manual queue/callback bookkeeping was removed. The deterministic
  tests assert the writer's maximum concurrency remains one.

### Finding 3: failed video replacement stales the visible document

Regression:
`test_failed_video_replacement_keeps_save_identity_for_current_document`

- RED: failed preparation advanced `_dataset_generation` (`1 failed,
  13 deselected`), leaving the still-visible current video bound to a stale
  continuous-save identity.
- GREEN: preparation failure leaves the committed generation unchanged; the
  test then performs two real current-video edits/saves and verifies both
  SQLite revisions/observations (`1 passed, 13 deselected`).

Production result:

- The replacement request captures the current committed generation without
  advancing it.
- A new task/document generation is allocated only after a prepared candidate
  reaches the successful result/commit boundary.
- Preparation errors and replacement problems therefore leave the visible
  video's document key and save coordinator binding intact.

### Finding 4: legacy prompt setting overrides the new policy

Regressions:

- `test_valid_prompt_policy_is_authoritative_over_legacy_single_class`
- `test_legacy_prompt_setting_round_trips_but_new_policy_wins_next_launch`

- RED: the valid new `confirm_each` policy was replaced by legacy
  `singleclass=True`, and the inert legacy action remained exposed. Combined
  targeted result: `2 failed, 18 deselected`.
- GREEN: the valid new key wins, the old value remains persisted for downgrade
  compatibility, the selected new policy survives a second launch, and the
  inactive action is absent from View. Combined targeted result: `2 passed,
  18 deselected`.

Production result:

- `load_prompt_policy()` first accepts a valid new value and consults the
  legacy flag only for an absent/invalid value.
- The compatibility action/object remains available for persistence but is no
  longer exposed as a command.

### Finding 5: workflow draft/session boundaries

Regressions in `tests/integration/test_workflow_boundaries.py` cover:

- rectangle navigation,
- polygon navigation,
- a visible class picker plus provisional geometry,
- and `close_file()` resetting the authoritative interaction session.

RED/GREEN evidence:

- The first workflow run was RED at `4 failed`; the isolated close boundary
  was also observed RED at `1 failed, 3 deselected` during the cycle.
- GREEN: `4 passed` for the workflow file. The combined workflow/centering
  selection passed at `5 passed, 82 deselected`.

Production result:

- `_discard_workflow_draft()` centralizes dismissal of the picker,
  provisional shape, `canvas.current`, edit-drag/freehand state, and workflow
  provisional state.
- It restores the active tool/class projection and reports exactly
  `Draft discarded` when user-visible draft state existed.
- Image navigation, direct video-frame navigation, next/previous video frame,
  and synchronous image load use the boundary.
- `close_file()` resets state and starts a new authoritative interaction
  session rather than merely repainting Select.

### Finding 6: manual image navigation does not center pan

Regression:
`test_manual_image_navigation_centers_both_scrollbars`

- RED: the differently sized, larger-than-viewport destination retained
  manual zoom but left the horizontal scrollbar away from center (`1 failed,
  82 deselected`).
- GREEN: the combined centering/workflow selection passed at `5 passed,
  82 deselected`.

Production result:

- Dataset navigation marks a pending image-centering projection.
- After `paint_canvas()`, MANUAL mode centers both horizontal and vertical
  scrollbars.
- Video frame commits clear the image marker and retain their existing
  normalized scroll-ratio restoration, so image and video navigation policies
  remain distinct.

### Finding 7: blank compact-inspector icons

Regression:
`test_compact_inspector_controls_use_non_null_resource_icons`

- Test-quality note: the first draft checked `QIcon.isNull()`, which can be
  false even for a missing Qt resource. It was corrected before production
  work to request a real `QPixmap` and assert that pixmap is non-null.
- Corrected RED: `1 failed, 13 deselected` with the nonexistent
  `chevron-right` / `chevron-left` resources.
- GREEN: the combined icon/PyQt compatibility selection passed at `3 passed,
  57 deselected`.

Production result:

- Collapse and reopen buttons now use the resource-backed `next` and `prev`
  aliases at construction and during theme changes.

### Finding 8: PyQt4 compatibility gaps

Regressions:

- `test_set_active_class_uses_qt4_compatible_combo_api`
- `test_themed_icon_imports_its_painting_dependencies_on_pyqt4`

- Combo RED: `1 failed, 4 deselected` because the fake legacy combo had no
  `setCurrentText()`.
- Themed-icon RED: `1 failed, 40 deselected` because the real PyQt4 import
  branch left `QSize`/painting dependencies unbound.
- GREEN: the combined compatibility/icon selection passed at `3 passed,
  57 deselected`.

Production result:

- Active class selection uses `findText()` plus `setCurrentIndex()` or
  `setEditText()`, APIs available in the supported legacy path.
- The PyQt4 utility imports now include `QPainter`, `QPixmap`, and `QSize`.
- The fake-legacy test imports the actual utility module through the PyQt4
  branch and executes real themed-icon recoloring, rather than checking only
  placeholder behavior.

## Focused verification

Fresh focused result on the combined integration tree:

```text
QT_QPA_PLATFORM=offscreen pytest -q \
  tests/core/test_continuous_save.py \
  tests/core/test_workspace_settings.py \
  tests/core/test_utils.py \
  tests/widgets/test_active_class_control.py \
  tests/integration/test_autosave.py \
  tests/integration/test_workflow_boundaries.py \
  tests/integration/test_workspace_inspector.py \
  tests/integration/test_main_window.py \
  tests/video/test_editing.py \
  tests/video/test_opening.py

177 passed, 21 skipped in 141.95s
```

The reconstructed implementation commit was also tested independently from
the unstaged UX layer with the same focused module list:

```text
171 passed, 21 skipped in 125.20s
```

That isolated run initially exposed one missing test-only
`SimpleNamespace` import because the import existed in the unstaged layer.
The import was added to the fix commit, and the entire isolated focused set
was rerun to the green result above.

Additional focused evidence:

- `tests/integration/test_autosave.py`: `9 passed` before the final missing
  publication regression was added; all autosave tests are included in the
  final focused and aggregate runs.
- `tests/integration/test_main_window.py`: `83 passed` during the compatibility
  investigation.
- Order-sensitive synchronous compatibility sequence:
  `11 passed, 72 deselected`.
- `tests/video/test_editing.py tests/video/test_opening.py`:
  `5 passed, 21 skipped` before the last publication regression was added;
  all final video tests are included in the final focused/full runs.
- `python -m py_compile` passed for all amended production modules.

## Required aggregate gates

Both commands were run exactly as required and allowed to complete normally.

### Image-focused gate

```text
QT_QPA_PLATFORM=offscreen pytest -q tests/core tests/widgets tests/integration -k 'not video and not sam'

746 passed, 47 deselected in 247.22s
```

### Full suite

```text
QT_QPA_PLATFORM=offscreen pytest -q

1091 passed, 72 skipped in 407.20s
```

For comparison, the pre-fix full-suite baseline was `1074 passed, 72 skipped
in 300.06s`.

## Files in the implementation commit

Production:

- `labelImgPlusPlus.py`
- `libs/core/continuous_save.py`
- `libs/core/workspace_settings.py`
- `libs/utils/utils.py`
- `libs/widgets/activeClassControl.py`
- `libs/widgets/workspaceInspector.py`

Tests:

- `tests/core/test_continuous_save.py`
- `tests/core/test_utils.py`
- `tests/core/test_workspace_settings.py`
- `tests/integration/test_autosave.py`
- `tests/integration/test_main_window.py`
- `tests/integration/test_workflow_boundaries.py`
- `tests/integration/test_workspace_inspector.py`
- `tests/video/test_editing.py`
- `tests/video/test_opening.py`
- `tests/widgets/test_active_class_control.py`

Implementation diff: 16 paths, 1,001 insertions, 184 deletions.

## Dirty-hunk isolation proof

- The index was empty at fix-wave start.
- Before editing, the complete dirty status and patch were captured under
  `/private/tmp/labelimgpp-final-fix.ZJVXMl/`, including
  `preexisting.status`, `preexisting.patch`, and a tar snapshot of every
  candidate overlap file.
- Mixed paths were reconstructed in a detached temporary worktree from exact
  base `9ac872a`. Only the delta from the captured pre-edit file to the final
  file was applied. Rejected overlaps were manually translated against the
  base so unrelated UX additions were not absorbed.
- Clean fix-wave files were staged whole; mixed paths were staged from the
  reconstructed base blobs. The reconstructed staged tree passed its own
  171-test focused run.
- The complete cached path list and cached diff were inspected. Immediately
  before the implementation commit, `git diff --cached --check` exited zero.
- The committed path list is exactly the 16 paths listed above. No screenshot,
  canvas, gallery, workspace-page, accessibility, or polygon-integrity UX
  work entered the implementation commit.
- After the implementation commit, the original UX-remediation files remain
  modified/untracked in the worktree and unstaged. They were not reset,
  cleaned, overwritten, or pushed.

## Self-review

### Plan alignment and data-loss safety

- Image and video GUI serialization each have one request-construction owner.
- Save/Save As/close/navigation compatibility paths join drain; searches show
  one video `build_save_request()` call and one image
  `write_save_request()` call in the GUI production path.
- No synchronous fallback write, second save owner, nested `QEventLoop`, or
  sleep-based race workaround was introduced.
- The synchronous compatibility boundary joins the actual background pool in
  bounded slices and processes queued GUI completion callbacks until the same
  document identity reaches `saved` or `failed`.
- Request data remain immutable. Chained video construction happens after
  `mark_saved`; chained image construction happens only after ticket
  completion. Missing durable publications fail without clearing dirty state.
- Reset/reopen changes the continuous identity epoch, so a same-path,
  same-revision late result cannot clean or fail the replacement document.
- Close callbacks are document-identity scoped and fire only after the newest
  revision drains.

### Compatibility

- Amended production modules compile under the project's Python runtime and
  use Python 3.8-compatible syntax (no structural pattern matching, PEP 604
  unions, or newer-only collection annotations were introduced).
- A separate Python 3.8 executable was not available in this environment; the
  compatibility check therefore consisted of syntax/API review, compilation,
  and the fake-PyQt4 import/execution regression.
- PyQt4 fallbacks retain legacy import locations and avoid Qt5-only combo APIs.

### Concerns and warnings

- Every pytest run emitted the existing `pytest-asyncio` deprecation warning
  that `asyncio_default_fixture_loop_scope` is unset.
- Focused and aggregate runs repeatedly printed an existing non-fatal Qt
  close callback traceback for partially constructed windows:
  `AttributeError: 'MainWindow' object has no attribute
  '_reset_all_in_progress'`. The same traceback was present in the pre-fix
  baseline, all relevant commands exited successfully, and fixing partial
  construction was outside these eight findings.
- The full suite skipped 72 optional media/backend tests, matching the
  baseline skip count. The focused video modules skipped nodes requiring the
  unavailable optional media stack; real SQLite save-owner tests supplied
  non-skipped deterministic coverage.
