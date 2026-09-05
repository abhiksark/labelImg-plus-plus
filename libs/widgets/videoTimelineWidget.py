# libs/widgets/videoTimelineWidget.py
"""PTS-based controls and marker strip for smart-video documents."""

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider,
    QStyle, QToolButton, QVBoxLayout, QWidget,
)

from libs.core.video_types import VideoFrameRef
from libs.utils.dpi import scale_px
from libs.utils.styles import Theme, get_theme_colors
from libs.utils.utils import themed_icon


TIMELINE_MAX = 1_000_000


def format_timecode(seconds):
    milliseconds = max(0, int(round(float(seconds) * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return '%02d:%02d:%02d.%03d' % (hours, minutes, secs, millis)


def parse_timecode(value):
    parts = value.strip().split(':')
    if len(parts) != 3:
        raise ValueError('timecode must use HH:MM:SS.mmm')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError('timecode is outside its valid range')
    return hours * 3600 + minutes * 60 + seconds


class _MarkerSlider(QSlider):
    """A standard slider with a compact non-interactive marker overlay."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('videoTimeline')
        self._snapshot = None
        self._dragging = False
        self._playing = False
        self._theme = Theme.LIGHT
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(50)
        self._debounce.timeout.connect(self._emit_slider_seek)

        style = self.style()
        self.play_button = QPushButton()
        self.play_button.setAccessibleName('Play or pause video')
        self.play_button.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setToolTip('Play/Pause (Ctrl+Space)')
        self.previous_button = QPushButton()
        self.previous_button.setAccessibleName('Previous frame')
        self.previous_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward))
        self.previous_button.setToolTip('Previous frame (A)')
        self.next_button = QPushButton()
        self.next_button.setAccessibleName('Next frame')
        self.next_button.setIcon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        self.next_button.setToolTip('Next frame (D)')
        self.time_edit = QLineEdit('00:00:00.000')
        self.time_edit.setAccessibleName('Presentation time')
        self.time_edit.setFixedWidth(138)
        self.time_edit.setToolTip('Exact presentation time (HH:MM:SS.mmm)')
        self.speed_combo = QComboBox()
        self.speed_combo.setAccessibleName('Playback speed')
        for speed in (0.25, 0.5, 1.0, 2.0):
            self.speed_combo.addItem('%gx' % speed, speed)
        self.speed_combo.setCurrentIndex(2)
        self.position_label = QLabel('00:00:00.000 / —')
        self.position_label.setObjectName('videoElapsedPosition')
        self._marker_spans = ()
        self._marker_accepted = ()
        self._marker_pending = ()
        self.workflow_stages = []
        self.workflow_arrows = []
        workflow = QHBoxLayout()
        workflow.setContentsMargins(0, 0, 0, 0)
        workflow.setSpacing(4)
        for index, name in enumerate(
                ('Anchor', 'Propagate', 'Review', 'Export')):
            if index:
                arrow = QLabel('›')
                arrow.setObjectName('videoWorkflowArrow')
                workflow.addWidget(arrow)
                self.workflow_arrows.append(arrow)
            stage = QLabel(name)
            stage.setObjectName('videoWorkflowStage')
            workflow.addWidget(stage)
            self.workflow_stages.append(stage)
        self._set_workflow_stage(0)
        self.propagate_all_button = QToolButton()
        self.propagate_selected_button = QToolButton()
        self.cancel_propagation_button = QToolButton()
        for button in (
                self.propagate_all_button, self.propagate_selected_button,
                self.cancel_propagation_button):
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.progress_label = QLabel()
        self.progress_label.setObjectName('videoPropagationProgress')
        self.progress_label.hide()
        self.cancel_propagation_button.hide()
        self.slider = _MarkerSlider()
        self.slider.setAccessibleName('Video timeline')
        self.slider.setRange(0, TIMELINE_MAX)

        top = QHBoxLayout()
        top.setContentsMargins(4, 2, 4, 0)
        top.addWidget(self.previous_button)
        top.addWidget(self.play_button)
        top.addWidget(self.next_button)
        top.addWidget(self.time_edit)
        top.addWidget(self.speed_combo)
        top.addWidget(self.position_label)
        top.addSpacing(8)
        top.addLayout(workflow)
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
        self.apply_theme(Theme.LIGHT)

    def apply_theme(self, theme):
        self._theme = theme
        colors = get_theme_colors(theme)
        self.setStyleSheet("""
            #videoTimeline QPushButton:focus,
            #videoTimeline QToolButton:focus,
            #videoTimeline QLineEdit:focus,
            #videoTimeline QComboBox:focus,
            #videoTimeline QSlider:focus {{
                border: {width}px solid {focus};
                border-radius: {radius}px;
            }}
        """.format(
            width=scale_px(2), radius=scale_px(4),
            focus=colors['focus']))
        style = self.style()
        play_icon = (QStyle.StandardPixmap.SP_MediaPause if self._playing
                     else QStyle.StandardPixmap.SP_MediaPlay)
        self.play_button.setIcon(themed_icon(
            style.standardIcon(play_icon), theme))
        self.previous_button.setIcon(themed_icon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipBackward), theme))
        self.next_button.setIcon(themed_icon(
            style.standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward), theme))

    def set_propagation_actions(self, all_action, selected_action,
                                cancel_action):
        self.propagate_all_button.setDefaultAction(all_action)
        self.propagate_selected_button.setDefaultAction(selected_action)
        self.cancel_propagation_button.setDefaultAction(cancel_action)
        self.propagate_all_button.hide()
        self.propagate_selected_button.hide()

    def set_propagation_progress(self, processed, total, active, completed,
                                 eta_seconds, failures, running=True):
        # Propagation now lives with the selected track in the inspector.
        # The timeline retains the authoritative actions for compatibility,
        # but only active progress/cancellation belongs in this footer.
        self.propagate_all_button.hide()
        self.propagate_selected_button.hide()
        self.cancel_propagation_button.setVisible(running)
        self.progress_label.setVisible(running)
        self._set_workflow_stage(
            1 if running else self._stage_from_markers())
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
        self._snapshot = snapshot
        self.setEnabled(snapshot is not None)
        if snapshot is None:
            self.slider.setValue(0)
            self.position_label.setText('00:00:00.000 / —')
            self.position_label.setToolTip('No video frame')
            self._set_workflow_stage(0)
            return
        self.set_current_frame(snapshot.initial_frame.frame_ref)

    def set_playing(self, playing):
        self._playing = bool(playing)
        icon = (QStyle.StandardPixmap.SP_MediaPause if self._playing
                else QStyle.StandardPixmap.SP_MediaPlay)
        self.play_button.setIcon(themed_icon(
            self.style().standardIcon(icon), self._theme))

    def set_markers(self, spans=(), accepted=(), pending=(), verified=()):
        self._marker_spans = tuple(spans)
        self._marker_accepted = tuple(accepted)
        self._marker_pending = tuple(pending)
        self.slider.set_markers(
            spans=tuple(self._pts_to_normalized_range(item)
                        for item in self._marker_spans),
            accepted=tuple(self._pts_to_normalized(item)
                           for item in self._marker_accepted),
            pending=tuple(self._pts_to_normalized(item)
                          for item in self._marker_pending),
            verified=tuple(self._pts_to_normalized(item) for item in verified))
        if not self.progress_label.isVisible():
            self._set_workflow_stage(self._stage_from_markers())

    def set_current_frame(self, frame_ref):
        if self._snapshot is None:
            return
        value = self._pts_to_normalized(frame_ref.pts)
        blocked = self.slider.blockSignals(True)
        self.slider.setValue(value)
        self.slider.blockSignals(blocked)
        start_pts = int(self._snapshot.start_pts or 0)
        seconds = (frame_ref.pts - start_pts) * \
            self._snapshot.time_base_num / self._snapshot.time_base_den
        self.time_edit.setText(format_timecode(seconds))
        self.time_edit.setCursorPosition(0)
        rate_num = self._snapshot.average_rate_num
        rate_den = self._snapshot.average_rate_den
        approximate = (
            max(0, int(round(seconds * rate_num / rate_den)))
            if rate_num and rate_den else None)
        frame_text = '~%s' % approximate if approximate is not None else '~—'
        duration_seconds = self._duration_pts() * \
            self._snapshot.time_base_num / self._snapshot.time_base_den
        self.position_label.setText('%s / %s' % (
            format_timecode(seconds), format_timecode(duration_seconds)))
        self.position_label.setToolTip(
            'Exact PTS %s · Approximate frame %s' %
            (frame_ref.pts, frame_text))

    def _stage_from_markers(self):
        if self._marker_pending:
            return 2
        if any(int(end) > int(start) for start, end in self._marker_spans):
            return 3
        if self._marker_accepted:
            return 1
        return 0

    def _set_workflow_stage(self, active):
        active = max(0, min(len(self.workflow_stages) - 1, int(active)))
        for index, label in enumerate(self.workflow_stages):
            name = ('Anchor', 'Propagate', 'Review', 'Export')[index]
            label.setProperty('active', index == active)
            label.setProperty('done', index < active)
            label.setText(
                ('✓ ' if index < active else '● ' if index == active else '')
                + name)
            label.style().unpolish(label)
            label.style().polish(label)

    def workflow_stage(self):
        for index, label in enumerate(self.workflow_stages):
            if bool(label.property('active')):
                return ('anchor', 'propagate', 'review', 'export')[index]
        return 'anchor'

    def resizeEvent(self, event):
        # At inspector-open laptop widths the timeline column is much narrower
        # than the window. The command bar already owns elapsed/current time,
        # so keep exact seek plus only the active workflow stage rather than
        # squeezing every label until all of them become unreadable.
        self._update_responsive_chrome(event.size().width())
        super().resizeEvent(event)

    def _update_responsive_chrome(self, width):
        compact = int(width) < 850
        self.position_label.setVisible(not compact)
        for arrow in self.workflow_arrows:
            arrow.setVisible(not compact)
        for label in self.workflow_stages:
            label.setVisible(
                not compact or bool(label.property('active')))

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
        self._emit_slider_seek()

    def _slider_changed(self, _value):
        if self._dragging:
            self._debounce.start()

    def _emit_slider_seek(self):
        if self._snapshot is not None:
            self.seekRequested.emit(
                self._normalized_to_ref(self.slider.value()))

    def _emit_time_seek(self):
        if self._snapshot is None:
            return
        try:
            seconds = parse_timecode(self.time_edit.text())
        except ValueError:
            self.time_edit.setText(format_timecode(
                self._snapshot.initial_frame.frame_ref.seconds))
            return
        pts = int(self._snapshot.start_pts or 0) + int(round(
            seconds * self._snapshot.time_base_den /
            self._snapshot.time_base_num))
        self.seekRequested.emit(VideoFrameRef(
            self._snapshot.fingerprint, self._snapshot.stream_index, pts,
            self._snapshot.time_base_num, self._snapshot.time_base_den))
