"""Unit contracts for reusable workspace accessibility checks."""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget

from libs.utils.accessibility import (
    contrast_ratio, relative_luminance, visible_primary_targets,
)


app = QApplication.instance() or QApplication([])


def test_wcag_contrast_examples():
    """The helper follows the WCAG sRGB-to-luminance calculation."""
    assert relative_luminance(QColor('#000000')) == 0.0
    assert contrast_ratio(QColor('#000000'), QColor('#ffffff')) == 21.0
    assert contrast_ratio(QColor('#777777'), QColor('#ffffff')) == \
        pytest.approx(4.48, abs=.02)


def test_visible_primary_targets_include_visible_action_controls_only():
    """Hidden and explicit secondary controls never become primary targets."""
    root = QWidget()
    primary = QPushButton('Primary', root)
    text_entry = QLineEdit(root)
    secondary = QPushButton('Secondary', root)
    secondary.setProperty('secondaryAction', True)
    hidden = QPushButton('Hidden', root)
    hidden.hide()
    root.show()
    QApplication.processEvents()
    try:
        targets = visible_primary_targets(root)
        assert primary in targets
        assert text_entry in targets
        assert secondary not in targets
        assert hidden not in targets
    finally:
        root.close()
