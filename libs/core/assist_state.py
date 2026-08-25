"""Qt-free state and plain-data records for contextual Assist workflows."""

from dataclasses import dataclass, replace
from enum import Enum


class AssistPhase(str, Enum):
    SETUP_REQUIRED = 'setup_required'
    READY_TO_DOWNLOAD = 'ready_to_download'
    DOWNLOADING = 'downloading'
    READY = 'ready'
    RUNNING = 'running'
    PREVIEW = 'preview'
    FAILED = 'failed'


class AssistFailureKind(str, Enum):
    OFFLINE = 'offline'
    PROVIDER = 'provider'
    VALIDATION = 'validation'
    RUNTIME = 'runtime'
    INFERENCE = 'inference'


@dataclass(frozen=True)
class AssistPrompt:
    """Plain image-space prompt coordinates sent to an Assist provider."""

    mode: str
    positive_points: tuple = ()
    negative_points: tuple = ()
    box: object = None


@dataclass(frozen=True)
class AssistPreview:
    """A provisional provider result and the prompt that produced it."""

    result: object
    prompt: object = None


@dataclass(frozen=True)
class AssistSnapshot:
    phase: AssistPhase = AssistPhase.SETUP_REQUIRED
    model_id: object = None
    document_generation: object = None
    preview: object = None
    failure_kind: object = None
    message: str = ''


class AssistState:
    """Own the Assist lifecycle without mutating annotation state."""

    def __init__(self):
        self.snapshot = AssistSnapshot()

    def require_setup(self, model_id):
        self.snapshot = AssistSnapshot(
            AssistPhase.SETUP_REQUIRED, model_id=model_id)

    def ready_to_download(self, model_id):
        self.snapshot = AssistSnapshot(
            AssistPhase.READY_TO_DOWNLOAD, model_id=model_id)

    def start_download(self):
        self._require_phase(AssistPhase.READY_TO_DOWNLOAD)
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.DOWNLOADING,
            failure_kind=None, message='')

    def download_ready(self):
        self._require_phase(AssistPhase.DOWNLOADING)
        self.ready(self.snapshot.model_id)

    def ready(self, model_id=None):
        if model_id is None:
            model_id = self.snapshot.model_id
        self.snapshot = AssistSnapshot(
            AssistPhase.READY, model_id=model_id)

    def start_run(self, document_generation):
        self._require_phase(AssistPhase.READY)
        generation = int(document_generation)
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.RUNNING,
            document_generation=generation, preview=None,
            failure_kind=None, message='')

    def show_preview(self, document_generation, result):
        self._require_phase(AssistPhase.RUNNING)
        if int(document_generation) != self.snapshot.document_generation:
            return False
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.PREVIEW, preview=result)
        return True

    def accept_preview(self):
        self._require_phase(AssistPhase.PREVIEW)
        value = self.snapshot.preview
        self.ready(self.snapshot.model_id)
        return value

    def reject_preview(self):
        self._require_phase(AssistPhase.PREVIEW)
        self.ready(self.snapshot.model_id)

    def fail(self, kind, message):
        self.snapshot = replace(
            self.snapshot, phase=AssistPhase.FAILED,
            preview=None, failure_kind=AssistFailureKind(kind),
            message=str(message))

    def _require_phase(self, phase):
        if self.snapshot.phase is not phase:
            raise ValueError(
                'Assist transition requires %s, got %s' % (
                    phase.value, self.snapshot.phase.value))
