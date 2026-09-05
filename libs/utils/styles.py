# libs/utils/styles.py
"""Theme and stylesheet definitions for labelImg++."""

from enum import Enum

from libs.utils.dpi import scale_px


class Theme(Enum):
    """Available application themes."""
    LIGHT = 'light'
    DARK = 'dark'


# Shared workspace metrics. Values are logical pixels and pass through
# ``scale_px`` at the point of use so the same tokens support high-DPI screens.
COMMAND_BAR_HEIGHT = 44
SPACING = {
    'hairline': 1,
    'xs': 2,
    'sm': 4,
    'md': 8,
    'lg': 12,
    'xl': 16,
}
RADII = {
    'sm': 4,
    'md': 6,
    'pill': 999,
}
TYPOGRAPHY = {
    'caption': 11,
    'body': 12,
    'label': 12,
    'weight_medium': 500,
    'weight_semibold': 600,
}


# Semantic theme palettes. Compatibility aliases such as ``accent_light`` and
# ``success`` remain available to existing widgets while new workspace chrome
# uses the explicit surface/focus/status names.
LIGHT_COLORS = {
    'background': '#f7f8fa',
    'surface': '#ffffff',
    'surface_subtle': '#f1f3f6',
    'surface_raised': '#ffffff',
    'border': '#dfe3e8',
    'border_strong': '#c8d0da',
    'text': '#182230',
    'text_secondary': '#5d6b7a',
    'text_disabled': '#9aa4b2',
    'accent': '#2563eb',
    'accent_hover': '#1d4ed8',
    'accent_pressed': '#1e40af',
    'accent_light': '#dbeafe',
    'accent_text': '#1d4ed8',
    'on_accent': '#ffffff',
    'focus': '#2563eb',
    'hover': '#eef2f6',
    'pressed': '#e2e8f0',
    'success': '#16803c',
    'warning': '#b45309',
    'error': '#c73737',
    'info': '#2563eb',
    'status_success': '#16803c',
    'status_warning': '#b45309',
    'warning_surface': '#fff7ed',
    'status_error': '#c73737',
    'status_info': '#2563eb',
    'verified_bg': '#b8ef26',  # Bright green overlay for verified images
    'canvas_bg': '#e0e0e0',    # Canvas viewport background
    'placeholder': '#dcdcdc',  # Light gray for placeholders
    'item_bg': '#f0f0f0',      # Very light gray for item backgrounds
    'status_saved': '#34a853',   # Green
    'status_unsaved': '#ff9800', # Orange
    'issue_typo': '#ffc8c8',      # Light red
    'issue_case': '#ffffc8',      # Light yellow
    'issue_whitespace': '#ffe6c8', # Light orange
    'issue_undefined': '#c8c8ff',  # Light blue
    'issue_duplicate': '#ffc8ff',  # Light purple
    'status_no_labels': '#969696',   # Gray
    'status_has_labels': '#4285f4',  # Blue
    'status_verified': '#34a853',    # Green
    'grid_line': '#cccccc',
    'alignment_guide': '#4da6ff',
    'midpoint_handle': '#999999',
    # Track state colours: anchor/interpolated/pending stand out with state significance.
    # track_absent recedes into the surface in both themes (not lifted in dark mode)
    # because it marks the absence of tracking data and must not compete visually.
    'track_anchor': '#2db45a',
    'track_interpolated': '#468cdc',
    'track_pending': '#eba523',
    'track_absent': '#c9ccd1',
}

DARK_COLORS = {
    'background': '#1e1e1e',
    'surface': '#2d2d2d',
    'surface_subtle': '#252525',
    'surface_raised': '#343434',
    'border': '#404040',
    'border_strong': '#565656',
    'text': '#e0e0e0',
    'text_secondary': '#a0a0a0',
    'text_disabled': '#666666',
    'accent': '#4da6ff',
    'accent_hover': '#70b7ff',
    'accent_pressed': '#2f8fe8',
    'accent_light': '#264f78',
    # Lightened from #4da6ff, which sat at 3.32:1 on accent_light and failed
    # the 4.5:1 body-text bar for every selected row, menu item and caption.
    'accent_text': '#a8d3ff',
    'on_accent': '#101820',
    'focus': '#70b7ff',
    'hover': '#3d3d3d',
    'pressed': '#4d4d4d',
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',
    'info': '#4da6ff',
    'status_success': '#4caf50',
    'status_warning': '#ff9800',
    'warning_surface': '#3b2a1a',
    'status_error': '#f44336',
    'status_info': '#4da6ff',
    'verified_bg': '#295131',  # Quiet green wash for verified canvases
    'canvas_bg': '#2d2d2d',    # Canvas viewport background
    'placeholder': '#3d3d3d',  # Dark gray for placeholders
    'item_bg': '#2d2d2d',      # Darker gray for item backgrounds
    'status_saved': '#4caf50',   # Slightly brighter green
    'status_unsaved': '#ff9800', # Same orange (good contrast in dark)
    'issue_typo': '#8b3a3a',      # Dark red
    'issue_case': '#8b8b3a',      # Dark yellow
    'issue_whitespace': '#8b6a3a', # Dark orange
    'issue_undefined': '#3a3a8b',  # Dark blue
    'issue_duplicate': '#8b3a8b',  # Dark purple
    'status_no_labels': '#808080',   # Slightly lighter gray
    'status_has_labels': '#4da6ff',  # Brighter blue
    'status_verified': '#4caf50',    # Brighter green
    'grid_line': '#404040',
    'alignment_guide': '#4da6ff',
    'midpoint_handle': '#666666',
    # Track state colours: anchor/interpolated/pending lifted for dark-surface contrast.
    # track_absent remains subdued (not lifted) so it recedes and marks absence.
    'track_anchor': '#4ecb75',
    'track_interpolated': '#6ba9e8',
    'track_pending': '#f0b84a',
    'track_absent': '#4a4d52',
}


def hex_to_qcolor(hex_color, alpha=255):
    """Convert hex color string to QColor.

    Args:
        hex_color: Hex color string (e.g., '#ff0000' or 'ff0000')
        alpha: Alpha value 0-255 (default: 255 for opaque)

    Returns:
        QColor object
    """
    from PyQt6.QtGui import QColor
    hex_clean = hex_color.lstrip('#')
    r, g, b = tuple(int(hex_clean[i:i+2], 16) for i in (0, 2, 4))
    return QColor(r, g, b, alpha)


def _get_colors(theme: Theme) -> dict:
    """Get color palette for the given theme."""
    return DARK_COLORS if theme == Theme.DARK else LIGHT_COLORS


def get_design_tokens(theme: Theme) -> dict:
    """Return the complete semantic token set for workspace widgets."""
    return {
        'color': _get_colors(theme),
        'space': dict(SPACING),
        'radius': dict(RADII),
        'type': dict(TYPOGRAPHY),
    }


def get_command_bar_style(theme: Theme) -> str:
    """Generate the fixed application command-bar stylesheet."""
    tokens = get_design_tokens(theme)
    c = tokens['color']
    space = tokens['space']
    radius = tokens['radius']
    type_tokens = tokens['type']
    return f"""
QWidget#workspaceCommandBar {{
    background: {c['surface_raised']};
    border-bottom: {scale_px(1)}px solid {c['border']};
}}

QWidget#workspaceCommandBar QToolButton {{
    min-height: {scale_px(30)}px;
    max-height: {scale_px(30)}px;
    padding: 0 {scale_px(space['md'])}px;
    border: {scale_px(1)}px solid transparent;
    border-radius: {scale_px(radius['md'])}px;
    background: transparent;
    color: {c['text']};
    font-size: {scale_px(type_tokens['label'])}px;
    font-weight: {type_tokens['weight_medium']};
}}

QWidget#workspaceCommandBar QToolButton:hover {{
    background: {c['hover']};
    border-color: {c['border']};
}}

QWidget#workspaceCommandBar QToolButton:pressed,
QWidget#workspaceCommandBar QToolButton:checked {{
    background: {c['pressed']};
    border-color: {c['border_strong']};
}}

QWidget#workspaceCommandBar QToolButton:focus {{
    border: {scale_px(2)}px solid {c['focus']};
}}

QWidget#workspaceCommandBar QToolButton:disabled {{
    color: {c['text_disabled']};
    background: transparent;
    border-color: transparent;
}}

QWidget#workspaceCommandBar QToolButton#primaryActionButton {{
    min-width: {scale_px(104)}px;
    background: {c['accent']};
    border-color: {c['accent']};
    color: {c['on_accent']};
    font-weight: {type_tokens['weight_semibold']};
}}

QWidget#workspaceCommandBar QToolButton#primaryActionButton:hover {{
    background: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}

QWidget#workspaceCommandBar QToolButton#primaryActionButton:pressed {{
    background: {c['accent_pressed']};
    border-color: {c['accent_pressed']};
}}

QWidget#workspaceCommandBar QToolButton#primaryActionButton:disabled {{
    background: {c['surface_subtle']};
    border-color: {c['border']};
    color: {c['text_disabled']};
}}

QToolButton#applicationMenuButton {{
    font-weight: {type_tokens['weight_semibold']};
}}

QToolButton#previousButton,
QToolButton#nextButton,
QToolButton#overflowButton {{
    min-width: {scale_px(30)}px;
    max-width: {scale_px(30)}px;
    padding: 0;
}}

QLabel#documentLabel {{
    color: {c['text']};
    font-size: {scale_px(type_tokens['body'])}px;
    font-weight: {type_tokens['weight_medium']};
    background: transparent;
}}

QLabel#documentSaveState {{
    color: {c['text_secondary']};
    font-size: {scale_px(type_tokens['caption'])}px;
    background: transparent;
    padding: 0 {scale_px(space['xs'])}px;
}}

QLabel#documentDirtyIndicator {{
    color: {c['status_warning']};
    font-size: {scale_px(18)}px;
    background: transparent;
}}

QLabel#documentPosition {{
    color: {c['text_secondary']};
    font-size: {scale_px(type_tokens['caption'])}px;
    background: {c['surface_subtle']};
    border-radius: {scale_px(radius['sm'])}px;
    padding: 0 {scale_px(space['sm'])}px;
}}
"""


def get_toolbar_style(theme: Theme) -> str:
    """Generate toolbar stylesheet for the given theme."""
    c = _get_colors(theme)
    return f"""
QToolBar {{
    background: {c['surface']};
    border: none;
    border-right: {scale_px(1)}px solid {c['border']};
    spacing: {scale_px(2)}px;
    padding: {scale_px(4)}px;
}}

QToolBar::separator {{
    background: {c['border']};
    width: {scale_px(1)}px;
    height: {scale_px(20)}px;
    margin: {scale_px(6)}px {scale_px(4)}px;
}}

QToolButton {{
    background: transparent;
    border: none;
    border-radius: {scale_px(4)}px;
    padding: {scale_px(4)}px;
    margin: {scale_px(1)}px;
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


def get_tool_rail_style(theme: Theme) -> str:
    """Generate the fixed modern annotation-rail stylesheet."""
    c = _get_colors(theme)
    return f"""
QWidget#annotationToolRail {{
    background: {c['surface']};
    border-right: {scale_px(1)}px solid {c['border']};
}}

QWidget#annotationToolRail QToolButton {{
    background: transparent;
    border: {scale_px(1)}px solid transparent;
    border-radius: {scale_px(7)}px;
    color: {c['text_secondary']};
    padding: 0;
}}

QWidget#annotationToolRail QToolButton:hover {{
    background: {c['hover']};
    color: {c['text']};
}}

QWidget#annotationToolRail QToolButton:focus {{
    border: {scale_px(2)}px solid {c['focus']};
}}

QWidget#annotationToolRail QToolButton:checked {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QWidget#annotationToolRail QToolButton:disabled {{
    color: {c['text_disabled']};
}}
"""


def get_workspace_inspector_style(theme: Theme) -> str:
    """Generate the fixed inspector shell stylesheet."""
    c = _get_colors(theme)
    return f"""
QWidget#workspaceInspector {{
    background: {c['surface']};
    border-left: {scale_px(1)}px solid {c['border']};
}}

QWidget#workspaceInspector QTabWidget::pane {{
    border: none;
    border-top: {scale_px(1)}px solid {c['border']};
}}

QWidget#workspaceInspector QTabBar::tab {{
    min-height: {scale_px(34)}px;
    padding: 0 {scale_px(14)}px;
}}

QWidget#workspaceInspector QToolButton#collapseInspectorButton {{
    border: none;
    padding: {scale_px(6)}px;
}}

QWidget#workspaceInspector QToolButton:focus {{
    border: {scale_px(2)}px solid {c['focus']};
}}

QWidget#inspectorContextCard {{
    background: {c['surface_subtle']};
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(7)}px;
    margin: {scale_px(8)}px;
}}

QLabel#inspectorContextEyebrow {{
    color: {c['text_secondary']};
    font-size: {scale_px(10)}px;
    font-weight: 600;
    background: transparent;
}}

QLabel#inspectorContextTitle {{
    color: {c['text']};
    font-size: {scale_px(13)}px;
    font-weight: 600;
    background: transparent;
}}

QLabel#inspectorContextDetail {{
    color: {c['text_secondary']};
    font-size: {scale_px(11)}px;
    background: transparent;
}}

QWidget#inspectorContextCard QToolButton {{
    min-height: {scale_px(28)}px;
    padding: 0 {scale_px(7)}px;
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(5)}px;
    background: {c['surface']};
    color: {c['text']};
}}

QWidget#inspectorContextCard QToolButton:hover {{
    background: {c['hover']};
    border-color: {c['border_strong']};
}}

QWidget#inspectorContextCard QToolButton[primary="true"] {{
    background: {c['accent']};
    border-color: {c['accent']};
    color: {c['on_accent']};
    font-weight: 600;
}}

QWidget#inspectorContextCard QToolButton[primary="true"]:hover {{
    background: {c['accent_hover']};
    border-color: {c['accent_hover']};
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
    padding: {scale_px(6)}px;
    border-bottom: {scale_px(1)}px solid {c['border']};
}}

QListWidget, QListView {{
    background: {c['background']};
    border: {scale_px(1)}px solid {c['border']};
    color: {c['text']};
}}

QListWidget::item, QListView::item {{
    padding: {scale_px(4)}px;
}}

QListWidget::item:selected, QListView::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QListWidget::item:hover, QListView::item:hover {{
    background: {c['hover']};
}}

QLabel#videoElapsedPosition {{
    color: {c['text']};
    font-weight: 600;
}}

QLabel#videoWorkflowStage, QLabel#videoWorkflowArrow {{
    color: {c['text_secondary']};
    background: transparent;
    font-size: {scale_px(11)}px;
}}

QLabel#videoWorkflowStage[done="true"] {{
    color: {c['status_saved']};
}}

QLabel#videoWorkflowStage[active="true"] {{
    color: {c['accent_text']};
    font-weight: 600;
}}

QScrollBar:vertical {{
    background: {c['surface']};
    width: {scale_px(12)}px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: {scale_px(4)}px;
    min-height: {scale_px(20)}px;
    margin: {scale_px(2)}px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['text_secondary']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: {scale_px(0)}px;
}}

QScrollBar:horizontal {{
    background: {c['surface']};
    height: {scale_px(12)}px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {c['border']};
    border-radius: {scale_px(4)}px;
    min-width: {scale_px(20)}px;
    margin: {scale_px(2)}px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c['text_secondary']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: {scale_px(0)}px;
}}

QMenu {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    color: {c['text']};
    padding: {scale_px(4)}px;
}}

QMenu::item {{
    padding: {scale_px(6)}px {scale_px(20)}px;
    border-radius: {scale_px(4)}px;
}}

QMenu::item:selected {{
    background: {c['accent_light']};
    color: {c['accent_text']};
}}

QMenu::separator {{
    height: {scale_px(1)}px;
    background: {c['border']};
    margin: {scale_px(4)}px {scale_px(8)}px;
}}

QMenuBar {{
    background: {c['surface']};
    color: {c['text']};
    border-bottom: {scale_px(1)}px solid {c['border']};
}}

QMenuBar::item {{
    padding: {scale_px(6)}px {scale_px(10)}px;
}}

QMenuBar::item:selected {{
    background: {c['hover']};
}}

QComboBox {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    padding: {scale_px(4)}px {scale_px(8)}px;
    color: {c['text']};
}}

QComboBox:hover {{
    border-color: {c['accent']};
}}

QComboBox::drop-down {{
    border: none;
    padding-right: {scale_px(8)}px;
}}

QComboBox QAbstractItemView {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    color: {c['text']};
    selection-background-color: {c['accent_light']};
    selection-color: {c['accent_text']};
}}

QLineEdit {{
    background: {c['background']};
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    padding: {scale_px(4)}px {scale_px(8)}px;
    color: {c['text']};
}}

QLineEdit:focus {{
    border-color: {c['accent']};
}}

QPushButton {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    padding: {scale_px(6)}px {scale_px(16)}px;
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
    width: {scale_px(16)}px;
    height: {scale_px(16)}px;
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(3)}px;
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
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    margin-top: {scale_px(8)}px;
    padding-top: {scale_px(8)}px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: {scale_px(10)}px;
    padding: 0 {scale_px(5)}px;
}}

QTabWidget::pane {{
    border: {scale_px(1)}px solid {c['border']};
    background: {c['background']};
}}

QTabBar::tab {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    padding: {scale_px(8)}px {scale_px(16)}px;
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
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    background: {c['surface']};
    text-align: center;
    color: {c['text']};
}}

QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: {scale_px(3)}px;
}}

QTableWidget {{
    background: {c['background']};
    border: {scale_px(1)}px solid {c['border']};
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
    border-right: {scale_px(1)}px solid {c['border']};
    border-bottom: {scale_px(1)}px solid {c['border']};
    padding: {scale_px(6)}px;
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
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    padding: {scale_px(4)}px;
    color: {c['text']};
}}

QToolTip {{
    background: {c['surface']};
    border: {scale_px(1)}px solid {c['border']};
    color: {c['text']};
    padding: {scale_px(4)}px;
}}
"""


def get_status_bar_style(theme: Theme) -> str:
    """Generate status bar stylesheet for the given theme."""
    c = _get_colors(theme)
    return f"""
QStatusBar {{
    background: {c['surface']};
    border-top: {scale_px(1)}px solid {c['border']};
    color: {c['text']};
}}

QStatusBar QLabel {{
    color: {c['text']};
}}
"""


def get_workspace_pages_style(theme: Theme) -> str:
    """Generate central-page, canvas-chrome, and slim-strip styling."""
    c = _get_colors(theme)
    return f"""
QWidget#canvasChrome, QWidget#workspaceStatusStrip {{
    background: {c['surface']};
    color: {c['text']};
}}
QWidget#canvasChrome {{
    border-bottom: {scale_px(1)}px solid {c['border']};
}}
QWidget#saveErrorNotice {{
    background: {c['warning_surface']};
    border-bottom: {scale_px(1)}px solid {c['status_warning']};
}}
QLabel#saveErrorTitle {{
    color: {c['text']};
    font-weight: 600;
}}
QLabel#saveErrorDetail {{
    color: {c['text_secondary']};
    font-size: {scale_px(11)}px;
}}
QWidget#saveErrorNotice QPushButton {{
    min-height: {scale_px(26)}px;
    padding: 0 {scale_px(8)}px;
}}
QLabel#annotationSessionHint {{
    color: {c['accent_text']};
    background: {c['accent_light']};
    border: {scale_px(1)}px solid {c['border']};
    border-radius: {scale_px(4)}px;
    padding: {scale_px(3)}px {scale_px(8)}px;
    font-size: {scale_px(11)}px;
    font-weight: 600;
}}
QWidget#workspaceStatusStrip {{
    border-top: {scale_px(1)}px solid {c['border']};
}}
QWidget#workspaceStatusStrip QLabel {{
    color: {c['text_secondary']};
    font-size: {scale_px(10)}px;
}}
QWidget#emptyWorkspacePage {{
    background: {c['background']};
}}
QLabel#emptyWorkspaceTitle {{
    color: {c['text']};
    font-size: {scale_px(24)}px;
    font-weight: 600;
}}
QLabel#emptyRecentTitle {{
    color: {c['text_secondary']};
    font-weight: 600;
}}
"""


def get_canvas_background(theme: Theme) -> str:
    """Get canvas background color for the given theme."""
    return _get_colors(theme)['canvas_bg']


def get_slider_style(theme: Theme) -> str:
    """Generate slider stylesheet for gallery widget."""
    c = _get_colors(theme)
    return f"""
QSlider::groove:horizontal {{
    height: {scale_px(6)}px;
    background: {c['border']};
    border-radius: {scale_px(3)}px;
}}
QSlider::handle:horizontal {{
    background: {c['accent']};
    width: {scale_px(16)}px;
    height: {scale_px(16)}px;
    margin: -{scale_px(5)}px 0;
    border-radius: {scale_px(8)}px;
}}
QSlider::handle:horizontal:hover {{
    background: {c['accent_text']};
}}
QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: {scale_px(3)}px;
}}
"""


def get_gallery_controls_style(theme: Theme) -> str:
    """Generate gallery slider frame and button styles."""
    c = _get_colors(theme)
    return {
        'frame': f"QFrame {{ background-color: {c['surface']}; border-bottom: {scale_px(1)}px solid {c['border']}; }}",
        'button': f"""QPushButton {{
            background-color: {c['background']};
            border: {scale_px(1)}px solid {c['border']};
            border-radius: {scale_px(4)}px;
            font-weight: bold;
            font-size: {scale_px(11)}px;
            color: {c['text']};
            /* The main-window sheet sets padding: 6px 17px on every
               QPushButton. These are fixed at 32px wide, so inheriting it
               leaves a negative content width and clips S/M/L/XL to a
               sliver. */
            padding: 0px;
        }}
        QPushButton:hover {{
            background-color: {c['hover']};
        }}
        QPushButton:pressed {{
            background-color: {c['pressed']};
        }}""",
        'label': f"font-weight: bold; color: {c['text']};",
    }


def get_expand_button_style(theme: Theme) -> str:
    """Generate expand button stylesheet for toolbar."""
    c = _get_colors(theme)
    return f"""
QToolButton {{
    border: none;
    background: transparent;
    padding: {scale_px(4)}px;
}}
QToolButton:hover {{
    background: {c['hover']};
    border-radius: {scale_px(4)}px;
}}
"""


def get_label_dialog_style(theme: Theme) -> str:
    """Generate label dialog filter styles."""
    c = _get_colors(theme)
    return {
        'filter_label': f"color: {c['text_secondary']};",
        'count_label': f"color: {c['text_secondary']}; font-size: {scale_px(11)}px;",
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
    padding: {scale_px(4)}px;
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
        get_status_bar_style(theme) +
        get_workspace_pages_style(theme)
    )


# Legacy compatibility
TOOLBAR_STYLE = get_toolbar_style(Theme.LIGHT)
MAIN_WINDOW_STYLE = get_main_window_style(Theme.LIGHT)
STATUS_BAR_STYLE = get_status_bar_style(Theme.LIGHT)


def get_combined_style():
    """Return combined stylesheet for the application (light theme)."""
    return get_stylesheet(Theme.LIGHT)
