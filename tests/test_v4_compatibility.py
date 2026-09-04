"""Compatibility checks against persisted 4.0.0rc0 artifacts."""

import json
from pathlib import Path
import sqlite3

from PyQt6.QtCore import QByteArray, QPoint, QSize
from PyQt6.QtGui import QColor, QImage

from libs.core.settings import Settings
from libs.core.video_project import (
    APPLICATION_ID, SCHEMA_VERSION, fingerprint_video, load_project,
    read_project_source, save_project_as,
)
from libs.formats.coco_io import COCOReader, COCOWriter
from libs.formats.create_ml_io import CreateMLReader, CreateMLWriter
from libs.formats.labelFile import LabelFileFormat
from libs.formats.pascal_voc_io import PascalVocReader, PascalVocWriter
from libs.formats.yolo_io import YoloReader, YOLOWriter
from libs.formats.yolo_seg_io import YOLOSegReader, YOLOSegWriter


FIXTURES = Path(__file__).parent / "fixtures" / "compatibility" / "v4"
IMAGE_SIZE = [80, 100, 3]


def _shape_signature(shapes):
    return [
        (
            shape[0],
            tuple(tuple(point) for point in shape[1]),
            bool(shape[4]),
            shape[5] if len(shape) > 5 else None,
        )
        for shape in shapes
    ]


def test_v4_rc0_settings_load_and_reencode_without_contract_changes(
        tmp_path):
    fixture = FIXTURES / "settings.json"
    expected_json = json.loads(fixture.read_text(encoding="utf-8"))
    settings = Settings()
    settings.path = str(fixture)

    assert settings.load()
    assert set(settings.data) == set(expected_json)
    assert settings["window/size"] == QSize(1280, 720)
    assert settings["window/position"] == QPoint(48, 72)
    assert settings["line/color"] == QColor(10, 20, 30, 200)
    assert settings["window/state"] == QByteArray(b"\x00\x01\x02\xff")
    assert settings["labelFileFormat"] is LabelFileFormat.YOLO

    output = tmp_path / "settings.json"
    settings.path = str(output)
    assert settings.save()
    assert json.loads(output.read_text(encoding="utf-8")) == expected_json


def test_v4_rc0_plugin_settings_and_shortcuts_roundtrip(tmp_path):
    fixture = FIXTURES / "plugin-settings.json"
    expected = json.loads(fixture.read_text(encoding="utf-8"))
    settings = Settings()
    settings.path = str(fixture)

    assert settings.load()
    assert settings.data == expected
    assert settings.data["plugins"]["enabled"] == [
        "org.labelimgpp.fixture"]
    assert settings.data["shortcuts"] == {
        "plugin.org.labelimgpp.fixture.execute": "Ctrl+Alt+F",
        "save": "Ctrl+S",
    }

    output = tmp_path / "plugin-settings.json"
    settings.path = str(output)
    assert settings.save()
    assert json.loads(output.read_text(encoding="utf-8")) == expected


def test_v4_rc0_pascal_voc_roundtrip_preserves_polygon(tmp_path):
    source = PascalVocReader(str(FIXTURES / "sample.xml"))
    output = tmp_path / "sample.xml"
    writer = PascalVocWriter("dataset", "sample.jpg", IMAGE_SIZE)
    writer.verified = source.verified
    for label, points, _line, _fill, difficult, shape_type in \
            source.get_shapes():
        if shape_type == "polygon":
            writer.add_polygon(points, label, difficult)
        else:
            xs, ys = zip(*points)
            writer.add_bnd_box(
                min(xs), min(ys), max(xs), max(ys), label, difficult)
    writer.save(str(output))

    reloaded = PascalVocReader(str(output))
    assert reloaded.verified is True
    assert _shape_signature(reloaded.get_shapes()) == \
        _shape_signature(source.get_shapes())


def test_v4_rc0_yolo_roundtrip_preserves_box(tmp_path):
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    source = YoloReader(
        str(FIXTURES / "sample-yolo.txt"), image,
        str(FIXTURES / "classes.txt"),
    )
    output = tmp_path / "sample-yolo.txt"
    writer = YOLOWriter("dataset", "sample.jpg", IMAGE_SIZE)
    for label, points, _line, _fill, difficult in source.get_shapes():
        xs, ys = zip(*points)
        writer.add_bnd_box(
            min(xs), min(ys), max(xs), max(ys), label, difficult)
    writer.save(class_list=list(source.classes), target_file=str(output))

    reloaded = YoloReader(str(output), image)
    assert _shape_signature(reloaded.get_shapes()) == \
        _shape_signature(source.get_shapes())


def test_v4_rc0_createml_roundtrip_preserves_box(tmp_path):
    fixture = FIXTURES / "sample-createml.json"
    source = CreateMLReader(str(fixture), "sample.jpg")
    output = tmp_path / "sample-createml.json"
    shapes = [
        {"label": shape[0], "points": shape[1]}
        for shape in source.get_shapes()
    ]
    writer = CreateMLWriter(
        "dataset", "sample.jpg", IMAGE_SIZE, shapes, str(output))
    writer.verified = source.verified
    writer.write()

    reloaded = CreateMLReader(str(output), "sample.jpg")
    assert reloaded.verified is True
    assert _shape_signature(reloaded.get_shapes()) == \
        _shape_signature(source.get_shapes())


def test_v4_rc0_coco_roundtrip_preserves_polygon(tmp_path):
    fixture = FIXTURES / "sample-coco.json"
    source = COCOReader(str(fixture), target_filename="sample.jpg")
    output = tmp_path / "sample-coco.json"
    writer = COCOWriter("dataset", "sample.jpg", IMAGE_SIZE)
    for shape in source.get_shapes():
        label, points, _line, _fill, difficult, shape_type, keypoints = shape
        if shape_type == "polygon":
            writer.add_polygon(points, label, difficult, keypoints=keypoints)
        else:
            xs, ys = zip(*points)
            writer.add_bnd_box(
                min(xs), min(ys), max(xs), max(ys), label, difficult,
                keypoints=keypoints,
            )
    writer.save(str(output))

    reloaded = COCOReader(str(output), target_filename="sample.jpg")
    assert _shape_signature(reloaded.get_shapes()) == \
        _shape_signature(source.get_shapes())


def test_v4_rc0_yolo_segmentation_roundtrip_preserves_polygon(tmp_path):
    image = QImage(100, 80, QImage.Format.Format_RGB32)
    source = YOLOSegReader(
        str(FIXTURES / "sample-yolo-seg.txt"), image,
        str(FIXTURES / "classes.txt"),
    )
    output = tmp_path / "sample-yolo-seg.txt"
    writer = YOLOSegWriter("dataset", "sample.jpg", IMAGE_SIZE)
    for label, points, _line, _fill, difficult, _shape_type in \
            source.get_shapes():
        writer.add_polygon(points, label, difficult)
    writer.save(target_file=str(output), class_list=list(source.classes))

    reloaded = YOLOSegReader(str(output), image)
    assert _shape_signature(reloaded.get_shapes()) == \
        _shape_signature(source.get_shapes())


def test_v4_rc0_vfr_sidecar_roundtrip_preserves_storage_contract(tmp_path):
    source_file = FIXTURES / "vfr-source.bin"
    project = FIXTURES / "vfr-source.bin.labelimgpp.sqlite"
    stored_source = read_project_source(str(project))
    contents = load_project(str(project))

    assert stored_source.relative_path == "vfr-source.bin"
    assert stored_source.stream_index == 0
    assert (stored_source.time_base_num, stored_source.time_base_den) == \
        (1, 1000)
    assert stored_source.fingerprint.content_matches(
        fingerprint_video(str(source_file)))
    assert contents.revision == 4
    assert tuple(item.pts for item in contents.observations) == (0, 41, 83, 150)
    assert tuple(item.review_state for item in contents.observations) == (
        "accepted", "pending", "rejected", "accepted")
    assert tuple(item.anchor for item in contents.observations) == (
        True, False, False, True)
    assert tuple(item.source for item in contents.observations) == (
        "manual", "tracker", "tracker", "manual")

    copied = tmp_path / "copied.labelimgpp.sqlite"
    save_project_as(str(project), str(copied))
    assert load_project(str(copied)) == contents
    copied_source = read_project_source(str(copied))
    assert copied_source.fingerprint == stored_source.fingerprint
    assert (
        copied_source.stream_index,
        copied_source.time_base_num,
        copied_source.time_base_den,
    ) == (0, 1, 1000)

    connection = sqlite3.connect(copied)
    try:
        assert connection.execute("PRAGMA application_id").fetchone()[0] == \
            APPLICATION_ID
        assert connection.execute("PRAGMA user_version").fetchone()[0] == \
            SCHEMA_VERSION
    finally:
        connection.close()
