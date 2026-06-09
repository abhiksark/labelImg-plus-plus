# tests/integration/test_sam_mainwindow.py
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

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
