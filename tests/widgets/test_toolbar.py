#!/usr/bin/env python
# tests/widgets/test_toolbar.py
"""Tests for ToolBar and DropdownToolButton widgets."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication, QMainWindow, QAction
from PyQt5.QtCore import QSize

from libs.widgets.toolBar import ToolBar, DropdownToolButton, ToolButton


class TestToolBar(unittest.TestCase):
    """Tests for ToolBar functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()
        cls.main_window = QMainWindow()

    def test_init(self):
        """Test ToolBar initializes."""
        toolbar = ToolBar('Test Toolbar')
        self.assertIsNotNone(toolbar)
        self.assertEqual(toolbar.windowTitle(), 'Test Toolbar')

    def test_add_action_returns_button(self):
        """Test adding action to ToolBar returns ToolButton."""
        toolbar = ToolBar('Test Toolbar')
        action = QAction('Test Action', None)
        btn = toolbar.addAction(action)
        # addAction returns a ToolButton wrapping the action
        self.assertIsInstance(btn, ToolButton)
        self.assertEqual(btn.defaultAction(), action)

    def test_icon_size_set(self):
        """Test toolbar has icon size set."""
        toolbar = ToolBar('Test Toolbar')
        icon_size = toolbar.iconSize()
        self.assertIsInstance(icon_size, QSize)
        self.assertGreater(icon_size.width(), 0)
        self.assertGreater(icon_size.height(), 0)

    def test_update_icon_size(self):
        """Test updating icon size."""
        toolbar = ToolBar('Test Toolbar')
        toolbar.update_icon_size(32)
        self.assertEqual(toolbar.iconSize().width(), 32)
        self.assertEqual(toolbar.iconSize().height(), 32)

    def test_expanded_state_initial(self):
        """Test initial expanded state is False."""
        toolbar = ToolBar('Test Toolbar')
        self.assertFalse(toolbar.is_expanded())

    def test_set_expanded(self):
        """Test setting expanded state."""
        toolbar = ToolBar('Test Toolbar')
        toolbar.add_expand_button()
        toolbar.set_expanded(True)
        self.assertTrue(toolbar.is_expanded())


class TestDropdownToolButton(unittest.TestCase):
    """Tests for DropdownToolButton functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init(self):
        """Test DropdownToolButton initializes with text."""
        button = DropdownToolButton('Test')
        self.assertIsNotNone(button)
        self.assertEqual(button.text(), 'Test')

    def test_add_actions(self):
        """Test adding actions to dropdown menu."""
        button = DropdownToolButton('Main')

        sub_action = QAction('Sub', None)
        button.add_action(sub_action)

        # Should have actions in menu
        self.assertIsNotNone(button.menu())
        self.assertEqual(len(button.menu().actions()), 1)

    def test_init_with_actions(self):
        """Test DropdownToolButton initializes with actions."""
        action1 = QAction('Action 1', None)
        action2 = QAction('Action 2', None)
        button = DropdownToolButton('Test', actions=[action1, action2])

        self.assertEqual(len(button.menu().actions()), 2)

    def test_update_icon_size(self):
        """Test updating icon size."""
        button = DropdownToolButton('Test')
        button.update_icon_size(32)
        self.assertEqual(button.iconSize().width(), 32)


class TestToolButton(unittest.TestCase):
    """Tests for ToolButton functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init(self):
        """Test ToolButton initializes."""
        button = ToolButton()
        self.assertIsNotNone(button)

    def test_init_with_icon_size(self):
        """Test ToolButton initializes with icon size."""
        button = ToolButton(icon_size=32)
        self.assertEqual(button.iconSize().width(), 32)

    def test_update_icon_size(self):
        """Test updating icon size."""
        button = ToolButton()
        button.update_icon_size(48)
        self.assertEqual(button.iconSize().width(), 48)


if __name__ == '__main__':
    unittest.main()
