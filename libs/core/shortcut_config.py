# libs/core/shortcut_config.py
"""Keyboard shortcut configuration management."""

import json


DEFAULT_SHORTCUTS = {
    'quit': 'Ctrl+Q',
    'open': 'Ctrl+O',
    'open_dir': 'Ctrl+U',
    'change_save_dir': 'Ctrl+R',
    'open_annotation': 'Ctrl+Shift+O',
    'copy_prev_bounding': 'Ctrl+Shift+V',
    'open_next_image': 'D',
    'open_prev_image': 'A',
    'verify': 'Space',
    'save': 'Ctrl+S',
    'save_format': 'Ctrl+Y',
    'save_as': 'Ctrl+Shift+S',
    'close': 'Ctrl+W',
    'delete_image': 'Ctrl+Shift+D',
    'color1': 'Ctrl+L',
    'create_mode': 'W',
    'edit_mode': 'Ctrl+J',
    'create': 'W',
    'delete': 'Delete',
    'copy': 'Ctrl+D',
    'copy_to_clipboard': 'Ctrl+C',
    'paste_from_clipboard': 'Ctrl+V',
    'copy_all_to_clipboard': 'Ctrl+Shift+C',
    'undo': 'Ctrl+Z',
    'redo': 'Ctrl+Shift+Z',
    'advanced_mode': 'Ctrl+Shift+A',
    'gallery_mode': 'Ctrl+G',
    'hide_all': 'Ctrl+H',
    'show_all': 'Ctrl+A',
    'zoom_in': 'Ctrl++',
    'zoom_out': 'Ctrl+-',
    'zoom_org': 'Ctrl+=',
    'fit_window': 'Ctrl+F',
    'fit_width': 'Ctrl+Shift+F',
    'light_brighten': 'Ctrl+Shift++',
    'light_darken': 'Ctrl+Shift+-',
    'light_org': 'Ctrl+Shift+=',
    'edit_label': 'Ctrl+E',
    'show_grid': 'Ctrl+Shift+G',
}


class ShortcutConfig:
    """Manages keyboard shortcut configuration."""

    def __init__(self):
        self._shortcuts = dict(DEFAULT_SHORTCUTS)

    def get(self, action_name):
        """Returns the shortcut for the given action name, or None."""
        return self._shortcuts.get(action_name)

    def set(self, action_name, shortcut):
        """Sets the shortcut for the given action name."""
        self._shortcuts[action_name] = shortcut

    def reset(self, action_name):
        """Resets a single action's shortcut to its default value."""
        if action_name in DEFAULT_SHORTCUTS:
            self._shortcuts[action_name] = DEFAULT_SHORTCUTS[action_name]

    def reset_all(self):
        """Resets all shortcuts to their default values."""
        self._shortcuts = dict(DEFAULT_SHORTCUTS)

    def get_all(self):
        """Returns a copy of all current shortcuts."""
        return dict(self._shortcuts)

    def get_default(self, action_name):
        """Returns the default shortcut for the given action name."""
        return DEFAULT_SHORTCUTS.get(action_name, '')

    def find_conflict(self, shortcut, exclude_action=None):
        """Return action name that has this shortcut, or None."""
        if not shortcut:
            return None
        for name, sc in self._shortcuts.items():
            if name != exclude_action and sc == shortcut:
                return name
        return None

    def to_dict(self):
        """Serializes shortcuts to a dictionary."""
        return dict(self._shortcuts)

    def from_dict(self, data):
        """Loads shortcuts from a dictionary, only updating known keys."""
        for key in DEFAULT_SHORTCUTS:
            if key in data:
                self._shortcuts[key] = data[key]

    def export_json(self, file_path):
        """Exports shortcuts to a JSON file."""
        with open(file_path, 'w') as f:
            json.dump(self._shortcuts, f, indent=2)

    def import_json(self, file_path):
        """Imports shortcuts from a JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)
        self.from_dict(data)
