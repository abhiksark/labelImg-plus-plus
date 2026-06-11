<!-- docs/features/sam-assisted-polygon.md -->
# SAM-Assisted Polygon

Click once on an object to auto-generate a polygon annotation.

## Install

    pip install labelimgplusplus[sam]

This pulls a small inference stack (ONNX Runtime, NumPy, OpenCV — roughly
70 MB, no PyTorch). Without it, the **SAM Segment** action stays disabled with
an install hint — the core app is unaffected.

## First use

Toggle **SAM Segment** (toolbar / Tools menu). The first click downloads the
MobileSAM model pair (~45 MB) and runs the image encoder (~0.3 s on a typical
CPU), then traces the mask into a polygon. Further clicks on the same image
take ~25 ms each; Ctrl+Z undoes a shape like any polygon.

## Settings (Tools → SAM Settings…)

- **Encoder model (.onnx)** / **Decoder model (.onnx)** — leave both empty to
  auto-download the bundled MobileSAM pair, or point both at your own exported
  SAM variant. The two files must come from the same export: a mismatched
  pair produces embeddings the decoder cannot read, so setting only one is
  rejected.

To export your own pair from a SAM checkpoint, see
`scripts/export_sam_onnx.py`.

## Security note

ONNX models are protobuf data, not pickled code — loading one cannot execute
arbitrary code (unlike PyTorch `.pt` checkpoints). The auto-downloaded pair
is additionally verified against SHA256 checksums pinned in the source. Model
paths you set yourself are treated as trusted local input.
