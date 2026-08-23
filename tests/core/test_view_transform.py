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


def test_fit_window_never_rounds_up_past_the_viewport():
    """A whole-percent fit projection must leave the entire image visible."""
    state = ViewTransform()
    state.choose_fit_window()

    projection = state.project((812, 612), (1600, 1200))

    assert projection.percent == 50
    assert 1600 * projection.percent <= 81200
    assert 1200 * projection.percent <= 61200


def test_fit_width_never_rounds_up_past_the_viewport():
    """Fit-width uses the same non-clipping integer percentage contract."""
    state = ViewTransform()
    state.choose_fit_width()

    projection = state.project((812, 612), (1600, 1200))

    assert projection.percent == 50
    assert 1600 * projection.percent <= 81200


def test_start_session_returns_manual_zoom_to_fit_window():
    """A new document session discards an explicit zoom selection."""
    state = ViewTransform()
    state.choose_manual(125)

    state.start_session()

    assert state.mode is ViewMode.FIT_WINDOW
    assert state.project((800, 600), (1600, 1200)).percent == 50
