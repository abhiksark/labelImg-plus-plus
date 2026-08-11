# libs/core/shortcut_config.py
"""Keyboard shortcut configuration management."""

import json


DEFAULT_SHORTCUTS = {
    'quit': 'Ctrl+Q',
    'open': 'Ctrl+O',
    'open_video': 'Ctrl+Alt+V',
    'open_dir': 'Ctrl+U',
    'change_save_dir': 'Ctrl+R',
    'open_annotation': 'Ctrl+Shift+O',
    'copy_prev_bounding': 'Ctrl+Shift+V',
    'open_next_image': 'D',
    'open_prev_image': 'A',
    'verify': 'Space',
    'video_play_pause': 'Ctrl+Space',
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
    'create_polygon': 'P',
    'keypoint_mode': 'K',
    'sam_mode': 'S',
    'video_add_keyframe': 'Shift+K',
    'video_track_forward': 'T',
    'video_track_backward': 'Shift+T',
    'video_accept_suggestion': 'Shift+Enter',
    'video_reject_suggestion': 'Backspace',
}


class ShortcutConfig:
    """Manages keyboard shortcut configuration."""

    def __init__(self):
        self._dynamic_defaults = {}
        self._plugin_owners = {}
        self._shortcuts = dict(DEFAULT_SHORTCUTS)

    def get(self, action_name):
        """Returns the shortcut for the given action name, or None."""
        return self._shortcuts.get(action_name)

    def set(self, action_name, shortcut):
        """Sets the shortcut for the given action name."""
        if action_name not in DEFAULT_SHORTCUTS \
                and action_name not in self._dynamic_defaults:
            raise KeyError('unknown shortcut action: %s' % action_name)
        if not isinstance(shortcut, str):
            raise TypeError('shortcut must be a string')
        self._shortcuts[action_name] = shortcut

    def register_plugin(self, action_name, default_shortcut='', plugin_id=None):
        """Register a live plugin command while retaining stored overrides."""
        if not isinstance(action_name, str) \
                or not action_name.startswith('plugin.'):
            raise ValueError('plugin shortcut IDs must start with plugin.')
        if not isinstance(default_shortcut, str):
            raise TypeError('default shortcut must be a string')
        if plugin_id is not None \
                and (not isinstance(plugin_id, str) or not plugin_id):
            raise ValueError('plugin owner must be a non-empty string')
        self._dynamic_defaults[action_name] = default_shortcut
        if plugin_id is not None:
            self._plugin_owners[action_name] = plugin_id
        self._shortcuts.setdefault(action_name, default_shortcut)
        return self._shortcuts[action_name]

    def unregister_plugin(self, action_name, retain=True):
        """Hide a plugin command, optionally discarding a staged default."""
        self._dynamic_defaults.pop(action_name, None)
        if not retain:
            self._shortcuts.pop(action_name, None)
            self._plugin_owners.pop(action_name, None)

    def forget_plugin(self, plugin_id):
        """Remove defaults and retained overrides for one forgotten plugin."""
        owned = {
            name for name, owner in self._plugin_owners.items()
            if owner == plugin_id
        }
        for name in owned:
            self._dynamic_defaults.pop(name, None)
            self._shortcuts.pop(name, None)
            self._plugin_owners.pop(name, None)

    def reset(self, action_name):
        """Resets a single action's shortcut to its default value."""
        default = self.get_default(action_name)
        if action_name in DEFAULT_SHORTCUTS \
                or action_name in self._dynamic_defaults:
            self._shortcuts[action_name] = default

    def reset_all(self):
        """Resets all shortcuts to their default values."""
        retained = {
            name: value for name, value in self._shortcuts.items()
            if name.startswith('plugin.')
            and name not in self._dynamic_defaults
        }
        self._shortcuts = dict(DEFAULT_SHORTCUTS)
        self._shortcuts.update(retained)
        self._shortcuts.update(self._dynamic_defaults)
        self._plugin_owners = {
            name: owner for name, owner in self._plugin_owners.items()
            if name in self._shortcuts
        }

    def get_all(self):
        """Returns a copy of all current shortcuts."""
        visible = {
            name: self._shortcuts.get(name, default)
            for name, default in DEFAULT_SHORTCUTS.items()
        }
        for name, default in self._dynamic_defaults.items():
            visible[name] = self._shortcuts.get(name, default)
        return visible

    def plugin_owners(self):
        """Return the persisted command-to-plugin ownership index."""
        return dict(self._plugin_owners)

    def restore_plugin_owners(self, owners):
        """Restore validated ownership for retained plugin shortcut keys."""
        self._plugin_owners = {}
        if not isinstance(owners, dict):
            return
        for name, owner in owners.items():
            if (isinstance(name, str) and name.startswith('plugin.')
                    and name in self._shortcuts
                    and isinstance(owner, str) and owner):
                self._plugin_owners[name] = owner

    def owner_for(self, action_name):
        return self._plugin_owners.get(action_name)

    def set_plugin_owner(self, action_name, plugin_id):
        if plugin_id is None:
            self._plugin_owners.pop(action_name, None)
        else:
            self._plugin_owners[action_name] = plugin_id

    def _snapshot(self):
        return (
            dict(self._shortcuts),
            dict(self._dynamic_defaults),
            dict(self._plugin_owners),
        )

    def _restore(self, snapshot):
        shortcuts, dynamic_defaults, plugin_owners = snapshot
        self._shortcuts = dict(shortcuts)
        self._dynamic_defaults = dict(dynamic_defaults)
        self._plugin_owners = dict(plugin_owners)

    def get_default(self, action_name):
        """Returns the default shortcut for the given action name."""
        if action_name in DEFAULT_SHORTCUTS:
            return DEFAULT_SHORTCUTS[action_name]
        return self._dynamic_defaults.get(action_name, '')

    def find_conflict(self, shortcut, exclude_action=None):
        """Return action name that has this shortcut, or None."""
        if not shortcut:
            return None
        for name, sc in self.get_all().items():
            if name != exclude_action and sc == shortcut:
                return name
        return None

    def to_dict(self):
        """Serializes shortcuts to a dictionary."""
        return dict(self._shortcuts)

    def from_dict(self, data):
        """Load shortcuts from a dictionary, updating only known keys with
        string values. Non-dict input and non-string values are ignored so a
        corrupt config can never crash the load."""
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if not isinstance(value, str):
                continue
            if key in DEFAULT_SHORTCUTS or (
                    isinstance(key, str) and key.startswith('plugin.')):
                self._shortcuts[key] = value

    def export_json(self, file_path):
        """Exports shortcuts to a JSON file."""
        with open(file_path, 'w') as f:
            json.dump(self._shortcuts, f, indent=2)

    def import_json(self, file_path):
        """Import shortcuts from a JSON file.

        Raises:
            ValueError: if the file cannot be read, is not valid JSON, or is
                not a JSON object of shortcuts.
        """
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError(f"Could not read shortcuts file: {e}")
        if not isinstance(data, dict):
            raise ValueError("Shortcuts file must be a JSON object")
        self.from_dict(data)
