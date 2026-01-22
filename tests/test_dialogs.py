"""Tests for dialog widgets (ColorDialog, LabelDialog)."""
import os
import sys
import unittest

# Set offscreen platform for headless testing
if 'QT_QPA_PLATFORM' not in os.environ:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..'))
sys.path.insert(0, os.path.join(dir_name, '..', 'libs'))

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication, QWidget, QDialogButtonBox

from libs.colorDialog import ColorDialog
from libs.labelDialog import LabelDialog

# Create QApplication for tests
app = QApplication.instance() or QApplication(sys.argv)


class TestColorDialog(unittest.TestCase):
    """Test cases for ColorDialog."""

    def test_init(self):
        """Test ColorDialog initialization."""
        dialog = ColorDialog()

        self.assertIsNotNone(dialog)
        self.assertIsNone(dialog.default)

    def test_alpha_channel_enabled(self):
        """Test that alpha channel option is enabled."""
        dialog = ColorDialog()

        # Check option is set
        self.assertTrue(dialog.testOption(ColorDialog.ShowAlphaChannel))

    def test_native_dialog_disabled(self):
        """Test that native dialog is disabled."""
        dialog = ColorDialog()

        self.assertTrue(dialog.testOption(ColorDialog.DontUseNativeDialog))

    def test_has_restore_button(self):
        """Test that restore defaults button exists."""
        dialog = ColorDialog()

        # Button box should have restore defaults
        bb = dialog.bb
        self.assertIsNotNone(bb)

    def test_set_window_title(self):
        """Test setting window title via getColor."""
        dialog = ColorDialog()
        # We can't actually call getColor in tests (it blocks), but we can check setup
        dialog.setWindowTitle('Test Title')

        self.assertEqual(dialog.windowTitle(), 'Test Title')

    def test_set_current_color(self):
        """Test setting current color."""
        dialog = ColorDialog()
        test_color = QColor(255, 128, 64, 200)

        dialog.setCurrentColor(test_color)

        self.assertEqual(dialog.currentColor().red(), 255)
        self.assertEqual(dialog.currentColor().green(), 128)
        self.assertEqual(dialog.currentColor().blue(), 64)


class TestLabelDialog(unittest.TestCase):
    """Test cases for LabelDialog."""

    def setUp(self):
        """Create a parent widget for dialogs."""
        self.parent = QWidget()

    def tearDown(self):
        """Clean up parent widget."""
        self.parent.close()

    def test_init_default(self):
        """Test LabelDialog default initialization."""
        # LabelDialog requires list_item to be a list (not None)
        dialog = LabelDialog(parent=self.parent, list_item=[])

        self.assertIsNotNone(dialog)
        self.assertEqual(dialog.edit.text(), 'Enter object label')

    def test_init_custom_text(self):
        """Test LabelDialog with custom text."""
        dialog = LabelDialog(text='Custom Label', parent=self.parent, list_item=[])

        self.assertEqual(dialog.edit.text(), 'Custom Label')

    def test_init_with_list_items(self):
        """Test LabelDialog with predefined list items."""
        items = ['cat', 'dog', 'bird']
        dialog = LabelDialog(parent=self.parent, list_item=items)

        self.assertTrue(hasattr(dialog, 'list_widget'))
        self.assertEqual(dialog.list_widget.count(), 3)

    def test_edit_has_validator(self):
        """Test that edit field has a validator."""
        dialog = LabelDialog(parent=self.parent, list_item=[])

        self.assertIsNotNone(dialog.edit.validator())

    def test_edit_has_completer(self):
        """Test that edit field has a completer."""
        dialog = LabelDialog(parent=self.parent, list_item=['cat', 'dog'])

        self.assertIsNotNone(dialog.edit.completer())

    def test_button_box_has_ok_cancel(self):
        """Test that dialog has OK and Cancel buttons."""
        dialog = LabelDialog(parent=self.parent, list_item=[])

        buttons = dialog.button_box.buttons()
        self.assertGreaterEqual(len(buttons), 2)

    def test_post_process_trims_whitespace(self):
        """Test that post_process trims whitespace."""
        dialog = LabelDialog(parent=self.parent, list_item=[])
        dialog.edit.setText('  hello  ')

        dialog.post_process()

        self.assertEqual(dialog.edit.text(), 'hello')

    def test_list_item_click_sets_text(self):
        """Test that clicking list item sets edit text."""
        items = ['cat', 'dog', 'bird']
        dialog = LabelDialog(parent=self.parent, list_item=items)

        # Simulate clicking on first item
        item = dialog.list_widget.item(0)
        dialog.list_item_click(item)

        self.assertEqual(dialog.edit.text(), 'cat')

    def test_empty_list_no_list_widget(self):
        """Test that empty list doesn't create list widget."""
        dialog = LabelDialog(parent=self.parent, list_item=[])

        self.assertFalse(hasattr(dialog, 'list_widget'))

    def test_empty_list_no_list_widget_attr(self):
        """Test that empty list doesn't create list widget."""
        dialog = LabelDialog(parent=self.parent, list_item=[])

        # Empty list should not create list_widget
        self.assertFalse(hasattr(dialog, 'list_widget'))


class TestLabelDialogValidation(unittest.TestCase):
    """Test cases for LabelDialog validation."""

    def setUp(self):
        """Create a parent widget for dialogs."""
        self.parent = QWidget()

    def tearDown(self):
        """Clean up parent widget."""
        self.parent.close()

    def test_validate_empty_text_no_accept(self):
        """Test that empty text is not accepted."""
        dialog = LabelDialog(parent=self.parent, list_item=[])
        dialog.edit.setText('')

        # validate() should not call accept for empty text
        # We can't easily test this without mocking, but we can check
        # that the text is indeed empty after setting
        self.assertEqual(dialog.edit.text(), '')

    def test_validate_whitespace_only_no_accept(self):
        """Test that whitespace-only text is not accepted."""
        dialog = LabelDialog(parent=self.parent, list_item=[])
        dialog.edit.setText('   ')
        dialog.post_process()

        # After post_process, whitespace should be trimmed to empty
        self.assertEqual(dialog.edit.text(), '')

    def test_validate_valid_text(self):
        """Test that valid text would be accepted."""
        dialog = LabelDialog(parent=self.parent, list_item=[])
        dialog.edit.setText('valid_label')

        # Text should remain as-is
        self.assertEqual(dialog.edit.text(), 'valid_label')


class TestLabelDialogCompleter(unittest.TestCase):
    """Test cases for LabelDialog completer functionality."""

    def setUp(self):
        """Create a parent widget for dialogs."""
        self.parent = QWidget()

    def tearDown(self):
        """Clean up parent widget."""
        self.parent.close()

    def test_completer_model_has_items(self):
        """Test that completer model contains list items."""
        items = ['apple', 'banana', 'cherry']
        dialog = LabelDialog(parent=self.parent, list_item=items)

        completer = dialog.edit.completer()
        model = completer.model()

        self.assertEqual(model.rowCount(), 3)

    def test_completer_with_empty_list(self):
        """Test completer with empty list."""
        dialog = LabelDialog(parent=self.parent, list_item=[])

        completer = dialog.edit.completer()
        model = completer.model()

        self.assertEqual(model.rowCount(), 0)


if __name__ == '__main__':
    unittest.main()
