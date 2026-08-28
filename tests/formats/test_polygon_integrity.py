"""Regression coverage for duplicate pointer delivery in polygon creation."""

from xml.etree import ElementTree

from PyQt5.QtCore import QPointF

from libs.core.shape import Shape, ShapeType
from libs.formats.pascal_voc_io import PascalVocWriter


def test_user_created_polygon_has_no_duplicate_pascal_voc_points():
    """A logical four-point polygon must serialize as four XML points."""
    shape = Shape(label='tree', shape_type=ShapeType.POLYGON)
    for x, y in (
            (10, 10), (10, 10), (90, 10), (90, 10),
            (90, 70), (90, 70), (10, 70), (10, 70)):
        shape.add_point(QPointF(x, y))
    shape.close()

    writer = PascalVocWriter('images', 'frame.png', (100, 120, 3))
    writer.add_polygon(
        [(point.x(), point.y()) for point in shape.points],
        shape.label, difficult=False)
    root = writer.gen_xml()
    writer.append_objects(root)
    xml = ElementTree.fromstring(ElementTree.tostring(root))

    points = [
        (float(point.findtext('x')), float(point.findtext('y')))
        for point in xml.findall('./object/polygon/pt')
    ]
    assert points == [
        (10.0, 10.0), (90.0, 10.0),
        (90.0, 70.0), (10.0, 70.0),
    ]
