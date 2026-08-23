# Video Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing PTS-accurate decoder into a responsive, accessible, crash-resistant video annotation workspace that works with every supplied VFR video.

**Architecture:** Preserve the immutable `VideoFrameRef`, serialized decoder lane, and SQLite project model. Add explicit optional-runtime onboarding, make `VideoTimelineWidget` a projection of user intent rather than a source of playback state, stage propagation as reviewable pending data, and replace blocking teardown with a bounded asynchronous shutdown coordinator.

**Tech Stack:** Python 3.8+, PyQt5, optional PyAV/NumPy/OpenCV video extra, pytest, QtTest, SQLite video projects, existing `TaskCoordinator` and `VideoProjectModel`.

**Spec:** `docs/superpowers/specs/2026-08-24-continuous-annotation-video-design.md`

**Prerequisite:** `docs/superpowers/plans/2026-08-24-continuous-image-workflow.md` is complete and its full base suite passes.

## Global Constraints

- Variable-frame-rate stepping remains presentation-timestamp accurate.
- Video dependencies remain optional; no installation or network operation starts automatically.
- Previous frame, Play/Pause, Next frame, exact time, speed, and seek remain visible at 800 logical pixels.
- Exact time accepts only `HH:MM:SS.mmm`; invalid or out-of-range input never seeks.
- Mouse release, keyboard, and accessibility value changes emit seek intent; internal position projection never does.
- Pending propagation never becomes accepted without explicit review.
- Quit allows five seconds for graceful cancellation, then offers Wait and Force Quit; it never silently abandons work.
- The current workspace remains usable when replacement video/project opening fails.
- No annotation or video-project format changes.
- Nothing is pushed automatically.

## File Structure

- Create `libs/core/video_runtime.py`: optional dependency probe and install guidance without importing heavy modules.
- Create `libs/core/shutdown_coordinator.py`: asynchronous five-second graceful shutdown state.
- Create `libs/widgets/videoSetupCard.py`: in-app missing-runtime surface.
- Modify `libs/widgets/videoTimelineWidget.py`: exact input, semantic transport, responsive Track menu, and marker semantics.
- Modify `libs/core/video_model.py`: stage pending propagation and review it explicitly.
- Modify `libs/core/task_coordinator.py`: named active-job inspection and nonblocking cancellation/polling.
- Modify `labelImgPlusPlus.py`: transactional runtime/open flow, timeline projection, propagation review, and close orchestration.
- Add/modify tests under `tests/video`, `tests/core`, `tests/widgets`, and `tests/integration`.

---

### Task 1: Optional video-runtime onboarding

**Files:**
- Create: `libs/core/video_runtime.py`
- Create: `libs/widgets/videoSetupCard.py`
- Create: `tests/core/test_video_runtime.py`
- Create: `tests/widgets/test_video_setup_card.py`
- Modify: `libs/core/video_decoder.py:13-37`
- Modify: `libs/core/video_session.py:1-69`
- Modify: `labelImgPlusPlus.py:3618-3828`
- Modify: `labelImgPlusPlus.py:6735-6770`
- Modify: `libs/widgets/workspacePages.py:98-225`

**Interfaces:**
- Consumes: `importlib.util.find_spec` and the existing video extra command.
- Produces: `VideoRuntimeStatus`, `probe_video_runtime()`, and `VideoSetupCard.chooseAnotherRequested`; `MainWindow._show_video_runtime_setup(path, status)` uses them before submitting decoder work.

- [ ] **Step 1: Write failing probe and UI tests**

```python
from libs.core.video_runtime import probe_video_runtime


def test_runtime_probe_names_missing_components_without_importing_them(monkeypatch):
    monkeypatch.setattr(
        'libs.core.video_runtime.importlib.util.find_spec',
        lambda name: None if name == 'av' else object())
    status = probe_video_runtime()
    assert status.available is False
    assert status.missing == ('av',)
    assert status.install_command == 'pip install "labelimgplusplus[video]"'
```

```python
def test_setup_card_explains_and_copies_but_never_installs(monkeypatch):
    card = VideoSetupCard()
    card.set_status(VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av'))
    assert 'video annotation' in card.explanation.text().lower()
    assert card.install_command.text() == \
        'pip install "labelimgplusplus[video]"'
    assert not hasattr(card, 'install_button')
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest -q tests/core/test_video_runtime.py tests/widgets/test_video_setup_card.py`

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement a side-effect-free runtime probe**

```python
@dataclass(frozen=True)
class VideoRuntimeStatus:
    available: bool
    missing: tuple
    install_command: str
    detail: str


def probe_video_runtime(required=('av', 'numpy')):
    missing = tuple(
        name for name in required if importlib.util.find_spec(name) is None)
    command = 'pip install "labelimgplusplus[video]"'
    detail = ('Ready' if not missing else
              'Missing optional component%s: %s' % (
                  '' if len(missing) == 1 else 's', ', '.join(missing)))
    return VideoRuntimeStatus(not missing, missing, command, detail)
```

`VideoSetupCard` contains a heading, explanation, missing-component detail, read-only selectable command, Copy, and **Choose another file**. Copy uses `QApplication.clipboard()`; no subprocess or package installer API is present.

- [ ] **Step 4: Gate video opening transactionally**

Before `request_open_video()` allocates a generation or replaces visible state, call `probe_video_runtime()`. If unavailable, keep the current document intact and present the setup card in the workspace overlay. Choosing another file reopens the file chooser; closing the card returns focus to the canvas/current page. Keep `VideoDependencyError` as a race-safe fallback if imports disappear after probing.

- [ ] **Step 5: Run opening tests**

Run: `pytest -q tests/core/test_video_runtime.py tests/widgets/test_video_setup_card.py tests/video/test_opening.py -k 'dependency or runtime or failed or transactional'`

Expected: PASS and no test observes an automatic install attempt.

- [ ] **Step 6: Commit runtime onboarding**

```bash
git add libs/core/video_runtime.py libs/widgets/videoSetupCard.py libs/core/video_decoder.py libs/core/video_session.py libs/widgets/workspacePages.py labelImgPlusPlus.py tests/core/test_video_runtime.py tests/widgets/test_video_setup_card.py tests/video/test_opening.py
git commit -m "feat: explain optional video setup"
```

### Task 2: Exact time and complete seek semantics

**Files:**
- Modify: `libs/widgets/videoTimelineWidget.py:1-278`
- Modify: `tests/video/test_timeline.py`
- Modify: `tests/video/test_navigation.py`

**Interfaces:**
- Consumes: `VideoSessionSnapshot` and immutable `VideoFrameRef`.
- Produces: canonical `parse_timecode()`, `VideoTimelineWidget.seekRequested(VideoFrameRef)`, `timeInputError(str)`, `restore_time_editor()`, and projection guard `_projecting_position`.

- [ ] **Step 1: Write failing validator and seek-source tests**

```python
@pytest.fixture
def video_snapshot(tmp_path, make_video):
    decoder = VideoDecoderSession(make_video(tmp_path / 'timeline.mp4'))
    first = decoder.decode_first()
    snapshot = decoder.snapshot(None, first)
    decoder.close()
    return snapshot


@pytest.mark.parametrize('value', [
    '00:00:02.000d', '0:00:02.000', '00:60:00.000', '00:00:60.000',
])
def test_timecode_rejects_noncanonical_values(value):
    with pytest.raises(ValueError):
        parse_timecode(value)


def test_accessibility_style_value_change_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    widget.set_session(video_snapshot)
    spy = QSignalSpy(widget.seekRequested)
    widget.slider.setValue(TIMELINE_MAX // 2)
    if not spy:
        assert spy.wait(100)
    assert len(spy) == 1


def test_internal_position_projection_never_emits_seek(video_snapshot):
    widget = VideoTimelineWidget()
    widget.set_session(video_snapshot)
    spy = QSignalSpy(widget.seekRequested)
    widget.set_current_frame(video_snapshot.initial_frame.frame_ref)
    QApplication.processEvents()
    assert len(spy) == 0
```

Add tests proving out-of-range Return emits `timeInputError`, does not emit seek, and keeps the invalid value visible; Escape restores the current displayed time and focuses the canvas through the connected MainWindow handler.

- [ ] **Step 2: Run the timeline tests**

Run: `pytest -q tests/video/test_timeline.py -k 'timecode or accessibility or projection or escape'`

Expected: FAIL because parsing accepts suffixes through `float()` and non-drag slider changes emit nothing.

- [ ] **Step 3: Implement canonical parsing and range checks**

```python
_TIMECODE = re.compile(r'^(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})$')


def parse_timecode(value):
    match = _TIMECODE.fullmatch(str(value).strip())
    if match is None:
        raise ValueError('Use HH:MM:SS.mmm')
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0
```

Attach a `QRegularExpressionValidator`/`QRegExpValidator` compatible with the existing Qt fallback pattern. In `_emit_time_seek()`, compare the parsed seconds with the snapshot duration; on failure emit `timeInputError` and leave text/focus in place. Escape calls `restore_time_editor()` and emits a focus-return signal.

- [ ] **Step 4: Separate internal projection from user intent**

Set `_projecting_position=True` only around `set_current_frame()` slider updates. `_slider_changed()` starts the 50 ms debounce whenever `_projecting_position` is false, whether the source is mouse, keyboard, or an accessibility value action. `_slider_released()` always stops the debounce and emits the final value once.

- [ ] **Step 5: Run timeline and navigation tests**

Run: `pytest -q tests/video/test_timeline.py tests/video/test_navigation.py -k 'seek or time or frame or pts'`

Expected: PASS.

- [ ] **Step 6: Commit complete seek semantics**

```bash
git add libs/widgets/videoTimelineWidget.py tests/video/test_timeline.py tests/video/test_navigation.py
git commit -m "fix: complete video seek semantics"
```

### Task 3: Semantic transport and responsive control hierarchy

**Files:**
- Modify: `libs/widgets/videoTimelineWidget.py:76-223`
- Modify: `libs/widgets/commandBar.py:154-181`
- Modify: `labelImgPlusPlus.py:5357-5415`
- Modify: `labelImgPlusPlus.py:1775-1805`
- Modify: `tests/video/test_timeline.py`
- Modify: `tests/integration/test_command_bar.py`

**Interfaces:**
- Consumes: `set_playing(bool)`, existing propagation actions, and widget width.
- Produces: exact accessible action name/tooltip/icon state, `layout_mode` (`wide`/`compact`), and named `Track` menu.

- [ ] **Step 1: Write failing semantic and 800-pixel layout tests**

```python
def test_play_button_names_the_current_action():
    widget = VideoTimelineWidget()
    widget.set_playing(False)
    assert widget.play_button.accessibleName() == 'Play video'
    assert widget.play_button.toolTip().startswith('Play video')
    widget.set_playing(True)
    assert widget.play_button.accessibleName() == 'Pause video'


def test_compact_timeline_keeps_essential_controls_visible():
    widget = VideoTimelineWidget()
    widget.resize(748, 96)
    widget.show()
    QApplication.processEvents()
    assert widget.layout_mode == 'compact'
    assert all(control.isVisible() for control in (
        widget.previous_button, widget.play_button, widget.next_button,
        widget.time_edit, widget.speed_combo, widget.slider,
    ))
    assert widget.track_button.isVisible()
```

- [ ] **Step 2: Run responsive timeline tests**

Run: `pytest -q tests/video/test_timeline.py -k 'play_button or compact or essential'`

Expected: FAIL because the accessible name is empty and propagation buttons compress in one row.

- [ ] **Step 3: Rebuild the timeline as two logical rows**

Place `_MarkerSlider` in a full-width first row and transport/context in the second row. Give Previous, Play/Pause, Next, time, and speed fixed minimum target sizes of 32×32 logical pixels but zero artificial aggregate minimum width. Put propagation actions in `track_menu`; show direct Track buttons only in wide mode. The primary position is `Frame ~N · HH:MM:SS.mmm`; raw PTS appears in the tooltip.

```python
def set_playing(self, playing):
    self._playing = bool(playing)
    verb = 'Pause' if self._playing else 'Play'
    self.play_button.setAccessibleName('%s video' % verb)
    self.play_button.setToolTip('%s video (Ctrl+Space)' % verb)
    self.play_button.setChecked(self._playing)
```

In `resizeEvent`, choose compact below the measured size hint required by all essentials, not screen width. Update the command bar to say **Previous document** and **Next document** for video and never expose “Image” as the video noun.

- [ ] **Step 4: Run timeline and command-bar tests**

Run: `pytest -q tests/video/test_timeline.py tests/integration/test_command_bar.py`

Expected: PASS.

- [ ] **Step 5: Commit the responsive transport**

```bash
git add libs/widgets/videoTimelineWidget.py libs/widgets/commandBar.py labelImgPlusPlus.py tests/video/test_timeline.py tests/integration/test_command_bar.py
git commit -m "feat: make video transport responsive"
```

### Task 4: Accessible timeline markers and legend

**Files:**
- Modify: `libs/widgets/videoTimelineWidget.py:39-75`
- Create: `tests/widgets/test_video_timeline_markers.py`
- Modify: `tests/video/test_timeline.py`

**Interfaces:**
- Consumes: normalized accepted, pending, verified, propagation, and gap values.
- Produces: immutable `TimelineMarkerGroup`, `_MarkerSlider.accessible_marker_summary()`, and a keyboard-reachable **Timeline legend** menu grouped by marker kind/range.

- [ ] **Step 1: Write failing non-color and accessibility tests**

```python
def test_marker_groups_have_distinct_patterns_and_accessible_counts():
    slider = _MarkerSlider()
    slider.set_markers(
        accepted=(10,), pending=(20, 30), verified=(40,), gaps=((50, 60),))
    groups = slider.marker_groups()
    assert {group.kind for group in groups} == {
        'accepted', 'pending', 'verified', 'gap'}
    assert len({group.pattern for group in groups}) == 4
    assert '2 pending' in slider.accessible_marker_summary()
```

- [ ] **Step 2: Run marker tests**

Run: `pytest -q tests/widgets/test_video_timeline_markers.py tests/video/test_timeline.py -k marker`

Expected: FAIL because current markers differ only by position/color.

- [ ] **Step 3: Implement shape/pattern semantics**

Represent groups as frozen records with `kind`, `label`, `pattern`, and normalized ranges. Paint accepted as solid ticks, pending as hollow diamonds, verified as bottom triangles, propagation as hatched spans, and gaps as crossed spans. Set the slider accessible description to the count summary.

Add a `legend_button` with a **Timeline legend** menu. Each kind is one focusable action with its count and range summary; do not add one tab stop per frame. Clicking a group action seeks to its next marker through the same `seekRequested` path.

- [ ] **Step 4: Run marker and accessibility tests**

Run: `pytest -q tests/widgets/test_video_timeline_markers.py tests/video/test_timeline.py tests/integration/test_workspace_accessibility.py -k 'marker or legend or timeline'`

Expected: PASS.

- [ ] **Step 5: Commit marker semantics**

```bash
git add libs/widgets/videoTimelineWidget.py tests/widgets/test_video_timeline_markers.py tests/video/test_timeline.py tests/integration/test_workspace_accessibility.py
git commit -m "feat: expose semantic video markers"
```

### Task 5: Reviewable propagation and truthful cancellation

**Files:**
- Modify: `libs/core/video_model.py:190-321`
- Modify: `labelImgPlusPlus.py:4163-4480`
- Modify: `libs/widgets/videoTimelineWidget.py:159-181`
- Modify: `tests/video/test_model.py`
- Modify: `tests/video/test_tracking_ui.py`
- Modify: `tests/video/test_sam2_propagation.py`

**Interfaces:**
- Consumes: `PropagationResult`, accumulated preview observations/gaps, and existing review actions.
- Produces: `VideoProjectModel.stage_propagation_result(result)`, `MainWindow.accept_pending_propagation()`, `reject_pending_propagation()`, and cancellation that stages accumulated results as pending while recording unresolved gaps.

- [ ] **Step 1: Write failing pending/review tests**

```python
def test_completed_propagation_is_pending_until_review():
    model = VideoProjectModel()
    track = _track(model)
    result = PropagationResult(
        1, 2, model.revision,
        observations=(ObservationRecord(
            track.track_id, 10, [2, 2, 12, 12], source='tracker',
            review_state='accepted', anchor=False),))
    staged = model.stage_propagation_result(result)
    assert staged.observations
    assert all(item.review_state == 'pending'
               for item in staged.observations)
    assert model.dirty

    model.review_many(
        ((item.track_id, item.pts) for item in staged.observations),
        'accepted')
    assert all(model.observations[(item.track_id, item.pts)].review_state
               == 'accepted' for item in staged.observations)
```

In `test_batches_are_preview_only_then_commit_accepted_in_one_undo_step`, add
a cancellation branch after its existing delayed batch is visible:

```python
window.cancel_video_propagation()
assert _wait(app, lambda: window._propagation_handle is None)
generated = [item for item in window.video_model.observations.values()
             if item.source == 'tracker']
assert generated
assert all(item.review_state == 'pending' for item in generated)
assert window.video_model.gaps
```

- [ ] **Step 2: Run propagation tests**

Run: `pytest -q tests/video/test_model.py tests/video/test_tracking_ui.py -k 'propagation or cancel or pending'`

Expected: FAIL because full propagation currently applies accepted observations immediately and cancellation discards preview state.

- [ ] **Step 3: Stage generated observations as pending**

Implement `stage_propagation_result()` by validating media/track identity before advancing one revision, coercing tracker observations to `review_state='pending'`, preserving all manual/accepted barriers, and storing gaps. Add `review_many(keys, state)` so one acceptance/rejection is one revision and one undo command.

On final result, stage pending values, show counts plus Accept/Reject actions, save through the continuous coordinator, and leave editing enabled. **Track selected object** is enabled only for an accepted manual anchor; **Track all anchors** remains in the Track menu.

- [ ] **Step 4: Make cancellation durable and explicit**

When Cancel is selected, cancel the worker, convert accumulated preview batches to one pending `PropagationResult`, derive gap records for unresolved requested intervals, stage them, clear the visual preview, and restore editing. Previously accepted durable results are untouched. If no batch arrived, record only unresolved gaps; never manufacture accepted observations.

- [ ] **Step 5: Run model and UI propagation suites**

Run: `pytest -q tests/video/test_model.py tests/video/test_tracking.py tests/video/test_tracking_ui.py tests/video/test_sam2_propagation.py`

Expected: PASS with updated expectations that complete full-video propagation is pending before review.

- [ ] **Step 6: Commit reviewable propagation**

```bash
git add libs/core/video_model.py libs/widgets/videoTimelineWidget.py labelImgPlusPlus.py tests/video/test_model.py tests/video/test_tracking_ui.py tests/video/test_sam2_propagation.py
git commit -m "feat: review propagated video results"
```

### Task 6: Bounded asynchronous shutdown

**Files:**
- Create: `libs/core/shutdown_coordinator.py`
- Create: `tests/core/test_shutdown_coordinator.py`
- Modify: `libs/core/task_coordinator.py:97-207`
- Modify: `labelImgPlusPlus.py:5878-5975`
- Modify: `tests/video/test_navigation.py`
- Modify: `tests/video/test_editing.py`

**Interfaces:**
- Consumes: `TaskCoordinator.cancel_all()`, `queue_depths()`, save coordinator state, and named job keys.
- Produces: `TaskCoordinator.active_jobs()`, `is_idle()`, `ShutdownCoordinator.begin()`, `wait_again()`, `force_requested()`, `ready()`, and `timedOut(tuple)`.

- [ ] **Step 1: Write failing timeout/ready tests with a fake worker source**

```python
_APP = QApplication.instance() or QApplication([])


class FakeActivity:
    def __init__(self, jobs):
        self.jobs = tuple(jobs)
        self.cancelled = False

    def cancel_all(self):
        self.cancelled = True

    def active_jobs(self):
        return self.jobs

    def is_idle(self):
        return not self.jobs


def test_shutdown_waits_five_seconds_then_reports_remaining():
    source = FakeActivity(['video decode'])
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)
    timed_out = QSignalSpy(shutdown.timedOut)
    shutdown.begin()
    shutdown._deadline_expired()
    assert timed_out[0][0] == ('video decode',)
    assert shutdown.state == 'timed_out'


def test_shutdown_finishes_when_workers_and_save_are_drained():
    source = FakeActivity([])
    shutdown = ShutdownCoordinator(source, timeout_ms=5000)
    ready = QSignalSpy(shutdown.ready)
    shutdown.begin()
    shutdown.poll()
    assert len(ready) == 1
```

- [ ] **Step 2: Run shutdown tests**

Run: `pytest -q tests/core/test_shutdown_coordinator.py tests/video/test_navigation.py -k shutdown`

Expected: FAIL because shutdown currently blocks for short per-pool waits and returns only a boolean.

- [ ] **Step 3: Add inspectable nonblocking cancellation**

`TaskCoordinator.active_jobs()` returns stable human-readable keys/lane names for pending and running records. `is_idle()` is true only when every lane has no pending/running record. Keep `shutdown(wait_ms=...)` for compatibility tests, but MainWindow uses `cancel_all()` plus polling instead of blocking the GUI thread.

```python
def active_jobs(self):
    values = []
    for lane in self._lanes.values():
        for record in list(lane.pending) + list(lane.running.values()):
            values.append(str(record.handle.key or '%s job' % lane.name))
    return tuple(sorted(set(values)))
```

Implement the nonblocking owner in `shutdown_coordinator.py`:

```python
class ShutdownCoordinator(QObject):
    ready = pyqtSignal()
    timedOut = pyqtSignal(tuple)

    def __init__(self, activity, timeout_ms=5000, parent=None):
        super(ShutdownCoordinator, self).__init__(parent)
        self.activity = activity
        self.timeout_ms = int(timeout_ms)
        self.state = 'idle'
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self.poll)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._deadline_expired)

    def begin(self):
        self.state = 'waiting'
        self.activity.cancel_all()
        self._poll_timer.start()
        self._deadline.start(self.timeout_ms)
        self.poll()

    def poll(self):
        if self.state == 'waiting' and self.activity.is_idle():
            self._poll_timer.stop()
            self._deadline.stop()
            self.state = 'ready'
            self.ready.emit()

    def _deadline_expired(self):
        if self.state != 'waiting':
            return
        self._poll_timer.stop()
        self.state = 'timed_out'
        self.timedOut.emit(self.activity.active_jobs())

    def wait_again(self):
        if self.state == 'timed_out':
            self.begin()

    def force_requested(self):
        self._poll_timer.stop()
        self._deadline.stop()
        self.state = 'force_requested'
```

- [ ] **Step 4: Integrate a close state machine**

The first `closeEvent` flushes continuous save, cancels document workers, starts `ShutdownCoordinator`, and ignores the event. `ready` sets `_shutdown_ready=True`, closes the decoder only after the video lane is idle, then calls `close()` again. At five seconds, keep the window open and show a nonmodal surface naming remaining work with **Wait** and **Force Quit**. Wait restarts the five-second interval. Force Quit asks a second confirmation only when unsaved changes remain, then explicitly accepts close.

- [ ] **Step 5: Run shutdown/crash regression suites**

Run: `pytest -q tests/core/test_task_coordinator.py tests/core/test_shutdown_coordinator.py tests/video/test_navigation.py tests/video/test_editing.py -k 'shutdown or close or worker or save'`

Expected: PASS; no test leaves a running decoder lane or invokes Force Quit without explicit selection.

- [ ] **Step 6: Commit bounded shutdown**

```bash
git add libs/core/task_coordinator.py libs/core/shutdown_coordinator.py labelImgPlusPlus.py tests/core/test_shutdown_coordinator.py tests/video/test_navigation.py tests/video/test_editing.py
git commit -m "fix: coordinate graceful video shutdown"
```

### Task 7: Supplied-video acceptance slice

**Files:**
- Create: `tests/video/test_workspace_flow.py`
- Create: `docs/testing/video-workspace-acceptance.md`
- Modify: `docs/screenshots/README.md`

**Interfaces:**
- Consumes: Tasks 1-6 and the three unique supplied videos.
- Produces: automated flow coverage plus a reproducible OS-level computer-use checklist.

- [ ] **Step 1: Add the automated video workspace flow**

```python
def _wait(app, predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _seed(window, track_id):
    track = window.video_model.create_track(
        'vehicle', 'rectangle', (0, 255, 0, 255), track_id=track_id)
    window.video_model.upsert_manual(
        track.track_id, window.current_video_frame_ref.pts,
        [8, 8, 40, 32])
    window._on_video_model_mutation()
    return track


def test_open_step_seek_annotate_save_reopen(
        tmp_path, make_video):
    app, window = get_main_app()
    path = make_video(
        tmp_path / 'workspace-vfr.mp4', frames=20, variable_rate=True)
    try:
        assert window.open_video(path)
        first = window.current_video_frame_ref
        window.request_next_video_frame()
        assert _wait(
            app, lambda: window.current_video_frame_ref.pts > first.pts)
        window.video_timeline.slider.setValue(TIMELINE_MAX // 2)
        assert _wait(
            app, lambda: window.current_video_frame_ref != first)
        _seed(window, track_id='track-acceptance')
        assert _wait(
            app, lambda: window.continuous_save.state == 'saved')
        project = window.video_snapshot.project_path
        window.dirty = False
        window.close_file()
        assert window.open_video(project)
        assert window.video_model.tracks
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 2: Run all video-enabled automated suites**

Run: `pytest -q tests/video tests/core/test_task_coordinator.py tests/core/test_shutdown_coordinator.py tests/integration/test_command_bar.py`

Expected: PASS with the video extra installed.

- [ ] **Step 3: Exercise every supplied unique video through OS-level computer use**

Document and perform the exact flow for:

- `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-49-10_w.mp4`
- `/Users/abhiksarkar/Documents/Projects/personal/python-monolith/000414_000480_2025_09_04_17-06-31_w.mp4`
- `/Users/abhiksarkar/Downloads/Videos/000414_000558_2025_10_13_08-15-48_w.mp4`

For each: open, verify full-frame fit, A/D step, play/pause, mouse seek, keyboard seek, accessibility value seek, valid/invalid/out-of-range exact time, draw twice with one class selection, wait for Saved, verify, save/reopen, start/cancel propagation, accept/reject pending results, close/reopen, then repeat open/play/seek/close ten times. Repeat essentials at 800-pixel width.

- [ ] **Step 4: Capture the responsive video screenshot matrix**

Capture 800×600, 960×640, 1366×768, and 1440×900 states for paused, playing, invalid time, compact Track menu, propagation progress, propagation pending review, missing-runtime setup, and shutdown timeout. Record filenames and observations in `docs/testing/video-workspace-acceptance.md`.

- [ ] **Step 5: Commit video acceptance evidence**

```bash
git add tests/video/test_workspace_flow.py docs/testing/video-workspace-acceptance.md docs/screenshots/README.md docs/screenshots/video-workspace-2026-08-24
git commit -m "test: verify supplied video workflows"
```

- [ ] **Step 6: Gate the Assist plan**

Run: `pytest -q && git status --short`

Expected: the full base and video-enabled suites pass, no Python crash or abandoned-worker warning occurs, and the next plan is `2026-08-24-assist-model-lifecycle.md`.
