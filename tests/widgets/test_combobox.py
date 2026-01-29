#!/usr/bin/env python
# tests/widgets/test_combobox.py
"""Tests for ComboBox and DefaultLabelComboBox widgets."""
import os
import sys
import unittest

if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication, QWidget

from libs.widgets.combobox import ComboBox
from libs.widgets.default_label_combobox import DefaultLabelComboBox


class MockComboBoxParent(QWidget):
    """Mock parent widget for ComboBox that has required callback."""

    def __init__(self):
        super().__init__()
        self.selection_changed_calls = []

    def combo_selection_changed(self, index):
        """Handle combo selection change."""
        self.selection_changed_calls.append(index)


class MockDefaultLabelParent(QWidget):
    """Mock parent widget for DefaultLabelComboBox."""

    def __init__(self):
        super().__init__()
        self.selection_changed_calls = []

    def default_label_combo_selection_changed(self, index):
        """Handle default label combo selection change."""
        self.selection_changed_calls.append(index)


class TestComboBox(unittest.TestCase):
    """Tests for ComboBox functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init(self):
        """Test ComboBox initializes with parent."""
        parent = MockComboBoxParent()
        combo = ComboBox(parent=parent)
        self.assertIsNotNone(combo)

    def test_init_with_items(self):
        """Test ComboBox initializes with items."""
        parent = MockComboBoxParent()
        items = ['car', 'person', 'bike']
        combo = ComboBox(parent=parent, items=items)
        self.assertEqual(combo.cb.count(), 3)

    def test_current_text(self):
        """Test getting current text."""
        parent = MockComboBoxParent()
        items = ['car', 'person', 'bike']
        combo = ComboBox(parent=parent, items=items)
        combo.cb.setCurrentIndex(1)
        self.assertEqual(combo.cb.currentText(), 'person')

    def test_update_items(self):
        """Test updating items in ComboBox."""
        parent = MockComboBoxParent()
        combo = ComboBox(parent=parent, items=['a', 'b'])
        self.assertEqual(combo.cb.count(), 2)

        combo.update_items(['x', 'y', 'z'])
        self.assertEqual(combo.cb.count(), 3)
        self.assertEqual(combo.cb.itemText(0), 'x')

    def test_selection_changed_callback(self):
        """Test that selection change triggers parent callback."""
        parent = MockComboBoxParent()
        items = ['car', 'person', 'bike']
        combo = ComboBox(parent=parent, items=items)

        # Change selection
        combo.cb.setCurrentIndex(2)

        self.assertIn(2, parent.selection_changed_calls)


class TestDefaultLabelComboBox(unittest.TestCase):
    """Tests for DefaultLabelComboBox functionality."""

    @classmethod
    def setUpClass(cls):
        """Create QApplication for widget tests."""
        if not QApplication.instance():
            cls.app = QApplication([])
        else:
            cls.app = QApplication.instance()

    def test_init_with_items(self):
        """Test DefaultLabelComboBox initializes with items."""
        parent = MockDefaultLabelParent()
        items = ['car', 'person', 'bike']
        combo = DefaultLabelComboBox(parent=parent, items=items)
        self.assertIsNotNone(combo)
        self.assertEqual(combo.cb.count(), len(items))

    def test_current_text(self):
        """Test getting current text from combobox."""
        parent = MockDefaultLabelParent()
        items = ['car', 'person', 'bike']
        combo = DefaultLabelComboBox(parent=parent, items=items)
        combo.cb.setCurrentIndex(1)
        self.assertEqual(combo.cb.currentText(), 'person')

    def test_selection_changed_callback(self):
        """Test that selection change triggers parent callback."""
        parent = MockDefaultLabelParent()
        items = ['car', 'person', 'bike']
        combo = DefaultLabelComboBox(parent=parent, items=items)

        # Change selection
        combo.cb.setCurrentIndex(2)

        self.assertIn(2, parent.selection_changed_calls)


if __name__ == '__main__':
    unittest.main()
