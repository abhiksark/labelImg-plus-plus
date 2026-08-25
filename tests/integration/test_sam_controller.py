# tests/integration/test_sam_controller.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

import labelImgPlusPlus as app_mod
from libs.core.assist_state import AssistFailureKind, AssistPhase, AssistPrompt
from libs.core.sam_controller import SamController
from libs.core.sam_types import SamResult

app = QApplication.instance() or QApplication([])


class _FakeCanvas:
    def __init__(self):
        self.committed = []
        self.rectangles = []

    def commit_polygon(self, points):
        self.committed.append(points)

    def commit_rectangle(self, bounds):
        self.rectangles.append(bounds)


class _FakeMain:
    def __init__(self):
        self.canvas = _FakeCanvas()
        self.file_path = "/img/a.jpg"
        self.image = None
        self.settings = {}
        self.sam_output_mode = 'polygon'
        self._dataset_generation = 7
        self.messages = []

    def status(self, message, delay=5000):
        self.messages.append(message)


class _FakeBackend:
    model_loaded = True

    def __init__(self):
        self.image_set = False

    @property
    def image_is_set(self):
        return self.image_set

    def set_image(self, rgb):
        self.image_set = True

    def predict(self, prompt):
        import numpy as np
        m = np.zeros((100, 100), dtype=bool)
        m[20:80, 20:80] = True
        return m


def test_busy_guard_ignores_second_click():
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl.backend = _FakeBackend()
    ctrl._busy = True
    ctrl.segment_at(QPointF(40, 40))
    assert mw.canvas.committed == []
    assert "SAM working…" in mw.messages


def test_stale_generation_is_discarded():
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl._gen = 5
    ctrl._on_finished(2, [(0, 0), (1, 1), (2, 2)], None)   # stale gen
    assert mw.canvas.committed == []


def test_happy_path_emits_polygon_preview():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    mw = _FakeMain()
    ctrl = SamController(mw)
    previews = []
    ctrl.previewReady.connect(lambda _generation, result: previews.append(result))
    ctrl.backend = _FakeBackend()
    ctrl._embedded_key = mw.file_path          # skip embedding (rgb None)
    ctrl.segment_at(QPointF(50, 50))
    ctrl._standalone_pool.waitForDone(3000)
    app.processEvents()
    assert len(previews) == 1
    assert len(previews[0].polygon) >= 3
    assert mw.canvas.committed == []


def test_worker_returns_frozen_polygon_and_tight_component_bounds():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from libs.core.sam_controller import _SamTask

    task = _SamTask(
        4, _FakeBackend(), {}, None,
        AssistPrompt(mode='points', positive_points=((50.0, 50.0),)), None)
    generation, result, created = task.execute()
    assert generation == 4
    assert created is None
    assert isinstance(result, SamResult)
    assert isinstance(result.polygon, tuple)
    assert len(result.polygon) >= 3
    assert result.bounds == (20.0, 20.0, 80.0, 80.0)


def test_finished_result_is_emitted_as_preview_without_committing():
    mw = _FakeMain()
    ctrl = SamController(mw)
    previews = []
    ctrl.previewReady.connect(
        lambda generation, result: previews.append((generation, result)))
    result = SamResult(
        polygon=((1.0, 1.0), (9.0, 1.0), (9.0, 7.0)),
        bounds=(1.0, 1.0, 10.0, 8.0))
    ctrl._on_finished(0, result, None)

    assert previews == [(7, result)]
    assert mw.canvas.rectangles == []
    assert mw.canvas.committed == []


def test_on_image_changed_invalidates_embedding():
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl._embedded_key = "/img/a.jpg"
    mw.file_path = "/img/b.jpg"
    ctrl.on_image_changed()
    assert ctrl._embedded_key is None


def test_cancel_invalidates_result_but_keeps_busy_until_completion():
    # cancel cannot stop a running task, so it must NOT release _busy (which
    # would let a concurrent task start); it only bumps the generation.
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl._busy = True
    ctrl._gen = 1
    ctrl.cancel()
    assert ctrl._gen == 2
    assert ctrl._busy is True
    # The still-running task eventually completes with the old generation:
    ctrl._on_finished(1, [(0, 0), (1, 1), (2, 2)], None)
    assert mw.canvas.committed == []     # stale result discarded
    assert ctrl._busy is False           # completion clears the guard


def test_image_switch_mid_inference_discards_result():
    # Click on image A, then switch to image B before inference finishes:
    # A's polygon must never commit onto B's canvas.
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl._busy = True
    ctrl._gen = 1
    ctrl._embedded_key = "/img/a.jpg"
    mw.file_path = "/img/b.jpg"
    ctrl.on_image_changed()
    assert ctrl._embedded_key is None
    assert ctrl._gen != 1
    ctrl._on_finished(1, [(0, 0), (1, 1), (2, 2)], None)   # image A's late result
    assert mw.canvas.committed == []


def test_reset_backend_clears_model_and_embedding():
    # After a settings change the backend is dropped; the cached embedding MUST
    # be dropped too, else the next click skips set_image and predict() crashes.
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl.backend = _FakeBackend()
    ctrl._embedded_key = "/img/a.jpg"
    ctrl.reset_backend()
    assert ctrl.backend is None
    assert ctrl._embedded_key is None


def test_first_click_loads_model_in_worker(monkeypatch):
    # With no backend yet, the first click must load the model INSIDE the worker
    # (so the UI never blocks), then segment and store the loaded backend.
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from PyQt5.QtGui import QImage
    from libs.integrations import segmentation

    mw = _FakeMain()
    mw.image = QImage(64, 64, QImage.Format_RGB888)
    mw.image.fill(0)
    fake = _FakeBackend()
    monkeypatch.setattr(segmentation, "load_backend", lambda settings: (fake, None))

    ctrl = SamController(mw)
    assert ctrl.backend is None
    ctrl.segment_at(QPointF(32, 32))
    ctrl._standalone_pool.waitForDone(3000)
    app.processEvents()

    assert ctrl.backend is fake                 # loaded backend stored on main thread
    assert fake.image_set is True               # embedded inside the worker
    assert mw.canvas.committed == []
    assert "Loading SAM…" in mw.messages


def test_box_prompt_reaches_backend_as_box():
    """Catches the controller collapsing a box into one positive point."""
    numpy = pytest.importorskip('numpy')

    class RecordingBackend(_FakeBackend):
        def __init__(self):
            super().__init__()
            self.prompts = []

        def predict(self, prompt):
            self.prompts.append(prompt)
            return numpy.zeros((8, 8), dtype=bool)

    backend = RecordingBackend()
    prompt = AssistPrompt(mode='box', box=(1.0, 2.0, 30.0, 40.0))
    from libs.core.sam_controller import _SamTask
    task = _SamTask(3, backend, {}, None, prompt, None)

    task.execute()

    assert backend.prompts[-1] == prompt


def test_replaced_prompt_result_cannot_publish():
    """Catches late inference overwriting a newer prompt's pending preview."""
    mw = _FakeMain()
    ctrl = SamController(mw)
    previews = []
    ctrl.previewReady.connect(lambda *value: previews.append(value))
    ctrl._busy = True
    ctrl._gen = 1
    ctrl.run_prompt(AssistPrompt(
        mode='points', positive_points=((10.0, 10.0),)))
    ctrl._start_pending = lambda: None

    ctrl._on_finished(1, SamResult(
        polygon=((1.0, 1.0), (2.0, 1.0), (2.0, 2.0)),
        bounds=(1.0, 1.0, 3.0, 3.0)), None)

    assert previews == []


def test_preview_signal_keeps_request_document_generation():
    """Catches a late callback being relabelled as the current document."""
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl._gen = 2
    ctrl._active_document_generation = 3
    mw._dataset_generation = 9
    previews = []
    ctrl.previewReady.connect(lambda *value: previews.append(value))
    result = SamResult(
        polygon=((1.0, 1.0), (2.0, 1.0), (2.0, 2.0)),
        bounds=(1.0, 1.0, 3.0, 3.0))

    ctrl._on_finished(2, result, None)

    assert previews == [(3, result)]


def test_preview_failure_is_typed_and_does_not_open_modal_dialog():
    """Catches inference errors becoming untyped modal warnings."""
    mw = _FakeMain()
    ctrl = SamController(mw)
    failures = []
    ctrl.previewFailed.connect(lambda *value: failures.append(value))

    ctrl._on_failed(0, AssistFailureKind.INFERENCE, 'decoder failed')

    assert failures == [(7, AssistFailureKind.INFERENCE, 'decoder failed')]


def test_smart_points_preview_does_not_mutate_document(monkeypatch, tmp_path):
    """Catches an inference result entering shapes, dirty, undo, or save state."""
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    monkeypatch.setattr(app_mod.segmentation, 'sam_available', lambda: True)
    monkeypatch.setattr(
        app_mod.model_cache, 'resolve_models', lambda *_args, **_kwargs: ('e', 'd'))
    window = app_mod.MainWindow(default_save_dir=str(tmp_path))
    image_path = tmp_path / 'points.png'
    image = QImage(64, 48, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    submitted = []
    monkeypatch.setattr(window.sam_controller, 'run_prompt', submitted.append)
    try:
        assert window.load_file(str(image_path))
        window.activate_smart_points_tool()
        prompt = AssistPrompt(
            mode='points', positive_points=((20.0, 20.0),))
        clean_revision = window._document_revision
        clean_history = (
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack))
        clean_save_state = (
            window.continuous_save.state,
            window.continuous_save._newest_revision,
            window.continuous_save._durable_revision,
            window.continuous_save._in_flight)
        window.canvas.assistPrompted.emit(prompt)
        assert submitted == [prompt]
        assert window.assist_state.snapshot.phase is AssistPhase.RUNNING

        window._on_assist_preview(
            window._dataset_generation,
            SamResult(
                polygon=((2.0, 2.0), (20.0, 2.0), (20.0, 20.0)),
                bounds=(2.0, 2.0, 21.0, 21.0)))

        assert window.assist_state.snapshot.phase is AssistPhase.PREVIEW
        assert window.canvas.assist_preview_shape is not None
        assert window.canvas.shapes == []
        assert window.canvas.provisional_shape is None
        assert window.dirty is False
        assert window._document_revision == clean_revision
        assert (
            tuple(window.undo_stack._undo_stack),
            tuple(window.undo_stack._redo_stack)) == clean_history
        assert (
            window.continuous_save.state,
            window.continuous_save._newest_revision,
            window.continuous_save._durable_revision,
            window.continuous_save._in_flight) == clean_save_state

        window._close_assist()
        assert window.assist_state.snapshot.phase is AssistPhase.READY
        assert window.canvas.assist_preview_shape is None
    finally:
        window.dirty = False
        window.close()
