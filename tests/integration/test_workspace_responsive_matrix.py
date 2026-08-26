"""Responsive accessibility contracts for the primary workspace paths."""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import MainWindow
from libs.core.assist_state import AssistPhase, AssistSnapshot
from libs.integrations.model_manifest import MOBILE_SAM_MANIFEST
from libs.utils.accessibility import contrast_ratio, visible_primary_targets
from libs.utils.styles import Theme, get_theme_colors, hex_to_qcolor
from libs.widgets.videoTimelineWidget import VideoTimelineWidget


app = QApplication.instance() or QApplication([])

_SIZES = ((800, 600), (960, 640), (1366, 768), (1440, 900))
_NORMAL_TEXT_PAIRS = (
    ('text', 'background'),
    ('text', 'surface'),
    ('text_secondary', 'surface'),
    ('accent_text', 'accent_light'),
    ('on_accent', 'accent'),
)
_MEANINGFUL_BOUNDARY_PAIRS = (
    ('border', 'surface'),
    ('border', 'surface_subtle'),
    ('border', 'surface_raised'),
    ('focus', 'surface'),
    ('accent_light', 'surface'),
)


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv(
        'LABELIMGPP_SETTINGS_PATH', str(tmp_path / 'settings.json'))
    value = MainWindow(default_save_dir=str(tmp_path))
    yield value
    value.dirty = False
    value.close()
    QApplication.processEvents()
    QApplication.processEvents()


def _show(window, size, page):
    window.workspace_pages.set_page(page)
    window.resize(*size)
    window.show()
    QApplication.processEvents()
    QApplication.processEvents()


def _target_failures(targets):
    return [
        '%s(%r): name=%r size=%dx%d' % (
            type(widget).__name__, widget.objectName(),
            widget.accessibleName(), widget.width(), widget.height())
        for widget in targets
        if (not widget.accessibleName().strip()
            or widget.width() < 32 or widget.height() < 32)
    ]


@pytest.mark.parametrize('size', _SIZES)
@pytest.mark.parametrize('page', ('empty', 'canvas'))
def test_primary_targets_are_visible_named_and_large(window, size, page):
    """Every visible primary target clears the shared 32px/name contract."""
    _show(window, size, page)
    targets = visible_primary_targets(window)
    assert targets
    assert not _target_failures(targets)


def test_primary_tool_projection_has_exactly_one_checked_action(window):
    _show(window, (800, 600), 'canvas')
    checked = [
        action for action in window.tool_rail.action_group.actions()
        if action.isChecked()
    ]
    assert len(checked) == 1


def test_hidden_command_is_not_reachable_in_narrow_focus_chain(window):
    _show(window, (800, 600), 'canvas')
    hidden = window.command_bar.format_button
    assert hidden.isHidden()

    current = window.command_bar.application_button
    reachable = []
    for _index in range(128):
        current = current.nextInFocusChain()
        if (current.isVisibleTo(window) and current.isEnabled()
                and current.focusPolicy() != Qt.NoFocus):
            reachable.append(current)
        if current is window.command_bar.application_button:
            break
    assert hidden not in reachable


def test_drawer_traps_tab_and_restores_reopen_focus(window):
    _show(window, (800, 600), 'canvas')
    window.workspace_shell.open_inspector()
    QApplication.processEvents()
    for _index in range(8):
        QTest.keyClick(QApplication.focusWidget(), Qt.Key_Tab)
        QApplication.processEvents()
        focused = QApplication.focusWidget()
        assert (focused is window.workspace_inspector
                or window.workspace_inspector.isAncestorOf(focused))

    window.workspace_shell.close_inspector()
    QApplication.processEvents()
    assert window.workspace_shell.reopen_button.hasFocus()


def test_assist_primary_actions_keep_the_800px_canvas_layout(window):
    _show(window, (800, 600), 'canvas')
    panel = window.workspace_pages.assist_panel
    panel.set_snapshot(
        AssistSnapshot(
            phase=AssistPhase.READY_TO_DOWNLOAD,
            model_id=MOBILE_SAM_MANIFEST.model_id),
        MOBILE_SAM_MANIFEST)
    window.workspace_pages.show_assist()
    QApplication.processEvents()

    surface = window.workspace_pages.page_surface
    assert panel.geometry().right() == surface.rect().right()
    assert panel.height() == surface.height()
    assert not _target_failures(visible_primary_targets(panel))


def test_timeline_accessibility_tracks_current_action_and_marker_meaning():
    timeline = VideoTimelineWidget()
    timeline.resize(720, 120)
    timeline.show()
    QApplication.processEvents()
    try:
        timeline.set_playing(False)
        assert timeline.play_button.accessibleName() == 'Play video'
        timeline.set_playing(True)
        assert timeline.play_button.accessibleName() == 'Pause video'

        timeline.set_markers(accepted=(10,), pending=(20,), gaps=(30,))
        summary = timeline.slider.accessible_marker_summary().lower()
        assert 'accepted' in summary
        assert 'pending' in summary
        assert 'gap' in summary
        assert 'green' not in summary
        assert not _target_failures(visible_primary_targets(timeline))
    finally:
        timeline.close()


@pytest.mark.parametrize('theme', (Theme.LIGHT, Theme.DARK))
def test_measured_workspace_token_pairs_meet_contrast_contract(theme):
    """Only named token pairs used by workspace styles are evaluated."""
    colors = get_theme_colors(theme)
    for foreground, background in _NORMAL_TEXT_PAIRS:
        ratio = contrast_ratio(
            hex_to_qcolor(colors[foreground]), hex_to_qcolor(colors[background]))
        assert ratio >= 4.5, '%s/%s is %.2f:1' % (
            foreground, background, ratio)
    for foreground, background in _MEANINGFUL_BOUNDARY_PAIRS:
        ratio = contrast_ratio(
            hex_to_qcolor(colors[foreground]), hex_to_qcolor(colors[background]))
        assert ratio >= 3.0, '%s/%s is %.2f:1' % (
            foreground, background, ratio)
