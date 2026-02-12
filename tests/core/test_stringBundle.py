"""Tests for StringBundle i18n functionality."""
import os
import sys
import unittest

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from libs import resources
from libs.utils.stringBundle import StringBundle


class TestStringBundle(unittest.TestCase):
    """Test cases for StringBundle internationalization."""

    def test_load_english_bundle(self):
        """Test loading the default English bundle."""
        str_bundle = StringBundle.get_bundle('en')
        self.assertEqual(str_bundle.get_string("openDir"), 'Open Dir')

    def test_load_traditional_chinese_bundle(self):
        """Test loading Traditional Chinese bundle with fallback."""
        str_bundle = StringBundle.get_bundle('zh-TW')
        self.assertEqual(str_bundle.get_string("openDir"), u'\u958B\u555F\u76EE\u9304')

    def test_invalid_locale_falls_back_to_english(self):
        """Test that invalid locale falls back to English."""
        # Save original env vars (use .get() to handle missing keys)
        prev_lc = os.environ.get('LC_ALL')
        prev_lang = os.environ.get('LANG')

        try:
            os.environ['LC_ALL'] = 'UTF-8'
            os.environ['LANG'] = 'UTF-8'
            str_bundle = StringBundle.get_bundle()
            self.assertEqual(str_bundle.get_string("openDir"), 'Open Dir')
        finally:
            # Restore original env vars
            if prev_lc is not None:
                os.environ['LC_ALL'] = prev_lc
            elif 'LC_ALL' in os.environ:
                del os.environ['LC_ALL']

            if prev_lang is not None:
                os.environ['LANG'] = prev_lang
            elif 'LANG' in os.environ:
                del os.environ['LANG']

    def test_get_string_raises_on_missing_id(self):
        """Test that get_string raises AssertionError for missing string ID."""
        str_bundle = StringBundle.get_bundle('en')
        with self.assertRaises(AssertionError):
            str_bundle.get_string("nonexistent_string_id")

    def test_get_bundle_with_explicit_none(self):
        """Test get_bundle with None locale auto-detects."""
        # Should not raise, will auto-detect or fallback to English
        str_bundle = StringBundle.get_bundle(None)
        self.assertIsNotNone(str_bundle)
        # Should at least have English strings
        result = str_bundle.get_string("openDir")
        self.assertIsNotNone(result)

    def test_multiple_string_keys_loaded(self):
        """Test that multiple strings are loaded from bundle."""
        str_bundle = StringBundle.get_bundle('en')
        # Verify multiple keys exist
        self.assertIsNotNone(str_bundle.get_string("openDir"))
        self.assertIsNotNone(str_bundle.get_string("save"))
        self.assertIsNotNone(str_bundle.get_string("quit"))

    def test_string_bundle_caches_id_to_message(self):
        """Test that StringBundle stores strings in id_to_message dict."""
        str_bundle = StringBundle.get_bundle('en')
        self.assertIsInstance(str_bundle.id_to_message, dict)
        self.assertIn("openDir", str_bundle.id_to_message)

    def test_fallback_path_includes_base_path(self):
        """Test that fallback paths always include base path."""
        str_bundle = StringBundle.get_bundle('de')
        # Even for German locale, should load some strings
        # (will have base English strings even if no German translation)
        self.assertIsNotNone(str_bundle.id_to_message)
        self.assertGreater(len(str_bundle.id_to_message), 0)


if __name__ == '__main__':
    unittest.main()
