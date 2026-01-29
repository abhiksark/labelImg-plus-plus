"""Qt smoke tests for labelImg++ application.

These tests verify that the application boots and basic operations don't crash.
Run with QT_QPA_PLATFORM=offscreen for headless CI environments.
"""
import os
import sys
import tempfile
import shutil
import unittest

# Set offscreen platform for headless testing if not already set
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..'))

from labelImgPlusPlus import get_main_app


class TestMainWindowSmoke(unittest.TestCase):
    """Smoke tests for MainWindow - verify app boots and basic ops don't crash."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests in this class."""
        cls.app, cls.win = get_main_app()
        cls.temp_dir = tempfile.mkdtemp()

    @classmethod
    def tearDownClass(cls):
        """Clean up after all tests."""
        cls.win.close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_app_boots(self):
        """Test that application boots without error."""
        self.assertIsNotNone(self.app)
        self.assertIsNotNone(self.win)

    def test_window_has_canvas(self):
        """Test that main window has a canvas widget."""
        self.assertIsNotNone(self.win.canvas)

    def test_window_has_label_list(self):
        """Test that main window has a label list widget."""
        self.assertIsNotNone(self.win.label_list)

    def test_initial_state(self):
        """Test initial state of the application."""
        # No file loaded initially
        self.assertIsNone(self.win.file_path)
        # Canvas should have no shapes
        self.assertEqual(len(self.win.canvas.shapes), 0)

    def test_toggle_draw_mode(self):
        """Test toggling draw mode doesn't crash."""
        # Toggle to create mode
        self.win.canvas.set_editing(False)
        self.assertTrue(self.win.canvas.drawing())

        # Toggle back to edit mode
        self.win.canvas.set_editing(True)
        self.assertTrue(self.win.canvas.editing())

    def test_zoom_actions_exist(self):
        """Test that zoom actions are properly set up."""
        # These should not raise
        self.assertIsNotNone(self.win.zoom_widget)

    def test_format_actions_exist(self):
        """Test that format selection actions exist."""
        # Should have format-related attributes
        self.assertTrue(hasattr(self.win, 'label_file_format'))


class TestUndoRedoIntegration(unittest.TestCase):
    """Integration tests for undo/redo functionality."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app, cls.win = get_main_app()

    @classmethod
    def tearDownClass(cls):
        """Clean up after tests."""
        cls.win.close()

    def setUp(self):
        """Clear state before each test."""
        self.win.canvas.shapes.clear()
        self.win.undo_stack.clear()

    def test_undo_stack_exists(self):
        """Test that undo stack is properly initialized."""
        self.assertIsNotNone(self.win.undo_stack)

    def test_initial_undo_state(self):
        """Test initial undo/redo state."""
        self.assertFalse(self.win.undo_stack.can_undo())
        self.assertFalse(self.win.undo_stack.can_redo())


if __name__ == '__main__':
    unittest.main()
