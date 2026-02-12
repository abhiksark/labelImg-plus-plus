"""Tests for utility functions in libs/utils.py."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))
sys.path.insert(0, os.path.join(dir_name, '..', '..', 'libs'))

from PyQt5.QtWidgets import QApplication, QMenu, QToolBar, QWidget
from PyQt5.QtCore import QPointF

from libs.utils.utils import (
    Struct, new_action, new_icon, add_actions, format_shortcut,
    generate_color_by_text, natural_sort, distance, trimmed
)

# Create QApplication for tests
app = QApplication.instance() or QApplication(sys.argv)


class TestGenerateColorByText(unittest.TestCase):
    """Test cases for generate_color_by_text function."""

    def test_returns_valid_color(self):
        """Test that function returns a valid QColor."""
        res = generate_color_by_text('test')

        self.assertGreaterEqual(res.red(), 0)
        self.assertLessEqual(res.red(), 255)
        self.assertGreaterEqual(res.green(), 0)
        self.assertLessEqual(res.green(), 255)
        self.assertGreaterEqual(res.blue(), 0)
        self.assertLessEqual(res.blue(), 255)

    def test_unicode_text(self):
        """Test with unicode text."""
        res = generate_color_by_text(u'\u958B\u555F\u76EE\u9304')

        self.assertGreaterEqual(res.green(), 0)
        self.assertGreaterEqual(res.red(), 0)
        self.assertGreaterEqual(res.blue(), 0)

    def test_same_text_same_color(self):
        """Test that same text produces same color."""
        color1 = generate_color_by_text('person')
        color2 = generate_color_by_text('person')

        self.assertEqual(color1.red(), color2.red())
        self.assertEqual(color1.green(), color2.green())
        self.assertEqual(color1.blue(), color2.blue())

    def test_different_text_likely_different_color(self):
        """Test that different text likely produces different colors."""
        color1 = generate_color_by_text('cat')
        color2 = generate_color_by_text('dog')

        # At least one component should differ (with very high probability)
        different = (color1.red() != color2.red() or
                     color1.green() != color2.green() or
                     color1.blue() != color2.blue())
        self.assertTrue(different)

    def test_empty_string(self):
        """Test with empty string."""
        res = generate_color_by_text('')

        self.assertIsNotNone(res)


class TestNaturalSort(unittest.TestCase):
    """Test cases for natural_sort function."""

    def test_basic_natural_sort(self):
        """Test basic natural alphanumeric sorting."""
        items = ['f1', 'f11', 'f3']
        natural_sort(items)

        self.assertEqual(items, ['f1', 'f3', 'f11'])

    def test_sort_with_leading_zeros(self):
        """Test sorting with leading zeros."""
        items = ['img001', 'img010', 'img002']
        natural_sort(items)

        self.assertEqual(items, ['img001', 'img002', 'img010'])

    def test_sort_mixed_alpha_numeric(self):
        """Test sorting with mixed alpha and numeric."""
        items = ['a2b', 'a10b', 'a1b']
        natural_sort(items)

        self.assertEqual(items, ['a1b', 'a2b', 'a10b'])

    def test_sort_already_sorted(self):
        """Test sorting already sorted list."""
        items = ['a1', 'a2', 'a3']
        natural_sort(items)

        self.assertEqual(items, ['a1', 'a2', 'a3'])

    def test_sort_with_custom_key(self):
        """Test sorting with custom key function."""
        items = [{'name': 'f10'}, {'name': 'f2'}, {'name': 'f1'}]
        natural_sort(items, key=lambda x: x['name'])

        self.assertEqual([x['name'] for x in items], ['f1', 'f2', 'f10'])

    def test_sort_empty_list(self):
        """Test sorting empty list."""
        items = []
        natural_sort(items)

        self.assertEqual(items, [])

    def test_sort_single_item(self):
        """Test sorting single item list."""
        items = ['only']
        natural_sort(items)

        self.assertEqual(items, ['only'])


class TestDistance(unittest.TestCase):
    """Test cases for distance function."""

    def test_zero_distance(self):
        """Test distance of zero point."""
        p = QPointF(0, 0)
        self.assertEqual(distance(p), 0)

    def test_unit_distance_x(self):
        """Test distance along x axis."""
        p = QPointF(1, 0)
        self.assertEqual(distance(p), 1)

    def test_unit_distance_y(self):
        """Test distance along y axis."""
        p = QPointF(0, 1)
        self.assertEqual(distance(p), 1)

    def test_diagonal_distance(self):
        """Test diagonal distance (3-4-5 triangle)."""
        p = QPointF(3, 4)
        self.assertEqual(distance(p), 5)

    def test_negative_coordinates(self):
        """Test distance with negative coordinates."""
        p = QPointF(-3, -4)
        self.assertEqual(distance(p), 5)


class TestFormatShortcut(unittest.TestCase):
    """Test cases for format_shortcut function."""

    def test_basic_shortcut(self):
        """Test basic shortcut formatting."""
        result = format_shortcut('Ctrl+S')

        self.assertEqual(result, '<b>Ctrl</b>+<b>S</b>')

    def test_shortcut_with_shift(self):
        """Test shortcut with Shift modifier."""
        result = format_shortcut('Shift+Delete')

        self.assertEqual(result, '<b>Shift</b>+<b>Delete</b>')

    def test_shortcut_multi_plus(self):
        """Test shortcut with multiple plus signs."""
        result = format_shortcut('Ctrl+Shift+S')

        # Only splits on first +
        self.assertEqual(result, '<b>Ctrl</b>+<b>Shift+S</b>')


class TestTrimmed(unittest.TestCase):
    """Test cases for trimmed function."""

    def test_trim_whitespace(self):
        """Test trimming whitespace."""
        result = trimmed('  hello  ')

        self.assertEqual(result, 'hello')

    def test_trim_tabs(self):
        """Test trimming tabs."""
        result = trimmed('\thello\t')

        self.assertEqual(result, 'hello')

    def test_no_trim_needed(self):
        """Test string with no whitespace to trim."""
        result = trimmed('hello')

        self.assertEqual(result, 'hello')

    def test_empty_string(self):
        """Test empty string."""
        result = trimmed('')

        self.assertEqual(result, '')


class TestStruct(unittest.TestCase):
    """Test cases for Struct class."""

    def test_basic_struct(self):
        """Test basic Struct creation."""
        s = Struct(a=1, b='hello')

        self.assertEqual(s.a, 1)
        self.assertEqual(s.b, 'hello')

    def test_empty_struct(self):
        """Test empty Struct."""
        s = Struct()

        self.assertIsNotNone(s)

    def test_struct_update(self):
        """Test updating Struct attributes."""
        s = Struct(x=10)
        s.x = 20
        s.y = 30

        self.assertEqual(s.x, 20)
        self.assertEqual(s.y, 30)


class TestNewAction(unittest.TestCase):
    """Test cases for new_action function."""

    def test_basic_action(self):
        """Test creating basic action."""
        parent = QWidget()
        action = new_action(parent, 'Test Action')

        self.assertEqual(action.text(), 'Test Action')
        self.assertTrue(action.isEnabled())

    def test_action_disabled(self):
        """Test creating disabled action."""
        parent = QWidget()
        action = new_action(parent, 'Disabled', enabled=False)

        self.assertFalse(action.isEnabled())

    def test_action_checkable(self):
        """Test creating checkable action."""
        parent = QWidget()
        action = new_action(parent, 'Checkable', checkable=True)

        self.assertTrue(action.isCheckable())

    def test_action_with_tip(self):
        """Test creating action with tooltip."""
        parent = QWidget()
        action = new_action(parent, 'With Tip', tip='This is a tip')

        self.assertEqual(action.toolTip(), 'This is a tip')
        self.assertEqual(action.statusTip(), 'This is a tip')

    def test_action_with_shortcut(self):
        """Test creating action with shortcut."""
        parent = QWidget()
        action = new_action(parent, 'With Shortcut', shortcut='Ctrl+T')

        self.assertEqual(action.shortcut().toString(), 'Ctrl+T')

    def test_action_with_shortcut_list(self):
        """Test creating action with multiple shortcuts."""
        parent = QWidget()
        action = new_action(parent, 'Multi', shortcut=['Ctrl+A', 'Ctrl+B'])

        shortcuts = action.shortcuts()
        self.assertEqual(len(shortcuts), 2)


class TestAddActions(unittest.TestCase):
    """Test cases for add_actions function."""

    def test_add_action_to_toolbar(self):
        """Test adding action to toolbar."""
        toolbar = QToolBar()
        parent = QWidget()
        action = new_action(parent, 'Test')

        add_actions(toolbar, [action])

        self.assertEqual(len(toolbar.actions()), 1)

    def test_add_separator(self):
        """Test adding separator (None) to toolbar."""
        toolbar = QToolBar()
        parent = QWidget()
        action1 = new_action(parent, 'Action1')
        action2 = new_action(parent, 'Action2')

        add_actions(toolbar, [action1, None, action2])

        # Should have 3 items: action, separator, action
        self.assertEqual(len(toolbar.actions()), 3)

    def test_add_menu_to_menubar(self):
        """Test adding menu to menubar."""
        from PyQt5.QtWidgets import QMenuBar
        menubar = QMenuBar()
        menu = QMenu('Test Menu')

        add_actions(menubar, [menu])

        # Menu should be added
        self.assertGreaterEqual(len(menubar.actions()), 1)


if __name__ == '__main__':
    unittest.main()
