from dataclasses import dataclass

try:
    from PyQt5.QtCore import QObject, QTimer, pyqtSignal
except ImportError:  # pragma: no cover - legacy Qt fallback
    from PyQt4.QtCore import QObject, QTimer, pyqtSignal


@dataclass(frozen=True)
class SaveTicket:
    document_key: str
    generation: int
    revision: int


class ContinuousSaveCoordinator(QObject):
    saveRequested = pyqtSignal(object)
    stateChanged = pyqtSignal(str)
    drained = pyqtSignal()

    def __init__(self, delay_ms=250, parent=None):
        super(ContinuousSaveCoordinator, self).__init__(parent)
        self.delay_ms = int(delay_ms)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)
        self._state = 'saved'
        self._document_key = ''
        self._generation = 0
        self._durable_revision = 0
        self._newest_revision = 0
        self._in_flight = None
        self._enabled = True
        self._draining = False
        self.error = None

    @property
    def state(self):
        return self._state

    @property
    def is_drained(self):
        return (
            self._state == 'saved'
            and self._in_flight is None
            and self._newest_revision <= self._durable_revision)

    def _set_state(self, value):
        if value != self._state:
            self._state = value
            self.stateChanged.emit(value)

    @property
    def enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        if not self._enabled:
            self._timer.stop()
            if (self._in_flight is None
                    and self._newest_revision > self._durable_revision
                    and self._state != 'failed'):
                self._set_state('pending')
            return
        if (self._in_flight is None
                and self._newest_revision > self._durable_revision
                and self._state != 'failed'):
            self._set_state('pending')
            self.flush()

    def reset(self, document_key, generation, durable_revision=0):
        self._timer.stop()
        self._document_key = str(document_key)
        self._generation = int(generation)
        self._durable_revision = int(durable_revision)
        self._newest_revision = int(durable_revision)
        self._in_flight = None
        self._draining = False
        self.error = None
        self._set_state('saved')

    def mark_dirty(self, revision):
        self._newest_revision = max(self._newest_revision, int(revision))
        if self._state == 'failed':
            return
        self._set_state('pending')
        if self._enabled and self._in_flight is None:
            self._timer.start(self.delay_ms)

    def flush(self):
        self._timer.stop()
        if ((self._enabled or self._draining) and self._in_flight is None
                and self._newest_revision > self._durable_revision):
            ticket = SaveTicket(
                self._document_key, self._generation, self._newest_revision)
            self._in_flight = ticket
            self._set_state('saving')
            self.saveRequested.emit(ticket)

    def drain(self):
        """Force the current immutable ticket stream through its newest edit."""
        self._timer.stop()
        self._draining = True
        if self._state == 'failed':
            self.error = None
            self._set_state('pending')
        if (self._in_flight is None
                and self._newest_revision <= self._durable_revision):
            self._draining = False
            self._set_state('saved')
            self.drained.emit()
            return
        self.flush()

    def complete(self, ticket):
        if not self._is_current_in_flight(ticket):
            return
        self._durable_revision = max(
            self._durable_revision, ticket.revision)
        self._in_flight = None
        if self._newest_revision > self._durable_revision:
            self._set_state('pending')
            if self._enabled or self._draining:
                self.flush()
        else:
            self._draining = False
            self._set_state('saved')
            self.drained.emit()

    def fail(self, ticket, message):
        if not self._is_current_in_flight(ticket):
            return False
        self._in_flight = None
        self._draining = False
        self.error = str(message)
        self._set_state('failed')
        return True

    def retry(self):
        if self._state != 'failed':
            return
        self.error = None
        self._set_state('pending')
        self.flush()

    def _is_current_in_flight(self, ticket):
        return (
            ticket == self._in_flight
            and ticket.document_key == self._document_key
            and ticket.generation == self._generation)
