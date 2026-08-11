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
import threading
from collections import OrderedDict

from libs.formats.create_ml_io import JSON_EXT
from libs.formats.pascal_voc_io import PascalVocReader, XML_EXT
from libs.formats.yolo_io import YoloReader
from libs.formats.annotation_paths import find_existing_annotation

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


def _resolve(image_path, save_dir, image_list=None, resolver=None):
    """Return (path, fmt) for the first matching annotation, or (None, None)."""
    dirs = _search_dirs(image_path, save_dir)

    path = find_existing_annotation(
        image_path,
        save_dir=save_dir,
        image_list=image_list,
        extensions=(XML_EXT, TXT_EXT, JSON_EXT),
        resolver=resolver,
    )
    if path:
        extension = os.path.splitext(path)[1].lower()
        if extension == XML_EXT:
            return path, 'voc'
        if extension == TXT_EXT:
            return path, 'yolo'
        return path, 'json'

    txt = None
    if not txt:
        # Standard YOLO layout: <parent-of-image-dir>/labels/<base>.txt
        basename = os.path.splitext(os.path.basename(image_path))[0]
        img_dir = os.path.dirname(image_path)
        sibling = os.path.join(os.path.dirname(img_dir), 'labels',
                               basename + TXT_EXT)
        if resolver is not None:
            txt = resolver.conventional_yolo_path(image_path)
        elif os.path.isfile(sibling):
            txt = sibling
    if txt:
        return txt, 'yolo'

    coco_json = (resolver.named_file(image_path, COCO_JSON_NAME)
                 if resolver is not None
                 else _first_existing(dirs, COCO_JSON_NAME))
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


class SharedJsonCache:
    """Fingerprint-keyed LRU for shared COCO/CreateML catalog reads."""

    def __init__(self, max_size=8):
        self.max_size = max(1, int(max_size))
        self._cache = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def fingerprint(path):
        stat = os.stat(path)
        return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)

    def _get_entry(self, path):
        fingerprint = self.fingerprint(path)
        with self._lock:
            cached = self._cache.get(fingerprint)
            if cached is not None:
                self._cache.move_to_end(fingerprint)
                return cached
            with open(path, 'r') as json_file:
                data = json.load(json_file)
            entry = (data, _build_shared_json_index(data))
            # Remove old fingerprints of the same path during invalidation.
            for key in list(self._cache):
                if key[0] == fingerprint[0] and key != fingerprint:
                    self._cache.pop(key, None)
            self._cache[fingerprint] = entry
            self._cache.move_to_end(fingerprint)
            while len(self._cache) > self.max_size:
                self._cache.popitem(last=False)
        return entry

    def get(self, path):
        return self._get_entry(path)[0]

    def get_index(self, path):
        return self._get_entry(path)[1]

    def invalidate(self, path=None):
        with self._lock:
            if path is None:
                self._cache.clear()
                return
            target = os.path.abspath(path)
            for key in list(self._cache):
                if key[0] == target:
                    self._cache.pop(key, None)


shared_json_cache = SharedJsonCache()


def _build_shared_json_index(data):
    """Build constant-time per-image lookups for one shared JSON document."""
    if _is_coco(data):
        categories = {
            entry.get('id'): entry.get('name', 'unknown')
            for entry in data.get('categories', [])
            if isinstance(entry, dict)
        }
        labels_by_image_id = {}
        for annotation in data.get('annotations', []):
            if not isinstance(annotation, dict):
                continue
            image_id = annotation.get('image_id')
            category_id = annotation.get('category_id')
            if image_id is None or category_id is None:
                continue
            labels_by_image_id.setdefault(image_id, []).append(
                categories.get(category_id, 'unknown'))
        by_name = {}
        for image in data.get('images', []):
            if not isinstance(image, dict):
                continue
            filename = image.get('file_name')
            if not filename:
                continue
            labels = tuple(labels_by_image_id.get(image.get('id'), ()))
            normalized = str(filename).replace('\\', '/')
            by_name.setdefault(normalized, labels)
            by_name.setdefault(os.path.basename(normalized), labels)
        return 'coco', by_name

    by_name = {}
    if isinstance(data, list):
        for image in data:
            if not isinstance(image, dict) or not image.get('image'):
                continue
            labels = tuple(
                annotation.get('label')
                for annotation in image.get('annotations', [])
                if isinstance(annotation, dict)
                and annotation.get('label') is not None
            )
            value = (labels, bool(image.get('verified', False)))
            normalized = str(image['image']).replace('\\', '/')
            by_name.setdefault(normalized, value)
            by_name.setdefault(os.path.basename(normalized), value)
    return 'createml', by_name


def _read_json(path, image_path, json_cache=None):
    """Return (fmt, has_labels, verified, labels) for a CreateML or COCO file."""
    if json_cache is not None:
        data = json_cache.get(path)
        indexed_format, by_name = json_cache.get_index(path)
        relative_name = os.path.relpath(
            image_path, os.path.dirname(path)).replace(os.sep, '/')
        image_name = relative_name if relative_name in by_name else \
            os.path.basename(image_path)
        if indexed_format == 'coco':
            labels = list(by_name.get(image_name, ()))
            return 'coco', bool(labels), False, labels
        value = by_name.get(image_name)
        if value is None:
            return 'createml', False, False, []
        labels, verified = value
        labels = list(labels)
        return 'createml', bool(labels), verified, labels
    else:
        with open(path, 'r') as f:
            data = json.load(f)

    if _is_coco(data):
        target_name = os.path.basename(image_path)
        image = next(
            (entry for entry in data.get('images', [])
             if isinstance(entry, dict)
             and entry.get('file_name') == target_name),
            None)
        image_id = image.get('id') if image else None
        categories = {
            entry.get('id'): entry.get('name', 'unknown')
            for entry in data.get('categories', [])
            if isinstance(entry, dict)
        }
        labels = [
            categories.get(annotation.get('category_id'), 'unknown')
            for annotation in data.get('annotations', [])
            if isinstance(annotation, dict)
            and image_id is not None
            and annotation.get('image_id') == image_id
            and annotation.get('category_id') is not None
        ]
        return 'coco', bool(labels), False, labels  # COCO has no verified flag

    # CreateML: a list of image objects, possibly sharing one file.
    if not isinstance(data, list):
        raise ValueError('CreateML annotation file must be a JSON array')
    target_name = os.path.basename(image_path)
    image = next(
        (entry for entry in data
         if isinstance(entry, dict) and entry.get('image') == target_name),
        None)
    if image is None:
        return 'createml', False, False, []
    labels = [
        annotation.get('label')
        for annotation in image.get('annotations', [])
        if isinstance(annotation, dict) and annotation.get('label') is not None
    ]
    return 'createml', bool(labels), bool(image.get('verified', False)), labels


def probe(image_path, save_dir=None, want_labels=False, image_list=None,
          resolver=None, json_cache=None):
    """Resolve and read an image's annotation.

    Args:
        image_path: Path to the image file.
        save_dir: Optional directory annotations are saved to.
        want_labels: When True, read label names (a full read for YOLO);
            when False, labels may be left empty for cheaper status-only scans.
        image_list: Optional active dataset paths used to disambiguate
            recursively discovered images with the same basename.

    Returns:
        An :class:`AnnotationInfo`.
    """
    path, fmt = _resolve(
        image_path, save_dir, image_list=image_list, resolver=resolver)
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
                _read_json(path, image_path, json_cache=json_cache)
    except Exception:
        # Malformed annotation: report "no labels" rather than crashing the
        # caller (gallery scan, stats worker). Format-level readers already
        # surface hard errors when a file is opened explicitly.
        pass
    return info
