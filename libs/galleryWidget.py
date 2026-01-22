# libs/galleryWidget.py
"""Gallery view widget for image thumbnail display with annotation status."""

try:
    from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QImageReader, QIcon, QBrush, QPolygonF
    from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QTimer, QPointF
    from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                                  QListView, QSlider, QLabel)
except ImportError:
    from PyQt4.QtGui import (QPixmap, QImage, QPainter, QColor, QPen, QImageReader, QIcon, QBrush,
                              QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                              QListView, QSlider, QLabel, QPolygonF)
    from PyQt4.QtCore import Qt, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QPointF

import os
import hashlib
from collections import OrderedDict
from enum import IntEnum
try:
    from xml.etree import ElementTree
except ImportError:
    ElementTree = None


def generate_color_by_text(text):
    """Generate a consistent color based on text hash."""
    hash_val = int(hashlib.md5(text.encode('utf-8')).hexdigest()[:8], 16)
    r = (hash_val & 0xFF0000) >> 16
    g = (hash_val & 0x00FF00) >> 8
    b = hash_val & 0x0000FF
    # Ensure colors are bright enough
    r = max(100, r)
    g = max(100, g)
    b = max(100, b)
    return QColor(r, g, b)


def parse_yolo_annotations(txt_path, classes_path=None):
    """Parse YOLO format annotations.

    Returns list of (label, normalized_bbox) where bbox is (x_center, y_center, w, h).
    """
    annotations = []
    if not os.path.isfile(txt_path):
        return annotations

    # Load class names
    classes = []
    if classes_path and os.path.isfile(classes_path):
        with open(classes_path, 'r') as f:
            classes = [line.strip() for line in f if line.strip()]

    with open(txt_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 5:
                class_idx = int(parts[0])
                x_center = float(parts[1])
                y_center = float(parts[2])
                w = float(parts[3])
                h = float(parts[4])
                label = classes[class_idx] if class_idx < len(classes) else f"class_{class_idx}"
                annotations.append((label, (x_center, y_center, w, h)))
    return annotations


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


def find_annotation_file(image_path, save_dir=None):
    """Find annotation file for an image.

    Returns (annotation_path, format) or (None, None) if not found.
    Format is 'yolo', 'voc', or 'createml'.
    """
    base = os.path.splitext(os.path.basename(image_path))[0]
    img_dir = os.path.dirname(image_path)

    # Directories to search
    search_dirs = [img_dir]
    if save_dir and save_dir != img_dir:
        search_dirs.append(save_dir)

    # Check for YOLO format (.txt)
    for search_dir in search_dirs:
        txt_path = os.path.join(search_dir, base + '.txt')
        if os.path.isfile(txt_path):
            # Find classes.txt
            classes_path = os.path.join(search_dir, 'classes.txt')
            if not os.path.isfile(classes_path):
                classes_path = os.path.join(img_dir, 'classes.txt')
            return txt_path, 'yolo', classes_path if os.path.isfile(classes_path) else None

    # Check for Pascal VOC format (.xml)
    for search_dir in search_dirs:
        xml_path = os.path.join(search_dir, base + '.xml')
        if os.path.isfile(xml_path):
            return xml_path, 'voc', None

    return None, None, None


class AnnotationStatus(IntEnum):
    """Enum representing annotation status of an image."""
    NO_LABELS = 0      # Gray border
    HAS_LABELS = 1     # Blue border
    VERIFIED = 2       # Green border


class ThumbnailCache:
    """LRU cache for thumbnail images with O(1) operations using OrderedDict."""

    def __init__(self, max_size=200):
        self.max_size = max_size
        self._cache = OrderedDict()

    def get(self, path):
        """Retrieve thumbnail from cache (O(1) with LRU update)."""
        if path in self._cache:
            self._cache.move_to_end(path)  # O(1) instead of O(n)
            return self._cache[path]
        return None

    def put(self, path, pixmap):
        """Store thumbnail in cache with O(1) LRU eviction."""
        if path in self._cache:
            self._cache.move_to_end(path)  # O(1)
            self._cache[path] = pixmap
        else:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)  # O(1) eviction
            self._cache[path] = pixmap

    def clear(self):
        """Clear all cached thumbnails."""
        self._cache.clear()

    def remove(self, path):
        """Remove specific thumbnail from cache."""
        self._cache.pop(path, None)  # O(1)


class ThumbnailLoaderSignals(QObject):
    """Signals for async thumbnail loading."""
    thumbnail_ready = pyqtSignal(str, QImage)  # path, image


class ThumbnailLoaderWorker(QRunnable):
    """Worker for async thumbnail generation with annotation overlay."""

    def __init__(self, image_path, size=100, save_dir=None):
        super().__init__()
        self.image_path = image_path
        self.size = size
        self.save_dir = save_dir
        self.signals = ThumbnailLoaderSignals()

    def run(self):
        """Load, scale image, and draw annotations in background thread."""
        try:
            reader = QImageReader(self.image_path)
            reader.setAutoTransform(True)

            original_size = reader.size()
            if original_size.isValid():
                scaled_size = original_size.scaled(
                    self.size, self.size,
                    Qt.KeepAspectRatio
                )
                reader.setScaledSize(scaled_size)

            image = reader.read()
            if not image.isNull():
                # Draw annotations on thumbnail
                image = self._draw_annotations(image)
                self.signals.thumbnail_ready.emit(self.image_path, image)
        except Exception:
            pass

    def _draw_annotations(self, image):
        """Draw bounding boxes on the thumbnail image."""
        # Find annotation file
        ann_path, ann_format, classes_path = find_annotation_file(
            self.image_path, self.save_dir
        )
        if not ann_path:
            return image

        # Parse annotations
        if ann_format == 'yolo':
            annotations = parse_yolo_annotations(ann_path, classes_path)
        elif ann_format == 'voc':
            annotations = parse_voc_annotations(ann_path)
        else:
            return image

        if not annotations:
            return image

        # Draw on image
        img_w = image.width()
        img_h = image.height()

        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)

        for label, bbox in annotations:
            x_center, y_center, w, h = bbox

            # Convert normalized coords to pixel coords
            x1 = int((x_center - w / 2) * img_w)
            y1 = int((y_center - h / 2) * img_h)
            x2 = int((x_center + w / 2) * img_w)
            y2 = int((y_center + h / 2) * img_h)

            # Get color for this label
            color = generate_color_by_text(label)
            pen = QPen(color)
            pen.setWidth(2)
            painter.setPen(pen)

            # Draw rectangle
            painter.drawRect(x1, y1, x2 - x1, y2 - y1)

        painter.end()
        return image


class GalleryWidget(QWidget):
    """Gallery widget using QListWidget in IconMode for tiled layout."""

    image_selected = pyqtSignal(str)  # Single click
    image_activated = pyqtSignal(str)  # Double click

    DEFAULT_ICON_SIZE = 100
    MIN_ICON_SIZE = 40
    MAX_ICON_SIZE = 300

    STATUS_COLORS = {
        AnnotationStatus.NO_LABELS: QColor(150, 150, 150),     # Gray
        AnnotationStatus.HAS_LABELS: QColor(66, 133, 244),     # Blue
        AnnotationStatus.VERIFIED: QColor(52, 168, 83),        # Green
    }

    def __init__(self, parent=None, show_size_slider=False):
        super().__init__(parent)

        self._icon_size = self.DEFAULT_ICON_SIZE
        self._show_size_slider = show_size_slider
        self._save_dir = None  # Directory where annotations are saved

        self.thumbnail_cache = ThumbnailCache(max_size=300)
        self.thread_pool = QThreadPool.globalInstance()
        self.thread_pool.setMaxThreadCount(4)

        self._path_to_item = {}
        self._image_list = []
        self._loading_paths = set()
        self._statuses = {}
        self._loading_thumbnails = False  # Guard against re-entrant calls

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
        if self._show_size_slider:
            slider_layout = QHBoxLayout()
            slider_layout.setContentsMargins(10, 5, 10, 5)

            self.size_label = QLabel("Size:")
            slider_layout.addWidget(self.size_label)

            self.size_slider = QSlider(Qt.Horizontal)
            self.size_slider.setMinimum(self.MIN_ICON_SIZE)
            self.size_slider.setMaximum(self.MAX_ICON_SIZE)
            self.size_slider.setValue(self._icon_size)
            self.size_slider.setTickPosition(QSlider.TicksBelow)
            self.size_slider.setTickInterval(20)
            self.size_slider.valueChanged.connect(self._on_size_changed)
            slider_layout.addWidget(self.size_slider)

            self.size_value_label = QLabel(f"{self._icon_size}px")
            self.size_value_label.setMinimumWidth(45)
            slider_layout.addWidget(self.size_value_label)

            layout.addLayout(slider_layout)

        layout.addWidget(self.list_widget)

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
        # Clear cache and reload thumbnails at new size
        self.thumbnail_cache.clear()
        self._loading_paths.clear()
        self._reload_all_thumbnails()

    def _reload_all_thumbnails(self):
        """Reload all thumbnails at current size."""
        for path, item in self._path_to_item.items():
            # Set placeholder
            placeholder = QPixmap(self._icon_size, self._icon_size)
            placeholder.fill(QColor(220, 220, 220))
            item.setIcon(QIcon(placeholder))
            item.setSizeHint(QSize(self._icon_size + 20, self._icon_size + 40))
        self._load_visible_thumbnails()

    def set_image_list(self, image_paths):
        """Populate gallery with images."""
        self.clear()
        self._image_list = list(image_paths)

        for path in image_paths:
            self._add_item(path)

        # Defer thumbnail loading to next event loop cycle to prevent blocking
        QTimer.singleShot(0, self._load_visible_thumbnails)

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
        placeholder = QPixmap(self._icon_size, self._icon_size)
        placeholder.fill(QColor(220, 220, 220))
        item.setIcon(QIcon(placeholder))

        # Set initial status color (gray background)
        item.setBackground(QBrush(QColor(240, 240, 240)))

        # Store path in item's data
        item.setData(Qt.UserRole, image_path)

        self.list_widget.addItem(item)
        self._path_to_item[image_path] = item

    def _on_scroll(self):
        """Handle scroll to load visible thumbnails."""
        self._load_visible_thumbnails()

    def _load_visible_thumbnails(self):
        """Load thumbnails for visible items."""
        # Guard against re-entrant calls during layout/scroll cascades
        if self._loading_thumbnails:
            return
        self._loading_thumbnails = True
        try:
            viewport_rect = self.list_widget.viewport().rect()
            count = self.list_widget.count()

            for i in range(count):
                item = self.list_widget.item(i)
                item_rect = self.list_widget.visualItemRect(item)

                # Check if item is visible (with some buffer)
                if item_rect.intersects(viewport_rect.adjusted(0, -200, 0, 200)):
                    path = item.data(Qt.UserRole)
                    if path and path not in self._loading_paths:
                        cached = self.thumbnail_cache.get(path)
                        if cached:
                            self._set_item_icon(item, cached, path)
                        else:
                            self._load_thumbnail_async(path)
        finally:
            self._loading_thumbnails = False

    def _load_thumbnail_async(self, image_path):
        """Load thumbnail in background thread."""
        if image_path in self._loading_paths:
            return

        self._loading_paths.add(image_path)
        worker = ThumbnailLoaderWorker(image_path, self._icon_size, self._save_dir)
        worker.signals.thumbnail_ready.connect(self._on_thumbnail_loaded)
        self.thread_pool.start(worker)

    def _on_thumbnail_loaded(self, path, image):
        """Handle loaded thumbnail."""
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
        bordered.fill(self.STATUS_COLORS[status])

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
            # Load visible thumbnails once after scrolling
            self._load_visible_thumbnails()

    def update_status(self, image_path, status):
        """Update annotation status for an image."""
        self._statuses[image_path] = status

        if image_path in self._path_to_item:
            item = self._path_to_item[image_path]
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
                cached = self.thumbnail_cache.get(path)
                if cached:
                    self._set_item_icon(item, cached, path)

    def clear(self):
        """Clear all items."""
        self.list_widget.clear()
        self._path_to_item.clear()
        self._image_list.clear()
        self._loading_paths.clear()
        self._statuses.clear()

    def refresh_thumbnail(self, image_path):
        """Force reload of a specific thumbnail."""
        self.thumbnail_cache.remove(image_path)
        self._loading_paths.discard(image_path)
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
            self._reload_all_thumbnails()
