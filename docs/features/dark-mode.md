# Dark Mode Theme

## Overview

labelImg++ supports both light and dark themes, providing a comfortable annotation experience in any lighting condition. The dark theme is designed to reduce eye strain during extended annotation sessions and integrates seamlessly with modern dark-themed desktop environments.

## User Guide

### Enabling Dark Mode

There are two ways to toggle dark mode:

1. **Keyboard Shortcut:** Press `Ctrl+D` to instantly switch between light and dark themes
2. **Menu Option:** Navigate to `View > Dark Mode` and click to toggle

The theme preference is automatically saved and will persist across application restarts.

### Screenshots

**Light Mode**
![Light Mode Interface](../screenshots/light-mode.png)
*The classic light theme with high contrast and clear visibility*

**Dark Mode**
![Dark Mode Interface](../screenshots/dark-mode.png)
*The modern dark theme reducing eye strain in low-light environments*

### Visual Differences

The dark theme features:

- **Background:** Deep gray (#1e1e1e) instead of white
- **UI Elements:** Darker surfaces with softer borders
- **Text:** Light gray (#e0e0e0) for optimal readability
- **Canvas:** Medium gray background (#2d2d2d) for better image visibility
- **Accent Colors:** Adjusted for proper contrast on dark backgrounds
- **Status Colors:** Tuned for visibility (green, orange, blue status indicators)

### Theme-Aware Components

All UI components respect the active theme:

- Main window and toolbars
- Canvas and annotation overlays
- Gallery thumbnails and status borders
- Dialogs (label selection, file operations)
- Menus and context menus
- Scroll bars and sliders
- Status bar indicators

## Developer Guide

### Architecture

The theme system is centralized in `/libs/utils/styles.py` and uses a palette-based approach for consistent theming across all components.

#### Theme Enum

```python
from libs.utils.styles import Theme

class Theme(Enum):
    LIGHT = 'light'
    DARK = 'dark'
```

#### Color Palettes

Two complete color palettes are defined:

- `LIGHT_COLORS`: Dictionary with 25+ semantic color keys
- `DARK_COLORS`: Parallel dictionary with dark theme equivalents

**Key Colors:**
- `background`: Main window background
- `surface`: Elevated UI elements (toolbars, menus)
- `border`: Dividers and control borders
- `text`: Primary text color
- `text_secondary`: Less prominent text
- `accent`: Interactive elements and highlights
- `hover`/`pressed`: Button state colors
- Status colors: `status_saved`, `status_unsaved`, etc.

### Applying Themes to Components

#### 1. Main Window Stylesheet

The main window applies themes using the centralized stylesheet generator:

```python
from libs.utils.styles import get_stylesheet, Theme

# In MainWindow.__init__
self._current_theme = Theme.DARK if settings.get(SETTING_DARK_MODE, False) else Theme.LIGHT
self._apply_theme(self._current_theme)

def _apply_theme(self, theme):
    """Apply the given theme to all components."""
    # Apply main stylesheet
    self.setStyleSheet(get_stylesheet(theme))

    # Update all child components...
```

#### 2. Canvas Background

The canvas uses a direct background color setter:

```python
from libs.utils.styles import get_canvas_background

# In canvas
bg_color = get_canvas_background(theme)
self.canvas.set_background_color(bg_color)
```

#### 3. Custom Component Styling

For components with specialized styling needs:

```python
from libs.utils.styles import get_theme_colors

def apply_theme(self, theme):
    """Apply theme to this widget."""
    colors = get_theme_colors(theme)

    # Use semantic color names
    self.setStyleSheet(f"""
        QWidget {{
            background-color: {colors['background']};
            color: {colors['text']};
        }}
        QPushButton:hover {{
            background-color: {colors['hover']};
        }}
    """)
```

#### 4. Gallery Widget Example

The gallery widget demonstrates comprehensive theme integration:

```python
def apply_theme(self, theme):
    """Apply theme to gallery components."""
    from libs.utils.styles import (
        get_gallery_list_style,
        get_gallery_controls_style,
        get_slider_style,
        get_theme_colors
    )

    colors = get_theme_colors(theme)

    # List widget
    self.icon_list.setStyleSheet(get_gallery_list_style(theme))

    # Control buttons
    control_styles = get_gallery_controls_style(theme)
    self.slider_frame.setStyleSheet(control_styles['frame'])

    # Update item backgrounds and placeholders
    self._update_gallery_item_backgrounds(colors)
```

### Adding New Style Functions

When creating new components that need theming:

1. **Define color keys** in both `LIGHT_COLORS` and `DARK_COLORS` dictionaries
2. **Create style generator** function in `styles.py`:

```python
def get_my_component_style(theme: Theme) -> str:
    """Generate stylesheet for MyComponent."""
    c = _get_colors(theme)  # Get palette for theme
    return f"""
    MyComponent {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        color: {c['text']};
    }}
    MyComponent:hover {{
        background: {c['hover']};
    }}
    """
```

3. **Implement `apply_theme()` method** in your component:

```python
class MyComponent(QWidget):
    def apply_theme(self, theme):
        """Apply theme to this component."""
        self.setStyleSheet(get_my_component_style(theme))
```

4. **Call from MainWindow._apply_theme()** to propagate theme changes:

```python
def _apply_theme(self, theme):
    # ... existing code ...

    if hasattr(self, 'my_component') and self.my_component:
        if hasattr(self.my_component, 'apply_theme'):
            self.my_component.apply_theme(theme)
```

### Helper Functions

#### `hex_to_qcolor()`

Convert hex color strings to QColor objects for drawing operations:

```python
from libs.utils.styles import hex_to_qcolor

# With alpha transparency
color = hex_to_qcolor('#ff0000', alpha=128)  # Semi-transparent red
painter.setBrush(QBrush(color))
```

#### `get_theme_colors()`

Access the full color palette for a theme:

```python
from libs.utils.styles import get_theme_colors, Theme

colors = get_theme_colors(Theme.DARK)
background = colors['background']  # '#1e1e1e'
text = colors['text']              # '#e0e0e0'
```

### Style Guidelines

When implementing theme support:

1. **Use semantic color names** from the palette (e.g., `'accent'` not `'blue'`)
2. **Avoid hardcoded colors** - always reference palette
3. **Test both themes** - ensure proper contrast and visibility
4. **Consider state changes** - hover, pressed, disabled states
5. **Update related components** - modals, tooltips, child widgets

### Theme Persistence

The theme preference is stored in user settings:

```python
from libs.utils.constants import SETTING_DARK_MODE

# Saving theme preference
settings[SETTING_DARK_MODE] = self.dark_mode_action.isChecked()
settings.save()

# Loading theme preference
is_dark = settings.get(SETTING_DARK_MODE, False)
self._current_theme = Theme.DARK if is_dark else Theme.LIGHT
```

### Testing Theme Changes

#### Manual Testing

See [theme-testing.md](../testing/theme-testing.md) for comprehensive manual testing checklist.

Key areas to verify:
- Theme toggle works immediately without restart
- All UI components update correctly
- Text remains readable in both themes
- Status colors remain distinguishable
- Dialogs and menus respect theme

#### Automated Testing

Theme integration tests are located in `tests/test_theme_integration.py`:

```bash
# Run all theme tests
python3 -m pytest tests/ -k theme -v

# Run specific test
python3 -m pytest tests/test_theme_integration.py::TestThemeIntegration::test_theme_toggle -v
```

Key tests:
- Theme toggle functionality
- Component stylesheet updates
- Color palette consistency
- Theme persistence across sessions

### Common Issues and Solutions

#### Issue: Component not updating when theme changes

**Solution:** Ensure the component implements `apply_theme()` and is called from `MainWindow._apply_theme()`:

```python
# In component
def apply_theme(self, theme):
    self.setStyleSheet(get_my_style(theme))
    self.update()  # Force repaint if needed

# In MainWindow._apply_theme()
if hasattr(self, 'my_component'):
    if hasattr(self.my_component, 'apply_theme'):
        self.my_component.apply_theme(theme)
```

#### Issue: Hardcoded colors overriding theme

**Solution:** Search for hex colors in component code and replace with palette references:

```python
# Bad - hardcoded
self.setStyleSheet("QWidget { background: #ffffff; }")

# Good - theme-aware
colors = get_theme_colors(theme)
self.setStyleSheet(f"QWidget {{ background: {colors['background']}; }}")
```

#### Issue: Child widgets inheriting wrong styles

**Solution:** Set explicit stylesheets on child widgets or use `setStyleSheet()` with proper selectors:

```python
# Isolate child widget styling
child_widget.setStyleSheet(get_specific_style(theme))

# Or use specific selector
parent.setStyleSheet(f"""
    QWidget#parent {{ background: {colors['background']}; }}
    QWidget#parent > QLabel {{ color: {colors['text']}; }}
""")
```

### File Locations

Key files for theme implementation:

```
libs/utils/styles.py              # Theme system and color palettes
libs/utils/constants.py           # SETTING_DARK_MODE constant
labelImgPlusPlus.py              # MainWindow._apply_theme() and toggle
libs/widgets/galleryWidget.py    # Gallery theme integration
libs/widgets/canvas.py           # Canvas theme integration
tests/test_theme_integration.py  # Theme automated tests
docs/testing/theme-testing.md    # Manual testing checklist
```

## Future Enhancements

Potential improvements for the theme system:

- **Custom Themes:** Allow users to define custom color palettes
- **System Theme Detection:** Auto-detect OS dark mode preference
- **Per-Component Overrides:** Let users customize individual component colors
- **High Contrast Mode:** Alternative palette for accessibility
- **Theme Preview:** Show theme comparison before switching

## Related Documentation

- [Architecture Overview](../architecture.md) - Overall application structure
- [Adding Features](../guides/adding-features.md) - How to add new UI features
- [Theme Testing Guide](../testing/theme-testing.md) - Manual testing checklist

## Questions?

For issues or questions about dark mode:
- File an issue: https://github.com/abhiksark/labelImg-plus-plus/issues
- Check existing issues with label `theme` or `dark-mode`
