"""Tests for Shape class."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..'))
sys.path.insert(0, os.path.join(dir_name, '..', 'libs'))

from PyQt5.QtCore import QPointF
from PyQt5.QtWidgets import QApplication

from libs.shape import Shape

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


if __name__ == '__main__':
    unittest.main()
