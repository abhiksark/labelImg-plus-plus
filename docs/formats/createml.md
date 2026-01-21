# CreateML Format

CreateML format is Apple's JSON-based annotation format for training object detection models on iOS and macOS.

**Files:** `libs/create_ml_io.py` (lines 13-135)

## File Structure

Single JSON file contains annotations for multiple images:
```
dataset/
├── images/
│   ├── image001.jpg
│   ├── image002.jpg
│   └── image003.jpg
└── annotations.json
```

## JSON Schema

```json
[
    {
        "image": "image001.jpg",
        "verified": true,
        "annotations": [
            {
                "label": "cat",
                "coordinates": {
                    "x": 250,
                    "y": 300,
                    "width": 300,
                    "height": 300
                }
            },
            {
                "label": "dog",
                "coordinates": {
                    "x": 600,
                    "y": 375,
                    "width": 300,
                    "height": 350
                }
            }
        ]
    },
    {
        "image": "image002.jpg",
        "verified": false,
        "annotations": [
            {
                "label": "person",
                "coordinates": {
                    "x": 400,
                    "y": 300,
                    "width": 200,
                    "height": 400
                }
            }
        ]
    }
]
```

## Element Reference

| Field | Type | Description |
|-------|------|-------------|
| `image` | string | Image filename (not full path) |
| `verified` | boolean | Annotation review status |
| `annotations` | array | List of annotation objects |
| `label` | string | Class name |
| `coordinates.x` | number | Center X (pixels) |
| `coordinates.y` | number | Center Y (pixels) |
| `coordinates.width` | number | Box width (pixels) |
| `coordinates.height` | number | Box height (pixels) |

## Coordinate System

```
Pixel Center Coordinates
+---------------------------+
|                           |
|         (x, y)            |
|            *              |
|       +--------+          |
|       |        |          |
|       | object | height   |
|       |        |          |
|       +--------+          |
|         width             |
|                           |
+---------------------------+

x, y = center point in pixels
width, height = dimensions in pixels
```

## Conversion Formulas

### Corner to Center

```python
# From (xmin, ymin, xmax, ymax)
width = xmax - xmin
height = ymax - ymin
x = xmin + width / 2
y = ymin + height / 2
```

### Center to Corner

```python
# From (x, y, width, height)
xmin = x - width / 2
ymin = y - height / 2
xmax = x + width / 2
ymax = y + height / 2
```

## Writer Class

**File:** `libs/create_ml_io.py` (lines 13-93)

```python
class CreateMLWriter:
    def __init__(self, folder_name, filename, img_size, shapes,
                 output_file, ...):
        self.filename = filename
        self.shapes = shapes
        self.output_file = output_file
        self.verified = False

    def write(self):
        """Write or update JSON file."""
        # Load existing file if present
        if os.path.isfile(self.output_file):
            output_dict = json.loads(open(self.output_file).read())
        else:
            output_dict = []

        # Create image entry
        output_image_dict = {
            "image": self.filename,
            "verified": self.verified,
            "annotations": []
        }

        # Convert each shape
        for shape in self.shapes:
            points = shape["points"]
            x1, y1 = points[0]
            x2 = points[1][0]
            y2 = points[2][1]

            height, width, x, y = self.calculate_coordinates(x1, x2, y1, y2)

            output_image_dict["annotations"].append({
                "label": shape["label"],
                "coordinates": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height
                }
            })

        # Update or append image entry
        exists = False
        for i, entry in enumerate(output_dict):
            if entry["image"] == self.filename:
                output_dict[i] = output_image_dict
                exists = True
                break

        if not exists:
            output_dict.append(output_image_dict)

        # Write JSON
        Path(self.output_file).write_text(json.dumps(output_dict))

    def calculate_coordinates(self, x1, x2, y1, y2):
        """Calculate center coordinates from corners."""
        xmin, xmax = (x1, x2) if x1 < x2 else (x2, x1)
        ymin, ymax = (y1, y2) if y1 < y2 else (y2, y1)

        width = xmax - xmin
        height = ymax - ymin
        x = xmin + width / 2
        y = ymin + height / 2

        return height, width, x, y
```

## Reader Class

**File:** `libs/create_ml_io.py` (lines 96-135)

```python
class CreateMLReader:
    def __init__(self, json_path, file_path):
        self.json_path = json_path
        self.filename = os.path.basename(file_path)
        self.shapes = []
        self.verified = False
        self.parse_json()

    def parse_json(self):
        """Parse JSON and extract shapes for current image."""
        output_list = json.loads(open(self.json_path).read())

        if output_list:
            self.verified = output_list[0].get("verified", False)

        for image in output_list:
            if image["image"] == self.filename:
                for shape in image["annotations"]:
                    self.add_shape(shape["label"], shape["coordinates"])

    def add_shape(self, label, bnd_box):
        """Convert center coordinates to corner points."""
        x_min = bnd_box["x"] - (bnd_box["width"] / 2)
        y_min = bnd_box["y"] - (bnd_box["height"] / 2)
        x_max = bnd_box["x"] + (bnd_box["width"] / 2)
        y_max = bnd_box["y"] + (bnd_box["height"] / 2)

        points = [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max)
        ]
        # Note: difficult is hardcoded to True
        self.shapes.append((label, points, None, None, True))

    def get_shapes(self):
        return self.shapes
```

## Usage Example

### Writing

```python
from libs.create_ml_io import CreateMLWriter

shapes = [
    {
        'label': 'cat',
        'points': [(100, 150), (400, 150), (400, 450), (100, 450)]
    },
    {
        'label': 'dog',
        'points': [(450, 200), (750, 200), (750, 550), (450, 550)]
    }
]

writer = CreateMLWriter(
    folder_name='images',
    filename='test.jpg',
    img_size=(600, 800, 3),
    shapes=shapes,
    output_file='annotations.json'
)
writer.verified = True
writer.write()
```

### Reading

```python
from libs.create_ml_io import CreateMLReader

reader = CreateMLReader('annotations.json', 'images/test.jpg')
shapes = reader.get_shapes()

for label, points, _, _, difficult in shapes:
    print(f"Label: {label}")
    print(f"Corners: {points}")
    # Note: difficult is always True
```

## Important Notes

### Aggregated File

```
NOTE: CreateML uses a single JSON file for all images.
- Saving updates existing entry or appends new one
- File is read and rewritten on each save
- Order of images may change
```

### Difficult Flag Behavior

```
WARNING: Difficult flag handling is inconsistent.
- When saving: difficult flag is not written
- When loading: difficult is hardcoded to True
```

### File Matching

The reader matches images by filename only (not path):
```python
if image["image"] == self.filename:  # Just the filename
```

### Verified Flag

Only the first image's verified status is used when reading:
```python
self.verified = output_list[0].get("verified", False)
```

## Integration with LabelFile

```python
# In LabelFile.save_create_ml_format():
def save_create_ml_format(self, filename, shapes, image_path, ...):
    img_file_name = os.path.basename(image_path)

    writer = CreateMLWriter(
        folder_name,
        img_file_name,
        image_shape,
        shapes,     # Pass shapes directly (not converted)
        filename,   # Output JSON path
        local_img_path=image_path
    )
    writer.verified = self.verified
    writer.write()
```

## Compatibility

Works with:
- Apple Create ML
- Turi Create
- Core ML model training
