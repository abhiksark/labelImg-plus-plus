"""Contracts for deterministic workspace screenshot captures."""

import os
import sys
from types import SimpleNamespace

import pytest


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HARNESS_DIR = os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..', '..', 'tools', 'ux'))
if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)


from PyQt5.QtGui import QImage  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from labelImgPlusPlus import DocumentKind, get_main_app  # noqa: E402
import capture_workspace_matrix as matrix  # noqa: E402


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
