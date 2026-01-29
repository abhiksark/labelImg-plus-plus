# Extension Guide

Overview of extension points in labelImg++ for developers who want to customize or extend functionality.

## Extension Points Overview

```
+----------------------------------------------------------+
|                    Extension Points                       |
+----------------------------------------------------------+
|                                                          |
|  +------------------+    +------------------+             |
|  | Annotation       |    | User Interface   |             |
|  | Formats          |    | Actions          |             |
|  +------------------+    +------------------+             |
|         |                        |                       |
|         v                        v                       |
|  +--------------+         +--------------+               |
|  | *_io.py      |         | labelImgPlusPlus.py  |               |
|  | LabelFile    |         | new_action() |               |
|  +--------------+         +--------------+               |
|                                                          |
|  +------------------+    +------------------+             |
|  | Internationa-   |    | Drawing Tools    |             |
|  | lization        |    | & Shapes         |             |
|  +------------------+    +------------------+             |
|         |                        |                       |
|         v                        v                       |
|  +--------------+         +--------------+               |
|  | strings/     |         | canvas.py    |               |
|  | StringBundle |         | shape.py     |               |
|  +--------------+         +--------------+               |
|                                                          |
+----------------------------------------------------------+
```

## Quick Reference

| Extension Type | Files to Modify | Guide |
|----------------|-----------------|-------|
| New annotation format | `libs/*_io.py`, `libs/labelFile.py`, `labelImgPlusPlus.py` | [Adding Formats](adding-formats.md) |
| New action/feature | `labelImgPlusPlus.py`, `resources/strings/` | [Adding Features](adding-features.md) |
| New language | `resources/strings/strings-XX.properties` | [i18n Guide](i18n-guide.md) |
| Custom shape types | `libs/shape.py`, `libs/canvas.py` | See below |

## Architecture Patterns

### Signal-Slot Pattern

labelImg++ uses PyQt5's signal-slot mechanism for component communication:

```python
# Canvas emits signals
class Canvas(QWidget):
    newShape = pyqtSignal()
    selectionChanged = pyqtSignal(bool)
    shapeMoved = pyqtSignal()

# MainWindow connects handlers
self.canvas.newShape.connect(self.new_shape)
self.canvas.selectionChanged.connect(self.shape_selection_changed)
```

**Extension Pattern:**
1. Define signal in component class
2. Emit signal at appropriate event
3. Connect handler in MainWindow

### Action Factory Pattern

Actions are created using `new_action()` helper:

```python
# libs/toolBar.py
def new_action(parent, text, slot=None, shortcut=None, icon=None,
               tip=None, checkable=False, enabled=True):
    """Create a QAction with consistent configuration."""
    a = QAction(text, parent)
    if icon:
        a.setIconVisually(new_icon(icon))
    if shortcut:
        a.setShortcut(shortcut)
    if tip:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    a.setEnabled(enabled)
    return a
```

**Extension Pattern:**
1. Create action with `action()` (partial of `new_action`)
2. Implement handler method
3. Add to appropriate menu/toolbar

### Format Dispatch Pattern

Format handling uses a dispatch pattern in LabelFile:

```python
class LabelFile:
    def save(self, filename, shapes, ...):
        if self.label_file_format == LabelFileFormat.PASCAL_VOC:
            self.save_pascal_voc_format(...)
        elif self.label_file_format == LabelFileFormat.YOLO:
            self.save_yolo_format(...)
        elif self.label_file_format == LabelFileFormat.CREATE_ML:
            self.save_create_ml_format(...)
```

**Extension Pattern:**
1. Create `libs/new_format_io.py` with Writer/Reader classes
2. Add enum value in `libs/labelFile.py`
3. Add dispatch cases in save/load methods
4. Add format toggle in `labelImgPlusPlus.py`

## Component Dependencies

```
                    labelImgPlusPlus.py (MainWindow)
                           |
          +----------------+----------------+
          |                |                |
          v                v                v
     canvas.py        labelFile.py     settings.py
          |                |
          v                v
      shape.py       *_io.py (formats)
```

### Dependency Rules

1. **libs/** modules should not import `labelImgPlusPlus.py`
2. **canvas.py** owns shapes but doesn't know about file formats
3. **labelFile.py** orchestrates formats but doesn't know about UI
4. **Format I/O** classes are standalone with no Qt dependencies

## Minimal Extension Examples

### Adding a Toolbar Button

```python
# In MainWindow.__init__ (labelImgPlusPlus.py)

# 1. Create action
my_action = action(
    'My Action',           # Display text
    self.my_handler,       # Handler method
    'Ctrl+M',              # Shortcut
    'my-icon',             # Icon name (add to resources/)
    'My action tooltip'    # Tooltip
)

# 2. Add to toolbar
self.tools = self.toolbar('Tools', position='left')
add_actions(self.tools, (open, my_action, save, ...))

# 3. Implement handler
def my_handler(self):
    """Handle my action."""
    print("Action triggered!")
```

### Adding a Menu Item

```python
# In MainWindow.__init__ (labelImgPlusPlus.py)

# 1. Create action (same as toolbar)
my_menu_item = action('Menu Item', self.menu_handler, 'Ctrl+Shift+M')

# 2. Add to menu
self.menus = struct(
    file=self.menu(get_str('menu_file')),
    edit=self.menu(get_str('menu_edit')),
    view=self.menu(get_str('menu_view')),
    help=self.menu(get_str('menu_help'))
)
add_actions(self.menus.edit, (my_menu_item, None, ...))  # None = separator
```

### Adding a Setting

```python
# 1. Add constant (libs/constants.py)
SETTING_MY_OPTION = 'myOption'

# 2. Read in __init__ (labelImgPlusPlus.py)
self.my_option = settings.get(SETTING_MY_OPTION, False)

# 3. Save in closeEvent (labelImgPlusPlus.py)
settings[SETTING_MY_OPTION] = self.my_option

# 4. Create toggle action if needed
my_option_action = action(
    'My Option',
    self.toggle_my_option,
    checkable=True
)
my_option_action.setChecked(self.my_option)
```

## Testing Extensions

### Manual Testing Workflow

1. Make code changes
2. Run: `python labelImgPlusPlus.py`
3. Test with sample images
4. Verify annotation save/load

### Testing Formats

```python
# Quick format test
from libs.my_format_io import MyFormatWriter, MyFormatReader

# Test write
writer = MyFormatWriter('images', 'test.jpg', (600, 800, 3))
writer.add_bnd_box(100, 150, 400, 450, 'cat', False)
writer.save(target_file='test.myformat')

# Test read
reader = MyFormatReader('test.myformat', image)
shapes = reader.get_shapes()
assert len(shapes) == 1
assert shapes[0][0] == 'cat'
```

## Resources

- [Adding Formats Guide](adding-formats.md) - Complete format implementation
- [Adding Features Guide](adding-features.md) - UI and action implementation
- [i18n Guide](i18n-guide.md) - Adding translations
- [Architecture Overview](../architecture.md) - System design
