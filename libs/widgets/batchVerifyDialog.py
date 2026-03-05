# libs/widgets/batchVerifyDialog.py
"""Batch verify/unverify dialog for annotation review workflow."""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt


class BatchVerifyDialog(QDialog):
    """Dialog for batch verifying or unverifying annotated images.

    Attributes:
        verify_radio: Radio button for verify mode.
        unverify_radio: Radio button for unverify mode.
        progress: Progress bar shown during batch operation.
        run_btn: Button to execute the batch operation.
    """

    def __init__(self, parent=None, image_count=0, annotated_count=0):
        """Initialize the batch verify dialog.

        Args:
            parent: Parent widget.
            image_count: Total number of images in the dataset.
            annotated_count: Number of images with annotations.
        """
        super().__init__(parent)
        self.setWindowTitle('Batch Verify')
        self.setMinimumWidth(350)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f'Images: {image_count}'))
        layout.addWidget(QLabel(f'Annotated: {annotated_count}'))
        layout.addWidget(QLabel(''))

        self.btn_group = QButtonGroup(self)
        self.verify_radio = QRadioButton('Verify all annotated images')
        self.unverify_radio = QRadioButton('Unverify all images')
        self.verify_radio.setChecked(True)
        self.btn_group.addButton(self.verify_radio)
        self.btn_group.addButton(self.unverify_radio)
        layout.addWidget(self.verify_radio)
        layout.addWidget(self.unverify_radio)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton('Run')
        self.run_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

    @property
    def verify_mode(self):
        """Return True if verify mode is selected, False for unverify."""
        return self.verify_radio.isChecked()

    def apply_theme(self, theme):
        """Apply the given theme stylesheet to this dialog.

        Args:
            theme: Theme enum value to apply.
        """
        from libs.utils.styles import get_stylesheet
        self.setStyleSheet(get_stylesheet(theme))
