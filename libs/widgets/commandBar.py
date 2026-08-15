# libs/widgets/commandBar.py
"""Compact application command bar for the annotation workspace."""

try:
    from PyQt5.QtCore import Qt, QSize
    from PyQt5.QtWidgets import (
        QHBoxLayout, QLabel, QLayout, QMenu, QSizePolicy, QToolButton, QWidget,
    )
except ImportError:
    from PyQt4.QtCore import Qt, QSize
    from PyQt4.QtGui import (
        QHBoxLayout, QLabel, QLayout, QMenu, QSizePolicy, QToolButton, QWidget,
    )

from libs.utils.dpi import scale_px
from libs.utils.styles import (
    COMMAND_BAR_HEIGHT, Theme, get_command_bar_style,
)
from libs.utils.utils import new_icon, themed_icon


class CommandBar(QWidget):
    """Expose high-frequency commands without duplicating their state.

    Every command-bearing control wraps a ``QAction`` owned by ``MainWindow``.
    The bar therefore mirrors shortcut, checked, enabled, text, icon, and
    plugin state instead of introducing a second command layer.
    """

    _FORMAT_BREAKPOINT = 900
    _SAVE_STATE_BREAKPOINT = 1040
    _APP_LABEL_BREAKPOINT = 720
    _POSITION_BREAKPOINT = 640

    def __init__(self, application_name, menus, open_entries,
                 previous_action, next_action, save_action, verify_action,
                 format_action, overflow_entries=(), primary_action=None,
                 parent=None):
        super(CommandBar, self).__init__(parent)
        self.setObjectName('workspaceCommandBar')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(scale_px(COMMAND_BAR_HEIGHT))

        self.application_menu = QMenu(self)
        self.application_menu.setObjectName('applicationMenu')
        for menu in menus:
            self.application_menu.addMenu(menu)

        self.application_button = self._menu_button(
            application_name, 'app', self.application_menu,
            'applicationMenuButton', 'Application menu')

        self.open_menu = QMenu(self)
        self.open_menu.setObjectName('openMenu')
        self._add_entries(self.open_menu, open_entries)
        self.open_button = self._menu_button(
            'Open', 'open', self.open_menu, 'openMenuButton',
            'Open an image, folder, annotation, or video')

        self.dirty_indicator = QLabel('•')
        self.dirty_indicator.setObjectName('documentDirtyIndicator')
        self.dirty_indicator.setToolTip('Unsaved changes')
        self.dirty_indicator.hide()

        self.save_state_label = QLabel('Saved')
        self.save_state_label.setObjectName('documentSaveState')
        self.save_state_label.setAccessibleName('Document save state')

        self.document_label = QLabel('No document')
        self.document_label.setObjectName('documentLabel')
        self.document_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.document_label.setMinimumWidth(scale_px(80))
        self.document_label.setAccessibleName('Current document')

        self.previous_button = self._action_button(
            previous_action, 'previousButton', 'Previous')
        self.position_label = QLabel('— / —')
        self.position_label.setObjectName('documentPosition')
        self.position_label.setAlignment(Qt.AlignCenter)
        self.position_label.setMinimumWidth(scale_px(76))
        self.position_label.setAccessibleName('Document position')
        self.next_button = self._action_button(
            next_action, 'nextButton', 'Next')

        self.primary_button = self._action_button(
            primary_action or next_action, 'primaryActionButton',
            'Complete current item')
        self.primary_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.save_button = self._action_button(
            save_action, 'saveButton', 'Save')
        self.save_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.verify_button = self._action_button(
            verify_action, 'verifyButton', 'Verify')
        self.verify_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        # Save and Verify remain authoritative and reachable in overflow, but
        # they are no longer peers of the state-derived completion action.
        # Keep these projections for compatibility/tests without giving the
        # annotator three competing ways to finish the current item.
        self.save_button.setParent(self)
        self.save_button.hide()
        self.verify_button.setParent(self)
        self.verify_button.hide()
        self.format_button = self._action_button(
            format_action, 'formatButton', 'Annotation format')
        self.format_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.overflow_menu = QMenu(self)
        self.overflow_menu.setObjectName('commandOverflowMenu')
        self._add_entries(self.overflow_menu, overflow_entries)
        self.overflow_button = self._menu_button(
            '', 'settings', self.overflow_menu, 'overflowButton',
            'More commands')

        layout = QHBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        layout.setContentsMargins(scale_px(8), 0, scale_px(8), 0)
        layout.setSpacing(scale_px(4))
        layout.addWidget(self.application_button)
        layout.addWidget(self.open_button)
        layout.addSpacing(scale_px(4))
        layout.addWidget(self.dirty_indicator)
        layout.addWidget(self.document_label, 1)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.position_label)
        layout.addWidget(self.next_button)
        layout.addSpacing(scale_px(4))
        layout.addWidget(self.save_state_label)
        layout.addWidget(self.primary_button)
        layout.addWidget(self.format_button)
        layout.addWidget(self.overflow_button)

        self.apply_theme(Theme.LIGHT)

    @staticmethod
    def _add_entries(menu, entries):
        for entry in entries:
            if entry is None:
                menu.addSeparator()
            elif isinstance(entry, QMenu):
                menu.addMenu(entry)
            else:
                menu.addAction(entry)

    @staticmethod
    def _action_button(action, object_name, accessible_name):
        button = QToolButton()
        button.setObjectName(object_name)
        button.setDefaultAction(action)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setIconSize(QSize(scale_px(18), scale_px(18)))
        button.setAccessibleName(accessible_name)
        return button

    @staticmethod
    def _menu_button(text, icon_name, menu, object_name, accessible_name):
        button = QToolButton()
        button.setObjectName(object_name)
        button.setText(text)
        button.setIcon(new_icon(icon_name))
        button.setProperty('iconName', icon_name)
        button.setIconSize(QSize(scale_px(18), scale_px(18)))
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setMenu(menu)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.StrongFocus)
        button.setAccessibleName(accessible_name)
        return button

    def set_document(self, name, dirty=False, full_path=None, read_only=False,
                     provisional=False):
        display = name or 'No document'
        if read_only:
            display += ' · Read only'
        self.document_label.setText(display)
        self.document_label.setToolTip(full_path or display)
        self.dirty_indicator.setVisible(bool(dirty))
        if read_only:
            state = 'Read only'
        elif provisional and dirty:
            state = 'Unsaved changes · provisional object'
        elif provisional:
            state = 'Provisional object · not saved'
        elif dirty:
            state = 'Unsaved changes'
        else:
            state = 'Saved'
        self.save_state_label.setText(state)
        self.save_state_label.setToolTip(state)

    def set_position(self, text):
        self.position_label.setText(text or '— / —')

    def set_primary_text(self, text):
        """Render a literal ampersand without changing the QAction text."""
        value = str(text or '')
        self.primary_button.setText(value.replace('&', '&&'))
        self.primary_button.setAccessibleName(value)

    def apply_theme(self, theme):
        self._current_theme = theme
        self.setStyleSheet(get_command_bar_style(theme))
        # Menu buttons own their icon instead of following an action, so the
        # window-wide action re-icon pass does not reach them.
        for button in self.findChildren(QToolButton):
            icon_name = button.property('iconName')
            if icon_name:
                button.setIcon(new_icon(icon_name) if icon_name == 'app'
                               else themed_icon(icon_name, theme))

    def resizeEvent(self, event):
        """Move lower-priority labels into the always-present overflow menu."""
        width = event.size().width()
        self.format_button.setVisible(width >= scale_px(self._FORMAT_BREAKPOINT))
        self.save_state_label.setVisible(
            width >= scale_px(self._SAVE_STATE_BREAKPOINT))
        self.application_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
            if width >= scale_px(self._APP_LABEL_BREAKPOINT)
            else Qt.ToolButtonIconOnly)
        self.position_label.setVisible(
            width >= scale_px(self._POSITION_BREAKPOINT))
        super(CommandBar, self).resizeEvent(event)
