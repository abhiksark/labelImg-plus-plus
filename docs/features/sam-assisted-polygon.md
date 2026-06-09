<!-- docs/features/sam-assisted-polygon.md -->
# SAM-Assisted Polygon

Click once on an object to auto-generate a polygon annotation.

## Install

    pip install labelimgplusplus[sam]

This pulls the optional ML stack (PyTorch, MobileSAM, OpenCV). Without it, the
**SAM Segment** action stays disabled with an install hint — the core app is
unaffected.

## First use

Toggle **SAM Segment** (toolbar / Tools menu). The first click on an image runs
the MobileSAM encoder (a moment on CPU), then traces the mask into a polygon.
Click again for another shape; Ctrl+Z undoes it like any polygon.

## Settings (Tools → SAM Settings…)

- **Checkpoint** — leave blank to auto-download MobileSAM (~40 MB) on first use,
  or point at your own checkpoint (e.g. a full SAM ``vit_h`` for GPU).
- **Model type** — ``vit_t`` (MobileSAM, default), ``vit_b``, ``vit_h``.
- **Device** — ``cpu`` (default) or ``cuda``. Choosing ``cuda`` with no GPU
  falls back to CPU automatically.

## Security note

A SAM checkpoint is a pickled file loaded by PyTorch. The auto-downloaded
default is fetched from this project's GitHub Release and verified against a
pinned SHA256 checksum (the checksum is set when the release asset is
published). A checkpoint path you set yourself is treated as trusted local
input — only point it at files you trust.
