# libs/widgets/videoOverview.py
"""The smart-video overview: two readings of one clip, kept in step.

The lanes answer "where did tracking fail" and the grid answers "which frames
actually carry new information". They are the same question asked along the two
axes of the same data, so they must never disagree, and this container is where
that agreement is enforced:

* One distinct-frames answer. The container -- not the grid -- calls
  ``geometry_distinct_pts``, so the grid can never be handed a set computed
  from a different state than the lanes were built from.
* One selection. Picking a lane narrows the grid to that track, so switching
  view keeps the subject rather than resetting it.
* One seek. Either child asking to seek reaches the host as this widget's own
  ``seekRequested``; the host wires one signal, not two.

Refinement is additive by construction. ``set_refined_pts`` unions the pixel
pass's answer with the geometry answer it was seeded from, so a partial,
cancelled or stale refinement can only ever leave the geometry answer standing
-- the same promise ``video_distinctness_worker`` makes, restated here because
this is the last place the two answers meet before the user sees them.

Both children are self-styled panels that construct light, so ``apply_theme``
forwards to each of them: this widget is the only thing the host themes.
"""

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget)

from libs.core.video_distinctness import geometry_distinct_pts
from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_theme_colors
from libs.widgets.videoFramesView import VideoFramesView
from libs.widgets.videoLanesView import VideoLanesView


#: The two pages, in display order. The stack is filled in this order, so an
#: index into it is an index into this tuple. A closed set: an unknown name is
#: a programming error, not a state the user can reach.
VIEWS = ('lanes', 'frames')

VIEW_LABELS = {
    'lanes': 'Lanes',
    'frames': 'Frames',
}


class VideoOverview(QWidget):
    """A toggle between the track lanes and the distinct-frames grid."""

    seekRequested = pyqtSignal(int)

    #: Kept as a template so the count reads the same wherever it is shown.
    COUNT_FORMAT = '%d of %d frames'

    # Base pixel values; every use goes through scale_px at call time so a
    # display scale change is picked up without rebuilding the widget.
    HEADER_SPACING = 6
    BUTTON_RADIUS = 10
    BUTTON_PADDING_V = 3
    BUTTON_PADDING_H = 11

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('videoOverview')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._state = None
        self._geometry_pts = ()
        self._setup_ui()
        self._connect()
        self._set_count(0, 0)
        self.apply_theme(Theme.LIGHT)

    def _setup_ui(self):
        self.lanes = VideoLanesView(self)
        self.frames = VideoFramesView(self)

        self._buttons = {}
        button_group = QButtonGroup(self)
        button_group.setExclusive(True)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(scale_px(self.HEADER_SPACING))
        for name in VIEWS:
            button = QToolButton(self)
            button.setObjectName('videoOverviewToggle')
            button.setText(VIEW_LABELS[name])
            button.setCheckable(True)
            button.setChecked(name == VIEWS[0])
            button.setCursor(Qt.PointingHandCursor)
            # clicked, not toggled: set_view checks the button itself, and
            # toggled would send that back round as a second set_view.
            button.clicked.connect(
                lambda _checked, view=name: self.set_view(view))
            button_group.addButton(button)
            header.addWidget(button)
            self._buttons[name] = button
        header.addStretch(1)

        self.count_label = QLabel(self)
        self.count_label.setObjectName('videoOverviewCount')
        header.addWidget(self.count_label)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName('videoOverviewStack')
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for name in VIEWS:
            self.stack.addWidget(getattr(self, name))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(self.HEADER_SPACING))
        layout.addLayout(header)
        layout.addWidget(self.stack)

    def _connect(self):
        self.lanes.trackSelected.connect(self.frames.set_track_filter)
        self.lanes.seekRequested.connect(self.seekRequested)
        self.frames.frameActivated.connect(self.seekRequested)
        self.frames.countChanged.connect(self._set_count)

    # -- model ----------------------------------------------------------

    def set_state(self, state, duration_pts):
        """Rebuild both views from *state*, discarding any refinement.

        The refinement was computed against the previous state's frames, so
        carrying it over would show frames this state may not even annotate.
        """
        self._state = state
        self._geometry_pts = geometry_distinct_pts(state)
        self.lanes.set_state(state, duration_pts)
        self.frames.set_state(state, self._geometry_pts)

    def set_refined_pts(self, pts):
        """Add the pixel pass's frames to the geometry answer.

        Union, not replacement: refinement runs on a worker and may be
        cancelled or fail, and the geometry answer must survive that intact.
        """
        refined = set(self._geometry_pts) | {int(value) for value in pts or ()}
        self.frames.set_state(self._state, tuple(sorted(refined)))

    def distinct_pts(self):
        """The geometry answer the grid was seeded with."""
        return self._geometry_pts

    # -- the view toggle ------------------------------------------------

    def set_view(self, name):
        """Show one of ``VIEWS``."""
        if name not in VIEWS:
            raise ValueError('unknown overview view: %r' % (name,))
        self.stack.setCurrentIndex(VIEWS.index(name))
        button = self._buttons[name]
        if not button.isChecked():
            button.setChecked(True)

    def current_view(self):
        """The page on screen, one of ``VIEWS``."""
        return VIEWS[self.stack.currentIndex()]

    def view_button(self, name):
        """The toggle button for a view, so callers can drive it as a user."""
        return self._buttons[name]

    # -- the live count -------------------------------------------------

    def _set_count(self, shown, total):
        self.count_label.setText(self.COUNT_FORMAT % (shown, total))

    def count_text(self):
        """The count as the user reads it."""
        return self.count_label.text()

    # -- theming --------------------------------------------------------

    def apply_theme(self, theme):
        colors = get_theme_colors(theme)
        self.lanes.apply_theme(theme)
        self.frames.apply_theme(theme)
        self.setStyleSheet("""
            #videoOverview {{ background-color: {surface}; }}
            #videoOverviewStack {{ background-color: {surface}; }}
            #videoOverviewCount {{ color: {text_secondary}; }}
            #videoOverviewToggle {{
                background-color: {surface_subtle};
                border: 1px solid {border};
                border-radius: {radius}px;
                color: {text_secondary};
                padding: {pad_v}px {pad_h}px;
            }}
            #videoOverviewToggle:hover {{ background-color: {hover}; }}
            #videoOverviewToggle:checked {{
                background-color: {accent_light};
                border-color: {accent};
                color: {accent_text};
            }}
        """.format(
            radius=scale_px(self.BUTTON_RADIUS),
            pad_v=scale_px(self.BUTTON_PADDING_V),
            pad_h=scale_px(self.BUTTON_PADDING_H),
            **{key: colors[key] for key in (
                'surface', 'surface_subtle', 'border', 'text_secondary',
                'accent', 'accent_light', 'accent_text', 'hover')}))
