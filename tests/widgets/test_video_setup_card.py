from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from libs.core.video_runtime import VideoRuntimeStatus
from libs.widgets.videoSetupCard import VideoSetupCard


def _missing_status():
    return VideoRuntimeStatus(
        False, ('av',), 'pip install "labelimgplusplus[video]"',
        'Missing optional component: av')


def test_setup_card_explains_missing_runtime_without_install_control():
    card = VideoSetupCard()
    try:
        card.set_status(_missing_status())

        assert 'video annotation' in card.explanation.text().lower()
        assert card.detail.text() == 'Missing optional component: av'
        assert card.install_command.text() == \
            'pip install "labelimgplusplus[video]"'
        assert card.install_command.isReadOnly()
        assert card.autoFillBackground()
        assert not hasattr(card, 'install_button')
    finally:
        card.close()
        card.deleteLater()


def test_setup_card_copy_button_copies_exact_command():
    card = VideoSetupCard()
    clipboard = QApplication.clipboard()
    clipboard.clear()
    try:
        card.set_status(_missing_status())

        card.copy_button.click()

        assert clipboard.text() == 'pip install "labelimgplusplus[video]"'
    finally:
        card.close()
        card.deleteLater()


def test_setup_card_choose_another_button_emits_request():
    card = VideoSetupCard()
    requests = []
    card.chooseAnotherRequested.connect(lambda: requests.append(True))
    try:
        card.choose_another_button.click()

        assert requests == [True]
    finally:
        card.close()
        card.deleteLater()


def test_setup_card_contains_focus_in_visual_tab_order():
    card = VideoSetupCard()
    app = QApplication.instance()
    try:
        card.show()
        card.install_command.setFocus(Qt.OtherFocusReason)
        app.processEvents()

        forward = (
            card.copy_button,
            card.close_button,
            card.choose_another_button,
            card.install_command,
        )
        current = card.install_command
        for expected in forward:
            QTest.keyClick(current, Qt.Key_Tab)
            app.processEvents()
            assert QApplication.focusWidget() is expected
            current = expected

        QTest.keyClick(card.install_command, Qt.Key_Tab, Qt.ShiftModifier)
        app.processEvents()
        assert QApplication.focusWidget() is card.choose_another_button
        QTest.keyClick(
            card.choose_another_button, Qt.Key_Tab, Qt.ShiftModifier)
        app.processEvents()
        assert QApplication.focusWidget() is card.close_button
    finally:
        card.close()
        card.deleteLater()
