"""Authoritative state for projecting a canvas view into a zoom percentage."""

from dataclasses import dataclass
from enum import Enum

from libs.widgets import view_scaling


class ViewMode(str, Enum):
    """The active source of truth for canvas zoom."""

    FIT_WINDOW = 'fit_window'
    FIT_WIDTH = 'fit_width'
    MANUAL = 'manual'


@dataclass(frozen=True)
class ViewProjection:
    """The computed zoom percentage for one viewport/pixmap pair."""

    mode: ViewMode
    percent: int


class ViewTransform:
    """Keep fit selection separate from its layout-dependent projection."""

    def __init__(self):
        self.mode = ViewMode.FIT_WINDOW
        self.manual_percent = 100

    def start_session(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_window(self):
        self.mode = ViewMode.FIT_WINDOW

    def choose_fit_width(self):
        self.mode = ViewMode.FIT_WIDTH

    def choose_manual(self, percent):
        self.mode = ViewMode.MANUAL
        self.manual_percent = max(1, min(500, int(percent)))

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
        percent = min(int(round(scale * 100)), maximum_percent)
        return ViewProjection(self.mode, max(1, percent))

    @staticmethod
    def _maximum_width_percent(viewport, pixmap):
        if pixmap[0] <= 0:
            return 1
        return max(1, int(viewport[0] * 100 // pixmap[0]))

    @classmethod
    def _maximum_window_percent(cls, viewport, pixmap):
        if pixmap[1] <= 0:
            return cls._maximum_width_percent(viewport, pixmap)
        return min(
            cls._maximum_width_percent(viewport, pixmap),
            max(1, int(viewport[1] * 100 // pixmap[1])))
