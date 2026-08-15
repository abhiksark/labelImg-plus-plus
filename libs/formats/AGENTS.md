# Annotation Format Instructions

## Scope

This file governs annotation readers, writers, metadata, path resolution, probes, and loader glue under `libs/formats/`. It extends the repository-wide instructions in the root `AGENTS.md`.

## Contracts

- Treat annotation formats as a closed registry, not a plugin extension point.
- Never construct annotation paths manually. Use `annotation_output_base()` and `find_existing_annotation()` with the active `AnnotationResolver`.
- Do not add a production asynchronous save path that invokes a writer directly. Register it with `SaveRequest` and `write_save_request()` so publication remains atomic.
- Writers receive a temporary path in the destination directory. Derive sibling files such as `classes.txt` from `target_file`, not from the source image path.
- Preserve the ordering of an existing YOLO `classes.txt`; append new labels without renumbering existing annotations.
- Reader shape tuples are not uniform: YOLO and CreateML return 5 fields, VOC and YOLO-seg return 6, and COCO returns 7. Callers must handle the actual tuple arity.

## Adding a format

- Add the reader/writer and update `LabelFileFormat` plus its `LabelFile` save adapter.
- Update `libs/utils/constants.py`, `format_metadata.py` (`_FORMATS`, `_CYCLE_WARNINGS`, and the predecessor warning), `libs/core/save_pipeline.py`, `annotation_loader.py`, `libs/core/image_pipeline.py`, and `annotation_probe.py`.
- Update the synchronous load/map paths in `labelImgPlusPlus.py` and format parsing in `libs/widgets/galleryWidget.py`.
- Add a non-XML/TXT/JSON extension to `ANNOTATION_EXTENSIONS`.
- If the format appears in video export, update `libs/widgets/videoExportDialog.py` and `libs/core/video_export.py`.
- If an icon or resource alias changes, run `make qt5py3` and `python3 scripts/verify_qt_resources.py`.

## Validation

- Run `python3 -m pytest tests/formats tests/core/test_save_pipeline.py -v`.
- Add integration, gallery, or export tests when those call paths change.
- Do not use `docs/guides/adding-formats.md` or `docs/formats/overview.md` as implementation authority; both describe the older format layout.
