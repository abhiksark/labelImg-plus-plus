# libs/widgets/inlineClassPicker.py
"""Non-modal class confirmation for newly drawn provisional geometry."""

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QVBoxLayout, QWidget,
)

from libs.utils.styles import Theme, get_theme_colors
from libs.utils.utils import label_validator, trimmed


class InlineClassPicker(QFrame):
    """A lightweight picker that confirms or cancels provisional geometry."""

    accepted = pyqtSignal(str)
    cancelled = pyqtSignal()
    reviewAccepted = pyqtSignal()

    def __init__(self, parent=None):
        super(InlineClassPicker, self).__init__(parent)
        if parent is None:
            self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
        self.setObjectName('inlineClassPicker')
        self.setWindowTitle('Choose class')
        self.setMinimumWidth(280)
        self._navigation_active = False
        self._closing = False

        self.prompt = QLabel('Choose a class')
        self.edit = QLineEdit()
        self.edit.setObjectName('inlineClassEdit')
        self.edit.setAccessibleName('Class name')
        self.edit.setPlaceholderText('Filter or enter a new class…')
        self.edit.setValidator(label_validator())
        self.edit.textChanged.connect(self._filter)
        self.edit.installEventFilter(self)

        self.list_widget = QListWidget()
        self.list_widget.setObjectName('inlineClassList')
        self.list_widget.setAccessibleName('Available classes')
        self.list_widget.itemClicked.connect(self._choose_item)
        self.list_widget.installEventFilter(self)

        self.class_discard_hint = QLabel('Esc · discard')
        self.class_discard_hint.setObjectName('classDiscardHint')

        self.review_actions = QWidget()
        review_layout = QHBoxLayout(self.review_actions)
        review_layout.setContentsMargins(0, 0, 0, 0)
        review_layout.setSpacing(6)
        self.try_again_button = QPushButton('Try again (Esc)')
        self.try_again_button.setObjectName('tryAgainButton')
        self.try_again_button.setAccessibleName('Try again')
        self.try_again_button.setProperty('primary', False)
        self.try_again_button.clicked.connect(self.cancel)
        self.try_again_button.installEventFilter(self)
        self.use_outline_button = QPushButton('Use outline (Enter)')
        self.use_outline_button.setObjectName('useOutlineButton')
        self.use_outline_button.setAccessibleName('Use outline')
        self.use_outline_button.setProperty('primary', True)
        self.use_outline_button.setDefault(True)
        self.use_outline_button.clicked.connect(self._accept_review)
        self.use_outline_button.installEventFilter(self)
        review_layout.addWidget(self.try_again_button)
        review_layout.addWidget(self.use_outline_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.addWidget(self.prompt)
        layout.addWidget(self.edit)
        layout.addWidget(self.list_widget)
        layout.addWidget(self.class_discard_hint)
        layout.addWidget(self.review_actions)

        self.review_actions.hide()
        self.prompt.setBuddy(self.edit)

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
            ' color: %(text)s; }'
            'QLineEdit:focus, QListWidget:focus, QPushButton:focus {'
            ' border: 2px solid %(focus)s; }'
            'QPushButton[primary="true"] {'
            ' background: %(accent)s; border: 1px solid %(accent)s;'
            ' color: %(on_accent)s; }' % {
                'surface': colors['surface'],
                'border': colors['border'],
                'text': colors['text'],
                'background': colors['background'],
                'focus': colors['focus'],
                'accent': colors['accent'],
                'on_accent': colors['on_accent'],
            })

    def open_at(self, labels, text, anchor_global):
        """Populate, position beside geometry, and show without blocking."""
        self._closing = False
        self._navigation_active = False
        self.setWindowTitle('Choose class')
        self.prompt.setText('Choose a class')
        self.review_actions.hide()
        self.edit.show()
        self.list_widget.show()
        self.class_discard_hint.show()
        self.list_widget.clear()
        for label in labels:
            if trimmed(label):
                self.list_widget.addItem(trimmed(label))
        self.edit.setText(text or '')
        self.edit.selectAll()
        self._filter(self.edit.text())
        self._show_at(anchor_global)
        self.edit.setFocus(Qt.FocusReason.PopupFocusReason)

    def open_review_at(self, anchor_global, approval_label=''):
        """Show the Smart Select geometry decision beside its outline."""
        self._closing = False
        self.setWindowTitle('Review outline')
        self.prompt.setText('Use this outline?')
        self.use_outline_button.setText(
            'Use outline as %s (Enter)' % approval_label
            if approval_label else 'Use outline (Enter)')
        self.edit.hide()
        self.list_widget.hide()
        self.class_discard_hint.hide()
        self.review_actions.show()
        self._show_at(anchor_global)
        self.use_outline_button.setFocus(Qt.FocusReason.PopupFocusReason)

    def _show_at(self, anchor_global):
        """Position the current picker stage within the active screen."""
        self.adjustSize()

        anchor = QPoint(anchor_global)
        screen = QApplication.screenAt(anchor)
        if screen is None:
            screen = QApplication.primaryScreen()
        available = (
            screen.availableGeometry()
            if screen is not None else QRect(anchor, self.sizeHint()))
        parent = self.parentWidget()
        if parent is not None and not self.isWindow():
            parent_rect = QRect(
                parent.mapToGlobal(QPoint(0, 0)), parent.size())
            available = available.intersected(parent_rect)
        width = max(self.sizeHint().width(), self.minimumWidth())
        height = self.sizeHint().height()
        x = min(max(anchor.x() + 12, available.left()),
                available.right() - width + 1)
        y = min(max(anchor.y() + 12, available.top()),
                available.bottom() - height + 1)
        if parent is not None and not self.isWindow():
            self.move(parent.mapFromGlobal(QPoint(x, y)))
        else:
            self.move(x, y)
        self.show()
        self.raise_()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.cancel()
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self.review_actions.isVisible():
                    self._accept_review()
                    return True
                self._accept()
                return True
            if watched is self.edit and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._move_selection(1 if key == Qt.Key.Key_Down else -1)
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
        self.edit.setText(item.text())
        self._accept()

    def _accept_review(self):
        if self._closing:
            return
        self._closing = True
        QTimer.singleShot(0, self.reviewAccepted.emit)

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
