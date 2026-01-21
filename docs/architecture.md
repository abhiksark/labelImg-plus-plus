# Architecture Overview

This document describes the high-level architecture of labelImg++, including component relationships, data flow, and design patterns.

## System Architecture

```
+------------------------------------------------------------------+
|                         MainWindow                                |
|                      (labelImg.py:73)                             |
|  +------------------+  +------------------+  +------------------+ |
|  |    Menu Bar     |  |    Tool Bar      |  |   Status Bar     | |
|  +------------------+  +------------------+  +------------------+ |
|                                                                   |
|  +-------------------------------+  +---------------------------+ |
|  |         QScrollArea           |  |     Dock Widgets          | |
|  |  +-----------------------+    |  |  +---------------------+  | |
|  |  |       Canvas          |    |  |  | Label List Widget   |  | |
|  |  |   (libs/canvas.py)    |    |  |  | - Annotation items  |  | |
|  |  |                       |    |  |  | - Checkboxes        |  | |
|  |  |   +---------------+   |    |  |  | - Difficult flag    |  | |
|  |  |   | Shape objects |   |    |  |  +---------------------+  | |
|  |  |   | (bounding     |   |    |  |  +---------------------+  | |
|  |  |   |  boxes)       |   |    |  |  | File List Widget    |  | |
|  |  |   +---------------+   |    |  |  | - Image files       |  | |
|  |  +-----------------------+    |  |  | - Double-click nav  |  | |
|  +-------------------------------+  |  +---------------------+  | |
|                                     +---------------------------+ |
+------------------------------------------------------------------+
         |                    |                    |
         v                    v                    v
+----------------+   +----------------+   +------------------+
|   LabelFile    |   |   Settings     |   |  StringBundle    |
| (Format I/O)   |   | (Persistence)  |   |     (i18n)       |
+----------------+   +----------------+   +------------------+
         |
         v
+--------------------------------------------------+
|              Format Writers/Readers               |
|  +------------+  +------------+  +-------------+ |
|  | PascalVoc  |  |    YOLO    |  |  CreateML   | |
|  |  Writer    |  |   Writer   |  |   Writer    | |
|  |  Reader    |  |   Reader   |  |   Reader    | |
|  +------------+  +------------+  +-------------+ |
+--------------------------------------------------+
         |
         v
+--------------------------------------------------+
|              Annotation Files                     |
|  +------------+  +------------+  +-------------+ |
|  |   .xml     |  |   .txt     |  |   .json     | |
|  | (VOC)      |  |  (YOLO)    |  | (CreateML)  | |
|  +------------+  +------------+  +-------------+ |
+--------------------------------------------------+
```

## Component Responsibilities

### MainWindow (`labelImg.py:73-1722`)
The central controller and UI orchestrator:
- **UI Setup**: Creates menus, toolbars, dock widgets, canvas
- **Action Handling**: Defines and connects all user actions
- **State Management**: Tracks current file, dirty flag, image list
- **Format Selection**: Manages annotation format switching
- **File Operations**: Load/save images and annotations

### Canvas (`libs/canvas.py:24-749`)
Interactive drawing surface:
- **Mode Management**: CREATE (drawing) vs EDIT (selecting/moving)
- **Mouse Handling**: Click, drag, hover for drawing and editing
- **Coordinate Transformation**: Screen to image coordinates
- **Shape Rendering**: Draws shapes with highlights and labels
- **Zoom/Pan**: Scroll and scale operations

### Shape (`libs/shape.py:23-210`)
Bounding box representation:
- **Point Storage**: 4-corner polygon as QPointF list
- **Label/Metadata**: Class label, difficult flag, colors
- **Rendering**: Paint method for Qt drawing
- **Geometry**: Contains point, bounding rect, nearest vertex

### LabelFile (`libs/labelFile.py:28-175`)
Format orchestration layer:
- **Format Dispatch**: Routes to appropriate writer/reader
- **Coordinate Conversion**: Points to bounding box conversion
- **Verification State**: Tracks verified annotation status

## Data Flow

### Annotation Creation Flow

```
User clicks on Canvas (CREATE mode)
         |
         v
+------------------+
| Canvas           |
| mousePressEvent  |-----> Creates new Shape object
| (line 258)       |       with first point
+------------------+
         |
         | Mouse move updates preview
         v
+------------------+
| Canvas           |
| handle_drawing   |-----> Adds remaining 3 points
| (line 322)       |       to complete rectangle
+------------------+
         |
         | finalise() called
         v
+------------------+
| Canvas           |
| newShape signal  |-----> Emits signal to MainWindow
| (line 586)       |
+------------------+
         |
         v
+------------------+
| MainWindow       |
| new_shape        |-----> Opens LabelDialog for label input
| (line 958)       |
+------------------+
         |
         v
+------------------+
| LabelDialog      |
| pop_up           |-----> Returns label text
+------------------+
         |
         v
+------------------+
| MainWindow       |
| add_label        |-----> Creates list item, maps shape
| (line 815)       |
+------------------+
```

### Save Flow

```
User triggers save (Ctrl+S)
         |
         v
+------------------+
| MainWindow       |
| save_file        |-----> Determines save path
| (line 1467)      |
+------------------+
         |
         v
+------------------+
| MainWindow       |
| save_labels      |-----> Collects shapes, formats data
| (line 879)       |
+------------------+
         |
         | Routes by label_file_format
         v
+------------------+------------------+------------------+
|    PASCAL_VOC    |       YOLO       |    CREATE_ML     |
+------------------+------------------+------------------+
         |                  |                  |
         v                  v                  v
+------------------+------------------+------------------+
| save_pascal_voc  | save_yolo        | save_create_ml   |
| _format          | _format          | _format          |
| (line 54)        | (line 84)        | (line 39)        |
+------------------+------------------+------------------+
         |                  |                  |
         v                  v                  v
+------------------+------------------+------------------+
| PascalVocWriter  | YOLOWriter       | CreateMLWriter   |
| add_bnd_box()    | add_bnd_box()    | write()          |
| save()           | save()           |                  |
+------------------+------------------+------------------+
         |                  |                  |
         v                  v                  v
      .xml file        .txt file          .json file
                    + classes.txt
```

### Load Flow

```
User opens image file
         |
         v
+------------------+
| MainWindow       |
| load_file        |-----> Loads image to Canvas
| (line 1093)      |
+------------------+
         |
         v
+------------------+
| MainWindow       |
| show_bounding_   |-----> Searches for annotation file
| box_from_        |       Priority: .xml > .txt > .json
| annotation_file  |
| (line 1180)      |
+------------------+
         |
         | File found
         v
+------------------+------------------+------------------+
| load_pascal_xml  | load_yolo_txt    | load_create_ml   |
| _by_filename     | _by_filename     | _json_by_        |
| (line 1619)      | (line 1632)      | filename (1645)  |
+------------------+------------------+------------------+
         |                  |                  |
         v                  v                  v
+------------------+------------------+------------------+
| PascalVocReader  | YoloReader       | CreateMLReader   |
| get_shapes()     | get_shapes()     | get_shapes()     |
+------------------+------------------+------------------+
         |                  |                  |
         +------------------+------------------+
                           |
                           v
+------------------+
| MainWindow       |
| load_labels      |-----> Creates Shape objects from tuples
| (line 838)       |       Adds to Canvas and label list
+------------------+
```

## Coordinate Systems

```
Screen Coordinates              Image Coordinates
(Widget/Mouse Position)         (Actual Pixel Position)
+----------------------+        +----------------------+
|(0,0)                 |        |(0,0)                 |
|  +------------+      |        |                      |
|  | scroll     |      |        |    (x,y)             |
|  | area       |      |  --->  |      *               |
|  |  +------+  |      | scale  |                      |
|  |  |image |  |      | offset |                      |
|  |  +------+  |      |        |                      |
|  +------------+      |        |          (img_w,     |
|            (W,H)     |        |           img_h)     |
+----------------------+        +----------------------+

Transformation (Canvas.transform_pos, line 557):
    image_pos = screen_pos / scale - offset_to_center()

Offset Calculation (Canvas.offset_to_center, line 561):
    x_offset = (canvas_width - pixmap_width * scale) / (2 * scale)
    y_offset = (canvas_height - pixmap_height * scale) / (2 * scale)
```

## Design Patterns

### Signal-Slot Pattern (Qt)
Components communicate via signals without tight coupling:

```
Canvas                          MainWindow
+------------------+            +------------------+
| newShape --------|----------->| new_shape()      |
| shapeMoved ------|----------->| set_dirty()      |
| selectionChanged-|----------->| shape_selection  |
|                  |            |   _changed()     |
| zoomRequest -----|----------->| zoom_request()   |
| scrollRequest ---|----------->| scroll_request() |
+------------------+            +------------------+
```

### Strategy Pattern (Format I/O)
Format selection determines which writer/reader is used:

```
LabelFileFormat enum
         |
         +---> PASCAL_VOC --> PascalVocWriter/Reader
         |
         +---> YOLO --------> YOLOWriter/YoloReader
         |
         +---> CREATE_ML ---> CreateMLWriter/CreateMLReader
```

### Observer Pattern (Label List)
Label list observes Canvas selection changes:

```
Canvas.selectionChanged signal
         |
         v
MainWindow.shape_selection_changed()
         |
         v
label_list.setCurrentItem(shape_item)
```

## State Management

### Application State (MainWindow)

| State Variable | Type | Description |
|----------------|------|-------------|
| `dirty` | bool | Unsaved changes exist |
| `file_path` | str | Current image path |
| `m_img_list` | list | All images in directory |
| `cur_img_idx` | int | Current image index |
| `label_file_format` | enum | Selected format |
| `label_hist` | list | Used labels history |
| `default_save_dir` | str | Annotation save directory |

### Canvas State

| State Variable | Type | Description |
|----------------|------|-------------|
| `mode` | int | CREATE or EDIT |
| `shapes` | list | All Shape objects |
| `selected_shape` | Shape | Currently selected |
| `current` | Shape | Shape being drawn |
| `scale` | float | Zoom level |
| `h_shape` | Shape | Hovered shape |
| `h_vertex` | int | Hovered vertex index |

### Dirty Flag Flow

```
Action                          Result
------                          ------
new_shape()            ------>  set_dirty()
shape moved            ------>  set_dirty()
label edited           ------>  set_dirty()
save_file() success    ------>  set_clean()
load_file()            ------>  set_clean()
```

## Event Handling

### Keyboard Events

```
MainWindow.keyPressEvent          Canvas.keyPressEvent
+---------------------------+     +---------------------------+
| Ctrl held --> draw square |     | Escape --> cancel drawing |
+---------------------------+     | Return --> finalize shape |
                                  | Arrows --> move shape 1px |
                                  +---------------------------+
```

### Mouse Events (Canvas)

```
Mode        Event           Handler
----        -----           -------
CREATE      Press+Drag      handle_drawing() - add points
CREATE      Release         Complete rectangle if 4 points
EDIT        Press           select_shape_point()
EDIT        Drag            bounded_move_shape/vertex()
EDIT        Right-click     Context menu (copy/move)
Any         Wheel           Zoom (Ctrl) or Scroll
```

## File Organization

```
labelImg++/
├── labelImg.py          # MainWindow, entry point (1722 lines)
│
├── libs/
│   ├── canvas.py        # Canvas widget (749 lines)
│   ├── shape.py         # Shape class (210 lines)
│   ├── labelFile.py     # Format orchestration (175 lines)
│   │
│   ├── pascal_voc_io.py # VOC format (172 lines)
│   ├── yolo_io.py       # YOLO format (144 lines)
│   ├── create_ml_io.py  # CreateML format (136 lines)
│   │
│   ├── settings.py      # Persistence (45 lines)
│   ├── stringBundle.py  # i18n (78 lines)
│   │
│   ├── labelDialog.py   # Label input
│   ├── colorDialog.py   # Color picker
│   ├── zoomWidget.py    # Zoom control
│   ├── lightWidget.py   # Brightness control
│   │
│   ├── utils.py         # Helpers
│   └── constants.py     # Constants
│
└── resources/
    ├── resources.qrc    # Qt resource file
    ├── icons/           # Application icons
    └── strings/         # Localization
```

## Threading Model

labelImg++ runs entirely on the main Qt event loop thread:
- No background workers for I/O
- UI remains responsive for typical image sizes
- Large images may cause brief freezes during load/save

## Extension Points

| Extension | Location | Pattern |
|-----------|----------|---------|
| New format | `libs/` | Add Writer/Reader classes |
| New action | `labelImg.py` | Define action, add to menu |
| New widget | `libs/` | Create widget, add to MainWindow |
| New language | `resources/strings/` | Add properties file |

See [Extension Guide](guides/extension-guide.md) for details.
