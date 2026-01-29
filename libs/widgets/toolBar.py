# libs/toolBar.py
"""Custom toolbar and button classes for labelImg++."""

try:
    from PyQt5.QtGui import *
    from PyQt5.QtCore import *
    from PyQt5.QtWidgets import *
except ImportError:
    from PyQt4.QtGui import *
    from PyQt4.QtCore import *


# Base icon size for toolbar buttons (Feather icons are 24x24)
BASE_ICON_SIZE = 22
# Minimum and maximum icon sizes for scaling
MIN_ICON_SIZE = 16
MAX_ICON_SIZE = 48


def get_dpi_scale_factor():
    """Get the DPI scale factor for the primary screen.

    Returns:
        float: Scale factor (1.0 for standard 96 DPI, higher for HiDPI displays)
    """
    app = QApplication.instance()
    if app is None:
        return 1.0

    # Try to get the primary screen
    try:
        screen = app.primaryScreen()
        if screen:
            # Get logical DPI (accounts for user scaling settings)
            logical_dpi = screen.logicalDotsPerInch()
            # Standard DPI is 96 on most systems
            return logical_dpi / 96.0
    except AttributeError:
        # Qt4 fallback
        pass

    return 1.0


def calculate_icon_size(base_size=BASE_ICON_SIZE):
    """Calculate appropriate icon size based on DPI.

    Args:
        base_size: Base icon size at standard DPI

    Returns:
        int: Scaled icon size clamped to min/max bounds
    """
    scale = get_dpi_scale_factor()
    scaled_size = int(base_size * scale)
    return max(MIN_ICON_SIZE, min(MAX_ICON_SIZE, scaled_size))


class ToolBar(QToolBar):
    """Custom toolbar with modern styling and DPI-aware icons."""

    # Signal emitted when expanded state changes
    expandedChanged = pyqtSignal(bool)

    def __init__(self, title):
        super(ToolBar, self).__init__(title)
        layout = self.layout()
        layout.setSpacing(0)
        layout.setContentsMargins(2, 2, 2, 2)
        self.setContentsMargins(0, 0, 0, 0)
        self._icon_size = calculate_icon_size()
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        # Track tool buttons for icon size updates
        self._tool_buttons = []

        # Expand/collapse state
        self._expanded = False
        self._collapsed_width = 85
        self._expanded_width = 140
        self._expand_btn = None

    def addAction(self, action):
        if isinstance(action, QWidgetAction):
            return super(ToolBar, self).addAction(action)
        btn = ToolButton(self._icon_size)
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(self.toolButtonStyle())
        self.addWidget(btn)
        self._tool_buttons.append(btn)
        return btn

    def addWidget(self, widget):
        """Override to track widgets that support icon sizing."""
        super(ToolBar, self).addWidget(widget)
        if isinstance(widget, (ToolButton, DropdownToolButton)):
            if widget not in self._tool_buttons:
                self._tool_buttons.append(widget)

    def update_icon_size(self, size=None):
        """Update icon size for toolbar and all buttons.

        Args:
            size: New icon size, or None to recalculate from DPI
        """
        if size is None:
            size = calculate_icon_size()

        self._icon_size = size
        self.setIconSize(QSize(size, size))

        # Update all tracked buttons
        for btn in self._tool_buttons:
            if hasattr(btn, 'update_icon_size'):
                btn.update_icon_size(size)
            else:
                btn.setIconSize(QSize(size, size))

    def showEvent(self, event):
        """Recalculate icon size when toolbar becomes visible."""
        super(ToolBar, self).showEvent(event)
        # Recalculate in case screen/DPI changed
        new_size = calculate_icon_size()
        if new_size != self._icon_size:
            self.update_icon_size(new_size)

    def add_expand_button(self):
        """Add expand/collapse toggle button at the bottom of toolbar."""
        from libs.utils.utils import new_icon

        # Add spacer to push button to bottom
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.addWidget(spacer)

        # Add separator
        self.addSeparator()

        # Create expand button
        self._expand_btn = QToolButton()
        self._expand_btn.setIcon(new_icon('chevron-down'))
        self._expand_btn.setToolTip("Expand toolbar")
        self._expand_btn.setIconSize(QSize(16, 16))
        self._expand_btn.clicked.connect(self.toggle_expanded)
        self._expand_btn.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                padding: 4px;
            }
            QToolButton:hover {
                background: #e0e0e0;
                border-radius: 4px;
            }
        """)
        self.addWidget(self._expand_btn)

        # Set initial width
        self.setFixedWidth(self._collapsed_width)

    def toggle_expanded(self):
        """Toggle between expanded and collapsed state."""
        from libs.utils.utils import new_icon

        self._expanded = not self._expanded

        if self._expanded:
            self._expand_btn.setIcon(new_icon('chevron-up'))
            self._expand_btn.setToolTip("Collapse toolbar")
            self.setFixedWidth(self._expanded_width)
        else:
            self._expand_btn.setIcon(new_icon('chevron-down'))
            self._expand_btn.setToolTip("Expand toolbar")
            self.setFixedWidth(self._collapsed_width)

        self.expandedChanged.emit(self._expanded)

    def set_expanded(self, expanded):
        """Set the expanded state programmatically."""
        if expanded != self._expanded:
            self.toggle_expanded()

    def is_expanded(self):
        """Return current expanded state."""
        return self._expanded


class ToolButton(QToolButton):
    """Custom toolbar button with DPI-aware sizing."""

    def __init__(self, icon_size=None):
        super(ToolButton, self).__init__()
        self._icon_size = icon_size or calculate_icon_size()
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)

    def update_icon_size(self, size):
        """Update the icon size."""
        self._icon_size = size
        self.setIconSize(QSize(size, size))
        self.updateGeometry()

    def sizeHint(self):
        hint = super(ToolButton, self).sizeHint()
        # Calculate width based on actual text
        fm = self.fontMetrics()
        text = self.text()
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        # Add padding for icon and margins
        width = max(hint.width(), text_width + 20, 70)
        height = max(hint.height(), self._icon_size + 30)
        return QSize(width, height)

    def minimumSizeHint(self):
        # Use actual text width for minimum
        fm = self.fontMetrics()
        text = self.text()
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        return QSize(max(text_width + 16, 65), self._icon_size + 24)


class DropdownToolButton(QToolButton):
    """Toolbar button with dropdown menu and DPI-aware sizing."""

    def __init__(self, text, icon=None, actions=None, icon_size=None):
        super(DropdownToolButton, self).__init__()
        self._icon_size = icon_size or calculate_icon_size()
        self.setText(text)
        if icon:
            self.setIcon(icon)
        self.setIconSize(QSize(self._icon_size, self._icon_size))
        self.setPopupMode(QToolButton.InstantPopup)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Preferred)

        # Create menu for dropdown actions
        self.dropdown_menu = QMenu(self)
        if actions:
            for action in actions:
                if action is None:
                    self.dropdown_menu.addSeparator()
                else:
                    self.dropdown_menu.addAction(action)
        self.setMenu(self.dropdown_menu)

    def add_action(self, action):
        """Add an action to the dropdown menu."""
        if action is None:
            self.dropdown_menu.addSeparator()
        else:
            self.dropdown_menu.addAction(action)

    def update_icon_size(self, size):
        """Update the icon size."""
        self._icon_size = size
        self.setIconSize(QSize(size, size))
        self.updateGeometry()

    def sizeHint(self):
        hint = super(DropdownToolButton, self).sizeHint()
        # Calculate width based on actual text
        fm = self.fontMetrics()
        text = self.text()
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        # Add padding for icon, dropdown arrow, and margins
        width = max(hint.width(), text_width + 30, 70)
        height = max(hint.height(), self._icon_size + 30)
        return QSize(width, height)

    def minimumSizeHint(self):
        # Use actual text width for minimum
        fm = self.fontMetrics()
        text = self.text()
        text_width = fm.horizontalAdvance(text) if hasattr(fm, 'horizontalAdvance') else fm.width(text)
        return QSize(max(text_width + 24, 65), self._icon_size + 24)
