#!/usr/bin/env python
"""Tests for Settings class with proper isolation (uses temp files)."""
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
from libs.core.settings import Settings


class TestSettingsPath(unittest.TestCase):
    """Settings paths are explicit in tests and unchanged in production."""

    def test_pytest_session_uses_an_isolated_settings_file(self):
        """The suite must never construct Settings against the user file."""
        path = os.environ.get('LABELIMGPP_SETTINGS_PATH')

        self.assertIsNotNone(path)
        self.assertNotEqual(
            path, os.path.expanduser('~/.labelImgSettings.json'))
        self.assertTrue(
            os.path.basename(path).startswith('session-settings-'))

    def test_constructor_uses_exact_environment_override(self):
        """The supported override must select only the supplied test file."""
        path = '/tmp/labelimgpp-explicit-test-settings.json'
        with patch.dict(
                os.environ, {'LABELIMGPP_SETTINGS_PATH': path}, clear=False):
            settings = Settings()

        self.assertEqual(settings.path, path)

    def test_constructor_keeps_user_home_default_without_override(self):
        """Normal application launches retain the existing settings path."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('LABELIMGPP_SETTINGS_PATH', None)
            with patch('libs.core.settings.os.path.expanduser',
                       return_value='/example-user'):
                settings = Settings()

        self.assertEqual(
            settings.path, '/example-user/.labelImgSettings.json')

    def test_override_persists_across_separate_settings_instances(self):
        """A test session can intentionally share its isolated settings."""
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'session-settings.json')
            with patch.dict(
                    os.environ, {'LABELIMGPP_SETTINGS_PATH': path},
                    clear=False):
                first = Settings()
                first['shared'] = 'session-only'
                self.assertTrue(first.save())

                second = Settings()
                self.assertTrue(second.load())

        self.assertEqual(second.get('shared'), 'session-only')


class TestSettings(unittest.TestCase):
    """Test cases for Settings persistence."""

    def setUp(self):
        """Create a temp file for settings to avoid polluting user home."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pkl')
        self.temp_file.close()
        self.settings = Settings()
        self.settings.path = self.temp_file.name

    def tearDown(self):
        """Clean up temp file."""
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_set_and_get(self):
        """Test setting and getting values."""
        self.settings['test0'] = 'hello'
        self.settings['test1'] = 10
        self.settings['test2'] = [0, 2, 3]
        self.assertEqual(self.settings.get('test0'), 'hello')
        self.assertEqual(self.settings.get('test1'), 10)
        self.assertEqual(self.settings.get('test2'), [0, 2, 3])

    def test_get_with_default(self):
        """Test get() returns default for missing keys."""
        self.assertEqual(self.settings.get('nonexistent', 'default'), 'default')
        self.assertEqual(self.settings.get('missing', 42), 42)
        self.assertIsNone(self.settings.get('missing'))

    def test_save_and_load(self):
        """Test save/load roundtrip."""
        self.settings['key1'] = 'value1'
        self.settings['key2'] = 123
        self.assertTrue(self.settings.save())

        # Create a new settings instance and load
        new_settings = Settings()
        new_settings.path = self.temp_file.name
        self.assertTrue(new_settings.load())
        self.assertEqual(new_settings.get('key1'), 'value1')
        self.assertEqual(new_settings.get('key2'), 123)

    def test_reset(self):
        """Test reset clears data and removes file."""
        self.settings['key'] = 'value'
        self.settings.save()
        self.assertTrue(os.path.exists(self.temp_file.name))

        self.settings.reset()
        self.assertFalse(os.path.exists(self.temp_file.name))
        self.assertEqual(self.settings.data, {})

    def test_load_nonexistent_file(self):
        """Test load returns False for nonexistent file."""
        self.settings.path = '/nonexistent/path/settings.pkl'
        self.assertFalse(self.settings.load())


class TestSettingsEdgeCases(unittest.TestCase):
    """Edge case tests for Settings error handling."""

    def setUp(self):
        """Create a temp file for settings."""
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pkl')
        self.temp_file.close()
        self.settings = Settings()
        self.settings.path = self.temp_file.name

    def tearDown(self):
        """Clean up temp file."""
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_load_corrupted_pickle(self):
        """Test loading corrupted pickle file."""
        # Write invalid pickle data
        with open(self.temp_file.name, 'wb') as f:
            f.write(b'not a valid pickle file content')

        # Should return False, not crash
        result = self.settings.load()
        self.assertFalse(result)

    def test_load_empty_file(self):
        """Test loading empty file."""
        # File is already empty from temp creation
        result = self.settings.load()
        self.assertFalse(result)

    def test_save_overwrites_corrupted_file(self):
        """Test that save can overwrite corrupted file."""
        # Write invalid data first
        with open(self.temp_file.name, 'wb') as f:
            f.write(b'corrupted data')

        # Save should work and create valid pickle
        self.settings['key'] = 'value'
        result = self.settings.save()
        self.assertTrue(result)

        # Verify we can load it back
        new_settings = Settings()
        new_settings.path = self.temp_file.name
        self.assertTrue(new_settings.load())
        self.assertEqual(new_settings.get('key'), 'value')

    def test_many_recent_files(self):
        """Test handling many recent file entries."""
        # Add many recent files
        recent_files = [f'/path/to/file{i}.jpg' for i in range(100)]
        self.settings['recent_files'] = recent_files
        self.settings.save()

        # Load and verify
        new_settings = Settings()
        new_settings.path = self.temp_file.name
        new_settings.load()
        loaded_files = new_settings.get('recent_files')
        self.assertEqual(len(loaded_files), 100)

    def test_special_characters_in_values(self):
        """Test handling special characters in settings values."""
        self.settings['unicode_key'] = u'中文文字'
        self.settings['path_with_spaces'] = '/path/with spaces/file.jpg'
        self.settings['emoji'] = '🎨📷'
        self.settings.save()

        new_settings = Settings()
        new_settings.path = self.temp_file.name
        new_settings.load()

        self.assertEqual(new_settings.get('unicode_key'), u'中文文字')
        self.assertEqual(new_settings.get('path_with_spaces'), '/path/with spaces/file.jpg')
        self.assertEqual(new_settings.get('emoji'), '🎨📷')

    def test_nested_data_structures(self):
        """Test handling nested data structures."""
        self.settings['nested'] = {
            'level1': {
                'level2': {
                    'list': [1, 2, 3],
                    'dict': {'a': 'b'}
                }
            }
        }
        self.settings.save()

        new_settings = Settings()
        new_settings.path = self.temp_file.name
        new_settings.load()

        nested = new_settings.get('nested')
        self.assertEqual(nested['level1']['level2']['list'], [1, 2, 3])
        self.assertEqual(nested['level1']['level2']['dict']['a'], 'b')


class TestSettingsJsonMigration(unittest.TestCase):
    """Settings must persist as JSON, never via pickle (arbitrary-code-exec)."""

    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.json')
        self.temp_file.close()
        self.settings = Settings()
        self.settings.path = self.temp_file.name

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_saved_file_is_valid_json(self):
        """The on-disk settings file must be JSON text, not a pickle blob."""
        self.settings['key'] = 'value'
        self.settings['n'] = 7
        self.settings.save()

        with open(self.temp_file.name, 'r', encoding='utf-8') as f:
            data = json.load(f)  # raises if the file is a pickle
        self.assertEqual(data['key'], 'value')
        self.assertEqual(data['n'], 7)

    def test_load_does_not_execute_pickle_payload(self):
        """A malicious legacy pickle must NOT execute code when load() runs."""
        import pickle
        sentinel = tempfile.mktemp(prefix='labelimg_pwned_')

        class Exploit:
            def __reduce__(self):
                return (os.system, ('touch %s' % sentinel,))

        with open(self.temp_file.name, 'wb') as f:
            pickle.dump(Exploit(), f)

        try:
            self.settings.load()  # must not run the payload
            self.assertFalse(
                os.path.exists(sentinel),
                'pickle payload executed - settings.load() is unsafe')
        finally:
            if os.path.exists(sentinel):
                os.remove(sentinel)

    def test_qt_types_roundtrip(self):
        """QSize/QPoint/QColor/QByteArray/enum must survive a save/load cycle."""
        from PyQt5.QtCore import QByteArray, QPoint, QSize
        from PyQt5.QtGui import QColor
        from libs.formats.labelFile import LabelFileFormat

        self.settings['size'] = QSize(640, 480)
        self.settings['pos'] = QPoint(12, 34)
        self.settings['color'] = QColor(10, 20, 30, 200)
        self.settings['state'] = QByteArray(b'\x00\x01\x02\xff')
        self.settings['fmt'] = LabelFileFormat.YOLO
        self.settings.save()

        loaded = Settings()
        loaded.path = self.temp_file.name
        self.assertTrue(loaded.load())

        self.assertEqual(loaded.get('size'), QSize(640, 480))
        self.assertEqual(loaded.get('pos'), QPoint(12, 34))
        self.assertEqual(loaded.get('color'), QColor(10, 20, 30, 200))
        self.assertEqual(loaded.get('state'), QByteArray(b'\x00\x01\x02\xff'))
        self.assertEqual(loaded.get('fmt'), LabelFileFormat.YOLO)

    def test_reset_keeps_path_so_persistence_survives(self):
        """reset() must not null the path (which would disable all saving)."""
        self.settings['k'] = 'v'
        self.settings.save()
        self.settings.reset()

        self.assertEqual(self.settings.data, {})
        self.assertIsNotNone(self.settings.path)
        # Persistence still works after reset.
        self.settings['k2'] = 'v2'
        self.assertTrue(self.settings.save())


if __name__ == '__main__':
    unittest.main()
