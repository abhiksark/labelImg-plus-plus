import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from libs.widgets.sam_settings_dialog import SamSettingsDialog
from libs.utils.styles import Theme

app = QApplication.instance() or QApplication([])


def test_values_reflect_initial_settings():
    dlg = SamSettingsDialog(checkpoint="/m.pt", model_type="vit_h", device="cuda")
    assert dlg.values() == {
        "checkpoint": "/m.pt", "model_type": "vit_h", "device": "cuda"}


def test_unknown_model_type_falls_back_without_crashing():
    dlg = SamSettingsDialog(model_type="nonsense", device="weird")
    vals = dlg.values()
    assert vals["model_type"] in SamSettingsDialog.MODEL_TYPES
    assert vals["device"] in SamSettingsDialog.DEVICES


def test_apply_theme_runs():
    dlg = SamSettingsDialog()
    dlg.apply_theme(Theme.DARK)        # must not raise
