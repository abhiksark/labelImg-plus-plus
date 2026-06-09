# libs/widgets/canvas.py
"""Canvas widget for drawing and editing bounding box annotations."""

try:
    from PyQt5.QtGui import QColor, QPixmap, QPainter, QCursor, QBrush, QPen
    from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QPoint
    from PyQt5.QtWidgets import QWidget, QMenu, QApplication
except ImportError:
    from PyQt4.QtGui import (
        QColor, QPixmap, QPainter, QCursor, QBrush, QWidget, QMenu, QApplication
    )
    from PyQt4.QtCore import Qt, pyqtSignal, QPointF, QPoint

import math

from libs.core.shape import Shape, ShapeType
from libs.utils.dpi import scale_px
from libs.utils.utils import distance, douglas_peucker
from libs.utils.styles import Theme

CURSOR_DEFAULT = Qt.ArrowCursor
CURSOR_POINT = Qt.PointingHandCursor
CURSOR_DRAW = Qt.CrossCursor
CURSOR_MOVE = Qt.ClosedHandCursor
CURSOR_GRAB = Qt.OpenHandCursor


class Canvas(QWidget):
    zoomRequest = pyqtSignal(int)
    lightRequest = pyqtSignal(int)
    scrollRequest = pyqtSignal(int, int)
    newShape = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()
    drawingPolygon = pyqtSignal(bool)
    # Emitted on polygon vertex insert / remove / drag-move with the
    # pre-mutation points list so MainWindow can push an undo command.
    polygonVerticesEdited = pyqtSignal(object, object)  # (shape, old_points)
    # Emitted on keypoint placement / mutation with the pre-mutation
    # keypoints list (may be None) for undo support.
    keypointsEdited = pyqtSignal(object, object)        # (shape, old_keypoints)
    # Emitted on mouse release after a non-polygon shape (rectangle) was moved
    # or resized, with the pre-drag points list, so MainWindow can push a
    # MoveShapeCommand. Polygon edits use polygonVerticesEdited instead.
    shapeMoveFinished = pyqtSignal(object, object)      # (shape, old_points)

    CREATE, EDIT, CREATE_POLYGON, KEYPOINT_MODE = list(range(4))

    def __init__(self, *args, **kwargs):
        super(Canvas, self).__init__(*args, **kwargs)
        # Initialise local state.
        # Hit-test tolerance as a screen-pixel radius; scaled for HiDPI so
        # grabbing vertices feels the same on high-density displays. Set per
        # instance (not a class attribute) so the DPI factor is read after the
        # QApplication exists.
        self.epsilon = float(scale_px(24))
        self.mode = self.EDIT
        self.shapes = []
        self.current = None
        self.selected_shape = None  # save the selected shape here
        self.selected_shape_copy = None
        self.drawing_line_color = QColor(0, 0, 255)
        self.drawing_rect_color = QColor(0, 0, 255)
        self.line = Shape(line_color=self.drawing_line_color)
        self.prev_point = QPointF()
        self.offsets = QPointF(), QPointF()
        self.scale = 1.0
        self.overlay_color = None
        # Cache for the overlay-composited pixmap so paintEvent does not copy
        # and re-composite the full-resolution image on every repaint.
        self._overlay_cache = None
        self._overlay_cache_key = None
        self.label_font_size = 8
        self.pixmap = QPixmap()
        self.visible = {}
        self._hide_background = False
        self.hide_background = False
        self.h_shape = None
        self.h_vertex = None
        self._painter = QPainter()
        self._cursor = CURSOR_DEFAULT
        # Menus:
        self.menus = (QMenu(), QMenu())
        # Set widget options.
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.WheelFocus)
        self.verified = False
        self._locked = False
        self.draw_square = False

        # Theme background color for dark mode support
        self._theme_background = QColor(232, 232, 232, 255)  # Default light mode
        self._theme = Theme.LIGHT  # Default theme
        self._verified_bg_color = QColor(184, 239, 38, 128)  # Default
        self._crosshair_color = QColor(0, 0, 0)  # Default light mode crosshair

        # Grid and edge alignment state
        self._grid_enabled = False
        self._grid_size = 32
        self._edge_alignment = False
        self._alignment_guides = []

        # initialisation for panning
        self.pan_initial_pos = QPoint()

        # Freehand polygon drawing state
        self._freehand_active = False
        self._freehand_points = []

        # Keypoint annotation state
        self._keypoint_shape = None
        self._keypoint_index = 0
        self._hovered_keypoint = -1
        self._keypoint_template_name = None
        self._keypoint_template = None

        # Snapshot of points list captured at the start of a polygon
        # vertex drag, so we can emit polygonVerticesEdited on release
        # if the drag actually changed any vertex position.
        self._polygon_drag_old_points = None

        # Same idea for non-polygon (rectangle) shapes moved or resized by
        # drag, emitted as shapeMoveFinished on release for undo support.
        self._move_shape_old_points = None

    def set_drawing_color(self, qcolor):
        self.drawing_line_color = qcolor
        self.drawing_rect_color = qcolor

    def set_background_color(self, color):
        """Set canvas background color (for dark mode support)."""
        self._theme_background = QColor(color)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self._theme_background)
        self.setAutoFillBackground(True)
        self.setPalette(palette)
        self.update()

    def set_theme(self, theme):
        """Set theme and update colors."""
        from libs.utils.styles import get_theme_colors, hex_to_qcolor
        self._theme = theme
        colors = get_theme_colors(theme)
        # Parse hex to QColor with alpha
        self._verified_bg_color = hex_to_qcolor(colors['verified_bg'], alpha=128)
        self._crosshair_color = hex_to_qcolor(colors['text'])

    def enterEvent(self, ev):
        self.override_cursor(self._cursor)

    def leaveEvent(self, ev):
        self.restore_cursor()

    def focusOutEvent(self, ev):
        self.restore_cursor()

    def isVisible(self, shape):
        return self.visible.get(shape, True)

    def drawing(self):
        return self.mode in (self.CREATE, self.CREATE_POLYGON)

    def editing(self):
        return self.mode == self.EDIT

    def drawing_polygon(self):
        return self.mode == self.CREATE_POLYGON

    def set_editing(self, value=True):
        self.mode = self.EDIT if value else self.CREATE
        if not value:  # Create
            self.un_highlight()
            self.de_select_shape()
        self.prev_point = QPointF()
        self.repaint()

    def set_polygon_drawing(self, value=True):
        self.mode = self.CREATE_POLYGON if value else self.EDIT
        if value:
            self.un_highlight()
            self.de_select_shape()
        self.prev_point = QPointF()
        self.repaint()

    def set_keypoint_mode(self, shape, template_name='person'):
        """Enter keypoint placement mode for the given shape."""
        from libs.core.keypoint_config import get_template
        self._keypoint_shape = shape
        self._keypoint_template_name = template_name
        self._keypoint_template = get_template(template_name)
        self._keypoint_index = self._next_unplaced_keypoint(0)
        self.mode = self.KEYPOINT_MODE
        self.update()

    def exit_keypoint_mode(self):
        """Exit keypoint mode, return to edit."""
        self._keypoint_shape = None
        self._keypoint_index = 0
        self._hovered_keypoint = -1
        self._keypoint_template_name = None
        self._keypoint_template = None
        self.mode = self.EDIT
        self.update()

    def _keypoint_count(self):
        """Return the number of keypoints in the current template."""
        if self._keypoint_template:
            return len(self._keypoint_template['names'])
        return 17

    def _next_unplaced_keypoint(self, start):
        """Find next unplaced keypoint index. Returns count if all done."""
        count = self._keypoint_count()
        kps = self._keypoint_shape.keypoints
        for i in range(start, count):
            if kps is None or kps[i] is None:
                return i
        return count

    @property
    def locked(self):
        return self._locked

    @locked.setter
    def locked(self, value):
        self._locked = value
        if value:
            self.un_highlight()
            self.de_select_shape()
            self.override_cursor(CURSOR_DEFAULT)
        self.update()

    def un_highlight(self, shape=None):
        if shape == None or shape == self.h_shape:
            if self.h_shape:
                self.h_shape.highlight_clear()
            self.h_vertex = self.h_shape = None

    def selected_vertex(self):
        return self.h_vertex is not None

    def mouseMoveEvent(self, ev):
        """Update line with last point and current coordinates."""
        if self._locked:
            return
        pos = self.transform_pos(ev.pos())

        # Update coordinates in status bar if image is opened
        window = self.parent().window()
        if window.file_path is not None:
            self.parent().window().label_coordinates.setText(
                'X: %d; Y: %d' % (pos.x(), pos.y()))

        # Freehand polygon tracing
        if self._freehand_active and Qt.LeftButton & ev.buttons():
            if not self.out_of_pixmap(pos):
                last = self._freehand_points[-1]
                if math.hypot(pos.x() - last.x(), pos.y() - last.y()) >= 5.0:
                    self._freehand_points.append(pos)
                    self.update()
            return

        # Keypoint hover detection
        if self.mode == self.KEYPOINT_MODE and self._keypoint_shape:
            self._hovered_keypoint = self._keypoint_at(pos)
            self.update()

        # Polygon drawing.
        if self.drawing():
            self.override_cursor(CURSOR_DRAW)
            if self.current:
                color = self.drawing_line_color

                if self.mode == self.CREATE_POLYGON:
                    # Polygon mode: show close indicator near first vertex
                    if len(self.current) >= 3 and self.close_enough(pos, self.current[0]):
                        pos = self.current[0]
                        color = self.current.line_color
                        self.override_cursor(CURSOR_POINT)
                        self.current.highlight_vertex(0, Shape.NEAR_VERTEX)
                    self.line[1] = self.apply_snapping(pos)
                    self.line.line_color = color
                    self.current.highlight_clear()

                    # Update status bar with vertex count
                    window = self.parent().window()
                    if hasattr(window, 'label_coordinates'):
                        window.label_coordinates.setText(
                            'Vertices: %d / X: %d; Y: %d' % (len(self.current), pos.x(), pos.y()))
                else:
                    # Rectangle mode: display annotation width and height while drawing
                    current_width = abs(self.current[0].x() - pos.x())
                    current_height = abs(self.current[0].y() - pos.y())
                    self.parent().window().label_coordinates.setText(
                            'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))

                    if self.out_of_pixmap(pos):
                        # Don't allow the user to draw outside the pixmap.
                        # Clip the coordinates to 0 or max,
                        # if they are outside the range [0, max]
                        size = self.pixmap.size()
                        clipped_x = min(max(0, pos.x()), size.width())
                        clipped_y = min(max(0, pos.y()), size.height())
                        pos = QPointF(clipped_x, clipped_y)
                    elif len(self.current) > 1 and self.close_enough(pos, self.current[0]):
                        # Attract line to starting point and colorise to alert the
                        # user:
                        pos = self.current[0]
                        color = self.current.line_color
                        self.override_cursor(CURSOR_POINT)
                        self.current.highlight_vertex(0, Shape.NEAR_VERTEX)

                    if self.draw_square:
                        init_pos = self.current[0]
                        min_x = init_pos.x()
                        min_y = init_pos.y()
                        min_size = min(abs(pos.x() - min_x), abs(pos.y() - min_y))
                        direction_x = -1 if pos.x() - min_x < 0 else 1
                        direction_y = -1 if pos.y() - min_y < 0 else 1
                        square_pos = QPointF(min_x + direction_x * min_size, min_y + direction_y * min_size)
                        self.line[1] = self.apply_snapping(square_pos)
                    else:
                        self.line[1] = self.apply_snapping(pos)

                    self.line.line_color = color
                    self.prev_point = QPointF()
                    self.current.highlight_clear()
            else:
                self.prev_point = pos
            self.repaint()
            return

        # Polygon copy moving.
        if Qt.RightButton & ev.buttons():
            if self.selected_shape_copy and self.prev_point:
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shape(self.selected_shape_copy, pos)
                self.repaint()
            elif self.selected_shape:
                self.selected_shape_copy = self.selected_shape.copy()
                self.repaint()
            return

        # Polygon/Vertex moving.
        if Qt.LeftButton & ev.buttons():
            if self.selected_vertex():
                self.bounded_move_vertex(pos)
                self.shapeMoved.emit()
                self.repaint()

                # Display annotation width and height while moving vertex
                rect = self.h_shape.bounding_rect()
                current_width = rect.width()
                current_height = rect.height()
                self.parent().window().label_coordinates.setText(
                        'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
            elif self.selected_shape and self.prev_point:
                self.override_cursor(CURSOR_MOVE)
                self.bounded_move_shape(self.selected_shape, pos)
                self.shapeMoved.emit()
                self.repaint()

                # Display annotation width and height while moving shape
                rect = self.selected_shape.bounding_rect()
                current_width = rect.width()
                current_height = rect.height()
                self.parent().window().label_coordinates.setText(
                        'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
            else:
                # pan
                delta = ev.pos() - self.pan_initial_pos
                self.scrollRequest.emit(delta.x(), Qt.Horizontal)
                self.scrollRequest.emit(delta.y(), Qt.Vertical)
                self.update()
            return

        # Just hovering over the canvas, 2 possibilities:
        # - Highlight shapes
        # - Highlight vertex
        # Update shape/vertex fill and tooltip value accordingly.
        self.setToolTip("Image")
        priority_list = self.shapes + ([self.selected_shape] if self.selected_shape else [])
        visible_shapes = [s for s in priority_list if self.isVisible(s)]

        # First pass: check for nearby vertices (these take priority)
        vertex_found = False
        for shape in reversed(visible_shapes):
            index = shape.nearest_vertex(pos, self.epsilon)
            if index is not None:
                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.h_vertex, self.h_shape = index, shape
                shape.highlight_vertex(index, shape.MOVE_VERTEX)
                self.override_cursor(CURSOR_POINT)
                self.setToolTip("Click & drag to move point")
                self.setStatusTip(self.toolTip())
                self.update()
                vertex_found = True
                break

        if not vertex_found:
            # Second pass: find smallest shape containing point (for nested box support)
            candidates = [s for s in visible_shapes if s.contains_point(pos)]
            if candidates:
                def shape_area(s):
                    rect = s.bounding_rect()
                    return rect.width() * rect.height()
                shape = min(candidates, key=shape_area)

                if self.selected_vertex():
                    self.h_shape.highlight_clear()
                self.h_vertex, self.h_shape = None, shape
                self.setToolTip(
                    "Click & drag to move shape '%s'" % shape.label)
                self.setStatusTip(self.toolTip())
                self.override_cursor(CURSOR_GRAB)
                self.update()

                # Display annotation width and height while hovering inside
                rect = self.h_shape.bounding_rect()
                current_width = rect.width()
                current_height = rect.height()
                self.parent().window().label_coordinates.setText(
                        'Width: %d, Height: %d / X: %d; Y: %d' % (current_width, current_height, pos.x(), pos.y()))
            else:  # Nothing found, clear highlights, reset state.
                if self.h_shape:
                    self.h_shape.highlight_clear()
                    self.update()
                self.h_vertex, self.h_shape = None, None
                self.override_cursor(CURSOR_DEFAULT)

    def _keypoint_at(self, pos):
        """Index of the placed keypoint within hover range of image-space pos.

        ``epsilon`` is a screen-pixel radius, so divide it by the current zoom
        to get an image-space threshold that stays constant on screen.
        """
        shape = self._keypoint_shape
        # NB: `not shape` would call Shape.__len__ (point count), so test None.
        if shape is None or not shape.keypoints:
            return -1
        threshold = (self.epsilon / 2) / max(self.scale, 1e-6)
        for i, kp in enumerate(shape.keypoints):
            if kp is not None and kp[2] > 0:
                if distance(QPointF(kp[0], kp[1]) - pos) < threshold:
                    return i
        return -1

    def mousePressEvent(self, ev):
        pos = self.transform_pos(ev.pos())

        # Snapshot polygon points before any potential vertex drag.
        # Emitted on release if any point actually changed.
        self._polygon_drag_old_points = None
        if (ev.button() == Qt.LeftButton
                and self.selected_shape
                and self.selected_shape.shape_type == ShapeType.POLYGON):
            self._polygon_drag_old_points = list(self.selected_shape.points)

        # Snapshot non-polygon (rectangle) points before a potential body
        # move or corner resize. Emitted as shapeMoveFinished on release if
        # the drag actually changed the geometry.
        self._move_shape_old_points = None
        if (ev.button() == Qt.LeftButton
                and self.selected_shape
                and self.selected_shape.shape_type != ShapeType.POLYGON):
            self._move_shape_old_points = [
                QPointF(p.x(), p.y()) for p in self.selected_shape.points]

        # Keypoint placement
        if self.mode == self.KEYPOINT_MODE and self._keypoint_shape:
            kp_count = self._keypoint_count()
            if ev.button() == Qt.LeftButton and self._keypoint_index < kp_count:
                if not self.out_of_pixmap(pos):
                    old_kps = (list(self._keypoint_shape.keypoints)
                               if self._keypoint_shape.keypoints else None)
                    if self._keypoint_shape.keypoints is None:
                        self._keypoint_shape.keypoints = [None] * kp_count
                    self._keypoint_shape.keypoints[self._keypoint_index] = (
                        pos.x(), pos.y(), 2)
                    self._emit_keypoints_edit(
                        self._keypoint_shape, old_kps)
                    self._keypoint_index = self._next_unplaced_keypoint(
                        self._keypoint_index + 1)
                    if self._keypoint_index >= kp_count:
                        self.exit_keypoint_mode()
                    self.shapeMoved.emit()
                    self.update()
                return
            elif ev.button() == Qt.RightButton and self._keypoint_index < kp_count:
                if not self.out_of_pixmap(pos):
                    old_kps = (list(self._keypoint_shape.keypoints)
                               if self._keypoint_shape.keypoints else None)
                    if self._keypoint_shape.keypoints is None:
                        self._keypoint_shape.keypoints = [None] * kp_count
                    self._keypoint_shape.keypoints[self._keypoint_index] = (
                        pos.x(), pos.y(), 1)
                    self._emit_keypoints_edit(
                        self._keypoint_shape, old_kps)
                    self._keypoint_index = self._next_unplaced_keypoint(
                        self._keypoint_index + 1)
                    if self._keypoint_index >= kp_count:
                        self.exit_keypoint_mode()
                    self.shapeMoved.emit()
                    self.update()
                return
            return

        if ev.button() == Qt.LeftButton and self._locked:
            return

        if ev.button() == Qt.LeftButton:
            if self.drawing():
                if self.mode == self.CREATE_POLYGON and ev.modifiers() & Qt.ShiftModifier:
                    # Start freehand drawing
                    if not self.out_of_pixmap(pos):
                        self._freehand_active = True
                        self._freehand_points = [pos]
                else:
                    self.handle_drawing(pos)
            else:
                # Check for midpoint click on selected polygon
                if self.selected_shape and self.selected_shape.shape_type == ShapeType.POLYGON:
                    mid_idx = self.selected_shape.nearest_midpoint(pos, self.epsilon)
                    if mid_idx is not None:
                        mid = self.selected_shape.midpoint_of_edge(mid_idx)
                        old_points = list(self.selected_shape.points)
                        self.selected_shape.insert_point(mid_idx + 1, mid)
                        self._emit_polygon_edit(
                            self.selected_shape, old_points)
                        # Reseat the drag baseline to the post-insert state so a
                        # subsequent drag-while-held emits a second edit covering
                        # only the move, not the insert (already emitted above).
                        self._polygon_drag_old_points = list(
                            self.selected_shape.points)
                        self.h_vertex = mid_idx + 1
                        self.h_shape = self.selected_shape
                        self.selected_shape.highlight_vertex(mid_idx + 1, Shape.MOVE_VERTEX)
                        self.update()
                        self.prev_point = pos
                        return

                selection = self.select_shape_point(pos)
                self.prev_point = pos

                if selection is None:
                    QApplication.setOverrideCursor(QCursor(Qt.OpenHandCursor))
                    self.pan_initial_pos = ev.pos()

        elif ev.button() == Qt.RightButton and self.editing():
            self.select_shape_point(pos)
            self.prev_point = pos
        self.update()

    def mouseReleaseEvent(self, ev):
        if self._freehand_active and ev.button() == Qt.LeftButton:
            self._freehand_active = False
            if len(self._freehand_points) >= 3:
                simplified = douglas_peucker(self._freehand_points, 2.0)
                if len(simplified) >= 3:
                    self.current = Shape(shape_type=ShapeType.POLYGON)
                    for pt in simplified:
                        snapped = self.apply_snapping(pt)
                        self.current.add_point(snapped)
                    self.finalise()
            self._freehand_points = []
            self._polygon_drag_old_points = None
            self._move_shape_old_points = None
            return

        # If a polygon was selected on press and any vertex moved during
        # the drag, emit polygonVerticesEdited so MainWindow can push an
        # undo command. Compares pre-press snapshot to current points.
        if (ev.button() == Qt.LeftButton
                and self._polygon_drag_old_points is not None
                and self.selected_shape
                and self.selected_shape.shape_type == ShapeType.POLYGON):
            new_pts = self.selected_shape.points
            old_pts = self._polygon_drag_old_points
            moved = (
                len(new_pts) != len(old_pts)
                or any((a.x(), a.y()) != (b.x(), b.y())
                       for a, b in zip(old_pts, new_pts))
            )
            if moved:
                self._emit_polygon_edit(self.selected_shape, old_pts)

        # Same for a non-polygon (rectangle) shape moved or resized during the
        # drag: emit shapeMoveFinished so MainWindow can push a MoveShapeCommand.
        if (ev.button() == Qt.LeftButton
                and self._move_shape_old_points is not None
                and self.selected_shape
                and self.selected_shape.shape_type != ShapeType.POLYGON):
            new_pts = self.selected_shape.points
            old_pts = self._move_shape_old_points
            moved = (
                len(new_pts) != len(old_pts)
                or any((a.x(), a.y()) != (b.x(), b.y())
                       for a, b in zip(old_pts, new_pts))
            )
            if moved:
                self.shapeMoveFinished.emit(self.selected_shape, old_pts)

        if ev.button() == Qt.LeftButton:
            self._polygon_drag_old_points = None
            self._move_shape_old_points = None

        if ev.button() == Qt.RightButton:
            # Check if right-clicking a polygon vertex
            if self.selected_shape and self.selected_shape.shape_type == ShapeType.POLYGON:
                pos = self.transform_pos(ev.pos())
                idx = self.selected_shape.nearest_vertex(pos, self.epsilon)
                if idx is not None:
                    vertex_menu = QMenu()
                    delete_action = vertex_menu.addAction("Delete Vertex")
                    if len(self.selected_shape.points) <= 3:
                        delete_action.setEnabled(False)
                    action = vertex_menu.exec_(self.mapToGlobal(ev.pos()))
                    if action == delete_action:
                        old_points = list(self.selected_shape.points)
                        self.selected_shape.remove_point(idx)
                        self._emit_polygon_edit(
                            self.selected_shape, old_points)
                        self.shapeMoved.emit()
                        self.update()
                    return

            menu = self.menus[bool(self.selected_shape_copy)]
            self.restore_cursor()
            if not menu.exec_(self.mapToGlobal(ev.pos()))\
               and self.selected_shape_copy:
                # Cancel the move by deleting the shadow copy.
                self.selected_shape_copy = None
                self.repaint()
        elif ev.button() == Qt.LeftButton and self.selected_shape:
            if self.selected_vertex():
                self.override_cursor(CURSOR_POINT)
            else:
                self.override_cursor(CURSOR_GRAB)
        elif ev.button() == Qt.LeftButton:
            pos = self.transform_pos(ev.pos())
            if self.drawing():
                self.handle_drawing(pos)
            else:
                # pan
                QApplication.restoreOverrideCursor()

    def end_move(self, copy=False):
        assert self.selected_shape and self.selected_shape_copy
        shape = self.selected_shape_copy
        # del shape.fill_color
        # del shape.line_color
        if copy:
            self.shapes.append(shape)
            self.selected_shape.selected = False
            self.selected_shape = shape
            self.repaint()
        else:
            # Snapshot before committing the dragged points so the
            # context-menu move is undoable (Issue #68).
            old_points = [QPointF(p.x(), p.y())
                          for p in self.selected_shape.points]
            self.selected_shape.points = [p for p in shape.points]
            new_points = self.selected_shape.points
            moved = (len(old_points) != len(new_points)
                     or any((a.x(), a.y()) != (b.x(), b.y())
                            for a, b in zip(old_points, new_points)))
            if moved:
                if self.selected_shape.shape_type == ShapeType.POLYGON:
                    self._emit_polygon_edit(self.selected_shape, old_points)
                else:
                    self.shapeMoveFinished.emit(self.selected_shape, old_points)
        self.selected_shape_copy = None

    def hide_background_shapes(self, value):
        self.hide_background = value
        if self.selected_shape:
            # Only hide other shapes if there is a current selection.
            # Otherwise the user will not be able to select a shape.
            self.set_hiding(True)
            self.repaint()

    def handle_drawing(self, pos):
        if self.mode == self.CREATE_POLYGON:
            self._handle_polygon_drawing(pos)
            return

        # Original rectangle drawing logic (unchanged)
        if self.current and self.current.reach_max_points() is False:
            init_pos = self.current[0]
            min_x = init_pos.x()
            min_y = init_pos.y()
            target_pos = self.line[1]
            max_x = target_pos.x()
            max_y = target_pos.y()
            self.current.add_point(QPointF(max_x, min_y))
            self.current.add_point(target_pos)
            self.current.add_point(QPointF(min_x, max_y))
            self.finalise()
        elif not self.out_of_pixmap(pos):
            snapped = self.apply_snapping(pos)
            self.current = Shape()
            self.current.add_point(snapped)
            self.line.points = [snapped, snapped]
            self.set_hiding()
            self.drawingPolygon.emit(True)
            self.update()

    def _handle_polygon_drawing(self, pos):
        """Handle click-to-place polygon vertex."""
        if self.out_of_pixmap(pos):
            return
        snapped = self.apply_snapping(pos)

        if self.current is None:
            # First vertex
            self.current = Shape(shape_type=ShapeType.POLYGON)
            self.current.add_point(snapped)
            self.line.points = [snapped, snapped]
            self.set_hiding()
            self.drawingPolygon.emit(True)
            self.update()
        elif self.close_enough(snapped, self.current[0]) and len(self.current) >= 3:
            # Close polygon — clicked near first vertex
            self.finalise()
        else:
            # Add vertex
            self.current.add_point(snapped)
            self.line.points = [snapped, snapped]
            self.update()

    def set_hiding(self, enable=True):
        self._hide_background = self.hide_background if enable else False

    def can_close_shape(self):
        return self.drawing() and self.current and len(self.current) > 2

    def mouseDoubleClickEvent(self, ev):
        if self._locked:
            return
        if self.mode == self.CREATE_POLYGON and self.current and len(self.current) >= 3:
            # Close polygon on double-click
            self.finalise()
        elif self.can_close_shape() and len(self.current) > 3:
            # We need at least 4 points here, since the mousePress handler
            # adds an extra one before this handler is called.
            self.current.pop_point()
            self.finalise()

    def select_shape(self, shape):
        self.de_select_shape()
        shape.selected = True
        self.selected_shape = shape
        self.set_hiding()
        self.selectionChanged.emit(True)
        self.update()

    def select_shape_point(self, point):
        """Select the smallest shape which contains this point."""
        self.de_select_shape()
        if self.selected_vertex():  # A vertex is marked for selection.
            index, shape = self.h_vertex, self.h_shape
            shape.highlight_vertex(index, shape.MOVE_VERTEX)
            self.select_shape(shape)
            return self.h_vertex

        # Find all shapes containing the point
        candidates = []
        for shape in self.shapes:
            if self.isVisible(shape) and shape.contains_point(point):
                candidates.append(shape)

        if candidates:
            # Select the smallest shape (by bounding rect area) for nested box support
            def shape_area(s):
                rect = s.bounding_rect()
                return rect.width() * rect.height()
            smallest = min(candidates, key=shape_area)
            self.select_shape(smallest)
            self.calculate_offsets(smallest, point)
            return self.selected_shape
        return None

    def calculate_offsets(self, shape, point):
        rect = shape.bounding_rect()
        x1 = rect.x() - point.x()
        y1 = rect.y() - point.y()
        x2 = (rect.x() + rect.width()) - point.x()
        y2 = (rect.y() + rect.height()) - point.y()
        self.offsets = QPointF(x1, y1), QPointF(x2, y2)

    def snap_point_to_canvas(self, x, y):
        """
        Moves a point x,y to within the boundaries of the canvas.
        :return: (x,y,snapped) where snapped is True if x or y were changed, False if not.
        """
        if x < 0 or x > self.pixmap.width() or y < 0 or y > self.pixmap.height():
            x = max(x, 0)
            y = max(y, 0)
            x = min(x, self.pixmap.width())
            y = min(y, self.pixmap.height())
            return x, y, True

        return x, y, False

    def snap_to_grid(self, pos):
        """Snap a point to the nearest grid intersection."""
        if not self._grid_enabled or self._grid_size <= 0:
            return pos
        gs = self._grid_size
        x = round(pos.x() / gs) * gs
        y = round(pos.y() / gs) * gs
        return QPointF(x, y)

    def snap_to_edges(self, pos, exclude_shape=None):
        """Snap point to nearby edges of existing shapes."""
        if not self._edge_alignment:
            return pos
        threshold = 5.0 / self.scale if self.scale else 5.0
        self._alignment_guides = []
        snapped_x, snapped_y = pos.x(), pos.y()

        for shape in self.shapes:
            if shape is exclude_shape:
                continue
            for point in shape.points:
                if abs(pos.x() - point.x()) < threshold:
                    snapped_x = point.x()
                    self._alignment_guides.append(('v', point.x()))
                if abs(pos.y() - point.y()) < threshold:
                    snapped_y = point.y()
                    self._alignment_guides.append(('h', point.y()))

        return QPointF(snapped_x, snapped_y)

    def apply_snapping(self, pos, exclude_shape=None):
        """Apply all active snapping modes to a position."""
        pos = self.snap_to_grid(pos)
        pos = self.snap_to_edges(pos, exclude_shape)
        return pos

    def bounded_move_vertex(self, pos):
        index, shape = self.h_vertex, self.h_shape
        point = shape[index]
        if self.out_of_pixmap(pos):
            size = self.pixmap.size()
            clipped_x = min(max(0, pos.x()), size.width())
            clipped_y = min(max(0, pos.y()), size.height())
            pos = QPointF(clipped_x, clipped_y)

        pos = self.apply_snapping(pos, exclude_shape=shape)

        if shape.shape_type == ShapeType.POLYGON:
            # Polygon: move vertex independently
            shift_pos = pos - point
            shape.move_vertex_by(index, shift_pos)
            return

        # Rectangle: existing constraint logic (unchanged)
        if self.draw_square:
            opposite_point_index = (index + 2) % 4
            opposite_point = shape[opposite_point_index]
            min_size = min(abs(pos.x() - opposite_point.x()),
                           abs(pos.y() - opposite_point.y()))
            direction_x = -1 if pos.x() - opposite_point.x() < 0 else 1
            direction_y = -1 if pos.y() - opposite_point.y() < 0 else 1
            shift_pos = QPointF(
                opposite_point.x() + direction_x * min_size - point.x(),
                opposite_point.y() + direction_y * min_size - point.y())
        else:
            shift_pos = pos - point

        shape.move_vertex_by(index, shift_pos)

        left_index = (index + 1) % 4
        right_index = (index + 3) % 4
        if index % 2 == 0:
            right_shift = QPointF(shift_pos.x(), 0)
            left_shift = QPointF(0, shift_pos.y())
        else:
            left_shift = QPointF(shift_pos.x(), 0)
            right_shift = QPointF(0, shift_pos.y())
        shape.move_vertex_by(right_index, right_shift)
        shape.move_vertex_by(left_index, left_shift)

    def bounded_move_shape(self, shape, pos):
        if self.out_of_pixmap(pos):
            return False  # No need to move
        o1 = pos + self.offsets[0]
        if self.out_of_pixmap(o1):
            pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
        o2 = pos + self.offsets[1]
        if self.out_of_pixmap(o2):
            pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                           min(0, self.pixmap.height() - o2.y()))
        # The next line tracks the new position of the cursor
        # relative to the shape, but also results in making it
        # a bit "shaky" when nearing the border and allows it to
        # go outside of the shape's area for some reason. XXX
        # self.calculateOffsets(self.selectedShape, pos)
        dp = pos - self.prev_point
        if dp:
            shape.move_by(dp)
            self.prev_point = pos
            return True
        return False

    def _emit_polygon_edit(self, shape, old_points):
        """Emit polygonVerticesEdited with a deep-copy snapshot of old_points."""
        snapshot = [QPointF(p.x(), p.y()) for p in old_points]
        self.polygonVerticesEdited.emit(shape, snapshot)

    def _emit_keypoints_edit(self, shape, old_keypoints):
        """Emit keypointsEdited with a deep-copy snapshot."""
        snapshot = list(old_keypoints) if old_keypoints else None
        self.keypointsEdited.emit(shape, snapshot)

    def de_select_shape(self):
        if self.selected_shape:
            self.selected_shape.selected = False
            self.selected_shape = None
            self.set_hiding(False)
            self.selectionChanged.emit(False)
            self.update()

    def delete_selected(self):
        if self.selected_shape:
            shape = self.selected_shape
            # If this shape is the active keypoint subject, exit keypoint mode
            # before removing — otherwise the next click crashes on a stale ref.
            if self._keypoint_shape is shape:
                self.exit_keypoint_mode()
            self.un_highlight(shape)
            self.shapes.remove(self.selected_shape)
            self.selected_shape = None
            self.update()
            return shape

    def copy_selected_shape(self):
        if self.selected_shape:
            shape = self.selected_shape.copy()
            self.de_select_shape()
            self.shapes.append(shape)
            shape.selected = True
            self.selected_shape = shape
            self.bounded_shift_shape(shape)
            return shape

    def bounded_shift_shape(self, shape):
        # Try to move in one direction, and if it fails in another.
        # Give up if both fail.
        point = shape[0]
        offset = QPointF(2.0, 2.0)
        self.calculate_offsets(shape, point)
        self.prev_point = point
        if not self.bounded_move_shape(shape, point - offset):
            self.bounded_move_shape(shape, point + offset)

    def _draw_polygon_midpoints(self, painter, shape):
        """Draw midpoint handles on polygon edges for the selected shape."""
        if shape.shape_type != ShapeType.POLYGON or not shape.selected:
            return
        from libs.utils.styles import get_theme_colors, hex_to_qcolor
        colors = get_theme_colors(self._theme)
        mid_color = hex_to_qcolor(colors.get('midpoint_handle', '#999999'))
        d = shape.point_size / shape.scale / 2
        for i in range(len(shape.points)):
            mid = shape.midpoint_of_edge(i)
            painter.fillRect(
                int(mid.x() - d/2), int(mid.y() - d/2),
                int(d), int(d), mid_color)

    def _draw_keypoints(self, painter, shape):
        """Draw keypoint dots and skeleton bones for a shape."""
        from libs.core.keypoint_config import get_keypoint_color, get_template
        from libs.utils.styles import hex_to_qcolor

        kps = shape.keypoints
        if not kps:
            return

        # Resolve template from shape label
        template = get_template(shape.label) if shape.label else None
        if not template:
            return
        template_name = shape.label.lower()
        skeleton = template['skeleton']
        names = template['names']

        dot_size = max(4, 8 / self.scale)

        # Draw skeleton bones first (under dots)
        for start_idx, end_idx in skeleton:
            if start_idx >= len(kps) or end_idx >= len(kps):
                continue
            kp_a = kps[start_idx]
            kp_b = kps[end_idx]
            if kp_a is None or kp_b is None:
                continue
            if kp_a[2] == 0 or kp_b[2] == 0:
                continue
            color = hex_to_qcolor(get_keypoint_color(start_idx, template_name))
            pen_style = Qt.DashLine if (kp_a[2] == 1 or kp_b[2] == 1) else Qt.SolidLine
            pen = QPen(color, max(1, int(2 / self.scale)), pen_style)
            painter.setPen(pen)
            painter.drawLine(
                QPointF(kp_a[0], kp_a[1]),
                QPointF(kp_b[0], kp_b[1]))

        # Draw keypoint dots
        for i, kp in enumerate(kps):
            if kp is None or kp[2] == 0:
                continue
            color = hex_to_qcolor(get_keypoint_color(i, template_name))
            x, y, v = kp
            if v == 2:
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.setBrush(color)
                painter.drawEllipse(QPointF(x, y), dot_size / 2, dot_size / 2)
            elif v == 1:
                pen = QPen(color, max(1, int(2 / self.scale)), Qt.DashLine)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(x, y), dot_size / 2, dot_size / 2)

        # Draw label on hovered keypoint
        if 0 <= self._hovered_keypoint < len(names):
            kp = kps[self._hovered_keypoint] if self._hovered_keypoint < len(kps) else None
            if kp is not None:
                name = names[self._hovered_keypoint]
                font = painter.font()
                font.setPointSize(max(6, int(8 / self.scale)))
                painter.setFont(font)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(int(kp[0] + dot_size), int(kp[1] - dot_size / 2),
                                 name.replace('_', ' '))

    def paintEvent(self, event):
        if not self.pixmap:
            return super(Canvas, self).paintEvent(event)

        p = self._painter
        p.begin(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.HighQualityAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        p.scale(self.scale, self.scale)
        p.translate(self.offset_to_center())

        p.drawPixmap(0, 0, self._composited_pixmap())
        Shape.scale = self.scale
        Shape.label_font_size = self.label_font_size
        for shape in self.shapes:
            if (shape.selected or not self._hide_background) and self.isVisible(shape):
                shape.fill = shape.selected or shape == self.h_shape
                shape.paint(p)
                if shape.selected:
                    self._draw_polygon_midpoints(p, shape)

        # Draw keypoints and skeleton for shapes that have them
        for shape in self.shapes:
            if shape.keypoints and self.isVisible(shape):
                self._draw_keypoints(p, shape)

        if self.current:
            self.current.paint(p)
            self.line.paint(p)
        if self.selected_shape_copy:
            self.selected_shape_copy.paint(p)

        # Paint rect / polygon preview
        if self.current is not None and len(self.line) == 2:
            if self.mode == self.CREATE_POLYGON:
                # Draw dotted line from cursor back to first vertex (close preview)
                if len(self.current) >= 2:
                    pen = QPen(self.drawing_line_color, 1, Qt.DashLine)
                    p.setPen(pen)
                    p.drawLine(self.line[1], self.current[0])
            else:
                # Rectangle preview
                left_top = self.line[0]
                right_bottom = self.line[1]
                rect_width = right_bottom.x() - left_top.x()
                rect_height = right_bottom.y() - left_top.y()
                p.setPen(self.drawing_rect_color)
                brush = QBrush(Qt.BDiagPattern)
                p.setBrush(brush)
                p.drawRect(int(left_top.x()), int(left_top.y()),
                           int(rect_width), int(rect_height))

        # Draw freehand path in progress
        if self._freehand_active and len(self._freehand_points) >= 2:
            pen = QPen(self.drawing_line_color, 2)
            p.setPen(pen)
            for i in range(len(self._freehand_points) - 1):
                p.drawLine(self._freehand_points[i], self._freehand_points[i + 1])

        # Draw grid overlay
        if self._grid_enabled and self.pixmap and self._grid_size > 0:
            from libs.utils.styles import get_theme_colors, hex_to_qcolor
            colors = get_theme_colors(getattr(self, '_theme', None))
            grid_color = hex_to_qcolor(colors.get('grid_line', '#cccccc'), alpha=80)
            p.setPen(grid_color)
            gs = self._grid_size
            w, h = self.pixmap.width(), self.pixmap.height()
            for x in range(0, w + 1, gs):
                p.drawLine(x, 0, x, h)
            for y in range(0, h + 1, gs):
                p.drawLine(0, y, w, y)

        # Draw alignment guides
        if self._alignment_guides:
            from libs.utils.styles import get_theme_colors, hex_to_qcolor
            colors = get_theme_colors(getattr(self, '_theme', None))
            guide_color = hex_to_qcolor(colors.get('alignment_guide', '#4da6ff'))
            pen = QPen(guide_color, 1, Qt.DashLine)
            p.setPen(pen)
            w, h = self.pixmap.width(), self.pixmap.height()
            for orientation, position in self._alignment_guides:
                if orientation == 'v':
                    p.drawLine(int(position), 0, int(position), h)
                else:
                    p.drawLine(0, int(position), w, int(position))
            self._alignment_guides = []

        if self.drawing() and not self.prev_point.isNull() and not self.out_of_pixmap(self.prev_point):
            p.setPen(self._crosshair_color)
            p.drawLine(int(self.prev_point.x()), 0, int(self.prev_point.x()), int(self.pixmap.height()))
            p.drawLine(0, int(self.prev_point.y()), int(self.pixmap.width()), int(self.prev_point.y()))

        self.setAutoFillBackground(True)
        pal = self.palette()
        if self.verified:
            pal.setColor(self.backgroundRole(), self._verified_bg_color)
        else:
            pal.setColor(self.backgroundRole(), self._theme_background)
        self.setPalette(pal)

        p.end()

    def transform_pos(self, point):
        """Convert from widget-logical coordinates to painter-logical coordinates."""
        return point / self.scale - self.offset_to_center()

    def offset_to_center(self):
        s = self.scale
        area = super(Canvas, self).size()
        w, h = self.pixmap.width() * s, self.pixmap.height() * s
        aw, ah = area.width(), area.height()
        x = (aw - w) / (2 * s) if aw > w else 0
        y = (ah - h) / (2 * s) if ah > h else 0
        return QPointF(x, y)

    def out_of_pixmap(self, p):
        w, h = self.pixmap.width(), self.pixmap.height()
        return not (0 <= p.x() <= w and 0 <= p.y() <= h)

    def finalise(self):
        assert self.current
        if self.current.points[0] == self.current.points[-1]:
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
            return

        self.current.close()
        self.shapes.append(self.current)
        self.current = None
        self.set_hiding(False)
        self.newShape.emit()
        self.update()

    def close_enough(self, p1, p2):
        return distance(p1 - p2) < self.epsilon

    # These two, along with a call to adjustSize are required for the
    # scroll area.
    def sizeHint(self):
        return self.minimumSizeHint()

    def minimumSizeHint(self):
        if self.pixmap:
            return self.scale * self.pixmap.size()
        return super(Canvas, self).minimumSizeHint()

    def wheelEvent(self, ev):
        qt_version = 4 if hasattr(ev, "delta") else 5
        if qt_version == 4:
            if ev.orientation() == Qt.Vertical:
                v_delta = ev.delta()
                h_delta = 0
            else:
                h_delta = ev.delta()
                v_delta = 0
        else:
            delta = ev.angleDelta()
            h_delta = delta.x()
            v_delta = delta.y()

        mods = ev.modifiers()
        if int(Qt.ControlModifier) | int(Qt.ShiftModifier) == int(mods) and v_delta:
            self.lightRequest.emit(v_delta)
        elif Qt.ControlModifier == int(mods) and v_delta:
            self.zoomRequest.emit(v_delta)
        else:
            v_delta and self.scrollRequest.emit(v_delta, Qt.Vertical)
            h_delta and self.scrollRequest.emit(h_delta, Qt.Horizontal)
        ev.accept()

    def keyPressEvent(self, ev):
        key = ev.key()
        mods = ev.modifiers()

        if key == Qt.Key_Escape and self.mode == self.KEYPOINT_MODE:
            kp_count = self._keypoint_count()
            if self._keypoint_index < kp_count:
                if self._keypoint_shape and self._keypoint_shape.keypoints is None:
                    self._keypoint_shape.keypoints = [None] * kp_count
                self._keypoint_index = self._next_unplaced_keypoint(
                    self._keypoint_index + 1)
                if self._keypoint_index >= kp_count:
                    self.exit_keypoint_mode()
                self.update()
            else:
                self.exit_keypoint_mode()
            return

        if (key == Qt.Key_Z and mods == Qt.ControlModifier
                and self.mode == self.KEYPOINT_MODE
                and self._keypoint_shape):
            kps = self._keypoint_shape.keypoints
            if kps:
                old_kps = list(kps)
                for i in range(self._keypoint_index - 1, -1, -1):
                    if kps[i] is not None:
                        kps[i] = None
                        self._keypoint_index = i
                        # Make the in-mode clear undoable (Issue #68).
                        self._emit_keypoints_edit(
                            self._keypoint_shape, old_kps)
                        break
            self.shapeMoved.emit()
            self.update()
            return

        if key == Qt.Key_Escape and self.current:
            self.current = None
            self.drawingPolygon.emit(False)
            self.update()
        elif key == Qt.Key_Return and self.can_close_shape():
            self.finalise()
        elif (key == Qt.Key_Z and mods == Qt.ControlModifier
              and self.mode == self.CREATE_POLYGON
              and self.current and len(self.current) > 1):
            # Undo last vertex during polygon drawing
            self.current.pop_point()
            self.line.points = [self.current[-1], self.line[1]]
            self.update()
        elif key == Qt.Key_Left and self.selected_shape:
            self.move_one_pixel('Left')
        elif key == Qt.Key_Right and self.selected_shape:
            self.move_one_pixel('Right')
        elif key == Qt.Key_Up and self.selected_shape:
            self.move_one_pixel('Up')
        elif key == Qt.Key_Down and self.selected_shape:
            self.move_one_pixel('Down')

    def move_one_pixel(self, direction):
        offsets = {
            'Left': QPointF(-1.0, 0),
            'Right': QPointF(1.0, 0),
            'Up': QPointF(0, -1.0),
            'Down': QPointF(0, 1.0),
        }
        step = offsets.get(direction)
        if step and not self.move_out_of_bound(step):
            # Snapshot before mutating so the nudge is undoable (Issue #68).
            old_points = [QPointF(p.x(), p.y())
                          for p in self.selected_shape.points]
            for i in range(len(self.selected_shape.points)):
                self.selected_shape.points[i] += step
            if self.selected_shape.shape_type == ShapeType.POLYGON:
                self._emit_polygon_edit(self.selected_shape, old_points)
            else:
                self.shapeMoveFinished.emit(self.selected_shape, old_points)
        self.shapeMoved.emit()
        self.repaint()

    def move_out_of_bound(self, step):
        points = [p + step for p in self.selected_shape.points]
        return any(self.out_of_pixmap(p) for p in points)

    def set_last_label(self, text, line_color=None):
        assert text
        self.shapes[-1].label = text
        if line_color:
            self.shapes[-1].line_color = line_color
        return self.shapes[-1]

    def undo_last_line(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.set_open()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)

    def reset_all_lines(self):
        assert self.shapes
        self.current = self.shapes.pop()
        self.current.set_open()
        self.line.points = [self.current[-1], self.current[0]]
        self.drawingPolygon.emit(True)
        self.current = None
        self.drawingPolygon.emit(False)
        self.update()

    def _composited_pixmap(self):
        """Return the pixmap with overlay_color composited on top.

        The result is cached and only rebuilt when the pixmap content
        (``cacheKey``) or the overlay color changes, so a full-resolution
        copy + composite does not happen on every repaint.
        """
        if not self.overlay_color or self.pixmap is None:
            return self.pixmap
        key = (self.pixmap.cacheKey(), self.overlay_color.rgba())
        if self._overlay_cache_key != key:
            composited = QPixmap(self.pixmap)
            painter = QPainter(composited)
            painter.setCompositionMode(QPainter.CompositionMode_Overlay)
            painter.fillRect(composited.rect(), self.overlay_color)
            painter.end()
            self._overlay_cache = composited
            self._overlay_cache_key = key
        return self._overlay_cache

    def load_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.shapes = []
        self.repaint()

    def load_shapes(self, shapes):
        self.shapes = list(shapes)
        self.current = None
        self.repaint()

    def set_shape_visible(self, shape, value):
        self.visible[shape] = value
        self.repaint()

    def current_cursor(self):
        cursor = QApplication.overrideCursor()
        if cursor is not None:
            cursor = cursor.shape()
        return cursor

    def override_cursor(self, cursor):
        self._cursor = cursor
        if self.current_cursor() is None:
            QApplication.setOverrideCursor(cursor)
        else:
            QApplication.changeOverrideCursor(cursor)

    def restore_cursor(self):
        QApplication.restoreOverrideCursor()

    def reset_state(self):
        self.de_select_shape()
        self.un_highlight()
        self.selected_shape_copy = None

        # Clear per-file drawing/keypoint state to avoid stale references.
        self._keypoint_shape = None
        self._keypoint_index = 0
        self._keypoint_template = None
        self._freehand_active = False
        self._freehand_points = []
        self.current = None
        self.mode = self.EDIT

        self.restore_cursor()
        self.pixmap = None
        self.update()

    def set_drawing_shape_to_square(self, status):
        self.draw_square = status
