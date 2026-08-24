"""PTS-based controls and marker strip for smart-video documents."""

from dataclasses import dataclass
import re
import weakref

try:
    from PyQt5.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
    from PyQt5.QtGui import (
        QBrush, QColor, QIcon, QKeySequence, QPainter, QPen, QPixmap,
        QPolygon,
    )
    from PyQt5.QtWidgets import (
        QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
        QSizePolicy, QSlider, QStyle, QToolButton, QVBoxLayout, QWidget,
    )
    _QT5 = True
except ImportError:
    from PyQt4.QtCore import (
        QEvent, QPoint, QRegExp, Qt, QTimer, pyqtSignal,
    )
    from PyQt4.QtGui import (
        QBrush, QColor, QComboBox, QHBoxLayout, QIcon, QKeySequence, QLabel,
        QLineEdit, QMenu, QPainter, QPen, QPixmap, QPolygon, QPushButton,
        QRegExpValidator, QSizePolicy, QSlider, QStyle, QToolButton, QVBoxLayout,
        QWidget,
    )
    _QT5 = False

if _QT5:
    try:
        from PyQt5.QtCore import QRegularExpression
        from PyQt5.QtGui import QRegularExpressionValidator
        _REGULAR_EXPRESSION_VALIDATOR = True
    except ImportError:
        from PyQt5.QtCore import QRegExp
        from PyQt5.QtGui import QRegExpValidator
        _REGULAR_EXPRESSION_VALIDATOR = False
else:
    _REGULAR_EXPRESSION_VALIDATOR = False

from libs.core.video_types import VideoFrameRef


TIMELINE_MAX = 1_000_000
_TIMECODE_PATTERN = r'^(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})$'
_TIMECODE = re.compile(_TIMECODE_PATTERN)
_MARKER_SPECS = (
    ('accepted', 'Accepted', 'solid-tick'),
    ('pending', 'Pending', 'hollow-diamond'),
    ('verified', 'Verified', 'bottom-triangle'),
    ('propagation', 'Propagation', 'hatched-span'),
    ('gap', 'Gaps', 'crossed-span'),
)
_MARKER_COLORS = {
    'accepted': (45, 180, 90, 255),
    'pending': (235, 165, 35, 255),
    'verified': (125, 90, 220, 255),
    'propagation': (70, 140, 220, 190),
    'gap': (200, 75, 75, 190),
}
_PATTERN_NAMES = {
    'solid-tick': 'solid tick',
    'hollow-diamond': 'hollow diamond',
    'bottom-triangle': 'bottom triangle',
    'hatched-span': 'hatched span',
    'crossed-span': 'crossed span',
}


@dataclass(frozen=True)
class TimelineMarkerGroup:
    """One immutable semantic marker layer in normalized slider space."""

    kind: str
    label: str
    pattern: str
    ranges: tuple


def _marker_range(value):
    if isinstance(value, (tuple, list)) and len(value) == 2:
        start, end = value
    else:
        start = end = value
    start = int(start)
    end = int(end)
    return (min(start, end), max(start, end))


def _normalize_marker_range(value):
    start, end = _marker_range(value)
    start = max(0, min(TIMELINE_MAX, start))
    end = max(0, min(TIMELINE_MAX, end))
    return (start, end)


def _normalize_marker_ranges(values):
    return tuple(sorted(_normalize_marker_range(value) for value in values))


def _marker_ranges(values):
    return tuple(sorted(_marker_range(value) for value in values))


def _marker_group_summary(group):
    first = min(item[0] for item in group.ranges)
    last = max(item[1] for item in group.ranges)
    range_text = str(first) if first == last else '%s–%s' % (first, last)
    kind = group.kind
    if kind == 'gap' and len(group.ranges) != 1:
        kind = 'gaps'
    return '%s %s, range %s' % (len(group.ranges), kind, range_text)


def _draw_marker_treatment(painter, pattern, color, x, x_end, height):
    if pattern in ('hatched-span', 'crossed-span'):
        brush_style = (Qt.BDiagPattern
                       if pattern == 'hatched-span' else Qt.CrossPattern)
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color, brush_style))
        painter.drawRect(x, 1, max(2, x_end - x), 5)
    elif pattern == 'solid-tick':
        painter.setPen(QPen(color, 2))
        painter.drawLine(x, 0, x, 7)
    elif pattern == 'hollow-diamond':
        painter.setPen(QPen(color, 2))
        painter.setBrush(QBrush(Qt.NoBrush))
        painter.drawPolygon(QPolygon((
            QPoint(x, 0), QPoint(x + 4, 4), QPoint(x, 8),
            QPoint(x - 4, 4))))
    elif pattern == 'bottom-triangle':
        bottom = height - 1
        painter.setPen(QPen(color, 1))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(QPolygon((
            QPoint(x - 4, bottom), QPoint(x + 4, bottom),
            QPoint(x, bottom - 7))))


def _marker_treatment_icon(kind, pattern):
    pixmap = QPixmap(18, 12)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, False)
    _draw_marker_treatment(
        painter, pattern, QColor(*_MARKER_COLORS[kind]), 9, 15, 12)
    painter.end()
    return QIcon(pixmap)


def _timecode_validator(parent):
    if _REGULAR_EXPRESSION_VALIDATOR:
        expression = QRegularExpression(_TIMECODE_PATTERN)
        return QRegularExpressionValidator(expression, parent)
    return QRegExpValidator(QRegExp(_TIMECODE_PATTERN), parent)


def format_timecode(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return '%02d:%02d:%02d.%03d' % (hours, minutes, secs, millis)


def parse_timecode(value):
    match = _TIMECODE.fullmatch(str(value).strip())
    if match is None:
        raise ValueError('Use HH:MM:SS.mmm')
    hours, minutes, seconds, millis = map(int, match.groups())
    total_millis = (
        ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis)
    try:
        return total_millis / 1000.0
    except OverflowError:
        raise ValueError('Timecode is outside the supported range')


class _MarkerSlider(QSlider):
    """A standard slider with a compact non-interactive marker overlay."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._marker_groups = ()
        self.spans = ()
        self.accepted = ()
        self.pending = ()
        self.verified = ()
        self.gaps = ()
        self.setAccessibleName('Video timeline')
        self.setAccessibleDescription(self.accessible_marker_summary())

    def set_markers(self, spans=(), accepted=(), pending=(), verified=(),
                    propagation=(), gaps=()):
        values_by_kind = {
            'accepted': _normalize_marker_ranges(accepted),
            'pending': _normalize_marker_ranges(pending),
            'verified': _normalize_marker_ranges(verified),
            'propagation': _normalize_marker_ranges(
                tuple(spans) + tuple(propagation)),
            'gap': _normalize_marker_ranges(gaps),
        }
        self._marker_groups = tuple(
            TimelineMarkerGroup(kind, label, pattern, values_by_kind[kind])
            for kind, label, pattern in _MARKER_SPECS
            if values_by_kind[kind])
        self.spans = values_by_kind['propagation']
        self.accepted = tuple(item[0] for item in values_by_kind['accepted'])
        self.pending = tuple(item[0] for item in values_by_kind['pending'])
        self.verified = tuple(item[0] for item in values_by_kind['verified'])
        self.gaps = values_by_kind['gap']
        self.setAccessibleDescription(self.accessible_marker_summary())
        self.update()

    def marker_groups(self):
        return self._marker_groups

    def accessible_marker_summary(self):
        if not self._marker_groups:
            return 'No timeline markers'
        return 'Timeline markers: %s' % '; '.join(
            _marker_group_summary(group) for group in self._marker_groups)

    def paintEvent(self, event):
        super().paintEvent(event)
        width = max(1, self.width() - 12)
        left = 6
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        for group in self._marker_groups:
            color = QColor(*_MARKER_COLORS[group.kind])
            for start, _end in group.ranges:
                x = left + int(start * width / TIMELINE_MAX)
                x_end = left + int(_end * width / TIMELINE_MAX)
                _draw_marker_treatment(
                    painter, group.pattern, color, x, x_end, self.height())
        painter.end()


class VideoTimelineWidget(QWidget):
    """Bottom-dock controls that emit immutable frame references."""

    seekRequested = pyqtSignal(object)
    previousRequested = pyqtSignal()
    nextRequested = pyqtSignal()
    playPauseRequested = pyqtSignal()
    speedChanged = pyqtSignal(float)
    timeInputError = pyqtSignal(str)
    focusReturnRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._snapshot = None
        self._dragging = False
        self._drag_seek_value = None
        self._drag_emitted_value = None
        self._playing = False
        self._playback_action = None
        self._playback_action_destroyed_slot = None
        self._propagation_running = False
        self._projecting_position = False
        self._pending_seek_value = None
        self._displayed_timecode = '00:00:00.000'
        self._displayed_pts = None
        self._marker_pts_by_kind = {}
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(50)
        self._debounce.timeout.connect(self._emit_slider_seek)

        style = self.style()
        self.play_button = QPushButton()
        self.play_button.setCheckable(True)
        self.previous_button = QPushButton()
        self.previous_button.setIcon(
            style.standardIcon(QStyle.SP_MediaSkipBackward))
        self.previous_button.setToolTip('Previous frame (A)')
        self.previous_button.setAccessibleName('Previous frame')
        self.next_button = QPushButton()
        self.next_button.setIcon(
            style.standardIcon(QStyle.SP_MediaSkipForward))
        self.next_button.setToolTip('Next frame (D)')
        self.next_button.setAccessibleName('Next frame')
        self.time_edit = QLineEdit('00:00:00.000')
        self.time_edit.setValidator(_timecode_validator(self.time_edit))
        self.time_edit.installEventFilter(self)
        self.time_edit.setMaximumWidth(110)
        self.time_edit.setToolTip('Exact presentation time (HH:MM:SS.mmm)')
        self.time_edit.setAccessibleName('Exact video time')
        self.speed_combo = QComboBox()
        for speed in (0.25, 0.5, 1.0, 2.0):
            self.speed_combo.addItem('%gx' % speed, speed)
        self.speed_combo.setCurrentIndex(2)
        self.speed_combo.setAccessibleName('Playback speed')
        for control in (
                self.previous_button, self.play_button, self.next_button,
                self.time_edit, self.speed_combo):
            control.setMinimumSize(32, 32)
        self.position_label = QLabel('Frame ~— · 00:00:00.000')
        self.position_label.setToolTip('PTS —')
        self.position_label.setMinimumWidth(0)
        self.position_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.propagate_all_button = QToolButton()
        self.propagate_all_button.setText('Track all anchors')
        self.propagate_selected_button = QToolButton()
        self.propagate_selected_button.setText('Track selected object')
        self.cancel_propagation_button = QToolButton()
        self.cancel_propagation_button.setText('Cancel propagation')
        for button in (
                self.propagate_all_button, self.propagate_selected_button,
                self.cancel_propagation_button):
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.track_menu = QMenu('Track', self)
        self.track_menu.setObjectName('videoTrackMenu')
        self.track_button = QToolButton()
        self.track_button.setText('Track')
        self.track_button.setAccessibleName('Track')
        self.track_button.setToolTip('Track video objects')
        self.track_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.track_button.setPopupMode(QToolButton.InstantPopup)
        self.track_button.setMenu(self.track_menu)
        self.track_button.setMinimumSize(32, 32)
        self.progress_label = QLabel()
        self.progress_label.setObjectName('videoPropagationProgress')
        self.progress_label.setMinimumWidth(0)
        self.progress_label.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.progress_label.hide()
        self.cancel_propagation_button.hide()
        self.slider = _MarkerSlider()
        self.slider.setRange(0, TIMELINE_MAX)
        self.slider.setMinimumHeight(32)
        self.legend_menu = QMenu('Timeline legend', self)
        self.legend_menu.setObjectName('videoTimelineLegendMenu')
        self.legend_button = QToolButton()
        self.legend_button.setText('Legend')
        self.legend_button.setAccessibleName('Timeline legend')
        self.legend_button.setAccessibleDescription(
            self.slider.accessible_marker_summary())
        self.legend_button.setToolTip('Timeline legend')
        self.legend_button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.legend_button.setPopupMode(QToolButton.InstantPopup)
        self.legend_button.setMenu(self.legend_menu)
        self.legend_button.setFocusPolicy(Qt.StrongFocus)
        self.legend_button.setMinimumSize(32, 32)
        self._legend_actions = {}

        transport = QHBoxLayout()
        transport.setContentsMargins(4, 0, 4, 2)
        transport.setSpacing(4)
        transport.addWidget(self.previous_button)
        transport.addWidget(self.play_button)
        transport.addWidget(self.next_button)
        transport.addWidget(self.time_edit)
        transport.addWidget(self.speed_combo)
        transport.addWidget(self.position_label, 1)
        transport.addWidget(self.progress_label, 1)
        transport.addWidget(self.propagate_all_button)
        transport.addWidget(self.propagate_selected_button)
        transport.addWidget(self.cancel_propagation_button)
        transport.addWidget(self.legend_button)
        transport.addWidget(self.track_button)
        self._transport_layout = transport
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        layout.addWidget(self.slider)
        layout.addLayout(transport)
        self.layout_mode = 'compact'
        self._apply_responsive_visibility()
        self.set_playing(False)

        self.play_button.clicked.connect(self.playPauseRequested)
        self.previous_button.clicked.connect(self.previousRequested)
        self.next_button.clicked.connect(self.nextRequested)
        self.speed_combo.currentIndexChanged.connect(
            lambda _index: self.speedChanged.emit(
                float(self.speed_combo.currentData())))
        self.time_edit.returnPressed.connect(self._emit_time_seek)
        self.slider.sliderPressed.connect(self._slider_pressed)
        self.slider.sliderReleased.connect(self._slider_released)
        self.slider.valueChanged.connect(self._slider_changed)
        focus_handler = getattr(parent, '_restore_canvas_focus', None)
        if focus_handler is not None:
            self.focusReturnRequested.connect(focus_handler)

    def eventFilter(self, watched, event):
        if watched is self.time_edit and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.restore_time_editor()
                self.focusReturnRequested.emit()
                return True
            if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                    and not self.time_edit.hasAcceptableInput()):
                self._emit_time_seek()
                return True
        return super(VideoTimelineWidget, self).eventFilter(watched, event)

    def set_propagation_actions(self, all_action, selected_action,
                                cancel_action):
        self.propagate_all_button.setDefaultAction(all_action)
        self.propagate_selected_button.setDefaultAction(selected_action)
        self.cancel_propagation_button.setDefaultAction(cancel_action)
        self.track_menu.clear()
        self.track_menu.addAction(all_action)
        self.track_menu.addAction(selected_action)
        self.track_menu.addAction(cancel_action)
        self._update_layout_mode(self.width())

    def set_playback_action(self, action):
        previous = self._playback_action
        destroyed_slot = self._playback_action_destroyed_slot
        if previous is not None:
            try:
                previous.changed.disconnect(self._sync_play_button)
            except (RuntimeError, TypeError):
                pass
            if destroyed_slot is not None:
                try:
                    previous.destroyed.disconnect(destroyed_slot)
                except (RuntimeError, TypeError):
                    pass
        self._playback_action = action
        self._playback_action_destroyed_slot = None
        if action is not None:
            owner_ref = weakref.ref(self)
            action_ref = weakref.ref(action)

            def clear_destroyed_action(_object=None, owner=owner_ref,
                                       observed=action_ref):
                widget = owner()
                if (widget is not None
                        and widget._playback_action is observed()):
                    widget._playback_action = None
                    widget._playback_action_destroyed_slot = None

            self._playback_action_destroyed_slot = clear_destroyed_action
            action.changed.connect(self._sync_play_button)
            action.destroyed.connect(clear_destroyed_action)
        self._sync_play_button()

    def set_propagation_progress(self, processed, total, active, completed,
                                 eta_seconds, failures, running=True):
        self._propagation_running = bool(running)
        if not running:
            self.progress_label.clear()
        else:
            eta = ('—' if eta_seconds is None
                   else format_timecode(float(eta_seconds)))
            total_text = str(total) if total else '—'
            self.progress_label.setText(
                '%s/%s frames · %s active · %s complete · ETA %s · '
                '%s gaps/failures' % (
                    processed, total_text, active, completed, eta, failures))
        self._update_layout_mode(self.width())

    def set_session(self, snapshot):
        self._debounce.stop()
        self._dragging = False
        self._drag_seek_value = None
        self._drag_emitted_value = None
        self._pending_seek_value = None
        self._snapshot = snapshot
        self.setEnabled(snapshot is not None)
        if snapshot is None:
            blocked = self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(blocked)
            self._displayed_timecode = '00:00:00.000'
            self._displayed_pts = None
            self.time_edit.setText(self._displayed_timecode)
            self.position_label.setText(
                'Frame ~— · %s' % self._displayed_timecode)
            self.position_label.setToolTip('PTS —')
            return
        self.time_edit.setModified(False)
        self.set_current_frame(snapshot.initial_frame.frame_ref)

    def set_playing(self, playing):
        self._playing = bool(playing)
        self._sync_play_button()

    def _sync_play_button(self):
        verb = 'Pause' if self._playing else 'Play'
        icon = (QStyle.SP_MediaPause if self._playing
                else QStyle.SP_MediaPlay)
        name = '%s video' % verb
        shortcut = (
            self._playback_action.shortcut().toString(
                QKeySequence.NativeText)
            if self._playback_action is not None else '')
        self.play_button.setIcon(self.style().standardIcon(icon))
        self.play_button.setAccessibleName(name)
        self.play_button.setToolTip(
            '%s (%s)' % (name, shortcut) if shortcut else name)
        self.play_button.setChecked(self._playing)

    def set_markers(self, spans=(), accepted=(), pending=(), verified=(),
                    propagation=(), gaps=()):
        exact_by_kind = {
            'accepted': _marker_ranges(accepted),
            'pending': _marker_ranges(pending),
            'verified': _marker_ranges(verified),
            'propagation': _marker_ranges(
                tuple(spans) + tuple(propagation)),
            'gap': _marker_ranges(gaps),
        }
        self._marker_pts_by_kind = exact_by_kind
        self.slider.set_markers(
            propagation=tuple(
                self._pts_to_normalized_range(item)
                for item in exact_by_kind['propagation']),
            accepted=tuple(
                self._pts_to_normalized_range(item)
                for item in exact_by_kind['accepted']),
            pending=tuple(
                self._pts_to_normalized_range(item)
                for item in exact_by_kind['pending']),
            verified=tuple(
                self._pts_to_normalized_range(item)
                for item in exact_by_kind['verified']),
            gaps=tuple(
                self._pts_to_normalized_range(item)
                for item in exact_by_kind['gap']))
        self._rebuild_legend()

    def _rebuild_legend(self):
        self.legend_menu.clear()
        self._legend_actions = {}
        summary = self.slider.accessible_marker_summary()
        groups = self.slider.marker_groups()
        pattern_summary = '; '.join(
            '%s uses %s' % (group.label, _PATTERN_NAMES[group.pattern])
            for group in groups)
        description = (
            '%s. %s' % (summary, pattern_summary)
            if pattern_summary else summary)
        self.legend_button.setAccessibleDescription(description)
        self.legend_button.setToolTip(description)
        for group in groups:
            pattern_name = _PATTERN_NAMES[group.pattern]
            group_summary = _marker_group_summary(group)
            action = self.legend_menu.addAction(
                '%s — %s: %s' % (
                    group.label, pattern_name, group_summary))
            action.setData(group.kind)
            action.setIcon(_marker_treatment_icon(group.kind, group.pattern))
            action.setIconVisibleInMenu(True)
            action.setToolTip('%s uses %s; %s' % (
                group.label, pattern_name, group_summary))
            action.triggered.connect(
                lambda _checked=False, kind=group.kind:
                self._seek_next_marker(kind))
            self._legend_actions[group.kind] = action

    def _seek_next_marker(self, kind):
        ranges = self._marker_pts_by_kind.get(kind, ())
        if (not ranges or self._snapshot is None
                or self._displayed_pts is None):
            return
        starts = tuple(item[0] for item in ranges)
        current = self._displayed_pts
        value = next((item for item in starts if item > current), starts[0])
        self._debounce.stop()
        self._pending_seek_value = None
        self._emit_pts_seek(value)

    def set_current_frame(self, frame_ref):
        if self._snapshot is None:
            return
        self._displayed_pts = int(frame_ref.pts)
        value = self._pts_to_normalized(frame_ref.pts)
        self._projecting_position = True
        try:
            self.slider.setValue(value)
        finally:
            self._projecting_position = False
        start_pts = int(self._snapshot.start_pts or 0)
        seconds = (frame_ref.pts - start_pts) * \
            self._snapshot.time_base_num / self._snapshot.time_base_den
        self._displayed_timecode = format_timecode(seconds)
        if not self.time_edit.isModified():
            self.time_edit.setText(self._displayed_timecode)
        rate_num = self._snapshot.average_rate_num
        rate_den = self._snapshot.average_rate_den
        approximate = (
            max(0, int(round(seconds * rate_num / rate_den)))
            if rate_num and rate_den else None)
        frame_text = '~%s' % approximate if approximate is not None else '~—'
        self.position_label.setText(
            'Frame %s · %s' % (frame_text, self._displayed_timecode))
        self.position_label.setToolTip('PTS %s' % frame_ref.pts)

    @staticmethod
    def _measured_control_width(control):
        width = max(
            control.minimumWidth(), control.minimumSizeHint().width(),
            control.sizeHint().width())
        maximum = control.maximumWidth()
        return min(width, maximum) if maximum > 0 else width

    def _wide_required_width(self):
        essentials = (
            self.previous_button, self.play_button, self.next_button,
            self.time_edit, self.speed_combo, self.position_label,
            self.legend_button,
        )
        idle_track = (
            self.propagate_all_button, self.propagate_selected_button)
        running_track = (
            self.progress_label, self.cancel_propagation_button)

        def measured(controls):
            return sum(self._measured_control_width(item)
                       for item in controls)

        context_width = max(measured(idle_track), measured(running_track))
        control_count = len(essentials) + max(
            len(idle_track), len(running_track))
        margins = self._transport_layout.contentsMargins()
        outer = self.layout().contentsMargins()
        return (
            measured(essentials) + context_width
            + max(0, control_count - 1) * self._transport_layout.spacing()
            + margins.left() + margins.right()
            + outer.left() + outer.right())

    def _apply_responsive_visibility(self):
        wide = self.layout_mode == 'wide'
        running = self._propagation_running
        self.propagate_all_button.setVisible(wide and not running)
        self.propagate_selected_button.setVisible(wide and not running)
        self.cancel_propagation_button.setVisible(wide and running)
        self.progress_label.setVisible(running)
        self.track_button.setVisible(not wide)

    def _update_layout_mode(self, width):
        self.layout_mode = (
            'wide' if int(width) >= self._wide_required_width()
            else 'compact')
        self._apply_responsive_visibility()

    def resizeEvent(self, event):
        self._update_layout_mode(event.size().width())
        super(VideoTimelineWidget, self).resizeEvent(event)

    def _duration_pts(self):
        return max(0, int(self._snapshot.duration_pts or 0))

    def _pts_to_normalized(self, pts):
        if self._snapshot is None or not self._duration_pts():
            return 0
        start = int(self._snapshot.start_pts or 0)
        return max(0, min(TIMELINE_MAX, int(round(
            (int(pts) - start) * TIMELINE_MAX / self._duration_pts()))))

    def _pts_to_normalized_range(self, span):
        return (self._pts_to_normalized(span[0]),
                self._pts_to_normalized(span[1]))

    def _normalized_to_ref(self, value):
        snapshot = self._snapshot
        start = int(snapshot.start_pts or 0)
        pts = start + int(round(
            int(value) * self._duration_pts() / TIMELINE_MAX))
        return VideoFrameRef(
            snapshot.fingerprint, snapshot.stream_index, pts,
            snapshot.time_base_num, snapshot.time_base_den)

    def _slider_pressed(self):
        self._dragging = True
        self._drag_seek_value = self.slider.value()
        self._drag_emitted_value = None

    def _slider_released(self):
        self._debounce.stop()
        dragging = self._dragging
        value = (self._drag_seek_value if dragging
                 else self._pending_seek_value)
        if value is None:
            value = self.slider.value()
        already_emitted = (
            dragging and self._drag_emitted_value == value)
        self._dragging = False
        self._drag_seek_value = None
        self._drag_emitted_value = None
        self._pending_seek_value = None if already_emitted else value
        if not already_emitted:
            self._emit_slider_seek()

    def _slider_changed(self, value):
        if self._projecting_position:
            return
        self._pending_seek_value = int(value)
        if self._dragging:
            self._drag_seek_value = int(value)
        self._debounce.start()

    def _emit_slider_seek(self):
        value = self._pending_seek_value
        self._pending_seek_value = None
        if self._snapshot is not None and value is not None:
            self._emit_normalized_seek(value)
            if self._dragging:
                self._drag_emitted_value = value

    def _emit_normalized_seek(self, value):
        if self._snapshot is not None:
            self.seekRequested.emit(self._normalized_to_ref(value))

    def _emit_pts_seek(self, pts):
        snapshot = self._snapshot
        if snapshot is not None:
            self.seekRequested.emit(VideoFrameRef(
                snapshot.fingerprint, snapshot.stream_index, int(pts),
                snapshot.time_base_num, snapshot.time_base_den))

    def restore_time_editor(self):
        self.time_edit.setText(self._displayed_timecode)

    def _emit_time_seek(self):
        if self._snapshot is None:
            return
        try:
            seconds = parse_timecode(self.time_edit.text())
            if self._snapshot.duration_pts is not None:
                duration = (max(0, int(self._snapshot.duration_pts))
                            * self._snapshot.time_base_num
                            / self._snapshot.time_base_den)
                if seconds > duration:
                    raise ValueError(
                        'Time must be within 00:00:00.000 and %s'
                        % format_timecode(duration))
        except ValueError as exc:
            self.time_edit.setModified(True)
            self.timeInputError.emit(str(exc))
            return
        self.time_edit.setModified(False)
        pts = int(self._snapshot.start_pts or 0) + int(round(
            seconds * self._snapshot.time_base_den /
            self._snapshot.time_base_num))
        self.seekRequested.emit(VideoFrameRef(
            self._snapshot.fingerprint, self._snapshot.stream_index, pts,
            self._snapshot.time_base_num, self._snapshot.time_base_den))
        self.focusReturnRequested.emit()
