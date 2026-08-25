"""State projection and orchestration coverage for contextual Assist."""

import os
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from dataclasses import replace

from PyQt5.QtWidgets import QApplication
import pytest

import labelImgPlusPlus as app_mod
from libs.core.annotation_workflow import AnnotationTool
from libs.core.assist_state import (
    AssistFailureKind,
    AssistPhase,
    AssistSnapshot,
)
from libs.core.task_coordinator import JobPriority
from libs.integrations import model_cache, segmentation
from libs.integrations.model_cache import (
    ModelDownloadCancelled,
    ModelDownloadProgress,
)
from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST
from libs.widgets.assistPanel import AssistPanel, format_bytes


app = QApplication.instance() or QApplication([])


def _snapshot(phase, **changes):
    return replace(
        AssistSnapshot(
            phase=phase, model_id=MOBILE_SAM_MANIFEST.model_id),
        **changes)


def _shown_panel():
    panel = AssistPanel()
    panel.show()
    app.processEvents()
    return panel


def _wait(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _window(monkeypatch, tmp_path, cached=False, runtime=True):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(segmentation, 'sam_available', lambda: runtime)
    paths = tuple(str(tmp_path / artifact.name)
                  for artifact in MOBILE_SAM_MANIFEST.artifacts)
    monkeypatch.setattr(
        model_cache, 'cached_model_paths',
        lambda *_args, **_kwargs: paths if cached else None)
    window = app_mod.MainWindow(default_save_dir=str(tmp_path))
    window.show()
    app.processEvents()
    return window


def _make_editable_image_projection(window, tmp_path):
    window.file_path = str(tmp_path / 'current.png')
    window._set_document_kind(app_mod.DocumentKind.IMAGE)
    window.canvas.setEnabled(True)
    window.toggle_actions(True)


def _assert_action_label_fits(panel, button):
    assert panel.layout().contentsRect().contains(button.geometry())
    assert button.width() >= button.sizeHint().width()
    assert button.contentsRect().width() >= \
        button.fontMetrics().horizontalAdvance(button.text())


def test_setup_state_explains_model_before_download():
    """Removing the setup metadata would hide the informed-consent details."""
    panel = _shown_panel()
    try:
        panel.set_snapshot(
            _snapshot(AssistPhase.SETUP_REQUIRED), MOBILE_SAM_MANIFEST)

        assert MOBILE_SAM_MANIFEST.purpose in panel.explanation.text()
        assert MOBILE_SAM_MANIFEST.provider in panel.provider.text()
        assert format_bytes(MOBILE_SAM_MANIFEST.total_size) in panel.size.text()
        assert panel.storage.text().strip()
        assert panel.download_button.isVisible()
        assert panel.cancel_button.isHidden()
    finally:
        panel.close()


def test_downloading_and_preview_offer_only_truthful_actions():
    """A phase projection must not retain actions from the previous phase."""
    panel = _shown_panel()
    try:
        progress = ModelDownloadProgress(
            'mobile_sam.encoder.onnx', 42, 100, 42, 100)
        panel.set_snapshot(
            _snapshot(AssistPhase.DOWNLOADING, message=progress),
            MOBILE_SAM_MANIFEST)

        assert panel.cancel_button.isVisible()
        assert panel.progress.isVisible()
        assert panel.progress.maximum() == 100
        assert panel.progress.value() == 42
        assert panel.download_button.isHidden()

        panel.set_snapshot(
            _snapshot(AssistPhase.DOWNLOADING, message='Cancelling…'),
            MOBILE_SAM_MANIFEST)
        assert panel.message.isVisible()
        assert panel.message.text() == 'Cancelling…'

        panel.set_snapshot(
            _snapshot(AssistPhase.PREVIEW, preview=object()),
            MOBILE_SAM_MANIFEST)

        assert panel.accept_button.isVisible()
        assert panel.reject_button.isVisible()
        assert panel.cancel_button.isHidden()
        assert panel.progress.isHidden()
    finally:
        panel.close()


def test_failure_copy_distinguishes_cause_and_preserves_document():
    """Collapsing failure kinds would make Retry guidance untruthful."""
    panel = _shown_panel()
    expected = {
        AssistFailureKind.OFFLINE: 'offline',
        AssistFailureKind.PROVIDER: 'provider',
        AssistFailureKind.VALIDATION: 'validation',
        AssistFailureKind.RUNTIME: 'runtime',
        AssistFailureKind.INFERENCE: 'preview',
    }
    try:
        for kind, phrase in expected.items():
            panel.set_snapshot(
                _snapshot(
                    AssistPhase.FAILED, failure_kind=kind,
                    message='detail'),
                MOBILE_SAM_MANIFEST)
            copy = panel.message.text().lower()
            assert phrase in copy
            assert 'document' in copy
            assert panel.retry_button.isVisible()
            assert panel.download_button.isHidden()
    finally:
        panel.close()


def test_ready_state_exposes_both_prompt_tools_and_public_signals():
    """Dropping either prompt action would collapse Smart Box/Points again."""
    panel = _shown_panel()
    received = []
    panel.smartBoxRequested.connect(lambda: received.append('box'))
    panel.smartPointsRequested.connect(lambda: received.append('points'))
    try:
        panel.set_snapshot(
            _snapshot(AssistPhase.READY), MOBILE_SAM_MANIFEST)

        assert panel.smart_box_button.isVisible()
        assert panel.smart_points_button.isVisible()
        panel.smart_box_button.click()
        panel.smart_points_button.click()
        assert received == ['box', 'points']

        for name in (
                'downloadRequested', 'cancelRequested', 'retryRequested',
                'acceptRequested', 'rejectRequested',
                'trackForwardRequested', 'closeRequested'):
            assert hasattr(panel, name)
    finally:
        panel.close()


@pytest.mark.parametrize('window_size', ((800, 600), (1366, 768)))
def test_ready_assist_action_labels_fit_at_review_sizes(
        monkeypatch, tmp_path, window_size):
    """A single action row must not squeeze essential labels out of view."""
    window = _window(monkeypatch, tmp_path, cached=True, runtime=True)
    try:
        _make_editable_image_projection(window, tmp_path)
        window.workspace_pages.set_page('canvas')
        window.resize(*window_size)
        panel = window.workspace_pages.assist_panel
        panel.set_snapshot(
            _snapshot(AssistPhase.READY), MOBILE_SAM_MANIFEST,
            track_forward_available=True)
        window.workspace_pages.show_assist()
        app.processEvents()

        assert (window.width(), window.height()) == window_size
        for button in (
                panel.smart_box_button, panel.smart_points_button,
                panel.track_forward_button):
            assert button.isVisible()
            _assert_action_label_fits(panel, button)
    finally:
        window.dirty = False
        window.close()


def test_editable_document_opens_assist_even_without_optional_runtime(
        monkeypatch, tmp_path):
    """Reintroducing the runtime gate would silently disable setup again."""
    window = _window(monkeypatch, tmp_path, cached=False, runtime=False)
    try:
        _make_editable_image_projection(window, tmp_path)
        assert window.actions.sam_mode.isEnabled()

        window.actions.sam_mode.trigger()
        app.processEvents()

        assert not window.workspace_pages.assist_panel.isHidden()
        assert window.workspace_pages.assist_panel.state_label.hasFocus()
        assert window.assist_state.snapshot.phase is \
            AssistPhase.READY_TO_DOWNLOAD
        assert window._assist_download_handle is None
    finally:
        window.dirty = False
        window.close()


def test_contextual_overlays_are_siblings_above_the_active_page_stack(
        monkeypatch, tmp_path):
    """A QStackedWidget child can be hidden behind its managed current page."""
    window = _window(monkeypatch, tmp_path, cached=False, runtime=False)
    try:
        _make_editable_image_projection(window, tmp_path)
        window.workspace_pages.set_page('canvas')
        window.resize(900, 640)
        app.processEvents()

        pages = window.workspace_pages
        surface = pages.stack.parentWidget()
        assert surface is not pages.stack
        assert pages.assist_panel.parentWidget() is surface
        assert pages.video_setup_overlay.parentWidget() is surface
        assert surface.layout().indexOf(pages.stack) >= 0
        assert surface.layout().indexOf(pages.assist_panel) == -1
        assert surface.layout().indexOf(pages.video_setup_overlay) == -1

        pages.show_assist()
        app.processEvents()
        assert pages.assist_panel.geometry().right() == surface.rect().right()
        assert pages.assist_panel.height() == surface.height()
        assert pages.video_setup_overlay.geometry() == surface.rect()
        assert pages.assist_panel.state_label.hasFocus()

        exposed_region = pages.assist_panel.geometry()
        workspace_updates = []
        pages.stack.update = lambda *args: workspace_updates.append(args)
        pages.assist_panel.close_button.click()
        app.processEvents()
        assert pages.assist_panel.isHidden()
        assert workspace_updates == [(exposed_region,)]
        assert window.canvas.hasFocus()
    finally:
        window.dirty = False
        window.close()


def test_ready_assist_tools_update_authoritative_workflow(
        monkeypatch, tmp_path):
    """A button that changes only paint state would drift from workflow state."""
    window = _window(monkeypatch, tmp_path, cached=True, runtime=True)
    monkeypatch.setattr(
        window.sam_controller, 'set_enabled',
        lambda enabled: setattr(window.sam_controller, '_enabled', bool(enabled)))
    try:
        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert window.workflow.snapshot.active_tool is AnnotationTool.SELECT
        assert window.canvas.mode == window.canvas.EDIT

        window.workspace_pages.assist_panel.smart_box_button.click()
        assert window.workflow.snapshot.active_tool is AnnotationTool.SMART_BOX
        assert window.canvas.mode == window.canvas.CREATE_SAM

        window.workspace_pages.assist_panel.smart_points_button.click()
        assert window.workflow.snapshot.active_tool is \
            AnnotationTool.SMART_POINTS
        assert window.canvas.mode == window.canvas.CREATE_SAM
    finally:
        window.dirty = False
        window.close()


def test_configured_custom_model_projects_ready_without_default_cache(
        monkeypatch, tmp_path):
    """A valid custom model must not be hidden behind the default download."""
    encoder = tmp_path / 'custom-encoder.onnx'
    decoder = tmp_path / 'custom-decoder.onnx'
    encoder.write_bytes(b'encoder')
    decoder.write_bytes(b'decoder')

    def load_settings(settings):
        settings.data = {
            app_mod.SETTING_SAM_ENCODER: str(encoder),
            app_mod.SETTING_SAM_DECODER: str(decoder),
        }
        return True

    monkeypatch.setattr(app_mod.Settings, 'load', load_settings)
    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    try:
        assert window.assist_state.snapshot.phase is AssistPhase.READY
    finally:
        window.dirty = False
        window.close()


def test_cache_io_failure_projects_runtime_recovery_without_blocking_startup(
        monkeypatch, tmp_path):
    """An optional cache failure must not prevent the main window opening."""
    monkeypatch.setattr(
        model_cache, 'resolve_models',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError('cache unavailable')))

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    try:
        assert window.assist_state.snapshot.phase is AssistPhase.FAILED
        assert window.assist_state.snapshot.failure_kind is \
            AssistFailureKind.RUNTIME
        assert 'cache unavailable' in window.assist_state.snapshot.message

        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        assert window.workspace_pages.assist_panel.retry_button.isVisible()
        assert 'document' in \
            window.workspace_pages.assist_panel.message.text().lower()
    finally:
        window.dirty = False
        window.close()


@pytest.mark.parametrize('source', ('cache', 'custom'))
def test_model_files_without_runtime_project_typed_recovery(
        monkeypatch, tmp_path, source):
    """Files alone must not expose prompt tools without the SAM runtime."""
    cached = source == 'cache'
    if source == 'custom':
        encoder = tmp_path / 'custom-encoder.onnx'
        decoder = tmp_path / 'custom-decoder.onnx'
        encoder.write_bytes(b'encoder')
        decoder.write_bytes(b'decoder')

        def load_settings(settings):
            settings.data = {
                app_mod.SETTING_SAM_ENCODER: str(encoder),
                app_mod.SETTING_SAM_DECODER: str(decoder),
            }
            return True

        monkeypatch.setattr(app_mod.Settings, 'load', load_settings)

    window = _window(monkeypatch, tmp_path, cached=cached, runtime=False)
    try:
        assert window.assist_state.snapshot.phase is AssistPhase.FAILED
        assert window.assist_state.snapshot.failure_kind is \
            AssistFailureKind.RUNTIME

        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        panel = window.workspace_pages.assist_panel
        assert panel.isVisible()
        assert panel.retry_button.isVisible()
        assert panel.smart_box_button.isHidden()
        assert panel.smart_points_button.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_runtime_retry_rechecks_local_setup_without_downloading_again(
        monkeypatch, tmp_path):
    """Installing the runtime must reuse valid files instead of redownloading."""
    runtime_ready = [False]
    download_calls = []
    window = _window(monkeypatch, tmp_path, cached=True, runtime=False)
    monkeypatch.setattr(
        segmentation, 'sam_available', lambda: runtime_ready[0])
    monkeypatch.setattr(
        model_cache, 'download_manifest',
        lambda *_args, **_kwargs: download_calls.append(True))
    try:
        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        assert window.assist_state.snapshot.phase is AssistPhase.FAILED

        runtime_ready[0] = True
        window.workspace_pages.assist_panel.retry_button.click()
        app.processEvents()

        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert download_calls == []
        assert window.workspace_pages.assist_panel.smart_box_button.isVisible()
    finally:
        window.dirty = False
        window.close()


def test_download_starts_only_after_explicit_action_and_resets_backend(
        monkeypatch, tmp_path):
    calls = []

    def download(manifest, cache_dir, cancelled=None, progress=None):
        calls.append((manifest, cache_dir))
        assert not cancelled()
        progress(ModelDownloadProgress(
            manifest.artifacts[0].name, 4, 8, 4, manifest.total_size))
        return tuple(os.path.join(cache_dir, item.name)
                     for item in manifest.artifacts)

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    monkeypatch.setattr(model_cache, 'download_manifest', download)
    window.sam_controller.backend = object()
    window.sam_controller._embedded_key = 'old-image'
    try:
        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        app.processEvents()
        assert calls == []

        window.workspace_pages.assist_panel.download_button.click()

        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY)
        assert len(calls) == 1
        assert window.sam_controller.backend is None
        assert window.sam_controller._embedded_key is None
        assert window._assist_download_handle is None
    finally:
        window.dirty = False
        window.close()


def test_downloaded_model_without_runtime_projects_typed_recovery(
        monkeypatch, tmp_path):
    """A successful file download cannot make an unavailable tool READY."""
    paths = tuple(str(tmp_path / artifact.name)
                  for artifact in MOBILE_SAM_MANIFEST.artifacts)

    window = _window(monkeypatch, tmp_path, cached=False, runtime=False)
    monkeypatch.setattr(
        model_cache, 'download_manifest',
        lambda *_args, **_kwargs: paths)
    try:
        _make_editable_image_projection(window, tmp_path)
        window.activate_smart_select_tool()
        window._download_assist_model()

        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.FAILED)
        assert window.assist_state.snapshot.failure_kind is \
            AssistFailureKind.RUNTIME
        assert window.workspace_pages.assist_panel.retry_button.isVisible()
        assert window.workspace_pages.assist_panel.smart_box_button.isHidden()
    finally:
        window.dirty = False
        window.close()


def test_cancel_queued_download_reconciles_without_running_worker(
        monkeypatch, tmp_path):
    """A job proven pending must leave Cancelling without awaiting cleanup."""
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    download_calls = []

    def blocker(_handle):
        blocker_started.set()
        release_blocker.wait(2.0)

    def download(*_args, **_kwargs):
        download_calls.append(True)
        return ()

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    monkeypatch.setattr(model_cache, 'download_manifest', download)
    try:
        window.task_coordinator.submit(
            'sam', blocker, priority=JobPriority.IMAGE_LOAD,
            key='sam-lane-blocker')
        assert blocker_started.wait(1.0)

        window._download_assist_model()
        queued = window._assist_download_handle
        assert queued is not None
        assert window.task_coordinator.has_active_handle(queued)

        window.cancel_assist_download()
        app.processEvents()

        assert window.assist_state.snapshot.phase is \
            AssistPhase.READY_TO_DOWNLOAD
        assert window._assist_download_handle is None
        assert not window.task_coordinator.has_active_handle(queued)
        assert download_calls == []
    finally:
        release_blocker.set()
        window.dirty = False
        window.close()


def test_cancel_projects_ready_only_after_worker_cleanup(
        monkeypatch, tmp_path):
    started = threading.Event()
    cancellation_seen = threading.Event()
    release_cleanup = threading.Event()
    calls = []
    part_paths = []

    def download(manifest, cache_dir, cancelled=None, progress=None):
        calls.append(manifest.model_id)
        part_path = os.path.join(cache_dir, manifest.artifacts[0].name + '.part')
        part_paths.append(part_path)
        os.makedirs(cache_dir, exist_ok=True)
        with open(part_path, 'wb') as output:
            output.write(b'partial')
        started.set()
        while not cancelled():
            time.sleep(.002)
        cancellation_seen.set()
        release_cleanup.wait(2.0)
        os.unlink(part_path)
        raise ModelDownloadCancelled()

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    monkeypatch.setattr(model_cache, 'download_manifest', download)
    try:
        window._download_assist_model()
        assert started.wait(1.0)
        window.cancel_assist_download()
        assert cancellation_seen.wait(1.0)
        app.processEvents()

        assert window.assist_state.snapshot.phase is AssistPhase.DOWNLOADING
        assert os.path.exists(part_paths[0])

        release_cleanup.set()
        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY_TO_DOWNLOAD)
        assert not os.path.exists(part_paths[0])
        assert calls == [MOBILE_SAM_MANIFEST.model_id]
        assert window._assist_download_handle is None
    finally:
        release_cleanup.set()
        window.dirty = False
        window.close()


def test_late_cancel_does_not_hide_already_promoted_model(
        monkeypatch, tmp_path):
    """Cancelling after atomic promotion must not claim setup is still needed."""
    worker_returned = threading.Event()
    cache_ready = threading.Event()
    paths = tuple(str(tmp_path / artifact.name)
                  for artifact in MOBILE_SAM_MANIFEST.artifacts)

    def cached(*_args, **_kwargs):
        return paths if cache_ready.is_set() else None

    def download(*_args, **_kwargs):
        cache_ready.set()
        worker_returned.set()
        return paths

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    monkeypatch.setattr(model_cache, 'cached_model_paths', cached)
    monkeypatch.setattr(model_cache, 'download_manifest', download)
    try:
        window._download_assist_model()
        assert worker_returned.wait(1.0)
        window.cancel_assist_download()

        assert _wait(lambda: window._assist_download_handle is None)
        assert window.assist_state.snapshot.phase is AssistPhase.READY
    finally:
        window.dirty = False
        window.close()


@pytest.mark.parametrize('error,kind', (
    (model_cache.ModelOfflineError('network down'), AssistFailureKind.OFFLINE),
    (model_cache.ModelProviderError('503'), AssistFailureKind.PROVIDER),
    (model_cache.ModelValidationError('bad checksum'),
     AssistFailureKind.VALIDATION),
))
def test_download_failure_keeps_typed_cause_and_current_document(
        monkeypatch, tmp_path, error, kind):
    def download(*_args, **_kwargs):
        raise error

    window = _window(monkeypatch, tmp_path, cached=False, runtime=True)
    monkeypatch.setattr(model_cache, 'download_manifest', download)
    try:
        _make_editable_image_projection(window, tmp_path)
        current_path = window.file_path
        window.activate_smart_select_tool()
        window._download_assist_model()

        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.FAILED)
        assert window.assist_state.snapshot.failure_kind is kind
        assert window.file_path == current_path
        assert window.workspace_pages.assist_panel.retry_button.isVisible()
    finally:
        window.dirty = False
        window.close()
