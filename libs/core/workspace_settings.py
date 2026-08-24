"""Validated settings contract for the modern workspace shell."""

from dataclasses import dataclass

from libs.utils.constants import (
    SETTING_INSPECTOR_COLLAPSED, SETTING_INSPECTOR_TAB,
    SETTING_INSPECTOR_WIDTH, SETTING_PROMPT_POLICY, SETTING_SINGLE_CLASS,
)


DEFAULT_INSPECTOR_WIDTH = 304
MIN_INSPECTOR_WIDTH = 260
MAX_INSPECTOR_WIDTH = 420
INSPECTOR_DRAWER_BREAKPOINT = 960
INSPECTOR_TABS = ('objects', 'files')
PROMPT_POLICIES = ('reuse_active', 'confirm_each')


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


def load_prompt_policy(settings):
    """Load a valid prompt policy while migrating the legacy mode."""
    policy = settings.get(SETTING_PROMPT_POLICY)
    if policy in PROMPT_POLICIES:
        return policy
    if settings.get(SETTING_SINGLE_CLASS) is True:
        return 'reuse_active'
    return 'reuse_active'


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
