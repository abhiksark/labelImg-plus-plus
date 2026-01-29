# libs/styles.py
"""Modern stylesheet definitions for labelImg++."""

# Toolbar stylesheet with modern flat design
TOOLBAR_STYLE = """
QToolBar {
    background: #f5f5f5;
    border: none;
    border-right: 1px solid #ddd;
    spacing: 2px;
    padding: 4px;
}

QToolBar::separator {
    background: #ddd;
    width: 1px;
    height: 20px;
    margin: 6px 4px;
}

QToolButton {
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
    margin: 1px;
    color: #000000;
}

QToolButton:hover {
    background: #e0e0e0;
}

QToolButton:pressed {
    background: #d0d0d0;
}

QToolButton:checked {
    background: #cce5ff;
    color: #004085;
}

QToolButton:disabled {
    color: #999999;
}
"""

# Main window stylesheet
MAIN_WINDOW_STYLE = """
QMainWindow {
    background: #ffffff;
}

QDockWidget::title {
    background: #f5f5f5;
    padding: 6px;
    border-bottom: 1px solid #ddd;
}

QListWidget {
    background: #ffffff;
    border: 1px solid #ddd;
}

QListWidget::item:selected {
    background: #cce5ff;
    color: #004085;
}
"""

# Status bar stylesheet
STATUS_BAR_STYLE = """
QStatusBar {
    background: #f5f5f5;
    border-top: 1px solid #ddd;
}
"""


def get_combined_style():
    """Return combined stylesheet for the application."""
    return TOOLBAR_STYLE + MAIN_WINDOW_STYLE + STATUS_BAR_STYLE
