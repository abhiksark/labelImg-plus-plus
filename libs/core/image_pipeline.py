"""Thread-safe image decode/annotation parse results and bounded frame cache."""

from collections import OrderedDict
from dataclasses import dataclass
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImageReader

from libs.formats import annotation_loader
from libs.formats.annotation_paths import find_existing_annotation
from libs.formats.labelFile import LabelFileFormat


MAX_DISPLAY_DIMENSION = 2048


@dataclass(frozen=True)
class ImageLoadResult:
    path: str
    image: object
    original_width: int
    original_height: int
    scale_factor: float
    image_format: object
    verified: bool
    annotation_path: object
    annotation_format: object
    shapes: tuple
    annotation_error: object
    annotation_fingerprint: object
    annotation_directory_fingerprints: tuple
    fingerprint: tuple

    @property
    def byte_size(self):
        try:
            return int(self.image.sizeInBytes())
        except AttributeError:  # Older Qt bindings.
            return int(self.image.byteCount())


def file_fingerprint(path):
    stat = os.stat(path)
    return (os.path.abspath(path), stat.st_mtime_ns, stat.st_size)


def _annotation_directories(path, save_dir):
    directories = []
    for directory in (
            save_dir,
            os.path.dirname(path),
            os.path.join(os.path.dirname(os.path.dirname(path)), 'labels')):
        if not directory:
            continue
        absolute = os.path.abspath(os.fspath(directory))
        if absolute not in directories:
            directories.append(absolute)
    return tuple(directories)


def _directory_fingerprints(directories):
    values = []
    for directory in directories:
        try:
            values.append((directory, os.stat(directory).st_mtime_ns))
        except OSError:
            values.append((directory, None))
    return tuple(values)


def _shared_annotation_path(path, save_dir, resolver):
    if resolver is not None:
        return resolver.named_file(path, 'annotations.json')
    for directory in _annotation_directories(path, save_dir)[:2]:
        candidate = os.path.join(directory, 'annotations.json')
        if os.path.isfile(candidate):
            return candidate
    return None


def _annotation_extensions(label_file_format):
    if label_file_format == LabelFileFormat.COCO:
        return ('.json', '.xml', '.txt')
    if label_file_format == LabelFileFormat.YOLO_SEG:
        return ('.txt', '.xml', '.json')
    return ('.xml', '.txt', '.json')


def _load_annotation(annotation_path, label_file_format, image_path, image,
                     original_size):
    extension = os.path.splitext(annotation_path)[1].lower()
    if extension == '.xml':
        loaded = annotation_loader.load_pascal_voc(annotation_path)
        annotation_format = LabelFileFormat.PASCAL_VOC
    elif extension == '.txt':
        if label_file_format == LabelFileFormat.YOLO_SEG:
            loaded = annotation_loader.load_yolo_seg(
                annotation_path, image, original_size)
            annotation_format = LabelFileFormat.YOLO_SEG
        else:
            loaded = annotation_loader.load_yolo(
                annotation_path, image, original_size)
            annotation_format = LabelFileFormat.YOLO
    elif label_file_format == LabelFileFormat.COCO:
        from libs.formats.annotation_probe import shared_json_cache
        loaded = annotation_loader.load_coco(
            annotation_path, image_path,
            data=shared_json_cache.get(annotation_path))
        annotation_format = LabelFileFormat.COCO
    else:
        from libs.formats.annotation_probe import shared_json_cache
        loaded = annotation_loader.load_create_ml(
            annotation_path, image_path,
            data=shared_json_cache.get(annotation_path))
        annotation_format = LabelFileFormat.CREATE_ML
    return tuple(loaded.shapes), bool(loaded.verified), annotation_format


def load_image_result(path, resolver=None, image_list=None, save_dir=None,
                      label_file_format=LabelFileFormat.PASCAL_VOC,
                      cancelled=None):
    """Decode an image and parse sidecars without constructing GUI objects."""
    path = os.path.abspath(os.fspath(path))
    if cancelled is not None and cancelled():
        return None
    fingerprint = file_fingerprint(path)
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    original_size = reader.size()
    if not original_size.isValid():
        raise ValueError('%s is not a valid image file' % path)
    if (original_size.width() > MAX_DISPLAY_DIMENSION
            or original_size.height() > MAX_DISPLAY_DIMENSION):
        scaled_size = original_size.scaled(
            MAX_DISPLAY_DIMENSION, MAX_DISPLAY_DIMENSION, Qt.KeepAspectRatio)
        reader.setScaledSize(scaled_size)
        scale_factor = scaled_size.width() / original_size.width()
    else:
        scale_factor = 1.0
    image_format = bytes(reader.format())
    image = reader.read()
    if image.isNull():
        raise ValueError('%s is not a valid image file' % path)
    if cancelled is not None and cancelled():
        return None

    annotation_path = find_existing_annotation(
        path, save_dir=save_dir, image_list=image_list,
        extensions=_annotation_extensions(label_file_format),
        resolver=resolver)
    if (annotation_path is None
            and label_file_format in (
                LabelFileFormat.CREATE_ML, LabelFileFormat.COCO)):
        annotation_path = _shared_annotation_path(path, save_dir, resolver)
    shapes = ()
    verified = False
    annotation_format = None
    annotation_error = None
    if annotation_path:
        try:
            shapes, verified, annotation_format = _load_annotation(
                annotation_path, label_file_format, path, image,
                original_size)
        except Exception as exc:
            annotation_error = str(exc)

    return ImageLoadResult(
        path=path,
        image=image,
        original_width=original_size.width(),
        original_height=original_size.height(),
        scale_factor=scale_factor,
        image_format=image_format,
        verified=verified,
        annotation_path=annotation_path,
        annotation_format=annotation_format,
        shapes=shapes,
        annotation_error=annotation_error,
        annotation_fingerprint=(
            file_fingerprint(annotation_path) if annotation_path else None),
        annotation_directory_fingerprints=_directory_fingerprints(
            _annotation_directories(path, save_dir)),
        fingerprint=fingerprint,
    )


class FrameCache:
    """Image/video LRU capped by both frame count and detached image bytes."""

    def __init__(self, max_images=5, max_bytes=128 * 1024 * 1024):
        self.max_images = max(1, int(max_images))
        self.max_bytes = max(1, int(max_bytes))
        self._entries = OrderedDict()
        self._bytes = 0

    @property
    def byte_size(self):
        return self._bytes

    def __len__(self):
        return len(self._entries)

    @staticmethod
    def _key(value):
        cache_key = getattr(value, 'cache_key', None)
        if cache_key is not None:
            return cache_key
        if hasattr(value, 'path'):
            return os.path.abspath(os.fspath(value.path))
        if isinstance(value, tuple) and value[:1] == ('video',):
            return value
        return os.path.abspath(os.fspath(value))

    def get(self, key):
        key = self._key(key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        # Video cache entries are session-scoped and cleared on document
        # replacement. Re-hashing multi-gigabyte media on every lookup would
        # defeat interactive seeks.
        if hasattr(entry, 'frame_ref'):
            self._entries.move_to_end(key)
            return entry
        path = entry.path
        try:
            if entry.fingerprint != file_fingerprint(path):
                self.remove(path)
                return None
            if (entry.annotation_path is not None
                    and entry.annotation_fingerprint
                    != file_fingerprint(entry.annotation_path)):
                self.remove(path)
                return None
            directories = tuple(
                directory
                for directory, _mtime
                in entry.annotation_directory_fingerprints)
            if (entry.annotation_directory_fingerprints
                    != _directory_fingerprints(directories)):
                self.remove(path)
                return None
        except OSError:
            self.remove(path)
            return None
        self._entries.move_to_end(key)
        return entry

    def put(self, result):
        key = self._key(result)
        self.remove(key)
        if result.byte_size > self.max_bytes:
            return
        self._entries[key] = result
        self._bytes += result.byte_size
        while (len(self._entries) > self.max_images
               or self._bytes > self.max_bytes):
            _path, evicted = self._entries.popitem(last=False)
            self._bytes -= evicted.byte_size

    def remove(self, key):
        entry = self._entries.pop(self._key(key), None)
        if entry is not None:
            self._bytes -= entry.byte_size

    def clear(self):
        self._entries.clear()
        self._bytes = 0

    def video_neighbor(self, frame_ref, direction):
        """Return the closest cached PTS before/after *frame_ref*."""
        direction = 1 if direction > 0 else -1
        candidates = []
        for entry in self._entries.values():
            other = getattr(entry, 'frame_ref', None)
            if other is None:
                continue
            if (other.fingerprint != frame_ref.fingerprint
                    or other.stream_index != frame_ref.stream_index):
                continue
            delta = other.pts - frame_ref.pts
            if delta * direction > 0:
                candidates.append((abs(delta), entry))
        return min(candidates, key=lambda item: item[0])[1] \
            if candidates else None
