# libs/styles.py
"""Modern stylesheet definitions for labelImg++."""

# Toolbar stylesheet with modern flat design and hover effects
TOOLBAR_STYLE = """
QToolBar {
    background: #f8f9fa;
    border: none;
    border-right: 1px solid #dee2e6;
    spacing: 2px;
    padding: 4px;
}

QToolBar::separator {
    background: #dee2e6;
    width: 1px;
    height: 24px;
    margin: 8px 4px;
}

QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px;
    margin: 2px;
    color: #495057;
}

QToolButton:hover {
    background: #e9ecef;
}

QToolButton:pressed {
    background: #dee2e6;
}

QToolButton:checked {
    background: #d0ebff;
    color: #1971c2;
}

QToolButton:disabled {
    color: #adb5bd;
}

QToolButton::menu-indicator {
    image: none;
}
"""

# Main window stylesheet
MAIN_WINDOW_STYLE = """
QMainWindow {
    background: #ffffff;
}

QDockWidget {
    titlebar-close-icon: url(:/close);
    titlebar-normal-icon: url(:/maximize-2);
}

QDockWidget::title {
    background: #f8f9fa;
    padding: 8px;
    border-bottom: 1px solid #dee2e6;
}

QListWidget {
    background: #ffffff;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    padding: 4px;
}

QListWidget::item {
    padding: 4px 8px;
    border-radius: 4px;
}

QListWidget::item:hover {
    background: #f1f3f4;
}

QListWidget::item:selected {
    background: #d0ebff;
    color: #1971c2;
}

QScrollBar:vertical {
    background: #f8f9fa;
    width: 12px;
    border-radius: 6px;
}

QScrollBar::handle:vertical {
    background: #dee2e6;
    border-radius: 6px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #ced4da;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

# Status bar stylesheet
STATUS_BAR_STYLE = """
QStatusBar {
    background: #f8f9fa;
    border-top: 1px solid #dee2e6;
    padding: 4px;
}

QStatusBar::item {
    border: none;
}
"""


def get_combined_style():
    """Return combined stylesheet for the application."""
    return TOOLBAR_STYLE + MAIN_WINDOW_STYLE + STATUS_BAR_STYLE
