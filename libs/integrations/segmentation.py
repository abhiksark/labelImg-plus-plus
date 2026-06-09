# libs/integrations/segmentation.py
"""Pluggable segmentation backend for SAM-assisted polygons.

Only SamBackend touches torch, and only inside its methods, so importing this
module stays cheap. sam_available() probes importability without instantiating.
"""

import importlib.util
from abc import ABC, abstractmethod

_REQUIRED_MODULES = ("torch", "numpy", "cv2", "mobile_sam")


class SegmentationBackend(ABC):
    """Contract the app depends on, hiding all SAM/torch specifics."""

    @abstractmethod
    def set_image(self, rgb):
        """Run the (expensive) image encoder on an (H, W, 3) uint8 RGB array."""

    @abstractmethod
    def predict(self, points, labels):
        """Given [(x, y), ...] and [1, ...], return an (H, W) bool mask."""

    @property
    @abstractmethod
    def model_loaded(self):
        """True once the checkpoint is loaded onto the device."""

    @property
    @abstractmethod
    def image_is_set(self):
        """True once an embedding exists for the current image."""


def sam_available():
    """True only if every module the [sam] extra provides is importable."""
    return all(
        importlib.util.find_spec(name) is not None
        for name in _REQUIRED_MODULES
    )
