# libs/integrations/mask_to_polygon.py
"""Trace a boolean segmentation mask into a single simplified polygon ring.

Largest connected component -> external contour (holes implicitly filled) ->
Douglas-Peucker simplification with a perimeter-proportional epsilon, capped at
MAX_POLYGON_POINTS. Takes a numpy + cv2 mask and returns a list of (x, y) tuples;
QPointF is used internally only to reuse the shared douglas_peucker simplifier.
"""

import cv2
import numpy as np
from PyQt5.QtCore import QPointF

from libs.core.shape import MAX_POLYGON_POINTS
from libs.utils.utils import douglas_peucker

_AREA_FLOOR_FRACTION = 0.0005   # 0.05% of total pixels


def mask_to_polygon(mask, max_points=MAX_POLYGON_POINTS):
    """Return a list of (x, y) float tuples, or None if no usable contour."""
    if max_points < 3:
        raise ValueError("max_points must be >= 3, got %d" % max_points)
    mask = np.asarray(mask, dtype=bool)
    if mask.sum() < max(1, int(_AREA_FLOOR_FRACTION * mask.size)):
        return None

    binary = (mask.astype(np.uint8)) * 255
    count, labels = cv2.connectedComponents(binary)
    if count <= 1:
        return None
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0                        # ignore background
    largest = int(sizes.argmax())
    component = (labels == largest).astype(np.uint8) * 255

    contours, _ = cv2.findContours(
        component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    contour = max(contours, key=cv2.contourArea)
    # Pre-reduce with cv2's iterative approximation before the recursive
    # douglas_peucker: a jagged contour on a large image can otherwise be deep
    # enough to hit Python's recursion limit.
    contour = cv2.approxPolyDP(contour, 2.0, True)
    qpoints = [QPointF(float(p[0][0]), float(p[0][1])) for p in contour]
    if len(qpoints) < 3:
        return None

    epsilon = max(1.0, 0.01 * cv2.arcLength(contour, True))
    simplified = douglas_peucker(qpoints, epsilon)
    while len(simplified) > max_points:
        epsilon *= 1.5
        simplified = douglas_peucker(qpoints, epsilon)
    if len(simplified) < 3:
        return None
    return [(p.x(), p.y()) for p in simplified]
