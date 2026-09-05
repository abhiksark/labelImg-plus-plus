"""In-memory track domain, materialization, and coalesced save deltas."""

from dataclasses import dataclass, replace
import uuid

from libs.core.video_types import (
    FrameStateRecord, ObservationRecord, PropagationResult, TrackGapRecord,
    TrackRecord, VideoSaveRequest,
)


@dataclass(frozen=True)
class MaterializedTrack:
    track: TrackRecord
    observation: ObservationRecord
    render_state: str  # exact, interpolation, or pending


@dataclass(frozen=True)
class VideoModelState:
    tracks: tuple
    observations: tuple
    frame_states: tuple
    classes: tuple
    gaps: tuple = ()


def _interpolate_keypoints(left, right, ratio):
    if left is None or right is None or len(left) != len(right):
        return None
    result = []
    nearest = left if ratio < .5 else right
    for index, (first, second) in enumerate(zip(left, right)):
        if first is None or second is None:
            result.append(nearest[index])
            continue
        result.append([
            first[0] + (second[0] - first[0]) * ratio,
            first[1] + (second[1] - first[1]) * ratio,
            nearest[index][2],
        ])
    return result


def interpolate_rectangle(left, right, pts):
    if not left.present or not right.present:
        return None
    if left.geometry is None or right.geometry is None:
        return None
    if len(left.geometry) != 4 or len(right.geometry) != 4:
        return None
    if right.pts <= left.pts or not left.pts < pts < right.pts:
        return None
    ratio = (pts - left.pts) / (right.pts - left.pts)
    geometry = [
        first + (second - first) * ratio
        for first, second in zip(left.geometry, right.geometry)
    ]
    return ObservationRecord(
        track_id=left.track_id, pts=int(pts), geometry=geometry,
        keypoints=_interpolate_keypoints(
            left.keypoints, right.keypoints, ratio),
        present=True, source='manual', review_state='accepted',
        anchor=False, quality=None,
        revision=max(left.revision, right.revision))


class VideoProjectModel:
    """Mutable only on the GUI thread; workers receive immutable deltas."""

    def __init__(self, revision=0, tracks=(), observations=(),
                 frame_states=(), classes=(), gaps=()):
        self.durable_revision = int(revision)
        self.revision = int(revision)
        self.tracks = {item.track_id: item for item in tracks}
        self.observations = {
            (item.track_id, int(item.pts)): item for item in observations}
        self.frame_states = {int(item.pts): item for item in frame_states}
        self.gaps = {
            (item.track_id, int(item.start_pts), int(item.end_pts)): item
            for item in gaps}
        self.classes = list(classes)
        self._changed_tracks = {}
        self._changed_observations = {}
        self._changed_frames = {}
        self._changed_gaps = {}
        self._deleted_observations = {}
        self._deleted_gaps = {}
        self._deleted_tracks = {}
        self._classes_changed_revision = None

    @property
    def dirty(self):
        return self.revision != self.durable_revision

    def snapshot_state(self):
        return VideoModelState(
            tuple(self.tracks.values()),
            tuple(sorted(self.observations.values(),
                         key=lambda item: (item.pts, item.track_id))),
            tuple(sorted(self.frame_states.values(),
                         key=lambda item: item.pts)),
            tuple(self.classes),
            tuple(sorted(self.gaps.values(), key=lambda item: (
                item.start_pts, item.end_pts, item.track_id))))

    def restore_state(self, state):
        self._advance()
        revision = self.revision
        old_track_ids = set(self.tracks)
        old_observation_keys = set(self.observations)
        old_gap_keys = set(self.gaps)
        self.tracks = {
            item.track_id: replace(item, revision=revision)
            for item in state.tracks}
        self.observations = {
            (item.track_id, item.pts): replace(item, revision=revision)
            for item in state.observations}
        self.frame_states = {
            item.pts: replace(item, revision=revision)
            for item in state.frame_states}
        self.gaps = {
            (item.track_id, item.start_pts, item.end_pts): replace(
                item, revision=revision)
            for item in getattr(state, 'gaps', ())}
        self.classes = list(state.classes)
        self._changed_tracks.update(self.tracks)
        self._changed_observations.update(self.observations)
        self._changed_frames.update(self.frame_states)
        self._changed_gaps.update(self.gaps)
        for track_id in old_track_ids - set(self.tracks):
            self._deleted_tracks[track_id] = revision
        for key in old_observation_keys - set(self.observations):
            self._deleted_observations[key] = revision
        for key in old_gap_keys - set(self.gaps):
            self._deleted_gaps[key] = revision
        self._classes_changed_revision = revision

    def _advance(self):
        self.revision += 1
        return self.revision

    def create_track(self, label, shape_type, color, difficult=False,
                     track_id=None):
        revision = self._advance()
        track = TrackRecord(
            track_id or str(uuid.uuid4()), label, shape_type, tuple(color),
            bool(difficult), revision)
        self.tracks[track.track_id] = track
        self._changed_tracks[track.track_id] = track
        self._deleted_tracks.pop(track.track_id, None)
        if label not in self.classes:
            self.classes.append(label)
            self._classes_changed_revision = revision
        return track

    def rename_track(self, track_id, label):
        track = self.tracks[track_id]
        if track.label == label:
            return track
        revision = self._advance()
        track = replace(track, label=label, revision=revision)
        self.tracks[track_id] = track
        self._changed_tracks[track_id] = track
        if label not in self.classes:
            self.classes.append(label)
            self._classes_changed_revision = revision
        return track

    def update_track(self, track_id, color=None, difficult=None):
        track = self.tracks[track_id]
        revision = self._advance()
        track = replace(
            track,
            color=(tuple(color) if color is not None else track.color),
            difficult=(bool(difficult) if difficult is not None
                       else track.difficult),
            revision=revision)
        self.tracks[track_id] = track
        self._changed_tracks[track_id] = track
        return track

    def upsert_manual(self, track_id, pts, geometry, keypoints=None,
                      present=True):
        revision = self._advance()
        observation = ObservationRecord(
            track_id, int(pts), geometry, keypoints=keypoints,
            present=bool(present), source='manual',
            review_state='accepted', anchor=True, revision=revision)
        key = (track_id, int(pts))
        self.observations[key] = observation
        self._changed_observations[key] = observation
        self._deleted_observations.pop(key, None)
        track = self.tracks.get(track_id)
        if track is not None:
            track = replace(track, revision=revision)
            self.tracks[track_id] = track
            self._changed_tracks[track_id] = track
        return observation

    def upsert_tracker(self, observation, replace_reviewed=False):
        key = (observation.track_id, int(observation.pts))
        existing = self.observations.get(key)
        if existing is not None:
            if existing.source == 'manual' or (
                    existing.review_state == 'accepted'
                    and not replace_reviewed):
                return existing
        revision = self._advance()
        value = replace(
            observation, source='tracker', anchor=False,
            revision=revision)
        self.observations[key] = value
        self._changed_observations[key] = value
        self._deleted_observations.pop(key, None)
        return value

    def upsert_gap(self, gap):
        if not isinstance(gap, TrackGapRecord):
            raise TypeError('gap must be a TrackGapRecord')
        if int(gap.end_pts) < int(gap.start_pts):
            raise ValueError('gap end_pts must be greater than or equal to start_pts')
        if gap.track_id not in self.tracks:
            raise KeyError(gap.track_id)
        revision = self._advance()
        key = (gap.track_id, int(gap.start_pts), int(gap.end_pts))
        value = replace(
            gap, start_pts=key[1], end_pts=key[2], revision=revision)
        self.gaps[key] = value
        self._changed_gaps[key] = value
        self._deleted_gaps.pop(key, None)
        track = replace(self.tracks[gap.track_id], revision=revision)
        self.tracks[gap.track_id] = track
        self._changed_tracks[gap.track_id] = track
        return value

    def apply_propagation_result(self, result):
        """Atomically apply accepted generated observations and gaps.

        Validation is completed before the model advances. Existing manual
        observations are immutable barriers, and gaps replace generated data
        in their inclusive intervals without affecting other tracks.
        """
        if not isinstance(result, PropagationResult):
            raise TypeError('result must be a PropagationResult')
        observations = {}
        for item in result.observations:
            if item.track_id not in self.tracks:
                raise KeyError(item.track_id)
            if (item.source != 'tracker'
                    or item.review_state not in ('accepted', 'pending')
                    or item.anchor):
                raise ValueError(
                    'propagation observations must be unanchored tracker data '
                    'awaiting or having passed review')
            observations[(item.track_id, int(item.pts))] = item
        gaps = {}
        for item in result.gaps:
            if not isinstance(item, TrackGapRecord):
                raise TypeError('propagation gaps must be TrackGapRecord values')
            if item.track_id not in self.tracks:
                raise KeyError(item.track_id)
            if int(item.end_pts) < int(item.start_pts):
                raise ValueError(
                    'gap end_pts must be greater than or equal to start_pts')
            key = (item.track_id, int(item.start_pts), int(item.end_pts))
            gaps[key] = item

        accepted = {}
        for key, item in observations.items():
            existing = self.observations.get(key)
            if existing is not None and existing.source == 'manual':
                continue
            if any(gap.track_id == item.track_id
                   and gap.start_pts <= item.pts <= gap.end_pts
                   for gap in gaps.values()):
                continue
            accepted[key] = item
        if not accepted and not gaps:
            return result

        revision = self._advance()
        touched_tracks = set()
        for gap in gaps.values():
            for key, current in tuple(self.observations.items()):
                if (key[0] == gap.track_id
                        and gap.start_pts <= key[1] <= gap.end_pts
                        and current.source != 'manual'):
                    del self.observations[key]
                    self._changed_observations.pop(key, None)
                    self._deleted_observations[key] = revision
            key = (gap.track_id, int(gap.start_pts), int(gap.end_pts))
            value = replace(gap, start_pts=key[1], end_pts=key[2],
                            revision=revision)
            self.gaps[key] = value
            self._changed_gaps[key] = value
            self._deleted_gaps.pop(key, None)
            touched_tracks.add(gap.track_id)
        for key, item in accepted.items():
            for gap_key, gap in tuple(self.gaps.items()):
                if (gap.track_id == item.track_id
                        and gap.start_pts <= item.pts <= gap.end_pts):
                    del self.gaps[gap_key]
                    self._changed_gaps.pop(gap_key, None)
                    self._deleted_gaps[gap_key] = revision
            value = replace(item, pts=key[1], revision=revision)
            self.observations[key] = value
            self._changed_observations[key] = value
            self._deleted_observations.pop(key, None)
            touched_tracks.add(item.track_id)
        for track_id in touched_tracks:
            track = replace(self.tracks[track_id], revision=revision)
            self.tracks[track_id] = track
            self._changed_tracks[track_id] = track
        return PropagationResult(
            result.request_id, result.generation, revision,
            observations=tuple(
                self.observations[key] for key in accepted),
            gaps=tuple(self.gaps[key] for key in gaps),
            failures=result.failures)

    def apply_regeneration_result(self, result, track_id, intervals):
        """Replace generated data strictly inside correction segments.

        Manual anchors, other tracks, and generated data outside the supplied
        open intervals are preserved. The replacement advances the model at
        most once so it can be represented by one undo command.
        """
        if not isinstance(result, PropagationResult):
            raise TypeError('result must be a PropagationResult')
        if track_id not in self.tracks:
            raise KeyError(track_id)
        ranges = tuple(sorted(
            (int(start), int(end)) for start, end in intervals))
        if not ranges or any(end <= start for start, end in ranges):
            raise ValueError('regeneration intervals must have start < end')

        def inside(pts):
            return any(start < int(pts) < end for start, end in ranges)

        observations = {}
        for item in result.observations:
            if item.track_id != track_id:
                raise ValueError('regeneration result contains another track')
            if (item.source != 'tracker'
                    or item.review_state not in ('accepted', 'pending')
                    or item.anchor):
                raise ValueError(
                    'regeneration observations must be unanchored tracker data '
                    'awaiting or having passed review')
            if inside(item.pts):
                observations[(track_id, int(item.pts))] = item
        gaps = {}
        for item in result.gaps:
            if not isinstance(item, TrackGapRecord):
                raise TypeError('regeneration gaps must be TrackGapRecord values')
            if item.track_id != track_id:
                raise ValueError('regeneration gap contains another track')
            for start, end in ranges:
                start_pts = max(int(item.start_pts), start + 1)
                end_pts = min(int(item.end_pts), end - 1)
                if end_pts >= start_pts:
                    value = replace(
                        item, start_pts=start_pts, end_pts=end_pts)
                    gaps[(track_id, start_pts, end_pts)] = value

        stale_observations = [
            key for key, item in self.observations.items()
            if key[0] == track_id and inside(key[1])
            and item.source != 'manual']
        stale_gaps = [
            key for key, item in self.gaps.items()
            if item.track_id == track_id
            and any(item.end_pts > start and item.start_pts < end
                    for start, end in ranges)]
        retained_gap_pieces = []
        for key in stale_gaps:
            item = self.gaps[key]
            pieces = [(int(item.start_pts), int(item.end_pts))]
            for start, end in ranges:
                cut_start, cut_end = start + 1, end - 1
                next_pieces = []
                for piece_start, piece_end in pieces:
                    if piece_end < cut_start or piece_start > cut_end:
                        next_pieces.append((piece_start, piece_end))
                        continue
                    if piece_start < cut_start:
                        next_pieces.append((piece_start, cut_start - 1))
                    if piece_end > cut_end:
                        next_pieces.append((cut_end + 1, piece_end))
                pieces = next_pieces
            retained_gap_pieces.extend(
                replace(item, start_pts=start, end_pts=end)
                for start, end in pieces if end >= start)
        if not stale_observations and not stale_gaps \
                and not observations and not gaps:
            return result

        revision = self._advance()
        for key in stale_observations:
            del self.observations[key]
            self._changed_observations.pop(key, None)
            self._deleted_observations[key] = revision
        for key in stale_gaps:
            del self.gaps[key]
            self._changed_gaps.pop(key, None)
            self._deleted_gaps[key] = revision
        for item in retained_gap_pieces:
            key = (track_id, int(item.start_pts), int(item.end_pts))
            value = replace(item, revision=revision)
            self.gaps[key] = value
            self._changed_gaps[key] = value
            self._deleted_gaps.pop(key, None)
        for key, item in observations.items():
            existing = self.observations.get(key)
            if existing is not None and existing.source == 'manual':
                continue
            value = replace(item, pts=key[1], revision=revision)
            self.observations[key] = value
            self._changed_observations[key] = value
            self._deleted_observations.pop(key, None)
        for key, item in gaps.items():
            value = replace(item, revision=revision)
            self.gaps[key] = value
            self._changed_gaps[key] = value
            self._deleted_gaps.pop(key, None)
        track = replace(self.tracks[track_id], revision=revision)
        self.tracks[track_id] = track
        self._changed_tracks[track_id] = track
        return PropagationResult(
            result.request_id, result.generation, revision,
            observations=tuple(
                self.observations[key] for key in observations
                if key in self.observations),
            gaps=tuple(self.gaps[key] for key in gaps),
            failures=result.failures)

    def delete_gap(self, track_id, start_pts, end_pts):
        key = (track_id, int(start_pts), int(end_pts))
        if key not in self.gaps:
            return False
        revision = self._advance()
        del self.gaps[key]
        self._changed_gaps.pop(key, None)
        self._deleted_gaps[key] = revision
        track = self.tracks.get(track_id)
        if track is not None:
            track = replace(track, revision=revision)
            self.tracks[track_id] = track
            self._changed_tracks[track_id] = track
        return True

    def review(self, track_id, pts, review_state):
        if review_state not in ('accepted', 'pending', 'rejected'):
            raise ValueError('invalid review state: %s' % review_state)
        key = (track_id, int(pts))
        current = self.observations[key]
        if current.source != 'tracker':
            return current
        revision = self._advance()
        value = replace(
            current, review_state=review_state, anchor=False,
            revision=revision)
        self.observations[key] = value
        self._changed_observations[key] = value
        return value

    def promote_to_manual(self, track_id, pts):
        current = self.materialize_one(track_id, pts)
        if current is None:
            return None
        return self.upsert_manual(
            track_id, pts, current.observation.geometry,
            keypoints=current.observation.keypoints,
            present=current.observation.present)

    def delete_occurrence(self, track_id, pts):
        key = (track_id, int(pts))
        if key in self.observations:
            revision = self._advance()
            del self.observations[key]
            self._changed_observations.pop(key, None)
            self._deleted_observations[key] = revision
            if not any(item.track_id == track_id
                       for item in self.observations.values()):
                self.delete_track(track_id)
            return
        if self.materialize_one(track_id, pts) is not None:
            self.upsert_manual(track_id, pts, None, present=False)

    def delete_track(self, track_id):
        if track_id not in self.tracks:
            return
        revision = self._advance()
        del self.tracks[track_id]
        self._changed_tracks.pop(track_id, None)
        self._deleted_tracks[track_id] = revision
        for key in tuple(self.observations):
            if key[0] == track_id:
                del self.observations[key]
                self._changed_observations.pop(key, None)
                self._deleted_observations[key] = revision
        for key in tuple(self.gaps):
            if key[0] == track_id:
                del self.gaps[key]
                self._changed_gaps.pop(key, None)
                self._deleted_gaps[key] = revision

    def set_frame_verified(self, pts, verified):
        revision = self._advance()
        state = FrameStateRecord(int(pts), bool(verified), revision)
        self.frame_states[int(pts)] = state
        self._changed_frames[int(pts)] = state
        return state

    def materialize_one(self, track_id, pts):
        track = self.tracks.get(track_id)
        if track is None:
            return None
        exact = self.observations.get((track_id, int(pts)))
        if exact is not None and exact.review_state != 'rejected':
            if not exact.present:
                return None
            render = ('pending' if exact.review_state == 'pending'
                      else 'exact')
            return MaterializedTrack(track, exact, render)
        if any(item.track_id == track_id
               and item.start_pts <= int(pts) <= item.end_pts
               for item in self.gaps.values()):
            return None
        if track.shape_type != 'rectangle':
            return None
        anchors = sorted(
            (item for item in self.observations.values()
             if item.track_id == track_id and item.source == 'manual'
             and item.review_state == 'accepted' and item.anchor),
            key=lambda item: item.pts)
        left = next((item for item in reversed(anchors)
                     if item.pts < pts), None)
        right = next((item for item in anchors if item.pts > pts), None)
        if left is None or right is None:
            return None
        interpolated = interpolate_rectangle(left, right, int(pts))
        if interpolated is None:
            return None
        return MaterializedTrack(track, interpolated, 'interpolation')

    def materialize(self, pts):
        values = []
        for track_id in self.tracks:
            value = self.materialize_one(track_id, int(pts))
            if value is not None:
                values.append(value)
        return tuple(values)

    def build_save_request(self, project_path):
        target = self.revision
        tracks = tuple(
            value for value in self._changed_tracks.values()
            if value.revision <= target)
        observations = tuple(
            value for value in self._changed_observations.values()
            if value.revision <= target)
        frames = tuple(
            value for value in self._changed_frames.values()
            if value.revision <= target)
        gaps = tuple(
            value for value in self._changed_gaps.values()
            if value.revision <= target)
        deleted_observations = tuple(
            key for key, revision in self._deleted_observations.items()
            if revision <= target)
        deleted_tracks = tuple(
            key for key, revision in self._deleted_tracks.items()
            if revision <= target)
        deleted_gaps = tuple(
            key for key, revision in self._deleted_gaps.items()
            if revision <= target)
        touched = set(item.track_id for item in observations)
        touched.update(item.track_id for item in tracks)
        touched.update(key[0] for key in deleted_observations)
        touched.update(item.track_id for item in gaps)
        touched.update(key[0] for key in deleted_gaps)
        classes = (tuple(self.classes)
                   if self._classes_changed_revision is not None
                   and self._classes_changed_revision <= target else ())
        return VideoSaveRequest(
            project_path, self.durable_revision, target,
            tracks=tracks, observations=observations,
            deleted_observations=deleted_observations,
            deleted_tracks=deleted_tracks, frame_states=frames,
            classes=classes, touched_tracks=tuple(sorted(touched)),
            gaps=gaps, deleted_gaps=deleted_gaps)

    def mark_saved(self, target_revision):
        target_revision = int(target_revision)
        self.durable_revision = target_revision
        self._changed_tracks = {
            key: value for key, value in self._changed_tracks.items()
            if value.revision > target_revision}
        self._changed_observations = {
            key: value for key, value in self._changed_observations.items()
            if value.revision > target_revision}
        self._changed_frames = {
            key: value for key, value in self._changed_frames.items()
            if value.revision > target_revision}
        self._changed_gaps = {
            key: value for key, value in self._changed_gaps.items()
            if value.revision > target_revision}
        self._deleted_observations = {
            key: value for key, value in self._deleted_observations.items()
            if value > target_revision}
        self._deleted_tracks = {
            key: value for key, value in self._deleted_tracks.items()
            if value > target_revision}
        self._deleted_gaps = {
            key: value for key, value in self._deleted_gaps.items()
            if value > target_revision}
        if (self._classes_changed_revision is not None
                and self._classes_changed_revision <= target_revision):
            self._classes_changed_revision = None
