# Shape Component

The Shape class represents a single bounding box annotation with its label, coordinates, and visual properties.

**File:** `libs/shape.py` (lines 23-210)

## Overview

Shape is a data container and renderer for bounding box annotations:
- Stores 4-point polygon coordinates
- Holds label text and metadata (difficult flag)
- Provides methods for painting, hit-testing, and manipulation
- Manages visual state (selection, highlighting)

## Class Variables (Shared State)

```python
# Default colors (RGBA)
line_color = DEFAULT_LINE_COLOR       # QColor(0, 255, 0, 128) - green
fill_color = DEFAULT_FILL_COLOR       # QColor(255, 0, 0, 128) - red
select_line_color = DEFAULT_SELECT_LINE_COLOR   # white
select_fill_color = DEFAULT_SELECT_FILL_COLOR   # light blue
vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR   # green
h_vertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR # red (highlight)

# Vertex rendering
point_type = P_ROUND    # P_SQUARE or P_ROUND
point_size = 16

# Set by Canvas before painting
scale = 1.0
label_font_size = 8
```

## Instance Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `label` | str | None | Class label text |
| `points` | list[QPointF] | [] | Corner coordinates |
| `fill` | bool | False | Fill shape interior |
| `selected` | bool | False | Selection state |
| `difficult` | bool | False | Difficult object flag |
| `paint_label` | bool | False | Draw label on canvas |
| `_closed` | bool | False | Polygon is closed |
| `_highlight_index` | int | None | Highlighted vertex |
| `_highlight_mode` | int | None | Highlight type |

## Point Structure

```
    points[0]                points[1]
    (x_min, y_min)           (x_max, y_min)
    Top-Left                 Top-Right
         +------------------------+
         |                        |
         |    "Label Text"        |  <-- Label drawn here
         |    (if paint_label)    |      if paint_label=True
         |                        |
         |                        |
         +------------------------+
    points[3]                points[2]
    (x_min, y_max)           (x_max, y_max)
    Bottom-Left              Bottom-Right

Points are stored in CLOCKWISE order starting from top-left.
Rectangle edges: 0->1 (top), 1->2 (right), 2->3 (bottom), 3->0 (left)
```

## Constructor

```python
def __init__(self, label=None, line_color=None, difficult=False, paint_label=False):
    self.label = label
    self.points = []
    self.fill = False
    self.selected = False
    self.difficult = difficult
    self.paint_label = paint_label
    self._closed = False

    # Override class colors if provided
    if line_color is not None:
        self.line_color = line_color
    else:
        self.line_color = Shape.line_color
```

## Point Management

### Adding Points

```python
def add_point(self, point):
    """Add point if shape not complete (max 4 points for rectangle)."""
    if self.points and point == self.points[0]:
        self.close()
    else:
        self.points.append(point)

def reach_max_points(self):
    """Check if shape has maximum points (4 for rectangle)."""
    return len(self.points) >= 4
```

### Accessing Points

```python
def __getitem__(self, key):
    return self.points[key]

def __len__(self):
    return len(self.points)

# Usage:
shape[0]        # First point (top-left)
len(shape)      # Number of points (typically 4)
```

### Modifying Points

```python
def __setitem__(self, key, value):
    self.points[key] = value

def pop_point(self):
    """Remove and return last point."""
    if self.points:
        return self.points.pop()
    return None

# Usage:
shape[0] = QPointF(100, 100)  # Set first point
```

## Movement Methods

### Move Entire Shape

```python
def move_by(self, offset):
    """Translate all points by offset."""
    self.points = [p + offset for p in self.points]

# Usage:
shape.move_by(QPointF(10, 5))  # Move right 10, down 5
```

### Move Single Vertex

```python
def move_vertex_by(self, i, offset):
    """Move vertex at index i by offset."""
    self.points[i] = self.points[i] + offset

# Usage:
shape.move_vertex_by(0, QPointF(-5, 0))  # Move top-left left by 5
```

## Geometry Methods

### Bounding Rectangle

```python
def bounding_rect(self):
    """Return QRectF bounding rectangle."""
    return self.make_path().boundingRect()
```

### Point Containment

```python
def contains_point(self, point):
    """Check if point is inside shape."""
    return self.make_path().contains(point)
```

### Nearest Vertex

```python
def nearest_vertex(self, point, epsilon):
    """Find vertex within epsilon distance of point.

    Returns vertex index or None if no vertex is close enough.
    """
    for i, p in enumerate(self.points):
        if distance(point - p) <= epsilon:
            return i
    return None
```

### QPainterPath Generation

```python
def make_path(self):
    """Create QPainterPath from points."""
    path = QPainterPath(self.points[0])
    for p in self.points[1:]:
        path.lineTo(p)
    return path
```

## Rendering (paint method)

```python
def paint(self, painter):
    """Draw shape on painter."""
    if self.points:
        # Set colors based on selection state
        color = self.select_line_color if self.selected else self.line_color
        pen = QPen(color)
        pen.setWidth(max(1, int(round(2.0 / self.scale))))
        painter.setPen(pen)

        # Create path
        line_path = self.make_path()
        vrt_path = QPainterPath()

        # Draw vertices
        for i, point in enumerate(self.points):
            self.draw_vertex(vrt_path, i)

        # Draw edges
        if self._closed:
            line_path.lineTo(self.points[0])
        painter.drawPath(line_path)

        # Fill if selected/hovered
        if self.fill:
            fill_color = self.select_fill_color if self.selected else self.fill_color
            painter.fillPath(line_path, fill_color)

        # Draw label text
        if self.paint_label:
            min_x = min(p.x() for p in self.points)
            min_y = min(p.y() for p in self.points)
            painter.drawText(min_x, min_y, self.label)
```

### Vertex Drawing

```python
def draw_vertex(self, path, i):
    """Draw single vertex at index i."""
    d = self.point_size / self.scale
    shape = self.point_type
    point = self.points[i]

    # Determine fill color
    if self._highlight_index is not None and self._highlight_index == i:
        size = self.point_size + 8  # Larger when highlighted
        fill_color = self.h_vertex_fill_color
    else:
        size = self.point_size
        fill_color = self.vertex_fill_color

    # Draw circle or square
    if shape == self.P_SQUARE:
        path.addRect(point.x() - d/2, point.y() - d/2, d, d)
    elif shape == self.P_ROUND:
        path.addEllipse(point, d/2, d/2)
```

## Highlighting

```python
# Highlight modes
NEAR_VERTEX = 1     # Cursor near vertex (visual cue)
MOVE_VERTEX = 2     # Vertex being moved

def highlight_vertex(self, i, action):
    """Mark vertex for highlighting."""
    self._highlight_index = i
    self._highlight_mode = action

def highlight_clear(self):
    """Clear highlight state."""
    self._highlight_index = None
    self._highlight_mode = None
```

## Shape State

### Closing/Opening

```python
def close(self):
    """Mark shape as closed (complete)."""
    self._closed = True

def set_open(self):
    """Mark shape as open (incomplete)."""
    self._closed = False

def is_closed(self):
    return self._closed
```

## Copying

```python
def copy(self):
    """Create deep copy of shape."""
    shape = Shape(
        label=self.label,
        difficult=self.difficult,
        paint_label=self.paint_label
    )
    shape.points = [p for p in self.points]
    shape.fill = self.fill
    shape.selected = self.selected
    shape._closed = self._closed
    shape.line_color = self.line_color
    shape.fill_color = self.fill_color
    return shape
```

## Usage in Canvas

### Creating New Shape

```python
# In Canvas.handle_drawing():
if not self.out_of_pixmap(pos):
    self.current = Shape()
    self.current.add_point(pos)
```

### Completing Shape

```python
# In Canvas.finalise():
self.current.close()
self.shapes.append(self.current)
self.newShape.emit()
```

### Setting Label

```python
# In Canvas.set_last_label():
self.shapes[-1].label = text
if line_color:
    self.shapes[-1].line_color = line_color
```

## Serialization Format

When saving annotations, shapes are serialized as:

```python
# In MainWindow.save_labels():
def format_shape(s):
    return dict(
        label=s.label,
        line_color=s.line_color.getRgb(),  # (R, G, B, A) tuple
        fill_color=s.fill_color.getRgb(),
        points=[(p.x(), p.y()) for p in s.points],  # List of (x, y)
        difficult=s.difficult
    )
```

When loading annotations, shapes are deserialized as:

```python
# In MainWindow.load_labels():
# shapes is list of tuples: (label, points, line_color, fill_color, difficult)
for label, points, line_color, fill_color, difficult in shapes:
    shape = Shape(label=label)
    for x, y in points:
        shape.add_point(QPointF(x, y))
    shape.difficult = difficult
    shape.close()
```

## Method Reference

| Method | Line | Description |
|--------|------|-------------|
| `__init__` | 41-62 | Initialize shape state |
| `add_point` | 72-77 | Add point to polygon |
| `pop_point` | 79-82 | Remove last point |
| `reach_max_points` | 67-69 | Check if 4 points |
| `paint` | 87-135 | Render shape |
| `draw_vertex` | 137-152 | Render single vertex |
| `nearest_vertex` | 155-162 | Find vertex near point |
| `contains_point` | 164-165 | Point inside test |
| `make_path` | 167-171 | Create QPainterPath |
| `bounding_rect` | 173-174 | Get bounding QRectF |
| `move_by` | 176-177 | Translate all points |
| `move_vertex_by` | 179-180 | Move single vertex |
| `highlight_vertex` | 182-184 | Set highlight state |
| `highlight_clear` | 186-188 | Clear highlight |
| `copy` | 189-200 | Deep copy shape |
| `close` | 202-203 | Mark as complete |
| `set_open` | 205-206 | Mark as incomplete |
