# libs/widgets/keypointPanel.py
"""Inline keypoint checklist panel for the label sidebar."""

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                              QPushButton)
from PyQt5.QtCore import pyqtSignal, Qt

from libs.core.keypoint_config import get_keypoint_color, get_template
from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_theme_colors


class KeypointPanel(QWidget):
    """Inline panel showing keypoint checklist for any template."""

    keypointClicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._keypoints = None
        self._current_index = -1
        self._template_name = None
        self._template = None
        # Active theme palette; status glyph colors are sourced from it so
        # they re-theme instead of being hardcoded.
        self._colors = get_theme_colors(Theme.LIGHT)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(2)
        self._count_label = QLabel('0/0 placed')
        self._count_label.setAlignment(Qt.AlignCenter)
        self._layout.addWidget(self._count_label)
        self.hide()

    def load_template(self, template_name):
        """Build the panel rows for a given template (e.g., 'person', 'face')."""
        if template_name == self._template_name and self._rows:
            return

        # Clear existing rows
        for row in self._rows:
            row['container'].setParent(None)
            row['container'].deleteLater()
        self._rows = []

        self._template_name = template_name
        self._template = get_template(template_name)
        if not self._template:
            return

        names = self._template['names']
        for i, name in enumerate(names):
            row = QHBoxLayout()
            row.setSpacing(4)

            status_label = QLabel('\u25cb')
            status_label.setFixedWidth(scale_px(16))
            status_label.setAlignment(Qt.AlignCenter)

            name_btn = QPushButton(name.replace('_', ' ').title())
            name_btn.setFlat(True)
            name_btn.setCursor(Qt.PointingHandCursor)
            name_btn.clicked.connect(
                lambda checked, idx=i: self.keypointClicked.emit(idx))

            color_indicator = QLabel()
            color_indicator.setFixedSize(scale_px(8), scale_px(8))
            color_hex = get_keypoint_color(i, template_name)
            color_indicator.setStyleSheet(
                'background: %s; border-radius: %dpx;' % (color_hex, scale_px(4)))

            row.addWidget(color_indicator)
            row.addWidget(status_label)
            row.addWidget(name_btn, 1)

            container = QWidget()
            container.setLayout(row)
            self._layout.addWidget(container)

            self._rows.append({
                'status': status_label,
                'button': name_btn,
                'container': container,
            })

        self._count_label.setText('0/%d placed' % len(names))

    def set_keypoints(self, keypoints):
        """Update the panel with current keypoint state."""
        self._keypoints = keypoints
        total = len(self._rows)
        placed = 0
        missing = 'color: %s;' % self._colors['text_disabled']
        for i, row in enumerate(self._rows):
            if keypoints is None or i >= len(keypoints) or keypoints[i] is None:
                row['status'].setText('\u25cb')
                row['status'].setStyleSheet(missing)
            else:
                v = keypoints[i][2]
                if v == 2:
                    row['status'].setText('\u25cf')
                    row['status'].setStyleSheet(
                        'color: %s;' % self._colors['success'])
                    placed += 1
                elif v == 1:
                    row['status'].setText('\u25cc')
                    row['status'].setStyleSheet(
                        'color: %s;' % self._colors['warning'])
                    placed += 1
                else:
                    row['status'].setText('\u2014')
                    row['status'].setStyleSheet(missing)
        self._count_label.setText('%d/%d placed' % (placed, total))

    def set_current_index(self, index):
        """Highlight the currently active keypoint."""
        self._current_index = index
        for i, row in enumerate(self._rows):
            if i == index:
                row['button'].setStyleSheet(
                    'font-weight: bold; text-decoration: underline;')
            else:
                row['button'].setStyleSheet('')

    def apply_theme(self, theme):
        """Apply theme styling."""
        self._colors = get_theme_colors(theme)
        self._count_label.setStyleSheet(
            'color: %s;' % self._colors['text_secondary'])
        # Repaint existing rows so status colors follow the new theme.
        self.set_keypoints(self._keypoints)
        self.set_current_index(self._current_index)

    def clear(self):
        """Reset panel to empty state."""
        self._keypoints = None
        self._current_index = -1
        for row in self._rows:
            row['status'].setText('\u25cb')
            row['status'].setStyleSheet(
                'color: %s;' % self._colors['text_disabled'])
            row['button'].setStyleSheet('')
        total = len(self._rows)
        self._count_label.setText('0/%d placed' % total)
