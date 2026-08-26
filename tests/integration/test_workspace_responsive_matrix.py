"""Responsive accessibility contracts for the primary workspace paths."""

import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import QPoint, QRect, Qt
from PyQt5.QtGui import QImage
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import DocumentKind, MainWindow
from libs.core.assist_state import AssistPhase, AssistSnapshot
from libs.core.video_types import (
    VideoFingerprint, VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
)
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
    if page == 'canvas':
        assert window.zoom_widget in targets
    assert not _target_failures(targets)


def test_primary_tool_projection_has_exactly_one_checked_action(window):
    _show(window, (800, 600), 'canvas')
    checked = [
        action for action in window.tool_rail.action_group.actions()
        if action.isChecked()
    ]
    assert len(checked) == 1


def test_hidden_format_command_never_receives_real_tab_focus(window):
    """A hidden Format command must not become focused during real Tab input."""
    _show(window, (800, 600), 'canvas')
    hidden = window.command_bar.format_button
    assert hidden.isHidden()

    window.command_bar.application_button.setFocus(Qt.TabFocusReason)
    QApplication.processEvents()
    assert QApplication.focusWidget() is window.command_bar.application_button

    visited = []
    for _index in range(128):
        focused = QApplication.focusWidget()
        assert focused is not hidden
        visited.append(focused)
        QTest.keyClick(focused, Qt.Key_Tab)
        QApplication.processEvents()
        if (QApplication.focusWidget()
                is window.command_bar.application_button and len(visited) > 1):
            break
    assert len(visited) > 1
    assert hidden not in visited


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


def _timeline_snapshot():
    fingerprint = VideoFingerprint(1024, 123, 'responsive-timeline')
    frame_ref = VideoFrameRef(fingerprint, 0, 3400, 1, 1000)
    image = QImage(96, 64, QImage.Format_RGB32)
    byte_size = (image.sizeInBytes() if hasattr(image, 'sizeInBytes')
                 else image.byteCount())
    first = VideoFrameResult(
        frame_ref, image, 96, 64, 96, 64, 0,
        byte_size, 'responsive-timeline:0:3400')
    return VideoSessionSnapshot(
        'responsive-timeline.mp4', None, fingerprint, 0, 1, 1000,
        96, 64, 0, 'fixture', 10_000, 900, 12, 1, 0, first)


def _window_rect(widget, window):
    return QRect(widget.mapTo(window, QPoint(0, 0)), widget.size())


@pytest.mark.parametrize('size', _SIZES)
def test_video_transport_projects_essential_controls_without_overlap(
        window, size):
    """MainWindow keeps the active video transport reachable at every size."""
    window._set_document_kind(DocumentKind.VIDEO)
    timeline = window.video_timeline
    timeline.set_session(_timeline_snapshot())
    timeline.set_markers(accepted=(3400,), pending=(5000,))
    _show(window, size, 'canvas')

    controls = (
        timeline.previous_button, timeline.play_button, timeline.next_button,
        timeline.slider, timeline.time_edit, timeline.speed_combo,
        timeline.track_button, timeline.legend_button,
    )
    rectangles = []
    for control in controls:
        assert control.isVisibleTo(window), control.accessibleName()
        rect = _window_rect(control, window)
        assert window.rect().contains(rect), control.accessibleName()
        assert _window_rect(timeline, window).contains(rect), (
            control.accessibleName())
        rectangles.append((control.accessibleName(), rect))

    for index, (name, rect) in enumerate(rectangles):
        for other_name, other_rect in rectangles[index + 1:]:
            assert not rect.intersects(other_rect), '%s overlaps %s' % (
                name, other_name)


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
