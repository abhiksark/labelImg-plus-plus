# libs/formats/annotation_probe.py
"""Single source of truth for resolving an image's annotation file and
reading its status and labels.

This logic was previously duplicated across the statistics worker, the
status-refresh worker, and two MainWindow methods, and the copies had drifted:
the status checks only looked at ``annotations.json`` while label extraction
only looked at a per-image ``<base>.json``, so the gallery and the statistics
view could disagree about whether an image was annotated. This module unifies
the resolution so every caller agrees.

Resolution order (first match wins), searched in both ``save_dir`` and the
image's own directory:

    PASCAL VOC  <base>.xml
    YOLO        <base>.txt   (also a ``labels/`` sibling folder)
    JSON        <base>.json  then  annotations.json
                (auto-detected as COCO or CreateML by structure)
"""
import json
import os

from libs.formats.create_ml_io import CreateMLReader, JSON_EXT
from libs.formats.coco_io import COCOReader
from libs.formats.pascal_voc_io import PascalVocReader, XML_EXT
from libs.formats.yolo_io import YoloReader

try:
    from PyQt5.QtGui import QImageReader
except ImportError:  # pragma: no cover - legacy Qt4 fallback
    from PyQt4.QtGui import QImageReader

TXT_EXT = '.txt'
COCO_JSON_NAME = 'annotations.json'


class _MockImage:
    """Minimal image stand-in exposing the dimensions ``YoloReader`` needs."""

    def __init__(self, width, height, grayscale=False):
        self._w, self._h, self._gray = width, height, grayscale

    def width(self):
        return self._w

    def height(self):
        return self._h

    def isGrayscale(self):
        return self._gray


class AnnotationInfo:
    """Result of probing an image for its annotation."""

    def __init__(self, path=None, fmt=None, has_labels=False,
                 verified=False, labels=None):
        self.path = path           # annotation file path, or None
        self.fmt = fmt             # 'voc' | 'yolo' | 'createml' | 'coco' | None
        self.has_labels = has_labels
        self.verified = verified
        self.labels = labels if labels is not None else []


def _search_dirs(image_path, save_dir):
    dirs = []
    if save_dir:
        dirs.append(save_dir)
    img_dir = os.path.dirname(image_path)
    if img_dir and img_dir not in dirs:
        dirs.append(img_dir)
    return dirs


def _first_existing(dirs, name):
    for d in dirs:
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path
    return None


def _resolve(image_path, save_dir):
    """Return (path, fmt) for the first matching annotation, or (None, None)."""
    basename = os.path.splitext(os.path.basename(image_path))[0]
    dirs = _search_dirs(image_path, save_dir)

    xml = _first_existing(dirs, basename + XML_EXT)
    if xml:
        return xml, 'voc'

    txt = _first_existing(dirs, basename + TXT_EXT)
    if not txt:
        # Standard YOLO layout: <parent-of-image-dir>/labels/<base>.txt
        img_dir = os.path.dirname(image_path)
        sibling = os.path.join(os.path.dirname(img_dir), 'labels',
                               basename + TXT_EXT)
        if os.path.isfile(sibling):
            txt = sibling
    if txt:
        return txt, 'yolo'

    base_json = _first_existing(dirs, basename + JSON_EXT)
    if base_json:
        return base_json, 'json'

    coco_json = _first_existing(dirs, COCO_JSON_NAME)
    if coco_json:
        return coco_json, 'json'

    return None, None


def _yolo_classes_path(txt_path):
    """Find classes.txt next to the annotations, then one directory up."""
    txt_dir = os.path.dirname(txt_path)
    candidate = os.path.join(txt_dir, 'classes.txt')
    if os.path.isfile(candidate):
        return candidate
    candidate = os.path.join(os.path.dirname(txt_dir), 'classes.txt')
    if os.path.isfile(candidate):
        return candidate
    return None


def _read_yolo_labels(image_path, txt_path):
    classes_path = _yolo_classes_path(txt_path)
    if not classes_path:
        return []
    reader = QImageReader(image_path)
    size = reader.size()
    if not size.isValid():
        return []
    mock = _MockImage(size.width(), size.height())
    shapes = YoloReader(txt_path, mock, classes_path).get_shapes()
    return [shape[0] for shape in shapes]


def _is_coco(data):
    return (isinstance(data, dict)
            and 'annotations' in data and 'images' in data)


def _read_json(path, image_path):
    """Return (fmt, has_labels, verified, labels) for a CreateML or COCO file."""
    with open(path, 'r') as f:
        data = json.load(f)

    if _is_coco(data):
        shapes = COCOReader(path, os.path.basename(image_path)).get_shapes()
        labels = [shape[0] for shape in shapes]
        return 'coco', bool(labels), False, labels  # COCO has no verified flag

    # CreateML: a list of image objects, possibly sharing one file.
    reader = CreateMLReader(path, image_path)
    shapes = reader.get_shapes()
    labels = [shape[0] for shape in shapes]
    return 'createml', bool(labels), bool(reader.verified), labels


def probe(image_path, save_dir=None, want_labels=False):
    """Resolve and read an image's annotation.

    Args:
        image_path: Path to the image file.
        save_dir: Optional directory annotations are saved to.
        want_labels: When True, read label names (a full read for YOLO);
            when False, labels may be left empty for cheaper status-only scans.

    Returns:
        An :class:`AnnotationInfo`.
    """
    path, fmt = _resolve(image_path, save_dir)
    info = AnnotationInfo(path=path, fmt=fmt)
    if not path:
        return info

    try:
        if fmt == 'voc':
            reader = PascalVocReader(path)
            shapes = reader.get_shapes()
            info.labels = [shape[0] for shape in shapes]
            info.has_labels = len(shapes) > 0
            info.verified = reader.verified
        elif fmt == 'yolo':
            info.has_labels = os.path.getsize(path) > 0
            if want_labels and info.has_labels:
                info.labels = _read_yolo_labels(image_path, path)
        else:  # 'json' - CreateML or COCO, auto-detected
            info.fmt, info.has_labels, info.verified, info.labels = \
                _read_json(path, image_path)
    except Exception:
        # Malformed annotation: report "no labels" rather than crashing the
        # caller (gallery scan, stats worker). Format-level readers already
        # surface hard errors when a file is opened explicitly.
        pass
    return info
