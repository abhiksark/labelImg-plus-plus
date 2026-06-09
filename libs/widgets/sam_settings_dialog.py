# libs/widgets/sam_settings_dialog.py
"""Settings dialog for the SAM-assisted polygon backend."""

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget)


class SamSettingsDialog(QDialog):
    """Dialog for configuring SAM (Segment Anything Model) settings.

    Provides controls for checkpoint path, model type, and compute device.
    Unknown model_type/device values are silently normalized to valid defaults.
    """

    MODEL_TYPES = ["vit_t", "vit_b", "vit_h"]
    DEVICES = ["cpu", "cuda"]

    def __init__(self, checkpoint="", model_type="vit_t", device="cpu", parent=None):
        super().__init__(parent)
        self.setWindowTitle("SAM Settings")

        self._checkpoint = QLineEdit(checkpoint)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        ckpt_row = QHBoxLayout()
        ckpt_row.setContentsMargins(0, 0, 0, 0)
        ckpt_row.addWidget(self._checkpoint)
        ckpt_row.addWidget(browse)
        ckpt_widget = QWidget()
        ckpt_widget.setLayout(ckpt_row)

        self._model_type = QComboBox()
        self._model_type.addItems(self.MODEL_TYPES)
        if model_type in self.MODEL_TYPES:
            self._model_type.setCurrentText(model_type)

        self._device = QComboBox()
        self._device.addItems(self.DEVICES)
        if device in self.DEVICES:
            self._device.setCurrentText(device)

        form = QFormLayout()
        form.addRow("Checkpoint (blank = auto-download)", ckpt_widget)
        form.addRow("Model type", self._model_type)
        form.addRow("Device", self._device)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _browse(self):
        """Open file dialog to select a SAM checkpoint file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SAM checkpoint", "",
            "Checkpoints (*.pt *.pth);;All files (*)")
        if path:
            self._checkpoint.setText(path)

    def values(self):
        """Return the current settings as a dict."""
        return {
            "checkpoint": self._checkpoint.text().strip(),
            "model_type": self._model_type.currentText(),
            "device": self._device.currentText(),
        }

    def apply_theme(self, theme):
        """Apply a theme to this dialog."""
        from libs.utils.styles import get_stylesheet
        self.setStyleSheet(get_stylesheet(theme))
