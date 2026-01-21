# Keyboard Shortcuts Reference

Complete reference of all keyboard shortcuts in labelImg++.

## File Operations

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl+O` | Open File | Open single image or label file |
| `Ctrl+U` | Open Directory | Load all images from a directory |
| `Ctrl+R` | Change Save Dir | Set annotation save location |
| `Ctrl+Shift+O` | Open Annotation | Load specific annotation file |
| `Ctrl+S` | Save | Save current annotations |
| `Ctrl+Shift+S` | Save As | Save to different location |
| `Ctrl+W` | Close | Close current file |
| `Ctrl+Q` | Quit | Exit application |

## Navigation

| Shortcut | Action | Description |
|----------|--------|-------------|
| `D` | Next Image | Go to next image in directory |
| `A` | Previous Image | Go to previous image in directory |
| `Space` | Verify Image | Toggle verified status (green background) |

## Annotation Creation

| Shortcut | Action | Description |
|----------|--------|-------------|
| `W` | Create RectBox | Start drawing new bounding box |
| `Ctrl+J` | Edit Mode | Switch to edit mode (Advanced) |
| `Delete` | Delete Box | Delete selected annotation |
| `Ctrl+D` | Duplicate Box | Copy selected annotation |
| `Ctrl+E` | Edit Label | Change label of selected box |
| `Ctrl+V` | Copy Previous | Copy annotations from previous image |

## Shape Movement

| Shortcut | Action | Description |
|----------|--------|-------------|
| `↑` | Move Up | Move selected shape up 1 pixel |
| `↓` | Move Down | Move selected shape down 1 pixel |
| `←` | Move Left | Move selected shape left 1 pixel |
| `→` | Move Right | Move selected shape right 1 pixel |

## View Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl++` | Zoom In | Increase zoom by 10% |
| `Ctrl+-` | Zoom Out | Decrease zoom by 10% |
| `Ctrl+=` | Original Size | Reset zoom to 100% |
| `Ctrl+F` | Fit Window | Scale to fit window |
| `Ctrl+Shift+F` | Fit Width | Scale to fit width |

## Brightness Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl+Shift++` | Brighten | Increase brightness |
| `Ctrl+Shift+-` | Darken | Decrease brightness |
| `Ctrl+Shift+=` | Reset Light | Reset to default brightness |

## Display Options

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl+H` | Hide All | Hide all bounding boxes |
| `Ctrl+A` | Show All | Show all bounding boxes |
| `Ctrl+Shift+L` | Toggle Labels | Show/hide labels panel |
| `Ctrl+Shift+P` | Display Labels | Toggle label text on boxes |
| `Ctrl+Shift+R` | Draw Squares | Toggle square constraint |

## Mode Controls

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl+Shift+A` | Advanced Mode | Toggle Advanced/Beginner mode |
| `Ctrl+Y` | Change Format | Cycle: VOC → YOLO → CreateML |

## Drawing Modifiers

| Shortcut | Action | Description |
|----------|--------|-------------|
| `Ctrl` (hold) | Draw Square | Constrain to square while drawing |
| `Escape` | Cancel | Cancel current drawing operation |
| `Return` | Finalize | Complete current shape |

## Mouse Controls

| Action | Description |
|--------|-------------|
| Left Click + Drag | Draw new box (CREATE mode) |
| Left Click | Select shape (EDIT mode) |
| Left Drag on shape | Move entire shape |
| Left Drag on vertex | Resize shape |
| Right Click + Drag | Copy and move shape |
| Scroll Wheel | Scroll canvas |
| Ctrl + Scroll | Zoom in/out |
| Ctrl+Shift + Scroll | Adjust brightness |
| Double Click (file list) | Open selected image |
| Double Click (label list) | Edit label |

## Shortcut Reference by Method

| Shortcut | Handler Method | Line |
|----------|----------------|------|
| `Ctrl+O` | `open_file` | 1453 |
| `Ctrl+U` | `open_dir_dialog` | 1343 |
| `Ctrl+R` | `change_save_dir_dialog` | 1296 |
| `Ctrl+Shift+O` | `open_annotation_dialog` | 1316 |
| `Ctrl+S` | `save_file` | 1467 |
| `Ctrl+Shift+S` | `save_file_as` | 1482 |
| `Ctrl+W` | `close_file` | 1510 |
| `Ctrl+Q` | `close` | inherited |
| `D` | `open_next_image` | 1422 |
| `A` | `open_prev_image` | 1397 |
| `Space` | `verify_image` | 1379 |
| `W` | `create_shape` | 704 |
| `Delete` | `delete_selected_shape` | 1574 |
| `Ctrl+D` | `copy_selected_shape` | 920 |
| `Ctrl+E` | `edit_label` | 752 |
| `Ctrl+V` | `copy_previous_bounding_boxes` | 1658 |
| `Ctrl+J` | `set_edit_mode` | 728 |

## Context Menu (Right-Click)

When right-clicking on canvas with a shape selected:

| Option | Description |
|--------|-------------|
| Copy here | Copy selected shape to click location |
| Move here | Move selected shape to click location |

## Tips

### Drawing Efficiently
1. Press `W` to start drawing
2. Click and drag to create box
3. Type label or select from list
4. Press `D` to move to next image

### Batch Labeling
1. Enable auto-save in View menu
2. Navigate with `A`/`D` keys
3. Annotations save automatically

### Precise Positioning
1. Select shape
2. Use arrow keys for pixel-perfect adjustment
3. Each press moves 1 pixel

### Square Boxes
1. Hold `Ctrl` while drawing
2. Or enable "Draw Squares" in View menu
