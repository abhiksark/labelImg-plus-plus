import os
import sys
import time
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest


if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

HARNESS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'tools', 'ux'))
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)


from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from labelImgPlusPlus import get_main_app  # noqa: E402
from libs.core.annotation_workflow import (  # noqa: E402
    AnnotationTool, PromptPolicy,
)
from libs.core.view_transform import ViewMode  # noqa: E402
from libs.formats.labelFile import LabelFileFormat  # noqa: E402
from capture_workspace_matrix import (  # noqa: E402
    _write_sample_image, capture_scenario,
)


def _wait(app, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        QTest.qWait(5)
    return False


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
    original_policy = window.workflow.snapshot.prompt_policy
    try:
        window.default_save_dir = None
        window.label_file_format = LabelFileFormat.PASCAL_VOC
        window.save_changes_automatically.setChecked(True)
        window.active_class_control.confirm_each.setChecked(True)
        window.active_class_control.confirm_each.setChecked(False)
        assert window.workflow.snapshot.prompt_policy is \
            PromptPolicy.REUSE_ACTIVE
        assert window.import_dir_images(str(tmp_path))
        window._active_class_selected('vehicle')
        window.activate_box_tool()
        _commit_rectangle(window, (5, 5, 30, 30))
        _commit_rectangle(window, (40, 10, 70, 45))

        assert len(window.canvas.shapes) == 2
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        sidecar = tmp_path / 'frame-1.xml'
        assert _wait(app, lambda: (
            window.continuous_save.state == 'saved' and sidecar.exists()))
        assert len(ElementTree.parse(str(sidecar)).findall('object')) == 2

        window.request_next_image()
        assert _wait(app, lambda: window.cur_img_idx == 1)
        assert window.workflow.snapshot.active_class == 'vehicle'
        assert window.workflow.snapshot.active_tool is AnnotationTool.RECTANGLE
        assert window.view_transform.mode is ViewMode.FIT_WINDOW
        assert sidecar.exists()

        window.request_previous_image()
        assert _wait(app, lambda: window.cur_img_idx == 0)
        labels = [
            node.text for node in
            ElementTree.parse(str(sidecar)).findall('./object/name')]
        assert labels == ['vehicle', 'vehicle']
        assert len(window.canvas.shapes) == 2
    finally:
        window.active_class_control.confirm_each.setChecked(
            original_policy is PromptPolicy.CONFIRM_EACH)
        window.save_changes_automatically.setChecked(True)
        window.dirty = False
        window.close()


def test_capture_scenario_writes_named_window_png(tmp_path):
    _app, window = get_main_app()
    try:
        window.show()

        path = capture_scenario(
            window, 'empty-workspace', (800, 600), 'light', tmp_path)

        assert path == str(
            tmp_path / 'empty-workspace-light-800x600.png')
        assert os.path.getsize(path) > 0
        screenshot = QImage(path)
        assert not screenshot.isNull()
        assert (screenshot.width(), screenshot.height()) == (800, 600)
    finally:
        window.dirty = False
        window.close()


def _prepare_capture_context(window, directory):
    image_path = directory / 'continuous-sample.png'
    image = QImage(640, 480, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(str(image_path))
    window._ux_capture_context = SimpleNamespace(
        dataset_dir=str(directory), image_path=str(image_path))
    window.active_class_control.confirm_each.setChecked(True)
    window.show()


def test_capture_source_image_is_visually_neutral(tmp_path):
    path = tmp_path / 'neutral.png'

    _write_sample_image(path)

    image = QImage(str(path))
    colors = {
        image.pixelColor(x, y).name()
        for x, y in ((0, 0), (70, 60), (260, 230),
                     (330, 140), (560, 390), (639, 479))}
    assert colors == {'#dce6ee'}


@pytest.mark.parametrize(
    'scenario, expected_state, expects_ticket', (
        ('two-rectangles', 'saved', False),
        ('saving', 'saving', True),
        ('saved', 'saved', False),
        ('save-failed', 'failed', False),
    ))
def test_capture_scenario_establishes_real_state_from_fresh_window(
        tmp_path, scenario, expected_state, expects_ticket):
    _app, window = get_main_app()
    original_policy = window.workflow.snapshot.prompt_policy
    try:
        _prepare_capture_context(window, tmp_path)

        path = capture_scenario(
            window, scenario, (800, 600), 'light', tmp_path / 'captures')

        assert os.path.getsize(path) > 0
        assert len(window.canvas.shapes) == 2
        assert window.continuous_save.state == expected_state
        assert (window.continuous_save._in_flight is not None) is \
            expects_ticket
        assert window.workflow.snapshot.prompt_policy is \
            PromptPolicy.CONFIRM_EACH
        assert window.active_class_control.confirm_each.isChecked()
    finally:
        window.active_class_control.confirm_each.setChecked(
            original_policy is PromptPolicy.CONFIRM_EACH)
        window.continuous_save.set_enabled(False)
        window.dirty = False
        window.close()
