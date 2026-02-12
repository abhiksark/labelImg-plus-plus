# tests/test_stats_widget.py
"""Tests for StatsWidget annotation statistics dashboard (Issue #19)."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt5.QtWidgets import QApplication
from libs.widgets.statsWidget import StatsWidget


class TestStatsWidgetInit(unittest.TestCase):
    """Tests for StatsWidget initialization."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_creates_successfully(self):
        """Test that StatsWidget can be created."""
        widget = StatsWidget()
        self.assertIsNotNone(widget)

    def test_has_required_labels(self):
        """Test that widget has required UI elements."""
        widget = StatsWidget()
        self.assertIsNotNone(widget.total_images_label)
        self.assertIsNotNone(widget.annotated_label)
        self.assertIsNotNone(widget.verified_label)
        self.assertIsNotNone(widget.progress_bar)

    def test_has_label_table(self):
        """Test that widget has label distribution table."""
        widget = StatsWidget()
        self.assertIsNotNone(widget.label_table)
        self.assertEqual(widget.label_table.columnCount(), 2)

    def test_has_current_image_labels(self):
        """Test that widget has current image stats labels."""
        widget = StatsWidget()
        self.assertIsNotNone(widget.current_annotations_label)
        self.assertIsNotNone(widget.current_labels_label)

    def test_has_refresh_button(self):
        """Test that widget has refresh button."""
        widget = StatsWidget()
        self.assertIsNotNone(widget.refresh_btn)


class TestStatsWidgetDatasetStats(unittest.TestCase):
    """Tests for dataset statistics updates."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_update_dataset_stats_zero(self):
        """Test updating with zero images."""
        widget = StatsWidget()
        widget.update_dataset_stats(0, 0, 0)

        self.assertIn('0', widget.total_images_label.text())
        self.assertEqual(widget.progress_bar.value(), 0)

    def test_update_dataset_stats_with_data(self):
        """Test updating with actual data."""
        widget = StatsWidget()
        widget.update_dataset_stats(100, 80, 50)

        self.assertIn('100', widget.total_images_label.text())
        self.assertIn('80', widget.annotated_label.text())
        self.assertIn('80%', widget.annotated_label.text())
        self.assertIn('50', widget.verified_label.text())
        self.assertIn('50%', widget.verified_label.text())
        self.assertEqual(widget.progress_bar.value(), 80)

    def test_get_dataset_stats(self):
        """Test retrieving dataset stats."""
        widget = StatsWidget()
        widget.update_dataset_stats(150, 120, 90)

        stats = widget.get_dataset_stats()
        self.assertEqual(stats['total'], 150)
        self.assertEqual(stats['annotated'], 120)
        self.assertEqual(stats['verified'], 90)


class TestStatsWidgetLabelDistribution(unittest.TestCase):
    """Tests for label distribution updates."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_update_label_distribution_empty(self):
        """Test updating with no labels."""
        widget = StatsWidget()
        widget.update_label_distribution({})

        self.assertEqual(widget.label_table.rowCount(), 0)

    def test_update_label_distribution_with_data(self):
        """Test updating with label data."""
        widget = StatsWidget()
        labels = {'person': 45, 'car': 30, 'dog': 15}
        widget.update_label_distribution(labels)

        self.assertEqual(widget.label_table.rowCount(), 3)

    def test_label_distribution_sorted_by_count(self):
        """Test that labels are sorted by count descending."""
        widget = StatsWidget()
        labels = {'dog': 10, 'person': 50, 'car': 25}
        widget.update_label_distribution(labels)

        # First row should be 'person' with highest count
        first_label = widget.label_table.item(0, 0).text()
        first_count = widget.label_table.item(0, 1).text()
        self.assertEqual(first_label, 'person')
        self.assertEqual(first_count, '50')

    def test_get_label_counts(self):
        """Test retrieving label counts."""
        widget = StatsWidget()
        labels = {'person': 45, 'car': 30}
        widget.update_label_distribution(labels)

        counts = widget.get_label_counts()
        self.assertEqual(counts['person'], 45)
        self.assertEqual(counts['car'], 30)


class TestStatsWidgetCurrentImage(unittest.TestCase):
    """Tests for current image statistics updates."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_update_current_image_no_annotations(self):
        """Test updating with no annotations."""
        widget = StatsWidget()
        widget.update_current_image_stats(0, [])

        self.assertIn('0', widget.current_annotations_label.text())
        self.assertIn('-', widget.current_labels_label.text())

    def test_update_current_image_with_annotations(self):
        """Test updating with annotations."""
        widget = StatsWidget()
        widget.update_current_image_stats(5, ['person', 'car', 'person', 'dog'])

        self.assertIn('5', widget.current_annotations_label.text())
        # Should show unique labels
        self.assertIn('car', widget.current_labels_label.text())
        self.assertIn('dog', widget.current_labels_label.text())
        self.assertIn('person', widget.current_labels_label.text())

    def test_get_current_image_stats(self):
        """Test retrieving current image stats."""
        widget = StatsWidget()
        widget.update_current_image_stats(3, ['cat', 'dog'])

        stats = widget.get_current_image_stats()
        self.assertEqual(stats['annotations'], 3)
        self.assertEqual(stats['labels'], ['cat', 'dog'])


class TestStatsWidgetClear(unittest.TestCase):
    """Tests for clearing statistics."""

    @classmethod
    def setUpClass(cls):
        """Create app once for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_clear_stats(self):
        """Test clearing all statistics."""
        widget = StatsWidget()

        # Set some data first
        widget.update_dataset_stats(100, 80, 50)
        widget.update_label_distribution({'person': 45})
        widget.update_current_image_stats(5, ['person'])

        # Clear
        widget.clear_stats()

        # Verify cleared
        stats = widget.get_dataset_stats()
        self.assertEqual(stats['total'], 0)
        self.assertEqual(widget.label_table.rowCount(), 0)
        self.assertEqual(widget.get_current_image_stats()['annotations'], 0)


if __name__ == '__main__':
    unittest.main()
