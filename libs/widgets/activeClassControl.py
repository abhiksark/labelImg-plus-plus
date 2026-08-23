import sys

try:
    from PyQt5.QtCore import pyqtSignal
    from PyQt5.QtWidgets import (
        QCheckBox, QComboBox, QLabel, QVBoxLayout, QWidget,
    )
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtCore import pyqtSignal
    from PyQt4.QtGui import (
        QCheckBox, QComboBox, QLabel, QVBoxLayout, QWidget,
    )


class ActiveClassControl(QWidget):
    classSelected = pyqtSignal(str)
    policyChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        super(ActiveClassControl, self).__init__(parent)
        self.combo = QComboBox(self)
        self.combo.setEditable(True)
        self.combo.setAccessibleName('Active annotation class')
        self._set_placeholder_text(self.combo)
        self.combo.activated.connect(
            lambda _index: self._choose(self.combo.currentText()))
        self.confirm_each = QCheckBox('Ask for every object', self)
        self.confirm_each.toggled.connect(
            lambda checked: self.policyChanged.emit(
                'confirm_each' if checked else 'reuse_active'))
        self.combo.lineEdit().returnPressed.connect(self._accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('Active class', self))
        layout.addWidget(self.combo)
        layout.addWidget(self.confirm_each)

    @staticmethod
    def _set_placeholder_text(combo):
        try:
            combo.setPlaceholderText('Choose a class')
        except AttributeError:
            combo.lineEdit().setPlaceholderText('Choose a class')

    def set_choices(self, labels):
        current = self.active_class()
        self.combo.clear()
        self.combo.addItems(sorted(set(
            str(item) for item in labels if item)))
        self.set_active_class(current)

    def set_active_class(self, label):
        if label:
            self.combo.setCurrentText(str(label))
        else:
            self.combo.setCurrentIndex(-1)

    def choices(self):
        return tuple(self.combo.itemText(index)
                     for index in range(self.combo.count()))

    def active_class(self):
        value = self.combo.currentText().strip()
        return value or None

    def _accept(self):
        value = self.active_class()
        if value:
            self.classSelected.emit(value)

    def _choose(self, value):
        self.set_active_class(value)
        self.classSelected.emit(str(value))
