# libs/widgets/labelCheckerDialog.py
"""Dialog for reviewing and reporting label consistency issues."""

import os
import tempfile
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QProgressBar, QHeaderView, QAbstractItemView,
    QMessageBox, QFileDialog, QCheckBox, QGroupBox
)
from libs.tools.label_checker import LabelConsistencyChecker, LabelIssue, IssueType


ISSUE_TYPE_NAMES = {
    IssueType.TYPO: "Typo",
    IssueType.CASE_MISMATCH: "Case Mismatch",
    IssueType.WHITESPACE: "Whitespace",
    IssueType.UNDEFINED: "Undefined",
    IssueType.DUPLICATE: "Duplicate",
}

AUTOMATIC_FIXES_UNAVAILABLE_TEXT = (
    "Automatic label fixes are unavailable in this release. "
    "Review the suggestions and export a report to make changes manually."
)


class LabelCheckerDialog(QDialog):
    """Dialog for checking and reporting label consistency issues."""

    # Retained for compatibility; automatic fixes are unavailable and this
    # signal is deliberately never emitted by the dialog.
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
        self._coordinator = getattr(parent, 'task_coordinator', None)
        self._scan_handle = None
        self._export_handle = None
        from libs.utils.styles import Theme
        self._issue_colors = self._get_issue_colors(Theme.LIGHT)

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
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
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

        self.fix_selected_btn = QPushButton("Fix Selected (Unavailable)")
        self.fix_selected_btn.clicked.connect(self._fix_selected)
        self.fix_selected_btn.setToolTip(AUTOMATIC_FIXES_UNAVAILABLE_TEXT)
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

    def _get_issue_colors(self, theme):
        """Get issue colors from centralized theme palette.

        Args:
            theme: Theme enum value (Theme.LIGHT or Theme.DARK)
        """
        from libs.utils.styles import get_theme_colors, hex_to_qcolor
        colors = get_theme_colors(theme)
        return {
            IssueType.TYPO: hex_to_qcolor(colors['issue_typo']),
            IssueType.CASE_MISMATCH: hex_to_qcolor(colors['issue_case']),
            IssueType.WHITESPACE: hex_to_qcolor(colors['issue_whitespace']),
            IssueType.UNDEFINED: hex_to_qcolor(colors['issue_undefined']),
            IssueType.DUPLICATE: hex_to_qcolor(colors['issue_duplicate']),
        }

    def apply_theme(self, theme):
        """Apply theme to issue colors."""
        self._issue_colors = self._get_issue_colors(theme)
        # Refresh table colors
        if hasattr(self, 'table'):
            self._refresh_table_colors()

    def _refresh_table_colors(self):
        """Refresh table row background colors after theme change."""
        for row in range(self.table.rowCount()):
            issue_type_text = self.table.item(row, 1).text()
            # Map display name back to enum
            issue_type = None
            for it, name in ISSUE_TYPE_NAMES.items():
                if name == issue_type_text:
                    issue_type = it
                    break
            if issue_type:
                self.table.item(row, 1).setBackground(self._issue_colors[issue_type])

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

        if self._coordinator is None:
            self._scan_sync()
            return

        predefined = tuple(self.predefined_classes)
        annotations_dir = self.annotations_dir
        save_dir = self.save_dir

        def scan(handle):
            labels_with_files = LabelConsistencyChecker.scan_annotations(
                annotations_dir, save_dir,
                cancelled=handle.is_cancelled,
                progress=lambda current, total: handle.report_progress(
                    (current, total)))
            handle.check_cancelled()
            checker = LabelConsistencyChecker(list(predefined))
            return checker.check_labels(labels_with_files), len(labels_with_files)

        from libs.core.task_coordinator import JobPriority
        self.progress_bar.setRange(0, 100)
        self._scan_handle = self._coordinator.submit(
            'background', scan, priority=JobPriority.BULK,
            key='label-checker', latest=True)
        self._scan_handle.progress.connect(self._on_scan_progress)
        self._scan_handle.result.connect(self._on_scan_result)
        self._scan_handle.error.connect(self._on_scan_error)

    def _scan_sync(self):
        try:
            labels_with_files = LabelConsistencyChecker.scan_annotations(
                self.annotations_dir, self.save_dir)

            if not labels_with_files:
                self.status_label.setText("No annotations found")
                self.progress_bar.setVisible(False)
                self.scan_button.setEnabled(True)
                return

            # Check for issues
            if self.checker is None:
                self.checker = LabelConsistencyChecker(self.predefined_classes)

            self._on_scan_result((
                self.checker.check_labels(labels_with_files),
                len(labels_with_files)))

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

    def _on_scan_progress(self, value):
        current, total = value
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            return
        self.progress_bar.setRange(0, max(1, total))
        self.progress_bar.setValue(current)

    def _on_scan_result(self, result):
        self.issues, label_count = result
        self._populate_table()
        self._update_summary()
        issue_count = len(self.issues)
        if label_count:
            self.status_label.setText(
                f"Found {issue_count} issues in {label_count} unique labels")
        else:
            self.status_label.setText("No annotations found")
        self.fix_selected_btn.setEnabled(False)
        self.export_btn.setEnabled(issue_count > 0)
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self._scan_handle = None

    def _on_scan_error(self, message):
        QMessageBox.critical(
            self, "Scan Error", f"Error scanning annotations: {message}")
        self.status_label.setText("Scan failed")
        self.progress_bar.setVisible(False)
        self.scan_button.setEnabled(True)
        self._scan_handle = None

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
            type_item.setBackground(self._issue_colors[issue.issue_type])
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 1, type_item)

            # Label
            label_item = QTableWidgetItem(repr(issue.label))
            label_item.setFlags(label_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, label_item)

            # Suggestion
            suggestion = issue.suggestion or "-"
            if issue.similarity > 0 and issue.suggestion:
                suggestion = f"{issue.suggestion} ({issue.similarity:.0%})"
            suggestion_item = QTableWidgetItem(suggestion)
            suggestion_item.setFlags(suggestion_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, suggestion_item)

            # Count
            count_item = QTableWidgetItem(str(issue.count))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 4, count_item)

            # Files (show count, full list in tooltip)
            files_item = QTableWidgetItem(f"{len(issue.files)} files")
            files_item.setToolTip("\n".join(issue.files[:20]))
            if len(issue.files) > 20:
                files_item.setToolTip(
                    files_item.toolTip() + f"\n... and {len(issue.files) - 20} more"
                )
            files_item.setFlags(files_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
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
        """Explain that automatic rewriting is unavailable and do nothing.

        The button is disabled in the UI, but this method is intentionally a
        defensive no-op in case it is invoked directly by code.
        """
        self.fix_selected_btn.setEnabled(False)
        QMessageBox.information(
            self,
            "Automatic Fixes Unavailable",
            AUTOMATIC_FIXES_UNAVAILABLE_TEXT,
        )
        return False

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

        issues = tuple(self.issues)
        annotations_dir = self.annotations_dir
        if self._coordinator is not None:
            from libs.core.task_coordinator import JobPriority
            render_report = LabelCheckerDialog._render_report
            atomic_write_text = LabelCheckerDialog._atomic_write_text

            def export(handle):
                text = render_report(
                    file_path, issues, annotations_dir)
                handle.check_cancelled()
                atomic_write_text(file_path, text)
                return file_path

            self.export_btn.setEnabled(False)
            self._export_handle = self._coordinator.submit(
                'background', export, priority=JobPriority.BULK,
                key='label-report-export', latest=True)
            self._export_handle.result.connect(self._on_exported)
            self._export_handle.error.connect(self._on_export_error)
            return

        try:
            text = self._render_report(file_path, issues, annotations_dir)
            self._atomic_write_text(file_path, text)
            self._on_exported(file_path)

        except Exception as e:
            self._on_export_error(str(e))

    @staticmethod
    def _render_report(file_path, issues, annotations_dir):
        lines = []
        if file_path.endswith('.csv'):
            lines.append("Type,Label,Suggestion,Similarity,Count,Files")
            for issue in issues:
                files = "|".join(issue.files)
                lines.append(
                    f'{ISSUE_TYPE_NAMES[issue.issue_type]},'
                    f'"{issue.label}","{issue.suggestion or ""}",'
                    f'{issue.similarity:.2f},{issue.count},"{files}"')
        else:
            lines.extend([
                "Label Consistency Report",
                "=" * 50,
                "",
                f"Directory: {annotations_dir}",
                f"Total issues: {len(issues)}",
                "",
            ])
            for issue_type in IssueType:
                type_issues = [
                    issue for issue in issues
                    if issue.issue_type == issue_type]
                if not type_issues:
                    continue
                lines.extend([
                    f"{ISSUE_TYPE_NAMES[issue_type]} ({len(type_issues)})",
                    "-" * 40,
                ])
                for issue in type_issues:
                    suggestion = (
                        f" → '{issue.suggestion}'"
                        if issue.suggestion else '')
                    lines.append(
                        f"  '{issue.label}'{suggestion} "
                        f"({issue.count} occurrences)")
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _atomic_write_text(file_path, text):
        directory = os.path.dirname(os.path.abspath(file_path)) or os.curdir
        descriptor, temporary = tempfile.mkstemp(
            prefix='.' + os.path.basename(file_path) + '.',
            suffix='.tmp', dir=directory)
        try:
            with os.fdopen(descriptor, 'w') as output:
                output.write(text)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, file_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def _on_exported(self, file_path):
        self.export_btn.setEnabled(bool(self.issues))
        self._export_handle = None
        QMessageBox.information(
            self, "Export Complete", f"Report saved to:\n{file_path}")

    def _on_export_error(self, message):
        self.export_btn.setEnabled(bool(self.issues))
        self._export_handle = None
        QMessageBox.critical(
            self, "Export Error", f"Failed to export report: {message}")

    def closeEvent(self, event):
        for handle in (self._scan_handle, self._export_handle):
            if handle is not None:
                handle.cancel()
        super().closeEvent(event)
