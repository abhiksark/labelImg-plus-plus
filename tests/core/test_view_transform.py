"""Behavior tests for authoritative canvas view transforms."""

from libs.core.view_transform import ViewMode, ViewTransform


def test_fit_mode_reprojects_but_manual_zoom_survives_navigation():
    """Fit follows a new canvas while explicit manual zoom stays fixed."""
    state = ViewTransform()
    state.choose_fit_window()

    assert state.project((800, 600), (1600, 1200)).percent == 50
    assert state.project((600, 600), (1600, 1200)).percent == 37

    state.choose_manual(125)
    assert state.project((600, 600), (900, 900)).percent == 125
    assert state.mode is ViewMode.MANUAL
