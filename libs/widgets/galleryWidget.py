# libs/galleryWidget.py
"""Gallery view widget for image thumbnail display with annotation status."""

try:
    from PyQt5.QtGui import QPixmap, QImage, QPainter, QColor, QPen, QImageReader, QIcon, QBrush, QPolygonF
    from PyQt5.QtCore import Qt, QSize, QObject, pyqtSignal, QRunnable, QThreadPool, QTimer, QPointF
    from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                                  QListView, QSlider, QLabel, QPushButton, QFrame)
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
    hash_val = int(hashlib.sha256(text.encode('utf-8')).hexdigest()[:8], 16)
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

        # Corner marker length (proportional to image size)
        corner_len = max(4, min(img_w, img_h) // 8)

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

            # Draw corner markers instead of full rectangle (less cluttered)
            box_w = x2 - x1
            box_h = y2 - y1
            c = min(corner_len, box_w // 3, box_h // 3)  # Adjust corner size for small boxes

            if c >= 2:
                # Top-left corner
                painter.drawLine(x1, y1, x1 + c, y1)
                painter.drawLine(x1, y1, x1, y1 + c)
                # Top-right corner
                painter.drawLine(x2, y1, x2 - c, y1)
                painter.drawLine(x2, y1, x2, y1 + c)
                # Bottom-left corner
                painter.drawLine(x1, y2, x1 + c, y2)
                painter.drawLine(x1, y2, x1, y2 - c)
                # Bottom-right corner
                painter.drawLine(x2, y2, x2 - c, y2)
                painter.drawLine(x2, y2, x2, y2 - c)
            else:
                # Box too small, draw simple rectangle
                painter.drawRect(x1, y1, box_w, box_h)

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
        self._pending_paths = []  # For batched item creation
        self._batch_id = 0  # For cancelling pending batch callbacks
        self._loading_paths = set()
        self._statuses = {}
        self._loading_thumbnails = False  # Guard against re-entrant calls
        self._thumbnail_load_pending = False  # Debounce flag

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
            # Container frame for better visual grouping
            slider_frame = QFrame()
            slider_frame.setStyleSheet("""
                QFrame {
                    background-color: #f5f5f5;
                    border-bottom: 1px solid #ddd;
                }
            """)
            slider_layout = QHBoxLayout(slider_frame)
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
                btn.setFixedSize(32, 26)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #fff;
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        font-weight: bold;
                        font-size: 11px;
                    }
                    QPushButton:hover {
                        background-color: #e8e8e8;
                        border-color: #999;
                    }
                    QPushButton:pressed {
                        background-color: #ddd;
                    }
                """)
                btn.clicked.connect(lambda checked, s=size: self._set_preset_size(s))
                slider_layout.addWidget(btn)

            slider_layout.addSpacing(10)

            # Size slider
            self.size_slider = QSlider(Qt.Horizontal)
            self.size_slider.setMinimum(self.MIN_ICON_SIZE)
            self.size_slider.setMaximum(self.MAX_ICON_SIZE)
            self.size_slider.setValue(self._icon_size)
            self.size_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    height: 6px;
                    background: #ddd;
                    border-radius: 3px;
                }
                QSlider::handle:horizontal {
                    background: #4285f4;
                    width: 16px;
                    height: 16px;
                    margin: -5px 0;
                    border-radius: 8px;
                }
                QSlider::handle:horizontal:hover {
                    background: #3367d6;
                }
                QSlider::sub-page:horizontal {
                    background: #4285f4;
                    border-radius: 3px;
                }
            """)
            self.size_slider.valueChanged.connect(self._on_size_changed)
            slider_layout.addWidget(self.size_slider, 1)

            # Size value display
            self.size_value_label = QLabel(f"{self._icon_size}px")
            self.size_value_label.setMinimumWidth(50)
            self.size_value_label.setStyleSheet("font-weight: bold; color: #333;")
            slider_layout.addWidget(self.size_value_label)

            layout.addWidget(slider_frame)

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

    def _set_preset_size(self, size):
        """Set thumbnail size from preset button."""
        if hasattr(self, 'size_slider'):
            self.size_slider.setValue(size)
        else:
            self._on_size_changed(size)

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
        """Populate gallery with images using batched creation."""
        self.clear()
        self._image_list = list(image_paths)
        self._pending_paths = list(image_paths)
        # Start batched item creation with current batch_id
        current_batch = self._batch_id
        self._add_items_batch(current_batch)

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
        placeholder = QPixmap(self._icon_size, self._icon_size)
        placeholder.fill(QColor(220, 220, 220))
        item.setIcon(QIcon(placeholder))

        # Set initial status color (gray background)
        item.setBackground(QBrush(QColor(240, 240, 240)))

        # Store path in item's data
        item.setData(Qt.UserRole, image_path)

        self.list_widget.addItem(item)
        self._path_to_item[image_path] = item

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
            # Debounced thumbnail loading - prevents flooding during rapid navigation
            self._schedule_thumbnail_load()

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
        self._batch_id += 1  # Invalidate pending batch callbacks
        self._pending_paths = []  # Stop batched creation
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
