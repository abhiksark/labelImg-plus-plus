# Canvas Component

The Canvas widget is the interactive drawing surface where users create and edit bounding box annotations.

**File:** `libs/canvas.py` (lines 24-749)

## Overview

Canvas is a QWidget subclass that handles:
- Drawing new bounding boxes
- Selecting and editing existing annotations
- Zoom and pan operations
- Coordinate transformation between screen and image space

## Class Definition

```python
class Canvas(QWidget):
    # Mode constants
    CREATE, EDIT = list(range(2))

    # Vertex detection tolerance (pixels)
    epsilon = 24.0
```

## Signals

| Signal | Parameters | Description |
|--------|------------|-------------|
| `zoomRequest` | int (delta) | Request zoom change |
| `lightRequest` | int (delta) | Request brightness change |
| `scrollRequest` | int, int | Request scroll position change |
| `newShape` | none | New shape completed |
| `selectionChanged` | bool | Selection state changed |
| `shapeMoved` | none | Shape position changed |
| `drawingPolygon` | bool | Drawing state changed |

## Modes of Operation

```
                    Canvas Modes
                         |
          +--------------+--------------+
          |                             |
     CREATE Mode                   EDIT Mode
     self.mode == CREATE           self.mode == EDIT
     drawing() == True             editing() == True
          |                             |
    +-----+-----+              +--------+--------+
    |           |              |        |        |
  Click       Move         Select    Move     Resize
  to start   updates       shape    whole    single
  drawing    preview       by       shape    vertex
             line          click
```

### CREATE Mode
- Activated by pressing 'W' or clicking Create button
- Click to start drawing, release to complete rectangle
- Crosshair cursor shows current position
- Preview rectangle shown during drawing

### EDIT Mode
- Default mode when not drawing
- Click to select shapes
- Drag to move shapes or vertices
- Right-click for copy/move context menu

## State Variables

| Variable | Type | Description |
|----------|------|-------------|
| `mode` | int | CREATE or EDIT |
| `shapes` | list[Shape] | All annotations |
| `current` | Shape | Shape being drawn |
| `selected_shape` | Shape | Currently selected |
| `selected_shape_copy` | Shape | Shadow copy for move |
| `line` | Shape | Preview line while drawing |
| `scale` | float | Current zoom level |
| `pixmap` | QPixmap | Loaded image |
| `h_shape` | Shape | Hovered shape |
| `h_vertex` | int | Hovered vertex index |
| `draw_square` | bool | Constrain to square |

## Mouse Event Handling

### Drawing Flow (CREATE Mode)

```
mousePressEvent (Left button)
         |
         v
    out_of_pixmap(pos)?
         |
    +----+----+
    |         |
   No        Yes
    |         |
    v      (ignore)
handle_drawing(pos)
    |
    +---> If current shape exists with < 4 points:
    |         - Add remaining corner points
    |         - Call finalise()
    |
    +---> Else if pos in pixmap:
              - Create new Shape()
              - Add first point
              - Set preview line
              - Emit drawingPolygon(True)

mouseMoveEvent (during drawing)
         |
         v
    Update self.line[1] with current position
         |
         +---> Clip to pixmap bounds if outside
         |
         +---> If draw_square: constrain to equal w/h
         |
         +---> Update status bar with dimensions
         |
         v
    repaint()

mouseReleaseEvent (Left button)
         |
         v
    If drawing: handle_drawing(pos)
         |
         +---> Rectangle completed (4 points)
         |
         v
    finalise()
         |
         +---> Close shape
         +---> Add to shapes list
         +---> Emit newShape signal
         +---> MainWindow opens label dialog
```

### Editing Flow (EDIT Mode)

```
mousePressEvent (Left button)
         |
         v
select_shape_point(pos)
         |
    +----+----+----+
    |         |    |
 Vertex    Shape  Nothing
 clicked   body   clicked
    |         |    |
    v         v    v
 Select    Select  Start
 vertex    shape   panning
    |         |    |
    v         v    v
h_vertex  selected  pan_
 set      _shape    initial_
          set       pos set

mouseMoveEvent (dragging)
         |
    +----+----+----+
    |         |    |
 Vertex    Shape  Pan
 selected  selected mode
    |         |    |
    v         v    v
bounded_  bounded_  scroll
move_     move_     Request
vertex()  shape()   emitted
```

## Coordinate Transformation

### Screen to Image Coordinates

```python
def transform_pos(self, point):
    """Convert from widget-logical to painter-logical coordinates."""
    return point / self.scale - self.offset_to_center()
```

```
Screen Space                    Image Space
+------------------+            +------------------+
|(0,0)             |            |(0,0)             |
|   +---------+    |   scale    |                  |
|   | visible |    |   ------>  |   (x, y)         |
|   | area    |    |   offset   |     *            |
|   |  *click |    |            |   actual         |
|   +---------+    |            |   position       |
|          (W,H)   |            |          (w,h)   |
+------------------+            +------------------+

click_pos = (400, 300)  # screen coordinates
scale = 2.0
offset = (50, 25)

image_pos = click_pos / scale - offset
          = (200, 150) - (50, 25)
          = (150, 125)  # image coordinates
```

### Offset Calculation

```python
def offset_to_center(self):
    """Calculate offset to center image in widget."""
    s = self.scale
    area = super(Canvas, self).size()
    w, h = self.pixmap.width() * s, self.pixmap.height() * s
    aw, ah = area.width(), area.height()
    x = (aw - w) / (2 * s) if aw > w else 0
    y = (ah - h) / (2 * s) if ah > h else 0
    return QPointF(x, y)
```

## Shape Rendering (paintEvent)

```python
def paintEvent(self, event):
    # Setup painter with antialiasing
    p.begin(self)
    p.setRenderHint(QPainter.Antialiasing)

    # Apply transformations
    p.scale(self.scale, self.scale)
    p.translate(self.offset_to_center())

    # Draw pixmap (with optional overlay)
    p.drawPixmap(0, 0, temp)

    # Draw all shapes
    for shape in self.shapes:
        if self.isVisible(shape):
            shape.fill = shape.selected or shape == self.h_shape
            shape.paint(p)

    # Draw current drawing-in-progress
    if self.current:
        self.current.paint(p)
        self.line.paint(p)

    # Draw preview rectangle while drawing
    if self.current and len(self.line) == 2:
        p.drawRect(...)

    # Draw crosshairs while drawing
    if self.drawing() and not self.prev_point.isNull():
        p.drawLine(...)  # vertical
        p.drawLine(...)  # horizontal

    # Set background color (green if verified)
    p.end()
```

## Vertex and Shape Detection

### Finding Nearest Vertex

```python
# In mouseMoveEvent, for each shape:
index = shape.nearest_vertex(pos, self.epsilon)
if index is not None:
    # Vertex found within epsilon pixels
    self.h_vertex, self.h_shape = index, shape
    shape.highlight_vertex(index, shape.MOVE_VERTEX)
```

### Checking Point Inside Shape

```python
elif shape.contains_point(pos):
    # Point is inside shape boundaries
    self.h_vertex, self.h_shape = None, shape
```

## Bounded Movement

### Moving Entire Shape

```python
def bounded_move_shape(self, shape, pos):
    # Check if movement would go outside pixmap
    if self.out_of_pixmap(pos):
        return False

    # Check corners after applying offsets
    o1 = pos + self.offsets[0]  # top-left
    o2 = pos + self.offsets[1]  # bottom-right

    # Clamp to boundaries
    if self.out_of_pixmap(o1):
        pos -= QPointF(min(0, o1.x()), min(0, o1.y()))
    if self.out_of_pixmap(o2):
        pos += QPointF(min(0, self.pixmap.width() - o2.x()),
                       min(0, self.pixmap.height() - o2.y()))

    # Apply movement
    dp = pos - self.prev_point
    if dp:
        shape.move_by(dp)
        self.prev_point = pos
```

### Moving Single Vertex

```python
def bounded_move_vertex(self, pos):
    index, shape = self.h_vertex, self.h_shape
    point = shape[index]

    # Clip position to pixmap
    if self.out_of_pixmap(pos):
        pos = QPointF(clipped_x, clipped_y)

    # Handle square constraint
    if self.draw_square:
        # Calculate equal-sided dimensions
        ...

    # Move vertex and adjacent vertices
    shape.move_vertex_by(index, shift_pos)

    # Update adjacent vertices to maintain rectangle
    left_index = (index + 1) % 4
    right_index = (index + 3) % 4
    shape.move_vertex_by(right_index, right_shift)
    shape.move_vertex_by(left_index, left_shift)
```

## Keyboard Handling

```python
def keyPressEvent(self, ev):
    key = ev.key()

    if key == Qt.Key_Escape and self.current:
        # Cancel current drawing
        self.current = None
        self.drawingPolygon.emit(False)

    elif key == Qt.Key_Return and self.can_close_shape():
        # Finalize current shape
        self.finalise()

    elif key in [Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down]:
        # Move selected shape by 1 pixel
        if self.selected_shape:
            self.move_one_pixel(direction)
```

## Zoom and Pan

### Mouse Wheel Handling

```python
def wheelEvent(self, ev):
    mods = ev.modifiers()

    if Qt.ControlModifier | Qt.ShiftModifier == mods:
        # Ctrl+Shift+Wheel: brightness
        self.lightRequest.emit(v_delta)

    elif Qt.ControlModifier == mods:
        # Ctrl+Wheel: zoom
        self.zoomRequest.emit(v_delta)

    else:
        # Regular wheel: scroll
        self.scrollRequest.emit(v_delta, Qt.Vertical)
```

### Pan Implementation

```python
# In mousePressEvent (no shape selected):
QApplication.setOverrideCursor(QCursor(Qt.OpenHandCursor))
self.pan_initial_pos = ev.pos()

# In mouseMoveEvent:
delta = ev.pos() - self.pan_initial_pos
self.scrollRequest.emit(delta.x(), Qt.Horizontal)
self.scrollRequest.emit(delta.y(), Qt.Vertical)
```

## Key Methods Reference

| Method | Line | Description |
|--------|------|-------------|
| `__init__` | 37-70 | Initialize canvas state |
| `set_editing` | 94-100 | Switch between modes |
| `mouseMoveEvent` | 111-256 | Handle mouse movement |
| `mousePressEvent` | 258-276 | Handle mouse clicks |
| `mouseReleaseEvent` | 278-298 | Handle mouse release |
| `handle_drawing` | 322-340 | Process drawing actions |
| `select_shape_point` | 363-376 | Find shape at point |
| `bounded_move_shape` | 436-456 | Move shape within bounds |
| `bounded_move_vertex` | 400-434 | Move vertex within bounds |
| `paintEvent` | 495-555 | Render canvas contents |
| `transform_pos` | 557-559 | Coordinate transformation |
| `finalise` | 574-587 | Complete current shape |
| `load_pixmap` | 708-711 | Load new image |
| `load_shapes` | 713-716 | Load annotation shapes |

## Cursor States

| State | Cursor | Trigger |
|-------|--------|---------|
| Default | Arrow | No hover, editing mode |
| Drawing | Cross | CREATE mode active |
| Vertex hover | Pointing hand | Mouse near vertex |
| Shape hover | Open hand | Mouse inside shape |
| Moving | Closed hand | Dragging shape/vertex |

## Integration with MainWindow

```python
# In MainWindow.__init__:
self.canvas = Canvas(parent=self)

# Connect signals
self.canvas.zoomRequest.connect(self.zoom_request)
self.canvas.lightRequest.connect(self.light_request)
self.canvas.scrollRequest.connect(self.scroll_request)
self.canvas.newShape.connect(self.new_shape)
self.canvas.shapeMoved.connect(self.set_dirty)
self.canvas.selectionChanged.connect(self.shape_selection_changed)
self.canvas.drawingPolygon.connect(self.toggle_drawing_sensitive)
```
