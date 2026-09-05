"""Central Empty, Canvas, Gallery, and Overview pages for the workspace.

Gallery and Overview are one slot with two contents: the browse page for an
image directory is the gallery, and for a video it is the overview. Which one
shows is the host's routing decision from the document kind, never a second
user-facing toggle, so both live in this stack side by side.
"""

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from libs.utils.dpi import scale_px
from libs.widgets.videoOverview import VideoOverview


def _action_button(action, parent):
    button = QToolButton(parent)
    button.setDefaultAction(action)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
    button.setAutoRaise(True)
    button.setFixedSize(scale_px(32), scale_px(32))
    return button


class SamOutputModeToggle(QWidget):
    """Compact contextual selector for Smart Select geometry output."""

    modeChanged = pyqtSignal(str)

    def __init__(self, mode='polygon', parent=None):
        super(SamOutputModeToggle, self).__init__(parent)
        self.setObjectName('samOutputModeToggle')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(scale_px(6), 0, scale_px(6), 0)
        layout.setSpacing(0)
        label = QLabel('Output')
        label.setObjectName('samOutputModeLabel')
        layout.addWidget(label)
        layout.addSpacing(scale_px(4))
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for value, text in (('box', 'Box'), ('polygon', 'Polygon')):
            button = QToolButton(self)
            button.setObjectName('samOutput' + text + 'Button')
            button.setText(text)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            button.setFixedHeight(scale_px(28))
            button.setMinimumWidth(scale_px(48 if value == 'box' else 68))
            button.setProperty('outputMode', value)
            button.clicked.connect(self._emit_mode)
            self.group.addButton(button)
            self.buttons[value] = button
            layout.addWidget(button)
        self.set_mode(mode)
        self.hide()

    def set_mode(self, mode):
        normalized = mode if mode in ('box', 'polygon') else 'polygon'
        self.buttons[normalized].setChecked(True)

    def mode(self):
        return ('box' if self.buttons['box'].isChecked() else 'polygon')

    def _emit_mode(self, _checked=False):
        button = self.sender()
        if button is not None:
            self.modeChanged.emit(str(button.property('outputMode')))


class EmptyWorkspacePage(QWidget):
    recentActivated = pyqtSignal(str)

    def __init__(self, open_image, open_folder, open_video, parent=None):
        super(EmptyWorkspacePage, self).__init__(parent)
        self.setObjectName('emptyWorkspacePage')
        title = QLabel('Start annotating')
        title.setObjectName('emptyWorkspaceTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        actions = QHBoxLayout()
        for label, action in (
                ('Open Image', open_image), ('Open Folder', open_folder),
                ('Open Video', open_video)):
            button = QPushButton(label)
            button.setDefault(False)
            button.clicked.connect(action.trigger)
            actions.addWidget(button)
        self.recent_title = QLabel('Recent')
        self.recent_title.setObjectName('emptyRecentTitle')
        self.recent_buttons = []
        recent_layout = QVBoxLayout()
        recent_layout.setSpacing(scale_px(4))
        for _index in range(5):
            button = QPushButton()
            button.setFlat(True)
            button.setVisible(False)
            button.clicked.connect(
                lambda _checked=False, widget=button:
                self.recentActivated.emit(widget.property('path')))
            self.recent_buttons.append(button)
            recent_layout.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale_px(48), scale_px(48), scale_px(48), scale_px(48))
        layout.addStretch(1)
        layout.addWidget(title)
        layout.addLayout(actions)
        layout.addSpacing(scale_px(24))
        layout.addWidget(self.recent_title)
        layout.addLayout(recent_layout)
        layout.addStretch(2)
        self.set_recent_paths(())

    def set_recent_paths(self, paths):
        visible = tuple(paths)[:5]
        self.recent_title.setVisible(bool(visible))
        for index, button in enumerate(self.recent_buttons):
            if index < len(visible):
                path = str(visible[index])
                button.setProperty('path', path)
                button.setText(os.path.basename(path.rstrip(os.sep)) or path)
                button.setToolTip(path)
                button.setVisible(True)
            else:
                button.setProperty('path', '')
                button.setVisible(False)


class CanvasChrome(QWidget):
    def __init__(self, zoom_out, zoom_widget, zoom_in, fit_window,
                 fit_width, actual_size, hide_all, show_all, parent=None):
        super(CanvasChrome, self).__init__(parent)
        self.setObjectName('canvasChrome')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            scale_px(6), scale_px(2), scale_px(6), scale_px(2))
        layout.setSpacing(scale_px(2))
        layout.addWidget(_action_button(zoom_out, self))
        zoom_widget.setFixedWidth(scale_px(56))
        layout.addWidget(zoom_widget)
        layout.addWidget(_action_button(zoom_in, self))
        layout.addSpacing(scale_px(8))
        for action in (fit_window, fit_width, actual_size):
            layout.addWidget(_action_button(action, self))
        self.sam_output_toggle = SamOutputModeToggle(parent=self)
        layout.addWidget(self.sam_output_toggle)
        layout.addSpacing(scale_px(8))
        self.annotation_session_hint = QLabel(self)
        self.annotation_session_hint.setObjectName('annotationSessionHint')
        # The hint is more important than leftover blank chrome. A zero
        # minimum let the trailing stretch collapse it completely at laptop
        # and split-inspector widths, leaving only the old status strip as an
        # explanation of the armed tool.
        self.annotation_session_hint.setMinimumWidth(scale_px(96))
        self.annotation_session_hint.setMaximumWidth(scale_px(520))
        self.annotation_session_hint.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.annotation_session_hint.hide()
        layout.addWidget(self.annotation_session_hint)
        layout.addStretch(1)
        visibility = QToolButton(self)
        visibility.setObjectName('annotationVisibilityButton')
        visibility.setIcon(show_all.icon())
        visibility.setToolTip('Annotation visibility')
        visibility.setFixedSize(scale_px(32), scale_px(32))
        visibility.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(visibility)
        menu.addAction(show_all)
        menu.addAction(hide_all)
        visibility.setMenu(menu)
        layout.addWidget(visibility)

    def set_annotation_session(self, text):
        """Show the next annotation gesture beside the active tool chrome."""
        value = str(text or '')
        # The durable state remains legible when the canvas column is narrow;
        # the complete next-gesture instruction stays in the tooltip and the
        # status projection.
        display = value.split(' · ', 1)[0]
        self.annotation_session_hint.setText(display)
        self.annotation_session_hint.setToolTip(value)
        self.annotation_session_hint.setVisible(bool(value))


class SaveErrorNotice(QWidget):
    """Persistent recovery surface for a failed annotation write."""

    retryRequested = pyqtSignal()
    saveAsRequested = pyqtSignal()

    def __init__(self, parent=None):
        super(SaveErrorNotice, self).__init__(parent)
        self.setObjectName('saveErrorNotice')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.title = QLabel('Annotations remain intact', self)
        self.title.setObjectName('saveErrorTitle')
        self.detail = QLabel(self)
        self.detail.setObjectName('saveErrorDetail')
        self.detail.setWordWrap(True)

        copy = QWidget(self)
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(scale_px(1))
        copy_layout.addWidget(self.title)
        copy_layout.addWidget(self.detail)

        self.retry_button = QPushButton('Retry save', self)
        self.retry_button.setObjectName('retrySaveButton')
        self.retry_button.clicked.connect(self.retryRequested.emit)
        self.save_as_button = QPushButton('Save as…', self)
        self.save_as_button.setObjectName('saveErrorSaveAsButton')
        self.save_as_button.clicked.connect(self.saveAsRequested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            scale_px(10), scale_px(6), scale_px(10), scale_px(6))
        layout.setSpacing(scale_px(8))
        layout.addWidget(copy, 1)
        layout.addWidget(self.retry_button)
        layout.addWidget(self.save_as_button)
        self.hide()

    def show_error(self, message):
        detail = 'Save failed: %s' % str(message or 'unknown error')
        self.detail.setText(detail)
        self.detail.setToolTip(detail)
        self.set_busy(False)
        self.show()

    def set_busy(self, busy):
        enabled = not bool(busy)
        self.retry_button.setEnabled(enabled)
        self.save_as_button.setEnabled(enabled)

    def clear(self):
        self.detail.clear()
        self.detail.setToolTip('')
        self.set_busy(False)
        self.hide()


class WorkspacePages(QWidget):
    EMPTY = 0
    CANVAS = 1
    GALLERY = 2
    OVERVIEW = 3

    #: Page names in stack order, so an index into the stack is an index into
    #: this tuple. set_page() and current_page() both read it: adding a page
    #: to one and not the other is how current_page() starts raising
    #: IndexError on the page it was never told about.
    PAGES = ('empty', 'canvas', 'gallery', 'overview')

    def __init__(self, scroll_area, timeline, gallery_page, status_widgets,
                 actions, zoom_widget, parent=None):
        super(WorkspacePages, self).__init__(parent)
        self.setObjectName('workspacePagesColumn')
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.stack = QStackedWidget(self)
        self.timeline = timeline
        self.stack.setObjectName('workspacePageStack')
        self.stack.setMinimumWidth(0)
        self.stack.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.empty_page = EmptyWorkspacePage(
            actions.open, actions.openDir, actions.openVideo, self.stack)
        self.stack.addWidget(self.empty_page)

        self.canvas_page = QWidget(self.stack)
        canvas_layout = QVBoxLayout(self.canvas_page)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self.canvas_chrome = CanvasChrome(
            actions.zoomOut, zoom_widget, actions.zoomIn,
            actions.fitWindow, actions.fitWidth, actions.zoomOrg,
            actions.hideAll, actions.showAll, self.canvas_page)
        self.sam_output_toggle = self.canvas_chrome.sam_output_toggle
        self.save_error_notice = SaveErrorNotice(self.canvas_page)
        canvas_layout.addWidget(self.canvas_chrome)
        canvas_layout.addWidget(self.save_error_notice)
        canvas_layout.addWidget(scroll_area, 1)
        canvas_layout.addWidget(timeline)
        self.stack.addWidget(self.canvas_page)

        self.gallery_page = gallery_page
        self.stack.addWidget(gallery_page)

        self.video_overview = VideoOverview(self.stack)
        self.stack.addWidget(self.video_overview)

        self.status_strip = QWidget(self)
        self.status_strip.setObjectName('workspaceStatusStrip')
        self.status_strip.setFixedHeight(scale_px(24))
        self.status_widgets = tuple(status_widgets)
        self._status_message = self.status_widgets[0].text()
        self.status_widgets[0].setMinimumWidth(0)
        self.status_widgets[0].setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        status_layout = QHBoxLayout(self.status_strip)
        status_layout.setContentsMargins(
            scale_px(6), 0, scale_px(6), 0)
        status_layout.setSpacing(scale_px(8))
        for index, widget in enumerate(status_widgets):
            status_layout.addWidget(widget, 1 if index == 0 else 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.status_strip)
        self.set_page('empty')

    def set_page(self, name):
        index = (self.PAGES.index(name) if name in self.PAGES
                 else self.EMPTY)
        self.stack.setCurrentIndex(index)

    def current_page(self):
        return self.PAGES[self.stack.currentIndex()]

    def set_video_visible(self, visible):
        self.timeline.setVisible(bool(visible))

    def set_status_message(self, text):
        """Show a status message, eliding it rather than clipping it.

        The label has an Ignored size policy so the strip can shrink it, but
        QLabel clips instead of eliding -- which silently truncated the save
        directory with no ellipsis and no tooltip to recover it.
        """
        self._status_message = text or ''
        self._refresh_status_message()

    def _refresh_status_message(self):
        label = self.status_widgets[0]
        label.setToolTip(self._status_message)
        available = label.width() - scale_px(4)
        if available <= 0:
            label.setText(self._status_message)
            return
        label.setText(label.fontMetrics().elidedText(
            self._status_message, Qt.TextElideMode.ElideMiddle, available))

    def resizeEvent(self, event):
        super(WorkspacePages, self).resizeEvent(event)
        self._update_status_visibility(event.size().width())
        self._refresh_status_message()

    # Dropped in this order as room runs out; the message, save state and
    # zoom chips are never dropped.
    _OPTIONAL_STATUS_ORDER = (7, 5, 3, 2, 4)

    def _update_status_visibility(self, width):
        """Hide status chips only once they genuinely stop fitting.

        A fixed pixel breakpoint measured the canvas column rather than the
        window, so an ordinary 1024px window dropped four chips while ~130px
        of slack sat unused beneath the stretch-1 message label.
        """
        layout = self.status_strip.layout()
        margins = layout.contentsMargins()
        spacing = layout.spacing()
        # Always leave the message label enough room to say something.
        available = (width - margins.left() - margins.right()
                     - scale_px(140))

        widths = [widget.sizeHint().width() for widget in self.status_widgets]
        needed = sum(widths[1:]) + spacing * max(0, len(widths) - 1)

        hidden = set()
        for index in self._OPTIONAL_STATUS_ORDER:
            if needed <= available:
                break
            hidden.add(index)
            needed -= widths[index] + spacing

        for index, widget in enumerate(self.status_widgets):
            widget.setVisible(index not in hidden)
