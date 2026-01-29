# tests/test_label_dialog.py
"""Tests for LabelDialog search/filter functionality (Issue #10)."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication
from libs.widgets.labelDialog import LabelDialog


class TestLabelDialogFilter(unittest.TestCase):
    """Tests for label dialog search/filter feature."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])
        cls.labels = ['person', 'car', 'bicycle', 'dog', 'cat', 'person_sitting']

    def test_dialog_with_labels_has_filter(self):
        """Test that dialog with labels has filter widget."""
        dialog = LabelDialog(list_item=self.labels)
        self.assertTrue(hasattr(dialog, 'filter_edit'))
        self.assertTrue(hasattr(dialog, 'list_widget'))
        self.assertTrue(hasattr(dialog, 'count_label'))

    def test_dialog_without_labels_no_filter(self):
        """Test that dialog without labels has no filter widget."""
        dialog = LabelDialog(list_item=[])
        self.assertFalse(hasattr(dialog, 'filter_edit'))

    def test_filter_hides_non_matching_items(self):
        """Test that filter hides items not matching search text."""
        dialog = LabelDialog(list_item=self.labels)

        # Filter by 'car'
        dialog._filter_list('car')

        visible_count = 0
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if not item.isHidden():
                visible_count += 1
                self.assertIn('car', item.text().lower())

        self.assertEqual(visible_count, 1)  # Only 'car' should be visible

    def test_filter_is_case_insensitive(self):
        """Test that filter matching is case insensitive."""
        dialog = LabelDialog(list_item=self.labels)

        # Filter with uppercase
        dialog._filter_list('CAR')

        visible_items = []
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if not item.isHidden():
                visible_items.append(item.text())

        self.assertIn('car', visible_items)

    def test_filter_partial_match(self):
        """Test that filter matches partial text."""
        dialog = LabelDialog(list_item=self.labels)

        # Filter by 'per' should match 'person' and 'person_sitting'
        dialog._filter_list('per')

        visible_items = []
        for i in range(dialog.list_widget.count()):
            item = dialog.list_widget.item(i)
            if not item.isHidden():
                visible_items.append(item.text())

        self.assertEqual(len(visible_items), 2)
        self.assertIn('person', visible_items)
        self.assertIn('person_sitting', visible_items)

    def test_empty_filter_shows_all(self):
        """Test that empty filter shows all items."""
        dialog = LabelDialog(list_item=self.labels)

        # First filter
        dialog._filter_list('car')
        # Then clear
        dialog._filter_list('')

        visible_count = 0
        for i in range(dialog.list_widget.count()):
            if not dialog.list_widget.item(i).isHidden():
                visible_count += 1

        self.assertEqual(visible_count, len(self.labels))

    def test_count_label_updates(self):
        """Test that count label updates on filter."""
        dialog = LabelDialog(list_item=self.labels)

        # Initial count
        self.assertEqual(dialog.count_label.text(), f"{len(self.labels)} labels")

        # After filter
        dialog._filter_list('per')
        self.assertIn('2 of', dialog.count_label.text())

        # After clearing
        dialog._filter_list('')
        self.assertEqual(dialog.count_label.text(), f"{len(self.labels)} labels")


if __name__ == '__main__':
    unittest.main()
