"""Lazy PyAV compatibility adapter and frame-accurate video decoder."""

from dataclasses import dataclass
from fractions import Fraction
import importlib
import math
import os
import struct

from PyQt5.QtGui import QImage

from libs.core.video_project import fingerprint_video
from libs.core.video_types import (
    VideoFrameRef, VideoFrameResult, VideoSessionSnapshot,
)


VIDEO_EXTENSIONS = ('.mp4', '.mov', '.mkv', '.avi')
VIDEO_INSTALL_HINT = (
    'Smart video annotation requires optional dependencies. Install them with '
    '`pip install "labelimgplusplus[video]"`.')


class VideoDependencyError(RuntimeError):
    pass


class VideoDecodeError(RuntimeError):
    pass


def load_video_dependencies():
    """Import optional modules only after a video operation is requested."""
    try:
        av = importlib.import_module('av')
        np = importlib.import_module('numpy')
    except ImportError as exc:
        raise VideoDependencyError('%s (%s)' % (VIDEO_INSTALL_HINT, exc))
    return av, np


def pyav_major():
    av, _np = load_video_dependencies()
    return int(av.__version__.split('.', 1)[0])


def _fraction_parts(value):
    value = Fraction(value)
    return int(value.numerator), int(value.denominator)


def _normalized_rotation(value, fallback=0):
    try:
        value = int(round(float(value))) % 360
    except (TypeError, ValueError):
        value = int(fallback) % 360
    return value if value in (0, 90, 180, 270) else int(fallback) % 360


def _rotation_for_stream(stream):
    """Read rotation from old PyAV stream side data or metadata."""
    side_data = getattr(stream, 'side_data', None)
    if side_data is not None:
        try:
            value = side_data.get('DISPLAYMATRIX')
        except AttributeError:
            value = None
        if value is not None:
            return _normalized_rotation(value)
    metadata = getattr(stream, 'metadata', {})
    return _normalized_rotation(metadata.get('rotate', 0))


def _frame_display_matrix_rotation(frame):
    """Decode raw DISPLAYMATRIX side data used by PyAV 13 through 16."""
    for item in getattr(frame, 'side_data', ()):
        item_type = getattr(item, 'type', None)
        name = getattr(item_type, 'name', str(item_type))
        if str(name).split('.')[-1] != 'DISPLAYMATRIX':
            continue
        try:
            matrix = struct.unpack('=9i', bytes(item)[:36])
        except (TypeError, ValueError, struct.error):
            return None
        if matrix[0] == 0 and matrix[1] == 0:
            return None
        return _normalized_rotation(
            -math.degrees(math.atan2(matrix[1], matrix[0])))
    return None


def _rotation_for_frame(frame, fallback=0):
    """Read FFmpeg display-matrix rotation when PyAV exposes it."""
    matrix_rotation = _frame_display_matrix_rotation(frame)
    if matrix_rotation is not None:
        return matrix_rotation
    try:
        value = _normalized_rotation(frame.rotation, fallback)
    except (AttributeError, TypeError, ValueError):
        return _normalized_rotation(fallback)
    # PyAV 17+ returns zero when no display matrix is attached. Preserve an
    # older stream-level rotation in that case.
    if value == 0 and _normalized_rotation(fallback) != 0:
        return _normalized_rotation(fallback)
    return value


def _oriented_array(frame, rotation, np):
    array = frame.to_ndarray(format='rgb24')
    if rotation == 90:
        array = np.rot90(array, 3)
    elif rotation == 180:
        array = np.rot90(array, 2)
    elif rotation == 270:
        array = np.rot90(array, 1)
    return np.ascontiguousarray(array)


@dataclass(frozen=True)
class PreparedVideoOpen:
    snapshot: VideoSessionSnapshot
    decoder: object
    tracks: tuple
    observations: tuple
    frame_states: tuple
    classes: tuple


class VideoDecoderSession:
    """One decoder context serialized by TaskCoordinator's video lane."""

    def __init__(self, source_path, stream_index=None, cancelled=None):
        av, np = load_video_dependencies()
        self._av = av
        self._np = np
        self.source_path = os.path.abspath(os.fspath(source_path))
        self.fingerprint = fingerprint_video(
            self.source_path, cancelled=cancelled)
        if self.fingerprint is None:
            raise VideoDecodeError('video opening was cancelled')
        self.container = av.open(self.source_path, mode='r')
        streams = list(self.container.streams.video)
        if stream_index is None:
            stream = next((item for item in streams
                           if item.codec_context is not None), None)
        else:
            stream = next((item for item in streams
                           if item.index == stream_index), None)
        if stream is None:
            self.close()
            raise VideoDecodeError('no playable video stream found')
        self.stream = stream
        self.stream_index = int(stream.index)
        self.time_base = Fraction(stream.time_base)
        self.time_base_num, self.time_base_den = _fraction_parts(
            self.time_base)
        self.rotation = _rotation_for_stream(stream)
        self.width = int(stream.codec_context.width or stream.width or 0)
        self.height = int(stream.codec_context.height or stream.height or 0)
        if self.width <= 0 or self.height <= 0:
            self.close()
            raise VideoDecodeError('video stream has invalid dimensions')
        self.oriented_width = (
            self.height if self.rotation in (90, 270) else self.width)
        self.oriented_height = (
            self.width if self.rotation in (90, 270) else self.height)
        self.duration_pts = (
            int(stream.duration) if stream.duration is not None else None)
        self.start_pts = (
            int(stream.start_time) if stream.start_time is not None else None)
        self.codec = str(getattr(stream.codec_context, 'name', '') or
                         getattr(stream.codec, 'name', '') or 'unknown')
        rate = getattr(stream, 'average_rate', None)
        if rate is not None:
            self.average_rate_num, self.average_rate_den = _fraction_parts(rate)
        else:
            self.average_rate_num = self.average_rate_den = None
        self._iterator = iter(self.container.decode(self.stream))
        self._history = []
        self._closed = False

    def _result(self, frame):
        if frame.pts is None:
            raise VideoDecodeError('decoded frame has no presentation timestamp')
        rotation = _rotation_for_frame(frame, self.rotation)
        if rotation != self.rotation:
            self.rotation = rotation
            self.oriented_width = (
                self.height if rotation in (90, 270) else self.width)
            self.oriented_height = (
                self.width if rotation in (90, 270) else self.height)
        array = _oriented_array(frame, rotation, self._np)
        height, width = array.shape[:2]
        image = QImage(
            array.data, width, height, int(array.strides[0]),
            QImage.Format_RGB888).copy()
        frame_ref = VideoFrameRef(
            self.fingerprint, self.stream_index, int(frame.pts),
            self.time_base_num, self.time_base_den)
        byte_size = int(image.sizeInBytes()) if hasattr(
            image, 'sizeInBytes') else int(image.byteCount())
        result = VideoFrameResult(
            frame_ref, image, width, height, self.width, self.height,
            rotation, byte_size,
            '%s:%s:%s' % (self.fingerprint.sampled_sha256,
                          self.stream_index, frame.pts))
        self._history.append(result)
        if len(self._history) > 24:
            del self._history[:-24]
        return result

    def decode_first(self, cancelled=None):
        for frame in self._iterator:
            if cancelled is not None and cancelled():
                raise VideoDecodeError('video opening was cancelled')
            if frame.pts is not None:
                return self._result(frame)
        raise VideoDecodeError('video stream contains no decodable frames')

    def next_frame(self, cancelled=None):
        for frame in self._iterator:
            if cancelled is not None and cancelled():
                return None
            if frame.pts is not None:
                return self._result(frame)
        return None

    def seek_pts(self, target_pts, mode='nearest', cancelled=None):
        """Seek to a stream PTS and decode forward from a keyframe."""
        target_pts = int(target_pts)
        self.container.seek(
            target_pts, stream=self.stream, backward=True, any_frame=False)
        self._iterator = iter(self.container.decode(self.stream))
        previous = None
        for frame in self._iterator:
            if cancelled is not None and cancelled():
                return None
            if frame.pts is None:
                continue
            pts = int(frame.pts)
            result = self._result(frame)
            if mode == 'at_or_after':
                if pts >= target_pts:
                    return result
            elif pts >= target_pts:
                if previous is None:
                    return result
                if abs(previous.frame_ref.pts - target_pts) <= abs(
                        pts - target_pts):
                    return previous
                return result
            previous = result
        return previous

    def previous_frame(self, current_ref, cancelled=None):
        for result in reversed(self._history[:-1]):
            if result.frame_ref.pts < current_ref.pts:
                return result
        rate = (self.average_rate_num / self.average_rate_den
                if self.average_rate_num and self.average_rate_den else 30.0)
        step_pts = max(1, int(round(1.0 / rate / float(self.time_base))))
        target = max(self.start_pts or 0, current_ref.pts - step_pts * 3)
        candidate = self.seek_pts(target, mode='at_or_after', cancelled=cancelled)
        previous = None
        while candidate is not None and candidate.frame_ref.pts < current_ref.pts:
            previous = candidate
            candidate = self.next_frame(cancelled=cancelled)
        return previous

    def snapshot(self, project_path, initial_frame, revision=0,
                 read_only=False):
        return VideoSessionSnapshot(
            source_path=self.source_path,
            project_path=project_path,
            fingerprint=self.fingerprint,
            stream_index=self.stream_index,
            time_base_num=self.time_base_num,
            time_base_den=self.time_base_den,
            width=self.oriented_width,
            height=self.oriented_height,
            rotation=self.rotation,
            codec=self.codec,
            duration_pts=self.duration_pts,
            start_pts=self.start_pts,
            average_rate_num=self.average_rate_num,
            average_rate_den=self.average_rate_den,
            revision=revision,
            initial_frame=initial_frame,
            read_only=read_only,
        )

    def close(self):
        if getattr(self, '_closed', False):
            return
        self._closed = True
        container = getattr(self, 'container', None)
        self.container = None
        self._iterator = iter(())
        if container is not None:
            container.close()
