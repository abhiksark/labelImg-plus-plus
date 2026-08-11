"""Structural tests for the fixed workspace command bar."""

import os
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QAction, QApplication, QMenu

from libs.widgets.commandBar import CommandBar


def _action(text, parent, checkable=False):
    action = QAction(text, parent)
    action.setCheckable(checkable)
    return action


def _bar():
    owner = QMenu()
    file_menu = QMenu('&File', owner)
    edit_menu = QMenu('&Edit', owner)
    open_action = _action('Open image', owner)
    open_video = _action('Open video', owner)
    previous = _action('Previous', owner)
    next_action = _action('Next', owner)
    save = _action('Save', owner, checkable=True)
    verify = _action('Verify', owner)
    output_format = _action('Pascal VOC', owner)
    save_as = _action('Save as', owner)
    file_menu.addActions([open_action, save])
    edit_menu.addAction(verify)
    bar = CommandBar(
        'labelImgPlusPlus', (file_menu, edit_menu),
        (open_action, open_video), previous, next_action, save, verify,
        output_format, (save, save_as, verify, output_format),
    )
    return owner, bar, {
        'open': open_action,
        'previous': previous,
        'next': next_action,
        'save': save,
        'verify': verify,
        'format': output_format,
    }


def test_command_bar_reuses_actions_and_tracks_their_state():
    owner, bar, actions = _bar()
    assert owner is not None
    save = actions['save']
    assert bar.save_button.defaultAction() is save
    assert bar.verify_button.defaultAction() is actions['verify']
    assert bar.format_button.defaultAction() is actions['format']

    save.setEnabled(False)
    save.setText('Store')
    save.setChecked(True)
    QApplication.processEvents()
    assert not bar.save_button.isEnabled()
    assert bar.save_button.text() == 'Store'
    assert bar.save_button.isChecked()


def test_command_bar_uses_44_logical_pixel_height_and_scales_for_hidpi():
    with patch('libs.widgets.commandBar.scale_px', side_effect=lambda value: value):
        owner, bar, _actions = _bar()
        assert owner is not None
        assert bar.minimumHeight() == 44
        assert bar.maximumHeight() == 44

    with patch(
            'libs.widgets.commandBar.scale_px',
            side_effect=lambda value: value * 2):
        owner, bar, _actions = _bar()
        assert owner is not None
        assert bar.minimumHeight() == 88
        assert bar.maximumHeight() == 88


def test_command_bar_buttons_trigger_the_authoritative_action():
    owner, bar, actions = _bar()
    assert owner is not None
    calls = []
    actions['save'].setEnabled(True)
    actions['save'].triggered.connect(lambda checked: calls.append(checked))
    bar.save_button.click()
    assert calls == [True]


def test_command_bar_exposes_top_level_menus_and_open_commands():
    owner, bar, actions = _bar()
    assert owner is not None
    top_menus = [entry.menu() for entry in bar.application_menu.actions()]
    assert [menu.title() for menu in top_menus] == ['&File', '&Edit']
    assert actions['open'] in bar.open_menu.actions()


def test_command_bar_focus_and_responsive_overflow():
    owner, bar, actions = _bar()
    assert owner is not None
    bar.show()
    bar.resize(1000, bar.height())
    QApplication.processEvents()
    assert not bar.position_label.isHidden()
    assert not bar.verify_button.isHidden()
    assert not bar.format_button.isHidden()
    assert bar.application_button.toolButtonStyle() == \
        Qt.ToolButtonTextBesideIcon

    bar.resize(600, bar.height())
    QApplication.processEvents()
    assert bar.position_label.isHidden()
    assert bar.verify_button.isHidden()
    assert bar.format_button.isHidden()
    assert bar.application_button.toolButtonStyle() == Qt.ToolButtonIconOnly
    assert not bar.overflow_button.isHidden()
    assert actions['verify'] in bar.overflow_menu.actions()
    assert actions['format'] in bar.overflow_menu.actions()
    for button in (
            bar.application_button, bar.open_button, bar.previous_button,
            bar.next_button, bar.save_button, bar.overflow_button):
        assert button.focusPolicy() == Qt.StrongFocus


def test_command_bar_document_and_dirty_state():
    owner, bar, _actions = _bar()
    assert owner is not None
    bar.set_document(
        'frame-001.png', dirty=True, full_path='/data/frame-001.png')
    bar.set_position('17 / 240')
    assert bar.document_label.text() == 'frame-001.png'
    assert bar.document_label.toolTip() == '/data/frame-001.png'
    assert not bar.dirty_indicator.isHidden()
    assert bar.position_label.text() == '17 / 240'

    bar.set_document('clip.mp4', dirty=False, read_only=True)
    assert bar.document_label.text() == 'clip.mp4 · Read only'
    assert bar.dirty_indicator.isHidden()
