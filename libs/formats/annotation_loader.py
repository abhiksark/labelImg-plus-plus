# libs/formats/annotation_loader.py
"""Format-agnostic annotation loading.

Pulls the per-format reader glue out of ``MainWindow`` so it can be unit
tested without a Qt main window. Each loader builds the appropriate reader
and returns a :class:`LoadedAnnotation`; the caller is responsible for the UI
side effects (selecting the format, populating the label list, propagating the
``verified`` flag, and surfacing errors).

The YOLO loaders accept an ``original_image_size`` so normalized coordinates
convert against the source image's dimensions rather than a downscaled display
image (Issue #31).
"""
import os
from collections import namedtuple

from libs.formats.pascal_voc_io import PascalVocReader
from libs.formats.yolo_io import YoloReader
from libs.formats.yolo_seg_io import YOLOSegReader
from libs.formats.create_ml_io import CreateMLReader
from libs.formats.coco_io import COCOReader

LoadedAnnotation = namedtuple('LoadedAnnotation', ['shapes', 'verified'])


class _ImageSizeAdapter:
    """Minimal stand-in exposing the ``width``/``height``/``isGrayscale`` API
    the YOLO readers expect, backed by an explicit (original) image size.

    Lets normalized coordinates convert against the source dimensions even when
    the live display image has been scaled.
    """

    def __init__(self, size, grayscale=False):
        self._size = size
        self._grayscale = grayscale

    def width(self):
        return self._size.width()

    def height(self):
        return self._size.height()

    def isGrayscale(self):
        return self._grayscale


def _yolo_image(image, original_image_size):
    """Return the image object the YOLO readers should measure against.

    Prefers ``original_image_size`` (wrapped in an adapter) when available,
    falling back to the live ``image``.
    """
    if original_image_size is not None:
        grayscale = image.isGrayscale() if image is not None else False
        return _ImageSizeAdapter(original_image_size, grayscale)
    return image


def load_pascal_voc(xml_path):
    """Load a PASCAL VOC ``.xml`` annotation file."""
    reader = PascalVocReader(xml_path)
    return LoadedAnnotation(reader.get_shapes(), reader.verified)


def load_yolo(txt_path, image, original_image_size=None):
    """Load a YOLO ``.txt`` annotation file (needs a sibling ``classes.txt``)."""
    reader = YoloReader(txt_path, _yolo_image(image, original_image_size))
    return LoadedAnnotation(reader.get_shapes(), reader.verified)


def load_yolo_seg(txt_path, image, original_image_size=None):
    """Load a YOLO segmentation ``.txt`` annotation file."""
    reader = YOLOSegReader(txt_path, _yolo_image(image, original_image_size))
    return LoadedAnnotation(reader.get_shapes(), reader.verified)


def load_create_ml(json_path, image_path):
    """Load a CreateML ``.json`` annotation file for ``image_path``."""
    reader = CreateMLReader(json_path, image_path)
    return LoadedAnnotation(reader.get_shapes(), reader.verified)


def load_coco(json_path, image_path):
    """Load a COCO ``.json`` annotation file, matching by image basename."""
    reader = COCOReader(json_path, os.path.basename(image_path))
    return LoadedAnnotation(reader.get_shapes(), reader.verified)
