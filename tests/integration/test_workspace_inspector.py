"""Structural and persistence coverage for the fixed workspace inspector."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication, QDockWidget, QToolBar
from PyQt5.QtTest import QTest

from labelImgPlusPlus import MainWindow
from libs.core.dataset import DatasetSnapshot
from libs.core.settings import Settings
from libs.utils.constants import (
    SETTING_ADVANCE_MODE, SETTING_ICON_SIZE, SETTING_INSPECTOR_COLLAPSED,
    SETTING_INSPECTOR_TAB, SETTING_INSPECTOR_WIDTH,
    SETTING_PROMPT_POLICY, SETTING_SINGLE_CLASS, SETTING_TOOLBAR_EXPANDED,
    SETTING_WIN_STATE,
)
from libs.utils.dpi import scale_px


def _write_settings(monkeypatch, tmp_path, values):
    monkeypatch.setenv('HOME', str(tmp_path))
    settings = Settings()
    settings.data.update(values)
    assert settings.save()


def _window(monkeypatch, tmp_path, values=None):
    _write_settings(monkeypatch, tmp_path, values or {})
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()
    QApplication.processEvents()


def _view_actions(window):
    found = set()
    for action in window.menus.view.actions():
        found.add(action)
        if action.menu() is not None:
            found.add(action.menu().menuAction())
    return found


def test_splitter_reparents_existing_controls_without_backing_duplicates(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        assert window.workspace_shell.splitter.widget(0) is \
            window.workspace_pages
        assert window.scroll_area.parent() is window.workspace_pages.canvas_page
        assert window.workspace_shell.splitter.widget(1) is \
            window.workspace_inspector
        assert window.workspace_inspector.tabs.widget(0) is \
            window.annotation_controls
        assert window.workspace_inspector.tabs.widget(1) is \
            window.file_controls
        assert window.label_list is window.rect_label_list
        assert window.label_list is window.poly_label_list
        assert window.label_list is window.track_list_widget
        assert not hasattr(window, 'label_tab_widget')
        assert window.file_list_widget.parent() is not None

        assert window.findChildren(QToolBar) == []
        assert window.findChildren(QDockWidget) == []
        assert window.video_timeline.parent() is \
            window.workspace_pages.canvas_page
    finally:
        _close(window)


def test_inspector_restores_width_tab_and_collapsed_state(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path, {
        SETTING_INSPECTOR_WIDTH: 350,
        SETTING_INSPECTOR_COLLAPSED: True,
        SETTING_INSPECTOR_TAB: 'files',
    })
    try:
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()
        assert window.workspace_shell.is_inspector_collapsed()
        assert window.workspace_shell.reopen_button.isVisible()
        assert window.workspace_inspector.selected_tab() == 'files'

        window.workspace_shell.reopen_button.click()
        QApplication.processEvents()
        assert not window.workspace_shell.is_inspector_collapsed()
        assert abs(window.workspace_shell.inspector_width()
                   - scale_px(350)) <= scale_px(3)
        assert window.actions.inspectorVisible.isChecked()
    finally:
        _close(window)


def test_collapse_tab_and_completed_splitter_move_persist(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()

        window.workspace_inspector.set_selected_tab('files')
        window.set_inspector_collapsed(True)
        assert window.settings.get(SETTING_INSPECTOR_TAB) == 'files'
        assert window.settings.get(SETTING_INSPECTOR_COLLAPSED) is True

        window.set_inspector_collapsed(False)
        window.workspace_shell.splitter.setSizes([1000, scale_px(100)])
        window._persist_inspector_width()
        assert window.settings.get(SETTING_INSPECTOR_WIDTH) == 260
        assert abs(window.workspace_shell.inspector_width()
                   - scale_px(260)) <= scale_px(3)
    finally:
        _close(window)


def test_malformed_workspace_settings_restore_safe_defaults(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path, {
        SETTING_INSPECTOR_WIDTH: 'wide',
        SETTING_INSPECTOR_COLLAPSED: 1,
        SETTING_INSPECTOR_TAB: 'tracks',
    })
    try:
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()
        assert not window.workspace_shell.is_inspector_collapsed()
        assert window.workspace_inspector.selected_tab() == 'objects'
        assert abs(window.workspace_shell.inspector_width()
                   - scale_px(304)) <= scale_px(3)
    finally:
        _close(window)


def test_legacy_layout_and_toolbar_values_round_trip_without_exposure(
        monkeypatch, tmp_path):
    legacy_state = QByteArray(b'legacy-dock-layout')
    window = _window(monkeypatch, tmp_path, {
        SETTING_ADVANCE_MODE: True,
        SETTING_ICON_SIZE: 36,
        SETTING_TOOLBAR_EXPANDED: True,
        SETTING_WIN_STATE: legacy_state,
    })
    try:
        actions = _view_actions(window)
        assert window.actions.advancedMode not in actions
        assert window.icon_size_menu.menuAction() not in actions
        assert window.beginner()
    finally:
        _close(window)

    loaded = Settings()
    assert loaded.load()
    assert loaded.get(SETTING_ADVANCE_MODE) is True
    assert loaded.get(SETTING_ICON_SIZE) == 36
    assert loaded.get(SETTING_TOOLBAR_EXPANDED) is True
    assert loaded.get(SETTING_WIN_STATE) == legacy_state


def test_legacy_prompt_setting_round_trips_but_new_policy_wins_next_launch(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path, {
        SETTING_SINGLE_CLASS: True,
    })
    try:
        assert window.single_class_mode not in _view_actions(window)
        window._active_class_policy_changed('confirm_each')
    finally:
        _close(window)

    persisted = Settings()
    assert persisted.load()
    assert persisted.get(SETTING_SINGLE_CLASS) is True
    assert persisted.get(SETTING_PROMPT_POLICY) == 'confirm_each'

    second = MainWindow(default_save_dir=str(tmp_path))
    try:
        assert second.workflow.snapshot.prompt_policy.value == 'confirm_each'
        assert second.single_class_mode not in _view_actions(second)
    finally:
        _close(second)


def test_file_list_shows_basename_and_keeps_full_path_as_data(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        path = str(tmp_path / 'nested' / 'a-very-long-image-name.png')
        snapshot = DatasetSnapshot.from_images(
            (path,), root_dir=str(tmp_path), save_dir=str(tmp_path),
            generation=1)
        window._commit_dataset_snapshot(snapshot)

        item = window.file_list_widget.item(0)
        assert item.text() == 'a-very-long-image-name.png'
        assert item.data(Qt.UserRole) == path
        assert item.toolTip() == path
    finally:
        _close(window)


def test_inspector_becomes_dismissible_drawer_below_960(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'drawer'
        assert window.workspace_inspector.isHidden()

        window.workspace_shell.reopen_button.click()
        QApplication.processEvents()
        assert window.workspace_inspector.isVisible()
        assert window.workspace_inspector.tabs.hasFocus()
        QTest.keyClick(window.workspace_inspector, Qt.Key_Escape)
        QApplication.processEvents()
        assert window.workspace_inspector.isHidden()
        assert window.workspace_shell.reopen_button.hasFocus()
    finally:
        _close(window)


def test_compact_inspector_controls_use_non_null_resource_icons(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()
        assert not window.workspace_inspector.collapse_button.icon().pixmap(
            QSize(32, 32)).isNull()
        window.workspace_shell.set_inspector_collapsed(True)
        assert not window.workspace_shell.reopen_button.icon().pixmap(
            QSize(32, 32)).isNull()
    finally:
        _close(window)


def test_crossing_breakpoint_does_not_overwrite_wide_preference(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.workspace_shell.set_inspector_collapsed(False)
        window.resize(800, 600)
        window.show()
        QApplication.processEvents()
        window.resize(1200, 700)
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'docked'
        assert not window.workspace_shell.is_inspector_collapsed()
    finally:
        _close(window)


def test_inspector_breakpoint_uses_logical_pixels_without_scaling(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(959, 600)
        window.show()
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'drawer'

        window.resize(960, 600)
        QApplication.processEvents()
        assert window.workspace_shell.layout_mode == 'docked'
    finally:
        _close(window)


def test_layout_mode_change_schedules_view_reprojection(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(1200, 700)
        window.show()
        QApplication.processEvents()
        scheduled = []
        monkeypatch.setattr(
            window, '_schedule_view_projection',
            lambda: scheduled.append('projection'))

        window.workspace_shell.set_available_width(800)

        assert scheduled == ['projection']
    finally:
        _close(window)


def _settle_layout():
    QApplication.processEvents()
    QTest.qWait(5)
    QApplication.processEvents()


def test_drawer_transitions_settle_overlay_bounds_and_fit_projection(
        monkeypatch, tmp_path):
    image_path = str(tmp_path / 'wide.png')
    image = QImage(4000, 400, QImage.Format_RGB32)
    image.fill(Qt.white)
    assert image.save(image_path)
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        assert window.load_file(image_path)
        window.set_fit_window()
        _settle_layout()
        closed_viewport_width = window.scroll_area.viewport().width()
        closed_zoom = window.zoom_widget.value()

        window.workspace_shell.reopen_button.click()
        _settle_layout()

        bounds = window.workspace_shell.splitter.geometry()
        drawer = window.workspace_inspector.geometry()
        assert window.workspace_shell.scrim.geometry() == bounds
        assert drawer.right() == bounds.right()
        assert drawer.top() == bounds.top()
        assert drawer.bottom() == bounds.bottom()
        assert window.scroll_area.viewport().width() > closed_viewport_width
        assert window.zoom_widget.value() > closed_zoom
        assert (window.canvas.pixmap.width() * window.canvas.scale
                <= window.scroll_area.viewport().width() + 1)

        window.workspace_inspector.collapse_button.click()
        _settle_layout()

        assert window.workspace_shell.scrim.geometry() == \
            window.workspace_shell.splitter.geometry()
        assert window.scroll_area.viewport().width() == closed_viewport_width
        assert window.zoom_widget.value() == closed_zoom
        assert window.workspace_shell.reopen_button.hasFocus()
    finally:
        _close(window)


def test_crossing_breakpoint_while_drawer_is_open_reparents_once(
        monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.resize(800, 600)
        window.show()
        _settle_layout()
        window.workspace_shell.open_inspector()
        _settle_layout()

        window.resize(1200, 700)
        _settle_layout()

        assert window.workspace_shell.layout_mode == 'docked'
        assert window.workspace_shell.splitter.widget(1) is \
            window.workspace_inspector
        assert window.workspace_inspector.isVisible()
        assert window.workspace_shell.scrim.isHidden()

        window.resize(800, 600)
        _settle_layout()
        assert window.workspace_shell.layout_mode == 'drawer'
        assert window.workspace_inspector.isHidden()
        assert window.workspace_shell.reopen_button.isVisible()
    finally:
        _close(window)
