# tests/widgets/test_canvas_theme.py
import sys
from unittest.mock import MagicMock
from PyQt5.QtGui import QPainterPath
from PyQt5.QtWidgets import QApplication
from libs.core.shape import Shape
from libs.widgets.canvas import Canvas
from libs.utils.styles import Theme, get_theme_colors, hex_to_qcolor

app = QApplication.instance() or QApplication(sys.argv)

def test_canvas_theme_colors():
    """Test canvas respects theme for verified background."""
    canvas = Canvas()

    # Test light theme
    canvas.set_theme(Theme.LIGHT)
    assert canvas._theme == Theme.LIGHT

    # Test dark theme
    canvas.set_theme(Theme.DARK)
    assert canvas._theme == Theme.DARK


def test_canvas_theme_sets_shape_contrast_halo():
    canvas = Canvas()
    canvas.set_theme(Theme.DARK)
    expected = hex_to_qcolor(
        get_theme_colors(Theme.DARK)['text'], alpha=150)
    assert Shape.contrast_line_color == expected


def test_unselected_shape_draws_contrast_understroke():
    shape = Shape()
    shape.selected = False
    painter = MagicMock()
    line_path = QPainterPath()
    vertex_path = QPainterPath()

    shape._draw_shape(painter, line_path, vertex_path)

    assert painter.setPen.call_count == 2
    assert painter.setPen.call_args_list[0].args[0].width() >= 3
    assert [call.args[0] for call in painter.drawPath.call_args_list] == [
        line_path, line_path, vertex_path]

if __name__ == '__main__':
    test_canvas_theme_colors()
    print("PASS: Canvas theme test")
