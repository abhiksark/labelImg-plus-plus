# libs/widgets/labelCheckerDialog.py
"""Dialog for displaying and fixing label consistency issues."""

import os
from typing import Callable, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QProgressBar, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QCheckBox, QGroupBox
)
from PyQt5.QtGui import QColor

from libs.tools.label_checker import LabelConsistencyChecker, LabelIssue, IssueType


ISSUE_TYPE_NAMES = {
    IssueType.TYPO: "Typo",
    IssueType.CASE_MISMATCH: "Case Mismatch",
    IssueType.WHITESPACE: "Whitespace",
    IssueType.UNDEFINED: "Undefined",
    IssueType.DUPLICATE: "Duplicate",
}

ISSUE_TYPE_COLORS = {
    IssueType.TYPO: QColor(255, 200, 200),         # Light red
    IssueType.CASE_MISMATCH: QColor(255, 255, 200),  # Light yellow
    IssueType.WHITESPACE: QColor(255, 230, 200),   # Light orange
    IssueType.UNDEFINED: QColor(200, 200, 255),    # Light blue
    IssueType.DUPLICATE: QColor(255, 200, 255),    # Light purple
}


class LabelCheckerDialog(QDialog):
    """Dialog for checking and fixing label consistency issues."""

    fix_requested = pyqtSignal(str, str)  # old_label, new_label

    def __init__(
        self,
        parent=None,
        predefined_classes: Optional[List[str]] = None,
        annotations_dir: Optional[str] = None,
        save_dir: Optional[str] = None
    ):
        super().__init__(parent)
        self.predefined_classes = predefined_classes or []
        self.annotations_dir = annotations_dir
        self.save_dir = save_dir
        self.issues: List[LabelIssue] = []
        self.checker: Optional[LabelConsistencyChecker] = None

        self._setup_ui()
        self.setWindowTitle("Label Consistency Checker")
        self.resize(800, 500)

    def _setup_ui(self):
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Status section
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Ready to scan")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self.scan_button = QPushButton("Scan Dataset")
        self.scan_button.clicked.connect(self._on_scan)
        status_layout.addWidget(self.scan_button)
        layout.addLayout(status_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Summary section
        self.summary_group = QGroupBox("Summary")
        summary_layout = QHBoxLayout(self.summary_group)
        self.summary_labels = {}
        for issue_type in IssueType:
            label = QLabel(f"{ISSUE_TYPE_NAMES[issue_type]}: 0")
            self.summary_labels[issue_type] = label
            summary_layout.addWidget(label)
        summary_layout.addStretch()
        layout.addWidget(self.summary_group)

        # Issues table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "Select", "Type", "Label", "Suggestion", "Count", "Files"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table)

        # Action buttons
        button_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        button_layout.addWidget(self.select_all_btn)

        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        button_layout.addWidget(self.deselect_all_btn)

        button_layout.addStretch()

        self.fix_selected_btn = QPushButton("Fix Selected")
        self.fix_selected_btn.clicked.connect(self._fix_selected)
        self.fix_selected_btn.setEnabled(False)
        button_layout.addWidget(self.fix_selected_btn)

        self.export_btn = QPushButton("Export Report")
        self.export_btn.clicked.connect(self._export_report)
        self.export_btn.setEnabled(False)
        button_layout.addWidget(self.export_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def set_data(
        self,
        predefined_classes: List[str],
        annotations_dir: str,
        save_dir: Optional[str] = None
    ):
        """Set the data for checking.

        Args:
            predefined_classes: List of valid class names
            annotations_dir: Directory containing images/annotations
            save_dir: Optional separate save directory
        """
        self.predefined_classes = predefined_classes
        self.annotations_dir = annotations_dir
        self.save_dir = save_dir
        self.checker = LabelConsistencyChecker(predefined_classes)

    def _on_scan(self):
        """Handle scan button click."""
        if not self.annotations_dir:
            QMessageBox.warning(
                self,
                "No Directory",
                "Please open a directory with images first."
            )
            return

        self.scan_button.setEnabled(False)
        self.status_label.setText("Scanning...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate

        try:
            # Scan annotations
            labels_with_files = LabelConsistencyChecker.scan_annotations(
                self.annotations_dir,
                self.save_dir
            )

            if not labels_with_files:
                self.status_label.setText("No annotations found")
                self.progress_bar.setVisible(False)
                self.scan_button.setEnabled(True)
                return

            # Check for issues
            if self.checker is None:
                self.checker = LabelConsistencyChecker(self.predefined_classes)

            self.issues = self.checker.check_labels(labels_with_files)

            # Update UI
            self._populate_table()
            self._update_summary()

            issue_count = len(self.issues)
            label_count = len(labels_with_files)
            self.status_label.setText(
                f"Found {issue_count} issues in {label_count} unique labels"
            )

            self.fix_selected_btn.setEnabled(issue_count > 0)
            self.export_btn.setEnabled(issue_count > 0)

        except Exception as e:
            QMessageBox.critical(
                self,
                "Scan Error",
                f"Error scanning annotations: {e}"
            )
            self.status_label.setText("Scan failed")

        finally:
            self.progress_bar.setVisible(False)
            self.scan_button.setEnabled(True)

    def _populate_table(self):
        """Populate the issues table."""
        self.table.setRowCount(len(self.issues))

        for row, issue in enumerate(self.issues):
            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(issue.suggestion is not None)
            self.table.setCellWidget(row, 0, checkbox)

            # Issue type
            type_item = QTableWidgetItem(ISSUE_TYPE_NAMES[issue.issue_type])
            type_item.setBackground(ISSUE_TYPE_COLORS[issue.issue_type])
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, type_item)

            # Label
            label_item = QTableWidgetItem(repr(issue.label))
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, label_item)

            # Suggestion
            suggestion = issue.suggestion or "-"
            if issue.similarity > 0 and issue.suggestion:
                suggestion = f"{issue.suggestion} ({issue.similarity:.0%})"
            suggestion_item = QTableWidgetItem(suggestion)
            suggestion_item.setFlags(suggestion_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 3, suggestion_item)

            # Count
            count_item = QTableWidgetItem(str(issue.count))
            count_item.setFlags(count_item.flags() & ~Qt.ItemIsEditable)
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, count_item)

            # Files (show count, full list in tooltip)
            files_item = QTableWidgetItem(f"{len(issue.files)} files")
            files_item.setToolTip("\n".join(issue.files[:20]))
            if len(issue.files) > 20:
                files_item.setToolTip(
                    files_item.toolTip() + f"\n... and {len(issue.files) - 20} more"
                )
            files_item.setFlags(files_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 5, files_item)

    def _update_summary(self):
        """Update the summary labels."""
        counts = {issue_type: 0 for issue_type in IssueType}
        for issue in self.issues:
            counts[issue.issue_type] += 1

        for issue_type, label in self.summary_labels.items():
            count = counts[issue_type]
            label.setText(f"{ISSUE_TYPE_NAMES[issue_type]}: {count}")

    def _on_cell_double_clicked(self, row: int, column: int):
        """Handle double-click on a cell to view files."""
        if column == 5 and row < len(self.issues):
            issue = self.issues[row]
            files_text = "\n".join(issue.files)
            QMessageBox.information(
                self,
                f"Files with '{issue.label}'",
                f"Found in {len(issue.files)} files:\n\n{files_text}"
            )

    def _select_all(self):
        """Select all rows."""
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(True)

    def _deselect_all(self):
        """Deselect all rows."""
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(False)

    def _fix_selected(self):
        """Fix selected label issues."""
        fixes = []
        for row in range(self.table.rowCount()):
            checkbox = self.table.cellWidget(row, 0)
            if checkbox and checkbox.isChecked():
                issue = self.issues[row]
                if issue.suggestion:
                    fixes.append((issue.label, issue.suggestion))

        if not fixes:
            QMessageBox.information(
                self,
                "No Fixes Selected",
                "Please select issues with suggestions to fix."
            )
            return

        # Confirm
        msg = f"This will rename {len(fixes)} labels:\n\n"
        for old, new in fixes[:10]:
            msg += f"  '{old}' → '{new}'\n"
        if len(fixes) > 10:
            msg += f"  ... and {len(fixes) - 10} more\n"
        msg += "\nThis cannot be undone. Continue?"

        reply = QMessageBox.question(
            self,
            "Confirm Fixes",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            for old_label, new_label in fixes:
                self.fix_requested.emit(old_label, new_label)

            QMessageBox.information(
                self,
                "Fixes Applied",
                f"Applied {len(fixes)} label fixes.\n"
                "Re-scan to verify the changes."
            )

    def _export_report(self):
        """Export issues report to a file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            "label_consistency_report.txt",
            "Text Files (*.txt);;CSV Files (*.csv)"
        )

        if not file_path:
            return

        try:
            with open(file_path, 'w') as f:
                if file_path.endswith('.csv'):
                    f.write("Type,Label,Suggestion,Similarity,Count,Files\n")
                    for issue in self.issues:
                        files = "|".join(issue.files)
                        f.write(
                            f"{ISSUE_TYPE_NAMES[issue.issue_type]},"
                            f"\"{issue.label}\","
                            f"\"{issue.suggestion or ''}\","
                            f"{issue.similarity:.2f},"
                            f"{issue.count},"
                            f"\"{files}\"\n"
                        )
                else:
                    f.write("Label Consistency Report\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(f"Directory: {self.annotations_dir}\n")
                    f.write(f"Total issues: {len(self.issues)}\n\n")

                    for issue_type in IssueType:
                        type_issues = [
                            i for i in self.issues
                            if i.issue_type == issue_type
                        ]
                        if type_issues:
                            f.write(f"\n{ISSUE_TYPE_NAMES[issue_type]} ({len(type_issues)})\n")
                            f.write("-" * 40 + "\n")
                            for issue in type_issues:
                                f.write(f"  '{issue.label}'")
                                if issue.suggestion:
                                    f.write(f" → '{issue.suggestion}'")
                                f.write(f" ({issue.count} occurrences)\n")

            QMessageBox.information(
                self,
                "Export Complete",
                f"Report saved to:\n{file_path}"
            )

        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Error",
                f"Failed to export report: {e}"
            )
