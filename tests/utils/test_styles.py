import sys
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication

from libs.utils import dpi
from libs.utils.styles import (
    hex_to_qcolor, get_canvas_background, get_theme_colors,
    get_design_tokens, get_command_bar_style,
    get_toolbar_style, get_main_window_style, get_slider_style,
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


def _relative_luminance(hex_color):
    channels = []
    for offset in (1, 3, 5):
        value = int(hex_color[offset:offset + 2], 16) / 255.0
        channels.append(
            value / 12.92 if value <= 0.03928
            else ((value + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast_ratio(foreground, background):
    light = _relative_luminance(foreground)
    dark = _relative_luminance(background)
    if light < dark:
        light, dark = dark, light
    return (light + 0.05) / (dark + 0.05)


def test_text_on_its_own_surface_meets_wcag_aa():
    """Body-text token pairs must clear 4.5:1 in both palettes.

    Dark accent_text sat at 3.32:1 on accent_light, which covered every
    selected row, highlighted menu entry and selected gallery caption.
    """
    pairs = (
        ('text', 'background'),
        ('text', 'surface'),
        ('accent_text', 'accent_light'),
    )
    for palette_name, palette in (
            ('light', LIGHT_COLORS), ('dark', DARK_COLORS)):
        for foreground, background in pairs:
            ratio = _contrast_ratio(palette[foreground], palette[background])
            assert ratio >= 4.5, (
                '%s %s on %s is %.2f:1' % (
                    palette_name, foreground, background, ratio))


def test_workspace_tokens_cover_interaction_and_status_states():
    for theme in (Theme.LIGHT, Theme.DARK):
        tokens = get_design_tokens(theme)
        colors = tokens['color']
        assert {'space', 'radius', 'type'} <= set(tokens)
        assert {
            'hover', 'pressed', 'focus', 'text_disabled',
            'status_success', 'status_warning', 'status_error', 'status_info',
        } <= set(colors)
        css = get_command_bar_style(theme)
        assert colors['focus'] in css
        assert colors['text_disabled'] in css

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


def _at_2x():
    return patch.object(dpi, 'get_dpi_scale_factor', return_value=2.0)


def test_toolbar_style_scales_px_at_2x():
    with _at_2x():
        css = get_toolbar_style(Theme.LIGHT)
    assert 'height: 40px' in css        # was 20px
    assert 'border-right: 2px' in css   # 1px hairline scaled too


def test_command_bar_style_scales_controls_at_2x():
    with _at_2x():
        css = get_command_bar_style(Theme.LIGHT)
    assert 'min-height: 60px' in css
    assert 'border-bottom: 2px' in css


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


def test_track_state_colours_exist_in_both_palettes():
    """Palette parity: all four track keys must exist in light and dark."""
    keys = ('track_anchor', 'track_interpolated',
            'track_pending', 'track_absent')
    for key in keys:
        assert key in LIGHT_COLORS, key
        assert key in DARK_COLORS, key


def test_track_state_colours_stand_out_and_absent_recedes():
    """The three states must be visible; absent must not compete with them.

    anchor/interpolated/pending are state colours and must stand out.
    absent marks the absence of tracking and must recede into the surface.
    """
    for palette, palette_name in ((LIGHT_COLORS, 'light'),
                                   (DARK_COLORS, 'dark')):
        surface = palette['surface']
        # Three state colours must exceed 1.9:1 contrast against surface
        for key in ('track_anchor', 'track_interpolated', 'track_pending'):
            ratio = _contrast_ratio(palette[key], surface)
            assert ratio > 1.9, (
                f'{palette_name} {key}: {ratio:.2f}:1 (need > 1.9:1)')
        # track_absent must stay subdued: below 2.0:1 to recede
        ratio = _contrast_ratio(palette['track_absent'], surface)
        assert ratio < 2.0, (
            f'{palette_name} track_absent: {ratio:.2f}:1 (need < 2.0:1 to recede)')


if __name__ == '__main__':
    test_hex_to_qcolor()
