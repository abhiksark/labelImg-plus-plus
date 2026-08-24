"""Nonblocking owner for bounded application shutdown."""

try:
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
except ImportError:  # pragma: no cover - legacy Qt fallback
    from PyQt4.QtCore import QObject, QTimer, pyqtSignal


class ShutdownCoordinator(QObject):
    """Cancel work, poll for a clean drain, and expose one timeout choice."""

    ready = pyqtSignal()
    timedOut = pyqtSignal(tuple)

    def __init__(self, activity, timeout_ms=5000, parent=None):
        super(ShutdownCoordinator, self).__init__(parent)
        self.activity = activity
        self.timeout_ms = int(timeout_ms)
        self.state = 'idle'
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(50)
        self._poll_timer.timeout.connect(self.poll)
        self._deadline = QTimer(self)
        self._deadline.setSingleShot(True)
        self._deadline.timeout.connect(self._deadline_expired)

    def begin(self):
        if self.state in ('waiting', 'ready', 'force_requested'):
            return
        self.state = 'waiting'
        self.activity.cancel_all()
        self._poll_timer.start()
        self._deadline.start(self.timeout_ms)
        self.poll()

    def poll(self):
        if self.state == 'waiting' and self.activity.is_idle():
            self._poll_timer.stop()
            self._deadline.stop()
            self.state = 'ready'
            self.ready.emit()

    def _deadline_expired(self):
        if self.state != 'waiting':
            return
        self._poll_timer.stop()
        self.state = 'timed_out'
        self.timedOut.emit(tuple(self.activity.active_jobs()))

    def wait_again(self):
        if self.state != 'timed_out':
            return
        self.state = 'waiting'
        self._poll_timer.start()
        self._deadline.start(self.timeout_ms)
        self.poll()

    def force_requested(self):
        self._poll_timer.stop()
        self._deadline.stop()
        self.state = 'force_requested'
