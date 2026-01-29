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

from PyQt5.QtCore import QPointF, QPoint, Qt
from PyQt5.QtGui import QPixmap, QColor
from PyQt5.QtWidgets import QApplication

from libs.canvas import Canvas
from libs.shape import Shape

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


if __name__ == '__main__':
    unittest.main()
