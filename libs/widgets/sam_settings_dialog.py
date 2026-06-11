# libs/widgets/sam_settings_dialog.py
"""Settings dialog for the SAM-assisted polygon backend."""

from PyQt5.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget)

from libs.utils.dpi import scale_px


class SamSettingsDialog(QDialog):
    """Dialog for configuring the ONNX model pair used by SAM segmentation.

    Both paths empty (the default) means the bundled MobileSAM pair is
    auto-downloaded on first use. Custom models must be set as a pair.
    """

    def __init__(self, encoder_path="", decoder_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("SAM Settings")
        self.setMinimumWidth(scale_px(480))

        self._encoder = QLineEdit(encoder_path)
        self._decoder = QLineEdit(decoder_path)

        form = QFormLayout()
        form.addRow("Encoder model (.onnx)",
                    self._path_row(self._encoder, "Select SAM encoder model"))
        form.addRow("Decoder model (.onnx)",
                    self._path_row(self._decoder, "Select SAM decoder model"))

        hint = QLabel("Leave both empty to use the bundled MobileSAM "
                      "(downloaded on first use). Custom models require "
                      "both an encoder and a decoder.")
        hint.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(buttons)
        self.setLayout(layout)

    def _path_row(self, line_edit, caption):
        """Wrap a line edit and its Browse... button into one form-row widget."""
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: self._browse(line_edit, caption))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(line_edit)
        row.addWidget(browse)
        widget = QWidget()
        widget.setLayout(row)
        return widget

    def _browse(self, line_edit, caption):
        path, _ = QFileDialog.getOpenFileName(
            self, caption, "", "ONNX models (*.onnx);;All files (*)")
        if path:
            line_edit.setText(path)

    def values(self):
        """Return the current settings as a dict."""
        return {
            "encoder": self._encoder.text().strip(),
            "decoder": self._decoder.text().strip(),
        }

    def apply_theme(self, theme):
        """Apply a theme to this dialog."""
        from libs.utils.styles import get_stylesheet
        self.setStyleSheet(get_stylesheet(theme))
