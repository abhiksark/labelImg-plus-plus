# tests/core/test_shortcut_config.py
"""Tests for shortcut configuration import validation."""
import os
import sys
import shutil
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs.core.shortcut_config import ShortcutConfig, DEFAULT_SHORTCUTS


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


if __name__ == '__main__':
    unittest.main()
