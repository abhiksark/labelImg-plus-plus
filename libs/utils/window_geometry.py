# libs/utils/window_geometry.py
"""Screen-relative sizing and on-screen clamping for the main window.

The functions here take the target screen's available rectangle rather than
querying ``QApplication`` themselves, so they stay pure and can be unit tested
without a real screen.
"""

try:
    from PyQt5.QtCore import QPoint, QRect, QSize
except ImportError:
    from PyQt4.QtCore import QPoint, QRect, QSize

from libs.utils.dpi import scale_px

#: Fraction of the available screen a fresh profile opens at.
DEFAULT_SCREEN_FRACTION = 0.8

#: Smallest and largest default, before the screen itself has the final say.
#: These are content sizes, so they track the same DPI factor as the chrome.
MIN_DEFAULT_WIDTH = 1024
MIN_DEFAULT_HEIGHT = 700
MAX_DEFAULT_WIDTH = 1600
MAX_DEFAULT_HEIGHT = 1000


def _clamp(value, lowest, highest):
    return max(lowest, min(value, highest))


def default_window_size(available):
    """Return the size a window with no persisted geometry should open at.

    Args:
        available: The target screen's ``availableGeometry()`` as a ``QRect``.

    Returns:
        A ``QSize`` that always fits inside ``available``.
    """
    if not isinstance(available, QRect) or available.isEmpty():
        return QSize(scale_px(MIN_DEFAULT_WIDTH), scale_px(MIN_DEFAULT_HEIGHT))

    width = _clamp(int(available.width() * DEFAULT_SCREEN_FRACTION),
                   scale_px(MIN_DEFAULT_WIDTH), scale_px(MAX_DEFAULT_WIDTH))
    height = _clamp(int(available.height() * DEFAULT_SCREEN_FRACTION),
                    scale_px(MIN_DEFAULT_HEIGHT), scale_px(MAX_DEFAULT_HEIGHT))

    # The screen has the last word: on a small display the minimum above would
    # otherwise open a window larger than the screen it sits on.
    return QSize(min(width, available.width()),
                 min(height, available.height()))


def fit_to_available(available, size, position):
    """Constrain a restored window geometry to the screen it will open on.

    Shrinks an oversized window and slides an off-screen one back into view,
    so geometry saved on a larger or since-disconnected monitor still opens
    somewhere the user can reach it.

    Args:
        available: The target screen's ``availableGeometry()`` as a ``QRect``.
        size: Persisted ``QSize``, or any junk a hand-edited settings file
            may contain.
        position: Persisted ``QPoint``, or junk.

    Returns:
        A ``(QSize, QPoint)`` pair fully contained by ``available``.
    """
    if not isinstance(available, QRect) or available.isEmpty():
        fallback = default_window_size(available)
        origin = position if isinstance(position, QPoint) else QPoint(0, 0)
        return fallback, origin

    if not isinstance(size, QSize) or not size.isValid():
        size = default_window_size(available)

    width = min(max(1, size.width()), available.width())
    height = min(max(1, size.height()), available.height())

    if not isinstance(position, QPoint):
        position = available.topLeft()

    # Clamp the whole window inside the screen, not just its top-left corner:
    # a corner one pixel inside a display still leaves the body off it.
    x = _clamp(position.x(), available.left(), available.right() - width + 1)
    y = _clamp(position.y(), available.top(), available.bottom() - height + 1)

    return QSize(width, height), QPoint(x, y)
