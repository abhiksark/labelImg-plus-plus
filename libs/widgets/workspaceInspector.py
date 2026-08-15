# libs/widgets/workspaceInspector.py
"""Fixed inspector and splitter shell for the Balanced workspace."""

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QComboBox, QHBoxLayout, QLabel, QMenu, QSizePolicy, QSplitter,
        QTabWidget, QToolButton, QVBoxLayout, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import Qt, pyqtSignal
    from PyQt4.QtGui import (
        QComboBox, QHBoxLayout, QLabel, QMenu, QSizePolicy, QSplitter,
        QTabWidget, QToolButton, QVBoxLayout, QWidget,
    )

from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_workspace_inspector_style
from libs.utils.utils import themed_icon


class InspectorContextCard(QWidget):
    """A calm projection of the next actions for the current object state."""

    classStrategyChanged = pyqtSignal(str)
    fixedClassChanged = pyqtSignal(str)

    MAX_ACTIONS = 3
    COMPACT_ACTION_TEXT = {
        'Propagate selected object': 'Propagate…',
        'Add Track Keyframe': 'Add keyframe',
        'Accept Next': 'Accept + Next',
        'Reject Next': 'Reject',
        'Previous issue': 'Previous',
    }

    def __init__(self, parent=None):
        super(InspectorContextCard, self).__init__(parent)
        self.setObjectName('inspectorContextCard')
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.eyebrow = QLabel(self)
        self.eyebrow.setObjectName('inspectorContextEyebrow')
        self.title = QLabel(self)
        self.title.setObjectName('inspectorContextTitle')
        self.title.setWordWrap(True)
        self.detail = QLabel(self)
        self.detail.setObjectName('inspectorContextDetail')
        self.detail.setWordWrap(True)

        self.class_strategy_combo = QComboBox(self)
        self.class_strategy_combo.setObjectName('classStrategyCombo')
        self.class_strategy_combo.setAccessibleName('Class strategy')
        for text, value in (
                ('Confirm each', 'confirm'), ('Repeat last', 'repeat'),
                ('Fixed class', 'fixed')):
            self.class_strategy_combo.addItem(text, value)
        self.class_strategy_combo.currentIndexChanged.connect(
            self._emit_class_strategy)
        self.class_strategy_combo.hide()

        self.fixed_class_combo = QComboBox(self)
        self.fixed_class_combo.setObjectName('fixedClassCombo')
        self.fixed_class_combo.setAccessibleName('Fixed class')
        self.fixed_class_combo.currentIndexChanged.connect(
            self._emit_fixed_class)
        self.fixed_class_combo.hide()

        self.action_buttons = []
        primary_row = QHBoxLayout()
        primary_row.setContentsMargins(0, 0, 0, 0)
        primary_row.setSpacing(scale_px(4))
        secondary_row = QHBoxLayout()
        secondary_row.setContentsMargins(0, 0, 0, 0)
        secondary_row.setSpacing(scale_px(4))
        for index in range(self.MAX_ACTIONS):
            button = QToolButton(self)
            button.setObjectName('inspectorContextAction')
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
            button.setFocusPolicy(Qt.StrongFocus)
            button.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Preferred)
            button.setProperty('primary', index == 0)
            button.hide()
            (primary_row if index == 0 else secondary_row).addWidget(button)
            self.action_buttons.append(button)

        self.more_menu = QMenu(self)
        self.more_button = QToolButton(self)
        self.more_button.setObjectName('inspectorContextMore')
        self.more_button.setText('More')
        self.more_button.setAccessibleName('More object actions')
        self.more_button.setFocusPolicy(Qt.StrongFocus)
        self.more_button.setPopupMode(QToolButton.InstantPopup)
        self.more_button.setMenu(self.more_menu)
        self.more_button.hide()
        secondary_row.addStretch(1)
        secondary_row.addWidget(self.more_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale_px(10), scale_px(8), scale_px(10), scale_px(9))
        layout.setSpacing(scale_px(3))
        layout.addWidget(self.eyebrow)
        layout.addWidget(self.title)
        layout.addWidget(self.detail)
        layout.addWidget(self.class_strategy_combo)
        layout.addWidget(self.fixed_class_combo)
        layout.addSpacing(scale_px(3))
        layout.addLayout(primary_row)
        layout.addLayout(secondary_row)

    def set_context(self, eyebrow, title, detail='', actions=(), more=()):
        self.class_strategy_combo.hide()
        self.fixed_class_combo.hide()
        self.eyebrow.setText(str(eyebrow or '').upper())
        self.title.setText(str(title or ''))
        self.detail.setText(str(detail or ''))
        self.detail.setVisible(bool(detail))

        visible_actions = tuple(action for action in actions
                                if action is not None and action.isEnabled())
        for index, button in enumerate(self.action_buttons):
            action = (visible_actions[index]
                      if index < len(visible_actions) else None)
            if action is None:
                button.hide()
            else:
                button.setDefaultAction(action)
                action_text = ' '.join(
                    action.text().replace('&', '').split())
                button.setText(self.COMPACT_ACTION_TEXT.get(
                    action_text, action_text))
                button.setAccessibleName(action_text)
                button.setVisible(True)

        self.more_menu.clear()
        for action in more:
            if action is None:
                if self.more_menu.actions():
                    self.more_menu.addSeparator()
            elif action.isEnabled():
                self.more_menu.addAction(action)
        has_more = any(not action.isSeparator()
                       for action in self.more_menu.actions())
        self.more_button.setVisible(has_more)

    def set_class_strategy(self, strategy, labels, fixed_label=''):
        """Show the one visible projection over legacy class settings."""
        strategy = strategy if strategy in ('confirm', 'repeat', 'fixed') \
            else 'confirm'
        blocked = self.class_strategy_combo.blockSignals(True)
        self.class_strategy_combo.setCurrentIndex(
            self.class_strategy_combo.findData(strategy))
        self.class_strategy_combo.blockSignals(blocked)

        values = tuple(dict.fromkeys(
            str(label).strip() for label in labels if str(label).strip()))
        blocked = self.fixed_class_combo.blockSignals(True)
        self.fixed_class_combo.clear()
        self.fixed_class_combo.addItems(values)
        index = self.fixed_class_combo.findText(str(fixed_label or ''))
        if index >= 0:
            self.fixed_class_combo.setCurrentIndex(index)
        self.fixed_class_combo.blockSignals(blocked)
        self.class_strategy_combo.show()
        self.fixed_class_combo.setVisible(strategy == 'fixed')

    def _emit_class_strategy(self, _index):
        self.classStrategyChanged.emit(
            str(self.class_strategy_combo.currentData()))

    def _emit_fixed_class(self, _index):
        self.fixedClassChanged.emit(self.fixed_class_combo.currentText())

    def visible_actions(self):
        return tuple(button.defaultAction() for button in self.action_buttons
                     if not button.isHidden())


class WorkspaceInspector(QWidget):
    """Own the existing Objects and Files projections in one fixed panel."""

    collapseRequested = pyqtSignal()
    tabChanged = pyqtSignal(str)

    def __init__(self, objects_widget, files_widget, parent=None):
        super(WorkspaceInspector, self).__init__(parent)
        self.setObjectName('workspaceInspector')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(scale_px(420))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName('inspectorTabs')
        self.tabs.addTab(objects_widget, 'Objects')
        self.tabs.addTab(files_widget, 'Files')
        self._files_widget = files_widget
        self._tab_before_files_hidden = 'objects'
        self.tabs.currentChanged.connect(self._tab_changed)

        self.collapse_button = QToolButton(self)
        self.collapse_button.setObjectName('collapseInspectorButton')
        self.collapse_button.setAccessibleName('Collapse inspector')
        self.collapse_button.setFocusPolicy(Qt.StrongFocus)
        self.collapse_button.setToolTip('Collapse inspector')
        self.collapse_button.clicked.connect(self.collapseRequested)
        self.tabs.setCornerWidget(self.collapse_button, Qt.TopRightCorner)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)
        self.apply_theme(Theme.LIGHT)

    def selected_tab(self):
        return 'files' if self.tabs.currentIndex() == 1 else 'objects'

    def set_selected_tab(self, name):
        self.tabs.setCurrentIndex(1 if name == 'files' else 0)

    def set_files_visible(self, visible):
        """Remove image-only browsing chrome while retaining its live widget."""
        visible = bool(visible)
        if hasattr(self.tabs, 'isTabVisible') \
                and self.tabs.isTabVisible(1) == visible:
            return
        if not visible:
            self._tab_before_files_hidden = self.selected_tab()
            blocked = self.tabs.blockSignals(True)
            if self.tabs.currentIndex() == 1:
                self.tabs.setCurrentIndex(0)
            if hasattr(self.tabs, 'setTabVisible'):
                self.tabs.setTabVisible(1, False)
            else:
                self.tabs.setTabEnabled(1, False)
            self.tabs.blockSignals(blocked)
            return
        blocked = self.tabs.blockSignals(True)
        if hasattr(self.tabs, 'setTabVisible'):
            self.tabs.setTabVisible(1, True)
        else:
            self.tabs.setTabEnabled(1, True)
        if self._tab_before_files_hidden == 'files':
            self.tabs.setCurrentIndex(1)
        self.tabs.blockSignals(blocked)

    def _tab_changed(self, _index):
        self.tabChanged.emit(self.selected_tab())

    def apply_theme(self, theme):
        self._current_theme = theme
        self.collapse_button.setIcon(themed_icon('chevron-right', theme))
        self.setStyleSheet(get_workspace_inspector_style(theme))


class WorkspaceSplitterShell(QWidget):
    """Keep the tool rail fixed and resize only canvas versus inspector."""

    inspectorCollapsedChanged = pyqtSignal(bool)

    def __init__(self, tool_rail, canvas_column, inspector,
                 inspector_width, collapsed=False, parent=None):
        super(WorkspaceSplitterShell, self).__init__(parent)
        self.setObjectName('workspaceShell')
        self.inspector = inspector
        self._inspector_width = int(inspector_width)

        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setObjectName('workspaceSplitter')
        self.splitter.setChildrenCollapsible(True)
        self.splitter.addWidget(canvas_column)
        self.splitter.addWidget(inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._sync_collapse_after_drag)

        self.reopen_button = QToolButton(self)
        self.reopen_button.setObjectName('reopenInspectorButton')
        self.reopen_button.setAccessibleName('Open inspector')
        self.reopen_button.setFocusPolicy(Qt.StrongFocus)
        self.reopen_button.setToolTip('Open inspector')
        self.reopen_button.setIcon(themed_icon('chevron-left', Theme.LIGHT))
        self.reopen_button.setFixedWidth(scale_px(32))
        self.reopen_button.clicked.connect(
            lambda: self.set_inspector_collapsed(False))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(tool_rail)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.reopen_button)

        inspector.collapseRequested.connect(
            lambda: self.set_inspector_collapsed(True))
        if collapsed:
            self.set_inspector_collapsed(True, emit=False)
        else:
            self.reopen_button.hide()
            self.splitter.setSizes([scale_px(1000), self._inspector_width])

    def set_inspector_width(self, width):
        self._inspector_width = int(width)
        if not self.is_inspector_collapsed():
            self._apply_inspector_width(self._inspector_width)

    def _apply_inspector_width(self, width):
        """Resize the splitter regardless of the collapsed state.

        Reopening has to bypass the collapsed guard in set_inspector_width:
        a drag-collapsed panel is still zero-width at that point, so the
        guard would refuse the very resize that reopens it.
        """
        total = max(0, self.splitter.width())
        self.splitter.setSizes([max(0, total - width), width])

    def inspector_width(self):
        sizes = self.splitter.sizes()
        if len(sizes) > 1 and sizes[1] > 0:
            return sizes[1]
        return self._inspector_width

    def is_inspector_collapsed(self):
        # A QSplitter with collapsible children gives a drag-collapsed panel
        # zero width without hiding it. Reporting that as "open" made the
        # width-persist timer reopen the panel 200ms after every drag.
        return self.inspector.isHidden() or self.inspector.width() == 0

    def set_inspector_collapsed(self, collapsed, emit=True,
                                 remember_width=True):
        collapsed = bool(collapsed)
        if collapsed == self.is_inspector_collapsed():
            self.reopen_button.setVisible(collapsed)
            return
        if collapsed:
            sizes = self.splitter.sizes()
            if remember_width and len(sizes) > 1 and sizes[1] > 0:
                self._inspector_width = sizes[1]
            self.inspector.hide()
        else:
            self.inspector.show()
            self._apply_inspector_width(self._inspector_width)
        self.reopen_button.setVisible(collapsed)
        if emit:
            self.inspectorCollapsedChanged.emit(collapsed)

    def _sync_collapse_after_drag(self, _position, _index):
        """Keep the reopen affordance in step with a drag-collapse.

        Dragging the handle to the edge collapses the panel without going
        through set_inspector_collapsed, so nothing would otherwise show the
        chevron that brings it back.
        """
        collapsed = self.is_inspector_collapsed()
        if collapsed == self.reopen_button.isVisible():
            return
        self.reopen_button.setVisible(collapsed)
        self.inspectorCollapsedChanged.emit(collapsed)

    def apply_theme(self, theme):
        self.reopen_button.setIcon(themed_icon('chevron-left', theme))
