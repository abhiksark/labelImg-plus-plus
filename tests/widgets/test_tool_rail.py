"""Structural coverage for the modern annotation tool rail."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QSize
from PyQt5.QtWidgets import QAction, QApplication, QWidget

from libs.widgets.toolRail import AnnotationToolRail, WorkspaceShell
from libs.utils.dpi import scale_px


def _actions(parent):
    return tuple(
        (key, label, QAction(label, parent))
        for key, label in (
            ('select', 'Select'), ('box', 'Bounding Box'),
            ('polygon', 'Polygon'), ('smartSelect', 'Smart Select'),
            ('keypoints', 'Keypoints'),
        )
    )


def test_rail_has_fixed_logical_geometry_and_exclusive_actions():
    parent = QWidget()
    actions = _actions(parent)
    rail = AnnotationToolRail(actions)

    assert rail.minimumWidth() == rail.maximumWidth() == scale_px(52)
    assert rail.action_group.isExclusive()
    assert len(rail.buttons) == 5
    for key, _label, action in actions:
        button = rail.buttons[key]
        assert button.defaultAction() is action
        assert button.minimumSize() == QSize(scale_px(40), scale_px(40))
        assert button.maximumSize() == QSize(scale_px(40), scale_px(40))
        assert button.iconSize() == QSize(scale_px(20), scale_px(20))


def test_rail_tooltip_tracks_live_user_shortcut():
    parent = QWidget()
    actions = _actions(parent)
    rail = AnnotationToolRail(actions)
    box = actions[1][2]

    box.setShortcut('B')
    QApplication.processEvents()
    assert rail.buttons['box'].toolTip() == 'Bounding Box (B)'

    box.setShortcut('')
    QApplication.processEvents()
    assert rail.buttons['box'].toolTip() == 'Bounding Box'


def test_workspace_shell_keeps_rail_beside_canvas_column():
    parent = QWidget()
    rail = AnnotationToolRail(_actions(parent))
    canvas_column = QWidget()
    shell = WorkspaceShell(rail, canvas_column)

    assert shell.layout().itemAt(0).widget() is rail
    assert shell.layout().itemAt(1).widget() is canvas_column
    assert shell.layout().contentsMargins().left() == 0
