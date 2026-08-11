"""Validated settings contract for the modern workspace shell."""

from dataclasses import dataclass

from libs.utils.constants import (
    SETTING_INSPECTOR_COLLAPSED, SETTING_INSPECTOR_TAB,
    SETTING_INSPECTOR_WIDTH,
)


DEFAULT_INSPECTOR_WIDTH = 304
MIN_INSPECTOR_WIDTH = 260
MAX_INSPECTOR_WIDTH = 420
INSPECTOR_TABS = ('objects', 'files')


@dataclass(frozen=True)
class WorkspaceSettings:
    inspector_width: int = DEFAULT_INSPECTOR_WIDTH
    inspector_collapsed: bool = False
    inspector_tab: str = 'objects'


def clamp_inspector_width(value):
    """Validate and clamp a logical-pixel inspector width."""
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_INSPECTOR_WIDTH
    return max(MIN_INSPECTOR_WIDTH, min(MAX_INSPECTOR_WIDTH, value))


def load_workspace_settings(settings):
    """Return safe workspace values from a Settings-like mapping."""
    width = clamp_inspector_width(settings.get(
        SETTING_INSPECTOR_WIDTH, DEFAULT_INSPECTOR_WIDTH))
    collapsed = settings.get(SETTING_INSPECTOR_COLLAPSED, False)
    if not isinstance(collapsed, bool):
        collapsed = False
    tab = settings.get(SETTING_INSPECTOR_TAB, 'objects')
    if tab not in INSPECTOR_TABS:
        tab = 'objects'
    return WorkspaceSettings(width, collapsed, tab)
