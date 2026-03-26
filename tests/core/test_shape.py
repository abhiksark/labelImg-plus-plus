"""Tests for Shape class."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
sys.path.insert(0, os.path.join(dir_name, '..', '..', 'libs'))

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication

from libs.core.shape import Shape, ShapeType

# Create QApplication for tests
app = QApplication.instance() or QApplication(sys.argv)


class TestShapeInit(unittest.TestCase):
    """Test cases for Shape initialization."""

    def test_default_init(self):
        """Test default Shape initialization."""
        shape = Shape()

        self.assertIsNone(shape.label)
        self.assertEqual(shape.points, [])
        self.assertFalse(shape.fill)
        self.assertFalse(shape.selected)
        self.assertFalse(shape.difficult)
        self.assertFalse(shape.paint_label)
        self.assertFalse(shape.is_closed())

    def test_init_with_label(self):
        """Test Shape initialization with label."""
        shape = Shape(label='cat')

        self.assertEqual(shape.label, 'cat')

    def test_init_with_difficult(self):
        """Test Shape initialization with difficult flag."""
        shape = Shape(difficult=True)

        self.assertTrue(shape.difficult)

    def test_init_with_paint_label(self):
        """Test Shape initialization with paint_label flag."""
        shape = Shape(paint_label=True)

        self.assertTrue(shape.paint_label)


class TestShapePoints(unittest.TestCase):
    """Test cases for Shape point manipulation."""

    def test_add_point(self):
        """Test adding points to shape."""
        shape = Shape()

        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))

        self.assertEqual(len(shape.points), 2)

    def test_add_point_max_four(self):
        """Test that shape stops accepting points after 4."""
        shape = Shape()

        for i in range(6):
            shape.add_point(QPointF(i * 10, i * 10))

        self.assertEqual(len(shape.points), 4)

    def test_reach_max_points(self):
        """Test reach_max_points detection."""
        shape = Shape()

        self.assertFalse(shape.reach_max_points())

        for i in range(4):
            shape.add_point(QPointF(i * 10, i * 10))

        self.assertTrue(shape.reach_max_points())

    def test_pop_point(self):
        """Test popping last point."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 100))

        popped = shape.pop_point()

        self.assertEqual(popped.x(), 100)
        self.assertEqual(popped.y(), 100)
        self.assertEqual(len(shape.points), 1)

    def test_pop_point_empty(self):
        """Test popping from empty shape returns None."""
        shape = Shape()

        result = shape.pop_point()

        self.assertIsNone(result)

    def test_len(self):
        """Test __len__ returns number of points."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))

        self.assertEqual(len(shape), 3)

    def test_getitem(self):
        """Test __getitem__ returns point at index."""
        shape = Shape()
        shape.add_point(QPointF(10, 20))
        shape.add_point(QPointF(30, 40))

        self.assertEqual(shape[0].x(), 10)
        self.assertEqual(shape[1].y(), 40)

    def test_setitem(self):
        """Test __setitem__ sets point at index."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))

        shape[0] = QPointF(50, 50)

        self.assertEqual(shape[0].x(), 50)
        self.assertEqual(shape[0].y(), 50)


class TestShapeState(unittest.TestCase):
    """Test cases for Shape state management."""

    def test_close(self):
        """Test closing a shape."""
        shape = Shape()

        self.assertFalse(shape.is_closed())

        shape.close()

        self.assertTrue(shape.is_closed())

    def test_set_open(self):
        """Test reopening a closed shape."""
        shape = Shape()
        shape.close()

        shape.set_open()

        self.assertFalse(shape.is_closed())

    def test_highlight_vertex(self):
        """Test vertex highlighting."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))

        shape.highlight_vertex(0, Shape.MOVE_VERTEX)

        self.assertEqual(shape._highlight_index, 0)
        self.assertEqual(shape._highlight_mode, Shape.MOVE_VERTEX)

    def test_highlight_clear(self):
        """Test clearing vertex highlight."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.highlight_vertex(0, Shape.MOVE_VERTEX)

        shape.highlight_clear()

        self.assertIsNone(shape._highlight_index)


class TestShapeMovement(unittest.TestCase):
    """Test cases for Shape movement operations."""

    def test_move_by(self):
        """Test moving entire shape by offset."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))

        shape.move_by(QPointF(50, 25))

        self.assertEqual(shape[0].x(), 50)
        self.assertEqual(shape[0].y(), 25)
        self.assertEqual(shape[2].x(), 150)
        self.assertEqual(shape[2].y(), 125)

    def test_move_vertex_by(self):
        """Test moving single vertex by offset."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))

        shape.move_vertex_by(0, QPointF(10, 20))

        self.assertEqual(shape[0].x(), 10)
        self.assertEqual(shape[0].y(), 20)
        # Other vertex unchanged
        self.assertEqual(shape[1].x(), 100)
        self.assertEqual(shape[1].y(), 0)


class TestShapeGeometry(unittest.TestCase):
    """Test cases for Shape geometry operations."""

    def test_bounding_rect(self):
        """Test bounding rectangle calculation."""
        shape = Shape()
        shape.add_point(QPointF(10, 20))
        shape.add_point(QPointF(110, 20))
        shape.add_point(QPointF(110, 80))
        shape.add_point(QPointF(10, 80))

        rect = shape.bounding_rect()

        self.assertEqual(rect.x(), 10)
        self.assertEqual(rect.y(), 20)
        self.assertEqual(rect.width(), 100)
        self.assertEqual(rect.height(), 60)

    def test_contains_point_inside(self):
        """Test that contains_point returns True for point inside."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))

        self.assertTrue(shape.contains_point(QPointF(50, 50)))

    def test_contains_point_outside(self):
        """Test that contains_point returns False for point outside."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))

        self.assertFalse(shape.contains_point(QPointF(200, 200)))

    def test_nearest_vertex(self):
        """Test finding nearest vertex to a point."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))
        shape.add_point(QPointF(100, 100))
        shape.add_point(QPointF(0, 100))

        # Point near vertex 2 (100, 100)
        index = shape.nearest_vertex(QPointF(95, 95), epsilon=20)

        self.assertEqual(index, 2)

    def test_nearest_vertex_none_if_too_far(self):
        """Test that nearest_vertex returns None if no vertex within epsilon."""
        shape = Shape()
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 0))

        index = shape.nearest_vertex(QPointF(50, 50), epsilon=5)

        self.assertIsNone(index)


class TestShapeCopy(unittest.TestCase):
    """Test cases for Shape copy operation."""

    def test_copy_basic(self):
        """Test basic shape copy."""
        shape = Shape(label='original')
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 100))
        shape.close()

        copied = shape.copy()

        self.assertEqual(copied.label, 'original')
        self.assertEqual(len(copied.points), 2)
        self.assertTrue(copied.is_closed())

    def test_copy_is_independent(self):
        """Test that copied shape is independent of original."""
        shape = Shape(label='original')
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(100, 100))

        copied = shape.copy()
        copied.label = 'modified'
        copied.move_by(QPointF(50, 50))

        # Original unchanged
        self.assertEqual(shape.label, 'original')
        self.assertEqual(shape[0].x(), 0)

    def test_copy_preserves_difficult(self):
        """Test that copy preserves difficult flag."""
        shape = Shape(difficult=True)

        copied = shape.copy()

        self.assertTrue(copied.difficult)

    def test_copy_preserves_selected(self):
        """Test that copy preserves selected state."""
        shape = Shape()
        shape.selected = True

        copied = shape.copy()

        self.assertTrue(copied.selected)

    def test_copy_preserves_fill(self):
        """Test that copy preserves fill state."""
        shape = Shape()
        shape.fill = True

        copied = shape.copy()

        self.assertTrue(copied.fill)


class TestShapeClassConstants(unittest.TestCase):
    """Test cases for Shape class constants."""

    def test_point_types(self):
        """Test point type constants."""
        self.assertEqual(Shape.P_SQUARE, 0)
        self.assertEqual(Shape.P_ROUND, 1)

    def test_vertex_modes(self):
        """Test vertex mode constants."""
        self.assertEqual(Shape.MOVE_VERTEX, 0)
        self.assertEqual(Shape.NEAR_VERTEX, 1)


class TestShapeType(unittest.TestCase):
    """Test ShapeType enum and type-aware behavior."""

    def test_default_shape_type_is_rectangle(self):
        shape = Shape()
        self.assertEqual(shape.shape_type, ShapeType.RECTANGLE)

    def test_polygon_shape_type(self):
        shape = Shape(shape_type=ShapeType.POLYGON)
        self.assertEqual(shape.shape_type, ShapeType.POLYGON)

    def test_rectangle_max_points_is_4(self):
        shape = Shape()
        for i in range(10):
            shape.add_point(QPointF(i, i))
        self.assertEqual(len(shape.points), 4)

    def test_polygon_allows_many_points(self):
        shape = Shape(shape_type=ShapeType.POLYGON)
        for i in range(50):
            shape.add_point(QPointF(i, i))
        self.assertEqual(len(shape.points), 50)

    def test_polygon_max_points_cap(self):
        shape = Shape(shape_type=ShapeType.POLYGON)
        for i in range(150):
            shape.add_point(QPointF(i, i))
        self.assertEqual(len(shape.points), 100)


class TestPolygonVertexOps(unittest.TestCase):
    """Test polygon-specific vertex operations."""

    def _make_triangle(self):
        shape = Shape(label='tri', shape_type=ShapeType.POLYGON)
        shape.add_point(QPointF(0, 0))
        shape.add_point(QPointF(10, 0))
        shape.add_point(QPointF(5, 10))
        shape.close()
        return shape

    def test_remove_point_polygon(self):
        shape = self._make_triangle()
        shape.add_point(QPointF(7, 5))  # now 4 points
        shape.remove_point(2)
        self.assertEqual(len(shape.points), 3)

    def test_remove_point_enforces_min_3(self):
        shape = self._make_triangle()
        result = shape.remove_point(0)
        self.assertFalse(result)
        self.assertEqual(len(shape.points), 3)

    def test_remove_point_not_allowed_on_rectangle(self):
        shape = Shape()
        for p in [QPointF(0, 0), QPointF(10, 0), QPointF(10, 10), QPointF(0, 10)]:
            shape.add_point(p)
        result = shape.remove_point(0)
        self.assertFalse(result)

    def test_insert_point(self):
        shape = self._make_triangle()
        shape.insert_point(1, QPointF(7, 0))
        self.assertEqual(len(shape.points), 4)
        self.assertEqual(shape.points[1], QPointF(7, 0))

    def test_midpoint_of_edge(self):
        shape = self._make_triangle()
        mid = shape.midpoint_of_edge(0)
        self.assertAlmostEqual(mid.x(), 5.0)
        self.assertAlmostEqual(mid.y(), 0.0)

    def test_midpoint_of_last_edge_wraps(self):
        shape = self._make_triangle()
        mid = shape.midpoint_of_edge(2)  # edge from (5,10) back to (0,0)
        self.assertAlmostEqual(mid.x(), 2.5)
        self.assertAlmostEqual(mid.y(), 5.0)

    def test_copy_preserves_shape_type(self):
        shape = self._make_triangle()
        copied = shape.copy()
        self.assertEqual(copied.shape_type, ShapeType.POLYGON)

    def test_nearest_midpoint_hit(self):
        """Test nearest_midpoint returns edge index when point is near midpoint."""
        shape = self._make_triangle()
        # Midpoint of edge 0 is (5, 0). Search near it.
        result = shape.nearest_midpoint(QPointF(5.5, 0.5), 2.0)
        self.assertEqual(result, 0)

    def test_nearest_midpoint_miss(self):
        """Test nearest_midpoint returns None when no midpoint is close."""
        shape = self._make_triangle()
        result = shape.nearest_midpoint(QPointF(100, 100), 2.0)
        self.assertIsNone(result)

    def test_nearest_midpoint_rectangle_returns_none(self):
        """Test nearest_midpoint returns None for rectangle shapes."""
        shape = Shape()
        for p in [QPointF(0, 0), QPointF(10, 0), QPointF(10, 10), QPointF(0, 10)]:
            shape.add_point(p)
        result = shape.nearest_midpoint(QPointF(5, 0), 2.0)
        self.assertIsNone(result)

    def test_insert_point_blocked_on_rectangle(self):
        """Test insert_point is blocked on rectangle shapes."""
        shape = Shape()
        for p in [QPointF(0, 0), QPointF(10, 0), QPointF(10, 10), QPointF(0, 10)]:
            shape.add_point(p)
        shape.insert_point(1, QPointF(5, 0))
        self.assertEqual(len(shape.points), 4)  # unchanged


class TestShapeKeypoints(unittest.TestCase):
    """Test keypoint metadata on Shape."""

    def _make_person_box(self):
        shape = Shape(label='person')
        for p in [QPointF(10, 10), QPointF(100, 10),
                  QPointF(100, 200), QPointF(10, 200)]:
            shape.add_point(p)
        shape.close()
        return shape

    def test_keypoints_default_none(self):
        shape = Shape()
        self.assertIsNone(shape.keypoints)

    def test_set_keypoints(self):
        shape = self._make_person_box()
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)
        shape.keypoints = kps
        self.assertEqual(shape.keypoints[0], (50.0, 20.0, 2))
        self.assertIsNone(shape.keypoints[1])

    def test_num_keypoints_none(self):
        shape = Shape()
        self.assertEqual(shape.num_keypoints, 0)

    def test_num_keypoints_count(self):
        shape = self._make_person_box()
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)   # visible
        kps[1] = (45.0, 18.0, 1)   # occluded
        kps[2] = (55.0, 18.0, 0)   # not labeled
        shape.keypoints = kps
        self.assertEqual(shape.num_keypoints, 2)

    def test_move_by_shifts_keypoints(self):
        shape = self._make_person_box()
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)
        kps[5] = (30.0, 60.0, 1)
        shape.keypoints = kps
        shape.move_by(QPointF(10.0, 5.0))
        self.assertAlmostEqual(shape.keypoints[0][0], 60.0)
        self.assertAlmostEqual(shape.keypoints[0][1], 25.0)
        self.assertEqual(shape.keypoints[0][2], 2)
        self.assertAlmostEqual(shape.keypoints[5][0], 40.0)
        self.assertAlmostEqual(shape.keypoints[5][1], 65.0)
        self.assertIsNone(shape.keypoints[1])

    def test_copy_preserves_keypoints(self):
        shape = self._make_person_box()
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)
        shape.keypoints = kps
        copied = shape.copy()
        self.assertIsNotNone(copied.keypoints)
        self.assertEqual(copied.keypoints[0], (50.0, 20.0, 2))

    def test_copy_keypoints_independent(self):
        shape = self._make_person_box()
        kps = [None] * 17
        kps[0] = (50.0, 20.0, 2)
        shape.keypoints = kps
        copied = shape.copy()
        copied.keypoints[0] = (99.0, 99.0, 1)
        self.assertEqual(shape.keypoints[0], (50.0, 20.0, 2))

    def test_keypoints_none_after_copy_when_not_set(self):
        shape = self._make_person_box()
        copied = shape.copy()
        self.assertIsNone(copied.keypoints)


if __name__ == '__main__':
    unittest.main()
