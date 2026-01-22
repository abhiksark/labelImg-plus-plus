# tests/test_commands.py
"""Unit tests for the undo/redo command system."""

import os
import sys
import unittest

# Add parent directory to path for imports
dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QPointF

from libs.commands import (
    UndoStack,
    CreateShapeCommand,
    DeleteShapeCommand,
    MoveShapeCommand,
    EditLabelCommand,
)
from libs.shape import Shape


# Create a QApplication instance for tests
app = QApplication.instance() or QApplication(sys.argv)


class MockMainWindow:
    """Mock MainWindow for testing commands."""

    def __init__(self):
        self.shapes_to_items = {}
        self.items_to_shapes = {}

        class MockCanvas:
            def __init__(self):
                self.shapes = []
                self.selected_shape = None

            def update(self):
                pass

        self.canvas = MockCanvas()

        class MockLabelList:
            def __init__(self):
                self.items = []

            def addItem(self, item):
                self.items.append(item)

            def takeItem(self, idx):
                return self.items.pop(idx)

            def row(self, item):
                return self.items.index(item) if item in self.items else -1

        self.label_list = MockLabelList()

    def add_label(self, shape):
        item = shape.label
        self.items_to_shapes[item] = shape
        self.shapes_to_items[shape] = item
        self.label_list.addItem(item)

    def remove_label(self, shape):
        if shape is None:
            return
        if shape in self.shapes_to_items:
            item = self.shapes_to_items[shape]
            idx = self.label_list.row(item)
            if idx >= 0:
                self.label_list.takeItem(idx)
            del self.shapes_to_items[shape]
            del self.items_to_shapes[item]

    def update_combo_box(self):
        pass


def create_test_shape(label='test'):
    """Create a test shape with default points."""
    shape = Shape(label=label)
    shape.points = [
        QPointF(0, 0),
        QPointF(100, 0),
        QPointF(100, 100),
        QPointF(0, 100),
    ]
    shape.close()
    return shape


class TestUndoStack(unittest.TestCase):
    """Test cases for UndoStack class."""

    def test_init(self):
        """Test UndoStack initialization."""
        stack = UndoStack()
        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())
        self.assertEqual(len(stack), 0)

    def test_push(self):
        """Test pushing commands to the stack."""
        stack = UndoStack()
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)

        self.assertTrue(stack.can_undo())
        self.assertFalse(stack.can_redo())
        self.assertEqual(len(stack), 1)

    def test_undo(self):
        """Test undoing a command."""
        stack = UndoStack()
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)

        stack.undo()

        self.assertFalse(stack.can_undo())
        self.assertTrue(stack.can_redo())
        self.assertEqual(len(mw.canvas.shapes), 0)

    def test_redo(self):
        """Test redoing a command."""
        stack = UndoStack()
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)
        stack.undo()
        stack.redo()

        self.assertTrue(stack.can_undo())
        self.assertFalse(stack.can_redo())
        self.assertEqual(len(mw.canvas.shapes), 1)

    def test_clear(self):
        """Test clearing the stack."""
        stack = UndoStack()
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)
        stack.clear()

        self.assertFalse(stack.can_undo())
        self.assertFalse(stack.can_redo())
        self.assertEqual(len(stack), 0)

    def test_max_size(self):
        """Test that stack respects max size."""
        stack = UndoStack(max_size=3)
        mw = MockMainWindow()

        for i in range(5):
            shape = create_test_shape(f'shape{i}')
            mw.canvas.shapes.append(shape)
            mw.add_label(shape)
            cmd = CreateShapeCommand(mw, shape)
            stack.push(cmd)

        self.assertEqual(len(stack), 3)

    def test_push_clears_redo(self):
        """Test that pushing a new command clears the redo stack."""
        stack = UndoStack()
        mw = MockMainWindow()

        shape1 = create_test_shape('shape1')
        mw.canvas.shapes.append(shape1)
        mw.add_label(shape1)
        cmd1 = CreateShapeCommand(mw, shape1)
        stack.push(cmd1)

        stack.undo()
        self.assertTrue(stack.can_redo())

        shape2 = create_test_shape('shape2')
        mw.canvas.shapes.append(shape2)
        mw.add_label(shape2)
        cmd2 = CreateShapeCommand(mw, shape2)
        stack.push(cmd2)

        self.assertFalse(stack.can_redo())

    def test_callback(self):
        """Test that callbacks are called on stack changes."""
        stack = UndoStack()
        callback_count = [0]

        def callback():
            callback_count[0] += 1

        stack.add_callback(callback)

        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)
        cmd = CreateShapeCommand(mw, shape)

        stack.push(cmd)  # callback called
        self.assertEqual(callback_count[0], 1)

        stack.undo()  # callback called
        self.assertEqual(callback_count[0], 2)

        stack.redo()  # callback called
        self.assertEqual(callback_count[0], 3)


class TestCreateShapeCommand(unittest.TestCase):
    """Test cases for CreateShapeCommand."""

    def test_undo_removes_shape(self):
        """Test that undo removes the shape."""
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = CreateShapeCommand(mw, shape)
        cmd.undo()

        self.assertEqual(len(mw.canvas.shapes), 0)
        self.assertEqual(len(mw.shapes_to_items), 0)

    def test_execute_adds_shape(self):
        """Test that execute adds the shape."""
        mw = MockMainWindow()
        shape = create_test_shape()

        cmd = CreateShapeCommand(mw, shape)
        cmd.execute()

        self.assertEqual(len(mw.canvas.shapes), 1)
        self.assertIn(shape, mw.canvas.shapes)


class TestDeleteShapeCommand(unittest.TestCase):
    """Test cases for DeleteShapeCommand."""

    def test_execute_removes_shape(self):
        """Test that execute removes the shape."""
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = DeleteShapeCommand(mw, shape, 0)
        cmd.execute()

        self.assertEqual(len(mw.canvas.shapes), 0)

    def test_undo_restores_shape(self):
        """Test that undo restores the shape."""
        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)

        cmd = DeleteShapeCommand(mw, shape, 0)
        cmd.execute()
        cmd.undo()

        self.assertEqual(len(mw.canvas.shapes), 1)


class TestMoveShapeCommand(unittest.TestCase):
    """Test cases for MoveShapeCommand."""

    def test_undo_restores_position(self):
        """Test that undo restores original position."""
        mw = MockMainWindow()
        shape = create_test_shape()
        old_points = [QPointF(p.x(), p.y()) for p in shape.points]
        new_points = [QPointF(p.x() + 50, p.y() + 50) for p in shape.points]

        shape.points = new_points

        cmd = MoveShapeCommand(mw, shape, old_points, new_points)
        cmd.undo()

        for i, p in enumerate(shape.points):
            self.assertEqual(p.x(), old_points[i].x())
            self.assertEqual(p.y(), old_points[i].y())

    def test_execute_applies_new_position(self):
        """Test that execute applies new position."""
        mw = MockMainWindow()
        shape = create_test_shape()
        old_points = [QPointF(p.x(), p.y()) for p in shape.points]
        new_points = [QPointF(p.x() + 50, p.y() + 50) for p in shape.points]

        cmd = MoveShapeCommand(mw, shape, old_points, new_points)
        cmd.execute()

        for i, p in enumerate(shape.points):
            self.assertEqual(p.x(), new_points[i].x())
            self.assertEqual(p.y(), new_points[i].y())


class TestEditLabelCommand(unittest.TestCase):
    """Test cases for EditLabelCommand."""

    def test_undo_restores_label(self):
        """Test that undo restores the old label."""
        mw = MockMainWindow()
        shape = create_test_shape('old_label')
        shape.label = 'new_label'

        cmd = EditLabelCommand(mw, shape, 'old_label', 'new_label')
        cmd.undo()

        self.assertEqual(shape.label, 'old_label')

    def test_execute_applies_new_label(self):
        """Test that execute applies the new label."""
        mw = MockMainWindow()
        shape = create_test_shape('old_label')

        cmd = EditLabelCommand(mw, shape, 'old_label', 'new_label')
        cmd.execute()

        self.assertEqual(shape.label, 'new_label')


class TestUndoStackEdgeCases(unittest.TestCase):
    """Edge case tests for UndoStack."""

    def test_undo_empty_stack(self):
        """Test that undo on empty stack does nothing."""
        stack = UndoStack()

        # Should not raise
        stack.undo()

        self.assertFalse(stack.can_undo())

    def test_redo_empty_stack(self):
        """Test that redo on empty stack does nothing."""
        stack = UndoStack()

        # Should not raise
        stack.redo()

        self.assertFalse(stack.can_redo())

    def test_multiple_undo_redo_cycles(self):
        """Test multiple undo/redo cycles."""
        stack = UndoStack()
        mw = MockMainWindow()

        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)
        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)

        # Multiple cycles
        for _ in range(3):
            stack.undo()
            self.assertEqual(len(mw.canvas.shapes), 0)

            stack.redo()
            self.assertEqual(len(mw.canvas.shapes), 1)

    def test_undo_sequence(self):
        """Test undoing a sequence of commands."""
        stack = UndoStack()
        mw = MockMainWindow()

        shapes = []
        for i in range(3):
            shape = create_test_shape(f'shape{i}')
            mw.canvas.shapes.append(shape)
            mw.add_label(shape)
            cmd = CreateShapeCommand(mw, shape)
            stack.push(cmd)
            shapes.append(shape)

        self.assertEqual(len(mw.canvas.shapes), 3)

        # Undo all
        stack.undo()
        self.assertEqual(len(mw.canvas.shapes), 2)

        stack.undo()
        self.assertEqual(len(mw.canvas.shapes), 1)

        stack.undo()
        self.assertEqual(len(mw.canvas.shapes), 0)

    def test_remove_callback(self):
        """Test removing a callback."""
        stack = UndoStack()
        callback_count = [0]

        def callback():
            callback_count[0] += 1

        stack.add_callback(callback)
        stack.remove_callback(callback)

        mw = MockMainWindow()
        shape = create_test_shape()
        mw.canvas.shapes.append(shape)
        mw.add_label(shape)
        cmd = CreateShapeCommand(mw, shape)
        stack.push(cmd)

        # Callback should not have been called
        self.assertEqual(callback_count[0], 0)


class TestMoveShapeCommandEdgeCases(unittest.TestCase):
    """Edge case tests for MoveShapeCommand."""

    def test_move_zero_offset(self):
        """Test move with zero offset."""
        mw = MockMainWindow()
        shape = create_test_shape()
        old_points = [QPointF(p.x(), p.y()) for p in shape.points]
        new_points = old_points.copy()  # Same positions

        cmd = MoveShapeCommand(mw, shape, old_points, new_points)
        cmd.execute()

        # Points should remain unchanged
        for i, p in enumerate(shape.points):
            self.assertEqual(p.x(), old_points[i].x())
            self.assertEqual(p.y(), old_points[i].y())

    def test_move_negative_offset(self):
        """Test move with negative offset."""
        mw = MockMainWindow()
        shape = create_test_shape()
        old_points = [QPointF(p.x(), p.y()) for p in shape.points]
        new_points = [QPointF(p.x() - 25, p.y() - 25) for p in shape.points]

        cmd = MoveShapeCommand(mw, shape, old_points, new_points)
        cmd.execute()

        for i, p in enumerate(shape.points):
            self.assertEqual(p.x(), old_points[i].x() - 25)
            self.assertEqual(p.y(), old_points[i].y() - 25)


class TestEditLabelCommandEdgeCases(unittest.TestCase):
    """Edge case tests for EditLabelCommand."""

    def test_edit_label_empty_string(self):
        """Test editing label to empty string."""
        mw = MockMainWindow()
        shape = create_test_shape('original')

        cmd = EditLabelCommand(mw, shape, 'original', '')
        cmd.execute()

        self.assertEqual(shape.label, '')

    def test_edit_label_unicode(self):
        """Test editing label with unicode characters."""
        mw = MockMainWindow()
        shape = create_test_shape('original')

        cmd = EditLabelCommand(mw, shape, 'original', '猫')
        cmd.execute()

        self.assertEqual(shape.label, '猫')

    def test_edit_label_same_value(self):
        """Test editing label to same value."""
        mw = MockMainWindow()
        shape = create_test_shape('same')

        cmd = EditLabelCommand(mw, shape, 'same', 'same')
        cmd.execute()

        self.assertEqual(shape.label, 'same')


if __name__ == '__main__':
    unittest.main()
