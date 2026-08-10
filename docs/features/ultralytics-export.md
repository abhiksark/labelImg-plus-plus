# Ultralytics Dataset Export

LabelImg++ can export the current image dataset directly as an Ultralytics
YOLO detection dataset. Open an image directory, choose **Tools → Export
Ultralytics Dataset…**, select train/validation/test percentages, and choose
whether to copy images or create symlinks.

The destination must be new or empty. LabelImg++ builds the complete export in
an owned sibling staging directory and publishes it only after every image and
annotation succeeds. Cancellation or a conversion error leaves no partial
dataset at the destination.

## Output layout

```text
my-dataset/
├── data.yaml
├── labelimgpp_export_manifest.json
├── images/
│   ├── train/
│   ├── val/
│   └── test/
└── labels/
    ├── train/
    ├── val/
    └── test/
```

`data.yaml` uses paths relative to its own directory and stores the stable,
zero-based class ordering used by every label file:

```yaml
path: .
train: images/train
val: images/val
test: images/test
names:
  0: "person"
  1: "vehicle"
```

The split is deterministic for a given image set, ratios, and random seed.
Images with colliding basenames receive deterministic suffixes, and their
labels retain the matching stem. Missing annotations are treated as
background images and therefore do not receive an empty label file. Existing
but object-free annotations do receive an empty label file.

Copy mode creates a self-contained dataset. Symlink mode saves storage and
uses absolute links to the local source images, so moving or deleting the
source dataset breaks those links.

## Annotation behavior

The exporter reads PASCAL VOC, YOLO bbox, YOLO-seg, COCO, or CreateML through
the same loaders used by the application. Keep the format selector on the
intended source format before exporting; it disambiguates shared `.json` and
`.txt` annotation types.

This command targets Ultralytics **object detection**:

- Rectangles are written as normalized `class x_center y_center width height`.
- Polygons are converted to their enclosing detection boxes and reported in
  the completion summary and manifest.
- Keypoints and polygon vertices are not included in the detection labels.
- Difficult flags are not represented by the YOLO detection format.

Use the normal YOLO-seg or COCO save/export paths when segmentation vertices
or keypoints must be preserved.

## Manifest and failures

`labelimgpp_export_manifest.json` records the split ratios and seed, copy or
symlink mode, class order, source-to-output mapping, per-image object counts,
and annotated/unannotated totals. It is metadata for audit and relocation; it
does not alter the Ultralytics payload.

A corrupt annotation, unreadable image, invalid or zero-area geometry, or a
non-empty destination fails the whole export. Save pending edits when prompted
so the exporter reads the latest durable annotations.
