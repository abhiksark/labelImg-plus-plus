"""Keyboard and assistive-technology contracts for the workspace shell."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QCloseEvent
from PyQt5.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QPushButton, QToolButton, QWidget,
)
from PyQt5.QtTest import QTest

from labelImgPlusPlus import MainWindow


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()
    QApplication.processEvents()


def _chrome_button(window, action):
    return next(
        button for button in
        window.workspace_pages.canvas_chrome.findChildren(QToolButton)
        if button.defaultAction() is action)


def _reachable_focus_widgets(window, start):
    reachable = []
    current = start
    for _index in range(128):
        if (current.isVisibleTo(window) and current.isEnabled()
                and current.focusPolicy() != Qt.NoFocus):
            reachable.append(current)
        current = current.nextInFocusChain()
        if current is start:
            break
    return reachable


def _contains_subsequence(actual, expected):
    position = 0
    for widget in actual:
        if widget is expected[position]:
            position += 1
            if position == len(expected):
                return True
    return False


def test_primary_workspace_controls_have_accessible_names(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.canvas.accessibleName() == 'Annotation canvas'
        assert window.active_class_control.combo.accessibleName() == \
            'Active annotation class'
        assert window.combo_box.cb.accessibleName() == \
            'Filter annotations by class'
        assert window.annotation_search.accessibleName() == \
            'Search annotations'
        assert window.label_list.accessibleName() == 'Annotations'
        assert window.status_filter_combo.accessibleName() == \
            'Filter files by annotation status'
        assert window.file_list_widget.accessibleName() == 'Dataset files'
        assert window.workspace_inspector.tabs.accessibleName() == 'Inspector'
        assert window.full_gallery.list_widget.accessibleName() == \
            'Dataset gallery'
    finally:
        _close(window)


def test_primary_workspace_targets_accept_tab_focus(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.canvas.focusPolicy() == Qt.StrongFocus
        assert all(button.focusPolicy() == Qt.StrongFocus
                   for button in window.tool_rail.buttons.values())
        chrome_buttons = [
            button for button in
            window.workspace_pages.canvas_chrome.findChildren(QToolButton)
        ]
        assert chrome_buttons
        assert all(button.focusPolicy() == Qt.StrongFocus
                   for button in chrome_buttons)
        assert window.workspace_inspector.collapse_button.focusPolicy() == \
            Qt.StrongFocus
        assert window.workspace_shell.reopen_button.focusPolicy() == \
            Qt.StrongFocus
    finally:
        _close(window)


def test_canvas_focus_chain_contains_tools_chrome_and_inspector(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.file_path = str(tmp_path / 'frame.png')
        window.canvas.setEnabled(True)
        window.toggle_actions(True)
        window.zoom_widget.setEnabled(True)
        for action in window.tool_rail.action_group.actions():
            action.setEnabled(True)
        window.workspace_pages.set_page('canvas')
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()

        reachable = _reachable_focus_widgets(
            window, window.command_bar.application_button)
        expected = [
            window.command_bar.application_button,
            window.command_bar.open_button,
            window.tool_rail.buttons['select'],
            window.tool_rail.buttons['box'],
            window.tool_rail.buttons['polygon'],
            _chrome_button(window, window.actions.zoomOut),
            window.zoom_widget,
            _chrome_button(window, window.actions.zoomIn),
            window.canvas,
            window.workspace_inspector.tabs,
            window.annotation_search,
            window.label_list,
            window.workspace_inspector.collapse_button,
        ]
        assert _contains_subsequence(reachable, expected)
    finally:
        _close(window)


def test_drawer_scrim_dismisses_and_restores_reopen_focus(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()
        assert window.workspace_inspector.collapse_button.accessibleName() == \
            'Close inspector'

        QTest.mouseClick(window.workspace_shell.scrim, Qt.LeftButton)
        QApplication.processEvents()
        assert window.workspace_inspector.isHidden()
        assert window.workspace_shell.reopen_button.hasFocus()
    finally:
        _close(window)


def test_tab_focus_stays_inside_visible_drawer(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()

        for _index in range(32):
            QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
            QApplication.processEvents()
            focused = QApplication.focusWidget()
            assert focused is window.workspace_inspector or \
                window.workspace_inspector.isAncestorOf(focused)
    finally:
        _close(window)


def test_reopen_accessible_name_includes_current_object_count(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 0 objects'
        window.canvas.shapes = [object(), object(), object()]
        window.update_box_count()
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 3 objects'

        window.reset_state()
        assert window.workspace_shell.reopen_button.accessibleName() == \
            'Open inspector, 0 objects'
    finally:
        _close(window)


def _focus_pair(container):
    first = QPushButton('First', container)
    second = QPushButton('Second', container)
    layout = QHBoxLayout(container)
    layout.addWidget(first)
    layout.addWidget(second)
    QWidget.setTabOrder(first, second)
    return first, second


def test_shift_tab_stays_inside_visible_drawer(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()
        window.workspace_inspector.tabs.setFocus()

        QTest.keyClick(
            window.workspace_inspector.tabs, Qt.Key_Tab, Qt.ShiftModifier)
        QApplication.processEvents()

        focused = QApplication.focusWidget()
        assert focused is window.workspace_inspector or \
            window.workspace_inspector.isAncestorOf(focused)
    finally:
        _close(window)


def test_drawer_filter_does_not_intercept_child_dialog(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    dialog = QDialog(window)
    first, second = _focus_pair(dialog)
    try:
        window.resize(800, 600)
        window.show()
        window.workspace_shell.open_inspector()
        dialog.setModal(True)
        dialog.show()
        first.setFocus()
        QApplication.processEvents()

        QTest.keyClick(first, Qt.Key_Tab)
        QApplication.processEvents()
        assert second.hasFocus()
        QTest.keyClick(second, Qt.Key_Escape)
        QApplication.processEvents()
        assert window.workspace_inspector.isVisible()
    finally:
        dialog.close()
        _close(window)


def test_drawer_filter_does_not_intercept_another_window(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    other = QWidget()
    first, second = _focus_pair(other)
    try:
        window.resize(800, 600)
        window.show()
        window.workspace_shell.open_inspector()
        other.show()
        other.activateWindow()
        first.setFocus()
        QApplication.processEvents()

        QTest.keyClick(first, Qt.Key_Tab)
        QApplication.processEvents()
        assert second.hasFocus()
        QTest.keyClick(second, Qt.Key_Escape)
        QApplication.processEvents()
        assert window.workspace_inspector.isVisible()
    finally:
        other.close()
        _close(window)


def test_hiding_open_drawer_removes_application_focus_filter(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    other = QWidget()
    first, second = _focus_pair(other)
    try:
        window.resize(800, 600)
        window.show()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()
        window.hide()
        other.show()
        first.setFocus()
        QApplication.processEvents()

        QTest.keyClick(first, Qt.Key_Tab)
        QApplication.processEvents()

        assert second.hasFocus()
    finally:
        other.close()
        _close(window)


def _owner_focus_probe(window):
    probe = QWidget(window)
    probe.setGeometry(8, 8, 240, 56)
    first, second = _focus_pair(probe)
    probe.show()
    probe.raise_()
    return probe, first, second


def test_closing_open_drawer_removes_application_focus_filter(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    probe, first, second = _owner_focus_probe(window)
    try:
        window.resize(800, 600)
        window.show()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()

        QApplication.sendEvent(window.workspace_shell, QCloseEvent())
        window.activateWindow()
        first.setFocus()
        QApplication.processEvents()

        QTest.keyClick(first, Qt.Key_Tab)
        QApplication.processEvents()

        assert second.hasFocus()
    finally:
        probe.close()
        window.deleteLater()
        QApplication.sendPostedEvents(window, QEvent.DeferredDelete)
        QApplication.processEvents()


def test_deferred_delete_of_open_drawer_removes_application_focus_filter(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    probe, first, second = _owner_focus_probe(window)
    try:
        window.resize(800, 600)
        window.show()
        window.workspace_shell.open_inspector()
        QApplication.processEvents()

        shell = window.workspace_shell
        shell.deleteLater()
        QApplication.sendPostedEvents(shell, QEvent.DeferredDelete)
        QApplication.processEvents()
        window.activateWindow()
        first.setFocus()
        QApplication.processEvents()

        QTest.keyClick(first, Qt.Key_Tab)
        QApplication.processEvents()

        assert second.hasFocus()
    finally:
        probe.close()
        window.deleteLater()
        QApplication.sendPostedEvents(window, QEvent.DeferredDelete)
        QApplication.processEvents()
