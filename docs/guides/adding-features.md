# Adding New Features

Step-by-step guide for adding new actions, tools, and features to labelImg++.

## Overview

Features in labelImg++ are implemented as **actions** - QAction objects that connect UI elements (menus, toolbars, shortcuts) to handler methods.

```
+----------------------------------------------------------+
|                    Feature Architecture                   |
+----------------------------------------------------------+
|                                                          |
|  +------------+     +------------+     +------------+    |
|  |   Menu     |     |  Toolbar   |     | Shortcut   |    |
|  +------------+     +------------+     +------------+    |
|        |                  |                  |           |
|        +--------+---------+--------+---------+           |
|                 |                  |                     |
|                 v                  v                     |
|          +------------+     +------------+               |
|          |  QAction   |     |  QAction   |               |
|          +------------+     +------------+               |
|                 |                  |                     |
|                 v                  v                     |
|          +------------+     +------------+               |
|          |  Handler   |     |  Handler   |               |
|          |  Method    |     |  Method    |               |
|          +------------+     +------------+               |
|                                                          |
+----------------------------------------------------------+
```

## Action Factory

The `new_action()` helper creates configured QAction objects:

**File:** `libs/toolBar.py` (lines 19-48)

```python
def new_action(parent, text, slot=None, shortcut=None, icon=None,
               tip=None, checkable=False, enabled=True):
    """Create a QAction with standard configuration.

    Args:
        parent: Parent widget (usually MainWindow)
        text: Display text for menus/tooltips
        slot: Handler function to connect
        shortcut: Keyboard shortcut string (e.g., 'Ctrl+N')
        icon: Icon name (without extension, from resources/)
        tip: Tooltip and status bar text
        checkable: Whether action is a toggle
        enabled: Initial enabled state

    Returns:
        Configured QAction
    """
    a = QAction(text, parent)
    if icon is not None:
        a.setIconVisually(new_icon(icon))
    if shortcut is not None:
        if isinstance(shortcut, (list, tuple)):
            a.setShortcuts(shortcut)
        else:
            a.setShortcut(shortcut)
    if tip is not None:
        a.setToolTip(tip)
        a.setStatusTip(tip)
    if slot is not None:
        a.triggered.connect(slot)
    if checkable:
        a.setCheckable(True)
    a.setEnabled(enabled)
    return a
```

## Adding a Simple Action

### Step 1: Add String Resources

Edit `resources/strings/strings.properties`:

```properties
myFeature=My Feature
myFeatureDetail=Description of my feature
```

### Step 2: Create the Action

In `labelImg.py` within `MainWindow.__init__()`:

```python
# After line ~216 where other actions are defined
action = partial(new_action, self)

# Create your action
my_feature = action(
    get_str('myFeature'),        # Text from strings
    self.my_feature_handler,     # Handler method
    'Ctrl+Shift+M',              # Keyboard shortcut
    'my-icon',                   # Icon name
    get_str('myFeatureDetail')   # Tooltip
)
```

### Step 3: Implement Handler

Add method to `MainWindow` class:

```python
def my_feature_handler(self):
    """Handle my feature action."""
    # Your implementation here
    print("My feature activated!")

    # Common patterns:

    # Access current image
    if self.file_path:
        print(f"Current file: {self.file_path}")

    # Access shapes
    for shape in self.canvas.shapes:
        print(f"Shape: {shape.label}")

    # Show message
    self.status_bar.showMessage("Feature completed")

    # Mark as dirty (needs save)
    self.set_dirty()
```

### Step 4: Add to Menu

```python
# In MainWindow.__init__(), find the menus section
# Add to appropriate menu
add_actions(self.menus.edit, (
    copy, delete, None,  # None creates separator
    my_feature,          # Add your action
    None,
    ...
))
```

### Step 5: Add to Toolbar (Optional)

```python
# Find toolbar creation section
self.tools = self.toolbar('Tools', position='left')
add_actions(self.tools, (
    open, open_dir, change_save_dir, open_next_image, open_prev_image,
    verify, save, save_format, None,
    my_feature,  # Add here
    None,
    create_mode, edit_mode, ...
))
```

### Step 6: Add Icon (Optional)

1. Create icon: `resources/icons/my-icon.png` (recommended: 24x24 or 32x32)
2. Update `resources.qrc`:

```xml
<qresource prefix="/">
    <file>icons/my-icon.png</file>
</qresource>
```

3. Rebuild resources:

```bash
pyrcc5 -o libs/resources.py resources.qrc
```

## Adding a Toggle Feature

For features that can be enabled/disabled:

### Step 1: Add Setting Constant

Edit `libs/constants.py`:

```python
SETTING_MY_TOGGLE = 'myToggle'
```

### Step 2: Create Checkable Action

```python
# In MainWindow.__init__()
my_toggle = action(
    get_str('myToggle'),
    self.toggle_my_feature,
    'Ctrl+Shift+T',
    'my-toggle-icon',
    get_str('myToggleDetail'),
    checkable=True  # Makes it a toggle
)

# Set initial state from settings
my_toggle.setChecked(settings.get(SETTING_MY_TOGGLE, False))
self.my_toggle_enabled = settings.get(SETTING_MY_TOGGLE, False)
```

### Step 3: Implement Toggle Handler

```python
def toggle_my_feature(self, enabled):
    """Toggle my feature on/off.

    Args:
        enabled: New state (True/False)
    """
    self.my_toggle_enabled = enabled
    if enabled:
        print("Feature enabled")
        # Enable feature logic
    else:
        print("Feature disabled")
        # Disable feature logic
```

### Step 4: Save Setting

In `closeEvent()`:

```python
def closeEvent(self, event):
    # ... existing code ...
    settings[SETTING_MY_TOGGLE] = self.my_toggle_enabled
    settings.save()
```

## Adding a Canvas Tool

For drawing or interaction features:

### Step 1: Add Mode Constant

Edit `libs/canvas.py`:

```python
# Add to mode constants at top of file
CREATE, EDIT, MY_MODE = list(range(3))
```

### Step 2: Add Mode Handler

In `Canvas` class:

```python
def enter_my_mode(self):
    """Enter my custom mode."""
    self.mode = MY_MODE
    self.setCursor(Qt.CrossCursor)  # Set appropriate cursor

def handle_my_mode_click(self, pos):
    """Handle click in my mode."""
    # Your click handling logic
    pass
```

### Step 3: Update Event Handlers

In `Canvas.mousePressEvent()`:

```python
def mousePressEvent(self, ev):
    pos = self.transform_pos(ev.pos())

    if ev.button() == Qt.LeftButton:
        if self.mode == MY_MODE:
            self.handle_my_mode_click(pos)
            return
        # ... existing code ...
```

### Step 4: Add Mode Toggle Action

In `labelImg.py`:

```python
my_mode = action(
    get_str('myMode'),
    self.set_my_mode,
    'M',
    'my-mode-icon',
    get_str('myModeDetail'),
    enabled=False  # Enable when image loaded
)

def set_my_mode(self):
    """Switch to my custom mode."""
    self.canvas.enter_my_mode()
    self.actions.create.setEnabled(True)
    self.actions.editMode.setEnabled(True)
    self.actions.myMode.setEnabled(False)  # Disable current
```

## Adding a Dialog

For features requiring user input:

### Step 1: Create Dialog Class

Create `libs/myDialog.py`:

```python
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, \
    QDialogButtonBox


class MyDialog(QDialog):
    """Custom dialog for my feature."""

    def __init__(self, parent=None, initial_value=''):
        super().__init__(parent)
        self.setWindowTitle('My Dialog')
        self.setup_ui(initial_value)

    def setup_ui(self, initial_value):
        layout = QVBoxLayout()

        # Add label
        layout.addWidget(QLabel('Enter value:'))

        # Add input
        self.input = QLineEdit(initial_value)
        layout.addWidget(self.input)

        # Add buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def get_value(self):
        """Return entered value."""
        return self.input.text()


def get_my_value(parent=None, initial=''):
    """Convenience function to show dialog and get result.

    Returns:
        Tuple of (value, accepted)
    """
    dialog = MyDialog(parent, initial)
    result = dialog.exec_()
    if result == QDialog.Accepted:
        return dialog.get_value(), True
    return None, False
```

### Step 2: Use Dialog in Handler

```python
# In labelImg.py
from libs.myDialog import get_my_value

def my_feature_handler(self):
    """Handle my feature with dialog."""
    value, ok = get_my_value(self, initial='default')
    if ok:
        print(f"User entered: {value}")
        # Process value
```

## Complete Example: Export Statistics

Here's a complete example adding a feature to export annotation statistics:

### strings.properties

```properties
exportStats=Export Statistics
exportStatsDetail=Export annotation statistics to CSV
```

### labelImg.py additions

```python
# In __init__, after other action definitions
export_stats = action(
    get_str('exportStats'),
    self.export_statistics,
    'Ctrl+Shift+E',
    'statistics',
    get_str('exportStatsDetail'),
    enabled=False
)

# Add to menus.file
add_actions(self.menus.file, (
    open, open_dir, ...,
    None,
    export_stats,  # Add here
    None,
    quit
))

# Store reference for enabling/disabling
self.actions = struct(
    ...,
    exportStats=export_stats,
)

# In load_file(), enable when directory loaded:
if self.dir_path:
    self.actions.exportStats.setEnabled(True)

# Implement handler
def export_statistics(self):
    """Export annotation statistics to CSV."""
    if not self.m_img_list:
        return

    # Collect statistics
    stats = {}
    total_annotations = 0

    for img_path in self.m_img_list:
        # Find corresponding label file
        label_path = self.get_label_path(img_path)
        if os.path.exists(label_path):
            # Count annotations (simplified)
            with open(label_path) as f:
                count = len(f.readlines())
            total_annotations += count
            stats[os.path.basename(img_path)] = count

    # Get save path
    from PyQt5.QtWidgets import QFileDialog
    save_path, _ = QFileDialog.getSaveFileName(
        self, 'Save Statistics', '', 'CSV Files (*.csv)'
    )

    if save_path:
        with open(save_path, 'w') as f:
            f.write('image,annotation_count\n')
            for img, count in stats.items():
                f.write(f'{img},{count}\n')
            f.write(f'\nTotal,{total_annotations}\n')

        self.status_bar.showMessage(f'Statistics exported to {save_path}')
```

## Feature Patterns

### Conditional Enabling

```python
# Enable when image loaded
def load_file(self, file_path):
    # ... load logic ...
    self.actions.my_feature.setEnabled(True)

# Enable when shape selected
def shape_selection_changed(self, selected):
    self.actions.my_shape_feature.setEnabled(selected)
```

### Batch Operations

```python
def batch_operation(self):
    """Apply operation to all images."""
    for img_path in self.m_img_list:
        # Load image
        self.load_file(img_path)
        # Apply operation
        self.do_operation()
        # Save
        self.save_file()

    self.status_bar.showMessage(f'Processed {len(self.m_img_list)} images')
```

### Undo Support

labelImg++ doesn't have built-in undo, but you can implement simple undo for your feature:

```python
def __init__(self):
    self.undo_stack = []

def my_feature_with_undo(self):
    # Save state
    self.undo_stack.append(self.get_current_state())
    # Make change
    self.do_change()

def undo_my_feature(self):
    if self.undo_stack:
        state = self.undo_stack.pop()
        self.restore_state(state)
```

## Checklist

- [ ] Added string resources to `strings.properties`
- [ ] Created action with `new_action()`
- [ ] Implemented handler method
- [ ] Added to appropriate menu
- [ ] Added to toolbar (if applicable)
- [ ] Created icon (if needed)
- [ ] Rebuilt resources (`make qt5py3`)
- [ ] Added settings persistence (if toggle)
- [ ] Handled enable/disable states
- [ ] Tested feature
- [ ] Added translations to other language files
