# libs/core/__init__.py
"""Core data structures and logic."""

from libs.core.shape import Shape, DEFAULT_LINE_COLOR, DEFAULT_FILL_COLOR
from libs.core.commands import UndoStack, CreateShapeCommand, DeleteShapeCommand, MoveShapeCommand, EditLabelCommand
from libs.core.settings import Settings

__all__ = [
    'Shape', 'DEFAULT_LINE_COLOR', 'DEFAULT_FILL_COLOR',
    'UndoStack', 'CreateShapeCommand', 'DeleteShapeCommand', 'MoveShapeCommand', 'EditLabelCommand',
    'Settings',
]
