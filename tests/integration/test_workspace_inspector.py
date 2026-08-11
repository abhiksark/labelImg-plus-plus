"""Structural and persistence coverage for the fixed workspace inspector."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QByteArray
from PyQt5.QtWidgets import QApplication, QDockWidget, QToolBar

from labelImgPlusPlus import MainWindow
from libs.core.settings import Settings
from libs.utils.constants import (
    SETTING_ADVANCE_MODE, SETTING_ICON_SIZE, SETTING_INSPECTOR_COLLAPSED,
    SETTING_INSPECTOR_TAB, SETTING_INSPECTOR_WIDTH,
    SETTING_TOOLBAR_EXPANDED, SETTING_WIN_STATE,
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
        assert window.workspace_shell.splitter.widget(0) is window.scroll_area
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
        assert window.findChildren(QDockWidget) == [window.timeline_dock]
        assert window.timeline_dock.features() == \
            QDockWidget.DockWidgetMovable
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
