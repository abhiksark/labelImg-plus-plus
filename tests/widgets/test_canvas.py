"""Tests for Canvas widget."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
sys.path.insert(0, os.path.join(dir_name, '..', '..', 'libs'))

from PyQt6.QtCore import QPointF, QPoint, Qt, QEvent
from PyQt6.QtGui import QPixmap, QColor, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication

from libs.widgets.canvas import (
    Canvas, CURSOR_DEFAULT, CURSOR_DRAW, CURSOR_GRAB)
from libs.core.shape import Shape, ShapeType

# Create QApplication for tests
app = QApplication.instance() or QApplication(sys.argv)


class TestCanvasInit(unittest.TestCase):
    """Test cases for Canvas initialization."""

    def test_default_init(self):
        """Test default Canvas initialization."""
        canvas = Canvas()

        self.assertEqual(canvas.mode, Canvas.EDIT)
        self.assertEqual(canvas.shapes, [])
        self.assertIsNone(canvas.current)
        self.assertIsNone(canvas.selected_shape)
        self.assertEqual(canvas.scale, 1.0)
        self.assertFalse(canvas.verified)
        self.assertFalse(canvas.draw_square)

    def test_initial_mode_is_edit(self):
        """Test that initial mode is EDIT."""
        canvas = Canvas()

        self.assertTrue(canvas.editing())
        self.assertFalse(canvas.drawing())


class TestCanvasMode(unittest.TestCase):
    """Test cases for Canvas mode switching."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def test_set_editing_true(self):
        """Test setting editing mode."""
        self.canvas.set_editing(True)

        self.assertTrue(self.canvas.editing())
        self.assertFalse(self.canvas.drawing())

    def test_set_editing_false(self):
        """Test setting drawing mode."""
        self.canvas.set_editing(False)

        self.assertFalse(self.canvas.editing())
        self.assertTrue(self.canvas.drawing())

    def test_mode_constants(self):
        """Test mode constants."""
        # CREATE=0, EDIT=1 from list(range(2))
        self.assertEqual(Canvas.CREATE, 0)
        self.assertEqual(Canvas.EDIT, 1)


class TestCanvasShapes(unittest.TestCase):
    """Test cases for Canvas shape management."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def _create_shape(self, label='test'):
        """Helper to create a test shape."""
        shape = Shape(label=label)
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))
        shape.close()
        return shape

    def test_add_shape(self):
        """Test adding shape to canvas."""
        shape = self._create_shape()
        self.canvas.shapes.append(shape)

        self.assertEqual(len(self.canvas.shapes), 1)
        self.assertIn(shape, self.canvas.shapes)

    def test_remove_shape(self):
        """Test removing shape from canvas."""
        shape = self._create_shape()
        self.canvas.shapes.append(shape)
        self.canvas.shapes.remove(shape)

        self.assertEqual(len(self.canvas.shapes), 0)

    def test_multiple_shapes(self):
        """Test adding multiple shapes."""
        shape1 = self._create_shape('shape1')
        shape2 = self._create_shape('shape2')
        shape3 = self._create_shape('shape3')

        self.canvas.shapes.extend([shape1, shape2, shape3])

        self.assertEqual(len(self.canvas.shapes), 3)


class TestCanvasVisibility(unittest.TestCase):
    """Test cases for Canvas shape visibility."""

    def setUp(self):
        """Create canvas and shape for each test."""
        self.canvas = Canvas()
        self.shape = Shape(label='test')
        self.shape.add_point(QPointF(0, 0))
        self.shape.add_point(QPointF(100, 100))
        self.canvas.shapes.append(self.shape)

    def test_default_visibility(self):
        """Test that shapes are visible by default."""
        self.assertTrue(self.canvas.isVisible(self.shape))

    def test_hide_shape(self):
        """Test hiding a shape."""
        self.canvas.visible[self.shape] = False

        self.assertFalse(self.canvas.isVisible(self.shape))

    def test_show_hidden_shape(self):
        """Test showing a hidden shape."""
        self.canvas.visible[self.shape] = False
        self.canvas.visible[self.shape] = True

        self.assertTrue(self.canvas.isVisible(self.shape))


class TestCanvasHighlight(unittest.TestCase):
    """Test cases for Canvas highlight management."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()
        self.shape = Shape(label='test')
        self.shape.add_point(QPointF(0, 0))
        self.shape.add_point(QPointF(100, 100))
        self.canvas.shapes.append(self.shape)

    def test_initial_no_highlight(self):
        """Test that initially nothing is highlighted."""
        self.assertIsNone(self.canvas.h_shape)
        self.assertIsNone(self.canvas.h_vertex)

    def test_un_highlight(self):
        """Test un_highlight clears highlight state."""
        self.canvas.h_shape = self.shape
        self.canvas.h_vertex = 0

        self.canvas.un_highlight()

        self.assertIsNone(self.canvas.h_shape)
        self.assertIsNone(self.canvas.h_vertex)

    def test_selected_vertex(self):
        """Test selected_vertex detection."""
        self.assertFalse(self.canvas.selected_vertex())

        self.canvas.h_vertex = 0

        self.assertTrue(self.canvas.selected_vertex())


class TestCanvasDrawingColor(unittest.TestCase):
    """Test cases for Canvas drawing color."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def test_set_drawing_color(self):
        """Test setting drawing color."""
        color = QColor(255, 0, 0)
        self.canvas.set_drawing_color(color)

        self.assertEqual(self.canvas.drawing_line_color, color)
        self.assertEqual(self.canvas.drawing_rect_color, color)


class TestCanvasSelection(unittest.TestCase):
    """Test cases for Canvas shape selection."""

    def setUp(self):
        """Create canvas and shapes for each test."""
        self.canvas = Canvas()
        self.shape1 = Shape(label='shape1')
        self.shape1.add_point(QPointF(0, 0))
        self.shape1.add_point(QPointF(50, 0))
        self.shape1.add_point(QPointF(50, 50))
        self.shape1.add_point(QPointF(0, 50))
        self.shape1.close()

        self.shape2 = Shape(label='shape2')
        self.shape2.add_point(QPointF(100, 100))
        self.shape2.add_point(QPointF(150, 100))
        self.shape2.add_point(QPointF(150, 150))
        self.shape2.add_point(QPointF(100, 150))
        self.shape2.close()

        self.canvas.shapes.extend([self.shape1, self.shape2])

    def test_initial_no_selection(self):
        """Test that initially no shape is selected."""
        self.assertIsNone(self.canvas.selected_shape)

    def test_select_shape(self):
        """Test selecting a shape."""
        self.canvas.selected_shape = self.shape1

        self.assertEqual(self.canvas.selected_shape, self.shape1)

    def test_deselect_shape(self):
        """Test deselecting a shape."""
        self.canvas.selected_shape = self.shape1
        self.canvas.de_select_shape()

        self.assertIsNone(self.canvas.selected_shape)


class TestCanvasPixmap(unittest.TestCase):
    """Test cases for Canvas pixmap handling."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def test_initial_pixmap_null(self):
        """Test that initial pixmap is null."""
        self.assertTrue(self.canvas.pixmap.isNull())

    def test_load_pixmap(self):
        """Test loading a pixmap."""
        pixmap = QPixmap(100, 100)
        pixmap.fill(QColor(255, 255, 255))
        self.canvas.load_pixmap(pixmap)

        self.assertFalse(self.canvas.pixmap.isNull())
        self.assertEqual(self.canvas.pixmap.width(), 100)
        self.assertEqual(self.canvas.pixmap.height(), 100)

    def test_out_of_pixmap_no_pixmap(self):
        """Test out_of_pixmap when no pixmap loaded."""
        # With null pixmap, any point is "out of pixmap"
        result = self.canvas.out_of_pixmap(QPointF(50, 50))
        self.assertTrue(result)

    def test_out_of_pixmap_inside(self):
        """Test out_of_pixmap for point inside."""
        pixmap = QPixmap(100, 100)
        self.canvas.load_pixmap(pixmap)

        result = self.canvas.out_of_pixmap(QPointF(50, 50))
        self.assertFalse(result)

    def test_out_of_pixmap_outside(self):
        """Test out_of_pixmap for point outside."""
        pixmap = QPixmap(100, 100)
        self.canvas.load_pixmap(pixmap)

        result = self.canvas.out_of_pixmap(QPointF(150, 150))
        self.assertTrue(result)

    def test_out_of_pixmap_negative(self):
        """Test out_of_pixmap for negative coordinates."""
        pixmap = QPixmap(100, 100)
        self.canvas.load_pixmap(pixmap)

        result = self.canvas.out_of_pixmap(QPointF(-10, -10))
        self.assertTrue(result)


class TestCanvasTransform(unittest.TestCase):
    """Test cases for Canvas coordinate transformation."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()
        # Load a pixmap so transforms work
        pixmap = QPixmap(200, 200)
        self.canvas.load_pixmap(pixmap)

    def test_transform_pos_returns_point(self):
        """Test transform_pos returns a QPointF."""
        self.canvas.scale = 1.0
        pos = QPoint(50, 50)

        result = self.canvas.transform_pos(pos)

        self.assertIsInstance(result, QPointF)

    def test_transform_pos_scale_affects_result(self):
        """Test that scale affects transform_pos result."""
        pos = QPoint(100, 100)

        self.canvas.scale = 1.0
        result1 = self.canvas.transform_pos(pos)

        self.canvas.scale = 2.0
        result2 = self.canvas.transform_pos(pos)

        # Results should differ when scale differs
        # (exact values depend on widget geometry)


class TestCanvasScale(unittest.TestCase):
    """Test cases for Canvas scale property."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def test_default_scale(self):
        """Test default scale is 1.0."""
        self.assertEqual(self.canvas.scale, 1.0)

    def test_set_scale(self):
        """Test setting scale."""
        self.canvas.scale = 2.5

        self.assertEqual(self.canvas.scale, 2.5)


class TestCanvasVerified(unittest.TestCase):
    """Test cases for Canvas verified flag."""

    def setUp(self):
        """Create canvas for each test."""
        self.canvas = Canvas()

    def test_default_not_verified(self):
        """Test default verified is False."""
        self.assertFalse(self.canvas.verified)

    def test_set_verified(self):
        """Test setting verified flag."""
        self.canvas.verified = True

        self.assertTrue(self.canvas.verified)


class TestCanvasResetState(unittest.TestCase):
    """Test cases for Canvas.reset_state clearing per-file drawing state."""

    def test_reset_state_clears_keypoint_and_freehand_state(self):
        """reset_state must clear all per-file drawing state."""
        canvas = Canvas()
        shape = Shape(label='person', shape_type=ShapeType.RECTANGLE)
        canvas._keypoint_shape = shape
        canvas._keypoint_index = 3
        canvas._freehand_active = True
        canvas._freehand_points = [object(), object()]
        canvas.current = Shape(shape_type=ShapeType.POLYGON)
        canvas.mode = Canvas.KEYPOINT_MODE

        canvas.reset_state()

        self.assertIsNone(canvas._keypoint_shape)
        self.assertEqual(canvas._keypoint_index, 0)
        self.assertFalse(canvas._freehand_active)
        self.assertEqual(canvas._freehand_points, [])
        self.assertIsNone(canvas.current)
        self.assertEqual(canvas.mode, Canvas.EDIT)


class TestCanvasDeleteSelected(unittest.TestCase):
    """Test cases for Canvas.delete_selected interacting with keypoint mode."""

    def _make_rect_shape(self, label='person'):
        """Create a rectangle shape with corner points (Shape.__len__ returns
        len(points), so a point-less Shape is falsy and short-circuits
        delete_selected's `if self.selected_shape:` guard)."""
        shape = Shape(label=label, shape_type=ShapeType.RECTANGLE)
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))
        shape.close()
        return shape

    def test_delete_selected_exits_keypoint_mode_when_subject_deleted(self):
        """Deleting the active keypoint shape must exit keypoint mode safely."""
        canvas = Canvas()
        shape = self._make_rect_shape('person')
        canvas.shapes = [shape]
        canvas.selected_shape = shape
        shape.selected = True
        canvas._keypoint_shape = shape
        canvas._keypoint_index = 2
        canvas.mode = canvas.KEYPOINT_MODE

        canvas.delete_selected()

        self.assertIsNone(canvas._keypoint_shape)
        self.assertEqual(canvas._keypoint_index, 0)
        self.assertEqual(canvas.mode, canvas.EDIT)

    def test_delete_selected_preserves_keypoint_mode_for_other_shape(self):
        """Deleting a non-subject shape must NOT exit keypoint mode."""
        canvas = Canvas()
        subject = self._make_rect_shape('person')
        other = self._make_rect_shape('other')
        canvas.shapes = [subject, other]
        canvas.selected_shape = other
        other.selected = True
        canvas._keypoint_shape = subject
        canvas._keypoint_index = 2
        canvas.mode = canvas.KEYPOINT_MODE

        canvas.delete_selected()

        self.assertIs(canvas._keypoint_shape, subject)
        self.assertEqual(canvas._keypoint_index, 2)
        self.assertEqual(canvas.mode, canvas.KEYPOINT_MODE)


class TestCanvasEditSignals(unittest.TestCase):
    """Tests for polygonVerticesEdited / keypointsEdited signal emission."""

    def test_emit_polygon_edit_emits_with_snapshot(self):
        """_emit_polygon_edit emits a deep-copy snapshot of old_points."""
        canvas = Canvas()
        shape = Shape(shape_type=ShapeType.POLYGON)
        old_points = [QPointF(0, 0), QPointF(10, 0), QPointF(10, 10)]

        received = []

        def handler(emitted_shape, emitted_points):
            received.append((emitted_shape, emitted_points))

        canvas.polygonVerticesEdited.connect(handler)
        canvas._emit_polygon_edit(shape, old_points)

        self.assertEqual(len(received), 1)
        emitted_shape, emitted_points = received[0]
        self.assertIs(emitted_shape, shape)
        self.assertEqual(
            [(p.x(), p.y()) for p in emitted_points],
            [(p.x(), p.y()) for p in old_points],
        )
        # Verify snapshot is a deep copy: mutating the original should
        # not affect the emitted list.
        old_points[0].setX(999)
        self.assertEqual(emitted_points[0].x(), 0)

    def test_emit_keypoints_edit_emits_with_snapshot(self):
        """_emit_keypoints_edit emits a copy of the old keypoints list."""
        canvas = Canvas()
        shape = Shape(label='person', shape_type=ShapeType.RECTANGLE)
        old_keypoints = [(1.0, 2.0, 2), None, (5.0, 6.0, 1)]

        received = []

        def handler(emitted_shape, emitted_kps):
            received.append((emitted_shape, emitted_kps))

        canvas.keypointsEdited.connect(handler)
        canvas._emit_keypoints_edit(shape, old_keypoints)

        self.assertEqual(len(received), 1)
        emitted_shape, emitted_kps = received[0]
        self.assertIs(emitted_shape, shape)
        self.assertEqual(emitted_kps, old_keypoints)
        # Snapshot must not alias the original list.
        old_keypoints.append((9.0, 9.0, 2))
        self.assertEqual(len(emitted_kps), 3)

    def test_emit_keypoints_edit_with_none(self):
        """_emit_keypoints_edit handles None old keypoints (first placement)."""
        canvas = Canvas()
        shape = Shape(label='person', shape_type=ShapeType.RECTANGLE)

        received = []
        canvas.keypointsEdited.connect(
            lambda s, kps: received.append((s, kps)))

        canvas._emit_keypoints_edit(shape, None)

        self.assertEqual(len(received), 1)
        self.assertIs(received[0][0], shape)
        self.assertIsNone(received[0][1])


class TestCanvasUndoGaps(unittest.TestCase):
    """Issue #68: mutation paths that previously bypassed the UndoStack must
    now emit the matching edit signal so MainWindow can push a command."""

    def _polygon(self, pts):
        shape = Shape(shape_type=ShapeType.POLYGON)
        for x, y in pts:
            shape.add_point(QPointF(x, y))
        return shape

    def _rectangle(self, pts):
        shape = Shape(shape_type=ShapeType.RECTANGLE)
        for x, y in pts:
            shape.add_point(QPointF(x, y))
        return shape

    # --- move_one_pixel (arrow-key nudge) ---

    def test_move_one_pixel_polygon_emits_polygon_edit(self):
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(100, 100))
        shape = self._polygon([(10, 10), (20, 10), (20, 20)])
        canvas.shapes = [shape]
        canvas.selected_shape = shape

        received = []
        canvas.polygonVerticesEdited.connect(
            lambda s, pts: received.append((s, pts)))

        canvas.move_one_pixel('Right')

        self.assertEqual(len(received), 1)
        emitted_shape, old_points = received[0]
        self.assertIs(emitted_shape, shape)
        # Snapshot must hold the PRE-move positions.
        self.assertEqual([(p.x(), p.y()) for p in old_points],
                         [(10, 10), (20, 10), (20, 20)])
        # And the shape actually moved right by 1px.
        self.assertEqual(shape.points[0].x(), 11)

    def test_move_one_pixel_rectangle_emits_move_finished(self):
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(100, 100))
        shape = self._rectangle([(10, 10), (20, 20)])
        canvas.shapes = [shape]
        canvas.selected_shape = shape

        received = []
        canvas.shapeMoveFinished.connect(
            lambda s, pts: received.append((s, pts)))

        canvas.move_one_pixel('Down')

        self.assertEqual(len(received), 1)
        emitted_shape, old_points = received[0]
        self.assertIs(emitted_shape, shape)
        self.assertEqual([(p.x(), p.y()) for p in old_points],
                         [(10, 10), (20, 20)])
        self.assertEqual(shape.points[0].y(), 11)

    def test_move_one_pixel_out_of_bounds_emits_nothing(self):
        """A nudge that would leave the pixmap is a no-op: no mutation, no
        signal (otherwise Ctrl-Z would undo the wrong action)."""
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(100, 100))
        shape = self._polygon([(0, 10), (5, 10), (5, 20)])  # x=0 at left edge
        canvas.shapes = [shape]
        canvas.selected_shape = shape

        received = []
        canvas.polygonVerticesEdited.connect(
            lambda s, pts: received.append(1))

        canvas.move_one_pixel('Left')  # would push x to -1

        self.assertEqual(received, [])
        self.assertEqual(shape.points[0].x(), 0)  # unchanged

    # --- end_move (context-menu "Move here") ---

    def test_end_move_polygon_emits_polygon_edit(self):
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(100, 100))
        shape = self._polygon([(10, 10), (20, 10), (20, 20)])
        canvas.selected_shape = shape
        moved_copy = shape.copy()
        for p in moved_copy.points:
            p.setX(p.x() + 5)
        canvas.selected_shape_copy = moved_copy

        received = []
        canvas.polygonVerticesEdited.connect(
            lambda s, pts: received.append((s, pts)))

        canvas.end_move(copy=False)

        self.assertEqual(len(received), 1)
        emitted_shape, old_points = received[0]
        self.assertIs(emitted_shape, shape)
        self.assertEqual([(p.x(), p.y()) for p in old_points],
                         [(10, 10), (20, 10), (20, 20)])
        # Points were committed from the dragged copy.
        self.assertEqual(shape.points[0].x(), 15)

    def test_end_move_copy_true_does_not_emit_move_signal(self):
        """The duplicate ('Move copy here') branch creates a shape; it must
        not masquerade as a move edit."""
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(100, 100))
        shape = self._polygon([(10, 10), (20, 10), (20, 20)])
        canvas.shapes = [shape]
        canvas.selected_shape = shape
        canvas.selected_shape_copy = shape.copy()

        received = []
        canvas.polygonVerticesEdited.connect(lambda s, pts: received.append(1))
        canvas.shapeMoveFinished.connect(lambda s, pts: received.append(1))

        canvas.end_move(copy=True)

        self.assertEqual(received, [])

    # --- in-mode keypoint Ctrl-Z ---

    def test_keypoint_ctrl_z_emits_keypoints_edit(self):
        canvas = Canvas()
        # A real keypoint shape carries bounding points (Shape truthiness is
        # point-count based), so give it some.
        shape = self._rectangle([(0, 0), (50, 50)])
        shape.label = 'person'
        shape.keypoints = [(1.0, 2.0, 2), (3.0, 4.0, 2), None]
        canvas.mode = canvas.KEYPOINT_MODE
        canvas._keypoint_shape = shape
        canvas._keypoint_index = 2  # two placed, third unplaced

        received = []
        canvas.keypointsEdited.connect(
            lambda s, kps: received.append((s, kps)))

        ctrl_z = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        canvas.keyPressEvent(ctrl_z)

        self.assertEqual(len(received), 1)
        emitted_shape, old_kps = received[0]
        self.assertIs(emitted_shape, shape)
        # Snapshot holds the PRE-clear keypoints.
        self.assertEqual(old_kps, [(1.0, 2.0, 2), (3.0, 4.0, 2), None])
        # The last placed keypoint was cleared.
        self.assertIsNone(shape.keypoints[1])
        self.assertEqual(canvas._keypoint_index, 1)

    def test_keypoint_ctrl_z_with_no_placed_points_emits_nothing(self):
        canvas = Canvas()
        shape = self._rectangle([(0, 0), (50, 50)])
        shape.label = 'person'
        shape.keypoints = [None, None]
        canvas.mode = canvas.KEYPOINT_MODE
        canvas._keypoint_shape = shape
        canvas._keypoint_index = 0

        received = []
        canvas.keypointsEdited.connect(lambda s, kps: received.append(1))

        ctrl_z = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        canvas.keyPressEvent(ctrl_z)

        self.assertEqual(received, [])


class TestOverlayPixmapCache(unittest.TestCase):
    """The overlay composite must be cached, not rebuilt every paint."""

    def test_overlay_pixmap_cached_until_inputs_change(self):
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(50, 50))
        canvas.overlay_color = QColor(255, 0, 0, 128)

        first = canvas._composited_pixmap()
        again = canvas._composited_pixmap()
        self.assertIs(again, first)  # reused, not recomposited

        canvas.overlay_color = QColor(0, 255, 0, 128)
        self.assertIsNot(canvas._composited_pixmap(), first)  # rebuilt

    def test_no_overlay_returns_base_pixmap(self):
        canvas = Canvas()
        canvas.load_pixmap(QPixmap(10, 10))
        canvas.overlay_color = None
        self.assertIs(canvas._composited_pixmap(), canvas.pixmap)


class TestKeypointHitTest(unittest.TestCase):
    """Keypoint hover hit-test must scale with zoom (screen-space radius)."""

    def _canvas_with_keypoint(self):
        canvas = Canvas()
        shape = Shape(shape_type=ShapeType.POLYGON)
        shape.keypoints = [(100.0, 100.0, 2)]
        canvas._keypoint_shape = shape
        return canvas

    def test_hit_within_threshold_at_unit_scale(self):
        canvas = self._canvas_with_keypoint()
        canvas.scale = 1.0  # threshold = epsilon/2 = 12 image px
        self.assertEqual(canvas._keypoint_at(QPointF(108, 100)), 0)  # 8 < 12

    def test_threshold_shrinks_when_zoomed_in(self):
        canvas = self._canvas_with_keypoint()
        canvas.scale = 4.0  # threshold = 12 / 4 = 3 image px
        self.assertEqual(canvas._keypoint_at(QPointF(108, 100)), -1)  # 8 > 3
        self.assertEqual(canvas._keypoint_at(QPointF(101, 100)), 0)   # 1 < 3


class _DrawFirstBase(unittest.TestCase):
    """Shared fixture for the EDIT-mode drag-to-draw gesture.

    The canvas is sized to the pixmap so offset_to_center() is zero and
    widget coordinates equal image coordinates, which keeps the geometry
    assertions readable.
    """

    def setUp(self):
        self.canvas = Canvas()
        self.canvas.load_pixmap(QPixmap(200, 200))
        self.canvas.resize(200, 200)
        self.canvas.scale = 1.0
        self.log = []
        self.canvas.drawingPolygon.connect(
            lambda v: self.log.append(('poly', v)))
        self.canvas.newShape.connect(lambda: self.log.append(('new',)))
        self.modes = []
        self.canvas.modeChanged.connect(self.modes.append)

    @staticmethod
    def _mouse(kind, x, y, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton):
        return QMouseEvent(
            kind, QPointF(x, y), button, buttons, Qt.KeyboardModifier.NoModifier)

    def _drag(self, x0, y0, x1, y1, button=Qt.MouseButton.LeftButton):
        held = button
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, x0, y0, button, held))
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, x1, y1, Qt.MouseButton.NoButton, held))
        self.canvas.mouseReleaseEvent(
            self._mouse(
                QEvent.Type.MouseButtonRelease, x1, y1, button, Qt.MouseButton.NoButton))

    def _corners(self):
        shape = self.canvas.provisional_shape
        return None if shape is None else [
            (p.x(), p.y()) for p in shape.points]


class TestEditDragDraw(_DrawFirstBase):
    """A left-drag on empty pixels draws a rectangle without leaving EDIT."""

    def test_drag_emits_the_create_mode_signal_sequence(self):
        self._drag(20, 20, 60, 50)

        # Ordering matters: MainWindow.new_shape reads provisional_shape on
        # newShape, and toggle_drawing_sensitive restores the cursor on the
        # drawingPolygon(False) that must precede it.
        self.assertEqual(
            self.log, [('poly', True), ('poly', False), ('new',)])
        self.assertEqual(
            self._corners(),
            [(20.0, 20.0), (60.0, 20.0), (60.0, 50.0), (20.0, 50.0)])
        self.assertEqual(self.canvas.shapes, [])

    def test_drag_never_changes_mode(self):
        seen = []
        self.canvas.drawingPolygon.connect(
            lambda _v: seen.append(self.canvas.mode))

        self._drag(20, 20, 60, 50)

        self.assertEqual(seen, [Canvas.EDIT, Canvas.EDIT])
        self.assertEqual(self.modes, [])
        self.assertEqual(self.canvas.mode, Canvas.EDIT)

    def test_sub_threshold_click_draws_nothing(self):
        self._drag(20, 20, 21, 21)

        self.assertEqual(self.log, [])
        self.assertIsNone(self.canvas.provisional_shape)
        self.assertIsNone(self.canvas._edit_draw_origin)

    def test_threshold_is_start_drag_distance(self):
        threshold = QApplication.startDragDistance()
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 20, 20))

        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 20 + threshold - 1, 20,
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
        self.assertIsNone(self.canvas.current)

        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 20 + threshold, 20,
                        Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
        self.assertIsNotNone(self.canvas.current)
        self.assertEqual(len(self.canvas.current), 1)

    def test_drag_starting_outside_the_pixmap_draws_nothing(self):
        # Pixmap 200x200 inside a 400x400 widget: (5, 5) is letterbox.
        self.canvas.resize(400, 400)

        self._drag(5, 5, 60, 60)

        self.assertEqual(self.log, [])
        self.assertIsNone(self.canvas._edit_draw_origin)

    def test_drag_on_a_shape_body_moves_it_instead(self):
        shape = Shape(label='box')
        for point in [(10, 10), (80, 10), (80, 80), (10, 80)]:
            shape.add_point(QPointF(*point))
        shape.close()
        self.canvas.load_shapes([shape])

        self._drag(40, 40, 70, 70)

        self.assertEqual(self.log, [])
        self.assertIsNone(self.canvas.provisional_shape)
        self.assertNotEqual(
            [(p.x(), p.y()) for p in shape.points][0], (10.0, 10.0))

    def test_pending_provisional_shape_blocks_a_new_drag(self):
        self._drag(20, 20, 60, 50)
        self.log.clear()

        self._drag(90, 90, 140, 140)

        self.assertEqual(self.log, [])

    def test_draw_square_applies_during_an_edit_drag(self):
        # Proves handle_drawing is reused rather than a forked rect builder.
        self.canvas.draw_square = True

        self._drag(20, 20, 80, 40)

        xs = [x for x, _y in self._corners()]
        ys = [y for _x, y in self._corners()]
        self.assertEqual(max(xs) - min(xs), max(ys) - min(ys))

    def test_degenerate_drag_is_discarded_as_in_create_mode(self):
        # Purely horizontal: first corner equals last, so finalise drops it.
        self._drag(20, 20, 80, 20)

        self.assertEqual(self.log, [('poly', True), ('poly', False)])
        self.assertIsNone(self.canvas.provisional_shape)

    def test_locking_mid_drag_cancels_without_creating(self):
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 20, 20))
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 60, 50, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))

        self.canvas.locked = True
        self.canvas.mouseReleaseEvent(
            self._mouse(QEvent.Type.MouseButtonRelease, 60, 50,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))

        self.assertEqual(self.log, [('poly', True), ('poly', False)])
        self.assertIsNone(self.canvas.provisional_shape)
        self.assertIsNone(self.canvas.current)

    def test_click_blocked_by_pending_geometry_is_announced(self):
        """A swallowed click must not vanish in silence.

        The class picker is a frameless Qt.Tool window that never grabs the
        mouse, so a canvas click steals its focus; without this signal the
        user is left with a picker that ignores typing and a canvas that
        ignores clicks, which reads as the app having frozen.
        """
        blocked = []
        self.canvas.provisionalClickBlocked.connect(
            lambda: blocked.append(True))
        self._drag(20, 20, 60, 50)
        self.assertIsNotNone(self.canvas.provisional_shape)

        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 100, 100))

        self.assertEqual(len(blocked), 1)

    def test_click_blocked_is_announced_in_sam_mode_too(self):
        self.canvas.set_sam_mode(True)
        self.canvas.commit_rectangle([20, 20, 60, 50])
        self.assertIsNotNone(self.canvas.provisional_shape)
        blocked = []
        self.canvas.provisionalClickBlocked.connect(
            lambda: blocked.append(True))

        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 100, 100))

        self.assertEqual(len(blocked), 1)

    def test_right_press_mid_drag_cancels_and_swallows_the_menu(self):
        # menu.exec() is a nested event loop; letting it run here would eat
        # the pending left release and strand the gesture forever.
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 20, 20))
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 60, 50, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))

        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 60, 50,
                        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton))

        self.assertFalse(self.canvas._edit_drag_draw)
        self.assertIsNone(self.canvas.current)
        self.assertTrue(self.canvas._suppress_context_menu)
        self.assertEqual(self.log, [('poly', True), ('poly', False)])

        # The swallow is one-shot: the next right-click gets its menu back.
        self.canvas.mouseReleaseEvent(
            self._mouse(QEvent.Type.MouseButtonRelease, 60, 50,
                        Qt.MouseButton.RightButton, Qt.MouseButton.NoButton))
        self.assertFalse(self.canvas._suppress_context_menu)

    def test_reset_state_clears_drag_draw_fields(self):
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 20, 20))
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 60, 50, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))

        self.canvas.reset_state()

        self.assertFalse(self.canvas._edit_drag_draw)
        self.assertIsNone(self.canvas._edit_draw_origin)
        self.assertFalse(self.canvas._panning)


class TestCanvasPanning(_DrawFirstBase):
    """Panning moved off left-drag so left-drag could draw."""

    def setUp(self):
        super(TestCanvasPanning, self).setUp()
        self.scrolls = []
        self.canvas.scrollRequest.connect(
            lambda delta, orientation: self.scrolls.append(
                (delta, orientation)))

    def test_middle_drag_pans(self):
        self._drag(10, 10, 60, 40, button=Qt.MouseButton.MiddleButton)

        self.assertEqual(
            self.scrolls, [
                (50, Qt.Orientation.Horizontal.value),
                (30, Qt.Orientation.Vertical.value),
            ])
        self.assertFalse(self.canvas._panning)

    def test_middle_drag_pans_while_locked(self):
        # Panning mutates nothing, so it stays available during propagation.
        self.canvas.locked = True

        self._drag(10, 10, 60, 40, button=Qt.MouseButton.MiddleButton)

        self.assertEqual(
            self.scrolls, [
                (50, Qt.Orientation.Horizontal.value),
                (30, Qt.Orientation.Vertical.value),
            ])

    def test_left_drag_no_longer_pans(self):
        self._drag(20, 20, 60, 50)

        self.assertEqual(self.scrolls, [])


class TestCanvasHoverCursor(_DrawFirstBase):
    """The crosshair advertises exactly where a drag would draw."""

    def _hover(self, x, y):
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, x, y, Qt.MouseButton.NoButton, Qt.MouseButton.NoButton))
        return self.canvas._cursor

    def test_empty_pixels_offer_the_draw_cursor(self):
        self.assertEqual(self._hover(100, 100), CURSOR_DRAW)

    def test_shape_body_keeps_the_grab_cursor(self):
        shape = Shape(label='box')
        for point in [(10, 10), (80, 10), (80, 80), (10, 80)]:
            shape.add_point(QPointF(*point))
        shape.close()
        self.canvas.load_shapes([shape])

        self.assertEqual(self._hover(40, 40), CURSOR_GRAB)

    def test_letterbox_outside_the_image_keeps_the_arrow(self):
        self.canvas.resize(400, 400)

        self.assertEqual(self._hover(5, 5), CURSOR_DEFAULT)


class TestCanvasEscape(_DrawFirstBase):
    """Escape is two-stage: cancel what is in flight, then go home."""

    @staticmethod
    def _escape():
        return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)

    def test_escape_in_create_returns_to_edit_once(self):
        self.canvas.set_editing(False)
        self.modes.clear()

        self.canvas.keyPressEvent(self._escape())

        self.assertEqual(self.canvas.mode, Canvas.EDIT)
        self.assertEqual(self.modes, [Canvas.EDIT])

    def test_escape_in_edit_changes_nothing(self):
        self.canvas.keyPressEvent(self._escape())

        self.assertEqual(self.canvas.mode, Canvas.EDIT)
        self.assertEqual(self.modes, [])

    def test_escape_cancels_an_in_flight_polygon_before_leaving(self):
        self.canvas.set_polygon_drawing(True)
        self.modes.clear()
        self.log.clear()
        self.canvas.handle_drawing(QPointF(20, 20))
        self.canvas.handle_drawing(QPointF(60, 20))

        self.canvas.keyPressEvent(self._escape())

        # First press cancels the geometry and stays in the tool.
        self.assertIsNone(self.canvas.current)
        self.assertEqual(self.log, [('poly', True), ('poly', False)])
        self.assertEqual(self.canvas.mode, Canvas.CREATE_POLYGON)
        self.assertEqual(self.modes, [])

        self.canvas.keyPressEvent(self._escape())

        self.assertEqual(self.canvas.mode, Canvas.EDIT)
        self.assertEqual(self.modes, [Canvas.EDIT])

    def test_escape_mid_edit_drag_cancels_and_release_is_inert(self):
        self.canvas.mousePressEvent(
            self._mouse(QEvent.Type.MouseButtonPress, 20, 20))
        self.canvas.mouseMoveEvent(
            self._mouse(QEvent.Type.MouseMove, 60, 50, Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))

        self.canvas.keyPressEvent(self._escape())
        self.canvas.mouseReleaseEvent(
            self._mouse(QEvent.Type.MouseButtonRelease, 60, 50,
                        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))

        self.assertEqual(self.log, [('poly', True), ('poly', False)])
        self.assertIsNone(self.canvas.provisional_shape)
        self.assertEqual(self.canvas.mode, Canvas.EDIT)

    def test_escape_keeps_placed_keypoints_when_it_exits(self):
        shape = Shape(label='person', shape_type=ShapeType.POLYGON)
        for point in [(10, 10), (80, 10), (80, 80)]:
            shape.add_point(QPointF(*point))
        shape.close()
        self.canvas.set_keypoint_mode(shape, 'person')
        self.modes.clear()

        for _ in range(self.canvas._keypoint_count() + 1):
            self.canvas.keyPressEvent(self._escape())

        self.assertEqual(self.canvas.mode, Canvas.EDIT)
        self.assertIsNone(self.canvas._keypoint_shape)


if __name__ == '__main__':
    unittest.main()
