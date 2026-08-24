"""In-workspace guidance for enabling optional video annotation support."""

try:
    from PyQt5.QtCore import QEvent, Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton,
        QVBoxLayout, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import QEvent, Qt, pyqtSignal
    from PyQt4.QtGui import (
        QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton,
        QVBoxLayout, QWidget,
    )

from libs.utils.dpi import scale_px


class VideoSetupCard(QWidget):
    """Explain the optional runtime and offer copy/manual file actions."""

    chooseAnotherRequested = pyqtSignal()
    dismissRequested = pyqtSignal()

    def __init__(self, parent=None):
        super(VideoSetupCard, self).__init__(parent)
        self.setObjectName('videoSetupCard')
        self.setAutoFillBackground(True)
        self.setMinimumWidth(scale_px(420))
        self.setMaximumWidth(scale_px(640))

        self.heading = QLabel('Set up video annotation', self)
        self.heading.setObjectName('videoSetupHeading')
        self.explanation = QLabel(
            'Video annotation needs optional components that are not '
            'included in the standard installation.', self)
        self.explanation.setObjectName('videoSetupExplanation')
        self.explanation.setWordWrap(True)
        self.detail = QLabel('', self)
        self.detail.setObjectName('videoSetupDetail')

        self.install_command = QLineEdit(self)
        self.install_command.setObjectName('videoSetupCommand')
        self.install_command.setReadOnly(True)
        self.install_command.setAccessibleName(
            'Optional video setup command')
        self.copy_button = QPushButton('Copy', self)
        self.copy_button.setObjectName('videoSetupCopyButton')
        self.copy_button.clicked.connect(self._copy_command)

        command_row = QHBoxLayout()
        command_row.setSpacing(scale_px(8))
        command_row.addWidget(self.install_command, 1)
        command_row.addWidget(self.copy_button)

        self.choose_another_button = QPushButton(
            'Choose another file', self)
        self.choose_another_button.setObjectName(
            'videoSetupChooseAnotherButton')
        self.choose_another_button.clicked.connect(
            self.chooseAnotherRequested.emit)
        self.close_button = QPushButton('Close', self)
        self.close_button.setObjectName('videoSetupCloseButton')
        self.close_button.clicked.connect(self.dismissRequested.emit)

        actions = QHBoxLayout()
        actions.addStretch(1)
        actions.addWidget(self.close_button)
        actions.addWidget(self.choose_another_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale_px(24), scale_px(24), scale_px(24), scale_px(24))
        layout.setSpacing(scale_px(12))
        layout.addWidget(self.heading)
        layout.addWidget(self.explanation)
        layout.addWidget(self.detail)
        layout.addLayout(command_row)
        layout.addLayout(actions)

        self._focus_order = (
            self.install_command,
            self.copy_button,
            self.close_button,
            self.choose_another_button,
        )
        for before, after in zip(
                self._focus_order, self._focus_order[1:]):
            QWidget.setTabOrder(before, after)
        for widget in self._focus_order:
            widget.installEventFilter(self)

    def set_status(self, status):
        self.detail.setText(status.detail)
        self.install_command.setText(status.install_command)

    def _copy_command(self):
        QApplication.clipboard().setText(self.install_command.text())

    def eventFilter(self, watched, event):
        if (watched in self._focus_order
                and event.type() == QEvent.KeyPress
                and event.key() in (Qt.Key_Tab, Qt.Key_Backtab)):
            backwards = (
                event.key() == Qt.Key_Backtab
                or bool(event.modifiers() & Qt.ShiftModifier))
            index = self._focus_order.index(watched)
            offset = -1 if backwards else 1
            target = self._focus_order[
                (index + offset) % len(self._focus_order)]
            target.setFocus(
                Qt.BacktabFocusReason if backwards else Qt.TabFocusReason)
            return True
        return super(VideoSetupCard, self).eventFilter(watched, event)
