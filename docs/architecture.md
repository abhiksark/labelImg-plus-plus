# Architecture Overview

This document describes the high-level architecture of labelImg++, including component relationships, data flow, and design patterns.

## Runtime and dataset pipeline

Normal UI actions use bounded Qt worker lanes owned by
`libs/core/task_coordinator.py`. Interactive image work has one or two threads,
background catalog/thumbnail/bulk work has one to four, and SAM has one
dedicated thread. Jobs carry cancellation handles, dataset generations, and
optional latest-request-wins keys. The process-global Qt thread pool is not
used.

Opening a directory builds an immutable `DatasetSnapshot` in a worker. The
snapshot owns the sorted paths, an O(1) path index, and an `AnnotationResolver`
that computes recursive collision-safe annotation stems and directory filename
sets once. A completed snapshot replaces the visible dataset atomically; a
failed or cancelled scan leaves the prior dataset intact.

One progressive `AnnotationCatalog` supplies file-list filters, both gallery
surfaces, statistics, and verification counts. Shared COCO/CreateML documents
are parsed and indexed once per `(path, mtime_ns, size)` fingerprint.

UI navigation calls `request_load_file()`. Its worker returns an immutable
`ImageLoadResult` containing a worker-owned `QImage` and raw shape tuples. Only
the application thread creates `QPixmap`, `Shape`, and widget items. A
fingerprinted five-frame/96 MiB LRU supports adjacent-image prefetch. The
historical synchronous `load_file()` remains available to extensions and
tests.

Menu, shortcut, autosave, navigation, and verification saves create immutable
`SaveRequest` values. Worker serialization is atomically published with
`os.replace`; a revision check marks the document clean only if no later edit
occurred. `save_file()` remains the synchronous compatibility entry point.

## Plugin runtime

The Qt-free public boundary is `labelimgplusplus.plugins`. Installed
distributions advertise zero-argument factories through the
`labelimgplusplus.plugins` entry-point group. `plugin_discovery.py` reads only
distribution metadata during discovery, adapts both legacy and selectable
`importlib.metadata` collections, sorts deterministically, and does not import
disabled plugin targets.

MainWindow constructs `PluginManager` after Settings and TaskCoordinator. Once
core UI construction is complete, enabled candidates are loaded in order.
Each activation receives an `ActivationContext` containing staged commands,
namespaced JSON settings, a restricted background task service, immutable
document descriptors, and diagnostics. The manager commits registrations
atomically or discards them and continues base startup.

The Qt command host creates every plugin `QAction`, places actions in the
host-owned Plugins menu, and applies dynamic shortcut defaults and retained
overrides. Plugins never receive MainWindow, menu, action, Canvas, Shape, or
mutable video objects. Enable/disable state is saved immediately but is applied
only on restart.

Plugin workers share the bounded background lane and use cooperative
cancellation. Result, error, progress, command, enablement, and document
callbacks return to `QApplication.thread()`. Successful image/video commits,
reset/close transitions, and dirty/revision changes publish frozen
`DocumentDescriptor` values. A generation change cancels plugin work and
discards stale results.

Shutdown stops plugin task submission, cancels handles, deactivates active
plugins in reverse order, removes host registrations, and then shuts down the
core TaskCoordinator. `LABELIMGPP_DISABLE_PLUGINS=1` bypasses discovery and
loading for recovery. This boundary limits accidental coupling but is not a
sandbox; enabled plugins are trusted in-process Python code.

Ultralytics dataset export captures the active immutable snapshot, annotation
resolver, source-format selection, class order, split ratios, and copy mode in
an `UltralyticsExportRequest`. A background job reuses the image annotation
pipeline and YOLO normalization writer, builds `images/`, `labels/`,
`data.yaml`, and a manifest in an owned sibling staging directory, then
atomically publishes only to a new or empty destination. Cancellation and
conversion errors remove only that staging tree.

## Smart-video pipeline

`DocumentKind` isolates no-document, image, and video state. Video requests use
a dedicated one-thread decoder lane; tracking and export use independent PyAV
contexts on the background lane so bulk work cannot block scrubbing. Workers
return immutable records and detached `QImage` values. `QPixmap`, `Shape`, dock,
track-list, timeline, and canvas mutation remain on `QApplication.thread()`.

Opening is transactional. `video_session.py` resolves a video/project source,
opens the first playable stream, fingerprints bounded source samples, decodes
the first frame, and validates or initializes SQLite before MainWindow swaps
the visible document. Failed or stale requests close their new container and
leave the old document intact. `open_video()` is the synchronous compatibility
path; `request_open_video()` is the GUI path.

The session-owned `VideoDecoderSession` seeks in stream PTS/time-base units,
decodes forward from a keyframe, supports nearest or at/after selection, and
applies stream or display-matrix rotation before display. Video uses up to 12
entries in the shared 96 MiB frame cache. Together with two 16 MiB gallery
caches, the application cache ceiling remains 128 MiB.

`VideoProjectModel` is the in-memory overlay. It materializes accepted manual
states, accepted tracker states, pending suggestions, or rectangle/keypoint
interpolation in that order. Polygon interpolation is forbidden. Canvas edits
become accepted manual observations; computed occurrences never serialize as
image `Shape` state.

`video_project.py` owns the application-ID/schema-versioned SQLite file. WAL,
foreign keys, `synchronous=FULL`, busy timeout, expected durable revisions, and
`BEGIN IMMEDIATE` delta commits fence concurrent or failed saves. MainWindow
chains writes and only marks clean when the saved revision still matches.
Save As uses SQLite backup and clean close checkpoints WAL.

`video_tracking.py` performs bounded-resolution Shi–Tomasi/Lucas–Kanade flow
and RANSAC affine estimation, emitting immutable pending observations. Session,
request, generation, document-revision, and seed-revision checks discard stale
batches. `video_export.py` decodes original-resolution oriented frames in an
independent context, filters to accepted materialization, reuses the existing
format contracts, and atomically publishes an owned staging directory plus a
video manifest.

## System Architecture

```
+------------------------------------------------------------------+
|                         MainWindow                                |
|                      (labelImgPlusPlus.py:73)                             |
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

### MainWindow (`labelImgPlusPlus.py:73-1722`)
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
├── labelImgPlusPlus.py          # MainWindow, entry point (1722 lines)
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

The Qt application thread owns widgets, `QPixmap`, `Shape`, selection, and
document mutation. Bounded coordinator lanes own image decode/catalog work,
bulk jobs, SAM, and serialized interactive video decode. Background work uses
immutable snapshots, cooperative cancellation, generation fencing, and queued
signals to return plain data or detached `QImage` values to the UI.

## Extension Points

| Extension | Location | Pattern |
|-----------|----------|---------|
| New format | `libs/` | Add Writer/Reader classes |
| New action | `labelImgPlusPlus.py` | Define action, add to menu |
| New widget | `libs/` | Create widget, add to MainWindow |
| New language | `resources/strings/` | Add properties file |

See [Extension Guide](guides/extension-guide.md) for details.
