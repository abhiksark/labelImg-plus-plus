# YOLO Format

YOLO format uses normalized center-based coordinates in plain text files, designed for YOLO object detection frameworks.

**Files:** `libs/yolo_io.py` (lines 11-143)

## File Structure

Each image has a corresponding `.txt` file, plus a shared `classes.txt`:
```
dataset/
├── images/
│   ├── image001.jpg
│   └── image002.jpg
├── labels/
│   ├── image001.txt
│   ├── image002.txt
│   └── classes.txt
```

## Annotation Format

### Label File (.txt)

```
0 0.453125 0.416667 0.234375 0.333333
1 0.734375 0.583333 0.328125 0.416667
```

Each line: `class_id x_center y_center width height`

| Field | Description | Range |
|-------|-------------|-------|
| `class_id` | 0-based class index | 0 to num_classes-1 |
| `x_center` | Center X (normalized) | 0.0 to 1.0 |
| `y_center` | Center Y (normalized) | 0.0 to 1.0 |
| `width` | Box width (normalized) | 0.0 to 1.0 |
| `height` | Box height (normalized) | 0.0 to 1.0 |

### Classes File (classes.txt)

```
cat
dog
person
car
```

One class name per line, order determines class_id (0-indexed).

## Coordinate System

```
Normalized Coordinates (0.0 to 1.0)
+---------------------------+ (1.0, 0.0)
|                           |
|        (x_center,         |
|         y_center)         |
|            *              |
|         +-----+           |
|         |     | height    |
|         +-----+           |
|          width            |
|                           |
+---------------------------+ (1.0, 1.0)
(0.0, 1.0)

All values are relative to image dimensions:
  x_center = absolute_x / image_width
  y_center = absolute_y / image_height
  width = absolute_width / image_width
  height = absolute_height / image_height
```

## Conversion Formulas

### Pixel to YOLO

```python
# From corner coordinates (xmin, ymin, xmax, ymax)
x_center = (xmin + xmax) / 2 / image_width
y_center = (ymin + ymax) / 2 / image_height
width = (xmax - xmin) / image_width
height = (ymax - ymin) / image_height
```

### YOLO to Pixel

```python
# From normalized (x_center, y_center, width, height)
xmin = (x_center - width/2) * image_width
ymin = (y_center - height/2) * image_height
xmax = (x_center + width/2) * image_width
ymax = (y_center + height/2) * image_height
```

## Writer Class

**File:** `libs/yolo_io.py` (lines 11-77)

```python
class YOLOWriter:
    def __init__(self, folder_name, filename, img_size, ...):
        self.img_size = img_size  # (height, width, depth)
        self.box_list = []

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        """Add bounding box (difficult flag stored but not written)."""
        self.box_list.append({
            'xmin': x_min, 'ymin': y_min,
            'xmax': x_max, 'ymax': y_max,
            'name': name, 'difficult': difficult
        })

    def bnd_box_to_yolo_line(self, box, class_list):
        """Convert box to YOLO format line."""
        x_center = (box['xmin'] + box['xmax']) / 2 / self.img_size[1]
        y_center = (box['ymin'] + box['ymax']) / 2 / self.img_size[0]
        w = (box['xmax'] - box['xmin']) / self.img_size[1]
        h = (box['ymax'] - box['ymin']) / self.img_size[0]

        # Get or add class index
        if box['name'] not in class_list:
            class_list.append(box['name'])
        class_index = class_list.index(box['name'])

        return class_index, x_center, y_center, w, h

    def save(self, class_list=[], target_file=None):
        """Write .txt and classes.txt files."""
        for box in self.box_list:
            class_idx, x, y, w, h = self.bnd_box_to_yolo_line(box, class_list)
            out_file.write("%d %.6f %.6f %.6f %.6f\n" % (class_idx, x, y, w, h))

        # Write classes.txt
        for c in class_list:
            out_class_file.write(c + '\n')
```

## Reader Class

**File:** `libs/yolo_io.py` (lines 81-143)

```python
class YoloReader:
    def __init__(self, file_path, image, class_list_path=None):
        self.file_path = file_path
        self.img_size = [image.height(), image.width(), ...]

        # Load classes.txt from same directory
        self.class_list_path = class_list_path or \
            os.path.join(os.path.dirname(file_path), "classes.txt")
        self.classes = open(self.class_list_path).read().strip().split('\n')

        self.shapes = []
        self.verified = False
        self.parse_yolo_format()

    def yolo_line_to_shape(self, class_index, x_center, y_center, w, h):
        """Convert YOLO line to pixel coordinates."""
        label = self.classes[int(class_index)]

        # Denormalize and clamp
        x_min = max(float(x_center) - float(w) / 2, 0)
        x_max = min(float(x_center) + float(w) / 2, 1)
        y_min = max(float(y_center) - float(h) / 2, 0)
        y_max = min(float(y_center) + float(h) / 2, 1)

        # Scale to image size
        x_min = round(self.img_size[1] * x_min)
        x_max = round(self.img_size[1] * x_max)
        y_min = round(self.img_size[0] * y_min)
        y_max = round(self.img_size[0] * y_max)

        return label, x_min, y_min, x_max, y_max

    def parse_yolo_format(self):
        for line in open(self.file_path):
            class_idx, x, y, w, h = line.strip().split(' ')
            label, xmin, ymin, xmax, ymax = self.yolo_line_to_shape(...)
            # Note: difficult=False always (not preserved)
            self.add_shape(label, xmin, ymin, xmax, ymax, False)
```

## Usage Example

### Writing

```python
from libs.yolo_io import YOLOWriter

writer = YOLOWriter(
    folder_name='images',
    filename='test.jpg',
    img_size=(600, 800, 3)  # height, width, depth
)

# Class list maintains consistent indexing
class_list = ['cat', 'dog', 'person']

writer.add_bnd_box(100, 150, 400, 450, 'cat', difficult=0)
writer.add_bnd_box(450, 200, 750, 550, 'dog', difficult=1)
writer.save(class_list=class_list, target_file='test.txt')

# Creates:
#   test.txt with normalized coordinates
#   classes.txt with class names
```

### Reading

```python
from libs.yolo_io import YoloReader
from PyQt5.QtGui import QImage

image = QImage('test.jpg')
reader = YoloReader('test.txt', image)
shapes = reader.get_shapes()

for label, points, _, _, difficult in shapes:
    print(f"Label: {label}")
    print(f"Corners: {points}")
    # Note: difficult is always False
```

## Important Notes

### Difficult Flag Lost

```
WARNING: The difficult flag is NOT preserved in YOLO format.
- When saving: difficult flag is stored but not written to file
- When loading: difficult is always set to False
```

### Class List Management

```
WARNING: classes.txt is rewritten on each save.
- Class order may change if not using predefined classes
- Use data/predefined_classes.txt for consistent ordering
- Classes are added to list if not already present
```

### Precision

- Values written with 6 decimal places
- Rounding occurs during read (normalized → pixels)
- Small pixel variations possible due to float math

## Integration with LabelFile

```python
# In LabelFile.save_yolo_format():
def save_yolo_format(self, filename, shapes, image_path, image_data,
                     class_list, ...):
    writer = YOLOWriter(folder_name, file_name, image_shape)

    for shape in shapes:
        bnd_box = LabelFile.convert_points_to_bnd_box(shape['points'])
        writer.add_bnd_box(
            bnd_box[0], bnd_box[1],
            bnd_box[2], bnd_box[3],
            shape['label'],
            int(shape['difficult'])
        )

    # class_list comes from MainWindow.label_hist
    writer.save(target_file=filename, class_list=class_list)
```

## Compatibility

Works with:
- Darknet YOLO
- Ultralytics YOLOv5/v8
- Any framework expecting normalized center format
