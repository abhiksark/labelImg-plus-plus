# libs/widgets/videoFramesView.py
"""The frames grid for smart-video projects.

Propagation writes an annotation on every frame, so a one-minute clip leaves
~1800 near-identical annotated frames behind.  This grid is where that
redundancy stops being a statistic: it shows the frames the distinctness
engine kept, and the chip row lets the user widen out to every annotated
frame or narrow down to the ones still awaiting review.

The three filters, stated once so they cannot drift apart:

* ``distinct``   -- the pts the engine handed us in ``distinct_pts``.
* ``annotated``  -- every pts carrying any observation at all.
* ``pending``    -- only the pts carrying a ``review_state == 'pending'``
  observation.  Not "anything unaccepted": ``rejected`` is a third state the
  project schema enforces, and a rejected frame is reviewed, not awaiting
  review.

Every filter selects *among annotated frames*.  ``distinct_pts`` arrives from
an engine reading the same state, so an entry with no observation on it means
the caller passed a list computed from an older state; showing a tile for it
would put a frame with nothing on it under a filter family whose whole domain
is annotated frames, and would let ``shown`` exceed ``total`` -- "1 of 0" from
a widget whose one job is making counts legible.  Such a pts is dropped, which
also keeps the no-track-filter case consistent with the track-filtered one
(narrowing already requires an observation to match against).

A track filter narrows whichever set the chip selected to the frames where
that one track is represented; it never widens it.  The total reported by
``countChanged`` is deliberately *not* narrowed: "2 of 1800" is the sentence
this view exists to say, and re-basing the total onto the current filter would
delete it.

This widget owns no media.  Thumbnails are a follow-up: decoding them needs
task_coordinator plumbing, so every tile is a placeholder captioned with its
pts, and the tile count and captions are the contract the tests hold.
"""

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QButtonGroup, QHBoxLayout, QListView, QListWidget, QListWidgetItem,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_theme_colors


#: The filter chips, in display order.  A closed set: an unknown name is a
#: programming error, not a state the user can reach.
FILTERS = ('distinct', 'annotated', 'pending')

FILTER_LABELS = {
    'distinct': 'Distinct',
    'annotated': 'Annotated',
    'pending': 'Pending',
}


def _index_observations(state):
    """Return ``(annotated, pending)`` maps of pts -> set of track ids.

    Both maps are keyed by pts so that two tracks annotated on the same frame
    count as one frame, which is what every count in this view means.
    """
    annotated = {}
    pending = {}
    for observation in getattr(state, 'observations', ()) or ():
        pts = int(observation.pts)
        annotated.setdefault(pts, set()).add(observation.track_id)
        if observation.review_state == 'pending':
            pending.setdefault(pts, set()).add(observation.track_id)
    return annotated, pending


class VideoFramesView(QWidget):
    """A grid of the frames a filter selected, one placeholder tile each."""

    frameActivated = pyqtSignal(int)
    countChanged = pyqtSignal(int, int)

    # Base pixel values; every use goes through scale_px at call time so a
    # display scale change is picked up without rebuilding the widget.
    TILE_SIZE = 96
    TILE_CAPTION_HEIGHT = 22
    TILE_SPACING = 5
    CHIP_SPACING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('videoFramesView')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._annotated = {}
        self._pending = {}
        self._distinct = ()
        self._track_ids = set()
        self._filter = 'distinct'
        self._track_filter = None
        self._visible_pts = []
        self._colors = get_theme_colors(Theme.LIGHT)
        self._setup_ui()
        self.apply_theme(Theme.LIGHT)

    def _setup_ui(self):
        self._chips = {}
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        chip_row = QHBoxLayout()
        chip_row.setContentsMargins(0, 0, 0, 0)
        chip_row.setSpacing(scale_px(self.CHIP_SPACING))
        for name in FILTERS:
            chip = QToolButton(self)
            chip.setObjectName('videoFramesChip')
            chip.setText(FILTER_LABELS[name])
            chip.setCheckable(True)
            chip.setChecked(name == self._filter)
            chip.setCursor(Qt.PointingHandCursor)
            # clicked, not toggled: set_filter checks the chip itself, and
            # toggled would send that back round as a second set_filter.
            chip.clicked.connect(
                lambda _checked, filter_name=name: self.set_filter(
                    filter_name))
            self._chip_group.addButton(chip)
            chip_row.addWidget(chip)
            self._chips[name] = chip
        chip_row.addStretch(1)

        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName('videoFramesGrid')
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setWrapping(True)
        self.list_widget.setSpacing(scale_px(self.TILE_SPACING))
        self.list_widget.setMovement(QListView.Static)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setWordWrap(False)
        self.list_widget.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.list_widget.itemClicked.connect(self._on_item_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scale_px(self.CHIP_SPACING))
        layout.addLayout(chip_row)
        layout.addWidget(self.list_widget)

    # -- model ----------------------------------------------------------

    def set_state(self, state, distinct_pts):
        """Rebuild the grid from *state* and the engine's distinct frames.

        A track filter naming a track the new state does not have is dropped:
        keeping it would leave the grid permanently and inexplicably empty.
        """
        self._annotated, self._pending = _index_observations(state)
        self._distinct = tuple(
            sorted({int(pts) for pts in distinct_pts or ()}))
        self._track_ids = {
            track.track_id for track in getattr(state, 'tracks', ()) or ()}
        if self._track_filter not in self._track_ids:
            self._track_filter = None
        self._refresh()

    def set_filter(self, name):
        """Select one of ``FILTERS`` and re-populate the grid."""
        if name not in FILTERS:
            raise ValueError('unknown frames filter: %r' % (name,))
        self._filter = name
        chip = self._chips[name]
        if not chip.isChecked():
            chip.setChecked(True)
        self._refresh()

    def set_track_filter(self, track_id):
        """Narrow to one track, or pass ``None`` to show every track.

        An unknown id is kept rather than ignored: the grid honestly shows
        nothing for a track that has no frames.
        """
        self._track_filter = track_id
        self._refresh()

    def track_filter(self):
        """The track the grid is narrowed to, or None."""
        return self._track_filter

    def filter_name(self):
        """The active filter chip, one of ``FILTERS``."""
        return self._filter

    def visible_pts(self):
        """The pts of the tiles on screen, ascending."""
        return list(self._visible_pts)

    def total_pts(self):
        """Every annotated pts, whatever the filters currently hide."""
        return len(self._annotated)

    def tile_count(self):
        return self.list_widget.count()

    def tile_captions(self):
        return [self.list_widget.item(row).text()
                for row in range(self.list_widget.count())]

    def chip_for(self, name):
        """The chip button for a filter, so callers can drive it as a user."""
        return self._chips[name]

    def activate_pts(self, pts):
        """Select the tile for *pts* and announce it; unseen pts are ignored."""
        pts = int(pts)
        if pts not in self._visible_pts:
            return
        self.list_widget.setCurrentRow(self._visible_pts.index(pts))
        self.frameActivated.emit(pts)

    # -- filtering ------------------------------------------------------

    def _membership(self):
        """The pts -> track ids map the active filter narrows against."""
        return self._pending if self._filter == 'pending' else self._annotated

    def _select_pts(self):
        if self._filter == 'distinct':
            selected = set(self._distinct)
        elif self._filter == 'annotated':
            selected = set(self._annotated)
        else:
            selected = set(self._pending)
        # Every filter selects among annotated frames; for 'annotated' and
        # 'pending' this is already true, so it only bites a stale distinct
        # pts.  Keeping it unconditional is what makes shown <= total hold.
        selected &= set(self._annotated)
        if self._track_filter is not None:
            membership = self._membership()
            selected = {pts for pts in selected
                        if self._track_filter in membership.get(pts, ())}
        return sorted(selected)

    def _refresh(self):
        self._visible_pts = self._select_pts()
        self._render()
        self.countChanged.emit(len(self._visible_pts), len(self._annotated))

    # -- rendering ------------------------------------------------------

    def _placeholder_icon(self, size):
        """A flat tile standing in for the frame image, until decode lands."""
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor(self._colors['placeholder']))
        painter = QPainter(pixmap)
        painter.setPen(QColor(self._colors['border']))
        painter.drawRect(0, 0, size - 1, size - 1)
        painter.end()
        return QIcon(pixmap)

    def _render(self):
        tile = scale_px(self.TILE_SIZE)
        spacing = scale_px(self.TILE_SPACING)
        self.list_widget.setSpacing(spacing)
        self.list_widget.setIconSize(QSize(tile, tile))
        self.list_widget.setGridSize(QSize(
            tile + 2 * spacing,
            tile + scale_px(self.TILE_CAPTION_HEIGHT) + 2 * spacing))
        icon = self._placeholder_icon(tile)
        self.list_widget.clear()
        for pts in self._visible_pts:
            item = QListWidgetItem(icon, str(pts))
            item.setData(Qt.UserRole, pts)
            item.setToolTip('PTS %d' % pts)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        if item is None:
            return
        self.frameActivated.emit(int(item.data(Qt.UserRole)))

    # -- theming --------------------------------------------------------

    def apply_theme(self, theme):
        colors = get_theme_colors(theme)
        self._colors = colors
        self.setStyleSheet("""
            #videoFramesView {{ background-color: {surface}; }}
            #videoFramesGrid {{
                background-color: {surface};
                border: none;
                color: {text};
            }}
            #videoFramesGrid::item:selected {{
                background: {accent_light};
                color: {accent_text};
            }}
            #videoFramesGrid::item:hover {{ background: {hover}; }}
            #videoFramesChip {{
                background-color: {surface_subtle};
                border: 1px solid {border};
                border-radius: {radius}px;
                color: {text_secondary};
                padding: {pad_v}px {pad_h}px;
            }}
            #videoFramesChip:hover {{ background-color: {hover}; }}
            #videoFramesChip:checked {{
                background-color: {accent_light};
                border-color: {accent};
                color: {accent_text};
            }}
        """.format(
            radius=scale_px(10), pad_v=scale_px(3), pad_h=scale_px(9),
            **{key: colors[key] for key in (
                'surface', 'surface_subtle', 'border', 'text',
                'text_secondary', 'accent', 'accent_light', 'accent_text',
                'hover')}))
        self._render()
