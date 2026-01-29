# Adding New Annotation Formats

Step-by-step guide for adding a new annotation format to labelImg++.

## Overview

Adding a new format requires modifications to:

1. Create `libs/new_format_io.py` - Reader/Writer classes
2. Update `libs/labelFile.py` - Format enum and dispatch
3. Update `labelImgPlusPlus.py` - Format toggle UI

```
+----------------------------------------------------------+
|                  Format Integration                       |
+----------------------------------------------------------+
|                                                          |
|  Step 1: I/O Classes                                     |
|  +--------------------------------------------------+   |
|  |  libs/new_format_io.py                            |   |
|  |  +--------------------+  +--------------------+   |   |
|  |  | NewFormatWriter    |  | NewFormatReader    |   |   |
|  |  | - add_bnd_box()    |  | - parse_format()   |   |   |
|  |  | - save()           |  | - get_shapes()     |   |   |
|  |  +--------------------+  +--------------------+   |   |
|  +--------------------------------------------------+   |
|                         |                               |
|                         v                               |
|  Step 2: LabelFile Integration                          |
|  +--------------------------------------------------+   |
|  |  libs/labelFile.py                                |   |
|  |  - Add to LabelFileFormat enum                    |   |
|  |  - Add save_new_format() method                   |   |
|  |  - Add dispatch case in save()                    |   |
|  +--------------------------------------------------+   |
|                         |                               |
|                         v                               |
|  Step 3: UI Integration                                 |
|  +--------------------------------------------------+   |
|  |  labelImgPlusPlus.py                                      |   |
|  |  - Add format icon                                |   |
|  |  - Update change_format()                         |   |
|  |  - Update load_labels()                           |   |
|  +--------------------------------------------------+   |
|                                                          |
+----------------------------------------------------------+
```

## Step 1: Create I/O Classes

### File Structure

Create `libs/new_format_io.py`:

```python
# libs/new_format_io.py
"""
New Format I/O classes for labelImg++.

Format specification:
- [Describe your format here]
"""
import os
from pathlib import Path


class NewFormatWriter:
    """Writes annotations in NewFormat."""

    def __init__(self, folder_name, filename, img_size, shapes=None,
                 output_file=None, local_img_path=None):
        """Initialize writer.

        Args:
            folder_name: Directory containing images
            filename: Image filename (not full path)
            img_size: Tuple of (height, width, depth)
            shapes: List of shape dictionaries (optional)
            output_file: Output annotation path
            local_img_path: Full path to image
        """
        self.folder_name = folder_name
        self.filename = filename
        self.img_size = img_size  # (height, width, depth)
        self.shapes = shapes or []
        self.output_file = output_file
        self.local_img_path = local_img_path
        self.box_list = []
        self.verified = False

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        """Add bounding box to write list.

        Args:
            x_min, y_min, x_max, y_max: Corner coordinates (pixels)
            name: Class label
            difficult: Difficult flag (bool or int)
        """
        self.box_list.append({
            'xmin': x_min,
            'ymin': y_min,
            'xmax': x_max,
            'ymax': y_max,
            'name': name,
            'difficult': difficult
        })

    def save(self, target_file=None):
        """Write annotation file.

        Args:
            target_file: Override output path
        """
        output_path = target_file or self.output_file

        # TODO: Implement format-specific writing logic
        # Example:
        # with open(output_path, 'w') as f:
        #     for box in self.box_list:
        #         line = format_box(box)
        #         f.write(line + '\n')

        raise NotImplementedError("Implement save() method")


class NewFormatReader:
    """Reads annotations from NewFormat files."""

    def __init__(self, file_path, image=None):
        """Initialize reader.

        Args:
            file_path: Path to annotation file
            image: QImage for dimension reference (optional)
        """
        self.file_path = file_path
        self.shapes = []
        self.verified = False

        if image:
            self.img_size = (image.height(), image.width(),
                           1 if image.isGrayscale() else 3)
        else:
            self.img_size = None

        self.parse_format()

    def parse_format(self):
        """Parse annotation file and populate shapes list."""
        # TODO: Implement format-specific parsing logic
        #
        # For each annotation found:
        #   self.add_shape(label, xmin, ymin, xmax, ymax, difficult)

        raise NotImplementedError("Implement parse_format() method")

    def add_shape(self, label, x_min, y_min, x_max, y_max, difficult):
        """Add parsed shape to shapes list.

        Args:
            label: Class name
            x_min, y_min, x_max, y_max: Corner coordinates (pixels)
            difficult: Difficult flag
        """
        points = [
            (x_min, y_min),
            (x_max, y_min),
            (x_max, y_max),
            (x_min, y_max)
        ]
        self.shapes.append((label, points, None, None, difficult))

    def get_shapes(self):
        """Return parsed shapes.

        Returns:
            List of tuples: (label, points, line_color, fill_color, difficult)
        """
        return self.shapes
```

### Coordinate Handling

Different formats use different coordinate systems:

| Format | Coordinate System |
|--------|------------------|
| PASCAL VOC | Corner pixels (xmin, ymin, xmax, ymax) |
| YOLO | Normalized center (x_center, y_center, width, height) |
| CreateML | Pixel center (x, y, width, height) |

**Conversion Examples:**

```python
# Corner to center (pixels)
def corners_to_center(xmin, ymin, xmax, ymax):
    width = xmax - xmin
    height = ymax - ymin
    x_center = xmin + width / 2
    y_center = ymin + height / 2
    return x_center, y_center, width, height

# Center to corners (pixels)
def center_to_corners(x_center, y_center, width, height):
    xmin = x_center - width / 2
    ymin = y_center - height / 2
    xmax = x_center + width / 2
    ymax = y_center + height / 2
    return xmin, ymin, xmax, ymax

# Normalize coordinates (for YOLO-like formats)
def normalize(xmin, ymin, xmax, ymax, img_width, img_height):
    x_center = (xmin + xmax) / 2 / img_width
    y_center = (ymin + ymax) / 2 / img_height
    width = (xmax - xmin) / img_width
    height = (ymax - ymin) / img_height
    return x_center, y_center, width, height

# Denormalize coordinates
def denormalize(x_center, y_center, width, height, img_width, img_height):
    xmin = (x_center - width / 2) * img_width
    ymin = (y_center - height / 2) * img_height
    xmax = (x_center + width / 2) * img_width
    ymax = (y_center + height / 2) * img_height
    return xmin, ymin, xmax, ymax
```

## Step 2: Update LabelFile

### Add Format Enum

Edit `libs/labelFile.py`:

```python
# At top of file, update enum
class LabelFileFormat(IntEnum):
    PASCAL_VOC = 1
    YOLO = 2
    CREATE_ML = 3
    NEW_FORMAT = 4  # Add your format
```

### Add Save Method

```python
# In LabelFile class
def save_new_format(self, filename, shapes, image_path, image_data,
                    class_list, line_color=None, fill_color=None,
                    database_src=None):
    """Save annotations in NewFormat.

    Args:
        filename: Output annotation file path
        shapes: List of shape dictionaries
        image_path: Path to source image
        image_data: Image bytes (may be None)
        class_list: List of class names
        line_color: Default line color (unused by most formats)
        fill_color: Default fill color (unused by most formats)
        database_src: Database source info (unused by most formats)
    """
    from libs.new_format_io import NewFormatWriter

    # Get image info
    img_folder_path = os.path.dirname(image_path)
    img_folder_name = os.path.split(img_folder_path)[-1]
    img_file_name = os.path.basename(image_path)
    image = QImage()
    image.load(image_path)
    image_shape = [image.height(), image.width(),
                  1 if image.isGrayscale() else 3]

    # Create writer
    writer = NewFormatWriter(
        img_folder_name,
        img_file_name,
        image_shape,
        output_file=filename,
        local_img_path=image_path
    )
    writer.verified = self.verified

    # Add each shape
    for shape in shapes:
        points = shape['points']
        label = shape['label']
        difficult = int(shape['difficult'])
        bnd_box = LabelFile.convert_points_to_bnd_box(points)
        writer.add_bnd_box(
            bnd_box[0], bnd_box[1],  # xmin, ymin
            bnd_box[2], bnd_box[3],  # xmax, ymax
            label, difficult
        )

    # Write file
    writer.save(target_file=filename)
```

### Add Dispatch Cases

```python
# In LabelFile.save_label_file() - add dispatch case
def save_label_file(self, filename, shapes, image_path, ...):
    if self.label_file_format == LabelFileFormat.PASCAL_VOC:
        return self.save_pascal_voc_format(...)
    elif self.label_file_format == LabelFileFormat.YOLO:
        return self.save_yolo_format(...)
    elif self.label_file_format == LabelFileFormat.CREATE_ML:
        return self.save_create_ml_format(...)
    elif self.label_file_format == LabelFileFormat.NEW_FORMAT:
        return self.save_new_format(...)  # Add this
```

## Step 3: Update MainWindow

### Add Format Icon

1. Create icon: `resources/icons/format_newformat.png`
2. Add to `resources.qrc`:

```xml
<qresource>
    <file>icons/format_newformat.png</file>
</qresource>
```

3. Rebuild resources:

```bash
pyrcc5 -o libs/resources.py resources.qrc
```

### Update Format Toggle

Edit `labelImgPlusPlus.py`:

```python
# In get_format_meta() function
def get_format_meta(format):
    if format == LabelFileFormat.PASCAL_VOC:
        return '&PascalVOC', 'format_voc'
    elif format == LabelFileFormat.YOLO:
        return '&YOLO', 'format_yolo'
    elif format == LabelFileFormat.CREATE_ML:
        return '&CreateML', 'format_createml'
    elif format == LabelFileFormat.NEW_FORMAT:  # Add this
        return '&NewFormat', 'format_newformat'

# In change_format() method
def change_format(self):
    if self.label_file_format == LabelFileFormat.PASCAL_VOC:
        self.label_file_format = LabelFileFormat.YOLO
    elif self.label_file_format == LabelFileFormat.YOLO:
        self.label_file_format = LabelFileFormat.CREATE_ML
    elif self.label_file_format == LabelFileFormat.CREATE_ML:
        self.label_file_format = LabelFileFormat.NEW_FORMAT  # Add this
    elif self.label_file_format == LabelFileFormat.NEW_FORMAT:  # Add this
        self.label_file_format = LabelFileFormat.PASCAL_VOC
    # Update UI...
```

### Update Load Labels

```python
# In load_labels() or load_file() method - add format detection
def load_labels(self, shapes, filepath):
    # Detect format from file extension
    if filepath.endswith('.xml'):
        # Load PASCAL VOC
        ...
    elif filepath.endswith('.txt'):
        # Load YOLO
        ...
    elif filepath.endswith('.json'):
        # Could be CreateML, check content
        ...
    elif filepath.endswith('.newext'):  # Add detection for your format
        from libs.new_format_io import NewFormatReader
        reader = NewFormatReader(filepath, self.image)
        shapes = reader.get_shapes()
        self.verified = reader.verified
```

## Complete Example: COCO Format

Here's a condensed example implementing COCO JSON format:

### libs/coco_io.py

```python
"""COCO format I/O."""
import json
import os


class COCOWriter:
    def __init__(self, folder_name, filename, img_size, **kwargs):
        self.filename = filename
        self.img_size = img_size
        self.box_list = []
        self.verified = False
        self.categories = {}

    def add_bnd_box(self, xmin, ymin, xmax, ymax, name, difficult):
        if name not in self.categories:
            self.categories[name] = len(self.categories) + 1

        self.box_list.append({
            'bbox': [xmin, ymin, xmax - xmin, ymax - ymin],  # COCO: x, y, w, h
            'category_id': self.categories[name],
            'category_name': name
        })

    def save(self, target_file=None):
        coco_data = {
            'images': [{
                'id': 1,
                'file_name': self.filename,
                'height': self.img_size[0],
                'width': self.img_size[1]
            }],
            'annotations': [],
            'categories': []
        }

        for i, box in enumerate(self.box_list):
            coco_data['annotations'].append({
                'id': i + 1,
                'image_id': 1,
                'category_id': box['category_id'],
                'bbox': box['bbox'],
                'area': box['bbox'][2] * box['bbox'][3],
                'iscrowd': 0
            })

        for name, cat_id in self.categories.items():
            coco_data['categories'].append({
                'id': cat_id,
                'name': name
            })

        with open(target_file, 'w') as f:
            json.dump(coco_data, f, indent=2)


class COCOReader:
    def __init__(self, file_path, image=None):
        self.file_path = file_path
        self.shapes = []
        self.verified = False
        self.parse_format()

    def parse_format(self):
        with open(self.file_path) as f:
            data = json.load(f)

        # Build category lookup
        categories = {c['id']: c['name'] for c in data.get('categories', [])}

        for ann in data.get('annotations', []):
            bbox = ann['bbox']  # x, y, width, height
            xmin = bbox[0]
            ymin = bbox[1]
            xmax = bbox[0] + bbox[2]
            ymax = bbox[1] + bbox[3]
            label = categories.get(ann['category_id'], 'unknown')
            self.add_shape(label, xmin, ymin, xmax, ymax, False)

    def add_shape(self, label, xmin, ymin, xmax, ymax, difficult):
        points = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        self.shapes.append((label, points, None, None, difficult))

    def get_shapes(self):
        return self.shapes
```

## Testing Your Format

### Unit Test

```python
# test_new_format.py
import tempfile
from libs.new_format_io import NewFormatWriter, NewFormatReader

def test_round_trip():
    """Test write then read produces same data."""
    with tempfile.NamedTemporaryFile(suffix='.newext', delete=False) as f:
        output_path = f.name

    # Write
    writer = NewFormatWriter('images', 'test.jpg', (600, 800, 3))
    writer.add_bnd_box(100, 150, 400, 450, 'cat', False)
    writer.add_bnd_box(450, 200, 750, 550, 'dog', True)
    writer.save(target_file=output_path)

    # Read back
    from PyQt5.QtGui import QImage
    image = QImage(800, 600, QImage.Format_RGB32)  # Dummy image
    reader = NewFormatReader(output_path, image)
    shapes = reader.get_shapes()

    assert len(shapes) == 2
    assert shapes[0][0] == 'cat'
    assert shapes[1][0] == 'dog'

    print("Round-trip test passed!")
```

### Integration Test

1. Run labelImg++: `python labelImgPlusPlus.py`
2. Open a test image
3. Draw bounding boxes with labels
4. Toggle to your format (Ctrl+Y repeatedly)
5. Save (Ctrl+S)
6. Close and reopen - verify annotations load correctly

## Checklist

- [ ] Created `libs/new_format_io.py` with Writer and Reader classes
- [ ] Added `LabelFileFormat.NEW_FORMAT` enum value
- [ ] Added `save_new_format()` method in LabelFile
- [ ] Added dispatch case in `save_label_file()`
- [ ] Created format icon in `resources/icons/`
- [ ] Updated `resources.qrc` and rebuilt resources
- [ ] Updated `get_format_meta()` in labelImgPlusPlus.py
- [ ] Updated `change_format()` cycle in labelImgPlusPlus.py
- [ ] Added format detection in load logic
- [ ] Tested write and read round-trip
- [ ] Tested with actual training framework
