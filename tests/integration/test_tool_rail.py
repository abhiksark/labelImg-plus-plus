"""Main-window integration coverage for modern tool activation."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QEvent, QPointF, Qt
from PyQt5.QtGui import QKeyEvent, QKeySequence
from PyQt5.QtWidgets import QApplication, QToolBar

from labelImgPlusPlus import MainWindow
from libs.integrations import segmentation
from libs.utils.dpi import scale_px
from libs.widgets.shortcutsDialog import ShortcutsDialog


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def test_main_window_uses_fixed_rail_without_legacy_toolbar(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.centralWidget() is window.workspace_shell
        assert window.tool_rail.width() == scale_px(52)
        assert window.findChildren(QToolBar) == []
        assert window.tool_rail.buttons['select'].defaultAction() is \
            window.actions.editMode
        assert window.tool_rail.buttons['box'].defaultAction() is \
            window.actions.create
        assert window.tool_rail.buttons['polygon'].defaultAction() is \
            window.actions.create_polygon
        assert window.tool_rail.buttons['smartSelect'].defaultAction() is \
            window.actions.sam_mode
        assert window.tool_rail.buttons['keypoints'].defaultAction() is \
            window.actions.keypoint_mode
    finally:
        window.dirty = False
        window.close()


def test_neutral_entry_points_sync_exclusive_state_and_canvas_focus(
        monkeypatch, tmp_path):
    monkeypatch.setattr(segmentation, 'sam_available', lambda: True)
    window = _window(monkeypatch, tmp_path)
    try:
        window.file_path = os.path.join(str(tmp_path), 'frame.png')
        window.canvas.setEnabled(True)
        window.toggle_actions(True)
        window.show()
        QApplication.processEvents()

        window.activate_box_tool()
        assert window.canvas.mode == window.canvas.CREATE
        assert window.actions.create.isChecked()

        window.activate_polygon_tool()
        assert window.canvas.mode == window.canvas.CREATE_POLYGON
        assert window.actions.create_polygon.isChecked()

        window.activate_smart_select_tool()
        assert window.workspace_pages.assist_panel.isVisible()
        assert window.canvas.mode == window.canvas.CREATE_POLYGON
        assert window.actions.create_polygon.isChecked()
        assert not window.actions.sam_mode.isChecked()

        window.activate_select_tool()
        QApplication.processEvents()
        assert window.canvas.mode == window.canvas.EDIT
        assert window.actions.editMode.isChecked()
        assert window.canvas.hasFocus()

        checked = [
            action for action in window.tool_rail.action_group.actions()
            if action.isChecked()]
        assert checked == [window.actions.editMode]
    finally:
        window.dirty = False
        window.close()


def test_sync_repairs_drifted_checked_state_from_canvas_mode(
        monkeypatch, tmp_path):
    """A repaint/state drift must not leave two tools visibly selected."""
    window = _window(monkeypatch, tmp_path)
    try:
        group = window.tool_rail.action_group
        group.setExclusive(False)
        window.actions.editMode.setChecked(True)
        window.actions.create_polygon.setChecked(True)
        group.setExclusive(True)
        window.canvas.mode = window.canvas.EDIT

        window._sync_tool_actions()

        checked = [
            action for action in group.actions() if action.isChecked()
        ]
        assert checked == [window.actions.editMode]
        assert window.label_active_tool.text().startswith('Select')
    finally:
        window.dirty = False
        window.close()


def test_legacy_callbacks_route_through_neutral_entry_points(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.file_path = os.path.join(str(tmp_path), 'frame.png')
        window.canvas.setEnabled(True)
        window.toggle_actions(True)

        window.create_shape()
        assert window.canvas.mode == window.canvas.CREATE
        window.create_polygon_mode()
        assert window.canvas.mode == window.canvas.CREATE_POLYGON
        window.set_edit_mode()
        assert window.canvas.mode == window.canvas.EDIT
    finally:
        window.dirty = False
        window.close()


def test_shortcut_dialog_updates_smart_select_action_and_tooltip(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    dialog = ShortcutsDialog(
        window.shortcut_config, window._action_map, window)
    try:
        assert window.shortcut_config.get_default('sam_mode') == 'S'
        assert window._action_map['sam_mode'] is window.actions.sam_mode

        dialog._on_shortcut_changed(
            0, 'sam_mode', QKeySequence('Alt+S'))
        QApplication.processEvents()

        assert window.actions.sam_mode.shortcut().toString() == 'Alt+S'
        assert window.tool_rail.buttons['smartSelect'].toolTip() == \
            'Smart Select (%s)' % QKeySequence('Alt+S').toString(
                QKeySequence.NativeText)
    finally:
        dialog.close()
        window.dirty = False
        window.close()


def test_tooltip_presents_shortcut_in_native_platform_text(
        monkeypatch, tmp_path):
    """macOS-facing hints must say Command when Qt maps Ctrl to Command."""
    window = _window(monkeypatch, tmp_path)
    try:
        sequence = QKeySequence('Ctrl+G')
        window.actions.create_polygon.setShortcut(sequence)
        QApplication.processEvents()

        expected = sequence.toString(QKeySequence.NativeText)
        assert window.tool_rail.buttons['polygon'].toolTip() == \
            'Polygon (%s)' % expected
    finally:
        window.dirty = False
        window.close()


def test_escape_from_box_returns_to_select_and_leaves_box_usable(
        monkeypatch, tmp_path):
    """Escape must not strand the Box action disabled.

    activate_box_tool disables actions.create so the armed tool cannot be
    re-armed. Escape returns the canvas to EDIT without going through
    activate_select_tool, and with nothing in flight it emits no
    drawingPolygon(False) either, so toggle_drawing_sensitive never runs.
    Only _on_canvas_mode_changed re-enables it -- without that slot the user
    can never draw again.
    """
    window = _window(monkeypatch, tmp_path)
    try:
        window.file_path = os.path.join(str(tmp_path), 'frame.png')
        window.canvas.setEnabled(True)
        window.toggle_actions(True)

        window.activate_box_tool()
        assert window.canvas.mode == window.canvas.CREATE
        assert not window.actions.create.isEnabled()

        window.canvas.keyPressEvent(
            QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
        QApplication.processEvents()

        assert window.canvas.mode == window.canvas.EDIT
        assert window.actions.editMode.isChecked()
        assert window.actions.create.isEnabled()
        assert window.actions.create_polygon.isEnabled()

        # And the tool is genuinely re-armable.
        window.activate_box_tool()
        assert window.canvas.mode == window.canvas.CREATE
    finally:
        window.dirty = False
        window.close()


def test_context_menu_copy_here_is_undoable(monkeypatch, tmp_path):
    """"&Copy here" mutated canvas.shapes without pushing a Command.

    end_move(copy=True) appends the drag shadow to canvas.shapes directly, so
    without an explicit push Ctrl+Z skipped straight past the duplicate. The
    sibling copy_selected_shape (Ctrl+D) always got this right.
    """
    from libs.core.shape import Shape

    window = _window(monkeypatch, tmp_path)
    try:
        window.file_path = os.path.join(str(tmp_path), 'frame.png')
        window.canvas.setEnabled(True)
        window.toggle_actions(True)

        original = Shape(label='crate')
        for point in [(10, 10), (60, 10), (60, 60), (10, 60)]:
            original.add_point(QPointF(*point))
        original.close()
        window.canvas.load_shapes([original])
        window.add_label(original)

        # Stand in for a right-drag: a shadow copy offset from the original.
        window.canvas.selected_shape = original
        shadow = original.copy()
        for point in shadow.points:
            point.setX(point.x() + 25)
        window.canvas.selected_shape_copy = shadow

        depth_before = len(window.canvas.shapes)
        window.copy_shape()

        assert len(window.canvas.shapes) == depth_before + 1
        assert window.undo_stack.can_undo()

        window.undo_action()

        assert len(window.canvas.shapes) == depth_before
        assert window.canvas.shapes == [original]
    finally:
        window.dirty = False
        window.close()
