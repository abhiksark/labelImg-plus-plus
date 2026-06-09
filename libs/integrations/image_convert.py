# libs/integrations/image_convert.py
"""Convert a Qt QImage into a contiguous uint8 RGB numpy array.

Isolated and unit-tested because QImage row stride (bytesPerLine) is padded to
a 4-byte boundary, a classic source of corrupted-image bugs.
"""

import numpy as np
from PyQt5.QtGui import QImage


def qimage_to_rgb(qimage: QImage) -> np.ndarray:
    """Return an (H, W, 3) uint8 array in RGB channel order."""
    img = qimage.convertToFormat(QImage.Format_RGB888)
    width, height = img.width(), img.height()
    bytes_per_line = img.bytesPerLine()
    ptr = img.bits()
    ptr.setsize(height * bytes_per_line)
    rows = np.frombuffer(ptr, dtype=np.uint8).reshape(height, bytes_per_line)
    # np.array() copies immediately while img is still alive; np.ascontiguousarray
    # skips the copy when memory is already contiguous, leaving a dangling sip.voidptr.
    return np.array(rows[:, : width * 3].reshape(height, width, 3))
