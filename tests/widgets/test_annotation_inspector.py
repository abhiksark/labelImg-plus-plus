# tests/widgets/test_annotation_inspector.py
"""Roles, identity, filtering, and mutation requests for the unified model."""

import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from libs.core.shape import Shape, ShapeType
from libs.core.video_model import VideoProjectModel
from libs.core.video_types import ObservationRecord
from libs.widgets.annotationInspector import (
    AnnotationFilterProxyModel, AnnotationListModel, AnnotationRoles,
)


def test_image_rows_keep_shape_identity_and_expose_semantic_roles():
    rectangle = Shape('car', shape_type=ShapeType.RECTANGLE)
    rectangle.line_color = QColor(10, 20, 30)
    rectangle.difficult = True
    polygon = Shape('road', shape_type=ShapeType.POLYGON)
    model = AnnotationListModel()

    model.set_image_shapes((rectangle, polygon))

    first = model.index(0, 0)
    identity = model.data(first, AnnotationRoles.Identity)
    assert model.rowCount() == 2
    assert identity == model.identity_for_shape(rectangle)
    assert model.data(first, AnnotationRoles.Object) is rectangle
    assert model.data(first, AnnotationRoles.Type) == 'rectangle'
    assert model.data(first, AnnotationRoles.Class) == 'car'
    assert model.data(first, AnnotationRoles.Difficult) is True
    assert model.data(first, AnnotationRoles.Provenance) == 'manual'
    assert model.index_for_identity(identity).row() == 0

    model.set_image_shapes((polygon, rectangle))
    assert model.index_for_identity(identity).row() == 1


def test_visibility_and_class_edits_are_requests_not_geometry_mutations():
    shape = Shape('car')
    model = AnnotationListModel()
    model.set_image_shapes((shape,))
    index = model.index(0, 0)
    visibility = []
    edits = []
    model.visibilityChangeRequested.connect(
        lambda identity, value: visibility.append((identity, value)))
    model.classEditRequested.connect(
        lambda identity, value: edits.append((identity, value)))

    assert model.setData(index, Qt.Unchecked, Qt.CheckStateRole)
    assert model.setData(index, 'vehicle', Qt.EditRole)

    identity = model.identity_for_shape(shape)
    assert visibility == [(identity, False)]
    assert edits == [(identity, 'vehicle')]
    assert shape.label == 'car'
    assert model.data(index, AnnotationRoles.Visible) is False


def test_proxy_searches_class_type_provenance_and_identity():
    rectangle = Shape('delivery van')
    polygon = Shape('loading zone', shape_type=ShapeType.POLYGON)
    model = AnnotationListModel()
    model.set_image_shapes((rectangle, polygon))
    proxy = AnnotationFilterProxyModel()
    proxy.setSourceModel(model)

    for query, expected in (
            ('delivery', 1), ('polygon', 1), ('manual', 2),
            (model.identity_for_shape(polygon), 1), ('missing', 0)):
        proxy.set_search_text(query)
        assert proxy.rowCount() == expected


def test_video_rows_include_absent_tracks_span_and_pending_state():
    model = VideoProjectModel()
    first = model.create_track(
        'car', 'rectangle', (1, 2, 3, 255), track_id='track-car')
    second = model.create_track(
        'person', 'polygon', (4, 5, 6, 255), track_id='track-person')
    model.upsert_manual(first.track_id, 10, [0, 0, 10, 10])
    model.upsert_manual(first.track_id, 30, [10, 0, 20, 10])
    model.upsert_tracker(ObservationRecord(
        first.track_id, 20, [5, 0, 15, 10], source='tracker',
        review_state='pending', quality=.8))

    inspector = AnnotationListModel()
    inspector.set_video_context(
        model, 20, start_pts=0, time_base_num=1, time_base_den=10)
    car = inspector.index_for_identity('track-car')
    person = inspector.index_for_identity('track-person')

    assert inspector.rowCount() == 2
    assert inspector.data(car, AnnotationRoles.VideoSpan) == (10, 30)
    assert inspector.data(car, AnnotationRoles.PendingReview) is True
    assert inspector.data(car, AnnotationRoles.Provenance) == 'pending'
    assert inspector.data(car, AnnotationRoles.CurrentRenderState) == 'pending'
    assert '10-30' not in inspector.data(car, Qt.DisplayRole)
    assert '00:00:01.000–00:00:03.000' in \
        inspector.data(car, Qt.DisplayRole)
    assert 'exact PTS 10–30' in inspector.data(car, Qt.ToolTipRole)
    assert inspector.data(person, AnnotationRoles.VideoSpan) is None
    assert inspector.data(person, AnnotationRoles.CurrentRenderState) == 'absent'
    assert inspector.data(person, AnnotationRoles.Identity) == second.track_id
