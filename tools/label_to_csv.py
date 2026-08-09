#!/usr/bin/env python3

"""Export YOLO or Pascal VOC labels to a Vertex AI import CSV."""

import argparse
import csv
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_CLASSES = (
    Path(__file__).resolve().parent.parent / "data" / "predefined_classes.txt"
)


class ExportError(ValueError):
    """An actionable error in the requested dataset export."""


def _parse_number(value, context):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ExportError("{} must be a number, got {!r}".format(context, value))
    if not math.isfinite(number):
        raise ExportError("{} must be finite, got {!r}".format(context, value))
    return number


def _clamp(value):
    return min(max(0.0, value), 1.0)


def _row(split, image_uri, label, x_min, y_min, x_max, y_max):
    # Vertex AI accepts two diagonally opposite vertices; the unused vertex
    # pairs remain empty in its 11-column object-detection CSV schema.
    return [
        split,
        image_uri,
        label,
        x_min,
        y_min,
        "",
        "",
        x_max,
        y_max,
        "",
        "",
    ]


def _annotation_files(location, suffix):
    try:
        children = sorted(location.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise ExportError("cannot read label directory {}: {}".format(location, exc))
    return [
        path
        for path in children
        if path.is_file()
        and path.suffix.lower() == suffix
        and path.name.lower() != "classes.txt"
    ]


def txt2csv(location, split, path_prefix, class_labels):
    """Convert the YOLO ``.txt`` annotations in *location* to CSV rows."""
    location = Path(location)
    rows = []
    for label_path in _annotation_files(location, ".txt"):
        try:
            lines = label_path.read_text(encoding="utf-8-sig").splitlines()
        except (OSError, UnicodeError) as exc:
            raise ExportError("cannot read {}: {}".format(label_path, exc))

        for line_number, raw_line in enumerate(lines, 1):
            line = raw_line.strip()
            if not line:
                continue
            fields = line.split()
            context = "{}: line {}".format(label_path, line_number)
            if len(fields) != 5:
                raise ExportError(
                    "{} has {} values; expected YOLO fields "
                    "'class x_center y_center width height'".format(
                        context, len(fields)
                    )
                )

            try:
                class_index = int(fields[0])
            except ValueError:
                raise ExportError(
                    "{} has invalid class index {!r}".format(context, fields[0])
                )
            if class_index < 0 or class_index >= len(class_labels):
                raise ExportError(
                    "{} has class index {}; expected 0 through {} from the "
                    "classes file".format(
                        context, class_index, len(class_labels) - 1
                    )
                )

            x_center = _parse_number(fields[1], context + " x_center")
            y_center = _parse_number(fields[2], context + " y_center")
            width = _parse_number(fields[3], context + " width")
            height = _parse_number(fields[4], context + " height")
            if width <= 0 or height <= 0:
                raise ExportError(
                    "{} width and height must be greater than zero".format(context)
                )

            image_uri = "{}/{}.jpg".format(
                path_prefix.rstrip("/"), label_path.stem
            )
            rows.append(
                _row(
                    split,
                    image_uri,
                    class_labels[class_index],
                    _clamp(x_center - width / 2),
                    _clamp(y_center - height / 2),
                    _clamp(x_center + width / 2),
                    _clamp(y_center + height / 2),
                )
            )
    return rows


def _required_xml_text(parent, element_name, context):
    element = parent.find(element_name) if parent is not None else None
    if element is None or element.text is None or not element.text.strip():
        raise ExportError("{} is missing <{}>".format(context, element_name))
    return element.text.strip()


def xml2csv(location, split, path_prefix):
    """Convert the Pascal VOC ``.xml`` annotations in *location* to CSV rows."""
    location = Path(location)
    rows = []
    for label_path in _annotation_files(location, ".xml"):
        try:
            root = ET.parse(str(label_path)).getroot()
        except ET.ParseError as exc:
            raise ExportError("{} contains invalid XML: {}".format(label_path, exc))
        except OSError as exc:
            raise ExportError("cannot read {}: {}".format(label_path, exc))

        size = root.find("size")
        size_context = "{}: <size>".format(label_path)
        width = _parse_number(
            _required_xml_text(size, "width", size_context),
            size_context + " <width>",
        )
        height = _parse_number(
            _required_xml_text(size, "height", size_context),
            size_context + " <height>",
        )
        if width <= 0 or height <= 0:
            raise ExportError(
                "{} image width and height must be greater than zero".format(
                    label_path
                )
            )

        image_uri = "{}/{}.jpg".format(path_prefix.rstrip("/"), label_path.stem)
        for object_number, label_object in enumerate(root.findall("object"), 1):
            context = "{}: object {}".format(label_path, object_number)
            label = _required_xml_text(label_object, "name", context)
            bounding_box = label_object.find("bndbox")
            if bounding_box is None:
                raise ExportError("{} is missing <bndbox>".format(context))

            x_min = _parse_number(
                _required_xml_text(bounding_box, "xmin", context),
                context + " <xmin>",
            )
            y_min = _parse_number(
                _required_xml_text(bounding_box, "ymin", context),
                context + " <ymin>",
            )
            x_max = _parse_number(
                _required_xml_text(bounding_box, "xmax", context),
                context + " <xmax>",
            )
            y_max = _parse_number(
                _required_xml_text(bounding_box, "ymax", context),
                context + " <ymax>",
            )
            if x_min >= x_max or y_min >= y_max:
                raise ExportError(
                    "{} bounding box must have xmin < xmax and ymin < ymax".format(
                        context
                    )
                )

            rows.append(
                _row(
                    split,
                    image_uri,
                    label,
                    x_min / width,
                    y_min / height,
                    x_max / width,
                    y_max / height,
                )
            )
    return rows


def _cloud_root(prefix):
    prefix = prefix.strip()
    if prefix.startswith("gs://"):
        prefix = prefix[5:]
    elif "://" in prefix:
        raise ExportError("--prefix must be a Cloud Storage bucket or gs:// URI")
    prefix = prefix.strip("/")
    if not prefix:
        raise ExportError("--prefix must not be empty")
    if "\\" in prefix or any(character.isspace() for character in prefix):
        raise ExportError("--prefix must not contain whitespace or backslashes")
    return "gs://{}".format(prefix)


def load_class_labels(classes_path):
    classes_path = Path(classes_path)
    if not classes_path.is_file():
        raise ExportError("classes file does not exist: {}".format(classes_path))
    try:
        lines = classes_path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ExportError("cannot read classes file {}: {}".format(classes_path, exc))

    labels = []
    for line_number, line in enumerate(lines, 1):
        label = line.strip()
        if not label:
            raise ExportError(
                "classes file {} has an empty label at line {}".format(
                    classes_path, line_number
                )
            )
        labels.append(label)
    if not labels:
        raise ExportError("classes file is empty: {}".format(classes_path))
    return labels


def export_rows(location, mode, prefix, class_labels=None):
    location = Path(location)
    if not location.exists():
        raise ExportError("label location does not exist: {}".format(location))
    if not location.is_dir():
        raise ExportError("label location is not a directory: {}".format(location))
    if mode not in ("txt", "xml"):
        raise ExportError("mode must be 'txt' or 'xml'")
    if mode == "txt" and not class_labels:
        raise ExportError("TXT mode requires a non-empty classes file")

    cloud_root = _cloud_root(prefix)
    try:
        split_paths = sorted(location.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise ExportError("cannot read label location {}: {}".format(location, exc))

    rows = []
    for split_path in split_paths:
        if not split_path.is_dir():
            continue
        try:
            class_paths = sorted(split_path.iterdir(), key=lambda path: path.name)
        except OSError as exc:
            raise ExportError("cannot read split directory {}: {}".format(split_path, exc))
        for class_path in class_paths:
            if not class_path.is_dir():
                continue
            path_prefix = "{}/{}".format(cloud_root, class_path.name)
            if mode == "txt":
                rows.extend(
                    txt2csv(class_path, split_path.name, path_prefix, class_labels)
                )
            else:
                rows.extend(xml2csv(class_path, split_path.name, path_prefix))
    return rows


def write_csv(rows, output_path):
    output_path = Path(output_path)
    try:
        with output_path.open("w", encoding="utf-8", newline="") as output_file:
            writer = csv.writer(output_file, lineterminator="\n")
            writer.writerows(rows)
    except OSError as exc:
        raise ExportError("cannot write output file {}: {}".format(output_path, exc))


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Export YOLO TXT or Pascal VOC XML labels to Vertex AI CSV."
    )
    parser.add_argument(
        "-p",
        "--prefix",
        required=True,
        help="Cloud Storage bucket or gs:// path prefix",
    )
    parser.add_argument(
        "-l",
        "--location",
        required=True,
        help="parent directory of the split label directories",
    )
    parser.add_argument(
        "-m",
        "--mode",
        required=True,
        choices=("txt", "xml"),
        help="source annotation format",
    )
    parser.add_argument(
        "-o", "--output", default="res.csv", help="output CSV path (default: res.csv)"
    )
    parser.add_argument(
        "-c",
        "--classes",
        default=str(DEFAULT_CLASSES),
        help="YOLO class names file (TXT mode only)",
    )
    return parser


def main(argv=None):
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        class_labels = None
        if args.mode == "txt":
            class_labels = load_class_labels(args.classes)
        rows = export_rows(args.location, args.mode, args.prefix, class_labels)
        write_csv(rows, args.output)
    except ExportError as exc:
        print("{}: error: {}".format(parser.prog, exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
