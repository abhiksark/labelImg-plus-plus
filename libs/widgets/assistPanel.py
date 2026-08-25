"""Contextual workspace drawer for Assist setup, progress, and review."""

import os

try:
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtWidgets import (
        QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
        QVBoxLayout,
    )
except ImportError:
    from PyQt4.QtCore import Qt, pyqtSignal
    from PyQt4.QtGui import (
        QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton,
        QVBoxLayout,
    )

from libs.core.assist_state import AssistFailureKind, AssistPhase
from libs.integrations.model_cache import (
    ModelDownloadProgress,
    default_model_paths,
)
from libs.utils.dpi import scale_px


def format_bytes(value):
    """Return a compact, human-readable byte count."""
    size = float(max(0, int(value)))
    for suffix in ('B', 'KB', 'MB', 'GB'):
        if size < 1024.0 or suffix == 'GB':
            if suffix == 'B':
                return '%d %s' % (int(size), suffix)
            return '%.1f %s' % (size, suffix)
        size /= 1024.0


class AssistPanel(QFrame):
    """Project one Assist lifecycle phase into one contextual surface."""

    downloadRequested = pyqtSignal()
    cancelRequested = pyqtSignal()
    retryRequested = pyqtSignal()
    acceptRequested = pyqtSignal()
    rejectRequested = pyqtSignal()
    trackForwardRequested = pyqtSignal()
    closeRequested = pyqtSignal()
    smartBoxRequested = pyqtSignal()
    smartPointsRequested = pyqtSignal()

    def __init__(self, parent=None):
        super(AssistPanel, self).__init__(parent)
        self.setObjectName('assistPanel')
        self.setFrameShape(QFrame.StyledPanel)
        self.setAccessibleName('Assist')
        self.setMinimumWidth(scale_px(300))
        self.setMaximumWidth(scale_px(380))

        heading = QHBoxLayout()
        self.title = QLabel('Assist', self)
        self.title.setObjectName('assistPanelTitle')
        heading.addWidget(self.title)
        heading.addStretch(1)
        self.close_button = QPushButton('Close', self)
        self.close_button.setAccessibleName('Close Assist')
        self.close_button.clicked.connect(self.closeRequested)
        heading.addWidget(self.close_button)

        self.state_label = QLabel('', self)
        self.state_label.setObjectName('assistStateTitle')
        self.state_label.setFocusPolicy(Qt.StrongFocus)
        self.explanation = QLabel('', self)
        self.explanation.setWordWrap(True)
        self.provider = QLabel('', self)
        self.provider.setWordWrap(True)
        self.size = QLabel('', self)
        self.storage = QLabel('', self)
        self.storage.setWordWrap(True)
        self.message = QLabel('', self)
        self.message.setWordWrap(True)
        self.progress = QProgressBar(self)
        self.progress.setAccessibleName('Assist model download progress')

        self.download_button = self._button(
            'Download model', 'Download Assist model', self.downloadRequested)
        self.cancel_button = self._button(
            'Cancel', 'Cancel Assist model download', self.cancelRequested)
        self.retry_button = self._button(
            'Retry', 'Retry Assist setup', self.retryRequested)
        self.smart_box_button = self._button(
            'Smart Box', 'Use Smart Box', self.smartBoxRequested)
        self.smart_points_button = self._button(
            'Smart Points', 'Use Smart Points', self.smartPointsRequested)
        self.accept_button = self._button(
            'Accept', 'Accept Assist preview', self.acceptRequested)
        self.reject_button = self._button(
            'Reject', 'Reject Assist preview', self.rejectRequested)
        self.track_forward_button = self._button(
            'Track forward', 'Track accepted Assist result forward',
            self.trackForwardRequested)

        actions = QGridLayout()
        actions.setHorizontalSpacing(scale_px(6))
        actions.setVerticalSpacing(scale_px(6))
        actions.setColumnStretch(0, 1)
        actions.setColumnStretch(1, 1)
        for button in (
                self.download_button, self.cancel_button, self.retry_button):
            actions.addWidget(button, 0, 0, 1, 2)
        actions.addWidget(self.smart_box_button, 0, 0)
        actions.addWidget(self.smart_points_button, 0, 1)
        actions.addWidget(self.accept_button, 0, 0)
        actions.addWidget(self.reject_button, 0, 1)
        actions.addWidget(self.track_forward_button, 1, 0, 1, 2)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            scale_px(16), scale_px(12), scale_px(16), scale_px(16))
        layout.setSpacing(scale_px(8))
        layout.addLayout(heading)
        layout.addWidget(self.state_label)
        layout.addWidget(self.explanation)
        layout.addWidget(self.provider)
        layout.addWidget(self.size)
        layout.addWidget(self.storage)
        layout.addWidget(self.message)
        layout.addWidget(self.progress)
        layout.addLayout(actions)
        layout.addStretch(1)

    def _button(self, text, accessible_name, signal):
        button = QPushButton(text, self)
        button.setAccessibleName(accessible_name)
        button.setMinimumHeight(scale_px(32))
        button.clicked.connect(signal)
        return button

    def _phase_buttons(self):
        return (
            self.download_button, self.cancel_button, self.retry_button,
            self.smart_box_button, self.smart_points_button,
            self.accept_button, self.reject_button,
            self.track_forward_button,
        )

    def set_snapshot(self, snapshot, manifest,
                     track_forward_available=False):
        """Render exactly one lifecycle phase from immutable domain state."""
        phase = AssistPhase(snapshot.phase)
        for widget in (
                self.explanation, self.provider, self.size, self.storage,
                self.message, self.progress):
            widget.hide()
        for button in self._phase_buttons():
            button.hide()
        self.track_forward_button.setEnabled(bool(track_forward_available))

        titles = {
            AssistPhase.SETUP_REQUIRED: 'Set up Assist',
            AssistPhase.READY_TO_DOWNLOAD: 'Ready to download',
            AssistPhase.DOWNLOADING: 'Downloading model',
            AssistPhase.READY: 'Choose an Assist tool',
            AssistPhase.RUNNING: 'Creating preview',
            AssistPhase.PREVIEW: 'Review preview',
            AssistPhase.FAILED: 'Assist needs attention',
        }
        self.state_label.setText(titles[phase])

        if phase in (
                AssistPhase.SETUP_REQUIRED,
                AssistPhase.READY_TO_DOWNLOAD):
            self._show_setup(manifest)
            self.download_button.show()
        elif phase is AssistPhase.DOWNLOADING:
            self._show_download_progress(snapshot.message, manifest)
            self.cancel_button.show()
        elif phase is AssistPhase.READY:
            self.explanation.setText(
                'Choose a box prompt or refine an object with points.')
            self.explanation.show()
            self.smart_box_button.show()
            self.smart_points_button.show()
            if track_forward_available:
                self.message.setText(
                    'Accepted as a manual anchor. Track it forward when '
                    'you are ready.')
                self.message.show()
                self.track_forward_button.show()
        elif phase is AssistPhase.RUNNING:
            self.message.setText(
                'Assist is working. Your current document is unchanged.')
            self.message.show()
            self.progress.setRange(0, 0)
            self.progress.show()
        elif phase is AssistPhase.PREVIEW:
            self.message.setText(
                'The result is provisional. Accept it or reject it; your '
                'document changes only after acceptance.')
            self.message.show()
            self.accept_button.show()
            self.reject_button.show()
        elif phase is AssistPhase.FAILED:
            self.message.setText(self._failure_copy(
                snapshot.failure_kind, snapshot.message))
            self.message.show()
            self.retry_button.show()

    def _show_setup(self, manifest):
        self.explanation.setText(str(manifest.purpose))
        self.provider.setText('Provider: %s' % manifest.provider)
        self.size.setText('Download size: %s' % format_bytes(
            manifest.total_size))
        paths = default_model_paths()
        location = os.path.dirname(paths[0]) if paths else ''
        self.storage.setText('Storage: %s' % location)
        for widget in (
                self.explanation, self.provider, self.size, self.storage):
            widget.show()

    def _show_download_progress(self, value, manifest):
        progress = value if isinstance(value, ModelDownloadProgress) else None
        downloaded = progress.total_downloaded if progress is not None else 0
        total = progress.total_size if progress is not None else \
            manifest.total_size
        if total > 0:
            self.progress.setRange(0, int(total))
            self.progress.setValue(min(int(downloaded), int(total)))
            self.progress.setFormat('%s / %s' % (
                format_bytes(downloaded), format_bytes(total)))
        else:
            self.progress.setRange(0, 0)
        if progress is not None:
            self.message.setText('Downloading %s' % progress.artifact)
            self.message.show()
        elif value:
            self.message.setText(str(value))
            self.message.show()
        self.progress.show()

    @staticmethod
    def _failure_copy(kind, detail):
        messages = {
            AssistFailureKind.OFFLINE:
                'You appear to be offline. Check your connection and retry.',
            AssistFailureKind.PROVIDER:
                'The model provider could not complete the download. Retry '
                'when the provider is available.',
            AssistFailureKind.VALIDATION:
                'Model validation failed, so the downloaded artifact was not '
                'installed.',
            AssistFailureKind.RUNTIME:
                'The optional Assist runtime is unavailable. Install the '
                'Assist extra, then retry.',
            AssistFailureKind.INFERENCE:
                'Assist could not create a preview. Adjust the prompt and retry.',
        }
        try:
            normalized = AssistFailureKind(kind)
        except (TypeError, ValueError):
            normalized = AssistFailureKind.RUNTIME
        text = messages[normalized]
        if detail:
            text += ' %s' % detail
        return '%s Your current document is preserved.' % text
