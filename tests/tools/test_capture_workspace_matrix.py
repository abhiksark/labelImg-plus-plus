"""Contracts for deterministic workspace screenshot captures."""

import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HARNESS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'tools', 'ux'))
REPOSITORY_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..'))
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)


from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from labelImgPlusPlus import DocumentKind, get_main_app  # noqa: E402
import capture_workspace_matrix as matrix  # noqa: E402
from libs.utils.styles import Theme  # noqa: E402


EXPECTED_SCENARIOS = (
    'empty-workspace',
    'first-image-fit',
    'two-rectangles',
    'inspector-open',
    'inspector-closed',
    'saving',
    'saved',
    'save-failed',
    'video-paused',
    'video-playing',
    'video-invalid-time',
    'video-track-menu',
    'video-propagation-pending',
    'assist-setup',
    'assist-downloading',
    'assist-failure',
    'assist-preview',
    'shutdown-timeout',
)

ASSIST_PHASES = {
    'assist-setup': matrix.AssistPhase.SETUP_REQUIRED,
    'assist-downloading': matrix.AssistPhase.DOWNLOADING,
    'assist-failure': matrix.AssistPhase.FAILED,
    'assist-preview': matrix.AssistPhase.PREVIEW,
}
FULL_MATRIX_MAX_SECONDS = 180.0


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    _app, value = get_main_app()
    value._ux_capture_context = SimpleNamespace(
        dataset_dir=str(tmp_path), image_path=str(tmp_path / 'sample.png'))
    matrix._write_sample_image(tmp_path / 'sample.png')
    value.show()
    QApplication.processEvents()
    yield value
    matrix.cleanup_scenario(value)
    value.continuous_save.set_enabled(False)
    value.dirty = False
    value.close()
    QApplication.processEvents()


def test_registry_is_explicit_deterministic_and_complete():
    """A renamed or omitted capture state changes the public evidence matrix."""
    assert matrix.SCENARIO_ORDER == EXPECTED_SCENARIOS
    assert tuple(matrix.SCENARIOS) == EXPECTED_SCENARIOS
    assert all(callable(setup) for setup in matrix.SCENARIOS.values())
    assert len(matrix.SCENARIO_ORDER) * len(matrix.SIZES) * \
        len(matrix.THEMES) == 144


def test_capture_uses_logical_size_and_stable_name(window, tmp_path):
    """The full-window artifact is exactly the requested 1x logical size."""
    path = matrix.capture_scenario(
        window, 'empty-workspace', (800, 600), 'light', tmp_path)

    screenshot = QImage(path)
    assert os.path.basename(path) == 'empty-workspace-light-800x600.png'
    assert (screenshot.width(), screenshot.height()) == (800, 600)


@pytest.mark.parametrize('theme', ('sepia', '', None))
def test_capture_rejects_unknown_theme(window, tmp_path, theme):
    """Silently mapping an unknown theme to light would corrupt evidence."""
    with pytest.raises(ValueError, match='theme'):
        matrix.capture_scenario(
            window, 'empty-workspace', (800, 600), theme, tmp_path)


def test_capture_rejects_unknown_scenario(window, tmp_path):
    """A typo must not create an unlabelled or misleading screenshot."""
    with pytest.raises(ValueError, match='scenario'):
        matrix.capture_scenario(
            window, 'not-a-workspace-state', (800, 600), 'light', tmp_path)


@pytest.mark.parametrize('scenario', EXPECTED_SCENARIOS[8:])
def test_extended_scenarios_project_meaningful_real_state(
        window, tmp_path, scenario):
    """Capture states must expose a real state owner, not painted mock copy."""
    path = matrix.capture_scenario(
        window, scenario, (800, 600), 'dark', tmp_path)

    assert os.path.isfile(path)
    assert matrix.scenario_is_meaningful(window, scenario)
    if scenario.startswith('video-'):
        assert window.document_kind == DocumentKind.VIDEO
        assert window.video_timeline._snapshot is not None
    if scenario.startswith('assist-'):
        assert window.workspace_pages.assist_panel.isVisible()
    if scenario == 'shutdown-timeout':
        assert window._shutdown_surface.isVisible()


def test_video_then_assist_states_republish_the_image_workspace(
        window, tmp_path):
    """A stale VIDEO kind after capture must not label an Assist PNG as image."""
    expected_path = window._ux_capture_context.image_path
    matrix.capture_scenario(
        window, 'first-image-fit', (800, 600), 'light', tmp_path)

    for scenario, expected_phase in ASSIST_PHASES.items():
        matrix.capture_scenario(
            window, 'video-paused', (800, 600), 'light', tmp_path)
        assert window.document_kind == DocumentKind.VIDEO
        assert window.file_path == expected_path

        matrix.capture_scenario(
            window, scenario, (800, 600), 'light', tmp_path)

        assert window.document_kind == DocumentKind.IMAGE
        assert window.file_path == expected_path
        assert window.canvas.pixmap is not None
        assert (window.canvas.pixmap.width(), window.canvas.pixmap.height()) \
            == (640, 480)
        assert not window.video_timeline.isVisible()
        assert not window.video_timeline.isEnabled()
        assert window.workspace_pages.assist_panel.isVisible()
        assert window.assist_state.snapshot.phase is expected_phase
        assert matrix.scenario_is_meaningful(window, scenario)


def _assert_capture_failure_cleanup(window, original_theme,
                                    original_stylesheet, original_policy):
    """Check the visible ownership state a failed capture must release."""
    assert window._current_theme is original_theme
    assert window.styleSheet() == original_stylesheet
    assert window.workflow.snapshot.prompt_policy is original_policy
    assert not hasattr(window, '_ux_capture_save')
    assert window.continuous_save._in_flight is None
    assert not window.video_timeline.track_menu.isVisible()
    assert not hasattr(window, '_ux_capture_track_menu_flags')
    assert not window.workspace_pages.assist_panel.isVisible()
    assert window.canvas.assist_preview_shape is None
    assert window._assist_download_progress is None
    assert window._assist_prompt is None
    assert window._assist_document_identity is None
    assert (window._shutdown_surface is None
            or not window._shutdown_surface.isVisible())
    assert window._replacement_loading_owner is None
    assert (window._loading_veil is None
            or not window._loading_veil.isVisible())


@pytest.mark.parametrize(
    'scenario', ('saving', 'video-track-menu', 'assist-downloading',
                 'shutdown-timeout'))
def test_post_setup_error_cleans_every_capture_projection_and_restores_theme(
        window, tmp_path, monkeypatch, scenario):
    """A setup exception must not leave a dark or held transient UI behind."""
    window._current_theme = Theme.LIGHT
    window._apply_theme(Theme.LIGHT)
    window.active_class_control.confirm_each.setChecked(True)
    original_theme = window._current_theme
    original_stylesheet = window.styleSheet()
    original_policy = window.workflow.snapshot.prompt_policy
    original_setup = matrix.SCENARIOS[scenario]

    def fail_after_real_setup(target):
        original_setup(target)
        target._show_replacement_loading(
            ('capture-test', scenario), 'Capture setup failed')
        raise RuntimeError('forced post-setup failure')

    monkeypatch.setitem(matrix.SCENARIOS, scenario, fail_after_real_setup)
    with pytest.raises(RuntimeError, match='post-setup'):
        matrix.capture_scenario(
            window, scenario, (800, 600), 'dark', tmp_path)

    _assert_capture_failure_cleanup(
        window, original_theme, original_stylesheet, original_policy)


def test_png_save_error_cleans_assist_projection_and_restores_theme(
        window, tmp_path, monkeypatch):
    """A failed PNG save must unwind a completed Assist setup transaction."""
    window._current_theme = Theme.LIGHT
    window._apply_theme(Theme.LIGHT)
    original_theme = window._current_theme
    original_stylesheet = window.styleSheet()
    original_policy = window.workflow.snapshot.prompt_policy

    class FailedGrab(object):
        def save(self, *_args):
            return False

    monkeypatch.setattr(window, 'grab', lambda: FailedGrab())
    with pytest.raises(AssertionError):
        matrix.capture_scenario(
            window, 'assist-preview', (800, 600), 'dark', tmp_path)

    _assert_capture_failure_cleanup(
        window, original_theme, original_stylesheet, original_policy)


def test_cleanup_scenario_is_idempotent_without_cancelling_live_workers(
        window, monkeypatch):
    """Capture cleanup releases only UI projections, never task-owner work."""
    matrix._video_track_menu(window)
    window._show_replacement_loading(('capture-test', 'cleanup'), 'Cleanup')

    def unexpected_worker_cancellation(*_args, **_kwargs):
        raise AssertionError('capture cleanup must not cancel live workers')

    monkeypatch.setattr(
        window.task_coordinator, 'cancel_key', unexpected_worker_cancellation)
    matrix.cleanup_scenario(window)
    matrix.cleanup_scenario(window)

    assert window._replacement_loading_owner is None
    assert not window.video_timeline.track_menu.isVisible()
    assert not hasattr(window, '_ux_capture_track_menu_flags')


def test_full_matrix_cli_writes_every_named_1x_artifact(tmp_path):
    """The standalone capture command must finish and retain every artifact."""
    environment = os.environ.copy()
    environment['LABELIMGPP_SETTINGS_PATH'] = str(
        tmp_path / 'subprocess-settings.json')
    command = (
        sys.executable,
        os.path.join(HARNESS_DIR, 'capture_workspace_matrix.py'),
        '--output-dir',
        str(tmp_path),
    )
    started = time.monotonic()
    completed = subprocess.run(
        command, cwd=REPOSITORY_ROOT, env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        universal_newlines=True, timeout=FULL_MATRIX_MAX_SECONDS)
    elapsed = time.monotonic() - started

    expected_dimensions = {
        '%s-%s-%sx%s.png' % (scenario, theme, width, height):
        (width, height)
        for scenario in EXPECTED_SCENARIOS
        for theme in matrix.THEMES
        for width, height in matrix.SIZES
    }
    assert elapsed < FULL_MATRIX_MAX_SECONDS, (
        'full workspace matrix exceeded %.1fs (%.1fs)'
        % (FULL_MATRIX_MAX_SECONDS, elapsed))
    assert completed.returncode == 0, completed.stderr
    paths = [os.path.join(str(tmp_path), name)
             for name in os.listdir(str(tmp_path)) if name.endswith('.png')]
    assert len(paths) == 144
    assert len(set(paths)) == 144
    assert {os.path.basename(path) for path in paths} == set(expected_dimensions)
    for path in paths:
        screenshot = QImage(path)
        assert os.path.getsize(path) > 0
        assert not screenshot.isNull()
        assert (screenshot.width(), screenshot.height()) == \
            expected_dimensions[os.path.basename(path)]
