try:
    from PyQt5.QtGui import QFontMetrics
    from PyQt5.QtCore import Qt, QSize
    from PyQt5.QtWidgets import QDoubleSpinBox, QAbstractSpinBox
except ImportError:
    from PyQt4.QtGui import QFontMetrics, QDoubleSpinBox, QAbstractSpinBox
    from PyQt4.QtCore import Qt, QSize

class ZoomWidget(QDoubleSpinBox):

    def __init__(self, value=100):
        super(ZoomWidget, self).__init__()
        # Delay this import until construction: ViewTransform imports the
        # lightweight geometry helper through the widgets package.
        from libs.core.view_transform import MIN_PERCENT, PERCENT_DECIMALS
        self._percent_decimals = PERCENT_DECIMALS
        self.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.setDecimals(self._percent_decimals)
        self.setRange(MIN_PERCENT, 500)
        self.setSuffix(' %')
        self.setValue(value)
        self.setToolTip(u'Zoom Level')
        self.setStatusTip(self.toolTip())
        self.setAlignment(Qt.AlignCenter)

    def minimumSizeHint(self):
        height = super(ZoomWidget, self).minimumSizeHint().height()
        fm = QFontMetrics(self.font())
        width = fm.width(self.textFromValue(self.maximum()))
        return QSize(width, height)

    def textFromValue(self, value):
        """Keep whole-percent zoom display compact while accepting fractions."""
        if value == int(value):
            return str(int(value))
        return ('{0:.%df}' % self._percent_decimals).format(value).rstrip('0')
