"""PTS-based controls and marker strip for smart-video documents."""

import re

from PyQt5.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen
from PyQt5.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
    QStyle, QToolButton, QVBoxLayout, QWidget,
)

try:
    from PyQt5.QtCore import QRegularExpression
    from PyQt5.QtGui import QRegularExpressionValidator
    _REGULAR_EXPRESSION_VALIDATOR = True
except ImportError:
    from PyQt5.QtCore import QRegExp
    from PyQt5.QtGui import QRegExpValidator
    _REGULAR_EXPRESSION_VALIDATOR = False

from libs.core.video_types import VideoFrameRef


TIMELINE_MAX = 1_000_000
_TIMECODE_PATTERN = r'^(\d{2,}):([0-5]\d):([0-5]\d)\.(\d{3})$'
_TIMECODE = re.compile(_TIMECODE_PATTERN)


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
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


class _MarkerSlider(QSlider):
    """A standard slider with a compact non-interactive marker overlay."""

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.spans = ()
        self.accepted = ()
        self.pending = ()
        self.verified = ()

    def set_markers(self, spans=(), accepted=(), pending=(), verified=()):
        self.spans = tuple(spans)
        self.accepted = tuple(accepted)
        self.pending = tuple(pending)
        self.verified = tuple(verified)
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        width = max(1, self.width() - 12)
        left = 6
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        for start, end in self.spans:
            painter.fillRect(
                left + int(start * width / TIMELINE_MAX), 1,
                max(1, int((end - start) * width / TIMELINE_MAX)), 3,
                QColor(70, 140, 220, 160))
        for values, color, y0, y1 in (
                (self.accepted, QColor(45, 180, 90), 0, 6),
                (self.pending, QColor(235, 165, 35), 0, 6),
                (self.verified, QColor(125, 90, 220),
                 self.height() - 6, self.height())):
            painter.setPen(QPen(color, 2))
            for value in values:
                x = left + int(value * width / TIMELINE_MAX)
                painter.drawLine(x, y0, x, y1)
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
        self._playing = False
        self._projecting_position = False
        self._pending_seek_value = None
        self._displayed_timecode = '00:00:00.000'
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(50)
        self._debounce.timeout.connect(self._emit_slider_seek)

        style = self.style()
        self.play_button = QPushButton()
        self.play_button.setIcon(style.standardIcon(QStyle.SP_MediaPlay))
        self.play_button.setToolTip('Play/Pause (Ctrl+Space)')
        self.previous_button = QPushButton()
        self.previous_button.setIcon(
            style.standardIcon(QStyle.SP_MediaSkipBackward))
        self.previous_button.setToolTip('Previous frame (A)')
        self.next_button = QPushButton()
        self.next_button.setIcon(
            style.standardIcon(QStyle.SP_MediaSkipForward))
        self.next_button.setToolTip('Next frame (D)')
        self.time_edit = QLineEdit('00:00:00.000')
        self.time_edit.setValidator(_timecode_validator(self.time_edit))
        self.time_edit.installEventFilter(self)
        self.time_edit.setMaximumWidth(110)
        self.time_edit.setToolTip('Exact presentation time (HH:MM:SS.mmm)')
        self.speed_combo = QComboBox()
        for speed in (0.25, 0.5, 1.0, 2.0):
            self.speed_combo.addItem('%gx' % speed, speed)
        self.speed_combo.setCurrentIndex(2)
        self.position_label = QLabel('PTS — · Frame ~—')
        self.propagate_all_button = QToolButton()
        self.propagate_selected_button = QToolButton()
        self.cancel_propagation_button = QToolButton()
        for button in (
                self.propagate_all_button, self.propagate_selected_button,
                self.cancel_propagation_button):
            button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.progress_label = QLabel()
        self.progress_label.setObjectName('videoPropagationProgress')
        self.progress_label.hide()
        self.cancel_propagation_button.hide()
        self.slider = _MarkerSlider()
        self.slider.setRange(0, TIMELINE_MAX)

        top = QHBoxLayout()
        top.setContentsMargins(4, 2, 4, 0)
        top.addWidget(self.previous_button)
        top.addWidget(self.play_button)
        top.addWidget(self.next_button)
        top.addWidget(self.time_edit)
        top.addWidget(self.speed_combo)
        top.addWidget(self.position_label)
        top.addStretch(1)
        top.addWidget(self.progress_label)
        top.addWidget(self.propagate_all_button)
        top.addWidget(self.propagate_selected_button)
        top.addWidget(self.cancel_propagation_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(1)
        layout.addLayout(top)
        layout.addWidget(self.slider)

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

    def set_propagation_progress(self, processed, total, active, completed,
                                 eta_seconds, failures, running=True):
        self.propagate_all_button.setVisible(not running)
        self.propagate_selected_button.setVisible(not running)
        self.cancel_propagation_button.setVisible(running)
        self.progress_label.setVisible(running)
        if not running:
            self.progress_label.clear()
            return
        eta = ('—' if eta_seconds is None
               else format_timecode(float(eta_seconds)))
        total_text = str(total) if total else '—'
        self.progress_label.setText(
            '%s/%s frames · %s active · %s complete · ETA %s · '
            '%s gaps/failures' % (
                processed, total_text, active, completed, eta, failures))

    def set_session(self, snapshot):
        self._debounce.stop()
        self._pending_seek_value = None
        self._snapshot = snapshot
        self.setEnabled(snapshot is not None)
        if snapshot is None:
            blocked = self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(blocked)
            self._displayed_timecode = '00:00:00.000'
            self.time_edit.setText(self._displayed_timecode)
            self.position_label.setText('PTS — · Frame ~—')
            return
        self.set_current_frame(snapshot.initial_frame.frame_ref)

    def set_playing(self, playing):
        self._playing = bool(playing)
        icon = (QStyle.SP_MediaPause if self._playing
                else QStyle.SP_MediaPlay)
        self.play_button.setIcon(self.style().standardIcon(icon))

    def set_markers(self, spans=(), accepted=(), pending=(), verified=()):
        self.slider.set_markers(
            spans=tuple(self._pts_to_normalized_range(item) for item in spans),
            accepted=tuple(self._pts_to_normalized(item) for item in accepted),
            pending=tuple(self._pts_to_normalized(item) for item in pending),
            verified=tuple(self._pts_to_normalized(item) for item in verified))

    def set_current_frame(self, frame_ref):
        if self._snapshot is None:
            return
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
        self.time_edit.setText(self._displayed_timecode)
        rate_num = self._snapshot.average_rate_num
        rate_den = self._snapshot.average_rate_den
        approximate = (
            max(0, int(round(seconds * rate_num / rate_den)))
            if rate_num and rate_den else None)
        frame_text = '~%s' % approximate if approximate is not None else '~—'
        self.position_label.setText(
            'PTS %s · Frame %s' % (frame_ref.pts, frame_text))

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

    def _slider_released(self):
        self._dragging = False
        self._debounce.stop()
        self._pending_seek_value = self.slider.value()
        self._emit_slider_seek()

    def _slider_changed(self, value):
        if self._projecting_position:
            return
        self._pending_seek_value = int(value)
        self._debounce.start()

    def _emit_slider_seek(self):
        value = self._pending_seek_value
        self._pending_seek_value = None
        if self._snapshot is not None and value is not None:
            self.seekRequested.emit(
                self._normalized_to_ref(value))

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
            self.timeInputError.emit(str(exc))
            return
        pts = int(self._snapshot.start_pts or 0) + int(round(
            seconds * self._snapshot.time_base_den /
            self._snapshot.time_base_num))
        self.seekRequested.emit(VideoFrameRef(
            self._snapshot.fingerprint, self._snapshot.stream_index, pts,
            self._snapshot.time_base_num, self._snapshot.time_base_den))
