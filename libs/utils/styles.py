# libs/utils/styles.py
"""Theme and stylesheet definitions for labelImg++."""

from enum import Enum


class Theme(Enum):
    """Available application themes."""
    LIGHT = 'light'
    DARK = 'dark'


# Theme color palettes
LIGHT_COLORS = {
    'background': '#ffffff',
    'surface': '#f5f5f5',
    'border': '#dddddd',
    'text': '#000000',
    'text_secondary': '#666666',
    'text_disabled': '#999999',
    'accent': '#0078d4',
    'accent_light': '#cce5ff',
    'accent_text': '#004085',
    'hover': '#e0e0e0',
    'pressed': '#d0d0d0',
    'success': '#34a853',
    'warning': '#fbbc04',
    'error': '#ea4335',
}

DARK_COLORS = {
    'background': '#1e1e1e',
    'surface': '#2d2d2d',
    'border': '#404040',
    'text': '#e0e0e0',
    'text_secondary': '#a0a0a0',
    'text_disabled': '#666666',
    'accent': '#4da6ff',
    'accent_light': '#264f78',
    'accent_text': '#4da6ff',
    'hover': '#3d3d3d',
    'pressed': '#4d4d4d',
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',
}


def _get_colors(theme: Theme) -> dict:
    """Get color palette for the given theme."""
    return DARK_COLORS if theme == Theme.DARK else LIGHT_COLORS


def get_toolbar_style(theme: Theme) -> str:
    """Generate toolbar stylesheet for the given theme."""
    c = _get_colors(theme)
    return f"""
QToolBar {{
    background: {c['surface']};
    border: none;
    border-right: 1px solid {c['border']};
    spacing: 2px;
    padding: 4px;
}}

QToolBar::separator {{
    background: {c['border']};
    width: 1px;
    height: 20px;
    margin: 6px 4px;
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px;
    margin: 1px;
    color: {c['text']};
}}

QToolButton:hover {{
    background: {c['hover']};
}}

QToolButton:pressed {{
    background: {c['pressed']};
}}

QToolButton:checked {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QToolButton:disabled {{
    color: {c['text_disabled']};
}}
"""


def get_main_window_style(theme: Theme) -> str:
    """Generate main window stylesheet for the given theme."""
    c = _get_colors(theme)
    return f"""
QMainWindow {{
    background: {c['background']};
}}

QWidget {{
    background: {c['background']};
    color: {c['text']};
}}

QDockWidget {{
    color: {c['text']};
}}

QDockWidget::title {{
    background: {c['surface']};
    padding: 6px;
    border-bottom: 1px solid {c['border']};
}}

QListWidget {{
    background: {c['background']};
    border: 1px solid {c['border']};
    color: {c['text']};
}}

QListWidget::item {{
    padding: 4px;
}}

QListWidget::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QListWidget::item:hover {{
    background: {c['hover']};
}}

QScrollBar:vertical {{
    background: {c['surface']};
    width: 12px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: 4px;
    min-height: 20px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['text_secondary']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {c['surface']};
    height: 12px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {c['border']};
    border-radius: 4px;
    min-width: 20px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c['text_secondary']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QMenu {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    color: {c['text']};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 4px 8px;
}}

QMenuBar {{
    background: {c['surface']};
    color: {c['text']};
    border-bottom: 1px solid {c['border']};
}}

QMenuBar::item {{
    padding: 6px 10px;
}}

QMenuBar::item:selected {{
    background: {c['hover']};
}}

QComboBox {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 4px 8px;
    color: {c['text']};
}}

QComboBox:hover {{
    border-color: {c['accent']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}

QComboBox QAbstractItemView {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    color: {c['text']};
    selection-background-color: {c['accent_light']};
    selection-color: {c['accent_text']};
}}

QLineEdit {{
    background: {c['background']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 4px 8px;
    color: {c['text']};
}}

QLineEdit:focus {{
    border-color: {c['accent']};
}}

QPushButton {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 6px 16px;
    color: {c['text']};
}}

QPushButton:hover {{
    background: {c['hover']};
}}

QPushButton:pressed {{
    background: {c['pressed']};
}}

QPushButton:disabled {{
    color: {c['text_disabled']};
}}

QCheckBox {{
    color: {c['text']};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c['border']};
    border-radius: 3px;
    background: {c['background']};
}}

QCheckBox::indicator:checked {{
    background: {c['accent']};
    border-color: {c['accent']};
}}

QLabel {{
    color: {c['text']};
}}

QGroupBox {{
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}}

QTabWidget::pane {{
    border: 1px solid {c['border']};
    background: {c['background']};
}}

QTabBar::tab {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    padding: 8px 16px;
    color: {c['text']};
}}

QTabBar::tab:selected {{
    background: {c['background']};
    border-bottom-color: {c['background']};
}}

QTabBar::tab:hover:!selected {{
    background: {c['hover']};
}}

QProgressBar {{
    border: 1px solid {c['border']};
    border-radius: 4px;
    background: {c['surface']};
    text-align: center;
    color: {c['text']};
}}

QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: 3px;
}}

QTableWidget {{
    background: {c['background']};
    border: 1px solid {c['border']};
    color: {c['text']};
    gridline-color: {c['border']};
}}

QTableWidget::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QHeaderView::section {{
    background: {c['surface']};
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']};
    padding: 6px;
    color: {c['text']};
}}

QDialog {{
    background: {c['background']};
    color: {c['text']};
}}

QMessageBox {{
    background: {c['background']};
    color: {c['text']};
}}

QSpinBox, QDoubleSpinBox {{
    background: {c['background']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    padding: 4px;
    color: {c['text']};
}}

QToolTip {{
    background: {c['surface']};
    border: 1px solid {c['border']};
    color: {c['text']};
    padding: 4px;
}}
"""


def get_status_bar_style(theme: Theme) -> str:
    """Generate status bar stylesheet for the given theme."""
    c = _get_colors(theme)
    return f"""
QStatusBar {{
    background: {c['surface']};
    border-top: 1px solid {c['border']};
    color: {c['text']};
}}

QStatusBar QLabel {{
    color: {c['text']};
}}
"""


def get_canvas_background(theme: Theme) -> str:
    """Get canvas background color for the given theme."""
    return '#2d2d2d' if theme == Theme.DARK else '#e0e0e0'


def get_slider_style(theme: Theme) -> str:
    """Generate slider stylesheet for gallery widget."""
    c = _get_colors(theme)
    return f"""
QSlider::groove:horizontal {{
    height: 6px;
    background: {c['border']};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::handle:horizontal:hover {{
    background: {c['accent_text']};
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: 3px;
}}
"""


def get_gallery_controls_style(theme: Theme) -> str:
    """Generate gallery slider frame and button styles."""
    c = _get_colors(theme)
    return {
        'frame': f"""
QFrame {{
    background-color: {c['surface']};
    border-bottom: 1px solid {c['border']};
}}
""",
        'button': f"""
QPushButton {{
    background-color: {c['background']};
    border: 1px solid {c['border']};
    border-radius: 4px;
    font-weight: bold;
    font-size: 11px;
    color: {c['text']};
}}
QPushButton:hover {{
    background-color: {c['hover']};
    border-color: {c['text_secondary']};
}}
QPushButton:pressed {{
    background-color: {c['pressed']};
}}
""",
        'label': f"font-weight: bold; color: {c['text']};",
    }


def get_expand_button_style(theme: Theme) -> str:
    """Generate expand button stylesheet for toolbar."""
    c = _get_colors(theme)
    return f"""
QToolButton {{
    border: none;
    background: transparent;
    padding: 4px;
}}
QToolButton:hover {{
    background: {c['hover']};
    border-radius: 4px;
}}
"""


def get_label_dialog_style(theme: Theme) -> str:
    """Generate label dialog filter styles."""
    c = _get_colors(theme)
    return {
        'filter_label': f"color: {c['text_secondary']};",
        'count_label': f"color: {c['text_secondary']}; font-size: 11px;",
    }


def get_gallery_list_style(theme: Theme) -> str:
    """Generate gallery list widget stylesheet."""
    c = _get_colors(theme)
    return f"""
QListWidget {{
    background: {c['background']};
    border: none;
    color: {c['text']};
}}
QListWidget::item {{
    color: {c['text']};
    padding: 4px;
}}
QListWidget::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}
QListWidget::item:hover {{
    background: {c['hover']};
}}
"""


def get_theme_colors(theme: Theme) -> dict:
    """Get full color palette for the given theme."""
    return _get_colors(theme)


def get_stylesheet(theme: Theme) -> str:
    """Generate complete stylesheet for the given theme."""
    return (
        get_toolbar_style(theme) +
        get_main_window_style(theme) +
        get_status_bar_style(theme)
    )


# Legacy compatibility
TOOLBAR_STYLE = get_toolbar_style(Theme.LIGHT)
MAIN_WINDOW_STYLE = get_main_window_style(Theme.LIGHT)
STATUS_BAR_STYLE = get_status_bar_style(Theme.LIGHT)


def get_combined_style():
    """Return combined stylesheet for the application (light theme)."""
    return get_stylesheet(Theme.LIGHT)
