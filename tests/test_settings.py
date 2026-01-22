#!/usr/bin/env python
"""Tests for Settings class with proper isolation (uses temp files)."""
import os
import sys
import tempfile
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
libs_path = os.path.join(dir_name, '..', 'libs')
sys.path.insert(0, libs_path)
from settings import Settings


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


if __name__ == '__main__':
    unittest.main()
