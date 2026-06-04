# libs/widgets/view_scaling.py
"""Pure geometry helpers for fitting the canvas pixmap into the viewport.

Extracted from ``MainWindow.scale_fit_window`` / ``scale_fit_width`` so the
aspect-ratio math can be unit tested without a Qt main window. Each helper
returns a float scale factor; callers multiply by 100 for the zoom widget.

The live code path only calls these with a valid (non-null) image, so the
degenerate-size guards never fire in practice — they're defensive, ensuring a
collapsed viewport or empty pixmap returns a safe unit scale instead of raising
``ZeroDivisionError``.
"""

_EPSILON = 2.0  # Viewport padding so fitting doesn't itself spawn scrollbars.


def fit_window_scale(viewport_width, viewport_height,
                     pixmap_width, pixmap_height):
    """Return the scale that fits the pixmap fully inside the viewport.

    Preserves aspect ratio: the limiting dimension (width or height) is chosen
    by comparing the viewport and pixmap aspect ratios.
    """
    w1 = viewport_width - _EPSILON
    h1 = viewport_height - _EPSILON
    if h1 <= 0 or pixmap_width <= 0 or pixmap_height <= 0:
        return 1.0
    a1 = w1 / h1
    w2 = float(pixmap_width)
    h2 = float(pixmap_height)
    a2 = w2 / h2
    return w1 / w2 if a2 >= a1 else h1 / h2


def fit_width_scale(viewport_width, pixmap_width):
    """Return the scale that fits the pixmap's width to the viewport width."""
    if pixmap_width <= 0:
        return 1.0
    return (viewport_width - _EPSILON) / pixmap_width
