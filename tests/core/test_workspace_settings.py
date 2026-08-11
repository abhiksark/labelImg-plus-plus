"""Validation coverage for modern workspace settings."""

from libs.core.workspace_settings import (
    DEFAULT_INSPECTOR_WIDTH, WorkspaceSettings, clamp_inspector_width,
    load_workspace_settings,
)


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
