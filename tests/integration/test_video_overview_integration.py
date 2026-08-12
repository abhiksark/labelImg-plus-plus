# tests/integration/test_video_overview_integration.py
"""The browse slot follows the document kind.

One slot, one shortcut, one button: what it shows is decided by the document
that is open, never by a second user-facing toggle. An image directory browses
as the gallery, a video browses as the overview, and switching document while
the slot is open re-routes it rather than stranding the previous document's
surface on screen.

Deliberately free of the ``[video]`` extra: these tests set ``document_kind``
directly, so they run in the base CI job where ``av`` is absent. Behaviour that
needs a real clip lives in ``tests/video/test_opening.py``.
"""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication

from labelImgPlusPlus import MainWindow
from libs.core.video_types import DocumentKind
from libs.utils.styles import Theme, get_theme_colors


def _window(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    return MainWindow(default_save_dir=str(tmp_path))


def _close(window):
    window.dirty = False
    window.close()
    QApplication.processEvents()


def test_browse_slot_shows_the_overview_for_video(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.document_kind = DocumentKind.VIDEO
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'overview'
        assert window.gallery_mode_enabled
    finally:
        _close(window)


def test_browse_slot_shows_the_gallery_for_images(monkeypatch, tmp_path):
    window = _window(monkeypatch, tmp_path)
    try:
        window.document_kind = DocumentKind.IMAGE
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'gallery'
    finally:
        _close(window)


def test_leaving_the_browse_slot_returns_to_the_canvas_for_video(
        monkeypatch, tmp_path):
    """The overview is a page of the browse slot, not a video mode."""
    window = _window(monkeypatch, tmp_path)
    try:
        window.document_kind = DocumentKind.VIDEO
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'overview'
        window.toggle_gallery_mode(False)
        assert window.workspace_pages.current_page() == 'canvas'
        assert not window.gallery_mode_enabled
    finally:
        _close(window)


def test_browse_slot_re_routes_when_the_document_kind_changes(
        monkeypatch, tmp_path):
    """Opening the other kind of document must not strand the old surface.

    Both directions matter: a video opened while browsing images has to reach
    the overview, and an image directory opened while browsing a video has to
    leave it -- otherwise the image dataset is browsed as a video's tracks.
    """
    window = _window(monkeypatch, tmp_path)
    try:
        window._set_document_kind(DocumentKind.IMAGE)
        window.toggle_gallery_mode(True)
        assert window.workspace_pages.current_page() == 'gallery'

        window._set_document_kind(DocumentKind.VIDEO)
        assert window.workspace_pages.current_page() == 'overview'

        window._set_document_kind(DocumentKind.IMAGE)
        assert window.workspace_pages.current_page() == 'gallery'
    finally:
        _close(window)


def test_document_kind_change_leaves_the_canvas_alone_when_not_browsing(
        monkeypatch, tmp_path):
    """Routing is the browse slot's business; the canvas keeps the canvas."""
    window = _window(monkeypatch, tmp_path)
    try:
        window._set_document_kind(DocumentKind.VIDEO)
        assert window.workspace_pages.current_page() == 'canvas'
        window._set_document_kind(DocumentKind.NONE)
        assert window.workspace_pages.current_page() == 'empty'
    finally:
        _close(window)


def test_the_browse_action_stays_enabled_and_checked_for_video(
        monkeypatch, tmp_path):
    """4.0.0rc0 disabled it and forced it off; the overview makes it real."""
    window = _window(monkeypatch, tmp_path)
    try:
        window.toggle_gallery_mode(True)
        window.actions.galleryMode.setChecked(True)
        window._set_document_kind(DocumentKind.VIDEO)
        assert window.actions.galleryMode.isEnabled()
        assert window.actions.galleryMode.isChecked()
        assert window.gallery_mode_enabled
    finally:
        _close(window)


def test_dark_theme_reaches_both_overview_children(monkeypatch, tmp_path):
    """The host themes the container; the container forwards to both views.

    ``VideoFramesView`` and ``VideoLanesView`` both construct with
    ``Theme.LIGHT``, so a missing registration or a missing forward leaves a
    white panel in dark mode with no error to notice.
    """
    window = _window(monkeypatch, tmp_path)
    try:
        overview = window.workspace_pages.video_overview
        light = get_theme_colors(Theme.LIGHT)['surface']
        dark = get_theme_colors(Theme.DARK)['surface']
        assert light != dark

        window._apply_theme(Theme.DARK)
        assert dark in overview.styleSheet()
        assert dark in overview.lanes.styleSheet()
        assert dark in overview.frames.styleSheet()

        window._apply_theme(Theme.LIGHT)
        assert light in overview.lanes.styleSheet()
        assert light in overview.frames.styleSheet()
    finally:
        _close(window)
