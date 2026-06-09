# libs/utils/dpi.py
"""Central DPI scaling utilities for HiDPI displays.

A single source of truth for the screen scale factor so chrome, dialogs,
stylesheets, and icons all scale by the same amount. Widget modules and the
theme system import from here rather than computing DPI themselves.
"""

try:
    from PyQt5.QtWidgets import QApplication
except ImportError:
    from PyQt4.QtGui import QApplication


def get_dpi_scale_factor():
    """Return the DPI scale factor for the primary screen.

    Returns:
        float: Scale factor (1.0 for standard 96 DPI, higher for HiDPI
            displays). Falls back to 1.0 when no application or screen is
            available (e.g. headless tests, Qt4).
    """
    app = QApplication.instance()
    if app is None:
        return 1.0

    try:
        screen = app.primaryScreen()
        if screen:
            # Logical DPI accounts for the user's display scaling setting.
            logical_dpi = screen.logicalDotsPerInch()
            # 96 DPI is the standard baseline on most systems.
            return logical_dpi / 96.0
    except AttributeError:
        # Qt4 has no primaryScreen(); treat as unscaled.
        pass

    return 1.0


def scale_px(n):
    """Scale a base pixel value by the current DPI factor.

    Args:
        n: Pixel value defined at the 96 DPI baseline.

    Returns:
        int: ``n`` scaled by the DPI factor, rounded to the nearest integer.
    """
    return int(round(n * get_dpi_scale_factor()))
