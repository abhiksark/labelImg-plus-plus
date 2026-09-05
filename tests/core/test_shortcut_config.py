# tests/core/test_shortcut_config.py
"""Tests for shortcut configuration import validation."""
import os
import sys
import shutil
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.core.shortcut_config import (  # noqa: E402
    DEFAULT_SHORTCUTS,
    ShortcutConfig,
)


class TestShortcutConfigImport(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.cfg = ShortcutConfig()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _write(self, content):
        path = os.path.join(self.d, 's.json')
        with open(path, 'w') as f:
            f.write(content)
        return path

    def test_import_malformed_json_raises_valueerror(self):
        with self.assertRaises(ValueError):
            self.cfg.import_json(self._write('{ not valid json'))

    def test_import_non_object_raises_valueerror(self):
        # A bare JSON number must be rejected cleanly (was a raw TypeError).
        with self.assertRaises(ValueError):
            self.cfg.import_json(self._write('123'))

    def test_from_dict_ignores_non_string_values(self):
        self.cfg.from_dict({'open': 123, 'save': 'Ctrl+Shift+K'})
        self.assertEqual(self.cfg.get('open'), DEFAULT_SHORTCUTS['open'])
        self.assertEqual(self.cfg.get('save'), 'Ctrl+Shift+K')

    def test_from_dict_tolerates_non_dict(self):
        self.cfg.from_dict([1, 2, 3])   # must not raise
        self.cfg.from_dict('garbage')   # must not raise
        self.assertEqual(self.cfg.get('open'), DEFAULT_SHORTCUTS['open'])

    def test_import_valid_applies(self):
        self.cfg.import_json(self._write('{"save": "Ctrl+K"}'))
        self.assertEqual(self.cfg.get('save'), 'Ctrl+K')

    def test_completion_action_has_a_dedicated_default_shortcut(self):
        self.assertEqual(DEFAULT_SHORTCUTS['complete_item'], 'E')
        self.assertEqual(self.cfg.get('complete_item'), 'E')

    def test_plugin_override_is_retained_while_command_is_hidden(self):
        command = 'plugin.com.example.review.run'
        self.cfg.from_dict({command: 'Ctrl+Alt+R'})
        self.assertNotIn(command, self.cfg.get_all())
        self.assertEqual(self.cfg.to_dict()[command], 'Ctrl+Alt+R')

        self.assertEqual(
            self.cfg.register_plugin(
                command, 'Ctrl+R', 'com.example.review'), 'Ctrl+Alt+R')
        self.assertEqual(self.cfg.get_all()[command], 'Ctrl+Alt+R')
        self.cfg.unregister_plugin(command)
        self.assertNotIn(command, self.cfg.get_all())
        self.assertEqual(self.cfg.to_dict()[command], 'Ctrl+Alt+R')

        self.cfg.register_plugin(command, 'Ctrl+R', 'com.example.review')
        self.cfg.unregister_plugin(command, retain=False)
        self.assertNotIn(command, self.cfg.to_dict())

    def test_dynamic_reset_conflicts_and_forget(self):
        command = 'plugin.com.example.review.run'
        self.cfg.register_plugin(
            command, 'Ctrl+Alt+R', 'com.example.review')
        self.cfg.set(command, 'Ctrl+Q')
        self.assertEqual(self.cfg.find_conflict('Ctrl+Q', command), 'quit')
        self.cfg.reset(command)
        self.assertEqual(self.cfg.get(command), 'Ctrl+Alt+R')
        self.cfg.set(command, 'Ctrl+Shift+R')
        self.cfg.forget_plugin('com.example.review')
        self.assertNotIn(command, self.cfg.to_dict())

    def test_customized_builtin_is_visible_and_conflicts(self):
        self.cfg.set('save', 'Ctrl+9')
        self.assertEqual(self.cfg.get_all()['save'], 'Ctrl+9')
        self.assertEqual(self.cfg.find_conflict('Ctrl+9'), 'save')
        self.assertIsNone(
            self.cfg.find_conflict(DEFAULT_SHORTCUTS['save']))

    def test_forget_plugin_keeps_dot_prefixed_plugin_commands(self):
        short_command = 'plugin.a.run'
        long_command = 'plugin.a.b.run'
        self.cfg.register_plugin(short_command, 'Ctrl+1', 'a')
        self.cfg.register_plugin(long_command, 'Ctrl+2', 'a.b')
        self.cfg.forget_plugin('a')
        self.assertNotIn(short_command, self.cfg.to_dict())
        self.assertIn(long_command, self.cfg.to_dict())
        self.assertEqual(self.cfg.owner_for(long_command), 'a.b')

    def test_unknown_non_plugin_keys_are_rejected(self):
        self.cfg.from_dict({'not_a_real_action': 'Ctrl+9'})
        self.assertNotIn('not_a_real_action', self.cfg.to_dict())
        with self.assertRaises(KeyError):
            self.cfg.set('not_a_real_action', 'Ctrl+9')


if __name__ == '__main__':
    unittest.main()
