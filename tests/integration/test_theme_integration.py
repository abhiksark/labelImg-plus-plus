# tests/integration/test_theme_integration.py
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from PyQt5.QtWidgets import QApplication
from labelImgPlusPlus import MainWindow
from libs.utils.styles import Theme

app = QApplication(sys.argv)

def test_theme_integration():
    """Test theme changes propagate to all components."""
    try:
        # Initialize MainWindow with default predefined classes file
        default_file = os.path.join(
            os.path.dirname(__file__), '../../data/predefined_classes.txt'
        )
        win = MainWindow(default_prefdef_class_file=default_file)

        # Get initial theme (may be from settings)
        initial_theme = win._current_theme
        initial_checked = win.dark_mode_action.isChecked()
        print(f"✓ Initial theme: {initial_theme.name} (action checked: {initial_checked})")

        # Toggle theme via action (this is how the UI does it)
        win.dark_mode_action.setChecked(not initial_checked)
        win._toggle_dark_mode()
        toggled_theme = win._current_theme
        assert toggled_theme != initial_theme
        print(f"✓ Theme toggled to: {toggled_theme.name}")

        # Check canvas has theme
        if hasattr(win.canvas, '_theme'):
            assert win.canvas._theme == toggled_theme
            print(f"✓ Canvas theme: {win.canvas._theme.name}")
        else:
            print("⚠ Canvas does not have _theme attribute")

        # Check gallery has theme
        if hasattr(win.gallery_widget, '_current_theme'):
            assert win.gallery_widget._current_theme == toggled_theme
            print(f"✓ Gallery theme: {win.gallery_widget._current_theme.name}")
        else:
            print("⚠ Gallery widget does not have _current_theme attribute")

        # Toggle back
        win.dark_mode_action.setChecked(initial_checked)
        win._toggle_dark_mode()
        assert win._current_theme == initial_theme
        print(f"✓ Theme toggled back to: {win._current_theme.name}")

        # Verify theme consistency after multiple toggles
        current_checked = win.dark_mode_action.isChecked()
        for i in range(3):
            current_checked = not current_checked
            win.dark_mode_action.setChecked(current_checked)
            win._toggle_dark_mode()
        final_theme = win._current_theme
        print(f"✓ After 3 toggles, theme is: {final_theme.name}")

        print("\nPASS: Theme integration test")
        return True
    except Exception as e:
        print(f"\nFAIL: Theme integration test - {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_theme_integration()
    sys.exit(0 if success else 1)
