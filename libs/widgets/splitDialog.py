# libs/widgets/splitDialog.py
"""Dataset split configuration dialog."""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QRadioButton, QSpinBox, QVBoxLayout,
)


class SplitDialog(QDialog):
    """Dialog for configuring dataset train/val/test split parameters."""

    def __init__(self, parent=None, image_count=0, default_dir=''):
        super().__init__(parent)
        self.setWindowTitle('Split Dataset')
        self.setMinimumWidth(450)
        self._image_count = image_count

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f'Total images: {image_count}'))

        # Ratio section
        ratio_group = QGroupBox('Split Ratios')
        ratio_layout = QVBoxLayout()
        self.train_spin = self._create_ratio_row(ratio_layout, 'Train:', 70)
        self.val_spin = self._create_ratio_row(ratio_layout, 'Val:', 20)
        self.test_spin = self._create_ratio_row(ratio_layout, 'Test:', 10)
        self.train_spin.valueChanged.connect(self._sync_ratios)
        self.val_spin.valueChanged.connect(self._sync_ratios)
        self.total_label = QLabel('Total: 100%')
        ratio_layout.addWidget(self.total_label)
        ratio_group.setLayout(ratio_layout)
        layout.addWidget(ratio_group)

        # Preview
        self.preview_label = QLabel('')
        self._update_preview()
        layout.addWidget(self.preview_label)

        # Options
        self.stratified_cb = QCheckBox('Stratified split (balance classes)')
        layout.addWidget(self.stratified_cb)

        # Seed
        seed_layout = QHBoxLayout()
        seed_layout.addWidget(QLabel('Random seed:'))
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 99999)
        self.seed_spin.setValue(42)
        seed_layout.addWidget(self.seed_spin)
        seed_layout.addStretch()
        layout.addLayout(seed_layout)

        # Output mode
        mode_group = QGroupBox('Output Mode')
        mode_layout = QHBoxLayout()
        self.copy_radio = QRadioButton('Copy files')
        self.symlink_radio = QRadioButton('Create symlinks')
        self.copy_radio.setChecked(True)
        mode_layout.addWidget(self.copy_radio)
        mode_layout.addWidget(self.symlink_radio)
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Output directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel('Output:'))
        self._output_dir = default_dir + '_split' if default_dir else ''
        self.dir_label = QLabel(self._output_dir or '(select)')
        self.dir_label.setWordWrap(True)
        dir_layout.addWidget(self.dir_label, 1)
        browse_btn = QPushButton('Browse...')
        browse_btn.clicked.connect(self._browse_output)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Buttons
        btn_layout = QHBoxLayout()
        self.run_btn = QPushButton('Split')
        self.run_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton('Cancel')
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self.run_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _create_ratio_row(self, layout, label, default):
        """Create a labeled spin box row for a split ratio.

        Args:
            layout: Parent layout to add the row to.
            label: Label text for the row.
            default: Default percentage value.

        Returns:
            The QSpinBox widget for the row.
        """
        row = QHBoxLayout()
        row.addWidget(QLabel(label))
        spin = QSpinBox()
        spin.setRange(0, 100)
        spin.setValue(default)
        spin.setSuffix('%')
        row.addWidget(spin)
        layout.addLayout(row)
        return spin

    def _sync_ratios(self):
        """Synchronize the test ratio when train or val changes."""
        train = self.train_spin.value()
        val = self.val_spin.value()
        test = 100 - train - val
        self.test_spin.blockSignals(True)
        self.test_spin.setValue(max(0, test))
        self.test_spin.blockSignals(False)
        total = train + val + max(0, test)
        self.total_label.setText(f'Total: {total}%')
        self._update_preview()

    def _update_preview(self):
        """Update the image count preview based on current ratios."""
        t = round(self._image_count * self.train_spin.value() / 100)
        v = round(self._image_count * self.val_spin.value() / 100)
        te = self._image_count - t - v
        self.preview_label.setText(f'Preview: Train={t}, Val={v}, Test={te}')

    def _browse_output(self):
        """Open a directory picker for the output directory."""
        path = QFileDialog.getExistingDirectory(self, 'Output Directory')
        if path:
            self._output_dir = path
            self.dir_label.setText(path)

    @property
    def ratios(self):
        """Return split ratios as a dict with float values summing to 1.0."""
        return {
            'train': self.train_spin.value() / 100,
            'val': self.val_spin.value() / 100,
            'test': self.test_spin.value() / 100,
        }

    @property
    def output_dir(self):
        """Return the selected output directory path."""
        return self._output_dir

    @property
    def seed(self):
        """Return the random seed value."""
        return self.seed_spin.value()

    @property
    def stratified(self):
        """Return whether stratified splitting is enabled."""
        return self.stratified_cb.isChecked()

    @property
    def copy_mode(self):
        """Return True if copy mode is selected, False for symlink."""
        return self.copy_radio.isChecked()

    def apply_theme(self, theme):
        """Apply a visual theme to the dialog.

        Args:
            theme: Theme enum value to apply.
        """
        from libs.utils.styles import get_stylesheet
        self.setStyleSheet(get_stylesheet(theme))
