"""Recoverable in-workspace error projection for document replacement."""

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton
except ImportError:
    from PyQt4.QtCore import Qt, pyqtSignal
    from PyQt4.QtGui import QFrame, QHBoxLayout, QLabel, QPushButton

from libs.utils.dpi import scale_px


class InlineErrorBanner(QFrame):
    """Show one contextual replacement failure without replacing the document."""

    retryRequested = pyqtSignal()
    chooseAnotherRequested = pyqtSignal()

    def __init__(self, parent=None):
        super(InlineErrorBanner, self).__init__(parent)
        self.setObjectName('inlineOpenErrorBanner')
        self.message = QLabel(self)
        self.message.setAccessibleName('Document open error')
        self.retry_button = QPushButton('Retry', self)
        self.retry_button.setAccessibleName('Retry opening document')
        self.choose_button = QPushButton('Choose another file', self)
        self.choose_button.setAccessibleName('Choose another document')
        for button in (self.retry_button, self.choose_button):
            button.setMinimumSize(scale_px(32), scale_px(32))
        self.retry_button.clicked.connect(self.retryRequested)
        self.choose_button.clicked.connect(self.chooseAnotherRequested)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            scale_px(8), scale_px(4), scale_px(8), scale_px(4))
        layout.setSpacing(scale_px(4))
        layout.addWidget(self.message, 1)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.choose_button)
        self.hide()

    def show_error(self, message):
        """Publish the current replacement failure and focus Retry."""
        self.message.setText(str(message))
        self.show()
        self.retry_button.setFocus(Qt.OtherFocusReason)

    def clear(self):
        """Hide this contextual failure after a new replacement request."""
        self.message.clear()
        self.hide()
