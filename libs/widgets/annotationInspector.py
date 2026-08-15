# libs/widgets/annotationInspector.py
"""Unified, geometry-free projection for image shapes and video tracks."""

try:
    from PyQt5.QtCore import (
        QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal,
    )
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QListView
except ImportError:
    from PyQt4.QtCore import (
        QAbstractListModel, QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal,
    )
    from PyQt4.QtGui import QColor, QListView


class AnnotationRoles(object):
    Identity = Qt.UserRole + 1
    Type = Qt.UserRole + 2
    Class = Qt.UserRole + 3
    Color = Qt.UserRole + 4
    Visible = Qt.UserRole + 5
    Difficult = Qt.UserRole + 6
    Selected = Qt.UserRole + 7
    Provenance = Qt.UserRole + 8
    VideoSpan = Qt.UserRole + 9
    CurrentRenderState = Qt.UserRole + 10
    PendingReview = Qt.UserRole + 11
    Keyframe = Qt.UserRole + 12
    Object = Qt.UserRole + 13


class AnnotationListModel(QAbstractListModel):
    """Observe canonical controllers without owning copied geometry."""

    visibilityChangeRequested = pyqtSignal(str, bool)
    classEditRequested = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super(AnnotationListModel, self).__init__(parent)
        self._kind = 'image'
        self._rows = []
        self._video_model = None
        self._pts = None
        self._start_pts = 0
        self._time_base_num = 1
        self._time_base_den = 1
        self._selected_identity = None
        self._visibility = {}

    def roleNames(self):
        names = dict(super(AnnotationListModel, self).roleNames())
        names.update({
            AnnotationRoles.Identity: b'identity',
            AnnotationRoles.Type: b'type',
            AnnotationRoles.Class: b'className',
            AnnotationRoles.Color: b'color',
            AnnotationRoles.Visible: b'visible',
            AnnotationRoles.Difficult: b'difficult',
            AnnotationRoles.Selected: b'selected',
            AnnotationRoles.Provenance: b'provenance',
            AnnotationRoles.VideoSpan: b'videoSpan',
            AnnotationRoles.CurrentRenderState: b'currentRenderState',
            AnnotationRoles.PendingReview: b'pendingReview',
            AnnotationRoles.Keyframe: b'keyframe',
        })
        return names

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def set_image_shapes(self, shapes):
        self.beginResetModel()
        self._kind = 'image'
        self._video_model = None
        self._pts = None
        self._start_pts = 0
        self._time_base_num = 1
        self._time_base_den = 1
        self._rows = list(shapes)
        live = set(self.identity_for_shape(shape) for shape in self._rows)
        self._visibility = {
            key: value for key, value in self._visibility.items()
            if key in live}
        self.endResetModel()

    def set_video_context(self, model, pts, start_pts=0, time_base_num=1,
                          time_base_den=1):
        self.beginResetModel()
        self._kind = 'video'
        self._video_model = model
        self._pts = None if pts is None else int(pts)
        self._start_pts = int(start_pts or 0)
        self._time_base_num = int(time_base_num)
        self._time_base_den = max(1, int(time_base_den))
        self._rows = ([] if model is None else list(model.tracks))
        live = set(self._rows)
        self._visibility = {
            key: value for key, value in self._visibility.items()
            if key in live}
        self.endResetModel()

    def _elapsed(self, pts):
        milliseconds = max(0, int(round(
            (int(pts) - self._start_pts) * self._time_base_num * 1000 /
            self._time_base_den)))
        seconds, milliseconds = divmod(milliseconds, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return '%02d:%02d:%02d.%03d' % (
            hours, minutes, seconds, milliseconds)

    def clear(self):
        self.set_image_shapes(())

    @staticmethod
    def identity_for_shape(shape):
        return 'shape:%x' % id(shape)

    def identity_at(self, index):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        row = self._rows[index.row()]
        return row if self._kind == 'video' else self.identity_for_shape(row)

    def shape_at(self, index):
        if self._kind != 'image' or not index.isValid():
            return None
        return self._rows[index.row()]

    def object_for_identity(self, identity):
        if self._kind == 'video':
            return None
        return next((shape for shape in self._rows
                     if self.identity_for_shape(shape) == identity), None)

    def index_for_identity(self, identity):
        for row in range(len(self._rows)):
            if self.identity_at(self.index(row, 0)) == identity:
                return self.index(row, 0)
        return QModelIndex()

    def set_selected_identity(self, identity):
        if identity == self._selected_identity:
            return
        old = self.index_for_identity(self._selected_identity)
        self._selected_identity = identity
        new = self.index_for_identity(identity)
        for index in (old, new):
            if index.isValid():
                self.dataChanged.emit(index, index, [AnnotationRoles.Selected])

    def _video_values(self, track_id):
        model = self._video_model
        track = model.tracks[track_id]
        observations = [
            item for item in model.observations.values()
            if item.track_id == track_id]
        current = (None if self._pts is None else
                   model.materialize_one(track_id, self._pts))
        if current is None:
            render_state = 'absent'
            provenance = 'manual' if any(
                item.source == 'manual' for item in observations) else 'tracker'
            keyframe = False
        else:
            render_state = current.render_state
            observation = current.observation
            provenance = ('interpolation' if render_state == 'interpolation'
                          else ('pending' if render_state == 'pending'
                                else observation.source))
            keyframe = bool(observation.anchor)
        span = (None if not observations else (
            min(item.pts for item in observations),
            max(item.pts for item in observations)))
        pending = any(item.review_state == 'pending' for item in observations)
        return track, span, render_state, provenance, pending, keyframe

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        identity = self.identity_at(index)
        if self._kind == 'video':
            track, span, render, provenance, pending, keyframe = \
                self._video_values(identity)
            class_name = track.label
            shape_type = track.shape_type
            color = QColor(*track.color)
            difficult = track.difficult
            if span is None:
                span_text = 'empty'
                tooltip = 'Track %s' % identity
            else:
                span_text = '%s–%s' % (
                    self._elapsed(span[0]), self._elapsed(span[1]))
                tooltip = 'Track %s · exact PTS %s–%s' % (
                    identity, span[0], span[1])
            display = '%s  · %s  · %s' % (
                class_name, shape_type, span_text)
            object_value = None
        else:
            shape = self._rows[index.row()]
            class_name = shape.label
            shape_type = shape.shape_type.value
            color = shape.line_color
            difficult = shape.difficult
            span = None
            render = 'exact'
            provenance = 'manual'
            pending = False
            keyframe = False
            display = '%s  · %s' % (class_name, shape_type)
            tooltip = None
            object_value = shape
        values = {
            Qt.DisplayRole: display,
            Qt.ToolTipRole: tooltip,
            Qt.EditRole: class_name,
            Qt.CheckStateRole: (Qt.Checked if self._visibility.get(
                identity, True) else Qt.Unchecked),
            # Row text uses the theme's own foreground. Painting it in the
            # shape colour capped contrast at 3.7:1 (dark) / 2.8:1 (light),
            # because every shape colour carries alpha and composites toward
            # the panel. The colour stays available through AnnotationRoles
            # .Color for anything that wants to draw an opaque swatch.
            AnnotationRoles.Identity: identity,
            AnnotationRoles.Type: shape_type,
            AnnotationRoles.Class: class_name,
            AnnotationRoles.Color: color,
            AnnotationRoles.Visible: self._visibility.get(identity, True),
            AnnotationRoles.Difficult: bool(difficult),
            AnnotationRoles.Selected: identity == self._selected_identity,
            AnnotationRoles.Provenance: provenance,
            AnnotationRoles.VideoSpan: span,
            AnnotationRoles.CurrentRenderState: render,
            AnnotationRoles.PendingReview: pending,
            AnnotationRoles.Keyframe: keyframe,
            AnnotationRoles.Object: object_value,
        }
        return values.get(role)

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        return (Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                Qt.ItemIsUserCheckable | Qt.ItemIsEditable)

    def setData(self, index, value, role=Qt.EditRole):
        identity = self.identity_at(index)
        if identity is None:
            return False
        if role == Qt.CheckStateRole:
            visible = value == Qt.Checked
            if self._visibility.get(identity, True) == visible:
                return False
            self._visibility[identity] = visible
            self.dataChanged.emit(index, index, [
                Qt.CheckStateRole, AnnotationRoles.Visible])
            self.visibilityChangeRequested.emit(identity, visible)
            return True
        if role == Qt.EditRole:
            label = str(value).strip()
            if not label or label == self.data(index, AnnotationRoles.Class):
                return False
            self.classEditRequested.emit(identity, label)
            return True
        return False

    def notify_identity_changed(self, identity):
        index = self.index_for_identity(identity)
        if index.isValid():
            self.dataChanged.emit(index, index)


class AnnotationFilterProxyModel(QSortFilterProxyModel):
    """Filter across class, type, provenance, and stable identity."""

    def __init__(self, parent=None):
        super(AnnotationFilterProxyModel, self).__init__(parent)
        self._query = ''
        self.setDynamicSortFilter(True)

    def set_search_text(self, text):
        self._query = str(text).strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._query:
            return True
        model = self.sourceModel()
        index = model.index(source_row, 0, source_parent)
        values = (
            model.data(index, AnnotationRoles.Class),
            model.data(index, AnnotationRoles.Type),
            model.data(index, AnnotationRoles.Provenance),
            model.data(index, AnnotationRoles.Identity),
        )
        return self._query in ' '.join(str(value) for value in values).casefold()


class UnifiedAnnotationView(QListView):
    """Named compatibility surface for the single annotation projection."""

    def count(self):
        return self.model().rowCount() if self.model() is not None else 0
