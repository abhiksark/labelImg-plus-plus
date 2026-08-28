# Assist and Model Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Smart Box and Smart Points discoverable, explicitly downloadable, truly cancellable, and safely provisional for both images and video.

**Architecture:** Introduce a small Assist state model and manifest-driven model cache. Keep all download, model loading, embedding, and inference work in the existing worker lanes; the UI presents one contextual `AssistPanel`, while results stay in a canvas preview until the user accepts them into the normal class/undo/save workflow.

**Tech Stack:** Python 3.8+, PyQt5, optional ONNX Runtime/NumPy/OpenCV SAM extra, stdlib `urllib`/`hashlib`, existing `TaskCoordinator`, `SamController`, and continuous save coordinator.

**Spec:** `docs/superpowers/specs/2026-08-24-continuous-annotation-video-design.md`

**Prerequisite:** The continuous image and video workspace plans are complete and passing.

## Global Constraints

- Smart assistance is enabled whenever the current document can be annotated, even when no model is installed.
- Setup explains model purpose, provider, storage path, and download size before network work begins.
- Download begins only after explicit user choice; Cancel stops network/worker activity, removes incomplete artifacts, and never retries.
- Provider manifest, expected size, and SHA-256 must validate before atomic cache promotion.
- Offline, provider, and artifact-validation failures remain distinguishable.
- Smart results are provisional; Enter accepts and Escape rejects.
- Accepted results use Active class or the same inline class picker and enter undo plus continuous saving.
- Accepting a video result may offer **Track forward** but never starts propagation automatically.
- Closing Assist cancels provisional prompts/inference only, not accepted annotations or completed downloads.
- No AI dependency becomes mandatory in the base installation; annotation formats remain unchanged.
- Nothing is pushed automatically.

## File Structure

- Create `libs/core/assist_state.py`: Qt-free Assist state, prompt, preview, and failure records.
- Create `libs/integrations/model_manifest.py`: immutable provider/artifact metadata.
- Create `libs/widgets/assistPanel.py`: contextual setup/download/run/preview/failure projection.
- Modify `libs/integrations/model_cache.py`: explicit cancellable manifest download and validation.
- Modify `libs/integrations/segmentation.py`: cached-only backend loading and box/point prompts.
- Modify `libs/core/sam_controller.py`: worker orchestration that returns previews rather than committing shapes.
- Modify `libs/widgets/canvas.py`: Smart Box/Points prompt gestures and provisional preview painting.
- Modify `libs/widgets/toolRail.py` and `labelImgPlusPlus.py`: enabled Assist entry, tools, acceptance, tracking offer, and focus.
- Add focused tests under `tests/core`, `tests/integrations`, `tests/widgets`, and `tests/integration`.

---

### Task 1: Assist state and model manifest

**Files:**
- Create: `libs/core/assist_state.py`
- Create: `libs/integrations/model_manifest.py`
- Create: `tests/core/test_assist_state.py`
- Create: `tests/integrations/test_model_manifest.py`

**Interfaces:**
- Consumes: plain prompt coordinates and provider metadata.
- Produces: `AssistPhase`, `AssistFailureKind`, `AssistPrompt`, `AssistPreview`, `AssistSnapshot`, `AssistState`, `ModelArtifact`, `ModelManifest`, and `MOBILE_SAM_MANIFEST`.

- [ ] **Step 1: Write failing state and manifest tests**

```python
from libs.core.assist_state import AssistPhase, AssistState


def test_setup_download_run_preview_accept_sequence():
    assist = AssistState()
    assist.require_setup('mobile-sam')
    assert assist.snapshot.phase is AssistPhase.SETUP_REQUIRED
    assist.ready_to_download('mobile-sam')
    assist.start_download()
    assist.download_ready()
    assist.start_run(document_generation=7)
    assist.show_preview(document_generation=7, result='preview')
    assert assist.snapshot.phase is AssistPhase.PREVIEW
    assert assist.accept_preview() == 'preview'
    assert assist.snapshot.phase is AssistPhase.READY


def test_stale_preview_cannot_replace_new_document():
    assist = AssistState()
    assist.ready()
    assist.start_run(document_generation=2)
    assert not assist.show_preview(document_generation=1, result='stale')
```

```python
def test_mobile_sam_manifest_is_complete():
    assert MOBILE_SAM_MANIFEST.provider == 'LabelImg++ GitHub Releases'
    assert MOBILE_SAM_MANIFEST.total_size > 0
    assert len(MOBILE_SAM_MANIFEST.artifacts) == 2
    assert all(len(item.sha256) == 64 and item.size > 0
               for item in MOBILE_SAM_MANIFEST.artifacts)
```

- [ ] **Step 2: Run the focused tests**

Run: `pytest -q tests/core/test_assist_state.py tests/integrations/test_model_manifest.py`

Expected: FAIL because the modules do not exist.

- [ ] **Step 3: Implement immutable state and metadata**

```python
class AssistPhase(str, Enum):
    SETUP_REQUIRED = 'setup_required'
    READY_TO_DOWNLOAD = 'ready_to_download'
    DOWNLOADING = 'downloading'
    READY = 'ready'
    RUNNING = 'running'
    PREVIEW = 'preview'
    FAILED = 'failed'


class AssistFailureKind(str, Enum):
    OFFLINE = 'offline'
    PROVIDER = 'provider'
    VALIDATION = 'validation'
    RUNTIME = 'runtime'
    INFERENCE = 'inference'


@dataclass(frozen=True)
class AssistPrompt:
    mode: str
    positive_points: tuple = ()
    negative_points: tuple = ()
    box: object = None


@dataclass(frozen=True)
class ModelArtifact:
    name: str
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    display_name: str
    purpose: str
    provider: str
    artifacts: tuple

    @property
    def total_size(self):
        return sum(item.size for item in self.artifacts)


MOBILE_SAM_MANIFEST = ModelManifest(
    model_id='mobile-sam-onnx-v1',
    display_name='MobileSAM',
    purpose='Turn box or point prompts into object masks',
    provider='LabelImg++ GitHub Releases',
    artifacts=(
        ModelArtifact(
            'mobile_sam.encoder.onnx', MOBILE_SAM_ENCODER_URL,
            28157203,
            '801d81952ee19217632966f7cfe07a8030c115a7fe5bfbec9294bfaf95e44a45'),
        ModelArtifact(
            'mobile_sam.decoder.onnx', MOBILE_SAM_DECODER_URL,
            16501737,
            '001f6386a4c6036f6fac6a104d18d7c008c7eb188b2936dab749e34cae33e1c8'),
    ),
)


@dataclass(frozen=True)
class AssistSnapshot:
    phase: AssistPhase = AssistPhase.SETUP_REQUIRED
    model_id: object = None
    document_generation: object = None
    preview: object = None
    failure_kind: object = None
    message: str = ''


class AssistState:
    def __init__(self):
        self.snapshot = AssistSnapshot()

    def require_setup(self, model_id):
        self.snapshot = AssistSnapshot(
            AssistPhase.SETUP_REQUIRED, model_id=model_id)

    def ready_to_download(self, model_id):
        self.snapshot = AssistSnapshot(
            AssistPhase.READY_TO_DOWNLOAD, model_id=model_id)

    def start_download(self):
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.DOWNLOADING,
            failure_kind=None, message='')

    def download_ready(self):
        self.ready(self.snapshot.model_id)

    def ready(self, model_id=None):
        self.snapshot = AssistSnapshot(
            AssistPhase.READY, model_id=model_id or self.snapshot.model_id)

    def start_run(self, document_generation):
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.RUNNING,
            document_generation=int(document_generation), preview=None)

    def show_preview(self, document_generation, result):
        if (self.snapshot.phase is not AssistPhase.RUNNING
                or int(document_generation) !=
                self.snapshot.document_generation):
            return False
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.PREVIEW, preview=result)
        return True

    def accept_preview(self):
        value = self.snapshot.preview
        self.ready(self.snapshot.model_id)
        return value

    def reject_preview(self):
        self.ready(self.snapshot.model_id)

    def fail(self, kind, message):
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.FAILED,
            preview=None, failure_kind=AssistFailureKind(kind),
            message=str(message))
```

Add transition guards for `start_download`, `download_ready`, `start_run`, and preview review so invalid callers raise `ValueError`; the shown state assignments are the successful-path bodies. Stale generation callbacks return `False` rather than changing phase. No method mutates an annotation model.

- [ ] **Step 4: Run state and manifest tests**

Run: `pytest -q tests/core/test_assist_state.py tests/integrations/test_model_manifest.py`

Expected: PASS.

- [ ] **Step 5: Commit Assist domain state**

```bash
git add libs/core/assist_state.py libs/integrations/model_manifest.py tests/core/test_assist_state.py tests/integrations/test_model_manifest.py
git commit -m "feat: define assist lifecycle state"
```

### Task 2: Explicit, cancellable, validated model downloads

**Files:**
- Modify: `libs/integrations/model_cache.py:1-115`
- Modify: `libs/integrations/segmentation.py:83-110`
- Modify: `tests/integrations/test_model_cache.py`
- Modify: `tests/integrations/test_segmentation.py`

**Interfaces:**
- Consumes: `ModelManifest`, destination cache, `cancelled()`, and `progress(ModelDownloadProgress)` callback.
- Produces: `ModelDownloadProgress`, `ModelOfflineError`, `ModelProviderError`, `ModelValidationError`, `cached_model_paths()`, and `download_manifest()`; `load_backend()` never downloads.

- [ ] **Step 1: Write failing cancellation and validation tests**

```python
class ChunkedResponse:
    headers = {'Content-Length': '8'}

    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        self.read_count += 1
        return self.chunks.pop(0) if self.chunks else b''


class Response(ChunkedResponse):
    def __init__(self, payload):
        super().__init__([payload])
        self.headers = {'Content-Length': str(len(payload))}


@pytest.fixture
def fake_manifest():
    payload = b'aaaabbbb'
    return ModelManifest(
        'fake', 'Fake model', 'Test segmentation', 'Test provider',
        (ModelArtifact(
            'fake.onnx', 'https://provider.invalid/fake.onnx',
            len(payload), hashlib.sha256(payload).hexdigest()),))


def test_cancel_removes_part_and_never_retries(tmp_path, fake_manifest, monkeypatch):
    calls = []
    response = ChunkedResponse([b'a' * 4, b'b' * 4])
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request: calls.append(request) or response)
    cancelled = lambda: response.read_count >= 1
    with pytest.raises(model_cache.ModelDownloadCancelled):
        model_cache.download_manifest(
            fake_manifest, str(tmp_path), cancelled=cancelled)
    assert calls and len(calls) == 1
    assert not list(tmp_path.glob('*.part'))
    assert not list(tmp_path.glob('*.onnx'))


def test_wrong_content_length_is_validation_failure(tmp_path, fake_manifest,
                                                    monkeypatch):
    monkeypatch.setattr(model_cache.urllib.request, 'urlopen',
                        lambda request: Response(b'short'))
    with pytest.raises(model_cache.ModelValidationError, match='size'):
        model_cache.download_manifest(fake_manifest, str(tmp_path))
```

Add distinct tests mapping `URLError` to `ModelOfflineError`, HTTP status/provider failures to `ModelProviderError`, SHA mismatch to `ModelValidationError`, and success to atomic final files with no `.part` residue.

- [ ] **Step 2: Run cache tests**

Run: `pytest -q tests/integrations/test_model_cache.py tests/integrations/test_segmentation.py`

Expected: FAIL because resolution still auto-downloads and has no cooperative cancellation taxonomy.

- [ ] **Step 3: Separate cache lookup from download**

```python
@dataclass(frozen=True)
class ModelDownloadProgress:
    artifact: str
    downloaded: int
    artifact_size: int
    total_downloaded: int
    total_size: int


class ModelDownloadCancelled(Exception):
    pass


class ModelOfflineError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    pass


class ModelValidationError(RuntimeError):
    pass


def cached_model_paths(manifest=MOBILE_SAM_MANIFEST, cache_dir=None):
    root = cache_dir or _cache_dir()
    paths = tuple(os.path.join(root, item.name) for item in manifest.artifacts)
    return paths if all(_valid_cached(path, artifact)
                        for path, artifact in zip(paths, manifest.artifacts)) else None


def download_manifest(manifest, cache_dir, cancelled=None, progress=None):
    os.makedirs(cache_dir, exist_ok=True)
    outputs = []
    total_downloaded = 0
    for artifact in manifest.artifacts:
        destination = os.path.join(cache_dir, artifact.name)
        temporary = destination + '.part'
        try:
            with urllib.request.urlopen(artifact.url) as response, \
                    open(temporary, 'wb') as output:
                header_size = int(response.headers.get('Content-Length') or 0)
                if header_size and header_size != artifact.size:
                    raise ModelValidationError('provider size does not match manifest')
                digest = hashlib.sha256()
                artifact_bytes = 0
                while True:
                    if cancelled and cancelled():
                        raise ModelDownloadCancelled()
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    output.write(chunk)
                    digest.update(chunk)
                    artifact_bytes += len(chunk)
                    total_downloaded += len(chunk)
                    if progress:
                        progress(ModelDownloadProgress(
                            artifact.name, artifact_bytes, artifact.size,
                            total_downloaded, manifest.total_size))
                output.flush()
                os.fsync(output.fileno())
            if artifact_bytes != artifact.size:
                raise ModelValidationError('download size does not match manifest')
            if digest.hexdigest() != artifact.sha256:
                raise ModelValidationError('download checksum does not match manifest')
            if cancelled and cancelled():
                raise ModelDownloadCancelled()
            os.replace(temporary, destination)
            outputs.append(destination)
        except urllib.error.HTTPError as exc:
            raise ModelProviderError(str(exc))
        except urllib.error.URLError as exc:
            raise ModelOfflineError(str(exc))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return tuple(outputs)
```

Use a unique run suffix if concurrent cache tools are later introduced; the current single SAM lane guarantees one writer. The function never loops/retries, and the `finally` block removes the active temporary artifact on every failure or cancellation.

Change `load_backend(settings)` to use configured custom paths or `cached_model_paths()`. If absent, return a typed/setup-required error; downloading is owned only by the explicit Assist action.

- [ ] **Step 4: Run cache/backend tests**

Run: `pytest -q tests/integrations/test_model_cache.py tests/integrations/test_segmentation.py tests/integrations/test_sam_backend.py`

Expected: PASS.

- [ ] **Step 5: Commit explicit model acquisition**

```bash
git add libs/integrations/model_cache.py libs/integrations/segmentation.py tests/integrations/test_model_cache.py tests/integrations/test_segmentation.py
git commit -m "feat: validate explicit model downloads"
```

### Task 3: Contextual Assist panel

**Files:**
- Create: `libs/widgets/assistPanel.py`
- Create: `tests/widgets/test_assist_panel.py`
- Modify: `libs/widgets/workspacePages.py:132-224`
- Modify: `libs/widgets/toolRail.py:27-83`
- Modify: `labelImgPlusPlus.py:696-706`
- Modify: `labelImgPlusPlus.py:1140-1230`
- Modify: `labelImgPlusPlus.py:2267-2300`

**Interfaces:**
- Consumes: `AssistSnapshot` and `ModelManifest`.
- Produces: `AssistPanel.downloadRequested`, `cancelRequested`, `retryRequested`, `acceptRequested`, `rejectRequested`, `trackForwardRequested`, `closeRequested`, and `set_snapshot(snapshot, manifest)`.

- [ ] **Step 1: Write failing state-projection tests**

```python
def test_setup_state_explains_before_download():
    panel = AssistPanel()
    panel.set_snapshot(setup_snapshot(), MOBILE_SAM_MANIFEST)
    assert MOBILE_SAM_MANIFEST.purpose in panel.explanation.text()
    assert MOBILE_SAM_MANIFEST.provider in panel.provider.text()
    assert format_bytes(MOBILE_SAM_MANIFEST.total_size) in panel.size.text()
    assert panel.download_button.isVisible()
    assert panel.cancel_button.isHidden()


def test_downloading_and_preview_have_truthful_actions():
    panel = AssistPanel()
    panel.set_snapshot(downloading_snapshot(42, 100), MOBILE_SAM_MANIFEST)
    assert panel.cancel_button.isVisible()
    panel.set_snapshot(preview_snapshot(), MOBILE_SAM_MANIFEST)
    assert panel.accept_button.isVisible()
    assert panel.reject_button.isVisible()
```

- [ ] **Step 2: Run panel tests**

Run: `pytest -q tests/widgets/test_assist_panel.py`

Expected: FAIL because the panel does not exist.

- [ ] **Step 3: Implement one contextual surface**

Build the panel as a workspace overlay/drawer, not a permanent command-bar occupant. Render exactly one of setup required, ready to download, downloading, ready, running, preview, or failed. Failure copy depends on `AssistFailureKind` and always preserves the current document. Progress has determinate bytes when size is known and a real Cancel action.

Replace the disabled Smart Select behavior: the rail action is enabled whenever the document is editable. Activating it opens Assist even when runtime/model setup is missing. Split the tool choice into Smart Box and Smart Points inside the ready panel or its tool-menu projection; both update `AnnotationWorkflow.active_tool`.

- [ ] **Step 4: Wire explicit download orchestration**

`MainWindow._download_assist_model()` changes state to DOWNLOADING, submits `download_manifest()` to the `sam` lane with `JobHandle.is_cancelled`, forwards progress, and never submits a replacement automatically. Cancel calls the handle's `cancel()` and returns to READY_TO_DOWNLOAD after cleanup. Success resets `SamController` and transitions to READY; failures preserve typed failure kind and show Retry.

- [ ] **Step 5: Run panel and MainWindow availability tests**

Run: `pytest -q tests/widgets/test_assist_panel.py tests/integration/test_sam_mainwindow.py -k 'assist or unavailable or download or cancel'`

Expected: PASS.

- [ ] **Step 6: Commit contextual Assist setup**

```bash
git add libs/widgets/assistPanel.py libs/widgets/workspacePages.py libs/widgets/toolRail.py labelImgPlusPlus.py tests/widgets/test_assist_panel.py tests/integration/test_sam_mainwindow.py
git commit -m "feat: add contextual assist setup"
```

### Task 4: Smart Box/Points prompt and provisional preview

**Files:**
- Modify: `libs/core/sam_controller.py:1-231`
- Modify: `libs/integrations/segmentation.py:17-99`
- Modify: `libs/widgets/canvas.py:129-190`
- Modify: `libs/widgets/canvas.py:773-1035`
- Modify: `libs/widgets/canvas.py:1437-1515`
- Modify: `tests/integration/test_sam_controller.py`
- Modify: `tests/widgets/test_canvas_sam.py`
- Modify: `tests/integrations/test_sam_backend.py`

**Interfaces:**
- Consumes: `AssistPrompt` and current QImage/document generation.
- Produces: `SamController.previewReady(generation, SamResult)`, `previewFailed(generation, kind, message)`, `run_prompt(prompt)`, and Canvas `assistPrompted(AssistPrompt)`, `set_assist_preview(shape)`, `clear_assist_preview()`.

- [ ] **Step 1: Write failing prompt/preview tests**

```python
def test_smart_points_refines_preview_without_committing(tmp_path):
    window = app_mod.MainWindow(default_save_dir=str(tmp_path))
    image_path = tmp_path / 'points.png'
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    try:
        assert window.load_file(str(image_path))
        window.activate_smart_points_tool()
        window.canvas.assistPrompted.emit(AssistPrompt(
            mode='points', positive_points=((20.0, 20.0),)))
        window._on_assist_preview(
            window._dataset_generation,
            SamResult(
                polygon=((2, 2), (20, 2), (20, 20)),
                bounds=(2, 2, 20, 20)))
        assert window.canvas.assist_preview_shape is not None
        assert window.canvas.shapes == []
    finally:
        window.dirty = False
        window.close()


def test_box_prompt_reaches_backend_as_box():
    numpy = pytest.importorskip('numpy')
    fake_backend = _FakeBackend()
    fake_backend.prompts = []
    fake_backend.predict = lambda value: fake_backend.prompts.append(value) or \
        numpy.zeros((8, 8), dtype=bool)
    prompt = AssistPrompt(mode='box', box=(1.0, 2.0, 30.0, 40.0))
    task = _SamTask(3, fake_backend, {}, None, prompt, None)
    task.execute()
    assert fake_backend.prompts[-1].box == prompt.box
```

- [ ] **Step 2: Run SAM prompt tests**

Run: `pytest -q tests/integration/test_sam_controller.py tests/widgets/test_canvas_sam.py tests/integrations/test_sam_backend.py -k 'prompt or preview or box or points'`

Expected: FAIL because `_SamTask` accepts one positive point and commits immediately.

- [ ] **Step 3: Extend backend prompt semantics**

Change `SegmentationBackend.predict(points, labels)` to `predict(prompt)`. Smart Points maps positive points to label `1` and negative points to label `0`; Smart Box maps its top-left/bottom-right to SAM labels `2`/`3`. Preserve the decoder's required padding point only for point prompts.

Smart Points gestures: left click adds positive, Option-click/right click adds negative, and each change replaces the in-flight request using generation checks. Smart Box uses drag-to-create bounds. Prompt geometry is painted distinctly from annotations.

- [ ] **Step 4: Return previews instead of committing**

Remove `canvas.commit_rectangle()`/`commit_polygon()` from `SamController._on_finished`. Emit `previewReady` with immutable result data. MainWindow converts the result to a provisional `Shape`, calls `canvas.set_assist_preview()`, and transitions Assist to PREVIEW. A stale generation is ignored; a new prompt cancels/invalidate the previous result.

- [ ] **Step 5: Run SAM/controller/canvas tests**

Run: `pytest -q tests/integration/test_sam_controller.py tests/widgets/test_canvas_sam.py tests/integrations/test_sam_backend.py`

Expected: PASS.

- [ ] **Step 6: Commit provisional Smart tools**

```bash
git add libs/core/sam_controller.py libs/integrations/segmentation.py libs/widgets/canvas.py tests/integration/test_sam_controller.py tests/widgets/test_canvas_sam.py tests/integrations/test_sam_backend.py
git commit -m "feat: preview smart box and point prompts"
```

### Task 5: Accept/reject, class resolution, save, and Track forward

**Files:**
- Modify: `labelImgPlusPlus.py:3299-3414`
- Modify: `labelImgPlusPlus.py:3983-4055`
- Modify: `labelImgPlusPlus.py:4740-4770`
- Modify: `libs/widgets/assistPanel.py`
- Modify: `tests/integration/test_sam_mainwindow.py`
- Modify: `tests/video/test_tracking_ui.py`

**Interfaces:**
- Consumes: provisional Assist shape, `AnnotationWorkflow.active_class`, inline class picker, undo stack, continuous save coordinator, and selected video track anchor.
- Produces: `MainWindow.accept_assist_preview()`, `reject_assist_preview()`, `_commit_assist_shape(label)`, and explicit `track_assist_forward()`.

- [ ] **Step 1: Write failing acceptance and rejection tests**

```python
def _wait(application, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        application.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _prepare_image_document(window, path):
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(path))
    assert window.load_file(str(path))


def _show_preview(window):
    result = SamResult(
        polygon=((2.0, 2.0), (20.0, 2.0), (20.0, 18.0)),
        bounds=(2.0, 2.0, 20.0, 18.0))
    window._on_assist_preview(window._dataset_generation, result)


def test_enter_accepts_preview_through_active_class_and_autosave(tmp_path):
    window = app_mod.MainWindow(default_save_dir=str(tmp_path))
    try:
        _prepare_image_document(window, tmp_path / 'assist.png')
        _show_preview(window)
        window.workflow.set_active_class('vehicle')
        window.accept_assist_preview()
        assert len(window.canvas.shapes) == 1
        assert window.canvas.shapes[0].label == 'vehicle'
        assert window.undo_stack.can_undo()
        assert _wait(app, lambda: window.continuous_save.state == 'saved')
    finally:
        window.dirty = False
        window.close()


def test_escape_rejects_without_document_mutation(tmp_path):
    window = app_mod.MainWindow(default_save_dir=str(tmp_path))
    try:
        _prepare_image_document(window, tmp_path / 'assist.png')
        revision = window._document_revision
        _show_preview(window)
        window.reject_assist_preview()
        assert window.canvas.assist_preview_shape is None
        assert window._document_revision == revision
    finally:
        window.dirty = False
        window.close()
```

For video, assert acceptance creates one accepted manual anchor and merely reveals/enables **Track forward**; no propagation handle exists until the user triggers it.

- [ ] **Step 2: Run acceptance tests**

Run: `pytest -q tests/integration/test_sam_mainwindow.py tests/video/test_tracking_ui.py -k 'assist or preview or track_forward'`

Expected: FAIL because no explicit preview acceptance path exists.

- [ ] **Step 3: Implement one acceptance lane**

Enter calls `accept_assist_preview()`. If Active class exists, commit immediately; otherwise retain the preview and open the same inline class picker. `_commit_assist_shape(label)` transfers the provisional shape into the image/video model, pushes one undo command, clears preview/prompt, calls the normal mutation boundary, and restores canvas focus. Escape rejects and restores focus without revision/undo/save changes.

On video, store the shape through `_store_video_shape_as_manual()`, then show **Track forward** in Assist. That action calls the existing directional propagation entry point with the accepted anchor. It is never invoked from acceptance itself.

- [ ] **Step 4: Add keyboard/focus tests**

Verify Enter and Escape only act while PREVIEW is active, visible class-picker Return commits, class-picker Escape returns to preview rather than losing it, and closing Assist cancels prompts/inference/preview but leaves accepted shapes and downloaded cache files untouched.

- [ ] **Step 5: Run Assist integration tests**

Run: `pytest -q tests/integration/test_sam_controller.py tests/integration/test_sam_mainwindow.py tests/video/test_tracking_ui.py -k 'assist or smart or preview or track'`

Expected: PASS.

- [ ] **Step 6: Commit Assist acceptance**

```bash
git add labelImgPlusPlus.py libs/widgets/assistPanel.py tests/integration/test_sam_mainwindow.py tests/video/test_tracking_ui.py
git commit -m "feat: accept assist previews explicitly"
```

### Task 6: Assist lifecycle acceptance slice

**Files:**
- Create: `tests/integration/test_assist_flow.py`
- Create: `docs/testing/assist-lifecycle-acceptance.md`
- Modify: `docs/screenshots/README.md`

**Interfaces:**
- Consumes: Tasks 1-5 and image/video workflow state from earlier plans.
- Produces: an offline deterministic lifecycle test, screenshot evidence, and a live optional-model checklist.

- [ ] **Step 1: Add the deterministic end-to-end lifecycle test**

```python
class FakeModelProvider:
    def __init__(self, root):
        self.root = root
        self.block = True
        self.started = threading.Event()
        self.release = threading.Event()

    def download(self, manifest, cache_dir, cancelled=None, progress=None):
        self.started.set()
        if progress:
            progress(ModelDownloadProgress(
                manifest.artifacts[0].name, 1,
                manifest.artifacts[0].size, 1, manifest.total_size))
        while self.block and not self.release.wait(.002):
            if cancelled and cancelled():
                raise ModelDownloadCancelled()
        paths = []
        for artifact in manifest.artifacts:
            path = self.root / artifact.name
            path.write_bytes(b'model')
            paths.append(str(path))
        return tuple(paths)

    def cancel_after_first_chunk(self):
        self.block = True

    def allow_success(self):
        self.block = False
        self.release.set()

    def part_files(self):
        return tuple(self.root.glob('*.part'))

    def finish_inference(self, window, result):
        window._on_assist_preview(window._dataset_generation, result)


@pytest.fixture
def fake_model_provider(tmp_path, monkeypatch):
    provider = FakeModelProvider(tmp_path)
    monkeypatch.setattr(model_cache, 'download_manifest', provider.download)
    return provider


def test_setup_cancel_retry_preview_accept_track_flow(
        tmp_path, make_video, fake_model_provider):
    app, window = get_main_app()
    video_path = make_video(tmp_path / 'assist-video.mp4')
    try:
        window.request_open_video(str(video_path))
        assert _wait(app, lambda: window.video_snapshot is not None)
        window.activate_smart_points_tool()
        assert window.assist_state.snapshot.phase is AssistPhase.READY_TO_DOWNLOAD

        fake_model_provider.cancel_after_first_chunk()
        window._download_assist_model()
        assert fake_model_provider.started.wait(1)
        window.cancel_assist_download()
        assert _wait(app, lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY_TO_DOWNLOAD)
        assert not fake_model_provider.part_files()

        fake_model_provider.allow_success()
        window._download_assist_model()
        assert _wait(app, lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY)
        fake_model_provider.finish_inference(window, SamResult(
            polygon=((2, 2), (20, 2), (20, 20)),
            bounds=(2, 2, 20, 20)))
        window.workflow.set_active_class('vehicle')
        window.accept_assist_preview()
        assert window.video_model.tracks
        assert window._propagation_handle is None
    finally:
        window.dirty = False
        window.close()
```

- [ ] **Step 2: Run all Assist/model suites**

Run: `pytest -q tests/core/test_assist_state.py tests/integrations/test_model_manifest.py tests/integrations/test_model_cache.py tests/integrations/test_segmentation.py tests/widgets/test_assist_panel.py tests/widgets/test_canvas_sam.py tests/integration/test_sam_controller.py tests/integration/test_sam_mainwindow.py tests/integration/test_assist_flow.py`

Expected: PASS without internet access.

- [ ] **Step 3: Run the live lifecycle once with the real provider**

Using OS-level computer use, open an image and one supplied video, activate Assist with an empty cache, inspect the pre-download purpose/provider/path/size, begin and cancel, verify no `.part` remains and no retry occurs for 30 seconds, retry explicitly, validate completed cache files, create/refine/reject a preview, create/accept another with Active class, wait for Saved, and on video choose Track forward explicitly.

- [ ] **Step 4: Capture Assist screenshots**

At 800×600 and 1366×768 capture setup required, ready to download, downloading with Cancel, offline failure, validation failure, ready, running, preview, post-accept Track forward, and closed Assist. Record accessible names/focus return and artifact paths in `docs/testing/assist-lifecycle-acceptance.md`.

- [ ] **Step 5: Commit lifecycle evidence**

```bash
git add tests/integration/test_assist_flow.py docs/testing/assist-lifecycle-acceptance.md docs/screenshots/README.md docs/screenshots/assist-lifecycle-2026-08-24
git commit -m "test: verify assist lifecycle"
```

- [ ] **Step 6: Gate integrated hardening**

Run: `pytest -q && git status --short`

Expected: all base, video, and optional Assist suites pass; the next plan is `2026-08-24-integrated-ux-hardening.md`.
