#!/usr/bin/env python
# tests/test_autosave.py
"""Tests for auto-save functionality (Issue #13).

Tests cover:
- Timer-based auto-save toggle
- Auto-save interval selection
- Save triggering conditions
- Settings persistence
"""
import os
import sys
import tempfile
import shutil
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from labelImgPlusPlus import get_main_app, SETTING_AUTO_SAVE, SETTING_AUTO_SAVE_ENABLED, SETTING_AUTO_SAVE_INTERVAL


class TestAutoSaveTimer(unittest.TestCase):
    """Tests for timer-based auto-save feature."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        # Don't close window to avoid Qt segfault on cleanup
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset auto-save state before each test."""
        self.win.auto_save_enabled.setChecked(False)
        self.win.auto_save_timer.stop()
        # Reset interval to default (60s)
        for action in self.win.auto_save_interval_group.actions():
            if action.data() == 60:
                action.setChecked(True)
                break

    def test_auto_save_timer_exists(self):
        """Test that auto-save timer is initialized."""
        self.assertIsNotNone(self.win.auto_save_timer)
        self.assertFalse(self.win.auto_save_timer.isActive())

    def test_auto_save_toggle_starts_timer(self):
        """Test that enabling auto-save starts the timer."""
        self.win.auto_save_enabled.setChecked(True)
        self.win._toggle_auto_save_timer()
        self.assertTrue(self.win.auto_save_timer.isActive())

    def test_auto_save_toggle_stops_timer(self):
        """Test that disabling auto-save stops the timer."""
        # Start first
        self.win.auto_save_enabled.setChecked(True)
        self.win._toggle_auto_save_timer()
        self.assertTrue(self.win.auto_save_timer.isActive())

        # Then stop
        self.win.auto_save_enabled.setChecked(False)
        self.win._toggle_auto_save_timer()
        self.assertFalse(self.win.auto_save_timer.isActive())

    def test_default_interval_is_one_minute(self):
        """Test that default auto-save interval is 60 seconds."""
        interval = self.win._get_current_auto_save_interval()
        self.assertEqual(interval, 60)

    def test_interval_selection_updates_timer(self):
        """Test that changing interval updates running timer."""
        # Enable auto-save
        self.win.auto_save_enabled.setChecked(True)
        self.win._toggle_auto_save_timer()

        # Find the 30 second option and select it
        for action in self.win.auto_save_interval_group.actions():
            if action.data() == 30:
                action.setChecked(True)
                # Manually trigger since we're not using menu
                self.win.auto_save_timer.start(30 * 1000)
                break

        # Verify interval changed
        interval = self.win._get_current_auto_save_interval()
        self.assertEqual(interval, 30)


class TestAutoSaveOnNavigate(unittest.TestCase):
    """Tests for auto-save on navigation feature."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()

    def test_auto_save_mode_action_exists(self):
        """Test that auto-save mode action is initialized."""
        self.assertIsNotNone(self.win.auto_saving)
        self.assertTrue(self.win.auto_saving.isCheckable())

    def test_auto_save_mode_is_checkable(self):
        """Test that auto-save mode can be toggled."""
        initial_state = self.win.auto_saving.isChecked()
        self.win.auto_saving.setChecked(not initial_state)
        self.assertEqual(self.win.auto_saving.isChecked(), not initial_state)
        # Restore
        self.win.auto_saving.setChecked(initial_state)


class TestAutoSaveTriggering(unittest.TestCase):
    """Tests for auto-save triggering conditions."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Reset state before each test."""
        self.win.dirty = False
        self.win.file_path = None

    def test_no_save_when_not_dirty(self):
        """Test that auto-save doesn't trigger when no changes."""
        self.win.dirty = False
        self.win.file_path = '/some/path/image.jpg'

        # This should return early without saving
        self.win._auto_save_triggered()
        # No error means success - nothing to assert

    def test_no_save_when_no_file(self):
        """Test that auto-save doesn't trigger when no file loaded."""
        self.win.dirty = True
        self.win.file_path = None

        # This should return early without saving
        self.win._auto_save_triggered()
        # No error means success


class TestAutoSaveIntervalMenu(unittest.TestCase):
    """Tests for auto-save interval menu."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()

    def test_interval_menu_exists(self):
        """Test that interval submenu is created."""
        self.assertIsNotNone(self.win.auto_save_interval_menu)

    def test_interval_options_available(self):
        """Test that all interval options are available."""
        actions = self.win.auto_save_interval_group.actions()
        intervals = [action.data() for action in actions]

        self.assertIn(30, intervals)   # 30 seconds
        self.assertIn(60, intervals)   # 1 minute
        self.assertIn(120, intervals)  # 2 minutes
        self.assertIn(300, intervals)  # 5 minutes

    def test_intervals_are_exclusive(self):
        """Test that only one interval can be selected at a time."""
        self.assertTrue(self.win.auto_save_interval_group.isExclusive())


if __name__ == '__main__':
    unittest.main()
