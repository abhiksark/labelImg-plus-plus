"""Workflow settings migration and downgrade-safe persistence coverage."""

import os
from dataclasses import FrozenInstanceError

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import MainWindow
from libs.core.settings import Settings
from libs.core.workspace_settings import (
    WorkflowSettingsMigration, migrate_workflow_settings,
)
from libs.utils.constants import (
    SETTING_AUTO_SAVE, SETTING_AUTO_SAVE_ENABLED, SETTING_AUTO_SAVE_INTERVAL,
    SETTING_CONTINUOUS_SAVE, SETTING_PROMPT_POLICY, SETTING_SINGLE_CLASS,
)


def test_navigation_autosave_migrates_to_continuous_enabled():
    """Catches dropping the legacy navigation-save preference at migration."""
    settings = {SETTING_AUTO_SAVE: True, SETTING_AUTO_SAVE_ENABLED: False}

    migrated = migrate_workflow_settings(settings)

    assert migrated.continuous_save is True
    assert settings[SETTING_AUTO_SAVE] is True
    assert settings[SETTING_AUTO_SAVE_ENABLED] is False


def test_legacy_interval_stays_readable_but_is_not_primary_policy():
    """Catches making the retired timer interval control the new debounce."""
    settings = {SETTING_AUTO_SAVE_INTERVAL: 120}

    migrated = migrate_workflow_settings(settings)

    assert migrated.legacy_interval == 120
    assert migrated.continuous_delay_ms == 250
    assert settings[SETTING_AUTO_SAVE_INTERVAL] == 120


def test_singleclass_migrates_to_reuse_active_without_preselecting_label():
    """Catches treating a legacy preference as a persisted session label."""
    settings = {SETTING_SINGLE_CLASS: True}

    migrated = migrate_workflow_settings(settings)

    assert migrated.prompt_policy == 'reuse_active'
    assert migrated.active_class is None


def test_unset_profile_defaults_to_enabled_immutable_continuous_save():
    """Catches a first-use profile inheriting a disabled legacy default."""
    migrated = migrate_workflow_settings({})

    assert migrated == WorkflowSettingsMigration(
        continuous_save=True,
        continuous_delay_ms=250,
        prompt_policy='reuse_active',
        legacy_interval=60,
        active_class=None,
    )
    with pytest.raises(FrozenInstanceError):
        migrated.continuous_save = False


def test_new_continuous_and_prompt_settings_are_authoritative():
    """Catches legacy controls overriding valid consolidated preferences."""
    settings = {
        SETTING_CONTINUOUS_SAVE: False,
        SETTING_AUTO_SAVE: True,
        SETTING_AUTO_SAVE_ENABLED: True,
        SETTING_AUTO_SAVE_INTERVAL: 300,
        SETTING_SINGLE_CLASS: True,
        SETTING_PROMPT_POLICY: 'confirm_each',
    }
    before = dict(settings)

    migrated = migrate_workflow_settings(settings)

    assert migrated.continuous_save is False
    assert migrated.prompt_policy == 'confirm_each'
    assert settings == before


def test_window_writes_consolidated_save_without_persisting_session_state(
        monkeypatch, tmp_path):
    """Catches close rewriting legacy keys or storing active class/tool state."""
    settings_path = tmp_path / 'settings.json'
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('LABELIMGPP_SETTINGS_PATH', str(settings_path))
    legacy = {
        SETTING_AUTO_SAVE: False,
        SETTING_AUTO_SAVE_ENABLED: True,
        SETTING_AUTO_SAVE_INTERVAL: 120,
        SETTING_SINGLE_CLASS: True,
    }
    initial = Settings()
    initial.data.update(legacy)
    assert initial.save()

    window = MainWindow(default_save_dir=str(tmp_path))
    try:
        assert window.save_changes_automatically.isChecked()
        assert window.single_class_mode.isChecked()
        assert window.single_class_mode not in window.menus.view.actions()
        window.save_changes_automatically.setChecked(False)
        window.workflow.set_active_class('session-only')
        window.workflow.set_tool('polygon')
        window.dirty = False
        window.close()
        QApplication.processEvents()
        QApplication.processEvents()
    finally:
        if not window.isHidden():
            window.dirty = False
            window.close()
            QApplication.processEvents()

    persisted = Settings()
    assert persisted.load()
    assert persisted.get(SETTING_CONTINUOUS_SAVE) is False
    for key, value in legacy.items():
        assert persisted.get(key) == value
    assert 'workflow/activeClass' not in persisted.data
    assert 'workflow/activeTool' not in persisted.data
