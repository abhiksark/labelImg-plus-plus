"""Main-window integration coverage for the modern command bar."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from labelImgPlusPlus import get_main_app


def _menu_actions(menu):
    found = set()
    for action in menu.actions():
        submenu = action.menu()
        if submenu is not None:
            found.update(_menu_actions(submenu))
        elif not action.isSeparator():
            found.add(action)
    return found


def test_main_window_installs_one_fixed_command_bar():
    _app, window = get_main_app([])
    try:
        assert window.menuWidget() is window.command_bar
        assert window.command_bar.minimumHeight() == \
            window.command_bar.maximumHeight()
        assert window.menuWidget() is not None
        assert window.command_bar.save_button.defaultAction() is \
            window.actions.save
        assert window.command_bar.verify_button.defaultAction() is \
            window.actions.verify
        assert window.command_bar.primary_button.defaultAction() is \
            window.actions.primary
        assert window.command_bar.format_button.defaultAction() is \
            window.actions.save_format
    finally:
        window.dirty = False
        window.close()


def test_application_menu_keeps_every_existing_menu_command_reachable():
    _app, window = get_main_app([])
    try:
        menus = (
            window.menus.file, window.menus.edit, window.menus.view,
            window.menus.tools, window.menus.plugins, window.menus.help,
        )
        expected = set()
        for menu in menus:
            expected.update(_menu_actions(menu))
        reachable = _menu_actions(window.command_bar.application_menu)
        assert expected <= reachable

        # Plugin commands are registered after the shell exists. Adding one to
        # the live Plugins menu must make it reachable without rebuilding UI.
        plugin_action = QAction('Fixture plugin command', window)
        window.menus.plugins.addAction(plugin_action)
        assert plugin_action in _menu_actions(
            window.command_bar.application_menu)
    finally:
        window.dirty = False
        window.close()


def test_menus_and_shortcuts_survive_one_event_loop_turn():
    """setMenuWidget() deletes the menu bar via deleteLater().

    DeferredDelete is only delivered once an event loop runs, so a test that
    never enters one cannot see the menus die. Enter the loop once before
    asserting, otherwise this whole file passes against a broken shell.
    """
    app, window = get_main_app([])
    try:
        QTimer.singleShot(0, app.quit)
        app.exec()

        entries = window.command_bar.application_menu.actions()
        assert len(entries) == 6
        for entry in entries:
            submenu = entry.menu()
            assert submenu is not None
            assert submenu.title()          # raises if the C++ object is gone

        for name in ('undo', 'redo', 'galleryMode', 'deleteImg'):
            action = getattr(window.actions, name)
            assert action.associatedObjects(), \
                '%s lost every associated widget, so its shortcut is dead' % name
    finally:
        window.dirty = False
        window.close()


def test_command_bar_syncs_document_position_dirty_state_and_actions():
    app, window = get_main_app([])
    try:
        window.file_path = '/dataset/frame-017.png'
        window.m_img_list = [
            '/dataset/frame-%03d.png' % value for value in range(1, 241)]
        window._path_to_idx = {
            path: index for index, path in enumerate(window.m_img_list)}
        window.file_path = window.m_img_list[16]
        window.update_status_bar()
        assert window.command_bar.document_label.text() == 'frame-017.png'
        assert window.command_bar.position_label.text() == '17 / 240'

        window.set_dirty()
        assert not window.command_bar.dirty_indicator.isHidden()
        assert window.command_bar.save_button.isEnabled()
        assert window.command_bar.save_state_label.text() == \
            'Unsaved changes'
        window.set_clean()
        assert window.command_bar.dirty_indicator.isHidden()
        assert not window.command_bar.save_button.isEnabled()

        window.resize(1366, 768)
        window.show()
        app.processEvents()
        assert window.command_bar.height() == \
            window.command_bar.minimumHeight()
        assert window.command_bar.format_button.isVisible()
        assert window.command_bar.verify_button.isHidden()
        assert window.command_bar.save_button.isHidden()
        assert window.command_bar.primary_button.isVisible()
        assert window.command_bar.overflow_button.geometry().right() < \
            window.command_bar.width()
        assert window.command_bar.save_button.focusPolicy() == Qt.FocusPolicy.StrongFocus
    finally:
        window.dirty = False
        window.close()
