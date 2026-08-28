# Continuous Image Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make image annotation continuous by preserving class, tool, view mode, and work while saving every completed mutation safely.

**Architecture:** Add three focused state owners: a Qt-free annotation workflow model, a revision-aware save coordinator, and a view-transform model. `MainWindow` remains the integration layer and projects those models into the existing canvas, actions, command bar, and inspector; the canvas continues to own only low-level geometry.

**Tech Stack:** Python 3.8+, PyQt5 with existing PyQt4 fallbacks, pytest, QtTest, existing `TaskCoordinator`, immutable `SaveRequest`, atomic `write_save_request`.

**Spec:** `docs/superpowers/specs/2026-08-24-continuous-annotation-video-design.md`

## Global Constraints

- Image and frame navigation within one interaction session preserve active class and active tool; opening different standalone content, directory, video, or project clears them.
- `reuse_active` is the default prompt policy; `confirm_each` remains available.
- Automatic saving is enabled by default and coalesces completed mutations for exactly 250 ms.
- Pointer movement and unfinished rectangle or polygon geometry never create a durable revision.
- View mode is exactly one of `fit_window`, `fit_width`, or `manual`.
- Pascal VOC, YOLO, YOLO segmentation, CreateML, COCO, and video-project formats do not change.
- Python 3.8 remains supported; touched production modules retain PyQt4 import fallbacks where that pattern already exists.
- No AI or video dependency becomes mandatory in the base installation.
- Nothing is pushed automatically.

## File Structure

- Create `libs/core/annotation_workflow.py`: Qt-free class/tool/prompt state and Escape transitions.
- Create `libs/core/continuous_save.py`: revision-safe save scheduling state machine and 250 ms Qt timer adapter.
- Create `libs/core/view_transform.py`: authoritative fit/manual mode and zoom projection.
- Create `libs/widgets/activeClassControl.py`: persistent Active class and prompt-policy control.
- Modify `libs/widgets/canvas.py`: non-editable post-commit highlight and explicit provisional-state signals.
- Modify `libs/widgets/workspaceInspector.py`: dock/drawer breakpoint behavior and focus restoration.
- Modify `libs/widgets/view_scaling.py`: viewport-based projection helpers used by the view state owner.
- Modify `libs/core/workspace_settings.py` and `libs/utils/constants.py`: validated continuous-save and prompt-policy migration keys.
- Modify `labelImgPlusPlus.py`: compose the new owners and remove duplicate workflow/save/view state.
- Create `tools/ux/capture_workspace_matrix.py`: reusable deterministic screenshot entry point, expanded by later slices.
- Add focused tests under `tests/core`, `tests/widgets`, and `tests/integration`.

---

### Task 1: Framework-independent annotation workflow

**Files:**
- Create: `libs/core/annotation_workflow.py`
- Create: `tests/core/test_annotation_workflow.py`

**Interfaces:**
- Consumes: plain strings from settings and tool actions.
- Produces: `AnnotationTool`, `PromptPolicy`, `EscapeOutcome`, `WorkflowSnapshot`, and `AnnotationWorkflow`; later tasks call `start_session()`, `set_active_class()`, `set_prompt_policy()`, `set_tool()`, `begin_provisional()`, `finish_provisional()`, `navigate()`, and `escape()`.

- [ ] **Step 1: Write the failing state-transition tests**

```python
from libs.core.annotation_workflow import (
    AnnotationTool, AnnotationWorkflow, EscapeOutcome, PromptPolicy,
)


def test_navigation_preserves_class_and_tool_but_new_session_clears_them():
    workflow = AnnotationWorkflow()
    workflow.start_session()
    workflow.set_active_class('vehicle')
    workflow.set_tool(AnnotationTool.RECTANGLE)

    workflow.navigate()
    assert workflow.snapshot.active_class == 'vehicle'
    assert workflow.snapshot.active_tool is AnnotationTool.RECTANGLE

    workflow.start_session()
    assert workflow.snapshot.active_class is None
    assert workflow.snapshot.active_tool is AnnotationTool.SELECT


def test_escape_cancels_geometry_before_selecting_the_neutral_tool():
    workflow = AnnotationWorkflow(prompt_policy=PromptPolicy.REUSE_ACTIVE)
    workflow.set_tool(AnnotationTool.POLYGON)
    workflow.begin_provisional()

    assert workflow.escape() is EscapeOutcome.CANCEL_PROVISIONAL
    assert workflow.snapshot.active_tool is AnnotationTool.POLYGON
    assert workflow.escape() is EscapeOutcome.SELECT_TOOL
    assert workflow.snapshot.active_tool is AnnotationTool.SELECT
```

- [ ] **Step 2: Run the focused tests and verify the missing-module failure**

Run: `pytest -q tests/core/test_annotation_workflow.py`

Expected: FAIL during collection with `ModuleNotFoundError: libs.core.annotation_workflow`.

- [ ] **Step 3: Implement the minimal workflow model**

```python
from dataclasses import dataclass, replace
from enum import Enum


class AnnotationTool(str, Enum):
    SELECT = 'select'
    RECTANGLE = 'rectangle'
    POLYGON = 'polygon'
    SMART_BOX = 'smart_box'
    SMART_POINTS = 'smart_points'


class PromptPolicy(str, Enum):
    REUSE_ACTIVE = 'reuse_active'
    CONFIRM_EACH = 'confirm_each'


class EscapeOutcome(str, Enum):
    CANCEL_PROVISIONAL = 'cancel_provisional'
    SELECT_TOOL = 'select_tool'
    NOOP = 'noop'


@dataclass(frozen=True)
class WorkflowSnapshot:
    active_class: object = None
    prompt_policy: PromptPolicy = PromptPolicy.REUSE_ACTIVE
    active_tool: AnnotationTool = AnnotationTool.SELECT
    provisional: bool = False


class AnnotationWorkflow:
    def __init__(self, prompt_policy=PromptPolicy.REUSE_ACTIVE):
        self._state = WorkflowSnapshot(prompt_policy=PromptPolicy(prompt_policy))

    @property
    def snapshot(self):
        return self._state

    def start_session(self):
        self._state = WorkflowSnapshot(prompt_policy=self._state.prompt_policy)

    def navigate(self):
        return self._state

    def set_active_class(self, label):
        value = str(label).strip() or None
        self._state = replace(self._state, active_class=value)

    def set_prompt_policy(self, policy):
        self._state = replace(
            self._state, prompt_policy=PromptPolicy(policy))

    def set_tool(self, tool):
        self._state = replace(self._state, active_tool=AnnotationTool(tool))

    def begin_provisional(self):
        self._state = replace(self._state, provisional=True)

    def finish_provisional(self):
        self._state = replace(self._state, provisional=False)

    def escape(self):
        if self._state.provisional:
            self.finish_provisional()
            return EscapeOutcome.CANCEL_PROVISIONAL
        if self._state.active_tool is not AnnotationTool.SELECT:
            self.set_tool(AnnotationTool.SELECT)
            return EscapeOutcome.SELECT_TOOL
        return EscapeOutcome.NOOP
```

- [ ] **Step 4: Run the workflow tests**

Run: `pytest -q tests/core/test_annotation_workflow.py`

Expected: PASS.

- [ ] **Step 5: Commit the state owner**

```bash
git add libs/core/annotation_workflow.py tests/core/test_annotation_workflow.py
git commit -m "feat: add annotation workflow state"
```

### Task 2: Active class control and prompt policy

**Files:**
- Create: `libs/widgets/activeClassControl.py`
- Create: `tests/widgets/test_active_class_control.py`
- Modify: `labelImgPlusPlus.py:331-369`
- Modify: `libs/core/workspace_settings.py:1-44`
- Modify: `libs/utils/constants.py`

**Interfaces:**
- Consumes: `AnnotationWorkflow.set_active_class()` and `PromptPolicy` from Task 1.
- Produces: `ActiveClassControl.classSelected(str)`, `policyChanged(str)`, `set_choices(iterable)`, `choices()`, `set_active_class(Optional[str])`, and `active_class()`.

- [ ] **Step 1: Write failing widget and migration tests**

```python
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication
from libs.widgets.activeClassControl import ActiveClassControl

_APP = QApplication.instance() or QApplication([])


def test_selecting_a_class_establishes_it_immediately():
    control = ActiveClassControl()
    control.set_choices(['vehicle', 'person'])
    spy = QSignalSpy(control.classSelected)

    control.combo.setCurrentText('vehicle')
    control.combo.lineEdit().returnPressed.emit()

    assert control.active_class() == 'vehicle'
    assert spy[-1] == ['vehicle']


def test_choices_do_not_imply_a_selection():
    control = ActiveClassControl()
    control.set_choices(['vehicle'])
    assert control.active_class() is None
    assert control.combo.placeholderText() == 'Choose a class'
    assert control.choices() == ('vehicle',)
```

Add to `tests/core/test_workspace_settings.py`:

```python
def test_legacy_single_class_migrates_to_reuse_active():
    settings = {SETTING_SINGLE_CLASS: True}
    assert load_prompt_policy(settings) == 'reuse_active'
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest -q tests/widgets/test_active_class_control.py tests/core/test_workspace_settings.py`

Expected: FAIL because the control and migration function do not exist.

- [ ] **Step 3: Implement the control with no implicit selection**

```python
class ActiveClassControl(QWidget):
    classSelected = pyqtSignal(str)
    policyChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super(ActiveClassControl, self).__init__(parent)
        self.combo = QComboBox(self)
        self.combo.setEditable(True)
        self.combo.setAccessibleName('Active annotation class')
        self.combo.setPlaceholderText('Choose a class')
        self.combo.activated.connect(
            lambda _index: self._choose(self.combo.currentText()))
        self.confirm_each = QCheckBox('Ask for every object', self)
        self.confirm_each.toggled.connect(
            lambda checked: self.policyChanged.emit(
                'confirm_each' if checked else 'reuse_active'))
        self.combo.lineEdit().returnPressed.connect(self._accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Active class', self))
        layout.addWidget(self.combo)
        layout.addWidget(self.confirm_each)

    def set_choices(self, labels):
        current = self.active_class()
        self.combo.clear()
        self.combo.addItems(sorted(set(str(item) for item in labels if item)))
        self.set_active_class(current)

    def set_active_class(self, label):
        self.combo.setCurrentText(str(label)) if label else self.combo.setCurrentIndex(-1)

    def choices(self):
        return tuple(self.combo.itemText(index)
                     for index in range(self.combo.count()))

    def active_class(self):
        value = self.combo.currentText().strip()
        return value or None

    def _accept(self):
        value = self.active_class()
        if value:
            self.classSelected.emit(value)

    def _choose(self, value):
        self.set_active_class(value)
        self.classSelected.emit(str(value))
```

Replace the **Use default label** checkbox/container in `MainWindow.__init__` with `ActiveClassControl`, keeping compatibility aliases only for settings migration. Implement `load_prompt_policy(settings)` so `SETTING_SINGLE_CLASS=True` maps to `reuse_active`; otherwise use the new validated key and default to `reuse_active`.

- [ ] **Step 4: Run widget and settings tests**

Run: `pytest -q tests/widgets/test_active_class_control.py tests/core/test_workspace_settings.py`

Expected: PASS.

- [ ] **Step 5: Commit the active-class surface**

```bash
git add libs/widgets/activeClassControl.py libs/core/workspace_settings.py libs/utils/constants.py labelImgPlusPlus.py tests/widgets/test_active_class_control.py tests/core/test_workspace_settings.py
git commit -m "feat: add persistent active class control"
```

### Task 3: Project workflow state into continuous drawing

**Files:**
- Modify: `labelImgPlusPlus.py:2192-2415`
- Modify: `labelImgPlusPlus.py:3299-3414`
- Modify: `labelImgPlusPlus.py:5526-5610`
- Modify: `libs/widgets/canvas.py:154-190`
- Modify: `libs/widgets/canvas.py:1437-1510`
- Modify: `libs/widgets/canvas.py:1592-1629`
- Modify: `tests/integration/test_main_window.py`
- Modify: `tests/integration/test_inline_class_picker.py`
- Modify: `tests/widgets/test_canvas.py`

**Interfaces:**
- Consumes: `AnnotationWorkflow` and `ActiveClassControl` from Tasks 1-2.
- Produces: `MainWindow._apply_workflow_state()`, `_start_interaction_session()`, and `Canvas.flash_committed_shape(shape, duration_ms=350)`.

- [ ] **Step 1: Replace transient-tool expectations with failing continuous-flow tests**

```python
def _wait(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def _write_image(path):
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(path))


def test_rectangle_class_and_tool_survive_commit_and_navigation(tmp_path):
    first, second = tmp_path / 'a.png', tmp_path / 'b.png'
    _write_image(first)
    _write_image(second)
    app, window = get_main_app()
    try:
        assert window.import_dir_images(str(tmp_path))
        window._active_class_selected('vehicle')
        window.activate_box_tool()
        window.canvas.commit_rectangle((2, 2, 20, 20))
        app.processEvents()
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert window.canvas.mode == window.canvas.CREATE
        assert window.canvas.selected_shape is None

        window.request_next_image()
        assert _wait(app, lambda: window.file_path == str(second))
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.canvas.mode == window.canvas.CREATE
    finally:
        window.dirty = False
        window.close()
```

```python
def test_new_dataset_clears_selection_but_retains_class_choices(tmp_path):
    first_dir, second_dir = tmp_path / 'one', tmp_path / 'two'
    first_dir.mkdir()
    second_dir.mkdir()
    _write_image(first_dir / 'a.png')
    _write_image(second_dir / 'b.png')
    app, window = get_main_app()
    try:
        assert window.import_dir_images(str(first_dir))
        window._active_class_selected('vehicle')
        window.activate_polygon_tool()
        assert window.import_dir_images(str(second_dir))
        app.processEvents()
        assert window.workflow.snapshot.active_class is None
        assert window.workflow.snapshot.active_tool is AnnotationTool.SELECT
        assert 'vehicle' in window.active_class_control.choices()
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 2: Run the focused integration tests and observe the old reset behavior**

Run: `pytest -q tests/integration/test_main_window.py -k 'survive_commit or new_dataset' tests/integration/test_inline_class_picker.py`

Expected: FAIL because rectangle commit calls `activate_select_tool()` and workflow state is not projected.

- [ ] **Step 3: Wire one synchronization path**

Instantiate `self.workflow = AnnotationWorkflow(load_prompt_policy(settings))`. Route all tool entry points through:

```python
def _apply_workflow_state(self):
    state = self.workflow.snapshot
    projection = {
        AnnotationTool.SELECT: lambda: self.canvas.set_editing(True),
        AnnotationTool.RECTANGLE: lambda: self.canvas.set_editing(False),
        AnnotationTool.POLYGON: lambda: self.canvas.set_polygon_drawing(True),
    }
    projection.get(state.active_tool, projection[AnnotationTool.SELECT])()
    self.active_class_control.set_active_class(state.active_class)
    self._sync_tool_actions()

def _start_interaction_session(self):
    self.workflow.start_session()
    self._apply_workflow_state()
```

Update `activate_select_tool`, `activate_box_tool`, and `activate_polygon_tool` to change `workflow` first and then call `_apply_workflow_state()`. Call `workflow.navigate()` after an image frame commits. Call `_start_interaction_session()` only when a standalone image, a different directory, a video, or a project replaces the session.

In `_commit_provisional_shape`, resolve `workflow.snapshot.active_class` before opening the picker, call `workflow.finish_provisional()`, keep the active drawing tool, clear canvas selection, and call `canvas.flash_committed_shape(shape)`. Do not call `activate_select_tool()` after Rectangle.

- [ ] **Step 4: Implement non-editable commit highlight**

```python
def flash_committed_shape(self, shape, duration_ms=350):
    self._commit_highlight = shape
    self.update()
    QTimer.singleShot(duration_ms, self._clear_commit_highlight)

def _clear_commit_highlight(self):
    self._commit_highlight = None
    self.update()
```

Paint `_commit_highlight` with a thicker outline and no vertex/edit handles. Explicit object selection must still enter Select through `activate_select_tool()`.

- [ ] **Step 5: Run the workflow and canvas tests**

Run: `pytest -q tests/core/test_annotation_workflow.py tests/widgets/test_canvas.py tests/integration/test_inline_class_picker.py tests/integration/test_main_window.py -k 'workflow or class or tool or provisional or commit or navigation'`

Expected: PASS.

- [ ] **Step 6: Commit continuous drawing**

```bash
git add labelImgPlusPlus.py libs/widgets/canvas.py tests/integration/test_main_window.py tests/integration/test_inline_class_picker.py tests/widgets/test_canvas.py
git commit -m "feat: keep class and drawing tool active"
```

### Task 4: Revision-safe continuous save coordinator

**Files:**
- Create: `libs/core/continuous_save.py`
- Create: `tests/core/test_continuous_save.py`
- Modify: `labelImgPlusPlus.py:1667-1704`
- Modify: `labelImgPlusPlus.py:3049-3125`
- Modify: `labelImgPlusPlus.py:3891-3998`
- Modify: `labelImgPlusPlus.py:6757-6872`
- Replace obsolete expectations in: `tests/integration/test_autosave.py`

**Interfaces:**
- Consumes: document key, dataset generation, and monotonically increasing revision from `MainWindow`/`VideoProjectModel`.
- Produces: immutable `SaveTicket`, `ContinuousSaveCoordinator.saveRequested(object)`, `stateChanged(str)`, `drained()`, `reset()`, `mark_dirty()`, `flush()`, `complete()`, `fail()`, and `retry()`.

- [ ] **Step 1: Write failing coordinator tests**

```python
from PyQt5.QtTest import QSignalSpy
from PyQt5.QtWidgets import QApplication
from libs.core.continuous_save import ContinuousSaveCoordinator

_APP = QApplication.instance() or QApplication([])


def test_mutations_coalesce_and_late_completion_cannot_clean_newer_revision():
    coordinator = ContinuousSaveCoordinator(delay_ms=20)
    coordinator.reset('image:/a.png', generation=4, durable_revision=0)
    requested = QSignalSpy(coordinator.saveRequested)

    coordinator.mark_dirty(1)
    coordinator.mark_dirty(2)
    assert requested.wait(1000)
    first = requested[0][0]
    assert first.revision == 2

    coordinator.mark_dirty(3)
    coordinator.complete(first)
    if len(requested) < 2:
        assert requested.wait(1000)
    assert requested[1][0].revision == 3
    assert coordinator.state == 'saving'


def test_failed_save_stays_dirty_until_explicit_retry():
    coordinator = ContinuousSaveCoordinator(delay_ms=1)
    coordinator.reset('image:/a.png', 1, 0)
    requested = QSignalSpy(coordinator.saveRequested)
    coordinator.mark_dirty(1)
    assert requested.wait(1000)
    coordinator.fail(requested[0][0], 'disk full')
    assert coordinator.state == 'failed'
    coordinator.retry()
    if len(requested) < 2:
        assert requested.wait(1000)
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest -q tests/core/test_continuous_save.py`

Expected: FAIL because `libs.core.continuous_save` does not exist.

- [ ] **Step 3: Implement ticketed scheduling**

```python
@dataclass(frozen=True)
class SaveTicket:
    document_key: str
    generation: int
    revision: int


class ContinuousSaveCoordinator(QObject):
    saveRequested = pyqtSignal(object)
    stateChanged = pyqtSignal(str)
    drained = pyqtSignal()

    def __init__(self, delay_ms=250, parent=None):
        super(ContinuousSaveCoordinator, self).__init__(parent)
        self.delay_ms = int(delay_ms)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        self._state = 'saved'
        self._document_key = ''
        self._generation = 0
        self._durable_revision = 0
        self._newest_revision = 0
        self._in_flight = None
        self.error = None

    @property
    def state(self):
        return self._state

    def _set_state(self, value):
        if value != self._state:
            self._state = value
            self.stateChanged.emit(value)

    def reset(self, document_key, generation, durable_revision=0):
        self._timer.stop()
        self._document_key = str(document_key)
        self._generation = int(generation)
        self._durable_revision = int(durable_revision)
        self._newest_revision = int(durable_revision)
        self._in_flight = None
        self.error = None
        self._set_state('saved')

    def mark_dirty(self, revision):
        self._newest_revision = max(self._newest_revision, int(revision))
        self._set_state('pending')
        if self._in_flight is None:
            self._timer.start(self.delay_ms)

    def flush(self):
        self._timer.stop()
        if self._in_flight is None and self._newest_revision > self._durable_revision:
            ticket = SaveTicket(self._document_key, self._generation,
                                self._newest_revision)
            self._in_flight = ticket
            self._set_state('saving')
            self.saveRequested.emit(ticket)

    def complete(self, ticket):
        if ticket != self._in_flight:
            return
        self._durable_revision = max(self._durable_revision, ticket.revision)
        self._in_flight = None
        if self._newest_revision > self._durable_revision:
            self.flush()
        else:
            self._set_state('saved')
            self.drained.emit()

    def fail(self, ticket, message):
        if ticket != self._in_flight:
            return
        self._in_flight = None
        self.error = str(message)
        self._set_state('failed')

    def retry(self):
        if self._state != 'failed':
            return
        self.error = None
        self._set_state('pending')
        self.flush()
```

Reject `complete()`/`fail()` tickets whose document key or generation differs from the current reset state. This invalidates late work from a replaced document while `retry()` re-emits only the newest revision.

- [ ] **Step 4: Integrate every completed mutation boundary**

Connect `saveRequested` to `_dispatch_continuous_save(ticket)`. Image saves build the existing immutable `SaveRequest`; video saves use the current `VideoSaveRequest`. Pass the ticket into result/error callbacks and call `complete(ticket)` only after atomic publication succeeds.

Change `set_dirty()` to increment/obtain the finished model revision and call `continuous_save.mark_dirty(revision)`. Keep drag motion out of `set_dirty()`; use only `shapeMoveFinished`, `polygonVerticesEdited`, and `keypointsEdited`. Route shape commit, edit completion, relabel, delete, verification, accepted Assist/propagation, undo, and redo through the same boundary.

Project the exact copy `Saving…`, `Saved`, or `Save failed · Retry` into the command/status surfaces. Replace the two primary autosave actions with one checkable `self.save_changes_automatically` action labelled **Save changes automatically**; disable automatic dispatch only when it is false and retain the existing Save/Discard/Cancel navigation safeguard.

- [ ] **Step 5: Replace old timer/navigation tests with continuous-save contracts**

```python
def _wait(app, predicate, timeout_ms=3000):
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


def test_shape_commit_creates_sidecar_without_navigation(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'frame.png'
    image = QImage(80, 60, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.file_path == str(image_path))
        commit_rectangle(window, 'vehicle')
        sidecar = image_path.with_suffix('.xml')
        assert _wait(app, sidecar.exists)
        assert window.continuous_save.state == 'saved'
    finally:
        window.dirty = False
        window.close()


def test_mid_drag_does_not_schedule_a_save(tmp_path):
    app, window = get_main_app()
    try:
        requested = QSignalSpy(window.continuous_save.saveRequested)
        event = QMouseEvent(
            QEvent.MouseMove, QPointF(20, 20), Qt.NoButton, Qt.LeftButton,
            Qt.NoModifier)
        window.canvas.mouseMoveEvent(event)
        app.processEvents()
        assert len(requested) == 0
    finally:
        window.dirty = False
        window.close()


def test_disabled_automatic_save_uses_navigation_safeguard(monkeypatch,
                                                           tmp_path):
    app, window = get_main_app()
    for name in ('a.png', 'b.png'):
        image = QImage(40, 30, QImage.Format_RGB32)
        image.fill(Qt.white)
        assert image.save(str(tmp_path / name))
    try:
        assert window.import_dir_images(str(tmp_path))
        window.save_changes_automatically.setChecked(False)
        window.dirty = True
        window.continuous_save.mark_dirty(1)
        QApplication.processEvents()
        assert window.continuous_save.state == 'pending'
        with monkeypatch.context() as patcher:
            patcher.setattr(
                window, 'discard_changes_dialog',
                lambda: QMessageBox.Cancel)
            current = window.file_path
            window.request_next_image()
            app.processEvents()
            assert window.file_path == current
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 6: Run save tests**

Run: `pytest -q tests/core/test_continuous_save.py tests/core/test_save_pipeline.py tests/integration/test_autosave.py tests/integration/test_main_window.py -k 'save or dirty or navigation or undo or redo or verify'`

Expected: PASS.

- [ ] **Step 7: Commit continuous saving**

```bash
git add libs/core/continuous_save.py labelImgPlusPlus.py tests/core/test_continuous_save.py tests/integration/test_autosave.py
git commit -m "feat: save completed mutations continuously"
```

### Task 5: Authoritative view transform and deferred fit

**Files:**
- Create: `libs/core/view_transform.py`
- Create: `tests/core/test_view_transform.py`
- Modify: `libs/widgets/view_scaling.py:1-43`
- Modify: `labelImgPlusPlus.py:5856-5885`
- Modify: `labelImgPlusPlus.py:3413-3475`
- Modify: `tests/widgets/test_view_scaling.py`
- Modify: `tests/integration/test_main_window.py`

**Interfaces:**
- Consumes: viewport/pixmap dimensions and explicit user zoom commands.
- Produces: `ViewMode`, `ViewProjection`, `ViewTransform.start_session()`, `choose_fit_window()`, `choose_fit_width()`, `choose_manual(percent)`, and `project(viewport, pixmap)`.

- [ ] **Step 1: Write failing pure-state tests**

```python
from libs.core.view_transform import ViewMode, ViewTransform


def test_fit_mode_reprojects_but_manual_zoom_survives_navigation():
    state = ViewTransform()
    state.choose_fit_window()
    assert state.project((800, 600), (1600, 1200)).percent == 50
    assert state.project((600, 600), (1600, 1200)).percent == 37

    state.choose_manual(125)
    assert state.project((600, 600), (900, 900)).percent == 125
    assert state.mode is ViewMode.MANUAL
```

- [ ] **Step 2: Run view tests**

Run: `pytest -q tests/core/test_view_transform.py tests/widgets/test_view_scaling.py`

Expected: FAIL because the state owner is missing.

- [ ] **Step 3: Implement the view state owner**

```python
class ViewMode(str, Enum):
    FIT_WINDOW = 'fit_window'
    FIT_WIDTH = 'fit_width'
    MANUAL = 'manual'


@dataclass(frozen=True)
class ViewProjection:
    mode: ViewMode
    percent: int


class ViewTransform:
    def __init__(self):
        self.mode = ViewMode.FIT_WINDOW
        self.manual_percent = 100

    def start_session(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_window(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_width(self):
        self.mode = ViewMode.FIT_WIDTH

    def choose_manual(self, percent):
        self.mode = ViewMode.MANUAL
        self.manual_percent = max(1, min(500, int(percent)))

    def project(self, viewport, pixmap):
        if self.mode is ViewMode.MANUAL:
            return ViewProjection(self.mode, self.manual_percent)
        scale = (view_scaling.fit_width_scale(viewport[0], pixmap[0])
                 if self.mode is ViewMode.FIT_WIDTH else
                 view_scaling.fit_window_scale(
                     viewport[0], viewport[1], pixmap[0], pixmap[1]))
        return ViewProjection(self.mode, max(1, int(scale * 100)))
```

Use explicit width/height arguments in production rather than tuple slicing if that is clearer; preserve the exact public signatures above.

- [ ] **Step 4: Project after final layout and inspector changes**

Replace `adjust_scale(initial=True)` with `_schedule_view_projection()`, which coalesces `QTimer.singleShot(0, self._apply_view_projection)` calls. Measure `scroll_area.viewport().size()`, not the full central widget. Fit-mode projection runs after pixmap commit, window resize, inspector collapse/open, inspector width change, and responsive breakpoint transitions. Manual mode preserves zoom and restores normalized scroll ratios for video frames; image navigation keeps percentage and centers within valid bounds.

- [ ] **Step 5: Add the clipped-frame regression test**

```python
def test_initial_fit_uses_final_canvas_viewport(tmp_path):
    app, window = get_main_app()
    image_path = tmp_path / 'wide.png'
    image = QImage(1600, 900, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        window.resize(800, 600)
        window.show()
        window.request_open_file(str(image_path), skip_prompt=True)
        assert _wait(app, lambda: window.canvas.pixmap is not None)
        app.processEvents()
        viewport = window.scroll_area.viewport().rect()
        painted_width = window.canvas.pixmap.width() * window.canvas.scale
        painted_height = window.canvas.pixmap.height() * window.canvas.scale
        assert painted_width <= viewport.width() + 1
        assert painted_height <= viewport.height() + 1
        assert window.actions.fitWindow.isChecked()
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 6: Run view suites**

Run: `pytest -q tests/core/test_view_transform.py tests/widgets/test_view_scaling.py tests/integration/test_main_window.py -k 'fit or zoom or viewport or inspector'`

Expected: PASS.

- [ ] **Step 7: Commit authoritative view state**

```bash
git add libs/core/view_transform.py libs/widgets/view_scaling.py labelImgPlusPlus.py tests/core/test_view_transform.py tests/widgets/test_view_scaling.py tests/integration/test_main_window.py
git commit -m "fix: make canvas fitting authoritative"
```

### Task 6: Responsive inspector drawer

**Files:**
- Modify: `libs/widgets/workspaceInspector.py:21-181`
- Modify: `libs/core/workspace_settings.py:9-44`
- Modify: `labelImgPlusPlus.py:1180-1250`
- Modify: `tests/integration/test_workspace_inspector.py`
- Modify: `tests/integration/test_workspace_accessibility.py`

**Interfaces:**
- Consumes: `WorkspaceSplitterShell.set_available_width(width)` and existing inspector preference.
- Produces: `layoutModeChanged(str)`, `open_inspector()`, `close_inspector()`, `layout_mode` (`docked` or `drawer`), and a reopen affordance whose accessible name includes object count.

- [ ] **Step 1: Write failing breakpoint/focus tests**

```python
def test_inspector_becomes_dismissible_drawer_below_960(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'drawer'
        assert window.workspace_inspector.isHidden()

        window.workspace_shell.reopen_button.click()
        QApplication.processEvents()
        assert window.workspace_inspector.isVisible()
        assert window.workspace_inspector.tabs.hasFocus()
        QTest.keyClick(window.workspace_inspector, Qt.Key_Escape)
        QApplication.processEvents()
        assert window.workspace_inspector.isHidden()
        assert window.workspace_shell.reopen_button.hasFocus()
    finally:
        _close(window)


def test_crossing_breakpoint_does_not_overwrite_wide_preference(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.workspace_shell.set_inspector_collapsed(False)
        window.resize(800, 600)
        QApplication.processEvents()
        window.resize(1200, 700)
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'docked'
        assert not window.workspace_shell.is_inspector_collapsed()
    finally:
        _close(window)
```

- [ ] **Step 2: Run inspector tests**

Run: `pytest -q tests/integration/test_workspace_inspector.py tests/integration/test_workspace_accessibility.py -k 'drawer or breakpoint or inspector'`

Expected: FAIL because only a splitter mode exists.

- [ ] **Step 3: Implement dock/drawer projection**

Add a `QStackedLayout`-style overlay container or reparent-safe overlay host inside `WorkspaceSplitterShell`. At `width < scale_px(960)`, hide the splitter's inspector pane and show the same `WorkspaceInspector` as a right-side overlay above a scrim; do not create a second inspector. At wider widths, return it to the splitter and restore `_wide_collapsed_preference`.

```python
def set_available_width(self, width):
    mode = 'drawer' if int(width) < 960 else 'docked'
    if mode == self.layout_mode:
        return
    self.layout_mode = mode
    self._project_layout_mode()
    self.layoutModeChanged.emit(mode)
```

Opening moves focus to `inspector.tabs`. Escape, Close, and scrim click call `close_inspector()` and focus `reopen_button`. Use an event filter to keep Tab/Shift+Tab inside the visible drawer. The reopen accessible name is `Open inspector, N objects`.

- [ ] **Step 4: Reproject fit after geometry settles**

Connect `layoutModeChanged`, `inspectorCollapsedChanged`, and splitter movement completion to `MainWindow._schedule_view_projection()` from Task 5. Do not write the drawer's temporary closed state into `SETTING_INSPECTOR_COLLAPSED`.

- [ ] **Step 5: Run responsive and accessibility tests**

Run: `pytest -q tests/integration/test_workspace_inspector.py tests/integration/test_workspace_accessibility.py tests/integration/test_main_window.py -k 'inspector or drawer or fit or focus'`

Expected: PASS.

- [ ] **Step 6: Commit the responsive inspector**

```bash
git add libs/widgets/workspaceInspector.py libs/core/workspace_settings.py labelImgPlusPlus.py tests/integration/test_workspace_inspector.py tests/integration/test_workspace_accessibility.py
git commit -m "feat: add responsive inspector drawer"
```

### Task 7: Image-workflow slice acceptance

**Files:**
- Create: `tests/integration/test_continuous_image_flow.py`
- Create: `tools/ux/capture_workspace_matrix.py`
- Modify: `docs/testing/ux-remediation-2026-08-23.md`
- Modify: `docs/screenshots/README.md`

**Interfaces:**
- Consumes: all public interfaces produced by Tasks 1-6.
- Produces: one end-to-end regression suite plus `capture_scenario(window, scenario, size, theme, output_dir) -> str`, which later plans extend with video and Assist scenarios.

- [ ] **Step 1: Write the full four-frame acceptance test**

```python
def _make_four_frames(directory):
    for index in range(1, 5):
        image = QImage(160, 120, QImage.Format_RGB32)
        image.fill(Qt.white)
        assert image.save(str(directory / ('frame-%s.png' % index)))


def _commit_rectangle(window, bounds):
    window.canvas.commit_rectangle(bounds)
    QApplication.processEvents()


def test_choose_once_draw_twice_navigate_save_reopen(tmp_path):
    _make_four_frames(tmp_path)
    app, window = get_main_app()
    try:
        assert window.import_dir_images(str(tmp_path))
        window._active_class_selected('vehicle')
        window.activate_box_tool()
        _commit_rectangle(window, (5, 5, 30, 30))
        _commit_rectangle(window, (40, 10, 70, 45))

        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert _wait(app, lambda: window.continuous_save.state == 'saved')

        window.request_next_image()
        assert _wait(app, lambda: window.cur_img_idx == 1)
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert window.view_transform.mode is ViewMode.FIT_WINDOW
        assert (tmp_path / 'frame-1.xml').exists()
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 2: Run the complete image-focused suite**

Run: `pytest -q tests/core tests/widgets tests/integration -k 'not video and not sam'`

Expected: PASS with no test preserving transient Rectangle or timer-only autosave behavior.

- [ ] **Step 3: Add and run the initial image screenshot harness**

Implement `capture_scenario()` with the stable naming contract used in the integrated hardening plan:

```python
def capture_scenario(window, scenario, size, theme, output_dir):
    window.resize(*size)
    window._apply_theme(Theme.DARK if theme == 'dark' else Theme.LIGHT)
    IMAGE_SCENARIOS[scenario](window)
    QApplication.processEvents()
    filename = '%s-%s-%sx%s.png' % (
        scenario, theme, size[0], size[1])
    path = os.path.join(output_dir, filename)
    assert window.grab().save(path, 'PNG')
    return path
```

Run it at `800x600`, `960x640`, `1366x768`, and `1440x900`. Capture empty workspace, first image fit, two committed rectangles with Rectangle still active, inspector drawer open/closed, Saving, Saved, and Save failed states. Store the named artifacts under `docs/screenshots/continuous-workflow-2026-08-24/` and list them in `docs/screenshots/README.md`.

- [ ] **Step 4: Commit the slice acceptance evidence**

```bash
git add tests/integration/test_continuous_image_flow.py tools/ux/capture_workspace_matrix.py docs/testing/ux-remediation-2026-08-23.md docs/screenshots/README.md docs/screenshots/continuous-workflow-2026-08-24
git commit -m "test: cover continuous image annotation flow"
```

- [ ] **Step 5: Gate the next plan**

Run: `git status --short && pytest -q`

Expected: the intended pre-existing worktree changes are understood, the new slice commits are present, and the complete base suite passes before beginning `2026-08-24-video-workspace.md`.
