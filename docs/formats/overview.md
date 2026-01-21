# Annotation Formats Overview

labelImg++ supports three annotation formats for object detection training data.

## Format Comparison

```
+------------------+------------------+------------------+
|   PASCAL VOC     |      YOLO        |    CreateML      |
+------------------+------------------+------------------+
| XML format       | Text format      | JSON format      |
| Corner-based     | Center-based     | Center-based     |
| Absolute pixels  | Normalized 0-1   | Absolute pixels  |
| 1-indexed coords | 0-indexed coords | 0-indexed coords |
| Per-image file   | Per-image file   | Aggregated file  |
| .xml extension   | .txt extension   | .json extension  |
+------------------+------------------+------------------+
```

## Coordinate Systems

```
PASCAL VOC (Corner-based)           YOLO (Normalized Center)
+-------------------------+         +-------------------------+
|(xmin, ymin)             |         |      (x_center,         |
|    +------------+       |         |       y_center)         |
|    |            |       |         |          *              |
|    |   object   |       |         |      width: 0.25        |
|    |            |       |         |      height: 0.33       |
|    +------------+       |         |                         |
|           (xmax, ymax)  |         |         (1.0, 1.0)      |
+-------------------------+         +-------------------------+

CreateML (Pixel Center)
+-------------------------+
|       (x, y)            |
|          *              |
|      width: 100         |
|      height: 80         |
|                         |
+-------------------------+
```

## Quick Reference

| Feature | PASCAL VOC | YOLO | CreateML |
|---------|------------|------|----------|
| File Extension | .xml | .txt | .json |
| Coordinate Type | Corner (xmin, ymin, xmax, ymax) | Normalized center (x, y, w, h) | Pixel center (x, y, w, h) |
| Value Range | 1 to image_size | 0.0 to 1.0 | 0 to image_size |
| Additional Files | None | classes.txt | None |
| Multiple Images | Separate files | Separate files | Single file |
| Difficult Flag | Yes | No (lost) | No (hardcoded) |
| Verified Flag | Yes | No | Yes |

## Format Selection

### In the UI
- Click the format button in toolbar (shows current format)
- Press **Ctrl+Y** to cycle through formats
- Format indicator: `&PascalVOC`, `&YOLO`, `&CreateML`

### Via Code

```python
# In MainWindow
self.label_file_format = LabelFileFormat.PASCAL_VOC  # or YOLO, CREATE_ML
```

## When to Use Each Format

### PASCAL VOC
- Training with TensorFlow Object Detection API
- Compatible with ImageNet tools
- Need to preserve difficult/truncated flags
- Prefer human-readable XML

### YOLO
- Training with Darknet/YOLO frameworks
- Training with Ultralytics YOLOv5/v8
- Need normalized coordinates
- Prefer minimal file size

### CreateML
- Training on Apple devices (iOS/macOS)
- Using Apple Create ML tool
- Need single file for all annotations

## Data Flow

```
Internal Shape
    |
    +---> points: [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
    |     (4 corners, clockwise from top-left)
    |
    v
convert_points_to_bnd_box()
    |
    +---> (xmin, ymin, xmax, ymax)
    |     (integers, 1-indexed minimum)
    |
    v
+-------+-------+-------+
|       |       |       |
v       v       v       v
VOC    YOLO    CreateML
Writer Writer  Writer
|       |       |
v       v       v
.xml   .txt    .json
```

## File Locations

Annotation files are saved in:
1. **Default save directory** (if set via File > Change Save Dir)
2. **Same directory as image** (if no default set)

When loading, labelImg++ searches in this priority:
1. Default save directory
2. Image directory

## Format-Specific Documentation

- [PASCAL VOC Format](pascal-voc.md) - XML structure and coordinate details
- [YOLO Format](yolo.md) - Text format and normalization
- [CreateML Format](createml.md) - JSON structure and aggregation
