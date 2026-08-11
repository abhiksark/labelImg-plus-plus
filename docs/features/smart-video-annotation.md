# Smart video annotation

Smart video mode adds timestamp-accurate annotation without changing the image
workflow or its file formats. It supports local MP4, MOV, MKV, and AVI sources,
uses the first playable video stream, applies display rotation, and ignores
audio.

## Install and open

```bash
pip install "labelimgplusplus[video]"
labelimgpp /path/to/clip.mp4
```

You can also use **File → Open Video…**, `Ctrl+Alt+V`, or pass an existing
`.labelimgpp.sqlite` project as the normal first positional argument.

Opening is transactional: the source, first frame, and project are validated
before the current document is replaced. A new project is created only after
the first frame decodes successfully. Its default path is the sibling
`<video-filename>.labelimgpp.sqlite`. If that directory is not writable, choose
another project path or cancel the picker to inspect the video read-only.

The project stores a sampled content fingerprint. Moving a video is safe when
the fingerprint still matches. Changed content is never combined with the old
annotations; locate the original source, create a new project, or cancel.

## Navigate the timeline

The bottom timeline contains play/pause, previous/next frame, an exact
`HH:MM:SS.mmm` entry, a normalized long-duration slider, and 0.25x, 0.5x, 1x,
and 2x playback. The PTS is exact; the displayed frame number is approximate
because variable-frame-rate media has no reliable integer frame index.

- `A` and `D` step backward and forward in video mode.
- `Ctrl+Space` toggles silent playback. `Space` verifies the current frame.
- Dragging the timeline is debounced; releasing it performs an exact
  latest-request-wins seek.
- Drawing or editing pauses playback automatically.

Blue spans show track coverage, green markers show accepted manual anchors,
amber markers show legacy pending suggestions, red spans show propagation
gaps, and purple markers show verified frames.

## Tracks, anchors, and interpolation

Drawing a rectangle or polygon on a video frame creates a UUID-backed track and
an accepted manual observation at the current PTS. The unified **Objects**
inspector shows the track label, span, color, visibility, provenance, render
state, and pending-review count, including tracks absent from the current
frame. Renaming a
tracked shape renames the track across the video.

Select a track and press `Shift+K` to make the current materialized occurrence
an editable manual keyframe. Rectangle geometry and compatible keypoints are
interpolated by presentation time between accepted manual anchors. Polygon
vertices are never interpolated. Blue dashed shapes are computed interpolation;
amber dashed shapes are pending tracker suggestions.

Deleting an exact occurrence removes that observation. Deleting an interpolated
occurrence writes an explicit absence anchor, which ends interpolation until a
later present anchor. **Tools → Delete Track…** removes all observations after
confirmation. Video mutations use the same undo stack as image annotations.

SAM can create a manual polygon observation on a paused video frame when both
the `sam` and `video` extras are installed. It is not an automatic video-mask
tracker.

## Whole-video propagation

Use **Propagate across video** to include every exact accepted manual anchor on
the current frame, or **Propagate selected object** for only the selected
qualifying track. Directional tracking actions remain compatibility aliases
that use the same accepted-result pipeline.

The portable OpenCV backend decodes each direction once, updates active
rectangles, polygons, and associated keypoints together, and uses bounded
Lucas–Kanade flow with affine estimation. Results stream to a preview overlay;
the canonical project, save state, export data, and undo history remain
unchanged until the complete result passes document, media, generation, and
per-track revision checks. The accepted tracker observations and inclusive gap
records then commit atomically as one undo step.

Manual anchors are never overwritten. Reaching another present anchor reseeds
that track; an absence anchor or failed track produces a stable ``occluded``,
``low_confidence``, ``out_of_frame``, or ``scene_cut`` gap while other tracks
continue. Cancel, document replacement, shutdown, stale state, or a backend or
decoder failure clears the preview without changing the durable project.

Editing tracker or interpolated geometry creates an accepted manual correction
immediately. A separate background job regenerates only the open segments up
to the nearest manual anchor on either side. Successful regeneration is a
second undo entry; failure or stale state preserves the correction and all
previous generated data.

## Optional SAM 2 backend

Open **Tools → SAM Settings…** and choose **Auto**, **OpenCV**, or **SAM 2**.
SAM 2 requires Linux, Python 3.10 or newer, compatible CUDA-enabled PyTorch and
torchvision, an official SAM 2 source installation, and local matching
checkpoint and config files. The config must be selected from the installed
``sam2`` package's ``configs`` directory.

Follow [Meta's official source-install and checkpoint instructions](https://github.com/facebookresearch/sam2#installation),
then select the two files in labelImg++. The application never downloads or
bundles Torch, SAM 2, model checkpoints, or configs, and these packages are
intentionally not part of the base, ``sam``, ``video``, or combined extras.

**Auto** evaluates those requirements only when propagation starts and uses
SAM 2 when all are satisfied; otherwise it uses portable OpenCV. Explicit
**SAM 2** selection reports an actionable error without falling back. SAM 2
turns video masks into simplified polygons or tight rectangles matching the
track type and records no-object results as normal propagation gaps. The same
preview, atomic commit, manual-anchor, cancellation, revision, and undo rules
apply to both backends.

## Legacy optical-flow suggestions and review

Tracking starts from an accepted exact rectangle. Select it, then press `T` or
`Shift+T`. The endpoint dialog defaults to the next manual anchor in that
direction, or five seconds when none exists. The worker decodes independently,
uses bounded-resolution pyramidal Lucas–Kanade flow with forward/backward
validation and RANSAC, and stops on weak geometry, excessive error, bounds
loss, or a scene cut.

Suggestions remain pending until reviewed:

- `Shift+Enter` accepts the current suggestion.
- `Backspace` rejects the current suggestion.
- The **Tools** menu can accept or reject the visible range or the full latest
  propagation run.

Accepted tracker observations become exact states but do not become
interpolation anchors until promoted with `Shift+K`. Rejected suggestions stay
recorded so they do not immediately reappear. Rerunning a range may replace
pending or rejected suggestions, but never accepted or manual observations.

## Save and recover

`Ctrl+S` flushes the video project; timer autosave uses the same revisioned
delta. Saves are serialized in SQLite transactions and retain dirty state on
failure or external revision conflict. Save As uses SQLite backup rather than a
file copy. Clean close checkpoints the WAL. Discard reloads the last durable
project state.

## Export accepted frames

Choose **Tools → Export Video Frames…**. The destination must be new or empty.
Select the current, annotated, or verified frames, or a time range sampled by
frames or seconds. JPEG quality 95 is the default; PNG is lossless. Annotation
output can be Pascal VOC, YOLO, YOLO-seg, COCO, or CreateML.

Only accepted manual/tracker states and accepted rectangle interpolation are
exported. Pending and rejected suggestions are excluded. Names are stable:

```text
<video-stem>__s<stream-index>__p<pts>.<extension>
```

The exporter stages the whole result before publishing it and writes
`video_export_manifest.json` with the source fingerprint, PTS/time base,
verification state, and track IDs for every image.

## Scope

Live/network streams, audio playback or editing, multi-stream selection,
automatic propagation after drawing, bundled model runtimes/checkpoints, and
native MOT/CVAT-video project formats are not included.
