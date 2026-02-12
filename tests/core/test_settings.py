#!/usr/bin/env python
"""Tests for Settings class with proper isolation (uses temp files)."""
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
from libs.core.settings import Settings


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


if __name__ == '__main__':
    unittest.main()
