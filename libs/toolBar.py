# libs/toolBar.py
"""Custom toolbar and button classes for labelImg++."""

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *


# Icon size for toolbar buttons (Feather icons are 24x24)
ICON_SIZE = 24
# Minimum button size for comfortable clicking
MIN_BUTTON_SIZE = 44


class ToolBar(QToolBar):
    """Custom toolbar with modern styling support."""

    def __init__(self, title):
        super(ToolBar, self).__init__(title)
        layout = self.layout()
        layout.setSpacing(2)
        layout.setContentsMargins(4, 4, 4, 4)
        self.setContentsMargins(0, 0, 0, 0)
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

    def addAction(self, action):
        if isinstance(action, QWidgetAction):
            return super(ToolBar, self).addAction(action)
        btn = ToolButton()
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(self.toolButtonStyle())
        self.addWidget(btn)


class ToolButton(QToolButton):
    """Custom toolbar button with consistent sizing."""

    def __init__(self):
        super(ToolButton, self).__init__()
        self.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        self.setMinimumSize(MIN_BUTTON_SIZE, MIN_BUTTON_SIZE)

    def minimumSizeHint(self):
        return QSize(MIN_BUTTON_SIZE, MIN_BUTTON_SIZE)
