"""Fixed inspector and splitter shell for the Balanced workspace."""

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QHBoxLayout, QSizePolicy, QSplitter, QTabWidget, QToolButton,
        QVBoxLayout, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import Qt, pyqtSignal
    from PyQt4.QtGui import (
        QHBoxLayout, QSizePolicy, QSplitter, QTabWidget, QToolButton,
        QVBoxLayout, QWidget,
    )

from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_workspace_inspector_style
from libs.utils.utils import themed_icon


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
        self.tabs.currentChanged.connect(self._tab_changed)

        self.collapse_button = QToolButton(self)
        self.collapse_button.setObjectName('collapseInspectorButton')
        self.collapse_button.setAccessibleName('Collapse inspector')
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

        self.reopen_button = QToolButton(self)
        self.reopen_button.setObjectName('reopenInspectorButton')
        self.reopen_button.setAccessibleName('Open inspector')
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
            total = max(0, self.splitter.width())
            self.splitter.setSizes([
                max(0, total - self._inspector_width),
                self._inspector_width,
            ])

    def inspector_width(self):
        sizes = self.splitter.sizes()
        if len(sizes) > 1 and sizes[1] > 0:
            return sizes[1]
        return self._inspector_width

    def is_inspector_collapsed(self):
        return self.inspector.isHidden()

    def set_inspector_collapsed(self, collapsed, emit=True):
        collapsed = bool(collapsed)
        if collapsed == self.is_inspector_collapsed():
            self.reopen_button.setVisible(collapsed)
            return
        if collapsed:
            sizes = self.splitter.sizes()
            if len(sizes) > 1 and sizes[1] > 0:
                self._inspector_width = sizes[1]
            self.inspector.hide()
        else:
            self.inspector.show()
            self.set_inspector_width(self._inspector_width)
        self.reopen_button.setVisible(collapsed)
        if emit:
            self.inspectorCollapsedChanged.emit(collapsed)

    def apply_theme(self, theme):
        self.reopen_button.setIcon(themed_icon('chevron-left', theme))
