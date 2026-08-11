# libs/galleryWidget.py
"""Gallery view widget for image thumbnail display with annotation status."""

try:
    from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QImageReader, QIcon, QBrush, QPolygonF
    from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QTimer, QPoint, QPointF
    from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                                  QListView, QSlider, QLabel, QPushButton, QFrame)
except ImportError:
    from PyQt4.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QImageReader, QIcon, QBrush,
                              QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                              QListView, QSlider, QLabel, QPolygonF)
    from PyQt4.QtCore import Qt, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QPoint, QPointF

import hashlib
import json
import math
import os
from collections import namedtuple, OrderedDict
from enum import IntEnum
try:
    from xml.etree import ElementTree
except ImportError:
    ElementTree = None

from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_slider_style, get_gallery_controls_style, get_gallery_list_style
from libs.formats.annotation_paths import find_existing_annotation
from libs.formats.coco_io import COCOReader
from libs.formats.create_ml_io import CreateMLReader
from libs.formats.pascal_voc_io import PascalVocReader
from libs.core.profiling import hash_path, recorder as trace_recorder


OverlayShape = namedtuple('OverlayShape', ['label', 'shape_type', 'points'])

RECTANGLE = 'rectangle'
POLYGON = 'polygon'


def generate_color_by_text(text):
    """Generate a consistent color based on text hash."""
    hash_val = int(hashlib.sha256(text.encode('utf-8')).hexdigest()[:8], 16)
    r = (hash_val & 0xFF0000) >> 16
    g = (hash_val & 0x00FF00) >> 8
    b = hash_val & 0x0000FF
    # Ensure colors are bright enough
    r = max(100, r)
    g = max(100, g)
    b = max(100, b)
    return QColor(r, g, b)


def _read_classes(classes_path):
    """Return class names from ``classes.txt`` without surfacing I/O errors."""
    if not classes_path or not os.path.isfile(classes_path):
        return []
    try:
        with open(classes_path, 'r') as classes_file:
            return [line.strip() for line in classes_file if line.strip()]
    except (OSError, UnicodeError):
        return []


def _class_label(classes, class_token):
    """Resolve a non-negative YOLO class index, with the legacy fallback."""
    try:
        class_index = int(class_token)
    except (TypeError, ValueError):
        return None
    if class_index < 0:
        return None
    if class_index < len(classes):
        return classes[class_index]
    return 'class_{}'.format(class_index)


def _finite_floats(values):
    try:
        numbers = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in numbers):
        return None
    return numbers


def _image_dimensions(image_size):
    """Return a valid ``(width, height)`` pair from QSize or a tuple."""
    if image_size is None:
        return None
    try:
        if hasattr(image_size, 'width'):
            width = float(image_size.width())
            height = float(image_size.height())
        else:
            width = float(image_size[0])
            height = float(image_size[1])
    except (IndexError, TypeError, ValueError):
        return None
    if not math.isfinite(width) or not math.isfinite(height):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _normalized_overlay_shape(label, shape_type, points):
    """Validate an already-normalized overlay shape."""
    normalized = []
    for point in points:
        values = _finite_floats(point)
        if values is None or len(values) != 2:
            return None
        x, y = values
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            return None
        normalized.append((x, y))

    expected_points = 4 if shape_type == RECTANGLE else 3
    if len(normalized) < expected_points:
        return None
    return OverlayShape(str(label), shape_type, tuple(normalized))


def _pixel_overlay_shape(label, shape_type, points, image_size):
    """Normalize pixel coordinates against the source image dimensions."""
    dimensions = _image_dimensions(image_size)
    if dimensions is None:
        return None
    width, height = dimensions
    normalized = []
    for point in points:
        values = _finite_floats(point)
        if values is None or len(values) != 2:
            return None
        normalized.append((values[0] / width, values[1] / height))
    return _normalized_overlay_shape(label, shape_type, normalized)


def _rectangle_points(x_min, y_min, x_max, y_max):
    if x_max <= x_min or y_max <= y_min:
        return None
    return (
        (x_min, y_min),
        (x_max, y_min),
        (x_max, y_max),
        (x_min, y_max),
    )


def _parse_yolo_bbox(parts, classes):
    """Parse one exact five-field YOLO bounding-box line."""
    if len(parts) != 5:
        return None
    label = _class_label(classes, parts[0])
    values = _finite_floats(parts[1:])
    if label is None or values is None:
        return None
    x_center, y_center, width, height = values
    if not (0.0 <= x_center <= 1.0 and 0.0 <= y_center <= 1.0
            and 0.0 < width <= 1.0 and 0.0 < height <= 1.0):
        return None
    return label, values


def parse_yolo_annotations(txt_path, classes_path=None):
    """Parse YOLO format annotations.

    Returns list of (label, normalized_bbox) where bbox is (x_center, y_center, w, h).
    """
    annotations = []
    if not os.path.isfile(txt_path):
        return annotations

    classes = _read_classes(classes_path)

    try:
        with open(txt_path, 'r') as annotation_file:
            for line in annotation_file:
                parsed = _parse_yolo_bbox(line.strip().split(), classes)
                if parsed is not None:
                    annotations.append(parsed)
    except (OSError, UnicodeError):
        return []
    return annotations


def parse_yolo_overlay_shapes(txt_path, classes_path=None):
    """Parse YOLO boxes and YOLO-seg polygons as normalized overlay shapes."""
    if not os.path.isfile(txt_path):
        return []

    classes = _read_classes(classes_path)
    shapes = []
    try:
        with open(txt_path, 'r') as annotation_file:
            for line in annotation_file:
                parts = line.strip().split()
                bbox = _parse_yolo_bbox(parts, classes)
                if bbox is not None:
                    label, (x_center, y_center, width, height) = bbox
                    points = _rectangle_points(
                        max(0.0, x_center - width / 2),
                        max(0.0, y_center - height / 2),
                        min(1.0, x_center + width / 2),
                        min(1.0, y_center + height / 2),
                    )
                    shape = _normalized_overlay_shape(
                        label, RECTANGLE, points or ())
                    if shape is not None:
                        shapes.append(shape)
                    continue

                # YOLO segmentation is class + at least three x/y pairs.
                if len(parts) < 7 or (len(parts) - 1) % 2:
                    continue
                label = _class_label(classes, parts[0])
                coordinates = _finite_floats(parts[1:])
                if label is None or coordinates is None:
                    continue
                points = tuple(zip(coordinates[::2], coordinates[1::2]))
                shape = _normalized_overlay_shape(label, POLYGON, points)
                if shape is not None:
                    shapes.append(shape)
    except (OSError, UnicodeError):
        return []
    return shapes


def parse_voc_annotations(xml_path):
    """Parse Pascal VOC format annotations.

    Returns list of (label, normalized_bbox) where bbox is (x_center, y_center, w, h).
    """
    annotations = []
    if not os.path.isfile(xml_path) or ElementTree is None:
        return annotations

    try:
        tree = ElementTree.parse(xml_path)
        root = tree.getroot()

        # Get image size for normalization
        size_elem = root.find('size')
        if size_elem is None:
            return annotations
        img_w = int(size_elem.find('width').text)
        img_h = int(size_elem.find('height').text)

        if img_w <= 0 or img_h <= 0:
            return annotations

        for obj in root.iter('object'):
            label = obj.find('name').text
            bbox = obj.find('bndbox')
            xmin = float(bbox.find('xmin').text)
            ymin = float(bbox.find('ymin').text)
            xmax = float(bbox.find('xmax').text)
            ymax = float(bbox.find('ymax').text)

            # Convert to normalized center format
            x_center = (xmin + xmax) / 2 / img_w
            y_center = (ymin + ymax) / 2 / img_h
            w = (xmax - xmin) / img_w
            h = (ymax - ymin) / img_h
            annotations.append((label, (x_center, y_center, w, h)))
    except Exception:
        pass

    return annotations


def _voc_image_size(root):
    try:
        size_element = root.find('size')
        return (
            float(size_element.find('width').text),
            float(size_element.find('height').text),
        )
    except (AttributeError, TypeError, ValueError):
        return None


def parse_voc_overlay_shapes(xml_path, original_size=None):
    """Parse VOC rectangles and native polygons into normalized shapes."""
    if not os.path.isfile(xml_path):
        return []

    image_size = original_size
    if image_size is None and ElementTree is not None:
        try:
            image_size = _voc_image_size(
                ElementTree.parse(xml_path).getroot())
        except Exception:
            return []
    if _image_dimensions(image_size) is None:
        return []

    try:
        reader = PascalVocReader(xml_path)
    except Exception:
        return []

    shapes = []
    for reader_shape in reader.get_shapes():
        try:
            label, points = reader_shape[:2]
            shape_type = (
                reader_shape[5]
                if len(reader_shape) > 5
                and reader_shape[5] in (RECTANGLE, POLYGON)
                else RECTANGLE
            )
            shape = _pixel_overlay_shape(
                label, shape_type, points, image_size)
            if shape is not None:
                shapes.append(shape)
        except (IndexError, TypeError, ValueError):
            continue
    return shapes


def _load_json(json_path):
    try:
        with open(json_path, 'r') as annotation_file:
            return json.load(annotation_file)
    except (OSError, UnicodeError, ValueError):
        return None


def _json_annotation_format(data):
    if (isinstance(data, dict)
            and isinstance(data.get('images'), list)
            and isinstance(data.get('annotations'), list)):
        return 'coco'
    if isinstance(data, list):
        return 'createml'
    return None


def _matching_coco_image(images, image_path):
    """Select the requested COCO image without falling back to the first."""
    target_path = os.path.normcase(os.path.normpath(os.fspath(image_path)))
    target_path = target_path.replace('\\', '/')
    target_basename = os.path.basename(target_path)

    basename_matches = []
    for image in images:
        if not isinstance(image, dict):
            continue
        file_name = image.get('file_name')
        if not isinstance(file_name, str) or not file_name:
            continue
        normalized = os.path.normcase(os.path.normpath(file_name))
        normalized = normalized.replace('\\', '/')
        if normalized == target_path or target_path.endswith('/' + normalized):
            return image
        if os.path.basename(normalized) == target_basename:
            basename_matches.append(image)
    if len(basename_matches) == 1:
        return basename_matches[0]
    return None


def _parse_createml_overlay_shapes(json_path, image_path, original_size):
    if _image_dimensions(original_size) is None:
        return []

    try:
        reader = CreateMLReader(json_path, image_path)
    except Exception:
        return []

    shapes = []
    for reader_shape in reader.get_shapes():
        try:
            label, points = reader_shape[:2]
            shape = _pixel_overlay_shape(
                label, RECTANGLE, points, original_size)
            if shape is not None:
                shapes.append(shape)
        except (IndexError, TypeError, ValueError):
            continue
    return shapes


def _parse_coco_overlay_shapes(data, json_path, image_path, original_size):
    target = _matching_coco_image(data.get('images', []), image_path)
    if target is None:
        return []
    image_size = original_size or (
        target.get('width'), target.get('height'))
    if _image_dimensions(image_size) is None:
        return []

    target_filename = target.get('file_name')
    try:
        reader = COCOReader(json_path, target_filename)
    except Exception:
        return []

    shapes = []
    for reader_shape in reader.get_shapes():
        try:
            label, points = reader_shape[:2]
            shape_type = (
                reader_shape[5]
                if len(reader_shape) > 5
                and reader_shape[5] in (RECTANGLE, POLYGON)
                else RECTANGLE
            )
            shape = _pixel_overlay_shape(
                label, shape_type, points, image_size)
            if shape is not None:
                shapes.append(shape)
        except (IndexError, TypeError, ValueError):
            continue
    return shapes


def parse_json_overlay_shapes(json_path, image_path, original_size=None):
    """Parse CreateML or COCO JSON, selecting only ``image_path``."""
    data = _load_json(json_path)
    annotation_format = _json_annotation_format(data)
    if annotation_format == 'createml':
        return _parse_createml_overlay_shapes(
            json_path, image_path, original_size)
    if annotation_format == 'coco':
        return _parse_coco_overlay_shapes(
            data, json_path, image_path, original_size)
    return []


def parse_overlay_annotations(annotation_path, annotation_format, image_path,
                              original_size=None, classes_path=None):
    """Return normalized shapes for any gallery-supported annotation file."""
    if annotation_format in ('yolo', 'yolo_seg'):
        return parse_yolo_overlay_shapes(annotation_path, classes_path)
    if annotation_format == 'voc':
        return parse_voc_overlay_shapes(annotation_path, original_size)
    if annotation_format in ('createml', 'coco'):
        return parse_json_overlay_shapes(
            annotation_path, image_path, original_size)
    return []


def _txt_annotation_format(txt_path):
    """Detect whether a TXT sidecar contains YOLO boxes or polygons."""
    try:
        with open(txt_path, 'r') as annotation_file:
            for line in annotation_file:
                parts = line.strip().split()
                if len(parts) < 7 or (len(parts) - 1) % 2:
                    continue
                if (_class_label([], parts[0]) is not None
                        and _finite_floats(parts[1:]) is not None):
                    return 'yolo_seg'
    except (OSError, UnicodeError):
        pass
    return 'yolo'


def _find_classes_file(annotation_path, image_dir):
    annotation_dir = os.path.dirname(annotation_path)
    directories = [annotation_dir, os.path.dirname(annotation_dir), image_dir]
    seen = set()
    for directory in directories:
        identity = os.path.normcase(os.path.abspath(directory or os.curdir))
        if identity in seen:
            continue
        seen.add(identity)
        candidate = os.path.join(directory, 'classes.txt')
        if os.path.isfile(candidate):
            return candidate
    return None


def find_annotation_file(image_path, save_dir=None, image_list=None,
                         resolver=None):
    """Find annotation file for an image.

    Returns (annotation_path, format, classes_path) or three ``None`` values.
    Format is 'yolo', 'yolo_seg', 'voc', 'createml', or 'coco'.
    """
    img_dir = os.path.dirname(image_path)

    annotation_path = find_existing_annotation(
        image_path,
        save_dir=save_dir,
        image_list=image_list,
        extensions=('.txt', '.xml', '.json'),
        resolver=resolver,
    )
    if not annotation_path:
        search_directories = []
        if save_dir:
            search_directories.append(os.fspath(save_dir))
        if img_dir not in search_directories:
            search_directories.append(img_dir)
        if resolver is not None:
            annotation_path = resolver.named_file(
                image_path, 'annotations.json')
        else:
            for directory in search_directories:
                candidate = os.path.join(directory, 'annotations.json')
                if os.path.isfile(candidate):
                    annotation_path = candidate
                    break
    if not annotation_path:
        return None, None, None

    extension = os.path.splitext(annotation_path)[1].lower()
    if extension == '.txt':
        return (
            annotation_path,
            _txt_annotation_format(annotation_path),
            _find_classes_file(annotation_path, img_dir),
        )
    if extension == '.xml':
        return annotation_path, 'voc', None
    if extension == '.json':
        annotation_format = _json_annotation_format(
            _load_json(annotation_path))
        return annotation_path, annotation_format, None

    return None, None, None


class AnnotationStatus(IntEnum):
    """Enum representing annotation status of an image."""
    NO_LABELS = 0      # Gray border
    HAS_LABELS = 1     # Blue border
    VERIFIED = 2       # Green border


class ThumbnailCache:
    """LRU cache for thumbnail images with O(1) operations using OrderedDict."""

    def __init__(self, max_size=200, max_bytes=16 * 1024 * 1024):
        self.max_size = max_size
        self.max_bytes = max(0, int(max_bytes))
        self._cache = OrderedDict()
        self._sizes = {}
        self._bytes = 0

    @staticmethod
    def _pixmap_bytes(pixmap):
        try:
            return max(0, pixmap.width()) * max(0, pixmap.height()) * 4
        except (AttributeError, TypeError):
            return 0

    @property
    def bytes_used(self):
        return self._bytes

    def get(self, path):
        """Retrieve thumbnail from cache (O(1) with LRU update)."""
        if path in self._cache:
            self._cache.move_to_end(path)  # O(1) instead of O(n)
            return self._cache[path]
        return None

    def put(self, path, pixmap):
        """Store thumbnail in cache with O(1) LRU eviction."""
        size = self._pixmap_bytes(pixmap)
        if path in self._cache:
            self._bytes -= self._sizes.pop(path, 0)
            self._cache.move_to_end(path)  # O(1)
            self._cache[path] = pixmap
        else:
            self._cache[path] = pixmap
        self._sizes[path] = size
        self._bytes += size
        while (len(self._cache) > self.max_size
               or (self.max_bytes and self._bytes > self.max_bytes)):
            evicted_path, _pixmap = self._cache.popitem(last=False)
            self._bytes -= self._sizes.pop(evicted_path, 0)

    def clear(self):
        """Clear all cached thumbnails."""
        self._cache.clear()
        self._sizes.clear()
        self._bytes = 0

    def remove(self, path):
        """Remove specific thumbnail from cache."""
        if self._cache.pop(path, None) is not None:
            self._bytes -= self._sizes.pop(path, 0)


class ThumbnailLoaderSignals(QObject):
    """Signals for async thumbnail loading."""
    thumbnail_ready = pyqtSignal(str, QImage)  # path, image


class ThumbnailLoaderWorker(QRunnable):
    """Worker for async thumbnail generation with annotation overlay."""

    def __init__(self, image_path, size=100, save_dir=None, image_list=None,
                 resolver=None):
        super().__init__()
        self.image_path = image_path
        self.size = size
        self.save_dir = save_dir
        self.image_list = list(image_list) if image_list is not None else None
        self.resolver = resolver
        self.signals = ThumbnailLoaderSignals()

    def run(self):
        """Load, scale image, and draw annotations in background thread."""
        try:
            image = self.load()
            if image is not None and not image.isNull():
                self.signals.thumbnail_ready.emit(self.image_path, image)
        except Exception:
            pass

    def load(self):
        """Return the worker-safe QImage, leaving QPixmap creation to the UI."""
        trace_started = None
        if trace_recorder is not None:
            import time
            trace_started = time.perf_counter_ns()
        try:
            return self._load_image()
        finally:
            if trace_recorder is not None:
                trace_recorder.complete(
                    'thumbnail.load', trace_started,
                    args={'path': hash_path(self.image_path)})

    def _load_image(self):
        reader = QImageReader(self.image_path)
        reader.setAutoTransform(True)

        original_size = reader.size()
        if original_size.isValid():
            scaled_size = original_size.scaled(
                self.size, self.size, Qt.KeepAspectRatio)
            reader.setScaledSize(scaled_size)

        image = reader.read()
        if image.isNull():
            return None
        source_size = (
            original_size if original_size.isValid()
            else QSize(image.width(), image.height()))
        return self._draw_annotations(image, source_size)

    def _draw_annotations(self, image, original_size=None):
        """Draw normalized annotation shapes on the thumbnail image."""
        # Find annotation file
        if self.resolver is None:
            ann_path, ann_format, classes_path = find_annotation_file(
                self.image_path, self.save_dir, self.image_list)
        else:
            ann_path, ann_format, classes_path = find_annotation_file(
                self.image_path, self.save_dir, self.image_list,
                resolver=self.resolver)
        if not ann_path:
            return image

        try:
            annotations = parse_overlay_annotations(
                ann_path,
                ann_format,
                self.image_path,
                original_size=original_size,
                classes_path=classes_path,
            )
        except Exception:
            return image

        if not annotations:
            return image

        # Draw on image
        img_w = image.width()
        img_h = image.height()

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        # Corner marker length (proportional to image size)
        corner_len = max(4, min(img_w, img_h) // 8)

        try:
            for shape in annotations:
                color = generate_color_by_text(shape.label)
                pen = QPen(color)
                pen.setWidth(2)
                painter.setPen(pen)

                points = [
                    QPointF(x * img_w, y * img_h)
                    for x, y in shape.points
                ]
                if shape.shape_type == POLYGON:
                    painter.drawPolygon(QPolygonF(points))
                    continue

                x_values = [point.x() for point in points]
                y_values = [point.y() for point in points]
                x1, x2 = int(min(x_values)), int(max(x_values))
                y1, y2 = int(min(y_values)), int(max(y_values))
                box_w = x2 - x1
                box_h = y2 - y1
                c = min(corner_len, box_w // 3, box_h // 3)

                if c >= 2:
                    painter.drawLine(x1, y1, x1 + c, y1)
                    painter.drawLine(x1, y1, x1, y1 + c)
                    painter.drawLine(x2, y1, x2 - c, y1)
                    painter.drawLine(x2, y1, x2, y1 + c)
                    painter.drawLine(x1, y2, x1 + c, y2)
                    painter.drawLine(x1, y2, x1, y2 - c)
                    painter.drawLine(x2, y2, x2 - c, y2)
                    painter.drawLine(x2, y2, x2, y2 - c)
                else:
                    painter.drawRect(x1, y1, box_w, box_h)
        finally:
            painter.end()
        return image


class GalleryWidget(QWidget):
    """Gallery widget using QListWidget in IconMode for tiled layout."""

    image_selected = pyqtSignal(str)  # Single click
    image_activated = pyqtSignal(str)  # Double click

    DEFAULT_ICON_SIZE = 100
    MIN_ICON_SIZE = 40
    MAX_ICON_SIZE = 300

    def __init__(self, parent=None, show_size_slider=False,
                 coordinator=None):
        super().__init__(parent)

        self._icon_size = self.DEFAULT_ICON_SIZE
        self._show_size_slider = show_size_slider
        self._save_dir = None  # Directory where annotations are saved
        self._coordinator = coordinator
        self._resolver = None

        self.thumbnail_cache = ThumbnailCache(max_size=300)
        self.thread_pool = (coordinator.pool('background')
                            if coordinator is not None else QThreadPool())
        if coordinator is None:
            self.thread_pool.setMaxThreadCount(4)

        self._path_to_item = {}
        self._image_list = []
        self._pending_paths = []  # For batched item creation
        self._batch_id = 0  # For cancelling pending batch callbacks
        self._loading_paths = set()
        self._thumbnail_request_serial = 0
        self._active_thumbnail_requests = {}
        self._thumbnail_handles = {}
        self._statuses = {}
        # Keep the status selection when the gallery is repopulated. Statuses
        # arrive asynchronously after a directory reload, so filtered views
        # hide an item until its status is known instead of briefly showing it
        # in the wrong result set.
        self._status_filter = 0
        self._loading_thumbnails = False  # Guard against re-entrant calls
        self._thumbnail_load_pending = False  # Debounce flag

        # Theme colors cache for placeholders and item backgrounds
        self._placeholder_color = QColor(220, 220, 220)  # Default light
        self._item_bg_color = QColor(240, 240, 240)      # Default light
        self._placeholder_icon_key = None
        self._placeholder_icon_value = None

        # Status border colors (defaults, updated by theme)
        self._status_colors = {
            AnnotationStatus.NO_LABELS: QColor(150, 150, 150),
            AnnotationStatus.HAS_LABELS: QColor(66, 133, 244),
            AnnotationStatus.VERIFIED: QColor(52, 168, 83),
        }

        self._setup_ui()

    def _setup_ui(self):
        """Initialize UI components."""
        self.list_widget = QListWidget(self)
        self.list_widget.setViewMode(QListView.IconMode)
        self._apply_icon_size()
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setWrapping(True)
        self.list_widget.setSpacing(5)
        self.list_widget.setMovement(QListView.Static)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setWordWrap(True)

        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_widget.verticalScrollBar().valueChanged.connect(self._on_scroll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add size slider if enabled
        self._current_theme = Theme.LIGHT
        self._slider_frame = None
        self._preset_buttons = []

        if self._show_size_slider:
            # Container frame for better visual grouping
            self._slider_frame = QFrame()
            self._slider_frame.setAutoFillBackground(True)  # Required for stylesheet bg
            slider_layout = QHBoxLayout(self._slider_frame)
            slider_layout.setContentsMargins(10, 8, 10, 8)
            slider_layout.setSpacing(8)

            # Preset size buttons
            self.size_presets = {
                'S': 60,
                'M': 100,
                'L': 150,
                'XL': 220
            }
            for label, size in self.size_presets.items():
                btn = QPushButton(label)
                btn.setFixedSize(scale_px(32), scale_px(26))
                btn.setAutoFillBackground(True)  # Required for stylesheet bg
                btn.clicked.connect(lambda checked, s=size: self._set_preset_size(s))
                slider_layout.addWidget(btn)
                self._preset_buttons.append(btn)

            slider_layout.addSpacing(10)

            # Size slider
            self.size_slider = QSlider(Qt.Horizontal)
            self.size_slider.setMinimum(self.MIN_ICON_SIZE)
            self.size_slider.setMaximum(self.MAX_ICON_SIZE)
            self.size_slider.setValue(self._icon_size)
            self.size_slider.valueChanged.connect(self._on_size_changed)
            slider_layout.addWidget(self.size_slider, 1)

            # Size value display
            self.size_value_label = QLabel(f"{self._icon_size}px")
            self.size_value_label.setMinimumWidth(scale_px(50))
            slider_layout.addWidget(self.size_value_label)

            layout.addWidget(self._slider_frame)

        layout.addWidget(self.list_widget)

        # Theme the gallery regardless of whether the size slider is shown,
        # otherwise the list widget and status/placeholder colors keep their
        # light-mode defaults under the dark theme.
        self.apply_theme(self._current_theme)

    def _apply_icon_size(self):
        """Apply current icon size to list widget."""
        grid_size = self._icon_size + 20
        self.list_widget.setIconSize(QSize(self._icon_size, self._icon_size))
        self.list_widget.setGridSize(QSize(grid_size, grid_size + 20))

    def _on_size_changed(self, value):
        """Handle size slider change."""
        self._icon_size = value
        if hasattr(self, 'size_value_label'):
            self.size_value_label.setText(f"{value}px")
        self._apply_icon_size()
        self._placeholder_icon_key = None
        # Clear cache and reload thumbnails at new size
        self.thumbnail_cache.clear()
        self._loading_paths.clear()
        self._active_thumbnail_requests.clear()
        self._reload_all_thumbnails()

    def _set_preset_size(self, size):
        """Set thumbnail size from preset button."""
        if hasattr(self, 'size_slider'):
            self.size_slider.setValue(size)
        else:
            self._on_size_changed(size)

    def apply_theme(self, theme):
        """Apply theme to gallery slider controls and list widget."""
        self._current_theme = theme

        # Cache theme colors for use in thumbnail loading
        from libs.utils.styles import get_theme_colors, hex_to_qcolor
        colors = get_theme_colors(theme)

        self._placeholder_color = hex_to_qcolor(colors['placeholder'])
        self._item_bg_color = hex_to_qcolor(colors['item_bg'])
        self._placeholder_icon_key = None

        # Update status border colors
        self._status_colors[AnnotationStatus.NO_LABELS] = hex_to_qcolor(colors['status_no_labels'])
        self._status_colors[AnnotationStatus.HAS_LABELS] = hex_to_qcolor(colors['status_has_labels'])
        self._status_colors[AnnotationStatus.VERIFIED] = hex_to_qcolor(colors['status_verified'])

        if self._slider_frame:
            styles = get_gallery_controls_style(theme)
            self._slider_frame.setStyleSheet(styles['frame'])
            for btn in self._preset_buttons:
                btn.setStyleSheet(styles['button'])
            if hasattr(self, 'size_value_label'):
                self.size_value_label.setStyleSheet(styles['label'])
        if hasattr(self, 'size_slider'):
            self.size_slider.setStyleSheet(get_slider_style(theme))
        # Style the list widget for proper text colors
        if hasattr(self, 'list_widget'):
            self.list_widget.setStyleSheet(get_gallery_list_style(theme))

    def _reload_all_thumbnails(self):
        """Reload all thumbnails at current size."""
        placeholder_icon = self._placeholder_icon()
        for path, item in self._path_to_item.items():
            item.setIcon(placeholder_icon)
            item.setSizeHint(QSize(self._icon_size + 20, self._icon_size + 40))
        self._load_visible_thumbnails()

    def _placeholder_icon(self):
        """Return one implicitly-shared placeholder for every unloaded item."""
        key = (self._icon_size, self._placeholder_color.rgba())
        if self._placeholder_icon_key != key:
            placeholder = QPixmap(self._icon_size, self._icon_size)
            placeholder.fill(self._placeholder_color)
            self._placeholder_icon_value = QIcon(placeholder)
            self._placeholder_icon_key = key
        return self._placeholder_icon_value

    def set_image_list(self, image_paths):
        """Populate gallery with images using batched creation."""
        self.clear()
        self._image_list = list(image_paths)
        self._pending_paths = list(image_paths)
        # Start batched item creation with current batch_id
        current_batch = self._batch_id
        self._add_items_batch(current_batch)

    def set_dataset_snapshot(self, snapshot):
        """Use a precomputed resolver for all subsequent thumbnail work."""
        self._resolver = snapshot.resolver if snapshot is not None else None
        self.set_save_dir(snapshot.save_dir if snapshot is not None else None)
        self.set_image_list(snapshot.image_paths if snapshot is not None else ())

    def set_annotation_resolver(self, resolver):
        self._resolver = resolver

    def set_task_coordinator(self, coordinator):
        self._coordinator = coordinator
        self.thread_pool = coordinator.pool('background')

    def _add_items_batch(self, batch_id, batch_size=100):
        """Add items in batches to prevent UI freeze."""
        # Ignore stale callbacks from old batches
        if batch_id != self._batch_id:
            return

        if not self._pending_paths:
            # All items added, now load visible thumbnails
            QTimer.singleShot(0, lambda bid=batch_id: self._load_visible_thumbnails(bid))
            return

        batch = self._pending_paths[:batch_size]
        self._pending_paths = self._pending_paths[batch_size:]

        for path in batch:
            self._add_item(path)

        # Schedule next batch if more items remain
        if self._pending_paths:
            QTimer.singleShot(0, lambda bid=batch_id: self._add_items_batch(bid))
        else:
            QTimer.singleShot(0, lambda bid=batch_id: self._load_visible_thumbnails(bid))

    def _add_item(self, image_path):
        """Add an item to the list widget."""
        filename = os.path.basename(image_path)
        if len(filename) > 12:
            display_name = filename[:10] + "..."
        else:
            display_name = filename

        item = QListWidgetItem(display_name)
        item.setToolTip(filename)
        grid_size = self._icon_size + 20
        item.setSizeHint(QSize(grid_size, grid_size + 20))

        # Set placeholder icon
        item.setIcon(self._placeholder_icon())

        # Set initial status color (gray background)
        item.setBackground(QBrush(self._item_bg_color))

        # Store path in item's data
        item.setData(Qt.UserRole, image_path)

        self.list_widget.addItem(item)
        self._path_to_item[image_path] = item
        self._update_item_filter_visibility(image_path)

    def _schedule_thumbnail_load(self, delay_ms=100):
        """Debounced thumbnail loading - prevents flooding during rapid navigation."""
        if self._thumbnail_load_pending:
            return  # Already scheduled
        self._thumbnail_load_pending = True
        batch_id = self._batch_id
        QTimer.singleShot(delay_ms, lambda bid=batch_id: self._do_scheduled_thumbnail_load(bid))

    def _do_scheduled_thumbnail_load(self, batch_id):
        """Execute the scheduled thumbnail load."""
        self._thumbnail_load_pending = False
        self._load_visible_thumbnails(batch_id)

    def _on_scroll(self):
        """Handle scroll to load visible thumbnails."""
        self._schedule_thumbnail_load(200)  # 200ms debounce for scroll (Bug 8 fix)

    def _load_visible_thumbnails(self, batch_id=None):
        """Load thumbnails for visible items."""
        # Ignore stale callbacks from old batches
        if batch_id is not None and batch_id != self._batch_id:
            return
        # Guard against re-entrant calls during layout/scroll cascades
        if self._loading_thumbnails:
            return
        self._loading_thumbnails = True
        try:
            items = self._visible_items_with_margin()
            desired = {
                item.data(Qt.UserRole) for item in items
                if item.data(Qt.UserRole)
            }
            # Queued work outside the viewport is no longer useful. Running
            # decodes are cooperatively invalidated and their results dropped.
            for path, handle in list(self._thumbnail_handles.items()):
                if path not in desired:
                    handle.cancel()
                    self._thumbnail_handles.pop(path, None)
                    self._loading_paths.discard(path)
                    self._active_thumbnail_requests.pop(path, None)

            for item in items:
                path = item.data(Qt.UserRole)
                if path and path not in self._loading_paths:
                    cached = self.thumbnail_cache.get(path)
                    if cached:
                        self._set_item_icon(item, cached, path)
                    else:
                        self._load_thumbnail_async(path)
        finally:
            self._loading_thumbnails = False

    def _visible_items_with_margin(self):
        """Return viewport items plus one grid row without scanning all rows."""
        count = self.list_widget.count()
        if not count:
            return []
        viewport = self.list_widget.viewport().rect()
        grid = self.list_widget.gridSize()
        step_x = max(1, grid.width())
        step_y = max(1, grid.height())
        visible_rows = set()
        for y in range(0, viewport.height() + step_y, step_y):
            for x in range(0, viewport.width() + step_x, step_x):
                item = self.list_widget.itemAt(QPoint(
                    min(x + step_x // 2, max(0, viewport.width() - 1)),
                    min(y + step_y // 2, max(0, viewport.height() - 1))))
                if item is not None:
                    visible_rows.add(self.list_widget.row(item))
        if not visible_rows:
            current = self.list_widget.currentRow()
            visible_rows.add(max(0, current))
        columns = max(1, viewport.width() // step_x)
        first = max(0, min(visible_rows) - columns)
        last = min(count, max(visible_rows) + columns + 1)
        # The scheduler is deliberately bounded even for pathological layouts.
        return [
            self.list_widget.item(row)
            for row in range(first, min(last, first + 512))
            if not self.list_widget.item(row).isHidden()
        ]

    def _load_thumbnail_async(self, image_path):
        """Load thumbnail in background thread."""
        if image_path in self._loading_paths:
            return

        self._loading_paths.add(image_path)
        self._thumbnail_request_serial += 1
        request_id = self._thumbnail_request_serial
        self._active_thumbnail_requests[image_path] = request_id
        if self._resolver is None:
            worker = ThumbnailLoaderWorker(
                image_path, self._icon_size, self._save_dir,
                self._image_list)
        else:
            worker = ThumbnailLoaderWorker(
                image_path, self._icon_size, self._save_dir,
                self._image_list, resolver=self._resolver)
        if self._coordinator is None:
            worker.signals.thumbnail_ready.connect(
                lambda path, image, rid=request_id:
                self._on_thumbnail_loaded(path, image, rid))
            self.thread_pool.start(worker)
            return
        if self._coordinator.is_shutting_down:
            self._loading_paths.discard(image_path)
            self._active_thumbnail_requests.pop(image_path, None)
            return

        handle = self._coordinator.submit(
            'background', lambda job: worker.load(),
            priority=10, key='thumbnail:' + image_path, latest=True)
        self._thumbnail_handles[image_path] = handle
        handle.result.connect(
            lambda image, path=image_path, rid=request_id:
            self._on_thumbnail_loaded(path, image, rid)
            if image is not None else None)
        handle.finished.connect(
            lambda path=image_path, rid=request_id:
            self._on_thumbnail_finished(path, rid))

    def _on_thumbnail_finished(self, path, request_id):
        if self._active_thumbnail_requests.get(path) == request_id:
            self._thumbnail_handles.pop(path, None)
            if path in self._loading_paths and path not in self.thumbnail_cache._cache:
                self._loading_paths.discard(path)
                self._active_thumbnail_requests.pop(path, None)

    def _on_thumbnail_loaded(self, path, image, request_id=None):
        """Handle loaded thumbnail."""
        if (request_id is not None
                and self._active_thumbnail_requests.get(path) != request_id):
            return

        self._active_thumbnail_requests.pop(path, None)
        self._thumbnail_handles.pop(path, None)
        self._loading_paths.discard(path)
        pixmap = QPixmap.fromImage(image)
        self.thumbnail_cache.put(path, pixmap)

        if path in self._path_to_item:
            item = self._path_to_item[path]
            self._set_item_icon(item, pixmap, path)

    def _set_item_icon(self, item, pixmap, path):
        """Set icon with status border."""
        status = self._statuses.get(path, AnnotationStatus.NO_LABELS)
        bordered_pixmap = self._add_status_border(pixmap, status)
        item.setIcon(QIcon(bordered_pixmap))

    def _add_status_border(self, pixmap, status):
        """Add colored border to pixmap based on status."""
        border_width = 4
        new_size = self._icon_size + border_width * 2

        bordered = QPixmap(new_size, new_size)
        bordered.fill(self._status_colors[status])

        painter = QPainter(bordered)
        # Center the original pixmap
        x = border_width + (self._icon_size - pixmap.width()) // 2
        y = border_width + (self._icon_size - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)
        painter.end()

        return bordered

    def _on_item_clicked(self, item):
        """Handle item click."""
        path = item.data(Qt.UserRole)
        if path:
            self.image_selected.emit(path)

    def _on_item_double_clicked(self, item):
        """Handle item double-click."""
        path = item.data(Qt.UserRole)
        if path:
            self.image_activated.emit(path)

    def select_image(self, image_path):
        """Select the specified image."""
        if image_path in self._path_to_item:
            item = self._path_to_item[image_path]
            self.list_widget.setCurrentItem(item)
            # Block scroll signals to prevent cascade during programmatic scroll
            scrollbar = self.list_widget.verticalScrollBar()
            scrollbar.blockSignals(True)
            self.list_widget.scrollToItem(item)
            scrollbar.blockSignals(False)
            # Debounced thumbnail loading - prevents flooding during rapid navigation
            self._schedule_thumbnail_load()

    def update_status(self, image_path, status):
        """Update annotation status for an image."""
        self._statuses[image_path] = status

        if image_path in self._path_to_item:
            item = self._path_to_item[image_path]
            self._update_item_filter_visibility(image_path)
            # Reload icon with new border color
            cached = self.thumbnail_cache.get(image_path)
            if cached:
                self._set_item_icon(item, cached, image_path)

    def update_all_statuses(self, statuses):
        """Batch update annotation statuses."""
        self._statuses.update(statuses)
        for path, status in statuses.items():
            if path in self._path_to_item:
                item = self._path_to_item[path]
                self._update_item_filter_visibility(path)
                cached = self.thumbnail_cache.get(path)
                if cached:
                    self._set_item_icon(item, cached, path)

    def set_status_filter(self, index):
        """Filter thumbnails using the main-window status combo contract.

        ``0`` shows all images, ``1`` shows annotated images (including
        verified), ``2`` shows verified images, and ``3`` shows unannotated
        images. In filtered views, images with an as-yet unknown asynchronous
        status stay hidden until a status update arrives.
        """
        if index not in (0, 1, 2, 3):
            raise ValueError('unknown gallery status filter: {}'.format(index))
        self._status_filter = index
        for path in self._path_to_item:
            self._update_item_filter_visibility(path)
        self._load_visible_thumbnails()

    def _update_item_filter_visibility(self, image_path):
        """Re-evaluate one thumbnail against the active status filter."""
        item = self._path_to_item.get(image_path)
        if item is None:
            return

        status = self._statuses.get(image_path)
        if self._status_filter == 0:
            visible = True
        elif status is None:
            visible = False
        elif self._status_filter == 1:
            visible = status in (
                AnnotationStatus.HAS_LABELS, AnnotationStatus.VERIFIED)
        elif self._status_filter == 2:
            visible = status == AnnotationStatus.VERIFIED
        else:
            visible = status == AnnotationStatus.NO_LABELS
        item.setHidden(not visible)

    def clear(self):
        """Clear all items."""
        self._batch_id += 1  # Invalidate pending batch callbacks
        self._pending_paths = []  # Stop batched creation
        self.list_widget.clear()
        self._path_to_item.clear()
        self._image_list.clear()
        self._loading_paths.clear()
        self._active_thumbnail_requests.clear()
        for handle in self._thumbnail_handles.values():
            handle.cancel()
        self._thumbnail_handles.clear()
        self._statuses.clear()

    def refresh_thumbnail(self, image_path):
        """Force reload of a specific thumbnail."""
        self.thumbnail_cache.remove(image_path)
        self._loading_paths.discard(image_path)
        self._active_thumbnail_requests.pop(image_path, None)
        handle = self._thumbnail_handles.pop(image_path, None)
        if handle is not None:
            handle.cancel()
        self._load_thumbnail_async(image_path)

    def showEvent(self, event):
        """Load visible thumbnails when widget becomes visible."""
        super().showEvent(event)
        # Defer to prevent blocking during rapid show/hide
        QTimer.singleShot(10, self._load_visible_thumbnails)

    def resizeEvent(self, event):
        """Handle resize."""
        super().resizeEvent(event)
        # Defer to prevent blocking during resize cascade
        QTimer.singleShot(10, self._load_visible_thumbnails)

    def set_save_dir(self, save_dir):
        """Set the annotation save directory.

        When changed, clears the cache to reload thumbnails with annotations.
        """
        if self._save_dir != save_dir:
            self._save_dir = save_dir
            # Clear cache so thumbnails reload with annotations
            self.thumbnail_cache.clear()
            self._loading_paths.clear()
            self._active_thumbnail_requests.clear()
            self._reload_all_thumbnails()
