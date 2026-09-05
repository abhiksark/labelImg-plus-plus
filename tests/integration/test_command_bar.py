"""Main-window integration coverage for the modern command bar."""

import os
import time
from xml.etree import ElementTree

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest

from labelImgPlusPlus import get_main_app
from libs.formats.labelFile import LabelFileFormat


@pytest.fixture
def command_window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    app, window = get_main_app([])
    try:
        # setMenuWidget() schedules the old menu bar for DeferredDelete.
        # Exercise commands after an event loop, not just processEvents(),
        # so accidentally destroying its menus cannot pass these tests.
        QTimer.singleShot(0, app.quit)
        app.exec()
        window.show()
        window.activateWindow()
        window.setFocus()
        app.processEvents()
        yield app, window
    finally:
        window.dirty = False
        window.close()
        window.deleteLater()
        app.processEvents()


def _load_image(window, tmp_path, annotated=True):
    image_path = tmp_path / 'frame.png'
    image = QImage(160, 120, QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.white)
    assert image.save(str(image_path))
    assert window.load_file(str(image_path))
    window.label_file_format = LabelFileFormat.PASCAL_VOC
    if annotated:
        window.load_labels([
            ('vehicle', [(10, 10), (40, 10), (40, 30), (10, 30)],
             None, None, False),
        ])
        window.set_dirty()
    return image_path


def _choose_application_action(app, window, menu, action):
    application_menu = window.command_bar.application_menu
    application_menu.popup(window.command_bar.mapToGlobal(QPoint(0, 0)))
    application_menu.setActiveAction(menu.menuAction())
    QTest.keyClick(application_menu, Qt.Key.Key_Right)
    app.processEvents()
    assert menu.isVisible()
    menu.setActiveAction(action)
    QTest.keyClick(menu, Qt.Key.Key_Return)
    app.processEvents()


@pytest.mark.parametrize('annotated', [True, False], ids=['saveable', 'disabled'])
def test_save_as_shortcut_never_toggles_single_class_mode(
        command_window, monkeypatch, tmp_path, annotated):
    app, window = command_window
    _load_image(window, tmp_path, annotated=annotated)
    assert window.actions.saveAs.isEnabled() == annotated
    assert not window.single_class_mode.isChecked()

    dialogs = []

    def cancel_save_dialog():
        dialogs.append('save-as')
        return ''

    # Intercept only the file-dialog boundary; Qt must resolve and dispatch
    # the real shortcut. A duplicate QAction binding makes it ambiguous.
    monkeypatch.setattr(window, 'save_file_dialog', cancel_save_dialog)
    modifiers = (Qt.KeyboardModifier.ControlModifier
                 | Qt.KeyboardModifier.ShiftModifier)
    for checked in (False, True):
        window.activateWindow()
        window.canvas.setFocus()
        app.processEvents()
        QTest.keyClick(window.canvas, Qt.Key.Key_S, modifiers)
        app.processEvents()
        assert window.single_class_mode.isChecked() == checked
        assert len(dialogs) == ((2 if checked else 1) if annotated else 0)

        # The original menu action remains checkable and usable in both
        # directions, even when Save As is disabled.
        _choose_application_action(
            app, window, window.menus.view, window.single_class_mode)
        assert window.single_class_mode.isChecked() != checked


def test_command_bar_overflow_saves_annotations_and_clears_dirty_indicator(
        command_window, tmp_path):
    app, window = command_window
    image_path = _load_image(window, tmp_path)
    window.resize(1366, 768)
    app.processEvents()
    assert window.command_bar.dirty_indicator.isVisible()
    button = window.command_bar.overflow_button
    assert button.isVisible()
    assert button.geometry().right() < window.command_bar.width()

    menu = window.command_bar.overflow_menu
    menu.popup(button.mapToGlobal(QPoint(0, button.height())))
    menu.setActiveAction(window.actions.save)
    QTest.keyClick(menu, Qt.Key.Key_Return)

    annotation_path = image_path.with_suffix('.xml')
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.processEvents()
        if annotation_path.is_file() and not window.dirty:
            break
        QTest.qWait(10)

    assert annotation_path.is_file()
    annotation = ElementTree.parse(str(annotation_path))
    assert annotation.findtext('object/name') == 'vehicle'
    assert not window.dirty
    assert not window.command_bar.dirty_indicator.isVisible()
    assert not window.command_bar.save_button.isEnabled()
