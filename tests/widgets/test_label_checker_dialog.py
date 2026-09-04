"""Regressions for the label consistency dialog's read-only workflow."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

dir_name = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, os.path.join(dir_name, '..', '..'))

from PyQt6.QtWidgets import QApplication

from libs.tools.label_checker import LabelConsistencyChecker
from libs.widgets.labelCheckerDialog import LabelCheckerDialog


app = QApplication.instance() or QApplication([])


class TestLabelCheckerDialogReadOnlyFixes(unittest.TestCase):
    """Automatic fixes stay unavailable until rewriting is implemented."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dialog = LabelCheckerDialog(
            predefined_classes=['cat'],
            annotations_dir=self.temp_dir.name,
        )
        self.dialog.checker = LabelConsistencyChecker(['cat'])

    def tearDown(self):
        self.dialog.close()
        self.temp_dir.cleanup()

    def _scan_with_issue(self):
        with patch.object(
            LabelConsistencyChecker,
            'scan_annotations',
            return_value={
                'Cat': [os.path.join(self.temp_dir.name, 'image.xml')],
            },
        ):
            self.dialog._on_scan()

    def test_fix_button_remains_disabled_after_scan_finds_issue(self):
        self._scan_with_issue()

        self.assertEqual(self.dialog.table.rowCount(), 1)
        self.assertTrue(self.dialog.export_btn.isEnabled())
        self.assertFalse(self.dialog.fix_selected_btn.isEnabled())
        self.assertIn('Unavailable', self.dialog.fix_selected_btn.text())
        self.assertIn(
            'unavailable',
            self.dialog.fix_selected_btn.toolTip().lower(),
        )

        # Reviewing suggestions and changing the report selection remain usable.
        checkbox = self.dialog.table.cellWidget(0, 0)
        self.dialog._deselect_all()
        self.assertFalse(checkbox.isChecked())
        self.dialog._select_all()
        self.assertTrue(checkbox.isChecked())
        self.assertIn('cat', self.dialog.table.item(0, 3).text())

    def test_direct_fix_invocation_never_emits_or_claims_success(self):
        self._scan_with_issue()
        emitted = []
        self.dialog.fix_requested.connect(
            lambda old, new: emitted.append((old, new))
        )

        with patch(
            'libs.widgets.labelCheckerDialog.QMessageBox.information'
        ) as information, patch(
            'libs.widgets.labelCheckerDialog.QMessageBox.question'
        ) as question:
            result = self.dialog._fix_selected()

        self.assertFalse(result)
        self.assertEqual(emitted, [])
        self.assertFalse(self.dialog.fix_selected_btn.isEnabled())
        question.assert_not_called()
        information.assert_called_once()
        self.assertEqual(
            information.call_args.args[1],
            'Automatic Fixes Unavailable',
        )
        self.assertNotEqual(information.call_args.args[1], 'Fixes Applied')


if __name__ == '__main__':
    unittest.main()
