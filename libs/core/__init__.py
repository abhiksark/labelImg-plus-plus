# libs/core/__init__.py
"""Core data structures and logic."""

import importlib

__all__ = [
    'Shape', 'DEFAULT_LINE_COLOR', 'DEFAULT_FILL_COLOR',
    'UndoStack', 'CreateShapeCommand', 'DeleteShapeCommand', 'MoveShapeCommand', 'EditLabelCommand',
    'Settings',
]

_EXPORTS = {
    'Shape': ('libs.core.shape', 'Shape'),
    'DEFAULT_LINE_COLOR': ('libs.core.shape', 'DEFAULT_LINE_COLOR'),
    'DEFAULT_FILL_COLOR': ('libs.core.shape', 'DEFAULT_FILL_COLOR'),
    'UndoStack': ('libs.core.commands', 'UndoStack'),
    'CreateShapeCommand': ('libs.core.commands', 'CreateShapeCommand'),
    'DeleteShapeCommand': ('libs.core.commands', 'DeleteShapeCommand'),
    'MoveShapeCommand': ('libs.core.commands', 'MoveShapeCommand'),
    'EditLabelCommand': ('libs.core.commands', 'EditLabelCommand'),
    'Settings': ('libs.core.settings', 'Settings'),
}


def __getattr__(name):
    """Preserve public exports while plain-data modules remain Qt-free."""
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError:
        raise AttributeError(name)
    value = getattr(importlib.import_module(module_name), attribute)
    globals()[name] = value
    return value
