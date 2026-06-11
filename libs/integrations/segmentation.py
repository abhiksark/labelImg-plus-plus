# libs/integrations/segmentation.py
"""Pluggable segmentation backend for SAM-assisted polygons.

Only OnnxSamBackend touches onnxruntime/numpy/cv2, and only inside its
methods, so importing this module stays cheap. sam_available() probes
importability without instantiating anything.
"""

import importlib.util
from abc import ABC, abstractmethod

_REQUIRED_MODULES = ("onnxruntime", "numpy", "cv2")


class SegmentationBackend(ABC):
    """Contract the app depends on, hiding all model-runtime specifics."""

    @abstractmethod
    def set_image(self, rgb):
        """Run the (expensive) image encoder on an (H, W, 3) uint8 RGB array."""

    @abstractmethod
    def predict(self, points, labels):
        """Given [(x, y), ...] and [1, ...], return an (H, W) bool mask."""

    @property
    @abstractmethod
    def model_loaded(self):
        """True once the model files are loaded into an inference session."""

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


class OnnxSamBackend(SegmentationBackend):
    """MobileSAM ONNX encoder/decoder pair behind SegmentationBackend.

    The encoder graph embeds preprocessing (normalize + pad), so set_image
    only resizes the longest side to TARGET_SIDE. The decoder was exported
    with return_single_mask, so predict needs no score argmax.
    """

    TARGET_SIDE = 1024

    def __init__(self, encoder_path, decoder_path):
        import onnxruntime as ort
        providers = ort.get_available_providers()
        self._encoder = ort.InferenceSession(encoder_path, providers=providers)
        self._decoder = ort.InferenceSession(decoder_path, providers=providers)
        self._embeddings = None
        self._orig_size = None      # (h, w) of the original image
        self._scale = None          # (sx, sy): resized / original
        self._model_loaded = True

    def set_image(self, rgb):
        import cv2
        import numpy as np
        h, w = rgb.shape[:2]
        scale = self.TARGET_SIDE / max(h, w)
        # Clamp so extreme aspect ratios (>1024:1) cannot round a side to 0,
        # which would crash cv2.resize with an opaque assertion.
        new_w = max(1, round(w * scale))
        new_h = max(1, round(h * scale))
        resized = cv2.resize(rgb, (new_w, new_h),
                             interpolation=cv2.INTER_LINEAR)
        self._embeddings = self._encoder.run(
            None, {"input_image": resized.astype(np.float32)})[0]
        self._orig_size = (h, w)
        self._scale = (new_w / w, new_h / h)

    def predict(self, points, labels):
        import numpy as np
        if self._embeddings is None:
            raise RuntimeError("set_image must be called before predict")
        sx, sy = self._scale
        # SAM's ONNX decoder wants a [0,0]/-1 padding point appended when no
        # box prompt is present, and coords in the resized-image frame.
        coords = [[x * sx, y * sy] for x, y in points] + [[0.0, 0.0]]
        marks = list(labels) + [-1]
        h, w = self._orig_size
        masks, _, _ = self._decoder.run(None, {
            "image_embeddings": self._embeddings,
            "point_coords": np.array([coords], dtype=np.float32),
            "point_labels": np.array([marks], dtype=np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), dtype=np.float32),
            "has_mask_input": np.zeros(1, dtype=np.float32),
            "orig_im_size": np.array([h, w], dtype=np.float32),
        })
        return masks[0, 0] > 0.0

    @property
    def model_loaded(self):
        return self._model_loaded

    @property
    def image_is_set(self):
        return self._embeddings is not None


def load_backend(settings):
    """Return (backend, None) on success or (None, error_message) on failure."""
    from libs.integrations.model_cache import resolve_models

    try:
        encoder_path, decoder_path = resolve_models(settings)
    except Exception as exc:  # network, SHA mismatch, disk, half-set pair
        return None, "Could not obtain the SAM model files: %s" % exc

    try:
        backend = OnnxSamBackend(encoder_path, decoder_path)
    except Exception as exc:  # corrupt file, unsupported opset
        return None, "Could not load the SAM model: %s" % exc
    return backend, None
