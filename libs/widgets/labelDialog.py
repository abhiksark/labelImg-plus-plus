# libs/labelDialog.py
"""Label dialog with search/filter capability for selecting annotation labels."""

try:
    from PyQt5.QtGui import QCursor
    from PyQt5.QtCore import Qt, QStringListModel, QPoint
    from PyQt5.QtWidgets import (
        QDialog, QLineEdit, QCompleter, QDialogButtonBox, QVBoxLayout,
        QHBoxLayout, QLabel, QListWidget
    )
except ImportError:
    from PyQt4.QtGui import (
        QCursor, QDialog, QLineEdit, QCompleter, QDialogButtonBox,
        QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QStringListModel
    )
    from PyQt4.QtCore import Qt, QPoint

from libs.utils.utils import new_icon, label_validator, trimmed

BB = QDialogButtonBox


class LabelDialog(QDialog):

    def __init__(self, text="Enter object label", parent=None, list_item=None):
        super(LabelDialog, self).__init__(parent)

        self.list_item = list_item or []

        # Label input field
        self.edit = QLineEdit()
        self.edit.setText(text)
        self.edit.setValidator(label_validator())
        self.edit.editingFinished.connect(self.post_process)
        self.edit.setPlaceholderText("Enter label name...")

        # Autocomplete for label input
        model = QStringListModel()
        model.setStringList(self.list_item)
        completer = QCompleter()
        completer.setModel(model)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.edit.setCompleter(completer)

        # OK/Cancel buttons
        self.button_box = bb = BB(BB.Ok | BB.Cancel, Qt.Horizontal, self)
        bb.button(BB.Ok).setIcon(new_icon('done'))
        bb.button(BB.Cancel).setIcon(new_icon('undo'))
        bb.accepted.connect(self.validate)
        bb.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(bb, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.edit)

        # Add search/filter and list widget if there are predefined classes
        if self.list_item:
            # Search/filter field
            self.filter_edit = QLineEdit()
            self.filter_edit.setPlaceholderText("Search labels...")
            self.filter_edit.setClearButtonEnabled(True)
            self.filter_edit.textChanged.connect(self._filter_list)

            # Label for filter
            filter_layout = QHBoxLayout()
            filter_label = QLabel("Filter:")
            filter_label.setStyleSheet("color: #666;")
            filter_layout.addWidget(filter_label)
            filter_layout.addWidget(self.filter_edit)
            layout.addLayout(filter_layout)

            # List widget for predefined classes
            self.list_widget = QListWidget(self)
            for item in self.list_item:
                self.list_widget.addItem(item)
            self.list_widget.itemClicked.connect(self.list_item_click)
            self.list_widget.itemDoubleClicked.connect(self.list_item_double_click)
            layout.addWidget(self.list_widget)

            # Count label
            self.count_label = QLabel(f"{len(self.list_item)} labels")
            self.count_label.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(self.count_label)

        self.setLayout(layout)

    def _filter_list(self, text):
        """Filter the list widget based on search text."""
        if not hasattr(self, 'list_widget'):
            return

        filter_text = text.lower()
        visible_count = 0

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item_text = item.text().lower()
            matches = filter_text in item_text
            item.setHidden(not matches)
            if matches:
                visible_count += 1

        # Update count label
        if hasattr(self, 'count_label'):
            if filter_text:
                self.count_label.setText(f"{visible_count} of {len(self.list_item)} labels")
            else:
                self.count_label.setText(f"{len(self.list_item)} labels")

    def validate(self):
        if trimmed(self.edit.text()):
            self.accept()

    def post_process(self):
        self.edit.setText(trimmed(self.edit.text()))

    def pop_up(self, text='', move=True):
        """
        Shows the dialog, setting the current text to `text`, and blocks the caller until the user has made a choice.
        If the user entered a label, that label is returned, otherwise (i.e. if the user cancelled the action)
        `None` is returned.
        """
        self.edit.setText(text)
        self.edit.setSelection(0, len(text))
        self.edit.setFocus(Qt.PopupFocusReason)

        # Clear filter when opening
        if hasattr(self, 'filter_edit'):
            self.filter_edit.clear()

        if move:
            cursor_pos = QCursor.pos()

            # move OK button below cursor
            btn = self.button_box.buttons()[0]
            self.adjustSize()
            btn.adjustSize()
            offset = btn.mapToGlobal(btn.pos()) - self.pos()
            offset += QPoint(btn.size().width() // 4, btn.size().height() // 2)
            cursor_pos.setX(max(0, cursor_pos.x() - offset.x()))
            cursor_pos.setY(max(0, cursor_pos.y() - offset.y()))

            parent_bottom_right = self.parentWidget().geometry()
            max_x = parent_bottom_right.x() + parent_bottom_right.width() - self.sizeHint().width()
            max_y = parent_bottom_right.y() + parent_bottom_right.height() - self.sizeHint().height()
            max_global = self.parentWidget().mapToGlobal(QPoint(max_x, max_y))
            if cursor_pos.x() > max_global.x():
                cursor_pos.setX(max_global.x())
            if cursor_pos.y() > max_global.y():
                cursor_pos.setY(max_global.y())
            self.move(cursor_pos)
        return trimmed(self.edit.text()) if self.exec_() else None

    def list_item_click(self, t_qlist_widget_item):
        text = trimmed(t_qlist_widget_item.text())
        self.edit.setText(text)

    def list_item_double_click(self, t_qlist_widget_item):
        self.list_item_click(t_qlist_widget_item)
        self.validate()
