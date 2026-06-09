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


class SamBackend(SegmentationBackend):
    """MobileSAM / SAM image predictor wrapped behind SegmentationBackend.

    torch and mobile_sam are imported lazily inside __init__ so importing this
    module never pulls the ML stack.
    """

    def __init__(self, checkpoint, model_type="vit_t", device="cpu"):
        import torch
        from mobile_sam import SamPredictor, sam_model_registry

        self.device_warning = None
        # Only "cuda" gets a runtime probe; other strings (e.g. "mps") are left
        # to raise naturally inside .to(device) and surface via load_backend.
        if device == "cuda" and not torch.cuda.is_available():
            device = "cpu"
            self.device_warning = "CUDA not available; falling back to CPU."

        sam = sam_model_registry[model_type](checkpoint=checkpoint)
        sam.to(device=device)
        sam.eval()
        self._predictor = SamPredictor(sam)
        self._model_loaded = True
        self._image_set = False

    def set_image(self, rgb):
        self._predictor.set_image(rgb)
        self._image_set = True

    def predict(self, points, labels):
        import numpy as np
        coords = np.array(points, dtype=np.float32)
        marks = np.array(labels, dtype=np.int64)   # SAM's documented label dtype
        masks, scores, _ = self._predictor.predict(
            point_coords=coords, point_labels=marks, multimask_output=True)
        best = int(scores.argmax())
        return masks[best].astype(bool)

    @property
    def model_loaded(self):
        return self._model_loaded

    @property
    def image_is_set(self):
        return self._image_set


def load_backend(settings):
    """Return (backend, None) on success or (None, error_message) on failure."""
    from libs.utils.constants import (
        SETTING_SAM_DEVICE, SETTING_SAM_MODEL_TYPE)
    from libs.integrations.model_cache import resolve_checkpoint

    try:
        checkpoint = resolve_checkpoint(settings)
    except Exception as exc:  # network, SHA mismatch, disk
        return None, "Could not obtain a SAM checkpoint: %s" % exc

    model_type = settings.get(SETTING_SAM_MODEL_TYPE, "vit_t")
    device = settings.get(SETTING_SAM_DEVICE, "cpu")
    try:
        backend = SamBackend(checkpoint, model_type=model_type, device=device)
    except Exception as exc:  # corrupt file, OOM, bad model_type
        return None, "Could not load the SAM model: %s" % exc
    return backend, None
