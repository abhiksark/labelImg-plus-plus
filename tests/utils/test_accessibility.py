"""Unit contracts for reusable workspace accessibility checks."""

import builtins
import types

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton, QWidget

import libs.utils.styles as styles
from libs.utils.accessibility import (
    contrast_ratio, relative_luminance, visible_primary_targets,
)
from libs.widgets.zoomWidget import ZoomWidget


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


def test_visible_primary_targets_include_zoom_spinbox_not_its_editor():
    """A visible ZoomWidget must be measured once as its primary control."""
    root = QWidget()
    zoom = ZoomWidget()
    zoom.setParent(root)
    zoom.lineEdit().setProperty('secondaryAction', True)
    root.show()
    QApplication.processEvents()
    try:
        targets = visible_primary_targets(root)
        assert zoom in targets
        assert zoom.lineEdit() not in targets
    finally:
        root.close()


def test_hex_to_qcolor_uses_pyqt4_qcolor_when_pyqt5_is_unavailable(
        monkeypatch):
    """Theme conversion still works in a PyQt4-only base installation."""
    class FakeQColor(object):
        def __init__(self, red, green, blue, alpha):
            self.rgba = (red, green, blue, alpha)

    pyqt4_qtgui = types.ModuleType('PyQt4.QtGui')
    pyqt4_qtgui.QColor = FakeQColor
    real_import = builtins.__import__

    def import_with_pyqt4_fallback(name, globals=None, locals=None,
                                  fromlist=(), level=0):
        if name == 'PyQt5.QtGui':
            raise ImportError('PyQt5 unavailable in this base install')
        if name == 'PyQt4.QtGui':
            return pyqt4_qtgui
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', import_with_pyqt4_fallback)
    color = styles.hex_to_qcolor('#123456', alpha=78)

    assert isinstance(color, FakeQColor)
    assert color.rgba == (18, 52, 86, 78)
