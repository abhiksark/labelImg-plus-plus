#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import codecs
from dataclasses import replace
import os.path
import platform
import shutil
import sys
import threading
import time
import webbrowser as wb
from functools import partial

try:
    from PyQt5.QtGui import QColor, QCursor, QImage, QImageReader, QPixmap
    from PyQt5.QtCore import (
        Qt, QFileInfo, QItemSelectionModel, QProcess, QSize, QTimer, QPoint,
        QPointF, QVariant
    )
    from PyQt5.QtWidgets import (
        QAction, QActionGroup, QApplication, QCheckBox, QComboBox,
        QDialog, QFileDialog, QHBoxLayout, QLabel,
        QInputDialog, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox,
        QScrollArea, QTabWidget, QToolButton,
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
        QAction, QActionGroup, QApplication, QCheckBox,
        QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
        QMainWindow, QMenu, QMessageBox, QScrollArea,
        QTabWidget, QToolButton, QVBoxLayout, QWidget, QWidgetAction
    )
    from PyQt4.QtCore import (
        Qt, QFileInfo, QItemSelectionModel, QProcess, QSize, QTimer, QPoint,
        QPointF, QVariant
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
from libs.widgets.videoTimelineWidget import VideoTimelineWidget
from libs.widgets.videoExportDialog import VideoExportDialog
from libs.widgets.commandBar import CommandBar
from libs.widgets.toolRail import AnnotationToolRail
from libs.widgets.workspaceInspector import (
    WorkspaceInspector, WorkspaceSplitterShell,
)
from libs.widgets.annotationInspector import (
    AnnotationFilterProxyModel, AnnotationListModel, AnnotationRoles,
    UnifiedAnnotationView,
)
from libs.widgets.workspacePages import WorkspacePages
from libs.widgets.inlineClassPicker import InlineClassPicker

# Core
from libs.core.shape import Shape, ShapeType, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.core.settings import Settings
from libs.core.commands import (
    UndoStack, CreateShapeCommand, DeleteShapeCommand, MoveShapeCommand,
    EditLabelCommand, EditPolygonVerticesCommand, EditKeypointsCommand,
    EditShapeAttributesCommand, VideoModelCommand,
)
from libs.core.shortcut_config import ShortcutConfig
from libs.core.workspace_settings import (
    clamp_inspector_width, load_workspace_settings,
)
from libs.core.sam_controller import SamController
from libs.core.sam_types import normalize_sam_output_mode
from libs.core.annotation_catalog import AnnotationCatalog
from libs.core.dataset import DatasetSnapshot
from libs.core.image_pipeline import FrameCache, load_image_result
from libs.core.save_pipeline import (
    SaveRequest, target_path as annotation_target_path, write_save_request,
)
from libs.core.task_coordinator import JobPriority, TaskCoordinator
from libs.core.plugin_manager import PluginManager
from libs.core.profiling import (
    hash_path, recorder as trace_recorder, trace_span,
)
from libs.core.video_decoder import VIDEO_EXTENSIONS, VideoDecoderSession
from libs.core.video_project import (
    PROJECT_SUFFIX, VideoSourceChanged, VideoSourceMissing,
    checkpoint_project, default_project_path, save_project_as,
    save_project_delta,
)
from libs.core.video_model import VideoProjectModel
from libs.core.video_export import export_video_frames
from libs.core.video_tracking import track_optical_flow
from libs.core.video_session import (
    VideoOpenProblem, is_video_project, prepare_video_open,
)
from libs.core.video_types import (
    DocumentKind, TrackingRequest, VideoExportRequest, VideoFrameRef,
)
from libs.widgets.videoTimelineWidget import format_timecode, parse_timecode
from libs.widgets.pluginManagerDialog import (
    PluginManagerDialog, QtPluginCommandHost,
)
from libs.integrations import segmentation
from labelimgplusplus.plugins import DocumentDescriptor

# Formats
from libs.formats.labelFile import LabelFile, LabelFileError, LabelFileFormat
from libs.formats.pascal_voc_io import PascalVocReader, XML_EXT
from libs.formats.yolo_io import TXT_EXT
from libs.formats.create_ml_io import JSON_EXT
from libs.formats.annotation_probe import probe as probe_annotation
from libs.formats.annotation_paths import (
    annotation_output_base, find_existing_annotation,
)
from libs.formats import annotation_loader
from libs.formats import format_metadata

# Utils
from libs.utils.constants import (
    SETTING_AUTO_SAVE, SETTING_AUTO_SAVE_ENABLED,
    SETTING_AUTO_SAVE_INTERVAL, SETTING_DARK_MODE, SETTING_DRAW_SQUARE,
    SETTING_EDGE_ALIGNMENT, SETTING_FILENAME, SETTING_FILL_COLOR,
    SETTING_GALLERY_MODE, SETTING_GRID_ENABLED, SETTING_GRID_SIZE,
    SETTING_ICON_SIZE, SETTING_LABEL_FILE_FORMAT, SETTING_LAST_OPEN_DIR,
    SETTING_LINE_COLOR, SETTING_LOCK_ON_VERIFY, SETTING_PAINT_LABEL,
    SETTING_RECENT_FILES, SETTING_SAVE_DIR, SETTING_SHORTCUTS,
    SETTING_INSPECTOR_COLLAPSED, SETTING_INSPECTOR_TAB,
    SETTING_INSPECTOR_WIDTH, SETTING_SINGLE_CLASS,
    SETTING_WIN_POSE, SETTING_WIN_SIZE,
    FORMAT_PASCALVOC, FORMAT_YOLO, FORMAT_CREATEML,
    FORMAT_COCO, FORMAT_YOLO_SEG,
    SETTING_SAM_ENCODER, SETTING_SAM_DECODER, SETTING_SAM_OUTPUT_MODE,
)
from libs.utils.utils import (
    new_icon, themed_icon, new_action, add_actions, format_shortcut, Struct,
    generate_color_by_text, have_qstring, natural_sort
)
from libs.utils.dpi import get_dpi_scale_factor, scale_px
from libs.utils.stringBundle import StringBundle
from libs.utils.styles import get_combined_style, Theme, get_stylesheet, get_canvas_background
from libs.utils.ustr import ustr

# Resources
from libs.resources import *  # noqa: F403

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


def _probe_status(image_path, save_dir, image_list=None, resolver=None):
    """Map the shared annotation probe to an AnnotationStatus enum value."""
    info = probe_annotation(
        image_path, save_dir, image_list=image_list, resolver=resolver)
    if info.verified:
        return AnnotationStatus.VERIFIED
    if info.has_labels:
        return AnnotationStatus.HAS_LABELS
    return AnnotationStatus.NO_LABELS


class MainWindow(QMainWindow, WindowMixin):
    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = list(range(3))

    def __init__(self, default_filename=None, default_prefdef_class_file=None, default_save_dir=None):
        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Load setting in the main thread
        self.settings = Settings()
        self.settings.load()
        settings = self.settings
        self.workspace_settings = load_workspace_settings(settings)
        self.sam_output_mode = normalize_sam_output_mode(
            settings.get(SETTING_SAM_OUTPUT_MODE, 'polygon'))

        self.shortcut_config = ShortcutConfig()
        if settings.get(SETTING_SHORTCUTS):
            self.shortcut_config.from_dict(settings.get(SETTING_SHORTCUTS))

        self.os_name = platform.system()

        # Load string bundle for i18n
        self.string_bundle = StringBundle.get_bundle()
        def get_str(str_id):
            return self.string_bundle.get_string(str_id)

        # Save as Pascal voc xml
        self.default_save_dir = default_save_dir
        self.label_file_format = settings.get(SETTING_LABEL_FILE_FORMAT, LabelFileFormat.PASCAL_VOC)

        # For loading all image under a directory
        self.m_img_list = []
        self._path_to_idx = {}  # O(1) lookup: path -> index
        self._annotation_status_cache = {}  # Cache: path -> status (reduces I/O)
        self.task_coordinator = TaskCoordinator(parent=self)
        self._plugin_document_generation = 0
        self._plugin_document_ready = False
        self.plugin_manager = PluginManager(
            settings, self.task_coordinator, parent=self)
        self._dataset_generation = 0
        self.dataset_snapshot = DatasetSnapshot.from_images(
            (), save_dir=default_save_dir, generation=0)
        # Reserve the remaining cache budget for the dock and full-screen
        # thumbnail galleries (16 MiB each): 96 + 16 + 16 = 128 MiB total.
        self.frame_cache = FrameCache(
            max_images=5, max_bytes=96 * 1024 * 1024)
        self.document_kind = DocumentKind.NONE
        self.video_decoder = None
        self.video_snapshot = None
        self.video_tracks = ()
        self.video_observations = ()
        self.video_frame_states = ()
        self.video_classes = ()
        self.video_model = None
        self._selected_video_track_id = None
        self._video_open_request_id = 0
        self._video_save_handle = None
        self._video_save_active = False
        self._video_save_queued = False
        self._video_save_callbacks = []
        self._video_close_save_pending = False
        self._video_frame_request_id = 0
        self._video_decode_in_flight = False
        self._video_prefetch_handle = None
        self.current_video_frame_ref = None
        self._video_playback_speed = 1.0
        self._video_play_started_wall = None
        self._video_play_started_seconds = None
        self._tracking_request_id = 0
        self._tracking_handle = None
        self._active_tracking_request = None
        self._tracking_run_keys = set()
        self._applying_tracking_batch = False
        self._video_export_handle = None
        self._load_request_id = 0
        self._pending_navigation_index = None
        self._prefetch_handles = {}
        self._navigation_direction = 0
        self._navigation_streak = 0
        self._document_revision = 0
        self._save_handle = None
        self._save_locks = {}
        self._loading_veil = None

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
        self._reset_all_in_progress = False

        # Clipboard for copy/paste annotations across images
        self.clipboard_shapes = []

        self._no_selection_slot = False
        self._beginner = True
        self.gallery_mode_enabled = False
        self._gallery_batch_id = 0  # For cancelling pending batch processing
        self.annotation_catalog = AnnotationCatalog(
            self.task_coordinator, parent=self)
        self.annotation_catalog.batch_ready.connect(
            self._on_catalog_batch)
        self.annotation_catalog.statistics_ready.connect(
            self._on_catalog_statistics)
        self.annotation_catalog.error.connect(
            lambda message: self.status('Annotation catalog: ' + message))
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

        self.prev_label_text = ''
        self._session_last_class = None
        self._pending_provisional_shape = None

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

        self.annotation_search = QLineEdit()
        self.annotation_search.setObjectName('annotationSearch')
        self.annotation_search.setPlaceholderText('Search objects…')
        self.annotation_search.setToolTip(
            'Search class, type, provenance, or track ID')
        self.annotation_model = AnnotationListModel(self)
        self.annotation_proxy = AnnotationFilterProxyModel(self)
        self.annotation_proxy.setSourceModel(self.annotation_model)
        self.label_list = UnifiedAnnotationView()
        self.label_list.setObjectName('unifiedAnnotationList')
        self.label_list.setModel(self.annotation_proxy)
        # Compatibility aliases now intentionally resolve to the one view.
        self.rect_label_list = self.label_list
        self.poly_label_list = self.label_list
        self.track_list_widget = self.label_list

        self.annotation_controls = QWidget()
        self.annotation_controls.setObjectName('objectsInspectorPage')
        self.annotation_controls.setLayout(list_layout)

        self.annotation_search.textChanged.connect(
            self.annotation_proxy.set_search_text)
        self.label_list.selectionModel().selectionChanged.connect(
            self.label_selection_changed)
        self.label_list.doubleClicked.connect(self.edit_label)
        self.annotation_model.visibilityChangeRequested.connect(
            self._annotation_visibility_changed)
        self.annotation_model.classEditRequested.connect(
            self._annotation_class_edit_requested)

        list_layout.addWidget(self.annotation_search)
        list_layout.addWidget(self.label_list)

        # Keypoint annotation panel (shown for person shapes)
        self.keypoint_panel = KeypointPanel()
        self.keypoint_panel.keypointClicked.connect(self._on_keypoint_panel_click)
        list_layout.addWidget(self.keypoint_panel)

        # File list widget (existing list view)
        self.file_list_widget = QListWidget()
        self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)
        self.file_list_widget.itemClicked.connect(self.file_item_clicked)

        # Gallery widget (new thumbnail view)
        self.gallery_widget = GalleryWidget(
            coordinator=self.task_coordinator)
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
        self.file_controls = QWidget()
        self.file_controls.setObjectName('filesInspectorPage')
        self.file_controls.setLayout(file_list_layout)

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
        self.class_picker = InlineClassPicker(self)
        self.class_picker.accepted.connect(self._commit_provisional_shape)
        self.class_picker.cancelled.connect(self._cancel_provisional_shape)
        self.sam_controller = SamController(self)
        self.canvas.samClicked.connect(self.sam_controller.segment_at)
        self._sam_available = segmentation.sam_available()
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

        self.video_timeline = VideoTimelineWidget(self)
        self.video_timeline.setObjectName('videoTimeline')
        self.video_timeline.hide()
        self.video_timeline.seekRequested.connect(self.request_video_frame)
        self.video_timeline.previousRequested.connect(
            self.request_previous_video_frame)
        self.video_timeline.nextRequested.connect(
            self.request_next_video_frame)
        self.video_timeline.playPauseRequested.connect(
            self.play_pause_video)
        self.video_timeline.speedChanged.connect(
            self._set_video_playback_speed)
        self._video_playback_timer = QTimer(self)
        self._video_playback_timer.setTimerType(Qt.PreciseTimer)
        self._video_playback_timer.setInterval(10)
        self._video_playback_timer.timeout.connect(self._video_playback_tick)

        # Actions
        action = partial(new_action, self)
        quit = action(get_str('quit'), self.close,
                      self.shortcut_config.get('quit'), 'quit', get_str('quitApp'))

        open = action(get_str('openFile'), self.open_file,
                      self.shortcut_config.get('open'), 'open', get_str('openFileDetail'))

        open_video = action(
            'Open Video…', self.open_video_dialog,
            self.shortcut_config.get('open_video'), 'file',
            'Open a local video or LabelImg++ video project')

        open_dir = action(get_str('openDir'), self.open_dir_dialog,
                          self.shortcut_config.get('open_dir'), 'open', get_str('openDir'))

        change_save_dir = action(get_str('changeSaveDir'), self.change_save_dir_dialog,
                                 self.shortcut_config.get('change_save_dir'), 'open', get_str('changeSavedAnnotationDir'))

        open_annotation = action(get_str('openAnnotation'), self.open_annotation_dialog,
                                 self.shortcut_config.get('open_annotation'), 'open', get_str('openAnnotationDetail'))
        copy_prev_bounding = action(get_str('copyPrevBounding'), self.copy_previous_bounding_boxes, self.shortcut_config.get('copy_prev_bounding'), 'copy', get_str('copyPrevBounding'))

        open_next_image = action(get_str('nextImg'), self.request_next_image,
                                 self.shortcut_config.get('open_next_image'), 'next', get_str('nextImgDetail'))

        open_prev_image = action(get_str('prevImg'), self.request_previous_image,
                                 self.shortcut_config.get('open_prev_image'), 'prev', get_str('prevImgDetail'))

        verify = action(get_str('verifyImg'), self.request_verify_image,
                        self.shortcut_config.get('verify'), 'verify', get_str('verifyImgDetail'))

        video_play_pause = action(
            'Play/Pause Video', self.play_pause_video,
            self.shortcut_config.get('video_play_pause'), None,
            'Play or pause the active video without audio', enabled=False)

        save = action(get_str('save'), self.request_save_file,
                      self.shortcut_config.get('save'), 'save', get_str('saveDetail'), enabled=False)

        current_format_meta = format_metadata.meta_for_enum(self.label_file_format)
        save_format = action(current_format_meta.menu_title,
                             self.change_format, self.shortcut_config.get('save_format'),
                             current_format_meta.icon,
                             get_str('changeSaveFormat'), enabled=True)

        save_as = action(get_str('saveAs'), self.request_save_file_as,
                         self.shortcut_config.get('save_as'), 'save-as', get_str('saveAsDetail'), enabled=False)

        close = action(get_str('closeCur'), self.close_file, self.shortcut_config.get('close'), 'close', get_str('closeCurDetail'))

        delete_image = action(get_str('deleteImg'), self.delete_image, self.shortcut_config.get('delete_image'), 'close', get_str('deleteImgDetail'))

        reset_all = action(get_str('resetAll'), self.reset_all, None, 'resetall', get_str('resetAllDetail'))

        color1 = action(get_str('boxLineColor'), self.choose_color1,
                        self.shortcut_config.get('color1'), 'color_line', get_str('boxLineColorDetail'))

        create_mode = action(get_str('crtBox'), self.set_create_mode,
                             self.shortcut_config.get('create_mode'), 'tool-box', get_str('crtBoxDetail'), enabled=False)
        edit_mode = action(get_str('editBox'), self.set_edit_mode,
                           self.shortcut_config.get('edit_mode'), 'tool-select', get_str('editBoxDetail'), enabled=False)

        create = action(get_str('crtBox'), self.create_shape,
                        self.shortcut_config.get('create'), 'tool-box', get_str('crtBoxDetail'), enabled=False)
        create_polygon = action(get_str('crtPolygon'), self.create_polygon_mode,
                                self.shortcut_config.get('create_polygon'),
                                'tool-polygon', get_str('crtPolygonDetail'), enabled=False)
        keypoint_mode_action = action(
            get_str('addKeypoints'),
            self.toggle_keypoint_mode,
            self.shortcut_config.get('keypoint_mode'),
            'tool-keypoints',
            get_str('addKeypointsDetail'),
            enabled=False)
        video_add_keyframe = action(
            'Add Track Keyframe', self.add_track_keyframe,
            self.shortcut_config.get('video_add_keyframe'), 'verify',
            'Promote the selected track at the current PTS to a manual anchor',
            enabled=False)
        video_delete_track = action(
            'Delete Track…', self.delete_selected_track,
            None, 'delete', 'Delete the selected track on every frame',
            enabled=False)
        video_edit_span = action(
            'Set Track Span…', self.edit_selected_track_span,
            None, None, 'Trim the selected track to inclusive PTS bounds',
            enabled=False)
        video_track_forward = action(
            'Track Forward…',
            lambda _checked=False: self.track_selected_forward(
                choose_endpoint=True),
            self.shortcut_config.get('video_track_forward'), None,
            'Propagate the selected rectangle forward with optical flow',
            enabled=False)
        video_track_backward = action(
            'Track Backward…',
            lambda _checked=False: self.track_selected_backward(
                choose_endpoint=True),
            self.shortcut_config.get('video_track_backward'), None,
            'Propagate the selected rectangle backward with optical flow',
            enabled=False)
        video_accept_suggestion = action(
            'Accept Current Suggestion', self.accept_current_suggestion,
            self.shortcut_config.get('video_accept_suggestion'), 'verify',
            'Accept the pending tracker observation on this frame',
            enabled=False)
        video_reject_suggestion = action(
            'Reject Current Suggestion', self.reject_current_suggestion,
            self.shortcut_config.get('video_reject_suggestion'), 'close',
            'Reject the pending tracker observation on this frame',
            enabled=False)
        video_accept_visible = action(
            'Accept Visible Suggestions',
            lambda: self.review_visible_suggestions('accepted'),
            None, 'verify',
            'Accept pending tracker observations in the visible range',
            enabled=False)
        video_reject_visible = action(
            'Reject Visible Suggestions',
            lambda: self.review_visible_suggestions('rejected'),
            None, 'close',
            'Reject pending tracker observations in the visible range',
            enabled=False)
        video_accept_run = action(
            'Accept Full Propagation',
            lambda: self.review_full_propagation('accepted'),
            None, 'verify',
            'Accept pending observations from the latest propagation run',
            enabled=False)
        video_reject_run = action(
            'Reject Full Propagation',
            lambda: self.review_full_propagation('rejected'),
            None, 'close',
            'Reject pending observations from the latest propagation run',
            enabled=False)
        video_export = action(
            'Export Video Frames…', self.open_video_export_dialog,
            None, 'save-as',
            'Export accepted tracked frames to the selected image format',
            enabled=False)
        sam_mode_action = action(
            'SAM Segment',
            self.toggle_sam_mode,
            self.shortcut_config.get('sam_mode'),
            'tool-smart-select',
            'Click an object to auto-generate the selected geometry '
            '(requires: pip install labelimgplusplus[sam])',
            enabled=False)
        sam_settings_action = action(
            'SAM Settings…', self.open_sam_settings, None, 'edit',
            'Configure the SAM checkpoint, model type, and device')
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

        labels = QAction(get_str('showHide'), self)
        labels.setCheckable(True)
        labels.setChecked(not self.workspace_settings.inspector_collapsed)
        labels.triggered.connect(
            lambda checked: self.set_inspector_collapsed(not checked))
        labels.setText(get_str('showHide'))
        labels.setShortcut('Ctrl+Shift+L')

        # Statistics panel moved to gallery mode (Issue #19)

        # Label list context menu.
        label_menu = QMenu()
        add_actions(label_menu, (
            edit, delete, shape_line_color, shape_fill_color, None,
            video_add_keyframe, video_edit_span, video_accept_suggestion,
            video_reject_suggestion, video_delete_track,
        ))
        self.label_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.label_list.customContextMenuRequested.connect(
            self.pop_label_list_menu)

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
            'open_video': open_video,
            'open_dir': open_dir,
            'change_save_dir': change_save_dir,
            'open_annotation': open_annotation,
            'copy_prev_bounding': copy_prev_bounding,
            'open_next_image': open_next_image,
            'open_prev_image': open_prev_image,
            'verify': verify,
            'video_play_pause': video_play_pause,
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
            'sam_mode': sam_mode_action,
            'video_add_keyframe': video_add_keyframe,
            'video_edit_span': video_edit_span,
            'video_track_forward': video_track_forward,
            'video_track_backward': video_track_backward,
            'video_accept_suggestion': video_accept_suggestion,
            'video_reject_suggestion': video_reject_suggestion,
        }

        # Store actions for further handling.
        self.actions = Struct(save=save, save_format=save_format,
                              saveAs=save_as, open=open,
                              openVideo=open_video, openDir=open_dir,
                              changeSaveDir=change_save_dir,
                              openAnnotation=open_annotation,
                              previous=open_prev_image, next=open_next_image,
                              close=close, resetAll=reset_all,
                              deleteImg=delete_image, verify=verify,
                              lineColor=color1, create=create, create_polygon=create_polygon,
                              keypoint_mode=keypoint_mode_action,
                              videoAddKeyframe=video_add_keyframe,
                              videoEditSpan=video_edit_span,
                              videoDeleteTrack=video_delete_track,
                              videoTrackForward=video_track_forward,
                              videoTrackBackward=video_track_backward,
                              videoAcceptSuggestion=video_accept_suggestion,
                              videoRejectSuggestion=video_reject_suggestion,
                              videoAcceptVisible=video_accept_visible,
                              videoRejectVisible=video_reject_visible,
                              videoAcceptRun=video_accept_run,
                              videoRejectRun=video_reject_run,
                              videoExport=video_export,
                              sam_mode=sam_mode_action,
                              delete=delete, edit=edit, copy=copy,
                              copyToClipboard=copy_to_clipboard, pasteFromClipboard=paste_from_clipboard,
                              copyAllToClipboard=copy_all_to_clipboard,
                              undo=undo, redo=redo,
                              videoPlayPause=video_play_pause,
                              createMode=create_mode, editMode=edit_mode, advancedMode=advanced_mode, galleryMode=gallery_mode,
                              inspectorVisible=labels,
                              shapeLineColor=shape_line_color, shapeFillColor=shape_fill_color,
                              zoom=zoom, zoomIn=zoom_in, zoomOut=zoom_out, zoomOrg=zoom_org,
                              fitWindow=fit_window, fitWidth=fit_width,
                              hideAll=hide_all, showAll=show_all,
                              zoomActions=zoom_actions,
                              lightBrighten=light_brighten, lightDarken=light_darken, lightOrg=light_org,
                              lightActions=light_actions,
                              fileMenuActions=(
                                  open, open_video, open_dir, save, save_as,
                                  close, reset_all, quit),
                              beginner=(), advanced=(),
                              editMenu=(undo, redo, None, edit, copy, copy_to_clipboard,
                                        paste_from_clipboard, copy_all_to_clipboard, delete,
                                        None, keypoint_mode_action,
                                        video_add_keyframe,
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
            plugins=self.menu('&Plugins'),
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
        self.auto_save_timer.timeout.connect(self._request_auto_save_triggered)

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
                    (open, open_video, open_dir, change_save_dir,
                     open_annotation, copy_prev_bounding,
                     self.menus.recentFiles, save, save_format, save_as,
                     close, reset_all, delete_image, quit))
        add_actions(self.menus.help, (help_default, show_info, show_shortcut))
        add_actions(self.menus.view, (
            self.auto_saving,
            self.auto_save_enabled,
            self.single_class_mode,
            self.display_label_option,
            self.lock_on_verify_option,
            labels, gallery_mode, None,
            hide_all, show_all, None,
            zoom_in, zoom_out, zoom_org, None,
            fit_window, fit_width, None,
            light_brighten, light_darken, light_org, None))
        self.menus.view.addMenu(self.auto_save_interval_menu)
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
        export_ultralytics_action = action(
            get_str('exportUltralytics'), self.export_ultralytics_dataset,
            None, 'save-as', get_str('exportUltralyticsDetail'))
        plugin_manager_action = action(
            'Plugins…', self.show_plugins_dialog,
            None, None, 'Inspect, enable, disable, and diagnose installed plugins')
        add_actions(self.menus.tools, (
            check_labels, batch_verify_action, split_dataset_action,
            export_ultralytics_action,
            None, video_play_pause, video_add_keyframe,
            video_track_forward, video_track_backward,
            video_accept_suggestion, video_reject_suggestion,
            video_accept_visible, video_reject_visible,
            video_accept_run, video_reject_run,
            video_delete_track, video_export,
            None, sam_mode_action, sam_settings_action,
            None, plugin_manager_action))

        # Custom context menu for the canvas widget:
        add_actions(self.canvas.menus[0], self.actions.beginnerContext)
        add_actions(self.canvas.menus[1], (
            action('&Copy here', self.copy_shape),
            action('&Move here', self.move_shape)))

        # The modern rail is a fixed projection of existing QActions. The
        # former QToolBar settings remain serialized for downgrade use, but no
        # legacy toolbar is instantiated or configured in the modern shell.
        self.tools = None
        self.tool_rail = AnnotationToolRail((
            ('select', 'Select', edit_mode),
            ('box', 'Bounding Box', create),
            ('polygon', 'Polygon', create_polygon),
            ('smartSelect', 'Smart Select', sam_mode_action),
            ('keypoints', 'Keypoints', keypoint_mode_action),
        ), self)

        # Keep a hidden native QStatusBar as the compatibility message bus;
        # its projection is rendered by the slim workspace strip below.
        self.label_status_message = QLabel('%s started.' % __appname__)
        self.label_status_message.setObjectName('workspaceStatusMessage')
        self.label_image_count = QLabel('Image: 0 / 0')
        self.label_dimensions = QLabel('0 x 0')
        self.label_box_count = QLabel('Objects: 0')
        self.label_active_tool = QLabel('Select')
        self.label_zoom = QLabel('Zoom: 100%')
        self.label_save_status = QLabel('● Saved')
        self.label_coordinates = QLabel('')
        self._update_save_status_style(saved=True)

        self.full_gallery = GalleryWidget(
            show_size_slider=True, coordinator=self.task_coordinator)
        self.full_gallery.set_save_dir(self.default_save_dir)
        self.full_gallery.set_status_filter(
            self.status_filter_combo.currentIndex())
        self.full_gallery.set_dataset_snapshot(self.dataset_snapshot)
        self.full_gallery.image_selected.connect(
            lambda path: self.gallery_image_selected(path, source='full'))
        self.full_gallery.image_activated.connect(self._exit_gallery_and_load)
        self.gallery_stats = StatsWidget()
        self.gallery_stats.refresh_btn.clicked.connect(
            self._refresh_all_statistics)
        self.gallery_stats.setMaximumWidth(scale_px(300))
        self.gallery_stats.setMinimumWidth(0)
        gallery_page = QWidget()
        gallery_page.setObjectName('embeddedGalleryPage')
        gallery_layout = QHBoxLayout(gallery_page)
        gallery_layout.setContentsMargins(0, 0, 0, 0)
        gallery_layout.setSpacing(0)
        gallery_layout.addWidget(self.full_gallery, stretch=4)
        gallery_layout.addWidget(self.gallery_stats, stretch=1)

        canvas_column = WorkspacePages(
            self.scroll_area, self.video_timeline, gallery_page,
            (self.label_status_message, self.label_save_status,
             self.label_dimensions, self.label_image_count,
             self.label_box_count, self.label_active_tool,
             self.label_zoom, self.label_coordinates),
            self.actions, self.zoom_widget, self)
        self.workspace_pages = canvas_column
        self.workspace_pages.sam_output_toggle.set_mode(self.sam_output_mode)
        self.workspace_pages.sam_output_toggle.modeChanged.connect(
            self._set_sam_output_mode)
        self.workspace_pages.empty_page.recentActivated.connect(
            self._open_workspace_recent)
        for tool_action in (
                self.actions.editMode, self.actions.create,
                self.actions.create_polygon, self.actions.sam_mode,
                self.actions.keypoint_mode):
            tool_action.changed.connect(self._update_active_tool_status)
        self.workspace_inspector = WorkspaceInspector(
            self.annotation_controls, self.file_controls, self)
        self.workspace_inspector.set_selected_tab(
            self.workspace_settings.inspector_tab)
        self.workspace_shell = WorkspaceSplitterShell(
            self.tool_rail, canvas_column, self.workspace_inspector,
            scale_px(self.workspace_settings.inspector_width),
            collapsed=self.workspace_settings.inspector_collapsed,
            parent=self)
        self.setCentralWidget(self.workspace_shell)
        self.setAcceptDrops(True)
        self._inspector_width_timer = QTimer(self)
        self._inspector_width_timer.setSingleShot(True)
        self._inspector_width_timer.setInterval(200)
        self._inspector_width_timer.timeout.connect(
            self._persist_inspector_width)
        self.workspace_shell.splitter.splitterMoved.connect(
            self._schedule_inspector_width_persist)
        self.workspace_shell.inspectorCollapsedChanged.connect(
            self._inspector_collapsed_changed)
        self.workspace_inspector.tabChanged.connect(
            self._inspector_tab_changed)
        self.canvas.modeChanged.connect(self._sync_tool_actions)
        self._sync_tool_actions()

        # Create dropdown for file/directory operations
        file_dropdown = DropdownToolButton(
            text=get_str('openFile'),
            icon=new_icon('file'),
            actions=[open, open_video, open_dir, change_save_dir]
        )

        self.actions.beginner = (
            file_dropdown, gallery_mode, None, open_next_image, open_prev_image, verify, save, save_format, None,
            create, create_polygon, keypoint_mode_action, sam_mode_action, copy, delete, None,
            zoom_in, zoom, zoom_out, fit_window, fit_width, None,
            brightness_dropdown)

        self.actions.advanced = (
            file_dropdown, gallery_mode, None, open_next_image, open_prev_image, save, save_format, None,
            create_mode, edit_mode, None,
            create_polygon, None,
            hide_all, show_all)

        compatibility_status = self.statusBar()
        compatibility_status.messageChanged.connect(
            self.label_status_message.setText)
        compatibility_status.showMessage('%s started.' % __appname__)
        compatibility_status.hide()

        # Application state.
        self.image = QImage()
        self.file_path = ustr(default_filename)
        self.last_open_dir = None
        self.recent_files = []
        self.max_recent = 7
        self.workspace_pages.empty_page.set_recent_paths(
            path for path in self.recent_files if os.path.exists(path))
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
        self.workspace_pages.empty_page.set_recent_paths(
            path for path in self.recent_files if os.path.exists(path))

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
            self.statusBar().hide()

        # Obsolete dock-layout bytes remain untouched for downgrade use. The
        # modern splitter restores only its validated workspace settings.
        Shape.line_color = self.line_color = QColor(settings.get(SETTING_LINE_COLOR, DEFAULT_LINE_COLOR))
        Shape.fill_color = self.fill_color = QColor(settings.get(SETTING_FILL_COLOR, DEFAULT_FILL_COLOR))
        self.canvas.set_drawing_color(self.line_color)
        # Add chris
        Shape.difficult = self.difficult

        def xbool(x):
            if isinstance(x, QVariant):
                return x.toBool()
            return bool(x)

        if xbool(settings.get(SETTING_GALLERY_MODE, False)):
            self.actions.galleryMode.setChecked(True)
            self.toggle_gallery_mode()

        # Populate the File menu dynamically.
        self.update_file_menu()

        # Since loading the file may take some time, make sure it runs in the background.
        if self.file_path and os.path.isdir(self.file_path):
            self.queue_event(partial(
                self.request_import_dir_images, self.file_path or ""))
        elif self.file_path:
            self.queue_event(partial(
                self.request_open_file, self.file_path or ""))

        # Callbacks:
        self.zoom_widget.valueChanged.connect(self.paint_canvas)
        self.zoom_widget.valueChanged.connect(self.update_zoom_display)
        self.light_widget.valueChanged.connect(self.paint_canvas)

        self.populate_mode_actions()

        # Replace the native in-app menu row with the compact workspace bar.
        # The original QMenus stay alive and are exposed as submenus so every
        # built-in and dynamically registered plugin command remains reachable.
        native_menu_bar = self.menuBar()
        native_menu_bar.hide()
        top_level_menus = (
            self.menus.file, self.menus.edit, self.menus.view,
            self.menus.tools, self.menus.plugins, self.menus.help,
        )
        self.command_bar = CommandBar(
            __appname__, top_level_menus,
            (open, open_video, open_dir, open_annotation,
             change_save_dir, self.menus.recentFiles),
            open_prev_image, open_next_image, save, verify, save_format,
            overflow_entries=(
                save, save_as, verify, save_format, None,
                close, reset_all,
            ),
            parent=self,
        )
        self._native_menu_bar = native_menu_bar
        self.setMenuWidget(self.command_bar)
        self.command_bar.apply_theme(self._current_theme)
        self._sync_command_bar()

        # Start auto-save timer if enabled (Issue #13)
        if self.auto_save_enabled.isChecked():
            self._toggle_auto_save_timer()

        self.plugin_command_host = QtPluginCommandHost(
            self, self.menus.plugins, self.shortcut_config,
            self._action_map, self.settings)
        self.plugin_manager.command_host = self.plugin_command_host
        self.plugin_manager.activate_enabled()

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.canvas.set_drawing_shape_to_square(False)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            # Draw rectangle if Ctrl is pressed
            self.canvas.set_drawing_shape_to_square(True)

    # Support Functions #
    def set_format(self, save_format):
        meta = format_metadata.by_name(save_format)
        if meta is None:
            return
        theme = getattr(self, '_current_theme', Theme.LIGHT)
        self.actions.save_format.setText(meta.name)
        self.actions.save_format.setIcon(themed_icon(meta.icon, theme))
        self.label_file_format = meta.enum
        LabelFile.suffix = meta.suffix

    def change_format(self):
        """Cycle through annotation formats: VOC -> YOLO -> CreateML -> COCO -> YOLO-seg -> VOC."""
        new_format, warning = format_metadata.next_in_cycle(self.label_file_format)

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
        return self.annotation_model.rowCount() == 0

    def toggle_advanced_mode(self, value=True):
        self._beginner = not value
        self.activate_select_tool()
        self.populate_mode_actions()
        self.edit_button.setVisible(not value)
        if value:
            self.actions.createMode.setEnabled(True)
            self.actions.editMode.setEnabled(False)

    def set_inspector_collapsed(self, collapsed):
        """Collapse or restore the fixed inspector."""
        if hasattr(self, 'workspace_shell'):
            self.workspace_shell.set_inspector_collapsed(collapsed)

    def _inspector_collapsed_changed(self, collapsed):
        self.settings[SETTING_INSPECTOR_COLLAPSED] = bool(collapsed)
        if hasattr(self.actions, 'inspectorVisible'):
            self.actions.inspectorVisible.blockSignals(True)
            self.actions.inspectorVisible.setChecked(not collapsed)
            self.actions.inspectorVisible.blockSignals(False)
        self.settings.save()

    def _inspector_tab_changed(self, tab):
        self.settings[SETTING_INSPECTOR_TAB] = (
            tab if tab in ('objects', 'files') else 'objects')
        self.settings.save()

    def _schedule_inspector_width_persist(self, _position, _index):
        if not self.workspace_shell.is_inspector_collapsed():
            self._inspector_width_timer.start()

    def _persist_inspector_width(self):
        if self.workspace_shell.is_inspector_collapsed():
            return
        scale = get_dpi_scale_factor() or 1.0
        logical_width = int(round(
            self.workspace_shell.inspector_width() / scale))
        logical_width = clamp_inspector_width(logical_width)
        self.workspace_shell.set_inspector_width(scale_px(logical_width))
        self.settings[SETTING_INSPECTOR_WIDTH] = logical_width
        self.settings.save()

    def toggle_gallery_mode(self, value=True):
        """Switch the central stack without detaching workspace chrome."""
        if hasattr(self, '_toggling_gallery') and self._toggling_gallery:
            return
        self._toggling_gallery = True
        self._gallery_batch_id += 1
        try:
            self.gallery_mode_enabled = bool(value)
            if self.gallery_mode_enabled:
                self.workspace_pages.set_page('gallery')
                QTimer.singleShot(0, self._refresh_full_gallery_statuses)
                QTimer.singleShot(100, self._refresh_all_statistics)
                if self.file_path:
                    self.full_gallery.select_image(self.file_path)
            else:
                page = ('empty' if self.document_kind == DocumentKind.NONE
                        else 'canvas')
                self.workspace_pages.set_page(page)
        finally:
            self._toggling_gallery = False

    def _cleanup_existing_gallery(self):
        """Compatibility hook: the embedded gallery has no resources to tear down."""
        if hasattr(self, 'workspace_pages'):
            page = ('empty' if self.document_kind == DocumentKind.NONE
                    else 'canvas')
            self.workspace_pages.set_page(page)

    def _create_gallery_window(self):
        """Compatibility entry point for the now-embedded gallery."""
        self.workspace_pages.set_page('gallery')

    def _exit_gallery_and_load(self, image_path):
        """Exit gallery mode and load the selected image."""
        self.actions.galleryMode.setChecked(False)
        self.toggle_gallery_mode(False)
        self.gallery_image_activated(image_path)

    def _refresh_full_gallery_statuses(self):
        """Apply the shared progressive catalog to the full gallery."""
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.update_all_statuses(
                self._annotation_status_cache)
        self._ensure_annotation_catalog()

    def populate_mode_actions(self):
        if self.beginner():
            menu = self.actions.beginnerContext
        else:
            menu = self.actions.advancedContext
        self.canvas.menus[0].clear()
        add_actions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (self.actions.create, self.actions.create_polygon) if self.beginner()\
            else (self.actions.createMode, self.actions.editMode, self.actions.create_polygon)
        add_actions(self.menus.edit, actions + self.actions.editMenu)

    def set_beginner(self):
        self._beginner = True
        self.populate_mode_actions()

    def set_advanced(self):
        self._beginner = False
        self.populate_mode_actions()

    def _video_editable(self):
        snapshot = getattr(self, 'video_snapshot', None)
        return not (
            self.document_kind == DocumentKind.VIDEO
            and snapshot is not None
            and snapshot.read_only)

    def _ensure_video_editable(self):
        if self._video_editable():
            return True
        self.status('This video is open read-only; editing is disabled')
        return False

    def set_dirty(self):
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                return
            self.pause_video()
            self.dirty = True
            self.actions.save.setEnabled(True)
            self.update_save_status(saved=False)
            self.update_box_count()
            self._sync_command_bar()
            self._publish_plugin_document()
            return
        self._document_revision += 1
        self.dirty = True
        self.actions.save.setEnabled(True)
        self.update_save_status(saved=False)
        self.update_box_count()
        self._sync_command_bar()
        self._publish_plugin_document()

    def set_clean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.create.setEnabled(True)
        self.actions.create_polygon.setEnabled(True)
        if (self.document_kind == DocumentKind.VIDEO
                and self.video_snapshot is not None
                and self.video_snapshot.read_only):
            self.actions.create.setEnabled(False)
            self.actions.create_polygon.setEnabled(False)
            self.actions.createMode.setEnabled(False)
            self.actions.editMode.setEnabled(False)
            self.actions.verify.setEnabled(False)
        self.update_save_status(saved=True)
        self._sync_command_bar()
        self._publish_plugin_document()

    def _plugin_document_descriptor(self):
        kind = getattr(self, 'document_kind', DocumentKind.NONE)
        source_path = None
        project_path = None
        read_only = True
        revision = 0
        dirty = False
        if kind == DocumentKind.IMAGE:
            source_path = self.file_path or None
            read_only = False
            revision = self._document_revision
            dirty = bool(self.dirty)
        elif kind == DocumentKind.VIDEO and self.video_snapshot is not None:
            source_path = self.video_snapshot.source_path
            project_path = self.video_snapshot.project_path
            if project_path is not None:
                project_path = os.fspath(project_path)
            read_only = bool(self.video_snapshot.read_only)
            revision = self._document_revision
            dirty = bool(self.dirty)
        return DocumentDescriptor(
            kind=kind.value,
            source_path=source_path,
            project_path=project_path,
            generation=self._plugin_document_generation,
            revision=revision,
            dirty=dirty,
            read_only=read_only,
        )

    def _publish_plugin_document(self, new_generation=False, force=False):
        manager = getattr(self, 'plugin_manager', None)
        if manager is None or (not self._plugin_document_ready and not force):
            return
        assert QApplication.instance().thread() == self.thread()
        if new_generation:
            self._plugin_document_generation += 1
        manager.publish_document(self._plugin_document_descriptor())

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
        if hasattr(self, 'actions') and hasattr(self.actions, 'sam_mode'):
            self.actions.sam_mode.setEnabled(
                bool(value) and getattr(self, '_sam_available', False))

    def queue_event(self, function):
        QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def update_status_bar(self):
        """Update all status bar widgets."""
        self.update_image_count()
        self.update_box_count()
        self.update_zoom_display()
        self._sync_command_bar()

    def _sync_command_bar(self):
        """Mirror document metadata without becoming a second state owner."""
        command_bar = getattr(self, 'command_bar', None)
        if command_bar is None:
            return
        source_path = getattr(self, 'file_path', None)
        name = os.path.basename(source_path) if source_path else 'No document'
        snapshot = getattr(self, 'video_snapshot', None)
        read_only = bool(
            self.document_kind == DocumentKind.VIDEO
            and snapshot is not None and snapshot.read_only)
        command_bar.set_document(
            name, dirty=getattr(self, 'dirty', False),
            full_path=source_path, read_only=read_only)

        if self.document_kind == DocumentKind.VIDEO:
            timeline = getattr(self, 'video_timeline', None)
            position = (
                timeline.position_label.text()
                if timeline is not None else '— / —')
        elif self.m_img_list and source_path:
            index = self._path_to_idx.get(source_path, -1) + 1
            position = '%s / %s' % (index, len(self.m_img_list))
        else:
            position = '— / —'
        command_bar.set_position(position)

    def update_image_count(self):
        """Update image counter in status bar."""
        if self.m_img_list and self.file_path:
            idx = self._path_to_idx.get(self.file_path, -1) + 1
            self.label_image_count.setText(f'Image: {idx} / {len(self.m_img_list)}')
        else:
            self.label_image_count.setText('Image: 0 / 0')
        size = getattr(self, '_original_image_size', QSize())
        if size is None or not size.isValid():
            size = self.image.size() if self.image is not None else QSize()
        self.label_dimensions.setText(
            '%s x %s' % (size.width(), size.height())
            if size.isValid() else '0 x 0')

    def update_box_count(self):
        """Update annotation count in status bar."""
        count = len(self.canvas.shapes) if self.canvas else 0
        self.label_box_count.setText(f'Objects: {count}')

    def update_zoom_display(self):
        """Update zoom level in status bar."""
        if self.zoom_widget:
            self.label_zoom.setText(f'Zoom: {self.zoom_widget.value()}%')

    def _update_save_status_style(self, saved):
        """Update save status indicator style based on theme."""
        from libs.utils.styles import get_theme_colors
        colors = get_theme_colors(self._current_theme)
        read_only = (
            self.document_kind == DocumentKind.VIDEO
            and self.video_snapshot is not None
            and self.video_snapshot.read_only)
        if read_only:
            color = colors['text_secondary']
            tooltip = 'Read-only'
        elif saved:
            color = colors['status_saved']
            tooltip = 'Saved'
        else:
            color = colors['status_unsaved']
            tooltip = 'Unsaved changes'

        self.label_save_status.setText('● ' + tooltip)
        self.label_save_status.setStyleSheet(
            f'color: {color}; font-size: 12px;')
        self.label_save_status.setToolTip(tooltip)

    def update_save_status(self, saved=True):
        """Update save status indicator in status bar."""
        self._update_save_status_style(saved)

    def reset_state(self):
        self._dismiss_class_picker()
        self._plugin_document_ready = False
        self._restart_workers_if_needed()
        self._close_video_decoder()
        self._set_document_kind(DocumentKind.NONE)
        self.annotation_model.clear()
        self.annotation_search.clear()
        self.file_path = None
        self.image_data = None
        self._original_image_size = QSize()
        self.label_file = None
        self.canvas.reset_state()
        self.label_coordinates.clear()
        self.combo_box.cb.clear()
        # Clear undo stack when loading new file
        self.undo_stack.clear()
        # Reset status bar widgets
        self.label_box_count.setText('Objects: 0')
        self.update_save_status(saved=True)
        self._sync_command_bar()
        self._publish_plugin_document(new_generation=True, force=True)

    def _set_document_kind(self, kind):
        """Switch cache policy and document-only UI without touching content."""
        previous = getattr(self, 'document_kind', DocumentKind.NONE)
        if previous != kind and hasattr(self, 'frame_cache'):
            self.frame_cache.clear()
        self.document_kind = kind
        if hasattr(self, 'frame_cache'):
            self.frame_cache.max_images = (
                12 if kind == DocumentKind.VIDEO else 5)
        if hasattr(self, 'workspace_pages'):
            self.workspace_pages.set_video_visible(
                kind == DocumentKind.VIDEO)
            if not self.gallery_mode_enabled:
                self.workspace_pages.set_page(
                    'empty' if kind == DocumentKind.NONE else 'canvas')
        if hasattr(self, 'annotation_model'):
            if kind == DocumentKind.VIDEO:
                pts = (None if self.current_video_frame_ref is None else
                       self.current_video_frame_ref.pts)
                self.annotation_model.set_video_context(self.video_model, pts)
            elif kind == DocumentKind.NONE:
                self.annotation_model.clear()
        if kind != DocumentKind.VIDEO and hasattr(self, 'diffc_button'):
            self.diffc_button.setEnabled(True)
        if hasattr(self, 'actions') and hasattr(
                self.actions, 'videoPlayPause'):
            self.actions.verify.setEnabled(kind != DocumentKind.NONE)
            self.actions.videoPlayPause.setEnabled(
                kind == DocumentKind.VIDEO)
            self.actions.videoExport.setEnabled(
                kind == DocumentKind.VIDEO)
            self.actions.videoAddKeyframe.setEnabled(False)
            self.actions.videoEditSpan.setEnabled(False)
            self.actions.videoDeleteTrack.setEnabled(False)
            self.actions.videoTrackForward.setEnabled(False)
            self.actions.videoTrackBackward.setEnabled(False)
            self.actions.videoAcceptSuggestion.setEnabled(False)
            self.actions.videoRejectSuggestion.setEnabled(False)
            self.actions.videoAcceptVisible.setEnabled(False)
            self.actions.videoRejectVisible.setEnabled(False)
            self.actions.videoAcceptRun.setEnabled(False)
            self.actions.videoRejectRun.setEnabled(False)

    def _close_video_decoder(self, close_decoder=True):
        if hasattr(self, '_video_playback_timer'):
            self.pause_video()
        if hasattr(self, '_tracking_handle'):
            self.cancel_video_tracking()
        if hasattr(self, '_video_export_handle'):
            self.cancel_video_export()
        decoder = getattr(self, 'video_decoder', None)
        self.video_decoder = None
        snapshot = getattr(self, 'video_snapshot', None)
        self.video_snapshot = None
        self.video_model = None
        self._selected_video_track_id = None
        self._video_save_active = False
        self._video_save_queued = False
        self._video_save_callbacks = []
        self._video_close_save_pending = False
        self.current_video_frame_ref = None
        if hasattr(self, 'video_timeline'):
            self.video_timeline.set_session(None)
        if decoder is not None and close_decoder:
            coordinator = getattr(self, 'task_coordinator', None)
            if coordinator is not None and not coordinator.is_shutting_down:
                handle = coordinator.submit(
                    'video', lambda _handle, session=decoder: session.close(),
                    priority=JobPriority.IMAGE_LOAD,
                    generation=self._dataset_generation)
                # Session teardown must stay ordered behind any active decode,
                # even if a later document generation cancels ordinary work.
                handle.begin_non_cancellable()
            else:
                decoder.close()
        if (snapshot is not None and snapshot.project_path
                and not snapshot.read_only and not self.dirty):
            try:
                checkpoint_project(snapshot.project_path)
            except Exception:
                pass
        return decoder

    def _restart_workers_if_needed(self):
        coordinator = getattr(self, 'task_coordinator', None)
        if coordinator is None or not coordinator.is_shutting_down:
            return
        self.task_coordinator = TaskCoordinator(parent=self)
        old_catalog = self.annotation_catalog
        self.annotation_catalog = AnnotationCatalog(
            self.task_coordinator, parent=self)
        self.annotation_catalog.batch_ready.connect(
            self._on_catalog_batch)
        self.annotation_catalog.statistics_ready.connect(
            self._on_catalog_statistics)
        self.annotation_catalog.error.connect(
            lambda message: self.status('Annotation catalog: ' + message))
        old_catalog.deleteLater()
        if hasattr(self, 'gallery_widget'):
            self.gallery_widget.set_task_coordinator(self.task_coordinator)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.set_task_coordinator(self.task_coordinator)

    def current_item(self):
        """Return the selected source-model index in the unified view."""
        indexes = self.label_list.selectionModel().selectedRows()
        if not indexes:
            return None
        return self.annotation_proxy.mapToSource(indexes[0])

    def current_annotation_identity(self):
        index = self.current_item()
        return (None if index is None else
                self.annotation_model.identity_at(index))

    def current_shape(self):
        index = self.current_item()
        if index is None:
            return None
        if self.document_kind == DocumentKind.VIDEO:
            track_id = self.annotation_model.identity_at(index)
            return next((shape for shape in self.canvas.shapes
                         if getattr(shape, 'video_track_id', None) == track_id),
                        None)
        return self.annotation_model.shape_at(index)

    def _select_annotation_identity(self, identity):
        source = self.annotation_model.index_for_identity(identity)
        self.annotation_model.set_selected_identity(identity)
        if not source.isValid():
            self.label_list.clearSelection()
            return
        proxy = self.annotation_proxy.mapFromSource(source)
        if proxy.isValid():
            self.label_list.selectionModel().setCurrentIndex(
                proxy, QItemSelectionModel.ClearAndSelect |
                QItemSelectionModel.Rows)

    def add_recent_file(self, file_path):
        if file_path in self.recent_files:
            self.recent_files.remove(file_path)
        elif len(self.recent_files) >= self.max_recent:
            self.recent_files.pop()
        self.recent_files.insert(0, file_path)
        if hasattr(self, 'workspace_pages'):
            self.workspace_pages.empty_page.set_recent_paths(
                path for path in self.recent_files if os.path.exists(path))

    def _open_workspace_recent(self, path):
        if os.path.isdir(path):
            return self.request_import_dir_images(path)
        return self.request_open_file(path)

    def _supported_workspace_drop(self, path):
        if not path or not os.path.exists(path):
            return False
        if os.path.isdir(path):
            return True
        lower = path.lower()
        return (is_video_project(path)
                or lower.endswith(VIDEO_EXTENSIONS)
                or lower.endswith(self._supported_image_extensions()))

    def _workspace_drop_path(self, event):
        mime = event.mimeData()
        urls = mime.urls() if mime is not None and mime.hasUrls() else []
        if len(urls) != 1 or not urls[0].isLocalFile():
            return None
        path = os.path.abspath(ustr(urls[0].toLocalFile()))
        return path if self._supported_workspace_drop(path) else None

    def dragEnterEvent(self, event):
        if self._workspace_drop_path(event) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        path = self._workspace_drop_path(event)
        if path is None:
            event.ignore()
            self.status('Drop exactly one supported local file or directory')
            return
        event.acceptProposedAction()
        self._open_workspace_recent(path)

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

    def show_plugins_dialog(self):
        dialog = PluginManagerDialog(self.plugin_manager, self)
        if hasattr(self, '_current_theme'):
            dialog.setStyleSheet(get_stylesheet(self._current_theme))
        dialog.exec_()

    def create_shape(self):
        """Compatibility callback for the Bounding Box action."""
        self.activate_box_tool()

    def activate_box_tool(self):
        """Activate rectangle drawing without depending on legacy UI mode."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            self._sync_tool_actions()
            return
        self._leave_special_tool_modes()
        self.canvas.set_editing(False)
        self.actions.create.setEnabled(False)
        self.actions.create_polygon.setEnabled(True)
        self.actions.editMode.setEnabled(True)
        self._finish_tool_activation()

    def create_polygon_mode(self):
        """Compatibility callback for the Polygon action."""
        self.activate_polygon_tool()

    def activate_polygon_tool(self):
        """Activate polygon drawing without depending on legacy UI mode."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            self._sync_tool_actions()
            return
        self._leave_special_tool_modes()
        self.canvas.set_polygon_drawing(True)
        self.actions.create.setEnabled(True)
        self.actions.create_polygon.setEnabled(False)
        self.actions.editMode.setEnabled(True)
        self._finish_tool_activation()

    def toggle_keypoint_mode(self):
        """Toggle keypoint annotation mode for the selected shape."""
        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.activate_select_tool()
            return
        self.activate_keypoint_tool()

    def activate_keypoint_tool(self):
        """Activate keypoint placement for the selected eligible shape."""
        from libs.core.keypoint_config import get_template

        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            self._sync_tool_actions()
            return

        shape = self.canvas.selected_shape
        if not shape or shape.shape_type != ShapeType.RECTANGLE:
            self._sync_tool_actions()
            return

        template = get_template(shape.label)
        if not template:
            self._sync_tool_actions()
            return

        self.sam_controller.set_enabled(False)

        template_name = shape.label.lower()
        kp_count = len(template['names'])

        if shape.keypoints is None:
            shape.keypoints = [None] * kp_count

        self.keypoint_panel.load_template(template_name)
        self.canvas.set_keypoint_mode(shape, template_name)
        self.keypoint_panel.set_keypoints(shape.keypoints)
        self.keypoint_panel.set_current_index(self.canvas._keypoint_index)
        self.keypoint_panel.show()
        self._finish_tool_activation()

    def toggle_sam_mode(self):
        """Enter/leave single-click SAM segmentation mode."""
        if self.canvas.mode == self.canvas.CREATE_SAM:
            self.activate_select_tool()
            return
        self.activate_smart_select_tool()

    def activate_smart_select_tool(self):
        """Activate Smart Select while keeping optional imports lazy."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            self._sync_tool_actions()
            return
        if not segmentation.sam_available():
            QMessageBox.warning(
                self, "SAM unavailable",
                "Install with: pip install labelimgplusplus[sam]")
            self._sync_tool_actions()
            return
        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.canvas.exit_keypoint_mode()
            self.keypoint_panel.hide()
        self.canvas.set_sam_mode(True)
        self.sam_controller.set_enabled(True)
        # set_sam_mode does not emit drawingPolygon, so re-enable the mode-switch
        # actions here (mirroring create_polygon_mode) so the user can leave SAM.
        self.actions.create.setEnabled(True)
        self.actions.create_polygon.setEnabled(True)
        self.actions.editMode.setEnabled(True)
        self._finish_tool_activation()

    def activate_select_tool(self):
        """Return to the neutral canvas selection/editing tool."""
        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.canvas.exit_keypoint_mode()
            self.keypoint_panel.hide()
        self.sam_controller.set_enabled(False)
        self.canvas.set_editing(True)
        editable = self._video_editable()
        self.actions.create.setEnabled(editable and bool(self.file_path))
        self.actions.create_polygon.setEnabled(
            editable and bool(self.file_path))
        self.actions.editMode.setEnabled(False)
        self._finish_tool_activation()

    def _leave_special_tool_modes(self):
        if self.canvas.mode == self.canvas.KEYPOINT_MODE:
            self.canvas.exit_keypoint_mode()
            self.keypoint_panel.hide()
        self.sam_controller.set_enabled(False)

    def _finish_tool_activation(self):
        self._sync_tool_actions()
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _sync_tool_actions(self, _mode=None):
        """Mirror the authoritative canvas mode into the exclusive actions."""
        if not hasattr(self, 'actions'):
            return
        mapping = {
            self.canvas.EDIT: self.actions.editMode,
            self.canvas.CREATE: self.actions.create,
            self.canvas.CREATE_POLYGON: self.actions.create_polygon,
            self.canvas.CREATE_SAM: self.actions.sam_mode,
            self.canvas.KEYPOINT_MODE: self.actions.keypoint_mode,
        }
        active = mapping.get(self.canvas.mode, self.actions.editMode)
        active.setChecked(True)
        if hasattr(self, 'workspace_pages'):
            self.workspace_pages.sam_output_toggle.setVisible(
                self.canvas.mode == self.canvas.CREATE_SAM)
        self._update_active_tool_status()

    def _set_sam_output_mode(self, mode):
        """Persist the contextual Smart Select geometry choice."""
        self.sam_output_mode = normalize_sam_output_mode(mode)
        self.workspace_pages.sam_output_toggle.set_mode(self.sam_output_mode)
        self.settings[SETTING_SAM_OUTPUT_MODE] = self.sam_output_mode
        self.settings.save()
        self._restore_canvas_focus()

    def _update_active_tool_status(self):
        if not hasattr(self, 'label_active_tool'):
            return
        active = next((action for action in (
            self.actions.editMode, self.actions.create,
            self.actions.create_polygon, self.actions.sam_mode,
            self.actions.keypoint_mode) if action.isChecked()),
            self.actions.editMode)
        shortcut = active.shortcut().toString()
        names = {
            self.actions.editMode: 'Select',
            self.actions.create: 'Bounding Box',
            self.actions.create_polygon: 'Polygon',
            self.actions.sam_mode: 'Smart Select',
            self.actions.keypoint_mode: 'Keypoints',
        }
        self.label_active_tool.setText(
            '%s%s' % (names.get(active, active.text().replace('&', '')),
                      ' (%s)' % shortcut if shortcut else ''))

    def open_sam_settings(self):
        """Open the SAM configuration dialog."""
        from libs.widgets.sam_settings_dialog import SamSettingsDialog
        dialog = SamSettingsDialog(
            encoder_path=self.settings.get(SETTING_SAM_ENCODER, ""),
            decoder_path=self.settings.get(SETTING_SAM_DECODER, ""),
            parent=self)
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)
        if dialog.exec_():
            values = dialog.values()
            self.settings[SETTING_SAM_ENCODER] = values["encoder"]
            self.settings[SETTING_SAM_DECODER] = values["decoder"]
            self.settings.save()
            if hasattr(self, 'sam_controller'):
                self.sam_controller.reset_backend()    # reload model on next use

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
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
                return
            before = self.video_model.snapshot_state()
            self._store_video_shape_as_manual(shape)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Edit video polygon keyframe'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return
        cmd = EditPolygonVerticesCommand(
            self, shape, old_points, list(shape.points))
        self.undo_stack.push(cmd)
        self.set_dirty()

    def _on_shape_move_finished(self, shape, old_points):
        """Capture whole-shape moves / rectangle resizes for undo support."""
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
                return
            before = self.video_model.snapshot_state()
            self._store_video_shape_as_manual(shape)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Edit video track keyframe'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return
        cmd = MoveShapeCommand(self, shape, old_points, list(shape.points))
        self.undo_stack.push(cmd)
        self.set_dirty()

    def _on_keypoints_edited(self, shape, old_keypoints):
        """Capture keypoint mutations for undo support."""
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
                return
            before = self.video_model.snapshot_state()
            self._store_video_shape_as_manual(shape)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Edit video keypoints'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return
        cmd = EditKeypointsCommand(
            self, shape, old_keypoints,
            list(shape.keypoints) if shape.keypoints else None)
        self.undo_stack.push(cmd)
        self.set_dirty()

    def toggle_drawing_sensitive(self, drawing=True):
        """In the middle of drawing, toggling between modes should be disabled."""
        if drawing and self.document_kind == DocumentKind.VIDEO:
            self.pause_video()
        editable = self._video_editable()
        self.actions.editMode.setEnabled(not drawing and editable)
        self.actions.create.setEnabled(not drawing and editable)
        self.actions.create_polygon.setEnabled(not drawing and editable)
        if not drawing:
            self.canvas.restore_cursor()
            self._sync_tool_actions()

    def toggle_draw_mode(self, edit=True):
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        self.canvas.set_editing(edit)
        self.actions.createMode.setEnabled(edit)
        self.actions.editMode.setEnabled(not edit)
        self.actions.create_polygon.setEnabled(edit)

    def set_create_mode(self):
        """Compatibility callback routed to the modern box entry point."""
        self.activate_box_tool()

    def set_edit_mode(self):
        """Compatibility callback routed to the modern select entry point."""
        self.activate_select_tool()
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
        self.menus.labelList.exec_(self.label_list.mapToGlobal(point))

    def edit_label(self, *_args):
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        if not self.canvas.editing():
            return
        index = self.current_item()
        if index is None:
            return
        text = self.label_dialog.pop_up(
            self.annotation_model.data(index, AnnotationRoles.Class))
        if text is not None:
            self._annotation_class_edit_requested(
                self.annotation_model.identity_at(index), text)

    # Tzutalin 20160906 : Add file list and dock to move faster
    def file_item_double_clicked(self, item=None):
        item_path = ustr(item.text())
        self.cur_img_idx = self._path_to_idx.get(item_path, 0)
        filename = self.m_img_list[self.cur_img_idx]
        if filename:
            self.request_load_file(filename)

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
            self.request_load_file(image_path)

    def on_file_view_tab_changed(self, index):
        """Handle tab switch between list and gallery view."""
        if index == 1:  # Gallery tab
            self._refresh_gallery_statuses()

    def _get_annotation_status(self, image_path, use_cache=True):
        """Determine annotation status for an image with optional caching."""
        # Check cache first for O(1) lookup
        if use_cache and image_path in self._annotation_status_cache:
            return self._annotation_status_cache[image_path]

        entry = self.annotation_catalog.entries.get(image_path)
        if entry is not None:
            status = AnnotationStatus(entry.status)
        else:
            status = _probe_status(
                image_path, self.default_save_dir, self.m_img_list,
                resolver=self._active_annotation_resolver(image_path))

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
        """Update dock statuses from the single progressive catalog."""
        self.gallery_widget.update_all_statuses(
            self._annotation_status_cache)
        self._ensure_annotation_catalog()

    def _active_annotation_resolver(self, image_path=None):
        snapshot = getattr(self, 'dataset_snapshot', None)
        if snapshot is None:
            return None
        if (image_path is not None
                and os.path.abspath(os.fspath(image_path))
                not in snapshot.path_to_index):
            return None
        return snapshot.resolver

    def _shared_annotation_path(self, image_path, resolver=None):
        if resolver is not None:
            path = resolver.named_file(image_path, 'annotations.json')
            if path:
                return path
        directories = []
        if self.default_save_dir:
            directories.append(ustr(self.default_save_dir))
        directories.append(os.path.dirname(os.path.abspath(image_path)))
        for directory in directories:
            path = os.path.join(directory, 'annotations.json')
            if os.path.isfile(path):
                return path
        return None

    def _ensure_annotation_catalog(self):
        coordinator = getattr(self, 'task_coordinator', None)
        if coordinator is None or coordinator.is_shutting_down:
            return False
        snapshot = getattr(self, 'dataset_snapshot', None)
        if snapshot is None or not snapshot.image_paths:
            return False
        if (self.annotation_catalog.snapshot is not snapshot
                or (not self.annotation_catalog.entries
                    and self.annotation_catalog._handle is None)):
            self.annotation_catalog.start(snapshot)
        return True

    def _on_catalog_batch(self, statuses):
        converted = {
            path: AnnotationStatus(status)
            for path, status in statuses.items()
        }
        self._annotation_status_cache.update(converted)
        if hasattr(self, 'gallery_widget') and self.gallery_widget:
            self.gallery_widget.update_all_statuses(converted)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.update_all_statuses(converted)
        filter_index = (self.status_filter_combo.currentIndex()
                        if hasattr(self, 'status_filter_combo') else 0)
        if filter_index:
            for path, status in converted.items():
                index = self._path_to_idx.get(path)
                if index is not None and index < self.file_list_widget.count():
                    self.file_list_widget.item(index).setHidden(
                        not self._status_matches_filter(status, filter_index))

    @staticmethod
    def _status_matches_filter(status, index):
        if index == 0:
            return True
        if index == 1:
            return status in (
                AnnotationStatus.HAS_LABELS, AnnotationStatus.VERIFIED)
        if index == 2:
            return status == AnnotationStatus.VERIFIED
        if index == 3:
            return status == AnnotationStatus.NO_LABELS
        return False

    def _on_catalog_statistics(self, total, annotated, verified,
                               label_counts):
        widget = getattr(self, 'gallery_stats', None)
        if widget is None:
            return
        widget.update_dataset_stats(total, annotated, verified)
        widget.update_label_distribution(label_counts)
        self._update_current_image_stats()

    def _update_current_image_gallery_status(self):
        """Reload gallery state for the current persisted annotation."""
        if self.file_path:
            # Invalidate cache for this file to get fresh status
            self._invalidate_status_cache(self.file_path)
            status = self._get_annotation_status(self.file_path)
            self.gallery_widget.update_status(self.file_path, status)
            self.gallery_widget.refresh_thumbnail(self.file_path)
            # Also update full-screen gallery if active
            if hasattr(self, 'full_gallery') and self.full_gallery:
                self.full_gallery.update_status(self.file_path, status)
                self.full_gallery.refresh_thumbnail(self.file_path)

    # Add chris
    def button_state(self, item=None):
        """ Function to handle difficult examples
        Update on each object """
        if not self.canvas.editing():
            return

        difficult = self.diffc_button.isChecked()
        identity = self.current_annotation_identity()
        shape = self.current_shape()

        if self.document_kind == DocumentKind.VIDEO:
            track = (None if identity is None or self.video_model is None else
                     self.video_model.tracks.get(identity))
            if track is None:
                return
            if difficult == track.difficult:
                return
            if not self._ensure_video_editable():
                blocked = self.diffc_button.blockSignals(True)
                self.diffc_button.setChecked(track.difficult)
                self.diffc_button.blockSignals(blocked)
                return
            before = self.video_model.snapshot_state()
            self.video_model.update_track(identity, difficult=difficult)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Change video track difficulty'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return

        if shape is None and self.canvas.shapes:
            shape = self.canvas.shapes[-1]
        if shape is None:
            return

        # Checked and Update
        if difficult != shape.difficult:
            old_difficult = shape.difficult
            shape.difficult = difficult
            self.undo_stack.push(EditShapeAttributesCommand(
                self, shape, {'difficult': old_difficult},
                {'difficult': difficult}, 'Change shape difficulty'))
            self.annotation_model.notify_identity_changed(
                self.annotation_model.identity_for_shape(shape))
            self.set_dirty()

    # React to canvas signals.
    def shape_selection_changed(self, selected=False):
        if self._no_selection_slot:
            self._no_selection_slot = False
        else:
            shape = self.canvas.selected_shape
            if shape:
                if self.document_kind == DocumentKind.VIDEO:
                    self._selected_video_track_id = getattr(
                        shape, 'video_track_id', None)
                    identity = self._selected_video_track_id
                else:
                    identity = self.annotation_model.identity_for_shape(shape)
                self._select_annotation_identity(identity)
            else:
                self.label_list.clearSelection()
                self.annotation_model.set_selected_identity(None)
        editable = self._video_editable()
        self.actions.delete.setEnabled(selected and editable)
        self.actions.copy.setEnabled(selected and editable)
        self.actions.copyToClipboard.setEnabled(selected)
        self.actions.edit.setEnabled(selected and editable)
        self.actions.shapeLineColor.setEnabled(selected and editable)
        self.actions.shapeFillColor.setEnabled(selected and editable)
        # Enable paste if clipboard has shapes
        self.actions.pasteFromClipboard.setEnabled(
            len(self.clipboard_shapes) > 0 and editable)
        # Enable copy all if there are shapes
        self.actions.copyAllToClipboard.setEnabled(len(self.canvas.shapes) > 0)

        # Show/hide keypoint panel based on selection
        from libs.core.keypoint_config import get_template
        shape = self.canvas.selected_shape
        has_template = (shape is not None
                        and shape.shape_type == ShapeType.RECTANGLE
                        and get_template(shape.label) is not None)
        self.actions.keypoint_mode.setEnabled(has_template and editable)
        if has_template and shape.keypoints:
            self.keypoint_panel.load_template(shape.label.lower())
            self.keypoint_panel.set_keypoints(shape.keypoints)
            self.keypoint_panel.show()
        else:
            self.keypoint_panel.hide()

    def add_label(self, shape, row=None, refresh=True):
        shape.paint_label = self.display_label_option.isChecked()
        if self.document_kind != DocumentKind.VIDEO:
            self.annotation_model.set_image_shapes(self.canvas.shapes)
        if refresh:
            for action in self.actions.onShapesPresent:
                action.setEnabled(True)
            self.update_combo_box()

    def remove_label(self, shape):
        """Remove a shape's label-list item. Returns the row it occupied
        (or None) so a caller can restore the exact ordering on undo."""
        if shape is None:
            return None
        index = self.annotation_model.index_for_identity(
            self.annotation_model.identity_for_shape(shape))
        row = index.row() if index.isValid() else None
        if self.document_kind != DocumentKind.VIDEO:
            self.annotation_model.set_image_shapes(self.canvas.shapes)
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

                self.add_label(shape, refresh=False)
        for action in self.actions.onShapesPresent:
            action.setEnabled(bool(s))
        self.canvas.load_shapes(s)
        self.annotation_model.set_image_shapes(s)
        self.update_combo_box()

    def update_combo_box(self):
        if self.document_kind == DocumentKind.VIDEO and self.video_model:
            items_text_list = [
                track.label for track in self.video_model.tracks.values()]
        else:
            items_text_list = [shape.label for shape in self.canvas.shapes]

        unique_text_list = list(set(items_text_list))
        # Add a null row for showing all the labels
        unique_text_list.append("")
        unique_text_list.sort()

        self.combo_box.update_items(unique_text_list)

    def _update_tab_counts(self):
        """Compatibility hook; the unified inspector has no nested tabs."""
        return self.annotation_model.rowCount()

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

        def get_str(str_id):
            return self.string_bundle.get_string(str_id)
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
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        shape = self.canvas.copy_selected_shape()
        self.add_label(shape)

        if self.document_kind == DocumentKind.VIDEO:
            before = self.video_model.snapshot_state()
            if hasattr(shape, 'video_track_id'):
                del shape.video_track_id
            track_id = self._store_video_shape_as_manual(shape)
            self._selected_video_track_id = track_id
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Duplicate video track'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
        else:
            # Push command for undo support (shape already created).
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
        self.actions.pasteFromClipboard.setEnabled(self._video_editable())
        self.statusBar().showMessage('Copied 1 annotation to clipboard', 3000)

    def copy_all_to_clipboard(self):
        """Copy all shapes to clipboard for pasting across images."""
        if not self.canvas.shapes:
            return
        # Store copies of all shapes
        self.clipboard_shapes = [shape.copy() for shape in self.canvas.shapes]
        self.actions.pasteFromClipboard.setEnabled(self._video_editable())
        self.statusBar().showMessage(f'Copied {len(self.clipboard_shapes)} annotations to clipboard', 3000)

    def paste_from_clipboard(self):
        """Paste shapes from clipboard to current image."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        if not self.clipboard_shapes:
            return
        if not self.canvas.pixmap or self.canvas.pixmap.isNull():
            return

        before = (self.video_model.snapshot_state()
                  if self.document_kind == DocumentKind.VIDEO else None)
        for clipboard_shape in self.clipboard_shapes:
            # Create a new copy for each paste
            shape = clipboard_shape.copy()
            # Add shape to canvas
            self.canvas.shapes.append(shape)
            self.add_label(shape)
            if self.document_kind == DocumentKind.VIDEO:
                self._store_video_shape_as_manual(shape)
            else:
                cmd = CreateShapeCommand(self, shape)
                self.undo_stack.push(cmd)

        self.canvas.rebuild_spatial_index()
        if self.document_kind == DocumentKind.VIDEO:
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Paste video tracks'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
        else:
            self.set_dirty()
        self.canvas.update()
        self.update_box_count()
        self.statusBar().showMessage(f'Pasted {len(self.clipboard_shapes)} annotations', 3000)

    def combo_selection_changed(self, index):
        text = self.combo_box.cb.itemText(index)
        for row in range(self.annotation_model.rowCount()):
            source = self.annotation_model.index(row, 0)
            label = self.annotation_model.data(source, AnnotationRoles.Class)
            self.annotation_model.setData(
                source, Qt.Checked if not text or text == label
                else Qt.Unchecked, Qt.CheckStateRole)

    def default_label_combo_selection_changed(self, index):
        self.default_label=self.label_hist[index]

    def label_selection_changed(self, *_args):
        # Guard selection feedback between the inspector and canvas.
        if hasattr(self, '_updating_label_selection') and self._updating_label_selection:
            return
        self._updating_label_selection = True
        try:
            identity = self.current_annotation_identity()
            self.annotation_model.set_selected_identity(identity)
            if identity is None:
                return
            if self.document_kind == DocumentKind.VIDEO:
                self._selected_video_track_id = identity
                self._sync_video_track_actions(identity)
                shape = self.current_shape()
                track = (None if self.video_model is None else
                         self.video_model.tracks.get(identity))
            else:
                shape = self.current_shape()
                track = None
            if shape is not None and self.canvas.editing():
                self._no_selection_slot = True
                self.canvas.select_shape(shape)
            difficult = (shape.difficult if shape is not None else
                         (track.difficult if track is not None else False))
            blocked = self.diffc_button.blockSignals(True)
            self.diffc_button.setChecked(difficult)
            self.diffc_button.blockSignals(blocked)
        finally:
            self._updating_label_selection = False

    def _annotation_visibility_changed(self, identity, visible):
        if self.document_kind == DocumentKind.VIDEO:
            shapes = [shape for shape in self.canvas.shapes
                      if getattr(shape, 'video_track_id', None) == identity]
        else:
            shape = self.annotation_model.object_for_identity(identity)
            shapes = [] if shape is None else [shape]
        for shape in shapes:
            self.canvas.set_shape_visible(shape, visible)

    def _annotation_class_edit_requested(self, identity, label):
        label = str(label).strip()
        if not label:
            return
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable() or self.video_model is None:
                return
            track = self.video_model.tracks.get(identity)
            if track is None or track.label == label:
                return
            before = self.video_model.snapshot_state()
            self.video_model.rename_track(identity, label)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Rename video track'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return
        shape = self.annotation_model.object_for_identity(identity)
        if shape is None or shape.label == label:
            return
        old_label = shape.label
        shape.label = label
        shape.line_color = generate_color_by_text(label)
        self.undo_stack.push(EditLabelCommand(
            self, shape, old_label, label))
        self.annotation_model.notify_identity_changed(identity)
        self.update_combo_box()
        self.canvas.update()
        self.set_dirty()

    def label_item_changed(self, item):
        """Legacy entry point routed through the unified model."""
        index = self.current_item()
        if index is not None:
            self._annotation_class_edit_requested(
                self.annotation_model.identity_at(index), str(item.text()))

    # Callback functions:
    def new_shape(self):
        """Stage completed geometry until its class is confirmed."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            self._cancel_provisional_shape()
            return
        shape = self.canvas.provisional_shape
        if shape is None:
            return
        if (self._pending_provisional_shape is not None
                and self._pending_provisional_shape is not shape):
            self._dismiss_class_picker(discard=False)
        self._pending_provisional_shape = shape

        if self.use_default_label_checkbox.isChecked():
            text = getattr(self, 'default_label', '')
            if text:
                self._commit_provisional_shape(text)
            else:
                self._cancel_provisional_shape()
            return
        if self.single_class_mode.isChecked() and self._session_last_class:
            self._commit_provisional_shape(self._session_last_class)
            return

        self.class_picker.open_at(
            self.label_hist,
            self._session_last_class or self.prev_label_text,
            self._provisional_picker_anchor(shape))

    def _provisional_picker_anchor(self, shape):
        """Return a global logical-pixel anchor beside provisional geometry."""
        xs = [point.x() for point in shape.points]
        ys = [point.y() for point in shape.points]
        offset = self.canvas.offset_to_center()
        point = QPoint(
            int(round((max(xs) + offset.x()) * self.canvas.scale)),
            int(round((min(ys) + offset.y()) * self.canvas.scale)))
        return self.canvas.mapToGlobal(point)

    def _commit_provisional_shape(self, text):
        text = str(text).strip()
        pending = self._pending_provisional_shape
        if (not text or pending is None
                or self.canvas.provisional_shape is not pending):
            self._cancel_provisional_shape()
            return

        video_before = (self.video_model.snapshot_state()
                        if self.document_kind == DocumentKind.VIDEO else None)
        shape = self.canvas.commit_provisional_shape(
            text, generate_color_by_text(text))
        self._pending_provisional_shape = None
        if shape is None:
            return
        self.add_label(shape)

        if self.document_kind == DocumentKind.VIDEO:
            track_id = self._store_video_shape_as_manual(shape)
            self._selected_video_track_id = track_id
            video_after = self.video_model.snapshot_state()
            self.undo_stack.push(CreateShapeCommand(
                self, shape, video_before=video_before,
                video_after=video_after))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
        else:
            self.undo_stack.push(CreateShapeCommand(self, shape))
            self.set_dirty()

        self.prev_label_text = text
        self.lastLabel = text
        self._session_last_class = text
        if text not in self.label_hist:
            self.label_hist.append(text)
        self._update_current_image_stats()
        self._sync_tool_actions()
        self._restore_canvas_focus()

    def _cancel_provisional_shape(self):
        self._pending_provisional_shape = None
        self.canvas.discard_provisional_shape()
        self._sync_tool_actions()
        self._restore_canvas_focus()

    def _restore_canvas_focus(self):
        QApplication.setActiveWindow(self)
        self.activateWindow()
        self.setFocusProxy(self.canvas)
        self.canvas.setFocus(Qt.OtherFocusReason)

    def _dismiss_class_picker(self, discard=True):
        picker = getattr(self, 'class_picker', None)
        if picker is not None:
            blocked = picker.blockSignals(True)
            picker.hide()
            picker.blockSignals(blocked)
        self._pending_provisional_shape = None
        if discard and hasattr(self, 'canvas'):
            self.canvas.discard_provisional_shape()

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
        for row in range(self.annotation_model.rowCount()):
            index = self.annotation_model.index(row, 0)
            if self.annotation_model.data(index, AnnotationRoles.Type) \
                    == ShapeType.POLYGON.value:
                self.annotation_model.setData(
                    index, Qt.Checked if value else Qt.Unchecked,
                    Qt.CheckStateRole)

    def _video_project_target(self, source_path, project_path=None,
                              allow_dialog=False):
        """Resolve the default sidecar, falling back to read-only safely."""
        if is_video_project(source_path):
            return source_path, False
        if project_path:
            return os.path.abspath(ustr(project_path)), False
        default = default_project_path(source_path)
        if os.path.exists(default) or os.access(
                os.path.dirname(default) or '.', os.W_OK):
            return default, False
        if allow_dialog:
            chosen, _selected_filter = QFileDialog.getSaveFileName(
                self, '%s - Choose Video Project' % __appname__, default,
                'LabelImg++ video project (*.labelimgpp.sqlite)')
            if chosen:
                chosen = ustr(chosen)
                if not chosen.lower().endswith('.labelimgpp.sqlite'):
                    chosen += '.labelimgpp.sqlite'
                return os.path.abspath(chosen), False
        return None, True

    def request_open_video(self, path, project_path=None, skip_prompt=False,
                           source_override=None):
        """Queue a transactional video/project open on the decoder lane."""
        path = os.path.abspath(ustr(path))
        if not skip_prompt and self.dirty:
            if self.auto_saving.isChecked():
                self.request_save_file(on_success=lambda: self.request_open_video(
                    path, project_path=project_path, skip_prompt=True,
                    source_override=source_override))
                return None
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return None
            if answer == QMessageBox.Yes:
                self.request_save_file(on_success=lambda: self.request_open_video(
                    path, project_path=project_path, skip_prompt=True,
                    source_override=source_override))
                return None

        target, read_only = self._video_project_target(
            path, project_path=project_path, allow_dialog=True)
        self._dataset_generation = self.task_coordinator.next_generation()
        generation = self._dataset_generation
        self._video_open_request_id += 1
        request_id = self._video_open_request_id
        self._show_loading_veil('Opening video %s…' % os.path.basename(path))

        def prepare(handle):
            try:
                prepared = prepare_video_open(
                    path, project_path=target, read_only=read_only,
                    cancelled=handle.is_cancelled,
                    source_override=source_override)
            except VideoSourceMissing as exc:
                return VideoOpenProblem('missing', str(exc))
            except VideoSourceChanged as exc:
                return VideoOpenProblem('changed', str(exc))
            if handle.is_cancelled():
                prepared.decoder.close()
                return None
            return prepared

        handle = self.task_coordinator.submit(
            'video', prepare, priority=JobPriority.IMAGE_LOAD,
            key='video-open', latest=True, generation=generation)
        handle.result.connect(
            lambda prepared, rid=request_id, gen=generation,
            requested=path, project=target, override=source_override:
            self._on_video_open_result(
                prepared, rid, gen, requested, project, override))
        handle.error.connect(
            lambda message, rid=request_id, gen=generation:
            self._on_video_open_error(message, rid, gen))
        return handle

    def _on_video_open_error(self, message, request_id, generation):
        if (request_id != self._video_open_request_id
                or generation != self._dataset_generation):
            return
        self._hide_loading_veil()
        self.canvas.setEnabled(bool(self.file_path))
        self.status('Error opening video: ' + message, delay=10000)

    def _on_video_open_result(self, prepared, request_id, generation,
                              requested_path=None, project_path=None,
                              source_override=None):
        if prepared is None:
            return
        if (request_id != self._video_open_request_id
                or generation != self._dataset_generation):
            decoder = getattr(prepared, 'decoder', None)
            if decoder is not None:
                decoder.close()
            return
        if isinstance(prepared, VideoOpenProblem):
            self._hide_loading_veil()
            self._resolve_video_open_problem(
                prepared, requested_path, project_path, source_override)
            return
        self._commit_video_open(prepared)
        self._hide_loading_veil()

    def _locate_video_source(self, project_path):
        source, _selected = QFileDialog.getOpenFileName(
            self, 'Locate original video', os.path.dirname(project_path),
            'Video files (*.mp4 *.mov *.mkv *.avi);;All files (*)')
        return os.path.abspath(ustr(source)) if source else None

    def _video_source_changed_choice(self, message):
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle('Video source changed')
        dialog.setText(message)
        dialog.setInformativeText(
            'Annotations will not be applied to changed media.')
        locate = dialog.addButton('Locate Original', QMessageBox.AcceptRole)
        create = dialog.addButton(
            'Create New Project', QMessageBox.DestructiveRole)
        cancel = dialog.addButton(QMessageBox.Cancel)
        dialog.exec_()
        clicked = dialog.clickedButton()
        if clicked is locate:
            return 'locate'
        if clicked is create:
            return 'create'
        if clicked is cancel:
            return 'cancel'
        return 'cancel'

    def _new_video_project_path(self, source_path, old_project_path):
        suggested = default_project_path(source_path)
        if os.path.abspath(suggested) == os.path.abspath(old_project_path):
            suggested = source_path + '.new' + PROJECT_SUFFIX
        path, _selected = QFileDialog.getSaveFileName(
            self, 'Create new video project', suggested,
            'LabelImg++ video project (*.labelimgpp.sqlite)')
        return os.path.abspath(ustr(path)) if path else None

    def _resolve_video_open_problem(self, problem, requested_path,
                                    project_path, source_override):
        if problem.kind == 'missing':
            located = self._locate_video_source(project_path)
            if located:
                self.request_open_video(
                    project_path, skip_prompt=True,
                    source_override=located)
            else:
                self.status('Video project open cancelled')
            return
        choice = self._video_source_changed_choice(problem.message)
        if choice == 'locate':
            located = self._locate_video_source(project_path)
            if located:
                self.request_open_video(
                    project_path, skip_prompt=True,
                    source_override=located)
            return
        if choice == 'create':
            source_path = source_override
            if source_path is None and not is_video_project(requested_path):
                source_path = requested_path
            if source_path is None:
                source_path = self._locate_video_source(project_path)
            if source_path:
                new_project = self._new_video_project_path(
                    source_path, project_path)
                if new_project:
                    self.request_open_video(
                        source_path, project_path=new_project,
                        skip_prompt=True)
            return
        self.status('Video project open cancelled')

    def _commit_video_open(self, prepared):
        """Atomically publish worker data on QApplication.thread()."""
        assert QApplication.instance().thread() == self.thread()
        snapshot = prepared.snapshot
        first = snapshot.initial_frame
        self.reset_state()
        self._set_document_kind(DocumentKind.VIDEO)
        self.video_decoder = prepared.decoder
        self.video_snapshot = snapshot
        self.video_tracks = prepared.tracks
        self.video_observations = prepared.observations
        self.video_frame_states = prepared.frame_states
        self.video_classes = prepared.classes
        self.video_model = VideoProjectModel(
            snapshot.revision, tracks=prepared.tracks,
            observations=prepared.observations,
            frame_states=prepared.frame_states, classes=prepared.classes)
        self._document_revision = snapshot.revision
        self.m_img_list = []
        self._path_to_idx = {}
        self.img_count = 0
        self.cur_img_idx = 0
        self.file_list_widget.clear()
        self.file_path = snapshot.source_path
        self.image_data = None
        self.image = first.image
        self._image_scale_factor = (
            first.display_width / snapshot.width if snapshot.width else 1.0)
        self._original_image_size = QSize(snapshot.width, snapshot.height)
        verified_pts = {state.pts for state in prepared.frame_states
                        if state.verified}
        self.canvas.verified = first.frame_ref.pts in verified_pts
        self.canvas.locked = (
            snapshot.read_only
            or (self.canvas.verified
                and self.lock_on_verify_option.isChecked()))
        self.canvas.load_pixmap(QPixmap.fromImage(first.image))
        self.current_video_frame_ref = first.frame_ref
        self.frame_cache.put(first)
        self.video_timeline.set_session(snapshot)
        self._refresh_video_timeline_markers()
        self._materialize_video_frame(first.frame_ref.pts)
        self.set_clean()
        self.canvas.setEnabled(True)
        self.adjust_scale(initial=True)
        self.paint_canvas()
        self.toggle_actions(True)
        editable = not snapshot.read_only
        mutation_actions = (
            self.actions.create, self.actions.create_polygon,
            self.actions.createMode, self.actions.editMode,
            self.actions.verify, self.actions.delete, self.actions.copy,
            self.actions.edit, self.actions.pasteFromClipboard,
            self.actions.keypoint_mode, self.actions.sam_mode,
            self.actions.shapeLineColor, self.actions.shapeFillColor,
            self.actions.undo, self.actions.redo,
            self.actions.videoAddKeyframe, self.actions.videoEditSpan,
            self.actions.videoDeleteTrack,
            self.actions.videoTrackForward,
            self.actions.videoTrackBackward,
            self.actions.videoAcceptSuggestion,
            self.actions.videoRejectSuggestion,
            self.actions.videoAcceptVisible,
            self.actions.videoRejectVisible,
            self.actions.videoAcceptRun,
            self.actions.videoRejectRun,
        )
        if not editable:
            for action in mutation_actions:
                action.setEnabled(False)
        else:
            for action in (self.actions.create, self.actions.create_polygon,
                           self.actions.createMode, self.actions.editMode,
                           self.actions.verify):
                action.setEnabled(True)
        self.diffc_button.setEnabled(editable)
        self.actions.saveAs.setEnabled(bool(snapshot.project_path))
        self.add_recent_file(snapshot.project_path or snapshot.source_path)
        suffix = ' [read-only]' if snapshot.read_only else ''
        self.setWindowTitle(
            '%s %s%s' % (__appname__, snapshot.source_path, suffix))
        self.update_status_bar()
        self.canvas.setFocus(True)
        self.status('Opened video %s' % os.path.basename(snapshot.source_path))
        self._plugin_document_ready = True
        self._publish_plugin_document(new_generation=True, force=True)

    def open_video(self, path, project_path=None):
        """Synchronous compatibility API for extensions and tests."""
        if self.dirty and not self.may_continue():
            return False
        path = os.path.abspath(ustr(path))
        target, read_only = self._video_project_target(
            path, project_path=project_path, allow_dialog=False)
        try:
            prepared = prepare_video_open(
                path, project_path=target, read_only=read_only)
        except Exception as exc:
            self.status('Error opening video: %s' % exc, delay=10000)
            return False
        self._dataset_generation = self.task_coordinator.next_generation()
        self._commit_video_open(prepared)
        return True

    def request_save_video_project(self, _value=False, on_success=None):
        snapshot = self.video_snapshot
        if (self.document_kind != DocumentKind.VIDEO or snapshot is None
                or snapshot.read_only or not snapshot.project_path):
            return None
        if callable(on_success):
            self._video_save_callbacks.append(on_success)
        if self._video_save_active:
            self._video_save_queued = True
            return self._video_save_handle
        model = self.video_model
        if model is None or not model.dirty:
            try:
                checkpoint_project(snapshot.project_path)
            except Exception as exc:
                self.status(
                    'Error saving video project: %s' % exc, delay=10000)
                return None
            self.set_clean()
            callbacks, self._video_save_callbacks = \
                self._video_save_callbacks, []
            for callback in callbacks:
                callback()
            return None
        request = model.build_save_request(snapshot.project_path)
        generation = self._dataset_generation

        def save(handle):
            handle.check_cancelled()
            return save_project_delta(
                request, cancelled=handle.is_cancelled,
                begin_commit=handle.begin_non_cancellable)

        handle = self.task_coordinator.submit(
            'background', save, priority=JobPriority.IMAGE_LOAD,
            generation=generation)
        self._video_save_handle = handle
        self._video_save_active = True
        self._video_save_queued = False
        handle.result.connect(
            lambda revision, req=request, gen=generation:
            self._on_video_save_result(revision, req, gen))
        handle.error.connect(
            self._on_video_save_error)
        handle.finished.connect(self._on_video_save_finished)
        return handle

    def _on_video_save_result(self, revision, request, generation):
        if (revision is None or generation != self._dataset_generation
                or self.video_model is None
                or self.video_snapshot is None
                or request.project_path != self.video_snapshot.project_path):
            return
        self.video_model.mark_saved(revision)
        self.video_snapshot = replace(
            self.video_snapshot, revision=revision)
        if not self.video_model.dirty:
            self.set_clean()
        else:
            self._video_save_queued = True
        self.status('Saved video project to %s' % request.project_path)

    def _on_video_save_error(self, message):
        self._video_save_queued = False
        self._video_save_callbacks = []
        self._video_close_save_pending = False
        self.status('Error saving video project: ' + message, delay=10000)

    def _on_video_save_finished(self):
        self._video_save_active = False
        self._video_save_handle = None
        if (self.video_model is not None and self.video_model.dirty
                and self._video_save_queued):
            self.request_save_video_project()
            return
        if self.video_model is not None and not self.video_model.dirty:
            callbacks, self._video_save_callbacks = \
                self._video_save_callbacks, []
            for callback in callbacks:
                callback()

    def save_video_project(self):
        snapshot = self.video_snapshot
        if (self.document_kind != DocumentKind.VIDEO or snapshot is None
                or snapshot.read_only or not snapshot.project_path):
            return False
        try:
            if self.video_model is not None and self.video_model.dirty:
                request = self.video_model.build_save_request(
                    snapshot.project_path)
                revision = save_project_delta(request)
                self.video_model.mark_saved(revision)
                self.video_snapshot = replace(
                    self.video_snapshot, revision=revision)
            checkpoint_project(snapshot.project_path)
        except Exception as exc:
            self.status('Error saving video project: %s' % exc, delay=10000)
            return False
        self.set_clean()
        return True

    def _refresh_video_timeline_markers(self):
        if self.video_snapshot is None:
            return
        by_track = {}
        accepted = []
        pending = []
        for observation in self.video_observations:
            by_track.setdefault(observation.track_id, []).append(
                observation.pts)
            if (observation.source == 'manual'
                    and observation.review_state == 'accepted'
                    and observation.anchor):
                accepted.append(observation.pts)
            elif observation.review_state == 'pending':
                pending.append(observation.pts)
        spans = tuple(
            (min(values), max(values)) for values in by_track.values()
            if values)
        verified = tuple(
            state.pts for state in self.video_frame_states if state.verified)
        self.video_timeline.set_markers(
            spans=spans, accepted=accepted, pending=pending,
            verified=verified)

    def _sync_video_model_views(self):
        model = self.video_model
        if model is None:
            return
        self.video_tracks = tuple(model.tracks.values())
        self.video_observations = tuple(model.observations.values())
        self.video_frame_states = tuple(model.frame_states.values())
        self.video_classes = tuple(model.classes)

    def _on_video_model_mutation(self):
        if not self._ensure_video_editable():
            return
        if (self._active_tracking_request is not None
                and not self._applying_tracking_batch):
            self.cancel_video_tracking()
        self.pause_video()
        self._sync_video_model_views()
        self._document_revision = self.video_model.revision
        self.dirty = self.video_model.dirty
        self.actions.save.setEnabled(self.dirty)
        self.update_save_status(saved=not self.dirty)
        self._refresh_video_timeline_markers()
        self._refresh_video_track_list()
        self.update_box_count()
        self._publish_plugin_document()

    def _shape_geometry(self, shape):
        inverse = (1.0 / self._image_scale_factor
                   if self._image_scale_factor else 1.0)
        points = [(point.x() * inverse, point.y() * inverse)
                  for point in shape.points]
        if shape.shape_type == ShapeType.RECTANGLE:
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            geometry = [min(xs), min(ys), max(xs), max(ys)]
        else:
            geometry = [[point[0], point[1]] for point in points]
        keypoints = None
        if shape.keypoints is not None:
            keypoints = [
                ([item[0] * inverse, item[1] * inverse, item[2]]
                 if item is not None else None)
                for item in shape.keypoints]
        return geometry, keypoints

    def _store_video_shape_as_manual(self, shape):
        if not self._video_editable():
            raise RuntimeError('cannot mutate a read-only video project')
        track_id = getattr(shape, 'video_track_id', None)
        if track_id is None:
            track = self.video_model.create_track(
                shape.label, shape.shape_type.value,
                shape.line_color.getRgb(), difficult=shape.difficult)
            track_id = track.track_id
            shape.video_track_id = track_id
        geometry, keypoints = self._shape_geometry(shape)
        self.video_model.upsert_manual(
            track_id, self.current_video_frame_ref.pts,
            geometry, keypoints=keypoints)
        return track_id

    def _shape_for_materialized(self, materialized):
        track = materialized.track
        observation = materialized.observation
        shape_type = (ShapeType.POLYGON if track.shape_type == 'polygon'
                      else ShapeType.RECTANGLE)
        shape = Shape(
            label=track.label, line_color=QColor(*track.color),
            difficult=track.difficult, shape_type=shape_type)
        scale = self._image_scale_factor
        geometry = observation.geometry
        if shape_type == ShapeType.RECTANGLE:
            xmin, ymin, xmax, ymax = geometry
            points = ((xmin, ymin), (xmax, ymin),
                      (xmax, ymax), (xmin, ymax))
        else:
            points = geometry
        for x, y in points:
            shape.add_point(QPointF(x * scale, y * scale))
        shape.close()
        if observation.keypoints is not None:
            shape.keypoints = [
                ([item[0] * scale, item[1] * scale, item[2]]
                 if item is not None else None)
                for item in observation.keypoints]
        shape.video_track_id = track.track_id
        shape.video_render_state = materialized.render_state
        return shape

    def _materialize_video_frame(self, pts):
        model = self.video_model
        if model is None:
            return
        selected = self._selected_video_track_id
        shapes = [self._shape_for_materialized(item)
                  for item in model.materialize(int(pts))]
        self.canvas.load_shapes(shapes)
        self.annotation_model.set_video_context(model, pts)
        self.update_combo_box()
        if selected:
            match = next((shape for shape in shapes
                          if shape.video_track_id == selected), None)
            if match is not None:
                self.canvas.select_shape(match)
            self._select_annotation_identity(selected)
        for shape in shapes:
            identity = shape.video_track_id
            index = self.annotation_model.index_for_identity(identity)
            visible = self.annotation_model.data(
                index, AnnotationRoles.Visible)
            self.canvas.set_shape_visible(shape, visible)
        self.update_box_count()
        has_pending = any(
            item.pts == int(pts) and item.review_state == 'pending'
            for item in model.observations.values())
        editable = self._video_editable()
        self.actions.videoAcceptSuggestion.setEnabled(has_pending and editable)
        self.actions.videoRejectSuggestion.setEnabled(has_pending and editable)
        has_any_pending = any(
            item.review_state == 'pending'
            for item in model.observations.values())
        has_run_pending = any(
            key in self._tracking_run_keys
            and item.review_state == 'pending'
            for key, item in model.observations.items())
        self.actions.videoAcceptVisible.setEnabled(
            has_any_pending and editable)
        self.actions.videoRejectVisible.setEnabled(
            has_any_pending and editable)
        self.actions.videoAcceptRun.setEnabled(has_run_pending and editable)
        self.actions.videoRejectRun.setEnabled(has_run_pending and editable)

    def _refresh_video_track_list(self):
        model = self.video_model
        if model is None:
            return
        selected = self._selected_video_track_id
        pts = (None if self.current_video_frame_ref is None else
               self.current_video_frame_ref.pts)
        self.annotation_model.set_video_context(model, pts)
        if selected:
            self._select_annotation_identity(selected)

    def _video_track_selection_changed(self):
        self.label_selection_changed()

    def _sync_video_track_actions(self, track_id):
        editable = self._video_editable()
        track = (None if self.video_model is None else
                 self.video_model.tracks.get(track_id))
        has_track = track is not None
        self.actions.videoAddKeyframe.setEnabled(editable and has_track)
        self.actions.videoEditSpan.setEnabled(editable and has_track)
        self.actions.videoDeleteTrack.setEnabled(editable and has_track)
        self.actions.edit.setEnabled(editable and has_track)
        self.actions.shapeLineColor.setEnabled(editable and has_track)
        self.actions.shapeFillColor.setEnabled(editable and has_track)
        can_track = track is not None and track.shape_type == 'rectangle'
        self.actions.videoTrackForward.setEnabled(can_track and editable)
        self.actions.videoTrackBackward.setEnabled(can_track and editable)

    def _video_track_item_changed(self, item):
        """Legacy entry point retained for controller compatibility."""
        identity = self.current_annotation_identity()
        if identity is not None:
            self._annotation_visibility_changed(
                identity, item.checkState() == Qt.Checked)

    def add_track_keyframe(self):
        if not self._ensure_video_editable():
            return
        model = self.video_model
        track_id = self._selected_video_track_id
        if model is None or track_id is None \
                or self.current_video_frame_ref is None:
            return
        before = model.snapshot_state()
        observation = model.promote_to_manual(
            track_id, self.current_video_frame_ref.pts)
        if observation is None:
            self.status('Selected track is not present on this frame')
            return
        after = model.snapshot_state()
        self.undo_stack.push(VideoModelCommand(
            self, before, after, 'Add video track keyframe'))
        self._on_video_model_mutation()
        self._materialize_video_frame(self.current_video_frame_ref.pts)

    def edit_selected_track_span(self):
        """Trim the selected track to inclusive PTS bounds."""
        if not self._ensure_video_editable():
            return
        model = self.video_model
        track_id = self._selected_video_track_id
        if model is None or track_id not in model.tracks:
            return
        observations = sorted(
            (item for item in model.observations.values()
             if item.track_id == track_id), key=lambda item: item.pts)
        if not observations:
            self.status('The selected track has no editable span')
            return
        current = '%s,%s' % (observations[0].pts, observations[-1].pts)
        value, accepted = QInputDialog.getText(
            self, 'Set Track Span',
            'Inclusive PTS bounds (start,end):', text=current)
        if not accepted:
            return
        try:
            start_text, end_text = str(value).split(',', 1)
            start_pts, end_pts = int(start_text), int(end_text)
            if start_pts > end_pts:
                raise ValueError
        except (TypeError, ValueError):
            self.status('Track span must be two integers with start <= end')
            return
        retained = [item for item in observations
                    if start_pts <= item.pts <= end_pts]
        if not retained:
            self.status('Track span must retain at least one observation')
            return
        discarded = [item for item in observations if item not in retained]
        if not discarded:
            return
        before = model.snapshot_state()
        for observation in discarded:
            model.delete_occurrence(track_id, observation.pts)
        after = model.snapshot_state()
        self.undo_stack.push(VideoModelCommand(
            self, before, after, 'Trim video track span'))
        self._on_video_model_mutation()
        self._materialize_video_frame(self.current_video_frame_ref.pts)

    def delete_selected_track(self):
        if not self._ensure_video_editable():
            return
        model = self.video_model
        track_id = self._selected_video_track_id
        if model is None or track_id not in model.tracks:
            return
        track = model.tracks[track_id]
        answer = QMessageBox.question(
            self, 'Delete Track',
            'Delete track "%s" and all of its observations?' % track.label,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        before = model.snapshot_state()
        model.delete_track(track_id)
        after = model.snapshot_state()
        self._selected_video_track_id = None
        self.undo_stack.push(VideoModelCommand(
            self, before, after, 'Delete video track'))
        self._on_video_model_mutation()
        self._materialize_video_frame(self.current_video_frame_ref.pts)

    def track_selected_forward(self, choose_endpoint=False):
        return self._request_video_tracking(
            1, choose_endpoint=choose_endpoint)

    def track_selected_backward(self, choose_endpoint=False):
        return self._request_video_tracking(
            -1, choose_endpoint=choose_endpoint)

    def _tracking_endpoint(self, track_id, start_pts, direction):
        anchors = sorted(
            item.pts for item in self.video_model.observations.values()
            if item.track_id == track_id and item.source == 'manual'
            and item.review_state == 'accepted' and item.anchor
            and (item.pts - start_pts) * direction > 0)
        if anchors:
            return anchors[0] if direction > 0 else anchors[-1]
        snapshot = self.video_snapshot
        five_seconds = int(round(
            5 * snapshot.time_base_den / snapshot.time_base_num))
        endpoint = start_pts + direction * five_seconds
        lower = int(snapshot.start_pts or 0)
        upper = lower + int(snapshot.duration_pts or five_seconds)
        return max(lower, min(upper, endpoint))

    def _choose_tracking_endpoint(self, default_pts, direction):
        snapshot = self.video_snapshot
        start = int(snapshot.start_pts or 0)
        seconds = (default_pts - start) * snapshot.time_base_num / \
            snapshot.time_base_den
        value, accepted = QInputDialog.getText(
            self, 'Optical-flow endpoint',
            'Track %s until (HH:MM:SS.mmm):' % (
                'forward' if direction > 0 else 'backward'),
            text=format_timecode(seconds))
        if not accepted:
            return None
        try:
            endpoint = start + int(round(
                parse_timecode(value) * snapshot.time_base_den /
                snapshot.time_base_num))
        except ValueError as exc:
            self.status('Invalid tracking endpoint: %s' % exc)
            return None
        current = self.current_video_frame_ref.pts
        if (endpoint - current) * direction <= 0:
            self.status('Tracking endpoint must be in the selected direction')
            return None
        upper = start + int(snapshot.duration_pts or max(0, endpoint - start))
        return max(start, min(upper, endpoint))

    def _request_video_tracking(self, direction, choose_endpoint=False):
        if not self._ensure_video_editable():
            return None
        model = self.video_model
        frame_ref = self.current_video_frame_ref
        track_id = self._selected_video_track_id
        if model is None or frame_ref is None or track_id is None:
            self.status('Select a rectangle track before tracking')
            return None
        track = model.tracks.get(track_id)
        seed = model.observations.get((track_id, frame_ref.pts))
        if (track is None or track.shape_type != 'rectangle'
                or seed is None or not seed.present
                or seed.review_state != 'accepted'):
            self.status(
                'Tracking must start from an accepted exact rectangle')
            return None
        endpoint = self._tracking_endpoint(
            track_id, frame_ref.pts, direction)
        if choose_endpoint:
            endpoint = self._choose_tracking_endpoint(endpoint, direction)
            if endpoint is None:
                return None
        if endpoint == frame_ref.pts:
            self.status('No tracking range is available in that direction')
            return None
        self.cancel_video_tracking()
        self._tracking_request_id += 1
        request = TrackingRequest(
            request_id=self._tracking_request_id,
            generation=self._dataset_generation,
            source_path=self.video_snapshot.source_path,
            stream_index=self.video_snapshot.stream_index,
            start_ref=frame_ref, end_pts=endpoint, direction=direction,
            track=track, seed=seed,
            seed_track_revision=track.revision,
            document_revision=model.revision)
        self._active_tracking_request = request
        self._tracking_run_keys = set()

        def propagate(handle):
            return track_optical_flow(request, handle)

        handle = self.task_coordinator.submit(
            'background', propagate, priority=JobPriority.BULK,
            key='video-tracking', latest=True,
            generation=self._dataset_generation)
        self._tracking_handle = handle
        handle.progress.connect(self._on_tracking_batch)
        handle.result.connect(self._on_tracking_result)
        handle.error.connect(self._on_tracking_error)
        handle.finished.connect(self._on_tracking_finished)
        self.status('Tracking %s…' % (
            'forward' if direction > 0 else 'backward'))
        return handle

    def _tracking_batch_is_current(self, batch):
        request = self._active_tracking_request
        if (request is None or self.video_model is None
                or not self._video_editable()):
            return False
        track = self.video_model.tracks.get(batch.track_id)
        return (
            batch.request_id == request.request_id
            and batch.generation == self._dataset_generation
            and batch.track_id == request.track.track_id
            and batch.seed_track_revision == request.seed_track_revision
            and batch.document_revision == request.document_revision
            and track is not None
            and track.revision == request.seed_track_revision
        )

    def _on_tracking_batch(self, batch):
        if not self._tracking_batch_is_current(batch):
            return
        changed = False
        self._applying_tracking_batch = True
        try:
            for observation in batch.observations:
                value = self.video_model.upsert_tracker(observation)
                if value.review_state == 'pending':
                    self._tracking_run_keys.add(
                        (value.track_id, value.pts))
                changed = changed or value is not observation \
                    or value.revision != observation.revision
            if batch.observations:
                self._on_video_model_mutation()
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
        finally:
            self._applying_tracking_batch = False
        if batch.observations:
            self.status('Tracking: %s to %s PTS' % (
                batch.start_pts, batch.end_pts))
        return changed

    def _on_tracking_result(self, batch):
        if not self._tracking_batch_is_current(batch):
            return
        self._on_tracking_batch(batch)
        self.status('Tracking stopped: %s' % (
            batch.stop_reason or 'range complete'))

    def _on_tracking_error(self, message):
        self.status('Video tracking failed: ' + message, delay=10000)

    def _on_tracking_finished(self):
        self._tracking_handle = None
        self._active_tracking_request = None

    def cancel_video_tracking(self):
        handle = getattr(self, '_tracking_handle', None)
        if handle is not None:
            handle.cancel()
        self._tracking_handle = None
        self._active_tracking_request = None

    def _current_pending_keys(self):
        if self.video_model is None or self.current_video_frame_ref is None:
            return ()
        pts = self.current_video_frame_ref.pts
        values = [
            key for key, item in self.video_model.observations.items()
            if item.pts == pts and item.review_state == 'pending']
        if self._selected_video_track_id is not None:
            preferred = (self._selected_video_track_id, pts)
            if preferred in values:
                return (preferred,)
        return tuple(values[:1])

    def _review_video_keys(self, keys, review_state, description):
        if not self._ensure_video_editable():
            return False
        keys = tuple(
            key for key in keys
            if key in self.video_model.observations
            and self.video_model.observations[key].review_state == 'pending')
        if not keys:
            return False
        self.cancel_video_tracking()
        before = self.video_model.snapshot_state()
        for track_id, pts in keys:
            self.video_model.review(track_id, pts, review_state)
        after = self.video_model.snapshot_state()
        self.undo_stack.push(VideoModelCommand(
            self, before, after, description))
        self._on_video_model_mutation()
        self._materialize_video_frame(self.current_video_frame_ref.pts)
        return True

    def accept_current_suggestion(self):
        return self._review_video_keys(
            self._current_pending_keys(), 'accepted',
            'Accept tracker suggestion')

    def reject_current_suggestion(self):
        return self._review_video_keys(
            self._current_pending_keys(), 'rejected',
            'Reject tracker suggestion')

    def review_visible_suggestions(self, review_state, start_pts=None,
                                   end_pts=None):
        if self.video_model is None:
            return False
        if start_pts is None or end_pts is None:
            center = self.current_video_frame_ref.pts
            radius = int(round(
                2.5 * self.video_snapshot.time_base_den /
                self.video_snapshot.time_base_num))
            start_pts, end_pts = center - radius, center + radius
        keys = tuple(
            key for key, item in self.video_model.observations.items()
            if start_pts <= item.pts <= end_pts
            and item.review_state == 'pending')
        return self._review_video_keys(
            keys, review_state,
            '%s visible tracker suggestions' % review_state.title())

    def review_full_propagation(self, review_state):
        return self._review_video_keys(
            tuple(self._tracking_run_keys), review_state,
            '%s full tracker propagation' % review_state.title())

    def _video_export_range_bounds(self, values):
        snapshot = self.video_snapshot
        start_seconds = parse_timecode(values['start_time'])
        end_seconds = parse_timecode(values['end_time'])
        if end_seconds < start_seconds:
            raise ValueError('export range end precedes its start')
        start_pts = int(snapshot.start_pts or 0) + int(round(
            start_seconds * snapshot.time_base_den /
            snapshot.time_base_num))
        end_pts = int(snapshot.start_pts or 0) + int(round(
            end_seconds * snapshot.time_base_den /
            snapshot.time_base_num))
        media_end = int(snapshot.start_pts or 0) + int(
            snapshot.duration_pts or max(0, end_pts - start_pts))
        start_pts = max(int(snapshot.start_pts or 0), start_pts)
        end_pts = min(media_end, end_pts)
        return start_pts, end_pts

    def _video_export_frame_refs(self, values):
        snapshot = self.video_snapshot
        selection = values['selection']
        if selection == 'current':
            pts_values = [self.current_video_frame_ref.pts]
        elif selection == 'annotated':
            pts_values = sorted({
                item.pts for item in self.video_model.observations.values()
                if item.present and item.review_state == 'accepted'})
        elif selection == 'verified':
            pts_values = sorted({
                item.pts for item in self.video_model.frame_states.values()
                if item.verified})
        else:
            start_pts, end_pts = self._video_export_range_bounds(values)
            if values['sample_unit'] == 'seconds':
                step = max(1, int(round(
                    values['sample_seconds'] * snapshot.time_base_den /
                    snapshot.time_base_num)))
                pts_values = list(range(start_pts, end_pts + 1, step))
            else:
                # Actual every-N-frame selection is resolved by the bulk
                # decoder. A fixed PTS grid cannot represent VFR frame cadence.
                pts_values = [start_pts]
                if end_pts != start_pts:
                    pts_values.append(end_pts)
        return tuple(VideoFrameRef(
            snapshot.fingerprint, snapshot.stream_index, int(pts),
            snapshot.time_base_num, snapshot.time_base_den)
            for pts in pts_values)

    def open_video_export_dialog(self):
        if self.document_kind != DocumentKind.VIDEO:
            return None
        dialog = VideoExportDialog(self.label_file_format, self)
        stem = os.path.splitext(
            os.path.basename(self.video_snapshot.source_path))[0]
        dialog.destination.setText(os.path.join(
            os.path.dirname(self.video_snapshot.source_path),
            stem + '-export'))
        if dialog.exec_() != QDialog.Accepted:
            return None
        values = dialog.values()
        if not values['destination']:
            self.status('Choose an export destination')
            return None
        try:
            frame_refs = self._video_export_frame_refs(values)
            range_start_pts = None
            range_end_pts = None
            sample_every_frames = None
            if (values['selection'] == 'range'
                    and values['sample_unit'] == 'frames'):
                range_start_pts, range_end_pts = \
                    self._video_export_range_bounds(values)
                sample_every_frames = max(1, int(values['sample_frames']))
        except ValueError as exc:
            self.status('Invalid video export selection: %s' % exc)
            return None
        if not frame_refs:
            self.status('The selected video export contains no frames')
            return None
        state = self.video_model.snapshot_state()
        request = VideoExportRequest(
            source_path=self.video_snapshot.source_path,
            project_path=self.video_snapshot.project_path,
            destination=os.path.abspath(values['destination']),
            stream_index=self.video_snapshot.stream_index,
            frame_refs=frame_refs, observations=state.observations,
            tracks=state.tracks, frame_states=state.frame_states,
            annotation_format=values['annotation_format'],
            image_format=values['image_format'],
            jpeg_quality=values['jpeg_quality'],
            class_order=state.classes,
            range_start_pts=range_start_pts,
            range_end_pts=range_end_pts,
            sample_every_frames=sample_every_frames)
        return self.request_export_video(request)

    def request_export_video(self, export_request):
        """Run one cancellable atomic export on an independent decoder."""
        if not isinstance(export_request, VideoExportRequest):
            raise TypeError('export_request must be a VideoExportRequest')
        self.cancel_video_export()
        generation = self._dataset_generation

        def export(handle):
            return export_video_frames(export_request, handle)

        handle = self.task_coordinator.submit(
            'background', export, priority=JobPriority.BULK,
            key='video-export', latest=True, generation=generation)
        self._video_export_handle = handle
        handle.progress.connect(
            lambda value, gen=generation:
            self.status('Exporting video frame %s / %s: %s' % value)
            if gen == self._dataset_generation else None)
        handle.result.connect(
            lambda destination, gen=generation:
            self.status('Exported video frames to %s' % destination)
            if gen == self._dataset_generation else None)
        handle.error.connect(
            lambda message, gen=generation:
            self.status('Video export failed: ' + message, delay=10000)
            if gen == self._dataset_generation else None)
        handle.finished.connect(
            lambda current=handle: self._clear_video_export_handle(current))
        return handle

    def _clear_video_export_handle(self, handle):
        if self._video_export_handle is handle:
            self._video_export_handle = None

    def cancel_video_export(self):
        handle = getattr(self, '_video_export_handle', None)
        if handle is not None:
            handle.cancel()
        self._video_export_handle = None

    def _video_step_pts(self):
        snapshot = self.video_snapshot
        if snapshot is None:
            return 1
        if snapshot.average_rate_num and snapshot.average_rate_den:
            seconds = (snapshot.average_rate_den /
                       snapshot.average_rate_num)
        else:
            seconds = 1.0 / 30.0
        return max(1, int(round(
            seconds * snapshot.time_base_den / snapshot.time_base_num)))

    def request_video_frame(self, frame_ref, playback=False):
        """Seek by immutable PTS reference with latest-request-wins semantics."""
        snapshot = self.video_snapshot
        if (self.document_kind != DocumentKind.VIDEO or snapshot is None
                or not isinstance(frame_ref, VideoFrameRef)
                or frame_ref.fingerprint != snapshot.fingerprint
                or frame_ref.stream_index != snapshot.stream_index):
            return None
        if playback and self._video_decode_in_flight:
            return None
        if not playback:
            self.pause_video()
        cached = self.frame_cache.get(frame_ref)
        if cached is not None:
            self._commit_video_frame(cached, playback=playback)
            return None
        mode = 'at_or_after' if playback else 'nearest'
        return self._submit_video_decode(
            lambda decoder, handle: decoder.seek_pts(
                frame_ref.pts, mode=mode, cancelled=handle.is_cancelled),
            playback=playback)

    def _submit_video_decode(self, operation, playback=False):
        if self.video_decoder is None:
            return None
        decoder = self.video_decoder
        self._video_frame_request_id += 1
        request_id = self._video_frame_request_id
        generation = self._dataset_generation
        if playback:
            self._video_decode_in_flight = True

        def decode(handle):
            handle.check_cancelled()
            return operation(decoder, handle)

        handle = self.task_coordinator.submit(
            'video', decode, priority=JobPriority.IMAGE_LOAD,
            key='video-frame', latest=True, generation=generation)
        handle.result.connect(
            lambda result, rid=request_id, gen=generation, playing=playback:
            self._on_video_frame_result(result, rid, gen, playing))
        handle.error.connect(
            lambda message, rid=request_id:
            self._on_video_frame_error(message, rid))
        handle.finished.connect(
            lambda rid=request_id:
            self._on_video_decode_finished(rid))
        return handle

    def _on_video_frame_result(self, result, request_id, generation,
                               playback=False):
        snapshot = self.video_snapshot
        if (request_id != self._video_frame_request_id
                or generation != self._dataset_generation
                or snapshot is None):
            return
        if result is None:
            self.pause_video()
            return
        if result.frame_ref.fingerprint != snapshot.fingerprint:
            return
        self.frame_cache.put(result)
        self._commit_video_frame(result, playback=playback)

    def _on_video_frame_error(self, message, request_id):
        if request_id != self._video_frame_request_id:
            return
        self.pause_video()
        self.status('Error decoding video frame: ' + message, delay=10000)

    def _on_video_decode_finished(self, request_id):
        if request_id == self._video_frame_request_id:
            self._video_decode_in_flight = False

    def _commit_video_frame(self, result, playback=False):
        assert QApplication.instance().thread() == self.thread()
        self.image = result.image
        self._image_scale_factor = (
            result.display_width / self.video_snapshot.width
            if self.video_snapshot.width else 1.0)
        self._original_image_size = QSize(
            self.video_snapshot.width, self.video_snapshot.height)
        self.canvas.load_pixmap(QPixmap.fromImage(result.image))
        self.current_video_frame_ref = result.frame_ref
        verified = any(
            state.pts == result.frame_ref.pts and state.verified
            for state in self.video_frame_states)
        self.canvas.verified = verified
        self.canvas.locked = (
            not self._video_editable()
            or (verified and self.lock_on_verify_option.isChecked()))
        # Track materialization is installed by the next delivery slice. Until
        # then a seek must never leak ordinary image shapes across frames.
        materialize = getattr(self, '_materialize_video_frame', None)
        if materialize is not None:
            materialize(result.frame_ref.pts)
        else:
            self.annotation_model.set_video_context(
                self.video_model, result.frame_ref.pts)
            self.canvas.load_shapes([])
        self.undo_stack.clear()
        self.video_timeline.set_current_frame(result.frame_ref)
        self.paint_canvas()
        self.update_status_bar()
        if not playback:
            self._schedule_video_prefetch(result.frame_ref)

    def request_next_video_frame(self):
        if self.current_video_frame_ref is None:
            return None
        self.pause_video()
        self._navigation_direction = 1
        cached = self.frame_cache.video_neighbor(
            self.current_video_frame_ref, 1)
        if cached is not None:
            self._commit_video_frame(cached)
            return None
        return self._submit_video_decode(
            lambda decoder, handle: decoder.next_frame(
                cancelled=handle.is_cancelled))

    def request_previous_video_frame(self):
        if self.current_video_frame_ref is None:
            return None
        self.pause_video()
        self._navigation_direction = -1
        cached = self.frame_cache.video_neighbor(
            self.current_video_frame_ref, -1)
        if cached is not None:
            self._commit_video_frame(cached)
            return None
        current = self.current_video_frame_ref
        return self._submit_video_decode(
            lambda decoder, handle: decoder.previous_frame(
                current, cancelled=handle.is_cancelled))

    def _schedule_video_prefetch(self, frame_ref):
        snapshot = self.video_snapshot
        if snapshot is None:
            return
        step = self._video_step_pts()
        offsets = ((-1, -2, 1) if self._navigation_direction < 0
                   else (1, 2, -1))
        targets = tuple(VideoFrameRef(
            snapshot.fingerprint, snapshot.stream_index,
            frame_ref.pts + offset * step,
            snapshot.time_base_num, snapshot.time_base_den)
            for offset in offsets
            if frame_ref.pts + offset * step >= int(snapshot.start_pts or 0))
        source_path = snapshot.source_path
        stream_index = snapshot.stream_index
        generation = self._dataset_generation

        def prefetch(handle):
            decoder = VideoDecoderSession(
                source_path, stream_index=stream_index,
                cancelled=handle.is_cancelled)
            results = []
            try:
                for target in targets:
                    handle.check_cancelled()
                    result = decoder.seek_pts(
                        target.pts, cancelled=handle.is_cancelled)
                    if result is not None:
                        results.append(result)
                return tuple(results)
            finally:
                decoder.close()

        handle = self.task_coordinator.submit(
            'background', prefetch, priority=JobPriority.BULK,
            key='video-prefetch', latest=True, generation=generation)
        self._video_prefetch_handle = handle
        handle.result.connect(
            lambda results, gen=generation:
            self._on_video_prefetch_results(results, gen))

    def _on_video_prefetch_results(self, results, generation):
        snapshot = self.video_snapshot
        if generation != self._dataset_generation or snapshot is None:
            return
        for result in results:
            if result.frame_ref.fingerprint == snapshot.fingerprint:
                self.frame_cache.put(result)

    def play_pause_video(self, _value=False):
        if self.document_kind != DocumentKind.VIDEO:
            return
        if self._video_playback_timer.isActive():
            self.pause_video()
            return
        if self.current_video_frame_ref is None:
            return
        self._video_play_started_wall = time.monotonic()
        self._video_play_started_seconds = \
            self.current_video_frame_ref.seconds
        self.video_timeline.set_playing(True)
        self._video_playback_timer.start()

    def pause_video(self):
        active = (getattr(self, '_video_decode_in_flight', False)
                  or (hasattr(self, '_video_playback_timer')
                      and self._video_playback_timer.isActive()))
        if hasattr(self, '_video_playback_timer'):
            self._video_playback_timer.stop()
        if hasattr(self, 'video_timeline'):
            self.video_timeline.set_playing(False)
        self._video_decode_in_flight = False
        if active and hasattr(self, 'task_coordinator'):
            self.task_coordinator.cancel_key('video-frame')
            self._video_frame_request_id += 1

    def _set_video_playback_speed(self, speed):
        self._video_playback_speed = float(speed)
        if (hasattr(self, '_video_playback_timer')
                and self._video_playback_timer.isActive()
                and self.current_video_frame_ref is not None):
            self._video_play_started_wall = time.monotonic()
            self._video_play_started_seconds = \
                self.current_video_frame_ref.seconds

    def _video_playback_tick(self):
        snapshot = self.video_snapshot
        if (snapshot is None or self.current_video_frame_ref is None
                or self._video_decode_in_flight):
            return
        elapsed = time.monotonic() - self._video_play_started_wall
        target_seconds = (self._video_play_started_seconds
                          + elapsed * self._video_playback_speed)
        end_pts = (int(snapshot.start_pts or 0)
                   + int(snapshot.duration_pts or 0))
        target_pts = int(round(
            target_seconds * snapshot.time_base_den /
            snapshot.time_base_num))
        if snapshot.duration_pts is not None and target_pts >= end_pts:
            self.pause_video()
            return
        self.request_video_frame(VideoFrameRef(
            snapshot.fingerprint, snapshot.stream_index, target_pts,
            snapshot.time_base_num, snapshot.time_base_den), playback=True)

    def request_open_file(self, file_path, skip_prompt=False):
        """Load a standalone file transactionally if it is outside the dataset."""
        file_path = os.path.abspath(ustr(file_path))
        if (is_video_project(file_path)
                or file_path.lower().endswith(VIDEO_EXTENSIONS)):
            return self.request_open_video(
                file_path, skip_prompt=skip_prompt)
        if file_path in self._path_to_idx:
            return self.request_load_file(
                file_path, skip_prompt=skip_prompt)
        if not skip_prompt and self.dirty:
            if self.auto_saving.isChecked() and self.default_save_dir:
                self.request_save_file(
                    on_success=lambda: self.request_open_file(
                        file_path, skip_prompt=True))
                return None
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return None
            if answer == QMessageBox.Yes:
                self.request_save_file(
                    on_success=lambda: self.request_open_file(
                        file_path, skip_prompt=True))
                return None
        previous_snapshot = self.dataset_snapshot
        self._dataset_generation = self.task_coordinator.next_generation()
        generation = self._dataset_generation
        save_dir = self.default_save_dir or os.path.dirname(file_path)
        replacement = DatasetSnapshot.from_images(
            (file_path,), root_dir=os.path.dirname(file_path),
            save_dir=save_dir, generation=generation)
        return self.request_load_file(
            file_path, skip_prompt=skip_prompt,
            replacement_snapshot=replacement,
            previous_snapshot=previous_snapshot)

    def request_load_file(self, file_path=None, skip_prompt=False,
                          replacement_snapshot=None,
                          previous_snapshot=None):
        """Queue a latest-wins image load while keeping the current image live."""
        if file_path is None:
            file_path = self.settings.get(SETTING_FILENAME)
        file_path = os.path.abspath(ustr(file_path))
        if LabelFile.is_label_file(file_path):
            self.error_message(
                u'Cannot open annotation file',
                u'<p>Open the image it describes instead.</p>')
            return None
        if not skip_prompt and self.dirty:
            if self.auto_saving.isChecked() and self.default_save_dir:
                self.request_save_file(
                    on_success=lambda: self.request_load_file(
                        file_path, skip_prompt=True,
                        replacement_snapshot=replacement_snapshot,
                        previous_snapshot=previous_snapshot))
                return None
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return None
            if answer == QMessageBox.Yes:
                self.request_save_file(
                    on_success=lambda: self.request_load_file(
                        file_path, skip_prompt=True,
                        replacement_snapshot=replacement_snapshot,
                        previous_snapshot=previous_snapshot))
                return None

        self._load_request_id += 1
        request_id = self._load_request_id
        generation = self._dataset_generation
        cached = (None if replacement_snapshot is not None
                  else self.frame_cache.get(file_path))
        self.canvas.setEnabled(False)
        self._show_loading_veil('Loading %s…' % os.path.basename(file_path))
        if cached is not None:
            QTimer.singleShot(
                0, lambda: self._on_image_result(
                    cached, request_id, generation,
                    replacement_snapshot))
            return None

        resolver = (replacement_snapshot.resolver
                    if replacement_snapshot is not None
                    else self._active_annotation_resolver(file_path))
        image_list = (replacement_snapshot.image_paths
                      if replacement_snapshot is not None
                      else tuple(self.m_img_list))
        save_dir = (replacement_snapshot.save_dir
                    if replacement_snapshot is not None
                    else self.default_save_dir)
        label_file_format = self.label_file_format

        def load(handle):
            with trace_span('image.load', args={'path': hash_path(file_path)}):
                return load_image_result(
                    file_path, resolver=resolver, image_list=image_list,
                    save_dir=save_dir, label_file_format=label_file_format,
                    cancelled=handle.is_cancelled)

        handle = self.task_coordinator.submit(
            'interactive', load, priority=JobPriority.IMAGE_LOAD,
            key='image-load', latest=True, generation=generation)
        handle.result.connect(
            lambda result, rid=request_id, gen=generation:
            self._on_image_result(
                result, rid, gen, replacement_snapshot))
        handle.error.connect(
            lambda message, rid=request_id, gen=generation:
            self._on_image_load_error(
                message, rid, gen, previous_snapshot))
        return handle

    def _on_image_load_error(self, message, request_id, generation,
                             previous_snapshot=None):
        if (request_id != self._load_request_id
                or generation != self._dataset_generation):
            return
        self._pending_navigation_index = None
        self.canvas.setEnabled(bool(self.file_path))
        self._hide_loading_veil()
        if previous_snapshot is not None:
            self.dataset_snapshot = previous_snapshot.with_generation(
                generation)
            if self.dataset_snapshot.image_paths:
                self.annotation_catalog.start(self.dataset_snapshot)
        self.status('Error reading image: ' + message)

    def _on_image_result(self, result, request_id, generation,
                         replacement_snapshot=None):
        if (result is None or request_id != self._load_request_id
                or generation != self._dataset_generation):
            return
        if replacement_snapshot is not None:
            self._commit_dataset_snapshot(replacement_snapshot)
        self._commit_image_result(result)
        self.frame_cache.put(result)
        self._pending_navigation_index = None
        self._hide_loading_veil()
        self._schedule_prefetch(result.path)

    def _commit_image_result(self, result):
        """Apply worker data; this method is the GUI-thread mutation boundary."""
        trace_started = None
        if trace_recorder is not None:
            import time
            trace_started = time.perf_counter_ns()
        assert QApplication.instance().thread() == self.thread()
        self.reset_state()
        self._set_document_kind(DocumentKind.IMAGE)
        self._image_scale_factor = result.scale_factor
        self._original_image_size = QSize(
            result.original_width, result.original_height)
        self.image_data = None
        self.image = result.image
        self.file_path = result.path
        self.cur_img_idx = self._path_to_idx.get(
            result.path, self.cur_img_idx)
        self.canvas.verified = result.verified
        self.canvas.load_pixmap(QPixmap.fromImage(result.image))
        if result.annotation_format is not None:
            format_names = {
                LabelFileFormat.PASCAL_VOC: FORMAT_PASCALVOC,
                LabelFileFormat.YOLO: FORMAT_YOLO,
                LabelFileFormat.CREATE_ML: FORMAT_CREATEML,
                LabelFileFormat.COCO: FORMAT_COCO,
                LabelFileFormat.YOLO_SEG: FORMAT_YOLO_SEG,
            }
            self.set_format(format_names[result.annotation_format])
            self.load_labels(result.shapes)
            self.label_file = LabelFile()
            self.label_file.verified = result.verified
        if self.lock_on_verify_option.isChecked():
            self.canvas.locked = self.canvas.verified
        else:
            self.canvas.locked = False
        if hasattr(self, 'sam_controller'):
            self.sam_controller.on_image_changed()
        if hasattr(self, 'show_grid_option'):
            self.canvas._grid_enabled = self.show_grid_option.isChecked()
            checked_action = self.grid_size_group.checkedAction()
            self.canvas._grid_size = (
                checked_action.data() if checked_action else 32)
            self.canvas._edge_alignment = \
                self.edge_alignment_option.isChecked()
        self.set_clean()
        self.canvas.setEnabled(True)
        self.adjust_scale(initial=True)
        self.paint_canvas()
        self.add_recent_file(result.path)
        self.toggle_actions(True)
        if result.path in self._path_to_idx:
            item = self.file_list_widget.item(self._path_to_idx[result.path])
            self.file_list_widget.setCurrentItem(item)
            self.gallery_widget.select_image(result.path)
        self.setWindowTitle(
            __appname__ + ' ' + result.path + ' ' + self.counter_str())
        self.update_status_bar()
        self.canvas.setFocus(True)
        self._update_current_image_stats()
        if result.annotation_error:
            self.status('Annotation error: ' + result.annotation_error)
        if trace_recorder is not None:
            trace_recorder.complete(
                'image.ui-apply', trace_started,
                args={'path': hash_path(result.path),
                      'shapes': len(result.shapes)})
        self._plugin_document_ready = True
        self._publish_plugin_document(new_generation=True, force=True)

    def request_next_image(self, _value=False):
        if self.document_kind == DocumentKind.VIDEO:
            return self.request_next_video_frame()
        return self._request_relative_image(1)

    def request_previous_image(self, _value=False):
        if self.document_kind == DocumentKind.VIDEO:
            return self.request_previous_video_frame()
        return self._request_relative_image(-1)

    def _request_relative_image(self, direction):
        if not self.m_img_list:
            return None
        if self._pending_navigation_index is not None:
            base = self._pending_navigation_index
        elif self.file_path is None:
            base = -1 if direction > 0 else 0
        else:
            base = self._path_to_idx.get(self.file_path, self.cur_img_idx)
        target = base + direction
        if target < 0 or target >= len(self.m_img_list):
            return None
        self._pending_navigation_index = target
        if direction == self._navigation_direction:
            self._navigation_streak += 1
        else:
            self._navigation_direction = direction
            self._navigation_streak = 1
        return self.request_load_file(self.m_img_list[target])

    def _schedule_prefetch(self, current_path):
        if current_path not in self._path_to_idx:
            return
        index = self._path_to_idx[current_path]
        offsets = [-1, 1]
        if self._navigation_streak >= 2:
            offsets = ([1, 2] if self._navigation_direction > 0
                       else [-1, -2])
        desired = {
            self.m_img_list[index + offset]
            for offset in offsets
            if 0 <= index + offset < len(self.m_img_list)
        }
        for path, handle in list(self._prefetch_handles.items()):
            if path not in desired:
                handle.cancel()
                self._prefetch_handles.pop(path, None)
        for path in desired:
            if path in self._prefetch_handles or self.frame_cache.get(path):
                continue
            resolver = self._active_annotation_resolver(path)
            image_list = tuple(self.m_img_list)
            save_dir = self.default_save_dir
            label_file_format = self.label_file_format
            handle = self.task_coordinator.submit(
                'interactive',
                lambda job, target=path: load_image_result(
                    target, resolver=resolver, image_list=image_list,
                    save_dir=save_dir,
                    label_file_format=label_file_format,
                    cancelled=job.is_cancelled),
                priority=JobPriority.VISIBLE_THUMBNAIL,
                key='prefetch:' + path, latest=True,
                generation=self._dataset_generation)
            self._prefetch_handles[path] = handle
            handle.result.connect(
                lambda value, target=path: self._on_prefetch_result(
                    target, value))
            handle.finished.connect(
                lambda target=path: self._prefetch_handles.pop(
                    target, None))

    def _on_prefetch_result(self, path, result):
        if result is not None and result.path == path:
            self.frame_cache.put(result)

    def load_file(self, file_path=None):
        """Load the specified file, or the last opened file if None."""
        requested = (file_path if file_path is not None
                     else self.settings.get(SETTING_FILENAME))
        if requested:
            requested = os.path.abspath(ustr(requested))
            if (is_video_project(requested)
                    or requested.lower().endswith(VIDEO_EXTENSIONS)):
                return self.open_video(requested)
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
            self._set_document_kind(DocumentKind.IMAGE)
            if hasattr(self, 'sam_controller'):
                self.sam_controller.on_image_changed()
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

            # Default: select the last canonical shape in the unified view.
            if self.canvas.shapes:
                self._select_annotation_identity(
                    self.annotation_model.identity_for_shape(
                        self.canvas.shapes[-1]))

            self.canvas.setFocus(True)
            self._update_current_image_stats()
            self._plugin_document_ready = True
            self._publish_plugin_document(new_generation=True, force=True)
            return True
        return False

    def counter_str(self):
        """
        Converts image counter to string representation.
        """
        return '[{} / {}]'.format(self.cur_img_idx + 1, self.img_count)

    def show_bounding_box_from_annotation_file(self, file_path):
        if not file_path:
            return

        if self.label_file_format == LabelFileFormat.COCO:
            extensions = (JSON_EXT, XML_EXT, TXT_EXT)
        elif self.label_file_format == LabelFileFormat.YOLO_SEG:
            extensions = (TXT_EXT, XML_EXT, JSON_EXT)
        else:
            extensions = (XML_EXT, TXT_EXT, JSON_EXT)

        resolver = self._active_annotation_resolver(file_path)
        annotation_path = find_existing_annotation(
            file_path,
            save_dir=self.default_save_dir,
            image_list=self.m_img_list,
            extensions=extensions,
            resolver=resolver,
        )
        if (not annotation_path
                and self.label_file_format in (
                    LabelFileFormat.CREATE_ML, LabelFileFormat.COCO)):
            annotation_path = self._shared_annotation_path(
                file_path, resolver)
        if not annotation_path:
            return

        extension = os.path.splitext(annotation_path)[1].lower()
        if extension == XML_EXT:
            self.load_pascal_xml_by_filename(annotation_path)
        elif extension == TXT_EXT:
            if self.label_file_format == LabelFileFormat.YOLO_SEG:
                self.load_yolo_seg_by_filename(annotation_path)
            else:
                self.load_yolo_txt_by_filename(annotation_path)
        elif extension == JSON_EXT:
            if self.label_file_format == LabelFileFormat.COCO:
                self.load_coco_json_by_filename(annotation_path, file_path)
            else:
                self.load_create_ml_json_by_filename(
                    annotation_path, file_path)

    def resizeEvent(self, event):
        if self.canvas and not self.image.isNull()\
           and self.zoom_mode != self.MANUAL_ZOOM:
            self.adjust_scale()
        super(MainWindow, self).resizeEvent(event)
        if self._loading_veil is not None and self._loading_veil.isVisible():
            self._loading_veil.setGeometry(self.centralWidget().rect())

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
        if self._reset_all_in_progress:
            self._shutdown_workers()
            event.accept()
            return

        if self._video_close_save_pending:
            event.ignore()
            return

        if self.document_kind == DocumentKind.VIDEO and self.dirty:
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Yes:
                self._video_close_save_pending = True
                handle = self.request_save_video_project(
                    on_success=self._finish_video_close_after_save)
                if handle is None and self.dirty:
                    self._video_close_save_pending = False
                    self._video_save_callbacks = []
                    self.status(
                        'Could not save the video project; close cancelled',
                        delay=10000)
                event.ignore()
                return
        elif not self.may_continue():
            event.ignore()
            return

        settings = self.settings
        # If it loads images from dir, don't load it at the beginning
        if self.dir_name is None:
            settings[SETTING_FILENAME] = self.file_path if self.file_path else ''
        else:
            settings[SETTING_FILENAME] = ''

        settings[SETTING_WIN_SIZE] = self.size()
        settings[SETTING_WIN_POSE] = self.pos()
        # Preserve obsolete window/state bytes verbatim for downgrade use.
        settings[SETTING_LINE_COLOR] = self.line_color
        settings[SETTING_FILL_COLOR] = self.fill_color
        settings[SETTING_RECENT_FILES] = self.recent_files
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
        # Preserve obsolete toolbarExpanded verbatim for downgrade round trips.
        settings[SETTING_DARK_MODE] = self.dark_mode_action.isChecked()
        settings[SETTING_GRID_ENABLED] = self.show_grid_option.isChecked()
        settings[SETTING_GRID_SIZE] = self.canvas._grid_size if self.canvas else 32
        settings[SETTING_EDGE_ALIGNMENT] = self.edge_alignment_option.isChecked()
        settings[SETTING_SHORTCUTS] = self.shortcut_config.to_dict()
        settings[SETTING_SAM_OUTPUT_MODE] = self.sam_output_mode
        settings.save()
        self._shutdown_workers()

    def _finish_video_close_after_save(self):
        if not self._video_close_save_pending:
            return
        self._video_close_save_pending = False
        QTimer.singleShot(0, self.close)

    def _shutdown_workers(self):
        self._dismiss_class_picker()
        self._plugin_document_ready = False
        self._publish_plugin_document(new_generation=True, force=True)
        if hasattr(self, 'plugin_manager'):
            self.plugin_manager.shutdown()
        self.annotation_catalog.cancel()
        if hasattr(self, 'sam_controller'):
            self.sam_controller.cancel()
        decoder = self._close_video_decoder(close_decoder=False)
        all_done = self.task_coordinator.shutdown()
        # Never close a PyAV container while its serialized lane may still be
        # decoding. If cancellation missed the bounded shutdown wait, the
        # worker retains the final reference and releases it when it finishes.
        if decoder is not None and all_done:
            decoder.close()

    def load_recent(self, filename):
        self.request_open_file(filename)

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

    def change_save_dir_dialog(self, _value=False, skip_prompt=False):
        if not skip_prompt and self.dirty:
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return
            if answer == QMessageBox.Yes:
                self.request_save_file(
                    on_success=lambda: self.change_save_dir_dialog(
                        skip_prompt=True))
                return
        if self.default_save_dir is not None:
            path = ustr(self.default_save_dir)
        else:
            path = '.'

        dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                         '%s - Save annotations to the directory' % __appname__, path,  QFileDialog.ShowDirsOnly
                                                         | QFileDialog.DontResolveSymlinks))

        if dir_path is not None and len(dir_path) > 1:
            current_path = self.file_path
            self._dataset_generation = self.task_coordinator.next_generation()
            self.default_save_dir = dir_path
            self.dataset_snapshot = DatasetSnapshot.from_images(
                self.dataset_snapshot.image_paths,
                root_dir=self.dataset_snapshot.root_dir,
                save_dir=dir_path,
                generation=self._dataset_generation)
            self.frame_cache.clear()
            # Clear status cache since annotation directory changed
            self._invalidate_status_cache()
            # Update gallery to reload thumbnails with annotations from new dir
            self.gallery_widget.set_save_dir(self.default_save_dir)
            self.gallery_widget.set_dataset_snapshot(self.dataset_snapshot)
            if hasattr(self, 'full_gallery') and self.full_gallery:
                self.full_gallery.set_dataset_snapshot(self.dataset_snapshot)
            self.annotation_catalog.start(self.dataset_snapshot)
            if current_path:
                self.request_load_file(current_path, skip_prompt=True)

        self.statusBar().showMessage('%s . Annotation will be saved to %s' %
                                     ('Change saved folder', self.default_save_dir))
        self.statusBar().hide()


    def open_annotation_dialog(self, _value=False):
        if self.file_path is None:
            self.statusBar().showMessage('Please select image first')
            self.statusBar().hide()
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
        default_open_dir_path = dir_path if dir_path else '.'
        if self.last_open_dir and os.path.exists(self.last_open_dir):
            default_open_dir_path = self.last_open_dir
        else:
            default_open_dir_path = os.path.dirname(self.file_path) if self.file_path else '.'
        if not silent:
            target_dir_path = ustr(QFileDialog.getExistingDirectory(self,
                                                                    '%s - Open Directory' % __appname__, default_open_dir_path,
                                                                    QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks))
        else:
            target_dir_path = ustr(default_open_dir_path)
        self.request_import_dir_images(target_dir_path)

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
        dialog.exec_()

    def _apply_label_fix(self, old_label, new_label):
        """Report that automatic label rewriting is not implemented.

        Args:
            old_label: The label to replace
            new_label: The replacement label

        Returns:
            False: No annotation files were changed.
        """
        return False

    def apply_status_filter(self, index):
        """Filter file list by annotation status.

        Args:
            index: Filter combo box index. 0=All, 1=Annotated,
                   2=Verified, 3=Unannotated.
        """
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            img_path = item.text()
            status = self._annotation_status_cache.get(img_path)
            if (status is None
                    and tuple(self.m_img_list)
                    != self.dataset_snapshot.image_paths):
                # Compatibility for extensions that replace m_img_list
                # directly instead of installing a DatasetSnapshot.
                status = self._get_annotation_status(img_path)
            # Unknown catalog entries stay visible only in All, matching the
            # gallery's 3.0 asynchronous filter contract.
            show = index == 0 or (
                status is not None
                and self._status_matches_filter(status, index))
            item.setHidden(not show)

        self.gallery_widget.set_status_filter(index)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.set_status_filter(index)
        self._ensure_annotation_catalog()

    def _has_annotation(self, img_path):
        """Check if image has an annotation file.

        Args:
            img_path: Path to the image file.

        Returns:
            True if an annotation file exists for the image.
        """
        resolver = self._active_annotation_resolver(img_path)
        annotation_path = find_existing_annotation(
            img_path,
            save_dir=self.default_save_dir,
            image_list=self.m_img_list,
            extensions=(XML_EXT, TXT_EXT, JSON_EXT),
            resolver=resolver,
        )
        if annotation_path is None:
            annotation_path = self._shared_annotation_path(
                img_path, resolver)
        return annotation_path is not None

    def _is_verified(self, img_path):
        """Check if image annotation is verified.

        Args:
            img_path: Path to the image file.

        Returns:
            True if the annotation is marked as verified.
        """
        annotation_path = find_existing_annotation(
            img_path,
            save_dir=self.default_save_dir,
            image_list=self.m_img_list,
            extensions=(XML_EXT, TXT_EXT, JSON_EXT),
            resolver=self._active_annotation_resolver(img_path),
        )
        if annotation_path and annotation_path.lower().endswith(XML_EXT):
            try:
                reader = PascalVocReader(annotation_path)
                return reader.verified
            except Exception:
                pass
        return False

    def batch_verify(self):
        """Open dialog to batch verify or unverify all annotated images."""
        if not self.m_img_list:
            return

        self._ensure_annotation_catalog()
        if tuple(self.m_img_list) == self.dataset_snapshot.image_paths:
            annotated = sum(
                entry.status != 0
                for entry in self.annotation_catalog.entries.values())
        else:
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
        from libs.tools.batch_verify import batch_verify_atomic
        snapshot = self.dataset_snapshot

        def apply(handle):
            return batch_verify_atomic(
                snapshot.image_paths, snapshot.save_dir, verify, handle,
                resolver=snapshot.resolver)

        worker = self.task_coordinator.submit(
            'background', apply, priority=JobPriority.BULK,
            key='batch-verify', latest=True,
            generation=snapshot.generation)
        worker.progress.connect(
            lambda value: self.status(
                'Preparing verification: %d / %d' % value))
        worker.result.connect(
            lambda result: self._on_batch_verify_finished(
                verify, *result))
        worker.error.connect(
            lambda message: self.status('Batch verification failed: ' + message))
        return worker

    def _on_batch_verify_finished(self, verify, count, failures):
        self._annotation_status_cache.clear()
        self.annotation_catalog.start(self.dataset_snapshot)

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
            self.request_load_file(self.file_path, skip_prompt=True)

    def _apply_batch_verify(self, verify):
        """Set/clear the PASCAL VOC ``verified`` flag across annotated images.

        Returns:
            (count, failures) where ``count`` is the number of images updated
            and ``failures`` is a list of (image_path, reason) for images that
            could not be updated - corrupt/unreadable XML, or a non-VOC
            annotation whose format has no verified flag.
        """
        import xml.etree.ElementTree as ET
        from libs.core.dataset import AnnotationResolver
        count = 0
        failures = []
        resolver = self._active_annotation_resolver()
        if resolver is None or tuple(self.m_img_list) != \
                resolver.image_paths:
            resolver = AnnotationResolver(
                self.m_img_list, self.default_save_dir)
        for img_path in self.m_img_list:
            annotation_path = find_existing_annotation(
                img_path,
                save_dir=self.default_save_dir,
                image_list=self.m_img_list,
                extensions=(XML_EXT, TXT_EXT, JSON_EXT),
                resolver=resolver,
            )
            if annotation_path is None:
                annotation_path = resolver.named_file(
                    img_path, 'annotations.json')
            if not annotation_path:
                continue
            if not annotation_path.lower().endswith(XML_EXT):
                failures.append((img_path, 'not a PASCAL VOC annotation'))
                continue
            try:
                tree = ET.parse(annotation_path)
                root = tree.getroot()
                if verify:
                    root.set('verified', 'yes')
                else:
                    root.attrib.pop('verified', None)
                tree.write(annotation_path)
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

        from libs.tools.dataset_splitter import (
            execute_split_transactional, split_dataset,
        )
        snapshot = self.dataset_snapshot
        ratios = dict(dialog.ratios)
        seed = dialog.seed
        stratified = dialog.stratified
        output_dir = dialog.output_dir
        copy_mode = dialog.copy_mode

        def split(handle):
            splits = split_dataset(
                snapshot.image_paths, ratios, seed=seed,
                stratified=stratified, save_dir=snapshot.save_dir,
                resolver=snapshot.resolver)
            manifest_path = execute_split_transactional(
                splits, output_dir, save_dir=snapshot.save_dir,
                copy=copy_mode, handle=handle,
                resolver=snapshot.resolver)
            return manifest_path, {
                key: len(value) for key, value in splits.items()}

        worker = self.task_coordinator.submit(
            'background', split, priority=JobPriority.BULK,
            key='dataset-split', latest=True,
            generation=snapshot.generation)
        worker.progress.connect(
            lambda value: self.status('Splitting dataset: %d / %d' % value))
        worker.result.connect(self._on_split_complete)
        worker.error.connect(
            lambda message: self.status('Dataset split failed: ' + message))
        return worker

    def _on_split_complete(self, result):
        manifest_path, counts = result
        if not manifest_path:
            self.status('Dataset split cancelled')
            return
        QMessageBox.information(
            self, 'Split Complete',
            f'Dataset split into:\n'
            f'  Train: {counts["train"]} images\n'
            f'  Val: {counts["val"]} images\n'
            f'  Test: {counts["test"]} images\n\n'
            f'Manifest: {manifest_path}'
        )

    def export_ultralytics_dataset(self, _value=False,
                                   skip_dirty_prompt=False):
        """Export the current image dataset in Ultralytics YOLO layout."""
        if (self.document_kind != DocumentKind.IMAGE
                or not self.m_img_list):
            QMessageBox.warning(
                self, 'Export Ultralytics Dataset',
                'No image dataset is loaded. Open a directory first.')
            return None

        if self.dirty and not skip_dirty_prompt:
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return None
            if answer == QMessageBox.Yes:
                return self.request_save_file(
                    on_success=lambda: self.export_ultralytics_dataset(
                        skip_dirty_prompt=True))

        from libs.widgets.ultralyticsExportDialog import (
            UltralyticsExportDialog,
        )
        default_dir = self.dataset_snapshot.root_dir or (
            os.path.dirname(self.m_img_list[0])
            if self.m_img_list else '')
        dialog = UltralyticsExportDialog(
            self, len(self.m_img_list), default_dir)
        if hasattr(self, '_current_theme'):
            dialog.apply_theme(self._current_theme)
        if dialog.exec_() != QDialog.Accepted:
            return None

        output_dir = ustr(dialog.output_dir)
        if not output_dir:
            QMessageBox.warning(
                self, 'Export Ultralytics Dataset',
                'Please select an output directory.')
            return None
        if (os.path.lexists(output_dir)
                and (os.path.islink(output_dir)
                     or not os.path.isdir(output_dir)
                     or os.listdir(output_dir))):
            QMessageBox.warning(
                self, 'Export Ultralytics Dataset',
                'The destination must be a new or empty directory.')
            return None

        from libs.core.ultralytics_export import (
            UltralyticsExportRequest, export_ultralytics_dataset,
        )
        snapshot = self.dataset_snapshot
        request = UltralyticsExportRequest(
            destination=output_dir,
            image_paths=snapshot.image_paths,
            save_dir=snapshot.save_dir,
            resolver=snapshot.resolver,
            source_format=self.label_file_format,
            class_order=tuple(self.label_hist),
            ratios=tuple(dialog.ratios.items()),
            seed=dialog.seed,
            copy_images=dialog.copy_mode,
        )

        def export_dataset(handle):
            return export_ultralytics_dataset(request, handle)

        worker = self.task_coordinator.submit(
            'background', export_dataset, priority=JobPriority.BULK,
            key='ultralytics-export', latest=True,
            generation=snapshot.generation)
        worker.progress.connect(
            lambda value: self.status(
                'Exporting Ultralytics dataset: %d / %d' % value))
        worker.result.connect(self._on_ultralytics_export_complete)
        worker.error.connect(self._on_ultralytics_export_error)
        return worker

    def _on_ultralytics_export_complete(self, result):
        if result is None:
            self.status('Ultralytics dataset export cancelled')
            return
        counts = result.counts_by_split
        details = (
            'Ultralytics dataset exported to:\n%s\n\n'
            'Train: %d images\nVal: %d images\nTest: %d images\n'
            'Classes: %d\nAnnotated: %d\nUnannotated: %d'
            % (result.destination, counts['train'], counts['val'],
               counts['test'], len(result.class_order),
               result.annotated_images, result.unannotated_images))
        if result.polygon_boxes:
            details += ('\nPolygon annotations converted to boxes: %d'
                        % result.polygon_boxes)
        QMessageBox.information(
            self, 'Ultralytics Export Complete', details)
        self.status('Exported Ultralytics dataset to %s'
                    % result.destination)

    def _on_ultralytics_export_error(self, message):
        self.status('Ultralytics dataset export failed: ' + message)
        self.error_message('Ultralytics Export Failed', message)

    def import_dir_images(self, dir_path):
        """Synchronous compatibility path used by tests and extensions."""
        if not self.may_continue() or not dir_path:
            return False
        self._dataset_generation = self.task_coordinator.next_generation()
        with trace_span('directory.scan', args={
                'root': hash_path(dir_path)}):
            snapshot = DatasetSnapshot.scan(
                dir_path, save_dir=self.default_save_dir,
                generation=self._dataset_generation,
                extensions=self._supported_image_extensions())
        self._commit_dataset_snapshot(snapshot)
        if snapshot.image_paths:
            self.cur_img_idx = 0
            self.load_file(snapshot.image_paths[0])
        return True

    def request_import_dir_images(self, dir_path, skip_prompt=False):
        """Transactionally scan a directory without clearing the live dataset."""
        if not dir_path:
            return None
        dir_path = os.path.abspath(ustr(dir_path))
        if not skip_prompt and self.dirty:
            if self.auto_saving.isChecked() and self.default_save_dir:
                self.request_save_file(
                    on_success=lambda: self.request_import_dir_images(
                        dir_path, skip_prompt=True))
                return None
            answer = self.discard_changes_dialog()
            if answer == QMessageBox.Cancel:
                return None
            if answer == QMessageBox.Yes:
                self.request_save_file(
                    on_success=lambda: self.request_import_dir_images(
                        dir_path, skip_prompt=True))
                return None
        previous_snapshot = self.dataset_snapshot
        self._dataset_generation = self.task_coordinator.next_generation()
        generation = self._dataset_generation
        save_dir = self.default_save_dir or dir_path
        extensions = self._supported_image_extensions()
        self._show_loading_veil('Scanning directory…')

        def scan(handle):
            with trace_span('directory.scan', args={'root': hash_path(dir_path)}):
                return DatasetSnapshot.scan(
                    dir_path, save_dir=save_dir, generation=generation,
                    extensions=extensions,
                    cancelled=handle.is_cancelled,
                    progress=lambda visited, found: handle.report_progress(
                        (visited, found)))

        handle = self.task_coordinator.submit(
            'background', scan, priority=JobPriority.CATALOG,
            key='directory-scan', latest=True, generation=generation)
        handle.progress.connect(
            lambda value, g=generation:
            self.status('Scanning: %d files, %d images' % value)
            if g == self._dataset_generation else None)
        handle.result.connect(
            lambda snapshot, g=generation:
            self._on_directory_snapshot(snapshot, g))
        handle.error.connect(
            lambda message, g=generation, previous=previous_snapshot:
            self._on_directory_scan_error(message, g, previous))
        return handle

    def _supported_image_extensions(self):
        return tuple(
            '.%s' % fmt.data().decode('ascii').lower()
            for fmt in QImageReader.supportedImageFormats())

    def _on_directory_snapshot(self, snapshot, generation):
        if generation != self._dataset_generation or snapshot is None:
            return
        self._commit_dataset_snapshot(snapshot)
        self._hide_loading_veil()
        if snapshot.image_paths:
            self.cur_img_idx = 0
            self.request_load_file(snapshot.image_paths[0], skip_prompt=True)

    def _on_directory_scan_error(self, message, generation,
                                 previous_snapshot=None):
        if generation != self._dataset_generation:
            return
        self._hide_loading_veil()
        if previous_snapshot is not None:
            self.dataset_snapshot = previous_snapshot.with_generation(
                generation)
            if self.dataset_snapshot.image_paths:
                self.annotation_catalog.start(self.dataset_snapshot)
        self.status('Directory scan failed: ' + message)

    def _commit_dataset_snapshot(self, snapshot):
        """Atomically replace all dataset-facing widgets on the GUI thread."""
        trace_started = None
        if trace_recorder is not None:
            import time
            trace_started = time.perf_counter_ns()
        self.annotation_catalog.cancel()
        self.dataset_snapshot = snapshot
        self.last_open_dir = snapshot.root_dir
        self.dir_name = snapshot.root_dir
        self.default_save_dir = snapshot.save_dir
        self.m_img_list = list(snapshot.image_paths)
        self._path_to_idx = dict(snapshot.path_to_index)
        self.img_count = len(snapshot.image_paths)
        self.cur_img_idx = 0
        self._annotation_status_cache.clear()
        self.frame_cache.clear()
        self.reset_state()

        self.file_list_widget.setUpdatesEnabled(False)
        try:
            self.file_list_widget.clear()
            self.file_list_widget.addItems(self.m_img_list)
        finally:
            self.file_list_widget.setUpdatesEnabled(True)
        self.gallery_widget.set_dataset_snapshot(snapshot)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.set_dataset_snapshot(snapshot)
        self.update_image_count()
        if snapshot.image_paths:
            self.annotation_catalog.start(snapshot)
        if trace_recorder is not None:
            trace_recorder.complete(
                'directory.ui-apply', trace_started,
                args={'images': len(snapshot.image_paths)})

    def _show_loading_veil(self, text):
        if self._loading_veil is None:
            self._loading_veil = QLabel(self.centralWidget())
            self._loading_veil.setAlignment(Qt.AlignCenter)
            self._loading_veil.setStyleSheet(
                'background: rgba(20, 20, 20, 150); color: white; '
                'font-size: 18px; padding: 20px;')
        self._loading_veil.setText(text)
        self._loading_veil.setGeometry(self.centralWidget().rect())
        self._loading_veil.show()
        self._loading_veil.raise_()

    def _hide_loading_veil(self):
        if self._loading_veil is not None:
            self._loading_veil.hide()

    def verify_image(self, _value=False):
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                return False
            if self.current_video_frame_ref is None:
                return
            self.video_model.set_frame_verified(
                self.current_video_frame_ref.pts,
                not bool(self.canvas.verified))
            self.canvas.verified = not bool(self.canvas.verified)
            self._on_video_model_mutation()
            return self.save_video_project()
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

    def request_verify_image(self, _value=False):
        """Toggle verification and persist it through the async save lane."""
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                return None
            if self.current_video_frame_ref is None:
                return None
            self.video_model.set_frame_verified(
                self.current_video_frame_ref.pts,
                not bool(self.canvas.verified))
            self.canvas.verified = not bool(self.canvas.verified)
            if self.lock_on_verify_option.isChecked():
                self.canvas.locked = self.canvas.verified
            self._on_video_model_mutation()
            self.paint_canvas()
            return self.request_save_video_project()
        if self.file_path is None:
            return None
        if self.label_file is None:
            self.label_file = LabelFile()
        self.label_file.verified = not bool(self.canvas.verified)
        self.canvas.verified = self.label_file.verified
        if self.lock_on_verify_option.isChecked():
            self.canvas.locked = self.canvas.verified
        self.set_dirty()
        self.paint_canvas()
        return self.request_save_file()

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
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        formats = ['*.%s' % fmt.data().decode("ascii").lower() for fmt in QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(formats + ['*%s' % LabelFile.suffix])
        filename,_ = QFileDialog.getOpenFileName(self, '%s - Choose Image or Label file' % __appname__, path, filters)
        if filename:
            if isinstance(filename, (tuple, list)):
                filename = filename[0]
            self.request_open_file(filename)

    def open_video_dialog(self, _value=False):
        path = os.path.dirname(ustr(self.file_path)) if self.file_path else '.'
        filters = (
            'Video and LabelImg++ projects '
            '(*.mp4 *.mov *.mkv *.avi *.labelimgpp.sqlite);;'
            'All files (*)')
        filename, _selected_filter = QFileDialog.getOpenFileName(
            self, '%s - Choose Video or Project' % __appname__,
            path, filters)
        if filename:
            self.request_open_video(ustr(filename))

    def request_save_file(self, _value=False, on_success=None,
                          annotation_base=None):
        """Queue an immutable, revision-aware save for GUI workflows."""
        if self.document_kind == DocumentKind.VIDEO:
            return self.request_save_video_project(on_success=on_success)
        if not self.file_path:
            return None
        degradation_formats = {
            LabelFileFormat.YOLO: FORMAT_YOLO,
            LabelFileFormat.CREATE_ML: FORMAT_CREATEML,
        }
        degradation = degradation_formats.get(self.label_file_format)
        if degradation and not self._check_polygon_degradation(degradation):
            return None

        if annotation_base:
            annotation_base = ustr(annotation_base)
        elif (self.default_save_dir is not None
              and len(ustr(self.default_save_dir))):
            resolver = self._active_annotation_resolver(self.file_path)
            shared_path = (
                self._shared_annotation_path(self.file_path, resolver)
                if self.label_file_format in (
                    LabelFileFormat.CREATE_ML, LabelFileFormat.COCO)
                else None)
            annotation_base = shared_path or annotation_output_base(
                self.file_path, ustr(self.default_save_dir), self.m_img_list,
                resolver=resolver)
        else:
            image_dir = os.path.dirname(self.file_path)
            image_stem = os.path.splitext(os.path.basename(self.file_path))[0]
            annotation_base = os.path.join(image_dir, image_stem)
            if self.label_file is None:
                annotation_base = self.save_file_dialog(remove_ext=False)
        if not annotation_base:
            return None

        inverse_scale = (1.0 / self._image_scale_factor
                         if self._image_scale_factor else 1.0)
        serialized = []
        for shape in self.canvas.shapes:
            values = {
                'label': shape.label,
                'line_color': shape.line_color.getRgb(),
                'fill_color': shape.fill_color.getRgb(),
                'points': tuple(
                    (point.x() * inverse_scale,
                     point.y() * inverse_scale)
                    for point in shape.points),
                'difficult': shape.difficult,
                'shape_type': shape.shape_type.value,
            }
            if shape.keypoints is not None:
                values['keypoints'] = tuple(
                    (point[0] * inverse_scale,
                     point[1] * inverse_scale, point[2])
                    if point is not None else None
                    for point in shape.keypoints)
            serialized.append(tuple(values.items()))
        request = SaveRequest(
            image_path=self.file_path,
            annotation_path=annotation_target_path(
                annotation_base, self.label_file_format),
            label_file_format=self.label_file_format,
            shapes=tuple(serialized),
            class_list=tuple(self.label_hist),
            verified=bool(self.canvas.verified),
            revision=self._document_revision,
        )
        save_lock = self._save_locks.setdefault(
            request.annotation_path, threading.Lock())

        def save(handle):
            with save_lock:
                handle.check_cancelled()
                with trace_span('annotation.save', args={
                        'path': hash_path(request.annotation_path)}):
                    return write_save_request(
                        request, cancelled=handle.is_cancelled,
                        begin_commit=handle.begin_non_cancellable)

        handle = self.task_coordinator.submit(
            'background', save, priority=JobPriority.IMAGE_LOAD,
            key='save:' + request.image_path, latest=True,
            generation=self._dataset_generation)
        self._save_handle = handle
        handle.result.connect(
            lambda path, req=request, callback=on_success,
            gen=self._dataset_generation:
            self._on_save_result(path, req, callback, gen))
        handle.error.connect(self._on_save_error)
        return handle

    def _on_save_result(self, path, request, on_success, generation=None):
        if path is None:
            return
        if (generation is not None
                and generation != self._dataset_generation):
            self.status('Saved superseded document to %s' % path)
            return
        self._record_annotation_written(path)
        if (self.file_path == request.image_path
                and self._document_revision == request.revision):
            self.set_clean()
        self.status('Saved to %s' % path)
        if self.file_path == request.image_path:
            self._update_current_image_gallery_status()
        if callable(on_success):
            on_success()

    def _on_save_error(self, message):
        self.status('Error saving annotation: ' + message)

    def _record_annotation_written(self, path):
        if getattr(self, 'dataset_snapshot', None) is None:
            return
        self.dataset_snapshot = self.dataset_snapshot.with_annotation_file(
            path, image_path=self.file_path)
        if self.file_path:
            self.frame_cache.remove(self.file_path)
        resolver = self.dataset_snapshot.resolver
        self.gallery_widget.set_annotation_resolver(resolver)
        if hasattr(self, 'full_gallery') and self.full_gallery:
            self.full_gallery.set_annotation_resolver(resolver)
        self.annotation_catalog._json_cache.invalidate(path)
        if self.file_path:
            self.annotation_catalog.invalidate(
                self.file_path, snapshot=self.dataset_snapshot)

    def save_file(self, _value=False):
        if self.document_kind == DocumentKind.VIDEO:
            return self.save_video_project()
        if not self.file_path:
            return False

        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            resolver = self._active_annotation_resolver(self.file_path)
            shared_path = (
                self._shared_annotation_path(self.file_path, resolver)
                if self.label_file_format in (
                    LabelFileFormat.CREATE_ML, LabelFileFormat.COCO)
                else None)
            saved_path = shared_path or annotation_output_base(
                self.file_path, ustr(self.default_save_dir), self.m_img_list,
                resolver=resolver)
            return self._save_file(saved_path)
        else:
            image_file_dir = os.path.dirname(self.file_path)
            image_file_name = os.path.basename(self.file_path)
            saved_file_name = os.path.splitext(image_file_name)[0]
            saved_path = os.path.join(image_file_dir, saved_file_name)
            return self._save_file(saved_path if self.label_file
                                   else self.save_file_dialog(remove_ext=False))

    def save_file_as(self, _value=False):
        if self.document_kind == DocumentKind.VIDEO:
            target = self._video_project_save_dialog()
            if not target:
                return False
            if self.video_model.dirty and not self.save_video_project():
                return False
            try:
                save_project_as(self.video_snapshot.project_path, target)
            except Exception as exc:
                self.status('Error saving video project: %s' % exc)
                return False
            return True
        assert not self.image.isNull(), "cannot save empty image"
        return self._save_file(self.save_file_dialog())

    def request_save_file_as(self, _value=False):
        """Choose a target on the GUI thread and write it asynchronously."""
        if self.document_kind == DocumentKind.VIDEO:
            target = self._video_project_save_dialog()
            if not target:
                return None
            if self.video_model.dirty:
                return self.request_save_video_project(
                    on_success=lambda: self._request_video_project_backup(
                        target))
            return self._request_video_project_backup(target)

        assert not self.image.isNull(), "cannot save empty image"
        annotation_base = self.save_file_dialog()
        if not annotation_base:
            return None
        return self.request_save_file(annotation_base=annotation_base)

    def _request_video_project_backup(self, target):
        source = self.video_snapshot.project_path

        def save_as(handle):
            handle.check_cancelled()
            return save_project_as(source, target)

        handle = self.task_coordinator.submit(
            'background', save_as, priority=JobPriority.IMAGE_LOAD,
            key='video-project-save-as', latest=True,
            generation=self._dataset_generation)
        handle.result.connect(
            lambda path: self.status('Saved video project to %s' % path))
        handle.error.connect(
            lambda message: self.status(
                'Error saving video project: ' + message))
        return handle

    def _video_project_save_dialog(self):
        snapshot = self.video_snapshot
        if snapshot is None or not snapshot.project_path:
            return ''
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self, '%s - Save Video Project As' % __appname__,
            snapshot.project_path,
            'LabelImg++ video project (*.labelimgpp.sqlite)')
        filename = ustr(filename)
        if filename and not filename.lower().endswith('.labelimgpp.sqlite'):
            filename += '.labelimgpp.sqlite'
        return filename

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
        if not annotation_file_path or not self.save_labels(annotation_file_path):
            return False

        self._record_annotation_written(annotation_target_path(
            annotation_file_path, self.label_file_format))
        self.set_clean()
        self.statusBar().showMessage('Saved to  %s' % annotation_file_path)
        self.statusBar().hide()
        # Update gallery status after save
        self._update_current_image_gallery_status()
        return True

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
        if delete_path is None:
            return False

        confirmation = QMessageBox.warning(
            self,
            u'Delete Image',
            (u'Permanently delete the current image?\n\n%s\n\n'
             u'This action cannot be undone. Annotation files will be kept.')
            % delete_path,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirmation != QMessageBox.Yes:
            return False

        if not self.may_continue():
            return False

        idx = self.cur_img_idx
        try:
            os.remove(delete_path)
        except OSError as error:
            self.error_message(
                u'Error deleting image',
                u'Could not delete %s:\n%s' % (delete_path, error),
            )
            self.status(u'Could not delete %s' % delete_path)
            return False

        # may_continue() deliberately leaves dirty set when the user chooses
        # to discard edits. Clear it only after the image is actually deleted
        # so refreshing the directory cannot prompt for those edits again.
        self.set_clean()
        if delete_path in self.dataset_snapshot.path_to_index:
            self._dataset_generation = self.task_coordinator.next_generation()
            snapshot = self.dataset_snapshot.without(delete_path)
            if snapshot.generation != self._dataset_generation:
                snapshot = DatasetSnapshot.from_images(
                    snapshot.image_paths, root_dir=snapshot.root_dir,
                    save_dir=snapshot.save_dir,
                    generation=self._dataset_generation)
            self._commit_dataset_snapshot(snapshot)
        else:
            # Compatibility for extensions that manage m_img_list directly.
            reload_dir = self.last_open_dir or os.path.dirname(delete_path)
            self.import_dir_images(reload_dir)
        if self.img_count > 0:
            self.cur_img_idx = min(idx, self.img_count - 1)
            filename = self.m_img_list[self.cur_img_idx]
            self.request_load_file(filename, skip_prompt=True)
        else:
            self.close_file()
        return True

    def reset_all(self):
        if not self.may_continue():
            return False

        self._reset_all_in_progress = True
        try:
            self.settings.reset()
            if not self.close():
                return False
        finally:
            self._reset_all_in_progress = False

        process = QProcess()
        # Relaunch through the Python interpreter so the restart works for an
        # installed (entry-point) package, not just a source checkout.
        process.startDetached(sys.executable, [os.path.abspath(__file__)])
        return True

    def may_continue(self):
        if not self.dirty:
            return True
        else:
            discard_changes = self.discard_changes_dialog()
            if discard_changes == QMessageBox.No:
                return True
            elif discard_changes == QMessageBox.Yes:
                return self.save_file()
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
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
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
        if self.document_kind == DocumentKind.VIDEO:
            if not self._ensure_video_editable():
                return
            track_id = getattr(shape, 'video_track_id', None)
            if track_id is None:
                return
            before = self.video_model.snapshot_state()
            self.video_model.delete_occurrence(
                track_id, self.current_video_frame_ref.pts)
            after = self.video_model.snapshot_state()
            self.undo_stack.push(VideoModelCommand(
                self, before, after, 'Delete video occurrence'))
            self._on_video_model_mutation()
            self._materialize_video_frame(self.current_video_frame_ref.pts)
            return
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
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        if self.undo_stack.can_undo():
            self.undo_stack.undo()
            self.set_dirty()
            self.canvas.update()

    def redo_action(self):
        """Redo the last undone action."""
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        if self.undo_stack.can_redo():
            self.undo_stack.redo()
            self.set_dirty()
            self.canvas.update()

    def update_undo_redo_actions(self):
        """Update the enabled state of undo/redo actions."""
        editable = self._video_editable()
        self.actions.undo.setEnabled(
            self.undo_stack.can_undo() and editable)
        self.actions.redo.setEnabled(
            self.undo_stack.can_redo() and editable)

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
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        color = self.color_dialog.getColor(self.line_color, u'Choose Line Color',
                                           default=DEFAULT_LINE_COLOR)
        if color:
            if self.document_kind == DocumentKind.VIDEO:
                track_id = self.current_annotation_identity()
                if track_id is None:
                    return
                before = self.video_model.snapshot_state()
                self.video_model.update_track(track_id, color=color.getRgb())
                after = self.video_model.snapshot_state()
                self.undo_stack.push(VideoModelCommand(
                    self, before, after, 'Change video track color'))
                self._on_video_model_mutation()
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
                return
            shape = self.canvas.selected_shape
            if shape is None:
                return
            old_color = shape.line_color
            shape.line_color = color
            self.undo_stack.push(EditShapeAttributesCommand(
                self, shape, {'line_color': old_color},
                {'line_color': color}, 'Change shape line color'))
            self.annotation_model.notify_identity_changed(
                self.annotation_model.identity_for_shape(shape))
            self.canvas.update()
            self.set_dirty()

    def choose_shape_fill_color(self):
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        color = self.color_dialog.getColor(self.fill_color, u'Choose Fill Color',
                                           default=DEFAULT_FILL_COLOR)
        if color:
            if self.document_kind == DocumentKind.VIDEO:
                track_id = self.current_annotation_identity()
                if track_id is None:
                    return
                before = self.video_model.snapshot_state()
                self.video_model.update_track(track_id, color=color.getRgb())
                after = self.video_model.snapshot_state()
                self.undo_stack.push(VideoModelCommand(
                    self, before, after, 'Change video track color'))
                self._on_video_model_mutation()
                self._materialize_video_frame(
                    self.current_video_frame_ref.pts)
                return
            shape = self.canvas.selected_shape
            if shape is None:
                return
            old_color = shape.fill_color
            shape.fill_color = color
            self.undo_stack.push(EditShapeAttributesCommand(
                self, shape, {'fill_color': old_color},
                {'fill_color': color}, 'Change shape fill color'))
            self.canvas.update()
            self.set_dirty()

    def copy_shape(self):
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
        if self.canvas.selected_shape is None:
            # True if one accidentally touches the left mouse button before releasing
            return
        self.canvas.end_move(copy=True)
        self.add_label(self.canvas.selected_shape)
        self.set_dirty()

    def move_shape(self):
        if (self.document_kind == DocumentKind.VIDEO
                and not self._ensure_video_editable()):
            return
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
            self.request_save_file()

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
                from libs.widgets.toolBar import calculate_icon_size
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
        """Synchronous auto-save compatibility hook for extensions/tests."""
        if not self.dirty:
            return  # Nothing to save

        if not self.file_path:
            return  # No file loaded

        if self.default_save_dir is not None and len(ustr(self.default_save_dir)):
            save_path = annotation_output_base(
                self.file_path, ustr(self.default_save_dir), self.m_img_list,
                resolver=self._active_annotation_resolver(self.file_path))
        else:
            image_dir = os.path.dirname(self.file_path)
            image_stem = os.path.splitext(os.path.basename(self.file_path))[0]
            save_path = os.path.join(image_dir, image_stem)
        if save_path:
            self.status("Auto-saving...")
            self._save_file(save_path)
            self.status("Auto-saved to %s" % os.path.basename(save_path))

    def _request_auto_save_triggered(self):
        if self.dirty and self.file_path:
            self.status("Auto-saving...")
            self.request_save_file()

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
        from libs.utils.styles import get_theme_colors

        # Resolve the palette once up front; several blocks below (including
        # the save-status refresh) read it regardless of which widgets exist.
        colors = get_theme_colors(theme)

        # Apply main stylesheet
        self.setStyleSheet(get_stylesheet(theme))

        if hasattr(self, 'tool_rail') and self.tool_rail:
            self.tool_rail.apply_theme(theme)
        if hasattr(self, 'workspace_inspector'):
            self.workspace_inspector.apply_theme(theme)
        if hasattr(self, 'workspace_shell'):
            self.workspace_shell.apply_theme(theme)

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

        if hasattr(self, 'command_bar'):
            self.command_bar.apply_theme(theme)

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
        """Complete label data in the shared catalog, then aggregate it."""
        # A refresh may already be queued when closeEvent shuts the worker
        # lanes down. Submitting from that late Qt callback raises inside a
        # slot and aborts the process, so closed windows must be inert.
        if not self._ensure_annotation_catalog():
            return
        self.annotation_catalog.request_statistics()

    def _update_current_image_stats(self):
        """Update statistics for the current image."""
        if not hasattr(self, 'gallery_stats') or not self.gallery_stats:
            return

        annotations_count = len(self.canvas.shapes)
        labels = [shape.label for shape in self.canvas.shapes]
        self.gallery_stats.update_current_image_stats(
            annotations_count, labels)

    def _get_labels_for_image(self, img_path):
        """Get list of labels for an image from its annotation file."""
        return probe_annotation(
            img_path, self.default_save_dir, want_labels=True,
            image_list=self.m_img_list,
            resolver=self._active_annotation_resolver(img_path),
            json_cache=self.annotation_catalog._json_cache).labels


def get_main_app(argv=None):
    """
    Standard boilerplate Qt application code.
    Do everything but app.exec_() -- so that we can test the application in one thread
    """
    if not argv:
        argv = []

    app = QApplication.instance()
    if app is None:
        # These attributes must be set before constructing QApplication.
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
