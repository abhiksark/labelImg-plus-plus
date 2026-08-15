# tests/widgets/test_tool_rail.py
"""Structural coverage for the modern annotation tool rail."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import QAction, QApplication, QWidget

from libs.widgets.toolRail import AnnotationToolRail
from libs.widgets.workspaceInspector import (
    InspectorContextCard, WorkspaceInspector, WorkspaceSplitterShell,
)
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
        assert button.focusPolicy() == Qt.StrongFocus
    assert 'QToolButton:focus' in rail.styleSheet()


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
    inspector = WorkspaceInspector(QWidget(), QWidget())
    shell = WorkspaceSplitterShell(
        rail, canvas_column, inspector, scale_px(304))

    assert shell.layout().itemAt(0).widget() is rail
    assert shell.layout().itemAt(1).widget() is shell.splitter
    assert shell.splitter.widget(0) is canvas_column
    assert shell.splitter.widget(1) is inspector
    assert shell.layout().contentsMargins().left() == 0


def test_inspector_actions_have_names_and_keyboard_focus_treatment():
    card = InspectorContextCard()
    action = QAction('Accept & Next', card)
    card.set_context('Review', 'car', actions=(action,))
    button = card.action_buttons[0]
    inspector = WorkspaceInspector(QWidget(), QWidget())
    try:
        assert button.accessibleName() == 'Accept Next'
        assert button.focusPolicy() == Qt.StrongFocus
        assert inspector.collapse_button.focusPolicy() == Qt.StrongFocus
        assert inspector.collapse_button.accessibleName() == \
            'Collapse inspector'
        assert 'QToolButton:focus' in inspector.styleSheet()
    finally:
        card.close()
        inspector.close()
