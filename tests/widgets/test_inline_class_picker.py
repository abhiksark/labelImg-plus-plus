from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from libs.widgets.inlineClassPicker import InlineClassPicker


def _picker():
    picker = InlineClassPicker()
    picker.open_at(['car', 'cargo truck', 'person'], '', QPoint(20, 20))
    QApplication.processEvents()
    return picker


def test_picker_filters_and_accepts_keyboard_selection():
    picker = _picker()
    accepted = []
    picker.accepted.connect(accepted.append)
    try:
        QTest.keyClicks(picker.edit, 'car')
        assert not picker.list_widget.item(0).isHidden()
        assert not picker.list_widget.item(1).isHidden()
        assert picker.list_widget.item(2).isHidden()
        QTest.keyClick(picker.edit, Qt.Key_Down)
        QTest.keyClick(picker.edit, Qt.Key_Return)
        QApplication.processEvents()
        assert accepted == ['car']
        assert not picker.isVisible()
    finally:
        picker.close()


def test_picker_accepts_valid_new_class_and_escape_cancels():
    picker = _picker()
    accepted = []
    cancelled = []
    picker.accepted.connect(accepted.append)
    picker.cancelled.connect(lambda: cancelled.append(True))
    try:
        picker.edit.setText('delivery van')
        QTest.keyClick(picker.edit, Qt.Key_Return)
        QApplication.processEvents()
        assert accepted == ['delivery van']

        picker.open_at(['car'], '', QPoint(20, 20))
        QTest.keyClick(picker.edit, Qt.Key_Escape)
        QApplication.processEvents()
        assert cancelled == [True]
    finally:
        picker.close()


def test_picker_is_clamped_to_active_screen():
    picker = InlineClassPicker()
    try:
        screen = QApplication.primaryScreen().availableGeometry()
        picker.open_at(
            ['car', 'person'], '',
            QPoint(screen.right() + 500, screen.bottom() + 500))
        QApplication.processEvents()
        assert picker.geometry().right() <= screen.right()
        assert picker.geometry().bottom() <= screen.bottom()
    finally:
        picker.close()
