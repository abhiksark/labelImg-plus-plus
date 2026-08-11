# tests/integration/test_sam_mainwindow.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import json

from PyQt5.QtWidgets import QApplication
import labelImgPlusPlus as app_mod

app = QApplication.instance() or QApplication([])


def test_sam_action_disabled_when_extra_missing(monkeypatch, tmp_path):
    # Force "extra not installed" regardless of the dev machine.
    from libs.integrations import segmentation
    monkeypatch.setattr(segmentation, "sam_available", lambda: False)

    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        assert hasattr(win.actions, "sam_mode")
        assert hasattr(win, "sam_controller")
        # Even once editing actions are enabled, the gate keeps SAM disabled
        # because the [sam] extra is absent.
        win.toggle_actions(True)
        assert win.actions.sam_mode.isEnabled() is False
    finally:
        win.close()


def test_sam_mode_sticks_in_beginner_mode(monkeypatch, tmp_path):
    # Regression: entering SAM mode must NOT be reverted to EDIT by the
    # drawingPolygon -> toggle_drawing_sensitive path in beginner mode.
    from libs.integrations import segmentation
    monkeypatch.setattr(segmentation, "sam_available", lambda: True)

    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        assert win.beginner()                       # default population
        win.toggle_sam_mode()
        assert win.canvas.mode == win.canvas.CREATE_SAM
        win.toggle_sam_mode()                        # toggle off
        assert win.canvas.mode != win.canvas.CREATE_SAM
    finally:
        win.close()


def test_sam_output_toggle_is_contextual_and_persists(monkeypatch, tmp_path):
    from libs.integrations import segmentation
    from libs.utils.constants import SETTING_SAM_OUTPUT_MODE

    settings_path = tmp_path / 'settings.json'

    def load_isolated(settings):
        settings.path = str(settings_path)
        settings.data = {}
        return False

    monkeypatch.setattr(app_mod.Settings, 'load', load_isolated)
    monkeypatch.setattr(segmentation, 'sam_available', lambda: True)
    win = app_mod.MainWindow(default_filename=None,
                             default_prefdef_class_file=None,
                             default_save_dir=str(tmp_path))
    try:
        toggle = win.workspace_pages.sam_output_toggle
        assert win.sam_output_mode == 'polygon'
        assert toggle.mode() == 'polygon'
        assert toggle.isHidden()

        win.activate_smart_select_tool()
        assert not toggle.isHidden()
        toggle.buttons['box'].click()
        app.processEvents()
        assert win.sam_output_mode == 'box'
        assert win.settings.get(SETTING_SAM_OUTPUT_MODE) == 'box'
        assert json.loads(settings_path.read_text())[SETTING_SAM_OUTPUT_MODE] \
            == 'box'
        assert win.canvas.hasFocus()

        win.activate_select_tool()
        assert toggle.isHidden()
    finally:
        win.close()
        app.processEvents()
        app.processEvents()
