import sys
from PyQt5.QtWidgets import QApplication
from libs.utils.styles import (
    hex_to_qcolor, get_canvas_background, get_theme_colors,
    LIGHT_COLORS, DARK_COLORS, Theme,
)

app = QApplication.instance() or QApplication(sys.argv)


def test_canvas_background_comes_from_palette():
    # The canvas background must be sourced from the palette, not a literal.
    for theme in (Theme.LIGHT, Theme.DARK):
        assert get_canvas_background(theme) == get_theme_colors(theme)['canvas_bg']


def test_palette_keys_match():
    # theme-audit invariant: light and dark palettes have identical keys.
    assert set(LIGHT_COLORS) == set(DARK_COLORS)

def test_hex_to_qcolor():
    # Test with # prefix
    color1 = hex_to_qcolor('#ff0000')
    assert color1.red() == 255
    assert color1.green() == 0
    assert color1.blue() == 0
    assert color1.alpha() == 255

    # Test without # prefix
    color2 = hex_to_qcolor('00ff00')
    assert color2.red() == 0
    assert color2.green() == 255
    assert color2.blue() == 0

    # Test with alpha
    color3 = hex_to_qcolor('#0000ff', alpha=128)
    assert color3.alpha() == 128

    print("PASS: hex_to_qcolor tests")


# --- HiDPI stylesheet scaling (issue #66) ---

from unittest.mock import patch
from libs.utils import dpi
from libs.utils.styles import (
    get_toolbar_style, get_main_window_style, get_slider_style,
)


def _at_2x():
    return patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0)


def test_toolbar_style_scales_px_at_2x():
    with _at_2x():
        css = get_toolbar_style(Theme.LIGHT)
    assert 'height: 40px' in css        # was 20px
    assert 'border-right: 2px' in css   # 1px hairline scaled too


def test_toolbar_style_unchanged_at_1x():
    with patch.object(dpi, 'get_dpi_scale_factor', return_value=1.0):
        css = get_toolbar_style(Theme.LIGHT)
    assert 'height: 20px' in css
    assert 'border-right: 1px' in css


def test_main_window_style_scales_min_width_at_2x():
    with _at_2x():
        css = get_main_window_style(Theme.LIGHT)
    assert 'min-width: 40px' in css     # was 20px


def test_slider_style_scales_negative_margin_at_2x():
    with _at_2x():
        css = get_slider_style(Theme.LIGHT)
    assert 'margin: -10px 0' in css     # was -5px 0


if __name__ == '__main__':
    test_hex_to_qcolor()
