# libs/commands.py
"""Command pattern implementation for undo/redo functionality.

This module provides undoable command classes for annotation actions.
"""

from abc import ABC, abstractmethod

try:
    from PyQt5.QtCore import QPointF
except ImportError:
    from PyQt4.QtCore import QPointF


class Command(ABC):
    """Base class for all undoable commands."""

    @abstractmethod
    def execute(self):
        """Execute the command."""
        pass

    @abstractmethod
    def undo(self):
        """Undo the command."""
        pass

    @property
    def description(self):
        """Return a description of this command."""
        return "Command"


class CreateShapeCommand(Command):
    """Command for creating a new shape.

    Undo removes the shape from canvas and label list.
    """

    def __init__(self, main_window, shape):
        """Initialize with reference to main window and the created shape.

        Args:
            main_window: The MainWindow instance.
            shape: The Shape object that was created.
        """
        self.main_window = main_window
        self.shape = shape

    def execute(self):
        """Add the shape to canvas and label list."""
        self.main_window.canvas.shapes.append(self.shape)
        self.main_window.add_label(self.shape)
        self.main_window.canvas.update()

    def undo(self):
        """Remove the shape from canvas and label list."""
        if self.shape in self.main_window.canvas.shapes:
            self.main_window.canvas.shapes.remove(self.shape)
        self.main_window.remove_label(self.shape)
        if self.main_window.canvas.selected_shape == self.shape:
            self.main_window.canvas.selected_shape = None
        self.main_window.canvas.update()

    @property
    def description(self):
        return f"Create shape '{self.shape.label}'"


class DeleteShapeCommand(Command):
    """Command for deleting a shape.

    Undo restores the shape to canvas and label list.
    """

    def __init__(self, main_window, shape, index=None):
        """Initialize with reference to main window and the deleted shape.

        Args:
            main_window: The MainWindow instance.
            shape: The Shape object that will be/was deleted.
            index: Optional index where shape was in the shapes list.
        """
        self.main_window = main_window
        self.shape = shape  # Keep reference to original shape
        self.index = index

    def execute(self):
        """Remove the shape from canvas and label list."""
        if self.shape in self.main_window.canvas.shapes:
            self.main_window.canvas.shapes.remove(self.shape)
        self.main_window.remove_label(self.shape)
        if self.main_window.canvas.selected_shape == self.shape:
            self.main_window.canvas.selected_shape = None
        self.main_window.canvas.update()

    def undo(self):
        """Restore the shape to canvas and label list."""
        if self.index is not None and self.index <= len(self.main_window.canvas.shapes):
            self.main_window.canvas.shapes.insert(self.index, self.shape)
        else:
            self.main_window.canvas.shapes.append(self.shape)
        self.main_window.add_label(self.shape)
        self.main_window.canvas.update()

    @property
    def description(self):
        return f"Delete shape '{self.shape.label}'"


class MoveShapeCommand(Command):
    """Command for moving a shape.

    Undo restores the shape to its original position.
    """

    def __init__(self, main_window, shape, old_points, new_points):
        """Initialize with shape and its positions.

        Args:
            main_window: The MainWindow instance.
            shape: The Shape object being moved.
            old_points: List of QPointF representing original position.
            new_points: List of QPointF representing new position.
        """
        self.main_window = main_window
        self.shape = shape
        # Store copies of points to avoid reference issues
        self.old_points = [QPointF(p.x(), p.y()) for p in old_points]
        self.new_points = [QPointF(p.x(), p.y()) for p in new_points]

    def execute(self):
        """Move shape to new position."""
        self.shape.points = [QPointF(p.x(), p.y()) for p in self.new_points]
        self.main_window.canvas.update()

    def undo(self):
        """Restore shape to original position."""
        self.shape.points = [QPointF(p.x(), p.y()) for p in self.old_points]
        self.main_window.canvas.update()

    @property
    def description(self):
        return f"Move shape '{self.shape.label}'"


class EditLabelCommand(Command):
    """Command for editing a shape's label.

    Undo restores the old label text.
    """

    def __init__(self, main_window, shape, old_label, new_label):
        """Initialize with shape and label values.

        Args:
            main_window: The MainWindow instance.
            shape: The Shape object being edited.
            old_label: The original label text.
            new_label: The new label text.
        """
        self.main_window = main_window
        self.shape = shape
        self.old_label = old_label
        self.new_label = new_label

    def execute(self):
        """Apply new label."""
        self.shape.label = self.new_label
        self._update_list_item()
        self.main_window.canvas.update()

    def undo(self):
        """Restore old label."""
        self.shape.label = self.old_label
        self._update_list_item()
        self.main_window.canvas.update()

    def _update_list_item(self):
        """Update the label list item to reflect current shape label."""
        if self.shape in self.main_window.shapes_to_items:
            item = self.main_window.shapes_to_items[self.shape]
            item.setText(self.shape.label)
            from libs.hashableQListWidgetItem import generate_color_by_text
            item.setBackground(generate_color_by_text(self.shape.label))

    @property
    def description(self):
        return f"Edit label '{self.old_label}' -> '{self.new_label}'"


class UndoStack:
    """Manages command history for undo/redo operations.

    Maintains two stacks: one for undo operations and one for redo.
    When a new command is pushed, the redo stack is cleared.
    """

    def __init__(self, max_size=50):
        """Initialize the undo stack.

        Args:
            max_size: Maximum number of commands to store (default 50).
        """
        self._undo_stack = []
        self._redo_stack = []
        self._max_size = max_size
        self._callbacks = []

    def push(self, command):
        """Add a command to the undo stack.

        The command should already be executed before pushing.
        Clears the redo stack since we're branching history.

        Args:
            command: The Command object to push.
        """
        self._undo_stack.append(command)
        self._redo_stack.clear()

        # Trim stack if it exceeds max size
        while len(self._undo_stack) > self._max_size:
            self._undo_stack.pop(0)

        self._notify_callbacks()

    def undo(self):
        """Undo the last command.

        Returns:
            The undone command, or None if stack was empty.
        """
        if not self.can_undo():
            return None

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        self._notify_callbacks()
        return command

    def redo(self):
        """Redo the last undone command.

        Returns:
            The redone command, or None if redo stack was empty.
        """
        if not self.can_redo():
            return None

        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        self._notify_callbacks()
        return command

    def can_undo(self):
        """Check if undo is available.

        Returns:
            True if there are commands to undo.
        """
        return len(self._undo_stack) > 0

    def can_redo(self):
        """Check if redo is available.

        Returns:
            True if there are commands to redo.
        """
        return len(self._redo_stack) > 0

    def clear(self):
        """Clear both undo and redo stacks.

        Call this when loading a new file.
        """
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_callbacks()

    def add_callback(self, callback):
        """Register a callback to be notified when stack changes.

        Args:
            callback: A callable that takes no arguments.
        """
        self._callbacks.append(callback)

    def remove_callback(self, callback):
        """Remove a previously registered callback.

        Args:
            callback: The callback to remove.
        """
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks of stack change."""
        for callback in self._callbacks:
            callback()

    def get_undo_description(self):
        """Get description of the command that would be undone.

        Returns:
            Description string or None if stack is empty.
        """
        if self.can_undo():
            return self._undo_stack[-1].description
        return None

    def get_redo_description(self):
        """Get description of the command that would be redone.

        Returns:
            Description string or None if redo stack is empty.
        """
        if self.can_redo():
            return self._redo_stack[-1].description
        return None

    def __len__(self):
        """Return number of commands in undo stack."""
        return len(self._undo_stack)
