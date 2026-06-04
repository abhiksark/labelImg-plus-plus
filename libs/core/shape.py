#!/usr/bin/python
# libs/core/shape.py
# -*- coding: utf-8 -*-

from enum import Enum

try:
    from PyQt5.QtGui import QColor, QPen, QPainterPath, QFont, QFontMetrics
    from PyQt5.QtCore import Qt, QPointF
except ImportError:
    from PyQt4.QtGui import QColor, QPen, QPainterPath, QFont, QFontMetrics
    from PyQt4.QtCore import Qt, QPointF

from libs.utils import distance
import sys


class ShapeType(Enum):
    """Supported annotation shape types."""

    RECTANGLE = 'rectangle'
    POLYGON = 'polygon'


MAX_POLYGON_POINTS = 100

DEFAULT_LINE_COLOR = QColor(0, 255, 0, 128)
DEFAULT_FILL_COLOR = QColor(255, 0, 0, 128)
DEFAULT_SELECT_LINE_COLOR = QColor(255, 255, 255)
DEFAULT_SELECT_FILL_COLOR = QColor(0, 128, 255, 155)
DEFAULT_VERTEX_FILL_COLOR = QColor(0, 255, 0, 255)
DEFAULT_HVERTEX_FILL_COLOR = QColor(255, 0, 0)


class Shape(object):
    P_SQUARE, P_ROUND = range(2)

    MOVE_VERTEX, NEAR_VERTEX = range(2)

    # The following class variables influence the drawing
    # of _all_ shape objects.
    line_color = DEFAULT_LINE_COLOR
    fill_color = DEFAULT_FILL_COLOR
    select_line_color = DEFAULT_SELECT_LINE_COLOR
    select_fill_color = DEFAULT_SELECT_FILL_COLOR
    vertex_fill_color = DEFAULT_VERTEX_FILL_COLOR
    h_vertex_fill_color = DEFAULT_HVERTEX_FILL_COLOR
    point_type = P_ROUND
    point_size = 16
    scale = 1.0
    label_font_size = 8

    def __init__(self, label=None, line_color=None, difficult=False,
                 paint_label=False, shape_type=ShapeType.RECTANGLE):
        self.label = label
        self.points = []
        self.fill = False
        self.selected = False
        self.difficult = difficult
        self.paint_label = paint_label
        self.shape_type = shape_type
        self.keypoints = None

        self._highlight_index = None
        self._highlight_mode = self.NEAR_VERTEX
        self._highlight_settings = {
            self.NEAR_VERTEX: (4, self.P_ROUND),
            self.MOVE_VERTEX: (1.5, self.P_SQUARE),
        }

        self._closed = False

        if line_color is not None:
            # Override the class line_color attribute
            # with an object attribute. Currently this
            # is used for drawing the pending line a different color.
            self.line_color = line_color

    def close(self):
        self._closed = True

    def reach_max_points(self):
        """Return True when the shape has reached its maximum allowed vertices."""
        if self.shape_type == ShapeType.RECTANGLE:
            return len(self.points) >= 4
        return len(self.points) >= MAX_POLYGON_POINTS

    def add_point(self, point):
        if not self.reach_max_points():
            self.points.append(point)

    def pop_point(self):
        if self.points:
            return self.points.pop()
        return None

    def remove_point(self, index):
        """Remove vertex at index.

        Polygon-only operation; enforces a minimum of 3 vertices.

        Args:
            index: The index of the vertex to remove.

        Returns:
            True if the point was removed, False otherwise.
        """
        if self.shape_type != ShapeType.POLYGON:
            return False
        if len(self.points) <= 3:
            return False
        self.points.pop(index)
        return True

    def insert_point(self, index, point):
        """Insert a vertex at the given index. Polygon-only.

        Args:
            index: Position at which to insert the new vertex.
            point: QPointF to insert.
        """
        if self.shape_type != ShapeType.POLYGON:
            return
        self.points.insert(index, point)

    def midpoint_of_edge(self, i):
        """Return the midpoint between vertex i and the next vertex.

        The last edge wraps around to vertex 0.

        Args:
            i: Edge start vertex index.

        Returns:
            QPointF midpoint of the edge.
        """
        p1 = self.points[i]
        p2 = self.points[(i + 1) % len(self.points)]
        return QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)

    def nearest_midpoint(self, point, epsilon):
        """Find nearest midpoint handle within epsilon distance.

        Polygon-only. Used for edge-click insertion of new vertices.

        Args:
            point: QPointF reference position.
            epsilon: Maximum distance to qualify as 'nearest'.

        Returns:
            Edge index whose midpoint is closest, or None.
        """
        if self.shape_type != ShapeType.POLYGON:
            return None
        best_dist = epsilon
        best_index = None
        for i in range(len(self.points)):
            mid = self.midpoint_of_edge(i)
            dist = distance(mid - point)
            if dist <= best_dist:
                best_index = i
                best_dist = dist
        return best_index

    @property
    def num_keypoints(self):
        """Count of keypoints with visibility > 0."""
        if not self.keypoints:
            return 0
        return sum(1 for kp in self.keypoints if kp is not None and kp[2] > 0)

    def is_closed(self):
        return self._closed

    def set_open(self):
        self._closed = False

    def paint(self, painter):
        if not self.points:
            return

        line_path, vertex_path = self._build_paths()
        self._draw_shape(painter, line_path, vertex_path)

        if self.paint_label:
            self._draw_label(painter)

        if self.fill:
            color = self.select_fill_color if self.selected else self.fill_color
            painter.fillPath(line_path, color)

    def _build_paths(self):
        """Build the line and vertex paths for drawing."""
        line_path = QPainterPath()
        vertex_path = QPainterPath()

        line_path.moveTo(self.points[0])
        for i, p in enumerate(self.points):
            line_path.lineTo(p)
            self.draw_vertex(vertex_path, i)

        if self.is_closed():
            line_path.lineTo(self.points[0])

        return line_path, vertex_path

    def _draw_shape(self, painter, line_path, vertex_path):
        """Draw the shape outline and vertices."""
        color = self.select_line_color if self.selected else self.line_color
        pen = QPen(color)
        pen.setWidth(max(1, int(round(2.0 / self.scale))))
        painter.setPen(pen)

        painter.drawPath(line_path)
        painter.drawPath(vertex_path)
        painter.fillPath(vertex_path, self.vertex_fill_color)

    def _draw_label(self, painter):
        """Draw the label text at the top-left corner of the shape."""
        min_x, min_y = self._get_top_left_corner()
        if min_x == sys.maxsize or min_y == sys.maxsize:
            return

        min_y_label = int(1.25 * self.label_font_size)
        if min_y < min_y_label:
            min_y += min_y_label

        font = QFont()
        font.setPointSize(self.label_font_size)
        font.setBold(True)
        painter.setFont(font)

        label_text = self.label if self.label is not None else ""
        painter.drawText(int(min_x), int(min_y), label_text)

    def _get_top_left_corner(self):
        """Get the top-left corner coordinates of the shape."""
        min_x = sys.maxsize
        min_y = sys.maxsize
        for point in self.points:
            min_x = min(min_x, point.x())
            min_y = min(min_y, point.y())
        return min_x, min_y

    def draw_vertex(self, path, i):
        d = self.point_size / self.scale
        shape = self.point_type
        point = self.points[i]
        if i == self._highlight_index:
            size, shape = self._highlight_settings[self._highlight_mode]
            d *= size
        if self._highlight_index is not None:
            self.vertex_fill_color = self.h_vertex_fill_color
        else:
            self.vertex_fill_color = Shape.vertex_fill_color
        if shape == self.P_SQUARE:
            path.addRect(point.x() - d / 2, point.y() - d / 2, d, d)
        elif shape == self.P_ROUND:
            path.addEllipse(point, d / 2.0, d / 2.0)
        else:
            assert False, "unsupported vertex shape"

    def nearest_vertex(self, point, epsilon):
        index = None
        for i, p in enumerate(self.points):
            dist = distance(p - point)
            if dist <= epsilon:
                index = i
                epsilon = dist
        return index

    def contains_point(self, point):
        return self.make_path().contains(point)

    def make_path(self):
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        return path

    def bounding_rect(self):
        return self.make_path().boundingRect()

    def move_by(self, offset):
        self.points = [p + offset for p in self.points]
        if self.keypoints:
            self.keypoints = [
                (kp[0] + offset.x(), kp[1] + offset.y(), kp[2])
                if kp is not None else None
                for kp in self.keypoints
            ]

    def move_vertex_by(self, i, offset):
        self.points[i] = self.points[i] + offset

    def highlight_vertex(self, i, action):
        self._highlight_index = i
        self._highlight_mode = action

    def highlight_clear(self):
        self._highlight_index = None

    def copy(self):
        shape = Shape(self.label, shape_type=self.shape_type)
        shape.points = [QPointF(p.x(), p.y()) for p in self.points]
        shape.fill = self.fill
        shape.selected = self.selected
        shape._closed = self._closed
        if self.line_color != Shape.line_color:
            shape.line_color = self.line_color
        if self.fill_color != Shape.fill_color:
            shape.fill_color = self.fill_color
        shape.difficult = self.difficult
        if self.keypoints is not None:
            shape.keypoints = list(self.keypoints)
        return shape

    def __len__(self):
        return len(self.points)

    def __getitem__(self, key):
        return self.points[key]

    def __setitem__(self, key, value):
        self.points[key] = value
