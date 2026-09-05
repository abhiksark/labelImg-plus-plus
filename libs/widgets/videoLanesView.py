# libs/widgets/videoLanesView.py
"""Per-track lanes for smart-video projects.

One horizontal lane per track, painted across the clip's duration, so that
"where did the tracker fail" is a glance rather than a scrub.  The view owns no
media and no model: it turns an immutable ``VideoModelState`` into plain
``Segment`` records and paints them.

Why a run spans first..last observation of its kind, and nothing more::

    anchor -> anchor    materialize_one interpolates between manual anchors,
                        so the span between them really is covered.
    tracker -> tracker   generated observations are per-frame dense, so the
                        span between them is covered too.
    anchor -> tracker    no interpolation crosses that boundary (only manual,
                        accepted, anchor observations are interpolation
                        anchors), so the space between the two runs is a hole
                        and is reported as ``absent``.

Segments therefore tile ``[0, duration_pts]`` for every track: every pts either
falls inside a filled run or inside an ``absent`` one.  ``absent`` is never
painted as a filled run; the lane background shows through it.

Coverage policy, stated once so the three "not this" cases agree:

* ``review_state == 'pending'`` outranks everything.  A frame awaiting review
  reads as ``pending`` even when it is a manual anchor, because the point of
  the lane is to find the frames that still need a human.
* Anything the user has marked as not-data contributes no coverage and breaks
  the run it falls in: a ``TrackGapRecord`` over the span it covers, and an
  observation that is ``review_state == 'rejected'`` or ``present`` False at
  its own pts.  The lane never claims coverage the user has rejected.
* That makes this view deliberately coarser than ``materialize_one``, which
  lets an exact observation outrank a gap and interpolates across a rejected
  frame between two anchors.  Both differences err the same way -- toward
  ``absent`` -- so the lane under-claims rather than hiding a hole, which is
  the safe direction for a view whose job is finding where tracking failed.
"""

from collections import namedtuple

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import QSizePolicy, QWidget

from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_theme_colors


Segment = namedtuple('Segment', ['track_id', 'start_pts', 'end_pts', 'kind'])

#: Filled segment kinds and the palette key each one paints with.  ``absent``
#: is missing on purpose: it is the lane background, not a fill.
KIND_COLOR_KEYS = {
    'anchor': 'track_anchor',
    'tracker': 'track_interpolated',
    'pending': 'track_pending',
}


def classify_observation(observation):
    """Return the segment kind an observation contributes, by precedence."""
    if observation.review_state == 'pending':
        return 'pending'
    if observation.source == 'manual' or observation.anchor:
        return 'anchor'
    return 'tracker'


def is_excluded(observation):
    """Return whether the user has marked this observation as not-data."""
    return observation.review_state == 'rejected' or not observation.present


def _merge_runs(observations):
    """Collapse observations into ``[start, end, kind]`` runs of one kind.

    An excluded observation is a barrier: it contributes nothing and closes
    the open run, so coverage never spans a frame the user rejected.
    """
    runs = []
    open_run = False
    for observation in sorted(observations, key=lambda item: int(item.pts)):
        if is_excluded(observation):
            open_run = False
            continue
        kind = classify_observation(observation)
        pts = int(observation.pts)
        if open_run and runs[-1][2] == kind:
            runs[-1][1] = pts
        else:
            runs.append([pts, pts, kind])
            open_run = True
    return runs


def _subtract_gaps(runs, gaps):
    """Remove every declared gap span from the runs it overlaps."""
    for gap_start, gap_end in gaps:
        remaining = []
        for start, end, kind in runs:
            if gap_end <= start or gap_start >= end:
                remaining.append([start, end, kind])
                continue
            if start < gap_start:
                remaining.append([start, gap_start, kind])
            if end > gap_end:
                remaining.append([gap_end, end, kind])
        runs = remaining
    return runs


def _tile(track_id, runs, duration_pts):
    """Return segments covering ``[0, duration_pts]`` with no holes."""
    if duration_pts <= 0:
        return ()
    segments = []
    cursor = 0
    for start, end, kind in runs:
        start = min(max(start, cursor), duration_pts)
        end = min(max(end, start), duration_pts)
        if start > cursor:
            segments.append(Segment(track_id, cursor, start, 'absent'))
        segments.append(Segment(track_id, start, end, kind))
        cursor = end
    if cursor < duration_pts:
        segments.append(Segment(track_id, cursor, duration_pts, 'absent'))
    return tuple(segments)


class VideoLanesView(QWidget):
    """A read-only projection of track coverage across the clip."""

    trackSelected = pyqtSignal(str)
    seekRequested = pyqtSignal(int)

    # Base pixel values; every use goes through scale_px at call time so a
    # display scale change is picked up without rebuilding the widget.
    LANE_HEIGHT = 34
    LABEL_WIDTH = 132
    LANE_PADDING = 7
    RIGHT_MARGIN = 8
    SWATCH_SIZE = 10
    MIN_RUN_WIDTH = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('videoLanesView')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._tracks = ()
        self._segments = {}
        self._duration_pts = 0
        self._selected_track_id = None
        self.apply_theme(Theme.LIGHT)

    # -- model ----------------------------------------------------------

    def set_state(self, state, duration_pts):
        """Rebuild every lane from *state*, discarding the previous one."""
        duration = max(0, int(duration_pts or 0))
        observations = {}
        for observation in state.observations:
            observations.setdefault(observation.track_id, []).append(
                observation)
        gaps = {}
        for gap in getattr(state, 'gaps', ()):
            gaps.setdefault(gap.track_id, []).append(
                (int(gap.start_pts), int(gap.end_pts)))

        segments = {}
        for track in state.tracks:
            runs = _merge_runs(observations.get(track.track_id, ()))
            runs = _subtract_gaps(runs, gaps.get(track.track_id, ()))
            segments[track.track_id] = _tile(track.track_id, runs, duration)

        self._tracks = tuple(state.tracks)
        self._segments = segments
        self._duration_pts = duration
        if self._selected_track_id not in segments:
            self._selected_track_id = None
        self.updateGeometry()
        self.update()

    def lane_count(self):
        return len(self._tracks)

    def lane_track_ids(self):
        return [track.track_id for track in self._tracks]

    def segments_for(self, track_id):
        return self._segments.get(track_id, ())

    def selection_colors(self):
        """The ``(fill, label)`` hex pair the selected lane paints with.

        Exposed as a pair because it is a contrast contract rather than two
        details: the label is drawn over the fill, so neither can be changed
        without reading the other.
        """
        return self._selected_color.name(), self._selected_text_color.name()

    def select_track(self, track_id):
        """Select a known lane and announce it; unknown ids are ignored."""
        if track_id not in self._segments:
            return
        self._selected_track_id = track_id
        self.update()
        self.trackSelected.emit(track_id)

    # -- theming --------------------------------------------------------

    def apply_theme(self, theme):
        colors = get_theme_colors(theme)
        self._kind_colors = {
            kind: QColor(colors[key]) for kind, key in KIND_COLOR_KEYS.items()}
        self._absent_color = QColor(colors['track_absent'])
        self._text_color = QColor(colors['text'])
        # The selected lane paints its label over its own fill, so the two
        # are chosen as a pair rather than separately: accent_light/accent_text
        # is the pair the palette guarantees is readable, and the same one the
        # overview toggle and the frames chips already select with.  Filling
        # with ``accent`` and lettering in ``text`` measured 3.1:1 in light and
        # 1.94:1 in dark -- selecting a lane made its label disappear.
        self._selected_color = QColor(colors['accent_light'])
        self._selected_text_color = QColor(colors['accent_text'])
        self._border_color = QColor(colors['border'])
        self.setStyleSheet(
            '#videoLanesView { background-color: %s; }' % colors['surface'])
        self.update()

    # -- geometry -------------------------------------------------------

    def sizeHint(self):
        lanes = max(1, len(self._tracks))
        return QSize(
            scale_px(self.LABEL_WIDTH) * 3, lanes * scale_px(self.LANE_HEIGHT))

    def minimumSizeHint(self):
        """Never shrink below the lanes there are.

        Lanes are a fixed height, so a widget shorter than their sum simply
        cannot paint the remainder.  Refusing to shrink is what turns that
        into a scrollbar in the enclosing ``QScrollArea`` -- which resizes its
        child to the viewport but no smaller than this -- rather than into
        lanes that silently do not exist.
        """
        return QSize(
            scale_px(self.LABEL_WIDTH + self.RIGHT_MARGIN),
            max(1, len(self._tracks)) * scale_px(self.LANE_HEIGHT))

    def _track_geometry(self):
        """Return the left edge and width of the painted lane area."""
        left = scale_px(self.LABEL_WIDTH)
        return left, max(1, self.width() - left - scale_px(self.RIGHT_MARGIN))

    def _pts_to_x(self, pts, left, width):
        if self._duration_pts <= 0:
            return left
        ratio = min(1.0, max(0.0, pts / self._duration_pts))
        return left + int(round(ratio * width))

    # -- painting -------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        lane_height = scale_px(self.LANE_HEIGHT)
        left, width = self._track_geometry()
        for index, track in enumerate(self._tracks):
            self._paint_lane(painter, track, index * lane_height, lane_height,
                             left, width)
        painter.end()

    def _paint_lane(self, painter, track, top, lane_height, left, width):
        padding = scale_px(self.LANE_PADDING)
        bar = QRect(left, top + padding, width, lane_height - 2 * padding)
        selected = track.track_id == self._selected_track_id
        if selected:
            painter.fillRect(
                QRect(0, top, self.width(), lane_height), self._selected_color)
        painter.fillRect(bar, self._absent_color)
        for segment in self._segments.get(track.track_id, ()):
            color = self._kind_colors.get(segment.kind)
            if color is None:
                continue
            start = self._pts_to_x(segment.start_pts, left, width)
            end = self._pts_to_x(segment.end_pts, left, width)
            run_width = max(scale_px(self.MIN_RUN_WIDTH), end - start)
            painter.fillRect(
                QRect(start, bar.top(), run_width, bar.height()), color)
        painter.setPen(self._border_color)
        painter.drawLine(0, top + lane_height - 1, self.width(),
                         top + lane_height - 1)
        self._paint_label(painter, track, top, lane_height, selected)

    def _paint_label(self, painter, track, top, lane_height, selected):
        swatch = scale_px(self.SWATCH_SIZE)
        padding = scale_px(self.LANE_PADDING)
        painter.fillRect(
            QRect(padding, top + (lane_height - swatch) // 2, swatch, swatch),
            QColor(*track.color))
        text_left = padding * 2 + swatch
        text_rect = QRect(
            text_left, top,
            max(1, scale_px(self.LABEL_WIDTH) - text_left - padding),
            lane_height)
        painter.setPen(
            self._selected_text_color if selected else self._text_color)
        metrics = QFontMetrics(painter.font())
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            metrics.elidedText(track.label, Qt.TextElideMode.ElideRight, text_rect.width()))

    # -- interaction ----------------------------------------------------

    def mousePressEvent(self, event):
        event_pos = event.position().toPoint()
        lane_height = scale_px(self.LANE_HEIGHT)
        index = int(event_pos.y() // lane_height)
        if event.button() != Qt.MouseButton.LeftButton or not 0 <= index < len(
                self._tracks):
            super().mousePressEvent(event)
            return
        self.select_track(self._tracks[index].track_id)
        left, width = self._track_geometry()
        if event_pos.x() < left or self._duration_pts <= 0:
            return
        ratio = min(1.0, max(0.0, (event_pos.x() - left) / width))
        self.seekRequested.emit(int(round(ratio * self._duration_pts)))
