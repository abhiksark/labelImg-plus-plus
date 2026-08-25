"""Validated settings contract for the modern workspace shell."""

from dataclasses import dataclass

from libs.utils.constants import (
    SETTING_AUTO_SAVE, SETTING_AUTO_SAVE_ENABLED, SETTING_AUTO_SAVE_INTERVAL,
    SETTING_CONTINUOUS_SAVE,
    SETTING_INSPECTOR_COLLAPSED, SETTING_INSPECTOR_TAB,
    SETTING_INSPECTOR_WIDTH, SETTING_PROMPT_POLICY,
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


@dataclass(frozen=True)
class WorkflowSettingsMigration:
    """Runtime workflow policy resolved without rewriting legacy settings."""
    continuous_save: bool
    continuous_delay_ms: int
    prompt_policy: str
    legacy_interval: int
    active_class: object = None


def clamp_inspector_width(value):
    """Validate and clamp a logical-pixel inspector width."""
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_INSPECTOR_WIDTH
    return max(MIN_INSPECTOR_WIDTH, min(MAX_INSPECTOR_WIDTH, value))


def load_prompt_policy(settings):
    """Load a valid prompt policy while migrating the legacy mode."""
    return migrate_workflow_settings(settings).prompt_policy


def migrate_workflow_settings(settings):
    """Resolve workflow policy while retaining legacy values for downgrade."""
    continuous = settings.get(SETTING_CONTINUOUS_SAVE, None)
    if continuous is None:
        navigation = settings.get(SETTING_AUTO_SAVE, None)
        timer = settings.get(SETTING_AUTO_SAVE_ENABLED, None)
        continuous = (True if navigation is None and timer is None
                      else bool(navigation or timer))
    policy = settings.get(SETTING_PROMPT_POLICY)
    if policy not in PROMPT_POLICIES:
        policy = 'reuse_active'
    interval = settings.get(SETTING_AUTO_SAVE_INTERVAL, 60)
    if interval not in (30, 60, 120, 300):
        interval = 60
    return WorkflowSettingsMigration(
        bool(continuous), 250, policy, interval, None)


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
