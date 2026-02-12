# tests/widgets/test_canvas_theme.py
import sys
from PyQt5.QtWidgets import QApplication
from libs.widgets.canvas import Canvas
from libs.utils.styles import Theme

app = QApplication(sys.argv)

def test_canvas_theme_colors():
    """Test canvas respects theme for verified background."""
    canvas = Canvas()

    # Test light theme
    canvas.set_theme(Theme.LIGHT)
    assert canvas._theme == Theme.LIGHT

    # Test dark theme
    canvas.set_theme(Theme.DARK)
    assert canvas._theme == Theme.DARK

if __name__ == '__main__':
    test_canvas_theme_colors()
    print("PASS: Canvas theme test")
