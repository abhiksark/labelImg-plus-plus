"""Authoritative state for projecting a canvas view into a zoom percentage."""

from dataclasses import dataclass
from enum import Enum
import math

from libs.widgets import view_scaling


# The zoom widget uses the same precision, so a fractional projection can be
# painted exactly as the authoritative transform produced it.
PERCENT_DECIMALS = 12
MIN_PERCENT = 10 ** -PERCENT_DECIMALS


class ViewMode(str, Enum):
    """The active source of truth for canvas zoom."""

    FIT_WINDOW = 'fit_window'
    FIT_WIDTH = 'fit_width'
    MANUAL = 'manual'


@dataclass(frozen=True)
class ViewProjection:
    """The computed zoom percentage for one viewport/pixmap pair."""

    mode: ViewMode
    percent: float


class ViewTransform:
    """Keep fit selection separate from its layout-dependent projection."""

    def __init__(self):
        self.mode = ViewMode.FIT_WINDOW
        self.manual_percent = 100.0

    def start_session(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_window(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_width(self):
        self.mode = ViewMode.FIT_WIDTH

    def choose_manual(self, percent):
        self.mode = ViewMode.MANUAL
        self.manual_percent = max(MIN_PERCENT, min(500.0, float(percent)))

    def project(self, viewport, pixmap):
        if self.mode is ViewMode.MANUAL:
            return ViewProjection(self.mode, self.manual_percent)
        if self.mode is ViewMode.FIT_WIDTH:
            scale = view_scaling.fit_width_scale(viewport[0], pixmap[0])
            maximum_percent = self._maximum_width_percent(viewport, pixmap)
        else:
            scale = view_scaling.fit_window_scale(
                viewport[0], viewport[1], pixmap[0], pixmap[1])
            maximum_percent = self._maximum_window_percent(
                viewport, pixmap)
        percent = scale * 100
        if percent >= 1:
            # Whole-percent display remains the normal case, but never at a
            # scale which would exceed the actual viewport.
            percent = min(int(round(percent)), int(maximum_percent))
        else:
            # A positive fit smaller than one percent cannot be rounded to a
            # whole percentage.  Truncate to widget precision so the value
            # remains representable and cannot paint beyond either fit axis.
            percent = self._truncate_fractional_percent(
                min(percent, maximum_percent))
        return ViewProjection(self.mode, max(MIN_PERCENT, percent))

    @staticmethod
    def _maximum_width_percent(viewport, pixmap):
        if pixmap[0] <= 0:
            return 1
        return float(viewport[0]) * 100 / pixmap[0]

    @classmethod
    def _maximum_window_percent(cls, viewport, pixmap):
        if pixmap[1] <= 0:
            return cls._maximum_width_percent(viewport, pixmap)
        return min(
            cls._maximum_width_percent(viewport, pixmap),
            float(viewport[1]) * 100 / pixmap[1])

    @staticmethod
    def _truncate_fractional_percent(percent):
        """Return a positive widget-representable percent without rounding up."""
        precision = 10 ** PERCENT_DECIMALS
        return math.floor(percent * precision) / precision
