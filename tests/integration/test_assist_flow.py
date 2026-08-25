"""Deterministic end-to-end acceptance for the Assist lifecycle."""

from dataclasses import replace
import fractions
import os
from pathlib import Path
import threading
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '0')
os.environ.setdefault('QT_SCALE_FACTOR', '1')

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication
import pytest

import labelImgPlusPlus as app_mod
from libs.core.assist_state import (
    AssistFailureKind,
    AssistPhase,
    AssistPrompt,
    AssistSnapshot,
)
from libs.core.sam_types import SamResult
from libs.core.shape import Shape
from libs.core.shape import ShapeType
from libs.core.video_types import PropagationResult
from libs.integrations import model_cache
from libs.integrations.model_cache import (
    ModelDownloadCancelled,
    ModelDownloadProgress,
)
from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST


app = QApplication.instance() or QApplication([])


def _wait(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _spin(duration):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.002)


def _make_video(path, frames=18, width=128, height=96, rate=12):
    av = pytest.importorskip('av')
    numpy = pytest.importorskip('numpy')
    output = av.open(str(path), mode='w')
    stream = output.add_stream('mpeg4', rate=rate)
    stream.width = width
    stream.height = height
    stream.pix_fmt = 'yuv420p'
    for index in range(frames):
        array = numpy.zeros((height, width, 3), dtype=numpy.uint8)
        x0, y0 = 16 + index, 14
        array[y0:y0 + 36, x0:x0 + 36] = 35
        for y in range(y0 + 3, y0 + 34, 6):
            for x in range(x0 + 3, x0 + 34, 6):
                array[y - 1:y + 2, x - 1:x + 2] = (240, 240, 240)
        frame = av.VideoFrame.from_ndarray(array, format='rgb24')
        frame.pts = index
        frame.time_base = fractions.Fraction(1, rate)
        for packet in stream.encode(frame):
            output.mux(packet)
    for packet in stream.encode():
        output.mux(packet)
    output.close()
    return str(path)


class ControlledModelProvider:
    """External-provider seam; real cache integrity stays in Task 2 tests."""

    def __init__(self, root):
        self.root = root
        self.calls = []
        self.started = threading.Event()
        self.cancellation_seen = threading.Event()
        self.release_cleanup = threading.Event()
        self.succeed = False

    def download(self, manifest, cache_dir, cancelled=None, progress=None):
        self.calls.append(manifest.model_id)
        assert cache_dir == str(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        if self.succeed:
            paths = []
            for artifact in manifest.artifacts:
                path = self.root / artifact.name
                path.write_bytes(b'controlled-model')
                paths.append(str(path))
            return tuple(paths)

        artifact = manifest.artifacts[0]
        partial = self.root / (artifact.name + '.part')
        partial.write_bytes(b'partial')
        if progress:
            progress(ModelDownloadProgress(
                artifact.name, 7, artifact.size, 7, manifest.total_size))
        self.started.set()
        while not cancelled():
            time.sleep(.002)
        self.cancellation_seen.set()
        self.release_cleanup.wait(2.0)
        partial.unlink()
        raise ModelDownloadCancelled()

    def part_files(self):
        return tuple(self.root.glob('*.part'))

    def allow_success(self):
        self.succeed = True

    @staticmethod
    def finish_inference(window, result):
        window._on_assist_preview(window._dataset_generation, result)


class ControlledInferenceBackend:
    """Minimal external runtime seam used by the controller's prepare job."""

    def __init__(self):
        self.images = []

    def set_image(self, image):
        self.images.append(image.shape)


CAPTURE_SIZES = ((800, 600), (1366, 768))
CAPTURE_STATES = (
    'setup-required',
    'ready-to-download',
    'downloading-cancel',
    'offline-failure',
    'validation-failure',
    'ready',
    'running',
    'preview',
    'post-accept-track-forward',
    'assist-closed',
)


def _capture_snapshot(name):
    base = AssistSnapshot(model_id=MOBILE_SAM_MANIFEST.model_id)
    if name == 'setup-required':
        return replace(base, phase=AssistPhase.SETUP_REQUIRED), False
    if name == 'ready-to-download':
        return replace(base, phase=AssistPhase.READY_TO_DOWNLOAD), False
    if name == 'downloading-cancel':
        progress = ModelDownloadProgress(
            MOBILE_SAM_MANIFEST.artifacts[0].name,
            9437184,
            MOBILE_SAM_MANIFEST.artifacts[0].size,
            9437184,
            MOBILE_SAM_MANIFEST.total_size,
        )
        return replace(
            base, phase=AssistPhase.DOWNLOADING, message=progress), False
    if name == 'offline-failure':
        return replace(
            base, phase=AssistPhase.FAILED,
            failure_kind=AssistFailureKind.OFFLINE,
            message='Connection unavailable during the explicit download.'
        ), False
    if name == 'validation-failure':
        return replace(
            base, phase=AssistPhase.FAILED,
            failure_kind=AssistFailureKind.VALIDATION,
            message='SHA-256 did not match the provider manifest.'
        ), False
    if name == 'ready':
        return replace(base, phase=AssistPhase.READY), False
    if name == 'running':
        return replace(
            base, phase=AssistPhase.RUNNING,
            document_generation=1), False
    if name == 'preview':
        return replace(
            base, phase=AssistPhase.PREVIEW,
            document_generation=1, preview=object()), False
    if name == 'post-accept-track-forward':
        return replace(base, phase=AssistPhase.READY), True
    raise ValueError(name)


def _capture_preview_shape():
    shape = Shape(
        line_color=QColor(20, 160, 240), shape_type=ShapeType.POLYGON)
    for point in ((150, 105), (390, 125), (420, 300), (185, 325)):
        shape.add_point(QPointF(*point))
    shape.close()
    return shape


def capture_assist_lifecycle_matrix(output_dir, workspace_dir):
    """Write truthful controlled product states when display size is limited."""
    output_dir = Path(output_dir)
    workspace_dir = Path(workspace_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    image_path = workspace_dir / 'assist-capture.png'
    image = QImage(640, 480, QImage.Format_RGB32)
    image.fill(QColor('#dce6ee'))
    assert image.save(str(image_path), 'PNG')

    app_instance, window = app_mod.get_main_app()
    captured = []
    try:
        window.default_save_dir = str(workspace_dir)
        window.show()
        assert window.load_file(str(image_path))
        window._active_class_selected('car')
        panel = window.workspace_pages.assist_panel

        for width, height in CAPTURE_SIZES:
            window.resize(width, height)
            app.processEvents()
            for name in CAPTURE_STATES:
                window.canvas.clear_assist_preview()
                if name == 'assist-closed':
                    window.workspace_pages.hide_assist()
                    window.canvas.setFocus()
                else:
                    snapshot, track_forward = _capture_snapshot(name)
                    window.workspace_pages.show_assist()
                    panel.set_snapshot(
                        snapshot, MOBILE_SAM_MANIFEST,
                        track_forward_available=track_forward)
                    if name == 'preview':
                        window.canvas.set_assist_preview(
                            _capture_preview_shape())
                    panel.state_label.setFocus()
                app.processEvents()

                path = output_dir / ('%s-%sx%s.png' % (
                    name, width, height))
                assert window.grab().save(str(path), 'PNG')
                screenshot = QImage(str(path))
                assert not screenshot.isNull()
                assert (screenshot.width(), screenshot.height()) == (
                    width, height)
                assert path.stat().st_size > 0
                if name == 'assist-closed':
                    assert panel.isHidden()
                    assert window.canvas.hasFocus()
                else:
                    assert panel.isVisible()
                    assert panel.state_label.hasFocus()
                captured.append(path)
    finally:
        window.dirty = False
        window._shutdown_force = True
        window.close()
        app_instance.processEvents()
    return captured


def test_smart_select_action_opens_visible_focused_assist(
        monkeypatch, tmp_path):
    """Catches the real QAction path checking Smart Select without its panel."""
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(app_mod.segmentation, 'sam_available', lambda: True)
    source = tmp_path / 'editable.png'
    image = QImage(96, 64, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(source))

    app_instance, window = app_mod.get_main_app()
    try:
        window.show()
        assert window.load_file(str(source))
        app.processEvents()
        panel = window.workspace_pages.assist_panel
        assert window.workspace_pages.current_page() == 'canvas'
        assert window.file_path == str(source)
        assert window.actions.sam_mode.isEnabled()
        assert panel.isHidden()

        window.actions.sam_mode.trigger()
        app.processEvents()

        # Assist is a contextual entry until the user chooses Box or Points;
        # Select therefore remains the one authoritative active tool.
        assert window.actions.editMode.isChecked()
        assert not window.actions.sam_mode.isChecked()
        assert not panel.isHidden()
        assert panel.isVisible()
        assert panel.state_label.hasFocus()
    finally:
        window.dirty = False
        window._shutdown_force = True
        window.close()
        app_instance.processEvents()


def test_explicit_cancel_retry_review_accept_and_track_lifecycle(
        monkeypatch, tmp_path):
    """Catches hidden network/retry, premature cleanup, mutation, or tracking."""
    cache_root = tmp_path / 'cache'
    model_root = cache_root / 'labelimgpp'
    provider = ControlledModelProvider(model_root)
    monkeypatch.setenv('XDG_CACHE_HOME', str(cache_root))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(app_mod.segmentation, 'sam_available', lambda: True)
    monkeypatch.setattr(model_cache, 'download_manifest', provider.download)
    monkeypatch.setattr(
        model_cache.urllib.request, 'urlopen',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('offline acceptance attempted network access')))

    prompts = []
    app_instance, window = app_mod.get_main_app()
    video = _make_video(tmp_path / 'assist-lifecycle.mp4')
    try:
        window.show()
        window.save_changes_automatically.setChecked(True)
        handle = window.request_open_video(str(video), skip_prompt=True)
        assert handle is not None
        assert _wait(lambda: window.video_snapshot is not None)

        window.activate_smart_points_tool()
        assert window.assist_state.snapshot.phase is \
            AssistPhase.READY_TO_DOWNLOAD
        _spin(.1)
        assert provider.calls == []

        window._download_assist_model()
        assert provider.started.wait(1.0)
        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.DOWNLOADING)
        assert provider.part_files()
        window.cancel_assist_download()
        assert provider.cancellation_seen.wait(1.0)
        app.processEvents()
        assert window.assist_state.snapshot.phase is AssistPhase.DOWNLOADING
        assert provider.part_files()

        provider.release_cleanup.set()
        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY_TO_DOWNLOAD)
        assert window._assist_download_handle is None
        assert provider.part_files() == ()
        assert provider.calls == ['mobile-sam-onnx-v1']
        _spin(.15)
        assert provider.calls == ['mobile-sam-onnx-v1']

        provider.allow_success()
        window._download_assist_model()
        assert _wait(lambda: window.assist_state.snapshot.phase
                     is AssistPhase.READY)
        assert provider.calls == [
            'mobile-sam-onnx-v1', 'mobile-sam-onnx-v1']
        assert all(path.is_file() for path in model_root.glob('*.onnx'))

        inference = ControlledInferenceBackend()
        window.sam_controller.backend = inference
        window.activate_smart_points_tool()
        assert _wait(lambda: not window.sam_controller._busy)
        assert inference.images
        monkeypatch.setattr(
            window.sam_controller, 'run_prompt', prompts.append)
        first_prompt = AssistPrompt(
            mode='points', positive_points=((20.0, 20.0),))
        window._on_assist_prompt(first_prompt)
        assert prompts == [first_prompt]
        assert window.assist_state.snapshot.phase is AssistPhase.RUNNING

        first_result = SamResult(
            polygon=((8.0, 8.0), (42.0, 8.0), (42.0, 38.0)),
            bounds=(8.0, 8.0, 43.0, 39.0))
        provider.finish_inference(window, first_result)
        assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
        assert window.canvas.assist_preview_shape is not None
        protected = (
            window.video_model.snapshot_state(),
            tuple(window.undo_stack._undo_stack),
            window._document_revision,
        )
        assert window.reject_assist_preview() is True
        assert window.canvas.assist_preview_shape is None
        assert (
            window.video_model.snapshot_state(),
            tuple(window.undo_stack._undo_stack),
            window._document_revision,
        ) == protected

        refined_prompt = AssistPrompt(
            mode='points', positive_points=((20.0, 20.0),),
            negative_points=((6.0, 6.0),))
        window._on_assist_prompt(refined_prompt)
        assert prompts[-1] == refined_prompt
        second_result = SamResult(
            polygon=((10.0, 10.0), (44.0, 10.0), (44.0, 40.0)),
            bounds=(10.0, 10.0, 45.0, 41.0))
        provider.finish_inference(window, second_result)
        window.workflow.set_active_class('vehicle')
        assert window.accept_assist_preview() is True
        assert _wait(lambda: window.continuous_save.state == 'saved')

        manual = [
            item for item in window.video_model.observations.values()
            if item.source == 'manual' and item.review_state == 'accepted'
            and item.anchor]
        assert len(window.video_model.tracks) == 1
        assert len(manual) == 1
        assert window._propagation_handle is None
        assert window._assist_track_forward_available(), (
            window._assist_track_forward_anchor,
            window.current_video_frame_ref,
            tuple(window.video_model.observations.values()),
            window._dataset_generation,
        )
        track_button = window.workspace_pages.assist_panel \
            .track_forward_button
        assert not track_button.isHidden()
        assert track_button.isEnabled()

        propagation_started = threading.Event()
        propagation_release = threading.Event()

        def propagate(_backend, request, _direction, cancelled, _emit):
            propagation_started.set()
            while not propagation_release.wait(.002) and not cancelled():
                pass
            return PropagationResult(
                request.request_id, request.generation,
                request.document_revision)

        monkeypatch.setattr(
            app_mod.ConfiguredPropagationBackend, 'propagate', propagate)
        propagation_handle = window.track_assist_forward()
        assert propagation_handle is not None
        assert propagation_started.wait(1.0)
        assert window._propagation_handle is propagation_handle
        propagation_release.set()
        assert _wait(lambda: window._propagation_handle is None)
    finally:
        provider.release_cleanup.set()
        window.dirty = False
        window._shutdown_force = True
        window.close()
        app_instance.processEvents()
        app_instance.processEvents()


def test_controlled_lifecycle_capture_matrix_has_exact_product_dimensions(
        monkeypatch, tmp_path):
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))

    captured = capture_assist_lifecycle_matrix(
        tmp_path / 'captures', tmp_path / 'workspace')

    assert len(captured) == len(CAPTURE_SIZES) * len(CAPTURE_STATES)
    assert {path.name for path in captured} == {
        '%s-%sx%s.png' % (name, width, height)
        for width, height in CAPTURE_SIZES
        for name in CAPTURE_STATES
    }
