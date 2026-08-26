"""Small Qt-compatible helpers for workspace accessibility validation."""

try:
    from PyQt5.QtWidgets import (
        QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox,
        QLineEdit, QWidget,
    )
except ImportError:
    from PyQt4.QtGui import (
        QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox,
        QLineEdit, QWidget,
    )


def _linear_srgb(channel):
    """Convert one 8-bit sRGB channel to a linear-light value."""
    value = max(0.0, min(255.0, float(channel))) / 255.0
    if value <= 0.03928:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color):
    """Return the WCAG relative luminance of an opaque Qt color."""
    return (
        0.2126 * _linear_srgb(color.red())
        + 0.7152 * _linear_srgb(color.green())
        + 0.0722 * _linear_srgb(color.blue())
    )


def contrast_ratio(first, second):
    """Return the WCAG contrast ratio between two Qt colors."""
    high, low = sorted(
        (relative_luminance(first), relative_luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def visible_primary_targets(root):
    """Return visible action controls that must meet target-size contracts.

    A widget may opt out only when it is intentionally marked as a secondary
    action.  Hidden controls are excluded because they cannot be reached by a
    pointer or a keyboard user in the current workspace projection.
    """
    target_types = (
        QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox,
        QLineEdit,
    )
    return tuple(
        widget for widget in root.findChildren(QWidget)
        if isinstance(widget, target_types)
        and widget.isVisibleTo(root)
        and not bool(widget.property('secondaryAction'))
    )
