"""Export selection dialog for smart-video projects."""

from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLineEdit, QPushButton, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QWidget,
)

from libs.formats.labelFile import LabelFileFormat


class VideoExportDialog(QDialog):
    def __init__(self, current_format, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Export Video Frames')
        self.destination = QLineEdit()
        browse = QPushButton('Browse…')
        browse.clicked.connect(self._browse)
        destination_row = QWidget()
        destination_layout = QHBoxLayout(destination_row)
        destination_layout.setContentsMargins(0, 0, 0, 0)
        destination_layout.addWidget(self.destination)
        destination_layout.addWidget(browse)

        self.selection = QComboBox()
        self.selection.addItem('Current frame', 'current')
        self.selection.addItem('Annotated frames', 'annotated')
        self.selection.addItem('Verified frames', 'verified')
        self.selection.addItem('Time range', 'range')
        self.selection.setCurrentIndex(1)
        self.start_time = QLineEdit('00:00:00.000')
        self.end_time = QLineEdit('00:00:05.000')
        self.sample_unit = QComboBox()
        self.sample_unit.addItem('frames', 'frames')
        self.sample_unit.addItem('seconds', 'seconds')
        self.sample_frames = QSpinBox()
        self.sample_frames.setRange(1, 1000000)
        self.sample_frames.setValue(1)
        self.sample_seconds = QDoubleSpinBox()
        self.sample_seconds.setRange(.001, 86400)
        self.sample_seconds.setDecimals(3)
        self.sample_seconds.setValue(1.0)

        self.image_format = QComboBox()
        self.image_format.addItem('JPEG (quality 95)', 'jpg')
        self.image_format.addItem('PNG (lossless)', 'png')
        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(1, 100)
        self.jpeg_quality.setValue(95)
        self.annotation_format = QComboBox()
        formats = (
            ('Pascal VOC', LabelFileFormat.PASCAL_VOC),
            ('YOLO', LabelFileFormat.YOLO),
            ('YOLO segmentation', LabelFileFormat.YOLO_SEG),
            ('COCO', LabelFileFormat.COCO),
            ('CreateML', LabelFileFormat.CREATE_ML),
        )
        for name, value in formats:
            self.annotation_format.addItem(name, value)
            if value == current_format:
                self.annotation_format.setCurrentIndex(
                    self.annotation_format.count() - 1)

        form = QFormLayout()
        form.addRow('Destination', destination_row)
        form.addRow('Frames', self.selection)
        form.addRow('Range start', self.start_time)
        form.addRow('Range end', self.end_time)
        form.addRow('Sample unit', self.sample_unit)
        form.addRow('Every N frames', self.sample_frames)
        form.addRow('Every N seconds', self.sample_seconds)
        form.addRow('Images', self.image_format)
        form.addRow('JPEG quality', self.jpeg_quality)
        form.addRow('Annotations', self.annotation_format)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.selection.currentIndexChanged.connect(self._update_enabled)
        self.sample_unit.currentIndexChanged.connect(self._update_enabled)
        self.image_format.currentIndexChanged.connect(self._update_enabled)
        self._update_enabled()

    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, 'Choose new or empty export directory')
        if path:
            self.destination.setText(path)

    def set_frame_counts(self, annotated, verified):
        """State the exact default-selection counts before export starts."""
        annotated_index = self.selection.findData('annotated')
        verified_index = self.selection.findData('verified')
        self.selection.setItemText(
            annotated_index, 'Annotated frames (%d accepted)' %
            max(0, int(annotated)))
        self.selection.setItemText(
            verified_index, 'Verified frames (%d)' %
            max(0, int(verified)))

    def _update_enabled(self, _value=None):
        ranged = self.selection.currentData() == 'range'
        self.start_time.setEnabled(ranged)
        self.end_time.setEnabled(ranged)
        self.sample_unit.setEnabled(ranged)
        frames = ranged and self.sample_unit.currentData() == 'frames'
        self.sample_frames.setEnabled(frames)
        self.sample_seconds.setEnabled(ranged and not frames)
        self.jpeg_quality.setEnabled(
            self.image_format.currentData() == 'jpg')

    def values(self):
        return {
            'destination': self.destination.text().strip(),
            'selection': self.selection.currentData(),
            'start_time': self.start_time.text().strip(),
            'end_time': self.end_time.text().strip(),
            'sample_unit': self.sample_unit.currentData(),
            'sample_frames': self.sample_frames.value(),
            'sample_seconds': self.sample_seconds.value(),
            'image_format': self.image_format.currentData(),
            'jpeg_quality': self.jpeg_quality.value(),
            'annotation_format': self.annotation_format.currentData(),
        }
