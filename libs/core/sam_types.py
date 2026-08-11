"""Immutable plain-data contracts for Smart Select results."""

from dataclasses import dataclass
from typing import Tuple


Point = Tuple[float, float]
Bounds = Tuple[float, float, float, float]


def normalize_sam_output_mode(value):
    """Return a supported persisted output mode, defaulting to polygon."""
    return value if value in ('polygon', 'box') else 'polygon'


@dataclass(frozen=True)
class SamResult:
    """Simplified polygon and tight half-open image-space mask bounds."""

    polygon: Tuple[Point, ...]
    bounds: Bounds
