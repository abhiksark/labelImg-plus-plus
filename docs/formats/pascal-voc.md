# PASCAL VOC Format

PASCAL VOC (Visual Object Classes) is an XML-based annotation format originally used for the PASCAL VOC challenge.

**Files:** `libs/pascal_voc_io.py` (lines 15-171)

## File Structure

Each image has a corresponding `.xml` file with the same base name:
```
images/
├── image001.jpg
├── image001.xml
├── image002.jpg
└── image002.xml
```

## XML Schema

```xml
<annotation verified="yes">
    <folder>images</folder>
    <filename>image001.jpg</filename>
    <path>/home/user/dataset/images/image001.jpg</path>
    <source>
        <database>Unknown</database>
    </source>
    <size>
        <width>800</width>
        <height>600</height>
        <depth>3</depth>
    </size>
    <segmented>0</segmented>
    <object>
        <name>cat</name>
        <pose>Unspecified</pose>
        <truncated>0</truncated>
        <difficult>0</difficult>
        <bndbox>
            <xmin>100</xmin>
            <ymin>150</ymin>
            <xmax>400</xmax>
            <ymax>450</ymax>
        </bndbox>
    </object>
    <object>
        <name>dog</name>
        <pose>Unspecified</pose>
        <truncated>1</truncated>
        <difficult>0</difficult>
        <bndbox>
            <xmin>450</xmin>
            <ymin>200</ymin>
            <xmax>750</xmax>
            <ymax>550</ymax>
        </bndbox>
    </object>
</annotation>
```

## Element Reference

### Root Element

| Element | Description |
|---------|-------------|
| `<annotation>` | Root element |
| `verified` attribute | "yes" if annotation reviewed |

### Image Metadata

| Element | Description |
|---------|-------------|
| `<folder>` | Parent folder name |
| `<filename>` | Image filename |
| `<path>` | Full path to image |
| `<source><database>` | Database source (usually "Unknown") |

### Image Size

| Element | Description |
|---------|-------------|
| `<size><width>` | Image width in pixels |
| `<size><height>` | Image height in pixels |
| `<size><depth>` | Color channels (3 for RGB, 1 for grayscale) |

### Objects

| Element | Description |
|---------|-------------|
| `<object>` | One per annotation |
| `<name>` | Class label |
| `<pose>` | Object pose (always "Unspecified") |
| `<truncated>` | 1 if object extends beyond image boundary |
| `<difficult>` | 1 if object is hard to recognize |
| `<bndbox>` | Bounding box coordinates |

### Bounding Box

| Element | Description |
|---------|-------------|
| `<xmin>` | Left edge (1-indexed) |
| `<ymin>` | Top edge (1-indexed) |
| `<xmax>` | Right edge |
| `<ymax>` | Bottom edge |

## Coordinate System

```
(0,0)                              (width,0)
  +------------------------------------+
  |  (xmin, ymin)                      |
  |       +------------------+         |
  |       |                  |         |
  |       |     object       |         |
  |       |                  |         |
  |       +------------------+         |
  |                    (xmax, ymax)    |
  +------------------------------------+
(0,height)                        (width,height)

Note: Coordinates are 1-indexed (minimum value = 1)
      This is for Faster R-CNN compatibility
```

## Writer Class

**File:** `libs/pascal_voc_io.py` (lines 15-124)

```python
class PascalVocWriter:
    def __init__(self, folder_name, filename, img_size,
                 database_src='Unknown', local_img_path=None):
        self.folder_name = folder_name
        self.filename = filename
        self.img_size = img_size  # (height, width, depth)
        self.box_list = []
        self.verified = False

    def add_bnd_box(self, x_min, y_min, x_max, y_max, name, difficult):
        """Add bounding box to annotation."""
        bnd_box = {
            'xmin': x_min, 'ymin': y_min,
            'xmax': x_max, 'ymax': y_max,
            'name': name, 'difficult': difficult
        }
        self.box_list.append(bnd_box)

    def save(self, target_file=None):
        """Write XML file."""
        root = self.gen_xml()
        self.append_objects(root)
        # Write with pretty printing
```

### Auto-Truncated Detection

```python
# In append_objects():
if int(ymax) == int(img_height) or int(ymin) == 1:
    truncated = "1"
elif int(xmax) == int(img_width) or int(xmin) == 1:
    truncated = "1"
else:
    truncated = "0"
```

## Reader Class

**File:** `libs/pascal_voc_io.py` (lines 127-171)

```python
class PascalVocReader:
    def __init__(self, file_path):
        self.shapes = []
        self.file_path = file_path
        self.verified = False
        self.parse_xml()

    def get_shapes(self):
        """Return list of shape tuples."""
        return self.shapes
        # Each: (label, points, None, None, difficult)

    def parse_xml(self):
        """Parse XML and extract shapes."""
        xml_tree = ElementTree.parse(self.file_path)
        # Check verified attribute
        # For each <object>, extract bndbox and create shape
```

### Shape Tuple Format

```python
# Output from get_shapes():
(
    label,      # str: class name
    points,     # list: [(xmin,ymin), (xmax,ymin), (xmax,ymax), (xmin,ymax)]
    None,       # line_color (not stored in VOC)
    None,       # fill_color (not stored in VOC)
    difficult   # bool: difficult flag
)
```

## Usage Example

### Writing

```python
from libs.pascal_voc_io import PascalVocWriter

writer = PascalVocWriter(
    folder_name='images',
    filename='test.jpg',
    img_size=(600, 800, 3),  # height, width, depth
    local_img_path='/path/to/test.jpg'
)
writer.verified = True
writer.add_bnd_box(100, 150, 400, 450, 'cat', difficult=0)
writer.add_bnd_box(450, 200, 750, 550, 'dog', difficult=1)
writer.save('test.xml')
```

### Reading

```python
from libs.pascal_voc_io import PascalVocReader

reader = PascalVocReader('test.xml')
shapes = reader.get_shapes()

for label, points, _, _, difficult in shapes:
    print(f"Label: {label}, Difficult: {difficult}")
    print(f"Corners: {points}")
```

## Integration with LabelFile

```python
# In LabelFile.save_pascal_voc_format():
def save_pascal_voc_format(self, filename, shapes, image_path, ...):
    writer = PascalVocWriter(folder_name, file_name, image_shape)
    writer.verified = self.verified

    for shape in shapes:
        points = shape['points']
        bnd_box = LabelFile.convert_points_to_bnd_box(points)
        writer.add_bnd_box(
            bnd_box[0], bnd_box[1],  # xmin, ymin
            bnd_box[2], bnd_box[3],  # xmax, ymax
            shape['label'],
            int(shape['difficult'])
        )

    writer.save(target_file=filename)
```

## Compatibility Notes

1. **1-indexed coordinates**: Minimum x/y values are clamped to 1 (not 0) for Faster R-CNN
2. **Integer coordinates**: All values are integers
3. **Truncated auto-detection**: Set based on box touching image edges
4. **Pose always "Unspecified"**: Pose information not captured by labelImg++
5. **Segmented always "0"**: Segmentation not supported
