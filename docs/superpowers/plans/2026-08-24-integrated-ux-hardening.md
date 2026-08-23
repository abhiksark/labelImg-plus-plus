# Integrated UX Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the continuous image, video, and Assist workflows work together without regressions, inaccessible controls, data loss, or macOS shutdown crashes.

**Architecture:** Treat the three prior slices as one product and validate their shared boundaries: settings migration, document generations, undo/revision/save state, focus/layout projection, optional runtimes, and worker teardown. Add deterministic accessibility/layout checks, a reusable screenshot harness, recovery/soak tests, and a final OS-level computer-use matrix on the supplied media.

**Tech Stack:** Python 3.8+, PyQt5/PyQt4 compatibility, pytest, QtTest, existing image/video format suites, macOS accessibility/computer use, PNG screenshot evidence.

**Spec:** `docs/superpowers/specs/2026-08-24-continuous-annotation-video-design.md`

**Prerequisites:** The continuous image, video workspace, and Assist/model lifecycle plans are complete with their focused suites passing.

## Global Constraints

- First use must support open, class choice, drawing, advance, and continued drawing without Preferences or documentation.
- Exactly one tool is checked at all times.
- Save, verification, object count, zoom, transport, time, speed, seek, and inspector affordance remain reachable at 800×600.
- Primary pointer targets are at least 32×32 logical pixels.
- Normal text meets 4.5:1 contrast; meaningful boundaries, focus rings, and selected states meet 3:1.
- Focus returns to canvas after class/time/Assist acceptance or cancellation and file selection.
- Failed image/video/project/model opens preserve the current workspace until replacement is ready.
- Stale async callbacks cannot replace newer documents or mark newer revisions durable.
- Base, video-enabled, screenshot, and supplied-media live matrices all pass.
- No `Python quit unexpectedly` or abandoned-worker warning is acceptable.
- Annotation formats and optional-dependency boundaries remain unchanged.
- Nothing is pushed automatically.

## File Structure

- Create `libs/utils/accessibility.py`: WCAG contrast and logical-target helpers used only by tests/UI validation.
- Create `libs/core/document_identity.py`: one immutable identity for async document callbacks.
- Create `libs/widgets/inlineErrorBanner.py`: recoverable replacement-open error with Retry and Choose another file.
- Create `tests/integration/test_settings_migration.py`: legacy preference migration and downgrade-safe persistence.
- Create `tests/integration/test_workflow_recovery.py`: cross-subsystem generation/save/failure recovery.
- Create `tests/integration/test_workspace_responsive_matrix.py`: visibility, overlap, focus, and target contracts at all four sizes.
- Modify `tools/ux/capture_workspace_matrix.py`: extend the image harness with deterministic video/Assist capture.
- Create `tests/integration/test_worker_soak.py`: repeated open/play/seek/close and cancellation cleanup.
- Create `docs/testing/continuous-annotation-release-matrix.md`: final automated and live evidence.
- Modify `README.rst`, `docs/screenshots/README.md`, and relevant existing settings/theme tests.

---

### Task 1: Settings migration and format compatibility

**Files:**
- Create: `tests/integration/test_settings_migration.py`
- Modify: `libs/core/workspace_settings.py`
- Modify: `libs/utils/constants.py`
- Modify: `labelImgPlusPlus.py:5878-5950`
- Modify: `tests/formats/test_io.py`
- Modify: `tests/formats/test_coco_io.py`
- Modify: `tests/formats/test_yolo_io.py`
- Modify: `tests/formats/test_yolo_seg_io.py`
- Modify: `tests/video/test_project.py`

**Interfaces:**
- Consumes: legacy navigation autosave, timer autosave, interval, `singleclass`, format, inspector, theme, and shortcut settings.
- Produces: `migrate_workflow_settings(settings) -> WorkflowSettingsMigration`; the migration changes runtime interpretation without deleting legacy keys.

- [ ] **Step 1: Write failing migration tests**

```python
def test_navigation_autosave_migrates_to_continuous_enabled():
    settings = {SETTING_AUTO_SAVE: True, SETTING_AUTO_SAVE_ENABLED: False}
    migrated = migrate_workflow_settings(settings)
    assert migrated.continuous_save is True
    assert settings[SETTING_AUTO_SAVE] is True
    assert settings[SETTING_AUTO_SAVE_ENABLED] is False


def test_legacy_interval_stays_readable_but_is_not_primary_policy():
    settings = {SETTING_AUTO_SAVE_INTERVAL: 120}
    migrated = migrate_workflow_settings(settings)
    assert migrated.legacy_interval == 120
    assert migrated.continuous_delay_ms == 250


def test_singleclass_migrates_to_reuse_active_without_preselecting_label():
    settings = {SETTING_SINGLE_CLASS: True}
    migrated = migrate_workflow_settings(settings)
    assert migrated.prompt_policy == 'reuse_active'
    assert migrated.active_class is None
```

- [ ] **Step 2: Run migration tests**

Run: `pytest -q tests/integration/test_settings_migration.py`

Expected: FAIL because the consolidated migration contract does not exist.

- [ ] **Step 3: Implement non-destructive migration**

```python
@dataclass(frozen=True)
class WorkflowSettingsMigration:
    continuous_save: bool
    continuous_delay_ms: int
    prompt_policy: str
    legacy_interval: int
    active_class: object = None


def migrate_workflow_settings(settings):
    continuous = settings.get(SETTING_CONTINUOUS_SAVE, None)
    if continuous is None:
        navigation = settings.get(SETTING_AUTO_SAVE, None)
        timer = settings.get(SETTING_AUTO_SAVE_ENABLED, None)
        continuous = (True if navigation is None and timer is None
                      else bool(navigation or timer))
    policy = settings.get(SETTING_PROMPT_POLICY)
    if policy not in ('reuse_active', 'confirm_each'):
        policy = 'reuse_active'
    interval = settings.get(SETTING_AUTO_SAVE_INTERVAL, 60)
    if interval not in (30, 60, 120, 300):
        interval = 60
    return WorkflowSettingsMigration(
        bool(continuous), 250, policy, interval, None)
```

Write the new settings keys when settings are saved, but preserve obsolete navigation/timer/interval values verbatim for downgrade compatibility. Never persist active class/tool across application sessions.

- [ ] **Step 4: Add unchanged-format round trips**

For Pascal VOC, YOLO, YOLO segmentation, CreateML, COCO, and the SQLite video project, load an existing fixture, perform a normal mutation/continuous save, reopen, and compare geometry/class/verification semantics. Example:

```python
def test_continuous_save_does_not_change_yolo_polygon_semantics(
        tmp_path, polygon_shape):
    path = tmp_path / 'frame.txt'
    save_yolo_seg(path, [polygon_shape])
    loaded = load_yolo_seg(path)
    save_yolo_seg(path, loaded)
    assert load_yolo_seg(path) == loaded
```

- [ ] **Step 5: Run migration and compatibility suites**

Run: `pytest -q tests/integration/test_settings_migration.py tests/formats tests/video/test_project.py tests/video/test_compatibility.py`

Expected: PASS.

- [ ] **Step 6: Commit migration hardening**

```bash
git add libs/core/workspace_settings.py libs/utils/constants.py labelImgPlusPlus.py tests/integration/test_settings_migration.py tests/formats/test_io.py tests/formats/test_coco_io.py tests/formats/test_yolo_io.py tests/formats/test_yolo_seg_io.py tests/video/test_project.py
git commit -m "test: preserve workflow compatibility"
```

### Task 2: Accessibility, target size, and contrast gates

**Files:**
- Create: `libs/utils/accessibility.py`
- Create: `tests/utils/test_accessibility.py`
- Create: `tests/integration/test_workspace_responsive_matrix.py`
- Modify: `tests/integration/test_workspace_accessibility.py`
- Modify: `tests/integration/test_theme_integration.py`
- Modify: `libs/utils/styles.py`
- Modify: `libs/widgets/commandBar.py`
- Modify: `libs/widgets/toolRail.py`
- Modify: `libs/widgets/workspaceInspector.py`
- Modify: `libs/widgets/videoTimelineWidget.py`
- Modify: `libs/widgets/assistPanel.py`

**Interfaces:**
- Consumes: Qt colors, widget geometry, visibility, accessible names, checked state, and focus chain.
- Produces: `relative_luminance(color)`, `contrast_ratio(first, second)`, `visible_primary_targets(root)`, and a four-size matrix test.

- [ ] **Step 1: Write failing helper and UI gates**

```python
def test_wcag_contrast_examples():
    assert contrast_ratio(QColor('#000000'), QColor('#ffffff')) == 21.0
    assert contrast_ratio(QColor('#777777'), QColor('#ffffff')) \
        == pytest.approx(4.48, abs=.02)
```

```python
@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    value = MainWindow(default_save_dir=str(tmp_path))
    yield value
    value.dirty = False
    value.close()
    QApplication.processEvents()


@pytest.mark.parametrize('size', [(800, 600), (960, 640),
                                  (1366, 768), (1440, 900)])
def test_primary_targets_visible_named_and_large(window, size):
    window.resize(*size)
    window.show()
    QApplication.processEvents()
    targets = visible_primary_targets(window)
    assert targets
    for widget in targets:
        assert widget.accessibleName().strip()
        assert widget.width() >= 32
        assert widget.height() >= 32
```

Add assertions that exactly one tool action is checked, hidden controls are absent from the focus chain, the drawer traps/restores focus, Play/Pause names current action, marker summary is non-color, and every visible normal-text token/background pair meets 4.5:1 while control/focus/selected tokens meet 3:1.

- [ ] **Step 2: Run accessibility gates**

Run: `pytest -q tests/utils/test_accessibility.py tests/integration/test_workspace_accessibility.py tests/integration/test_workspace_responsive_matrix.py tests/integration/test_theme_integration.py`

Expected: FAIL on any remaining undersized, unnamed, clipped, or low-contrast control.

- [ ] **Step 3: Implement helpers and fix only measured failures**

```python
def contrast_ratio(first, second):
    high, low = sorted((relative_luminance(first),
                        relative_luminance(second)), reverse=True)
    return (high + .05) / (low + .05)


def visible_primary_targets(root):
    target_types = (QAbstractButton, QAbstractSlider, QComboBox, QLineEdit)
    return tuple(widget for widget in root.findChildren(QWidget)
                 if isinstance(widget, target_types)
                 and widget.isVisibleTo(root)
                 and widget.property('secondaryAction') is not True)
```

Adjust theme tokens or widget sizing only where the failing assertion identifies a contract breach. Do not increase whole-window minimum sizes to make targets pass.

- [ ] **Step 4: Run accessibility and existing theme suites**

Run: `pytest -q tests/utils/test_accessibility.py tests/utils/test_styles.py tests/integration/test_workspace_accessibility.py tests/integration/test_workspace_responsive_matrix.py tests/integration/test_theme_integration.py tests/widgets/test_canvas_theme.py`

Expected: PASS in light/dark and 1×/2× scaling tests.

- [ ] **Step 5: Commit accessibility gates**

```bash
git add libs/utils/accessibility.py libs/utils/styles.py libs/widgets/commandBar.py libs/widgets/toolRail.py libs/widgets/workspaceInspector.py libs/widgets/videoTimelineWidget.py libs/widgets/assistPanel.py tests/utils/test_accessibility.py tests/integration/test_workspace_accessibility.py tests/integration/test_workspace_responsive_matrix.py tests/integration/test_theme_integration.py
git commit -m "test: enforce workspace accessibility gates"
```

### Task 3: Transactional replacement and cross-subsystem recovery

**Files:**
- Create: `libs/core/document_identity.py`
- Create: `libs/widgets/inlineErrorBanner.py`
- Create: `tests/core/test_document_identity.py`
- Create: `tests/integration/test_workflow_recovery.py`
- Modify: `labelImgPlusPlus.py:1884-2020`
- Modify: `labelImgPlusPlus.py:3618-3908`
- Modify: `labelImgPlusPlus.py:5480-5610`
- Modify: `libs/core/continuous_save.py`
- Modify: `libs/core/assist_state.py`
- Modify: `libs/core/task_coordinator.py`
- Modify: `tests/integration/test_assist_flow.py`
- Modify: `tests/video/test_navigation.py`

**Interfaces:**
- Consumes: dataset generation, document revision, save ticket, Assist run generation, and video request IDs.
- Produces: `DocumentIdentity(kind: str, key: str, generation: int)`, `InlineErrorBanner.retryRequested`, `chooseAnotherRequested`, `MainWindow.document_identity`, `_start_interaction_session_for(key)`, and `_is_current_document(identity)` used before every async UI/model mutation.

- [ ] **Step 1: Write failing stale-callback and replacement tests**

```python
def _wait(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def test_failed_video_replacement_preserves_current_image(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'current.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    bad_video = tmp_path / 'broken.mp4'
    bad_video.write_bytes(b'not a video')
    try:
        assert window.load_file(str(image_path))
        before = window.document_identity
        before_pixmap = window.canvas.pixmap.cacheKey()
        window.request_open_video(str(bad_video))
        assert _wait(app, lambda: window.last_inline_error is not None)
        assert window.document_identity == before
        assert window.canvas.pixmap.cacheKey() == before_pixmap
        assert window.canvas.isEnabled()
        assert window.inline_open_error.retry_button.text() == 'Retry'
        assert window.inline_open_error.choose_button.text() == \
            'Choose another file'
    finally:
        window.dirty = False
        window.close()


def test_old_save_completion_cannot_clean_new_document(tmp_path):
    _app, window = get_main_app()
    try:
        old_ticket = SaveTicket('image:a', generation=2, revision=5)
        window._start_interaction_session_for('image:b')
        window.continuous_save.mark_dirty(1)
        window._on_continuous_save_result(old_ticket, '/tmp/a.xml')
        assert window.continuous_save.state == 'pending'
    finally:
        window.dirty = False
        window.close()


def test_stale_assist_and_decode_results_are_ignored(tmp_path):
    _app, window = get_main_app()
    try:
        old = window.document_identity
        new_key = str(tmp_path / 'new.png')
        window._start_interaction_session_for(new_key)
        preview = SamResult(
            polygon=((1, 1), (10, 1), (10, 10)),
            bounds=(1, 1, 10, 10))
        window._on_assist_preview(old, preview)
        window._on_video_frame_result(object(), 1, old)
        assert window.canvas.assist_preview_shape is None
        assert window.document_identity.key == os.path.abspath(new_key)
    finally:
        window.dirty = False
        window.close()
```

Add the pure identity contract to `tests/core/test_document_identity.py`:

```python
def test_document_identity_is_hashable_and_generation_sensitive():
    first = DocumentIdentity('image', '/data/a.png', 3)
    assert first == DocumentIdentity('image', '/data/a.png', 3)
    assert first != DocumentIdentity('image', '/data/a.png', 4)
    assert {first: 'current'}[first] == 'current'
```

- [ ] **Step 2: Run recovery tests**

Run: `pytest -q tests/core/test_document_identity.py tests/integration/test_workflow_recovery.py tests/integration/test_async_workflows.py tests/video/test_opening.py -k 'stale or fail or replace or generation or identity'`

Expected: FAIL where callbacks use ad-hoc generation comparisons or clear the visible workspace too early.

- [ ] **Step 3: Centralize document identity checks**

```python
@dataclass(frozen=True)
class DocumentIdentity:
    kind: str
    key: str
    generation: int

    def __post_init__(self):
        object.__setattr__(self, 'kind', str(self.kind))
        object.__setattr__(self, 'key', os.path.abspath(
            os.fspath(self.key)) if self.key else '')
        object.__setattr__(self, 'generation', int(self.generation))
```

Capture this value in every load/save/decode/download/inference/propagation callback and call `_is_current_document(identity)` before painting, mutating, reporting Saved, or displaying a document-specific failure. Standardize the callback signatures as `_on_assist_preview(identity, result)`, `_on_video_frame_result(result, request_id, identity)`, and `_on_continuous_save_result(ticket, path)`, updating the earlier focused tests with them. Prepare replacement image/video/project state off-screen; call `_commit_*` only when it is fully ready. Project replacement failures into one `InlineErrorBanner` surface with Retry and Choose another file; neither action clears or disables the current workspace.

```python
class InlineErrorBanner(QFrame):
    retryRequested = pyqtSignal()
    chooseAnotherRequested = pyqtSignal()

    def __init__(self, parent=None):
        super(InlineErrorBanner, self).__init__(parent)
        self.message = QLabel(self)
        self.retry_button = QPushButton('Retry', self)
        self.choose_button = QPushButton('Choose another file', self)
        self.retry_button.clicked.connect(self.retryRequested)
        self.choose_button.clicked.connect(self.chooseAnotherRequested)
        layout = QHBoxLayout(self)
        layout.addWidget(self.message, 1)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.choose_button)
        self.hide()

    def show_error(self, message):
        self.message.setText(str(message))
        self.show()
        self.retry_button.setFocus(Qt.OtherFocusReason)
```

- [ ] **Step 4: Add save-failure and close recovery**

Test disk-full image and video saves, Retry success, Discard/Cancel, Assist cancellation during replacement, and graceful worker shutdown. Save failure must retain undoable in-memory edits and prevent destructive replacement until Retry or explicit Discard.

- [ ] **Step 5: Run all async/recovery suites**

Run: `pytest -q tests/core/test_document_identity.py tests/integration/test_workflow_recovery.py tests/integration/test_async_workflows.py tests/core/test_continuous_save.py tests/core/test_task_coordinator.py tests/core/test_shutdown_coordinator.py tests/video/test_opening.py tests/video/test_editing.py`

Expected: PASS.

- [ ] **Step 6: Commit recovery hardening**

```bash
git add labelImgPlusPlus.py libs/core/document_identity.py libs/widgets/inlineErrorBanner.py libs/core/continuous_save.py libs/core/assist_state.py libs/core/task_coordinator.py tests/core/test_document_identity.py tests/integration/test_workflow_recovery.py tests/integration/test_async_workflows.py tests/integration/test_assist_flow.py tests/video/test_navigation.py tests/video/test_opening.py tests/video/test_editing.py
git commit -m "fix: reject stale workflow results"
```

### Task 4: Deterministic screenshot matrix harness

**Files:**
- Modify: `tools/ux/capture_workspace_matrix.py`
- Create: `tests/tools/test_capture_workspace_matrix.py`
- Modify: `docs/screenshots/README.md`

**Interfaces:**
- Consumes: scenario name, logical width/height, theme, fixture path, and output directory.
- Produces: `capture_scenario(window, scenario, size, theme, output_dir) -> str` and PNGs named `<scenario>-<theme>-<width>x<height>.png`.

- [ ] **Step 1: Write failing naming/dimension tests**

```python
def test_capture_uses_logical_size_and_stable_name(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    window = MainWindow(default_save_dir=str(tmp_path))
    path = capture_scenario(
        window, 'image-saved', (800, 600), 'light', str(tmp_path))
    image = QImage(path)
    assert os.path.basename(path) == 'image-saved-light-800x600.png'
    assert image.size() == QSize(800, 600)
    window.dirty = False
    window.close()
```

- [ ] **Step 2: Run harness test**

Run: `pytest -q tests/tools/test_capture_workspace_matrix.py`

Expected: FAIL because the reusable harness does not exist.

- [ ] **Step 3: Implement explicit scenario setup**

```python
SIZES = ((800, 600), (960, 640), (1366, 768), (1440, 900))
THEMES = ('light', 'dark')


def capture_scenario(window, scenario, size, theme, output_dir):
    window.resize(*size)
    window._apply_theme(Theme.DARK if theme == 'dark' else Theme.LIGHT)
    SCENARIOS[scenario](window)
    QApplication.processEvents()
    QApplication.processEvents()
    filename = '%s-%s-%sx%s.png' % (
        scenario, theme, size[0], size[1])
    path = os.path.join(output_dir, filename)
    assert window.grab().save(path, 'PNG')
    return path
```

Provide named setup functions for empty, image first-fit, rectangle active after two commits, inspector drawer open, Saving, Saved, Save failed, video paused/playing, invalid time, Track menu, propagation pending, Assist setup/downloading/failure/preview, and shutdown timeout. Each setup uses fake providers/workers where network or long-running work would make capture nondeterministic.

- [ ] **Step 4: Run harness and dimension validation**

Run: `pytest -q tests/tools/test_capture_workspace_matrix.py`

Expected: PASS and every PNG matches its logical filename dimensions at 1×.

- [ ] **Step 5: Commit the capture harness**

```bash
git add tools/ux/capture_workspace_matrix.py tests/tools/test_capture_workspace_matrix.py docs/screenshots/README.md
git commit -m "test: add workspace screenshot harness"
```

### Task 5: Worker, save, and decoder soak tests

**Files:**
- Create: `tests/integration/test_worker_soak.py`
- Modify: `tools/performance/profile_video.py`
- Modify: `tests/video/test_performance_tools.py`
- Modify: `libs/core/task_coordinator.py`
- Modify: `libs/core/video_decoder.py`
- Modify: `labelImgPlusPlus.py`

**Interfaces:**
- Consumes: test VFR generator, `TaskCoordinator.queue_depths()`, active jobs, save state, decoder session, and open/close APIs.
- Produces: `run_video_soak(window, path, cycles=10)` summary with cycles, failures, remaining jobs, and elapsed time.

- [ ] **Step 1: Write the ten-cycle failure detector**

```python
def _wait(app, predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def test_ten_open_play_seek_close_cycles_leave_no_workers(
        tmp_path, make_video):
    app, window = get_main_app()
    path = make_video(
        tmp_path / 'soak.mp4', frames=40, variable_rate=True)
    try:
        for _cycle in range(10):
            assert window.open_video(path)
            first_pts = window.current_video_frame_ref.pts
            window.play_pause_video()
            assert _wait(
                app, lambda: window.current_video_frame_ref.pts > first_pts)
            snapshot = window.video_snapshot
            midpoint = int(snapshot.start_pts or 0) + \
                int(snapshot.duration_pts or 0) // 2
            window.request_video_frame(VideoFrameRef(
                snapshot.fingerprint, snapshot.stream_index, midpoint,
                snapshot.time_base_num, snapshot.time_base_den))
            assert _wait(app, lambda: not window._video_decode_in_flight)
            window.dirty = False
            window.close_file()
            assert _wait(app, window.task_coordinator.is_idle)
        assert window.task_coordinator.active_jobs() == ()
    finally:
        window.dirty = False
        window.close()
```

Add parallel tests for repeated image navigation while saving, cancel during model download, cancel during propagation, and close while inference/decode is in flight.

- [ ] **Step 2: Run soak tests alone**

Run: `pytest -q tests/integration/test_worker_soak.py tests/video/test_performance_tools.py -x`

Expected: PASS or expose a deterministic remaining job/decoder/save-state failure to fix.

- [ ] **Step 3: Fix lifecycle leaks at their owner**

If a test fails, cancel and clear the specific generation-owned handle, leave decoder closure until the video lane reports idle, and ensure every completion path clears its in-flight flag in one `finally`/finished handler. Do not add arbitrary sleeps or global thread-pool termination.

- [ ] **Step 4: Run soak plus async suites repeatedly**

Run: `pytest -q tests/integration/test_worker_soak.py tests/integration/test_async_workflows.py tests/core/test_task_coordinator.py tests/core/test_shutdown_coordinator.py tests/video/test_navigation.py --count=3`

If `pytest-repeat` is unavailable, run the same command three explicit times without adding a project dependency. Expected: all three runs PASS with zero remaining active jobs.

- [ ] **Step 5: Commit soak coverage and fixes**

```bash
git add tests/integration/test_worker_soak.py tools/performance/profile_video.py tests/video/test_performance_tools.py libs/core/task_coordinator.py libs/core/video_decoder.py labelImgPlusPlus.py
git commit -m "test: soak annotation worker lifecycles"
```

### Task 6: Final automated and OS-level computer-use release matrix

**Files:**
- Create: `docs/testing/continuous-annotation-release-matrix.md`
- Modify: `docs/screenshots/README.md`
- Modify: `README.rst`

**Interfaces:**
- Consumes: all prior plan deliverables and the supplied media.
- Produces: final pass/fail evidence, screenshot links, crash observations, and user-facing workflow documentation.

- [ ] **Step 1: Run focused suites by subsystem**

Run:

```bash
pytest -q tests/core/test_annotation_workflow.py tests/core/test_continuous_save.py tests/core/test_view_transform.py
pytest -q tests/video
pytest -q tests/core/test_assist_state.py tests/integrations/test_model_cache.py tests/widgets/test_assist_panel.py tests/integration/test_assist_flow.py
pytest -q tests/integration/test_workspace_responsive_matrix.py tests/integration/test_workflow_recovery.py tests/integration/test_worker_soak.py
```

Expected: every command PASS.

- [ ] **Step 2: Run complete base and optional suites**

Run: `pytest -q`

Then run in the environment containing `[video,sam]`: `pytest -q tests/video tests/integration/test_assist_flow.py tests/integrations/test_sam_backend.py`.

Expected: PASS; skips are only documented optional/platform skips, not failures hidden by selection.

- [ ] **Step 3: Generate and inspect the complete screenshot matrix**

Run the harness for all named scenarios at 800×600, 960×640, 1366×768, and 1440×900 in light/dark. Inspect for complete frame fit, hierarchy, non-overlap, active tool, save state, drawer focus, timeline essentials, semantic markers, Assist actions, and readable error/recovery states. Record every artifact and any accepted platform variance in the release matrix.

- [ ] **Step 4: Run the four-frame image flow through OS-level computer use**

Choose `vehicle` once, draw two rectangles, press D, confirm class/tool/fit continuity, wait for immediate sidecar creation, undo/redo across autosaves, verify, quit, and reopen. Repeat at 800-pixel width. Record whether any modal class prompt, tool reset, clipped frame, stale save state, or focus loss occurs; all must be **No**.

- [ ] **Step 5: Run every unique supplied video through OS-level computer use**

Use:

- `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-49-10_w.mp4`
- `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-06-31_w.mp4`
- `/Users/abhiksarkar/Downloads/Videos/000414_000558_2025_10_13_08-15-48_w.mp4`

For each, perform the complete flow from the video-plan matrix, including ten open/play/seek/close repetitions and one 800-pixel-width pass. Inspect macOS crash reports/process state after each set. Pass requires no crash dialog, no abandoned-worker warning, accurate neighboring PTS, durable annotations, and zero remaining application worker jobs after close.

- [ ] **Step 6: Run the real Assist lifecycle once**

With explicit consent already represented by the Download click, inspect setup metadata, cancel once, verify no retry/temporary artifact, retry, validate cache promotion, reject one preview, accept one with Active class, save/reopen, then explicitly Track forward on video. Pass requires no automatic download/propagation and truthful error/cancel state.

- [ ] **Step 7: Update user-facing documentation and release evidence**

Document the short primary flow in `README.rst`: Open, choose Active class, choose tool, draw repeatedly, A/D navigate, and Saved indicator. Document optional video/Assist setup without promising automatic installation. Fill `continuous-annotation-release-matrix.md` with exact command results, counts, durations, OS/runtime, supplied-file fingerprints, screenshot links, live observations, and any remaining non-release-blocking limitations. Include the comparison acceptance scorecard: one class choice for repeated objects, one tool choice until explicitly changed, one-key next/previous navigation, completed-mutation saving without navigation, complete frame on first paint, and essential video controls at 800 pixels. Each item must pass in LabelImg++; the competitor observations remain evidence, not runtime dependencies.

- [ ] **Step 8: Commit final evidence without pushing**

```bash
git add README.rst docs/testing/continuous-annotation-release-matrix.md docs/screenshots/README.md docs/screenshots/continuous-annotation-release-2026-08-24
git commit -m "docs: record continuous annotation verification"
```

- [ ] **Step 9: Final branch audit**

Run:

```bash
git status --short
git log --oneline --decorate -20
git diff --check HEAD~20..HEAD
pytest -q
```

Expected: no whitespace errors, all intended implementation/evidence commits are present, the full suite passes, unrelated user changes remain preserved, and nothing has been pushed.
