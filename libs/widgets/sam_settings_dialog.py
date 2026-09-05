# libs/widgets/sam_settings_dialog.py
"""Settings dialog for the SAM-assisted polygon backend."""

from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QWidget)

from libs.core.video_sam2 import normalize_propagation_backend
from libs.utils.dpi import scale_px


class SamSettingsDialog(QDialog):
    """Dialog for configuring the ONNX model pair used by SAM segmentation.

    Both paths empty (the default) means the bundled MobileSAM pair is
    auto-downloaded on first use. Custom models must be set as a pair.
    """

    def __init__(self, encoder_path="", decoder_path="", parent=None,
                 propagation_backend="auto", sam2_checkpoint="",
                 sam2_config=""):
        super().__init__(parent)
        self.setWindowTitle("SAM Settings")
        self.setMinimumWidth(scale_px(480))

        self._encoder = QLineEdit(encoder_path)
        self._decoder = QLineEdit(decoder_path)

        image_form = QFormLayout()
        image_form.addRow(
            "Encoder model (.onnx)",
            self._path_row(self._encoder, "Select SAM encoder model"))
        image_form.addRow(
            "Decoder model (.onnx)",
            self._path_row(self._decoder, "Select SAM decoder model"))
        image_group = QGroupBox("Smart Select")
        image_group.setLayout(image_form)

        hint = QLabel("Leave both empty to use the bundled MobileSAM "
                      "(downloaded on first use). Custom models require "
                      "both an encoder and a decoder.")
        hint.setWordWrap(True)

        self._propagation_backend = QComboBox()
        self._propagation_backend.addItem("Auto (recommended)", "auto")
        self._propagation_backend.addItem("OpenCV (portable)", "opencv")
        self._propagation_backend.addItem("SAM 2 (Linux/CUDA)", "sam2")
        selected = normalize_propagation_backend(propagation_backend)
        self._propagation_backend.setCurrentIndex(
            max(0, self._propagation_backend.findData(selected)))
        self._sam2_checkpoint = QLineEdit(sam2_checkpoint)
        self._sam2_config = QLineEdit(sam2_config)
        propagation_form = QFormLayout()
        propagation_form.addRow("Backend", self._propagation_backend)
        propagation_form.addRow(
            "SAM 2 checkpoint (.pt)", self._path_row(
                self._sam2_checkpoint, "Select SAM 2 checkpoint",
                "PyTorch checkpoints (*.pt *.pth);;All files (*)"))
        propagation_form.addRow(
            "SAM 2 config (.yaml)", self._path_row(
                self._sam2_config, "Select SAM 2 model config",
                "YAML configs (*.yaml *.yml);;All files (*)"))
        propagation_group = QGroupBox("Whole-video propagation")
        propagation_group.setLayout(propagation_form)
        propagation_hint = QLabel(
            "Auto uses SAM 2 only on Linux with Python 3.10+, a compatible "
            "source installation, CUDA, and both configured files; otherwise "
            "it uses OpenCV. labelImg++ never downloads or bundles Torch, "
            "SAM 2, checkpoints, or configs.")
        propagation_hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(image_group)
        layout.addWidget(hint)
        layout.addWidget(propagation_group)
        layout.addWidget(propagation_hint)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _path_row(self, line_edit, caption,
                  file_filter="ONNX models (*.onnx);;All files (*)"):
        """Wrap a line edit and its Browse... button into one form-row widget."""
        browse = QPushButton("Browse…")
        browse.clicked.connect(
            lambda: self._browse(line_edit, caption, file_filter))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        row.addWidget(browse)
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _browse(self, line_edit, caption, file_filter):
        path, _ = QFileDialog.getOpenFileName(
            self, caption, "", file_filter)
        if path:
            line_edit.setText(path)

    def values(self):
        """Return the original image-SAM settings contract."""
        return {
            "encoder": self._encoder.text().strip(),
            "decoder": self._decoder.text().strip(),
        }

    def propagation_values(self):
        """Return whole-video propagation settings without loading SAM 2."""
        return {
            "backend": normalize_propagation_backend(
                self._propagation_backend.currentData()),
            "checkpoint": self._sam2_checkpoint.text().strip(),
            "config": self._sam2_config.text().strip(),
        }

    def apply_theme(self, theme):
        """Apply a theme to this dialog."""
        from libs.utils.styles import get_stylesheet
        self.setStyleSheet(get_stylesheet(theme))
