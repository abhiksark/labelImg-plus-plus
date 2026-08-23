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
        else:
            scale = view_scaling.fit_window_scale(
                viewport[0], viewport[1], pixmap[0], pixmap[1])
        return ViewProjection(self.mode, max(1, int(round(scale * 100))))
