"""Immutable identity for one committed document generation."""

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DocumentIdentity:
    """Normalize the value carried by async document callbacks."""

    kind: str
    key: str
    generation: int

    def __post_init__(self):
        object.__setattr__(self, 'kind', str(self.kind))
        object.__setattr__(
            self, 'key',
            os.path.abspath(os.fspath(self.key)) if self.key else '')
        object.__setattr__(self, 'generation', int(self.generation))
