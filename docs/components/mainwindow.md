# MainWindow Component

MainWindow is the central controller that orchestrates all UI interactions, state management, and file operations.

**File:** `labelImg.py` (lines 73-1722)

## Overview

MainWindow (QMainWindow subclass) is responsible for:
- Building and managing the entire UI
- Handling user actions (menu, toolbar, keyboard)
- Managing application state (current file, dirty flag, format)
- Coordinating between Canvas, LabelFile, and Settings

## Class Hierarchy

```
QMainWindow
     |
     +-- WindowMixin (menu/toolbar helpers)
           |
           +-- MainWindow
```

## Initialization Flow

```
MainWindow.__init__(default_filename, default_prefdef_class_file, default_save_dir)
         |
         +---> Load Settings (line 81)
         |     self.settings = Settings()
         |     self.settings.load()
         |
         +---> Load i18n StringBundle (line 88)
         |     self.string_bundle = StringBundle.get_bundle()
         |
         +---> Initialize State Variables (lines 92-108)
         |     - m_img_list, dir_name, label_hist
         |     - cur_img_idx, img_count, dirty
         |
         +---> Load Predefined Classes (line 111)
         |     from data/predefined_classes.txt
         |
         +---> Create Label Dialog (line 119)
         |
         +---> Build Label List UI (lines 125-164)
         |     - Use default label checkbox
         |     - Default label combobox
         |     - Difficult checkbox
         |     - Label list widget
         |
         +---> Create Dock Widgets (lines 168-181)
         |     - Labels dock (right)
         |     - File list dock (right)
         |
         +---> Create Canvas (lines 187-209)
         |     - Inside QScrollArea
         |     - Connect signals
         |
         +---> Create Actions (lines 216-402)
         |     - File, Edit, View, Help actions
         |     - Keyboard shortcuts
         |
         +---> Build Menus (lines 404-440)
         |
         +---> Build Toolbar (lines 450-459)
         |
         +---> Restore Window State (lines 485-517)
         |     - Size, position, dock layout
         |     - Recent files, colors
         |
         +---> Connect Signals (lines 529-530)
         |
         +---> Load Initial File (lines 523-540)
               if provided via command line
```

## UI Structure

```
+------------------------------------------------------------------+
|  Menu Bar                                                         |
|  [File] [Edit] [View] [Help]                                      |
+------------------------------------------------------------------+
|  Tool Bar                                                         |
|  [Open][Dir][Save][Format][Prev][Next][Create][Copy][Delete]...   |
+------------------------------------------------------------------+
|                                         |                         |
|         QScrollArea                     |     Labels Dock         |
|  +---------------------------+          | +-------------------+   |
|  |                           |          | | [Edit] [Difficult]|   |
|  |                           |          | +-------------------+   |
|  |         Canvas            |          | | [Use Default]     |   |
|  |                           |          | | [Combobox filter] |   |
|  |    (image + shapes)       |          | +-------------------+   |
|  |                           |          | | [ ] label1        |   |
|  |                           |          | | [x] label2        |   |
|  +---------------------------+          | | [ ] label3        |   |
|                                         | +-------------------+   |
|                                         +-------------------------+
|                                         |     Files Dock          |
|                                         | +-------------------+   |
|                                         | | image1.jpg        |   |
|                                         | | image2.jpg  <--   |   |
|                                         | | image3.jpg        |   |
|                                         | +-------------------+   |
+------------------------------------------------------------------+
|  Status Bar                              | X: 150; Y: 200         |
+------------------------------------------------------------------+
```

## State Variables

### Application State

| Variable | Type | Description | Line |
|----------|------|-------------|------|
| `dirty` | bool | Unsaved changes exist | 104 |
| `file_path` | str | Current image path | 466 |
| `dir_name` | str | Current directory | 97 |
| `m_img_list` | list | Images in directory | 96 |
| `cur_img_idx` | int | Current image index | 100 |
| `img_count` | int | Total images | 101 |

### Format State

| Variable | Type | Description | Line |
|----------|------|-------------|------|
| `label_file_format` | LabelFileFormat | Current format | 93 |
| `label_file` | LabelFile | Current label file | 1119 |
| `default_save_dir` | str | Annotation save dir | 92 |

### Label State

| Variable | Type | Description | Line |
|----------|------|-------------|------|
| `label_hist` | list | Used labels | 98 |
| `default_label` | str | Default label text | 114 |
| `items_to_shapes` | dict | List item → Shape | 121 |
| `shapes_to_items` | dict | Shape → List item | 122 |

## Action System

Actions are created using the `new_action` helper:

```python
# Template:
action = new_action(
    parent,      # self
    text,        # Display text
    slot,        # Handler method
    shortcut,    # Keyboard shortcut
    icon,        # Icon name
    tip,         # Tooltip
    checkable,   # Is checkbox
    enabled      # Initial state
)
```

### File Actions (lines 217-268)

| Action | Shortcut | Handler |
|--------|----------|---------|
| `open` | Ctrl+O | `open_file` |
| `open_dir` | Ctrl+U | `open_dir_dialog` |
| `change_save_dir` | Ctrl+R | `change_save_dir_dialog` |
| `open_annotation` | Ctrl+Shift+O | `open_annotation_dialog` |
| `save` | Ctrl+S | `save_file` |
| `save_as` | Ctrl+Shift+S | `save_file_as` |
| `close` | Ctrl+W | `close_file` |
| `quit` | Ctrl+Q | `close` |

### Edit Actions (lines 273-284)

| Action | Shortcut | Handler |
|--------|----------|---------|
| `create` | W | `create_shape` |
| `delete` | Delete | `delete_selected_shape` |
| `copy` | Ctrl+D | `copy_selected_shape` |
| `edit` | Ctrl+E | `edit_label` |

### Navigation Actions (lines 233-240)

| Action | Shortcut | Handler |
|--------|----------|---------|
| `open_next_image` | D | `open_next_image` |
| `open_prev_image` | A | `open_prev_image` |
| `verify` | Space | `verify_image` |

## Key Methods

### File Operations

#### load_file (line 1093)

```python
def load_file(self, file_path=None):
    """Load image and its annotations.

    1. Reset state
    2. Load image to canvas
    3. Search for annotation file
    4. Load annotations if found
    5. Update UI (window title, file list selection)
    """
```

#### save_file (line 1467)

```python
def save_file(self, _value=False):
    """Save current annotations.

    1. Determine save path (default_save_dir or image dir)
    2. Call _save_file with path
    3. Update status bar
    """
```

#### save_labels (line 879)

```python
def save_labels(self, annotation_file_path):
    """Save annotations in current format.

    1. Format shape data as dicts
    2. Route to format-specific save method
    3. Handle file extensions
    """
```

### State Management

#### set_dirty / set_clean (lines 619-626)

```python
def set_dirty(self):
    self.dirty = True
    self.actions.save.setEnabled(True)

def set_clean(self):
    self.dirty = False
    self.actions.save.setEnabled(False)
    self.actions.create.setEnabled(True)
```

#### may_continue (line 1539)

```python
def may_continue(self):
    """Check if safe to proceed (prompts save if dirty)."""
    if not self.dirty:
        return True
    else:
        discard_changes = self.discard_changes_dialog()
        if discard_changes == QMessageBox.No:
            return True  # Discard changes
        elif discard_changes == QMessageBox.Yes:
            self.save_file()
            return True
        else:
            return False  # Cancel
```

### Shape Management

#### new_shape (line 958)

```python
def new_shape(self):
    """Handle new shape creation from Canvas.

    1. Show label dialog (or use default)
    2. Set label on shape
    3. Add to label list
    4. Update UI state
    """
```

#### add_label (line 815)

```python
def add_label(self, shape):
    """Add shape to label list widget.

    1. Create QListWidgetItem with checkbox
    2. Set background color from label
    3. Map item <-> shape bidirectionally
    """
```

#### load_labels (line 838)

```python
def load_labels(self, shapes):
    """Load shapes from annotation file.

    shapes: List of (label, points, line_color, fill_color, difficult)

    1. Create Shape objects
    2. Snap points to canvas bounds
    3. Add to canvas and label list
    """
```

### Mode Management

#### toggle_advanced_mode (line 585)

```python
def toggle_advanced_mode(self, value=True):
    """Switch between Beginner and Advanced modes.

    Beginner: Single Create button, auto-edit mode
    Advanced: Separate Create/Edit modes, more options
    """
    self._beginner = not value
    self.canvas.set_editing(True)
    self.populate_mode_actions()  # Rebuild toolbar
```

### Format Management

#### set_format (line 552)

```python
def set_format(self, save_format):
    """Set current annotation format."""
    if save_format == FORMAT_PASCALVOC:
        self.label_file_format = LabelFileFormat.PASCAL_VOC
        LabelFile.suffix = XML_EXT
    elif save_format == FORMAT_YOLO:
        self.label_file_format = LabelFileFormat.YOLO
        LabelFile.suffix = TXT_EXT
    elif save_format == FORMAT_CREATEML:
        self.label_file_format = LabelFileFormat.CREATE_ML
        LabelFile.suffix = JSON_EXT
```

#### change_format (line 571)

```python
def change_format(self):
    """Cycle through formats: VOC -> YOLO -> CreateML -> VOC"""
```

## Signal Connections

### Canvas Signals

```python
# In __init__:
self.canvas.zoomRequest.connect(self.zoom_request)
self.canvas.lightRequest.connect(self.light_request)
self.canvas.scrollRequest.connect(self.scroll_request)
self.canvas.newShape.connect(self.new_shape)
self.canvas.shapeMoved.connect(self.set_dirty)
self.canvas.selectionChanged.connect(self.shape_selection_changed)
self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)
```

### Widget Signals

```python
# Label list
self.label_list.itemActivated.connect(self.label_selection_changed)
self.label_list.itemSelectionChanged.connect(self.label_selection_changed)
self.label_list.itemDoubleClicked.connect(self.edit_label)
self.label_list.itemChanged.connect(self.label_item_changed)

# File list
self.file_list_widget.itemDoubleClicked.connect(self.file_item_double_clicked)

# Zoom/Light widgets
self.zoom_widget.valueChanged.connect(self.paint_canvas)
self.light_widget.valueChanged.connect(self.paint_canvas)
```

## Settings Persistence

### Save on Close (line 1245)

```python
def closeEvent(self, event):
    if not self.may_continue():
        event.ignore()
        return

    settings = self.settings
    settings[SETTING_WIN_SIZE] = self.size()
    settings[SETTING_WIN_POSE] = self.pos()
    settings[SETTING_WIN_STATE] = self.saveState()
    settings[SETTING_LINE_COLOR] = self.line_color
    settings[SETTING_FILL_COLOR] = self.fill_color
    settings[SETTING_RECENT_FILES] = self.recent_files
    settings[SETTING_ADVANCE_MODE] = not self._beginner
    settings[SETTING_SAVE_DIR] = self.default_save_dir
    settings[SETTING_AUTO_SAVE] = self.auto_saving.isChecked()
    settings[SETTING_LABEL_FILE_FORMAT] = self.label_file_format
    settings.save()
```

### Restore on Start (line 485)

```python
# Window geometry
size = settings.get(SETTING_WIN_SIZE, QSize(600, 500))
position = settings.get(SETTING_WIN_POSE, QPoint(0, 0))
self.resize(size)
self.move(position)

# Dock/toolbar state
self.restoreState(settings.get(SETTING_WIN_STATE, QByteArray()))

# Colors
Shape.line_color = self.line_color = QColor(settings.get(SETTING_LINE_COLOR))
Shape.fill_color = self.fill_color = QColor(settings.get(SETTING_FILL_COLOR))
```

## Method Reference

| Method | Line | Description |
|--------|------|-------------|
| `__init__` | 76-541 | Initialize UI and state |
| `load_file` | 1093-1172 | Load image and annotations |
| `save_file` | 1467-1480 | Save annotations |
| `save_labels` | 879-918 | Format and write annotations |
| `new_shape` | 958-996 | Handle shape creation |
| `add_label` | 815-826 | Add shape to list |
| `load_labels` | 838-866 | Load shapes from file |
| `set_dirty` | 619-621 | Mark unsaved changes |
| `set_clean` | 623-626 | Clear dirty state |
| `may_continue` | 1539-1550 | Check/prompt for save |
| `toggle_advanced_mode` | 585-595 | Switch UI modes |
| `set_format` | 552-569 | Set annotation format |
| `open_next_image` | 1422-1451 | Navigate to next |
| `open_prev_image` | 1397-1420 | Navigate to previous |
| `closeEvent` | 1245-1277 | Save settings on exit |
