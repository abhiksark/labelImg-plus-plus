# LabelFile Component

LabelFile is the orchestration layer that coordinates annotation saving across different formats.

**File:** `libs/labelFile.py` (lines 28-175)

## Overview

LabelFile provides:
- Format enumeration for supported annotation types
- Save methods that dispatch to format-specific writers
- Coordinate conversion utilities
- Verification state tracking

## Format Enumeration

```python
class LabelFileFormat(Enum):
    PASCAL_VOC = 1   # XML format
    YOLO = 2         # Text format with normalized coordinates
    CREATE_ML = 3    # JSON format (Apple)
```

## Class Definition

```python
class LabelFile(object):
    # Default file extension (can be changed)
    suffix = XML_EXT  # '.xml'

    def __init__(self, filename=None):
        self.shapes = ()
        self.image_path = None
        self.image_data = None
        self.verified = False
```

## Format Dispatch Architecture

```
MainWindow.save_labels(annotation_file_path)
         |
         v
    label_file_format?
         |
    +----+----+----+
    |         |    |
    v         v    v
PASCAL_VOC  YOLO  CREATE_ML
    |         |    |
    v         v    v
save_       save_  save_
pascal_     yolo_  create_
voc_        format ml_
format             format
    |         |    |
    v         v    v
PascalVoc  YOLO   CreateML
Writer     Writer Writer
    |         |    |
    v         v    v
  .xml     .txt   .json
          + classes.txt
```

## Save Methods

### PASCAL VOC Format

```python
def save_pascal_voc_format(self, filename, shapes, image_path, image_data,
                           line_color=None, fill_color=None, database_src=None):
    """Save annotations in PASCAL VOC XML format.

    Args:
        filename: Output file path
        shapes: List of shape dicts with label, points, difficult
        image_path: Path to source image
        image_data: QImage or raw image data
        line_color: Optional line color
        fill_color: Optional fill color
        database_src: Optional database source name

    File output: XML with bounding boxes as (xmin, ymin, xmax, ymax)
    """
    # Get image info
    img_folder_name = os.path.split(img_folder_path)[-1]
    img_file_name = os.path.basename(image_path)

    # Load image dimensions
    image = QImage()
    image.load(image_path)
    image_shape = [image.height(), image.width(),
                   1 if image.isGrayscale() else 3]

    # Create writer
    writer = PascalVocWriter(img_folder_name, img_file_name,
                             image_shape, local_img_path=image_path)
    writer.verified = self.verified

    # Add each shape
    for shape in shapes:
        points = shape['points']
        label = shape['label']
        difficult = int(shape['difficult'])
        bnd_box = LabelFile.convert_points_to_bnd_box(points)
        writer.add_bnd_box(bnd_box[0], bnd_box[1],
                          bnd_box[2], bnd_box[3], label, difficult)

    writer.save(target_file=filename)
```

### YOLO Format

```python
def save_yolo_format(self, filename, shapes, image_path, image_data, class_list,
                     line_color=None, fill_color=None, database_src=None):
    """Save annotations in YOLO text format.

    Args:
        filename: Output file path
        shapes: List of shape dicts
        image_path: Path to source image
        image_data: QImage or raw image data
        class_list: List of class names (for indexing)

    File output:
        - {filename}.txt: class_id x_center y_center width height
        - classes.txt: class names, one per line
    """
    # Similar setup to VOC...
    writer = YOLOWriter(img_folder_name, img_file_name,
                        image_shape, local_img_path=image_path)

    for shape in shapes:
        # Convert to bounding box
        bnd_box = LabelFile.convert_points_to_bnd_box(points)
        writer.add_bnd_box(...)

    # Pass class_list for consistent indexing
    writer.save(target_file=filename, class_list=class_list)
```

### CreateML Format

```python
def save_create_ml_format(self, filename, shapes, image_path, image_data,
                          class_list, line_color=None, fill_color=None,
                          database_src=None):
    """Save annotations in Apple CreateML JSON format.

    Args:
        filename: Output file path
        shapes: List of shape dicts
        image_path: Path to source image
        image_data: QImage or raw image data
        class_list: List of class names

    File output: JSON array with center-based coordinates
    """
    writer = CreateMLWriter(img_folder_name, img_file_name,
                            image_shape, shapes, filename,
                            local_img_path=image_path)
    writer.verified = self.verified
    writer.write()
```

## Coordinate Conversion

### Points to Bounding Box

```python
@staticmethod
def convert_points_to_bnd_box(points):
    """Convert polygon points to bounding box coordinates.

    Args:
        points: List of (x, y) tuples or QPointF objects

    Returns:
        Tuple (x_min, y_min, x_max, y_max) as integers

    Note: Minimum values are clamped to 1 for Faster R-CNN compatibility.
    """
    x_min = float('inf')
    y_min = float('inf')
    x_max = float('-inf')
    y_max = float('-inf')

    for p in points:
        x = p[0]  # Works with tuple or QPointF
        y = p[1]
        x_min = min(x, x_min)
        y_min = min(y, y_min)
        x_max = max(x, x_max)
        y_max = max(y, y_max)

    # Clamp minimums to 1 (Faster R-CNN requirement)
    if x_min < 1:
        x_min = 1
    if y_min < 1:
        y_min = 1

    return int(x_min), int(y_min), int(x_max), int(y_max)
```

### Coordinate Flow

```
Shape.points (4 QPointF)           convert_points_to_bnd_box()
[(x0,y0), (x1,y1),        ------>  (xmin, ymin, xmax, ymax)
 (x2,y2), (x3,y3)]                  integers, 1-indexed min

    points[0]         points[1]           xmin = min(x0,x1,x2,x3)
         +----------------+               ymin = min(y0,y1,y2,y3)
         |                |      --->     xmax = max(x0,x1,x2,x3)
         |                |               ymax = max(y0,y1,y2,y3)
         +----------------+
    points[3]         points[2]
```

## Verification State

```python
def toggle_verify(self):
    """Toggle verification status."""
    self.verified = not self.verified
```

The verified flag:
- Indicates annotation has been reviewed
- Persisted in PASCAL VOC as `<annotation verified="yes">`
- Persisted in CreateML as `"verified": true`
- Visual feedback: Green canvas background when verified

## Static Methods

### Check Label File

```python
@staticmethod
def is_label_file(filename):
    """Check if file has label file extension."""
    file_suffix = os.path.splitext(filename)[1].lower()
    return file_suffix == LabelFile.suffix
```

## Usage in MainWindow

### Saving

```python
# In MainWindow.save_labels():
def save_labels(self, annotation_file_path):
    if self.label_file is None:
        self.label_file = LabelFile()
        self.label_file.verified = self.canvas.verified

    # Format shapes
    shapes = [format_shape(shape) for shape in self.canvas.shapes]

    # Route by format
    if self.label_file_format == LabelFileFormat.PASCAL_VOC:
        self.label_file.save_pascal_voc_format(...)
    elif self.label_file_format == LabelFileFormat.YOLO:
        self.label_file.save_yolo_format(..., class_list=self.label_hist)
    elif self.label_file_format == LabelFileFormat.CREATE_ML:
        self.label_file.save_create_ml_format(...)
```

### Format Switching

```python
# In MainWindow:
def set_format(self, save_format):
    if save_format == FORMAT_PASCALVOC:
        self.label_file_format = LabelFileFormat.PASCAL_VOC
        LabelFile.suffix = XML_EXT  # '.xml'
    elif save_format == FORMAT_YOLO:
        self.label_file_format = LabelFileFormat.YOLO
        LabelFile.suffix = TXT_EXT  # '.txt'
    elif save_format == FORMAT_CREATEML:
        self.label_file_format = LabelFileFormat.CREATE_ML
        LabelFile.suffix = JSON_EXT  # '.json'
```

## Shape Dict Format

The shapes parameter passed to save methods is a list of dictionaries:

```python
{
    'label': str,           # Class label
    'line_color': tuple,    # (R, G, B, A)
    'fill_color': tuple,    # (R, G, B, A)
    'points': list,         # [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    'difficult': bool       # Difficult flag
}
```

## Method Reference

| Method | Line | Description |
|--------|------|-------------|
| `__init__` | 33-37 | Initialize state |
| `save_pascal_voc_format` | 54-82 | Save as VOC XML |
| `save_yolo_format` | 84-112 | Save as YOLO text |
| `save_create_ml_format` | 39-51 | Save as CreateML JSON |
| `toggle_verify` | 114-115 | Toggle verification |
| `is_label_file` | 147-149 | Check file extension |
| `convert_points_to_bnd_box` | 152-174 | Convert points to bbox |

## Error Handling

```python
class LabelFileError(Exception):
    pass

# Used in MainWindow for error display:
try:
    self.label_file.save_pascal_voc_format(...)
except LabelFileError as e:
    self.error_message(u'Error saving label data', u'<b>%s</b>' % e)
```
