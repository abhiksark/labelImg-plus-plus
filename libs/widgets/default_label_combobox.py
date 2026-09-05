from PyQt6.QtWidgets import QWidget, QHBoxLayout, QComboBox


class DefaultLabelComboBox(QWidget):
    def __init__(self, parent=None, items=[]):
        super(DefaultLabelComboBox, self).__init__(parent)

        layout = QHBoxLayout()
        # Default margins added ~18px, and an unset minimumContentsLength made
        # the combo demand the width of the longest class name -- together
        # they pushed the row past the inspector and clipped its checkbox.
        layout.setContentsMargins(0, 0, 0, 0)
        self.cb = QComboBox()
        self.cb.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cb.setMinimumContentsLength(8)
        self.items = items
        self.cb.addItems(self.items)

        self.cb.currentIndexChanged.connect(parent.default_label_combo_selection_changed)

        layout.addWidget(self.cb)
        self.setLayout(layout)
