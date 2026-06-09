# tests/integration/test_sam_controller.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt5.QtCore import QPointF, QThreadPool
from PyQt5.QtWidgets import QApplication

from libs.core.sam_controller import SamController

app = QApplication.instance() or QApplication([])


class _FakeCanvas:
    def __init__(self):
        self.committed = []

    def commit_polygon(self, points):
        self.committed.append(points)


class _FakeMain:
    def __init__(self):
        self.canvas = _FakeCanvas()
        self.file_path = "/img/a.jpg"
        self.image = None
        self.settings = {}
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
    ctrl._on_finished(2, [(0, 0), (1, 1), (2, 2)])   # stale gen
    assert mw.canvas.committed == []


def test_happy_path_commits_polygon():
    pytest.importorskip("numpy")
    pytest.importorskip("cv2")
    mw = _FakeMain()
    ctrl = SamController(mw)
    ctrl.backend = _FakeBackend()
    ctrl._embedded_key = mw.file_path          # skip embedding (rgb None)
    ctrl.segment_at(QPointF(50, 50))
    QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    assert len(mw.canvas.committed) == 1
    assert len(mw.canvas.committed[0]) >= 3


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
    ctrl._on_finished(1, [(0, 0), (1, 1), (2, 2)])
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
    ctrl._on_finished(1, [(0, 0), (1, 1), (2, 2)])   # image A's late result
    assert mw.canvas.committed == []
