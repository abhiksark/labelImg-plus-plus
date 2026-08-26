"""Fixed inspector and splitter shell for the Balanced workspace."""

try:
    from PyQt5.QtCore import QEvent, QTimer, Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QApplication, QHBoxLayout, QSizePolicy, QSplitter, QTabWidget,
        QToolButton, QVBoxLayout, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import QEvent, QTimer, Qt, pyqtSignal
    from PyQt4.QtGui import (
        QApplication, QHBoxLayout, QSizePolicy, QSplitter, QTabWidget,
        QToolButton, QVBoxLayout, QWidget,
    )

from libs.core.workspace_settings import INSPECTOR_DRAWER_BREAKPOINT
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
        self.tabs.setAccessibleName('Inspector')
        self.tabs.setUsesScrollButtons(False)
        self.tabs.addTab(objects_widget, 'Objects')
        self.tabs.addTab(files_widget, 'Files')
        self.tabs.currentChanged.connect(self._tab_changed)

        self.collapse_button = QToolButton(self)
        self.collapse_button.setObjectName('collapseInspectorButton')
        self.collapse_button.setAccessibleName('Collapse inspector')
        self.collapse_button.setToolTip('Collapse inspector')
        self.collapse_button.setFocusPolicy(Qt.StrongFocus)
        self.collapse_button.setFixedSize(scale_px(32), scale_px(32))
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
        self.collapse_button.setIcon(themed_icon('next', theme))
        self.setStyleSheet(get_workspace_inspector_style(theme))


class _DrawerScrim(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super(_DrawerScrim, self).__init__(parent)
        self.setObjectName('inspectorDrawerScrim')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet('background: rgba(0, 0, 0, 96);')

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super(_DrawerScrim, self).mousePressEvent(event)


class WorkspaceSplitterShell(QWidget):
    """Keep the tool rail fixed and resize only canvas versus inspector."""

    inspectorCollapsedChanged = pyqtSignal(bool)
    layoutModeChanged = pyqtSignal(str)
    drawerVisibilityChanged = pyqtSignal(bool)

    def __init__(self, tool_rail, canvas_column, inspector,
                 inspector_width, collapsed=False, parent=None):
        super(WorkspaceSplitterShell, self).__init__(parent)
        self.setObjectName('workspaceShell')
        self.inspector = inspector
        self._inspector_width = int(inspector_width)
        self._wide_collapsed_preference = bool(collapsed)
        self._drawer_open = False
        self._drawer_transition_serial = 0
        self.layout_mode = 'docked'

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
        self.reopen_button.setAccessibleName('Open inspector, 0 objects')
        self.reopen_button.setToolTip('Open inspector')
        self.reopen_button.setFocusPolicy(Qt.StrongFocus)
        self.reopen_button.setIcon(themed_icon('prev', Theme.LIGHT))
        self.reopen_button.setFixedSize(scale_px(32), scale_px(32))
        self.reopen_button.clicked.connect(self.open_inspector)

        self.scrim = _DrawerScrim(self)
        self.scrim.hide()
        self.scrim.clicked.connect(self.close_inspector)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(tool_rail)
        layout.addWidget(self.splitter, 1)
        layout.addWidget(self.reopen_button)

        inspector.collapseRequested.connect(self.close_inspector)
        if collapsed:
            self.set_inspector_collapsed(True, emit=False)
        else:
            self.reopen_button.hide()
            self.splitter.setSizes([scale_px(1000), self._inspector_width])

    def set_available_width(self, width):
        mode = ('drawer' if int(width) < INSPECTOR_DRAWER_BREAKPOINT
                else 'docked')
        if mode == self.layout_mode:
            return
        self.layout_mode = mode
        self._project_layout_mode()
        self.layoutModeChanged.emit(mode)

    def _project_layout_mode(self):
        if self.layout_mode == 'drawer':
            self._drawer_open = False
            self.inspector.collapse_button.setAccessibleName(
                'Close inspector')
            self.inspector.collapse_button.setToolTip('Close inspector')
            self.inspector.hide()
            self.inspector.setParent(self)
            self.scrim.hide()
            self.reopen_button.show()
            self._schedule_drawer_settle()
            return

        self._drawer_transition_serial += 1
        self._remove_focus_trap()
        self._drawer_open = False
        self.inspector.collapse_button.setAccessibleName(
            'Collapse inspector')
        self.inspector.collapse_button.setToolTip('Collapse inspector')
        self.scrim.hide()
        self.inspector.hide()
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        if self._wide_collapsed_preference:
            self.reopen_button.show()
        else:
            self.inspector.show()
            self._apply_inspector_width(self._inspector_width)
            self.reopen_button.hide()

    def open_inspector(self):
        if self.layout_mode == 'docked':
            self.set_inspector_collapsed(False)
            self.inspector.tabs.setFocus(Qt.OtherFocusReason)
            return
        self._drawer_open = True
        self.scrim.show()
        self.scrim.raise_()
        self.inspector.show()
        self.inspector.raise_()
        self.reopen_button.hide()
        self._schedule_drawer_settle(notify=True)
        QApplication.instance().installEventFilter(self)
        self.inspector.tabs.setFocus(Qt.OtherFocusReason)

    def close_inspector(self):
        if self.layout_mode == 'docked':
            self.set_inspector_collapsed(True)
            self.reopen_button.setFocus(Qt.OtherFocusReason)
            return
        self._drawer_open = False
        self._remove_focus_trap()
        self.inspector.hide()
        self.scrim.hide()
        self.reopen_button.show()
        self.reopen_button.setFocus(Qt.OtherFocusReason)
        self._schedule_drawer_settle(notify=True)

    def set_object_count(self, count):
        self.reopen_button.setAccessibleName(
            'Open inspector, %d objects' % max(0, int(count)))

    def _remove_focus_trap(self):
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)

    def _inside_inspector(self, widget):
        return widget is self.inspector or (
            widget is not None and self.inspector.isAncestorOf(widget))

    def _is_active_drawer_event(self, watched):
        if not isinstance(watched, QWidget):
            return False
        top_level = self.window()
        if watched.window() is not top_level:
            return False
        modal = QApplication.activeModalWidget()
        if modal is not None and modal is not top_level:
            return False
        return QApplication.activeWindow() is top_level

    def eventFilter(self, watched, event):
        if (self.layout_mode != 'drawer' or not self._drawer_open
                or event.type() != QEvent.KeyPress):
            return super(WorkspaceSplitterShell, self).eventFilter(
                watched, event)
        if not self._is_active_drawer_event(watched):
            return super(WorkspaceSplitterShell, self).eventFilter(
                watched, event)
        if event.key() == Qt.Key_Escape:
            self.close_inspector()
            return True
        if event.key() not in (Qt.Key_Tab, Qt.Key_Backtab):
            return super(WorkspaceSplitterShell, self).eventFilter(
                watched, event)

        current = QApplication.focusWidget()
        if not self._inside_inspector(current):
            self.inspector.tabs.setFocus(Qt.TabFocusReason)
            return True
        backwards = (event.key() == Qt.Key_Backtab
                     or bool(event.modifiers() & Qt.ShiftModifier))
        candidate = current
        for _index in range(256):
            candidate = (candidate.previousInFocusChain() if backwards
                         else candidate.nextInFocusChain())
            if candidate is current:
                break
            if (self._inside_inspector(candidate) and candidate.isVisible()
                    and candidate.isEnabled()
                    and candidate.focusPolicy() != Qt.NoFocus):
                candidate.setFocus(Qt.BacktabFocusReason if backwards
                                   else Qt.TabFocusReason)
                return True
        self.inspector.tabs.setFocus(Qt.TabFocusReason)
        return True

    def _schedule_drawer_settle(self, notify=False):
        self._drawer_transition_serial += 1
        serial = self._drawer_transition_serial
        QTimer.singleShot(
            0, lambda: self._settle_drawer_layout(serial, notify))

    def _settle_drawer_layout(self, serial, notify):
        if (serial != self._drawer_transition_serial
                or self.layout_mode != 'drawer'):
            return
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self._update_drawer_geometry()
        if self._drawer_open:
            self.scrim.raise_()
            self.inspector.raise_()
        if notify:
            self.drawerVisibilityChanged.emit(self._drawer_open)

    def _update_drawer_geometry(self):
        if self.layout_mode != 'drawer':
            return
        bounds = self.splitter.geometry()
        drawer_width = min(self._inspector_width, bounds.width())
        self.scrim.setGeometry(bounds)
        self.inspector.setGeometry(
            bounds.right() - drawer_width + 1, bounds.y(),
            drawer_width, bounds.height())

    def resizeEvent(self, event):
        super(WorkspaceSplitterShell, self).resizeEvent(event)
        self._update_drawer_geometry()

    def _dismiss_drawer_for_lifecycle(self):
        self._drawer_transition_serial += 1
        self._remove_focus_trap()
        if self.layout_mode != 'drawer' or not self._drawer_open:
            return
        self._drawer_open = False
        self.inspector.hide()
        self.scrim.hide()
        self.reopen_button.show()

    def hideEvent(self, event):
        self._dismiss_drawer_for_lifecycle()
        super(WorkspaceSplitterShell, self).hideEvent(event)

    def closeEvent(self, event):
        self._dismiss_drawer_for_lifecycle()
        super(WorkspaceSplitterShell, self).closeEvent(event)

    def set_inspector_width(self, width):
        self._inspector_width = int(width)
        if self.layout_mode == 'drawer':
            self._update_drawer_geometry()
        elif not self.is_inspector_collapsed():
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
        if self.layout_mode == 'drawer':
            return not self._drawer_open
        # A QSplitter with collapsible children gives a drag-collapsed panel
        # zero width without hiding it. Reporting that as "open" made the
        # width-persist timer reopen the panel 200ms after every drag.
        return self.inspector.isHidden() or self.inspector.width() == 0

    def set_inspector_collapsed(self, collapsed, emit=True):
        collapsed = bool(collapsed)
        if self.layout_mode == 'drawer':
            if collapsed:
                self.close_inspector()
            else:
                self.open_inspector()
            return
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
            self._apply_inspector_width(self._inspector_width)
        self._wide_collapsed_preference = collapsed
        self.reopen_button.setVisible(collapsed)
        if emit:
            self.inspectorCollapsedChanged.emit(collapsed)

    def _sync_collapse_after_drag(self, _position, _index):
        """Keep the reopen affordance in step with a drag-collapse.

        Dragging the handle to the edge collapses the panel without going
        through set_inspector_collapsed, so nothing would otherwise show the
        chevron that brings it back.
        """
        if self.layout_mode != 'docked':
            return
        collapsed = self.is_inspector_collapsed()
        if collapsed == self.reopen_button.isVisible():
            return
        self._wide_collapsed_preference = collapsed
        self.reopen_button.setVisible(collapsed)
        self.inspectorCollapsedChanged.emit(collapsed)

    def apply_theme(self, theme):
        self.reopen_button.setIcon(themed_icon('prev', theme))
