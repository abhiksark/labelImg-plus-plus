# tests/widgets/test_inline_class_picker.py
from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QWidget

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


def test_child_picker_is_clamped_to_parent_and_screen_intersection():
    screen = QApplication.primaryScreen().availableGeometry()
    parent = QWidget()
    parent.setGeometry(screen.left() + 40, screen.top() + 40, 520, 420)
    picker = InlineClassPicker(parent)
    try:
        parent.show()
        QApplication.processEvents()
        anchor = parent.mapToGlobal(parent.rect().bottomRight())
        picker.open_at(['car', 'person'], '', anchor)
        QApplication.processEvents()
        global_rect = QRect(
            picker.mapToGlobal(QPoint(0, 0)), picker.size())
        parent_rect = QRect(
            parent.mapToGlobal(QPoint(0, 0)), parent.size())
        assert parent_rect.contains(global_rect)
        assert screen.contains(global_rect)
    finally:
        picker.close()
        parent.close()


def test_review_stage_accepts_enter_and_escape_discards():
    picker = InlineClassPicker()
    accepted = []
    cancelled = []
    picker.reviewAccepted.connect(lambda: accepted.append(True))
    picker.cancelled.connect(lambda: cancelled.append(True))
    try:
        picker.open_review_at(QPoint(20, 20))
        QApplication.processEvents()

        use_outline = picker.findChild(QPushButton, 'useOutlineButton')
        assert picker.prompt.text() == 'Use this outline?'
        assert picker.edit.isHidden()
        assert picker.list_widget.isHidden()
        assert use_outline.hasFocus()
        assert use_outline.property('primary') is True
        assert use_outline.accessibleName() == 'Use outline'
        assert picker.try_again_button.accessibleName() == 'Try again'

        QTest.keyClick(use_outline, Qt.Key_Return)
        QApplication.processEvents()
        assert accepted == [True]
        assert cancelled == []

        picker.open_review_at(QPoint(20, 20))
        QTest.keyClick(use_outline, Qt.Key_Escape)
        QApplication.processEvents()
        assert cancelled == [True]
    finally:
        picker.close()


def test_class_stage_click_commits_existing_class_immediately():
    picker = _picker()
    accepted = []
    picker.accepted.connect(accepted.append)
    try:
        discard_hint = picker.findChild(QLabel, 'classDiscardHint')
        assert discard_hint.text() == 'Esc · discard'
        item = picker.list_widget.item(2)
        QTest.mouseClick(
            picker.list_widget.viewport(), Qt.LeftButton,
            pos=picker.list_widget.visualItemRect(item).center())
        QApplication.processEvents()

        assert accepted == ['person']
        assert not picker.isVisible()
    finally:
        picker.close()
