# libs/widgets/shortcutsDialog.py
"""Keyboard shortcuts configuration dialog."""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QHeaderView, QKeySequenceEdit, QMessageBox, QFileDialog
)
from PyQt5.QtCore import Qt

from libs.utils.styles import Theme, get_theme_colors, hex_to_qcolor


class ShortcutsDialog(QDialog):
    def __init__(self, shortcut_config, action_map, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Keyboard Shortcuts')
        self.setMinimumSize(550, 500)
        self.config = shortcut_config
        self.action_map = action_map  # {action_name: QAction}
        self._pending = dict(shortcut_config.get_all())
        self._theme = Theme.LIGHT

        layout = QVBoxLayout()

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(['Action', 'Shortcut', 'Default'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self._populate_table()
        layout.addWidget(self.table)

        # Buttons
        btn_layout = QHBoxLayout()
        reset_btn = QPushButton('Reset to Defaults')
        reset_btn.clicked.connect(self._reset_all)
        reset_sel_btn = QPushButton('Reset Selected')
        reset_sel_btn.clicked.connect(self._reset_selected)
        export_btn = QPushButton('Export...')
        export_btn.clicked.connect(self._export)
        import_btn = QPushButton('Import...')
        import_btn.clicked.connect(self._import)
        close_btn = QPushButton('Close')
        close_btn.clicked.connect(self.accept)

        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(reset_sel_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(export_btn)
        btn_layout.addWidget(import_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _populate_table(self):
        actions = sorted(self._pending.keys())
        self.table.setRowCount(len(actions))
        for row, name in enumerate(actions):
            # Action name (human-readable)
            name_item = QTableWidgetItem(name.replace('_', ' ').title())
            name_item.setData(Qt.UserRole, name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, name_item)

            # Current shortcut (editable via QKeySequenceEdit)
            sc_edit = QKeySequenceEdit(self._pending[name])
            sc_edit.keySequenceChanged.connect(
                lambda seq, r=row, n=name: self._on_shortcut_changed(r, n, seq))
            self.table.setCellWidget(row, 1, sc_edit)

            # Default (read-only, gray)
            default_item = QTableWidgetItem(self.config.get_default(name))
            default_item.setFlags(default_item.flags() & ~Qt.ItemIsEditable)
            colors = get_theme_colors(self._theme)
            default_item.setForeground(hex_to_qcolor(colors['text_secondary']))
            self.table.setItem(row, 2, default_item)

    def _on_shortcut_changed(self, row, action_name, key_sequence):
        shortcut = key_sequence.toString()
        conflict = self.config.find_conflict(shortcut, exclude_action=action_name)
        self._pending[action_name] = shortcut

        # Apply immediately to QAction
        if action_name in self.action_map:
            self.action_map[action_name].setShortcut(shortcut)
        self.config.set(action_name, shortcut)

        # Highlight conflict
        widget = self.table.cellWidget(row, 1)
        if conflict:
            colors = get_theme_colors(self._theme)
            widget.setStyleSheet(
                'background-color: %s;' % colors['issue_typo'])
            widget.setToolTip(f'Conflicts with: {conflict}')
        else:
            widget.setStyleSheet('')
            widget.setToolTip('')

    def _reset_all(self):
        self.config.reset_all()
        self._pending = dict(self.config.get_all())
        for name, act in self.action_map.items():
            sc = self.config.get(name)
            if sc:
                act.setShortcut(sc)
        self._refresh_table()

    def _reset_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        name = self.table.item(row, 0).data(Qt.UserRole)
        self.config.reset(name)
        self._pending[name] = self.config.get(name)
        if name in self.action_map:
            self.action_map[name].setShortcut(self.config.get(name))
        self._refresh_table()

    def _refresh_table(self):
        self.table.clearContents()
        self._populate_table()

    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, 'Export Shortcuts', 'shortcuts.json', 'JSON (*.json)')
        if path:
            self.config.export_json(path)

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, 'Import Shortcuts', '', 'JSON (*.json)')
        if path:
            self.config.import_json(path)
            self._pending = dict(self.config.get_all())
            for name, act in self.action_map.items():
                sc = self.config.get(name)
                if sc:
                    act.setShortcut(sc)
            self._refresh_table()

    def apply_theme(self, theme):
        from libs.utils.styles import get_stylesheet
        self._theme = theme
        self.setStyleSheet(get_stylesheet(theme))
        # Re-render rows so the themed default-shortcut color is applied.
        self._refresh_table()
