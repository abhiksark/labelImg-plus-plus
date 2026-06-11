import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from libs.widgets.sam_settings_dialog import SamSettingsDialog
from libs.utils.styles import Theme

app = QApplication.instance() or QApplication([])


def test_values_reflect_initial_settings():
    dlg = SamSettingsDialog(encoder_path="/e.onnx", decoder_path="/d.onnx")
    assert dlg.values() == {"encoder": "/e.onnx", "decoder": "/d.onnx"}


def test_defaults_are_empty():
    assert SamSettingsDialog().values() == {"encoder": "", "decoder": ""}


def test_values_are_stripped():
    dlg = SamSettingsDialog(encoder_path="  /e.onnx ", decoder_path=" ")
    assert dlg.values() == {"encoder": "/e.onnx", "decoder": ""}


def test_model_type_and_device_fields_are_gone():
    dlg = SamSettingsDialog()
    assert not hasattr(dlg, "_model_type")
    assert not hasattr(dlg, "_device")
    assert not hasattr(SamSettingsDialog, "MODEL_TYPES")
    assert not hasattr(SamSettingsDialog, "DEVICES")


def test_apply_theme_runs():
    SamSettingsDialog().apply_theme(Theme.DARK)     # must not raise
