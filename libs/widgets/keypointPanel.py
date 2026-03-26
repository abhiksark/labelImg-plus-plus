# libs/widgets/keypointPanel.py
"""Inline keypoint checklist panel for the label sidebar."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton)
from PyQt5.QtCore import pyqtSignal, Qt

from libs.core.keypoint_config import COCO_KEYPOINT_NAMES, get_keypoint_color
from libs.utils.styles import get_theme_colors


class KeypointPanel(QWidget):
    """Inline panel showing 17-point keypoint checklist."""

    keypointClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._keypoints = None
        self._current_index = -1
        self._init_ui()
        self.hide()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._count_label = QLabel('0/17 placed')
        self._count_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._count_label)

        for i, name in enumerate(COCO_KEYPOINT_NAMES):
            row = QHBoxLayout()
            row.setSpacing(4)

            status_label = QLabel('\u25cb')  # ○
            status_label.setFixedWidth(16)
            status_label.setAlignment(Qt.AlignCenter)

            name_btn = QPushButton(name.replace('_', ' ').title())
            name_btn.setFlat(True)
            name_btn.setCursor(Qt.PointingHandCursor)
            name_btn.clicked.connect(lambda checked, idx=i: self.keypointClicked.emit(idx))

            color_indicator = QLabel()
            color_indicator.setFixedSize(8, 8)
            color_hex = get_keypoint_color(i)
            color_indicator.setStyleSheet(
                'background: %s; border-radius: 4px;' % color_hex)

            row.addWidget(color_indicator)
            row.addWidget(status_label)
            row.addWidget(name_btn, 1)

            container = QWidget()
            container.setLayout(row)
            layout.addWidget(container)

            self._rows.append({
                'status': status_label,
                'button': name_btn,
                'container': container,
            })

    def set_keypoints(self, keypoints):
        """Update the panel with current keypoint state."""
        self._keypoints = keypoints
        placed = 0
        for i, row in enumerate(self._rows):
            if keypoints is None or keypoints[i] is None:
                row['status'].setText('\u25cb')  # ○ pending
                row['status'].setStyleSheet('color: #888;')
            else:
                v = keypoints[i][2]
                if v == 2:
                    row['status'].setText('\u25cf')  # ● visible
                    row['status'].setStyleSheet('color: #4caf50;')
                    placed += 1
                elif v == 1:
                    row['status'].setText('\u25cc')  # ◌ occluded
                    row['status'].setStyleSheet('color: #ff9800;')
                    placed += 1
                else:
                    row['status'].setText('\u2014')  # — skipped
                    row['status'].setStyleSheet('color: #888;')
        self._count_label.setText('%d/17 placed' % placed)

    def set_current_index(self, index):
        """Highlight the currently active keypoint."""
        self._current_index = index
        for i, row in enumerate(self._rows):
            if i == index:
                row['button'].setStyleSheet('font-weight: bold; text-decoration: underline;')
            else:
                row['button'].setStyleSheet('')

    def apply_theme(self, theme):
        """Apply theme styling."""
        colors = get_theme_colors(theme)
        self._count_label.setStyleSheet('color: %s;' % colors['text_secondary'])

    def clear(self):
        """Reset panel to empty state."""
        self._keypoints = None
        self._current_index = -1
        for row in self._rows:
            row['status'].setText('\u25cb')
            row['status'].setStyleSheet('color: #888;')
            row['button'].setStyleSheet('')
        self._count_label.setText('0/17 placed')
