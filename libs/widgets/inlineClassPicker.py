"""Non-modal class confirmation for newly drawn provisional geometry."""

try:
    from PyQt5.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
    from PyQt5.QtWidgets import (
        QApplication, QFrame, QLabel, QLineEdit, QListWidget,
        QVBoxLayout,
    )
except ImportError:
    from PyQt4.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
    from PyQt4.QtGui import (
        QApplication, QFrame, QLabel, QLineEdit, QListWidget,
        QVBoxLayout,
    )

from libs.utils.styles import Theme, get_theme_colors
from libs.utils.utils import label_validator, trimmed


class InlineClassPicker(QFrame):
    """A lightweight picker that confirms or cancels provisional geometry."""

    accepted = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super(InlineClassPicker, self).__init__(parent)
        if parent is None:
            self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setObjectName('inlineClassPicker')
        self.setWindowTitle('Choose class')
        self.setMinimumWidth(280)
        self._navigation_active = False
        self._closing = False

        self.prompt = QLabel('Choose a class')
        self.edit = QLineEdit()
        self.edit.setObjectName('inlineClassEdit')
        self.edit.setPlaceholderText('Filter or enter a new class…')
        self.edit.setValidator(label_validator())
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName('inlineClassList')
        self.list_widget.itemClicked.connect(self._choose_item)
        self.list_widget.itemDoubleClicked.connect(
            lambda _item: self._accept())
        self.list_widget.installEventFilter(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self.prompt)
        layout.addWidget(self.edit)
        layout.addWidget(self.list_widget)

        self.apply_theme(Theme.LIGHT)

    def apply_theme(self, theme):
        """Paint from the application palette, not the desktop's.

        palette(base)/palette(mid) resolve against the OS theme because the
        app never calls setPalette, so in dark mode the frame kept a white
        ring around its dark contents.
        """
        self._current_theme = theme
        colors = get_theme_colors(theme)
        self.setStyleSheet(
            'QFrame#inlineClassPicker {'
            ' background: %(surface)s; border: 1px solid %(border)s;'
            ' border-radius: 6px; }'
            'QLabel { font-weight: 600; border: none; color: %(text)s; }'
            'QLineEdit, QListWidget {'
            ' border: 1px solid %(border)s; background: %(background)s;'
            ' color: %(text)s; }' % {
                'surface': colors['surface'],
                'border': colors['border'],
                'text': colors['text'],
                'background': colors['background'],
            })

    def open_at(self, labels, text, anchor_global):
        """Populate, position beside geometry, and show without blocking."""
        self._closing = False
        self._navigation_active = False
        self.list_widget.clear()
        for label in labels:
            if trimmed(label):
                self.list_widget.addItem(trimmed(label))
        self.edit.setText(text or '')
        self.edit.selectAll()
        self._filter(self.edit.text())
        self.adjustSize()

        anchor = QPoint(anchor_global)
        screen = QApplication.screenAt(anchor)
        if screen is not None:
            available = screen.availableGeometry()
        else:
            available = QApplication.desktop().availableGeometry(anchor)
        width = max(self.sizeHint().width(), self.minimumWidth())
        height = self.sizeHint().height()
        x = min(max(anchor.x() + 12, available.left()),
                available.right() - width + 1)
        y = min(max(anchor.y() + 12, available.top()),
                available.bottom() - height + 1)
        if self.parentWidget() is not None and not self.isWindow():
            self.move(self.parentWidget().mapFromGlobal(QPoint(x, y)))
        else:
            self.move(x, y)
        self.show()
        self.raise_()
        self.edit.setFocus(Qt.PopupFocusReason)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_Escape:
                self.cancel()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._accept()
                return True
            if watched is self.edit and key in (Qt.Key_Down, Qt.Key_Up):
                self._move_selection(1 if key == Qt.Key_Down else -1)
                return True
        return super(InlineClassPicker, self).eventFilter(watched, event)

    def _visible_rows(self):
        return [row for row in range(self.list_widget.count())
                if not self.list_widget.item(row).isHidden()]

    def _move_selection(self, step):
        rows = self._visible_rows()
        if not rows:
            return
        current = self.list_widget.currentRow()
        if current not in rows:
            target = rows[0] if step > 0 else rows[-1]
        else:
            target = rows[(rows.index(current) + step) % len(rows)]
        self._navigation_active = True
        self.list_widget.setCurrentRow(target)

    def _filter(self, text):
        needle = trimmed(text).lower()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item.setHidden(needle not in item.text().lower())
        self._navigation_active = False
        self.list_widget.setCurrentRow(-1)

    def _choose_item(self, item):
        self._navigation_active = True
        self.edit.setText(item.text())
        self.edit.selectAll()

    def _selected_text(self):
        item = self.list_widget.currentItem()
        if (self._navigation_active and item is not None
                and not item.isHidden()):
            return trimmed(item.text())
        return trimmed(self.edit.text())

    def _accept(self):
        text = self._selected_text()
        if not text:
            return
        self.edit.setText(text)
        if not self.edit.hasAcceptableInput():
            return
        self._closing = True
        self.hide()
        QTimer.singleShot(0, lambda: self.accepted.emit(text))

    def cancel(self):
        if not self.isVisible() and self._closing:
            return
        self._closing = True
        self.hide()
        # Emit after the key event returns so Qt's hide-time focus repair
        # cannot override the host's explicit canvas-focus restoration.
        QTimer.singleShot(0, self.cancelled.emit)

    def closeEvent(self, event):
        if not self._closing:
            self.cancelled.emit()
        self._closing = True
        event.accept()
