# tests/utils/test_window_geometry.py
"""Screen-relative default size and on-screen clamping for the main window."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QPoint, QRect, QSize  # noqa: E402

from libs.utils import dpi  # noqa: E402
from libs.utils.window_geometry import (  # noqa: E402
    MAX_DEFAULT_HEIGHT, MAX_DEFAULT_WIDTH, MIN_DEFAULT_HEIGHT,
    MIN_DEFAULT_WIDTH, default_window_size, fit_to_available,
)

LAPTOP = QRect(0, 0, 1366, 768)
DESKTOP = QRect(0, 0, 1920, 1080)
UHD = QRect(0, 0, 3840, 2160)
TINY = QRect(0, 0, 800, 600)


def _unscaled(monkeypatch):
    """Pin the DPI factor so the floor/cap constants are exact."""
    monkeypatch.setattr(dpi, 'get_dpi_scale_factor', lambda: 1.0)


def test_default_never_exceeds_the_screen(monkeypatch):
    _unscaled(monkeypatch)
    for available in (TINY, LAPTOP, DESKTOP, UHD):
        size = default_window_size(available)
        assert size.width() <= available.width()
        assert size.height() <= available.height()


def test_default_is_far_larger_than_the_old_fixed_600x500(monkeypatch):
    _unscaled(monkeypatch)
    size = default_window_size(DESKTOP)
    assert size.width() > 600 and size.height() > 500
    # 80% of 1920x1080 is 1536x864, both inside the cap.
    assert size == QSize(1536, 864)


def test_default_is_capped_on_a_very_large_screen(monkeypatch):
    _unscaled(monkeypatch)
    size = default_window_size(UHD)
    assert size == QSize(MAX_DEFAULT_WIDTH, MAX_DEFAULT_HEIGHT)


def test_default_floor_yields_to_a_small_screen(monkeypatch):
    _unscaled(monkeypatch)
    size = default_window_size(TINY)
    # The floor is larger than this screen, so the screen wins outright.
    assert MIN_DEFAULT_WIDTH > TINY.width()
    assert size.width() <= TINY.width()
    assert size.height() <= TINY.height()


def test_default_cap_tracks_the_dpi_factor(monkeypatch):
    # A screen wide enough that the cap binds at both factors, so the two
    # results differ only by the DPI scaling of the cap itself.
    huge = QRect(0, 0, 6000, 4000)

    _unscaled(monkeypatch)
    assert default_window_size(huge) == QSize(MAX_DEFAULT_WIDTH,
                                              MAX_DEFAULT_HEIGHT)

    monkeypatch.setattr(dpi, 'get_dpi_scale_factor', lambda: 2.0)
    assert default_window_size(huge) == QSize(MAX_DEFAULT_WIDTH * 2,
                                              MAX_DEFAULT_HEIGHT * 2)


def test_oversized_restore_is_shrunk_to_the_current_screen(monkeypatch):
    _unscaled(monkeypatch)
    size, position = fit_to_available(LAPTOP, QSize(3840, 2160), QPoint(0, 0))
    assert size == QSize(1366, 768)
    assert LAPTOP.contains(QRect(position, size))


def test_offscreen_position_is_pulled_back_into_view(monkeypatch):
    _unscaled(monkeypatch)
    # Top-left one pixel inside the screen passed the old point-only check
    # while the whole window body hung off it.
    size, position = fit_to_available(
        DESKTOP, QSize(1200, 800), QPoint(1900, 1050))
    assert DESKTOP.contains(QRect(position, size))
    assert position == QPoint(1920 - 1200, 1080 - 800)


def test_a_geometry_that_already_fits_is_left_alone(monkeypatch):
    _unscaled(monkeypatch)
    size, position = fit_to_available(
        DESKTOP, QSize(1200, 800), QPoint(100, 50))
    assert size == QSize(1200, 800)
    assert position == QPoint(100, 50)


def test_corrupt_settings_values_fall_back_instead_of_reaching_resize(
        monkeypatch):
    _unscaled(monkeypatch)
    size, position = fit_to_available(DESKTOP, 'not-a-size', {'x': 1})
    assert size == default_window_size(DESKTOP)
    assert DESKTOP.contains(QRect(position, size))


def test_missing_screen_still_returns_something_usable(monkeypatch):
    _unscaled(monkeypatch)
    size = default_window_size(QRect())
    assert size == QSize(MIN_DEFAULT_WIDTH, MIN_DEFAULT_HEIGHT)
    fallback, _position = fit_to_available(QRect(), QSize(400, 300),
                                           QPoint(0, 0))
    assert fallback == QSize(MIN_DEFAULT_WIDTH, MIN_DEFAULT_HEIGHT)
