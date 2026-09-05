# tests/integration/test_sam_controller.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

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

    def predict(self, points, labels):
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


def test_happy_path_commits_polygon():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl.backend = _FakeBackend()
    ctrl._embedded_key = mw.file_path          # skip embedding (rgb None)
    ctrl.segment_at(QPointF(50, 50))
    ctrl._standalone_pool.waitForDone(3000)
    app.processEvents()
    assert len(mw.canvas.committed) == 1
    assert len(mw.canvas.committed[0]) >= 3


def test_worker_returns_frozen_polygon_and_tight_component_bounds():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    from libs.core.sam_controller import _SamTask

    task = _SamTask(
        4, _FakeBackend(), {}, None, QPointF(50, 50), None)
    generation, result, created = task.execute()
    assert generation == 4
    assert created is None
    assert isinstance(result, SamResult)
    assert isinstance(result.polygon, tuple)
    assert len(result.polygon) >= 3
    assert result.bounds == (20.0, 20.0, 80.0, 80.0)


def test_box_output_routes_bounds_instead_of_polygon():
    mw = _FakeMain()
    mw.sam_output_mode = 'box'
    ctrl = SamController(mw)
    result = SamResult(
        polygon=((1.0, 1.0), (9.0, 1.0), (9.0, 7.0)),
        bounds=(1.0, 1.0, 10.0, 8.0))
    ctrl._on_finished(0, result, None)
    assert mw.canvas.rectangles == [(1.0, 1.0, 10.0, 8.0)]
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
    from PyQt6.QtGui import QImage
    from libs.integrations import segmentation

    mw = _FakeMain()
    mw.image = QImage(64, 64, QImage.Format.Format_RGB888)
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
    assert len(mw.canvas.committed) == 1
    assert "Loading SAM…" in mw.messages
