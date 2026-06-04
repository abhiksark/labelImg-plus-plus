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

from PyQt5.QtCore import QPointF, QPoint, Qt, QEvent
from PyQt5.QtGui import QPixmap, QColor, QKeyEvent
from PyQt5.QtWidgets import QApplication

from libs.widgets.canvas import Canvas
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

        ctrl_z = QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.ControlModifier)
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

        ctrl_z = QKeyEvent(QEvent.KeyPress, Qt.Key_Z, Qt.ControlModifier)
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


if __name__ == '__main__':
    unittest.main()
