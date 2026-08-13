# libs/widgets/videoOverview.py
"""The smart-video overview: two readings of one clip, kept in step.

The lanes answer "where did tracking fail" and the grid answers "which frames
actually carry new information". They are the same question asked along the two
axes of the same data, so they must never disagree, and this container is where
that agreement is enforced:

* One distinct-frames answer. The container -- not the grid -- builds the
  ``DistinctnessPlan``, so the grid and bounded pixel pass can never receive
  answers computed from different state.
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
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from libs.core.video_distinctness import (
    DistinctnessPlan, build_distinctness_plan,
)
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
        self._plan = DistinctnessPlan((), (), ())
        self._geometry_pts = ()
        self._distinct_pts = ()
        self._refining = False
        self._setup_ui()
        self._connect()
        self._set_count(0, 0)
        self.apply_theme(Theme.LIGHT)

    def _setup_ui(self):
        self.lanes = VideoLanesView(self)
        self.frames = VideoFramesView(self)

        # A lane is a fixed height, so a clip with more tracks than fit is the
        # normal case, not the edge one.  Without this the surplus lanes are
        # unpaintable and unreachable, with nothing on screen saying so.  The
        # grid needs no equivalent: its list widget scrolls itself.
        self.lanes_scroll = QScrollArea(self)
        self.lanes_scroll.setObjectName('videoOverviewLanesScroll')
        self.lanes_scroll.setWidgetResizable(True)
        self.lanes_scroll.setFrameShape(QFrame.NoFrame)
        self.lanes_scroll.setWidget(self.lanes)
        #: The stack page for each view.  Lanes scroll, frames do not, so the
        #: page and the view are not always the same widget.
        self._pages = {'lanes': self.lanes_scroll, 'frames': self.frames}

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

        self.refining_label = QLabel('Refining…', self)
        self.refining_label.setObjectName('videoOverviewRefining')
        self.refining_label.hide()
        header.addWidget(self.refining_label)

        self.count_label = QLabel(self)
        self.count_label.setObjectName('videoOverviewCount')
        header.addWidget(self.count_label)

        self.readiness_label = QLabel(self)
        self.readiness_label.setObjectName('videoOverviewReadiness')
        self.readiness_label.setWordWrap(True)
        self.review_button = QToolButton(self)
        self.review_button.setObjectName('videoOverviewReview')
        self.review_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.export_button = QToolButton(self)
        self.export_button.setObjectName('videoOverviewExport')
        self.export_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        readiness = QHBoxLayout()
        readiness.setContentsMargins(
            scale_px(9), scale_px(6), scale_px(7), scale_px(6))
        readiness.setSpacing(scale_px(6))
        readiness.addWidget(self.readiness_label, 1)
        readiness.addWidget(self.review_button)
        readiness.addWidget(self.export_button)

        self.stack = QStackedWidget(self)
        self.stack.setObjectName('videoOverviewStack')
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        for name in VIEWS:
            self.stack.addWidget(self._pages[name])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(self.HEADER_SPACING))
        layout.addLayout(header)
        layout.addLayout(readiness)
        layout.addWidget(self.stack)

    def _connect(self):
        self.lanes.trackSelected.connect(self.frames.set_track_filter)
        self.lanes.seekRequested.connect(self.seekRequested)
        self.frames.frameActivated.connect(self.seekRequested)
        self.frames.countChanged.connect(self._set_count)

    def set_workflow_actions(self, review_action, export_action):
        """Project the host's authoritative review and export commands."""
        self.review_button.setDefaultAction(review_action)
        self.export_button.setDefaultAction(export_action)

    # -- model ----------------------------------------------------------

    def set_state(self, state, duration_pts, start_pts=0,
                  time_base_num=1, time_base_den=1):
        """Rebuild both views from *state*, discarding any refinement.

        The refinement was computed against the previous state's frames, so
        carrying it over would show frames this state may not even annotate.
        """
        self._state = state
        self._plan = build_distinctness_plan(
            state, start_pts=start_pts, time_base_num=time_base_num,
            time_base_den=time_base_den)
        self._geometry_pts = self._plan.selected_pts
        self._distinct_pts = self._geometry_pts
        self.set_refining(False)
        self.lanes.set_state(state, duration_pts)
        self.frames.set_state(state, self._geometry_pts)
        self._set_readiness(state)
        return self._plan

    def _set_readiness(self, state):
        observations = tuple(getattr(state, 'observations', ()) or ())
        pending = sum(1 for item in observations
                      if item.review_state == 'pending')
        accepted_pts = {
            int(item.pts) for item in observations
            if item.present and item.review_state == 'accepted'}
        accepted = len(accepted_pts)
        if pending:
            self.readiness_label.setText(
                '%d suggestion%s %s review · annotated export currently '
                'includes %d accepted frame%s' % (
                    pending, '' if pending == 1 else 's',
                    'needs' if pending == 1 else 'need', accepted,
                    '' if accepted == 1 else 's'))
        elif accepted:
            self.readiness_label.setText(
                'Review complete · ready to export %d accepted frame%s' % (
                    accepted, '' if accepted == 1 else 's'))
        else:
            self.readiness_label.setText(
                'Add and accept annotations before exporting annotated frames')
        self.review_button.setVisible(bool(pending))
        self.export_button.setVisible(bool(accepted))

    def readiness_text(self):
        return self.readiness_label.text()

    def set_refined_pts(self, pts):
        """Add the pixel pass's frames to the geometry answer.

        Union, not replacement: refinement runs on a worker and may be
        cancelled or fail, and the geometry answer must survive that intact.
        Each call re-derives from the geometry answer rather than accumulating,
        so a later, narrower refinement replaces an earlier one instead of
        stacking with it -- the grid shows one pass's result, not their sum.

        A refinement arriving before any state is dropped: there is no
        geometry answer to union it with, and recording it would make
        ``distinct_pts`` name frames the grid has nothing to show for.
        """
        if self._state is None:
            return
        sampled = set(self._plan.sample_pts)
        refined = set(self._geometry_pts) | {
            int(value) for value in pts or () if int(value) in sampled}
        self._distinct_pts = tuple(sorted(refined))
        self.frames.set_state(self._state, self._distinct_pts)

    def distinctness_plan(self):
        """The immutable plan shared with the current pixel pass."""
        return self._plan

    def distinct_pts(self):
        """The distinct frames as the grid is currently showing them.

        The union of the geometry answer and the current bounded refinement.
        """
        return self._distinct_pts

    def set_refining(self, refining):
        """Show a quiet progress hint without replacing the frame count."""
        self._refining = bool(refining)
        self.refining_label.setVisible(self._refining)

    def is_refining(self):
        return self._refining

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
            #videoOverviewLanesScroll {{
                background-color: {surface};
                border: none;
            }}
            #videoOverviewCount, #videoOverviewRefining {{
                background-color: transparent;
                color: {text_secondary};
            }}
            #videoOverviewReadiness {{
                background-color: {surface_subtle};
                border: 1px solid {border};
                border-radius: {radius}px;
                color: {text_secondary};
                padding: {pad_v}px {pad_h}px;
            }}
            #videoOverviewReview, #videoOverviewExport {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: {radius}px;
                color: {accent_text};
                padding: {pad_v}px {pad_h}px;
            }}
            #videoOverviewExport {{
                background-color: {accent};
                border-color: {accent};
                color: {on_accent};
            }}
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
                'accent', 'accent_light', 'accent_text', 'on_accent',
                'hover')}))
