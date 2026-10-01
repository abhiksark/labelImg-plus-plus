# tests/integration/test_hold_navigation.py
"""Holding Next/Previous must keep showing images while a decode is slow.

Key auto-repeat can outrun a full-size decode. These tests drive the load
with gated loaders, so they do not depend on how fast an image decodes.
"""
import os
import threading
import time
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QImage

from labelImgPlusPlus import get_main_app
from libs.core.image_pipeline import load_image_result
from libs.core.shape import Shape


def _wait(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(.002)
    return False


def _dataset(tmp_path, count):
    paths = []
    for index in range(count):
        path = str(tmp_path / ('%02d.png' % index))
        image = QImage(64, 48, QImage.Format.Format_RGB32)
        image.fill(0xFF000000 + index)
        assert image.save(path)
        paths.append(path)
    return paths


def _idle(window):
    return not window.task_coordinator.queue_depths()['interactive']


class _GatedLoader:
    """Decode stand-in that blocks chosen paths until the test releases them."""

    def __init__(self, gated_paths, failing_paths=()):
        self.gates = {path: threading.Event() for path in gated_paths}
        self.failing_paths = set(failing_paths)
        self.started = []

    def __call__(self, path, *args, **kwargs):
        self.started.append(path)
        gate = self.gates.get(path)
        if gate is not None:
            gate.wait(10)
        if path in self.failing_paths:
            raise ValueError('%s is not a valid image file' % path)
        return load_image_result(path, *args, **kwargs)

    def release(self, path):
        self.gates[path].set()

    def release_all(self):
        for gate in self.gates.values():
            gate.set()


def _record_commits(window):
    commits = []
    original = window._commit_image_result

    def recording(result):
        committed = original(result)
        if committed:
            commits.append(result.path)
        return committed

    window._commit_image_result = recording
    return commits


def test_held_navigation_shows_in_flight_image_then_latest_target(tmp_path):
    app, window = get_main_app()
    paths = _dataset(tmp_path, 6)
    window.import_dir_images(str(tmp_path))
    assert window.file_path == paths[0]
    commits = _record_commits(window)
    loader = _GatedLoader((paths[1], paths[4]))

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=loader):
            # Four key repeats arrive while the first decode is still running.
            for _repeat in range(4):
                window.request_next_image()
                app.processEvents()
            assert _wait(app, lambda: loader.started == [paths[1]])

            loader.release(paths[1])
            # The in-flight image is shown instead of being superseded.
            assert _wait(app, lambda: commits == [paths[1]], timeout=2)
            # Only the newest target is decoded next; the repeats in between
            # were coalesced rather than queued.
            assert _wait(app, lambda: loader.started == [paths[1], paths[4]])
            assert window.file_path == paths[1]

            loader.release(paths[4])
            assert _wait(app, lambda: window.file_path == paths[4])
            assert commits == [paths[1], paths[4]]
            assert window._pending_navigation_index is None
            assert _wait(app, lambda: _idle(window))

            # Navigation continues from the image that is now on screen.
            window.request_next_image()
            assert _wait(app, lambda: window.file_path == paths[5])
            assert _wait(app, lambda: _idle(window))
    finally:
        loader.release_all()
        window.dirty = False
        window.close()


def test_held_navigation_skips_unreadable_image_to_latest_target(tmp_path):
    app, window = get_main_app()
    paths = _dataset(tmp_path, 5)
    window.import_dir_images(str(tmp_path))
    commits = _record_commits(window)
    loader = _GatedLoader((paths[1],), failing_paths=(paths[1],))

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=loader):
            for _repeat in range(3):
                window.request_next_image()
                app.processEvents()
            assert _wait(app, lambda: loader.started == [paths[1]])

            loader.release(paths[1])
            assert _wait(app, lambda: window.file_path == paths[3])
            assert commits == [paths[3]]
            assert window._pending_navigation_index is None
            assert _wait(app, lambda: _idle(window))
    finally:
        loader.release_all()
        window.dirty = False
        window.close()


def test_explicit_load_supersedes_held_navigation(tmp_path):
    app, window = get_main_app()
    paths = _dataset(tmp_path, 6)
    window.import_dir_images(str(tmp_path))
    commits = _record_commits(window)
    loader = _GatedLoader((paths[1],))

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=loader):
            for _repeat in range(3):
                window.request_next_image()
                app.processEvents()
            assert _wait(app, lambda: loader.started == [paths[1]])

            # Picking an image directly is still latest-wins: it replaces both
            # the in-flight navigation load and the target queued behind it.
            window.request_load_file(paths[5], skip_prompt=True)
            assert _wait(app, lambda: window.file_path == paths[5])

            loader.release(paths[1])
            assert _wait(app, lambda: _idle(window))
            app.processEvents()
            assert window.file_path == paths[5]
            assert commits == [paths[5]]
            assert paths[3] not in loader.started
    finally:
        loader.release_all()
        window.dirty = False
        window.close()


def test_refused_navigation_commit_does_not_block_later_navigation(tmp_path):
    app, window = get_main_app()
    paths = _dataset(tmp_path, 4)
    window.import_dir_images(str(tmp_path))
    loader = _GatedLoader((paths[1],))

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=loader):
            window.request_next_image()
            assert _wait(app, lambda: loader.started == [paths[1]])
            # An unclassified shape drawn during the decode refuses the
            # commit, so the current image has to stay on screen.
            window.activate_box_tool()
            shape = Shape()
            for point in ((2, 3), (22, 3), (22, 23), (2, 23)):
                shape.add_point(QPointF(*point))
            window.canvas.current = shape
            window.canvas.finalise()

            loader.release(paths[1])
            assert _wait(app, lambda: _idle(window))
            app.processEvents()
            assert window.file_path == paths[0]

            window._cancel_provisional_shape()
            window.dirty = False
            window.request_next_image()
            assert _wait(app, lambda: window.file_path == paths[1])
            assert _wait(app, lambda: _idle(window))
    finally:
        loader.release_all()
        window._cancel_provisional_shape()
        window.dirty = False
        window.close()


def test_loading_veil_covers_only_slow_uncached_loads(tmp_path):
    app, window = get_main_app()
    paths = _dataset(tmp_path, 4)
    window.import_dir_images(str(tmp_path))
    loader = _GatedLoader((paths[1],))
    veil_texts = []
    original_show = window._show_loading_veil

    def recording_show(text):
        veil_texts.append(text)
        return original_show(text)

    window._show_loading_veil = recording_show

    def veil_visible():
        veil = window._loading_veil
        return veil is not None and not veil.isHidden()

    try:
        with patch('labelImgPlusPlus.load_image_result', side_effect=loader):
            window.request_next_image()
            # A load that has only just started must not cover the view.
            assert veil_texts == []
            assert not veil_visible()

            # The decode stays blocked, so the load is slow by construction.
            assert _wait(app, lambda: bool(veil_texts))
            assert veil_texts == ['Loading %s…' % os.path.basename(paths[1])]
            assert veil_visible()

            loader.release(paths[1])
            assert _wait(app, lambda: window.file_path == paths[1])
            assert not veil_visible()

            # The neighbour is prefetched, so the next step is a cache hit.
            assert _wait(
                app, lambda: window.frame_cache.get(paths[2]) is not None)
            window.request_next_image()
            assert _wait(app, lambda: window.file_path == paths[2])
            assert veil_texts == ['Loading %s…' % os.path.basename(paths[1])]
            assert not veil_visible()
            assert _wait(app, lambda: _idle(window))
    finally:
        loader.release_all()
        window.dirty = False
        window.close()
