#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import codecs
import os.path
import platform
import shutil
import sys
import webbrowser as wb
from functools import partial

try:
    from PyQt5.QtGui import QColor, QCursor, QImage, QImageReader, QPixmap
    from PyQt5.QtCore import (
        Qt, QByteArray, QFileInfo, QProcess, QSize, QTimer, QPoint, QPointF,
        QVariant, QObject, QRunnable, QThreadPool, pyqtSignal
    )
    from PyQt5.QtWidgets import (
        QAction, QActionGroup, QApplication, QCheckBox, QComboBox,
        QDialog, QDockWidget, QFileDialog, QHBoxLayout, QLabel,
        QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
        QProgressDialog, QScrollArea, QTabWidget, QToolButton,
        QVBoxLayout, QWidget, QWidgetAction
    )
except ImportError:
    # needed for py3+qt4
    # Ref:
    # http://pyqt.sourceforge.net/Docs/PyQt4/incompatible_apis.html
    # http://stackoverflow.com/questions/21217399/pyqt4-qtcore-qvariant-object-instead-of-a-string
    if sys.version_info.major >= 3:
        import sip
        sip.setapi('QVariant', 2)
    from PyQt4.QtGui import (
        QColor, QCursor, QImage, QImageReader, QPixmap,
        QAction, QActionGroup, QApplication, QCheckBox, QDockWidget,
        QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
        QMainWindow, QMenu, QMessageBox, QProgressDialog, QScrollArea,
        QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction
    )
    from PyQt4.QtCore import (
        Qt, QByteArray, QFileInfo, QProcess, QSize, QTimer, QPoint, QPointF,
        QVariant, QObject, QRunnable, QThreadPool, pyqtSignal
    )

# Widgets
from libs.widgets.combobox import ComboBox
from libs.widgets.default_label_combobox import DefaultLabelComboBox
from libs.widgets.canvas import Canvas
from libs.widgets.zoomWidget import ZoomWidget
from libs.widgets.lightWidget import LightWidget
from libs.widgets.labelDialog import LabelDialog
from libs.widgets.colorDialog import ColorDialog
from libs.widgets.toolBar import ToolBar, DropdownToolButton
from libs.widgets.galleryWidget import GalleryWidget, AnnotationStatus
from libs.widgets.statsWidget import StatsWidget
from libs.widgets.labelCheckerDialog import LabelCheckerDialog
from libs.widgets.keypointPanel import KeypointPanel
from libs.widgets import view_scaling
from libs.widgets.stats_controller import StatsController

# Core
from libs.core.shape import Shape, ShapeType, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.core.settings import Settings
from libs.core.commands import (
    UndoStack, CreateShapeCommand, DeleteShapeCommand, MoveShapeCommand,
    EditLabelCommand, EditPolygonVerticesCommand, EditKeypointsCommand,
)
from libs.core.shortcut_config import ShortcutConfig

# Formats
from libs.formats.labelFile import LabelFile, LabelFileError, LabelFileFormat
from libs.formats.pascal_voc_io import PascalVocReader, XML_EXT
from libs.formats.yolo_io import TXT_EXT
from libs.formats.create_ml_io import JSON_EXT
from libs.formats.annotation_probe import probe as probe_annotation
from libs.formats import annotation_loader

# Utils
from libs.utils.constants import (
    SETTING_ADVANCE_MODE, SETTING_AUTO_SAVE, SETTING_AUTO_SAVE_ENABLED,
    SETTING_AUTO_SAVE_INTERVAL, SETTING_DARK_MODE, SETTING_DRAW_SQUARE,
    SETTING_EDGE_ALIGNMENT, SETTING_FILENAME, SETTING_FILL_COLOR,
    SETTING_GALLERY_MODE, SETTING_GRID_ENABLED, SETTING_GRID_SIZE,
    SETTING_ICON_SIZE, SETTING_LABEL_FILE_FORMAT, SETTING_LAST_OPEN_DIR,
    SETTING_LINE_COLOR, SETTING_LOCK_ON_VERIFY, SETTING_PAINT_LABEL,
    SETTING_RECENT_FILES, SETTING_SAVE_DIR, SETTING_SHORTCUTS,
    SETTING_SINGLE_CLASS,
    SETTING_TOOLBAR_EXPANDED, SETTING_WIN_POSE, SETTING_WIN_SIZE,
    SETTING_WIN_STATE, FORMAT_PASCALVOC, FORMAT_YOLO, FORMAT_CREATEML,
    FORMAT_COCO, FORMAT_YOLO_SEG
)
from libs.utils.utils import (
    new_icon, themed_icon, new_action, add_actions, format_shortcut, Struct,
    generate_color_by_text, have_qstring, natural_sort
)
from libs.utils.stringBundle import StringBundle
from libs.utils.styles import get_combined_style, Theme, get_stylesheet, get_canvas_background
from libs.utils.ustr import ustr
from libs.utils.hashableQListWidgetItem import HashableQListWidgetItem

# Resources
from libs.resources import *

__appname__ = 'labelImgPlusPlus'


class WindowMixin(object):

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            add_actions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName(u'%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            add_actions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar


def _probe_status(image_path, save_dir):
    """Map the shared annotation probe to an AnnotationStatus enum value."""
    info = probe_annotation(image_path, save_dir)
    if info.verified:
        return AnnotationStatus.VERIFIED
    if info.has_labels:
        return AnnotationStatus.HAS_LABELS
    return AnnotationStatus.NO_LABELS


class StatisticsWorkerSignals(QObject):
    """Thread-safe signals for statistics worker."""
    progress = pyqtSignal(int, int, int, dict)  # total, annotated, verified, label_counts
    finished = pyqtSignal()
    error = pyqtSignal(str)  # Error reporting


class StatisticsWorker(QRunnable):
    """Thread-safe worker for background statistics computation."""

    def __init__(self, image_list, save_dir=None):
        super().__init__()
        self.setAutoDelete(True)  # Explicit cleanup by Qt

        # Copy all data to avoid shared state issues
        self.image_list = list(image_list)
        self.save_dir = save_dir  # Snapshot of value

        self.signals = StatisticsWorkerSignals()
        self._cancel_event = __import__('threading').Event()  # Thread-safe cancellation

    def cancel(self):
        """Thread-safe cancellation."""
        self._cancel_event.set()

    def is_cancelled(self):
        """Check cancellation state."""
        return self._cancel_event.is_set()

    def run(self):
        """Compute statistics with proper error handling."""
        error_occurred = False
        try:
            total = len(self.image_list)
            annotated = 0
            verified = 0
            label_counts = {}

            for i, img_path in enumerate(self.image_list):
                if self.is_cancelled():
                    return  # Clean exit on cancel

                try:
                    # Use stateless computation (no cache access)
                    status = self._compute_status(img_path)
                    if status != AnnotationStatus.NO_LABELS:
                        annotated += 1
                    if status == AnnotationStatus.VERIFIED:
                        verified += 1

                    labels = self._compute_labels(img_path)
                    for label in labels:
                        label_counts[label] = label_counts.get(label, 0) + 1
                except Exception:
                    # Log but continue processing other images
                    pass

                # Emit progress every 50 images
                if (i + 1) % 50 == 0 or i == total - 1:
                    self.signals.progress.emit(total, annotated, verified, label_counts.copy())

        except Exception as e:
            error_occurred = True
            self.signals.error.emit(str(e))
        finally:
            if not error_occurred and not self.is_cancelled():
                self.signals.finished.emit()

    def _compute_status(self, image_path):
        """Thread-safe annotation status check (no shared state)."""
        return _probe_status(image_path, self.save_dir)

    def _compute_labels(self, img_path):
        """Thread-safe label extraction (no shared state)."""
        return probe_annotation(img_path, self.save_dir, want_labels=True).labels


class StatusRefreshWorkerSignals(QObject):
    """Signals for status refresh worker."""
    batch_ready = pyqtSignal(dict)  # {path: AnnotationStatus} batch
    finished = pyqtSignal()
    error = pyqtSignal(str)


class StatusRefreshWorker(QRunnable):
    """Async worker for computing annotation statuses in background."""

    def __init__(self, image_list, save_dir=None, batch_size=100):
        super().__init__()
        self.setAutoDelete(True)
        self.image_list = list(image_list)
        self.save_dir = save_dir
        self.batch_size = batch_size
        self.signals = StatusRefreshWorkerSignals()
        self._cancel_event = __import__('threading').Event()

    def cancel(self):
        """Thread-safe cancellation."""
        self._cancel_event.set()

    def is_cancelled(self):
        """Check cancellation state."""
        return self._cancel_event.is_set()

    def run(self):
        """Compute statuses with proper error handling."""
        error_occurred = False
        try:
            batch = {}
            for img_path in self.image_list:
                if self.is_cancelled():
                    return

                status = self._compute_status(img_path)
                batch[img_path] = status

                if len(batch) >= self.batch_size:
                    self.signals.batch_ready.emit(batch.copy())
                    batch.clear()

            # Emit remaining batch
            if batch and not self.is_cancelled():
                self.signals.batch_ready.emit(batch)

        except Exception as e:
            error_occurred = True
            self.signals.error.emit(str(e))
        finally:
            if not error_occurred and not self.is_cancelled():
                self.signals.finished.emit()

    def _compute_status(self, image_path):
        """Thread-safe annotation status check (no shared state)."""
        return _probe_status(image_path, self.save_dir)


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, default_filename=None, default_prefdef_class_file=None, default_save_dir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings

        self.shortcut_config = ShortcutConfig()
        if settings.get(SETTING_SHORTCUTS):
            self.shortcut_config.from_dict(settings.get(SETTING_SHORTCUTS))

        self.os_name = platform.system()

        # Load string bundle for i18n
        self.string_bundle = StringBundle.get_bundle()
        get_str = lambda str_id: self.string_bundle.get_string(str_id)

        # Save as Pascal voc xml
        self.default_save_dir = default_save_dir
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT, LabelFileFormat.PASCAL_VOC)

        # For loading all image under a directory
        self.m_img_list = []
        self._path_to_idx = {}  # O(1) lookup: path -> index
        self._annotation_status_cache = {}  # Cache: path -> status (reduces I/O)

        # Memory optimization for large images (Issue #31)
        self._image_scale_factor = 1.0  # Display size / Original size
        self._original_image_size = None  # QSize of original image

        self.dir_name = None
        self.label_hist = []
        self.last_open_dir = None
        self.cur_img_idx = 0
        self.img_count = len(self.m_img_list)

        # Whether we need to save or not.
        self.dirty = False

        # Clipboard for copy/paste annotations across images
        self.clipboard_shapes = []

        self._no_selection_slot = False
        self._beginner = True
        self.gallery_mode_enabled = False
        self._gallery_batch_id = 0  # For cancelling pending batch processing
        self._status_worker_gen = 0  # Generation counter for status worker
        self._dock_status_worker_gen = 0  # Generation counter for dock status worker
        # Statistics orchestration lives in its own controller; the stats
        # widget is read lazily because the gallery panel is created on demand.
        self.stats_controller = StatsController(
            stats_widget_getter=lambda: getattr(self, 'gallery_stats', None),
            worker_factory=StatisticsWorker)
        self.stats_controller.current_image_refresh_requested.connect(
            self._update_current_image_stats)
        self._normal_central_widget = None
        self.screencast = "https://youtu.be/p0nR2YsCY_U"

        # Load predefined classes to the list
        self.load_predefined_classes(default_prefdef_class_file)

        if self.label_hist:
            self.default_label = self.label_hist[0]
        else:
            print("Not find:/data/predefined_classes.txt (optional)")

        # Main widgets and related state.
        self.label_dialog = LabelDialog(parent=self, list_item=self.label_hist)

        self.items_to_shapes = {}
        self.shapes_to_items = {}
        self.prev_label_text = ''

        list_layout = QVBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)

        # Create a widget for using default label
        self.use_default_label_checkbox = QCheckBox(get_str('useDefaultLabel'))
        self.use_default_label_checkbox.setChecked(False)
        self.default_label_combo_box = DefaultLabelComboBox(self,items=self.label_hist)

        use_default_label_qhbox_layout = QHBoxLayout()
        use_default_label_qhbox_layout.addWidget(self.use_default_label_checkbox)
        use_default_label_qhbox_layout.addWidget(self.default_label_combo_box)
        use_default_label_container = QWidget()
        use_default_label_container.setLayout(use_default_label_qhbox_layout)

        # Create a widget for edit and diffc button
        self.diffc_button = QCheckBox(get_str('useDifficult'))
        self.diffc_button.setChecked(False)
        self.diffc_button.stateChanged.connect(self.button_state)
        self.edit_button = QToolButton()
        self.edit_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Add some of widgets to list_layout
        list_layout.addWidget(self.edit_button)
        list_layout.addWidget(self.diffc_button)
        list_layout.addWidget(use_default_label_container)

        # Create and add combobox for showing unique labels in group
        self.combo_box = ComboBox(self)
        list_layout.addWidget(self.combo_box)

        # Create tabbed label lists for rectangles and polygons
        self.label_tab_widget = QTabWidget()
        self.rect_label_list = QListWidget()
        self.poly_label_list = QListWidget()
        self.label_tab_widget.addTab(self.rect_label_list, 'Rectangles (0)')
        self.label_tab_widget.addTab(self.poly_label_list, 'Polygons (0)')

        # Keep self.label_list as alias to rect list for backward compatibility
        self.label_list = self.rect_label_list

        label_list_container = QWidget()
        label_list_container.setLayout(list_layout)

        # Connect signals for both label lists
        for lw in (self.rect_label_list, self.poly_label_list):
            lw.itemActivated.connect(self.label_selection_changed)
            lw.itemSelectionChanged.connect(self.label_selection_changed)
            lw.itemDoubleClicked.connect(self.edit_label)
            lw.itemChanged.connect(self.label_item_changed)

        list_layout.addWidget(self.label_tab_widget)

        # Keypoint annotation panel (shown for person shapes)
        self.keypoint_panel = KeypointPanel()
        self.keypoint_panel.keypointClicked.connect(self._on_keypoint_panel_click)
        list_layout.addWidget(self.keypoint_panel)

        self.dock = QDockWidget(get_str('boxLabelText'), self)
        self.dock.setObjectName(get_str('labels'))
        self.dock.setWidget(label_list_container)

        # File list widget (existing list view)
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        self.file_list_widget.itemClicked.connect(self.file_item_clicked)

        # Gallery widget (new thumbnail view)
        self.gallery_widget = GalleryWidget()
        self.gallery_widget.image_selected.connect(
            lambda path: self.gallery_image_selected(path, source='dock'))
        self.gallery_widget.image_activated.connect(self.gallery_image_activated)

        # Tab widget to hold both views
        self.file_view_tabs = QTabWidget()
        self.file_view_tabs.addTab(self.file_list_widget, get_str('listView'))
        self.file_view_tabs.addTab(self.gallery_widget, get_str('galleryView'))
        self.file_view_tabs.currentChanged.connect(self.on_file_view_tab_changed)

        # Status filter combo box
        self.status_filter_combo = QComboBox()
        self.status_filter_combo.addItems([
            get_str('filterAll'),
            get_str('filterAnnotated'),
            get_str('filterVerified'),
            get_str('filterUnannotated'),
        ])
        self.status_filter_combo.currentIndexChanged.connect(
            self.apply_status_filter)

        file_list_layout = QVBoxLayout()
        file_list_layout.setContentsMargins(0, 0, 0, 0)
        file_list_layout.addWidget(self.status_filter_combo)
        file_list_layout.addWidget(self.file_view_tabs)
        file_list_container = QWidget()
        file_list_container.setLayout(file_list_layout)
        self.file_dock = QDockWidget(get_str('fileList'), self)
        self.file_dock.setObjectName(get_str('files'))
        self.file_dock.setWidget(file_list_container)

        # Statistics widget moved to gallery mode (Issue #19)

        self.zoom_widget = ZoomWidget()
        self.light_widget = LightWidget(get_str('lightWidgetTitle'))
        self.color_dialog = ColorDialog(parent=self)

        self.canvas = Canvas(parent=self)
        self.canvas.zoomRequest.connect(self.zoom_request)
        self.canvas.lightRequest.connect(self.light_request)
        self.canvas.set_drawing_shape_to_square(settings.get(SETTING_DRAW_SQUARE, False))

        scroll = QScrollArea()
        scroll.setWidget(self.canvas)
        scroll.setWidgetResizable(True)
        self.scroll_bars = {
            Qt.Vertical: scroll.verticalScrollBar(),
            Qt.Horizontal: scroll.horizontalScrollBar()
        }
        self.scroll_area = scroll
        self.canvas.scrollRequest.connect(self.scroll_request)

        self.canvas.newShape.connect(self.new_shape)
        self.canvas.shapeMoved.connect(self.set_dirty)
        self.canvas.shapeMoved.connect(self._on_shape_moved_keypoints)
        self.canvas.polygonVerticesEdited.connect(
            self._on_polygon_vertices_edited)
        self.canvas.keypointsEdited.connect(self._on_keypoints_edited)
        self.canvas.shapeMoveFinished.connect(self._on_shape_move_finished)
        self.canvas.selectionChanged.connect(self.shape_selection_changed)
        self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)

        # Initialize undo/redo system
        self.undo_stack = UndoStack(max_size=50)
        self.undo_stack.add_callback(self.update_undo_redo_actions)

        self.setCentralWidget(scroll)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.file_dock)

        # Configure dock features - all docks are movable for resizing
        # DockWidgetMovable enables drag-to-rearrange and proper splitter resizing
        dock_features_all = (QDockWidget.DockWidgetMovable |
                             QDockWidget.DockWidgetFloatable |
                             QDockWidget.DockWidgetClosable)
        self.file_dock.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)

        # Set minimum sizes for better resize UX
        self.dock.setMinimumHeight(100)
        self.file_dock.setMinimumHeight(100)
        self.dock.setMinimumWidth(200)
        self.file_dock.setMinimumWidth(200)

        # Features toggled by advanced mode (closable/floatable for labels dock)
        self.dock_features = QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetFloatable
        # In beginner mode, labels dock is movable only (not closable/floatable)
        self.dock.setFeatures(QDockWidget.DockWidgetMovable)

        # Actions
        action = partial(new_action, self)
        quit = action(get_str('quit'), self.close,
                      self.shortcut_config.get('quit'), 'quit', get_str('quitApp'))

        open = action(get_str('openFile'), self.open_file,
                      self.shortcut_config.get('open'), 'open', get_str('openFileDetail'))

        open_dir = action(get_str('openDir'), self.open_dir_dialog,
                          self.shortcut_config.get('open_dir'), 'open', get_str('openDir'))

        change_save_dir = action(get_str('changeSaveDir'), self.change_save_dir_dialog,
                                 self.shortcut_config.get('change_save_dir'), 'open', get_str('changeSavedAnnotationDir'))

        open_annotation = action(get_str('openAnnotation'), self.open_annotation_dialog,
                                 self.shortcut_config.get('open_annotation'), 'open', get_str('openAnnotationDetail'))
        copy_prev_bounding = action(get_str('copyPrevBounding'), self.copy_previous_bounding_boxes, self.shortcut_config.get('copy_prev_bounding'), 'copy', get_str('copyPrevBounding'))

        open_next_image = action(get_str('nextImg'), self.open_next_image,
                                 self.shortcut_config.get('open_next_image'), 'next', get_str('nextImgDetail'))

        open_prev_image = action(get_str('prevImg'), self.open_prev_image,
                                 self.shortcut_config.get('open_prev_image'), 'prev', get_str('prevImgDetail'))

        verify = action(get_str('verifyImg'), self.verify_image,
                        self.shortcut_config.get('verify'), 'verify', get_str('verifyImgDetail'))

        save = action(get_str('save'), self.save_file,
                      self.shortcut_config.get('save'), 'save', get_str('saveDetail'), enabled=False)

        def get_format_meta(format):
            """Return a tuple containing (title, icon_name) of the selected format."""
            if format == LabelFileFormat.PASCAL_VOC:
                return '&PascalVOC', 'format_voc'
            elif format == LabelFileFormat.YOLO:
                return '&YOLO', 'format_yolo'
            elif format == LabelFileFormat.CREATE_ML:
                return '&CreateML', 'format_createml'
            elif format == LabelFileFormat.COCO:
                return '&COCO', 'format_createml'
            elif format == LabelFileFormat.YOLO_SEG:
                return '&YOLO-seg', 'format_yolo'
            # Default fallback
            return '&PascalVOC', 'format_voc'

        save_format = action(get_format_meta(self.label_file_format)[0],
                             self.change_format, self.shortcut_config.get('save_format'),
                             get_format_meta(self.label_file_format)[1],
                             get_str('changeSaveFormat'), enabled=True)

        save_as = action(get_str('saveAs'), self.save_file_as,
                         self.shortcut_config.get('save_as'), 'save-as', get_str('saveAsDetail'), enabled=False)

        close = action(get_str('closeCur'), self.close_file, self.shortcut_config.get('close'), 'close', get_str('closeCurDetail'))

        delete_image = action(get_str('deleteImg'), self.delete_image, self.shortcut_config.get('delete_image'), 'close', get_str('deleteImgDetail'))

        reset_all = action(get_str('resetAll'), self.reset_all, None, 'resetall', get_str('resetAllDetail'))

        color1 = action(get_str('boxLineColor'), self.choose_color1,
                        self.shortcut_config.get('color1'), 'color_line', get_str('boxLineColorDetail'))

        create_mode = action(get_str('crtBox'), self.set_create_mode,
                             self.shortcut_config.get('create_mode'), 'new', get_str('crtBoxDetail'), enabled=False)
        edit_mode = action(get_str('editBox'), self.set_edit_mode,
                           self.shortcut_config.get('edit_mode'), 'edit', get_str('editBoxDetail'), enabled=False)

        create = action(get_str('crtBox'), self.create_shape,
                        self.shortcut_config.get('create'), 'new', get_str('crtBoxDetail'), enabled=False)
        create_polygon = action(get_str('crtPolygon'), self.create_polygon_mode,
                                self.shortcut_config.get('create_polygon'),
                                'objects', get_str('crtPolygonDetail'), enabled=False)
        keypoint_mode_action = action(
            get_str('addKeypoints'),
            self.toggle_keypoint_mode,
            self.shortcut_config.get('keypoint_mode'),
            'verify',
            get_str('addKeypointsDetail'),
            enabled=False)
        delete = action(get_str('delBox'), self.delete_selected_shape,
                        self.shortcut_config.get('delete'), 'delete', get_str('delBoxDetail'), enabled=False)
        copy = action(get_str('dupBox'), self.copy_selected_shape,
                      self.shortcut_config.get('copy'), 'copy', get_str('dupBoxDetail'),
                      enabled=False)

        copy_to_clipboard = action(get_str('copyBox'), self.copy_to_clipboard,
                                   self.shortcut_config.get('copy_to_clipboard'), 'copy', get_str('copyBoxDetail'),
                                   enabled=False)
        paste_from_clipboard = action(get_str('pasteBox'), self.paste_from_clipboard,
                                      self.shortcut_config.get('paste_from_clipboard'), 'paste', get_str('pasteBoxDetail'),
                                      enabled=False)
        copy_all_to_clipboard = action(get_str('copyAllBoxes'), self.copy_all_to_clipboard,
                                       self.shortcut_config.get('copy_all_to_clipboard'), 'copy', get_str('copyAllBoxesDetail'),
                                       enabled=False)

        undo = action(get_str('undo'), self.undo_action,
                      self.shortcut_config.get('undo'), 'undo', get_str('undoDetail'), enabled=False)
        redo = action(get_str('redo'), self.redo_action,
                      self.shortcut_config.get('redo'), 'redo', get_str('redoDetail'), enabled=False)

        advanced_mode = action(get_str('advancedMode'), self.toggle_advanced_mode,
                               self.shortcut_config.get('advanced_mode'), 'expert', get_str('advancedModeDetail'),
                               checkable=True)

        gallery_mode = action(get_str('galleryMode'), self.toggle_gallery_mode,
                              self.shortcut_config.get('gallery_mode'), 'labels', get_str('galleryModeDetail'),
                              checkable=True)

        hide_all = action(get_str('hideAllBox'), partial(self.toggle_polygons, False),
                          self.shortcut_config.get('hide_all'), 'hide', get_str('hideAllBoxDetail'),
                          enabled=False)
        show_all = action(get_str('showAllBox'), partial(self.toggle_polygons, True),
                          self.shortcut_config.get('show_all'), 'hide', get_str('showAllBoxDetail'),
                          enabled=False)

        help_default = action(get_str('tutorialDefault'), self.show_default_tutorial_dialog, None, 'help', get_str('tutorialDetail'))
        show_info = action(get_str('info'), self.show_info_dialog, None, 'help', get_str('info'))
        show_shortcut = action(get_str('shortcut'), self.show_shortcuts_dialog, None, 'help', get_str('shortcut'))

        zoom = QWidgetAction(self)
        zoom.setDefaultWidget(self.zoom_widget)
        self.zoom_widget.setWhatsThis(
            u"Zoom in or out of the image. Also accessible with"
            " %s and %s from the canvas." % (format_shortcut("Ctrl+[-+]"),
                                             format_shortcut("Ctrl+Wheel")))
        self.zoom_widget.setEnabled(False)

        zoom_in = action(get_str('zoomin'), partial(self.add_zoom, 10),
                         self.shortcut_config.get('zoom_in'), 'zoom-in', get_str('zoominDetail'), enabled=False)
        zoom_out = action(get_str('zoomout'), partial(self.add_zoom, -10),
                          self.shortcut_config.get('zoom_out'), 'zoom-out', get_str('zoomoutDetail'), enabled=False)
        zoom_org = action(get_str('originalsize'), partial(self.set_zoom, 100),
                          self.shortcut_config.get('zoom_org'), 'zoom', get_str('originalsizeDetail'), enabled=False)
        fit_window = action(get_str('fitWin'), self.set_fit_window,
                            self.shortcut_config.get('fit_window'), 'fit-window', get_str('fitWinDetail'),
                            checkable=True, enabled=False)
        fit_width = action(get_str('fitWidth'), self.set_fit_width,
                           self.shortcut_config.get('fit_width'), 'fit-width', get_str('fitWidthDetail'),
                           checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoom_actions = (self.zoom_widget, zoom_in, zoom_out,
                        zoom_org, fit_window, fit_width)
        self.zoom_mode = self.MANUAL_ZOOM
        self.scalers = {
            self.FIT_WINDOW: self.scale_fit_window,
            self.FIT_WIDTH: self.scale_fit_width,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        light = QWidgetAction(self)
        light.setDefaultWidget(self.light_widget)
        self.light_widget.setWhatsThis(
            u"Brighten or darken current image. Also accessible with"
            " %s and %s from the canvas." % (format_shortcut("Ctrl+Shift+[-+]"),
                                             format_shortcut("Ctrl+Shift+Wheel")))
        self.light_widget.setEnabled(False)

        light_brighten = action(get_str('lightbrighten'), partial(self.add_light, 10),
                                self.shortcut_config.get('light_brighten'), 'light_lighten', get_str('lightbrightenDetail'), enabled=False)
        light_darken = action(get_str('lightdarken'), partial(self.add_light, -10),
                              self.shortcut_config.get('light_darken'), 'light_darken', get_str('lightdarkenDetail'), enabled=False)
        light_org = action(get_str('lightreset'), partial(self.set_light, 50),
                           self.shortcut_config.get('light_org'), 'light_reset', get_str('lightresetDetail'), checkable=True, enabled=False)
        light_org.setChecked(True)

        # Create brightness dropdown button for toolbar
        brightness_dropdown = DropdownToolButton(
            "Brightness",
            new_icon('sun'),
            [light_brighten, light_darken, None, light_org]
        )

        # Group light controls into a list for easier toggling.
        light_actions = (self.light_widget, light_brighten,
                         light_darken, light_org, brightness_dropdown)

        edit = action(get_str('editLabel'), self.edit_label,
                      self.shortcut_config.get('edit_label'), 'edit', get_str('editLabelDetail'),
                      enabled=False)
        self.edit_button.setDefaultAction(edit)

        shape_line_color = action(get_str('shapeLineColor'), self.choose_shape_line_color,
                                  icon='color_line', tip=get_str('shapeLineColorDetail'),
                                  enabled=False)
        shape_fill_color = action(get_str('shapeFillColor'), self.choose_shape_fill_color,
                                  icon='color', tip=get_str('shapeFillColorDetail'),
                                  enabled=False)

        labels = self.dock.toggleViewAction()
        labels.setText(get_str('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Statistics panel moved to gallery mode (Issue #19)

        # Label list context menu.
        label_menu = QMenu()
        add_actions(label_menu, (edit, delete))
        for lw in (self.rect_label_list, self.poly_label_list):
            lw.setContextMenuPolicy(Qt.CustomContextMenu)
            lw.customContextMenuRequested.connect(self.pop_label_list_menu)

        # Draw squares/rectangles
        self.draw_squares_option = QAction(get_str('drawSquares'), self)
        self.draw_squares_option.setShortcut('Ctrl+Shift+R')
        self.draw_squares_option.setCheckable(True)
        self.draw_squares_option.setChecked(settings.get(SETTING_DRAW_SQUARE, False))
        self.draw_squares_option.triggered.connect(self.toggle_draw_square)

        # Lock on verify: prevent editing when image is verified
        self.lock_on_verify_option = QAction(get_str('lockOnVerify'), self)
        self.lock_on_verify_option.setCheckable(True)
        self.lock_on_verify_option.setChecked(settings.get(SETTING_LOCK_ON_VERIFY, False))
        self.lock_on_verify_option.toggled.connect(self.toggle_lock_on_verify)

        # Grid overlay toggle
        self.show_grid_option = QAction(get_str('showGrid'), self)
        self.show_grid_option.setShortcut('Ctrl+Shift+G')
        self.show_grid_option.setCheckable(True)
        self.show_grid_option.setChecked(settings.get(SETTING_GRID_ENABLED, False))
        self.show_grid_option.toggled.connect(self.toggle_grid)

        # Edge alignment toggle
        self.edge_alignment_option = QAction(get_str('edgeAlignment'), self)
        self.edge_alignment_option.setCheckable(True)
        self.edge_alignment_option.setChecked(settings.get(SETTING_EDGE_ALIGNMENT, False))
        self.edge_alignment_option.toggled.connect(self.toggle_edge_alignment)

        # Grid size submenu
        self.grid_size_menu = QMenu(get_str('gridSize'), self)
        self.grid_size_group = QActionGroup(self)
        self.grid_size_group.setExclusive(True)
        saved_grid_size = settings.get(SETTING_GRID_SIZE, 32)
        for size in [8, 16, 32, 64]:
            size_action = QAction(f'{size}px', self)
            size_action.setCheckable(True)
            size_action.setData(size)
            if size == saved_grid_size:
                size_action.setChecked(True)
            size_action.triggered.connect(self._set_grid_size)
            self.grid_size_group.addAction(size_action)
            self.grid_size_menu.addAction(size_action)

        # Map action names to QAction objects for shortcut customization.
        self._action_map = {
            'quit': quit,
            'open': open,
            'open_dir': open_dir,
            'change_save_dir': change_save_dir,
            'open_annotation': open_annotation,
            'copy_prev_bounding': copy_prev_bounding,
            'open_next_image': open_next_image,
            'open_prev_image': open_prev_image,
            'verify': verify,
            'save': save,
            'save_format': save_format,
            'save_as': save_as,
            'close': close,
            'delete_image': delete_image,
            'color1': color1,
            'create_mode': create_mode,
            'edit_mode': edit_mode,
            'create': create,
            'create_polygon': create_polygon,
            'delete': delete,
            'copy': copy,
            'copy_to_clipboard': copy_to_clipboard,
            'paste_from_clipboard': paste_from_clipboard,
            'copy_all_to_clipboard': copy_all_to_clipboard,
            'undo': undo,
            'redo': redo,
            'advanced_mode': advanced_mode,
            'gallery_mode': gallery_mode,
            'hide_all': hide_all,
            'show_all': show_all,
            'zoom_in': zoom_in,
            'zoom_out': zoom_out,
            'zoom_org': zoom_org,
            'fit_window': fit_window,
            'fit_width': fit_width,
            'light_brighten': light_brighten,
            'light_darken': light_darken,
            'light_org': light_org,
            'edit_label': edit,
            'keypoint_mode': keypoint_mode_action,
        }

        # Store actions for further handling.
        self.actions = Struct(save=save, save_format=save_format, saveAs=save_as, open=open, close=close, resetAll=reset_all, deleteImg=delete_image,
                              lineColor=color1, create=create, create_polygon=create_polygon,
                              keypoint_mode=keypoint_mode_action,
                              delete=delete, edit=edit, copy=copy,
                              copyToClipboard=copy_to_clipboard, pasteFromClipboard=paste_from_clipboard,
                              copyAllToClipboard=copy_all_to_clipboard,
                              undo=undo, redo=redo,
                              createMode=create_mode, editMode=edit_mode, advancedMode=advanced_mode, galleryMode=gallery_mode,
                              shapeLineColor=shape_line_color, shapeFillColor=shape_fill_color,
                              zoom=zoom, zoomIn=zoom_in, zoomOut=zoom_out, zoomOrg=zoom_org,
                              fitWindow=fit_window, fitWidth=fit_width,
                              zoomActions=zoom_actions,
                              lightBrighten=light_brighten, lightDarken=light_darken, lightOrg=light_org,
                              lightActions=light_actions,
                              fileMenuActions=(
                                  open, open_dir, save, save_as, close, reset_all, quit),
                              beginner=(), advanced=(),
                              editMenu=(undo, redo, None, edit, copy, copy_to_clipboard,
                                        paste_from_clipboard, copy_all_to_clipboard, delete,
                                        None, keypoint_mode_action,
                                        None, color1, self.draw_squares_option),
                              beginnerContext=(create, create_polygon, edit, copy, copy_to_clipboard, paste_from_clipboard, delete),
                              advancedContext=(create_mode, edit_mode, edit, copy, copy_to_clipboard,
                                               paste_from_clipboard, delete, shape_line_color, shape_fill_color),
                              onLoadActive=(
                                  close, create, create_polygon, create_mode, edit_mode),
                              onShapesPresent=(save_as, hide_all, show_all))

        self.menus = Struct(
            file=self.menu(get_str('menu_file')),
            edit=self.menu(get_str('menu_edit')),
            view=self.menu(get_str('menu_view')),
            tools=self.menu('&Tools'),
            help=self.menu(get_str('menu_help')),
            recentFiles=QMenu(get_str('menu_openRecent')),
            labelList=label_menu)

        # Auto saving : Enable auto saving if pressing next
        self.auto_saving = QAction(get_str('autoSaveMode'), self)
        self.auto_saving.setCheckable(True)
        self.auto_saving.setChecked(settings.get(SETTING_AUTO_SAVE, False))
        self.auto_saving.setToolTip(get_str('autoSaveModeDetail'))

        # Auto-save timer (Issue #13)
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self._auto_save_triggered)

        # Auto-save enabled toggle
        self.auto_save_enabled = QAction(get_str('autoSaveEnabled'), self)
        self.auto_save_enabled.setCheckable(True)
        self.auto_save_enabled.setChecked(settings.get(SETTING_AUTO_SAVE_ENABLED, False))
        self.auto_save_enabled.triggered.connect(self._toggle_auto_save_timer)
        self.auto_save_enabled.setToolTip(get_str('autoSaveEnabledDetail'))

        # Auto-save interval submenu
        self.auto_save_interval_menu = QMenu(get_str('autoSaveInterval'), self)
        self.auto_save_interval_group = QActionGroup(self)
        self.auto_save_interval_group.setExclusive(True)
        auto_save_intervals = [
            (get_str('autoSave30s'), 30),
            (get_str('autoSave1m'), 60),
            (get_str('autoSave2m'), 120),
            (get_str('autoSave5m'), 300),
        ]
        saved_interval = settings.get(SETTING_AUTO_SAVE_INTERVAL, 60)
        for name, interval in auto_save_intervals:
            interval_action = QAction(name, self)
            interval_action.setCheckable(True)
            interval_action.setData(interval)
            interval_action.triggered.connect(self._set_auto_save_interval)
            self.auto_save_interval_group.addAction(interval_action)
            self.auto_save_interval_menu.addAction(interval_action)
            if interval == saved_interval:
                interval_action.setChecked(True)
        # Default to 1 minute if nothing selected
        if not any(a.isChecked() for a in self.auto_save_interval_group.actions()):
            self.auto_save_interval_group.actions()[1].setChecked(True)  # 1 minute

        # Sync single class mode from PR#106
        self.single_class_mode = QAction(get_str('singleClsMode'), self)
        self.single_class_mode.setShortcut("Ctrl+Shift+S")
        self.single_class_mode.setCheckable(True)
        self.single_class_mode.setChecked(settings.get(SETTING_SINGLE_CLASS, False))
        self.lastLabel = None
        # Add option to enable/disable labels being displayed at the top of bounding boxes
        self.display_label_option = QAction(get_str('displayLabel'), self)
        self.display_label_option.setShortcut("Ctrl+Shift+P")
        self.display_label_option.setCheckable(True)
        self.display_label_option.setChecked(settings.get(SETTING_PAINT_LABEL, False))
        self.display_label_option.triggered.connect(self.toggle_paint_labels_option)

        # Icon size submenu for toolbar
        self.icon_size_menu = QMenu(get_str('iconSize'), self)
        self.icon_size_group = QActionGroup(self)
        self.icon_size_group.setExclusive(True)
        icon_sizes = [
            (get_str('iconSizeSmall'), 16),
            (get_str('iconSizeMedium'), 22),
            (get_str('iconSizeLarge'), 28),
            (get_str('iconSizeXLarge'), 36),
            (get_str('iconSizeAuto'), 0),  # 0 means auto-detect
        ]
        saved_icon_size = settings.get(SETTING_ICON_SIZE, 0)
        for name, size in icon_sizes:
            icon_action = QAction(name, self)
            icon_action.setCheckable(True)
            icon_action.setData(size)
            icon_action.triggered.connect(self.change_icon_size)
            self.icon_size_group.addAction(icon_action)
            self.icon_size_menu.addAction(icon_action)
            if size == saved_icon_size:
                icon_action.setChecked(True)
        # Default to auto if nothing selected
        if not any(a.isChecked() for a in self.icon_size_group.actions()):
            self.icon_size_group.actions()[-1].setChecked(True)

        add_actions(self.menus.file,
                    (open, open_dir, change_save_dir, open_annotation, copy_prev_bounding, self.menus.recentFiles, save, save_format, save_as, close, reset_all, delete_image, quit))
        add_actions(self.menus.help, (help_default, show_info, show_shortcut))
        add_actions(self.menus.view, (
            self.auto_saving,
            self.auto_save_enabled,
            self.single_class_mode,
            self.display_label_option,
            self.lock_on_verify_option,
            labels, advanced_mode, gallery_mode, None,
            hide_all, show_all, None,
            zoom_in, zoom_out, zoom_org, None,
            fit_window, fit_width, None,
            light_brighten, light_darken, light_org, None))
        self.menus.view.addMenu(self.auto_save_interval_menu)
        self.menus.view.addMenu(self.icon_size_menu)
        self.menus.view.addSeparator()
        self.menus.view.addAction(self.show_grid_option)
        self.menus.view.addMenu(self.grid_size_menu)
        self.menus.view.addAction(self.edge_alignment_option)

        # Dark mode toggle
        self.dark_mode_action = QAction('&Dark Mode', self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setShortcut('Ctrl+Shift+T')
        self.dark_mode_action.setToolTip('Toggle dark mode theme')
        self.dark_mode_action.setChecked(settings.get(SETTING_DARK_MODE, False))
        self.dark_mode_action.triggered.connect(self._toggle_dark_mode)
        self.menus.view.addSeparator()
        self.menus.view.addAction(self.dark_mode_action)

        # Apply initial theme
        self._current_theme = Theme.DARK if settings.get(SETTING_DARK_MODE, False) else Theme.LIGHT
        self._apply_theme(self._current_theme)

        self.menus.file.aboutToShow.connect(self.update_file_menu)

        # Tools menu actions
        check_labels = action('Check Label &Consistency', self.check_label_consistency,
                              'Ctrl+Shift+L', 'verify', 'Check for typos and inconsistent labels in dataset')
        batch_verify_action = action(
            get_str('batchVerify'), self.batch_verify,
            None, 'verify', get_str('batchVerifyDetail'))
        split_dataset_action = action(
            get_str('splitDataset'), self.split_dataset,
            None, 'file', get_str('splitDatasetDetail'))
        add_actions(self.menus.tools, (
            check_labels, batch_verify_action, split_dataset_action))

        # Custom context menu for the canvas widget:
        add_actions(self.canvas.menus[0], self.actions.beginnerContext)
        add_actions(self.canvas.menus[1], (
            action('&Copy here', self.copy_shape),
            action('&Move here', self.move_shape)))

        self.tools = self.toolbar('Tools')
        # Toolbar style will be set by _apply_theme() below

        # Apply saved icon size setting
        saved_icon_size = settings.get(SETTING_ICON_SIZE, 0)
        if saved_icon_size > 0:
            self.tools.update_icon_size(saved_icon_size)

        # Create dropdown for file/directory operations
        file_dropdown = DropdownToolButton(
            text=get_str('openFile'),
            icon=new_icon('file'),
            actions=[open, open_dir, change_save_dir]
        )

        self.actions.beginner = (
            file_dropdown, gallery_mode, None, open_next_image, open_prev_image, verify, save, save_format, None,
            create, create_polygon, keypoint_mode_action, copy, delete, None,
            zoom_in, zoom, zoom_out, fit_window, fit_width, None,
            brightness_dropdown)

        self.actions.advanced = (
            file_dropdown, gallery_mode, None, open_next_image, open_prev_image, save, save_format, None,
            create_mode, edit_mode, None,
            create_polygon, None,
            hide_all, show_all)

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        # Application state.
        self.image = QImage()
        self.file_path = ustr(default_filename)
        self.last_open_dir = None
        self.recent_files = []
        self.max_recent = 7
        self.line_color = None
        self.fill_color = None
        self.zoom_level = 100
        # Add Chris
        self.difficult = False

        # Fix the compatible issue for qt4 and qt5. Convert the QStringList to python list
        if settings.get(SETTING_RECENT_FILES):
            if have_qstring():
                recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)
                self.recent_files = [ustr(i) for i in recent_file_qstring_list]
            else:
                self.recent_files = recent_file_qstring_list = settings.get(SETTING_RECENT_FILES)

        size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
        position = QPoint(0, 0)
        saved_position = settings.get(SETTING_WIN_POSE, position)
        # Fix the multiple monitors issue
        for i in range(QApplication.desktop().screenCount()):
            if QApplication.desktop().availableGeometry(i).contains(saved_position):
                position = saved_position
                break
        self.resize(size)
        self.move(position)
        save_dir = ustr(settings.get(SETTING_SAVE_DIR, None))
        self.last_open_dir = ustr(settings.get(SETTING_LAST_OPEN_DIR, None))
        if self.default_save_dir is None and save_dir is not None and os.path.exists(save_dir):
            self.default_save_dir = save_dir
            self.statusBar().showMessage('%s started. Annotation will be saved to %s' %
                                         (__appname__, self.default_save_dir))
            self.statusBar().show()

        self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))
        Shape.line_color = self.line_color = QColor(settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fill_color = QColor(settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.set_drawing_color(self.line_color)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_ADVANCE_MODE, False)):
            self.actions.advancedMode.setChecked(True)
            self.toggle_advanced_mode()

        if xbool(settings.get(SETTING_GALLERY_MODE, False)):
            self.actions.galleryMode.setChecked(True)
            self.toggle_gallery_mode()

        # Populate the File menu dynamically.
        self.update_file_menu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.file_path and os.path.isdir(self.file_path):
            self.queue_event(partial(self.import_dir_images, self.file_path or ""))
        elif self.file_path:
            self.queue_event(partial(self.load_file, self.file_path or ""))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.paint_canvas)
        self.zoom_widget.valueChanged.connect(self.update_zoom_display)
        self.light_widget.valueChanged.connect(self.paint_canvas)

        self.populate_mode_actions()

        # Status bar permanent widgets (left to right)
        # Image counter
        self.label_image_count = QLabel('Image: 0 / 0')
        self.label_image_count.setMinimumWidth(100)
        self.statusBar().addPermanentWidget(self.label_image_count)

        # Annotation count
        self.label_box_count = QLabel('Boxes: 0')
        self.label_box_count.setMinimumWidth(70)
        self.statusBar().addPermanentWidget(self.label_box_count)

        # Zoom level
        self.label_zoom = QLabel('Zoom: 100%')
        self.label_zoom.setMinimumWidth(80)
        self.statusBar().addPermanentWidget(self.label_zoom)

        # Save status indicator
        self.label_save_status = QLabel('●')
        self._update_save_status_style(saved=True)  # Use helper method
        self.statusBar().addPermanentWidget(self.label_save_status)

        # Display cursor coordinates at the right of status bar
        self.label_coordinates = QLabel('')
        self.statusBar().addPermanentWidget(self.label_coordinates)

        # Open Dir if default file
        if self.file_path and os.path.isdir(self.file_path):
            self.open_dir_dialog(dir_path=self.file_path, silent=True)

        # Start auto-save timer if enabled (Issue #13)
        if self.auto_save_enabled.isChecked():
            self._toggle_auto_save_timer()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.set_drawing_shape_to_square(True)

    # Support Functions #
    def set_format(self, save_format):
        theme = getattr(self, '_current_theme', Theme.LIGHT)
        if save_format == FORMAT_PASCALVOC:
            self.actions.save_format.setText(FORMAT_PASCALVOC)
            self.actions.save_format.setIcon(themed_icon("format_voc", theme))
            self.label_file_format = LabelFileFormat.PASCAL_VOC
            LabelFile.suffix = XML_EXT

        elif save_format == FORMAT_YOLO:
            self.actions.save_format.setText(FORMAT_YOLO)
            self.actions.save_format.setIcon(themed_icon("format_yolo", theme))
            self.label_file_format = LabelFileFormat.YOLO
            LabelFile.suffix = TXT_EXT

        elif save_format == FORMAT_CREATEML:
            self.actions.save_format.setText(FORMAT_CREATEML)
            self.actions.save_format.setIcon(themed_icon("format_createml", theme))
            self.label_file_format = LabelFileFormat.CREATE_ML
            LabelFile.suffix = JSON_EXT

        elif save_format == FORMAT_COCO:
            self.actions.save_format.setText(FORMAT_COCO)
            self.actions.save_format.setIcon(themed_icon("format_createml", theme))
            self.label_file_format = LabelFileFormat.COCO
            LabelFile.suffix = JSON_EXT

        elif save_format == FORMAT_YOLO_SEG:
            self.actions.save_format.setText(FORMAT_YOLO_SEG)
            self.actions.save_format.setIcon(themed_icon("format_yolo", theme))
            self.label_file_format = LabelFileFormat.YOLO_SEG
            LabelFile.suffix = TXT_EXT

    def change_format(self):
        """Cycle through annotation formats: VOC -> YOLO -> CreateML -> COCO -> YOLO-seg -> VOC."""
        format_cycle = {
            LabelFileFormat.PASCAL_VOC: (FORMAT_YOLO, "Switching to YOLO format.\n\nNote: The 'difficult' flag will be lost."),
            LabelFileFormat.YOLO: (FORMAT_CREATEML, "Switching to CreateML format."),
            LabelFileFormat.CREATE_ML: (FORMAT_COCO, "Switching to COCO format.\n\nSupports polygon annotations natively."),
            LabelFileFormat.COCO: (FORMAT_YOLO_SEG, "Switching to YOLO-seg format.\n\nSupports polygon annotations natively."),
            LabelFileFormat.YOLO_SEG: (FORMAT_PASCALVOC, "Switching to PASCAL VOC format."),
        }

        entry = format_cycle.get(self.label_file_format)
        if entry is None:
            raise ValueError('Unknown label file format.')

        new_format, warning = entry

        # Show confirmation dialog
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Change Annotation Format")
        msg.setText(warning)
        msg.setInformativeText("This will only affect new saves. Existing annotation files will not be converted.")
        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Ok)

        if msg.exec_() == QMessageBox.Ok:
            self.set_format(new_format)
            self.set_dirty()
            self.status(f"Format changed to {new_format}")

    def no_shapes(self):
        return not self.items_to_shapes

    def toggle_advanced_mode(self, value=True):
        self._beginner = not value
        self.canvas.set_editing(True)
        self.populate_mode_actions()
        self.edit_button.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)
            self.dock.setFeatures(self.dock.features() | self.dock_features)
        else:
            self.dock.setFeatures(self.dock.features() ^ self.dock_features)

    def toggle_gallery_mode(self, value=True):
        """Toggle between normal view and full-screen gallery mode."""
        if hasattr(self, '_toggling_gallery') and self._toggling_gallery:
            return
        self._toggling_gallery = True
        self._gallery_batch_id += 1
        try:
            self.gallery_mode_enabled = value
            self._cleanup_existing_gallery()

            if value:
                self._create_gallery_window()
                QTimer.singleShot(0, self._refresh_full_gallery_statuses)
                QTimer.singleShot(100, self._refresh_all_statistics)
                if self.file_path:
                    self.full_gallery.select_image(self.file_path)
                self.gallery_window.showMaximized()
        finally:
            self._toggling_gallery = False

    def _cleanup_existing_gallery(self):
        """Clean up any existing gallery resources."""
        # Cancel any running workers with proper cleanup
        self._cleanup_stats_worker()
        self._cleanup_status_worker()
        if hasattr(self, 'full_gallery') and self.full_gallery:
            try:
                self.full_gallery.image_selected.disconnect()
                self.full_gallery.image_activated.disconnect()
            except TypeError:
                pass
            self.full_gallery = None
        if hasattr(self, 'gallery_stats') and self.gallery_stats:
            self.gallery_stats = None
        if hasattr(self, 'gallery_window') and self.gallery_window:
            self.gallery_window.close()
            self.gallery_window = None

    def _create_gallery_window(self):
        """Create and configure the gallery window with widgets."""
        self.gallery_window = QMainWindow(self)
        self.gallery_window.setWindowTitle(
            "Gallery Mode - Double-click to select, Press Escape or close to exit"
        )
        # Apply theme stylesheet to gallery_window to isolate from parent cascade
        if hasattr(self, '_current_theme'):
            self.gallery_window.setStyleSheet(get_stylesheet(self._current_theme))

        central_widget = QWidget()
        layout = QHBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Gallery widget (main area)
        self.full_gallery = GalleryWidget(show_size_slider=True)
        # Apply current theme to full gallery
        if hasattr(self, '_current_theme'):
            self.full_gallery.apply_theme(self._current_theme)
        self.full_gallery.set_save_dir(self.default_save_dir)
        self.full_gallery.set_image_list(self.m_img_list)
        self.full_gallery.image_selected.connect(
            lambda path: self.gallery_image_selected(path, source='full'))
        self.full_gallery.image_activated.connect(self._exit_gallery_and_load)
        layout.addWidget(self.full_gallery, stretch=4)

        # Stats panel (side)
        self.gallery_stats = StatsWidget()
        self.gallery_stats.refresh_btn.clicked.connect(self._refresh_all_statistics)
        self.gallery_stats.setMaximumWidth(300)
        self.gallery_stats.setMinimumWidth(250)
        layout.addWidget(self.gallery_stats, stretch=1)

        self.gallery_window.setCentralWidget(central_widget)

    def _exit_gallery_and_load(self, image_path):
        """Exit gallery mode and load the selected image."""
        self.actions.galleryMode.setChecked(False)
        self.toggle_gallery_mode(False)
        self.gallery_image_activated(image_path)

    def _refresh_full_gallery_statuses(self):
        """Update statuses for full-screen gallery using async worker."""
        if not (hasattr(self, 'full_gallery') and self.full_gallery):
            return

        # Apply cached statuses immediately for instant feedback
        cached_statuses = {p: self._annotation_status_cache[p]
                          for p in self.m_img_list if p in self._annotation_status_cache}
        if cached_statuses:
            self.full_gallery.update_all_statuses(cached_statuses)

        # Get uncached images for async processing
        uncached = [p for p in self.m_img_list if p not in self._annotation_status_cache]
        if not uncached:
            return

        # Cancel existing worker and start new async worker with new generation
        self._cleanup_status_worker()
        self._status_worker_gen += 1
        gen = self._status_worker_gen
        self._status_worker = StatusRefreshWorker(uncached, self.default_save_dir)
        self._status_worker.signals.batch_ready.connect(
            lambda s, g=gen: self._on_status_batch_ready(s, g))
        self._status_worker.signals.finished.connect(
            lambda g=gen: self._on_status_refresh_finished(g))
        self._status_worker.signals.error.connect(
            lambda e, g=gen: self._on_status_refresh_error(e, g))
        QThreadPool.globalInstance().start(self._status_worker)

    def _cleanup_status_worker(self):
        """Properly cleanup status worker and disconnect signals."""
        if hasattr(self, '_status_worker') and self._status_worker:
            self._status_worker.cancel()
            try:
                self._status_worker.signals.batch_ready.disconnect()
                self._status_worker.signals.finished.disconnect()
                self._status_worker.signals.error.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._status_worker = None

    def _on_status_batch_ready(self, statuses, gen):
        """Handle status batch from async worker."""
        # Ignore stale signals from old workers
        if gen != self._status_worker_gen:
            return
        # Early exit if gallery was closed
        if not (hasattr(self, 'full_gallery') and self.full_gallery):
            return
        # Update cache with computed statuses
        self._annotation_status_cache.update(statuses)
        # Update gallery UI
        self.full_gallery.update_all_statuses(statuses)

    def _on_status_refresh_finished(self, gen):
        """Handle status refresh completion."""
        if gen != self._status_worker_gen:
            return
        self._status_worker = None

    def _on_status_refresh_error(self, error_msg, gen):
        """Handle status worker errors."""
        if gen != self._status_worker_gen:
            return
        print(f"Status refresh worker error: {error_msg}")
        self._status_worker = None

    def populate_mode_actions(self):
        if self.beginner():
            tool, menu = self.actions.beginner, self.actions.beginnerContext
        else:
            tool, menu = self.actions.advanced, self.actions.advancedContext
        self.tools.clear()
        add_actions(self.tools, tool)
        self.canvas.menus[0].clear()
        add_actions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create, self.actions.create_polygon) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode, self.actions.create_polygon)
        add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_beginner(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.beginner)
        self.tools.add_expand_button()
        # Restore expanded state
        if self.settings.get(SETTING_TOOLBAR_EXPANDED, False):
            self.tools.set_expanded(True)

    def set_advanced(self):
        self.tools.clear()
        add_actions(self.tools, self.actions.advanced)
        self.tools.add_expand_button()
        # Restore expanded state
        if self.settings.get(SETTING_TOOLBAR_EXPANDED, False):
            self.tools.set_expanded(True)

    def set_dirty(self):
        self.dirty = True
        self.actions.save.setEnabled(True)
        self.update_save_status(saved=False)
        self.update_box_count()

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)
        self.actions.create_polygon.setEnabled(True)
        self.update_save_status(saved=True)

    def toggle_actions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for z in self.actions.lightActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)
        # Enable paste if clipboard has shapes and image is loaded
        if value and self.clipboard_shapes:
            self.actions.pasteFromClipboard.setEnabled(True)
        # Enable copy all if there are shapes
        if value and self.canvas.shapes:
            self.actions.copyAllToClipboard.setEnabled(True)

    def queue_event(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def update_status_bar(self):
        """Update all status bar widgets."""
        self.update_image_count()
        self.update_box_count()
        self.update_zoom_display()

    def update_image_count(self):
        """Update image counter in status bar."""
        if self.m_img_list and self.file_path:
            idx = self._path_to_idx.get(self.file_path, -1) + 1
            self.label_image_count.setText(f'Image: {idx} / {len(self.m_img_list)}')
        else:
            self.label_image_count.setText('Image: 0 / 0')

    def update_box_count(self):
        """Update annotation count in status bar."""
        count = len(self.canvas.shapes) if self.canvas else 0
        self.label_box_count.setText(f'Boxes: {count}')

    def update_zoom_display(self):
        """Update zoom level in status bar."""
        if self.zoom_widget:
            self.label_zoom.setText(f'Zoom: {self.zoom_widget.value()}%')

    def _update_save_status_style(self, saved):
        """Update save status indicator style based on theme."""
        from libs.utils.styles import get_theme_colors
        colors = get_theme_colors(self._current_theme)
        if saved:
            color = colors['status_saved']
            tooltip = 'Saved'
        else:
            color = colors['status_unsaved']
            tooltip = 'Unsaved changes'

        self.label_save_status.setStyleSheet(f'color: {color}; font-size: 14px;')
        self.label_save_status.setToolTip(tooltip)

    def update_save_status(self, saved=True):
        """Update save status indicator in status bar."""
        self._update_save_status_style(saved)

    def reset_state(self):
        self.items_to_shapes.clear()
        self.shapes_to_items.clear()
        self.rect_label_list.clear()
        self.poly_label_list.clear()
        self._update_tab_counts()
        self.file_path = None
        self.image_data = None
        self.label_file = None
        self.canvas.reset_state()
        self.label_coordinates.clear()
        self.combo_box.cb.clear()
        # Clear undo stack when loading new file
        self.undo_stack.clear()
        # Reset status bar widgets
        self.label_box_count.setText('Boxes: 0')
        self.update_save_status(saved=True)

    def current_item(self):
        """Return the currently selected item from either label list."""
        for lw in (self.rect_label_list, self.poly_label_list):
            items = lw.selectedItems()
            if items:
                return items[0]
        return None

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, file_path)

    def beginner(self):
        return self._beginner

    def advanced(self):
        return not self.beginner()

    def show_tutorial_dialog(self, browser='default', link=None):
        if link is None:
            link = self.screencast

        if browser.lower() == 'default':
            wb.open(link, new=2)
        elif browser.lower() == 'chrome' and self.os_name == 'Windows':
            if shutil.which(browser.lower()):  # 'chrome' not in wb._browsers in windows
                wb.register('chrome', None, wb.BackgroundBrowser('chrome'))
            else:
                chrome_path="D:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe"
                if os.path.isfile(chrome_path):
                    wb.register('chrome', None, wb.BackgroundBrowser(chrome_path))
            try:
                wb.get('chrome').open(link, new=2)
            except (wb.Error, KeyError):
                wb.open(link, new=2)
        elif browser.lower() in wb._browsers:
            wb.get(browser.lower()).open(link, new=2)

    def show_default_tutorial_dialog(self):
        self.show_tutorial_dialog(browser='default')

    def show_info_dialog(self):
        from libs.__init__ import __version__
        msg = u'Name:{0} \nApp Version:{1} \n{2} '.format(__appname__, __version__, sys.version_info)
        QMessageBox.information(self, u'Information', msg)

    def show_shortcuts_dialog(self):
        from libs.widgets.shortcutsDialog import ShortcutsDialog
        dialog = ShortcutsDialog(self.shortcut_config, self._action_map, self)
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)
        dialog.exec_()

    def create_shape(self):
        assert self.beginner()
        self.canvas.set_editing(False)
        self.actions.create.setEnabled(False)
        self.actions.create_polygon.setEnabled(True)

    def create_polygon_mode(self):
        """Switch to polygon drawing mode."""
        self.canvas.set_polygon_drawing(True)
        self.actions.create.setEnabled(True)
        self.actions.create_polygon.setEnabled(False)
        self.actions.editMode.setEnabled(True)

    def toggle_keypoint_mode(self):
        """Toggle keypoint annotation mode for the selected shape."""
        from libs.core.keypoint_config import get_template

        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.canvas.exit_keypoint_mode()
            self.keypoint_panel.hide()
            return

        shape = self.canvas.selected_shape
        if not shape or shape.shape_type != ShapeType.RECTANGLE:
            return

        template = get_template(shape.label)
        if not template:
            return

        template_name = shape.label.lower()
        kp_count = len(template['names'])

        if shape.keypoints is None:
            shape.keypoints = [None] * kp_count

        self.keypoint_panel.load_template(template_name)
        self.canvas.set_keypoint_mode(shape, template_name)
        self.keypoint_panel.set_keypoints(shape.keypoints)
        self.keypoint_panel.set_current_index(self.canvas._keypoint_index)
        self.keypoint_panel.show()

    def _on_keypoint_panel_click(self, index):
        """Handle click on a keypoint row in the panel."""
        if self.canvas.mode != self.canvas.KEYPOINT_MODE:
            self.toggle_keypoint_mode()
        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.canvas._keypoint_index = index
            self.keypoint_panel.set_current_index(index)
            self.canvas.update()

    def _on_shape_moved_keypoints(self):
        """Refresh the keypoint panel after a shape move."""
        if (self.canvas.mode == self.canvas.KEYPOINT_MODE
                and self.canvas._keypoint_shape):
            self.keypoint_panel.set_keypoints(
                self.canvas._keypoint_shape.keypoints)
            self.keypoint_panel.set_current_index(
                self.canvas._keypoint_index)

    def _on_polygon_vertices_edited(self, shape, old_points):
        """Capture polygon vertex edits for undo support."""
        cmd = EditPolygonVerticesCommand(
            self, shape, old_points, list(shape.points))
        self.undo_stack.push(cmd)
        self.set_dirty()

    def _on_shape_move_finished(self, shape, old_points):
        """Capture whole-shape moves / rectangle resizes for undo support."""
        cmd = MoveShapeCommand(self, shape, old_points, list(shape.points))
        self.undo_stack.push(cmd)
        self.set_dirty()

    def _on_keypoints_edited(self, shape, old_keypoints):
        """Capture keypoint mutations for undo support."""
        cmd = EditKeypointsCommand(
            self, shape, old_keypoints,
            list(shape.keypoints) if shape.keypoints else None)
        self.undo_stack.push(cmd)
        self.set_dirty()

    def toggle_drawing_sensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        self.actions.editMode.setEnabled(not drawing)
        self.actions.create_polygon.setEnabled(not drawing)
        if not drawing and self.beginner():
            # Cancel creation.
            print('Cancel creation.')
            self.canvas.set_editing(True)
            self.canvas.restore_cursor()
            self.actions.create.setEnabled(True)
            self.actions.create_polygon.setEnabled(True)

    def toggle_draw_mode(self, edit=True):
        self.canvas.set_editing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)
        self.actions.create_polygon.setEnabled(edit)

    def set_create_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(False)
        self.actions.create_polygon.setEnabled(True)

    def set_edit_mode(self):
        assert self.advanced()
        self.toggle_draw_mode(True)
        self.actions.create_polygon.setEnabled(True)
        self.label_selection_changed()

    def update_file_menu(self):
        curr_file_path = self.file_path

        def exists(filename):
            return os.path.exists(filename)
        menu = self.menus.recentFiles
        menu.clear()
        files = [f for f in self.recent_files if f !=
                 curr_file_path and exists(f)]
        for i, f in enumerate(files):
            icon = new_icon('labels')
            action = QAction(
                icon, '&%d %s' % (i + 1, QFileInfo(f).fileName()), self)
            action.triggered.connect(partial(self.load_recent, f))
            menu.addAction(action)

        # Add clear option if there are recent files
        if files:
            menu.addSeparator()
            clear_action = QAction(self.string_bundle.get_string('clearRecentFiles'), self)
            clear_action.triggered.connect(self.clear_recent_files)
            menu.addAction(clear_action)

    def clear_recent_files(self):
        self.recent_files.clear()
        self.update_file_menu()

    def pop_label_list_menu(self, point):
        sender = self.sender()
        if sender:
            self.menus.labelList.exec_(sender.mapToGlobal(point))
        else:
            self.menus.labelList.exec_(self.rect_label_list.mapToGlobal(point))

    def edit_label(self):
        if not self.canvas.editing():
            return
        item = self.current_item()
        if not item:
            return
        text = self.label_dialog.pop_up(item.text())
        if text is not None:
            item.setText(text)
            item.setBackground(generate_color_by_text(text))
            self.set_dirty()
            self.update_combo_box()

    # Tzutalin 20160906 : Add file list and dock to move faster
    def file_item_double_clicked(self, item=None):
        item_path = ustr(item.text())
        self.cur_img_idx = self._path_to_idx.get(item_path, 0)
        filename = self.m_img_list[self.cur_img_idx]
        if filename:
            self.load_file(filename)

    def file_item_clicked(self, item=None):
        """Handle single click on file list item - sync gallery selection."""
        # Skip if we're already in a gallery selection operation
        if hasattr(self, '_selecting_gallery') and self._selecting_gallery:
            return
        if item is not None:
            item_path = ustr(item.text())
            if item_path in self._path_to_idx:
                self.cur_img_idx = self._path_to_idx[item_path]
                self.gallery_widget.select_image(item_path)

    def gallery_image_selected(self, image_path, source=None):
        """Handle single click on gallery thumbnail - sync all views.

        Args:
            image_path: Path to the selected image
            source: 'dock' or 'full' to indicate which gallery triggered selection
        """
        # Prevent recursive calls
        if hasattr(self, '_selecting_gallery') and self._selecting_gallery:
            return
        self._selecting_gallery = True
        try:
            if image_path in self._path_to_idx:
                idx = self._path_to_idx[image_path]
                self.cur_img_idx = idx
                # Sync list selection using O(1) index lookup instead of O(n) loop
                self.file_list_widget.blockSignals(True)
                if idx < self.file_list_widget.count():
                    item = self.file_list_widget.item(idx)
                    if item:
                        self.file_list_widget.setCurrentItem(item)
                self.file_list_widget.blockSignals(False)
                # Sync gallery selections - skip the source gallery to avoid redundant updates
                if source != 'dock':
                    self.gallery_widget.select_image(image_path)
                if source != 'full' and hasattr(self, 'full_gallery') and self.full_gallery:
                    self.full_gallery.select_image(image_path)
        finally:
            self._selecting_gallery = False

    def gallery_image_activated(self, image_path):
        """Handle double-click on gallery thumbnail - load image."""
        if image_path in self._path_to_idx:
            self.cur_img_idx = self._path_to_idx[image_path]
            self.load_file(image_path)

    def on_file_view_tab_changed(self, index):
        """Handle tab switch between list and gallery view."""
        if index == 1:  # Gallery tab
            self._refresh_gallery_statuses()

    def _get_annotation_status(self, image_path, use_cache=True):
        """Determine annotation status for an image with optional caching."""
        # Check cache first for O(1) lookup
        if use_cache and image_path in self._annotation_status_cache:
            return self._annotation_status_cache[image_path]

        status = _probe_status(image_path, self.default_save_dir)

        # Cache the result
        self._annotation_status_cache[image_path] = status
        return status

    def _invalidate_status_cache(self, image_path=None):
        """Invalidate annotation status cache for a path or all paths."""
        if image_path:
            self._annotation_status_cache.pop(image_path, None)
        else:
            self._annotation_status_cache.clear()

    def _refresh_gallery_statuses(self):
        """Update all gallery thumbnail statuses using async worker."""
        if not hasattr(self, 'gallery_widget') or not self.gallery_widget:
            return

        # Apply cached statuses immediately
        cached = {p: self._annotation_status_cache[p]
                  for p in self.m_img_list if p in self._annotation_status_cache}
        if cached:
            self.gallery_widget.update_all_statuses(cached)

        # Get uncached images for async processing
        uncached = [p for p in self.m_img_list if p not in self._annotation_status_cache]
        if not uncached:
            return

        # Cancel existing worker and start new async worker with new generation
        self._cleanup_dock_status_worker()
        self._dock_status_worker_gen += 1
        gen = self._dock_status_worker_gen
        self._dock_status_worker = StatusRefreshWorker(uncached, self.default_save_dir)
        self._dock_status_worker.signals.batch_ready.connect(
            lambda s, g=gen: self._on_dock_status_batch_ready(s, g))
        self._dock_status_worker.signals.finished.connect(
            lambda g=gen: self._on_dock_status_finished(g))
        self._dock_status_worker.signals.error.connect(
            lambda e, g=gen: self._on_dock_status_error(e, g))
        QThreadPool.globalInstance().start(self._dock_status_worker)

    def _cleanup_dock_status_worker(self):
        """Cleanup dock gallery status worker."""
        if hasattr(self, '_dock_status_worker') and self._dock_status_worker:
            self._dock_status_worker.cancel()
            try:
                self._dock_status_worker.signals.batch_ready.disconnect()
                self._dock_status_worker.signals.finished.disconnect()
                self._dock_status_worker.signals.error.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._dock_status_worker = None

    def _on_dock_status_batch_ready(self, statuses, gen):
        """Handle status batch for dock gallery."""
        # Ignore stale signals from old workers
        if gen != self._dock_status_worker_gen:
            return
        if not hasattr(self, 'gallery_widget') or not self.gallery_widget:
            return
        self._annotation_status_cache.update(statuses)
        self.gallery_widget.update_all_statuses(statuses)

    def _on_dock_status_finished(self, gen):
        """Handle dock status refresh completion."""
        if gen != self._dock_status_worker_gen:
            return
        self._dock_status_worker = None

    def _on_dock_status_error(self, error_msg, gen):
        """Handle dock status worker errors."""
        if gen != self._dock_status_worker_gen:
            return
        print(f"Dock status worker error: {error_msg}")
        self._dock_status_worker = None

    def _update_current_image_gallery_status(self):
        """Update gallery status for current image after save/verify."""
        if self.file_path:
            # Invalidate cache for this file to get fresh status
            self._invalidate_status_cache(self.file_path)
            status = self._get_annotation_status(self.file_path)
            self.gallery_widget.update_status(self.file_path, status)
            # Also update full-screen gallery if active
            if hasattr(self, 'full_gallery') and self.full_gallery:
                self.full_gallery.update_status(self.file_path, status)

    # Add chris
    def button_state(self, item=None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        item = self.current_item()
        if not item:  # If not selected Item, take the last one from rect list
            if self.rect_label_list.count() > 0:
                item = self.rect_label_list.item(self.rect_label_list.count() - 1)
            elif self.poly_label_list.count() > 0:
                item = self.poly_label_list.item(self.poly_label_list.count() - 1)

        difficult = self.diffc_button.isChecked()

        shape = self.items_to_shapes.get(item)
        if shape is None:
            return

        # Checked and Update
        if difficult != shape.difficult:
            shape.difficult = difficult
            self.set_dirty()
        else:  # User probably changed item visibility
            self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)

    # React to canvas signals.
    def shape_selection_changed(self, selected=False):
        if self._no_selection_slot:
            self._no_selection_slot = False
        else:
            shape = self.canvas.selected_shape
            if shape:
                self.shapes_to_items[shape].setSelected(True)
            else:
                self.rect_label_list.clearSelection()
                self.poly_label_list.clearSelection()
        self.actions.delete.setEnabled(selected)
        self.actions.copy.setEnabled(selected)
        self.actions.copyToClipboard.setEnabled(selected)
        self.actions.edit.setEnabled(selected)
        self.actions.shapeLineColor.setEnabled(selected)
        self.actions.shapeFillColor.setEnabled(selected)
        # Enable paste if clipboard has shapes
        self.actions.pasteFromClipboard.setEnabled(len(self.clipboard_shapes) > 0)
        # Enable copy all if there are shapes
        self.actions.copyAllToClipboard.setEnabled(len(self.canvas.shapes) > 0)

        # Show/hide keypoint panel based on selection
        from libs.core.keypoint_config import get_template
        shape = self.canvas.selected_shape
        has_template = (shape is not None
                        and shape.shape_type == ShapeType.RECTANGLE
                        and get_template(shape.label) is not None)
        self.actions.keypoint_mode.setEnabled(has_template)
        if has_template and shape.keypoints:
            self.keypoint_panel.load_template(shape.label.lower())
            self.keypoint_panel.set_keypoints(shape.keypoints)
            self.keypoint_panel.show()
        else:
            self.keypoint_panel.hide()

    def add_label(self, shape, row=None):
        shape.paint_label = self.display_label_option.isChecked()
        item = HashableQListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        item.setBackground(generate_color_by_text(shape.label))
        self.items_to_shapes[item] = shape
        self.shapes_to_items[shape] = item
        # Route to the appropriate label list based on shape type
        target_list = self._label_list_for_shape(shape)
        # Restore at a specific row (undo of a delete) when given, else append.
        if row is not None and row >= 0:
            target_list.insertItem(row, item)
        else:
            target_list.addItem(item)
        self._update_tab_counts()
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)
        self.update_combo_box()

    def remove_label(self, shape):
        """Remove a shape's label-list item. Returns the row it occupied
        (or None) so a caller can restore the exact ordering on undo."""
        if shape is None:
            return None
        item = self.shapes_to_items[shape]
        # Remove from whichever list contains the item
        target_list = self._label_list_for_shape(shape)
        row = target_list.row(item)
        if row >= 0:
            target_list.takeItem(row)
        self._update_tab_counts()
        del self.shapes_to_items[shape]
        del self.items_to_shapes[item]
        self.update_combo_box()
        return row

    def load_labels(self, shapes):
        s = []
        # Scale factor for converting original coords to display coords (Issue #31)
        scale = self._image_scale_factor if hasattr(self, '_image_scale_factor') else 1.0

        for shape_data in shapes:
            # Handle 5-element (legacy), 6-element (with shape_type),
            # and 7-element (with keypoints) tuples
            if len(shape_data) == 7:
                label, points, line_color, fill_color, difficult, shape_type_str, kp_data = shape_data
            elif len(shape_data) == 6:
                label, points, line_color, fill_color, difficult, shape_type_str = shape_data
                kp_data = None
            else:
                label, points, line_color, fill_color, difficult = shape_data
                shape_type_str = 'rectangle'
                kp_data = None

            st = ShapeType.POLYGON if shape_type_str == 'polygon' else ShapeType.RECTANGLE
            shape = Shape(label=label, shape_type=st)
            for x, y in points:
                # Scale coordinates from original to display space
                x = x * scale
                y = y * scale

                # Ensure the labels are within the bounds of the image. If not, fix them.
                x, y, snapped = self.canvas.snap_point_to_canvas(x, y)
                if snapped:
                    self.set_dirty()

                shape.add_point(QPointF(x, y))
            shape.difficult = difficult
            if kp_data:
                shape.keypoints = [
                    (kp[0] * scale, kp[1] * scale, kp[2])
                    if kp is not None else None
                    for kp in kp_data
                ]
            shape.close()
            s.append(shape)

            if line_color:
                shape.line_color = QColor(*line_color)
            else:
                shape.line_color = generate_color_by_text(label)

            if fill_color:
                shape.fill_color = QColor(*fill_color)
            else:
                shape.fill_color = generate_color_by_text(label)

            self.add_label(shape)
        self.update_combo_box()
        self.canvas.load_shapes(s)

    def update_combo_box(self):
        # Get the unique labels from both label lists and add them to the Combobox.
        items_text_list = []
        for lw in (self.rect_label_list, self.poly_label_list):
            for i in range(lw.count()):
                items_text_list.append(str(lw.item(i).text()))

        unique_text_list = list(set(items_text_list))
        # Add a null row for showing all the labels
        unique_text_list.append("")
        unique_text_list.sort()

        self.combo_box.update_items(unique_text_list)

    def _label_list_for_shape(self, shape):
        """Return the appropriate QListWidget for the given shape's type."""
        if hasattr(shape, 'shape_type') and shape.shape_type == ShapeType.POLYGON:
            return self.poly_label_list
        return self.rect_label_list

    def _update_tab_counts(self):
        """Update the tab titles to reflect the count of shapes in each list."""
        rect_count = self.rect_label_list.count()
        poly_count = self.poly_label_list.count()
        self.label_tab_widget.setTabText(0, f'Rectangles ({rect_count})')
        self.label_tab_widget.setTabText(1, f'Polygons ({poly_count})')

    def _check_polygon_degradation(self, format_name):
        """Warn the user if polygons will be saved as bounding boxes.

        Args:
            format_name: Display name of the target format.

        Returns:
            True if saving should proceed, False to cancel.
        """
        polygon_count = sum(1 for s in self.canvas.shapes
                            if s.shape_type == ShapeType.POLYGON)
        if polygon_count == 0:
            return True

        get_str = lambda str_id: self.string_bundle.get_string(str_id)
        msg = get_str('polygonDegradeWarning') % (polygon_count, format_name)
        reply = QMessageBox.question(
            self, 'Polygon Degradation', msg,
            QMessageBox.Yes | QMessageBox.No)
        return reply == QMessageBox.Yes

    def save_labels(self, annotation_file_path):
        annotation_file_path = ustr(annotation_file_path)
        if self.label_file is None:
            self.label_file = LabelFile()
            self.label_file.verified = self.canvas.verified

        # Scale factor for converting display coords to original coords (Issue #31)
        inv_scale = 1.0 / self._image_scale_factor if hasattr(self, '_image_scale_factor') and self._image_scale_factor != 0 else 1.0

        def format_shape(s):
            # Scale coordinates from display space to original image space
            scaled_points = [(p.x() * inv_scale, p.y() * inv_scale) for p in s.points]
            result = dict(
                label=s.label,
                line_color=s.line_color.getRgb(),
                fill_color=s.fill_color.getRgb(),
                points=scaled_points,
                difficult=s.difficult,
                shape_type=s.shape_type.value,
            )
            if s.keypoints is not None:
                result['keypoints'] = [
                    (kp[0] * inv_scale, kp[1] * inv_scale, kp[2])
                    if kp is not None else None
                    for kp in s.keypoints
                ]
            return result

        # Check for polygon degradation when saving to formats that don't support polygons
        degradation_formats = {
            LabelFileFormat.YOLO: FORMAT_YOLO,
            LabelFileFormat.CREATE_ML: FORMAT_CREATEML,
        }
        if self.label_file_format in degradation_formats:
            if not self._check_polygon_degradation(degradation_formats[self.label_file_format]):
                return False

        shapes = [format_shape(shape) for shape in self.canvas.shapes]
        # Can add different annotation formats here
        try:
            if self.label_file_format == LabelFileFormat.PASCAL_VOC:
                if annotation_file_path[-4:].lower() != ".xml":
                    annotation_file_path += XML_EXT
                self.label_file.save_pascal_voc_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                       self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO:
                if annotation_file_path[-4:].lower() != ".txt":
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_format(annotation_file_path, shapes, self.file_path, self.image_data, self.label_hist,
                                                 self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.CREATE_ML:
                if annotation_file_path[-5:].lower() != ".json":
                    annotation_file_path += JSON_EXT
                self.label_file.save_create_ml_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                      self.label_hist, self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.COCO:
                if annotation_file_path[-5:].lower() != ".json":
                    annotation_file_path += JSON_EXT
                self.label_file.save_coco_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                 self.label_hist, self.line_color.getRgb(), self.fill_color.getRgb())
            elif self.label_file_format == LabelFileFormat.YOLO_SEG:
                if annotation_file_path[-4:].lower() != ".txt":
                    annotation_file_path += TXT_EXT
                self.label_file.save_yolo_seg_format(annotation_file_path, shapes, self.file_path, self.image_data,
                                                     self.label_hist, self.line_color.getRgb(), self.fill_color.getRgb())
            else:
                self.label_file.save(annotation_file_path, shapes, self.file_path, self.image_data,
                                     self.line_color.getRgb(), self.fill_color.getRgb())
            print('Image:{0} -> Annotation:{1}'.format(self.file_path, annotation_file_path))
            return True
        except LabelFileError as e:
            self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
            return False

    def copy_selected_shape(self):
        shape = self.canvas.copy_selected_shape()
        self.add_label(shape)

        # Push command for undo support (shape already created, so just push)
        cmd = CreateShapeCommand(self, shape)
        self.undo_stack.push(cmd)

        # fix copy and delete
        self.shape_selection_changed(True)

    def copy_to_clipboard(self):
        """Copy selected shape to clipboard for pasting across images."""
        if self.canvas.selected_shape is None:
            return
        # Store a copy of the selected shape
        self.clipboard_shapes = [self.canvas.selected_shape.copy()]
        self.actions.pasteFromClipboard.setEnabled(True)
        self.statusBar().showMessage(f'Copied 1 annotation to clipboard', 3000)

    def copy_all_to_clipboard(self):
        """Copy all shapes to clipboard for pasting across images."""
        if not self.canvas.shapes:
            return
        # Store copies of all shapes
        self.clipboard_shapes = [shape.copy() for shape in self.canvas.shapes]
        self.actions.pasteFromClipboard.setEnabled(True)
        self.statusBar().showMessage(f'Copied {len(self.clipboard_shapes)} annotations to clipboard', 3000)

    def paste_from_clipboard(self):
        """Paste shapes from clipboard to current image."""
        if not self.clipboard_shapes:
            return
        if not self.canvas.pixmap or self.canvas.pixmap.isNull():
            return

        for clipboard_shape in self.clipboard_shapes:
            # Create a new copy for each paste
            shape = clipboard_shape.copy()
            # Add shape to canvas
            self.canvas.shapes.append(shape)
            self.add_label(shape)
            # Push command for undo support
            cmd = CreateShapeCommand(self, shape)
            self.undo_stack.push(cmd)

        self.set_dirty()
        self.canvas.update()
        self.update_box_count()
        self.statusBar().showMessage(f'Pasted {len(self.clipboard_shapes)} annotations', 3000)

    def combo_selection_changed(self, index):
        text = self.combo_box.cb.itemText(index)
        for lw in (self.rect_label_list, self.poly_label_list):
            for i in range(lw.count()):
                if text == "":
                    lw.item(i).setCheckState(2)
                elif text != lw.item(i).text():
                    lw.item(i).setCheckState(0)
                else:
                    lw.item(i).setCheckState(2)

    def default_label_combo_selection_changed(self, index):
        self.default_label=self.label_hist[index]

    def label_selection_changed(self):
        # Guard against re-entrant calls from multiple signals (itemActivated + itemSelectionChanged)
        if hasattr(self, '_updating_label_selection') and self._updating_label_selection:
            return
        self._updating_label_selection = True
        try:
            item = self.current_item()
            if item and self.canvas.editing():
                self._no_selection_slot = True
                self.canvas.select_shape(self.items_to_shapes[item])
                shape = self.items_to_shapes[item]
                # Add Chris
                self.diffc_button.setChecked(shape.difficult)
        finally:
            self._updating_label_selection = False

    def label_item_changed(self, item):
        shape = self.items_to_shapes[item]
        label = item.text()
        if label != shape.label:
            old_label = shape.label
            shape.label = item.text()
            shape.line_color = generate_color_by_text(shape.label)

            # Push command for undo support (change already made, so just push)
            cmd = EditLabelCommand(self, shape, old_label, label)
            self.undo_stack.push(cmd)

            self.set_dirty()
        else:  # User probably changed item visibility
            self.canvas.set_shape_visible(shape, item.checkState() == Qt.Checked)

    # Callback functions:
    def new_shape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        if not self.use_default_label_checkbox.isChecked():
            if len(self.label_hist) > 0:
                self.label_dialog = LabelDialog(
                    parent=self, list_item=self.label_hist)
                if hasattr(self, '_current_theme'):
                    self.label_dialog.apply_theme(self._current_theme)

            # Sync single class mode from PR#106
            if self.single_class_mode.isChecked() and self.lastLabel:
                text = self.lastLabel
            else:
                text = self.label_dialog.pop_up(text=self.prev_label_text)
                self.lastLabel = text
        else:
            text = self.default_label

        # Add Chris
        self.diffc_button.setChecked(False)
        if text is not None:
            self.prev_label_text = text
            generate_color = generate_color_by_text(text)
            shape = self.canvas.set_last_label(text, generate_color)
            self.add_label(shape)

            # Push command for undo support (shape already created, so just push)
            cmd = CreateShapeCommand(self, shape)
            self.undo_stack.push(cmd)

            if self.beginner():  # Switch to edit mode.
                self.canvas.set_editing(True)
                self.actions.create.setEnabled(True)
                self.actions.create_polygon.setEnabled(True)
            else:
                self.actions.editMode.setEnabled(True)
                self.actions.create_polygon.setEnabled(True)
            self.set_dirty()
            self._update_current_image_stats()

            if text not in self.label_hist:
                self.label_hist.append(text)
        else:
            # self.canvas.undoLastLine()
            self.canvas.reset_all_lines()

    def scroll_request(self, delta, orientation):
        units = - delta / (8 * 15)
        bar = self.scroll_bars[orientation]
        bar.setValue(int(bar.value() + bar.singleStep() * units))

    def set_zoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.MANUAL_ZOOM
        # Arithmetic on scaling factor often results in float
        # Convert to int to avoid type errors
        self.zoom_widget.setValue(int(value))

    def add_zoom(self, increment=10):
        self.set_zoom(self.zoom_widget.value() + increment)

    def zoom_request(self, delta):
        # get the current scrollbar positions
        # calculate the percentages ~ coordinates
        h_bar = self.scroll_bars[Qt.Horizontal]
        v_bar = self.scroll_bars[Qt.Vertical]

        # get the current maximum, to know the difference after zooming
        h_bar_max = h_bar.maximum()
        v_bar_max = v_bar.maximum()

        # get the cursor position and canvas size
        # calculate the desired movement from 0 to 1
        # where 0 = move left
        #       1 = move right
        # up and down analogous
        cursor = QCursor()
        pos = cursor.pos()
        relative_pos = QWidget.mapFromGlobal(self, pos)

        cursor_x = relative_pos.x()
        cursor_y = relative_pos.y()

        w = self.scroll_area.width()
        h = self.scroll_area.height()

        # the scaling from 0 to 1 has some padding
        # you don't have to hit the very leftmost pixel for a maximum-left movement
        margin = 0.1
        move_x = (cursor_x - margin * w) / (w - 2 * margin * w)
        move_y = (cursor_y - margin * h) / (h - 2 * margin * h)

        # clamp the values from 0 to 1
        move_x = min(max(move_x, 0), 1)
        move_y = min(max(move_y, 0), 1)

        # zoom in
        units = delta // (8 * 15)
        scale = 10
        self.add_zoom(scale * units)

        # get the difference in scrollbar values
        # this is how far we can move
        d_h_bar_max = h_bar.maximum() - h_bar_max
        d_v_bar_max = v_bar.maximum() - v_bar_max

        # get the new scrollbar values
        new_h_bar_value = int(h_bar.value() + move_x * d_h_bar_max)
        new_v_bar_value = int(v_bar.value() + move_y * d_v_bar_max)

        h_bar.setValue(new_h_bar_value)
        v_bar.setValue(new_v_bar_value)

    def light_request(self, delta):
        self.add_light(5*delta // (8 * 15))

    def set_fit_window(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoom_mode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_fit_width(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoom_mode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjust_scale()

    def set_light(self, value):
        self.actions.lightOrg.setChecked(int(value) == 50)
        # Arithmetic on scaling factor often results in float
        # Convert to int to avoid type errors
        self.light_widget.setValue(int(value))

    def add_light(self, increment=10):
        self.set_light(self.light_widget.value() + increment)

    def toggle_polygons(self, value):
        for item, shape in self.items_to_shapes.items():
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def load_file(self, file_path=None):
        """Load the specified file, or the last opened file if None."""
        self.reset_state()
        self.canvas.setEnabled(False)
        if file_path is None:
            file_path = self.settings.get(SETTING_FILENAME)
        # Make sure that filePath is a regular python string, rather than QString
        file_path = ustr(file_path)

        # Fix bug: An  index error after select a directory when open a new file.
        unicode_file_path = ustr(file_path)
        unicode_file_path = os.path.abspath(unicode_file_path)
        # Tzutalin 20160906 : Add file list and dock to move faster
        # Highlight the file item
        if unicode_file_path and self.file_list_widget.count() > 0:
            if unicode_file_path in self._path_to_idx:
                index = self._path_to_idx[unicode_file_path]
                file_widget_item = self.file_list_widget.item(index)
                file_widget_item.setSelected(True)
                # Sync gallery selection
                self.gallery_widget.select_image(unicode_file_path)
            else:
                self.file_list_widget.clear()
                self.m_img_list.clear()

        if unicode_file_path and os.path.exists(unicode_file_path):
            if LabelFile.is_label_file(unicode_file_path):
                # Annotation files cannot be opened directly: in this fork
                # LabelFile is a write-only dispatcher with no reader and no
                # embedded image, so there is nothing to display. Report a
                # clear error rather than crashing. Open the corresponding
                # image instead; its annotations load automatically.
                self.error_message(
                    u'Cannot open annotation file',
                    (u"<p><b>%s</b> is an annotation file, not an image.</p>"
                     u"<p>Open the image it describes instead - its "
                     u"annotations will load automatically.</p>")
                    % unicode_file_path)
                self.status("Cannot open annotation file %s" % unicode_file_path)
                return False
            else:
                # Load image with memory-efficient downsampling for large images
                self.label_file = None
                self.canvas.verified = False

                # Use QImageReader for memory-efficient loading
                reader = QImageReader(unicode_file_path)
                reader.setAutoTransform(True)
                original_size = reader.size()

                if not original_size.isValid():
                    self.error_message(u'Error opening file',
                                       u"<p>Make sure <i>%s</i> is a valid image file." % unicode_file_path)
                    self.status("Error reading %s" % unicode_file_path)
                    return False

                # Downsample if larger than 2048px on either dimension (Issue #31)
                MAX_DISPLAY_DIM = 2048
                if original_size.width() > MAX_DISPLAY_DIM or original_size.height() > MAX_DISPLAY_DIM:
                    scaled_size = original_size.scaled(MAX_DISPLAY_DIM, MAX_DISPLAY_DIM, Qt.KeepAspectRatio)
                    reader.setScaledSize(scaled_size)
                    self._image_scale_factor = scaled_size.width() / original_size.width()
                else:
                    self._image_scale_factor = 1.0

                self._original_image_size = original_size
                image = reader.read()

                if image.isNull():
                    self.error_message(u'Error opening file',
                                       u"<p>Make sure <i>%s</i> is a valid image file." % unicode_file_path)
                    self.status("Error reading %s" % unicode_file_path)
                    return False

                # Don't store full image data - saves memory
                self.image_data = None

            # Apply review lock based on verified state
            if self.lock_on_verify_option.isChecked():
                self.canvas.locked = self.canvas.verified
            else:
                self.canvas.locked = False

            self.status("Loaded %s" % os.path.basename(unicode_file_path))
            self.image = image
            self.file_path = unicode_file_path
            self.canvas.load_pixmap(QPixmap.fromImage(image))
            if self.label_file:
                self.load_labels(self.label_file.shapes)
            self.set_clean()
            self.canvas.setEnabled(True)
            if hasattr(self, 'show_grid_option'):
                self.canvas._grid_enabled = self.show_grid_option.isChecked()
                checked_action = self.grid_size_group.checkedAction()
                self.canvas._grid_size = checked_action.data() if checked_action else 32
                self.canvas._edge_alignment = self.edge_alignment_option.isChecked()
            self.adjust_scale(initial=True)
            self.paint_canvas()
            self.add_recent_file(self.file_path)
            self.toggle_actions(True)
            self.show_bounding_box_from_annotation_file(self.file_path)

            counter = self.counter_str()
            self.setWindowTitle(__appname__ + ' ' + file_path + ' ' + counter)

            # Update status bar widgets
            self.update_status_bar()
            self.update_save_status(saved=True)

            # Default : select last item if there is at least one item
            if self.rect_label_list.count():
                self.rect_label_list.setCurrentItem(
                    self.rect_label_list.item(self.rect_label_list.count() - 1))
                self.rect_label_list.item(self.rect_label_list.count() - 1).setSelected(True)
            elif self.poly_label_list.count():
                self.poly_label_list.setCurrentItem(
                    self.poly_label_list.item(self.poly_label_list.count() - 1))
                self.poly_label_list.item(self.poly_label_list.count() - 1).setSelected(True)

            self.canvas.setFocus(True)
            self._update_current_image_stats()
            return True
        return False

    def counter_str(self):
        """
        Converts image counter to string representation.
        """
        return '[{} / {}]'.format(self.cur_img_idx + 1, self.img_count)

    def show_bounding_box_from_annotation_file(self, file_path):
        if self.default_save_dir is not None:
            basename = os.path.basename(os.path.splitext(file_path)[0])
            xml_path = os.path.join(self.default_save_dir, basename + XML_EXT)
            txt_path = os.path.join(self.default_save_dir, basename + TXT_EXT)
            json_path = os.path.join(self.default_save_dir, basename + JSON_EXT)
        else:
            xml_path = os.path.splitext(file_path)[0] + XML_EXT
            txt_path = os.path.splitext(file_path)[0] + TXT_EXT
            json_path = os.path.splitext(file_path)[0] + JSON_EXT

        # Dispatch based on current format for unambiguous types
        if self.label_file_format == LabelFileFormat.COCO:
            if os.path.isfile(json_path):
                self.load_coco_json_by_filename(json_path, file_path)
                return
        elif self.label_file_format == LabelFileFormat.YOLO_SEG:
            if os.path.isfile(txt_path):
                self.load_yolo_seg_by_filename(txt_path)
                return

        # Fallback: auto-detect by file extension priority
        # PascalXML > YOLO > CreateML
        if os.path.isfile(xml_path):
            self.load_pascal_xml_by_filename(xml_path)
        elif os.path.isfile(txt_path):
            self.load_yolo_txt_by_filename(txt_path)
        elif os.path.isfile(json_path):
            self.load_create_ml_json_by_filename(json_path, file_path)

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoom_mode != self.MANUAL_ZOOM:
            self.adjust_scale()
        super(MainWindow, self).resizeEvent(event)

    def paint_canvas(self):
        assert not self.image.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoom_widget.value()
        self.canvas.overlay_color = self.light_widget.color()
        self.canvas.label_font_size = int(0.02 * max(self.image.width(), self.image.height()))
        self.canvas.adjustSize()
        self.canvas.update()

    def adjust_scale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoom_mode]()
        self.zoom_widget.setValue(int(100 * value))

    def scale_fit_window(self):
        """Figure out the size of the pixmap in order to fit the main widget."""
        return view_scaling.fit_window_scale(
            self.centralWidget().width(), self.centralWidget().height(),
            self.canvas.pixmap.width(), self.canvas.pixmap.height())

    def scale_fit_width(self):
        return view_scaling.fit_width_scale(
            self.centralWidget().width(), self.canvas.pixmap.width())

    def closeEvent(self, event):
        if not self.may_continue():
            event.ignore()
        settings = self.settings
        # If it loads images from dir, don't load it at the beginning
        if self.dir_name is None:
            settings[SETTING_FILENAME] = self.file_path if self.file_path else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        settings[SETTING_WIN_STATE] = self.saveState()
        settings[SETTING_LINE_COLOR] = self.line_color
        settings[SETTING_FILL_COLOR] = self.fill_color
        settings[SETTING_RECENT_FILES] = self.recent_files
        settings[SETTING_ADVANCE_MODE] = not self._beginner
        settings[SETTING_GALLERY_MODE] = self.gallery_mode_enabled
        if self.default_save_dir and os.path.exists(self.default_save_dir):
            settings[SETTING_SAVE_DIR] = ustr(self.default_save_dir)
        else:
            settings[SETTING_SAVE_DIR] = ''

        if self.last_open_dir and os.path.exists(self.last_open_dir):
            settings[SETTING_LAST_OPEN_DIR] = self.last_open_dir
        else:
            settings[SETTING_LAST_OPEN_DIR] = ''

        settings[SETTING_AUTO_SAVE] = self.auto_saving.isChecked()
        settings[SETTING_AUTO_SAVE_ENABLED] = self.auto_save_enabled.isChecked()
        settings[SETTING_AUTO_SAVE_INTERVAL] = self._get_current_auto_save_interval()
        settings[SETTING_SINGLE_CLASS] = self.single_class_mode.isChecked()
        settings[SETTING_PAINT_LABEL] = self.display_label_option.isChecked()
        settings[SETTING_DRAW_SQUARE] = self.draw_squares_option.isChecked()
        settings[SETTING_LOCK_ON_VERIFY] = self.lock_on_verify_option.isChecked()
        settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format
        settings[SETTING_TOOLBAR_EXPANDED] = self.tools.is_expanded()
        settings[SETTING_DARK_MODE] = self.dark_mode_action.isChecked()
        settings[SETTING_GRID_ENABLED] = self.show_grid_option.isChecked()
        settings[SETTING_GRID_SIZE] = self.canvas._grid_size if self.canvas else 32
        settings[SETTING_EDGE_ALIGNMENT] = self.edge_alignment_option.isChecked()
        settings[SETTING_SHORTCUTS] = self.shortcut_config.to_dict()
        settings.save()

    def load_recent(self, filename):
        if self.may_continue():
            self.load_file(filename)

    def scan_all_images(self, folder_path):
        extensions = ['.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        images = []

        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relative_path = os.path.join(root, file)
                    path = ustr(os.path.abspath(relative_path))
                    images.append(path)
        natural_sort(images, key=lambda x: x.lower())
        return images

    def change_save_dir_dialog(self, _value=False):
        if self.default_save_dir is not None:
            path = ustr(self.default_save_dir)
        else:
            path = '.'

        dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                         '%s - Save annotations to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                         | QFileDialog.DontResolveSymlinks))

        if dir_path is not None and len(dir_path) > 1:
            self.default_save_dir = dir_path
            # Clear status cache since annotation directory changed
            self._invalidate_status_cache()
            # Update gallery to reload thumbnails with annotations from new dir
            self.gallery_widget.set_save_dir(self.default_save_dir)

        self.show_bounding_box_from_annotation_file(self.file_path)

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.default_save_dir))
        self.statusBar().show()


    def open_annotation_dialog(self, _value=False):
        if self.file_path is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().show()
            return

        path = os.path.dirname(ustr(self.file_path))\
            if self.file_path else '.'
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            filters = "Open Annotation XML file (%s)" % ' '.join(['*.xml'])
            filename = ustr(QFileDialog.getOpenFileName(self, '%s - Choose a xml file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]
            self.load_pascal_xml_by_filename(filename)

        elif self.label_file_format == LabelFileFormat.CREATE_ML:
            
            filters = "Open Annotation JSON file (%s)" % ' '.join(['*.json'])
            filename = ustr(QFileDialog.getOpenFileName(self, '%s - Choose a json file' % __appname__, path, filters))
            if filename:
                if isinstance(filename, (tuple, list)):
                    filename = filename[0]

            self.load_create_ml_json_by_filename(filename, self.file_path)         
        

    def open_dir_dialog(self, _value=False, dir_path=None, silent=False):
        if not self.may_continue():
            return

        default_open_dir_path = dir_path if dir_path else '.'
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            default_open_dir_path = self.last_open_dir
        else:
            default_open_dir_path = os.path.dirname(self.file_path) if self.file_path else '.'
        if silent != True:
            target_dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                                    '%s - Open Directory' % __appname__, default_open_dir_path,
                                                                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        else:
            target_dir_path = ustr(default_open_dir_path)
        self.last_open_dir = target_dir_path
        self.import_dir_images(target_dir_path)
        # Only set default_save_dir if not already set (e.g., from command line)
        if self.default_save_dir is None:
            self.default_save_dir = target_dir_path
        if self.file_path:
            self.show_bounding_box_from_annotation_file(file_path=self.file_path)

    def check_label_consistency(self):
        """Open dialog to check for label consistency issues in the dataset."""
        if not self.dir_name:
            self.error_message(
                'No Directory',
                'Please open a directory with images first.'
            )
            return

        dialog = LabelCheckerDialog(self)
        dialog.set_data(
            predefined_classes=self.label_hist,
            annotations_dir=self.dir_name,
            save_dir=self.default_save_dir
        )
        # Apply current theme before showing
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)
        dialog.fix_requested.connect(self._apply_label_fix)
        dialog.exec_()

    def _apply_label_fix(self, old_label, new_label):
        """Apply a label fix across annotations.

        Args:
            old_label: The label to replace
            new_label: The replacement label
        """
        if not self.dir_name:
            return

        # This would need to iterate through all annotation files
        # and replace old_label with new_label
        # For now, just log - full implementation would update files
        print(f"Label fix requested: '{old_label}' → '{new_label}'")
        self.statusBar().showMessage(
            f"Label fix: '{old_label}' → '{new_label}' (reload to see changes)",
            5000
        )

    def apply_status_filter(self, index):
        """Filter file list by annotation status.

        Args:
            index: Filter combo box index. 0=All, 1=Annotated,
                   2=Verified, 3=Unannotated.
        """
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            img_path = item.text()
            show = True
            if index == 1:  # Annotated Only
                show = self._has_annotation(img_path)
            elif index == 2:  # Verified Only
                show = self._is_verified(img_path)
            elif index == 3:  # Unannotated Only
                show = not self._has_annotation(img_path)
            item.setHidden(not show)

    def _has_annotation(self, img_path):
        """Check if image has an annotation file.

        Args:
            img_path: Path to the image file.

        Returns:
            True if an annotation file exists for the image.
        """
        basename = os.path.splitext(os.path.basename(img_path))[0]
        save_dir = self.default_save_dir or os.path.dirname(img_path)
        for ext in [XML_EXT, TXT_EXT, JSON_EXT]:
            if os.path.isfile(os.path.join(save_dir, basename + ext)):
                return True
            if os.path.isfile(os.path.splitext(img_path)[0] + ext):
                return True
        return False

    def _is_verified(self, img_path):
        """Check if image annotation is verified.

        Args:
            img_path: Path to the image file.

        Returns:
            True if the annotation is marked as verified.
        """
        basename = os.path.splitext(os.path.basename(img_path))[0]
        save_dir = self.default_save_dir or os.path.dirname(img_path)
        xml_path = os.path.join(save_dir, basename + XML_EXT)
        if not os.path.isfile(xml_path):
            xml_path = os.path.splitext(img_path)[0] + XML_EXT
        if os.path.isfile(xml_path):
            try:
                reader = PascalVocReader(xml_path)
                return reader.verified
            except Exception:
                pass
        return False

    def batch_verify(self):
        """Open dialog to batch verify or unverify all annotated images."""
        if not self.m_img_list:
            return

        annotated = sum(
            1 for img in self.m_img_list if self._has_annotation(img))

        from libs.widgets.batchVerifyDialog import BatchVerifyDialog
        dialog = BatchVerifyDialog(
            self, len(self.m_img_list), annotated)
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)

        if dialog.exec_() != QDialog.Accepted:
            return

        verify = dialog.verify_mode
        count, failures = self._apply_batch_verify(verify)

        action_label = 'Verified' if verify else 'Unverified'
        self.statusBar().showMessage(
            f'{action_label} {count} images', 3000)
        if failures:
            # Surface the files we could not update instead of silently
            # dropping them from the reported count.
            sample = '\n'.join(
                '- %s: %s' % (os.path.basename(p), reason)
                for p, reason in failures[:10])
            if len(failures) > 10:
                sample += '\n... and %d more' % (len(failures) - 10)
            self.error_message(
                f'{action_label} with errors',
                (f'<p>{action_label} {count} image(s); {len(failures)} could '
                 f'not be updated:</p><pre>{sample}</pre>'))
        if self.file_path:
            self.load_file(self.file_path)

    def _apply_batch_verify(self, verify):
        """Set/clear the PASCAL VOC ``verified`` flag across annotated images.

        Returns:
            (count, failures) where ``count`` is the number of images updated
            and ``failures`` is a list of (image_path, reason) for images that
            could not be updated - corrupt/unreadable XML, or a non-VOC
            annotation whose format has no verified flag.
        """
        import xml.etree.ElementTree as ET
        count = 0
        failures = []
        for img_path in self.m_img_list:
            if not self._has_annotation(img_path):
                continue
            basename = os.path.splitext(os.path.basename(img_path))[0]
            save_dir = self.default_save_dir or os.path.dirname(img_path)
            xml_path = os.path.join(save_dir, basename + XML_EXT)
            if not os.path.isfile(xml_path):
                xml_path = os.path.splitext(img_path)[0] + XML_EXT
            if not os.path.isfile(xml_path):
                failures.append((img_path, 'not a PASCAL VOC annotation'))
                continue
            try:
                tree = ET.parse(xml_path)
                root = tree.getroot()
                if verify:
                    root.set('verified', 'yes')
                else:
                    root.attrib.pop('verified', None)
                tree.write(xml_path)
                count += 1
            except (ET.ParseError, OSError) as e:
                failures.append((img_path, str(e)))
        return count, failures

    def split_dataset(self):
        """Open dialog to split dataset into train/val/test sets."""
        if not self.m_img_list:
            QMessageBox.warning(
                self, 'Split Dataset',
                'No images loaded. Open a directory first.')
            return

        from libs.widgets.splitDialog import SplitDialog
        default_dir = self.default_save_dir or (
            os.path.dirname(self.m_img_list[0]) if self.m_img_list else '')
        dialog = SplitDialog(self, len(self.m_img_list), default_dir)
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)

        if dialog.exec_() != QDialog.Accepted:
            return

        if not dialog.output_dir:
            QMessageBox.warning(
                self, 'Split Dataset',
                'Please select an output directory.')
            return

        from libs.tools.dataset_splitter import split_dataset, execute_split

        splits = split_dataset(
            self.m_img_list,
            dialog.ratios,
            seed=dialog.seed,
            stratified=dialog.stratified,
            save_dir=self.default_save_dir,
        )

        manifest_path = execute_split(
            splits,
            dialog.output_dir,
            save_dir=self.default_save_dir,
            copy=dialog.copy_mode,
        )

        counts = {k: len(v) for k, v in splits.items()}
        QMessageBox.information(
            self, 'Split Complete',
            f'Dataset split into:\n'
            f'  Train: {counts["train"]} images\n'
            f'  Val: {counts["val"]} images\n'
            f'  Test: {counts["test"]} images\n\n'
            f'Manifest: {manifest_path}'
        )

    def import_dir_images(self, dir_path):
        if not self.may_continue() or not dir_path:
            return

        self.last_open_dir = dir_path
        self.dir_name = dir_path
        self.file_path = None
        self.file_list_widget.clear()

        # Show progress dialog for scanning
        progress = QProgressDialog("Scanning directory...", "Cancel", 0, 0, self)
        progress.setWindowTitle("Loading Images")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(500)  # Only show if operation takes > 500ms
        progress.setValue(0)
        QApplication.processEvents()

        self.m_img_list = self.scan_all_images(dir_path)
        self._path_to_idx = {path: idx for idx, path in enumerate(self.m_img_list)}
        self._annotation_status_cache.clear()  # Clear cache for new directory
        self.img_count = len(self.m_img_list)

        if progress.wasCanceled():
            progress.close()
            return

        # Update progress for file list population
        if self.img_count > 100:
            progress.setLabelText(f"Loading {self.img_count} images...")
            progress.setMaximum(self.img_count)

        # Populate file list widget
        for i, imgPath in enumerate(self.m_img_list):
            item = QListWidgetItem(imgPath)
            self.file_list_widget.addItem(item)
            if self.img_count > 100 and i % 50 == 0:
                progress.setValue(i)
                QApplication.processEvents()
                if progress.wasCanceled():
                    progress.close()
                    return

        progress.setValue(self.img_count)

        # Populate gallery widget with annotation directory
        self.gallery_widget.set_save_dir(self.default_save_dir)
        self.gallery_widget.set_image_list(self.m_img_list)
        self._refresh_gallery_statuses()

        # Update full-screen gallery if active
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.set_save_dir(self.default_save_dir)
            self.full_gallery.set_image_list(self.m_img_list)
            self._refresh_full_gallery_statuses()

        progress.close()

        # Update image count in status bar
        self.update_image_count()

        # Refresh statistics (Issue #19)
        self._refresh_all_statistics()

        self.open_next_image()

    def verify_image(self, _value=False):
        # Proceeding next image without dialog if having any label
        if self.file_path is not None:
            try:
                self.label_file.toggle_verify()
            except AttributeError:
                # If the labelling file does not exist yet, create if and
                # re-save it with the verified attribute.
                self.save_file()
                if self.label_file is not None:
                    self.label_file.toggle_verify()
                else:
                    return

            self.canvas.verified = self.label_file.verified
            if self.lock_on_verify_option.isChecked():
                self.canvas.locked = self.canvas.verified
            self.paint_canvas()
            self.save_file()
            # Update gallery status after verify
            self._update_current_image_gallery_status()

    def open_prev_image(self, _value=False):
        # Proceeding prev image without dialog if having any label
        if self.auto_saving.isChecked():
            if self.default_save_dir is not None:
                if self.dirty is True:
                    self.save_file()
            else:
                self.change_save_dir_dialog()
                return

        if not self.may_continue():
            return

        if self.img_count <= 0:
            return

        if self.file_path is None:
            return

        if self.cur_img_idx - 1 >= 0:
            self.cur_img_idx -= 1
            filename = self.m_img_list[self.cur_img_idx]
            if filename:
                self.load_file(filename)

    def open_next_image(self, _value=False):
        # Proceeding next image without dialog if having any label
        if self.auto_saving.isChecked():
            if self.default_save_dir is not None:
                if self.dirty is True:
                    self.save_file()
            else:
                self.change_save_dir_dialog()
                return

        if not self.may_continue():
            return

        if self.img_count <= 0:
            return
        
        if not self.m_img_list:
            return

        filename = None
        if self.file_path is None:
            filename = self.m_img_list[0]
            self.cur_img_idx = 0
        else:
            if self.cur_img_idx + 1 < self.img_count:
                self.cur_img_idx += 1
                filename = self.m_img_list[self.cur_img_idx]

        if filename:
            self.load_file(filename)

    def open_file(self, _value=False):
        if not self.may_continue():
            return
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename,_ = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.cur_img_idx = 0
            self.img_count = 1
            self.load_file(filename)

    def save_file(self, _value=False):
        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            if self.file_path:
                image_file_name = os.path.basename(self.file_path)
                saved_file_name = os.path.splitext(image_file_name)[0]
                saved_path = os.path.join(ustr(self.default_save_dir), saved_file_name)
                self._save_file(saved_path)
        else:
            image_file_dir = os.path.dirname(self.file_path)
            image_file_name = os.path.basename(self.file_path)
            saved_file_name = os.path.splitext(image_file_name)[0]
            saved_path = os.path.join(image_file_dir, saved_file_name)
            self._save_file(saved_path if self.label_file
                            else self.save_file_dialog(remove_ext=False))

    def save_file_as(self, _value=False):
        assert not self.image.isNull(), "cannot save empty image"
        self._save_file(self.save_file_dialog())

    def save_file_dialog(self, remove_ext=True):
        caption = '%s - Choose File' % __appname__
        filters = 'File (*%s)' % LabelFile.suffix
        open_dialog_path = self.current_path()
        dlg = QFileDialog(self, caption, open_dialog_path, filters)
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QFileDialog.AcceptSave)
        filename_without_extension = os.path.splitext(self.file_path)[0]
        dlg.selectFile(filename_without_extension)
        dlg.setOption(QFileDialog.DontUseNativeDialog, False)
        if dlg.exec_():
            full_file_path = ustr(dlg.selectedFiles()[0])
            if remove_ext:
                return os.path.splitext(full_file_path)[0]  # Return file path without the extension.
            else:
                return full_file_path
        return ''

    def _save_file(self, annotation_file_path):
        if annotation_file_path and self.save_labels(annotation_file_path):
            self.set_clean()
            self.statusBar().showMessage('Saved to  %s' % annotation_file_path)
            self.statusBar().show()
            # Update gallery status after save
            self._update_current_image_gallery_status()

    def close_file(self, _value=False):
        if not self.may_continue():
            return
        self.reset_state()
        self.set_clean()
        self.toggle_actions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def delete_image(self):
        delete_path = self.file_path
        if delete_path is not None:
            idx = self.cur_img_idx
            if os.path.exists(delete_path):
                os.remove(delete_path)
            self.import_dir_images(self.last_open_dir)
            if self.img_count > 0:
                self.cur_img_idx = min(idx, self.img_count - 1)
                filename = self.m_img_list[self.cur_img_idx]
                self.load_file(filename)
            else:
                self.close_file()

    def reset_all(self):
        self.settings.reset()
        self.close()
        process = QProcess()
        # Relaunch through the Python interpreter so the restart works for an
        # installed (entry-point) package, not just a source checkout.
        process.startDetached(sys.executable, [os.path.abspath(__file__)])

    def may_continue(self):
        if not self.dirty:
            return True
        else:
            discard_changes = self.discard_changes_dialog()
            if discard_changes == QMessageBox.No:
                return True
            elif discard_changes == QMessageBox.Yes:
                self.save_file()
                return True
            else:
                return False

    def discard_changes_dialog(self):
        yes, no, cancel = QMessageBox.Yes, QMessageBox.No, QMessageBox.Cancel
        msg = u'You have unsaved changes, would you like to save them and proceed?\nClick "No" to undo all changes.'
        return QMessageBox.warning(self, u'Attention', msg, yes | no | cancel)

    def error_message(self, title, message):
        return QMessageBox.critical(self, title,
                                    '<p><b>%s</b></p>%s' % (title, message))

    def current_path(self):
        return os.path.dirname(self.file_path) if self.file_path else '.'

    def choose_color1(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose line color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.line_color = color
            Shape.line_color = color
            self.canvas.set_drawing_color(color)
            self.canvas.update()
            self.set_dirty()

    def delete_selected_shape(self):
        """Delete the currently selected shape with undo support."""
        if self.canvas.selected_shape is None:
            return
        shape = self.canvas.selected_shape
        index = self.canvas.shapes.index(shape) if shape in self.canvas.shapes else None

        # Create and push command (command handles the actual deletion)
        cmd = DeleteShapeCommand(self, shape, index)
        cmd.execute()
        self.undo_stack.push(cmd)
        self.set_dirty()
        self._update_current_image_stats()

        if self.no_shapes():
            for action in self.actions.onShapesPresent:
                action.setEnabled(False)

    def undo_action(self):
        """Undo the last action."""
        if self.undo_stack.can_undo():
            self.undo_stack.undo()
            self.set_dirty()
            self.canvas.update()

    def redo_action(self):
        """Redo the last undone action."""
        if self.undo_stack.can_redo():
            self.undo_stack.redo()
            self.set_dirty()
            self.canvas.update()

    def update_undo_redo_actions(self):
        """Update the enabled state of undo/redo actions."""
        self.actions.undo.setEnabled(self.undo_stack.can_undo())
        self.actions.redo.setEnabled(self.undo_stack.can_redo())

        # Update tooltips with descriptions
        if self.undo_stack.can_undo():
            desc = self.undo_stack.get_undo_description()
            self.actions.undo.setToolTip(f"Undo: {desc}")
        else:
            self.actions.undo.setToolTip("Undo")

        if self.undo_stack.can_redo():
            desc = self.undo_stack.get_redo_description()
            self.actions.redo.setToolTip(f"Redo: {desc}")
        else:
            self.actions.redo.setToolTip("Redo")

    def choose_shape_line_color(self):
        color = self.color_dialog.getColor(self.line_color, u'Choose Line Color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            self.canvas.selected_shape.line_color = color
            self.canvas.update()
            self.set_dirty()

    def choose_shape_fill_color(self):
        color = self.color_dialog.getColor(self.fill_color, u'Choose Fill Color',
                                           default=DEFAULT_FILL_COLOR)
        if color:
            self.canvas.selected_shape.fill_color = color
            self.canvas.update()
            self.set_dirty()

    def copy_shape(self):
        if self.canvas.selected_shape is None:
            # True if one accidentally touches the left mouse button before releasing
            return
        self.canvas.end_move(copy=True)
        self.add_label(self.canvas.selected_shape)
        self.set_dirty()

    def move_shape(self):
        self.canvas.end_move(copy=False)
        self.set_dirty()

    def load_predefined_classes(self, predef_classes_file):
        if predef_classes_file and os.path.exists(predef_classes_file):
            with codecs.open(predef_classes_file, 'r', 'utf8') as f:
                for line in f:
                    line = line.strip()
                    if self.label_hist is None:
                        self.label_hist = [line]
                    else:
                        self.label_hist.append(line)

    def load_pascal_xml_by_filename(self, xml_path):
        if self.file_path is None:
            return
        if os.path.isfile(xml_path) is False:
            return

        try:
            loaded = annotation_loader.load_pascal_voc(xml_path)
        except Exception as e:
            self.error_message(
                'Annotation Error',
                f'Error loading PASCAL VOC annotations from '
                f'{os.path.basename(xml_path)}: {e}')
            return

        # Defer the format switch until the reader succeeds (Issue #69).
        self.set_format(FORMAT_PASCALVOC)
        self.load_labels(loaded.shapes)
        self.canvas.verified = loaded.verified

    def load_yolo_txt_by_filename(self, txt_path):
        if self.file_path is None:
            return
        if os.path.isfile(txt_path) is False:
            return

        # YOLO stores normalized coords; convert against the original image
        # size rather than the (possibly scaled) display image (Issue #31).
        original_size = getattr(self, '_original_image_size', None)
        try:
            loaded = annotation_loader.load_yolo(
                txt_path, self.image, original_size)
        except Exception as e:
            self.error_message('Annotation Error',
                f'Error loading YOLO annotations for {os.path.basename(txt_path)}: {e}')
            return

        # Defer the format switch until the reader succeeds (Issue #69).
        self.set_format(FORMAT_YOLO)
        self.load_labels(loaded.shapes)
        self.canvas.verified = loaded.verified

    def load_create_ml_json_by_filename(self, json_path, file_path):
        if self.file_path is None:
            return
        if os.path.isfile(json_path) is False:
            return

        try:
            loaded = annotation_loader.load_create_ml(json_path, file_path)
        except Exception as e:
            self.error_message(
                'Annotation Error',
                f'Error loading CreateML annotations from '
                f'{os.path.basename(json_path)}: {e}')
            return

        self.set_format(FORMAT_CREATEML)
        self.load_labels(loaded.shapes)
        self.canvas.verified = loaded.verified

    def load_coco_json_by_filename(self, json_path, file_path):
        """Load annotations from a COCO JSON file for the given image.

        Args:
            json_path: Path to the COCO JSON annotation file.
            file_path: Path to the image file (used to match image entry).
        """
        if self.file_path is None:
            return
        if not os.path.isfile(json_path):
            return

        try:
            loaded = annotation_loader.load_coco(json_path, file_path)
        except Exception as e:
            self.error_message(
                'Annotation Error',
                f'Error loading COCO annotations from '
                f'{os.path.basename(json_path)}: {e}')
            return

        self.set_format(FORMAT_COCO)
        self.load_labels(loaded.shapes)
        self.canvas.verified = loaded.verified

    def load_yolo_seg_by_filename(self, txt_path):
        """Load annotations from a YOLO-seg text file.

        Args:
            txt_path: Path to the YOLO-seg annotation text file.
        """
        if self.file_path is None:
            return
        if not os.path.isfile(txt_path):
            return

        original_size = getattr(self, '_original_image_size', None)
        try:
            loaded = annotation_loader.load_yolo_seg(
                txt_path, self.image, original_size)
        except Exception as e:
            self.error_message(
                'Annotation Error',
                f'Error loading YOLO-seg annotations for '
                f'{os.path.basename(txt_path)}: {e}')
            return

        self.set_format(FORMAT_YOLO_SEG)
        self.load_labels(loaded.shapes)
        self.canvas.verified = loaded.verified

    def copy_previous_bounding_boxes(self):
        current_index = self._path_to_idx.get(self.file_path, 0)
        if current_index - 1 >= 0:
            prev_file_path = self.m_img_list[current_index - 1]
            self.show_bounding_box_from_annotation_file(prev_file_path)
            self.save_file()

    def toggle_paint_labels_option(self):
        for shape in self.canvas.shapes:
            shape.paint_label = self.display_label_option.isChecked()

    def toggle_draw_square(self):
        self.canvas.set_drawing_shape_to_square(self.draw_squares_option.isChecked())

    def toggle_lock_on_verify(self, checked):
        if self.canvas and self.canvas.verified and checked:
            self.canvas.locked = True
        elif not checked:
            self.canvas.locked = False

    def toggle_grid(self, checked):
        if self.canvas:
            self.canvas._grid_enabled = checked
            self.canvas.update()

    def toggle_edge_alignment(self, checked):
        if self.canvas:
            self.canvas._edge_alignment = checked

    def _set_grid_size(self):
        action = self.grid_size_group.checkedAction()
        if action and self.canvas:
            self.canvas._grid_size = action.data()
            self.canvas.update()

    def change_icon_size(self):
        """Change toolbar icon size based on user selection."""
        action = self.sender()
        if action:
            size = action.data()
            self.settings[SETTING_ICON_SIZE] = size

            if size == 0:
                # Auto mode - recalculate from DPI
                from libs.toolBar import calculate_icon_size
                size = calculate_icon_size()

            # Update toolbar icon size
            if hasattr(self, 'tools') and self.tools:
                self.tools.update_icon_size(size)

    # Auto-save timer methods (Issue #13)
    def _toggle_auto_save_timer(self):
        """Toggle timer-based auto-save."""
        if self.auto_save_enabled.isChecked():
            interval = self._get_current_auto_save_interval()
            self.auto_save_timer.start(interval * 1000)  # Convert to ms
        else:
            self.auto_save_timer.stop()

    def _set_auto_save_interval(self):
        """Set auto-save interval from menu selection."""
        action = self.sender()
        if action:
            interval = action.data()
            if self.auto_save_enabled.isChecked():
                self.auto_save_timer.start(interval * 1000)

    def _get_current_auto_save_interval(self):
        """Get currently selected auto-save interval in seconds."""
        for action in self.auto_save_interval_group.actions():
            if action.isChecked():
                return action.data()
        return 60  # Default 1 minute

    def _auto_save_triggered(self):
        """Called by timer to perform auto-save."""
        if not self.dirty:
            return  # Nothing to save

        if not self.file_path:
            return  # No file loaded

        # Determine save path (same logic as save_file)
        image_file_name = os.path.basename(self.file_path)
        saved_file_name = os.path.splitext(image_file_name)[0]

        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            save_path = os.path.join(ustr(self.default_save_dir), saved_file_name)
        else:
            image_file_dir = os.path.dirname(self.file_path)
            save_path = os.path.join(image_file_dir, saved_file_name)

        if save_path:
            self.status("Auto-saving...")
            self._save_file(save_path)
            self.status("Auto-saved to %s" % os.path.basename(save_path))

    # Dark mode methods (Issue #7)
    def _toggle_dark_mode(self):
        """Toggle between light and dark theme."""
        if self.dark_mode_action.isChecked():
            self._current_theme = Theme.DARK
        else:
            self._current_theme = Theme.LIGHT
        self._apply_theme(self._current_theme)

    def _apply_theme(self, theme):
        """Apply the given theme to all components."""
        from libs.utils.styles import get_toolbar_style, get_theme_colors

        # Resolve the palette once up front; several blocks below (including
        # the save-status refresh) read it regardless of which widgets exist.
        colors = get_theme_colors(theme)

        # Apply main stylesheet
        self.setStyleSheet(get_stylesheet(theme))

        # Update toolbar style and expand button
        if hasattr(self, 'tools') and self.tools:
            self.tools.setStyleSheet(get_toolbar_style(theme))
            if hasattr(self.tools, 'apply_theme'):
                self.tools.apply_theme(theme)

        # Update canvas background
        if hasattr(self, 'canvas') and self.canvas:
            bg_color = get_canvas_background(theme)
            self.canvas.set_background_color(bg_color)
            if hasattr(self.canvas, 'set_theme'):
                self.canvas.set_theme(theme)

        # Update scroll area viewport background
        if hasattr(self, 'scroll_area') and self.scroll_area:
            self.scroll_area.viewport().setStyleSheet(
                f"background-color: {colors['background']};"
            )

        # Update gallery widget (dock)
        if hasattr(self, 'gallery_widget') and self.gallery_widget:
            if hasattr(self.gallery_widget, 'apply_theme'):
                self.gallery_widget.apply_theme(theme)

        # Update gallery window stylesheet to isolate from parent cascade
        if hasattr(self, 'gallery_window') and self.gallery_window:
            self.gallery_window.setStyleSheet(get_stylesheet(theme))

        # Update full gallery (gallery mode window)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            if hasattr(self.full_gallery, 'apply_theme'):
                self.full_gallery.apply_theme(theme)

        # Apply theme to stats widget (in gallery mode)
        if hasattr(self, 'gallery_stats') and self.gallery_stats:
            if hasattr(self.gallery_stats, 'apply_theme'):
                self.gallery_stats.apply_theme(theme)

        # Apply theme to keypoint panel
        if hasattr(self, 'keypoint_panel'):
            self.keypoint_panel.apply_theme(theme)

        # Refresh save status indicator colors
        if hasattr(self, 'label_save_status'):
            # Preserve current saved state (check if green/saved or orange/unsaved)
            current_stylesheet = self.label_save_status.styleSheet()
            is_saved = 'green' in current_stylesheet or colors['status_saved'] in current_stylesheet
            self._update_save_status_style(saved=is_saved)

        # Refresh format button icon for current theme
        if hasattr(self, 'label_file_format') and hasattr(self, 'actions'):
            format_icon_map = {
                LabelFileFormat.PASCAL_VOC: 'format_voc',
                LabelFileFormat.YOLO: 'format_yolo',
                LabelFileFormat.CREATE_ML: 'format_createml',
                LabelFileFormat.COCO: 'format_createml',
                LabelFileFormat.YOLO_SEG: 'format_yolo',
            }
            icon_name = format_icon_map.get(self.label_file_format)
            if icon_name:
                self.actions.save_format.setIcon(themed_icon(icon_name, theme))

    # Statistics methods (Issue #19) - Stats shown in gallery mode
    def _refresh_all_statistics(self):
        """Start async refresh of all statistics in the gallery stats widget."""
        self.stats_controller.refresh_all(self.m_img_list, self.default_save_dir)

    def _cleanup_stats_worker(self):
        """Cancel the in-flight statistics worker and disconnect its signals."""
        self.stats_controller.cleanup()

    def _update_current_image_stats(self):
        """Update statistics for the current image."""
        if not hasattr(self, 'gallery_stats') or not self.gallery_stats:
            return

        annotations_count = len(self.canvas.shapes)
        labels = [shape.label for shape in self.canvas.shapes]
        self.stats_controller.update_current_image(annotations_count, labels)

    def _get_labels_for_image(self, img_path):
        """Get list of labels for an image from its annotation file."""
        return probe_annotation(
            img_path, self.default_save_dir, want_labels=True).labels


def get_main_app(argv=None):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    if not argv:
        argv = []

    # Enable high-DPI scaling for better icon rendering on HiDPI displays
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    except AttributeError:
        pass  # Qt4 doesn't have these attributes

    app = QApplication(argv)
    app.setStyle('Fusion')  # Use Fusion style for consistent cross-platform styling
    app.setStyleSheet(get_combined_style())  # Apply global stylesheet
    app.setApplicationName(__appname__)
    app.setWindowIcon(new_icon("app"))
    # Tzutalin 201705+: Accept extra agruments to change predefined class file.
    # Prefer the copy packaged inside the libs package (shipped in the wheel);
    # fall back to the top-level data/ dir for source checkouts.
    _here = os.path.dirname(__file__)
    default_class_file = os.path.join(_here, "libs", "data",
                                      "predefined_classes.txt")
    if not os.path.exists(default_class_file):
        default_class_file = os.path.join(_here, "data",
                                          "predefined_classes.txt")
    argparser = argparse.ArgumentParser()
    argparser.add_argument("image_dir", nargs="?")
    argparser.add_argument("class_file",
                           default=default_class_file,
                           nargs="?")
    argparser.add_argument("save_dir", nargs="?")
    args = argparser.parse_args(argv[1:])

    args.image_dir = args.image_dir and os.path.normpath(args.image_dir)
    args.class_file = args.class_file and os.path.normpath(args.class_file)
    args.save_dir = args.save_dir and os.path.normpath(args.save_dir)

    # Usage : labelImg.py image classFile saveDir
    win = MainWindow(args.image_dir,
                     args.class_file,
                     args.save_dir)
    win.show()
    return app, win


def main_deprecated():
    """Entry point for deprecated labelImgPlusPlus command."""
    import warnings
    warnings.warn(
        "The 'labelImgPlusPlus' command is deprecated. "
        "Please use 'labelimgpp' or 'labelimgplusplus' instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return main()


def main():
    """construct main app and run it"""
    app, _win = get_main_app(sys.argv)
    return app.exec_()

if __name__ == '__main__':
    sys.exit(main())
