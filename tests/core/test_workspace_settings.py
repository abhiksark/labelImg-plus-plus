"""Validation coverage for modern workspace settings."""

from libs.core.workspace_settings import (
    DEFAULT_INSPECTOR_WIDTH, WorkspaceSettings, clamp_inspector_width,
    load_prompt_policy, load_workspace_settings,
)
from libs.utils.constants import SETTING_PROMPT_POLICY, SETTING_SINGLE_CLASS


def test_workspace_defaults_are_balanced_contract():
    assert load_workspace_settings({}) == WorkspaceSettings(
        inspector_width=304,
        inspector_collapsed=False,
        inspector_tab='objects',
    )


def test_inspector_width_rejects_malformed_values_and_clamps_integers():
    for value in (None, True, 304.0, '304', [], {}):
        assert clamp_inspector_width(value) == DEFAULT_INSPECTOR_WIDTH
    assert clamp_inspector_width(100) == 260
    assert clamp_inspector_width(350) == 350
    assert clamp_inspector_width(900) == 420


def test_workspace_loader_rejects_malformed_tab_and_collapsed_state():
    loaded = load_workspace_settings({
        'workspace/inspectorWidth': 800,
        'workspace/inspectorCollapsed': 'yes',
        'workspace/inspectorTab': 'tracks',
    })
    assert loaded == WorkspaceSettings(
        inspector_width=420,
        inspector_collapsed=False,
        inspector_tab='objects',
    )


def test_workspace_loader_accepts_files_and_collapsed():
    loaded = load_workspace_settings({
        'workspace/inspectorWidth': 280,
        'workspace/inspectorCollapsed': True,
        'workspace/inspectorTab': 'files',
    })
    assert loaded == WorkspaceSettings(280, True, 'files')


def test_legacy_single_class_migrates_to_reuse_active():
    settings = {SETTING_SINGLE_CLASS: True}

    assert load_prompt_policy(settings) == 'reuse_active'


def test_prompt_policy_accepts_known_values_and_defaults_invalid_values():
    assert load_prompt_policy({
        SETTING_PROMPT_POLICY: 'confirm_each',
    }) == 'confirm_each'
    assert load_prompt_policy({
        SETTING_PROMPT_POLICY: 'unexpected',
    }) == 'reuse_active'


def test_valid_prompt_policy_is_authoritative_over_legacy_single_class():
    assert load_prompt_policy({
        SETTING_SINGLE_CLASS: True,
        SETTING_PROMPT_POLICY: 'confirm_each',
    }) == 'confirm_each'
