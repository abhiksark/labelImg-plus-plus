"""Fixed annotation-tool rail for the modern workspace."""

try:
    from PyQt5.QtCore import Qt, QSize
    from PyQt5.QtGui import QPalette
    from PyQt5.QtWidgets import (
        QActionGroup, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import Qt, QSize
    from PyQt4.QtGui import (
        QActionGroup, QPalette, QSizePolicy, QToolButton, QVBoxLayout,
        QWidget,
    )

from libs.utils.dpi import scale_px
from libs.utils.styles import (
    Theme, get_theme_colors, get_tool_rail_style, hex_to_qcolor,
)
from libs.utils.utils import native_shortcut_text, themed_icon


class AnnotationToolRail(QWidget):
    """A compact projection of the application's authoritative tool actions."""

    TOOL_SIZE = 40
    ICON_SIZE = 20
    RAIL_WIDTH = 52

    def __init__(self, actions, parent=None):
        super(AnnotationToolRail, self).__init__(parent)
        self.setObjectName('annotationToolRail')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(scale_px(self.RAIL_WIDTH))
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self.action_group = QActionGroup(self)
        self.action_group.setExclusive(True)
        self.buttons = {}
        self._tool_actions = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale_px(6), scale_px(8), scale_px(6), scale_px(8))
        layout.setSpacing(scale_px(4))

        for key, label, action in actions:
            action.setCheckable(True)
            self.action_group.addAction(action)
            self._tool_actions[key] = action
            button = QToolButton(self)
            button.setObjectName('%sToolButton' % key)
            button.setDefaultAction(action)
            button.setAutoRaise(True)
            button.setFocusPolicy(Qt.StrongFocus)
            button.setToolButtonStyle(Qt.ToolButtonIconOnly)
            button.setIconSize(QSize(
                scale_px(self.ICON_SIZE), scale_px(self.ICON_SIZE)))
            button.setFixedSize(
                scale_px(self.TOOL_SIZE), scale_px(self.TOOL_SIZE))
            button.setAccessibleName(label)
            self.buttons[key] = button
            self._sync_tooltip(button, action, label)
            action.changed.connect(
                lambda b=button, a=action, text=label:
                self._sync_tooltip(b, a, text))
            layout.addWidget(button, 0, Qt.AlignHCenter)

        layout.addStretch(1)
        self.apply_theme(Theme.LIGHT)

    @staticmethod
    def _sync_tooltip(button, action, label):
        shortcut = native_shortcut_text(action.shortcut())
        button.setToolTip(
            '%s (%s)' % (label, shortcut) if shortcut else label)

    def apply_theme(self, theme):
        self._current_theme = theme
        icon_names = {
            'select': 'tool-select',
            'box': 'tool-box',
            'polygon': 'tool-polygon',
            'smartSelect': 'tool-smart-select',
            'keypoints': 'tool-keypoints',
        }
        for key, action in self._tool_actions.items():
            action.setIcon(themed_icon(icon_names[key], theme))
        colors = get_theme_colors(theme)
        palette = self.palette()
        palette.setColor(
            QPalette.Window, hex_to_qcolor(colors['surface']))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        self.setStyleSheet(get_tool_rail_style(theme))
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
